"""#16 dead-ball stream: stoppages as intervals, from the out-of-play event to the restart.

    python tools/dead_ball.py --labels runs/engine/labels.csv --variant out \\
        --out runs/dead_ball/out.csv
    python tools/dead_ball.py --labels runs/engine/labels.csv --variant out --gt public

The engine (#6) labels every frame `H`/`A` and never `D`. A missed stoppage costs a possession on
the ranking metric -- `H D H` is two possessions and `H H H` is one -- so this module answers one
question per frame, "is the ball out of play here?", and `apply_dead` writes the answer onto the
engine's labels.

`D` is a state, not a ball threshold (DECISIONS 16): a stoppage begins at an out-of-play event and
lasts until the restart. The restart comes from Smart Tagging, whose `SET PIECES` are fixed windows
around it -- 35 s, or 5 s for a kick-off -- rather than the stoppage itself. The beginning comes
from the tracking: the ball observed outside the pitch, else the whole field standing still. Every
constant was fixed from tracking and tagging alone, before any variant met the ground truth; the
measurements behind each one are in docs/proposals/lane-d.md, and nothing here is swept.

The four variants are cumulative, each adding one source of evidence to the previous one:

- `tag`: the part of the `SET PIECES` window before its restart, nothing else;
- `out`: a stoppage begins at the last ball-out episode before the restart;
- `out+still`: without an episode, it reaches back while the field is still;
- `out+still+untagged`: a long ball-out episode with no tagged restart opens a stoppage of its own,
  which ends when the ball is next seen on the pitch.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

import games  # noqa: E402
from tools import smart_tagging  # noqa: E402

FPS = int(games.GAMES[games.GAME]["fps"])
PITCH_M = np.asarray(games.GAMES[games.GAME]["pitch"], dtype=float)

VARIANTS = ("tag", "out", "out+still", "out+still+untagged")

KICK_OFF_START = "Kick Off (Start)"
KICK_OFF_GOAL = "Kick Off (After Goal)"


@dataclass(frozen=True)
class Params:
    """Fixed before measuring against any label (docs/proposals/lane-d.md, section 3)."""

    # Where the restart sits inside a `SET PIECES` window. The two real kick-offs fall 3.52 s and
    # 3.28 s after their 5 s tags begin; across the 35 s tags the field is stillest from 0 to +4 s
    # and play resumes between +4 and +6 s.
    kick_off_restart_s: float = 3.5
    restart_s: float = 5.0
    # A ball that goes out is not back on the pitch within a second, so shorter interruptions of
    # an out-of-pitch run (an untracked frame, the ball on the line) belong to the same episode.
    merge_s: float = 1.0
    # How far back from a restart its stoppage may begin. Open-play stoppages rarely last 40 s;
    # after a goal the celebration and the walk back to the centre take longer.
    lookback_s: float = 40.0
    goal_lookback_s: float = 120.0
    # A field is still when the median player moves slower than walking pace (~1.4 m/s); live play
    # sits near 2 m/s. Smoothed over one second so a single tracking jump cannot break a stillness.
    still_mps: float = 1.5
    still_window_s: float = 1.0
    # Below a second outside the pitch is tracking noise at the line, not a ball out of play.
    untagged_min_out_s: float = 1.0

    def frames(self, seconds: float) -> int:
        return int(round(seconds * FPS))


DEFAULT = Params()


@dataclass(frozen=True)
class Restart:
    """A tagged restart: the frame play resumes and where its `SET PIECES` window begins."""

    frame: int
    tag_start: int
    kind: str


@dataclass(frozen=True)
class Evidence:
    """Everything the mask is decided from, as per-frame arrays of one length."""

    restarts: tuple[Restart, ...]
    out: np.ndarray  # the ball observed outside the pitch rectangle
    inside: np.ndarray  # the ball observed inside it
    still: np.ndarray  # the whole field moving slower than walking pace

    def __post_init__(self) -> None:
        lengths = {len(self.out), len(self.inside), len(self.still)}
        if len(lengths) != 1:
            raise ValueError(f"evidence arrays differ in length: {sorted(lengths)}")


def restarts(instances: list[dict], params: Params = DEFAULT) -> tuple[Restart, ...]:
    """Every `SET PIECES` instance as a restart, in frame order."""
    found = []
    for instance in instances:
        if (instance.get("code") or "").strip().upper() != "SET PIECES":
            continue
        kind = str((instance.get("tags") or {}).get("Type") or "").strip()
        offset = params.kick_off_restart_s if kind.startswith("Kick Off") else params.restart_s
        start = int(instance["start_frame"])
        found.append(Restart(start + params.frames(offset), start, kind))
    return tuple(sorted(found, key=lambda restart: (restart.frame, restart.tag_start)))


def out_episodes(out: np.ndarray, merge: int) -> list[tuple[int, int, int]]:
    """`(first, stop, n_out)`: runs of out-of-pitch frames, joined across gaps of `merge` frames.

    `first` is the first frame out and `stop` one past the last; `n_out` counts the out frames,
    which is what tells a ball that left the pitch from one that grazed the line.
    """
    frames = np.flatnonzero(np.asarray(out, dtype=bool))
    if not frames.size:
        return []
    breaks = np.flatnonzero(np.diff(frames) > merge + 1)
    firsts = np.concatenate(([0], breaks + 1))
    lasts = np.concatenate((breaks, [len(frames) - 1]))
    return [(int(frames[a]), int(frames[b]) + 1, int(b - a + 1)) for a, b in zip(firsts, lasts)]


def field_speed(players_xy_m: np.ndarray) -> np.ndarray:
    """Median player speed per frame in m/s; NaN on the first frame and where nobody is tracked."""
    speed = np.full(players_xy_m.shape[:2], np.nan)
    speed[1:] = np.linalg.norm(np.diff(players_xy_m, axis=0), axis=2) * FPS
    known = np.isfinite(speed).any(axis=1)
    median = np.full(len(speed), np.nan)
    median[known] = np.nanmedian(speed[known], axis=1)
    return median


def stillness(speed: np.ndarray, params: Params = DEFAULT) -> np.ndarray:
    """Is the field still? A centred moving mean of the median player speed, below walking pace.

    Unknown speed is not evidence of stillness: a window with no measurement is never still, and a
    window's mean uses only the frames it measured.
    """
    speed = np.asarray(speed, dtype=float)
    width = max(1, params.frames(params.still_window_s))
    kernel = np.ones(width)
    known = np.isfinite(speed)
    total = np.convolve(np.where(known, speed, 0.0), kernel, mode="same")
    count = np.convolve(known.astype(float), kernel, mode="same")
    mean = np.divide(total, count, out=np.full(len(speed), np.inf), where=count > 0)
    return mean < params.still_mps


def _walk_back(still: np.ndarray, start: int, floor: int) -> int:
    """The earliest frame >= `floor` from which the field stays still up to `start`."""
    moving = np.flatnonzero(~still[floor:start])
    return floor + int(moving[-1]) + 1 if moving.size else floor


@dataclass(frozen=True)
class Stoppage:
    """One `[start, stop)` interval of dead ball and the evidence that opened it.

    `source` is `kick-off` (before a half's first kick), `tag` (the window alone), `out` (a ball
    observed outside the pitch), `still` (a still field) or `untagged` (an out episode with no
    tagged restart). It says which rule fired, so a report can count them without frame dumps.
    """

    start: int
    stop: int
    source: str


def stoppages(
    evidence: Evidence,
    halves: Sequence[tuple[int, int]],
    variant: str = "out",
    params: Params = DEFAULT,
) -> list[Stoppage]:
    """Every stoppage the variant opens, half by half, in frame order within each source.

    `halves` are half-open `[start, stop)` video blocks; nothing outside them is ever marked, and
    no stoppage crosses one's edge. A stoppage never begins before the previous restart: the ball
    was in play from that restart on, whatever the tracking says about its position.
    """
    if variant not in VARIANTS:
        raise ValueError(f"unknown variant {variant!r}; expected one of {', '.join(VARIANTS)}")
    level = VARIANTS.index(variant)
    n = len(evidence.out)
    found: list[Stoppage] = []
    episodes = out_episodes(evidence.out, params.frames(params.merge_s))
    firsts = np.array([first for first, _stop, _n in episodes], dtype=np.int64)
    restart_frames = np.array([r.frame for r in evidence.restarts], dtype=np.int64)

    for half_start, half_stop in halves:
        half_start, half_stop = max(0, half_start), min(n, half_stop)
        previous = half_start
        for restart in evidence.restarts:
            if not half_start <= restart.frame < half_stop:
                continue
            tag_start = min(max(restart.tag_start, previous), restart.frame)
            if restart.kind == KICK_OFF_START:
                # Before the first kick of a half the ball is not in play, by the laws of the game.
                start, source = previous, "kick-off"
            else:
                after_goal = restart.kind == KICK_OFF_GOAL
                reach = params.frames(params.goal_lookback_s if after_goal else params.lookback_s)
                floor = max(previous, restart.frame - reach)
                start, source = tag_start, "tag"
                if level >= VARIANTS.index("out"):
                    candidates = firsts[(firsts >= floor) & (firsts < tag_start)]
                    if candidates.size:
                        start, source = int(candidates.max()), "out"
                    elif level >= VARIANTS.index("out+still"):
                        walked = _walk_back(evidence.still, tag_start, floor)
                        if walked < tag_start:
                            start, source = walked, "still"
            found.append(Stoppage(start, restart.frame, source))
            previous = restart.frame

        if level < VARIANTS.index("out+still+untagged"):
            continue
        reach = params.frames(params.lookback_s)
        minimum = params.frames(params.untagged_min_out_s)
        for first, stop, n_out in episodes:
            if not half_start <= first < half_stop or n_out < minimum:
                continue
            ahead = restart_frames[(restart_frames > first) & (restart_frames <= first + reach)]
            if ahead.size:
                continue  # a tagged restart already closes this stoppage
            limit = min(first + reach, half_stop)
            back_in = np.flatnonzero(evidence.inside[stop:limit])
            end = stop + int(back_in[0]) if back_in.size else limit
            found.append(Stoppage(first, end, "untagged"))
    return found


def dead_mask(
    evidence: Evidence,
    halves: Sequence[tuple[int, int]],
    variant: str = "out",
    params: Params = DEFAULT,
) -> np.ndarray:
    """`True` where the ball is out of play: the union of the variant's stoppages."""
    dead = np.zeros(len(evidence.out), dtype=bool)
    for stoppage in stoppages(evidence, halves, variant, params):
        dead[stoppage.start : stoppage.stop] = True
    return dead


