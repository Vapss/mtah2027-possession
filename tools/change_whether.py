"""Lane m-whether: WHETHER possession changes in open play, judged on Metrica's open games.

    python tools/change_whether.py --anatomy       # STEP 1: what the misses and extras are made of
    python tools/change_whether.py --explore       # section 5: the rules' grids, Metrica g1 only
    python tools/change_whether.py --measure       # section 7: g2, DFL, BAR-ATH, slice, bench

Round 5 (`tools/change_dating.py`, lane-m-dating.md) dated the delivered chain's changes against
the event truth of Metrica's open games (`tools/metrica_open.py`, rules E1-E5) and left a third of
the open-play changes unmatched, "with about as many spurious chain changes". This lane asks the
other question: WHETHER the chain changes, not WHEN. Step 1 is anatomy only, no rule: what the
tracking shows around every change the chain misses and every change it invents, on Metrica g1
(g2 stays held out), with the same counts on BAR-ATH without ground truth and, declared as
contaminated, on the public slice.

The instrument, corrected before any variant exists
---------------------------------------------------
Round 5 matched the truth's OPEN-PLAY changes (E5) against EVERY chain change, restarts included.
A change the chain makes at a set piece (forced by the restart, or by the taker's first control)
has no open-play partner by construction, so it was counted as spurious. Here every truth change
(open play or not) is matched one to one against every chain change, with round 5's rule
(`change_dating.match`: same new team, +/-5 s, closest first):

- **missed** = an open-play truth change with no chain partner;
- **spurious** = a chain change with no truth partner of any kind;
- the dating of matched open-play changes is reported as round 5 did.

Round 5's counts are reported next to these, so the two can be reconciled.

The degraded ball
-----------------
Metrica's sample ball is event-synchronised: when it is slow it sits 0.05 m from a player's foot
(median; BAR-ATH: 1.02 m), while both balls have the same speed distribution (median ~6 m/s). Our
tracking's error is therefore a slowly varying OFFSET of the ball, not frame-to-frame jitter. The
degraded game lays two things over a Metrica game, in this order:

1. **position noise**: per axis, white Gaussian noise smoothed by a Gaussian kernel of
   `NOISE_SMOOTH_S` (1 s: a speed error under 1 m/s), scaled to `NOISE_SIGMA_M` per axis. The sigma
   is FITTED ON g1 ONLY (`fit_sigma`), so that the median distance from a slow ball (<= 2 m/s, in
   the pitch, outside the delivered `D`) to its nearest player equals BAR-ATH's, a statistic that
   needs no label. A fixed seed per game keeps it deterministic.
2. **our ball-presence pattern**: BAR-ATH's ball-seen mask laid half over half
   (`change_dating.keep_mask`, round 5's `--degraded`).

`features_from` recomputes the engine's features from the players and the moved ball; it copies
the nearest-player arithmetic of `metrica_open.build`, which this lane does not edit.
"""

from __future__ import annotations

import argparse
import dataclasses
import sys
from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

import numpy as np

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from tools import change_dating as cd  # noqa: E402
from tools import dead_ball, emision, engine  # noqa: E402

if TYPE_CHECKING:
    from tools import metrica_open

NONE = engine.NONE
FPS = engine.FPS
REACH_M = engine.DEFAULT.radius_m  # the engine's 1.5 m: every "within reach" below is this one
TOLERANCE = int(cd.TOLERANCE_S * FPS)  # round 5's +/-5 s, unchanged
SHORT_S = 2.0  # a "short" truth possession, for the cross-tabs only: under the slice's p10
FLIP_S = 3.0  # a chain A -> B -> A whose B lasts less than this is a flip-flop (anatomy only)
SLOW_MPS = 2.0  # a ball this slow is at someone's feet or rolling: the noise fit's frames
NOISE_SMOOTH_S = 1.0
NOISE_SIGMA_GRID = tuple(round(0.05 * k, 2) for k in range(10, 31))  # 0.50 .. 1.50 m
NOISE_SEED = {"g1": 1, "g2": 2}  # one fixed seed per game: the degraded game is deterministic
# Fitted on g1 by `fit_sigma` against BAR-ATH's label-free target (lane-m-whether.md, section 4);
# a test reproduces the fit. g2's degraded game uses it unchanged.
NOISE_SIGMA_M = 0.85


# -- the corrected instrument ------------------------------------------------------------------


@dataclass(frozen=True)
class Truth:
    """The event truth's changes on one game: all of them, and which are open play (E5)."""

    changes: tuple[tuple[int, int], ...]  # (frame, new team), every change
    open_frames: frozenset[int]  # the frames of the open-play ones
    team: np.ndarray
    dead: np.ndarray


def metrica_truth(game: metrica_open.Game) -> Truth:
    t = game.truth
    return Truth(
        tuple((c.frame, c.new) for c in t.changes),
        frozenset(c.frame for c in t.changes if c.open_play),
        t.team,
        t.dead,
    )


@dataclass(frozen=True)
class Fair:
    """One chain against one truth: counts, the pairs, and the dating of open-play pairs."""

    chain: int
    matched: int
    missed: tuple[tuple[int, int], ...]  # open-play truth changes without a partner
    spurious: tuple[tuple[int, int], ...]  # chain changes without a partner of any kind
    pairs: tuple[tuple[int, int], ...]
    lag: dict


def fair(truth: Truth, pred: Sequence[tuple[int, int]]) -> Fair:
    """Every truth change against every chain change, one to one (`change_dating.match`)."""
    pairs = cd.match(list(truth.changes), list(pred))
    # One pair credits ONE truth change: two changes on the same frame need two partners
    # (review of PR #60). Counted by multiplicity, in the truth's order.
    left = Counter(a for a, _ in pairs)
    missed_list = []
    for c in truth.changes:
        if left[c[0]]:
            left[c[0]] -= 1
        elif c[0] in truth.open_frames:
            missed_list.append(c)
    missed = tuple(missed_list)
    used_p = Counter(b for _, b in pairs)
    spurious_list = []
    for c in pred:
        if used_p[c[0]]:
            used_p[c[0]] -= 1
        else:
            spurious_list.append(c)
    spurious = tuple(spurious_list)
    lags = [(b - a) / FPS for a, b in pairs if a in truth.open_frames]
    return Fair(len(pred), len(pairs), missed, spurious, tuple(pairs), cd.lag_stats(lags))


# -- anatomy -----------------------------------------------------------------------------------

MISS_KINDS = (
    "ya del nuevo equipo",
    "aceptado sin pareja",
    "veto del duelo",
    "toque rápido",
    "rival igual de cerca",
    "sin balón",
    "lejos",
)
EXTRA_KINDS = (
    "reanudación forzada",
    "balón muerto en la verdad",
    "corrección tardía",
    "ida y vuelta",
    "control del rival",
)


def _half(runs: Sequence[tuple[int, int]], frame: int) -> tuple[int, int]:
    return next((a, b) for a, b in runs if a <= frame < b)


def spell_end(truth: Truth, frame: int, team: int, runs: Sequence[tuple[int, int]]) -> int:
    """The first frame after `frame` where the truth leaves `team` (another team, dead ball or
    nobody), or the half's end: where the new team's truth possession ends."""
    _start, stop = _half(runs, frame)
    other = (truth.team[frame:stop] != team) | truth.dead[frame:stop]
    # `frame` itself can already be another team's when two events share it: look after it.
    later = np.flatnonzero(other[1:])
    return frame + 1 + int(later[0]) if later.size else stop


def touch(f: engine.Features) -> np.ndarray:
    """The team whose nearest player is within reach of a ball in the pitch and strictly nearer,
    at ANY speed: round 5's definition, `change_dating._touch`, so both rounds use one."""
    return cd._touch(f)


