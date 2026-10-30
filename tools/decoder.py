"""Lane decode: other ways to decode the engine's control evidence (docs/proposals/lane-decode.md).

    python tools/decoder.py --report                     # every measurement of the proposal
    python tools/decoder.py --variant uncontested --labels runs/decode/uncontested.csv

The engine (`tools/engine.py`, DECISIONS 29-32) decides *which* frames are evidence -- a control:
the ball seen inside the pitch, the nearest player within 1,5 m, the rival not as close, the ball
at <= 5 m/s -- and then decodes with the simplest rule there is: the first rival control changes
possession and the change is dated to it. This module keeps the evidence exactly as it is (same
`engine.control`, same forced restarts, same `D` mask) and changes only the decoding:

- `mid`: date each change to the middle of the hand-over, not to its last frame;
- `uncontested`: a change needs a control the team in possession could not also reach (a duel is
  not a control, CHALLENGE.md);
- `touch`: a rival possession shorter than 2 s between two of the other team's is a touch, not a
  possession, and is undone;
- `viterbi`: a two-state Viterbi on a soft control likelihood with a switch cost from the 3,4
  changes-per-minute prior;
- `mid+uncontested+touch`: the three rule-based changes together.

Every constant is fixed in the pre-registration, from physics or from a prior already written in
DECISIONS; nothing here is swept. Each variant is a bench method `(features, evidence) -> labels`.
"""

from __future__ import annotations

import argparse
import math
import sys
from collections.abc import Callable, Sequence
from pathlib import Path

import numpy as np
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from tools import dead_ball, engine  # noqa: E402
from tools.contract import check_submission  # noqa: E402

NONE = engine.NONE
FPS = engine.FPS

# A pass of 30-40 m at 15-20 m/s flies for at most ~2 s: past that the old team's last control is
# no longer where the hand-over began (lost ball, a tracker gap), so the redating is capped.
HANDOVER_CAP = 2 * FPS
# "A player keeps the ball for a few seconds" (CHALLENGE.md): a rival spell shorter than this that
# ends with the old team back in control is a touch or a deflection, not a possession.
TOUCH_FRAMES = 2 * FPS

# V4: the engine's thresholds as the centres, tracking noise as the widths (0,04 m per frame of
# position noise is ~1 m/s of speed noise at 25 fps).
SOFT_RADIUS_M = engine.DEFAULT.radius_m
SOFT_RADIUS_WIDTH_M = 0.25
SOFT_SPEED_MPS = engine.DEFAULT.speed_mps
SOFT_SPEED_WIDTH_MPS = 1.0
# The nearest player is the team in possession 91,1% of the time with a slow ball (DECISIONS 29).
EMISSION_LOG_ODDS = math.log(0.911 / 0.089)
# 3,4 possessions per minute (DECISIONS 26) as a per-frame switch probability.
SWITCH_PROBABILITY = 3.4 / (60 * FPS)
SWITCH_COST = math.log((1 - SWITCH_PROBABILITY) / SWITCH_PROBABILITY)


def uncontested(ctrl: np.ndarray, home_m: np.ndarray, away_m: np.ndarray, radius_m: float):
    """`ctrl` where the other team's nearest player is beyond `radius_m`, `NONE` elsewhere.

    A control both teams could play is a duel. An unknown distance is not evidence that the other
    team is far, so it fails closed, like everything else in the engine.
    """
    other = np.where(ctrl == 0, away_m, home_m)
    clear = np.nan_to_num(other, nan=-np.inf) > radius_m
    return np.where((ctrl != NONE) & clear, ctrl, NONE).astype(np.int8)