def apply_dead(labels: pd.DataFrame, dead: np.ndarray) -> pd.DataFrame:
    """A copy of a `frame,label` table with `D` wherever `dead` is True; nothing else changes."""
    dead = np.asarray(dead, dtype=bool)
    if len(dead) != len(labels):
        raise ValueError(f"mask has {len(dead)} frames, labels have {len(labels)}")
    out = labels.copy()
    out.loc[dead, "label"] = "D"
    return out


def halves() -> list[tuple[int, int]]:
    """The two half-time video blocks, half-open."""
    return [(start, stop + 1) for _half, start, stop in games.half_video_blocks(games.GAME)]


def load_evidence(params: Params = DEFAULT) -> Evidence:
    """Tracking and Smart Tagging of the delivered match, reduced to the mask's inputs."""
    from tools import atd

    tracking = atd.load("tactical")
    ball, present = tracking.ball()
    x, y = ball[:, 0], ball[:, 1]
    # The export normalises the pitch to [0, 1] on both axes; an absent ball is neither in nor out.
    off = (x < 0) | (x > 1) | (y < 0) | (y > 1)
    speed = field_speed(tracking.players_array[:, :, :2] * PITCH_M)
    return Evidence(
        restarts=restarts(smart_tagging.load(), params),
        out=present & off,
        inside=present & ~off,
        still=stillness(speed, params),
    )


