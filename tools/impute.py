"""Lane impute: infer the possession inside ball gaps from the players, for the engine (#6).

    python tools/impute.py --measure runs/impute   # every number in docs/proposals/lane-impute.md

The engine (`tools/engine.py`) carries the team of the last controlled ball between controls. When
the tracker loses the ball and the next control belongs to the other team, the engine dates the
change to that next control: the end of the gap, the latest possible moment. When the team before
and after a gap is the same, a whole possession of the other team inside the gap is invisible.

This module rewrites the engine's decoded state **inside those gaps only**, and leaves every other
frame as the engine had it:

1. **Intervals.** Between two consecutive anchors of a half -- a control frame, or a restart the
   engine forces (DECISIONS 30-32) -- that hold at least one frame without ball. An interval that
   ends in a forced restart is left alone: the restart rule already decides that hand-over.
2. **Evidence**, per frame without ball, from what the tracking still shows: the formation features
   of lane F (`tools/formation.py`), and the distance from each team to the ball *interpolated*
   between where it was last seen and where it is next seen. Offline, the gap's end is observed
   once the ball reappears, so the inference is bidirectional.
3. **A self-supervised model**: logistic regression without intercept on home-minus-away features
   (swapping the teams flips the probability), trained on *synthetic* gaps: the match's own
   ball-missing pattern shifted by five minutes and laid over frames where the ball is seen, with
   the engine's state there as the label. No ground truth, no Smart Tagging.
4. **Placement.** Where the team changes across an interval, put the change at the gap's median
   frame (prior only), or at the single change point the model's evidence prefers; or decode the
   interval with a two-state Viterbi whose switch cost is the physical possession rate, which may
   also insert a possession of the other team inside a gap.

Everything is pre-registered in docs/proposals/lane-impute.md. Only `measure()` reads the ground
truth or the Smart Tagging; a method only sees what `tools/bench.degrade` leaves visible.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

import games  # noqa: E402
from tools import atd, dead_ball, emision, engine, formation  # noqa: E402

FPS = int(games.GAMES[games.GAME]["fps"])
PITCH_M = np.asarray(games.GAMES[games.GAME]["pitch"], dtype=float)
NONE = engine.NONE

# The synthetic gaps for training: the match's own ball-missing pattern, shifted by one block
# (DECISIONS 26) in both directions inside each half. Five minutes is far longer than any
# possession, so the shifted gaps fall on unrelated play.
SELF_SHIFTS = (5 * 60 * FPS, -5 * 60 * FPS)
# Possessions per minute in the public slice (DECISIONS 26): the physical rate of a change, used
# as the prior cost of a switch in the Viterbi decoder.
POSSESSIONS_PER_MINUTE = 3.4
GAP_FEATURES = ("interp_d", "interp_d_near", "before_far", "after_near")


@dataclass(frozen=True)
class Variant:
    """One pre-registered placement rule: `mid`, `change` or `viterbi` (with its tempering)."""

    kind: str
    temper: int = 1  # frames per independent observation, Viterbi only
    free_end: bool = False  # Viterbi: a switch at the next control costs nothing


VARIANTS = {
    "V1": Variant("mid"),
    "V2": Variant("change"),
    "V3": Variant("viterbi", FPS),
    "V4": Variant("viterbi", FPS, free_end=True),
    "V5": Variant("viterbi", 5 * FPS, free_end=True),
}
# Self-bench shifts: the match degraded with its own gap pattern, scored against the engine with
# the ball in view. Different from SELF_SHIFTS, so no method is scored on the gaps it trained on.
SELF_BENCH_SHIFTS = (3750, 11250, -3750, -11250)


@dataclass(frozen=True)
class Interval:
    """Frames strictly between two anchors `p < q` of one half, with the team at each anchor."""

    p: int
    q: int
    before: int
    after: int


def anchor_teams(ctrl: np.ndarray, forced: dict[int, int]) -> np.ndarray:
    """The team each frame anchors the state to: a control, or a forced restart; `NONE` if not."""
    team = np.asarray(ctrl, dtype=np.int8).copy()
    for frame, side in forced.items():
        team[frame] = side
    return team


def intervals(
    ctrl: np.ndarray,
    forced: dict[int, int],
    present: np.ndarray,
    runs: Sequence[tuple[int, int]],
) -> list[Interval]:
    """Intervals between consecutive anchors with a frame without ball, not ending in a restart.

    The frames before a half's first anchor have no state to start from (the engine leaves `X`),
    and the frames after its last anchor have no end; neither is an interval.
    """
    team = anchor_teams(ctrl, forced)
    out: list[Interval] = []
    for start, stop in runs:
        idx = np.flatnonzero(team[start:stop] != NONE) + start
        for p, q in zip(idx[:-1], idx[1:]):
            if q - p < 2 or q in forced or present[p + 1 : q].all():
                continue
            out.append(Interval(int(p), int(q), int(team[p]), int(team[q])))
    return out


def ball_context(
    present: np.ndarray, runs: Sequence[tuple[int, int]]
) -> tuple[np.ndarray, np.ndarray]:
    """Per frame, the last frame with ball at or before it and the next at or after it, in its half.

    `-1` where there is none (outside the runs, or before the first / after the last ball of the
    half). A frame with ball is its own last and next.
    """
    n = len(present)
    last = np.full(n, -1, dtype=np.int64)
    nxt = np.full(n, -1, dtype=np.int64)
    index = np.arange(n)
    for start, stop in runs:
        seen = present[start:stop]
        here = index[start:stop]
        last[start:stop] = np.maximum.accumulate(np.where(seen, here, -1))
        reverse = np.where(seen, here, n)[::-1]
        ahead = np.minimum.accumulate(reverse)[::-1]
        nxt[start:stop] = np.where(ahead == n, -1, ahead)
    return last, nxt


def gap_features(
    players_m: np.ndarray,
    codes: np.ndarray,
    ball_m: np.ndarray,
    present: np.ndarray,
    runs: Sequence[tuple[int, int]],
    frames: np.ndarray,
) -> np.ndarray:
    """`(len(frames), 2)` home-minus-away evidence from the ball's ends around each gap frame.

    The ball is placed on the straight line between where it was last seen and where it is next
    seen, at the fraction of the gap elapsed (one end only if the other does not exist). Feature 0
    is the nearest home player's distance to it minus the nearest away player's, in metres;
    feature 1 is the same divided by `1 + seconds to the nearer end`, so the model can trust it more
    close to a seen ball than in the middle of a long gap. `0` (no evidence) where neither end
    exists or a team has nobody tracked. Only `ball_m` rows where `present` is True are read.
    """
    last, nxt = ball_context(present, runs)
    s, e = last[frames], nxt[frames]
    out = np.zeros((len(frames), 2))
    has_s, has_e = s >= 0, e >= 0
    ok = has_s | has_e
    if not ok.any():
        return out
    t = frames.astype(float)
    span = np.where(has_s & has_e, e - s, 1).astype(float)
    w = np.where(has_s & has_e, (t - s) / span, np.where(has_e, 1.0, 0.0))
    start_xy = ball_m[np.where(has_s, s, np.where(has_e, e, 0))]
    end_xy = ball_m[np.where(has_e, e, np.where(has_s, s, 0))]
    ball = (1 - w)[:, None] * start_xy + w[:, None] * end_xy
    distance = np.linalg.norm(players_m[frames] - ball[:, None, :], axis=2)
    distance[~np.isfinite(distance)] = np.inf
    home = distance[:, codes == 0].min(axis=1)
    away = distance[:, codes != 0].min(axis=1)
    with np.errstate(invalid="ignore"):
        diff = home - away  # inf - inf where a team has nobody tracked: NaN, dropped below
    usable = ok & np.isfinite(diff)
    near_s = np.where(has_s, t - s, np.inf)
    near_e = np.where(has_e, e - t, np.inf)
    near = np.minimum(near_s, near_e) / FPS
    out[usable, 0] = diff[usable]
    out[usable, 1] = diff[usable] / (1.0 + near[usable])
    return out


@dataclass(frozen=True)
class Context:
    """What the tracking shows that a gap does not hide: players, and the ball where seen."""

    players_m: np.ndarray  # (frames, slots, 2), NaN where a slot is absent
    codes: np.ndarray  # team per slot, 0 home
    ball_m: np.ndarray  # (frames, 2); read only where the method's `present` is True
    formation: np.ndarray  # (frames, len(formation.FEATURES)) home minus away, NaN if undefined


_CONTEXT: Context | None = None


def context() -> Context:
    """The match's player context, built once per process: players are never degraded."""
    global _CONTEXT
    if _CONTEXT is None:
        tracking = atd.load("tactical")
        teams = emision.team_slots()
        players_m = tracking.players_array[:, :, :2] * PITCH_M
        ball, _ = tracking.ball()
        _CONTEXT = Context(
            players_m,
            teams.codes,
            ball[:, :2] * PITCH_M,
            formation.features(tracking, teams),
        )
    return _CONTEXT


