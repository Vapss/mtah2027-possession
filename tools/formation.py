"""Lane F: evidence from the players' formation inside ball gaps, for the possession engine (#6).

    python tools/formation.py --measure runs/lane-f       # every number in docs/proposals/lane-f.md

The engine (`tools/engine.py`) labels a frame with the team of the last *controlled* ball and
carries that state between controls. The tracker loses the ball on 41% of graded frames, mostly in
gaps of minutes, and there the engine carries blind. This module gives it evidence from the players
alone:

1. **Features** per frame, from player tracking only: per team, how high the block sits, the most
   advanced player, the last outfield line, the spread, the speed towards the opponent goal and the
   players in the opponent half -- all measured along that team's attacking direction, derived per
   half from the data (the sides swap at half time). The model sees home-minus-away differences.
2. **A self-supervised classifier**: logistic regression without intercept, trained on the engine's
   own control frames. Antisymmetric features and no intercept mean swapping the teams flips the
   probability exactly: the model says which shape looks like possession, not who usually has it.
3. **`fill_gaps`**: inside a long ball gap, switch the carried state when the smoothed formation
   probability for the other team stays above a threshold, dated to where that run began.

Everything is pre-registered in docs/proposals/lane-f.md before measuring. The Smart Tagging is
never an input: it is the only signal independent of the tracking we can validate against outside
the public slice, and `measure()` is the only function here that reads it (or the ground truth).
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

import games  # noqa: E402
from tools import atd, emision, engine  # noqa: E402
from tools.ball_gaps import ball_gaps  # noqa: E402

FPS = int(games.GAMES[games.GAME]["fps"])
PITCH_M = np.asarray(games.GAMES[games.GAME]["pitch"], dtype=float)
HALFWAY_M = float(PITCH_M[0]) / 2
NONE = engine.NONE

FEATURES = ("mean_s", "max_s", "deep_s", "spread_x", "spread_y", "vel_s", "opp_half")
MIN_PLAYERS = 7  # fewer tracked players than this and the shape of a team is not a formation
VELOCITY_LAG = FPS  # one second: frame-to-frame differences are mostly tracking jitter
ITERATIONS = 25  # Newton steps; a 7-weight convex problem has converged long before this
RIDGE = 1e-3
SMOOTH_FRAMES = 5 * FPS  # a formation changes over seconds, a single frame is noise
SUSTAIN_FRAMES = 2 * FPS  # the evidence must hold this long before a switch, like engine dwell


@dataclass(frozen=True)
class Variant:
    """One pre-registered gap rule: gaps of `min_gap` frames or more, switch at P >= `threshold`."""

    min_gap: int
    threshold: float


VARIANTS = {
    "V1": Variant(125, 0.80),
    "V2": Variant(125, 0.90),
    "V3": Variant(500, 0.80),
    "V4": Variant(500, 0.90),
}


@dataclass(frozen=True)
class Model:
    """Logistic weights on the home-minus-away features, each divided by its training RMS."""

    weights: np.ndarray
    scale: np.ndarray


def home_direction(
    players_x_m: np.ndarray, codes: np.ndarray, runs: list[tuple[int, int]]
) -> np.ndarray:
    """`+1` where home attacks towards `+x`, `-1` towards `-x`, `0` outside the `runs`.

    Per half, the team whose centroid has the lower median `x` defends the `x = 0` goal. A median
    over a whole half is robust to the minutes one side spends pinned in its own half.
    """
    direction = np.zeros(len(players_x_m), dtype=np.int8)
    home = codes == 0
    for start, stop in runs:
        x = players_x_m[start:stop]
        centroid = [_masked_mean(x[:, side]) for side in (home, ~home)]
        home_median, away_median = (float(np.nanmedian(c)) for c in centroid)
        if not np.isfinite(home_median) or not np.isfinite(away_median):
            raise ValueError(f"no players to orient the half {start, stop}")
        direction[start:stop] = 1 if home_median < away_median else -1
    return direction


def _masked_mean(values: np.ndarray) -> np.ndarray:
    """Row means over finite entries, `NaN` for an empty row, without the empty-slice warning."""
    finite = np.isfinite(values)
    count = finite.sum(axis=1)
    total = np.where(finite, values, 0.0).sum(axis=1)
    out = np.full(len(values), np.nan)
    np.divide(total, count, out=out, where=count > 0)
    return out


def _masked_std(values: np.ndarray) -> np.ndarray:
    mean = _masked_mean(values)
    return np.sqrt(_masked_mean((values - mean[:, None]) ** 2))


def team_features(
    players_m: np.ndarray,
    codes: np.ndarray,
    runs: list[tuple[int, int]],
    direction: np.ndarray | None = None,
) -> np.ndarray:
    """`(frames, 2, len(FEATURES))`: per frame, home then away, `NaN` where there is no formation.

    `players_m` is `(frames, slots, 2)` in metres with `NaN` for an absent slot. A team with fewer
    than `MIN_PLAYERS` present, or any frame outside the `runs`, gets `NaN` in every feature.
    """
    n = len(players_m)
    if direction is None:
        direction = home_direction(players_m[:, :, 0], codes, runs)
    inside = direction != 0
    out = np.full((n, 2, len(FEATURES)), np.nan)
    for side in (0, 1):
        sign = direction.astype(float) * (1.0 if side == 0 else -1.0)
        x = players_m[:, codes == side, 0]
        y = players_m[:, codes == side, 1]
        s = sign[:, None] * (x - HALFWAY_M)  # positive in the opponent half, growing to their goal
        present = np.isfinite(s) & np.isfinite(y)
        s = np.where(present, s, np.nan)
        enough = inside & (present.sum(axis=1) >= MIN_PLAYERS)

        ordered = np.sort(np.where(present, s, np.inf), axis=1)  # absent slots sort last
        velocity = np.full(s.shape, np.nan)
        for start, stop in runs:  # never across the start of a half
            lagged = slice(start + VELOCITY_LAG, stop)
            velocity[lagged] = (s[lagged] - s[start : stop - VELOCITY_LAG]) * FPS / VELOCITY_LAG

        columns = (
            _masked_mean(s),
            np.where(enough, np.max(np.where(present, s, -np.inf), axis=1), np.nan),
            ordered[:, 1],  # the deepest is the goalkeeper; the second deepest is the last line
            _masked_std(np.where(present, x, np.nan)),
            _masked_std(np.where(present, y, np.nan)),
            _masked_mean(velocity),
            (present & (s > 0)).sum(axis=1).astype(float),
        )
        for k, column in enumerate(columns):
            out[:, side, k] = np.where(enough, column, np.nan)
    return out


def differences(per_team: np.ndarray) -> np.ndarray:
    """Home minus away, `(frames, len(FEATURES))`; a frame missing either side is all `NaN`."""
    diff = per_team[:, 0, :] - per_team[:, 1, :]
    diff[~np.isfinite(diff).all(axis=1)] = np.nan
    return diff


def features(tracking: atd.Tracking, teams: emision.TeamSlots) -> np.ndarray:
    """The model's input over the delivered match, from player tracking only."""
    players_m = tracking.players_array[:, :, :2] * PITCH_M
    return differences(team_features(players_m, teams.codes, engine.halves()))


