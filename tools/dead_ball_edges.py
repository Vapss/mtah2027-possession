"""Lane d-edges: where a stoppage ENDS.

    python tools/dead_ball_edges.py --explore                 # the match, no ground truth
    python tools/dead_ball_edges.py dfl                       # offline: every variant on DFL
    python tools/dead_ball_edges.py --variant cut --labels runs/d_edges/cut.csv --gt public
    python tools/dead_ball_edges.py --bench                   # gap-transplant bench, every variant

Why
---
The delivered `D` (DECISIONS 30-36) unites the tagged stoppages -- ball out to the Smart Tagging
restart, dated at the tag start + 5 s (+ 3,5 s for a kick-off) -- with W1, the players' stoppages.
The union ends where the LATER of the two ends. On the match, without any label
(`--explore`, docs/proposals/lane-d-edges.md section 2), a W1 run is still going at the estimated
restart of 44% of the tagged stoppages and runs on a median 1,6 s past it (p90 11,8 s): the frames
of the match where the tag says play resumed and `D` goes on because the players are still slow.
On DFL a W1 run also outlasts a third of the true restarts, briefly (median 0,6 s). The ball was in
play from the restart on whatever the players' speed says: the same principle `dead_ball.stoppages`
already applies to a stoppage's START (it never begins before the previous restart).

Two rules for the end, and their combination with lane dead-v3's onset (`U1`, unchanged):

- `cut`: a tagged restart ends the players' stoppage running through it. W1 frames from the restart
  frame to the end of the W1 run that holds it are live. No new constant.
- `kick`: `cut`, with the restart dated by the ball instead of the fixed offset: the first frame in
  `[tag start, tag start + 2 x offset)` -- a window centred on the delivered estimate -- in which
  the ball is seen inside the pitch at `kick_mps` or faster. A restart is a kick or a throw of a
  dead ball; a placed ball, a carried one and a dribble are slower than a pass (10 m/s,
  `engine.Params`). With no such frame the delivered estimate stays. The re-dated frame ends the
  tagged stoppage, cuts W1 and is where the restart hands the ball to its team (DECISIONS 30-32,
  unchanged).
- `cut+onset`, `kick+onset`: the same, over W1 with its starts moved back to their onset
  (`dead_ball_v3.kinematic_onset`, 3,25 m/s and 40 s, its barriers the delivered restart frames).

Every variant runs the delivered engine (`engine.DEFAULT`: control, duel rule, tagged restarts) and
changes only what its name says; `engine` reproduces `engine.run()` frame for frame.

The DFL corpus (DECISIONS 37) has no Smart Tagging and its ball is frozen while it is dead (every
dead frame has zero ball displacement; the restart is a jump), so `dfl` builds synthetic tags from
its own alive/dead status: one per stoppage whose frozen ball lies outside the pitch (ball out of
play, what our tags cover), the estimate placed off the true restart by a fixed cycle of errors
(`DFL_ERRORS_S`). The players' rules are judged there in full; the ball's dating is not, because a
frozen ball that jumps at the restart is not what our tracker sees.
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import sys
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

import numpy as np
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from tools import dead_ball, dead_ball_v2, dead_ball_v3, engine  # noqa: E402

if TYPE_CHECKING:
    from tools import external

FPS = engine.FPS

VARIANTS = ("engine", "cut", "kick", "cut+onset", "kick+onset")
KICK = ("kick", "kick+onset")
ONSET = ("cut+onset", "kick+onset")

# The estimate's error on the synthetic DFL tags, cycled over the stoppages of each match: the
# delivered estimate early and late by up to 2 s, around lane d's "play resumes between +4 and
# +6 s of the tag" (docs/proposals/lane-d.md).
DFL_ERRORS_S = (-2.0, -1.0, 0.0, 1.0, 2.0)


@dataclass(frozen=True)
class Params:
    """Fixed before any variant met a label (docs/proposals/lane-d-edges.md, section 3)."""

    # A restart kicks or throws a dead ball. A pass travels at 10 m/s and more (engine.Params);
    # a ball being placed, carried or dribbled to the spot is slower.
    kick_mps: float = 10.0
    # The kick is searched in [tag start, tag start + reach x offset): `reach` 2 centres the window
    # on the delivered estimate, as far after it as the tag start is before it.
    reach: float = 2.0


DEFAULT = Params()


# -- the rules ---------------------------------------------------------------------------------


def kicked(f: engine.Features, params: Params = DEFAULT) -> np.ndarray:
    """Frames where the ball is seen inside the pitch at `kick_mps` or faster.

    An unknown speed (the first frame after a gap) is not evidence of a kick: it fails closed.
    """
    fast = np.nan_to_num(f.speed_mps, nan=-np.inf) >= params.kick_mps
    return np.asarray(f.in_pitch, dtype=bool) & fast


def kick_dating(
    restarts: Sequence[dead_ball.Restart],
    kick: np.ndarray,
    runs: Sequence[tuple[int, int]],
    params: Params = DEFAULT,
) -> list[tuple[dead_ball.Restart, int]]:
    """`(restart, dated frame)` for every restart, in tag order: what `kick_restarts` applies.

    The window is `[tag_start, tag_start + reach x (frame - tag_start))`, kept inside the half that
    holds the estimate and after the previous restart's dated frame, so one kick never dates two
    restarts. Tags that share an estimate are dated once, together, so they stay on one frame and
    `engine.restart_controls` still sees them as one (possibly ambiguous) restart. A dated frame is
    never before the previous one: a tag that finds no kick and whose estimate lies before its
    neighbour's dated frame is put on that frame, keeping the tags in their order.
    """
    kick = np.asarray(kick, dtype=bool)
    out: list[tuple[dead_ball.Restart, int]] = []
    previous = -1
    dated: dict[int, int] = {}
    for r in sorted(restarts, key=lambda r: (r.frame, r.tag_start)):
        if r.frame in dated:
            out.append((r, dated[r.frame]))
            continue
        half = [(a, b) for a, b in runs if a <= r.frame < b]
        frame = r.frame
        if half:
            a, b = half[0]
            lo = max(r.tag_start, a, previous + 1)
            hi = min(r.tag_start + int(round(params.reach * (r.frame - r.tag_start))), b, len(kick))
            found = np.flatnonzero(kick[lo:hi]) if hi > lo else np.array([], dtype=np.int64)
            if found.size:
                frame = lo + int(found[0])
        frame = max(frame, previous)
        dated[r.frame] = frame
        out.append((r, frame))
        previous = frame
    return out


def kick_restarts(
    restarts: Sequence[dead_ball.Restart],
    kick: np.ndarray,
    runs: Sequence[tuple[int, int]],
    params: Params = DEFAULT,
) -> tuple[dead_ball.Restart, ...]:
    """Each restart dated at the first kick of its window (`kick_dating`); the estimate where none
    is seen. Team, kind and tag start are unchanged."""
    moved = [
        dataclasses.replace(r, frame=frame)
        for r, frame in kick_dating(restarts, kick, runs, params)
    ]
    return tuple(sorted(moved, key=lambda r: (r.frame, r.tag_start)))


def cut_at_restarts(kinematic: np.ndarray, restart_frames: Sequence[int]) -> np.ndarray:
    """The players' stoppages with every run that holds a restart ended at that restart.

    The ball is in play from the restart on, whatever the players' speed says. A run that does not
    hold a restart frame is left alone, and so is everything before the restart.
    """
    dead = np.asarray(kinematic, dtype=bool)
    out = dead.copy()
    n = len(dead)
    for frame in sorted(int(x) for x in restart_frames):
        if not 0 <= frame < n or not out[frame]:
            continue
        rest = np.flatnonzero(~dead[frame:])
        stop = frame + int(rest[0]) if rest.size else n
        out[frame:stop] = False
    return out


# -- the chain ---------------------------------------------------------------------------------


def chain(
    f: engine.Features,
    ev: dead_ball.Evidence,
    kinematic: np.ndarray,
    variant: str,
    params: engine.Params = engine.D36,
    edges: Params = DEFAULT,
) -> np.ndarray:
    """The W1 chain (DECISIONS 36, `engine.D36`: what this lane measured against; DECISIONS 45
    replaced it) with this variant's end of a stoppage: H/A/D/X for the whole match.

    `kinematic` is the players' `D` for the variant (W1, or W1 with its onsets). `engine` unites it
    with the tagged stoppages exactly as `engine.delivered_dead` does. Every other variant first
    dates the restarts (`kick`) or keeps the estimates, then cuts the players' runs at them; the
    same restarts close the tagged stoppages and force the possession (`engine.restart_controls`).
    """
    if variant not in VARIANTS:
        raise ValueError(f"unknown variant {variant!r}; expected one of {', '.join(VARIANTS)}")
    runs = engine.halves()
    kin = np.asarray(kinematic, dtype=bool)
    if variant != "engine":
        if variant in KICK:
            ev = dataclasses.replace(
                ev, restarts=kick_restarts(ev.restarts, kicked(f, edges), runs, edges)
            )
        kin = cut_at_restarts(kin, [r.frame for r in ev.restarts])
    dead = dead_ball.dead_mask(ev, runs, "out") | kin
    return engine.chain(f, params, ev.restarts, dead)[2]


def kinematic_for(variant: str) -> np.ndarray:
    """The players' `D` over the delivered match: W1 as delivered, or with its onsets (U1)."""
    return dead_ball_v3.match_kinematic(variant in ONSET)


