"""Deterministic structural cleanup for hard possession labels.

The transform is deliberately small and fixed-parameter. It never learns from ground truth and
never changes labels outside the supplied half-open runs.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

import games  # noqa: E402
from tools.contract import check_submission, read_submission  # noqa: E402

LABELS = frozenset({"H", "A", "D", "X"})


@dataclass(frozen=True)
class PostprocessConfig:
    """The reviewed constants for #35; changes require a separately reviewed experiment."""

    minimum_frames: int = 15
    merge_gap_frames: int = 15
    duration_prior_frames: int = 355


DEFAULT_CONFIG = PostprocessConfig()


@dataclass
class _Segment:
    label: str
    start: int
    stop: int
    anchor_duration: int

    @property
    def duration(self) -> int:
        return self.stop - self.start


def _validate_runs(runs: Sequence[tuple[int, int]], n_frames: int) -> list[tuple[int, int]]:
    checked: list[tuple[int, int]] = []
    previous_stop = 0
    for item in runs:
        if len(item) != 2:
            raise ValueError("each run must be a half-open (start, stop) pair")
        start, stop = item
        if not isinstance(start, int) or not isinstance(stop, int):
            raise ValueError("run boundaries must be integers")
        if start < previous_stop or stop <= start or stop > n_frames:
            raise ValueError("runs must be ordered, nonempty, disjoint, and within labels")
        checked.append((start, stop))
        previous_stop = stop
    return checked


def _fill_x(window: list[str]) -> list[str]:
    """Use the prior label to expose structure, backfilling only before the first answer."""
    known = [index for index, label in enumerate(window) if label != "X"]
    if not known:
        return window.copy()
    filled = window.copy()
    previous = window[known[0]]
    for index, label in enumerate(window):
        if label == "X":
            filled[index] = previous
        else:
            previous = label
    return filled


def _segments(labels: list[str]) -> list[_Segment]:
    result: list[_Segment] = []
    start = 0
    for index in range(1, len(labels) + 1):
        if index == len(labels) or labels[index] != labels[start]:
            result.append(_Segment(labels[start], start, index, index - start))
            start = index
    return result


def _merge_into(segments: list[_Segment], source: int, target: int) -> None:
    """Relabel one short segment and coalesce it with its selected neighbor."""
    target_anchor = segments[target].anchor_duration
    segments[source].label = segments[target].label
    segments[source].anchor_duration = target_anchor
    merged: list[_Segment] = []
    for segment in segments:
        if merged and merged[-1].label == segment.label:
            merged[-1].stop = segment.stop
            # Keep the leftmost surviving segment's original duration as its tie-break anchor.
        else:
            merged.append(
                _Segment(segment.label, segment.start, segment.stop, segment.anchor_duration)
            )
    segments[:] = merged


def _next_operation(segments: list[_Segment], config: PostprocessConfig) -> tuple[int, int] | None:
    for index, segment in enumerate(segments):
        if segment.label == "D":
            if segment.duration >= config.merge_gap_frames:
                continue
            if (
                index > 0
                and index + 1 < len(segments)
                and segments[index - 1].label == segments[index + 1].label
                and segments[index - 1].label in {"H", "A"}
            ):
                return index, index - 1
            continue
        if segment.label not in {"H", "A"}:
            continue
        if (
            segment.duration >= config.minimum_frames
            and segment.duration >= config.merge_gap_frames
        ):
            continue

        neighbors = [
            neighbor for neighbor in (index - 1, index + 1) if 0 <= neighbor < len(segments)
        ]
        if not neighbors:
            continue
        same_team = [
            neighbor for neighbor in neighbors if segments[neighbor].label == segment.label
        ]
        if same_team:
            return index, same_team[0]
        # Prefer the longer original neighbor. The 355-frame prior is a secondary tie-break,
        # followed by the previous neighbor for a fully equal candidate.
        target = min(
            neighbors,
            key=lambda neighbor: (
                -segments[neighbor].anchor_duration,
                abs(segments[neighbor].anchor_duration - config.duration_prior_frames),
                neighbor > index,
            ),
        )
        return index, target
    return None


def _process_run(window: list[str], config: PostprocessConfig) -> list[str]:
    original_x = [label == "X" for label in window]
    structure = _fill_x(window)
    segments = _segments(structure)
    # Each accepted operation removes at least one RLE segment. The bound is defensive and
    # documents that this process cannot oscillate even if a future rule is added.
    for _ in range(len(window) + 1):
        operation = _next_operation(segments, config)
        if operation is None:
            break
        previous_count = len(segments)
        source, target = operation
        _merge_into(segments, source, target)
        if len(segments) >= previous_count:
            raise RuntimeError("postprocess operation failed to reduce the number of runs")
    else:
        raise RuntimeError("postprocess did not reach a fixed point within n_frames+1 steps")

    result = ["X"] * len(window)
    for segment in segments:
        result[segment.start : segment.stop] = [segment.label] * segment.duration
    for index, was_x in enumerate(original_x):
        if was_x:
            result[index] = "X"
    return result


def postprocess(
    labels: Sequence[str],
    runs: Sequence[tuple[int, int]],
    config: PostprocessConfig = DEFAULT_CONFIG,
) -> list[str]:
    """Apply fixed structural rules inside half-open valid runs and preserve all other rows.

    `X` is forward-filled (backfilled at the run head) for structure only, then restored exactly.
    Entirely-X runs remain unchanged. The public constants are fixed for this issue; a different
    configuration is rejected so parameter sweeps cannot happen through this API.
    """
    if config != DEFAULT_CONFIG:
        raise ValueError("#35 parameters are fixed; parameter variants belong in #22")
    output = [str(label) for label in labels]
    invalid = sorted(set(output) - LABELS)
    if invalid:
        raise ValueError(f"labels outside H/A/D/X: {invalid}")
    checked_runs = _validate_runs(runs, len(output))

    for start, stop in checked_runs:
        original = output[start:stop]
        if all(label == "X" for label in original):
            continue
        processed = _process_run(original, config)
        output[start:stop] = processed
    return output


def _match_runs() -> list[tuple[int, int]]:
    """Return video-frame half blocks from games.py as half-open spans."""
    return [(start, stop + 1) for _half, start, stop in games.half_video_blocks(games.GAME)]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Apply fixed structural possession post-processing"
    )
    parser.add_argument("input", help="frame,label CSV")
    parser.add_argument("output", help="destination frame,label CSV")
    args = parser.parse_args(argv)
    try:
        source = check_submission(read_submission(args.input), args.input)
        before = source.iloc[:, 1].astype(str).str.strip().str.upper().tolist()
        after = postprocess(before, _match_runs())
        result = pd.DataFrame({"frame": source.iloc[:, 0].to_numpy(), "label": after})
        result = check_submission(result, args.output)
        target = Path(args.output)
        target.parent.mkdir(parents=True, exist_ok=True)
        result.to_csv(target, index=False, lineterminator="\n")
        print(
            json.dumps(
                {
                    "input": args.input,
                    "output": args.output,
                    "frames": len(result),
                    "changed_frames": int(sum(a != b for a, b in zip(before, after))),
                    "runs": _match_runs(),
                    "config": {
                        "minimum_frames": DEFAULT_CONFIG.minimum_frames,
                        "merge_gap_frames": DEFAULT_CONFIG.merge_gap_frames,
                        "duration_prior_frames": DEFAULT_CONFIG.duration_prior_frames,
                    },
                },
                indent=2,
                sort_keys=True,
            )
        )
    except (OSError, ValueError) as error:
        print(f"postprocess failed: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
