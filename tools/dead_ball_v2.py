"""Lane dead-v2: dead ball from how the players move, on top of the delivered stream (#16).

    python tools/dead_ball_v2.py --variant model --labels runs/dead_v2/model.csv --gt public
    python tools/dead_ball_v2.py --bench                     # gap-transplant bench, every variant
    python tools/dead_ball_v2.py dfl-convert --dir DFL_DIR   # offline: public DFL XML -> npz
    python tools/dead_ball_v2.py train --dir DFL_DIR --check # offline: refit, compare with MODEL
    python tools/dead_ball_v2.py dfl-bench --dir DFL_DIR     # offline: our engine on DFL

Why
---
The delivered stream (`tools/dead_ball.py`, variant `out`) only sees a stoppage that Smart Tagging
tagged: 59 restarts in a match that has about a hundred. Every untagged stoppage -- a foul, an
offside, an injury, most throw-ins -- merges the possessions either side of it, and on the public
slice that is two of its four `D` spans. The ball cannot find them either: it is missing on a third
of `D` frames and seen outside the pitch on 7% of them (DECISIONS 16).

The players can. When the referee stops play nobody sprints: the fastest players drop to walking
pace within a second of the whistle and stay there until the restart, while in live play somebody
is always running. That signature needs neither the ball nor player identities, so it holds where
the tracker loses the ball and survives slot swaps.

How it was fixed without the public ground truth
------------------------------------------------
The public Sportec/DFL dataset (Bassek et al. 2025, CC-BY 4.0, seven Bundesliga matches) labels
every frame alive or dead and names the team in possession. Everything below was fitted or chosen
there, before this module met our labels (docs/proposals/lane-dead-v2.md):

- the per-frame features (`features`): the median and the 90th percentile of the players' speeds
  over seven past/future windows, and five set-piece setup signals (a player at a corner flag,
  players on a touchline, players in the boxes, the spread of the field) over three windows. All
  of them are order-invariant -- a quantile or a count over whichever slots are tracked;
- a logistic regression on them (`MODEL`), fitted by Newton's method with a fixed ridge, so the
  fit is a deterministic function of the data and the weights are embedded below;
- the decoder (`Params`): a frame is dead above probability 0.5, live gaps under 1 s inside a
  stoppage are closed, and dead runs under 4 s are dropped. Chosen on the DFL leave-one-match-out
  spellF1 with our own engine run on DFL, with and without our match's missing-ball pattern.

Variants (`VARIANTS`, pre-registered)
-------------------------------------
- `rule`: one threshold, the 90th-percentile player speed over +/- 1 s below 2 m/s, decoded the
  same way, united with the delivered `D`;
- `model`: the logistic detector, united with the delivered `D`;
- `model+first-control`: `model`, and a stoppage the tags do not close hands the ball to the team
  of the first control after it, from its last frame (CHALLENGE.md: "whenever play restarts after
  a stoppage, there is a clear possessor");
- `model-only`: the detector alone, without the delivered `D` (ablation).

Only numpy and pandas run in the delivered path; the DFL commands need kloppy and stay offline.
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
from tools import dead_ball, engine  # noqa: E402

FPS = int(games.GAMES[games.GAME]["fps"])

VARIANTS = ("rule", "model", "model+first-control", "model-only")

# Past/future windows in seconds, `[a, b)` around each frame. The whistle shows in the seconds after
# it (players stop), the restart in the seconds after the restart (they start), so both directions
# are needed; the long ones carry the slower context of a stoppage that has lasted a while.
SPEED_WINDOWS = ((-1, 1), (-4, 0), (0, 4), (-10, 0), (0, 10), (-30, 0), (0, 30))
SETUP_WINDOWS = ((-2, 2), (-10, 0), (0, 10))
SPEED_SIGNALS = ("speed_p50", "speed_p90")
SETUP_SIGNALS = ("corner_m", "touchline_n", "box_n", "spread_x_m", "spread_y_m")


@dataclass(frozen=True)
class Params:
    """Fixed on the DFL data before any variant met our labels (lane-dead-v2.md, section 3)."""

    # A player's speed is the displacement over +/- 12 frames (0.96 s): one second of tracking
    # averages out the jitter of the automatic export, which a frame-to-frame difference amplifies.
    speed_half_window: int = 12
    # Faster than a sprint is a slot that jumped to another person, not a player: unknown.
    max_player_mps: float = 12.0
    # A quantile over fewer slots than this says nothing about the field.
    min_players: int = 8
    # `rule`: the 90th percentile (the second-fastest of ~21 players) below a fast walk.
    rule_mps: float = 2.0
    # The decoder: the probability above which a frame is dead, then live gaps shorter than
    # `min_live_s` inside a stoppage are closed and dead runs shorter than `min_dead_s` dropped.
    threshold: float = 0.5
    min_dead_s: float = 4.0
    min_live_s: float = 1.0
    # A player within this of a corner flag, or this close to a touchline, is setting a restart.
    corner_cap_m: float = 30.0
    touchline_m: float = 1.0

    def frames(self, seconds: float) -> int:
        return int(round(seconds * FPS))


DEFAULT = Params()


def feature_names() -> list[str]:
    """The model's columns, in order: every signal over every one of its windows."""
    names = [f"{s}[{a},{b}]" for s in SPEED_SIGNALS for a, b in SPEED_WINDOWS]
    return names + [f"{s}[{a},{b}]" for s in SETUP_SIGNALS for a, b in SETUP_WINDOWS]


