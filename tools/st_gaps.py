"""Lane st-gaps: inside a long ball gap, hand the possession to the team the Smart Tagging names.

    python tools/st_gaps.py --explore                 # no ground truth: where the rule would act
    python tools/st_gaps.py --measure runs/st_gaps    # every instrument, every variant (JSON)

Why
---
Inside a ball gap the engine sees no control and carries the last team (DECISIONS 24, 29). The
Smart Tagging is an opinion independent of the tracking, and on the public slice it is right on ~98%
of the live frames *without* ball (DECISIONS 34): reliable exactly where the tracking is blind. This
module asks whether following it there improves the delivered chain. Pre-registration, variants,
gates and results: `docs/proposals/lane-st-gaps.md`. Using it makes the Smart Tagging stop being an
independent validator for this component, and the block report's agreement column rises by
construction.

The rule
--------
A frame's *side* is the team every Smart Tagging phase covering it votes for
(`smart_tagging.possession_votes`, one team with votes; otherwise none), as in the block report.

1. A *unit* is a ball gap (`ball_gaps.ball_gaps`) or a *live* gap (no ball **and** not `D`) of at
   least `min_s` seconds. Its live frames are the ones the delivered chain does not call `D`.
2. The carried team is the decoded state on the unit's first live frame, with every earlier unit's
   switch already applied: units are processed in time order. A unit with no live frame, no state,
   or a forced restart anywhere inside it does nothing: the restart's own rule decides who has the
   ball there, whichever team it names (a restart to the carried team would undo the switch, and a
   phase dating could walk back across it). The unit is skipped whole, not split at the restart:
   a split would make new, shorter units the pre-registration does not name.
3. It fires when at least `share` of its live frames have the rival as side.
4. The switch is forced into `engine.decode` exactly like a restart (DECISIONS 30-32): from that
   frame the rival holds the ball until the next control the decoder accepts, duel rule included.
   A restart on the same frame wins: the laws of the game over an annotator.
5. Dating: `gap` switches on the unit's first live frame; `phase` on the onset of the rival's
   side run that holds its first rival frame, but never before the frame after the carried team's
   last *observation* (its own control, or a restart forced to it) nor before the half starts --
   an observation beats an estimate (DECISIONS 32, 35). No restart lies inside a firing unit
   (rule 2), so a switch is never dated before one either.
6. `D` is written over the result as in the delivered chain. With no unit firing, the output is
   `engine.chain`'s frame for frame.

numpy only, no fitted weight, no seed: deterministic.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import numpy as np
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from tools import ball_gaps, dead_ball, engine  # noqa: E402
from tools import smart_tagging as st  # noqa: E402

NONE = engine.NONE
FPS = engine.FPS
LOW_BALL_BLOCKS = (7, 9, 11, 18)  # the blocks with least ball (DECISIONS 26)


@dataclass(frozen=True)
class Variant:
    """One pre-registered configuration. Nothing here is swept (lane-st-gaps.md, section 1)."""

    name: str
    unit: str  # "gap": ball gap; "live": no ball and not `D`
    min_s: float  # shortest unit that can fire, in seconds
    share: float  # share of the unit's live frames the rival's side must cover
    dating: str  # "gap": first live frame; "phase": onset of the Smart Tagging's rival run

    def __post_init__(self) -> None:
        if self.unit not in ("gap", "live"):
            raise ValueError(f"unit must be 'gap' or 'live', got {self.unit!r}")
        if self.dating not in ("gap", "phase"):
            raise ValueError(f"dating must be 'gap' or 'phase', got {self.dating!r}")
        if not 0 < self.share <= 1:
            raise ValueError(f"share must be in (0, 1], got {self.share}")
        if self.min_s <= 0:
            raise ValueError(f"min_s must be positive, got {self.min_s}")


# G = 5 s and 20 s are the 126- and 500-frame band edges of DECISIONS 24, not new constants; X = 0,5
# is a majority of the gap. Reasons per variant: the pre-registration table.
VARIANTS: dict[str, Variant] = {
    "V1": Variant("V1", "gap", 5.0, 0.5, "gap"),
    "V2": Variant("V2", "gap", 5.0, 0.5, "phase"),
    "V3": Variant("V3", "live", 5.0, 0.5, "gap"),
    "V4": Variant("V4", "gap", 20.0, 0.5, "gap"),
}


def sides(votes: np.ndarray) -> np.ndarray:
    """`0` / `1` where every Smart Tagging vote on the frame goes to that team, `NONE` elsewhere."""
    votes = np.asarray(votes)
    home, away = votes[:, 0] > 0, votes[:, 1] > 0
    side = np.full(len(votes), NONE, dtype=np.int8)
    side[home & ~away] = 0
    side[away & ~home] = 1
    return side


@lru_cache(maxsize=1)
def match_sides() -> np.ndarray:
    """BAR-ATH's Smart Tagging sides, once per process (read-only: the bench shares them)."""
    side = sides(st.possession_votes(st.load()))
    side.flags.writeable = False
    return side


