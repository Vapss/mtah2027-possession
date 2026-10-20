"""Fail if a licensed asset, or an oversized file, is about to enter git.

The dataset is licensed for the competition only and the submission repository is public, so a
committed bundle is both a rule violation and a redistribution. `.gitignore` covers `data/`,
but downloaded archives land next to the repository and are untracked, which is exactly one
`git add -A` away from being published. This guard is the thing that notices.

    python tools/guard_data.py                       # every staged and untracked file
    python tools/guard_data.py path/to/file.zip      # explicit files (pre-commit mode)

Exit status 1 means "do not commit".
"""

from __future__ import annotations

import argparse
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

BANNED_SUFFIXES = {
    ".zip",
    ".tar",
    ".gz",
    ".tgz",
    ".7z",
    ".rar",
    ".mp4",
    ".mov",
    ".mkv",
    ".avi",
    ".webm",
    ".parquet",
    ".npy",
    ".npz",
    ".feather",
}
BANNED_PREFIXES = ("data/",)
ALLOWED_PATHS = {"data/README.md"}
DEFAULT_MAX_MB = 5.0


def relative(path: Path) -> str:
    """Repo-relative POSIX path, or the absolute path when it lives outside the repo."""
    resolved = path.resolve()
    try:
        return resolved.relative_to(REPO_ROOT).as_posix()
    except ValueError:
        return resolved.as_posix()


def candidates_from_git() -> list[Path]:
    """Files git would commit: staged, plus untracked-but-not-ignored."""
    completed = subprocess.run(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    return [REPO_ROOT / line for line in completed.stdout.splitlines() if line.strip()]


def offences(paths: list[Path], max_mb: float = DEFAULT_MAX_MB) -> list[str]:
    """Every reason these paths must not be committed."""
    found = []
    for path in paths:
        if not path.is_file():
            continue
        name = relative(path)
        if name in ALLOWED_PATHS:
            continue
        if name.startswith(BANNED_PREFIXES):
            found.append(f"{name}: lives under data/ -- the match assets are not redistributable")
            continue
        if path.suffix.lower() in BANNED_SUFFIXES:
            found.append(f"{name}: {path.suffix.lower()} files are never committed here")
            continue
        size_mb = path.stat().st_size / 1e6
        if size_mb > max_mb:
            found.append(f"{name}: {size_mb:.1f} MB exceeds the {max_mb:.0f} MB limit")
    return found


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Block licensed data and oversized files from git")
    parser.add_argument(
        "files", nargs="*", help="files to check (default: everything git would commit)"
    )
    parser.add_argument("--max-mb", type=float, default=DEFAULT_MAX_MB, help="size limit per file")
    args = parser.parse_args(argv)

    paths = [Path(item) for item in args.files] if args.files else candidates_from_git()
    found = offences(paths, args.max_mb)

    if found:
        print("refusing to commit -- these files must not enter the repository:")
        for problem in found:
            print(f"  - {problem}")
        print("\nThe dataset stays local (see data/README.md). Keep archives out of git;")
        print("they are already covered by .gitignore and .git/info/exclude.")
        return 1

    print(f"data guard ok: {len(paths)} path(s) checked, nothing redistributable")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