def bench_methods(
    kinematic: dict[bool, np.ndarray],
) -> dict[str, Callable[[engine.Features, dead_ball.Evidence], np.ndarray]]:
    """Bench methods (`tools/bench.py` signature) for every variant, `engine` included.

    `kinematic` maps "with onsets?" to the players' `D`. The bench degrades the ball, never the
    players or the tags, so each mask is closed over once; the kick dating still runs on the
    degraded ball.
    """
    return {v: (lambda f, ev, v=v, m=kinematic[v in ONSET]: chain(f, ev, m, v)) for v in VARIANTS}


# -- the DFL corpus (offline; public CC-BY data, never mixed with the match data) ---------------


def dfl_tags(
    truth: np.ndarray,
    out: np.ndarray,
    runs: Sequence[tuple[int, int]],
    errors_s: Sequence[float] = DFL_ERRORS_S,
    restart_s: float = dead_ball.DEFAULT.restart_s,
) -> tuple[dead_ball.Restart, ...]:
    """Synthetic Smart Tagging for a DFL match: one restart per ball-out stoppage.

    A stoppage is a run of `D` in `truth` strictly inside a half; it is tagged when the (frozen)
    ball is outside the pitch on its last dead frame -- a ball out of play, what our tags cover.
    The estimate sits `errors_s[i % len]` seconds off the true restart (positive is late) and the
    tag starts `restart_s` before it, as `dead_ball.restarts` dates ours; the team is the one the
    truth names on the first live frame. The estimate is kept inside the half and after the
    stoppage's first frame; the tag start may still fall before the stoppage, in live play, as ours
    can when a stoppage is shorter than the 5 s offset (41 of 464 tags).
    """
    truth = np.asarray(truth)
    out = np.asarray(out, dtype=bool)
    found: list[dead_ball.Restart] = []
    for a, b in runs:
        dead = truth[a:b] == "D"
        for start, stop in dead_ball_v2.runs_of(dead):
            start, stop = a + start, a + stop
            if start == a or stop >= b or not out[stop - 1]:
                continue
            error = errors_s[len(found) % len(errors_s)]
            # A restart never comes before the ball went out: an early error on a stoppage shorter
            # than it lands on the stoppage's second frame (review of PR #57: 1 of 464 tags).
            frame = min(max(stop + int(round(error * FPS)), start + 1, a + 1), b - 1)
            team = {"H": 0, "A": 1}.get(str(truth[stop]))
            tag_start = max(a, frame - int(round(restart_s * FPS)))
            found.append(dead_ball.Restart(frame, tag_start, "Throw-in", team))
    return tuple(sorted(found, key=lambda r: (r.frame, r.tag_start)))


