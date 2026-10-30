"""Lane m-whether: the corrected matching, the anatomy's kinds, the degraded ball.

Synthetic arrays everywhere except the tests marked for the Metrica sample games, which skip when
those files are absent."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from _bundle import requires_bundle

from tools import change_dating as cd
from tools import change_whether as cw
from tools import dead_ball, engine
from tools import metrica_open as mo

N = engine.NONE
H, A = 0, 1


def _features(home, away, speed, present=None, in_pitch=None) -> engine.Features:
    n = len(home)
    present = np.ones(n, bool) if present is None else np.asarray(present, bool)
    in_pitch = present.copy() if in_pitch is None else np.asarray(in_pitch, bool)
    return engine.Features(
        np.array(home, float), np.array(away, float), present, np.array(speed, float), in_pitch
    )


def _chain(state, ctrl, switch=None, forced=None, dead=None) -> cd.Chain:
    state = np.array(state, dtype=np.int8)
    ctrl = np.array(ctrl, dtype=np.int8)
    switch = ctrl.copy() if switch is None else np.array(switch, dtype=np.int8)
    dead = np.zeros(len(state), bool) if dead is None else np.array(dead, bool)
    return cd.Chain(ctrl, switch, forced or {}, state, dead)


def _truth(changes, open_frames, team, dead=None) -> cw.Truth:
    team = np.array(team, dtype=np.int8)
    dead = np.zeros(len(team), bool) if dead is None else np.array(dead, bool)
    return cw.Truth(tuple(changes), frozenset(open_frames), team, dead)


# -- the corrected instrument ------------------------------------------------------------------


def test_a_chain_change_at_a_set_piece_is_matched_not_spurious() -> None:
    # Truth: an open-play change at 100 and a set-piece change at 400 (not open play).
    truth = _truth([(100, A), (400, H)], {100}, [H] * 600)
    pred = [(102, A), (405, H), (550, A)]
    r = cw.fair(truth, pred)
    assert (r.chain, r.matched, r.missed, r.spurious) == (3, 2, (), ((550, A),))
    # Round 5 matched open play only: the set-piece change at 405 was counted as spurious.
    old = cd.dating([(100, A)], pred)
    assert old["extra"] == 2
    assert r.lag["n"] == 1 and r.lag["median"] == pytest.approx(2 / 25)


def test_an_open_play_change_without_partner_is_missed_and_a_set_piece_one_is_not() -> None:
    truth = _truth([(100, A), (400, H)], {100}, [H] * 600)
    r = cw.fair(truth, [])
    assert r.missed == ((100, A),) and r.spurious == ()


# -- anatomy -----------------------------------------------------------------------------------


def test_the_truth_spell_ends_at_another_team_a_stoppage_or_the_half() -> None:
    team = [H] * 5 + [A] * 5 + [H] * 5 + [A] * 5
    dead = np.zeros(20, bool)
    dead[17] = True
    truth = _truth([], set(), team, dead)
    runs = [(0, 20)]
    assert cw.spell_end(truth, 5, A, runs) == 10
    assert cw.spell_end(truth, 15, A, runs) == 17
    assert cw.spell_end(truth, 18, A, [(0, 19)]) == 19  # the half's end


def _window_chain(ctrl, switch, state=0, n=200):
    return _chain([state] * n, ctrl, switch)


def test_miss_kinds_follow_their_order() -> None:
    n, t = 200, 50
    far = [9.0] * n
    base = _features(far, far, [1.0] * n)
    none = [N] * n
    # The chain already has the new team at the truth's frame.
    assert cw.miss_kind(_chain([A] * n, none), base, t, A, 150) == "ya del nuevo equipo"
    # A control of the new team, vetoed by the duel rule (switch NONE).
    ctrl = list(none)
    ctrl[60] = A
    assert cw.miss_kind(_window_chain(ctrl, none), base, t, A, 150) == "veto del duelo"
    # Too late to count: beyond 5 s after the truth's frame the window is closed.
    ctrl = list(none)
    ctrl[t + cw.TOLERANCE + 1] = A
    assert cw.miss_kind(_window_chain(ctrl, none), base, t, A, 199) == "lejos"
    # The new team nearest within reach of a fast ball: no control at all.
    away = list(far)
    away[70] = 0.5
    fast = _features(far, away, [12.0] * n)
    assert cw.miss_kind(_window_chain(none, none), fast, t, A, 150) == "toque rápido"
    # Within reach but the old team as close: a contest, not a touch.
    home = list(far)
    home[70] = 0.5
    tie = _features(home, away, [12.0] * n)
    assert cw.miss_kind(_window_chain(none, none), tie, t, A, 150) == "rival igual de cerca"
    # No ball on most of the window.
    present = np.ones(n, bool)
    present[t:150] = False
    gone = _features(far, far, [1.0] * n, present)
    assert cw.miss_kind(_window_chain(none, none), gone, t, A, 150) == "sin balón"
    assert cw.miss_kind(_window_chain(none, none), base, t, A, 150) == "lejos"


def test_extra_kinds_follow_their_order() -> None:
    n = 300
    truth = _truth([], set(), [H] * 100 + [A] * 100 + [H] * 100)
    chain = _chain([H] * n, [N] * n, forced={20: A})
    assert cw.extra_kind(chain, truth, 20, A, None) == "reanudación forzada"
    dead_truth = _truth(
        [], set(), [H] * n, np.r_[np.zeros(30, bool), np.ones(10, bool), np.zeros(n - 40, bool)]
    )
    assert cw.extra_kind(chain, dead_truth, 35, A, None) == "balón muerto en la verdad"
    assert cw.extra_kind(chain, truth, 150, A, None) == "corrección tardía"
    assert cw.extra_kind(chain, truth, 30, A, 30 + 2 * 25) == "ida y vuelta"
    assert cw.extra_kind(chain, truth, 30, A, 30 + 4 * 25) == "control del rival"


def test_a_flip_flop_goes_back_to_the_team_before_it_quickly_and_inside_the_half() -> None:
    state = np.array([H] * 10 + [A] * 10 + [H] * 100 + [A] * 100, dtype=np.int8)
    pred = cd.state_changes(state, [(0, 220)])
    assert pred == [(10, A), (20, H), (120, A)]
    back = cw._returns(pred, [(0, 220)], state)
    assert back == {10: 20, 20: 120, 120: None}
    assert cw.flip_flops(pred, [(0, 220)], {}, state) == [10]
    assert cw.flip_flops(pred, [(0, 220)], {10: A}, state) == []  # a forced change is a restart
    # The return across a half edge is not a flip-flop: the next change is another half's.
    assert cw._returns([(10, A), (25, H)], [(0, 20), (20, 40)], state) == {10: None, 25: None}


def test_stretches_and_the_vetoed_and_fast_frames() -> None:
    assert cw.stretches(np.array([0, 1, 1, 0, 1, 1, 1, 1], bool), [(0, 5), (5, 8)]) == [
        (1, 3),
        (4, 5),
        (5, 8),
    ]
    #            0    1    2    3    4    5
    state = [H, H, H, A, A, N]
    ctrl = [A, A, H, A, H, A]
    switch = [N, A, H, A, N, A]
    chain = _chain(state, ctrl, switch)
    assert cw.vetoed(chain).tolist() == [True, False, False, False, True, False]
    home = [3.0, 0.4, 3.0, 9.0, 0.3, 9.0]
    away = [0.5, 3.0, 9.0, 0.5, 3.0, 9.0]
    f = _features(home, away, [8.0, 8.0, 8.0, 2.0, 8.0, 8.0])
    # 0: away nearest, home beyond reach, fast -> a fast touch by the rival; 1: home touches its own
    # ball; 3: the away team owns it; 4: home (the rival of A) nearest, away beyond reach, fast.
    assert cw.fast_touches(chain, f).tolist() == [True, False, False, False, True, False]


def test_the_structure_counts_vetoes_and_what_an_independent_judge_says() -> None:
    n = 100
    state = [H] * 50 + [A] * 50
    ctrl = [N] * n
    for i in (10, 11, 12):
        ctrl[i] = A  # a 3-frame vetoed stretch, then the chain changes at 50
    switch = [N] * n
    chain = _chain(state, ctrl, switch)
    f = _features([9.0] * n, [9.0] * n, [1.0] * n)
    owner = np.array([A] * n, dtype=np.int8)
    s = cw.structure(chain, f, [(0, n)], owner)
    assert s["changes"] == 1 and s["veto"] == 1 and s["veto_per_natural"] == 1.0
    assert s["veto_s"][1] == pytest.approx(3 / 25)
    assert s["veto_then_switch"] == 1.0  # it changes at 50, within 5 s of the stretch
    assert s["veto_owner_rival"] == 1.0 and s["owner_state"] == 0.5


def test_the_public_truth_skips_d_and_marks_restart_changes_as_not_open_play() -> None:
    labels = np.array(list("HHHAAADDHHHXAA"), dtype=object)
    truth = cw.public_truth(labels, [(0, 14)])
    assert truth.changes == ((3, A), (8, H), (12, A))
    assert truth.open_frames == frozenset({3, 12})  # a D lies between A at 5 and H at 8


def test_the_anatomy_ties_misses_and_extras_together() -> None:
    n = 400
    runs = [(0, n)]
    team = [H] * 100 + [A] * 150 + [H] * 150
    truth = _truth([(100, A), (250, H)], {100, 250}, team)
    # The chain sees the change at 100 one frame late, misses the one at 250, and invents one.
    state = [H] * 101 + [A] * 299
    ctrl = [N] * n
    ctrl[101] = A
    chain = _chain(state, ctrl)
    f = _features([9.0] * n, [9.0] * n, [1.0] * n)
    a = cw.anatomy(truth, chain, f, runs, chain)
    assert a.fair.missed == ((250, H),) and a.fair.spurious == ()
    assert a.misses["ya del nuevo equipo"] == 0 and sum(a.misses.values()) == 1
    assert a.no_duel_fixes[cw.miss_kind(chain, f, 250, H, n)] == 0


# -- the degraded ball -------------------------------------------------------------------------


def test_smooth_noise_is_deterministic_scaled_and_slow() -> None:
    a = cw.smooth_noise(20000, 0.8, 25, seed=7)
    b = cw.smooth_noise(20000, 0.8, 25, seed=7)
    assert np.array_equal(a, b) and a.shape == (20000, 2)
    assert a.std(axis=0) == pytest.approx([0.8, 0.8], rel=0.15)
    # Smoothed over a second: the speed it adds is a fraction of a metre per second.
    speed = np.linalg.norm(np.diff(a, axis=0), axis=1) * 25
    assert np.median(speed) < 1.0
    with pytest.raises(ValueError, match="smooth"):
        cw.smooth_noise(10, 1.0, 0, seed=0)


def _tracking_csv(path: Path, team: str, ball, players) -> Path:
    head = [
        f",,,{team},,{team},,,",
        ",,,1,,2,,,",
        "Period,Frame,Time [s],Player1,,Player2,,Ball,",
    ]
    rows = []
    for i, ((bx, by), (p1, p2)) in enumerate(zip(ball, players)):
        period = 1 if i < len(ball) // 2 else 2
        rows.append(
            f"{period},{i + 1},{(i + 1) * 0.04:.2f},{p1[0]},{p1[1]},{p2[0]},{p2[1]},{bx},{by}"
        )
    path.write_text("\n".join(head + rows) + "\n", encoding="utf-8")
    return path


def _game(tmp_path) -> mo.Game:
    rng = np.random.default_rng(0)
    n = 40
    ball = [(float(x), float(y)) for x, y in rng.uniform(0.1, 0.9, (n, 2))]
    ball[3] = (float("nan"), float("nan"))
    home_p = [((0.2, 0.3), (0.6, 0.5))] * n
    away_p = [((0.7, 0.7), (0.4, 0.2))] * n
    home = mo.read_tracking(_tracking_csv(tmp_path / "h.csv", "Home", ball, home_p))
    away = mo.read_tracking(_tracking_csv(tmp_path / "a.csv", "Away", ball, away_p))
    events = pd.DataFrame(
        {
            "team": [H],
            "type": ["PASS"],
            "subtype": [""],
            "period": [1],
            "start": [0],
            "end": [1],
            "player": ["Player1"],
        }
    )
    return mo.build("g1", home, away, events)


def test_features_from_reproduces_the_loaders_features_and_finds_the_home_slots(tmp_path) -> None:
    game = _game(tmp_path)
    assert cw.home_slots(game) == 2
    f = cw.features_from(game.players_m, 2, game.ball_m)
    for name in ("home_m", "away_m", "speed_mps"):
        assert np.allclose(getattr(f, name), getattr(game.features, name), equal_nan=True)
    assert np.array_equal(f.present, game.features.present)
    assert np.array_equal(f.in_pitch, game.features.in_pitch)


def test_the_degraded_game_moves_the_ball_then_deletes_it_where_ours_was_not_seen(tmp_path) -> None:
    game = _game(tmp_path)
    same, ev = cw.degraded(game, None, 0.0)
    assert same is game.features and np.array_equal(ev.out, game.evidence.out)
    noisy, ev = cw.degraded(game, None, 1.0)
    again, _ = cw.degraded(game, None, 1.0)
    assert np.allclose(noisy.home_m, again.home_m, equal_nan=True)  # a fixed seed per game
    assert not np.allclose(noisy.home_m, game.features.home_m, equal_nan=True)
    assert np.array_equal(ev.out, noisy.present & ~noisy.in_pitch)
    donors = [np.array([True, False]), np.array([False, True, True])]
    both, ev2 = cw.degraded(game, donors, 1.0)
    keep = cd.keep_mask(list(game.runs), 40, donors)
    assert np.array_equal(both.present, noisy.present & keep)
    assert np.isnan(both.home_m[~keep]).all()
    assert not ev2.out[~keep].any()


def test_the_slow_ball_distance_reads_slow_live_balls_in_the_pitch_only() -> None:
    f = _features([0.5, 2.0, 0.1, 9.0], [1.0, 3.0, 9.0, 0.2], [1.0, 1.0, 9.0, 1.0])
    live = np.array([True, True, True, False])
    assert cw.slow_ball_distance(f, live) == pytest.approx(np.median([0.5, 2.0]))


# -- the sample games --------------------------------------------------------------------------

METRICA = pytest.mark.skipif(
    not (mo.data_dir() / "g1" / "RawEventsData.csv").exists(), reason="Metrica sample games absent"
)


@METRICA
def test_on_g1_every_restart_forced_change_round_5_called_spurious_is_explained() -> None:
    game = mo.load("g1")
    runs, chain, no_duel = cw._metrica_inputs(game)
    a = cw.anatomy(cw.metrica_truth(game), chain, game.features, runs, no_duel)
    assert a.round5["extra"] == sum(a.round5_extra.values())
    assert len(a.fair.spurious) < a.round5["extra"]
    assert sum(a.misses.values()) == len(a.fair.missed)
    assert sum(a.extras.values()) == len(a.fair.spurious)


@METRICA
def test_the_noise_sigma_is_the_one_fitted_on_g1_against_bar_aths_target() -> None:
    from _bundle import missing_reason

    if missing_reason() is not None:
        pytest.skip(missing_reason())
    from tools import bench

    f, ev, _gt, _cut = bench.load()
    live = cw._live(len(f.present), engine.halves(), engine.delivered_dead(ev))
    sigma, _tried = cw.fit_sigma(mo.load("g1"), cw.slow_ball_distance(f, live))
    assert sigma == cw.NOISE_SIGMA_M


def test_the_dead_ball_on_a_degraded_game_is_the_delivered_union(tmp_path) -> None:
    game = _game(tmp_path)
    expected = cd.metrica_dead(game)
    assert np.array_equal(cw.metrica_dead_on(game, game.evidence), expected)
    ev = dead_ball.Evidence((), np.zeros(40, bool), np.ones(40, bool), np.zeros(40, bool))
    assert cw.metrica_dead_on(game, ev).shape == (40,)


# -- the variants (pre-registered) -------------------------------------------------------------


def test_a_contested_control_kept_long_enough_becomes_a_switch() -> None:
    ctrl = np.array([N, A, A, A, N, A, A, N, H, H, H], dtype=np.int8)
    switch = np.full(11, N, dtype=np.int8)
    out = cw.sustained(ctrl, switch, [(0, 11)], 3)
    assert out.tolist() == [N, A, A, A, N, N, N, N, H, H, H]
    assert cw.sustained(ctrl, switch, [(0, 2), (2, 11)], 3).tolist()[1:4] == [N, N, N]  # halves
    with pytest.raises(ValueError, match="frames"):
        cw.sustained(ctrl, switch, [(0, 11)], 0)


def test_a_relay_is_two_touches_of_one_team_with_nobody_between() -> None:
    far = 9.0
    #        0    1    2    3    4    5    6    7    8    9
    home = [far, far, far, far, far, far, 0.5, far, far, far]
    away = [far, 0.5, 0.6, far, 0.4, far, far, far, 0.3, far]
    f = _features(home, away, [12.0] * 10)
    ctrl = np.full(10, N, dtype=np.int8)
    switch = ctrl.copy()
    c2, s2 = cw.relayed(ctrl, switch, f, [(0, 10)], frames=3)
    # Away touches at 1-2, again at 4 (2 frames later): accepted at 1. Its touch at 4 is followed
    # by a home touch at 6, and home's by away's at 8: neither is confirmed.
    assert np.flatnonzero(s2 != N).tolist() == [1] and s2[1] == A and c2[1] == A
    # The gap is counted from the end of the first touch (3) to the start of the next (4).
    assert cw.relayed(ctrl, switch, f, [(0, 10)], frames=1)[1][1] == A
    assert (cw.relayed(ctrl, switch, f, [(0, 10)], frames=0)[1] == N).all()
    # Contested: home within reach on every frame of the away touch, so nothing is accepted.
    home_close = [far, 1.0, 1.2, far, far, far, 0.5, far, far, far]
    f2 = _features(home_close, away, [12.0] * 10)
    assert (cw.relayed(ctrl, switch, f2, [(0, 10)], frames=3)[1] == N).all()
    # A half edge between the two touches breaks the relay.
    assert (cw.relayed(ctrl, switch, f, [(0, 4), (4, 10)], frames=3)[1] == N).all()


def test_settle_removes_a_short_return_and_nothing_else() -> None:
    state = np.array([H] * 10 + [A] * 3 + [H] * 20 + [A] * 30, dtype=np.int8)
    runs = [(0, 63)]
    dead = np.zeros(63, bool)
    out = cw.settled(state, runs, {}, dead, frames=5)
    assert out.tolist() == [H] * 33 + [A] * 30  # the 3-frame A spell went back to H
    assert cw.settled(state, runs, {}, dead, frames=3).tolist() == state.tolist()  # 3 is not < 3
    assert cw.settled(state, runs, {10: A}, dead, frames=5).tolist() == state.tolist()  # forced
    assert cw.settled(state, runs, {13: H}, dead, frames=5).tolist() == state.tolist()
    stopped = dead.copy()
    stopped[11] = True
    assert cw.settled(state, runs, {}, stopped, frames=5).tolist() == state.tolist()
    assert cw.settled(state, [(0, 12), (12, 63)], {}, dead, frames=5).tolist() == state.tolist()


def test_settle_never_makes_a_new_pair_out_of_a_removed_one() -> None:
    state = np.array([H] * 10 + [A] * 2 + [H] * 2 + [A] * 20, dtype=np.int8)
    out = cw.settled(state, [(0, 34)], {}, np.zeros(34, bool), frames=5)
    # H->A at 10 and A->H at 12 go; the H->A at 14 stays a change.
    assert cd.state_changes(out, [(0, 34)]) == [(14, A)]


def _random_inputs(seed: int):
    rng = np.random.default_rng(seed)
    n = 3000
    f = engine.Features(
        rng.uniform(0, 3, n),
        rng.uniform(0, 3, n),
        np.ones(n, bool),
        rng.uniform(0, 12, n),
        np.ones(n, bool),
    )
    restarts = (dead_ball.Restart(2000, 1875, "Throw-in", H),)
    ev = dead_ball.Evidence(restarts, np.zeros(n, bool), np.ones(n, bool), np.zeros(n, bool))
    dead = np.zeros(n, bool)
    dead[1000:1100] = True
    return f, ev, [(0, 1500), (1500, 3000)], dead


@pytest.mark.parametrize("seed", [0, 1, 2])
def test_the_reference_is_the_delivered_chain_and_neutral_constants_change_nothing(seed) -> None:
    f, ev, runs, dead = _random_inputs(seed)
    ref = cw.variant_chain("engine", f, ev, runs, dead)
    expected = cd.delivered(f, ev, runs, dead)
    assert np.array_equal(ref.state, expected.state) and ref.forced == expected.forced
    neutral = {"persist": 10_000.0, "settle": 0.0, "relay": 0.0}
    for name in cw.VARIANTS:
        chain = cw.variant_chain(name, f, ev, runs, dead, neutral)
        assert np.array_equal(chain.state, ref.state), name


@pytest.mark.parametrize("seed", [0, 1, 2])
def test_no_variant_moves_a_d_frame_and_settle_only_removes_changes(seed) -> None:
    f, ev, runs, dead = _random_inputs(seed)
    ref = cw.variant_chain("engine", f, ev, runs, dead)
    base = cd.state_changes(ref.state, runs)
    for name in cw.VARIANTS:
        chain = cw.variant_chain(name, f, ev, runs, dead)
        labels = cd.finish(chain.state, chain.dead)
        assert ((labels == "D") == dead).all(), name
    settled = cw.variant_chain("settle", f, ev, runs, dead)
    assert set(cd.state_changes(settled.state, runs)) <= set(base)
    assert ((settled.state == N) == (ref.state == N)).all()


def test_a_kept_duel_cancels_a_restart_and_a_short_one_does_not() -> None:
    n = 400
    away = np.full(n, 9.0)
    away[120:150] = 0.5  # a contested away control, 30 frames, inside the restart's window
    home = np.full(n, 9.0)
    home[120:150] = 1.0
    home[10] = 0.3  # home has the ball before
    f = _features(list(home), list(away), [1.0] * n)
    restarts = (dead_ball.Restart(200, 75, "Throw-in", H),)
    ev = dead_ball.Evidence(restarts, np.zeros(n, bool), np.ones(n, bool), np.zeros(n, bool))
    dead = np.zeros(n, bool)
    ref = cw.variant_chain("engine", f, ev, [(0, n)], dead)
    assert ref.forced == {200: H}  # the duel inside the window does not cancel it (DECISIONS 35)
    held = cw.variant_chain("persist", f, ev, [(0, n)], dead, {"persist": 1.0})
    assert held.forced == {} and held.state[130] == A  # kept 1.2 s: a won duel, it cancels it
    brief = cw.variant_chain("persist", f, ev, [(0, n)], dead, {"persist": 2.0})
    assert brief.forced == {200: H} and np.array_equal(brief.state, ref.state)


def test_an_unknown_or_repeated_variant_is_refused() -> None:
    f, ev, runs, dead = _random_inputs(0)
    for name in ("touch", "persist+persist", "relay+"):
        with pytest.raises(ValueError, match="unknown variant"):
            cw.variant_chain(name, f, ev, runs, dead)


def test_the_constant_rule_takes_the_fewest_errors_then_the_most_conservative_value() -> None:
    assert cw.choose({0.2: 10, 0.4: 8, 0.6: 8}, "persist") == 0.6
    assert cw.choose({0.5: 9, 1.0: 9, 2.0: 12}, "settle") == 0.5
    assert cw.choose({0.5: 9, 1.0: 7, 3.0: 7}, "relay") == 1.0


def test_the_selection_follows_the_prior_order_never_the_numbers() -> None:
    ok, ko = cw.Gate("g", True, ""), cw.Gate("g", False, "")
    passed = {"persist": [ko], "settle": [ok], "relay": [ok], "relay+settle": [ok]}
    assert cw.select(passed) == "settle"
    assert cw.select({n: [ko] for n in cw.VARIANTS}) is None
    assert cw.PRIOR_ORDER == ("persist", "settle", "relay", "relay+settle")


def _scored(errors: int, f1: float) -> cw.Scored:
    fair = cw.Fair(0, 0, tuple((i, 0) for i in range(errors)), (), (), cd.lag_stats([]))
    return cw.Scored(fair, f1)


def test_the_gates_need_both_balls_on_g2_and_every_bar_ath_condition() -> None:
    metrica = {
        "g2": {
            "limpio": {"engine": _scored(10, 0.5), "x": _scored(9, 0.51)},
            "degradado": {"engine": _scored(20, 0.4), "x": _scored(19, 0.40)},
        }
    }
    ref = {
        "rate": 3.6,
        "block_ratio": (1.0, 1.0),
        "st": 0.77,
        "max_block_dead": 0.6,
        "delta": 0.0,
        "wins_a": 0,
        "wins_b": 0,
        "bench_mean": 0.43,
        "bench_low": 0.36,
    }
    bar = {"engine": ref, "x": dict(ref, rate=4.0)}
    g = {x.name: x.passed for x in cw.gates(metrica, bar, "x")}
    assert g["Metrica g2 limpio"] and not g["Metrica g2 degradado"]  # a spellF1 tie fails
    assert not g["BAR-ATH sin GT"]  # 4,0 pos/min is outside 3,4 ± 0,5
    assert g["slice público (pareado)"] and g["banco"]
    bar["x"] = dict(ref, block_ratio=(0.5, 1.2))  # one block halved
    assert not {x.name: x.passed for x in cw.gates(metrica, bar, "x")}["BAR-ATH sin GT"]
    bar["x"] = dict(ref, st=0.759)  # more than one point of Smart Tagging lost
    assert not {x.name: x.passed for x in cw.gates(metrica, bar, "x")}["BAR-ATH sin GT"]
    bar["x"] = dict(ref, wins_a=1, wins_b=0)
    assert not {x.name: x.passed for x in cw.gates(metrica, bar, "x")}["slice público (pareado)"]


@requires_bundle
def test_the_reference_variant_is_the_delivered_file_byte_for_byte() -> None:
    import hashlib

    from tools import bench

    f, ev, _gt, _cut = bench.load()
    labels = cw.METHODS["engine"](f, ev)
    table = pd.DataFrame({"frame": np.arange(len(labels)), "label": labels})
    csv = table.to_csv(index=False, lineterminator="\n")
    assert hashlib.sha256(csv.encode()).hexdigest().startswith("72c98ed4bb4a")  # DECISIONS 36


# -- review of PR #60 --------------------------------------------------------------------------


def test_one_partner_credits_one_truth_change_even_on_a_shared_frame() -> None:
    # Two open-play truth changes on frame 100 (events can share a frame) and one chain change:
    # one of them is matched, the other is still a miss.
    truth = _truth([(100, A), (100, A)], {100}, [H] * 400)
    r = cw.fair(truth, [(102, A)])
    assert (r.matched, len(r.missed), r.spurious) == (1, 1, ())


def test_then_switch_looks_after_the_stretch_and_stays_in_its_half() -> None:
    n = 400
    state = [H] * n
    state[150:200] = [A] * 50  # the rival has it 3 s after the stretch [100, 110)...
    late = [H] * n
    late[205:] = [A] * (n - 205)  # ...or only in the next half
    ctrl = [cw.NONE] * n
    assert cw._then_switch(_chain(state, ctrl), [(100, 110)], [(0, n)]) == 1.0
    assert cw._then_switch(_chain(late, ctrl), [(100, 110)], [(0, 200), (205, n)]) == 0.0
    # A rival spell during the stretch itself is not "after" it.
    during = [H] * n
    during[102:105] = [A] * 3
    assert cw._then_switch(_chain(during, ctrl), [(100, 110)], [(0, n)]) == 0.0
