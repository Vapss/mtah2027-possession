"""Lane dead-v3: where a players' stoppage begins, and who has the ball when it ends.

    python tools/dead_ball_v3.py dfl-edges                 # offline: W1's edges against DFL
    python tools/dead_ball_v3.py dfl-score                 # offline: the variants on DFL
    python tools/dead_ball_v3.py --variant onset --labels runs/dead_v3/onset.csv --gt public
    python tools/dead_ball_v3.py --bench                   # gap-transplant bench, every variant
    python tools/dead_ball_v3.py --explore                 # the match without ground truth

Why
---
The delivered `D` (DECISIONS 36) unites the tagged stoppages with W1, the players' stoppages: every
run of >= 4 s in which the 90th percentile of the players' speeds over +/- 1 s is under 2 m/s. Two
things about those runs were left open by lane dead-v2 (docs/proposals/lane-dead-v3.md):

1. **Their edges.** A speed rule fires once the players have slowed down, and they slow down after
   the whistle. On the seven public DFL/IDSSE matches, whose per-frame alive/dead status does not
   depend on any possession definition (DECISIONS 37), a W1 run begins a median 5,4 s after the
   ball went dead and ends 0,7 s *before* it comes alive again: the start is late, the end is not.
   `onset` moves each start back to the onset of the deceleration: the last frame, within
   `onset_cap_s`, where the field was seen moving faster than a jog (`onset_mps`, the same
   +/- 1 s p90). If no such frame is seen before a tagged restart, the previous stoppage, an
   untracked field or the cap, the onset is not observed and the start stays where W1 put it.
   Both constants were chosen on DFL alone.
2. **Who restarts an untagged stoppage.** After a W1 stoppage without a Smart Tagging restart the
   engine carries the team it had before the whistle until the rival controls the ball uncontested.
   By the laws, the restart is taken with the opponents at a distance (9,15 m at a free kick, 2 m
   at a throw-in), so the first player to control the ball after a stoppage is the restarting team.
   `first-control` hands the ball to that team from the stoppage's first live frame (lane
   dead-v2's `first_control_forcing`, never measured on W1). Contested or not makes no practical
   difference here: on the match the first control and the first uncontested one name a different
   team after 1 of 44 untagged stoppages.

Every variant runs the delivered engine (`engine.DEFAULT`: control, duel rule, tagged restarts
under DECISIONS 32/35) and changes only what its name says. `engine` reproduces `engine.run()`
frame for frame. Only numpy and pandas; the DFL commands read the IDSSE cache of
`tools/external.py` and never touch the match data.
"""

from __future__ import annotations

import argparse
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

from tools import dead_ball, dead_ball_v2, engine  # noqa: E402

if TYPE_CHECKING:
    from tools import external

FPS = engine.FPS

VARIANTS = ("engine", "onset", "first-control", "onset+first-control")
ONSET = ("onset", "onset+first-control")
FORCING = ("first-control", "onset+first-control")


@dataclass(frozen=True)
class Params:
    """Fixed on the DFL corpus before any variant met our labels (lane-dead-v3.md, section 3)."""

    # The onset of a stoppage is the last frame the field's +/- 1 s p90 speed was above a jog. On
    # DFL, among the thresholds keeping frame precision >= 0,90, 3,25 m/s gives the smallest median
    # start error: 1,7 s against 5,4 s for W1 alone (median +0,5 s against +5,4 s).
    onset_mps: float = 3.25
    # No further back than `dead_ball`'s own reach for a stoppage (`lookback_s`): open-play
    # stoppages rarely last 40 s. On DFL 20 s and 40 s tie on the start error.
    onset_cap_s: float = 40.0

    def frames(self, seconds: float) -> int:
        return int(round(seconds * FPS))


DEFAULT = Params()


# -- the edges ---------------------------------------------------------------------------------


def p90_window(
    players_xy_m: np.ndarray, params: dead_ball_v2.Params = dead_ball_v2.DEFAULT
) -> tuple[np.ndarray, np.ndarray]:
    """`(known, window)`: is the frame's own p90 known, and the p90 averaged over +/- 1 s.

    The same signal W1 thresholds (`dead_ball_v2.kinematic_mask`, method `rule`), on one half.
    """
    _p50, p90 = dead_ball_v2.speed_quantiles(players_xy_m, params)
    return np.isfinite(p90), dead_ball_v2.window_mean(p90, -FPS, FPS)


