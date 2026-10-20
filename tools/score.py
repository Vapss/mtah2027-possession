"""Run the official scorer and record the result in a ledger.

The scorer is `evaluation/run_evaluation.py`, unmodified: this wrapper only adds the two
things a team needs around it.

1. `--bootstrap` on by default, because the public ground truth is five minutes and a delta
   inside the noise band is not an improvement.
2. One line per run in `runs/ledger.jsonl` with the git commit, a hash of the config, and
   every scoreboard row. That is what stops "which version produced 0.43?" from being a
   conversation.

    python tools/score.py                                  # score evaluation/results/*
    python tools/score.py --results artifacts --note "dead ball from smart tagging"

Nothing here reads the private ground truth, and nothing here can: `--gt` is forwarded
verbatim and `private` only works on the organisers' copy.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parent.parent
SCORER = REPO_ROOT / "evaluation" / "run_evaluation.py"
LEDGER = REPO_ROOT / "runs" / "ledger.jsonl"


def git_line(*args: str) -> str:
    """A git command's stdout, or "unknown" outside a work tree."""
    try:
        return subprocess.run(
            ["git", *args], cwd=REPO_ROOT, capture_output=True, text=True, check=True
        ).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return "unknown"


def config_fingerprint(path: str | Path | None) -> str:
    """Stable hash of the config actually used, so two runs can be compared honestly."""
    if path is None or not Path(path).is_file():
        return "none"
    digest = hashlib.sha256(Path(path).read_bytes()).hexdigest()
    return digest[:12]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Score submissions and record the run")
    parser.add_argument(
        "--results",
        default=str(REPO_ROOT / "evaluation" / "results"),
        help="directory of submission CSVs to score",
    )
    parser.add_argument(
        "--gt", default="public", help="'public', 'private' (organisers only), or a path"
    )
    parser.add_argument(
        "--bootstrap", type=int, default=1000, help="segment-bootstrap draws (0 = off)"
    )
    parser.add_argument(
        "--out", default=str(REPO_ROOT / "runs" / "score"), help="where the scoreboard goes"
    )
    parser.add_argument("--config", default=None, help="config file to fingerprint in the ledger")
    parser.add_argument("--note", default="", help="free-text note for the ledger")
    parser.add_argument("--ledger", default=str(LEDGER), help="JSONL ledger to append to")
    parser.add_argument("--no-ledger", action="store_true", help="score without recording")
    args = parser.parse_args(argv)

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    command = [
        sys.executable,
        str(SCORER),
        "--gt",
        str(args.gt),
        "--results",
        str(args.results),
        "--out",
        str(out),
    ]
    if args.bootstrap:
        command += ["--bootstrap", str(args.bootstrap)]

    completed = subprocess.run(command, cwd=REPO_ROOT, text=True, capture_output=True)
    sys.stdout.write(completed.stdout)
    sys.stderr.write(completed.stderr)
    if completed.returncode != 0:
        return completed.returncode

    scoreboard = out / "scoreboard.csv"
    if not scoreboard.is_file():
        print(f"scorer produced no {scoreboard}; nothing recorded", file=sys.stderr)
        return 1

    board = pd.read_csv(scoreboard)
    entry = {
        "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "git_commit": git_line("rev-parse", "HEAD"),
        "git_dirty": bool(git_line("status", "--porcelain")),
        "git_branch": git_line("rev-parse", "--abbrev-ref", "HEAD"),
        "gt": str(args.gt),
        "bootstrap": args.bootstrap,
        "results": str(args.results),
        "config_sha": config_fingerprint(args.config),
        "note": args.note,
        "submissions": board.to_dict(orient="records"),
    }

    if not args.no_ledger:
        ledger = Path(args.ledger)
        ledger.parent.mkdir(parents=True, exist_ok=True)
        with ledger.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(entry) + "\n")
        best = board.sort_values("spell_f1_mean", ascending=False).iloc[0]
        print(
            f"ledger += {best['submission']}  spellF1 {best['spell_f1_mean']:.4f}  "
            f"macroF1 {best['macro_f1']:.4f}  -> {ledger}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
