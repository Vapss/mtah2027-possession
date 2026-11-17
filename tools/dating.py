"""Lane dating: WHEN possession changes, apart from WHETHER (docs/proposals/lane-dating.md).

    python tools/dating.py --explore           # the hand-over of every change; no ground truth
    python tools/dating.py --report            # every measurement of the proposal
    python tools/dating.py --variant first --labels runs/dating/first.csv

The delivered chain (`tools/engine.py`, DECISIONS 29-36) decides WHETHER possession changes with the
duel rule: a rival control changes it only when the team in possession has nobody within reach of
the ball. It then dates the change AT that control. This module keeps every decision of the chain
(same control, same duel rule, same forced restarts, same `D`) and moves only the date of each
natural change, back into its hand-over:

- the hand-over of a change from `old` to `new` at frame `c` is `(l, c]`, with `l` the last frame
  before `c` where `old` controlled the ball or was handed it by a restart, or the last stoppage
  frame if that is later: a date never moves across a stoppage or a restart;
- `first` (V-a) dates the change to the first control of `new` in the hand-over, contested or not;
- `touch` (V-b) dates it to the first frame of the hand-over where `new` is within reach of the
  ball at any speed: `engine.control` without its speed test.

No constant is new: the reach is the engine's 1,5 m. The number of changes, their teams and every
`D` frame are the delivered chain's; only the frames inside a hand-over can change team. Each
variant is a bench method `(features, evidence) -> labels`.
"""

from __future__ import annotations

import argparse
import math
import sys
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from tools import dead_ball, engine  # noqa: E402
from tools.contract import check_submission  # noqa: E402

NONE = engine.NONE
FPS = engine.FPS

# Diagnostics only, never a gate or a filter of a selectable variant (proposal, section 4): "a pass
# travels at 10 m/s and more" (engine.Params), and above 20 m/s the nearest player is right 39% of
# the time (DECISIONS 29). An anchor faster than that may be a ball flying past a player.
PASS_MPS = 10.0
FLIGHT_MPS = 20.0


def touch(f: engine.Features, radius_m: float = engine.DEFAULT.radius_m) -> np.ndarray:
    """`0` / `1` where that team's nearest player is within `radius_m` of a ball inside the pitch
    and strictly nearer than the other team's, at any speed (also unknown); `NONE` elsewhere.

    It is `engine.control` without the speed test, so every control frame is a touch frame.
    """
    nearest = np.fmin(f.home_m, f.away_m)
    close = f.in_pitch & (nearest <= radius_m)
    team = np.full(len(f.present), NONE, dtype=np.int8)
    team[close & (f.home_m < f.away_m)] = 0
    team[close & (f.away_m < f.home_m)] = 1
    return team


@dataclass(frozen=True)
class Handover:
    """One natural change of the delivered chain: `old` -> `new`, dated at `frame`."""

    frame: int  # c: the delivered date, the first uncontested control of `new`
    old: int
    new: int
    after: int  # l: the hand-over is (after, frame]


def handovers(
    state: np.ndarray,
    ctrl: np.ndarray,
    runs: Sequence[tuple[int, int]],
    forced: dict[int, int] | None = None,
    dead: np.ndarray | None = None,
) -> list[Handover]:
    """Every natural (not forced) `H <-> A` change of `state`, with where its hand-over begins.

    The hand-over begins after the last frame, inside the old team's spell, where the old team
    controlled the ball (contested or not), was forced the ball by a restart, or the ball was dead.
    Without any of them it begins at the spell's first frame, which is the old team's own change.
    """
    forced = forced or {}
    stopped = np.zeros(len(state), dtype=bool) if dead is None else np.asarray(dead, dtype=bool)
    out: list[Handover] = []
    for start, stop in runs:
        window = state[start:stop]
        change = (window[1:] != window[:-1]) & (window[1:] != NONE) & (window[:-1] != NONE)
        spell_start = start
        for c in (np.flatnonzero(change) + 1 + start).tolist():
            old, new = int(state[c - 1]), int(state[c])
            if c not in forced:
                marks = np.flatnonzero((ctrl[spell_start:c] == old) | stopped[spell_start:c])
                last = spell_start + int(marks[-1]) if marks.size else spell_start
                pushed = [f for f, team in forced.items() if spell_start <= f < c and team == old]
                out.append(Handover(c, old, new, max([last, *pushed])))
            spell_start = c
    return out


