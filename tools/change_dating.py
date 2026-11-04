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
  (`dead_ball.dead_mask`, "out") united with the players' stoppages (`metrica_kinematic`: the
  delivered detector, W3 since DECISIONS 45; the lanes of rounds 5-6 measured W1, "rule").
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
import dataclasses
import sys
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

import numpy as np

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from tools import dead_ball, engine  # noqa: E402

if TYPE_CHECKING:
    from tools import metrica_open

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
    runs = [tuple(r) for r in runs]
    ctrl, switch, forced = engine.inputs(f, params, ev.restarts, dead, runs)
    forced = forced or {}
    state = engine.decode(ctrl, runs, params.dwell, forced, switch)
    return Chain(ctrl, switch, forced, state, np.asarray(dead, dtype=bool))


def finish(state: np.ndarray, dead: np.ndarray) -> np.ndarray:
    """`H` / `A` / `X` from the state, then `D` over the stoppages: `engine.chain`'s last step."""
    out = engine.labels(state)
    out[np.asarray(dead, dtype=bool)] = "D"
    return out


# -- the variants (pre-registered, lane-m-dating.md section 6) ---------------------------------
#
# Every variant keeps every decision of the delivered chain (same control, duel rule, forced
# restarts and `D`) and moves only the DATE of each natural change, back into its hand-over: the
# number, order and teams of the changes are the chain's, so the time scale cannot move
# (DECISIONS 37). Constants were fixed on Metrica g1 (section 5), never on BAR-ATH's labels.

REACH_M = engine.DEFAULT.radius_m  # the engine's 1.5 m: no new reach
RELAXED_MPS = 7.5  # V3, fixed on g1 (section 5): the speed limit of the dating control only
LOOKBACK_S = 5.0  # V2, fixed on g1 (section 5): how far back before the change a reception counts


@dataclass(frozen=True)
class Handover:
    """One natural change of the chain: `old` -> `new` at `frame`; its hand-over is
    `(after, frame]`."""

    frame: int
    old: int
    new: int
    after: int


def handovers(
    state: np.ndarray,
    ctrl: np.ndarray,
    runs: Sequence[tuple[int, int]],
    forced: dict[int, int],
    dead: np.ndarray,
) -> list[Handover]:
    """Every natural (not forced) change of `state`, with where its hand-over begins: after the
    last frame of the old team's spell where it controlled the ball (contested or not), was forced
    the ball by a restart, or the ball was dead. A re-dated change never crosses any of them.
    (The definition of lane-dating.md, section 2.)"""
    out: list[Handover] = []
    for start, stop in runs:
        window = state[start:stop]
        flip = (window[1:] != window[:-1]) & (window[1:] != NONE) & (window[:-1] != NONE)
        spell = start
        for c in (np.flatnonzero(flip) + 1 + start).tolist():
            old, new = int(state[c - 1]), int(state[c])
            if c not in forced:
                marks = np.flatnonzero((ctrl[spell:c] == old) | dead[spell:c])
                last = spell + int(marks[-1]) if marks.size else spell
                pushed = [k for k, team in forced.items() if spell <= k < c and team == old]
                out.append(Handover(c, old, new, max([last, *pushed])))
            spell = c
    return out


def first_anchor(h: Handover, evidence: np.ndarray) -> int:
    """The first frame of the hand-over where `evidence` shows the new team, else the change."""
    seen = np.flatnonzero(evidence[h.after + 1 : h.frame + 1] == h.new)
    return h.after + 1 + int(seen[0]) if seen.size else h.frame


def reception_anchor(h: Handover, f: engine.Features, lookback: int) -> int:
    """V2: the frame of the new team's closest approach to the ball in the last `lookback` frames
    of the hand-over, among frames where the ball is in the pitch and the new team's nearest
    player is within `REACH_M` and strictly nearer than the old team's; the earliest on a tie.
    The change itself always qualifies (a control is such a frame), so it is never later. The
    window is the pre-registered `(max(l, c - lookback), c]`: `lookback` frames ending at the
    change, the frame `lookback` before it excluded (review of PR #59)."""
    lo = max(h.after + 1, h.frame - lookback + 1)
    idx = np.arange(lo, h.frame + 1)
    near_new = (f.home_m if h.new == 0 else f.away_m)[idx]
    near_old = (f.away_m if h.new == 0 else f.home_m)[idx]
    ok = f.in_pitch[idx] & (near_new <= REACH_M) & (near_new < near_old)
    if not ok.any():
        return h.frame
    d = np.where(ok, near_new, np.inf)
    return int(idx[np.flatnonzero(d == d.min())[0]])


def redate(state: np.ndarray, changes: Sequence[Handover], anchors: Sequence[int]) -> np.ndarray:
    """`state` with each change moved back to its anchor: frames `[anchor, change)` go to the new
    team. Nothing outside a hand-over changes."""
    out = state.copy()
    for h, a in zip(changes, anchors):
        if not h.after < a <= h.frame:
            raise ValueError(f"anchor {a} outside the hand-over ({h.after}, {h.frame}]")
        out[a : h.frame] = h.new
    return out


