import argparse
import re
import sys
import toml

from pathlib import Path

from . import manage_repos


def check_config(config):
    """
    Check all entries in the config file to confirm they are in the proper
    format:

    git@github.com:<user or org>/<repo name>.git
    """
    with open(config) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue

            if not re.match(
                "^git@github.com:[a-zA-Z0-9\.\-\_]+/[a-zA-Z0-9\.\-\_]+\.git$", line
            ):
                print(f"Malformed entry in {config}: {line}. Exiting.")
                sys.exit(1)


def main():
    version = "unknown"
    pyproject_toml_file = Path(__file__).parent.parent / "pyproject.toml"
    if pyproject_toml_file.exists() and pyproject_toml_file.is_file():
        data = toml.load(pyproject_toml_file)
        # check project.version
        if "project" in data and "version" in data["project"]:
            version = data["project"]["version"]

    argparser = argparse.ArgumentParser()
    subparsers = argparser.add_subparsers(
        dest="command",
        help="Command to execute. Additional help is available for each command.",
    )

    argparser.add_argument(
        "-c",
        "--config",
        default="repos.txt",
        help="Path to the file containing list of repositories to operate on. "
        + "Defaults to repos.txt located in the current working directory.",
        type=str,
    )
    argparser.add_argument(
        "-d",
        "--destination",
        default=".",
        help="Location on the filesystem of the directory containing the "
        + "managed repositories. Defaults to the current working directory.",
        type=str,
    )
    argparser.add_argument(
        "--version",
        action="version",
        version=f"{version}",
    )

    branch_parser = subparsers.add_parser(
        "branch",
        description="Create a new feature branch in the managed repositories.",
    )
    branch_parser.add_argument(
        "-b",
        "--branch",
        help="Name of the feature branch to create.",
        required=True,
        type=str,
    )

    clone_parser = subparsers.add_parser(
        "clone",
        description="Clone repositories in the config file and "
        + "optionally set a remote for a fork. If a repository sub-directory "
        + "does not exist, it will be created.",
    )
    clone_parser.add_argument(
        "-s",
        "--set-remote",
        const="origin",
        nargs="?",
        help="Set the user's GitHub fork as a remote. Defaults to '%(const)s'.",
        type=str,
    )
    clone_parser.add_argument(
        "-g",
        "--github-user",
        help="The GitHub username of the fork to set in the remote. Required "
        + "if --set-remote is used.",
        type=str,
    )

    merge_parser = subparsers.add_parser(
        "merge",
        description="Using the gh tool, merge the most recent pull "
        + "request in the managed repositories. Before using this command, "
        + "you must authenticate with gh to ensure that you have the correct "
        + "permission for the required scopes.",
    )
    merge_parser.add_argument(
        "-b",
        "--body",
        help="The commit message to apply to the merge (optional).",
        type=str,
    )
    merge_parser.add_argument(
        "-d",
        "--delete",
        action="store_true",
        help="Delete your local feature branch after the pull request is "
        + "merged (optional).",
    )
    merge_parser.add_argument(
        "-s",
        "--strategy",
        choices=["merge", "rebase", "squash"],
        default="merge",
        help="The pull request merge strategy to use, defaults to '%(default)s'.",
        type=str,
    )

    patch_parser = subparsers.add_parser(
        "patch",
        description="Apply a git patch to managed repositories.",
    )
    patch_parser.add_argument(
        "-p",
        "--patch",
        help="Path to the patch file to apply.",
        required=True,
        type=str,
    )

    pr_parser = subparsers.add_parser(
        "pr",
        description="Using the gh tool, create a pull request after pushing.",
    )
    pr_parser.add_argument(
        "-t",
        "--title",
        help="Title of the pull request.",
        required=True,
        type=str,
    )
    pr_parser.add_argument(
        "-b",
        "--body",
        help="Body of the pull request (optional).",
        type=str,
    )
    pr_parser.add_argument(
        "-B",
        "--branch-default",
        default="main",
        help="Default remote branch that the pull requests will be merged "
        + "to. This is optional and defaults to '%(default)s'.",
        type=str,
    )
    pr_parser.add_argument(
        "-g",
        "--github-user",
        help="The GitHub username used to create the pull request.",
        required=True,
        type=str,
    )

    push_parser = subparsers.add_parser(
        "push",
        description="Push managed repositories to a remote.",
    )
    push_parser.add_argument(
        "-b",
        "--branch",
        help="Name of the branch to push.",
        required=True,
        type=str,
    )
    push_parser.add_argument(
        "-r",
        "--remote",
        default="origin",
        help="Name of the remote to push to.  This is optional and defaults "
        + "to '%(default)s'.",
        type=str,
    )

    stage_parser = subparsers.add_parser(
        "stage",
        description="Stage changes in managed repositories. This performs a "
        + "git add and commit.",
    )
    stage_parser.add_argument(
        "-f",
        "--files",
        nargs="+",
        default=["."],
        help="Space-delimited list of files to stage in the repositories. "
        + "Optional, and if left blank will default to all modified files in "
        + "the directory."
    )
    stage_parser.add_argument(
        "-m",
        "--message",
        help="Commit message to use for the changes.",
        required=True,
        type=str,
    )

    sync_parser = subparsers.add_parser(
        "sync",
        description="Sync managed repositories to the latest version using "
        + "'git rebase'. Optionally push to a remote fork.",
    )
    sync_parser.add_argument(
        "-b",
        "--branch-default",
        default="main",
        help="Default remote branch to sync to. This is optional and "
        + "defaults to '%(default)s'.",
        type=str,
    )
    sync_parser.add_argument(
        "-u",
        "--upstream",
        default="upstream",
        help="Name of the parent remote to sync from. This is optional and "
        + "defaults to '%(default)s'.",
        type=str,
    )
    sync_parser.add_argument(
        "-p",
        "--push",
        action="store_true",
        help="Push the locally synced repo to a remote fork.",
    )
    sync_parser.add_argument(
        "-r",
        "--remote",
        default="origin",
        help="The name of the remote fork to push to.  This is optional and "
        + "defaults to '%(default)s'.",
    )

    args = argparser.parse_args()
    print(args)

    check_config(args.config)

    errors = []
    if args.command == "branch":
        errors.append(manage_repos.branch(args))
    elif args.command == "clone":
        errors.append(manage_repos.clone(args))
    elif args.command == "merge":
        errors.append(manage_repos.merge(args))
    elif args.command == "patch":
        errors.append(manage_repos.patch(args))
    elif args.command == "pr":
        errors.append(manage_repos.pr(args))
    elif args.command == "push":
        errors.append(manage_repos.push(args))
    elif args.command == "stage":
        errors.append(manage_repos.stage(args))
    elif args.command == "sync":
        errors.append(manage_repos.sync(args))
    else:
        argparser.print_help()

    if any(errors):
        print("\nThe following errors occurred during execution:")
        for error in errors:
            for e in error:
                print(e)


if __name__ == "__main__":
    main()
