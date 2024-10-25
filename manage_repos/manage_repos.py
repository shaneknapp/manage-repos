import re
import shutil
import subprocess
import sys
import time
import os


def _iter_repos(args):
    """
    Iterate over the repositories in the config file.

    Returns the name, path, and URL of the repository.
    """
    with open(args.config) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            name = line.split("/")[-1].replace(".git", "")
            path = os.path.join(args.destination, name)

            # clone behavior is a little different than other commands when
            # checking for existing repos
            if args.command == "clone":
                if os.path.exists(path):
                    print(f"Skipping {name} as it already exists in {path}")
                    continue
            else:
                if not os.path.exists(path):
                    print(f"Skipping {name} as it doesn't exist at {path}")
                    continue
            yield name, path, line


def branch(args):
    """
    Create a new feature branch in all repositories in the config file.
    """
    errors = list()
    for name, path, _ in _iter_repos(args):
        print(f"Creating and switching to feature branch {args.branch} in {name}")

        try:
            subprocess.check_call(["git", "switch", "-c", args.branch], cwd=path)
        except subprocess.CalledProcessError as e:
            error = f"Error creating branch {args.branch} in {name} in {path}: {e}"
            print(error)
            errors.append(error)
            print()
            continue

        print()

    if errors is not None:
        return errors


def clone(args):
    """
    Clone all repositories in the config file to the destination directory.

    Optionally set the the user's GitHub fork as a remote, which defaults to
    'origin'.
    """
    if args.set_remote and args.github_user is None:
        print(
            "Remote cannot be updated, please specify a GitHub username "
            + "for the forked repository to continue."
        )
        sys.exit(1)

    if not os.path.exists(args.destination):
        os.makedirs(args.destination)
        print(f"Created destination directory {args.destination}")

    errors = list()
    for name, path, repo in _iter_repos(args):
        print(f"Cloning {name} from {repo} to {path}.")
        try:
            subprocess.check_call(["git", "clone", repo, path])
        except subprocess.CalledProcessError as e:
            error = f"Error cloning {name} from {repo} to {path}: {e}"
            print(error)
            errors.append(error)
            print()
            continue

        if args.set_remote:
            print()
            print("Updating remotes and adding fork.")
            print("Renaming origin to 'upstream'.")
            try:
                subprocess.check_call(
                    ["git", "remote", "rename", "origin", "upstream"], cwd=path
                )
            except subprocess.CalledProcessError as e:
                error = f"Error renaming origin to upstream in {name} in {path}: {e}"
                print(error)
                errors.append(error)
                print()
                continue

            original_remote = re.search(".+:(.+?)/.*$", repo).group(1)
            repo = repo.replace(original_remote, args.github_user)
            print(f"Setting remote of fork to: {repo}")
            try:
                subprocess.check_call(
                    ["git", "remote", "add", args.set_remote, repo], cwd=path
                )
            except subprocess.CalledProcessError as e:
                error = f"Error setting remote in {name} in {path}: {e}"
                print(error)
                errors.append(error)
                print()
                continue

        subprocess.check_call(["git", "remote", "-v"], cwd=path)
        print()

    if errors is not None:
        return errors


def merge(args):
    """
    Using the gh cli tool, merge the latest pull request in all repositories in
    the config file.
    """
    errors = list()
    for name, path, repo in _iter_repos(args):
        try:
            limit = 1
            pr_list = subprocess.run(
                [
                    "gh",
                    "pr",
                    "list",
                    f"-L{limit}",
                ],
                cwd=path,
                capture_output=True,
                text=True,
            )
        except subprocess.CalledProcessError as e:
            error = f"Error getting open pull requests from {name}: {e}"
            print(error)
            errors.append(error)
            print()
            continue

        pr_number = pr_list.stdout.split("\t")[0]
        print(f"Merging PR #{pr_number} to base branch in {name}.")
        try:
            owner_and_repo = re.search(".+:(.+?).git$", repo).group(1)
            command = [
                "gh",
                "pr",
                "merge",
                f"{pr_number}",
                f"-R{owner_and_repo}",
            ]
            if args.body is not None:
                command.append(f"-b {args.body}")
            if args.delete:
                command.append("-d")
            match args.strategy:
                case "merge":
                    command.append("-m")
                case "rebase":
                    command.append("-r")
                case "squash":
                    command.append("-s")

            subprocess.check_call(command)
        except subprocess.CalledProcessError as e:
            error = f"Error merging pull request {pr_number} in {name}: {e}"
            print(error)
            errors.append(error)
            print()
            continue


