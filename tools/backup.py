"""The safety-net entry (DECISIONS 25) as one command: `smooth50` with the ball gaps carried.

    python tools/backup.py                         # -> submissions/backup.csv
    python tools/backup.py --workdir runs/x --out runs/x/backup.csv

The chain, every step from the licensed bundle and none of it hand-made:

    starter/baseline.py --window 50 -> tools/ball_gaps.py -> tools/onehot.py
        -> tools/assemble.py (the only writer, AGENTS.md rule 2) -> the organisers' validator

It lives here rather than only in the Makefile so that it runs the same way on every platform --
`make` is not on a stock Windows machine -- and so that `tools/repro.py` (#15) can build it twice.
Each step runs as its own process with this interpreter, through the same runner F0a uses, and its
output is shown as it runs.
"""

from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from tools.f0a import _run  # noqa: E402

# Resolved: if runs/ is a symlink or a junction to another disk, a workdir inside it resolves there
# too, and comparing against the unresolved path would refuse every workdir.
RUNS = (REPO_ROOT / "runs").resolve()
DEFAULT_WORKDIR = RUNS / "backup"
DEFAULT_OUT = REPO_ROOT / "submissions" / "backup.csv"


def check_workdir(workdir: Path) -> Path:
    """The workdir is wiped, so it must be a strict subdirectory of runs/ (gitignored scratch)."""
    resolved = workdir.resolve()
    if resolved == RUNS or RUNS not in resolved.parents:
        raise ValueError(f"workdir must be a subdirectory of runs/, got {workdir}")
    return resolved


def wipe(workdir: Path) -> Path:
    """Delete and recreate `workdir`; a file that cannot be deleted is an error, not a shrug."""
    workdir = check_workdir(workdir)
    if workdir.exists():
        shutil.rmtree(workdir)  # no ignore_errors: a locked file must say so (Windows, editors)
    workdir.mkdir(parents=True)
    return workdir


def build(workdir: Path = DEFAULT_WORKDIR, out: Path = DEFAULT_OUT) -> Path:
    """Build the backup entry from scratch in `workdir` and write it to `out`."""
    workdir = wipe(workdir)
    # Every step runs with cwd=REPO_ROOT, so a relative `out` must be resolved here, against the
    # caller's directory, or the steps and the caller would disagree on where the file is.
    out = out.resolve()
    labels = workdir / "baseline_smooth50.csv"
    filled = workdir / "smooth50_gaps.csv"
    artifact = workdir / "artifacts" / "backup.csv"

    _run(["starter/baseline.py", "--window", 50, "--out", workdir])
    _run(["tools/ball_gaps.py", labels, filled])
    _run(["tools/onehot.py", filled, "-o", artifact])
    _run(
        [
            "tools/assemble.py",
            "--artifacts",
            artifact.parent,
            "-o",
            out,
            "--json",
            workdir / "summary.json",
        ]
    )
    _run(["evaluation/validate_submission.py", out])
    return out


def shown(path: Path) -> str:
    """A repository-relative POSIX name when the path is inside the repository, else the path."""
    try:
        return path.resolve().relative_to(REPO_ROOT).as_posix()
    except ValueError:
        return str(path)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build the safety-net entry (DECISIONS 25)")
    parser.add_argument(
        "--workdir",
        type=Path,
        default=DEFAULT_WORKDIR,
        help="scratch directory under runs/, wiped first",
    )
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT, help="submission to write")
    args = parser.parse_args(argv)
    try:
        out = build(args.workdir, args.out)
    except (OSError, ValueError, RuntimeError) as problem:
        print(f"backup failed: {problem}", file=sys.stderr)
        return 1
    print(f"wrote {shown(out)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