def units(
    present: np.ndarray, dead: np.ndarray, runs: Sequence[tuple[int, int]], unit: str
) -> list[tuple[int, int]]:
    """The `[start, stop)` candidates: ball gaps, or live gaps (no ball and not `D`)."""
    present = np.asarray(present, dtype=bool)
    if unit == "gap":
        return ball_gaps.ball_gaps(present, runs)
    if unit == "live":
        # A live gap is a gap in "ball seen or dead": the one gap definition, reused.
        return ball_gaps.ball_gaps(present | np.asarray(dead, dtype=bool), runs)
    raise ValueError(f"unknown unit {unit!r}")


def _half_of(frame: int, runs: Sequence[tuple[int, int]]) -> tuple[int, int]:
    return next((a, b) for a, b in runs if a <= frame < b)


def last_observation(
    ctrl: np.ndarray, forced: dict[int, int], team: int, start: int, floor: int
) -> int | None:
    """The last frame in `[floor, start)` where a control or a restart showed `team` on the ball."""
    seen = np.flatnonzero(ctrl[floor:start] == team)
    last = int(seen[-1]) + floor if len(seen) else None
    for frame, owner in forced.items():
        if owner == team and floor <= frame < start and (last is None or frame > last):
            last = frame
    return last


def switch_frame(
    variant: Variant,
    live: np.ndarray,
    side: np.ndarray,
    rival: int,
    floor: int,
) -> int:
    """Where a firing unit hands the ball to `rival` (`live` = its live frames, ascending)."""
    if variant.dating == "gap":
        return int(live[0])
    first = int(live[np.argmax(side[live] == rival)])
    frame = first
    while frame - 1 >= floor and side[frame - 1] == rival:
        frame -= 1
    return frame


def _redecode(
    state: np.ndarray,
    ctrl: np.ndarray,
    frame: int,
    runs: Sequence[tuple[int, int]],
    dwell: int,
    forced: dict[int, int],
    switch: np.ndarray | None,
) -> None:
    """Decode again from a newly forced `frame` to the end of its half, in place.

    A forced frame resets the decoder (`engine.decode`), so decoding `[frame, half end)` alone gives
    exactly the frames a whole-match decode would: the earlier frames cannot change.
    """
    _start, stop = _half_of(frame, runs)
    part = engine.decode(ctrl, [(frame, stop)], dwell, forced, switch)
    state[frame:stop] = part[frame:stop]