# The logistic detector, fitted by `train` on all seven DFL matches (every 5th frame). `mean` and
# `scale` standardise each feature; `weights[0]` is the intercept. Regenerate with
# `python tools/dead_ball_v2.py train --dir DFL_DIR`; `--check` proves the constant is the fit.
MODEL: dict[str, list] = {
    "names": [
        "speed_p50[-1,1]",
        "speed_p50[-4,0]",
        "speed_p50[0,4]",
        "speed_p50[-10,0]",
        "speed_p50[0,10]",
        "speed_p50[-30,0]",
        "speed_p50[0,30]",
        "speed_p90[-1,1]",
        "speed_p90[-4,0]",
        "speed_p90[0,4]",
        "speed_p90[-10,0]",
        "speed_p90[0,10]",
        "speed_p90[-30,0]",
        "speed_p90[0,30]",
        "corner_m[-2,2]",
        "corner_m[-10,0]",
        "corner_m[0,10]",
        "touchline_n[-2,2]",
        "touchline_n[-10,0]",
        "touchline_n[0,10]",
        "box_n[-2,2]",
        "box_n[-10,0]",
        "box_n[0,10]",
        "spread_x_m[-2,2]",
        "spread_x_m[-10,0]",
        "spread_x_m[0,10]",
        "spread_y_m[-2,2]",
        "spread_y_m[-10,0]",
        "spread_y_m[0,10]",
    ],
    "mean": [
        1.6558222818650865,
        1.6560947149261105,
        1.655556410715618,
        1.6571633237597398,
        1.6538876468060715,
        1.6601893072088256,
        1.6510518244279615,
        2.9084743345768227,
        2.909787903626425,
        2.9070048294631308,
        2.912152886002106,
        2.9043070111377776,
        2.917118086241785,
        2.8997443681392343,
        23.17797027468771,
        23.187731845455623,
        23.169817448576993,
        0.3906943957664257,
        0.39081256446739804,
        0.3906684371716206,
        3.536037703058662,
        3.5337427145099833,
        3.538066475987682,
        16.125307993371116,
        16.127150767220876,
        16.122945872560205,
        11.910068546399799,
        11.914358274638959,
        11.906350929456867,
    ],
    "scale": [
        0.9808772157374412,
        0.9377665033025375,
        0.9377747267760851,
        0.8216592388530777,
        0.8205618439122856,
        0.6174524224550557,
        0.6135282639765348,
        1.3994758802871328,
        1.3420447129516824,
        1.3416930231741866,
        1.194300615692952,
        1.1925740702194627,
        0.89724116750469,
        0.8927979045132702,
        7.669104490289238,
        7.260766725973209,
        7.269941859560055,
        0.7028443402046172,
        0.6492346991611253,
        0.6491880347219022,
        4.028035159349597,
        3.8696967024049336,
        3.872388015079684,
        2.3805347359839115,
        2.283879485327829,
        2.288049239295015,
        2.641016133586815,
        2.5307707445227976,
        2.533918572312893,
    ],
    "weights": [
        -0.6521034976887673,
        -0.23206435630215788,
        0.1343928852694397,
        -0.7936083091066799,
        0.19574716158214608,
        0.01797155404614117,
        -0.41708686553558577,
        -0.1483411507218643,
        -1.311975292256963,
        -0.5511761367541241,
        0.3094429067008827,
        -0.15545378143862415,
        -1.5531752337954539,
        0.10172748361147939,
        0.17143986698721872,
        0.2650966770415895,
        -0.31979388014457066,
        -0.38930820943301114,
        0.8878387747541441,
        -0.437750628894145,
        -0.02658135582922947,
        -0.7227659788478498,
        0.8541566793316601,
        -0.21756535565971455,
        0.5513159628473444,
        -0.1491476948670931,
        0.18645287224401558,
        -0.2700930588514776,
        0.08694541020402977,
        -0.67475919474378,
    ],
}