def miss_kind(chain: cd.Chain, f: engine.Features, frame: int, new: int, end: int) -> str:
    """Why the chain has no partner for the open-play truth change `(frame, new)`, looked for in
    the frames `[frame, min(end, frame + 5 s)]` where its partner would have had to be. The first
    kind that applies wins, in `MISS_KINDS` order."""
    if int(chain.state[frame]) == new:
        return MISS_KINDS[0]  # the chain never saw the old team's spell before it
    w = np.arange(frame, max(frame + 1, min(end, frame + TOLERANCE + 1)))
    mine = chain.ctrl[w] == new
    if (mine & (chain.switch[w] == new)).any():
        return MISS_KINDS[1]
    if mine.any():
        return MISS_KINDS[2]  # controls of the new team, every one with a rival within reach
    near_new = (f.home_m if new == 0 else f.away_m)[w]
    near_old = (f.away_m if new == 0 else f.home_m)[w]
    reach = f.in_pitch[w] & (near_new <= REACH_M)
    if (reach & (near_new < near_old)).any():
        return MISS_KINDS[3]  # the new team was the nearest within reach, the ball too fast
    if reach.any():
        return MISS_KINDS[4]
    if f.present[w].mean() < 0.5:
        return MISS_KINDS[5]
    return MISS_KINDS[6]


def extra_kind(chain: cd.Chain, truth: Truth, frame: int, new: int, back: int | None) -> str:
    """Why the chain change `(frame, new)` has no truth partner. `back` is the frame where the
    chain next returns to the old team inside the half, if it does."""
    if frame in chain.forced:
        return EXTRA_KINDS[0]
    if truth.dead[frame] or truth.team[frame] == NONE:
        return EXTRA_KINDS[1]
    if truth.team[frame] == new:
        return EXTRA_KINDS[2]  # the truth already had the new team: the chain was late or wrong
    if back is not None and back - frame < FLIP_S * FPS:
        return EXTRA_KINDS[3]
    return EXTRA_KINDS[4]


def _returns(pred: Sequence[tuple[int, int]], runs, state: np.ndarray) -> dict[int, int | None]:
    """For each chain change, the frame of the next change of the same half if that one goes
    back to the team before it (A -> B -> A), else None."""
    out: dict[int, int | None] = {}
    for i, (frame, _new) in enumerate(pred):
        nxt = pred[i + 1] if i + 1 < len(pred) else None
        same_half = nxt is not None and _half(runs, nxt[0]) == _half(runs, frame)
        out[frame] = nxt[0] if same_half and nxt[1] == int(state[frame - 1]) else None
    return out


def stretches(mask: np.ndarray, runs: Sequence[tuple[int, int]]) -> list[tuple[int, int]]:
    """Maximal `[start, stop)` runs of `mask` inside each run."""
    out = []
    for start, stop in runs:
        edges = np.diff(np.concatenate(([0], mask[start:stop].astype(np.int8), [0])))
        out += [
            (start + int(a), start + int(b))
            for a, b in zip(np.flatnonzero(edges == 1), np.flatnonzero(edges == -1))
        ]
    return out


def rival_of(state: np.ndarray) -> np.ndarray:
    return np.where(state == 0, 1, np.where(state == 1, 0, NONE)).astype(np.int8)


def vetoed(chain: cd.Chain) -> np.ndarray:
    """Frames where the rival of the team in possession controls the ball (`engine.control`) and
    the duel rule vetoes it: the team in possession has someone within reach."""
    rival = rival_of(chain.state)
    return (rival != NONE) & (chain.ctrl == rival) & (chain.switch == NONE)


def fast_touches(chain: cd.Chain, f: engine.Features) -> np.ndarray:
    """Frames where the rival of the team in possession is the nearest within reach of a ball in
    the pitch, the team in possession beyond reach, and the ball too fast (or of unknown speed)
    for a control: the one-touch interceptions and deflections the chain cannot see."""
    rival = rival_of(chain.state)
    t = touch(f)
    owner = np.where(chain.state == 0, f.home_m, f.away_m)
    clear = np.nan_to_num(owner, nan=-np.inf) > REACH_M
    slow = np.nan_to_num(f.speed_mps, nan=np.inf) <= engine.DEFAULT.speed_mps
    return (rival != NONE) & (t == rival) & clear & ~slow


def flip_flops(
    pred: Sequence[tuple[int, int]],
    runs: Sequence[tuple[int, int]],
    forced: dict[int, int],
    state: np.ndarray,
) -> list[int]:
    """Natural chain changes A -> B that go back to A within `FLIP_S`."""
    back = _returns(pred, runs, state)
    return [
        frame
        for frame, _new in pred
        if frame not in forced and back[frame] is not None and back[frame] - frame < FLIP_S * FPS
    ]


def _minutes(runs: Sequence[tuple[int, int]]) -> float:
    return sum(b - a for a, b in runs) / FPS / 60


def _q(values: Sequence[float]) -> list[float]:
    v = np.asarray(values, dtype=float)
    return [float(x) for x in np.quantile(v, [0.25, 0.5, 0.75, 0.9])] if v.size else [np.nan] * 4


def structure(
    chain: cd.Chain,
    f: engine.Features,
    runs: Sequence[tuple[int, int]],
    owner: np.ndarray | None = None,
) -> dict:
    """The no-ground-truth anatomy of one chain: changes, duel vetoes, fast rival touches and
    flip-flops, per minute and in seconds. With `owner` (the team an independent source says has
    the ball, `NONE` where it says nothing), the share of each kind of stretch it agrees with."""
    pred = cd.state_changes(chain.state, runs)
    minutes = _minutes(runs)
    veto = stretches(vetoed(chain), runs)
    fast = stretches(fast_touches(chain, f), runs)
    flips = flip_flops(pred, runs, chain.forced, chain.state)
    rival = rival_of(chain.state)
    out = {
        "minutes": minutes,
        "changes": len(pred),
        "changes_per_min": len(pred) / minutes,
        "forced": sum(1 for c, _ in pred if c in chain.forced),
        # A rival control the duel rule lets through IS a natural change (the state flips on that
        # frame), so vetoes are counted against natural changes, not against control frames.
        "veto_per_natural": len(veto) / max(1, sum(1 for c, _ in pred if c not in chain.forced)),
        "veto": len(veto),
        "veto_per_min": len(veto) / minutes,
        "veto_s": _q([(b - a) / FPS for a, b in veto]),
        "veto_ge": {s: sum(1 for a, b in veto if b - a >= s * FPS) for s in (0.2, 0.4, 1.0)},
        "veto_then_switch": _then_switch(chain, veto, runs),
        "fast": len(fast),
        "fast_per_min": len(fast) / minutes,
        "fast_then_switch": _then_switch(chain, fast, runs),
        "flips": len(flips),
        "flips_per_min": len(flips) / minutes,
    }
    if owner is not None:
        out["veto_owner_rival"] = _agree(owner, rival, veto)
        out["fast_owner_rival"] = _agree(owner, rival, fast)
        live = (chain.state != NONE) & (owner != NONE) & ~chain.dead
        out["owner_state"] = float((owner[live] == chain.state[live]).mean())
    return out


def _then_switch(
    chain: cd.Chain, spans: Sequence[tuple[int, int]], runs: Sequence[tuple[int, int]]
) -> float:
    """The share of stretches after which the chain goes to the rival within 5 s anyway."""
    if not spans:
        return float("nan")
    rival = rival_of(chain.state)
    hit = []
    for a, b in spans:
        # After the stretch, within 5 s, and never past the end of its half (review of PR #60).
        stop = next((hi for lo, hi in runs if lo <= a < hi), len(chain.state))
        hit.append(bool((chain.state[b : min(stop, b + TOLERANCE)] == rival[a]).any()))
    return float(np.mean(hit))