def decode(
    ctrl: np.ndarray,
    runs: Sequence[tuple[int, int]],
    forced: dict[int, int] | None = None,
    switch: np.ndarray | None = None,
) -> np.ndarray:
    """`engine.decode` with `dwell = 1`, except that only `switch` frames may change the state.

    The first control of a run sets the state, whatever `switch` says; after that the state is the
    team of the last `switch` frame (default: `ctrl` itself, which is the engine exactly). A forced
    frame hands the ball to its team at once.
    """
    forced = forced or {}
    switch = ctrl if switch is None else switch
    state = np.full(len(ctrl), NONE, dtype=np.int8)
    for start, stop in runs:
        events = np.full(stop - start, NONE, dtype=np.int8)
        seen = np.flatnonzero(ctrl[start:stop] != NONE)
        if seen.size:
            events[seen[0]] = ctrl[start + seen[0]]
        events = np.where(switch[start:stop] != NONE, switch[start:stop], events)
        for frame, team in forced.items():
            if start <= frame < stop:
                events[frame - start] = team
        state[start:stop] = _carry(events)
    return state


def _carry(events: np.ndarray) -> np.ndarray:
    """Forward-fill the non-`NONE` values; `NONE` before the first one."""
    index = np.where(events != NONE, np.arange(len(events)), -1)
    last = np.maximum.accumulate(index) if len(index) else index
    return np.where(last >= 0, events[np.maximum(last, 0)], NONE).astype(np.int8)


def _switches(state: np.ndarray, runs: Sequence[tuple[int, int]]) -> list[int]:
    """Frames where the state changes from one team to the other inside a run."""
    out: list[int] = []
    for start, stop in runs:
        window = state[start:stop]
        change = (window[1:] != window[:-1]) & (window[1:] != NONE) & (window[:-1] != NONE)
        out += (np.flatnonzero(change) + 1 + start).tolist()
    return out