def endpoint_features(
    team: np.ndarray, runs: Sequence[tuple[int, int]], frames: np.ndarray
) -> np.ndarray:
    """`(len(frames), 2)`: the anchor teams around each frame, weighted by its place between them.

    `team` is the anchor team per frame (`anchor_teams`). With `w` the fraction of the way from the
    previous anchor to the next, feature 0 is the previous anchor's side (`+1` home, `-1` away)
    times `1 - w`, feature 1 the next anchor's side times `w`. It lets the model learn, from the
    synthetic gaps, how early inside a gap the next control's team already has the ball -- a prior
    on the change point that no one has to guess. `0` where an anchor is missing.
    """
    anchored = team != NONE
    last, nxt = ball_context(anchored, runs)
    p, q = last[frames], nxt[frames]
    side = np.where(team == 0, 1.0, np.where(team == 1, -1.0, 0.0))
    both = (p >= 0) & (q >= 0) & (q > p)
    w = np.where(both, (frames - p) / np.where(both, q - p, 1), 0.0)
    before = np.where(p >= 0, side[np.maximum(p, 0)], 0.0)
    after = np.where(q >= 0, side[np.maximum(q, 0)], 0.0)
    return np.stack([before * np.where(both, 1 - w, 1.0), after * np.where(both, w, 0.0)], axis=1)