VARIANTS = ("first", "reception", "relaxed")
PRIOR_ORDER = ("first", "reception", "relaxed")  # section 6: only among variants that pass
REFERENCE = "engine"


def variant_state(
    name: str,
    f: engine.Features,
    ev: dead_ball.Evidence,
    runs: Sequence[tuple[int, int]],
    dead: np.ndarray,
) -> Chain:
    """The delivered chain on these inputs with the variant's dates (`engine`: none moved)."""
    chain = delivered(f, ev, runs, dead)
    if name == REFERENCE:
        return chain
    changes = handovers(chain.state, chain.ctrl, runs, chain.forced, chain.dead)
    if name == "first":
        anchors = [first_anchor(h, chain.ctrl) for h in changes]
    elif name == "relaxed":
        fast = engine.control(f, dataclasses.replace(engine.DEFAULT, speed_mps=RELAXED_MPS))
        anchors = [first_anchor(h, fast) for h in changes]
    elif name == "reception":
        lookback = int(round(LOOKBACK_S * FPS))
        anchors = [reception_anchor(h, f, lookback) for h in changes]
    else:
        raise ValueError(f"unknown variant {name!r}; expected engine or one of {VARIANTS}")
    return dataclasses.replace(chain, state=redate(chain.state, changes, anchors))


def _bar_ath(name: str):
    def method(f: engine.Features, ev: dead_ball.Evidence) -> np.ndarray:
        chain = variant_state(name, f, ev, engine.halves(), engine.delivered_dead(ev))
        return finish(chain.state, chain.dead)

    method.__name__ = f"m_dating_{name}"
    return method


def _engine(f: engine.Features, ev: dead_ball.Evidence) -> np.ndarray:
    """The reference variant on BAR-ATH: the delivered chain rebuilt from this module's pieces.
    `tests/test_change_dating.py` pins it to the delivered file's SHA-256 (`7a7f70b68d39`)."""
    chain = delivered(f, ev, engine.halves(), engine.delivered_dead(ev))
    return finish(chain.state, chain.dead)


# bench-style `(features, evidence) -> labels` on BAR-ATH's halves, the reference first
METHODS = {REFERENCE: _engine, **{name: _bar_ath(name) for name in VARIANTS}}


_KINEMATIC: dict[tuple[str, int, str], np.ndarray] = {}


def metrica_kinematic(game: metrica_open.Game, detector: str | None = None) -> np.ndarray:
    """The players' stoppages of a Metrica game, once per game and detector: no degradation
    touches the players, so every condition shares them. `detector` defaults to the delivered."""
    from tools import dead_ball_v2, metrica_open

    detector = detector or engine.KINEMATIC
    key = (game.name, len(game.players_m), detector)
    if key not in _KINEMATIC:
        runs = [tuple(r) for r in game.runs]
        mask = dead_ball_v2.kinematic_mask(game.players_m, metrica_open.PITCH_M, runs, detector)
        mask.flags.writeable = False
        _KINEMATIC[key] = mask
    return _KINEMATIC[key]


def metrica_dead_on(
    game: metrica_open.Game, ev: dead_ball.Evidence, detector: str | None = None
) -> np.ndarray:
    """The delivered `D` on a (possibly degraded) Metrica game: the players' stoppages do not
    read the ball; the tagged ones see this evidence's `out`."""
    from tools import dead_ball_v2

    detector = detector or engine.KINEMATIC
    runs = [tuple(r) for r in game.runs]
    return dead_ball_v2.dead_union(detector, ev, metrica_kinematic(game, detector), runs)


def metrica_dead(game: metrica_open.Game, detector: str | None = None) -> np.ndarray:
    """The delivered `D` on a Metrica game: `engine.delivered_dead`'s union with this game's
    players (that function is pinned to BAR-ATH's). `detector` defaults to the delivered one."""
    return metrica_dead_on(game, game.evidence, detector)


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


def open_play(game: metrica_open.Game) -> list[tuple[int, int]]:
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


# -- DFL events: the secondary judge -----------------------------------------------------------
#
# The seven open DFL/IDSSE matches (`tools/external.py`) also ship their raw event log
# (`DFL_03_02_events_raw_*.xml`): every pass, shot, ball action and set piece with its team and the
# wall-clock `EventTime` an operator logged it at. Rules D1-D4, fixed before any engine output on
# DFL (lane-m-dating.md, section 6):
#
# - D1. Asserting events (the team has the ball): `Play`, `ShotAtGoal`, `OtherBallAction`,
#   `BallClaiming`, with the team of that element; a set piece (`KickOff`, `ThrowIn`, `FreeKick`,
#   `GoalKick`, `CornerKick`, `Penalty`) asserts its own team. `TacklingGame`, `Foul`, `Delete`
#   and the rest say nothing about the team.
# - D2. The clock: a frame's time is fixed by the shots' `CalculatedFrame` / `CalculatedTimestamp`
#   (25 Hz from there; every pair of a half gives the same origin). `EventTime` is logged late and
#   unevenly (the shots: +0.7 .. +2.5 s at the median, from -2.5 to +18 s), so each match gets one
#   SHIFT, the one in [-100, +50] frames that brings the acting team's nearest player closest to
#   the ball over all asserting events (median distance). Nothing of the engine enters it.
# - D3. A change is an asserting event of the other team, dated at its shifted frame.
# - D4. Open play: not a set piece, and DFL's own `BallStatus` alive on every frame from the old
#   team's last asserting event to it (the corrected live/dead state, DECISIONS 37's usable part).