def extend_onsets(
    dead: np.ndarray,
    known: np.ndarray,
    window: np.ndarray,
    barriers: Sequence[int] = (),
    params: Params = DEFAULT,
) -> np.ndarray:
    """Each run of `dead` begun at its onset: after the last frame the field was seen running.

    From a run's first frame, walk back over the frames whose own p90 is known and whose +/- 1 s
    window is under `onset_mps`. The run is extended only when the walk ends on a frame where the
    field was *seen* faster than that: the onset of the deceleration. When it ends anywhere else
    the onset was not observed and the run keeps its start: at another dead run (the field never
    sped up between two stoppages, so the live stretch between them stays live), at an unknown
    frame (losing the players is not evidence that they slowed), at a `barrier` (a tagged restart
    put the ball in play, so a stoppage never begins before it), at the edge of the array or after
    `onset_cap_s`. The end of every run is left alone; on DFL it is already 0,7 s early.
    """
    dead = np.asarray(dead, dtype=bool)
    known = np.asarray(known, dtype=bool)
    level = np.nan_to_num(window, nan=np.inf)
    slow = known & (level < params.onset_mps)
    fast = known & np.isfinite(window) & (level >= params.onset_mps)
    floor_at = np.zeros(len(dead), dtype=np.int64)
    for b in sorted(int(x) for x in barriers):
        if 0 <= b < len(dead):
            floor_at[b:] = b  # the latest barrier at or before each frame
    out = dead.copy()
    cap = params.frames(params.onset_cap_s)
    for start, _stop in dead_ball_v2.runs_of(dead):
        floor = max(int(floor_at[start]), start - cap)
        i = start
        while i > floor and slow[i - 1] and not dead[i - 1]:
            i -= 1
        if i < start and i > floor and fast[i - 1] and not dead[i - 1]:
            out[i:start] = True
    return out


def kinematic_onset(
    players_xy_m: np.ndarray,
    runs: Sequence[tuple[int, int]],
    barriers: Sequence[int] = (),
    params: Params = DEFAULT,
) -> np.ndarray:
    """W1's stoppages, half by half, each begun at its onset (`extend_onsets`)."""
    n = len(players_xy_m)
    w1 = dead_ball_v2.kinematic_mask(players_xy_m, (), runs, "rule")
    out = np.zeros(n, dtype=bool)
    bars = np.asarray(sorted(barriers), dtype=np.int64)
    for start, stop in runs:
        start, stop = max(0, start), min(n, stop)
        known, window = p90_window(players_xy_m[start:stop])
        inside = bars[(bars >= start) & (bars < stop)] - start
        out[start:stop] = extend_onsets(w1[start:stop], known, window, inside.tolist(), params)
    return out


# -- the restart -------------------------------------------------------------------------------


def untagged_restarts(
    ctrl: np.ndarray,
    dead: np.ndarray,
    runs: Sequence[tuple[int, int]],
    restart_frames: Sequence[int],
) -> dict[int, int]:
    """`{first live frame: team}` of each stoppage that no tagged restart closes.

    Lane dead-v2's `first_control_forcing`, unchanged: the team is the first control after the
    stoppage, provided no other stoppage starts before it, and a stoppage holding a tagged restart
    is left to the tag (DECISIONS 30-32). `ctrl` decides which controls count: every one, or only
    those the duel rule accepts.
    """
    return dead_ball_v2.first_control_forcing(ctrl, dead, runs, restart_frames)


# -- the chain ---------------------------------------------------------------------------------


def chain(
    f: engine.Features,
    ev: dead_ball.Evidence,
    kinematic: np.ndarray,
    variant: str,
    params: engine.Params = engine.DEFAULT,
) -> np.ndarray:
    """The delivered chain with this variant's change: H/A/D/X per frame for the whole match.

    `kinematic` is the players' `D` for the variant (`kinematic_for`): W1 as delivered, or W1 with
    its onsets. It is united with the tagged stoppages exactly as `engine.delivered_dead` does;
    control, the duel rule and the tagged restarts are `engine.chain`'s. A `FORCING` variant adds
    the restart of the stoppages no tag closes; a tagged restart on the same frame wins.
    """
    if variant not in VARIANTS:
        raise ValueError(f"unknown variant {variant!r}; expected one of {', '.join(VARIANTS)}")
    runs = engine.halves()
    dead = dead_ball_v2.dead_union("rule", ev, kinematic, runs)
    ctrl, switch, forced = engine.inputs(f, params, ev.restarts)
    forced = forced or {}
    if variant in FORCING:
        extra = untagged_restarts(ctrl, dead, runs, [r.frame for r in ev.restarts])
        forced = {**extra, **forced}
    state = engine.decode(ctrl, runs, params.dwell, forced, switch)
    out = engine.labels(state)
    out[dead] = "D"
    return out