def _sigmoid(z: np.ndarray) -> np.ndarray:
    return 1.0 / (1.0 + np.exp(-np.clip(z, -30.0, 30.0)))


def fit(x: np.ndarray, y: np.ndarray, iterations: int = ITERATIONS, ridge: float = RIDGE) -> Model:
    """Newton-Raphson logistic regression, no intercept, zero start: deterministic without a seed.

    Rows with any `NaN` are dropped. Each column is divided by its RMS, not centred: centring would
    add an offset that breaks the home/away antisymmetry the missing intercept is there to keep.
    """
    keep = np.isfinite(x).all(axis=1)
    x, y = x[keep], np.asarray(y, dtype=float)[keep]
    if len(x) == 0:
        raise ValueError("no training frame has a complete formation")
    scale = np.sqrt(np.mean(x**2, axis=0))
    scale[scale == 0] = 1.0
    z = x / scale
    w = np.zeros(z.shape[1])
    eye = np.eye(z.shape[1])
    for _ in range(iterations):
        p = _sigmoid(z @ w)
        gradient = z.T @ (p - y) / len(z) + ridge * w
        hessian = (z * (p * (1 - p))[:, None]).T @ z / len(z) + ridge * eye
        w = w - np.linalg.solve(hessian, gradient)
    return Model(w, scale)


