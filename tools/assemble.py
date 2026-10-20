"""The only code in this repository that writes the graded submission file.

Every job emits the same per-frame intermediate table (see tools/contract.py):

    frame,p_home,p_away,p_dead,confidence

and this assembler combines them into frame,label. One writer means format failures have
exactly one place to live, and it means a teammate can iterate on their own signal without
touching the deliverable.

    python tools/assemble.py                         # artifacts/*.csv -> submissions/submission.csv
    python tools/assemble.py --x-outside-halves      # abstain outside the two playing halves

Combination rule: each artifact votes with its `confidence` column (or an explicit
`--weight name=value`), so a job that is sure counts more than one that is not. If every
weight for a frame is zero the frame falls back to an unweighted mean -- an artifact that
abstains everywhere must not turn the output into a division by zero.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

import numpy as np
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

import games  # noqa: E402
from tools.contract import (  # noqa: E402
    ARTIFACT_COLUMNS,
    N_FRAMES,
    PROB_COLUMNS,
    check_artifact,
    check_submission,
)

DEFAULT_ARTIFACTS = REPO_ROOT / "artifacts"
DEFAULT_OUT = REPO_ROOT / "submissions" / "submission.csv"
DEFAULT_CONFIG = REPO_ROOT / "configs" / "assemble_default.json"


def load_config(path: str | Path | None) -> dict:
    """Read the assembler config. A missing file is not an error: the CLI default is the default."""
    if path is None:
        return {}
    resolved = Path(path)
    if not resolved.is_file():
        return {}
    return json.loads(resolved.read_text(encoding="utf-8"))


def find_artifacts(directory: str | Path) -> list[Path]:
    """Every artifact CSV in a directory, in a stable order so runs are reproducible."""
    paths = sorted(Path(directory).glob("*.csv"))
    if not paths:
        raise SystemExit(
            f"no artifact CSV in {directory}\n"
            "A job writes one with the columns "
            f"{','.join(ARTIFACT_COLUMNS)}. See AGENTS.md."
        )
    return paths


def combine(
    tables: dict[str, pd.DataFrame], weights: dict[str, float] | None = None
) -> pd.DataFrame:
    """Weighted mean of the per-frame probability columns across artifacts."""
    if not tables:
        raise ValueError("nothing to combine")

    weights = dict(weights or {})
    numerator = np.zeros((N_FRAMES, len(PROB_COLUMNS)))
    denominator = np.zeros(N_FRAMES)

    for name in sorted(tables):
        table = tables[name]
        probability = table[list(PROB_COLUMNS)].to_numpy(dtype=float)
        if name in weights:
            weight = np.full(N_FRAMES, float(weights[name]))
        else:
            weight = table["confidence"].to_numpy(dtype=float)
        numerator += weight[:, None] * probability
        denominator += weight

    unweighted = np.mean(
        np.stack(
            [tables[name][list(PROB_COLUMNS)].to_numpy(dtype=float) for name in sorted(tables)]
        ),
        axis=0,
    )
    zero = denominator <= 0.0
    combined = np.where(
        zero[:, None], unweighted, numerator / np.where(zero, 1.0, denominator)[:, None]
    )

    out = pd.DataFrame(combined, columns=list(PROB_COLUMNS))
    out.insert(0, "frame", np.arange(N_FRAMES))
    out["confidence"] = out[list(PROB_COLUMNS)].max(axis=1)
    return out


def decide(
    artifact: pd.DataFrame,
    abstain_below: float = 0.0,
    x_outside_halves: bool = False,
) -> pd.DataFrame:
    """Turn probabilities into the H/A/D/X label the submission contract wants."""
    probability = artifact[list(PROB_COLUMNS)].to_numpy(dtype=float)
    best = probability.argmax(axis=1)
    labels = np.array(["H", "A", "D"])[best]

    below = probability.max(axis=1) < abstain_below
    labels[below] = "X"

    if x_outside_halves:
        outside = np.array(
            [games.half_of_video_frame(games.GAME, frame) is None for frame in range(N_FRAMES)],
            dtype=bool,
        )
        labels[outside] = "X"

    return pd.DataFrame({"frame": np.arange(N_FRAMES), "label": labels})


def write_submission(df: pd.DataFrame, path: str | Path) -> Path:
    """Validate, then write atomically so a crash cannot leave a half-written submission."""
    check_submission(df, path)
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_suffix(target.suffix + ".tmp")
    df.to_csv(temporary, index=False, lineterminator="\n")
    os.replace(temporary, target)
    return target


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Combine artifact CSVs into the submission file")
    parser.add_argument(
        "--artifacts",
        default=None,
        help=f"directory of artifact CSVs (default {DEFAULT_ARTIFACTS})",
    )
    parser.add_argument(
        "-o", "--out", default=None, help=f"submission CSV to write (default {DEFAULT_OUT})"
    )
    parser.add_argument("--config", default=str(DEFAULT_CONFIG), help="JSON config, optional")
    parser.add_argument(
        "--weight",
        action="append",
        default=[],
        metavar="NAME=VALUE",
        help="explicit weight for one artifact, repeatable",
    )
    parser.add_argument(
        "--abstain-below",
        type=float,
        default=None,
        help="label X where the winning probability is below this value",
    )
    parser.add_argument(
        "--x-outside-halves",
        action="store_true",
        default=None,
        help="label X on frames outside the two playing halves",
    )
    parser.add_argument(
        "--json", dest="summary_path", default=None, help="write a run summary here"
    )
    args = parser.parse_args(argv)

    config = load_config(args.config)
    artifacts_dir = Path(args.artifacts or config.get("artifacts") or DEFAULT_ARTIFACTS)
    out_path = Path(args.out or config.get("out") or DEFAULT_OUT)
    abstain_below = (
        args.abstain_below
        if args.abstain_below is not None
        else float(config.get("abstain_below", 0.0))
    )
    x_outside_halves = (
        args.x_outside_halves
        if args.x_outside_halves is not None
        else bool(config.get("x_outside_halves", False))
    )

    weights = {str(k): float(v) for k, v in (config.get("weights") or {}).items()}
    for item in args.weight:
        if "=" not in item:
            raise SystemExit(f"--weight expects NAME=VALUE, got {item!r}")
        name, value = item.split("=", 1)
        weights[Path(name).name] = float(value)

    tables = {}
    for path in find_artifacts(artifacts_dir):
        tables[path.name] = check_artifact(pd.read_csv(path), path)

    combined = combine(tables, weights)
    submission = decide(combined, abstain_below=abstain_below, x_outside_halves=x_outside_halves)
    written = write_submission(submission, out_path)

    counts = submission["label"].value_counts().to_dict()
    summary = {
        "artifacts": sorted(tables),
        "weights": weights,
        "abstain_below": abstain_below,
        "x_outside_halves": x_outside_halves,
        "out": str(written),
        "label_counts": {label: int(counts.get(label, 0)) for label in ("H", "A", "D", "X")},
    }
    print(f"{written}: {len(submission)} rows from {len(tables)} artifact(s)")
    print("  " + "  ".join(f"{label} {count}" for label, count in summary["label_counts"].items()))
    if args.summary_path:
        Path(args.summary_path).parent.mkdir(parents=True, exist_ok=True)
        Path(args.summary_path).write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