def match_kinematic(onset: bool, params: Params = DEFAULT) -> np.ndarray:
    """The players' `D` over the delivered match: W1 exactly as delivered, or with its onsets."""
    if not onset:
        return np.array(engine._players_stoppages())
    from tools import atd
    from tools.ball_gaps import half_runs

    tracking = atd.load("tactical")
    players = tracking.players_array[:, :, :2] * engine.PITCH_M
    barriers = [r.frame for r in dead_ball.load_evidence().restarts]
    return kinematic_onset(players, half_runs(), barriers, params)


def kinematic_for(variant: str, params: Params = DEFAULT) -> np.ndarray:
    return match_kinematic(variant in ONSET, params)


def bench_methods(
    kinematic: dict[bool, np.ndarray],
) -> dict[str, Callable[[engine.Features, dead_ball.Evidence], np.ndarray]]:
    """Bench methods (`tools/bench.py` signature) for each variant, `engine` included.

    `kinematic` maps "with onsets?" to the players' `D`. The bench degrades the ball, never the
    players or the tags, so each mask is computed once and closed over; the bench still removes
    the ball from the engine, from the tagged `D` and from the first control after a stoppage.
    """
    return {v: (lambda f, ev, v=v, m=kinematic[v in ONSET]: chain(f, ev, m, v)) for v in VARIANTS}


# -- the DFL corpus (offline; public CC-BY data, never mixed with the match data) ---------------


def dfl_players(r: external.Raw) -> tuple[np.ndarray, list[tuple[int, int]]]:
    """Both teams' players of an `external.Raw`, laid out like `external.build`: metres from a
    corner, the halves concatenated with `external.HALF_GAP` empty frames between them."""
    from tools import external

    length, width = r.pitch
    offset = np.array([length / 2, width / 2])
    slots = max(s.home.shape[1] + s.away.shape[1] for s in r.sections)
    parts, runs, at = [], [], 0
    for i, s in enumerate(r.sections):
        if i:
            parts.append(np.full((external.HALF_GAP, slots, 2), np.nan))
            at += external.HALF_GAP
        both = np.concatenate([s.home, s.away], axis=1) + offset
        pad = np.full((len(both), slots - both.shape[1], 2), np.nan)
        parts.append(np.concatenate([both, pad], axis=1))
        runs.append((at, at + len(both)))
        at += len(both)
    return np.concatenate(parts), runs