DFL_ASSERTING = ("Play", "ShotAtGoal", "OtherBallAction", "BallClaiming")
DFL_SET_PIECES = ("KickOff", "ThrowIn", "FreeKick", "GoalKick", "CornerKick", "Penalty")
DFL_RESTART_KIND = {
    "KickOff": dead_ball.KICK_OFF_GOAL,
    "ThrowIn": "Throw-in",
    "FreeKick": "Free Kick",
    "GoalKick": "Goal Kick",
    "CornerKick": "Corner",
    "Penalty": "Penalty",
}
DFL_SHIFTS = range(-100, 51)


def _attrs(text: str) -> dict[str, str]:
    import re

    return dict(re.findall(r'([\w-]+)="([^"]*)"', text))


def _utc(stamp: str) -> float:
    from datetime import datetime

    return datetime.fromisoformat(stamp).timestamp()


@dataclass(frozen=True)
class DflEvent:
    time: float  # EventTime, seconds since the epoch
    kind: str  # the first element inside <Event>
    team: str  # the team id the event names, "" when it names none
    set_piece: bool


def dfl_events(path: Path) -> tuple[list[DflEvent], list[tuple[int, float]]]:
    """The asserting events of a raw DFL event file (D1), in file order, and every
    `(CalculatedFrame, CalculatedTimestamp)` pair it carries (D2)."""
    import re

    text = Path(path).read_text(encoding="utf-8")
    events, clock = [], []
    for head, body in re.findall(r"<Event ([^>]*)>(.*?)</Event>", text, flags=re.S):
        attrs = _attrs(head)
        if "CalculatedFrame" in attrs and "CalculatedTimestamp" in attrs:
            clock.append((int(attrs["CalculatedFrame"]), _utc(attrs["CalculatedTimestamp"])))
        first = re.search(r"<(\w+)([^>]*)>", body)
        if not first or "EventTime" not in attrs:
            continue
        kind, inner = first.group(1), _attrs(first.group(2))
        if kind not in DFL_ASSERTING and kind not in DFL_SET_PIECES:
            continue
        team = inner.get("Team", "")
        if not team and kind in DFL_SET_PIECES:
            # A kick-off names both teams (TeamLeft / TeamRight); its taker's Play names its own.
            play = re.search(r"<Play ([^>]*)>", body)
            team = _attrs(play.group(1)).get("Team", "") if play else ""
        if not team:
            continue
        events.append(DflEvent(_utc(attrs["EventTime"]), kind, team, kind in DFL_SET_PIECES))
    return events, clock


@dataclass(frozen=True)
class DflGame:
    """One DFL match in this lane's shape: the `external.Match`, its players, the shifted asserting
    events as `(index, team, set piece)`, the shift (D2) and the open-play changes (D3-D4)."""

    match: object  # external.Match
    players_m: np.ndarray
    events: list[tuple[int, int, bool]]
    shift: int
    changes: list[tuple[int, int]]
    restarts: tuple[dead_ball.Restart, ...]
    pitch: tuple[float, float]


def _dfl_players(raw) -> np.ndarray:
    """Both teams' players in corner-origin metres, laid out exactly as `external.build` lays out
    the ball (halves joined by `external.HALF_GAP` empty frames)."""
    from tools import external

    length, width = raw.pitch
    offset = np.array([length / 2, width / 2])
    slots = max(s.home.shape[1] for s in raw.sections), max(s.away.shape[1] for s in raw.sections)

    def pad(a: np.ndarray, n: int) -> np.ndarray:
        return np.concatenate([a, np.full((len(a), n - a.shape[1], 2), np.nan)], axis=1)

    parts = []
    for i, s in enumerate(raw.sections):
        if i:
            parts.append(np.full((external.HALF_GAP, sum(slots), 2), np.nan))
        parts.append(
            np.concatenate([pad(s.home, slots[0]), pad(s.away, slots[1])], axis=1) + offset
        )
    return np.concatenate(parts)


def dfl_shift(f: engine.Features, events: Sequence[tuple[int, int, bool]]) -> int:
    """D2: the shift that brings the acting team's nearest player closest to the ball."""
    at = np.array([i for i, _t, _s in events], dtype=np.int64)
    team = np.array([t for _i, t, _s in events], dtype=np.int64)
    n = len(f.present)
    best, best_d = 0, np.inf
    for k in DFL_SHIFTS:
        j = at + k
        ok = (j >= 0) & (j < n)
        d = np.where(team[ok] == 0, f.home_m[j[ok]], f.away_m[j[ok]])
        d = d[np.isfinite(d)]
        med = float(np.median(d)) if d.size else np.inf
        if med < best_d:
            best, best_d = k, med
    return best