def dead_precision_recall(gt_labels: np.ndarray, dead: np.ndarray) -> dict[str, float | int]:
    """The mask as a detector of `D`, on the frames the ground truth grades (not `X`)."""
    gt_labels = np.asarray(gt_labels)
    graded = gt_labels != "X"
    truth = gt_labels[graded] == "D"
    said = np.asarray(dead, dtype=bool)[graded]
    hits = int((truth & said).sum())
    return {
        "graded_frames": int(graded.sum()),
        "true_d_frames": int(truth.sum()),
        "predicted_d_frames": int(said.sum()),
        "hits": hits,
        "precision": hits / int(said.sum()) if said.any() else 0.0,
        "recall": hits / int(truth.sum()) if truth.any() else 0.0,
    }


def summary(found: list[Stoppage], n_frames: int, runs: Sequence[tuple[int, int]]) -> dict:
    """Aggregates only: how much of the match is `D`, and which rule opened each stoppage."""
    inside = np.zeros(n_frames, dtype=bool)
    for start, stop in runs:
        inside[start:stop] = True
    dead = np.zeros(n_frames, dtype=bool)
    for stoppage in found:
        dead[stoppage.start : stoppage.stop] = True
    sources: dict[str, int] = {}
    for stoppage in found:
        sources[stoppage.source] = sources.get(stoppage.source, 0) + 1
    lengths = np.array([s.stop - s.start for s in found if s.stop > s.start])
    return {
        "stoppages": len(found),
        "stoppages_by_source": dict(sorted(sources.items())),
        "dead_share_in_halves": float((dead & inside).sum() / max(1, inside.sum())),
        "median_stoppage_s": float(np.median(lengths) / FPS) if lengths.size else 0.0,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Dead-ball stream: stoppage intervals (#16)")
    parser.add_argument("--labels", type=Path, required=True, help="engine frame,label CSV")
    parser.add_argument("--variant", choices=VARIANTS, default="out")
    parser.add_argument("--out", type=Path, help="write the labels with D applied here")
    parser.add_argument("--gt", help="also report D precision/recall: public, or a CSV path")
    args = parser.parse_args(argv)
    try:
        from tools.contract import check_submission, read_submission

        labels = read_submission(args.labels)
        evidence = load_evidence()
        runs = halves()
        found = stoppages(evidence, runs, args.variant)
        dead = dead_mask(evidence, runs, args.variant)
        result = {
            "variant": args.variant,
            "restarts_tagged": len(evidence.restarts),
            **summary(found, len(dead), runs),
        }
        if args.out:
            table = check_submission(apply_dead(labels, dead), args.out)
            args.out.parent.mkdir(parents=True, exist_ok=True)
            table.to_csv(args.out, index=False, lineterminator="\n")
        if args.gt:
            from tools.compare_submissions import resolve_ground_truth

            gt = pd.read_csv(resolve_ground_truth(args.gt), keep_default_na=False)
            if len(gt) != len(dead):
                raise ValueError(f"ground truth has {len(gt)} frames, the match has {len(dead)}")
            result["d_detection"] = dead_precision_recall(gt["label"].to_numpy(), dead)
    except (OSError, ValueError, RuntimeError) as problem:
        print(f"dead_ball failed: {problem}", file=sys.stderr)
        return 1
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