# -- features ----------------------------------------------------------------------------------


def window_mean(x: np.ndarray, start: int, stop: int) -> np.ndarray:
    """Mean of `x` over frames `[t + start, t + stop)`, using only the frames it measured.

    The window is clipped at the array's edges; a window with no measurement is NaN, never zero.
    """
    x = np.asarray(x, dtype=float)
    if stop <= start:
        raise ValueError(f"empty window [{start}, {stop})")
    n = len(x)
    known = np.isfinite(x)
    sums = np.concatenate(([0.0], np.cumsum(np.where(known, x, 0.0))))
    counts = np.concatenate(([0], np.cumsum(known)))
    index = np.arange(n)
    lo = np.clip(index + start, 0, n)
    hi = np.clip(index + stop, 0, n)
    total, count = sums[hi] - sums[lo], counts[hi] - counts[lo]
    out = np.full(n, np.nan)
    np.divide(total, count, out=out, where=count > 0)
    return out


def player_speeds(players_xy_m: np.ndarray, params: Params = DEFAULT) -> np.ndarray:
    """`(frames, slots)` speed in m/s over +/- `speed_half_window` frames; NaN where unknown."""
    p = np.asarray(players_xy_m, dtype=float)
    h = params.speed_half_window
    speed = np.full(p.shape[:2], np.nan)
    if len(p) > 2 * h:
        speed[h:-h] = np.linalg.norm(p[2 * h :] - p[: -2 * h], axis=2) / (2 * h / FPS)
    speed[speed > params.max_player_mps] = np.nan
    return speed


def speed_quantiles(
    players_xy_m: np.ndarray, params: Params = DEFAULT
) -> tuple[np.ndarray, np.ndarray]:
    """Per-frame p50 and p90 of the players' speeds; NaN with fewer than `min_players` known."""
    speed = player_speeds(np.asarray(players_xy_m, dtype=float), params)
    n = len(speed)
    enough = np.isfinite(speed).sum(axis=1) >= params.min_players
    p50, p90 = np.full(n, np.nan), np.full(n, np.nan)
    if enough.any():
        p50[enough] = np.nanpercentile(speed[enough], 50, axis=1)
        p90[enough] = np.nanpercentile(speed[enough], 90, axis=1)
    return p50, p90


def frame_signals(
    players_xy_m: np.ndarray, pitch_m: Sequence[float], params: Params = DEFAULT
) -> dict[str, np.ndarray]:
    """Per-frame signals before windowing. Positions in metres, origin at a corner, NaN missing."""
    p = np.asarray(players_xy_m, dtype=float)
    length, width = float(pitch_m[0]), float(pitch_m[1])
    n = len(p)
    p50, p90 = speed_quantiles(p, params)

    x, y = p[..., 0], p[..., 1]
    seen = np.isfinite(x) & np.isfinite(y)
    corner = np.full(n, params.corner_cap_m)
    for cx in (0.0, length):
        for cy in (0.0, width):
            d = np.where(seen, np.hypot(x - cx, y - cy), np.inf)
            corner = np.minimum(corner, d.min(axis=1))
    edge = np.where(seen, np.minimum(y, width - y), np.inf)
    # The penalty area is 16.5 m deep and 40.32 m wide.
    box = seen & ((x < 16.5) | (x > length - 16.5)) & (np.abs(y - width / 2) < 20.16)
    any_seen = seen.any(axis=1)
    spread_x, spread_y = np.full(n, np.nan), np.full(n, np.nan)
    spread_x[any_seen] = np.nanstd(np.where(seen, x, np.nan)[any_seen], axis=1)
    spread_y[any_seen] = np.nanstd(np.where(seen, y, np.nan)[any_seen], axis=1)
    return {
        "speed_p50": p50,
        "speed_p90": p90,
        "corner_m": np.where(any_seen, corner, np.nan),
        "touchline_n": np.where(any_seen, (edge < params.touchline_m).sum(axis=1), np.nan),
        "box_n": np.where(any_seen, box.sum(axis=1), np.nan),
        "spread_x_m": spread_x,
        "spread_y_m": spread_y,
    }