def design(
    ctx: Context,
    present: np.ndarray,
    team: np.ndarray,
    runs: Sequence[tuple[int, int]],
    frames: np.ndarray,
) -> np.ndarray:
    """The model's rows for `frames`: formation differences, ball-end and anchor-team features."""
    gap = gap_features(ctx.players_m, ctx.codes, ctx.ball_m, present, runs, frames)
    ends = endpoint_features(team, runs, frames)
    return np.concatenate([ctx.formation[frames], gap, ends], axis=1)


def hide(f: engine.Features, keep: np.ndarray) -> engine.Features:
    """`f` with the ball deleted wherever `keep` is False: `tools/bench.degrade`, one definition."""
    from tools import bench

    n = len(f.present)
    empty = dead_ball.Evidence(
        (), np.zeros(n, dtype=bool), np.zeros(n, dtype=bool), np.zeros(n, dtype=bool)
    )
    return bench.degrade(f, empty, (0, n), keep)[0]


def _engine_d31(f: engine.Features, ev: dead_ball.Evidence) -> np.ndarray:
    dead = dead_ball.dead_mask(ev, engine.halves(), "out")
    return engine.chain(f, engine.D31, ev.restarts, dead)[2]


def anchors(f: engine.Features, ev: dead_ball.Evidence) -> tuple[np.ndarray, dict[int, int]]:
    """Control per frame and the restarts the delivered chain forces, as `engine.chain` has them."""
    ctrl = engine.control(f, engine.DEFAULT)
    return ctrl, engine.restart_controls(ev.restarts, ctrl)


def shifted(present: np.ndarray, runs: Sequence[tuple[int, int]], shift: int) -> np.ndarray:
    """`present` with the ball also removed where it was missing `shift` frames away, per half.

    The shift wraps around inside each half, so every frame gets a donor and no gap crosses the
    interval.
    """
    out = present.copy()
    for start, stop in runs:
        out[start:stop] &= np.roll(present[start:stop], -shift)
    return out