def dfl_inputs(
    match_id: str, errors_s: Sequence[float] = DFL_ERRORS_S
) -> tuple[external.Match, dict[bool, np.ndarray]]:
    """`(match with synthetic tags, {onset?: players' D})` for one DFL match."""
    from tools import external

    r = external.raw(match_id)
    m = external.build(r)
    tags = dfl_tags(m.truth, m.evidence.out, m.runs, errors_s)
    m = dataclasses.replace(m, evidence=dataclasses.replace(m.evidence, restarts=tags))
    players, runs = dead_ball_v3.dfl_players(r)
    barriers = [t.frame for t in tags]
    kin = {
        False: dead_ball_v2.kinematic_mask(players, (), runs, "rule"),
        True: dead_ball_v3.kinematic_onset(players, runs, barriers),
    }
    return m, kin


def dfl_edges_of(labels: np.ndarray, truth: np.ndarray) -> dict:
    """`D` of a label sequence against the DFL dead status: frame rates and edge offsets (s)."""
    detected = np.asarray(labels) == "D"
    dead, graded = np.asarray(truth) == "D", np.asarray(truth) != "X"
    starts, ends = dead_ball_v3.edge_offsets(detected, dead)
    return {
        "counts": dead_ball_v3.frame_counts(detected, dead, graded),
        "starts": starts,
        "ends": ends,
    }


