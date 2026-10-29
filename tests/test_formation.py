"""Lane F: formation features and the gap fill rule, on synthetic pitches and on the match."""

from __future__ import annotations

import numpy as np
import pytest
from _bundle import requires_bundle

from tools import formation as fm

NONE = fm.NONE
HOME = 0
AWAY = 1
# Ten slots: five per team, enough for every test once MIN_PLAYERS is lowered where needed.
CODES = np.array([0] * 5 + [1] * 5, dtype=np.int8)


def pitch(frames: int, home_x: float, away_x: float, spread: float = 4.0) -> np.ndarray:
    """`(frames, 10, 2)` metres: each team as five players in a line around a fixed x."""
    offsets = np.linspace(-2 * spread, 2 * spread, 5)
    out = np.empty((frames, 10, 2))
    out[:, :5, 0] = home_x + offsets
    out[:, 5:, 0] = away_x + offsets
    out[:, :, 1] = np.tile(np.linspace(10, 58, 5), 2)
    return out


@pytest.fixture(autouse=True)
def five_players_make_a_formation(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(fm, "MIN_PLAYERS", 5)


def column(name: str) -> int:
    return fm.FEATURES.index(name)


# -- attacking direction ------------------------------------------------------------------------


def test_direction_is_read_from_the_data_and_swaps_at_half_time() -> None:
    first = pitch(40, home_x=30, away_x=70)  # home defends x = 0
    second = pitch(40, home_x=70, away_x=30)  # the sides swap
    players = np.concatenate([first, second])
    direction = fm.home_direction(players[:, :, 0], CODES, [(0, 40), (40, 80)])
    assert set(direction[:40]) == {1}
    assert set(direction[40:]) == {-1}


def test_the_same_positions_are_attacking_in_one_half_and_defending_in_the_other() -> None:
    # Home pinned high in its *attacking* half in the first half; the same raw x after the swap is
    # deep in its own half. Raw x would call both "advanced"; the signed coordinate must not.
    players = pitch(60, home_x=80, away_x=60)  # identical raw positions in both halves
    direction = np.array([1] * 30 + [-1] * 30, dtype=np.int8)
    per_team = fm.team_features(players, CODES, [(0, 30), (30, 60)], direction)
    mean_s = per_team[:, HOME, column("mean_s")]
    assert np.allclose(mean_s[:30], 80 - fm.HALFWAY_M)
    assert np.allclose(mean_s[30:], -(80 - fm.HALFWAY_M))
    assert np.all(per_team[:30, HOME, column("opp_half")] == 5)
    assert np.all(per_team[30:, HOME, column("opp_half")] == 0)


def test_the_last_line_excludes_the_goalkeeper_and_the_most_advanced_is_the_highest() -> None:
    players = pitch(5, home_x=40, away_x=70)
    players[:, 0, 0] = 2.0  # home goalkeeper on its line
    per_team = fm.team_features(players, CODES, [(0, 5)], np.ones(5, dtype=np.int8))
    home_x = np.sort(players[0, :5, 0])
    assert np.allclose(per_team[:, HOME, column("deep_s")], home_x[1] - fm.HALFWAY_M)
    assert np.allclose(per_team[:, HOME, column("max_s")], home_x[-1] - fm.HALFWAY_M)
    # Away attacks -x: its most advanced player is its *lowest* x.
    assert np.allclose(per_team[:, AWAY, column("max_s")], fm.HALFWAY_M - players[0, 5:, 0].min())


def test_velocity_points_to_the_opponent_goal_and_never_crosses_the_half() -> None:
    frames = 2 * fm.VELOCITY_LAG + 10
    players = pitch(2 * frames, home_x=40, away_x=70)
    step = 2.0 / fm.FPS  # 2 m/s towards +x for everyone
    players[:, :, 0] += step * np.concatenate([np.arange(frames), np.arange(frames)])[:, None]
    direction = np.array([1] * frames + [-1] * frames, dtype=np.int8)
    per_team = fm.team_features(players, CODES, [(0, frames), (frames, 2 * frames)], direction)
    vel = per_team[:, :, column("vel_s")]
    lag = fm.VELOCITY_LAG
    assert np.all(np.isnan(vel[:lag])) and np.all(np.isnan(vel[frames : frames + lag]))
    assert np.allclose(vel[lag:frames, HOME], 2.0)  # home attacks +x in the first half
    assert np.allclose(vel[lag:frames, AWAY], -2.0)
    assert np.allclose(vel[frames + lag :, HOME], -2.0)  # and -x in the second


def test_a_team_below_the_minimum_has_no_formation(monkeypatch: pytest.MonkeyPatch) -> None:
    lag = fm.VELOCITY_LAG  # the first second of a half has no velocity, so no formation either
    players = pitch(lag + 4, home_x=40, away_x=70)
    players[lag : lag + 2, 0] = np.nan  # four home players on two frames
    per_team = fm.team_features(players, CODES, [(0, lag + 4)], np.ones(lag + 4, dtype=np.int8))
    assert np.all(np.isnan(per_team[lag : lag + 2, HOME]))
    assert np.all(np.isfinite(per_team[lag + 2 :, HOME]))
    diff = fm.differences(per_team)
    assert np.all(np.isnan(diff[: lag + 2])) and np.all(np.isfinite(diff[lag + 2 :]))
    model = fm.Model(np.ones(len(fm.FEATURES)), np.ones(len(fm.FEATURES)))
    assert np.all(fm.predict(model, diff)[: lag + 2] == 0.5)


# -- the model -----------------------------------------------------------------------------------


def test_swapping_the_teams_flips_the_probability_exactly() -> None:
    rng = np.random.default_rng(7)
    players = pitch(200, home_x=40, away_x=65) + rng.normal(0, 3, (200, 10, 2))
    direction = np.ones(200, dtype=np.int8)
    per_team = fm.team_features(players, CODES, [(0, 200)], direction)
    swapped = per_team[:, ::-1, :]
    model = fm.Model(rng.normal(size=len(fm.FEATURES)), np.ones(len(fm.FEATURES)))
    p = fm.predict(model, fm.differences(per_team))
    q = fm.predict(model, fm.differences(swapped))
    assert np.allclose(p + q, 1.0)


def test_fit_is_deterministic_and_learns_a_separable_signal() -> None:
    rng = np.random.default_rng(0)
    y = rng.integers(0, 2, 2000).astype(float)
    x = rng.normal(size=(2000, len(fm.FEATURES)))
    x[:, 0] += np.where(y > 0, 1.5, -1.5)
    x[5, 3] = np.nan  # an incomplete row is dropped, not fatal
    a, b = fm.fit(x, y), fm.fit(x, y)
    assert np.array_equal(a.weights, b.weights)
    assert a.weights[0] > 0
    assert np.mean((fm.predict(a, x) > 0.5) == (y > 0.5)) > 0.9


def test_smoothing_never_mixes_two_runs() -> None:
    p = np.concatenate([np.zeros(10), np.ones(10)])
    out = fm.smooth(p, [(0, 10), (10, 20)], window=5)
    assert np.array_equal(out, p)


# -- the fill rule -------------------------------------------------------------------------------


def scenario(n: int = 100, gap: tuple[int, int] = (20, 80)) -> tuple[np.ndarray, ...]:
    """Home controls before a ball gap; the engine carries home through it."""
    present = np.ones(n, dtype=bool)
    present[gap[0] : gap[1]] = False
    ctrl = np.full(n, NONE, dtype=np.int8)
    ctrl[5:15] = HOME
    state = np.full(n, NONE, dtype=np.int8)
    state[5:] = HOME
    return present, ctrl, state


def fill(state, p, present, ctrl=None, **kw):
    kw = {"min_gap": 30, "threshold": 0.8, "sustain": 10, "window": 1, **kw}
    return fm.fill_gaps(state, p, present, [(0, len(state))], ctrl=ctrl, **kw)


def test_strong_evidence_switches_the_gap_from_where_it_began() -> None:
    present, ctrl, state = scenario()
    p = np.full(100, 0.5)
    p[40:80] = 0.05  # away shape from frame 40
    out = fill(state, p, present)
    assert np.all(out[:40] == state[:40])
    assert np.all(out[40:80] == AWAY)  # dated to the first sustained frame, not the tenth
    assert np.all(out[80:] == HOME)  # without ctrl the change stays inside the gap


def test_the_new_state_is_carried_to_the_next_control_and_no_further() -> None:
    present, ctrl, state = scenario()
    ctrl[90:] = HOME  # home controls again at 90
    p = np.full(100, 0.5)
    p[40:80] = 0.05
    out = fill(state, p, present, ctrl=ctrl)
    assert np.all(out[40:90] == AWAY)
    assert np.all(out[90:] == state[90:])
    assert np.all(out[ctrl != NONE] == state[ctrl != NONE])


def test_weak_brief_or_short_gap_evidence_changes_nothing() -> None:
    present, ctrl, state = scenario()
    weak = np.full(100, 0.5)
    weak[20:80] = 0.25  # P(away) 0.75 < 0.8
    assert np.array_equal(fill(state, weak, present, ctrl=ctrl), state)
    brief = np.full(100, 0.5)
    brief[40:49] = 0.0  # 9 frames < sustain 10
    assert np.array_equal(fill(state, brief, present, ctrl=ctrl), state)
    strong = np.full(100, 0.0)
    assert np.array_equal(fill(state, strong, present, ctrl=ctrl, min_gap=61), state)


def test_evidence_for_the_carried_team_changes_nothing() -> None:
    present, ctrl, state = scenario()
    assert np.array_equal(fill(state, np.ones(100), present, ctrl=ctrl), state)


def test_a_long_gap_can_switch_twice() -> None:
    present, ctrl, state = scenario()
    p = np.full(100, 0.5)
    p[30:50] = 0.0
    p[60:80] = 1.0
    out = fill(state, p, present, ctrl=ctrl)
    assert np.all(out[20:30] == HOME)
    assert np.all(out[30:60] == AWAY)
    assert np.all(out[60:] == HOME)


def test_a_gap_with_no_state_yet_is_left_to_the_engine() -> None:
    present, ctrl, state = scenario(gap=(0, 60))
    state[:] = NONE
    state[60:] = HOME
    assert np.array_equal(fill(state, np.zeros(100), present), state)


def test_threshold_must_be_a_majority() -> None:
    present, ctrl, state = scenario()
    with pytest.raises(ValueError, match="threshold"):
        fill(state, np.zeros(100), present, threshold=0.5)


def test_the_variants_are_the_four_pre_registered_ones() -> None:
    assert {k: (v.min_gap, v.threshold) for k, v in fm.VARIANTS.items()} == {
        "V1": (125, 0.80),
        "V2": (125, 0.90),
        "V3": (500, 0.80),
        "V4": (500, 0.90),
    }


# -- the delivered match -------------------------------------------------------------------------


@requires_bundle
def test_on_the_match_home_attacks_opposite_ways_in_the_two_halves() -> None:
    from tools import atd, emision, engine

    tracking = atd.load("tactical")
    players_x = tracking.players_array[:, :, 0] * fm.PITCH_M[0]
    direction = fm.home_direction(players_x, emision.team_slots().codes, engine.halves())
    (a1, _), (a2, _) = engine.halves()
    assert direction[a1] == -direction[a2] != 0
