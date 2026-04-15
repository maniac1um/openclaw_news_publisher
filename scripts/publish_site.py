import argparse
from pathlib import Path
import subprocess


def run_git(args: list[str]) -> str:
    proc = subprocess.run(
        ["git", *args],
        check=True,
        capture_output=True,
        text=True,
    )
    return proc.stdout.strip()


def is_git_ignored(pathspec: str) -> bool:
    proc = subprocess.run(
        ["git", "check-ignore", "-q", pathspec],
        check=False,
        capture_output=True,
        text=True,
    )
    return proc.returncode == 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Publish rendered report into site pipeline.")
    parser.add_argument("--rendered", required=True, help="Rendered report JSON path")
    parser.add_argument("--remote", default="origin", help="Git remote name for optional push")
    parser.add_argument("--branch", default="main", help="Git branch for optional push")
    parser.add_argument("--push", action="store_true", help="Push commit after creating it")
    args = parser.parse_args()

    rendered = Path(args.rendered)
    if not rendered.exists():
        raise FileNotFoundError(f"Rendered payload not found: {rendered}")

    run_git(["rev-parse", "--is-inside-work-tree"])
    repo_root = Path(run_git(["rev-parse", "--show-toplevel"]))
    try:
        rendered_rel = str(rendered.resolve().relative_to(repo_root.resolve()).as_posix())
    except ValueError:
        rendered_rel = str(rendered.resolve().as_posix())

    # Runtime-rendered report JSON is often intentionally ignored in git.
    # In that case we treat publish as a no-op instead of failing ingestion.
    if is_git_ignored(rendered_rel):
        print(f"skip git publish for ignored path: {rendered_rel}")
        return 0

    run_git(["add", rendered_rel])
    staged = run_git(["diff", "--cached", "--name-only"])
    if not staged:
        print(f"no git changes to commit for: {rendered_rel}")
        return 0

    commit_message = f"publish report {rendered.name}"
    run_git(["commit", "-m", commit_message])
    print(f"created git commit for: {rendered_rel}")

    if args.push:
        run_git(["push", args.remote, f"HEAD:{args.branch}"])
        print(f"pushed to {args.remote}/{args.branch}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
