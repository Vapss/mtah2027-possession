"""Carry the previous label across ball-tracking gaps instead of answering `D`.

Why this exists (#5)
--------------------
The baseline's dead-ball rule is "the tracking lost the ball, so the ball is dead". Measured on
the public slice it is backwards: a missing ball splits one possession into two, and a split
possession is what `spellF1` charges. Replacing the `D` with the label the team already had moves
`spellF1` 0.3256 -> 0.3805 on `baseline_smooth50` (paired +0.0549) and costs `macroF1`
0.6207 -> 0.5105 -- the right price to pay, since only the ranked metric decides (DECISIONS 12).

Two things worth knowing before reading the code:

1. **The gain is the removal of `D`, not the fill.** The official scorer forward-fills `X` with the
   previous in-half label before matching possessions (`possession_metrics.fill_abstentions`), so
   emitting `X` on these frames scores exactly the same `spellF1` as writing the label. The fill is
   how a hard-label submission expresses "no dead ball here"; `D` was the damage.
2. **This is not a dead-ball detector** (DECISIONS 16). No threshold on ball speed, no ball-out-of-
   play rule, no kinematic test. Ball presence only decides *where* the state is carried from; the
   label itself is whatever the previous frame already said. A gap that follows a `D` stays `D`.

The rule
--------
Inside each half-time video block, a **gap** is a maximal run `[start, stop)` of frames where the
tactical ball is not observed (`x` and `y` both NaN, the mask from `tools/atd.py`; a `z` alone is
not a detection, and a pitch rectangle never enters the test). Every frame of that run is set to
the last non-`X` label strictly before it, within the same half:

- `start - 1` and `stop` keep their own labels and nothing is interpolated. What does move is any
  change of label *inside* the gap: a baseline that hands over from `H` to `A` halfway through a
  gap now hands over at `stop`. That is why the fill changes more frames than the `D` it removes.
- A gap whose predecessor is `D` stays `D` -- the rule carries state and does not resurrect a
  possession from before a stoppage.
- A gap at the head of a half has no predecessor and is left untouched: there is no back-fill from
  the future, that belongs to the restart rule (#16).
- A gap that runs to the end of a half is filled from the left, like any other.
- Frames outside the two half blocks (pre-match, halftime, after the whistle) are never modified.
- No length limit: #10 measured the four length bands and none earned its own policy
  (DECISIONS 24).

Deterministic, no training, no ground truth. `python tools/ball_gaps.py IN OUT` rewrites a
`frame,label` CSV; the output passes the same contract check as a submission.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections.abc import Sequence
from pathlib import Path

import numpy as np
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

import games  # noqa: E402
from tools import atd  # noqa: E402
from tools.contract import (  # noqa: E402
    check_submission,
    read_submission,
)

LABELS = frozenset({"H", "A", "D", "X"})


def half_runs(game=games.GAME) -> list[tuple[int, int]]:
    """The two half-time video blocks as half-open `(start, stop)` spans."""
    return [(start, stop + 1) for _half, start, stop in games.half_video_blocks(game)]


def ball_gaps(
    ball_present: Sequence[bool],
    runs: Sequence[tuple[int, int]],
) -> list[tuple[int, int]]:
    """Maximal `[start, stop)` runs with no observed ball, restricted to `runs`.

    Runs outside the half blocks are not gaps: the submission still needs a label for those
    frames, but the tracking's silence there means "not in play yet / halftime", not "ball lost".
    """
    present = np.asarray(ball_present, dtype=bool)
    gaps: list[tuple[int, int]] = []
    for start, stop in runs:
        if start < 0 or stop > len(present) or stop <= start:
            raise ValueError(f"run {start, stop} is outside {len(present)} frames")
        missing = ~present[start:stop]
        # Edges of every False run, in local coordinates, then shifted back to video frames.
        edges = np.diff(missing.astype(np.int8))
        opens = np.flatnonzero(edges == 1) + 1
        closes = np.flatnonzero(edges == -1) + 1
        if missing[0]:
            opens = np.concatenate(([0], opens))
        if missing[-1]:
            closes = np.concatenate((closes, [len(missing)]))
        # Python 3.9 has no zip(strict=True) (AGENTS.md: 3.9+ syntax); every open has its close.
        if len(opens) != len(closes):
            raise AssertionError("unbalanced gap edges")
        gaps.extend((start + int(a), start + int(b)) for a, b in zip(opens, closes))
    return gaps


def fill_ball_gaps(
    labels: Sequence[str],
    ball_present: Sequence[bool],
    runs: Sequence[tuple[int, int]],
) -> list[str]:
    """Set every frame of every ball gap to the previous non-`X` label in the same half."""
    if len(labels) != len(ball_present):
        raise ValueError("labels and ball_present must have the same length")
    output = [str(label) for label in labels]
    invalid = sorted(set(output) - LABELS)
    if invalid:
        raise ValueError(f"labels outside H/A/D/X: {invalid}")

    # Carry value is read from the input, not from the labels written in this pass: a gap must not
    # inherit a value another gap invented. The scan can reach an earlier gap by skipping `X`
    # frames, so it must look at `source`, never at `output`.
    source = list(output)
    for start, stop in ball_gaps(ball_present, runs):
        half_start = next(a for a, b in runs if a <= start < b)
        carry = None
        for index in range(start - 1, half_start - 1, -1):
            if source[index] != "X":
                carry = source[index]
                break
        if carry is None:
            continue  # no predecessor in this half: leave the gap as the input had it
        output[start:stop] = [carry] * (stop - start)
    return output


def _ball_present(source: str = games.DEFAULT_SOURCE) -> np.ndarray:
    """The ball-presence mask of the delivered tracking export."""
    return atd.load(source).ball()[1]


def _sha256(path: str | Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Carry the previous label across ball-tracking gaps"
    )
    parser.add_argument("input", help="frame,label CSV to rewrite")
    parser.add_argument("output", help="destination frame,label CSV")
    args = parser.parse_args(argv)
    try:
        runs = half_runs()
        present = _ball_present()
        gaps = ball_gaps(present, runs)
        summary = {
            "input": args.input,
            "output": args.output,
            "gaps": len(gaps),
            "gap_frames": sum(stop - start for start, stop in gaps),
            "runs": runs,
            "policy": "previous non-X label per half, all gap lengths",
        }
        source = check_submission(read_submission(args.input), args.input)
        before = source.iloc[:, 1].astype(str).str.strip().str.upper().tolist()
        after = fill_ball_gaps(before, present, runs)
        result = pd.DataFrame({"frame": source.iloc[:, 0].to_numpy(), "label": after})
        result = check_submission(result, args.output)
        summary["changed_frames"] = int(sum(a != b for a, b in zip(before, after)))
        target = Path(args.output)
        target.parent.mkdir(parents=True, exist_ok=True)
        result.to_csv(target, index=False, lineterminator="\n")
        summary["frames"] = len(result)
        summary["output_sha256"] = _sha256(args.output)
        print(json.dumps(summary, indent=2, sort_keys=True))
    except (OSError, ValueError) as error:
        print(f"ball gap fill failed: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