def features(
    players_xy_m: np.ndarray, pitch_m: Sequence[float], params: Params = DEFAULT
) -> np.ndarray:
    """`(frames, len(feature_names()))`: every signal averaged over each of its windows.

    Call it on one contiguous run (a half): a window must not reach across the half-time hole.
    """
    return _windowed(frame_signals(players_xy_m, pitch_m, params))


def _windowed(signals: dict[str, np.ndarray]) -> np.ndarray:
    columns = []
    for group, windows in ((SPEED_SIGNALS, SPEED_WINDOWS), (SETUP_SIGNALS, SETUP_WINDOWS)):
        for signal in group:
            for a, b in windows:
                columns.append(window_mean(signals[signal], a * FPS, b * FPS))
    return np.column_stack(columns)


# -- the detector ------------------------------------------------------------------------------


def fit_logistic(
    x: np.ndarray, y: np.ndarray, ridge: float = 1.0, iterations: int = 25
) -> dict[str, list]:
    """Ridge logistic regression by Newton's method: deterministic, no seed, no library.

    Features are standardised on the training rows and a missing value is the training mean (0
    after standardising). The intercept is not penalised.
    """
    x = np.asarray(x, dtype=float)
    y = np.asarray(y, dtype=float)
    mean = np.nanmean(x, axis=0)
    scale = np.nanstd(x, axis=0)
    scale[~(scale > 0)] = 1.0
    z = np.where(np.isfinite(x), (x - mean) / scale, 0.0)
    z = np.column_stack([np.ones(len(z)), z])
    penalty = ridge * np.eye(z.shape[1])
    penalty[0, 0] = 0.0
    w = np.zeros(z.shape[1])
    for _ in range(iterations):
        p = 1.0 / (1.0 + np.exp(-(z @ w)))
        gradient = z.T @ (p - y) + penalty @ w
        hessian = (z * (p * (1 - p))[:, None]).T @ z + penalty
        w = w - np.linalg.solve(hessian, gradient)
    return {
        "names": feature_names(),
        "mean": [float(v) for v in mean],
        "scale": [float(v) for v in scale],
        "weights": [float(v) for v in w],
    }


def probability(x: np.ndarray, model: dict[str, list] | None = None) -> np.ndarray:
    """P(dead) per frame from the feature matrix."""
    model = model or MODEL
    if list(model["names"]) != feature_names():
        raise ValueError("the model's feature names do not match feature_names(); retrain it")
    mean, scale = np.asarray(model["mean"]), np.asarray(model["scale"])
    w = np.asarray(model["weights"])
    z = np.where(np.isfinite(x), (x - mean) / scale, 0.0)
    return 1.0 / (1.0 + np.exp(-(w[0] + z @ w[1:])))


def runs_of(mask: np.ndarray) -> list[tuple[int, int]]:
    """Maximal `[start, stop)` runs of True."""
    m = np.concatenate(([False], np.asarray(mask, dtype=bool), [False]))
    edges = np.diff(m.astype(np.int8))
    return list(zip(np.flatnonzero(edges == 1).tolist(), np.flatnonzero(edges == -1).tolist()))


def decode(dead: np.ndarray, params: Params = DEFAULT) -> np.ndarray:
    """Per-frame dead -> stoppages: close short live gaps, then drop short dead runs.

    A live gap is closed only between two dead runs, never at the edge of the array: a stoppage
    must have evidence on both sides of the gap it swallows.
    """
    dead = np.asarray(dead, dtype=bool).copy()
    for start, stop in runs_of(~dead):
        if stop - start < params.frames(params.min_live_s) and start > 0 and stop < len(dead):
            dead[start:stop] = True
    for start, stop in runs_of(dead):
        if stop - start < params.frames(params.min_dead_s):
            dead[start:stop] = False
    return dead


def kinematic_mask(
    players_xy_m: np.ndarray,
    pitch_m: Sequence[float],
    runs: Sequence[tuple[int, int]],
    method: str = "model",
    params: Params = DEFAULT,
    model: dict[str, list] | None = None,
) -> np.ndarray:
    """`True` where the players say the ball is dead, decoded half by half.

    A frame whose own speed quantile is unknown is never dead: losing the players is not evidence
    that they stopped (the same rule as `dead_ball.stillness`).
    """
    if method not in ("model", "rule"):
        raise ValueError(f"unknown method {method!r}")
    n = len(players_xy_m)
    dead = np.zeros(n, dtype=bool)
    for start, stop in runs:
        start, stop = max(0, start), min(n, stop)
        segment = players_xy_m[start:stop]
        if method == "rule":
            # The rule needs one signal: compute only it, not the model's 29 windowed columns.
            _p50, p90 = speed_quantiles(segment, params)
            known = np.isfinite(p90)  # the frame's OWN quantile, as the docstring promises
            window = window_mean(p90, -FPS, FPS)
            raw = known & (np.nan_to_num(window, nan=np.inf) < params.rule_mps)
        else:
            signals = frame_signals(segment, pitch_m, params)
            known = np.isfinite(signals["speed_p90"])
            raw = known & (probability(_windowed(signals), model) > params.threshold)
        dead[start:stop] = decode(raw, params)
    return dead