def st_switches(
    ctrl: np.ndarray,
    switch: np.ndarray | None,
    forced: dict[int, int],
    present: np.ndarray,
    dead: np.ndarray,
    side: np.ndarray,
    runs: Sequence[tuple[int, int]],
    variant: Variant,
    dwell: int = 1,
) -> dict[int, int]:
    """`{frame: team}`: the Smart Tagging switches of `variant`, unit by unit in time order.

    Each unit is judged on the state that the earlier switches produce, so a switch can change the
    team the next unit carries -- the same answer a decoder walking the match once would give.
    """
    dead = np.asarray(dead, dtype=bool)
    state = engine.decode(ctrl, list(runs), dwell, forced, switch)
    shortest = int(round(variant.min_s * FPS))
    moves: dict[int, int] = {}
    for start, stop in units(present, dead, runs, variant.unit):
        if stop - start < shortest:
            continue
        live = np.flatnonzero(~dead[start:stop]) + start
        if not len(live):
            continue
        if any(start <= frame < stop for frame in forced):
            continue  # a restart inside the unit decides who has the ball there (rule 2)
        carried = int(state[live[0]])
        if carried == NONE or np.any(state[live] != carried):
            continue
        rival = 1 - carried
        if np.mean(side[live] == rival) < variant.share:
            continue
        half_start, _stop = _half_of(start, runs)
        last = last_observation(ctrl, {**forced, **moves}, carried, start, half_start)
        floor = half_start if last is None else last + 1
        frame = switch_frame(variant, live, side, rival, floor)
        if frame in forced:
            continue  # a restart on this very frame decides who has the ball
        moves[frame] = rival
        _redecode(state, ctrl, frame, runs, dwell, {**moves, **forced}, switch)
    return moves


def chain(
    f: engine.Features,
    ev: dead_ball.Evidence,
    variant: Variant,
    side: np.ndarray | None = None,
    dead: np.ndarray | None = None,
) -> tuple[np.ndarray, np.ndarray, dict[int, int]]:
    """The delivered chain (`engine.chain`, `DEFAULT`) plus `variant`: `(state, labels, moves)`."""
    params = engine.DEFAULT
    side = match_sides() if side is None else np.asarray(side)
    dead = engine.delivered_dead(ev) if dead is None else np.asarray(dead, dtype=bool)
    runs = engine.halves()
    ctrl, switch, forced = engine.inputs(f, params, ev.restarts, dead)
    forced = forced or {}
    moves = st_switches(ctrl, switch, forced, f.present, dead, side, runs, variant, params.dwell)
    # A restart wins a shared frame; st_switches already skips those, this keeps it true by order.
    state = engine.decode(ctrl, runs, params.dwell, {**moves, **forced}, switch)
    out = engine.labels(state)
    out[dead] = "D"
    return state, out, moves


def method(variant: Variant) -> Callable[[engine.Features, dead_ball.Evidence], np.ndarray]:
    """A bench method `(features, evidence) -> labels` for `variant` (tools/bench.py)."""

    def run(f: engine.Features, ev: dead_ball.Evidence) -> np.ndarray:
        return chain(f, ev, variant)[1]

    run.__name__ = f"st_gaps_{variant.name}"
    return run


# -- measurement ---------------------------------------------------------------------------------


def _block_index(n: int) -> np.ndarray:
    from tools import blocks as bl

    index = np.zeros(n, dtype=np.int16)
    for block in bl.blocks(bl.halves()):
        index[block.start : block.stop] = block.index
    return index


def explore() -> dict:
    """Where each variant would act, from tracking + Smart Tagging only: no ground truth is read."""
    from tools import atd, emision

    f = engine.features(atd.load("tactical"), emision.team_slots())
    ev = dead_ball.load_evidence()
    dead = engine.delivered_dead(ev)
    side = match_sides()
    runs = engine.halves()
    block = _block_index(len(dead))
    gaps = ball_gaps.ball_gaps(f.present, runs)
    live = units(f.present, dead, runs, "live")
    lengths = np.array([b - a for a, b in gaps])
    live_lengths = np.array([b - a for a, b in live])
    out: dict = {
        "ball_gaps": {
            "n": len(gaps),
            "frames": int(lengths.sum()),
            **{f"n_ge_{s}s": int((lengths >= s * FPS).sum()) for s in (1, 5, 10, 20)},
        },
        "live_gaps": {
            "n": len(live),
            "frames": int(live_lengths.sum()),
            **{f"n_ge_{s}s": int((live_lengths >= s * FPS).sum()) for s in (1, 5, 10, 20)},
        },
        "variants": {},
    }
    for name, variant in VARIANTS.items():
        _state, labels, moves = chain(f, ev, variant, side, dead)
        base = engine.chain(f, engine.DEFAULT, ev.restarts, dead)[2]
        changed = labels != base
        out["variants"][name] = {
            "switches": len(moves),
            "frames_changed": int(changed.sum()),
            "frames_changed_in_block_1": int((changed & (block == 1)).sum()),
            "frames_changed_in_low_ball_blocks": int(
                (changed & np.isin(block, LOW_BALL_BLOCKS)).sum()
            ),
        }
    return out