def predict(model: Model, x: np.ndarray) -> np.ndarray:
    """`P(home in possession)` per frame; `0.5` (no evidence) where the formation is undefined."""
    p = np.full(len(x), 0.5)
    ok = np.isfinite(x).all(axis=1)
    p[ok] = _sigmoid((x[ok] / model.scale) @ model.weights)
    return p


def smooth(p: np.ndarray, runs: list[tuple[int, int]], window: int = SMOOTH_FRAMES) -> np.ndarray:
    """Centred moving mean inside each run, shrinking at the run's edges; untouched outside."""
    out = np.asarray(p, dtype=float).copy()
    half = window // 2
    for start, stop in runs:
        segment = out[start:stop]
        total = np.concatenate(([0.0], np.cumsum(segment)))
        index = np.arange(len(segment))
        lo = np.maximum(0, index - half)
        hi = np.minimum(len(segment), index + half + 1)
        out[start:stop] = (total[hi] - total[lo]) / (hi - lo)
    return out


def fill_gaps(
    state: np.ndarray,
    p_home: np.ndarray,
    present: np.ndarray,
    runs: list[tuple[int, int]],
    *,
    min_gap: int = VARIANTS["V4"].min_gap,
    threshold: float = VARIANTS["V4"].threshold,
    sustain: int = SUSTAIN_FRAMES,
    window: int = SMOOTH_FRAMES,
    ctrl: np.ndarray | None = None,
) -> np.ndarray:
    """The engine's decoded `state` with its carry replaced inside long ball gaps (pre-registered).

    In every ball gap of at least `min_gap` frames that starts with a state, walk the gap: switch
    to the other team when its smoothed formation probability is `>= threshold` for `sustain`
    consecutive frames, dated to the first of them. The state the gap ends with is carried on to
    the next control frame when `ctrl` is given -- the engine has no new evidence before it either,
    and stopping at the gap's edge would leave a possession of a few frames between gap and control.
    Control frames are never changed. Without `ctrl` the change stays inside the gap.
    """
    if not 0.5 < threshold <= 1.0:
        raise ValueError(f"threshold must be in (0.5, 1], got {threshold}")
    if sustain < 1:
        raise ValueError(f"sustain must be at least 1 frame, got {sustain}")
    state = np.asarray(state)
    out = state.copy()
    p = smooth(p_home, runs, window)
    for start, stop in ball_gaps(present, runs):
        if stop - start < min_gap:
            continue
        current = int(out[start])  # an earlier gap's fill may already have carried into this one
        if current == NONE:
            continue  # nothing to carry yet: the engine's own `X` stands
        streak, since = 0, start
        for i in range(start, stop):
            p_other = p[i] if current == 1 else 1.0 - p[i]
            if p_other >= threshold:
                if streak == 0:
                    since = i
                streak += 1
                if streak >= sustain:
                    current = 1 - current
                    out[since : i + 1] = current
                    streak = 0
            else:
                streak = 0
            out[i] = current
        if ctrl is None or current == state[start]:
            continue
        run_stop = next(b for a, b in runs if a <= start < b)
        j = stop
        while j < run_stop and ctrl[j] == NONE:
            out[j] = current
            j += 1
    return out