# -- the chain ---------------------------------------------------------------------------------


def first_control_forcing(
    ctrl: np.ndarray,
    dead: np.ndarray,
    runs: Sequence[tuple[int, int]],
    restart_frames: Sequence[int] = (),
) -> dict[int, int]:
    """`{frame: team}`: each stoppage the tags do not close restarts with its first control.

    The frame is the stoppage's first live frame; the team is the one that first controls the ball
    after it, provided no other stoppage starts before that control. A stoppage holding a tagged
    restart is left to the tag (DECISIONS 30-32), so this never overrides `restart_controls`.
    """
    restarts = np.asarray(sorted(restart_frames), dtype=np.int64)
    forced: dict[int, int] = {}
    for start, stop in runs:
        for a, b in runs_of(dead[start:stop]):
            first, end = start + a, start + b
            if end >= stop:
                continue
            if restarts.size and np.any((restarts >= first) & (restarts <= end)):
                continue
            after = np.flatnonzero(ctrl[end:stop] != engine.NONE)
            if not after.size:
                continue
            control = end + int(after[0])
            if dead[end:control].any():
                continue
            forced[end] = int(ctrl[control])
    return forced


def dead_union(
    variant: str, ev: dead_ball.Evidence, kinematic: np.ndarray, runs: Sequence[tuple[int, int]]
) -> np.ndarray:
    """The variant's `D`: the delivered stoppages united with the players', or theirs alone."""
    if variant not in VARIANTS:
        raise ValueError(f"unknown variant {variant!r}; expected one of {', '.join(VARIANTS)}")
    kinematic = np.asarray(kinematic, dtype=bool)
    if variant == "model-only":
        return kinematic.copy()
    return dead_ball.dead_mask(ev, runs, "out") | kinematic


def chain(
    f: engine.Features,
    ev: dead_ball.Evidence,
    kinematic: np.ndarray,
    variant: str,
    params: engine.Params = engine.D31,
) -> np.ndarray:
    """The lane's chain with this variant's `D`: H/A/D/X per frame for the whole match.

    The engine the lane measured against (DECISIONS 29-32: no duel rule, `engine.D31` decoding),
    the tagged restarts, plus -- for `model+first-control` -- the first-control restart of the
    stoppages the tags do not close. It is NOT the delivered chain, which since DECISIONS 34-36 is
    `engine.run()` (duel rule; `D` from `engine.delivered_dead`).
    """
    runs = engine.halves()
    dead = dead_union(variant, ev, kinematic, runs)
    ctrl = engine.control(f, params)
    forced = engine.restart_controls(ev.restarts, ctrl)
    if variant == "model+first-control":
        extra = first_control_forcing(ctrl, dead, runs, [r.frame for r in ev.restarts])
        forced = {**extra, **forced}
    state = engine.decode(ctrl, runs, params.dwell, forced)
    out = engine.labels(state)
    out[dead] = "D"
    return out


def match_kinematic(method: str = "model", params: Params = DEFAULT) -> np.ndarray:
    """The players' stoppages over the delivered match (tactical tracking, both halves)."""
    from tools import atd
    from tools.ball_gaps import half_runs

    tracking = atd.load("tactical")
    players = tracking.players_array[:, :, :2] * engine.PITCH_M
    return kinematic_mask(players, engine.PITCH_M, half_runs(), method, params)


def kinematic_for(variant: str, params: Params = DEFAULT) -> np.ndarray:
    return match_kinematic("rule" if variant == "rule" else "model", params)


def bench_methods(
    kinematic: dict[str, np.ndarray],
) -> dict[str, Callable[[engine.Features, dead_ball.Evidence], np.ndarray]]:
    """Bench methods (`tools/bench.py` signature) for each variant.

    The players are not degraded by the bench, so the kinematic mask is computed once and closed
    over; the bench still removes the ball from the engine and from the delivered `D`.
    """
    methods = {}
    for variant in VARIANTS:
        mask = kinematic["rule" if variant == "rule" else "model"]
        methods[variant] = lambda f, ev, v=variant, m=mask: chain(f, ev, m, v)
    return methods