def _labels_csv(labels: np.ndarray, path: Path) -> Path:
    from tools.contract import check_submission

    table = pd.DataFrame({"frame": np.arange(len(labels)), "label": labels})
    check_submission(table, path)
    path.parent.mkdir(parents=True, exist_ok=True)
    table.to_csv(path, index=False, lineterminator="\n")
    return path


def measure(out_dir: Path) -> dict:
    """Every pre-registered instrument for the delivered chain and each variant (aggregates only).

    The label CSVs go to `out_dir` (under `runs/`, gitignored) so `tools/compare_submissions.py`
    can be run on them by hand; the JSON holds only counts, rates and scores.
    """
    from tools import bench, compare_submissions
    from tools import blocks as bl

    pm = bench.pm
    f, ev, gt, cut = bench.load()
    dead = engine.delivered_dead(ev)
    side = match_sides()
    block = _block_index(len(dead))
    window = pm.valid_runs(gt)
    graded = np.zeros(len(gt), dtype=bool)
    for a, b in window:
        graded[a:b] = True
    hidden = graded & ~f.present & ((gt == pm.H) | (gt == pm.A))  # the public slice's real gaps
    votes = st.possession_votes(st.load())
    block_runs = [(a, b) for _h, a, b in bl.halves()]

    methods = {"engine": bench.METHODS["engine"]}
    methods.update({name: method(v) for name, v in VARIANTS.items()})
    labels = {"engine": np.asarray(methods["engine"](f, ev))}
    moves: dict[str, dict[int, int]] = {}
    for name, variant in VARIANTS.items():
        _state, labels[name], moves[name] = chain(f, ev, variant, side, dead)
    for name, lab in labels.items():
        _labels_csv(lab, out_dir / f"{name}.csv")

    def filled(lab: np.ndarray) -> np.ndarray:
        return pm.fill_abstentions(pm.label_codes(list(lab)), window)

    base = labels["engine"]
    base_codes = pm.label_codes(list(base))
    result: dict = {"hidden_frames": int(hidden.sum()), "variants": {}}
    bench_rows = {name: bench.bench(m, f, ev, gt, cut) for name, m in methods.items()}
    bench_engine = bench_rows["engine"]
    measured_blocks = {
        name: bl.measure(list(lab), f.present, votes, cut, block_runs)
        for name, lab in labels.items()
    }

    for name, lab in labels.items():
        codes = pm.label_codes(list(lab))
        fill = filled(lab)
        rows = bench_rows[name]
        entry: dict = {
            "public": {
                "spell_f1": bench.spell_f1(gt, lab, window),
                "macro_f1": float(pm.macro_f1(pm.scored_confusion(pm.confusion(gt, codes)))),
                "hidden_accuracy": float(np.mean(fill[hidden] == gt[hidden])),
                "hidden_changed": int(np.sum(fill[hidden] != filled(base)[hidden])),
                "window_frames_changed": int(np.sum((lab != base) & graded)),
            },
            "bench": {
                **bench.summary(rows),
                "per_donor": [
                    {"donor": r["donor"], "ball": r["ball"], "spell_f1": r["spell_f1"]}
                    for r in rows
                ],
            },
            "blocks": [
                {
                    "block": r.label,
                    "rate": r.rate,
                    "possessions": r.possessions,
                    "mean_s": r.mean_s,
                    "longest": r.longest,
                    "dead": r.dead,
                    "st_agree": r.st_agree,
                }
                for r in measured_blocks[name]
            ],
        }
        if name != "engine":
            cmp = compare_submissions.compare_codes(gt, base_codes, codes)
            sign = cmp["sign_diagnostic"]
            donors = list(zip(bench_engine[1:], rows[1:]))
            changed = lab != base
            entry["public"].update(
                {
                    "delta_spell_f1": cmp["delta_mean_spell_f1_b_minus_a"],
                    "wins_engine": sign["wins_a"],
                    "wins_variant": sign["wins_b"],
                    "n_discordant": sign["n_discordant"],
                    "jackknife_range": cmp["jackknife"]["mean_delta_range"],
                }
            )
            entry["bench"].update(
                {
                    "delta_mean": entry["bench"]["mean"] - bench.summary(bench_engine)["mean"],
                    "delta_low_mean": entry["bench"]["low_mean"]
                    - bench.summary(bench_engine)["low_mean"],
                    "donors_better": sum(v["spell_f1"] > e["spell_f1"] for e, v in donors),
                    "donors_worse": sum(v["spell_f1"] < e["spell_f1"] for e, v in donors),
                    "changed_frame_agreement": _bench_changed(f, ev, gt, cut, VARIANTS[name]),
                }
            )
            entry["honesty"] = {
                "switches": len(moves[name]),
                "frames_changed": int(changed.sum()),
                "frames_changed_no_ball": int((changed & ~f.present).sum()),
                "frames_changed_low_ball_blocks": int(
                    (changed & np.isin(block, LOW_BALL_BLOCKS)).sum()
                ),
                "switches_low_ball_blocks": int(
                    sum(block[frame] in LOW_BALL_BLOCKS for frame in moves[name])
                ),
                "switches_block_1": int(sum(block[frame] == 1 for frame in moves[name])),
            }
        result["variants"][name] = entry
    return result


