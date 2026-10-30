"""Lane m-dating: WHEN possession changes in open play, judged on Metrica's open games.

    python tools/change_dating.py --calibrate        # STEP 1: the delivered chain's dating error

The delivered chain (`tools/engine.py`, DECISIONS 29-36) dates a change of possession at the new
team's first uncontested control: nearest player within 1.5 m, the other team not as close, the ball
at most 5 m/s, and (duel rule) the team in possession with nobody within 1.5 m. On the public slice
its matched possessions start late (+0.5 .. +5 s, median ~+1.4 s), but every attempt to re-date them
was judged on that same slice (lane-dating.md). This module measures the dating error against an
EXTERNAL truth: the event logs of Metrica's open games (`tools/metrica_open.py`, rules E1-E5).

The instrument, fixed before the first engine output on Metrica
---------------------------------------------------------------
- **The chain on Metrica** is the delivered one with Metrica's halves: `engine.inputs` (control,
  duel rule, restarts) and `engine.decode`, the events' set pieces and goal kicks as tagged
  restarts (team known, Smart Tagging's window), and the delivered `D`: tagged stoppages
  (`dead_ball.dead_mask`, "out") united with the players' stoppages (W1,
  `dead_ball_v2.kinematic_mask`, "rule").
- **A chain change** is a frame where the decoded state goes from one team to the other inside a
  half (the state, before `D` is written over it: `D` is not a dating rule).
- **Matching.** Each open-play truth change (E5) is paired with at most one chain change to the
  SAME new team within `TOLERANCE_S` either side, one to one, closest pairs first (ties: earlier
  truth change first). The signed lag is `chain - truth` in seconds: positive is late.
- **Reported:** matched / missed truth changes, unmatched chain changes, and the lag's median,
  median |lag|, mean |lag|, quantiles and the share within 0.5 s and 1 s, per game and per half.
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

import numpy as np

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from tools import dead_ball, engine  # noqa: E402

NONE = engine.NONE
FPS = engine.FPS
# Pre-registered before the first engine run on Metrica: wider than every late start the public
# slice shows but one (+0.5 .. +5 s, one at +7 s), narrower than the truth's median possession
# twice over, so a change is not paired with the one after next.
TOLERANCE_S = 5.0


# -- the chain ---------------------------------------------------------------------------------


@dataclass(frozen=True)
class Chain:
    """The delivered chain's pieces on one match, built exactly as `engine.chain` builds them."""

    ctrl: np.ndarray
    switch: np.ndarray | None
    forced: dict[int, int]
    state: np.ndarray
    dead: np.ndarray


def delivered(
    f: engine.Features,
    ev: dead_ball.Evidence,
    runs: Sequence[tuple[int, int]],
    dead: np.ndarray,
    params: engine.Params = engine.DEFAULT,
) -> Chain:
    ctrl, switch, forced = engine.inputs(f, params, ev.restarts)
    forced = forced or {}
    state = engine.decode(ctrl, [tuple(r) for r in runs], params.dwell, forced, switch)
    return Chain(ctrl, switch, forced, state, np.asarray(dead, dtype=bool))


def finish(state: np.ndarray, dead: np.ndarray) -> np.ndarray:
    """`H` / `A` / `X` from the state, then `D` over the stoppages: `engine.chain`'s last step."""
    out = engine.labels(state)
    out[np.asarray(dead, dtype=bool)] = "D"
    return out


def _engine(f: engine.Features, ev: dead_ball.Evidence) -> np.ndarray:
    """The reference variant on BAR-ATH: the delivered chain rebuilt from this module's pieces.
    `tests/test_change_dating.py` pins it to the delivered file's SHA-256 (`72c98ed4bb4a`)."""
    chain = delivered(f, ev, engine.halves(), engine.delivered_dead(ev))
    return finish(chain.state, chain.dead)


METHODS = {"engine": _engine}  # bench-style `(features, evidence) -> labels`, BAR-ATH's halves


def metrica_dead(game) -> np.ndarray:
    """The delivered `D` on a Metrica game: `engine.delivered_dead`'s union with this game's
    players (that function is pinned to BAR-ATH's)."""
    from tools import dead_ball_v2, metrica_open

    runs = [tuple(r) for r in game.runs]
    kinematic = dead_ball_v2.kinematic_mask(game.players_m, metrica_open.PITCH_M, runs, "rule")
    return dead_ball_v2.dead_union("rule", game.evidence, kinematic, runs)


# -- changes and their dating error ------------------------------------------------------------