def anchor(h: Handover, evidence: np.ndarray) -> int:
    """The first frame of `(h.after, h.frame]` where `evidence` shows the new team.

    `h.frame` always qualifies when `evidence` contains the control (`ctrl` and `touch` do), so the
    anchor is never later than the delivered date.
    """
    seen = np.flatnonzero(evidence[h.after + 1 : h.frame + 1] == h.new)
    return h.after + 1 + int(seen[0]) if seen.size else h.frame


def redate(
    state: np.ndarray,
    changes: Sequence[Handover],
    evidence: np.ndarray,
    accept: np.ndarray | None = None,
) -> np.ndarray:
    """`state` with each change moved back to its anchor in `evidence` (`accept[anchor]`, if given,
    must hold for the move). Only frames inside a hand-over change, and only to the new team."""
    out = state.copy()
    for h in changes:
        a = anchor(h, evidence)
        if accept is None or accept[a]:
            out[a : h.frame] = h.new
    return out


# -- the variants, as bench methods ---------------------------------------------------------------


@dataclass(frozen=True)
class Chain:
    """The delivered chain's pieces, built exactly as `engine.chain` builds them."""

    ctrl: np.ndarray
    state: np.ndarray
    forced: dict[int, int]
    dead: np.ndarray


def delivered(
    f: engine.Features, ev: dead_ball.Evidence, params: engine.Params = engine.DEFAULT
) -> Chain:
    dead = engine.delivered_dead(ev)
    ctrl, switch, forced = engine.inputs(f, params, ev.restarts, dead)
    forced = forced or {}
    state = engine.decode(ctrl, engine.halves(), params.dwell, forced, switch)
    return Chain(ctrl, state, forced, dead)


def finish(state: np.ndarray, dead: np.ndarray) -> np.ndarray:
    out = engine.labels(state)
    out[np.asarray(dead, dtype=bool)] = "D"
    return out


def _changes(chain: Chain) -> list[Handover]:
    return handovers(chain.state, chain.ctrl, engine.halves(), chain.forced, chain.dead)


def _none(f: engine.Features, ev: dead_ball.Evidence) -> np.ndarray:
    """V-c, the negative control: no redating, which must be the delivered chain exactly."""
    chain = delivered(f, ev)
    return finish(chain.state, chain.dead)


def _first(f: engine.Features, ev: dead_ball.Evidence) -> np.ndarray:
    chain = delivered(f, ev)
    return finish(redate(chain.state, _changes(chain), chain.ctrl), chain.dead)


def _touch(f: engine.Features, ev: dead_ball.Evidence) -> np.ndarray:
    chain = delivered(f, ev)
    return finish(redate(chain.state, _changes(chain), touch(f)), chain.dead)


def _touch_slow(f: engine.Features, ev: dead_ball.Evidence) -> np.ndarray:
    """Diagnostic of V-b, not a variant: only changes whose touch anchor is at <= 10 m/s move."""
    chain = delivered(f, ev)
    slow = np.nan_to_num(f.speed_mps, nan=np.inf) <= PASS_MPS
    return finish(redate(chain.state, _changes(chain), touch(f), slow), chain.dead)


Method = Callable[[engine.Features, dead_ball.Evidence], np.ndarray]

BASELINE = "none"
VARIANTS: dict[str, Method] = {"first": _first, "touch": _touch}
DIAGNOSTIC = "touch<=10"
METHODS: dict[str, Method] = {BASELINE: _none, **VARIANTS, DIAGNOSTIC: _touch_slow}
PRIOR_ORDER = ("first", "touch")  # proposal, section 6: used only among variants that pass


# -- exploration, without ground truth ------------------------------------------------------------