def dfl_load(match_id: str, root: Path | None = None) -> DflGame:
    from tools import external

    root = Path(root) if root is not None else external.data_dir() / "idsse"
    raw = external.raw(match_id, root)
    match = external.build(raw)
    infos = sorted(root.glob(f"DFL_02_01_matchinformation_*_DFL-MAT-{match_id}.xml"))
    if not infos:
        raise FileNotFoundError(f"{root}: no match information file for {match_id}")
    info = infos[0]
    home_id, _guest_id, _ = external.meta(info)
    found = sorted(root.glob(f"DFL_03_02_events_raw_*_DFL-MAT-{match_id}.xml"))
    if len(found) != 1:
        raise FileNotFoundError(f"{root}: expected one raw event file for {match_id}")
    events, clock = dfl_events(found[0])
    # D2: each half's origin, from the calculated frames that fall inside it.
    origins = []
    for s, (start, stop) in zip(raw.sections, match.runs):
        n = stop - start
        own = [t - (frame - s.first) / FPS for frame, t in clock if 0 <= frame - s.first < n]
        if not own:
            raise ValueError(f"{match_id}: no calculated frame in {s.name}")
        origins.append((float(np.median(own)), start, n))
    placed = []
    for e in events:
        for origin, start, n in origins:
            k = int(round((e.time - origin) * FPS))
            if 0 <= k < n:
                placed.append((start + k, 0 if e.team == home_id else 1, e.set_piece, e.kind))
                break
    placed.sort(key=lambda p: p[0])
    shift = dfl_shift(match.features, [(i, t, s) for i, t, s, _k in placed if not s])
    shifted = []
    for i, team, piece, kind in placed:
        j = i + shift
        if any(start <= j < start + n for _o, start, n in origins):
            shifted.append((j, team, piece, kind))
    alive = match.truth != "D"
    changes, restarts = [], []
    for _o, start, n in origins:
        half = [e for e in shifted if start <= e[0] < start + n]
        previous = None
        for j, team, piece, kind in half:
            if piece:
                params = dead_ball.DEFAULT
                lead = params.kick_off_restart_s if kind == "KickOff" else params.restart_s
                restarts.append(
                    dead_ball.Restart(
                        j, max(start, j - int(round(lead * FPS))), DFL_RESTART_KIND[kind], team
                    )
                )
            turned = previous is not None and previous[1] != team and not piece
            if turned and alive[previous[0] : j + 1].all():
                changes.append((j, team))
            previous = (j, team)
    kick_offs = set()
    fixed = []
    for r in sorted(restarts, key=lambda r: (r.frame, r.tag_start)):
        half = max(start for _o, start, _n in origins if start <= r.frame)
        if r.kind == dead_ball.KICK_OFF_GOAL and half not in kick_offs:
            kick_offs.add(half)
            r = dead_ball.Restart(r.frame, r.tag_start, dead_ball.KICK_OFF_START, r.team)
        fixed.append(r)
    return DflGame(
        match,
        _dfl_players(raw),
        [(j, t, p) for j, t, p, _k in shifted],
        shift,
        changes,
        tuple(fixed),
        raw.pitch,
    )


def dfl_inputs(game: DflGame) -> tuple[engine.Features, dead_ball.Evidence, list, np.ndarray]:
    """`(features, evidence with the set pieces as restarts, runs, delivered D)` of a DFL match."""
    from tools import dead_ball_v2

    runs = [tuple(r) for r in game.match.runs]
    ev = dataclasses.replace(game.match.evidence, restarts=game.restarts)
    kinematic = dead_ball_v2.kinematic_mask(game.players_m, game.pitch, runs, "rule")
    return game.match.features, ev, runs, dead_ball_v2.dead_union("rule", ev, kinematic, runs)


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
    """Per frame, is the ball kept? `external.keep_mask` itself (donor half `i` over half `i`,
    repeated if shorter, with its checks), for a game that is not an `external.Match`."""
    from types import SimpleNamespace

    from tools import external

    return external.keep_mask(SimpleNamespace(runs=list(runs), truth=range(n)), donors)


def degraded_chain(game: metrica_open.Game, donors: Sequence[np.ndarray]) -> tuple[Chain, float]:
    """The chain on `game` with the ball deleted where BAR-ATH's was not seen, and the ball share
    left. The players' stoppages do not read the ball; the tagged ones see the degraded `out`."""
    from tools import bench

    n = len(game.features.present)
    runs = [tuple(r) for r in game.runs]
    f, ev = bench.degrade(game.features, game.evidence, (0, n), keep_mask(runs, n, donors))
    return delivered(f, ev, runs, metrica_dead_on(game, ev)), float(f.present.mean())


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


# -- STEP 2: the exploration on g1 (declared), the measurements, the gates --------------------