def dfl(matches: Sequence[str] | None = None) -> dict:
    """Every variant on every DFL match: official spellF1 clean and with our ball, and the edges.

    Edges and frame rates are taken on the clean match under the cycled errors, and again with the
    estimate's error fixed at each value of `DFL_ERRORS_S` (edges only).
    """
    from tools import external

    donors = external.our_ball_halves()
    spell: dict[str, dict[str, list[float]]] = {v: {"clean": [], "degraded": []} for v in VARIANTS}
    agg: dict[str, dict] = {}
    fixed: dict[str, dict[str, list]] = {}
    names = list(matches or external.MATCHES)
    for match in names:
        m, kin = dfl_inputs(match)
        methods = bench_methods(kin)
        for variant, method in methods.items():
            for degraded in (False, True):
                row = external.score(method, [m], degraded, donors).iloc[0]
                spell[variant]["degraded" if degraded else "clean"].append(float(row["spell_f1"]))
            e = dfl_edges_of(external.run(method, m), m.truth)
            a = agg.setdefault(variant, {"counts": {}, "starts": [], "ends": []})
            for key, value in e["counts"].items():
                a["counts"][key] = a["counts"].get(key, 0) + value
            a["starts"].append(e["starts"])
            a["ends"].append(e["ends"])
        for error in DFL_ERRORS_S:
            mf, kf = dfl_inputs(match, (error,))
            for variant, method in bench_methods(kf).items():
                e = dfl_edges_of(external.run(method, mf), mf.truth)
                fixed.setdefault(f"{variant}|{error:+g}", {"ends": []})["ends"].append(e["ends"])
    result: dict = {"matches": names, "variants": {}}
    for variant in VARIANTS:
        a = agg[variant]
        starts, ends = np.concatenate(a["starts"]), np.concatenate(a["ends"])
        clean, degr = spell[variant]["clean"], spell[variant]["degraded"]
        base_c, base_d = spell["engine"]["clean"], spell["engine"]["degraded"]
        result["variants"][variant] = {
            "spell_f1_clean": clean,
            "spell_f1_degraded": degr,
            "mean_clean": float(np.mean(clean)),
            "mean_degraded": float(np.mean(degr)),
            "wins_clean": int(sum(x > y for x, y in zip(clean, base_c))),
            "wins_degraded": int(sum(x > y for x, y in zip(degr, base_d))),
            "losses_clean": int(sum(x < y for x, y in zip(clean, base_c))),
            "losses_degraded": int(sum(x < y for x, y in zip(degr, base_d))),
            **dead_ball_v3.rates(a["counts"]),
            "d_runs": int(len(ends)),
            "start_median_s": float(np.median(starts)),
            "start_abs_median_s": float(np.median(np.abs(starts))),
            "end_median_s": float(np.median(ends)),
            "end_abs_median_s": float(np.median(np.abs(ends))),
            "end_abs_mean_s": float(np.mean(np.abs(ends))),
            "end_late_over_1s": float(np.mean(ends > 1.0)),
        }
    result["fixed_error_end_abs_median_s"] = {
        key: float(np.median(np.abs(np.concatenate(v["ends"])))) for key, v in fixed.items()
    }
    return result


# -- the match, without and with the public ground truth ----------------------------------------