def control_labels(ctrl: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Training mask and target from the engine's control: `1` where home controls the ball."""
    mask = ctrl != NONE
    return mask, (ctrl == 0).astype(float)


def block_parity(n: int) -> np.ndarray:
    """`1` for frames in odd 5-minute blocks, `2` in even ones, `0` outside the halves."""
    from tools import blocks as bl

    parity = np.zeros(n, dtype=np.int8)
    for b in bl.blocks(bl.halves()):
        parity[b.start : b.stop] = 1 if b.index % 2 else 2
    return parity


def pipeline() -> dict:
    """The model over the delivered match: no ground truth, no Smart Tagging."""
    tracking = atd.load("tactical")
    teams = emision.team_slots()
    runs = engine.halves()
    f = engine.features(tracking, teams)
    ctrl = engine.control(f)
    state = engine.decode(ctrl, runs)
    x = features(tracking, teams)
    mask, target = control_labels(ctrl)
    model = fit(x[mask], target[mask])
    p_home = predict(model, x)
    fills = {
        name: fill_gaps(
            state,
            p_home,
            f.present,
            runs,
            min_gap=v.min_gap,
            threshold=v.threshold,
            ctrl=ctrl,
        )
        for name, v in VARIANTS.items()
    }
    return {
        "runs": runs,
        "present": f.present,
        "ctrl": ctrl,
        "state": state,
        "x": x,
        "model": model,
        "p_home": p_home,
        "fills": fills,
    }


def _accuracy(p: np.ndarray, y: np.ndarray) -> float:
    return float(np.mean((p > 0.5) == (y > 0.5))) if len(y) else float("nan")


def heldout(x: np.ndarray, ctrl: np.ndarray, runs: list[tuple[int, int]]) -> dict:
    """(a) Train on odd blocks' control frames, test on even blocks', and the other way round."""
    mask, target = control_labels(ctrl)
    parity = block_parity(len(ctrl))
    usable = mask & np.isfinite(x).all(axis=1)
    out: dict = {}
    hits = total = 0
    for train, test in ((1, 2), (2, 1)):
        tr, te = usable & (parity == train), usable & (parity == test)
        model = fit(x[tr], target[tr])
        p = predict(model, x)
        ps = smooth(p, runs)
        confident = te & ((ps >= 0.8) | (ps <= 0.2))
        accuracy = _accuracy(p[te], target[te])
        out[f"train_{'odd' if train == 1 else 'even'}"] = {
            "test_frames": int(te.sum()),
            "accuracy": accuracy,
            "accuracy_smoothed": _accuracy(ps[te], target[te]),
            "majority_baseline": float(max(target[te].mean(), 1 - target[te].mean())),
            "confident_share": float(confident.sum() / max(1, te.sum())),
            "confident_accuracy_smoothed": _accuracy(ps[confident], target[confident]),
        }
        hits += int(round(accuracy * te.sum()))
        total += int(te.sum())
    out["pooled_accuracy"] = hits / total
    return out


def _labels_csv(state: np.ndarray, path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame({"frame": np.arange(len(state)), "label": engine.labels(state)}).to_csv(
        path, index=False, lineterminator="\n"
    )
    return path


def measure(out_dir: Path) -> dict:
    """Every number in the proposal. The only place ground truth and Smart Tagging are read."""
    sys.path.insert(0, str(REPO_ROOT / "evaluation"))
    import possession_metrics as pm

    from tools import blocks as bl
    from tools import compare_submissions as cs
    from tools import smart_tagging as st

    m = pipeline()
    runs, present, state = m["runs"], m["present"], m["state"]
    p_home, fills = m["p_home"], m["fills"]
    result: dict = {
        "weights": dict(zip(FEATURES, m["model"].weights.round(4).tolist())),
        "heldout": heldout(m["x"], m["ctrl"], runs),
    }
    inside = np.zeros(len(state), dtype=bool)
    for a, b in runs:
        inside[a:b] = True
    gap = inside & ~present
    result["frames_changed"] = {name: int((s != state).sum()) for name, s in fills.items()}

    # (b) public live frames without ball.
    gt = cs.read_codes(cs.resolve_ground_truth("public"), len(state), "ground truth")
    live_gap = ((gt == pm.H) | (gt == pm.A)) & ~present
    truth = (gt[live_gap] == pm.H).astype(float)
    ps = smooth(p_home, runs)
    public = {
        "frames": int(live_gap.sum()),
        "model_raw": _accuracy(p_home[live_gap], truth),
        "model_smoothed": _accuracy(ps[live_gap], truth),
    }
    for name, s in {"engine": state, **fills}.items():
        public[name] = float(np.mean(s[live_gap] == np.where(truth > 0.5, 0, 1)))
    result["public_no_ball"] = public

    # (c) Smart Tagging agreement on gap frames: a frame counts when every vote goes to one side.
    votes = st.possession_votes(st.load())
    single = (votes[:, 0] > 0) ^ (votes[:, 1] > 0)
    owner = np.where(votes[:, 0] > 0, 0, 1)
    cut = bl.blocks(bl.halves())

    def agreement(s: np.ndarray, where: np.ndarray) -> tuple[int, float]:
        judged = where & single & (s != NONE)
        return int(judged.sum()), float(np.mean(s[judged] == owner[judged])) if judged.any() else 0

    smart: dict = {}
    for label, where in [("match", gap)] + [
        (str(b.index), gap & (np.arange(len(state)) >= b.start) & (np.arange(len(state)) < b.stop))
        for b in cut
    ]:
        row = {}
        for name, s in {"engine": state, **fills}.items():
            row["frames"], row[name] = agreement(s, where)
        smart[label] = row
    changed = {}
    for name, s in fills.items():
        diff = s != state
        changed[name] = {
            "frames": agreement(s, diff)[0],
            "engine": agreement(state, diff)[1],
            "fill": agreement(s, diff)[1],
        }
    result["smart_tagging_gap"] = smart
    result["smart_tagging_changed_frames"] = changed

    # Post hoc, after the gates were read: does the raw formation agree with the tagging where the
    # ball is lost? Diagnostic only; nothing here feeds back into the rule or the variants.
    ps_team = np.where(smooth(p_home, runs) > 0.5, 0, 1)
    confident = np.abs(smooth(p_home, runs) - 0.5) >= 0.3
    diagnostic: dict = {}
    for label, where in [("match", gap)] + [
        (str(b.index), gap & (np.arange(len(state)) >= b.start) & (np.arange(len(state)) < b.stop))
        for b in cut
        if b.index in (7, 9, 11, 18)
    ]:
        judged = where & single & (state != NONE)
        sure = judged & confident
        diagnostic[label] = {
            "frames": int(judged.sum()),
            "engine": float(np.mean(state[judged] == owner[judged])),
            "model_smoothed": float(np.mean(ps_team[judged] == owner[judged])),
            "model_confident_share": float(sure.sum() / judged.sum()),
            "model_confident": float(np.mean(ps_team[sure] == owner[sure])) if sure.any() else 0,
        }
    result["posthoc_model_vs_smart_tagging_gap"] = diagnostic

    # (d) public spellF1, paired against the engine; (e) possessions per minute per block.
    engine_csv = _labels_csv(state, out_dir / "engine.csv")
    spell: dict = {}
    rates: dict = {}
    rows = bl.measure(list(engine.labels(state)), present, votes, cut, runs)
    rates["engine"] = [round(r.rate, 2) for r in rows]
    for name, s in fills.items():
        compared = cs.compare_files(
            engine_csv, _labels_csv(s, out_dir / f"{name}.csv"), cs.resolve_ground_truth("public")
        )
        sign = compared["sign_diagnostic"]  # aggregates only: its per-possession rows stay here
        spell[name] = {
            "engine": compared["a"]["mean_spell_f1"],
            "fill": compared["b"]["mean_spell_f1"],
            "delta": compared["delta_mean_spell_f1_b_minus_a"],
            "n_discordant": sign["n_discordant"],
            "wins_engine": sign["wins_a"],
            "wins_fill": sign["wins_b"],
        }
        rows = bl.measure(list(engine.labels(s)), present, votes, cut, runs)
        rates[name] = [round(r.rate, 2) for r in rows]
    result["public_spell_f1"] = spell
    result["possessions_per_minute"] = {"blocks": [r.label for r in rows], **rates}
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Lane F: formation evidence in ball gaps")
    parser.add_argument("--measure", type=Path, help="measure everything, label CSVs go here")
    args = parser.parse_args(argv)
    if args.measure is None:
        parser.error("nothing to do: pass --measure <dir>")
    try:
        result = measure(args.measure)
    except (OSError, ValueError, RuntimeError) as problem:
        print(f"formation failed: {problem}", file=sys.stderr)
        return 1
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
