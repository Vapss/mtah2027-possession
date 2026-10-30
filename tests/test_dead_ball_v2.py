"""Lane dead-v2: each rule of the players' dead-ball detector, pinned on synthetic frames.

Synthetic fields are a handful of players on a 105 x 68 m pitch, moving at a chosen speed, so
every rule can be placed by hand: when the field is still, where a stoppage ends, which team
controls first. Times are in frames at 25 fps. One test reads the delivered match and skips on a
checkout without the bundle; it pins aggregates only, never a frame.
"""

from __future__ import annotations

import numpy as np
import pytest
from _bundle import requires_bundle

from tools import dead_ball, dead_ball_v2, engine
from tools.dead_ball_v2 import DEFAULT, Params

FPS = dead_ball_v2.FPS
PITCH = (105.0, 68.0)
NONE = engine.NONE


def field(speeds_mps: np.ndarray, players: int = 12) -> np.ndarray:
    """`(frames, players, 2)`: players spread over the pitch, all running along x at `speeds`."""
    speeds = np.asarray(speeds_mps, dtype=float)
    x0 = np.linspace(20.0, 80.0, players)
    y0 = np.linspace(10.0, 58.0, players)
    travelled = np.concatenate(([0.0], np.cumsum(speeds[1:]) / FPS))
    # Back and forth inside the pitch, so a long run never leaves it.
    offset = 10.0 * np.sin(travelled / 10.0)
    xy = np.empty((len(speeds), players, 2))
    xy[..., 0] = x0[None, :] + offset[:, None]
    xy[..., 1] = y0[None, :]
    return xy


# -- features ----------------------------------------------------------------------------------


def test_window_mean_uses_only_the_frames_it_measured() -> None:
    x = np.array([1.0, np.nan, 3.0, 5.0])
    out = dead_ball_v2.window_mean(x, 0, 2)
    assert out[0] == 1.0  # [1, nan]: the NaN is not a zero
    assert out[1] == 3.0
    assert out[2] == 4.0
    assert out[3] == 5.0  # clipped at the edge
    past = dead_ball_v2.window_mean(np.array([np.nan, np.nan, 2.0]), -1, 0)
    assert np.all(np.isnan(past))  # [t-1, t) never reaches the one measured frame
    with pytest.raises(ValueError, match="empty window"):
        dead_ball_v2.window_mean(x, 1, 1)


def test_player_speed_is_one_second_of_displacement() -> None:
    xy = np.zeros((100, 3, 2))
    xy[..., 0] = 3.0 * np.arange(100)[:, None] / FPS  # 3 m/s in a straight line
    speed = dead_ball_v2.player_speeds(xy)
    h = DEFAULT.speed_half_window
    assert np.all(np.isnan(speed[:h])) and np.all(np.isnan(speed[-h:]))
    assert np.allclose(speed[h:-h], 3.0)


def test_a_slot_that_jumps_faster_than_a_sprint_is_unknown_not_fast() -> None:
    xy = field(np.zeros(100))
    xy[50:, 0, 0] += 40.0  # an identity switch: the slot now follows someone 40 m away
    speed = dead_ball_v2.player_speeds(xy)
    assert np.all(np.isnan(speed[40:60, 0]))
    assert np.nanmax(speed[:, 1:]) < 1e-9


def test_too_few_tracked_players_give_no_speed_quantile() -> None:
    xy = field(np.full(100, 2.0), players=DEFAULT.min_players - 1)
    signals = dead_ball_v2.frame_signals(xy, PITCH)
    assert np.all(np.isnan(signals["speed_p90"]))


def test_setup_signals_count_the_corner_the_touchline_and_the_boxes() -> None:
    xy = np.full((1, 4, 2), np.nan)
    xy[0, 0] = (0.5, 0.5)  # at a corner flag, which is also on the touchline
    xy[0, 1] = (50.0, 67.5)  # on the far touchline
    xy[0, 2] = (10.0, 34.0)  # in a box
    signals = dead_ball_v2.frame_signals(xy, PITCH)
    assert signals["corner_m"][0] == pytest.approx(np.hypot(0.5, 0.5))
    assert signals["touchline_n"][0] == 2
    assert signals["box_n"][0] == 1  # a corner flag is wider than the penalty area
    empty = dead_ball_v2.frame_signals(np.full((1, 4, 2), np.nan), PITCH)
    assert np.isnan(empty["corner_m"][0]) and np.isnan(empty["touchline_n"][0])