# -- the public DFL data (offline; never mixed with the match data) ----------------------------

DFL_MATCHES = ("J03WMX", "J03WN1", "J03WOH", "J03WOY", "J03WPY", "J03WQQ", "J03WR9")
# figshare article 28196177 (doi 10.6084/m9.figshare.28196177.v1): (matchinformation, positions).
DFL_FILES = {
    "J03WMX": (51643475, 51643514),
    "J03WN1": (51643472, 51643517),
    "J03WOH": (51643478, 51643520),
    "J03WOY": (51643481, 51643523),
    "J03WPY": (51643487, 51643526),
    "J03WQQ": (51643484, 51643529),
    "J03WR9": (51643490, 51643532),
}
DFL_URL = "https://ndownloader.figshare.com/files/{}"
TRAIN_STRIDE = 5  # every 5th frame: neighbouring frames are near-duplicates and 5x is plenty


def dfl_convert(directory: Path, match: str) -> Path:
    """`meta_<id>.xml` + `pos_<id>.xml` -> `<id>.npz` (players, ball, alive, period, owner)."""
    from kloppy import sportec

    ds = sportec.load_tracking(
        raw_data=str(directory / f"pos_{match}.xml"),
        meta_data=str(directory / f"meta_{match}.xml"),
        only_alive=False,
        coordinates="sportec",
    )
    seen = {}
    for frame in ds.frames:
        for player in frame.players_data:
            seen.setdefault(player.player_id, player)
    players = sorted(seen.values(), key=lambda p: p.player_id)
    slot = {p.player_id: i for i, p in enumerate(players)}
    home = ds.metadata.teams[0]
    n = len(ds.frames)
    xy = np.full((n, len(players), 2), np.nan, dtype=np.float32)
    ball = np.full((n, 2), np.nan, dtype=np.float32)
    alive = np.zeros(n, dtype=bool)
    period = np.zeros(n, dtype=np.int8)
    owner = np.full(n, -1, dtype=np.int8)
    for i, frame in enumerate(ds.frames):
        for player, data in frame.players_data.items():
            if data.coordinates is not None:
                xy[i, slot[player.player_id]] = (data.coordinates.x, data.coordinates.y)
        if frame.ball_coordinates is not None:
            ball[i] = (frame.ball_coordinates.x, frame.ball_coordinates.y)
        alive[i] = str(frame.ball_state).lower().endswith("alive")
        period[i] = frame.period.id
        if frame.ball_owning_team is not None:
            owner[i] = 0 if frame.ball_owning_team == home else 1
    pitch = ds.metadata.pitch_dimensions
    team = np.array([0 if p.team == home else 1 for p in players], dtype=np.int8)
    out = directory / f"{match}.npz"
    np.savez_compressed(
        out,
        P=xy,
        B=ball,
        alive=alive,
        period=period,
        own=owner,
        team=team,
        L=pitch.pitch_length,
        W=pitch.pitch_width,
    )
    return out


@dataclass(frozen=True)
class DflMatch:
    """One DFL match in our conventions: metres from a corner, periods as half-open runs."""

    players: np.ndarray
    ball: np.ndarray
    team: np.ndarray
    alive: np.ndarray
    owner: np.ndarray
    pitch: tuple[float, float]
    runs: list[tuple[int, int]]


def dfl_load(directory: Path, match: str) -> DflMatch:
    z = np.load(directory / f"{match}.npz")
    length, width = float(z["L"]), float(z["W"])
    # The sportec coordinates are centred; ours start at a corner.
    shift = np.array([length / 2, width / 2])
    period = z["period"]
    cuts = np.flatnonzero(np.diff(period) != 0) + 1
    edges = [0, *cuts.tolist(), len(period)]
    return DflMatch(
        players=z["P"].astype(float) + shift,
        ball=z["B"].astype(float) + shift,
        team=z["team"],
        alive=z["alive"],
        owner=z["own"],
        pitch=(length, width),
        runs=list(zip(edges[:-1], edges[1:])),
    )


def dfl_training_rows(
    directory: Path, matches: Sequence[str], params: Params = DEFAULT
) -> tuple[np.ndarray, np.ndarray]:
    xs, ys = [], []
    for match in matches:
        m = dfl_load(directory, match)
        for start, stop in m.runs:
            xs.append(features(m.players[start:stop], m.pitch, params)[::TRAIN_STRIDE])
            ys.append(~m.alive[start:stop][::TRAIN_STRIDE])
    return np.vstack(xs), np.concatenate(ys)


