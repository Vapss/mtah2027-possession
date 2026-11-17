"""Turn a hard-label submission into an intermediate artifact.

The shipped baselines emit hard labels only. The harness speaks probabilities, so this is the
adapter that lets an existing label file take part in the pipeline -- and it is what the
round-trip test uses to prove that `tools/assemble.py` is label-preserving.

    python tools/onehot.py evaluation/results/baseline_smooth125.csv -o artifacts/baseline.csv

An `X` becomes a uniform distribution with confidence 0, which is the honest encoding of "this
job declines to answer": the assembler gives it no weight, so it neither helps nor hurts.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tools.contract import LABELS, check_artifact, read_submission  # noqa: E402

UNIFORM = 1.0 / 3.0


def onehot(labels: pd.Series) -> pd.DataFrame:
    """frame,label -> frame,p_home,p_away,p_dead,confidence."""
    clean = labels.astype(str).str.strip().str.upper()
    unknown = sorted(set(clean) - set(LABELS))
    if unknown:
        raise ValueError(f"unknown label(s) {unknown}")

    frame = pd.Series(range(len(clean)), name="frame")
    out = pd.DataFrame(
        {
            "frame": frame,
            "p_home": (clean == "H").astype(float).to_numpy(),
            "p_away": (clean == "A").astype(float).to_numpy(),
            "p_dead": (clean == "D").astype(float).to_numpy(),
            "confidence": (clean != "X").astype(float).to_numpy(),
        }
    )
    abstained = out["confidence"] == 0.0
    out.loc[abstained, ["p_home", "p_away", "p_dead"]] = UNIFORM
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Encode a frame,label CSV as probabilities")
    parser.add_argument("submission", help="frame,label CSV to encode")
    parser.add_argument("-o", "--out", required=True, help="where to write the artifact CSV")
    args = parser.parse_args(argv)

    df = read_submission(args.submission)
    artifact = check_artifact(onehot(df.iloc[:, 1]), args.out)

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    artifact.to_csv(out, index=False, lineterminator="\n")
    print(f"{out}: {len(artifact)} rows, {int((artifact['confidence'] == 0).sum())} abstentions")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
