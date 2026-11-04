"""Lane dead-v3: the onset of a players' stoppage and the restart of an untagged one, pinned on
synthetic frames.

The onset rules are placed by hand on a +/- 1 s p90 series (`known`, `window`), so every way the
walk back can end -- a running field, another stoppage, a tagged restart, an untracked field, the
cap -- is one test. The chain is driven by hand-made distances, as in tests/test_dead_ball_v2.py.
Times are in frames at 25 fps. One test reads the delivered match and skips without the bundle;
it compares labels in memory and pins nothing frame by frame.
"""

from __future__ import annotations

import numpy as np
import pytest
from _bundle import requires_bundle

from tools import dead_ball, dead_ball_v2, dead_ball_v3, engine
from tools.dead_ball_v3 import DEFAULT, Params

FPS = dead_ball_v3.FPS
NONE = engine.NONE


def series(levels: list[tuple[int, float]]) -> tuple[np.ndarray, np.ndarray]:
    """`(known, window)` from `(frames, p90 m/s)` pieces; NaN marks an untracked field."""
    window = np.concatenate([np.full(n, v) for n, v in levels])
    return np.isfinite(window), window


def stoppage(n: int, start: int, stop: int) -> np.ndarray:
    dead = np.zeros(n, dtype=bool)
    dead[start:stop] = True
    return dead


# -- the onset ---------------------------------------------------------------------------------


def test_a_stoppage_begins_after_the_last_frame_the_field_was_seen_running() -> None:
    # Running, then 5 s of slowing (a jog, under onset_mps but above W1's 2 m/s), then still.
    known, window = series([(500, 5.0), (125, 2.8), (500, 1.0)])
    dead = stoppage(1125, 625, 1125)
    out = dead_ball_v3.extend_onsets(dead, known, window)
    assert out[500:].all() and not out[:500].any()


def test_the_end_of_a_stoppage_is_never_moved() -> None:
    known, window = series([(500, 5.0), (125, 2.8), (300, 1.0), (125, 2.8), (500, 5.0)])
    dead = stoppage(1550, 625, 925)
    out = dead_ball_v3.extend_onsets(dead, known, window)
    assert out[924] and not out[925:].any()


def test_a_field_that_never_ran_since_the_previous_stoppage_keeps_both_apart() -> None:
    # Two stoppages with a slow live stretch between them: no onset is seen, nothing merges.
    known, window = series([(300, 1.0), (200, 2.8), (300, 1.0)])
    dead = stoppage(800, 0, 300) | stoppage(800, 500, 800)
    out = dead_ball_v3.extend_onsets(dead, known, window)
    assert np.array_equal(out, dead)


def test_a_stoppage_never_begins_before_a_tagged_restart() -> None:
    known, window = series([(300, 5.0), (300, 2.8), (300, 1.0)])
    dead = stoppage(900, 600, 900)
    assert dead_ball_v3.extend_onsets(dead, known, window)[300:600].all()
    # The ball was put in play at frame 450: the field never ran after it, so no onset is seen.
    blocked = dead_ball_v3.extend_onsets(dead, known, window, barriers=[450])
    assert np.array_equal(blocked, dead)


def test_an_untracked_field_or_the_cap_leaves_the_start_where_it_was() -> None:
    known, window = series([(300, 5.0), (50, np.nan), (300, 2.8), (300, 1.0)])
    dead = stoppage(950, 650, 950)
    assert np.array_equal(dead_ball_v3.extend_onsets(dead, known, window), dead)
    known, window = series([(300, 5.0), (300, 2.8), (300, 1.0)])
    dead = stoppage(900, 600, 900)
    short = Params(onset_cap_s=10.0)  # 250 frames: the run of 300 slow frames is longer
    assert np.array_equal(dead_ball_v3.extend_onsets(dead, known, window, (), short), dead)
    assert dead_ball_v3.extend_onsets(dead, known, window, (), DEFAULT)[300:600].all()


def test_the_edge_of_the_array_is_not_an_onset() -> None:
    known, window = series([(300, 2.8), (300, 1.0)])
    dead = stoppage(600, 300, 600)
    assert np.array_equal(dead_ball_v3.extend_onsets(dead, known, window), dead)