def training_rows(
    f: engine.Features,
    state: np.ndarray,
    dead: np.ndarray,
    runs: Sequence[tuple[int, int]],
    shift: int,
) -> tuple[np.ndarray, engine.Features]:
    """Frames a synthetic gap hides, and the features with that gap, for one `shift`.

    A row is a frame where the ball is seen, live (not `dead`), with an engine state, that the
    shifted mask removes. Its label is the engine's state there, decided with the ball in view.
    """
    synthetic = hide(f, shifted(f.present, runs, shift))
    inside = np.zeros(len(state), dtype=bool)
    for start, stop in runs:
        inside[start:stop] = True
    hidden = f.present & ~synthetic.present
    rows = np.flatnonzero(inside & hidden & ~dead & (state != NONE))
    return rows, synthetic


def train(
    ctx: Context,
    f: engine.Features,
    ev: dead_ball.Evidence,
    state: np.ndarray,
    dead: np.ndarray,
    runs: Sequence[tuple[int, int]],
    where: np.ndarray | None = None,
) -> formation.Model:
    """Fit the gap model on the synthetic gaps of every shift; `where` restricts the rows."""
    xs, ys = [], []
    for shift in SELF_SHIFTS:
        rows, synthetic = training_rows(f, state, dead, runs, shift)
        if where is not None:
            rows = rows[where[rows]]
        ctrl, forced = anchors(synthetic, ev)
        team = anchor_teams(ctrl, forced)
        xs.append(design(ctx, synthetic.present, team, runs, rows))
        ys.append((state[rows] == 0).astype(float))
    return formation.fit(np.concatenate(xs), np.concatenate(ys))


def logit(model: formation.Model, x: np.ndarray) -> np.ndarray:
    """Log-odds of home possession per row; `0` where the formation is undefined."""
    p = np.clip(formation.predict(model, x), 1e-6, 1 - 1e-6)
    return np.log(p / (1 - p))


def _sign(team: int) -> float:
    return 1.0 if team == 0 else -1.0