def redate_mid(
    state: np.ndarray,
    ctrl: np.ndarray,
    runs: Sequence[tuple[int, int]],
    forced: dict[int, int] | None = None,
    cap: int = HANDOVER_CAP,
) -> np.ndarray:
    """V1: move every natural change to the middle of its hand-over, at most `cap // 2` frames back.

    For a change from `o` to `n` at frame `c`, the hand-over is `(l, c]` with `l` the last frame `o`
    controlled (or was forced) before `c`, never before the spell of `o` began. The new start is
    `c - min(c - l, cap) // 2`, which always stays after `l`. Forced changes keep their frame.
    """
    forced = forced or {}
    out = state.copy()
    for start, stop in runs:
        spell_start = start
        for c in _switches(state, [(start, stop)]):
            old = int(state[c - 1])
            if c not in forced:
                held = np.flatnonzero(ctrl[spell_start:c] == old)
                last = spell_start + int(held[-1]) if held.size else spell_start
                pushed = [f for f, team in forced.items() if spell_start <= f < c and team == old]
                last = max([last, *pushed])
                out[c - min(c - last, cap) // 2 : c] = state[c]
            spell_start = c
    return out


def undo_touches(
    state: np.ndarray,
    dead: np.ndarray | None,
    runs: Sequence[tuple[int, int]],
    forced: dict[int, int] | None = None,
    min_frames: int = TOUCH_FRAMES,
) -> np.ndarray:
    """V3: a possession shorter than `min_frames` between two of the other team's is undone.

    Possessions are read the way the scorer reads them: maximal runs of one team with `D` (and
    `NONE`) as boundaries, so a stoppage on either side protects the spell. One pass over the
    original spells; a spell that starts on a forced frame, or whose successor does, is kept.
    """
    forced = forced or {}
    seq = state.astype(np.int16).copy()
    if dead is not None:
        seq[np.asarray(dead, dtype=bool)] = 2
    out = state.copy()
    for start, stop in runs:
        window = seq[start:stop]
        breaks = np.flatnonzero(window[1:] != window[:-1]) + 1
        bounds = np.concatenate(([0], breaks, [len(window)])) + start
        spells = [(int(a), int(b), int(seq[a])) for a, b in zip(bounds[:-1], bounds[1:])]
        for (_, _, before), (a, b, team), (c, _, after) in zip(spells, spells[1:], spells[2:]):
            if team not in (0, 1) or before != after or before != 1 - team:
                continue
            if b - a < min_frames and a not in forced and c not in forced:
                out[a:b] = before
    return out


def soft_control(f: engine.Features) -> tuple[np.ndarray, np.ndarray]:
    """V4: per-team control likelihood in [0, 1]; 0 without a ball seen inside the pitch."""

    def sigmoid(centre: float, value: np.ndarray, width: float) -> np.ndarray:
        # Unknown or absent (an untracked team) is infinitely far or fast: exp overflows to inf
        # and the likelihood is an exact 0, which is the intended value, so the warning is noise.
        far = np.where(np.isnan(value), np.inf, value)
        with np.errstate(over="ignore"):
            return 1.0 / (1.0 + np.exp((far - centre) / width))

    known = f.in_pitch & np.isfinite(f.speed_mps)
    slow = sigmoid(SOFT_SPEED_MPS, f.speed_mps, SOFT_SPEED_WIDTH_MPS)

    def reach(distance: np.ndarray) -> np.ndarray:
        near = sigmoid(SOFT_RADIUS_M, distance, SOFT_RADIUS_WIDTH_M)
        return np.where(known, near * slow, 0.0)

    return reach(f.home_m), reach(f.away_m)


def viterbi(
    llr: np.ndarray,
    ctrl: np.ndarray,
    runs: Sequence[tuple[int, int]],
    forced: dict[int, int] | None = None,
    cost: float = SWITCH_COST,
) -> np.ndarray:
    """V4: the most likely `H`/`A` path per run, `llr = log P(obs|H) - log P(obs|A)` per frame.

    A run starts at its first control (or forced frame) in that team's state, `NONE` before. A
    forced frame fixes its state. A tie between switching earlier or later resolves to the later
    frame, the engine's convention: a change begins with the new team's evidence.
    """
    forced = forced or {}
    state = np.full(len(llr), NONE, dtype=np.int8)
    for start, stop in runs:
        seeds = [start + int(i) for i in np.flatnonzero(ctrl[start:stop] != NONE)[:1]]
        seeds += [frame for frame in forced if start <= frame < stop]
        if not seeds:
            continue
        first = min(seeds)
        team = forced.get(first, int(ctrl[first]))
        half = (np.asarray(llr[first:stop], dtype=float) / 2).tolist()
        n = stop - first
        home = 0.0 if team == 0 else -math.inf
        away = 0.0 if team == 1 else -math.inf
        # came_from[t] = 1 when the best path into H (or A) at t switched from the other state.
        from_home = bytearray(n)
        from_away = bytearray(n)
        for t in range(1, n):
            stay_h, cross_h = home, away - cost
            stay_a, cross_a = away, home - cost
            from_home[t] = cross_h >= stay_h  # a tie switches here, the latest possible frame
            from_away[t] = cross_a >= stay_a
            home = (cross_h if from_home[t] else stay_h) + half[t]
            away = (cross_a if from_away[t] else stay_a) - half[t]
            team_forced = forced.get(first + t)
            if team_forced == 0:
                away = -math.inf
            elif team_forced == 1:
                home = -math.inf
        current = 0 if home >= away else 1
        path = np.empty(n, dtype=np.int8)
        for t in range(n - 1, -1, -1):
            path[t] = current
            if t and (from_home if current == 0 else from_away)[t]:
                current = 1 - current
        state[first:stop] = path
    return state


# -- the variants, as bench methods ---------------------------------------------------------------


def _inputs(f: engine.Features, ev: dead_ball.Evidence):
    """The delivered chain's evidence, unchanged: control, forced restarts, the `D` mask."""
    ctrl = engine.control(f, engine.DEFAULT)
    forced = engine.restart_controls(ev.restarts, ctrl)
    dead = dead_ball.dead_mask(ev, engine.halves(), "out")
    return ctrl, forced, dead


def _finish(state: np.ndarray, dead: np.ndarray) -> np.ndarray:
    out = engine.labels(state)
    out[np.asarray(dead, dtype=bool)] = "D"
    return out


def _uncontested_switch(f: engine.Features, ctrl: np.ndarray) -> np.ndarray:
    return uncontested(ctrl, f.home_m, f.away_m, engine.DEFAULT.radius_m)


def _engine(f: engine.Features, ev: dead_ball.Evidence) -> np.ndarray:
    ctrl, forced, dead = _inputs(f, ev)
    return _finish(decode(ctrl, engine.halves(), forced), dead)


def _mid(f: engine.Features, ev: dead_ball.Evidence) -> np.ndarray:
    ctrl, forced, dead = _inputs(f, ev)
    runs = engine.halves()
    return _finish(redate_mid(decode(ctrl, runs, forced), ctrl, runs, forced), dead)


def _uncontested(f: engine.Features, ev: dead_ball.Evidence) -> np.ndarray:
    ctrl, forced, dead = _inputs(f, ev)
    return _finish(decode(ctrl, engine.halves(), forced, _uncontested_switch(f, ctrl)), dead)


def _touch(f: engine.Features, ev: dead_ball.Evidence) -> np.ndarray:
    ctrl, forced, dead = _inputs(f, ev)
    runs = engine.halves()
    return _finish(undo_touches(decode(ctrl, runs, forced), dead, runs, forced), dead)


def _viterbi(f: engine.Features, ev: dead_ball.Evidence) -> np.ndarray:
    ctrl, forced, dead = _inputs(f, ev)
    home, away = soft_control(f)
    llr = EMISSION_LOG_ODDS * (home - away)
    return _finish(viterbi(llr, ctrl, engine.halves(), forced), dead)


def _stack(f: engine.Features, ev: dead_ball.Evidence) -> np.ndarray:
    ctrl, forced, dead = _inputs(f, ev)
    runs = engine.halves()
    state = decode(ctrl, runs, forced, _uncontested_switch(f, ctrl))
    state = undo_touches(state, dead, runs, forced)
    return _finish(redate_mid(state, ctrl, runs, forced), dead)


def _mid_uncontested(f: engine.Features, ev: dead_ball.Evidence) -> np.ndarray:
    """V6 (proposal, section 11): V5 without `touch`, the combination with no time scale."""
    ctrl, forced, dead = _inputs(f, ev)
    runs = engine.halves()
    state = decode(ctrl, runs, forced, _uncontested_switch(f, ctrl))
    return _finish(redate_mid(state, ctrl, runs, forced), dead)


Method = Callable[[engine.Features, dead_ball.Evidence], np.ndarray]

BASELINE = "engine"
VARIANTS: dict[str, Method] = {
    "mid": _mid,
    "uncontested": _uncontested,
    "touch": _touch,
    "viterbi": _viterbi,
    "mid+uncontested+touch": _stack,
}
# The follow-up of section 11, measured against V2, not against the engine; kept out of
# `VARIANTS` so the section-6 report and its rule stay what they were when they were measured.
FOLLOW_UP_BASELINE = "uncontested"
FOLLOW_UP = "mid+uncontested"
METHODS: dict[str, Method] = {BASELINE: _engine, **VARIANTS, FOLLOW_UP: _mid_uncontested}
# The pre-registered prior order (proposal, section 6), used only among variants that pass.
STACK = "mid+uncontested+touch"
STACK_PARTS = ("mid", "uncontested", "touch")
PRIOR_ORDER = ("uncontested", "mid", "touch", "viterbi")


# -- the measurements and the pre-registered rule -------------------------------------------------

LOW_BALL_BLOCKS = (7, 9, 11, 18)  # the four blocks with the least ball (DECISIONS 26)
RATE_BAND = (3.4 * 0.8, 3.4 * 1.2)


def gates(measured: dict[str, dict], baseline: str = BASELINE) -> dict[str, dict[str, bool]]:
    """G1 slice, G2 bench, G3 blocks (proposal, section 6), per variant against `baseline`."""
    base = measured[baseline]
    out = {}
    for name, m in measured.items():
        if name == baseline:
            continue
        delta = m["spell_f1"] - base["spell_f1"]
        g1 = delta >= 0 and m["wins_b"] >= m["wins_a"] and not m["jackknife_flips"]
        g2 = (
            m["bench_mean"] - base["bench_mean"] >= 0
            and m["bench_low"] - base["bench_low"] >= -0.01
        )
        halved = any(r < b / 2 for r, b in zip(m["block_rates"], base["block_rates"]))
        g3 = (
            RATE_BAND[0] <= m["match_rate"] <= RATE_BAND[1]
            and m["empty_blocks"] == 0
            and not halved
            and m["st_match"] >= base["st_match"] - 0.01
        )
        out[name] = {"G1": bool(g1), "G2": bool(g2), "G3": bool(g3)}
    return out


def select(passed: dict[str, dict[str, bool]]) -> str | None:
    """The pre-registered choice among the variants passing every gate; `None` keeps the engine."""
    ok = {name for name, g in passed.items() if all(g.values())}
    if STACK in ok and sum(part in ok for part in STACK_PARTS) >= 2:
        return STACK
    return next((name for name in PRIOR_ORDER if name in ok), None)


def adopt_follow_up(measured: dict[str, dict]) -> bool:
    """Section 11: V6 replaces V2 only if it passes G1-G3 against V2 and low-ball does not drop."""
    passed = gates(measured, FOLLOW_UP_BASELINE)[FOLLOW_UP]
    low = measured[FOLLOW_UP]["bench_low"] - measured[FOLLOW_UP_BASELINE]["bench_low"]
    return all(passed.values()) and low >= 0


def measure(names: Sequence[str]) -> dict[str, dict]:
    """Every number of the proposal's section 5, for `names` (the baseline first)."""
    from tools import bench, compare_submissions
    from tools import blocks as bl
    from tools import smart_tagging as st

    pm = bench.pm
    f, ev, gt, cut = bench.load()
    votes = st.possession_votes(st.load())
    runs = [(start, stop) for _half, start, stop in bl.halves()]
    base_codes = None
    out = {}
    for name in names:
        method = METHODS[name]
        labels = method(f, ev)
        codes = pm.label_codes(list(labels))
        base_codes = codes if base_codes is None else base_codes
        result = pm.evaluate(gt, codes)
        paired = compare_submissions.compare_codes(gt, base_codes, codes)
        jack = paired["jackknife"]
        sign = paired["sign_diagnostic"]
        summary = bench.summary(bench.bench(method, f, ev, gt, cut))
        rows = bl.measure(list(labels), f.present, votes, cut, runs)
        per_block, match = rows[:-1], rows[-1]
        tol = result["transitions"][25]
        out[name] = {
            "spell_f1": result["spell_f1_mean"],
            "macro_f1": result["macro_f1"],
            "delta": paired["delta_mean_spell_f1_b_minus_a"],
            "wins_a": sign["wins_a"],
            "wins_b": sign["wins_b"],
            "n_discordant": sign["n_discordant"],
            "jackknife_range": jack["mean_delta_range"],
            "jackknife_flips": jack["sign_differs_from_full_delta"],
            "tp_fp_fn": {
                iou: (s["n_matched"], s["n_spurious"], s["n_missed"])
                for iou, s in result["spell_f1"].items()
            },
            "n_pred": result["n_pred_spells"],
            "trans_matched": tol["n_matched"],
            "trans_gt": tol["n_gt"],
            "trans_abs_latency": tol["mean_abs_latency"],
            "team_acc": result["team_acc_gt_alive"],
            "bench_clean": summary["clean"],
            "bench_mean": summary["mean"],
            "bench_low": summary["low_mean"],
            "bench_min": summary["min"],
            "n_low": summary["n_low"],
            "match_rate": match.rate,
            "block_rates": [r.rate for r in per_block],
            "min_block_rate": min(r.rate for r in per_block),
            "max_block_rate": max(r.rate for r in per_block),
            "empty_blocks": sum(1 for r in per_block if r.possessions == 0),
            "st_match": match.st_agree,
            "st_low": float(np.mean([per_block[i - 1].st_agree for i in LOW_BALL_BLOCKS])),
            "dead_share": match.dead,
        }
    return out


def _f(value: float | None, digits: int = 4) -> str:
    return "—" if value is None else f"{value:.{digits}f}".replace(".", ",")


def _p(value: float) -> str:
    return f"{100 * value:.1f}%".replace(".", ",")


def report(measured: dict[str, dict]) -> str:
    """The section-6 tables as Markdown. Every number comes from `measured`."""
    passed = gates(measured)
    lines = _tables(measured, BASELINE)
    lines += ["", "Compuertas pre-registradas (sección 6).", ""]
    lines += _gate_table(passed)
    choice = select(passed)
    lines += [
        "",
        f"Elección por la regla: **`{choice}`**."
        if choice
        else "Elección por la regla: **ninguna** — se mantiene el decodificador del motor.",
    ]
    return "\n".join(lines) + "\n"


def report_follow_up(measured: dict[str, dict]) -> str:
    """The section-11 tables: V6 against V2, its gates and its stricter rule."""
    base, v6 = measured[FOLLOW_UP_BASELINE], measured[FOLLOW_UP]
    lines = _tables(measured, FOLLOW_UP_BASELINE)
    lines += ["", "Compuertas de la sección 6, frente a `uncontested` (sección 11).", ""]
    lines += _gate_table(gates(measured, FOLLOW_UP_BASELINE))
    low = v6["bench_low"] - base["bench_low"]
    adopted = adopt_follow_up(measured)
    lines += [
        "",
        f"Δ banco con poco balón (V6 − V2): {_f(low)}.",
        f"Decisión por la regla: **`{FOLLOW_UP if adopted else FOLLOW_UP_BASELINE}`**.",
    ]
    return "\n".join(lines) + "\n"


def _gate_table(passed: dict[str, dict[str, bool]]) -> list[str]:
    lines = ["| variante | G1 slice | G2 banco | G3 bloques |", "|---|---|---|---|"]
    for name, g in passed.items():
        cells = " | ".join("pasa" if g[k] else "**falla**" for k in ("G1", "G2", "G3"))
        lines.append(f"| `{name}` | {cells} |")
    return lines


def _tables(measured: dict[str, dict], baseline: str) -> list[str]:
    names = list(measured)
    lines = [
        f"Slice público (17 posesiones). Δ, `wins` y jackknife frente a `{baseline}`; "
        "TP/FP/FN por IoU.",
        "",
        f"| variante | spellF1 | macroF1 | Δ | wins {baseline}–var | jackknife Δ | "
        "TP/FP/FN 0,3 | 0,5 | 0,7 | pred | trans ±25 | \\|lat\\| | equipo |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for name in names:
        m = measured[name]
        lo, hi = m["jackknife_range"]
        counts = ["/".join(str(v) for v in m["tp_fp_fn"][iou]) for iou in (0.3, 0.5, 0.7)]
        lines.append(
            f"| `{name}` | {_f(m['spell_f1'])} | {_f(m['macro_f1'])} | {_f(m['delta'])} "
            f"| {m['wins_a']}–{m['wins_b']} | {_f(lo)} .. {_f(hi)} | {' | '.join(counts)} "
            f"| {m['n_pred']} | {m['trans_matched']}/{m['trans_gt']} "
            f"| {_f(m['trans_abs_latency'], 1)} | {_p(m['team_acc'])} |"
        )
    n_low = measured[names[0]]["n_low"]
    lines += [
        "",
        f"Banco de trasplante (19 donantes, {n_low} con < 50% de balón) e informe por bloques.",
        "",
        "| variante | banco limpio | media | poco balón | peor | pos/min | bloque mín–máx "
        "| sin pos. | ST partido | ST bloques 7/9/11/18 | %D |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for name in names:
        m = measured[name]
        lines.append(
            f"| `{name}` | {_f(m['bench_clean'])} | {_f(m['bench_mean'])} | {_f(m['bench_low'])} "
            f"| {_f(m['bench_min'])} | {_f(m['match_rate'], 2)} "
            f"| {_f(m['min_block_rate'], 2)}–{_f(m['max_block_rate'], 2)} | {m['empty_blocks']} "
            f"| {_p(m['st_match'])} | {_p(m['st_low'])} | {_p(m['dead_share'])} |"
        )
    return lines


# -- section 11: the block-11 diagnosis (aggregates only, no rule) --------------------------------

LONG_GAP = 500  # frames: DECISIONS 24's >500 band, where 67% of the match's missing ball is


def _true_runs(mask: np.ndarray, offset: int = 0) -> list[tuple[int, int]]:
    """Maximal `[start, stop)` runs of True, shifted by `offset`."""
    edges = np.diff(np.concatenate(([0], np.asarray(mask, dtype=np.int8), [0])))
    starts, stops = np.flatnonzero(edges == 1), np.flatnonzero(edges == -1)
    return [(offset + int(a), offset + int(b)) for a, b in zip(starts, stops)]


def _episodes(mask: np.ndarray, offset: int, join: int) -> list[tuple[int, int]]:
    """True runs joined across gaps of at most `join` frames."""
    out: list[tuple[int, int]] = []
    for a, b in _true_runs(mask, offset):
        if out and a - out[-1][1] <= join:
            out[-1] = (out[-1][0], b)
        else:
            out.append((a, b))
    return out


def diagnose_block(index: int, variant: str = FOLLOW_UP_BASELINE) -> dict:
    """The longest `variant` possession touching block `index`, described by aggregates only.

    How much of it has no ball, in how many gaps, how many of them long; and the duels the
    variant ignores inside it -- the rival's contested controls, the changes the delivered chain
    makes and V2 does not -- with the length of the ball gaps on either side of each one.
    """
    from tools import bench
    from tools import blocks as bl
    from tools import smart_tagging as st

    pm = bench.pm
    f, ev, _gt, cut = bench.load()  # the ground truth is not read
    block = cut[index - 1]
    runs = [(start, stop) for _half, start, stop in bl.halves()]
    half = next((s, e) for s, e in runs if s <= block.start < e)

    def spell_of(labels: np.ndarray) -> list[tuple[int, int, int]]:
        return pm.possession_spells(pm.fill_abstentions(pm.label_codes(list(labels)), runs), runs)

    def overlap(spell: tuple[int, int, int]) -> int:
        return max(0, min(spell[1], block.stop) - max(spell[0], block.start))

    start, stop, code = max(spell_of(METHODS[variant](f, ev)), key=overlap)
    team = 0 if code == pm.H else 1
    present = f.present[start:stop]
    gaps = _true_runs(~present, start)
    long_gaps = [(a, b) for a, b in gaps if b - a > LONG_GAP]

    ctrl = engine.control(f)
    clear = _uncontested_switch(f, ctrl)
    rival = ctrl[start:stop] == 1 - team
    contested = rival & (clear[start:stop] == NONE)
    # Ball gaps over the whole half, so a gap that crosses the possession's edge keeps its length.
    half_gaps = _true_runs(~f.present[half[0] : half[1]], half[0])
    duels = []
    for a, b in _episodes(contested, start, FPS):
        before = [g for g in half_gaps if g[1] <= a]
        after = [g for g in half_gaps if g[0] >= b]
        # The visible island holding the duel runs from the gap before it to the gap after it.
        island = (before[-1][1] if before else half[0], after[0][0] if after else half[1])
        duels.append(
            {
                "frames": b - a,
                "contested_frames": int(contested[a - start : b - start].sum()),
                "island_s": (island[1] - island[0]) / FPS,
                "gap_before_s": (before[-1][1] - before[-1][0]) / FPS if before else 0.0,
                "gap_after_s": (after[0][1] - after[0][0]) / FPS if after else 0.0,
            }
        )

    delivered = _engine(f, ev)[start:stop]
    other = "A" if team == 0 else "H"
    votes = st.possession_votes(st.load())[start:stop]
    single = (votes[:, 0] > 0) ^ (votes[:, 1] > 0)
    owner = np.where(votes[:, 0] > 0, 0, 1)
    return {
        "variant": variant,
        "block": index,
        "team": pm.LABELS[code],
        "length_s": (stop - start) / FPS,
        "block_share": overlap((start, stop, code)) / (block.stop - block.start),
        "ball_share": float(present.mean()),
        "missing_s": float((~present).sum()) / FPS,
        "n_gaps": len(gaps),
        "longest_gap_s": max((b - a for a, b in gaps), default=0) / FPS,
        "n_long_gaps": len(long_gaps),
        "long_gap_share": sum(b - a for a, b in long_gaps) / max(1, int((~present).sum())),
        "rival_uncontested_frames": int((rival & (clear[start:stop] != NONE)).sum()),
        "duels": duels,
        "delivered_other_share": float((delivered == other).mean()),
        "delivered_switches": len(
            _switches(np.where(delivered == other, 1, 0), [(0, len(delivered))])
        ),
        "st_cover": float(single.mean()),
        "st_for_team": float((owner[single] == team).mean()) if single.any() else float("nan"),
    }


def report_block(d: dict) -> str:
    """The diagnosis as Markdown, aggregates only."""
    lines = [
        f"Bloque {d['block']}, posesión más larga de `{d['variant']}` que lo toca: equipo "
        f"`{d['team']}`, {_f(d['length_s'], 1)} s, {_p(d['block_share'])} del bloque.",
        "",
        "| balón en la posesión | sin balón | huecos | hueco más largo | huecos > 20 s "
        "| parte del déficit en ellos | controles rivales sin disputa |",
        "|---:|---:|---:|---:|---:|---:|---:|",
        f"| {_p(d['ball_share'])} | {_f(d['missing_s'], 1)} s | {d['n_gaps']} "
        f"| {_f(d['longest_gap_s'], 1)} s | {d['n_long_gaps']} | {_p(d['long_gap_share'])} "
        f"| {d['rival_uncontested_frames']} |",
        "",
        "Duelos que la variante ignora dentro de esa posesión (controles rivales disputados, "
        "unidos si distan ≤ 1 s), con la isla de balón visible que los contiene y los huecos a "
        "cada lado:",
        "",
        "| duelo | frames | disputados | isla visible | hueco antes | hueco después |",
        "|---:|---:|---:|---:|---:|---:|",
    ]
    for i, duel in enumerate(d["duels"], 1):
        lines.append(
            f"| {i} | {duel['frames']} | {duel['contested_frames']} | {_f(duel['island_s'], 1)} s "
            f"| {_f(duel['gap_before_s'], 1)} s | {_f(duel['gap_after_s'], 1)} s |"
        )
    lines += [
        "",
        f"La cadena entregada etiqueta {_p(d['delivered_other_share'])} de esa posesión con el "
        f"otro equipo, en {d['delivered_switches']} cambios. Smart Tagging: cubre "
        f"{_p(d['st_cover'])} de la posesión y, de eso, vota `{d['team']}` en "
        f"{_p(d['st_for_team'])}.",
    ]
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Lane decode: decodings of the engine's control")
    parser.add_argument("--variant", choices=sorted(METHODS), help="decode with this variant")
    parser.add_argument("--labels", type=Path, help="write the variant's frame,label CSV here")
    parser.add_argument("--report", action="store_true", help="print every measurement")
    parser.add_argument("--block", type=int, help="diagnose V2's longest possession in a block")
    args = parser.parse_args(argv)
    try:
        if args.report or args.block:
            if args.report:
                text = report(measure([BASELINE, *VARIANTS]))
                text += "\n## V6 frente a V2 (sección 11)\n\n"
                text += report_follow_up(measure([FOLLOW_UP_BASELINE, FOLLOW_UP]))
            else:
                text = report_block(diagnose_block(args.block))
            if hasattr(sys.stdout, "reconfigure"):
                sys.stdout.reconfigure(encoding="utf-8")
            sys.stdout.write(text)
            return 0
        if not (args.variant and args.labels):
            parser.error("give --report, or --variant with --labels")
        from tools import atd, emision

        f = engine.features(atd.load("tactical"), emision.team_slots())
        labels = METHODS[args.variant](f, dead_ball.load_evidence())
        table = pd.DataFrame({"frame": np.arange(len(labels)), "label": labels})
        check_submission(table, args.labels)
        args.labels.parent.mkdir(parents=True, exist_ok=True)
        table.to_csv(args.labels, index=False, lineterminator="\n")
        print(f"wrote {args.labels}")
    except (OSError, ValueError, RuntimeError) as problem:
        print(f"decoder failed: {problem}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