def state_changes(state: np.ndarray, runs: Sequence[tuple[int, int]]) -> list[tuple[int, int]]:
    """`(frame, new team)` for every frame where `state` goes from one team to the other inside a
    run. The first state of a run is not a change: nothing was there before it."""
    out = []
    for start, stop in runs:
        window = np.asarray(state[start:stop])
        flip = (window[1:] != window[:-1]) & (window[1:] != NONE) & (window[:-1] != NONE)
        out += [(start + 1 + int(i), int(window[i + 1])) for i in np.flatnonzero(flip)]
    return out


def match(
    truth: Sequence[tuple[int, int]],
    pred: Sequence[tuple[int, int]],
    tolerance: int = int(TOLERANCE_S * FPS),
) -> list[tuple[int, int]]:
    """One-to-one `(truth frame, pred frame)` pairs: same new team, `|pred - truth| <= tolerance`,
    closest pairs first, ties broken by the earlier truth change then the earlier prediction."""
    candidates = []
    pred_frames = np.array([p for p, _ in pred], dtype=np.int64)
    pred_teams = np.array([t for _, t in pred], dtype=np.int64)
    for i, (frame, team) in enumerate(truth):
        near = np.flatnonzero(
            (np.abs(pred_frames - frame) <= tolerance) & (pred_teams == team)
        ).tolist()
        candidates += [
            (abs(int(pred_frames[j]) - frame), frame, int(pred_frames[j]), i, j) for j in near
        ]
    used_t: set[int] = set()
    used_p: set[int] = set()
    pairs = []
    for _gap, frame, at, i, j in sorted(candidates):
        if i in used_t or j in used_p:
            continue
        used_t.add(i)
        used_p.add(j)
        pairs.append((frame, at))
    return sorted(pairs)


def lag_stats(lags_s: Sequence[float]) -> dict:
    """The dating error of matched changes, in seconds (positive = the chain is late)."""
    lags = np.asarray(lags_s, dtype=float)
    if not lags.size:
        nan = float("nan")
        return {
            "n": 0,
            "median": nan,
            "median_abs": nan,
            "mean_abs": nan,
            "q": [nan] * 5,
            "within_05": nan,
            "within_1": nan,
            "late_1": nan,
        }
    return {
        "n": int(lags.size),
        "median": float(np.median(lags)),
        "median_abs": float(np.median(np.abs(lags))),
        "mean_abs": float(np.mean(np.abs(lags))),
        "q": [float(v) for v in np.quantile(lags, [0.1, 0.25, 0.5, 0.75, 0.9])],
        "within_05": float((np.abs(lags) <= 0.5).mean()),
        "within_1": float((np.abs(lags) <= 1.0).mean()),
        "late_1": float((lags > 1.0).mean()),
    }


def dating(
    truth: Sequence[tuple[int, int]],
    pred: Sequence[tuple[int, int]],
    window: tuple[int, int] | None = None,
) -> dict:
    """Matched / missed / extra and the lag statistics, optionally inside one `[start, stop)`."""
    if window is not None:
        start, stop = window
        truth = [c for c in truth if start <= c[0] < stop]
        pred = [c for c in pred if start <= c[0] < stop]
    pairs = match(truth, pred)
    return {
        "truth": len(truth),
        "pred": len(pred),
        "matched": len(pairs),
        "missed": len(truth) - len(pairs),
        "extra": len(pred) - len(pairs),
        **lag_stats([(at - frame) / FPS for frame, at in pairs]),
    }


def open_play(game) -> list[tuple[int, int]]:
    """`(frame, new team)` of the event truth's open-play changes (E5)."""
    return [(c.frame, c.new) for c in game.truth.changes if c.open_play]


def label_changes(labels: np.ndarray, runs: Sequence[tuple[int, int]]) -> list[tuple[int, int]]:
    """`(frame, new team)` where the labels the scorer sees first show a team other than the last
    team shown, `D` and `X` skipped: the change after `D` is written over the state."""
    out = []
    for start, stop in runs:
        last = NONE
        for i in range(start, stop):
            team = 0 if labels[i] == "H" else 1 if labels[i] == "A" else NONE
            if team == NONE:
                continue
            if last not in (NONE, team):
                out.append((i, team))
            last = team
    return out


# -- the report --------------------------------------------------------------------------------


def _dec(value: float, digits: int = 2) -> str:
    return "—" if value is None or np.isnan(value) else f"{value:+.{digits}f}".replace(".", ",")


def _abs(value: float, digits: int = 2) -> str:
    return "—" if value is None or np.isnan(value) else f"{value:.{digits}f}".replace(".", ",")


def _pct(value: float) -> str:
    return "—" if np.isnan(value) else f"{100 * value:.1f}%".replace(".", ",")