def test_on_a_field_that_slows_down_the_onset_starts_before_w1() -> None:
    # Players at 5 m/s, slowing to a jog for 4 s after the whistle, still for 20 s, then running.
    speeds = np.concatenate([np.full(1000, 5.0), np.full(100, 2.6), np.full(500, 0.3)])
    speeds = np.concatenate([speeds, np.full(1000, 5.0)])
    xy = _field(speeds)
    w1 = dead_ball_v2.kinematic_mask(xy, (), [(0, len(speeds))], "rule")
    onset = dead_ball_v3.kinematic_onset(xy, [(0, len(speeds))])
    ((w1_start, w1_stop),) = dead_ball_v2.runs_of(w1)
    ((start, stop),) = dead_ball_v2.runs_of(onset)
    assert stop == w1_stop  # the end is W1's
    assert w1_start > 1050 and abs(start - 1000) <= FPS  # W1 is late; the onset is the whistle


def _field(speeds_mps: np.ndarray, players: int = 12) -> np.ndarray:
    """Players spread over the pitch, all moving in a straight line along x at exactly `speeds`.

    Unlike test_dead_ball_v2's back-and-forth field, the speed never dips: the onset threshold
    sits between a jog and a run, so the test needs the speeds it states. The speed rules do not
    look at the pitch, so leaving it is harmless.
    """
    travelled = np.concatenate(([0.0], np.cumsum(np.asarray(speeds_mps)[1:]) / FPS))
    xy = np.empty((len(speeds_mps), players, 2))
    xy[..., 0] = np.linspace(20.0, 80.0, players)[None, :] + travelled[:, None]
    xy[..., 1] = np.linspace(10.0, 58.0, players)[None, :]
    return xy


# -- the DFL measures --------------------------------------------------------------------------


def test_edge_offsets_are_positive_when_late_and_bridge_two_true_stoppages() -> None:
    truth = stoppage(1000, 100, 200) | stoppage(1000, 300, 400)
    detected = stoppage(1000, 150, 390)  # 2 s late at the start, 0,4 s early at the end
    starts, ends = dead_ball_v3.edge_offsets(detected, truth)
    assert starts.tolist() == [50 / FPS] and ends.tolist() == [-10 / FPS]
    assert dead_ball_v3.edge_offsets(stoppage(1000, 600, 700), truth)[0].size == 0


def test_frame_rates_count_only_graded_frames() -> None:
    graded = np.ones(10, dtype=bool)
    graded[0] = False
    counts = dead_ball_v3.frame_counts(stoppage(10, 0, 4), stoppage(10, 2, 6), graded)
    assert counts == {"hits": 2, "said": 3, "true": 4, "graded": 9}
    rates = dead_ball_v3.rates(counts)
    assert rates["precision"] == pytest.approx(2 / 3) and rates["recall"] == 0.5


# -- the chain ---------------------------------------------------------------------------------

N = 4000
HALF = [(100, 3900)]


def _evidence(restarts=()) -> dead_ball.Evidence:
    zeros = np.zeros(N, dtype=bool)
    return dead_ball.Evidence(tuple(restarts), zeros.copy(), zeros.copy(), zeros.copy())


def _features(home: np.ndarray, away: np.ndarray) -> engine.Features:
    present = np.ones(N, dtype=bool)
    return engine.Features(home, away, present, np.zeros(N), present.copy())


def test_an_untagged_stoppage_restarts_with_its_first_control_even_a_contested_one(
    monkeypatch,
) -> None:
    monkeypatch.setattr(engine, "halves", lambda: HALF)
    home = np.full(N, 9.0)
    away = np.full(N, 9.0)
    home[200:210] = 0.5  # home controls early
    away[3300:3310], home[3300:3310] = 0.5, 1.0  # away first after the stoppage, home within reach
    kin = stoppage(N, 3000, 3200)
    f = _features(home, away)
    base = dead_ball_v3.chain(f, _evidence(), kin, "engine")
    moved = dead_ball_v3.chain(f, _evidence(), kin, "first-control")
    assert (base[3000:3200] == "D").all() and (moved[3000:3200] == "D").all()
    assert (base[3200:3900] == "H").all()  # the duel rule keeps home
    assert (moved[3200:3900] == "A").all()  # the laws give the restart to the first control