def edge_offsets(detected: np.ndarray, dead: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Seconds from each true stoppage's edges to those of the detected run that overlaps it.

    A detected run is compared with the first and the last true dead run it overlaps (it may
    bridge two); a run overlapping none has no offset. Positive is late.
    """
    truth = dead_ball_v2.runs_of(dead)
    first = np.array([a for a, _ in truth], dtype=np.int64)
    last = np.array([b for _, b in truth], dtype=np.int64)
    starts, ends = [], []
    for a, b in dead_ball_v2.runs_of(detected):
        over = np.flatnonzero((first < b) & (last > a))
        if over.size:
            starts.append((a - first[over[0]]) / FPS)
            ends.append((b - last[over[-1]]) / FPS)
    return np.asarray(starts, dtype=float), np.asarray(ends, dtype=float)


def frame_counts(detected: np.ndarray, dead: np.ndarray, graded: np.ndarray) -> dict[str, int]:
    """Hits, detections and true frames of `detected` as a detector of `dead`, on `graded`."""
    said, truth = detected & graded, dead & graded
    return {
        "hits": int((said & truth).sum()),
        "said": int(said.sum()),
        "true": int(truth.sum()),
        "graded": int(graded.sum()),
    }


def rates(counts: dict[str, int]) -> dict[str, float]:
    precision = counts["hits"] / max(1, counts["said"])
    recall = counts["hits"] / max(1, counts["true"])
    return {
        "precision": precision,
        "recall": recall,
        "f1": 2 * precision * recall / max(1e-12, precision + recall),
        "dead_share": counts["said"] / max(1, counts["graded"]),
    }


def dfl_edges(matches: Sequence[str] | None = None, grid: bool = False) -> dict:
    """W1 and `onset` against the DFL alive/dead status: frame detection and edge offsets.

    `grid` also scores the candidate thresholds and caps the constants were chosen from.
    """
    from tools import external

    candidates: dict[str, Params | None] = {"W1": None, "onset": DEFAULT}
    if grid:
        for mps in (3.0, 3.25, 3.5, 3.75):
            for cap in (10.0, 20.0, 40.0):
                candidates[f"onset<{mps}/{cap:g}s"] = Params(mps, cap)
    counts = {k: {"hits": 0, "said": 0, "true": 0, "graded": 0} for k in candidates}
    starts: dict[str, list] = {k: [] for k in candidates}
    ends: dict[str, list] = {k: [] for k in candidates}
    for match in matches or external.MATCHES:
        r = external.raw(match)
        for s in r.sections:
            players = np.concatenate([s.home, s.away], axis=1)  # speeds ignore the origin
            n = len(players)
            w1 = dead_ball_v2.kinematic_mask(players, (), [(0, n)], "rule")
            known, window = p90_window(players)
            dead, graded = s.status == 0, s.status >= 0
            for name, params in candidates.items():
                mask = w1 if params is None else extend_onsets(w1, known, window, (), params)
                for key, value in frame_counts(mask, dead, graded).items():
                    counts[name][key] += value
                a, b = edge_offsets(mask, dead)
                starts[name].append(a)
                ends[name].append(b)
    out: dict = {}
    for name in candidates:
        a, b = np.concatenate(starts[name]), np.concatenate(ends[name])
        out[name] = {
            **rates(counts[name]),
            "runs": int(len(a)),
            "start_median_s": float(np.median(a)),
            "start_abs_median_s": float(np.median(np.abs(a))),
            "start_p25_p75_s": [float(np.percentile(a, 25)), float(np.percentile(a, 75))],
            "end_median_s": float(np.median(b)),
            "end_abs_median_s": float(np.median(np.abs(b))),
            "end_p25_p75_s": [float(np.percentile(b, 25)), float(np.percentile(b, 75))],
        }
    out["truth_dead_share"] = counts["W1"]["true"] / max(1, counts["W1"]["graded"])
    return out


def dfl_score(matches: Sequence[str] | None = None) -> dict[str, pd.DataFrame]:
    """Every variant on every DFL match with the official scorer, clean and with our ball.

    DFL has no Smart Tagging, so `D` is the players' alone and every stoppage is untagged. Read it
    as a report, not as a judge of the restart variants: they change possession, and the DFL
    possession definition is not ours (DECISIONS 37).
    """
    from tools import external

    tables: dict[str, list[pd.DataFrame]] = {}
    donors = external.our_ball_halves()
    for match in matches or external.MATCHES:
        r = external.raw(match)
        m = external.build(r)
        players, runs = dfl_players(r)
        kin = {
            False: dead_ball_v2.kinematic_mask(players, (), runs, "rule"),
            True: kinematic_onset(players, runs, ()),
        }
        for variant, method in bench_methods(kin).items():
            for degraded in (False, True):
                key = f"{variant}|{'degraded' if degraded else 'clean'}"
                row = external.score(method, [m], degraded, donors).iloc[:1]
                tables.setdefault(key, []).append(row)
    return {k: pd.concat(v, ignore_index=True) for k, v in tables.items()}


# -- the match, without and with the public ground truth ----------------------------------------


def explore() -> dict:
    """Aggregates over the whole match, no ground truth: how much `D` the onsets add, and how
    often an untagged stoppage's first control names the rival of the team the engine carried."""
    from tools import atd, emision

    f = engine.features(atd.load("tactical"), emision.team_slots())
    ev = dead_ball.load_evidence()
    runs = engine.halves()
    inside = np.zeros(len(f.present), dtype=bool)
    for start, stop in runs:
        inside[start:stop] = True
    kin = {False: match_kinematic(False), True: match_kinematic(True)}
    ctrl, accepted, _forced = engine.inputs(f, engine.DEFAULT, None)
    restarts = [r.frame for r in ev.restarts]
    letter = {0: "H", 1: "A"}
    result: dict = {}
    for onset in (False, True):
        base = chain(f, ev, kin[onset], "onset" if onset else "engine")
        dead = dead_ball_v2.dead_union("rule", ev, kin[onset], runs)
        anyc = untagged_restarts(ctrl, dead, runs, restarts)
        acc = untagged_restarts(accepted, dead, runs, restarts)
        result["onset" if onset else "W1"] = {
            "dead_share_in_halves": float(dead[inside].mean()),
            "players_share_in_halves": float(kin[onset][inside].mean()),
            "stoppages": len(dead_ball_v2.runs_of(dead & inside)),
            "untagged_ends_with_a_control": len(anyc),
            "first_control_names_the_rival": sum(
                base[k] in ("H", "A") and base[k] != letter[t] for k, t in anyc.items()
            ),
            **first_control_vs_accepted(anyc, acc),
            "first_accepted_names_the_rival": sum(
                base[k] in ("H", "A") and base[k] != letter[t] for k, t in acc.items()
            ),
        }
    return result


def first_control_vs_accepted(first: dict[int, int], accepted: dict[int, int]) -> dict[str, int]:
    """How the untagged restarts by first control (`first`) compare with those by first
    uncontested control (`accepted`), both keyed by the stoppage's first live frame.

    A stoppage after which no uncontested control comes before the next one is not "a different
    team": it has no team to compare, and is counted apart.
    """
    return {
        "first_control_differs_from_first_accepted": sum(
            k in accepted and accepted[k] != t for k, t in first.items()
        ),
        "first_control_without_uncontested_control": sum(k not in accepted for k in first),
    }


def _public_report(labels: np.ndarray) -> dict:
    from tools.compare_submissions import resolve_ground_truth

    gt = pd.read_csv(resolve_ground_truth("public"), keep_default_na=False)["label"].to_numpy()
    sys.path.insert(0, str(REPO_ROOT / "evaluation"))
    import possession_metrics as pm

    result = pm.evaluate(pm.label_codes(gt), pm.label_codes(list(labels)))
    return {
        "spell_f1": result["spell_f1_mean"],
        "macro_f1": result["macro_f1"],
        "n_pred_spells": result["n_pred_spells"],
        "d_detection": dead_ball.dead_precision_recall(gt, labels == "D"),
    }


# -- command line ------------------------------------------------------------------------------


def _json_default(value: object) -> object:
    if isinstance(value, (np.integer, np.floating)):
        return value.item()
    raise TypeError(type(value).__name__)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Stoppage edges and untagged restarts (dead-v3)")
    sub = parser.add_subparsers(dest="command")
    edges = sub.add_parser("dfl-edges", help="W1 and onset against the DFL alive/dead status")
    edges.add_argument("--grid", action="store_true", help="also the candidate constants")
    sub.add_parser("dfl-score", help="every variant on DFL, clean and with our ball")
    parser.add_argument("--variant", choices=VARIANTS, default="onset")
    parser.add_argument("--labels", type=Path, help="write the frame,label CSV here")
    parser.add_argument("--gt", choices=["public"], help="score against the public slice")
    parser.add_argument("--bench", action="store_true", help="gap-transplant bench, all variants")
    parser.add_argument("--explore", action="store_true", help="aggregates, no ground truth")
    args = parser.parse_args(argv)
    try:
        if args.command == "dfl-edges":
            print(json.dumps(dfl_edges(grid=args.grid), indent=2, default=_json_default))
            return 0
        if args.command == "dfl-score":
            summary = {
                key: {
                    "spell_f1_mean": round(float(t["spell_f1"].mean()), 4),
                    "spell_f1": [round(float(v), 4) for v in t["spell_f1"]],
                    "pred_per_min": round(float(t["pred_per_min"].mean()), 3),
                    "gt_per_min": round(float(t["gt_per_min"].mean()), 3),
                    "pred_dead": round(float(t["pred_dead"].mean()), 4),
                }
                for key, t in dfl_score().items()
            }
            print(json.dumps(summary, indent=2))
            return 0
        if args.explore:
            print(json.dumps(explore(), indent=2, default=_json_default))
            return 0
        if args.bench:
            from tools import bench

            kin = {False: match_kinematic(False), True: match_kinematic(True)}
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
            result["public"] = _public_report(labels)
    except (OSError, ValueError, RuntimeError) as problem:
        print(f"dead_ball_v3 failed: {problem}", file=sys.stderr)
        return 1
    print(json.dumps(result, indent=2, sort_keys=True, default=_json_default))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