def dating_row(name: str, d: dict) -> str:
    q = " / ".join(_dec(v) for v in d["q"])
    return (
        f"| {name} | {d['truth']} | {d['pred']} | {d['matched']} | {d['missed']} | {d['extra']} "
        f"| {_dec(d['median'])} | {_abs(d['median_abs'])} | {_abs(d['mean_abs'])} | {q} "
        f"| {_pct(d['within_05'])} | {_pct(d['within_1'])} | {_pct(d['late_1'])} |"
    )


DATING_HEAD = [
    "| tramo | cambios verdad | cambios cadena | emparejados | perdidos | sobrantes "
    "| mediana s | mediana \\|·\\| s | media \\|·\\| s | p10 / p25 / p50 / p75 / p90 s "
    "| ≤ 0,5 s | ≤ 1 s | > 1 s tarde |",
    "|---|---:|---:|---:|---:|---:|---:|---:|---:|---|---:|---:|---:|",
]


def keep_mask(runs: Sequence[tuple[int, int]], n: int, donors: Sequence[np.ndarray]) -> np.ndarray:
    """Per frame, is the ball kept? Donor half `i` over half `i`, repeated if shorter: the
    deletion pattern of `external.keep_mask`, for a game that is not an `external.Match`."""
    keep = np.ones(n, dtype=bool)
    for (start, stop), donor in zip(runs, donors):
        keep[start:stop] = np.resize(np.asarray(donor, dtype=bool), stop - start)
    return keep


def degraded_chain(game, donors: Sequence[np.ndarray]) -> tuple[Chain, float]:
    """The chain on `game` with the ball deleted where BAR-ATH's was not seen, and the ball share
    left. The players' stoppages do not read the ball; the tagged ones see the degraded `out`."""
    from tools import bench, dead_ball_v2, metrica_open

    n = len(game.features.present)
    runs = [tuple(r) for r in game.runs]
    f, ev = bench.degrade(game.features, game.evidence, (0, n), keep_mask(runs, n, donors))
    kinematic = dead_ball_v2.kinematic_mask(game.players_m, metrica_open.PITCH_M, runs, "rule")
    dead = dead_ball_v2.dead_union("rule", ev, kinematic, runs)
    return delivered(f, ev, runs, dead), float(f.present.mean())


def calibrate(donors: Sequence[np.ndarray] | None = None) -> str:
    """STEP 1c: the delivered chain on g1 and g2 against the event truth, state and labels; with
    `donors` (BAR-ATH's ball presence per half), also with our missing ball laid over each game."""
    from tools import metrica_open

    lines = [
        "Calibración: la cadena entregada en Metrica g1 y g2 frente a la verdad de eventos "
        f"(cambios en juego, E5; tolerancia ±{_abs(TOLERANCE_S, 1)} s, mismo equipo nuevo).",
        "",
        "Estado decodificado (antes de escribir `D`):",
        "",
        *DATING_HEAD,
    ]
    label_rows, degraded_rows = [], []
    for name in metrica_open.GAMES:
        game = metrica_open.load(name)
        dead = metrica_dead(game)
        chain = delivered(game.features, game.evidence, game.runs, dead)
        truth = open_play(game)
        pred = state_changes(chain.state, game.runs)
        lines.append(dating_row(name, dating(truth, pred)))
        for h, run in enumerate(game.runs, start=1):
            lines.append(dating_row(f"{name} mitad {h}", dating(truth, pred, run)))
        shown = label_changes(finish(chain.state, chain.dead), game.runs)
        label_rows.append(dating_row(name, dating(truth, shown)))
        if donors is not None:
            worse, ball = degraded_chain(game, donors)
            changes = state_changes(worse.state, game.runs)
            degraded_rows.append(dating_row(f"{name} (balón {_pct(ball)})", dating(truth, changes)))
    lines += ["", "Etiquetas que ve el scorer (`D` encima; diagnóstico):", "", *DATING_HEAD]
    lines += label_rows
    if donors is not None:
        lines += [
            "",
            "Diagnóstico: con el balón visto de BAR-ATH por mitad encima (`external.keep_mask`, "
            "estado decodificado):",
            "",
            *DATING_HEAD,
            *degraded_rows,
        ]
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Lane m-dating: when possession changes")
    parser.add_argument("--calibrate", action="store_true", help="STEP 1c on Metrica g1, g2")
    parser.add_argument(
        "--degraded", action="store_true", help="also with BAR-ATH's missing ball (the bundle)"
    )
    args = parser.parse_args(argv)
    if not args.calibrate:
        parser.error("say --calibrate")
    try:
        donors = None
        if args.degraded:
            from tools import external

            donors = external.our_ball_halves()
        text = calibrate(donors)
    except (OSError, ValueError) as problem:
        print(f"change dating failed: {problem}", file=sys.stderr)
        return 1
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    sys.stdout.write(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