def explore() -> dict:
    """Aggregates over the whole match, no ground truth (lane-d-edges.md section 2)."""
    from tools import atd, emision

    f = engine.features(atd.load("tactical"), emision.team_slots())
    ev = dead_ball.load_evidence()
    runs = engine.halves()
    w1 = np.array(engine._players_stoppages("rule"))  # the lane measured W1 (DECISIONS 40)
    estimates = [r.frame for r in ev.restarts]
    through = [x for x in estimates if 0 <= x < len(w1) and w1[x]]
    past = []
    for x in through:
        rest = np.flatnonzero(~w1[x:])
        past.append((int(rest[0]) if rest.size else len(w1) - x) / FPS)
    # What `cut` actually removes: each W1 frame once (two estimates in one run cut it once), and
    # apart, the part of it not already inside a tagged stoppage.
    removed = w1 & ~cut_at_restarts(w1, estimates)
    tagged = dead_ball.dead_mask(ev, runs, "out")
    # Pair each restart with its own dated frame (`kick_restarts` re-sorts by the new frame).
    shift = np.array(
        [
            (frame - r.frame) / FPS
            for r, frame in kick_dating(ev.restarts, kicked(f), runs)
            if frame != r.frame
        ]
    )
    inside = np.zeros(len(w1), dtype=bool)
    for a, b in runs:
        inside[a:b] = True
    shares = {}
    for variant in VARIANTS:
        kin = kinematic_for(variant)
        labels = chain(f, ev, kin, variant)
        shares[variant] = float((labels == "D")[inside].mean())
    return {
        "tagged_restarts": len(estimates),
        "w1_holds_the_estimate": len(through),
        "w1_past_the_estimate_s_p10_25_50_75_90": _percentiles(past),
        "w1_frames_cut": int(removed.sum()),
        "w1_frames_cut_outside_tagged_d": int((removed & ~tagged).sum()),
        "restarts_moved_by_kick": int(len(shift)),
        "kick_minus_estimate_s_p10_25_50_75_90": _percentiles(shift),
        "kick_earlier_than_estimate": int((shift < 0).sum()),
        "dead_share_in_halves": shares,
    }


def _percentiles(values: Sequence[float] | np.ndarray) -> list[float]:
    """p10/25/50/75/90, zeros when there is nothing to summarise."""
    values = np.asarray(values, dtype=float)
    if not values.size:
        return [0.0] * 5
    return [float(np.percentile(values, p)) for p in (10, 25, 50, 75, 90)]


def _json_default(value):
    if isinstance(value, (np.integer, np.floating)):
        return value.item()
    if isinstance(value, np.ndarray):
        return value.tolist()
    raise TypeError(type(value).__name__)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="The end of a stoppage (lane d-edges)")
    sub = parser.add_subparsers(dest="command")
    sub.add_parser("dfl", help="every variant on DFL with synthetic tags, clean and degraded")
    parser.add_argument("--variant", choices=VARIANTS, default="cut")
    parser.add_argument("--labels", type=Path, help="write the frame,label CSV here")
    parser.add_argument("--gt", choices=["public"], help="score against the public slice")
    parser.add_argument("--bench", action="store_true", help="gap-transplant bench, all variants")
    parser.add_argument("--explore", action="store_true", help="aggregates, no ground truth")
    args = parser.parse_args(argv)
    try:
        if args.command == "dfl":
            print(json.dumps(dfl(), indent=2, default=_json_default))
            return 0
        if args.explore:
            print(json.dumps(explore(), indent=2, default=_json_default))
            return 0
        if args.bench:
            from tools import bench

            kin = {False: kinematic_for("engine"), True: kinematic_for("cut+onset")}
            f, ev, gt, cut = bench.load()
            for name, method in bench_methods(kin).items():
                print(name, json.dumps(bench.summary(bench.bench(method, f, ev, gt, cut))))
            return 0

        from tools import atd, emision

        f = engine.features(atd.load("tactical"), emision.team_slots())
        ev = dead_ball.load_evidence()
        labels = chain(f, ev, kinematic_for(args.variant), args.variant)
        inside = np.zeros(len(labels), dtype=bool)
        for start, stop in engine.halves():
            inside[start:stop] = True
        result: dict = {
            "variant": args.variant,
            "dead_share_in_halves": float((labels == "D")[inside].mean()),
        }
        if args.labels:
            from tools.contract import check_submission

            table = pd.DataFrame({"frame": np.arange(len(labels)), "label": labels})
            table = check_submission(table, args.labels)
            args.labels.parent.mkdir(parents=True, exist_ok=True)
            table.to_csv(args.labels, index=False, lineterminator="\n")
        if args.gt:
            result["public"] = dead_ball_v3._public_report(labels)
    except (OSError, ValueError, RuntimeError) as problem:
        print(f"dead_ball_edges failed: {problem}", file=sys.stderr)
        return 1
    print(json.dumps(result, indent=2, sort_keys=True, default=_json_default))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