def _touch(f: engine.Features, uncontested: bool = False) -> np.ndarray:
    """The new team within reach of a ball in the pitch and strictly nearer, at any speed."""
    nearest = np.fmin(f.home_m, f.away_m)
    close = f.in_pitch & (nearest <= REACH_M)
    team = np.full(len(f.present), NONE, dtype=np.int8)
    team[close & (f.home_m < f.away_m)] = 0
    team[close & (f.away_m < f.home_m)] = 1
    return engine.uncontested(team, f, REACH_M) if uncontested else team


def _lag_row(name: str, truth, state: np.ndarray, runs) -> str:
    pairs = match(truth, state_changes(state, runs))
    lag = np.array([(at - frame) / FPS for frame, at in pairs])
    if not lag.size:
        return f"| {name} | 0 | — | — | — | — | — | — |"
    q = " / ".join(_dec(v) for v in np.quantile(lag, [0.1, 0.25, 0.75, 0.9]))
    return (
        f"| {name} | {len(pairs)} | {_dec(float(np.median(lag)))} "
        f"| {_abs(float(np.median(np.abs(lag))))} | {_abs(float(np.mean(np.abs(lag))))} | {q} "
        f"| {_pct(float((lag < -0.5).mean()))} | {_pct(float((lag > 1).mean()))} |"
    )


WHY = ("sin balón", "fuera", "lejos", "rival más cerca", "rápido", "duelo")


def explore() -> str:
    """Section 5: what the late tail is made of on g1, and every anchor looked at there before
    the variants were written. Metrica g1 only: g2 is the held-out game."""
    from tools import metrica_open

    game = metrica_open.load("g1")
    f, runs = game.features, [tuple(r) for r in game.runs]
    chain = delivered(f, game.evidence, runs, metrica_dead(game))
    truth = open_play(game)
    pairs = match(truth, state_changes(chain.state, runs))
    new_of = dict(truth)
    near = {0: f.home_m, 1: f.away_m}
    # Why the chain had no control on the frames of a late change ([truth, chain), lag > 1 s).
    why = dict.fromkeys(WHY, 0)
    rival_at: dict[str, list[bool]] = {"tarde > 1 s": [], "≤ 0,5 s": []}
    for frame, at in pairs:
        new = new_of[frame]
        lag = (at - frame) / FPS
        if lag > 1:
            rival_at["tarde > 1 s"].append(bool(near[1 - new][frame] <= REACH_M))
        elif abs(lag) <= 0.5:
            rival_at["≤ 0,5 s"].append(bool(near[1 - new][frame] <= REACH_M))
        if lag <= 1:
            continue
        for i in range(frame, at):
            mine, other = near[new][i], near[1 - new][i]
            if not f.present[i]:
                why["sin balón"] += 1
            elif not f.in_pitch[i]:
                why["fuera"] += 1
            elif mine > REACH_M:
                why["lejos"] += 1
            elif other <= mine:
                why["rival más cerca"] += 1
            elif not np.nan_to_num(f.speed_mps[i], nan=np.inf) <= engine.DEFAULT.speed_mps:
                why["rápido"] += 1
            else:
                why["duelo"] += 1
    total = max(1, sum(why.values()))
    lines = [
        "Exploración en Metrica g1 (g2 no se mira): la cola tardía de la cadena entregada.",
        "",
        "Frames `[verdad, cadena)` de los cambios emparejados con retraso > 1 s: por qué no hubo "
        "control del nuevo equipo.",
        "",
        "| " + " | ".join(why) + " | frames |",
        "|" + "---:|" * (len(why) + 1),
        "| " + " | ".join(_pct(v / total) for v in why.values()) + f" | {total} |",
        "",
        "| cambios | n | rival a ≤ 1,5 m en el frame verdadero |",
        "|---|---:|---:|",
    ]
    for name, flags in rival_at.items():
        lines.append(f"| {name} | {len(flags)} | {_pct(float(np.mean(flags)))} |")
    lines += [
        "",
        "Anclas probadas (retraso de los emparejados, s; temprano = antes de −0,5 s):",
        "",
        "| ancla | emparejados | mediana | mediana \\|·\\| | media \\|·\\| "
        "| p10 / p25 / p75 / p90 | temprano | > 1 s tarde |",
        "|---|---:|---:|---:|---:|---|---:|---:|",
        _lag_row("cadena entregada", truth, chain.state, runs),
    ]
    by_ctrl = handovers(chain.state, chain.ctrl, runs, chain.forced, chain.dead)
    touch = _touch(f)
    by_touch = handovers(chain.state, touch, runs, chain.forced, chain.dead)
    tried = [
        ("toque, tras el último control del anterior (`touch` de lane-dating)", by_ctrl, touch),
        ("toque, tras el último toque del anterior", by_touch, touch),
        ("toque sin disputa, tras el último toque", by_touch, _touch(f, True)),
        ("toque sin disputa, tras el último control", by_ctrl, _touch(f, True)),
    ]
    for speed in (5.0, 7.5, 10.0, 15.0):
        fast = engine.control(f, dataclasses.replace(engine.DEFAULT, speed_mps=speed))
        tag = _abs(speed, 1)
        tried += [
            (f"control ≤ {tag} m/s, tras el último control", by_ctrl, fast),
            (f"control ≤ {tag} m/s, tras el último toque", by_touch, fast),
            (
                f"control sin disputa ≤ {tag} m/s, tras el último control",
                by_ctrl,
                engine.uncontested(fast, f, REACH_M),
            ),
        ]
    for name, changes, evidence in tried:
        state = redate(chain.state, changes, [first_anchor(h, evidence) for h in changes])
        lines.append(_lag_row(name, truth, state, runs))
    for seconds in (1.0, 2.0, 5.0):
        look = int(round(seconds * FPS))
        state = redate(chain.state, by_ctrl, [reception_anchor(h, f, look) for h in by_ctrl])
        name = f"recepción: aproximación mínima en los últimos {_abs(seconds, 0)} s"
        lines.append(_lag_row(name, truth, state, runs))
    return "\n".join(lines) + "\n"