def dfl_engine_features(m: DflMatch, keep: np.ndarray | None = None) -> engine.Features:
    """Our engine's inputs from a DFL match; `keep` deletes the ball where False (dropout)."""
    from tools import emision

    present = np.isfinite(m.ball[:, 0]) & np.isfinite(m.ball[:, 1])
    if keep is not None:
        present &= keep
    distance = np.linalg.norm(m.players - m.ball[:, None, :], axis=2)
    distance[~np.isfinite(distance)] = np.inf
    home = m.team == 0
    home_m = distance[:, home].min(axis=1)
    away_m = distance[:, ~home].min(axis=1)
    home_m[~present] = np.nan
    away_m[~present] = np.nan
    speed = emision._ball_speed(m.ball, present)
    for start, _stop in m.runs:
        speed[start] = np.nan  # a speed never bridges two periods
    length, width = m.pitch
    x, y = m.ball[:, 0], m.ball[:, 1]
    in_pitch = present & (x >= 0) & (x <= length) & (y >= 0) & (y <= width)
    return engine.Features(home_m, away_m, present, speed, in_pitch)


def _spell_f1(truth: np.ndarray, labels: np.ndarray, runs: Sequence[tuple[int, int]]) -> float:
    """The official spellF1 on a DFL match, with an `X` frame between periods."""
    sys.path.insert(0, str(REPO_ROOT / "evaluation"))
    import possession_metrics as pm

    def joined(codes: np.ndarray) -> np.ndarray:
        parts = []
        for start, stop in runs:
            parts += [codes[start:stop], np.array([3], dtype=np.int8)]
        return np.concatenate(parts[:-1]).astype(np.int8)

    gt, pred = joined(truth), joined(labels)
    valid = pm.valid_runs(gt)
    return float(pm.spell_scores(gt, pm.fill_abstentions(pred, valid), valid)["mean_f1"])


def dfl_bench(directory: Path, dropout: np.ndarray | None = None) -> dict[str, list[float]]:
    """Our engine on each DFL match with each `D` method, leave-one-match-out for the model.

    `bare` has no `D` (DFL has no Smart Tagging, so there is no delivered stream to unite with);
    `truth` inserts the true `D` (the ceiling). `dropout`, a ball-presence pattern, is tiled over
    each match to delete the ball where our match lost it.
    """
    rows: dict[str, list[float]] = {
        k: [] for k in ("bare", "rule", "model", "model+first-control", "truth")
    }
    cache = {m: dfl_training_rows(directory, [m]) for m in DFL_MATCHES}
    for match in DFL_MATCHES:
        rest = [m for m in DFL_MATCHES if m != match]
        model = fit_logistic(
            np.vstack([cache[m][0] for m in rest]), np.concatenate([cache[m][1] for m in rest])
        )
        m = dfl_load(directory, match)
        keep = None if dropout is None else np.resize(np.asarray(dropout, dtype=bool), len(m.alive))
        f = dfl_engine_features(m, keep)
        ctrl = engine.control(f)
        truth = np.where(m.alive, m.owner, 2).astype(np.int8)
        masks = {
            "rule": kinematic_mask(m.players, m.pitch, m.runs, "rule"),
            "model": kinematic_mask(m.players, m.pitch, m.runs, "model", model=model),
            "truth": ~m.alive,
        }
        masks["model+first-control"] = masks["model"]
        for name in rows:
            forced = None
            if name == "model+first-control":
                forced = first_control_forcing(ctrl, masks[name], m.runs)
            state = engine.decode(ctrl, m.runs, 1, forced)
            codes = np.where(state == 0, 0, np.where(state == 1, 1, 3)).astype(np.int8)
            if name in masks:
                codes[masks[name]] = 2
            rows[name].append(_spell_f1(truth, codes, m.runs))
    return rows


def _model_literal(model: dict[str, list]) -> str:
    lines = ["MODEL: dict[str, list] = {"]
    for key in ("names", "mean", "scale", "weights"):
        lines.append(f"    {json.dumps(key)}: [")
        for value in model[key]:
            lines.append(f"        {json.dumps(value) if isinstance(value, str) else repr(value)},")
        lines.append("    ],")
    return "\n".join(lines + ["}"])


# -- command line ------------------------------------------------------------------------------