def place_mid(iv: Interval, candidates: np.ndarray) -> int:
    """The change frame at the median of the interval's frames without ball (prior only)."""
    return int(candidates[(len(candidates) - 1) // 2])


def place_change(iv: Interval, candidates: np.ndarray, ell: np.ndarray) -> int:
    """The single change frame that best splits the evidence: `before` up to it, `after` from it.

    `ell` is the home log-odds on each candidate frame. A change at `q` (the engine's own answer)
    is always allowed. Ties go to the median of the tied frames, so with no evidence at all this
    is a median like `place_mid`.
    """
    sb, sa = _sign(iv.before), _sign(iv.after)
    head = np.concatenate(([0.0], np.cumsum(sb * ell)))  # evidence for `before` up to each cut
    tail = np.concatenate((np.cumsum((sa * ell)[::-1])[::-1], [0.0]))  # for `after` from it
    score = head + tail
    best = np.flatnonzero(np.isclose(score, score.max(), rtol=0.0, atol=1e-9))
    cut = int(best[(len(best) - 1) // 2])
    return int(candidates[cut]) if cut < len(candidates) else iv.q


def viterbi(
    iv: Interval,
    candidates: np.ndarray,
    ell: np.ndarray,
    switch_cost: float,
    end_cost: float | None = None,
) -> np.ndarray:
    """Two-state decode over the candidate frames with both ends fixed: team per candidate.

    The state starts as `before` and must be `after` at `q`; each switch costs `switch_cost` nats
    (`end_cost` for one at `q` itself, the engine's own answer) and each candidate adds its
    log-odds for the team it is given. Ties put a switch as late as possible: the engine's own
    answer is the latest one.
    """
    end_cost = switch_cost if end_cost is None else end_cost
    n = len(candidates)
    gain = np.stack([0.5 * ell, -0.5 * ell], axis=1)  # home, away halves of the log-odds
    score = np.full(2, -np.inf)
    score[iv.before] = 0.0
    back = np.zeros((n, 2), dtype=np.int8)
    for i in range(n):
        stay, move = score, score[::-1] - switch_cost
        back[i] = np.where(stay > move, [0, 1], [1, 0])
        score = np.maximum(stay, move) + gain[i]
    # Arriving at q: a final switch onto `after` is allowed at q itself.
    final = score[iv.after] if score[iv.after] > score[1 - iv.after] - end_cost else None
    path = np.zeros(n, dtype=np.int8)
    current = iv.after if final is not None else 1 - iv.after
    for i in range(n - 1, -1, -1):
        path[i] = current
        current = int(back[i, current])
    return path


def rewrite(
    state: np.ndarray,
    ivs: Sequence[Interval],
    present: np.ndarray,
    dead: np.ndarray,
    variant: Variant,
    ell: np.ndarray | None = None,
) -> np.ndarray:
    """The engine's `state` with each interval's carry replaced by the variant's placement.

    Candidates are the interval's frames without ball that are not dead: where the ball is seen
    and nobody controls it, the engine's "no change yet" is observed, and inside a stoppage nobody
    has the ball. `ell` (home log-odds, whole match) is needed by `change` and `viterbi`.
    """
    out = np.asarray(state).copy()
    switch_cost = -np.log(POSSESSIONS_PER_MINUTE / (60 * FPS))
    for iv in ivs:
        inner = np.arange(iv.p + 1, iv.q)
        candidates = inner[~present[inner] & ~dead[inner]]
        if len(candidates) == 0:
            continue
        if variant.kind == "viterbi":
            if ell is None:
                raise ValueError("viterbi needs the model's log-odds")
            end_cost = 0.0 if variant.free_end else switch_cost
            path = viterbi(iv, candidates, ell[candidates] / variant.temper, switch_cost, end_cost)
            team = np.full(len(inner), iv.before, dtype=np.int8)
            # Between candidates the state holds: each inner frame takes the last candidate's team.
            pos = np.searchsorted(candidates, inner, side="right") - 1
            team[pos >= 0] = path[pos[pos >= 0]]
            out[inner] = team
            continue
        if iv.before == iv.after:
            continue
        if variant.kind == "mid":
            cut = place_mid(iv, candidates)
        elif variant.kind == "change":
            if ell is None:
                raise ValueError("change needs the model's log-odds")
            cut = place_change(iv, candidates, ell[candidates])
        else:
            raise ValueError(f"unknown variant kind {variant.kind!r}")
        out[iv.p + 1 : cut] = iv.before
        out[cut : iv.q] = iv.after
    return out


def impute(
    f: engine.Features, ev: dead_ball.Evidence, variant: Variant, ctx: Context | None = None
) -> tuple[np.ndarray, np.ndarray, dict]:
    """The delivered chain with the variant's gap rewrite: `(state, labels, diagnostics)`.

    Everything comes from `f` and `ev` as given -- in the bench, the degraded ones -- and the
    players. The model is fitted here on the synthetic gaps of the frames `f` shows with ball.
    """
    ctx = ctx or context()
    runs = engine.halves()
    dead = dead_ball.dead_mask(ev, runs, "out")
    ctrl, state, _ = engine.chain(f, engine.D31, ev.restarts, dead)
    forced = engine.restart_controls(ev.restarts, ctrl)
    ivs = intervals(ctrl, forced, f.present, runs)
    ell = None
    if variant.kind != "mid":
        model = train(ctx, f, ev, state, dead, runs)
        frames = np.flatnonzero(~f.present)
        ell = np.zeros(len(state))
        team = anchor_teams(ctrl, forced)
        ell[frames] = logit(model, design(ctx, f.present, team, runs, frames))
    new = rewrite(state, ivs, f.present, dead, variant, ell)
    out = engine.labels(new)
    out[dead] = "D"
    info = {"intervals": len(ivs), "frames_changed": int((new != state).sum())}
    return new, out, info


def method(variant: Variant) -> Callable[[engine.Features, dead_ball.Evidence], np.ndarray]:
    """A `tools/bench.py` method for the variant."""

    def run(f: engine.Features, ev: dead_ball.Evidence) -> np.ndarray:
        return impute(f, ev, variant)[1]

    return run


def _labels_csv(labels: np.ndarray, path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame({"frame": np.arange(len(labels)), "label": labels}).to_csv(
        path, index=False, lineterminator="\n"
    )
    return path


def _inside(n: int, runs: Sequence[tuple[int, int]]) -> np.ndarray:
    inside = np.zeros(n, dtype=bool)
    for start, stop in runs:
        inside[start:stop] = True
    return inside


def heldout(ctx: Context, f: engine.Features, ev: dead_ball.Evidence) -> dict:
    """Model accuracy on synthetic gap rows of unseen blocks, against carrying the state."""
    runs = engine.halves()
    dead = dead_ball.dead_mask(ev, runs, "out")
    _, state, _ = engine.chain(f, engine.D31, ev.restarts, dead)
    parity = formation.block_parity(len(state))
    out: dict = {}
    hits = carry_hits = total = carry_total = 0
    for train_on, test_on in ((1, 2), (2, 1)):
        model = train(ctx, f, ev, state, dead, runs, where=parity == train_on)
        for shift in SELF_SHIFTS:
            rows, synthetic = training_rows(f, state, dead, runs, shift)
            rows = rows[parity[rows] == test_on]
            ctrl, forced = anchors(synthetic, ev)
            team = anchor_teams(ctrl, forced)
            ell = logit(model, design(ctx, synthetic.present, team, runs, rows))
            carry = engine.decode(ctrl, runs, 1, forced)[rows]
            truth = state[rows] == 0
            judged = carry != NONE
            name = f"train_{'odd' if train_on == 1 else 'even'}_shift_{shift}"
            out[name] = {
                "rows": int(len(rows)),
                "model": float(np.mean((ell > 0) == truth)),
                "carry": float(np.mean((carry[judged] == 0) == truth[judged])),
            }
            hits += int(np.sum((ell > 0) == truth))
            total += len(rows)
            carry_hits += int(np.sum((carry[judged] == 0) == truth[judged]))
            carry_total += int(judged.sum())
    out["pooled_model"] = hits / total
    out["pooled_carry"] = carry_hits / carry_total
    model = train(ctx, f, ev, state, dead, runs)
    out["weights"] = dict(
        zip(formation.FEATURES + GAP_FEATURES, [round(float(w), 4) for w in model.weights])
    )
    return out


def self_bench(f: engine.Features, ev: dead_ball.Evidence) -> dict:
    """GT-free: the whole match degraded by its own shifted gaps, scored against the engine."""
    sys.path.insert(0, str(REPO_ROOT / "evaluation"))
    import possession_metrics as pm

    from tools import bench

    runs = engine.halves()
    dead = dead_ball.dead_mask(ev, runs, "out")
    _, state, truth = engine.chain(f, engine.D31, ev.restarts, dead)
    pseudo = pm.label_codes(list(truth))
    out: dict = {}
    for shift in SELF_BENCH_SHIFTS:
        f2, ev2 = bench.degrade(f, ev, (0, len(state)), shifted(f.present, runs, shift))
        hidden = f.present & ~f2.present & (state != NONE) & ~dead
        dead2 = dead_ball.dead_mask(ev2, runs, "out")
        _, base, base_labels = engine.chain(f2, engine.D31, ev2.restarts, dead2)
        row: dict = {
            "ball": float(f2.present[_inside(len(state), runs)].mean()),
            "engine": {
                "spell_f1": pm.evaluate(pseudo, pm.label_codes(list(base_labels)))["spell_f1_mean"],
                "hidden_accuracy": float(np.mean(base[hidden] == state[hidden])),
            },
        }
        for name, variant in VARIANTS.items():
            new, labels, _ = impute(f2, ev2, variant)
            row[name] = {
                "spell_f1": pm.evaluate(pseudo, pm.label_codes(list(labels)))["spell_f1_mean"],
                "hidden_accuracy": float(np.mean(new[hidden] == state[hidden])),
            }
        out[str(shift)] = row
    return out


def bench_rows(f: engine.Features, ev: dead_ball.Evidence) -> dict:
    """The gap-transplant bench (`tools/bench.py`) for the engine and every variant.

    Besides `spellF1` per donor, the team accuracy on the live ground-truth frames the donor hid:
    a diagnostic of the imputation itself, not a selection criterion.
    """
    sys.path.insert(0, str(REPO_ROOT / "evaluation"))
    import possession_metrics as pm

    from tools import bench

    _, _, gt, cut = bench.load()
    # The baseline is the engine every variant rewrites (`engine.D31`), not the delivered one.
    methods = {"engine": _engine_d31, **{n: method(v) for n, v in VARIANTS.items()}}
    window = (cut[0].start, cut[0].stop)
    size = window[1] - window[0]
    live = (gt == pm.H) | (gt == pm.A)
    out: dict = {}
    for name, run in methods.items():
        rows = bench.bench(run, f, ev, gt, cut)
        accuracy = []
        for block in cut[1:]:
            if block.stop - block.start < size:
                continue
            donor = f.present[block.start : block.start + size]
            f2, ev2 = bench.degrade(f, ev, window, donor)
            hidden = live & f.present & ~f2.present
            codes = pm.label_codes(list(run(f2, ev2)))
            accuracy.append(float(np.mean(codes[hidden] == gt[hidden])) if hidden.any() else 1.0)
        for row, acc in zip(rows[1:], accuracy):
            row["hidden_accuracy"] = acc
        out[name] = {"rows": rows, "summary": bench.summary(rows)}
    base = [r["spell_f1"] for r in out["engine"]["rows"][1:]]
    for name in VARIANTS:
        values = [r["spell_f1"] for r in out[name]["rows"][1:]]
        low = out[name]["summary"]["low_mean"] - out["engine"]["summary"]["low_mean"]
        out[name]["vs_engine"] = {
            "mean_delta": float(np.mean(values) - np.mean(base)),
            "low_mean_delta": low,
            "donors_better": int(sum(v > b + 1e-12 for v, b in zip(values, base))),
            "donors_worse": int(sum(v < b - 1e-12 for v, b in zip(values, base))),
        }
    return out


def measure(out_dir: Path) -> dict:
    """Every number in the proposal. The only place ground truth and Smart Tagging are read."""
    from tools import blocks as bl
    from tools import compare_submissions as cs
    from tools import smart_tagging as st

    ctx = context()
    f = engine.features(atd.load("tactical"), emision.team_slots())
    ev = dead_ball.load_evidence()
    runs = engine.halves()
    dead = dead_ball.dead_mask(ev, runs, "out")
    _, state, engine_labels = engine.chain(f, engine.D31, ev.restarts, dead)
    result: dict = {"heldout": heldout(ctx, f, ev), "self_bench": self_bench(f, ev)}
    result["bench"] = bench_rows(f, ev)

    # The delivered match, undegraded: the public slice paired against the engine, and the blocks.
    votes = st.possession_votes(st.load())
    cut = bl.blocks(bl.halves())
    engine_csv = _labels_csv(engine_labels, out_dir / "engine.csv")
    gt_path = cs.resolve_ground_truth("public")
    candidates = {"engine": (state, engine_labels, {"intervals": None, "frames_changed": 0})}
    for name, variant in VARIANTS.items():
        candidates[name] = impute(f, ev, variant)
    full: dict = {}
    for name, (_, labels, info) in candidates.items():
        rows = bl.measure(list(labels), f.present, votes, cut, runs)
        entry = {
            **info,
            "rate_match": round(rows[-1].rate, 2),
            "rate_min_block": round(min(r.rate for r in rows[:-1]), 2),
            "rate_max_block": round(max(r.rate for r in rows[:-1]), 2),
            "st_agree_match": round(rows[-1].st_agree, 4),
            "rates": {r.label: round(r.rate, 2) for r in rows},
        }
        if name != "engine":
            compared = cs.compare_files(
                engine_csv, _labels_csv(labels, out_dir / f"{name}.csv"), gt_path
            )
            sign = compared["sign_diagnostic"]  # aggregates only
            entry.update(
                {
                    "public_spell_f1_engine": compared["a"]["mean_spell_f1"],
                    "public_spell_f1": compared["b"]["mean_spell_f1"],
                    "public_delta": compared["delta_mean_spell_f1_b_minus_a"],
                    "n_discordant": sign["n_discordant"],
                    "wins_engine": sign["wins_a"],
                    "wins_variant": sign["wins_b"],
                }
            )
        full[name] = entry
    result["full_match"] = full
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Lane impute: possession inside ball gaps")
    parser.add_argument("--measure", type=Path, help="measure everything, label CSVs go here")
    args = parser.parse_args(argv)
    if args.measure is None:
        parser.error("nothing to do: pass --measure <dir>")
    try:
        result = measure(args.measure)
    except (OSError, ValueError, RuntimeError) as problem:
        print(f"impute failed: {problem}", file=sys.stderr)
        return 1
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