def test_features_have_one_column_per_name() -> None:
    x = dead_ball_v2.features(field(np.full(200, 2.0)), PITCH)
    assert x.shape == (200, len(dead_ball_v2.feature_names()))
    assert len(set(dead_ball_v2.feature_names())) == x.shape[1]


# -- the detector ------------------------------------------------------------------------------


def test_the_embedded_model_is_complete_and_matches_the_feature_names() -> None:
    model = dead_ball_v2.MODEL
    assert list(model["names"]) == dead_ball_v2.feature_names()
    assert len(model["mean"]) == len(model["scale"]) == len(model["names"])
    assert len(model["weights"]) == len(model["names"]) + 1
    assert np.all(np.isfinite(model["weights"])) and np.all(np.asarray(model["scale"]) > 0)


def test_the_embedded_model_says_a_still_field_is_dead_and_a_running_one_is_not() -> None:
    still = dead_ball_v2.features(field(np.full(2000, 0.5)), PITCH)[1000]
    running = dead_ball_v2.features(field(np.full(2000, 5.0)), PITCH)[1000]
    p = dead_ball_v2.probability(np.vstack([still, running]))
    assert p[0] > 0.5 > p[1]


def test_fit_is_deterministic_and_learns_the_direction() -> None:
    x = np.linspace(-3, 3, 200)[:, None] * np.ones((1, len(dead_ball_v2.feature_names())))
    y = (x[:, 0] + np.sin(np.arange(200)) > 0).astype(float)
    a, b = dead_ball_v2.fit_logistic(x, y), dead_ball_v2.fit_logistic(x, y)
    assert a == b
    p = dead_ball_v2.probability(x[[0, -1]], a)
    assert p[0] < 0.5 < p[1]


def test_a_model_for_other_features_is_refused() -> None:
    bad = {**dead_ball_v2.MODEL, "names": ["something else"]}
    with pytest.raises(ValueError, match="feature names"):
        dead_ball_v2.probability(np.zeros((1, len(dead_ball_v2.feature_names()))), bad)


def test_decode_closes_short_live_gaps_inside_a_stoppage_and_drops_short_stoppages() -> None:
    p = Params(min_dead_s=4.0, min_live_s=1.0)
    dead = np.zeros(1000, dtype=bool)
    dead[100:200] = True
    dead[210:400] = True  # 10 live frames between them: one stoppage
    dead[600:650] = True  # 2 s: too short to be a stoppage
    out = dead_ball_v2.decode(dead, p)
    assert out[100:400].all()
    assert not out[600:650].any()
    assert not out[:100].any() and not out[400:].any()


def test_decode_never_closes_a_live_gap_at_the_edge() -> None:
    dead = np.zeros(300, dtype=bool)
    dead[10:300] = True  # 10 live frames at the start
    out = dead_ball_v2.decode(dead)
    assert not out[:10].any() and out[10:].all()


def test_the_rule_marks_a_still_field_inside_running_play() -> None:
    speeds = np.full(3000, 5.0)
    speeds[1000:1600] = 0.3  # a 24 s stoppage
    mask = dead_ball_v2.kinematic_mask(field(speeds), PITCH, [(0, 3000)], "rule")
    runs = dead_ball_v2.runs_of(mask)
    assert len(runs) == 1
    start, stop = runs[0]
    assert abs(start - 1000) < FPS and abs(stop - 1600) < FPS


def test_losing_the_players_is_never_a_stoppage() -> None:
    xy = field(np.full(3000, 0.3))
    xy[:, DEFAULT.min_players - 1 :] = np.nan  # too few players tracked anywhere
    for method in ("rule", "model"):
        assert not dead_ball_v2.kinematic_mask(xy, PITCH, [(0, 3000)], method).any()


def test_nothing_is_marked_outside_the_runs() -> None:
    mask = dead_ball_v2.kinematic_mask(field(np.full(3000, 0.3)), PITCH, [(500, 2500)], "rule")
    assert not mask[:500].any() and not mask[2500:].any() and mask[1000:2000].all()


def test_an_unknown_method_fails_closed() -> None:
    with pytest.raises(ValueError, match="unknown method"):
        dead_ball_v2.kinematic_mask(field(np.zeros(10)), PITCH, [(0, 10)], "stillness")


# -- the chain ---------------------------------------------------------------------------------