def _public_report(labels: np.ndarray, dead: np.ndarray) -> dict:
    from tools.compare_submissions import resolve_ground_truth

    gt = pd.read_csv(resolve_ground_truth("public"), keep_default_na=False)["label"].to_numpy()
    sys.path.insert(0, str(REPO_ROOT / "evaluation"))
    import possession_metrics as pm

    result = pm.evaluate(pm.label_codes(gt), pm.label_codes(list(labels)))
    return {
        "spell_f1": result["spell_f1_mean"],
        "macro_f1": result["macro_f1"],
        "n_pred_spells": result["n_pred_spells"],
        "d_detection": dead_ball.dead_precision_recall(gt, dead),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Dead ball from the players (lane dead-v2)")
    sub = parser.add_subparsers(dest="command")
    for name in ("dfl-convert", "train", "dfl-bench"):
        p = sub.add_parser(name)
        p.add_argument("--dir", type=Path, required=True, help="the public DFL files")
        if name == "train":
            p.add_argument("--check", action="store_true", help="fail unless MODEL is the fit")
        if name == "dfl-bench":
            p.add_argument("--dropout", action="store_true", help="our match's ball pattern")
    parser.add_argument("--variant", choices=VARIANTS, default="model")
    parser.add_argument("--labels", type=Path, help="write the frame,label CSV here")
    parser.add_argument("--gt", choices=["public"], help="score against the public slice")
    parser.add_argument("--bench", action="store_true", help="gap-transplant bench, all variants")
    args = parser.parse_args(argv)
    try:
        if args.command == "dfl-convert":
            for match in DFL_MATCHES:
                print(f"wrote {dfl_convert(args.dir, match)}")
            return 0
        if args.command == "train":
            model = fit_logistic(*dfl_training_rows(args.dir, DFL_MATCHES))
            if args.check:
                same = (
                    all(
                        np.array_equal(np.asarray(model[k]), np.asarray(MODEL[k]))
                        for k in ("mean", "scale", "weights")
                    )
                    and list(MODEL["names"]) == model["names"]
                )
                print("MODEL matches the fit" if same else "MODEL differs from the fit")
                return 0 if same else 1
            print(_model_literal(model))
            return 0
        if args.command == "dfl-bench":
            dropout = None
            if args.dropout:
                from tools import atd

                _ball, present = atd.load("tactical").ball()
                dropout = np.concatenate([present[a:b] for a, b in engine.halves()])
            rows = dfl_bench(args.dir, dropout)
            print(json.dumps({k: [round(v, 4) for v in vs] for k, vs in rows.items()}, indent=2))
            print(json.dumps({k: round(float(np.mean(vs)), 4) for k, vs in rows.items()}))
            return 0

        from tools import atd, bench, emision

        if args.bench:
            kin = {"rule": match_kinematic("rule"), "model": match_kinematic("model")}
            f, ev, gt, cut = bench.load()

            # The baseline the lane measured against: the D31 engine with the tagged D only, not
            # the delivered chain (which already contains the `rule` D and the duel rule).
            def _engine_d31(f: engine.Features, ev: dead_ball.Evidence) -> np.ndarray:
                tagged = dead_ball.dead_mask(ev, engine.halves(), "out")
                return engine.chain(f, engine.D31, ev.restarts, tagged)[2]

            methods = {"engine": _engine_d31, **bench_methods(kin)}
            for name, method in methods.items():
                print(name, json.dumps(bench.summary(bench.bench(method, f, ev, gt, cut))))
            return 0

        f = engine.features(atd.load("tactical"), emision.team_slots())
        ev = dead_ball.load_evidence()
        kin = kinematic_for(args.variant)
        labels = chain(f, ev, kin, args.variant)
        dead = labels == "D"
        inside = np.zeros(len(labels), dtype=bool)
        for start, stop in engine.halves():
            inside[start:stop] = True
        result = {
            "variant": args.variant,
            "dead_share_in_halves": float(dead[inside].mean()),
            "kinematic_share_in_halves": float(kin[inside].mean()),
            "kinematic_stoppages": len(runs_of(kin)),
        }
        if args.labels:
            from tools.contract import check_submission

            table = pd.DataFrame({"frame": np.arange(len(labels)), "label": labels})
            table = check_submission(table, args.labels)
            args.labels.parent.mkdir(parents=True, exist_ok=True)
            table.to_csv(args.labels, index=False, lineterminator="\n")
        if args.gt:
            result["public"] = _public_report(labels, dead)
    except (OSError, ValueError, RuntimeError) as problem:
        print(f"dead_ball_v2 failed: {problem}", file=sys.stderr)
        return 1
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