def reach(f: engine.Features, radius_m: float = engine.DEFAULT.radius_m) -> np.ndarray:
    """Per frame, why `touch` does or does not name a team: one of `REACH`.

    `unseen` no ball; `off` a ball outside the pitch; `nobody` nobody within `radius_m`; `tie` both
    teams' nearest equally close within it; `near` one team strictly nearer within it (`touch`).
    """
    nearest = np.fmin(f.home_m, f.away_m)
    out = np.full(len(f.present), "unseen", dtype=object)
    out[f.present & ~f.in_pitch] = "off"
    inside = f.present & f.in_pitch
    within = inside & (nearest <= radius_m)
    out[inside & ~within] = "nobody"
    out[within & (f.home_m == f.away_m)] = "tie"
    out[within & (f.home_m != f.away_m)] = "near"
    return out


REACH = ("unseen", "off", "nobody", "tie", "near")


def shift_row(name: str, shift: np.ndarray) -> str:
    """One row of the redating table; an empty `shift` (no natural change) prints zeros."""
    shift = np.asarray(shift, dtype=np.int64)
    moved = shift[shift > 0]
    mean = float(shift.mean()) if len(shift) else 0.0
    most = int(shift.max()) if len(shift) else 0
    return (
        f"| `{name}` | {len(moved)} de {len(shift)} | {_f(mean, 1)} | {_pctl(moved)} "
        f"| {most} | {int(shift.sum())} |"
    )


def _pctl(values: Sequence[float]) -> str:
    if not len(values):
        return "—"
    return " / ".join(f"{v:.0f}" for v in np.percentile(values, [10, 25, 50, 75, 90]))