def test_a_stoppage_restarts_with_the_first_control_after_it() -> None:
    ctrl = np.full(100, NONE, dtype=np.int8)
    ctrl[5] = 0
    ctrl[40] = 1  # inside the stoppage: a player picking the ball up does not decide it
    ctrl[70] = 1
    dead = np.zeros(100, dtype=bool)
    dead[30:60] = True
    assert dead_ball_v2.first_control_forcing(ctrl, dead, [(0, 100)]) == {60: 1}


def test_a_tagged_restart_inside_the_stoppage_is_left_to_the_tag() -> None:
    ctrl = np.full(100, NONE, dtype=np.int8)
    ctrl[70] = 1
    dead = np.zeros(100, dtype=bool)
    dead[30:60] = True
    assert dead_ball_v2.first_control_forcing(ctrl, dead, [(0, 100)], [55]) == {}
    assert dead_ball_v2.first_control_forcing(ctrl, dead, [(0, 100)], [80]) == {60: 1}


def test_no_first_control_before_the_next_stoppage_or_the_end_forces_nothing() -> None:
    ctrl = np.full(100, NONE, dtype=np.int8)
    ctrl[90] = 0
    dead = np.zeros(100, dtype=bool)
    dead[30:60] = True
    dead[70:80] = True  # the next stoppage begins before any control
    forced = dead_ball_v2.first_control_forcing(ctrl, dead, [(0, 100)])
    assert forced == {80: 0}
    assert dead_ball_v2.first_control_forcing(np.full(100, NONE, np.int8), dead, [(0, 100)]) == {}


N = 4000
HALF = [(100, 3900)]


def _evidence(restarts=()) -> dead_ball.Evidence:
    zeros = np.zeros(N, dtype=bool)
    return dead_ball.Evidence(tuple(restarts), zeros.copy(), zeros.copy(), zeros.copy())


def test_the_union_keeps_the_delivered_stoppages_and_model_only_drops_them() -> None:
    restart = dead_ball.Restart(2000, 1875, "Throw-in", 0)
    ev = _evidence([restart])
    kin = np.zeros(N, dtype=bool)
    kin[3000:3200] = True
    union = dead_ball_v2.dead_union("model", ev, kin, HALF)
    assert union[1875:2000].all() and union[3000:3200].all()
    only = dead_ball_v2.dead_union("model-only", ev, kin, HALF)
    assert not only[1875:2000].any() and only[3000:3200].all()
    with pytest.raises(ValueError, match="unknown variant"):
        dead_ball_v2.dead_union("still", ev, kin, HALF)


def test_the_chain_writes_d_and_first_control_moves_the_restart(monkeypatch) -> None:
    monkeypatch.setattr(engine, "halves", lambda: HALF)
    home = np.full(N, 9.0)
    away = np.full(N, 9.0)
    home[200:210] = 0.5  # home controls early
    away[3300:3310] = 0.5  # away controls only well after the stoppage
    present = np.ones(N, dtype=bool)
    f = engine.Features(home, away, present, np.zeros(N), present.copy())
    kin = np.zeros(N, dtype=bool)
    kin[3000:3200] = True
    plain = dead_ball_v2.chain(f, _evidence(), kin, "model")
    moved = dead_ball_v2.chain(f, _evidence(), kin, "model+first-control")
    assert (plain[3000:3200] == "D").all() and (moved[3000:3200] == "D").all()
    assert (plain[3200:3300] == "H").all()  # carried until away is seen controlling
    assert (moved[3200:3300] == "A").all()  # the stoppage restarted with away's first control
    assert (plain[3300:3900] == "A").all() and (moved[3300:3900] == "A").all()


def test_bench_methods_cover_every_variant() -> None:
    kin = {"rule": np.zeros(N, dtype=bool), "model": np.zeros(N, dtype=bool)}
    assert set(dead_ball_v2.bench_methods(kin)) == set(dead_ball_v2.VARIANTS)


@requires_bundle
def test_the_players_mark_a_plausible_share_of_the_match() -> None:
    """Aggregates only. The DFL matches are 40,7-51,7% dead; the delivered stream alone 12,3%."""
    kin = dead_ball_v2.match_kinematic("model")
    inside = np.zeros(len(kin), dtype=bool)
    for start, stop in engine.halves():
        inside[start:stop] = True
    assert 0.35 < kin[inside].mean() < 0.517