def dfl_calibrate() -> str:
    """The DFL instrument and the reference only (section 6): shift, sync, changes, dating."""
    from tools import external

    lines = [
        "DFL, eventos crudos: instrumento y cadena entregada (solo la referencia).",
        "",
        "| partido | desplazamiento (frames) | eventos afirmativos | equipo que actúa: mediana m "
        "/ ≤ 1,5 m | cambios en juego | /min | reanudaciones |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    rows, lags = [], []
    for match_id in external.MATCHES:
        game = dfl_load(match_id)
        f, ev, runs, dead = dfl_inputs(game)
        at = [(i, t) for i, t, piece in game.events if not piece]
        d = np.array([(f.home_m if t == 0 else f.away_m)[i] for i, t in at])
        d = d[np.isfinite(d)]
        minutes = sum(b - a for a, b in runs) / FPS / 60
        lines.append(
            f"| {match_id} | {game.shift:+d} | {len(at)} | {_abs(float(np.median(d)))} / "
            f"{_pct(float((d <= REACH_M).mean()))} | {len(game.changes)} "
            f"| {_abs(len(game.changes) / minutes)} | {len(game.restarts)} |"
        )
        pred = state_changes(delivered(f, ev, runs, dead).state, runs)
        rows.append(dating_row(match_id, dating(game.changes, pred)))
        lags += [(b - a) / FPS for a, b in match(game.changes, pred)]
    pooled = lag_stats(lags)
    lines += ["", "Cadena entregada frente a los cambios de los eventos:", "", *DATING_HEAD, *rows]
    q = " / ".join(_dec(v) for v in pooled["q"])
    lines.append(
        f"| todos | | | {pooled['n']} | | | {_dec(pooled['median'])} "
        f"| {_abs(pooled['median_abs'])} | {_abs(pooled['mean_abs'])} | {q} "
        f"| {_pct(pooled['within_05'])} | {_pct(pooled['within_1'])} | {_pct(pooled['late_1'])} |"
    )
    return "\n".join(lines) + "\n"


@dataclass(frozen=True)
class Gate:
    name: str
    passed: bool
    detail: str


def metrica_measure(names: Sequence[str]) -> dict[str, dict[str, dict]]:
    """`{variant: {span: dating}}` on Metrica: g1 (where constants were fixed, for information)
    and the held-out g2, whole and by half."""
    from tools import metrica_open

    out: dict[str, dict[str, dict]] = {n: {} for n in names}
    for gname in metrica_open.GAMES:
        game = metrica_open.load(gname)
        runs = [tuple(r) for r in game.runs]
        dead = metrica_dead(game)
        truth = open_play(game)
        for name in names:
            state = variant_state(name, game.features, game.evidence, runs, dead).state
            pred = state_changes(state, runs)
            out[name][gname] = dating(truth, pred)
            for h, run in enumerate(runs, start=1):
                out[name][f"{gname} mitad {h}"] = dating(truth, pred, run)
    return out


def dfl_measure(names: Sequence[str]) -> dict[str, dict[str, dict]]:
    """`{variant: {match or "todos": dating}}` on the seven DFL matches (D1-D4)."""
    from tools import external

    out: dict[str, dict[str, dict]] = {n: {} for n in names}
    lags: dict[str, list[float]] = {n: [] for n in names}
    totals = {n: {"truth": 0, "pred": 0, "matched": 0} for n in names}
    for match_id in external.MATCHES:
        game = dfl_load(match_id)
        f, ev, runs, dead = dfl_inputs(game)
        for name in names:
            pred = state_changes(variant_state(name, f, ev, runs, dead).state, runs)
            d = dating(game.changes, pred)
            d["shift"] = game.shift
            out[name][match_id] = d
            lags[name] += [(at - frame) / FPS for frame, at in match(game.changes, pred)]
            for key in totals[name]:
                totals[name][key] += d[key]
    for name in names:
        t = totals[name]
        out[name]["todos"] = {
            **t,
            "missed": t["truth"] - t["matched"],
            "extra": t["pred"] - t["matched"],
            **lag_stats(lags[name]),
        }
    return out


LOW_BALL_BLOCKS = (7, 9, 11, 18)  # the four blocks with the least ball (DECISIONS 26)
RATE_BAND = (3.4 - 0.5, 3.4 + 0.5)
MAX_BLOCK_DEAD = 0.70
ST_DROP = 0.01


def bar_ath_measure(names: Sequence[str]) -> dict[str, dict]:
    """Smart Tagging, blocks, the public slice (paired against the first name, the reference)
    and the bench."""
    from tools import bench, compare_submissions
    from tools import blocks as bl
    from tools import smart_tagging as st

    pm = bench.pm
    f, ev, gt, cut = bench.load()
    votes = st.possession_votes(st.load())
    runs = [(start, stop) for _half, start, stop in bl.halves()]
    base_codes, base_labels = None, None
    out = {}
    for name in names:
        labels = METHODS[name](f, ev)
        codes = pm.label_codes(list(labels))
        if base_codes is None:
            base_codes, base_labels = codes, labels
        result = pm.evaluate(gt, codes)
        paired = compare_submissions.compare_codes(gt, base_codes, codes)
        sign = paired["sign_diagnostic"]
        rows = bl.measure(list(labels), f.present, votes, cut, runs)
        per_block, whole = rows[:-1], rows[-1]
        summary = bench.summary(bench.bench(METHODS[name], f, ev, gt, cut))
        out[name] = {
            "spell_f1": result["spell_f1_mean"],
            "macro_f1": result["macro_f1"],
            "delta": paired["delta_mean_spell_f1_b_minus_a"],
            "wins_a": sign["wins_a"],
            "wins_b": sign["wins_b"],
            "jackknife": paired["jackknife"]["mean_delta_range"],
            "n_pred": result["n_pred_spells"],
            "bench_mean": summary["mean"],
            "bench_low": summary["low_mean"],
            "bench_min": summary["min"],
            "rate": whole.rate,
            "min_block_rate": min(r.rate for r in per_block),
            "max_block_rate": max(r.rate for r in per_block),
            "empty_blocks": sum(1 for r in per_block if r.possessions == 0),
            "max_block_dead": max(r.dead for r in per_block),
            "st": whole.st_agree,
            "st_low": float(np.mean([per_block[i - 1].st_agree for i in LOW_BALL_BLOCKS])),
            "dead": whole.dead,
            "moved_frames": int((labels != base_labels).sum()),
        }
    return out


METRICA_HELD_OUT = ("g2", "g2 mitad 1", "g2 mitad 2")


def gates(metrica: dict, dfl: dict, bar: dict, name: str) -> list[Gate]:
    """The pre-registered gates of section 6, for `name` against the reference."""
    ref = REFERENCE
    out = []
    for span in METRICA_HELD_OUT:
        a, b = metrica[ref][span], metrica[name][span]
        ok = b["median_abs"] < a["median_abs"] and abs(b["median"]) < abs(a["median"])
        out.append(
            Gate(
                f"Metrica {span}",
                bool(ok),
                f"mediana \\|·\\| {_abs(a['median_abs'])} → {_abs(b['median_abs'])}; "
                f"mediana {_dec(a['median'])} → {_dec(b['median'])}",
            )
        )
    a, b = dfl[ref]["todos"], dfl[name]["todos"]
    ok = b["median_abs"] <= a["median_abs"] and abs(b["median"]) <= abs(a["median"])
    out.append(
        Gate(
            "DFL eventos (7 partidos)",
            bool(ok),
            f"mediana \\|·\\| {_abs(a['median_abs'])} → {_abs(b['median_abs'])}; "
            f"mediana {_dec(a['median'])} → {_dec(b['median'])}",
        )
    )
    a, b = bar[ref], bar[name]
    ok = (
        b["st"] >= a["st"] - ST_DROP
        and b["max_block_dead"] <= MAX_BLOCK_DEAD
        and RATE_BAND[0] <= b["rate"] <= RATE_BAND[1]
        and b["empty_blocks"] == 0
    )
    out.append(
        Gate(
            "BAR-ATH sin GT",
            bool(ok),
            f"ST {_pct(a['st'])} → {_pct(b['st'])}; %D máx. por bloque "
            f"{_pct(b['max_block_dead'])}; {_abs(b['rate'])} pos/min; "
            f"bloques sin posesión {b['empty_blocks']}",
        )
    )
    ok = b["delta"] >= 0 and b["wins_a"] <= b["wins_b"] and b["wins_a"] == 0
    out.append(
        Gate(
            "slice público (pareado)",
            bool(ok),
            f"Δ {_dec(b['delta'], 4)}; wins ref–var {b['wins_a']}–{b['wins_b']}",
        )
    )
    ok = b["bench_mean"] >= a["bench_mean"] and b["bench_low"] >= a["bench_low"]
    out.append(
        Gate(
            "banco",
            bool(ok),
            f"media {_abs(a['bench_mean'], 4)} → {_abs(b['bench_mean'], 4)}; "
            f"poco balón {_abs(a['bench_low'], 4)} → {_abs(b['bench_low'], 4)}",
        )
    )
    return out


def select(passed: dict[str, list[Gate]]) -> str | None:
    """The first variant of `PRIOR_ORDER` passing every gate; `None` keeps the delivered chain."""
    ok = {name for name, g in passed.items() if all(x.passed for x in g)}
    return next((name for name in PRIOR_ORDER if name in ok), None)


def measure_report() -> str:
    """Every number of section 6, in its order (Metrica, DFL, BAR-ATH, public, bench), the gates
    and the choice. Pasted unedited into section 7."""
    names = (REFERENCE, *VARIANTS)
    metrica = metrica_measure(names)
    dfl = dfl_measure(names)
    bar = bar_ath_measure(names)
    lines = ["### Metrica (g2 reservado; g1, donde se fijaron las constantes, informativo)", ""]
    for span in ("g2", "g2 mitad 1", "g2 mitad 2", "g1"):
        lines += [f"**{span}**", "", *DATING_HEAD]
        lines += [dating_row(f"`{n}`", metrica[n][span]) for n in names]
        lines.append("")
    lines += ["### DFL, eventos (7 partidos)", "", *DATING_HEAD]
    lines += [dating_row(f"`{n}`", dfl[n]["todos"]) for n in names]
    lines += [
        "",
        "Desplazamiento D2 por partido (frames): "
        + ", ".join(f"{m} {dfl[REFERENCE][m]['shift']:+d}" for m in dfl[REFERENCE] if m != "todos"),
        "",
        "Mediana \\|·\\| por partido (s):",
        "",
        "| variante | " + " | ".join(m for m in dfl[REFERENCE] if m != "todos") + " |",
        "|---|" + "---:|" * (len(dfl[REFERENCE]) - 1),
    ]
    for n in names:
        cells = " | ".join(_abs(dfl[n][m]["median_abs"]) for m in dfl[n] if m != "todos")
        lines.append(f"| `{n}` | {cells} |")
    lines += [
        "",
        "### BAR-ATH: sin GT, slice público (pareado con `engine`) y banco",
        "",
        "| variante | frames movidos | ST partido | ST bloques 7/9/11/18 | pos/min "
        "| bloque mín–máx | sin pos. | %D máx. bloque | spellF1 | macroF1 | Δ | wins ref–var "
        "| jackknife Δ "
        "| banco media | poco balón | peor |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for n in names:
        b = bar[n]
        jack = " .. ".join(_dec(v, 4) for v in b["jackknife"])
        lines.append(
            f"| `{n}` | {b['moved_frames']} | {_pct(b['st'])} | {_pct(b['st_low'])} "
            f"| {_abs(b['rate'])} | {_abs(b['min_block_rate'])}–{_abs(b['max_block_rate'])} "
            f"| {b['empty_blocks']} | {_pct(b['max_block_dead'])} | {_abs(b['spell_f1'], 4)} "
            f"| {_abs(b['macro_f1'], 4)} | {_dec(b['delta'], 4)} | {b['wins_a']}–{b['wins_b']} "
            f"| {jack} | {_abs(b['bench_mean'], 4)} | {_abs(b['bench_low'], 4)} "
            f"| {_abs(b['bench_min'], 4)} |"
        )
    passed = {n: gates(metrica, dfl, bar, n) for n in VARIANTS}
    lines += ["", "### Compuertas (frente a `engine`)", ""]
    heads = [g.name for g in passed[VARIANTS[0]]]
    lines += ["| variante | " + " | ".join(heads) + " |", "|---|" + "---|" * len(heads)]
    for n in VARIANTS:
        cells = " | ".join(
            ("pasa" if g.passed else "**falla**") + f" ({g.detail})" for g in passed[n]
        )
        lines.append(f"| `{n}` | {cells} |")
    choice = select(passed)
    lines += [
        "",
        "Elección por la regla (orden previo "
        + " > ".join(f"`{n}`" for n in PRIOR_ORDER)
        + "): "
        + (f"**`{choice}`**." if choice else "**ninguna; se mantiene la cadena entregada**."),
    ]
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Lane m-dating: when possession changes")
    parser.add_argument("--calibrate", action="store_true", help="STEP 1c on Metrica g1, g2")
    parser.add_argument("--explore", action="store_true", help="section 5: g1 only")
    parser.add_argument("--dfl", action="store_true", help="section 6: the DFL instrument")
    parser.add_argument("--measure", action="store_true", help="section 7: every gate, the choice")
    parser.add_argument(
        "--degraded", action="store_true", help="also with BAR-ATH's missing ball (the bundle)"
    )
    args = parser.parse_args(argv)
    if not (args.calibrate or args.explore or args.dfl or args.measure):
        parser.error("say --calibrate, --explore, --dfl or --measure")
    try:
        if args.dfl:
            text = dfl_calibrate()
        elif args.measure:
            text = measure_report()
        elif args.explore:
            text = explore()
        else:
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
