"""Lane m-whether: the corrected matching, the anatomy's kinds, the degraded ball.

Synthetic arrays everywhere except the tests marked for the Metrica sample games, which skip when
those files are absent."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import pytest

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