def test_a_tagged_restart_decides_its_own_stoppage(monkeypatch) -> None:
    monkeypatch.setattr(engine, "halves", lambda: HALF)
    home = np.full(N, 9.0)
    away = np.full(N, 9.0)
    home[200:210] = 0.5
    away[3300:3310] = 0.5
    restart = dead_ball.Restart(3200, 3075, "Free Kick", 0)  # home restarts, tagged
    kin = stoppage(N, 3000, 3200)
    out = dead_ball_v3.chain(_features(home, away), _evidence([restart]), kin, "first-control")
    assert (out[3200:3300] == "H").all() and (out[3310:3900] == "A").all()


def test_engine_is_the_delivered_chain_and_unknown_variants_fail(monkeypatch) -> None:
    monkeypatch.setattr(engine, "halves", lambda: HALF)
    home = np.full(N, 9.0)
    away = np.full(N, 9.0)
    home[200:210] = 0.5
    away[3300:3310] = 0.5
    restart = dead_ball.Restart(2000, 1875, "Throw-in", 1)
    ev = _evidence([restart])
    kin = stoppage(N, 3000, 3200)
    f = _features(home, away)
    dead = dead_ball_v2.dead_union("rule", ev, kin, HALF)
    expected = engine.chain(f, engine.DEFAULT, ev.restarts, dead)[2]
    assert np.array_equal(dead_ball_v3.chain(f, ev, kin, "engine"), expected)
    with pytest.raises(ValueError, match="unknown variant"):
        dead_ball_v3.chain(f, ev, kin, "first-uncontested")


def test_every_variant_follows_the_engines_duel_flag(monkeypatch) -> None:
    # A home control contested by an away player at 3300: a duel under DEFAULT, a change under D31.
    monkeypatch.setattr(engine, "halves", lambda: HALF)
    home = np.full(N, 9.0)
    away = np.full(N, 9.0)
    home[200:210] = 0.5
    away[3300:3310], home[3300:3310] = 0.5, 1.0
    ev = _evidence()
    kin = np.zeros(N, dtype=bool)
    f = _features(home, away)
    dead = dead_ball_v2.dead_union("rule", ev, kin, HALF)
    for params in (engine.DEFAULT, engine.D31):
        expected = engine.chain(f, params, ev.restarts, dead)[2]
        assert np.array_equal(dead_ball_v3.chain(f, ev, kin, "engine", params), expected)
    assert dead_ball_v3.chain(f, ev, kin, "engine", engine.DEFAULT)[3305] == "H"
    assert dead_ball_v3.chain(f, ev, kin, "engine", engine.D31)[3305] == "A"


def test_engine_inputs_drop_the_duel_and_the_restarts_when_asked() -> None:
    home = np.full(N, 9.0)
    away = np.full(N, 9.0)
    home[200:210] = 0.5
    f = _features(home, away)
    restart = dead_ball.Restart(2000, 1875, "Throw-in", 1)
    ctrl, switch, forced = engine.inputs(f, engine.DEFAULT, (restart,))
    assert switch is not None and forced == {2000: 1}
    assert np.array_equal(ctrl, engine.control(f))
    _ctrl, switch, forced = engine.inputs(f, engine.D31, None)
    assert switch is None and forced is None


def test_a_stoppage_without_an_uncontested_control_is_counted_apart() -> None:
    first = {10: 0, 20: 1, 30: 0}  # first control after each untagged stoppage
    accepted = {10: 0, 20: 0}  # first uncontested one; none after the stoppage at 30
    assert dead_ball_v3.first_control_vs_accepted(first, accepted) == {
        "first_control_differs_from_first_accepted": 1,
        "first_control_without_uncontested_control": 1,
    }


def test_bench_methods_cover_every_variant() -> None:
    kin = {False: np.zeros(N, dtype=bool), True: np.zeros(N, dtype=bool)}
    assert set(dead_ball_v3.bench_methods(kin)) == set(dead_ball_v3.VARIANTS)


@requires_bundle
def test_the_engine_variant_reproduces_the_delivered_run() -> None:
    from tools import atd, emision

    f = engine.features(atd.load("tactical"), emision.team_slots())
    ev = dead_ball.load_evidence()
    labels = dead_ball_v3.chain(f, ev, dead_ball_v3.kinematic_for("engine"), "engine")
    # The lane is defined on W1's stoppages (DECISIONS 44): its reference is the D36 chain.
    assert np.array_equal(labels, engine.run(engine.D36, detector="rule")[0]["label"].to_numpy())