def _agree(owner: np.ndarray, rival: np.ndarray, spans) -> float:
    """Over the frames of `spans` where `owner` says something, the share where it names the
    rival of the team in possession."""
    idx = np.concatenate([np.arange(a, b) for a, b in spans]) if spans else np.array([], int)
    said = idx[owner[idx] != NONE]
    return float((owner[said] == rival[said]).mean()) if said.size else float("nan")


@dataclass(frozen=True)
class Anatomy:
    fair: Fair
    misses: Counter
    extras: Counter
    cross: dict[str, Counter]  # miss kind -> flags
    extra_in_d: Counter
    no_duel: Fair
    no_duel_fixes: Counter  # miss kind -> how many the chain without the duel rule matches
    round5: dict  # change_dating.dating(open play, every chain change)
    round5_extra: Counter


def anatomy(
    truth: Truth,
    chain: cd.Chain,
    f: engine.Features,
    runs: Sequence[tuple[int, int]],
    no_duel: cd.Chain,
) -> Anatomy:
    """Every miss and every spurious chain change of `chain` against `truth`, by kind."""
    pred = cd.state_changes(chain.state, runs)
    result = fair(truth, pred)
    alt = fair(truth, cd.state_changes(no_duel.state, runs))
    fixed = {c for c in truth.changes if c not in alt.missed}
    misses, cross, fixes = Counter(), {k: Counter() for k in MISS_KINDS}, Counter()
    for frame, new in result.missed:
        end = spell_end(truth, frame, new, runs)
        kind = miss_kind(chain, f, frame, new, end)
        misses[kind] += 1
        flags = cross[kind]
        flags["corta"] += int(end - frame < SHORT_S * FPS)
        stop = _half(runs, frame)[1]
        ends_dead = end < stop and (truth.dead[end] or truth.team[end] == NONE)
        flags["acaba en parada"] += int(ends_dead)
        flags["la recupera el anterior"] += int(
            end < stop and not ends_dead and truth.team[end] == 1 - new
        )
        flags["dentro de D predicho"] += int(chain.dead[frame : max(end, frame + 1)].mean() >= 0.5)
        fixes[kind] += int((frame, new) in fixed)
    back = _returns(pred, runs, chain.state)
    extras, in_d = Counter(), Counter()
    for frame, new in result.spurious:
        kind = extra_kind(chain, truth, frame, new, back[frame])
        extras[kind] += 1
        in_d[kind] += int(chain.dead[frame])
    open_changes = [c for c in truth.changes if c[0] in truth.open_frames]
    r5 = cd.dating(open_changes, pred)
    r5_pairs = {b for _, b in cd.match(open_changes, pred)}
    r5_extra = Counter()
    for frame, new in pred:
        if frame in r5_pairs:
            continue
        if frame in chain.forced:
            r5_extra["reanudación forzada"] += 1
        elif any(
            abs(a - frame) <= TOLERANCE and b == new and a not in truth.open_frames
            for a, b in truth.changes
        ):  # only a change that is NOT open play explains it (review of PR #60)
            r5_extra["junto a un cambio verdadero que no es en juego"] += 1
        else:
            r5_extra["sin cambio verdadero a ±5 s"] += 1
    return Anatomy(result, misses, extras, cross, in_d, alt, fixes, r5, r5_extra)


# -- the degraded ball -------------------------------------------------------------------------


def home_slots(game: metrica_open.Game) -> int:
    """How many of `game.players_m`'s slots are the home team's (`metrica_open.Game` keeps the
    players of both teams in one array, home first, without saying where the away team begins)."""
    present = game.features.present
    for k in range(1, game.players_m.shape[1]):
        d = np.linalg.norm(game.players_m[present, :k] - game.ball_m[present, None, :], axis=2)
        d[~np.isfinite(d)] = np.inf
        if np.allclose(d.min(axis=1), game.features.home_m[present]):
            return k
    raise ValueError(f"{game.name}: no split of the players reproduces the home distances")


def features_from(players_m: np.ndarray, home: int, ball_m: np.ndarray) -> engine.Features:
    """The engine's features for a moved ball: `metrica_open.build`'s arithmetic (copied, not
    edited) on a 105 x 68 m pitch."""
    from tools import metrica_open

    present = np.isfinite(ball_m).all(axis=1)
    x, y = ball_m[:, 0] / metrica_open.PITCH_M[0], ball_m[:, 1] / metrica_open.PITCH_M[1]
    inside = present & (x >= 0) & (x <= 1) & (y >= 0) & (y <= 1)

    def nearest(team: np.ndarray) -> np.ndarray:
        d = np.linalg.norm(team - ball_m[:, None, :], axis=2)
        d[~np.isfinite(d)] = np.inf  # an absent player is never the nearest
        out = d.min(axis=1)
        out[~present] = np.nan
        return out

    return engine.Features(
        nearest(players_m[:, :home]),
        nearest(players_m[:, home:]),
        present,
        emision._ball_speed(ball_m, present),
        inside,
    )


def smooth_noise(n: int, sigma: float, smooth: int, seed: int) -> np.ndarray:
    """`(n, 2)` Gaussian noise, smoothed by a Gaussian kernel of `smooth` frames (std) and scaled
    so each axis has std `sigma`. Deterministic for a seed."""
    if smooth < 1:
        raise ValueError(f"smooth must be at least 1 frame, got {smooth}")
    rng = np.random.default_rng(seed)
    half = 4 * smooth
    white = rng.standard_normal((n + 2 * half, 2))
    t = np.arange(-half, half + 1)
    kernel = np.exp(-0.5 * (t / smooth) ** 2)
    kernel /= np.sqrt((kernel**2).sum())  # unit-variance output from unit-variance input
    return sigma * np.stack([np.convolve(white[:, j], kernel, mode="valid") for j in range(2)], 1)


def slow_ball_distance(f: engine.Features, live: np.ndarray) -> float:
    """The median distance from a slow ball in the pitch to its nearest player, on `live` frames:
    the label-free statistic the noise is fitted to."""
    slow = live & f.present & f.in_pitch & (np.nan_to_num(f.speed_mps, nan=np.inf) <= SLOW_MPS)
    return float(np.median(np.fmin(f.home_m, f.away_m)[slow]))


def _live(n: int, runs, dead: np.ndarray) -> np.ndarray:
    inside = np.zeros(n, dtype=bool)
    for a, b in runs:
        inside[a:b] = True
    return inside & ~np.asarray(dead, dtype=bool)


def noisy_features(game: metrica_open.Game, sigma: float, seed: int) -> engine.Features:
    noise = smooth_noise(len(game.ball_m), sigma, int(round(NOISE_SMOOTH_S * FPS)), seed)
    return features_from(game.players_m, home_slots(game), game.ball_m + noise)


def fit_sigma(
    game, target_m: float, grid: Sequence[float] = NOISE_SIGMA_GRID, detector: str | None = None
) -> tuple:
    """The sigma of `grid` whose noisy game puts the median slow-ball distance closest to
    `target_m` (ties: the smaller), and every `(sigma, distance)` tried. `detector` picks the
    players' stoppages that mark the dead frames (default: the delivered one)."""
    live = _live(len(game.ball_m), game.runs, cd.metrica_dead(game, detector))
    tried = [
        (s, slow_ball_distance(noisy_features(game, s, NOISE_SEED[game.name]), live)) for s in grid
    ]
    best = min(tried, key=lambda t: (abs(t[1] - target_m), t[0]))
    return best[0], tried


def degraded(
    game: metrica_open.Game, donors: Sequence[np.ndarray] | None, sigma: float
) -> tuple[engine.Features, dead_ball.Evidence]:
    """`(features, evidence)` of `game` with the noisy ball, then our ball-presence pattern
    (`donors`, BAR-ATH's per half) when given. Players, stillness and restarts are kept; the
    in/out-of-pitch observation follows the moved ball."""
    from tools import bench

    f = noisy_features(game, sigma, NOISE_SEED[game.name]) if sigma > 0 else game.features
    ev = dataclasses.replace(game.evidence, out=f.present & ~f.in_pitch, inside=f.in_pitch)
    if donors is None:
        return f, ev
    n = len(f.present)
    runs = [tuple(r) for r in game.runs]
    return bench.degrade(f, ev, (0, n), cd.keep_mask(runs, n, donors))