def _bench_changed(
    f: engine.Features,
    ev: dead_ball.Evidence,
    gt: np.ndarray,
    cut: Sequence,
    variant: Variant,
) -> dict:
    """Diagnostic: on each donor, the window frames the rule changes and how many match the GT.

    It says *where* the bench's verdict comes from: transplanted gaps fall on play where the ball
    was seen, and there the Smart Tagging is a weaker judge than in real gaps (pre-registration).
    """
    from tools import bench

    pm = bench.pm
    window = pm.valid_runs(gt)
    start, stop = window[0]
    size = stop - start
    changed = right_new = right_old = 0
    for block in cut[1:]:
        if block.stop - block.start < size:
            continue
        f2, ev2 = bench.degrade(f, ev, (start, stop), f.present[block.start : block.start + size])
        dead = engine.delivered_dead(ev2)
        new = chain(f2, ev2, variant, dead=dead)[1]
        old = engine.chain(f2, engine.DEFAULT, ev2.restarts, dead)[2]
        new_c = pm.fill_abstentions(pm.label_codes(list(new)), window)[start:stop]
        old_c = pm.fill_abstentions(pm.label_codes(list(old)), window)[start:stop]
        g = gt[start:stop]
        moved = new_c != old_c
        changed += int(moved.sum())
        right_new += int(np.sum(moved & (new_c == g)))
        right_old += int(np.sum(moved & (old_c == g)))
    return {"frames": changed, "variant_right": right_new, "engine_right": right_old}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Lane st-gaps: Smart Tagging inside ball gaps")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--explore", action="store_true", help="where the rule acts (no GT)")
    group.add_argument("--measure", type=Path, help="every instrument; label CSVs go here")
    args = parser.parse_args(argv)
    try:
        result = explore() if args.explore else measure(args.measure)
    except (OSError, ValueError) as problem:
        print(f"st_gaps failed: {problem}", file=sys.stderr)
        return 1
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
