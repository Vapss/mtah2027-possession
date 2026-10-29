"""The safety-net entry (DECISIONS 25) as one command: `smooth50` with the ball gaps carried.

    python tools/backup.py                         # -> submissions/backup.csv
    python tools/backup.py --workdir runs/x --out runs/x/backup.csv

The chain, every step from the licensed bundle and none of it hand-made:

    starter/baseline.py --window 50 -> tools/ball_gaps.py -> tools/onehot.py
        -> tools/assemble.py (the only writer, AGENTS.md rule 2) -> the organisers' validator

It lives here rather than only in the Makefile so that it runs the same way on every platform --
`make` is not on a stock Windows machine -- and so that `tools/repro.py` (#15) can build it twice.
Each step runs as its own process with this interpreter, exactly as the Makefile would run it.
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
RUNS = REPO_ROOT / "runs"
DEFAULT_WORKDIR = RUNS / "backup"
DEFAULT_OUT = REPO_ROOT / "submissions" / "backup.csv"


def _run(args: list[object]) -> None:
    """Run one step with this interpreter; a failure names the exact command and its output."""
    command = [str(part) for part in args]
    done = subprocess.run([sys.executable, *command], cwd=REPO_ROOT, text=True, capture_output=True)
    if done.returncode != 0:
        detail = (done.stderr + done.stdout).strip()
        raise RuntimeError(f"{' '.join(command)} exited {done.returncode}:\n{detail}")


def _check_workdir(workdir: Path) -> Path:
    """The workdir is wiped, so it must be a strict subdirectory of runs/ (gitignored scratch)."""
    resolved = workdir.resolve()
    if resolved == RUNS or RUNS not in resolved.parents:
        raise ValueError(f"workdir must be a subdirectory of runs/, got {workdir}")
    return resolved


def build(workdir: Path = DEFAULT_WORKDIR, out: Path = DEFAULT_OUT) -> Path:
    """Build the backup entry from scratch in `workdir` and write it to `out`."""
    workdir = _check_workdir(workdir)
    shutil.rmtree(workdir, ignore_errors=True)
    (workdir / "artifacts").mkdir(parents=True)
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
    print(f"wrote {out.resolve().relative_to(REPO_ROOT).as_posix()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