def patch(args):
    """
    Apply a git patch to all repositories in the config file.
    """
    if not os.path.exists(args.patch):
        print(f"Patch file {args.patch} does not exist.")
        sys.exit(1)

    errors = list()
    for name, path, _ in _iter_repos(args):
        print(f"Applying patch to {name} in {path}")
        try:
            shutil.copy(args.patch, path)
            subprocess.check_call(["git", "apply", args.patch], cwd=path)
        except subprocess.CalledProcessError as e:
            error = f"Error applying patch {args.patch} in {path}: {e}"
            print(error)
            errors.append(error)
            print()
            continue

        os.remove(os.path.join(path, args.patch))
        print()

    if errors is not None:
        return errors


def pr(args):
    """
    Using the Github CLI tool (gh), push a feature branch and create a PR.
    """
    errors = list()
    for name, path, repo in _iter_repos(args):
        try:
            branch = (
                subprocess.run(
                    ["git", "branch", "--show-current"], cwd=path, capture_output=True
                )
                .stdout.decode("utf-8")
                .strip()
            )
        except subprocess.CalledProcessError as e:
            error = f"Unable to get branch from {name}: {e}."
            print(error)
            errors.append(error)
            print()
            continue

        if branch == "main":
            error = f"Currently on branch 'main' in {name}. Not creating a PR "
            +"for this repository."
            print(error)
            errors.append(error)
            continue
        else:
            print(f"Creating a pull request for {name} on branch {branch}")

            owner_and_repo = re.search(".+:(.+?).git$", repo).group(1)
            try:
                command = [
                    "gh",
                    "pr",
                    "new",
                    f"-t {args.title}",
                    f"-R{owner_and_repo}",
                    f"-H{args.github_user}:{branch}",
                    f"-B{args.branch_default}",
                ]
                if args.body is not None:
                    command.append(f"-b {args.body}")
                subprocess.run(command)
            except subprocess.CalledProcessError as e:
                error = f"Unable to create pull request for {name}: {e}"
                print(error)
                errors.append(error)
                print()
                continue

            # sleep for 2 seconds to keep us from being rate limited
            time.sleep(2)


def push(args):
    """
    Push all repositories in the config file to a remote.
    """
    errors = list()
    for name, path, _ in _iter_repos(args):
        print(f"Pushing {name}/{args.branch} to {args.remote}")
        try:
            subprocess.check_call(["git", "push", args.remote, args.branch], cwd=path)
        except subprocess.CalledProcessError as e:
            error = f"Error pushing {name}/{args.branch} to {args.remote}: {e}"
            print(error)
            errors.append(error)
            print()
            continue
        print()

    if errors is not None:
        return errors


def stage(args):
    """
    Stage all repositories in the config file by adding all changes and
    committing them.
    """
    errors = list()
    for name, path, repo in _iter_repos(args):
        for file in args.files:
            if file == ".":
                changed_files = subprocess.run(
                    ["git", "status", "--porcelain"],
                    cwd=path,
                    capture_output=True,
                    text=True,
                )
                print(f"Adding all changes in {name} to staging:")
                print(changed_files.stdout.strip())
            else:
                print(f"Adding {file} to staging in {name}.")

            try:
                subprocess.check_call(["git", "add", file], cwd=path)
            except subprocess.CalledProcessError as e:
                error = f"Error adding {name} to staging: {e}"
                print(error)
                errors.append(error)
                print()
                continue

        print(f"Committing changes in {name} with message {args.message}.")
        try:
            subprocess.check_call(
                ["git", "commit", "-m", f"{args.message}", file], cwd=path
            )
        except subprocess.CalledProcessError as e:
            error = f"Error adding {name} to staging: {e}"
            print(error)
            errors.append(error)
            print()
            continue

        print()

    if errors is not None:
        return errors


def sync(args):
    """
    Sync all repositories in the config file to the destination directory using
    rebase.

    Optionally push to the user's fork.
    """
    errors = list()
    for name, path, repo in _iter_repos(args):
        print(f"Syncing {name} from {repo} to {path}.")
        subprocess.check_call(["git", "switch", args.branch_default], cwd=path)

        try:
            subprocess.check_call(["git", "fetch", "--all", "--prune"], cwd=path)
        except subprocess.CalledProcessError as e:
            error = f"Error fetching {name}: {e}"
            error += f"\nPlease check to see if your fork of of {name} exists."
            print(error)
            errors.append(error)
            print()
            continue

        try:
            subprocess.check_call(
                ["git", "rebase", "--stat", "upstream/" + args.branch_default], cwd=path
            )
        except subprocess.CalledProcessError as e:
            error = f"Error rebasing {name} to {path}: {e}"
            print(error)
            errors.append(error)
            print()
            continue

        if args.push:
            print(f"Pushing {name} to {args.remote}.")
            try:
                subprocess.check_call(
                    ["git", "push", args.remote, args.branch_default], cwd=path
                )
            except subprocess.CalledProcessError as e:
                error = (
                    f"Error pushing {name} to {args.remote}/"
                    + f"{args.branch_default}: {e}"
                )
                print(error)
                errors.append(error)
                print()
                continue

        print()

    if errors is not None:
        return errors