def metrica_dead_on(game, ev: dead_ball.Evidence) -> np.ndarray:
    """The delivered `D` on a (possibly degraded) Metrica game: the players' stoppages do not
    read the ball; the tagged ones see this evidence's `out`."""
    from tools import dead_ball_v2, metrica_open

    runs = [tuple(r) for r in game.runs]
    kinematic = dead_ball_v2.kinematic_mask(
        game.players_m, metrica_open.PITCH_M, runs, engine.KINEMATIC
    )
    return dead_ball_v2.dead_union(engine.KINEMATIC, ev, kinematic, runs)


# -- the variants (pre-registered, lane-m-whether.md section 6) --------------------------------
#
# Each one is the delivered chain (control, duel rule, restarts, `D`) with ONE change to whether
# a change happens; the date of the changes it keeps is the chain's. Constants were fixed on
# Metrica g1, clean and degraded (section 5), never on BAR-ATH's labels or on g2.

PERSIST_S = 1.0  # V1: a contested control kept this long is a won duel (g1, section 5)
SETTLE_S = 0.5  # V2: an A -> B -> A whose B lasts less than this is not a possession (g1)
RELAY_S = 3.0  # V3: the confirming touch of the same team must come this soon (g1)
PERSIST_GRID = (0.2, 0.4, 0.6, 0.8, 1.0)
SETTLE_GRID = (0.5, 1.0, 2.0, 3.0)
RELAY_GRID = (0.5, 1.0, 2.0, 3.0)


def sustained(ctrl: np.ndarray, switch: np.ndarray, runs, frames: int) -> np.ndarray:
    """V1: `switch` plus every run of at least `frames` consecutive control frames of one team
    (`engine.control`, contested or not): a duel the rival keeps winning that long has been won.
    The run counts from its first frame, so the change is dated where the control began."""
    if frames < 1:
        raise ValueError(f"frames must be at least 1, got {frames}")
    out = switch.copy()
    for team in (0, 1):
        for start, stop in stretches(ctrl == team, runs):
            if stop - start >= frames:
                out[start:stop] = team
    return out


def relayed(
    ctrl: np.ndarray, switch: np.ndarray, f: engine.Features, runs, frames: int
) -> tuple[np.ndarray, np.ndarray]:
    """V3: a touch (`touch`: the team nearest within reach, at any speed) on which the other team
    is beyond reach becomes a control when the next touch of the half, within `frames` of it, is
    the same team's again: the team touched it twice with nobody else touching it in between.
    It is accepted at its first uncontested frame; `(ctrl, switch)` with those frames added."""
    t = touch(f)
    ctrl, switch = ctrl.copy(), switch.copy()
    for start, stop in runs:
        episodes: list[list[int]] = []  # [first, stop, team] of each maximal one-team touch run
        for i in (np.flatnonzero(t[start:stop] != NONE) + start).tolist():
            if episodes and episodes[-1][2] == t[i] and episodes[-1][1] == i:
                episodes[-1][1] = i + 1
            else:
                episodes.append([i, i + 1, int(t[i])])
        for (a0, b0, team), (a1, _b1, nxt) in zip(episodes, episodes[1:]):
            if nxt != team or a1 - b0 > frames:
                continue
            seg = np.arange(a0, b0)
            other = (f.away_m if team == 0 else f.home_m)[seg]
            clear = seg[np.nan_to_num(other, nan=-np.inf) > REACH_M]
            if clear.size:
                ctrl[clear[0]] = switch[clear[0]] = team
    return ctrl, switch


def settled(
    state: np.ndarray, runs, forced: dict[int, int], dead: np.ndarray, frames: int
) -> np.ndarray:
    """V2: `state` without the natural A -> B -> A whose B lasts less than `frames`, with no
    stoppage inside it and neither change forced by a restart: B goes back to A. Left to right,
    so a removed pair never makes a new one."""
    out = state.copy()
    changes = cd.state_changes(state, runs)
    i = 0
    while i + 1 < len(changes):
        (c, _new), (back, old) = changes[i], changes[i + 1]
        same_half = _half(runs, c) == _half(runs, back)
        if (
            same_half
            and old == int(state[c - 1])
            and back - c < frames
            and c not in forced
            and back not in forced
            and not dead[c:back].any()
        ):
            out[c:back] = old
            i += 2
        else:
            i += 1
    return out


VARIANTS = ("persist", "settle", "relay", "relay+settle")
PRIOR_ORDER = ("persist", "settle", "relay", "relay+settle")  # section 6.4, before measuring
REFERENCE = "engine"


def variant_chain(
    name: str,
    f: engine.Features,
    ev: dead_ball.Evidence,
    runs: Sequence[tuple[int, int]],
    dead: np.ndarray,
    constants: dict[str, float] | None = None,
) -> cd.Chain:
    """The delivered chain on these inputs with the variant's rule (`engine`: none). `constants`
    overrides the pre-registered seconds (`persist`, `settle`, `relay`): the exploration only."""
    runs = [tuple(r) for r in runs]
    if name == REFERENCE:
        return cd.delivered(f, ev, runs, dead)
    parts = name.split("+")
    if not set(parts) <= {"persist", "settle", "relay"} or len(set(parts)) != len(parts):
        raise ValueError(f"unknown variant {name!r}; expected engine or one of {VARIANTS}")
    seconds = {"persist": PERSIST_S, "settle": SETTLE_S, "relay": RELAY_S, **(constants or {})}

    def frames(key: str) -> int:
        return int(round(seconds[key] * FPS))

    ctrl, switch, _forced = engine.inputs(f, engine.DEFAULT, ev.restarts)
    if "persist" in parts:
        switch = sustained(ctrl, switch, runs, frames("persist"))
    if "relay" in parts:
        ctrl, switch = relayed(ctrl, switch, f, runs, frames("relay"))
    # A restart is cancelled only by a control the decoder accepts (DECISIONS 35): the variant's.
    forced = engine.restart_controls(ev.restarts, switch)
    state = engine.decode(ctrl, runs, engine.DEFAULT.dwell, forced, switch)
    dead = np.asarray(dead, dtype=bool)
    if "settle" in parts:
        state = settled(state, runs, forced, dead, frames("settle"))
    return cd.Chain(ctrl, switch, forced, state, dead)


def _bar_ath(name: str):
    def method(f: engine.Features, ev: dead_ball.Evidence) -> np.ndarray:
        chain = variant_chain(name, f, ev, engine.halves(), engine.delivered_dead(ev))
        return cd.finish(chain.state, chain.dead)

    method.__name__ = f"m_whether_{name.replace('+', '_')}"
    return method


# bench-style `(features, evidence) -> labels` on BAR-ATH's halves, the reference first; the
# reference is the delivered file byte for byte (`tests/test_change_whether.py`).
METHODS = {REFERENCE: _bar_ath(REFERENCE), **{name: _bar_ath(name) for name in VARIANTS}}


# -- the report --------------------------------------------------------------------------------


_abs, _dec, _pct = cd._abs, cd._dec, cd._pct


def _share(n: int, total: int) -> str:
    return f"{n} ({_pct(n / total)})" if total else "0"


def fair_head() -> list[str]:
    return [
        "| tramo | cambios verdad (en juego) | cambios cadena | emparejados | perdidos en juego "
        "| sobrantes | perdidos + sobrantes | mediana \\|·\\| s (en juego) |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
    ]