def explore(f: engine.Features, ev: dead_ball.Evidence) -> str:
    """The hand-overs of the delivered chain over the match, as aggregates (proposal, section 2)."""
    chain = delivered(f, ev)
    changes = _changes(chain)
    n_forced = len(handovers(chain.state, chain.ctrl, engine.halves())) - len(changes)
    near = touch(f)
    gaps = [h.frame - h.after - 1 for h in changes]
    inside = np.zeros(len(chain.state), dtype=bool)
    for h in changes:
        inside[h.after + 1 : h.frame] = True
    why = reach(f)[inside]
    count = {k: int((why == k).sum()) for k in REACH}
    lines = [
        "Exploración sin ground truth: los traspasos de la cadena entregada en el partido.",
        "",
        f"Cambios naturales: {len(changes)}; forzados por una reanudación: {n_forced}.",
        "",
        "| | valor |",
        "|---|---:|",
        f"| hueco del traspaso (l, c), frames, p10/25/50/75/90 | {_pctl(gaps)} |",
        f"| frames dentro de traspasos | {int(inside.sum())} |",
        f"| de ellos, sin balón | {_share(count['unseen'], inside.sum())} |",
        f"| balón visto fuera del campo | {_share(count['off'], inside.sum())} |",
        f"| balón visto en el campo, nadie a ≤ 1,5 m | {_share(count['nobody'], inside.sum())} |",
        f"| balón visto en el campo, empate a ≤ 1,5 m | {_share(count['tie'], inside.sum())} |",
        f"| balón visto en el campo, un equipo más cerca a ≤ 1,5 m "
        f"| {_share(count['near'], inside.sum())} |",
        "",
        "| variante | cambios movidos | adelanto medio | adelanto de los movidos p10/25/50/75/90 "
        "| adelanto máx. | frames reetiquetados |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for name, evidence in (("first", chain.ctrl), ("touch", near)):
        lines.append(shift_row(name, np.array([h.frame - anchor(h, evidence) for h in changes])))
    speeds = np.array([f.speed_mps[anchor(h, near)] for h in changes if anchor(h, near) < h.frame])
    known = speeds[np.isfinite(speeds)]
    lines += [
        "",
        f"Anclas de `touch` que mueven un cambio: {len(speeds)}. Velocidad del balón en el ancla: "
        f"desconocida {_share(len(speeds) - len(known), len(speeds))}, "
        f"≤ {PASS_MPS:.0f} m/s {_share(int((known <= PASS_MPS).sum()), len(speeds))}, "
        f"> {PASS_MPS:.0f} m/s {_share(int((known > PASS_MPS).sum()), len(speeds))}, "
        f"> {FLIGHT_MPS:.0f} m/s {_share(int((known > FLIGHT_MPS).sum()), len(speeds))}.",
    ]
    return "\n".join(lines) + "\n"


def _share(part: float, whole: float) -> str:
    return _p(part / whole) if whole else "—"


# -- the per-possession IoU sign test (proposal, section 5) ---------------------------------------


def best_iou(
    gt_spells: Sequence[tuple[int, int, int]], pred_spells: Sequence[tuple[int, int, int]]
) -> np.ndarray:
    """For each ground-truth spell, the highest IoU of any same-team predicted spell (0 if none)."""
    from tools.bench import pm

    best = np.zeros(len(gt_spells))
    for iou, gt_index, _pred_index in pm.spell_overlaps(gt_spells, pred_spells):
        best[gt_index] = max(best[gt_index], iou)
    return best


def iou_sign_test(gt: np.ndarray, codes_a: np.ndarray, codes_b: np.ndarray) -> dict:
    """Per ground-truth possession, best same-team IoU of `b` against `a`: improved, worsened,
    tied (exactly equal), and the exact two-sided binomial p over the untied ones."""
    from tools.bench import pm

    runs = pm.valid_runs(gt)
    gt_spells = pm.possession_spells(gt, runs)
    a = best_iou(gt_spells, pm.possession_spells(pm.fill_abstentions(codes_a, runs), runs))
    b = best_iou(gt_spells, pm.possession_spells(pm.fill_abstentions(codes_b, runs), runs))
    better, worse = int((b > a).sum()), int((b < a).sum())
    n = better + worse
    tail = sum(math.comb(n, k) for k in range(min(better, worse) + 1))
    return {
        "improved": better,
        "worsened": worse,
        "ties": len(gt_spells) - n,
        "p": min(1.0, 2.0 * tail / 2**n) if n else 1.0,
        "lost_at_half": int(((a >= 0.5) & (b < 0.5)).sum()),
        "before": a.tolist(),
        "after": b.tolist(),
    }


def start_offsets(gt: np.ndarray, codes: np.ndarray) -> list[float | None]:
    """Seconds from each ground-truth possession's start to the start of its best same-team
    predicted spell (`None` if no spell overlaps it): positive is late."""
    from tools.bench import pm

    runs = pm.valid_runs(gt)
    gt_spells = pm.possession_spells(gt, runs)
    pred = pm.possession_spells(pm.fill_abstentions(codes, runs), runs)
    best: dict[int, int] = {}
    for _iou, gt_index, pred_index in pm.spell_overlaps(gt_spells, pred):
        best.setdefault(gt_index, pred_index)  # the list is IoU-descending
    return [
        (pred[best[i]][0] - spell[0]) / FPS if i in best else None
        for i, spell in enumerate(gt_spells)
    ]


# -- the measurements and the pre-registered rule -------------------------------------------------

LOW_BALL_BLOCKS = (7, 9, 11, 18)  # the four blocks with the least ball (DECISIONS 26)
RATE_BAND = (3.4 * 0.8, 3.4 * 1.2)
SIGN_P = 0.05


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
        sign = paired["sign_diagnostic"]
        jack = paired["jackknife"]
        summary = bench.summary(bench.bench(method, f, ev, gt, cut))
        rows = bl.measure(list(labels), f.present, votes, cut, runs)
        per_block, match = rows[:-1], rows[-1]
        tol = result["transitions"][25]
        offsets = [o for o in start_offsets(gt, codes) if o is not None]
        out[name] = {
            "labels": labels,
            "spell_f1": result["spell_f1_mean"],
            "macro_f1": result["macro_f1"],
            "delta": paired["delta_mean_spell_f1_b_minus_a"],
            "wins_a": sign["wins_a"],
            "wins_b": sign["wins_b"],
            "jackknife_range": jack["mean_delta_range"],
            "jackknife_flips": jack["sign_differs_from_full_delta"],
            "iou": iou_sign_test(gt, base_codes, codes),
            "tp": [s["n_matched"] for s in result["spell_f1"].values()],
            "n_pred": result["n_pred_spells"],
            "trans_matched": tol["n_matched"],
            "trans_gt": tol["n_gt"],
            "trans_abs_latency": tol["mean_abs_latency"],
            "start_offset_median": float(np.median(offsets)) if offsets else float("nan"),
            "start_offset_mean_abs": float(np.mean(np.abs(offsets))) if offsets else float("nan"),
            "bench_clean": summary["clean"],
            "bench_mean": summary["mean"],
            "bench_low": summary["low_mean"],
            "bench_min": summary["min"],
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


def gates(measured: dict[str, dict], baseline: str = BASELINE) -> dict[str, dict[str, bool]]:
    """G1 slice, G2 bench, G3 blocks (proposal, section 6), per variant against `baseline`."""
    base = measured[baseline]
    out = {}
    for name, m in measured.items():
        if name == baseline:
            continue
        iou = m["iou"]
        g1 = (
            m["delta"] >= 0
            and iou["improved"] > iou["worsened"]
            and iou["p"] <= SIGN_P
            and m["wins_a"] == 0
            and not m["jackknife_flips"]
        )
        g2 = m["bench_mean"] >= base["bench_mean"] and m["bench_low"] >= base["bench_low"]
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
    """The pre-registered choice: the first variant in `PRIOR_ORDER` passing every gate; `None`
    keeps the delivered chain."""
    ok = {name for name, g in passed.items() if all(g.values())}
    return next((name for name in PRIOR_ORDER if name in ok), None)


def _f(value: float | None, digits: int = 4) -> str:
    return "—" if value is None or value != value else f"{value:.{digits}f}".replace(".", ",")


def _p(value: float) -> str:
    return f"{100 * value:.1f}%".replace(".", ",")


def report(measured: dict[str, dict]) -> str:
    names = list(measured)
    lines = [
        f"Slice público (17 posesiones). Δ, `wins` y jackknife frente a `{BASELINE}`; TP por IoU "
        "0,3 / 0,4 / 0,5 / 0,6 / 0,7.",
        "",
        "| variante | spellF1 | macroF1 | Δ | wins none–var | jackknife Δ | TP | pred "
        "| trans ±25 | \\|lat\\| | inicio: mediana / media \\|·\\| (s) |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for name in names:
        m = measured[name]
        lo, hi = m["jackknife_range"]
        lines.append(
            f"| `{name}` | {_f(m['spell_f1'])} | {_f(m['macro_f1'])} | {_f(m['delta'])} "
            f"| {m['wins_a']}–{m['wins_b']} | {_f(lo)} .. {_f(hi)} "
            f"| {' / '.join(str(t) for t in m['tp'])} | {m['n_pred']} "
            f"| {m['trans_matched']}/{m['trans_gt']} | {_f(m['trans_abs_latency'], 1)} "
            f"| {_f(m['start_offset_median'], 2)} / {_f(m['start_offset_mean_abs'], 2)} |"
        )
    lines += [
        "",
        "Test de signos por posesión: mejor IoU del mismo equipo, variante frente a `none`.",
        "",
        "| variante | mejoran | empeoran | empates | p exacto (dos colas) | pierden IoU ≥ 0,5 |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for name in names[1:]:
        s = measured[name]["iou"]
        lines.append(
            f"| `{name}` | {s['improved']} | {s['worsened']} | {s['ties']} | {_f(s['p'])} "
            f"| {s['lost_at_half']} |"
        )
    lines += [
        "",
        "Banco de trasplante (19 donantes, 6 con < 50% de balón) e informe por bloques.",
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
    selectable = {n: m for n, m in measured.items() if n == BASELINE or n in VARIANTS}
    passed = gates(selectable)
    lines += [
        "",
        "Compuertas pre-registradas (sección 6), frente a `none`.",
        "",
        "| variante | G1 slice | G2 banco | G3 bloques |",
        "|---|---|---|---|",
    ]
    for name, g in passed.items():
        cells = " | ".join("pasa" if g[k] else "**falla**" for k in ("G1", "G2", "G3"))
        lines.append(f"| `{name}` | {cells} |")
    choice = select(passed)
    lines += [
        "",
        f"Elección por la regla: **`{choice}`**."
        if choice
        else "Elección por la regla: **ninguna; se mantiene la cadena entregada**.",
    ]
    return "\n".join(lines) + "\n"


def report_possessions() -> str:
    """Post-hoc, not pre-registered (proposal, section 9): each true possession of the slice."""
    from tools import bench

    pm = bench.pm
    f, ev, gt, _cut = bench.load()
    runs = pm.valid_runs(gt)
    spells = pm.possession_spells(gt, runs)
    codes = {name: pm.label_codes(list(METHODS[name](f, ev))) for name in METHODS}
    iou = {
        name: best_iou(spells, pm.possession_spells(pm.fill_abstentions(c, runs), runs))
        for name, c in codes.items()
    }
    offset = {name: start_offsets(gt, codes[name]) for name in (BASELINE, "touch", DIAGNOSTIC)}
    lines = [
        "Por posesión verdadera del slice: mejor IoU del mismo equipo y desfase del inicio de esa "
        "posesión predicha (s, positivo = tarde). Diagnóstico posterior, no pre-registrado.",
        "",
        "| # | equipo | dura (s) | IoU none | first | touch | touch<=10 "
        "| inicio none | touch | touch<=10 |",
        "|---:|---|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for i, (start, stop, team) in enumerate(spells):
        cells = " | ".join(_f(iou[n][i], 3) for n in METHODS)
        starts = " | ".join(_f(offset[n][i], 2) for n in offset)
        lines.append(
            f"| {i + 1} | {pm.LABELS[team]} | {_f((stop - start) / FPS, 1)} | {cells} | {starts} |"
        )
    # Where the delivered chain starts late: what it says on the late frames, and what the tracking
    # shows there (control frames of each team, and touches of the new team that are not controls).
    chain = delivered(f, ev)
    filled = pm.fill_abstentions(codes[BASELINE], runs)
    switch = engine.uncontested(chain.ctrl, f, engine.DEFAULT.radius_m)
    near = touch(f)
    side = {pm.H: 0, pm.A: 1}
    lines += [
        "",
        "Posesiones que la cadena entregada empieza tarde: frames `[inicio verdadero, inicio "
        "predicho)`.",
        "",
        "| # | tarde (s) | `D` | otro equipo | mismo equipo | balón visto | control anterior "
        "sin disputa | control anterior disputado | control nuevo | toque nuevo sin control |",
        "|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for i, ((start, _stop, team), late) in enumerate(zip(spells, offset[BASELINE])):
        if late is None or late <= 0:
            continue
        window = slice(start, start + int(round(late * FPS)))
        seg, new = filled[window], side[team]
        lines.append(
            f"| {i + 1} | {_f(late, 2)} | {_p(np.mean(seg == pm.D))} "
            f"| {_p(np.mean((seg != pm.D) & (seg != team)))} | {_p(np.mean(seg == team))} "
            f"| {_p(f.present[window].mean())} | {int((switch[window] == 1 - new).sum())} "
            f"| {int(((chain.ctrl[window] == 1 - new) & (switch[window] != 1 - new)).sum())} "
            f"| {int((chain.ctrl[window] == new).sum())} "
            f"| {int(((near[window] == new) & (chain.ctrl[window] != new)).sum())} |"
        )
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Lane dating: when a change of possession happens")
    parser.add_argument("--explore", action="store_true", help="hand-overs, no ground truth")
    parser.add_argument("--report", action="store_true", help="every measurement of the proposal")
    parser.add_argument("--possessions", action="store_true", help="post-hoc, per true possession")
    parser.add_argument("--variant", choices=sorted(METHODS), help="label the match with one")
    parser.add_argument("--labels", type=Path, help="write the variant's frame,label CSV here")
    args = parser.parse_args(argv)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    try:
        if args.explore:
            from tools import atd, emision

            f = engine.features(atd.load("tactical"), emision.team_slots())
            sys.stdout.write(explore(f, dead_ball.load_evidence()))
        if args.report:
            sys.stdout.write(report(measure(list(METHODS))))
        if args.possessions:
            sys.stdout.write(report_possessions())
        if args.variant:
            from tools import atd, emision

            f = engine.features(atd.load("tactical"), emision.team_slots())
            labels = METHODS[args.variant](f, dead_ball.load_evidence())
            table = pd.DataFrame({"frame": np.arange(len(labels)), "label": labels})
            if args.labels:
                check_submission(table, args.labels)
                args.labels.parent.mkdir(parents=True, exist_ok=True)
                table.to_csv(args.labels, index=False, lineterminator="\n")
                print(f"wrote {args.labels}")
    except (OSError, ValueError, RuntimeError) as problem:
        print(f"dating failed: {problem}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