def fair_row(name: str, truth: Truth, r: Fair) -> str:
    return (
        f"| {name} | {len(truth.changes)} ({len(truth.open_frames)}) | {r.chain} | {r.matched} "
        f"| {len(r.missed)} | {len(r.spurious)} | {len(r.missed) + len(r.spurious)} "
        f"| {_abs(r.lag['median_abs'])} |"
    )


def anatomy_tables(a: Anatomy, truth: Truth) -> list[str]:
    n_miss, n_extra = len(a.fair.missed), len(a.fair.spurious)
    lines = [
        "Instrumento corregido (todas las verdades contra todos los cambios de la cadena) y el de "
        "la ronda 5 (solo verdades en juego):",
        "",
        *fair_head(),
        fair_row("cadena entregada", truth, a.fair),
        fair_row("sin la regla del duelo (`engine.D31`)", truth, a.no_duel),
        "",
        f"Ronda 5: {a.round5['matched']} emparejados, {a.round5['missed']} perdidos, "
        f"{a.round5['extra']} sobrantes. Sus sobrantes, por qué: "
        + ", ".join(f"{k} {v}" for k, v in sorted(a.round5_extra.items())),
        "",
        f"Cambios en juego perdidos ({n_miss}), por la primera causa que aplica:",
        "",
        "| causa | n | corta (< 2 s) | acaba en parada | la recupera el anterior "
        "| dentro de D predicho | la empareja la cadena sin duelo |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for kind in MISS_KINDS:
        n = a.misses[kind]
        if not n:
            continue
        c = a.cross[kind]
        lines.append(
            f"| {kind} | {_share(n, n_miss)} | {c['corta']} | {c['acaba en parada']} "
            f"| {c['la recupera el anterior']} | {c['dentro de D predicho']} "
            f"| {a.no_duel_fixes[kind]} |"
        )
    total = Counter()
    for c in a.cross.values():
        total.update(c)
    lines.append(
        f"| total | {n_miss} | {total['corta']} | {total['acaba en parada']} "
        f"| {total['la recupera el anterior']} | {total['dentro de D predicho']} "
        f"| {sum(a.no_duel_fixes.values())} |"
    )
    lines += [
        "",
        f"Cambios sobrantes de la cadena ({n_extra}):",
        "",
        "| causa | n | dentro de D predicho |",
        "|---|---:|---:|",
    ]
    for kind in EXTRA_KINDS:
        if a.extras[kind]:
            lines.append(f"| {kind} | {_share(a.extras[kind], n_extra)} | {a.extra_in_d[kind]} |")
    return lines


STRUCTURE_HEAD = [
    "| partido | min | cambios /min | forzados | vetos por cambio natural "
    "| vetos del duelo /min "
    "| veto p25 / p50 / p75 / p90 s | vetos ≥ 0,2 / 0,4 / 1 s | tras el veto, cambia a ±5 s "
    "| toques rápidos del rival /min | tras el toque, cambia a ±5 s | idas y vueltas < 3 s /min "
    "| juez independiente: dice rival en el veto / en el toque rápido / acuerdo con el estado |",
    "|---|---:|---:|---:|---:|---:|---|---|---:|---:|---:|---:|---|",
]


def structure_row(name: str, s: dict, judge: str) -> str:
    ge = s["veto_ge"]
    agree = (
        f"{judge}: {_pct(s['veto_owner_rival'])} / {_pct(s['fast_owner_rival'])} "
        f"/ {_pct(s['owner_state'])}"
        if "veto_owner_rival" in s
        else "—"
    )
    return (
        f"| {name} | {_abs(s['minutes'], 1)} | {_abs(s['changes_per_min'])} | {s['forced']} "
        f"| {_abs(s['veto_per_natural'])} | {_abs(s['veto_per_min'])} "
        f"| {' / '.join(_abs(v) for v in s['veto_s'])} "
        f"| {ge[0.2]} / {ge[0.4]} / {ge[1.0]} | {_pct(s['veto_then_switch'])} "
        f"| {_abs(s['fast_per_min'])} | {_pct(s['fast_then_switch'])} "
        f"| {_abs(s['flips_per_min'])} | {agree} |"
    )


def _metrica_inputs(game):
    runs = [tuple(r) for r in game.runs]
    dead = cd.metrica_dead(game)
    chain = cd.delivered(game.features, game.evidence, runs, dead)
    no_duel = cd.delivered(game.features, game.evidence, runs, dead, engine.D31)
    return runs, chain, no_duel


def ball_profile(f: engine.Features, live: np.ndarray) -> dict:
    """Label-free aggregates of one ball: what the noise is fitted to and what it must not break."""
    seen = live & f.present & f.in_pitch
    speed = f.speed_mps[seen & np.isfinite(f.speed_mps)]
    ctrl = engine.control(f)
    accepted = engine.uncontested(ctrl, f, REACH_M)
    return {
        "ball": float(f.present[live].mean()),
        "slow_m": slow_ball_distance(f, live),
        "speed": [float(v) for v in np.quantile(speed, [0.25, 0.5, 0.75])],
        "control": float((ctrl[seen] != NONE).mean()),
        "accepted": float((accepted[seen] != NONE).mean()),
    }


def degraded_tables(game, truth: Truth, bar_f: engine.Features, bar_live: np.ndarray) -> list:
    """The noise fit on g1 against BAR-ATH's label-free target, and the delivered chain on g1
    under each degradation: counts and the misses by kind."""
    from tools import external

    target = slow_ball_distance(bar_f, bar_live)
    sigma, tried = fit_sigma(game, target)
    donors = external.our_ball_halves()
    runs = [tuple(r) for r in game.runs]
    live = _live(len(game.ball_m), runs, cd.metrica_dead(game))
    lines = [
        "### El balón degradado: el ruido de posición, fijado en g1",
        "",
        f"Objetivo (BAR-ATH, sin etiquetas): mediana de la distancia de un balón lento (≤ "
        f"{_abs(SLOW_MPS, 0)} m/s, en el campo, fuera del `D` entregado) a su jugador más cercano "
        f"= **{_abs(target)} m**. Rejilla σ {_abs(NOISE_SIGMA_GRID[0])} .. "
        f"{_abs(NOISE_SIGMA_GRID[-1])} m por eje (suavizado {_abs(NOISE_SMOOTH_S, 0)} s); en g1: "
        + ", ".join(f"σ {_abs(s_)} → {_abs(d)} m" for s_, d in tried[::4])
        + f". **Elegido σ = {_abs(sigma)} m.**",
        "",
        "| balón | visto (mitades vivas) | balón lento → jugador, mediana m "
        "| velocidad p25 / p50 / p75 m/s | control | control sin disputa |",
        "|---|---:|---:|---|---:|---:|",
    ]
    rows = [("BAR-ATH", ball_profile(bar_f, bar_live))]
    conditions = {
        "g1 limpio": (None, 0.0),
        "g1 con nuestro balón visto": (donors, 0.0),
        f"g1 con ruido σ {_abs(sigma)}": (None, sigma),
        "g1 con ruido y nuestro balón visto (degradado)": (donors, sigma),
    }
    built = {}
    for name, (d, s_) in conditions.items():
        f, ev = degraded(game, d, s_)
        built[name] = (f, ev)
        rows.append((name, ball_profile(f, live)))
    for name, b in rows:
        lines.append(
            f"| {name} | {_pct(b['ball'])} | {_abs(b['slow_m'])} "
            f"| {' / '.join(_abs(v) for v in b['speed'])} | {_pct(b['control'])} "
            f"| {_pct(b['accepted'])} |"
        )
    lines += [
        "",
        "La cadena entregada en g1 bajo cada balón (instrumento corregido) y sus perdidos por "
        "causa:",
        "",
        *fair_head(),
    ]
    found = {}
    for name, (f, ev) in built.items():
        dead = metrica_dead_on(game, ev)
        chain = cd.delivered(f, ev, runs, dead)
        alt = cd.delivered(f, ev, runs, dead, engine.D31)
        found[name] = anatomy(truth, chain, f, runs, alt)
        lines.append(fair_row(name, truth, found[name].fair))
    lines += [
        "",
        "| causa | " + " | ".join(found) + " |",
        "|---|" + "---:|" * len(found),
    ]
    for kind in MISS_KINDS:
        cells = " | ".join(str(x.misses[kind]) for x in found.values())
        lines.append(f"| {kind} | {cells} |")
    for kind in EXTRA_KINDS:
        cells = " | ".join(str(x.extras[kind]) for x in found.values())
        lines.append(f"| sobrante: {kind} | {cells} |")
    return lines


def public_truth(gt_labels: np.ndarray, runs: Sequence[tuple[int, int]]) -> Truth:
    """The public slice's changes from its ground truth: a team change of the labels (`D` and `X`
    skipped); open play when no `D` lies between the old team's last frame and the new one's
    first. CONTAMINATED: these 17 possessions chose earlier rules."""
    changes, open_frames = [], set()
    team = np.full(len(gt_labels), NONE, dtype=np.int8)
    team[gt_labels == "H"] = 0
    team[gt_labels == "A"] = 1
    dead = gt_labels == "D"
    for start, stop in runs:
        last, last_at = NONE, start
        for i in range(start, stop):
            if team[i] == NONE:
                continue
            if last not in (NONE, int(team[i])):
                changes.append((i, int(team[i])))
                if not dead[last_at:i].any():
                    open_frames.add(i)
            last, last_at = int(team[i]), i
    return Truth(tuple(changes), frozenset(open_frames), team, dead)


def anatomy_report() -> str:
    """STEP 1: Metrica g1 (g2 is not loaded), BAR-ATH without ground truth, the public slice."""
    import pandas as pd

    from tools import bench, metrica_open
    from tools import smart_tagging as st

    game = metrica_open.load("g1")
    runs, chain, no_duel = _metrica_inputs(game)
    truth = metrica_truth(game)
    a = anatomy(truth, chain, game.features, runs, no_duel)
    f, ev, gt, _cut = bench.load()
    bar_runs = engine.halves()
    bar_dead = engine.delivered_dead(ev)
    bar = cd.delivered(f, ev, bar_runs, bar_dead)
    lines = [
        "### Metrica g1 (g2 no se carga)",
        "",
        *anatomy_tables(a, truth),
        "",
        *degraded_tables(game, truth, f, _live(len(f.present), bar_runs, bar_dead)),
        "",
        "### Estructura sin verdad: Metrica g1 frente a BAR-ATH",
        "",
        "Por minuto de las mitades. Un veto es un tramo de frames seguidos en que el rival del "
        "equipo en posesión controla el balón (`engine.control`) y la regla del duelo lo anula; "
        "un toque rápido, uno en que el rival es el más cercano a ≤ 1,5 m de un balón en el campo, "
        "el equipo en posesión está fuera de alcance y el balón va a > 5 m/s. El juez "
        "independiente es la verdad de eventos en g1 y el Smart Tagging en BAR-ATH (un solo "
        "equipo votado).",
        "",
        *STRUCTURE_HEAD,
    ]
    owner_g1 = np.where(truth.dead, NONE, truth.team).astype(np.int8)
    lines.append(
        structure_row("Metrica g1", structure(chain, game.features, runs, owner_g1), "eventos")
    )
    votes = st.possession_votes(st.load())
    single = (votes[:, 0] > 0) ^ (votes[:, 1] > 0)
    owner = np.where(single, np.where(votes[:, 0] > 0, 0, 1), NONE).astype(np.int8)
    lines.append(structure_row("BAR-ATH", structure(bar, f, bar_runs, owner), "Smart Tagging"))
    lines += [
        "",
        "### Slice público (CONTAMINADO: sus 17 posesiones eligieron reglas anteriores)",
        "",
    ]
    labels = pd.read_csv(bench.GROUND_TRUTH).label.astype(str).str.strip().str.upper().to_numpy()
    window = bench.pm.valid_runs(bench.pm.label_codes(list(labels)))
    slice_truth = public_truth(labels, window)
    bar_no_duel = cd.delivered(f, ev, bar_runs, engine.delivered_dead(ev), engine.D31)
    s = anatomy_on(slice_truth, bar, f, window, bar_no_duel)
    lines += anatomy_tables(s, slice_truth)
    return "\n".join(lines) + "\n"


def anatomy_on(
    truth: Truth,
    chain: cd.Chain,
    f: engine.Features,
    runs: Sequence[tuple[int, int]],
    no_duel: cd.Chain,
) -> Anatomy:
    """`anatomy` on a window of chains decoded over longer runs (the public slice): the state
    outside the window is blanked, so only the window's changes count."""
    clipped = dataclasses.replace(chain, state=_only(chain.state, runs))
    clipped_alt = dataclasses.replace(no_duel, state=_only(no_duel.state, runs))
    return anatomy(truth, clipped, f, runs, clipped_alt)


def _only(state: np.ndarray, runs) -> np.ndarray:
    out = np.full(len(state), NONE, dtype=state.dtype)
    for a, b in runs:
        out[a:b] = state[a:b]
    return out


def spell_f1(truth_labels: np.ndarray, labels: np.ndarray) -> float:
    """The official spellF1 of `labels` against a per-frame truth (`H`/`A`/`D`/`X`), graded where
    the truth is not `X`, abstentions filled as the scorer fills them (`bench.spell_f1`)."""
    from tools import bench

    gt = bench.pm.label_codes(list(truth_labels))
    return bench.spell_f1(gt, np.asarray(labels, dtype=object), bench.pm.valid_runs(gt))


@dataclass(frozen=True)
class Scored:
    fair: Fair
    spell_f1: float


def score_metrica(game, truth: Truth, chain: cd.Chain, runs) -> Scored:
    labels = cd.finish(chain.state, chain.dead)
    pred = cd.state_changes(chain.state, runs)
    return Scored(fair(truth, pred), spell_f1(game.truth.labels(), labels))


# The rule that fixes each constant on g1 (section 5, declared before running it): the grid value
# with the fewest missed + spurious changes summed over g1 clean and g1 degraded; on a tie, the one
# that changes the chain least (the longest persistence, the shortest settle and relay windows).
CONSERVATIVE = {"persist": max, "settle": min, "relay": min}
GRIDS = {"persist": PERSIST_GRID, "settle": SETTLE_GRID, "relay": RELAY_GRID}


def choose(errors: dict[float, int], key: str) -> float:
    best = min(errors.values())
    return CONSERVATIVE[key](v for v, e in errors.items() if e == best)


def _g1_conditions(game) -> dict:
    """g1 clean and degraded (noise and our ball-presence pattern), as `(f, ev, dead)`."""
    from tools import external

    runs = [tuple(r) for r in game.runs]
    f, ev = degraded(game, external.our_ball_halves(), NOISE_SIGMA_M)
    return {
        "limpio": (game.features, game.evidence, cd.metrica_dead(game)),
        "degradado": (f, ev, metrica_dead_on(game, ev)),
    }, runs


def explore() -> str:
    """Section 5: every grid value of every rule on Metrica g1, clean and degraded, the precision
    of the evidence each rule adds there, and the constants the declared rule fixes. g2 is not
    loaded."""
    from tools import metrica_open

    game = metrica_open.load("g1")
    truth = metrica_truth(game)
    conditions, runs = _g1_conditions(game)
    owner = np.where(truth.dead, NONE, truth.team).astype(np.int8)
    head = (
        "| regla | constante s | condición | cambios cadena | perdidos | sobrantes "
        "| perdidos + sobrantes | spellF1 (eventos) |"
    )
    lines = [
        "Exploración en Metrica g1, limpio y degradado (g2 no se carga).",
        "",
        head,
        "|---|---:|---|---:|---:|---:|---:|---:|",
    ]

    def row(rule: str, value: str, cond: str, s: Scored) -> str:
        r = s.fair
        return (
            f"| {rule} | {value} | {cond} | {r.chain} | {len(r.missed)} | {len(r.spurious)} "
            f"| {len(r.missed) + len(r.spurious)} | {_abs(s.spell_f1, 4)} |"
        )

    for cond, (f, ev, dead) in conditions.items():
        s = score_metrica(game, truth, variant_chain(REFERENCE, f, ev, runs, dead), runs)
        lines.append(row("`engine`", "—", cond, s))
    chosen = {}
    for key, grid in GRIDS.items():
        errors = {}
        for value in grid:
            total = 0
            for cond, (f, ev, dead) in conditions.items():
                chain = variant_chain(key, f, ev, runs, dead, {key: value})
                s = score_metrica(game, truth, chain, runs)
                total += len(s.fair.missed) + len(s.fair.spurious)
                lines.append(row(f"`{key}`", _abs(value, 1), cond, s))
            errors[value] = total
        chosen[key] = choose(errors, key)
    # V4 combines the two rules chosen alone, with their own constants: no joint tuning.
    for cond, (f, ev, dead) in conditions.items():
        chain = variant_chain("relay+settle", f, ev, runs, dead, chosen)
        value = f"{_abs(chosen['relay'], 1)} + {_abs(chosen['settle'], 1)}"
        lines.append(row("`relay+settle`", value, cond, score_metrica(game, truth, chain, runs)))
    lines += ["", "Precisión de la evidencia que añade cada regla en g1 limpio:", ""]
    lines += [
        "| evidencia | n | la verdad dice el equipo nuevo al final |",
        "|---|---:|---:|",
    ]
    f, ev, dead = conditions["limpio"]
    base = cd.delivered(f, ev, runs, dead)
    rival = rival_of(base.state)
    for value in PERSIST_GRID:
        spans = [(a, b) for a, b in stretches(vetoed(base), runs) if b - a >= round(value * FPS)]
        hit = [owner[b - 1] == rival[a] for a, b in spans]
        lines.append(
            f"| tramo vetado ≥ {_abs(value, 1)} s | {len(spans)} "
            f"| {_pct(float(np.mean(hit))) if hit else '—'} |"
        )
    for value in RELAY_GRID:
        ctrl, switch = relayed(base.ctrl, base.switch, f, runs, int(round(value * FPS)))
        added = np.flatnonzero((switch != base.switch) & (switch == rival))
        # The event is logged at the touch, give or take a frame or two: half a second of slack.
        hit = [bool((owner[i : i + FPS // 2 + 1] == rival[i]).any()) for i in added]
        lines.append(
            f"| toque confirmado del rival a ≤ {_abs(value, 1)} s | {len(added)} "
            f"| {_pct(float(np.mean(hit))) if hit else '—'} |"
        )
    lines += [
        "",
        "Constantes que fija la regla declarada: "
        + ", ".join(f"`{k}` {_abs(v, 1)} s" for k, v in chosen.items())
        + ".",
    ]
    return "\n".join(lines) + "\n"


# -- the measurements, the gates, the choice (section 6) ---------------------------------------

BALLS = ("limpio", "degradado")


def metrica_measure(names: Sequence[str]) -> dict[str, dict[str, dict[str, Scored]]]:
    """`{game: {ball: {variant: Scored}}}` on the held-out g2 and, for information, g1."""
    from tools import external, metrica_open

    donors = external.our_ball_halves()
    out: dict[str, dict[str, dict[str, Scored]]] = {}
    for gname in ("g2", "g1"):
        game = metrica_open.load(gname)
        truth = metrica_truth(game)
        runs = [tuple(r) for r in game.runs]
        f, ev = degraded(game, donors, NOISE_SIGMA_M)
        inputs = {
            "limpio": (game.features, game.evidence, cd.metrica_dead(game)),
            "degradado": (f, ev, metrica_dead_on(game, ev)),
        }
        out[gname] = {
            ball: {
                n: score_metrica(game, truth, variant_chain(n, fb, evb, runs, dead), runs)
                for n in names
            }
            for ball, (fb, evb, dead) in inputs.items()
        }
    return out


def dfl_measure(names: Sequence[str]) -> dict[str, dict[str, dict[str, float]]]:
    """`{ball: {variant: {match: spellF1}}}` on the seven DFL matches against their per-frame
    truth: the delivered chain with the events' set pieces as restarts and the delivered `D`
    (`change_dating.dfl_inputs`); "con nuestro balón" lays our ball-presence pattern over each."""
    from tools import bench, dead_ball_v2, external

    donors = external.our_ball_halves()
    out: dict[str, dict[str, dict[str, float]]] = {
        "limpio": {n: {} for n in names},
        "con nuestro balón": {n: {} for n in names},
    }
    for match_id in external.MATCHES:
        game = cd.dfl_load(match_id)
        f, ev, runs, dead = cd.dfl_inputs(game)
        n_frames = len(f.present)
        f2, ev2 = bench.degrade(f, ev, (0, n_frames), external.keep_mask(game.match, donors))
        kinematic = dead_ball_v2.kinematic_mask(game.players_m, game.pitch, runs, "rule")
        dead2 = dead_ball_v2.dead_union("rule", ev2, kinematic, runs)
        for ball, (fb, evb, db) in {
            "limpio": (f, ev, dead),
            "con nuestro balón": (f2, ev2, dead2),
        }.items():
            for n in names:
                chain = variant_chain(n, fb, evb, runs, db)
                labels = cd.finish(chain.state, chain.dead)
                out[ball][n][match_id] = spell_f1(game.match.truth, labels)
    return out


LOW_BALL_BLOCKS = cd.LOW_BALL_BLOCKS
RATE_BAND = cd.RATE_BAND
MAX_BLOCK_DEAD = cd.MAX_BLOCK_DEAD
ST_DROP = cd.ST_DROP
BLOCK_RATIO = (0.5, 2.0)  # a block's possessions/min halved or doubled against the reference


def bar_ath_measure(names: Sequence[str]) -> dict[str, dict]:
    """BAR-ATH without ground truth (Smart Tagging, the block report), the public slice paired
    against the first name (the reference) and the bench."""
    from tools import bench, compare_submissions
    from tools import blocks as bl
    from tools import smart_tagging as st

    pm = bench.pm
    f, ev, gt, cut = bench.load()
    votes = st.possession_votes(st.load())
    runs = [(start, stop) for _half, start, stop in bl.halves()]
    base_codes, base_labels, base_rates = None, None, None
    out = {}
    for name in names:
        labels = METHODS[name](f, ev)
        chain = variant_chain(name, f, ev, engine.halves(), engine.delivered_dead(ev))
        codes = pm.label_codes(list(labels))
        rows = bl.measure(list(labels), f.present, votes, cut, runs)
        per_block, whole = rows[:-1], rows[-1]
        rates = np.array([r.rate for r in per_block])
        if base_codes is None:
            base_codes, base_labels, base_rates = codes, labels, rates
        result = pm.evaluate(gt, codes)
        paired = compare_submissions.compare_codes(gt, base_codes, codes)
        sign = paired["sign_diagnostic"]
        summary = bench.summary(bench.bench(METHODS[name], f, ev, gt, cut))
        # A block with no possession in the reference cannot be halved or doubled by a ratio:
        # any possession there is an infinite change (review of PR #60), so it fails gate B.
        with np.errstate(divide="ignore", invalid="ignore"):
            ratio = np.where(base_rates > 0, rates / np.where(base_rates > 0, base_rates, 1), 1.0)
        ratio = np.where((base_rates == 0) & (rates > 0), np.inf, ratio)
        out[name] = {
            "spell_f1": result["spell_f1_mean"],
            "macro_f1": result["macro_f1"],
            "delta": paired["delta_mean_spell_f1_b_minus_a"],
            "wins_a": sign["wins_a"],
            "wins_b": sign["wins_b"],
            "jackknife": paired["jackknife"]["mean_delta_range"],
            "bench_mean": summary["mean"],
            "bench_low": summary["low_mean"],
            "bench_min": summary["min"],
            "rate": whole.rate,
            "min_block_rate": float(rates.min()),
            "max_block_rate": float(rates.max()),
            "block_ratio": (float(np.nanmin(ratio)), float(np.nanmax(ratio))),
            "empty_blocks": int((rates == 0).sum()),
            "max_block_dead": max(r.dead for r in per_block),
            "longest": whole.longest,
            "max_block_longest": max(r.longest for r in per_block),
            "st": whole.st_agree,
            "st_low": float(np.mean([per_block[i - 1].st_agree for i in LOW_BALL_BLOCKS])),
            "dead": whole.dead,
            "moved_frames": int((labels != base_labels).sum()),
            "changes": len(cd.state_changes(chain.state, engine.halves())),
        }
    return out


Gate = cd.Gate


def _errors(s: Scored) -> int:
    return len(s.fair.missed) + len(s.fair.spurious)


def gates(metrica: dict, bar: dict, name: str) -> list[Gate]:
    """The pre-registered gates of section 6.3, for `name` against the reference. DFL is
    reported, not gated (DECISIONS 37)."""
    ref = REFERENCE
    out = []
    for ball in BALLS:
        a, b = metrica["g2"][ball][ref], metrica["g2"][ball][name]
        ok = b.spell_f1 > a.spell_f1 and _errors(b) < _errors(a)
        out.append(
            Gate(
                f"Metrica g2 {ball}",
                bool(ok),
                f"spellF1 {_abs(a.spell_f1, 4)} → {_abs(b.spell_f1, 4)}; perdidos + sobrantes "
                f"{_errors(a)} → {_errors(b)}",
            )
        )
    a, b = bar[ref], bar[name]
    lo, hi = b["block_ratio"]
    ok = (
        RATE_BAND[0] <= b["rate"] <= RATE_BAND[1]
        and BLOCK_RATIO[0] < lo
        and hi < BLOCK_RATIO[1]
        and b["st"] >= a["st"] - ST_DROP
        and b["max_block_dead"] <= MAX_BLOCK_DEAD
    )
    out.append(
        Gate(
            "BAR-ATH sin GT",
            bool(ok),
            f"{_abs(a['rate'])} → {_abs(b['rate'])} pos/min; bloque frente a la referencia "
            f"×{_abs(lo)} .. ×{_abs(hi)}; ST {_pct(a['st'])} → {_pct(b['st'])}; %D máx. por "
            f"bloque {_pct(b['max_block_dead'])}",
        )
    )
    ok = b["delta"] >= 0 and b["wins_a"] <= b["wins_b"]
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


def dfl_wins(dfl: dict, ball: str, name: str) -> tuple[int, int, int]:
    """`(wins, ties, losses)` of `name` against the reference over the seven DFL matches."""
    a, b = dfl[ball][REFERENCE], dfl[ball][name]
    diff = [b[m] - a[m] for m in a]
    return (
        sum(d > 1e-12 for d in diff),
        sum(abs(d) <= 1e-12 for d in diff),
        sum(d < -1e-12 for d in diff),
    )


def measure_report() -> str:
    """Every number of section 6.2 in its order, the gates and the choice; pasted unedited."""
    names = (REFERENCE, *VARIANTS)
    metrica = metrica_measure(names)
    dfl = dfl_measure(names)
    bar = bar_ath_measure(names)
    lines = ["### Metrica (g2 reservado; g1, donde se fijaron las constantes, informativo)", ""]
    head = (
        "| variante | balón | cambios cadena | emparejados | perdidos en juego | sobrantes "
        "| perdidos + sobrantes | mediana \\|·\\| s (en juego) | spellF1 (eventos) |"
    )
    for gname in ("g2", "g1"):
        lines += [f"**{gname}**", "", head, "|---|---|---:|---:|---:|---:|---:|---:|---:|"]
        for ball in BALLS:
            for n in names:
                s = metrica[gname][ball][n]
                r = s.fair
                lines.append(
                    f"| `{n}` | {ball} | {r.chain} | {r.matched} | {len(r.missed)} "
                    f"| {len(r.spurious)} | {_errors(s)} | {_abs(r.lag['median_abs'])} "
                    f"| {_abs(s.spell_f1, 4)} |"
                )
        lines.append("")
    lines += ["### DFL (secundario, decisión 37: se reporta, no veta un cambio de número)", ""]
    matches = list(dfl["limpio"][REFERENCE])
    for ball in dfl:
        lines += [
            f"**{ball}**",
            "",
            "| variante | " + " | ".join(matches) + " | media | gana / empata / pierde |",
            "|---|" + "---:|" * (len(matches) + 2),
        ]
        for n in names:
            v = dfl[ball][n]
            w = "—" if n == REFERENCE else "{} / {} / {}".format(*dfl_wins(dfl, ball, n))
            cells = " | ".join(_abs(v[m], 4) for m in matches)
            lines.append(f"| `{n}` | {cells} | {_abs(float(np.mean(list(v.values()))), 4)} | {w} |")
        lines.append("")
    lines += [
        "### BAR-ATH: sin GT (informe por bloques, Smart Tagging), slice público y banco",
        "",
        "| variante | frames movidos | cambios | pos/min | bloque mín–máx | bloque / ref. "
        "| posesión más larga (partido / bloque máx.) | %D máx. bloque | ST partido "
        "| ST bloques 7/9/11/18 | spellF1 | macroF1 | Δ | wins ref–var | jackknife Δ "
        "| banco media | poco balón | peor |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for n in names:
        b = bar[n]
        jack = " .. ".join(_dec(v, 4) for v in b["jackknife"])
        lo, hi = b["block_ratio"]
        lines.append(
            f"| `{n}` | {b['moved_frames']} | {b['changes']} | {_abs(b['rate'])} "
            f"| {_abs(b['min_block_rate'])}–{_abs(b['max_block_rate'])} "
            f"| ×{_abs(lo)} .. ×{_abs(hi)} | {_pct(b['longest'])} / {_pct(b['max_block_longest'])} "
            f"| {_pct(b['max_block_dead'])} | {_pct(b['st'])} | {_pct(b['st_low'])} "
            f"| {_abs(b['spell_f1'], 4)} | {_abs(b['macro_f1'], 4)} | {_dec(b['delta'], 4)} "
            f"| {b['wins_a']}–{b['wins_b']} | {jack} | {_abs(b['bench_mean'], 4)} "
            f"| {_abs(b['bench_low'], 4)} | {_abs(b['bench_min'], 4)} |"
        )
    passed = {n: gates(metrica, bar, n) for n in VARIANTS}
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
    parser = argparse.ArgumentParser(description="Lane m-whether: whether possession changes")
    parser.add_argument("--anatomy", action="store_true", help="STEP 1: g1, BAR-ATH, the slice")
    parser.add_argument("--explore", action="store_true", help="section 5: g1 only, the grids")
    parser.add_argument("--measure", action="store_true", help="section 7: every gate, the choice")
    args = parser.parse_args(argv)
    if not (args.anatomy or args.explore or args.measure):
        parser.error("say --anatomy, --explore or --measure")
    try:
        if args.measure:
            text = measure_report()
        elif args.explore:
            text = explore()
        else:
            text = anatomy_report()
    except (OSError, ValueError) as problem:
        print(f"change whether failed: {problem}", file=sys.stderr)
        return 1
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    sys.stdout.write(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
