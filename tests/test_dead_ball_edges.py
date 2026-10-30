"""Lane d-edges: the end of a stoppage, pinned on synthetic frames.

The kick detector, the dating window, the cut of a players' stoppage at a tagged restart and the
synthetic DFL tags are each placed by hand. The chain is driven by hand-made distances, as in
tests/test_dead_ball_v3.py. Times are in frames at 25 fps. One test reads the delivered match and
skips without the bundle; it compares labels in memory and pins nothing frame by frame.
"""

from __future__ import annotations

import numpy as np
import pytest
from _bundle import requires_bundle

from tools import dead_ball, dead_ball_edges, dead_ball_v2, engine
from tools.dead_ball_edges import Params

FPS = dead_ball_edges.FPS
N = 4000
HALF = [(0, N)]


def stoppage(n: int, start: int, stop: int) -> np.ndarray:
    dead = np.zeros(n, dtype=bool)
    dead[start:stop] = True
    return dead


def _evidence(restarts=(), out: np.ndarray | None = None) -> dead_ball.Evidence:
    zeros = np.zeros(N, dtype=bool)
    out = zeros.copy() if out is None else out
    return dead_ball.Evidence(tuple(restarts), out, zeros.copy(), zeros.copy())


def _features(home, away, speed=None, in_pitch=None) -> engine.Features:
    present = np.ones(N, dtype=bool)
    speed = np.zeros(N) if speed is None else speed
    in_pitch = present.copy() if in_pitch is None else in_pitch
    return engine.Features(home, away, present, speed, in_pitch)


# -- the kick ----------------------------------------------------------------------------------


def test_a_kick_is_a_fast_ball_seen_inside_the_pitch() -> None:
    speed = np.array([np.nan, 12.0, 12.0, 9.9, 10.0])
    in_pitch = np.array([True, True, False, True, True])
    f = engine.Features(np.zeros(5), np.zeros(5), np.ones(5, bool), speed, in_pitch)
    # Unknown speed fails closed; out of the pitch is not a restart yet; 9,9 m/s is a dribble.
    assert dead_ball_edges.kicked(f).tolist() == [False, True, False, False, True]


def test_a_restart_is_dated_at_the_first_kick_of_a_window_centred_on_the_estimate() -> None:
    r = dead_ball.Restart(1125, 1000, "Throw-in", 0)  # tag at 1000, estimate +5 s
    kick = np.zeros(N, dtype=bool)
    kick[[1160, 1200]] = True  # a kick 1 s after the estimate, then a pass
    (dated,) = dead_ball_edges.kick_restarts([r], kick, HALF)
    assert dated.frame == 1160
    assert (dated.tag_start, dated.team, dated.kind) == (1000, 0, "Throw-in")
    early = np.zeros(N, dtype=bool)
    early[1050] = True  # the estimate is late: the kick came 3 s after the tag
    assert dead_ball_edges.kick_restarts([r], early, HALF)[0].frame == 1050


def test_no_kick_in_the_window_keeps_the_estimate() -> None:
    r = dead_ball.Restart(1125, 1000, "Corner Kick", 1)
    kick = np.zeros(N, dtype=bool)
    kick[[999, 1250]] = True  # before the tag, and exactly at tag + 2 x offset (excluded)
    assert dead_ball_edges.kick_restarts([r], kick, HALF)[0].frame == 1125


def test_one_kick_never_dates_two_restarts_and_the_window_stays_in_its_half() -> None:
    first = dead_ball.Restart(1125, 1000, "Throw-in", 0)
    second = dead_ball.Restart(1150, 1025, "Throw-in", 1)  # a retaken throw, tags overlapping
    kick = np.zeros(N, dtype=bool)
    kick[[1130, 1170]] = True
    dated = dead_ball_edges.kick_restarts([second, first], kick, HALF)
    assert [d.frame for d in dated] == [1130, 1170]
    late = dead_ball.Restart(1990, 1865, "Goal Kick", 0)
    kick2 = np.zeros(N, dtype=bool)
    kick2[2010] = True  # inside the window but in the next half
    assert dead_ball_edges.kick_restarts([late], kick2, [(0, 2000), (2000, N)])[0].frame == 1990


# -- the cut -----------------------------------------------------------------------------------


def test_a_tagged_restart_ends_the_players_stoppage_running_through_it() -> None:
    kin = stoppage(N, 1000, 1400) | stoppage(N, 2000, 2200)
    out = dead_ball_edges.cut_at_restarts(kin, [1125, 1900, N + 5])
    assert out[1000:1125].all() and not out[1125:1400].any()
    assert out[2000:2200].all()  # no restart inside: untouched, as is a restart in live play
    assert np.array_equal(dead_ball_edges.cut_at_restarts(kin, []), kin)


def test_a_run_reaching_the_end_of_the_array_is_cut_to_the_end() -> None:
    kin = stoppage(N, 3000, N)
    assert not dead_ball_edges.cut_at_restarts(kin, [3500])[3500:].any()


# -- the chain ---------------------------------------------------------------------------------


def _scene():
    """Away controls early; a ball-out stoppage tagged for home at 2000 (estimate 2125); the
    players stand until 2400; home plays the ball from 2140 on."""
    home = np.full(N, 9.0)
    away = np.full(N, 9.0)
    away[200:210] = 0.5
    home[2140:2160] = 0.5
    out = np.zeros(N, dtype=bool)
    out[1900:1950] = True  # the ball observed outside the pitch: the stoppage begins at 1900
    restart = dead_ball.Restart(2125, 2000, "Throw-in", 0)
    kin = stoppage(N, 1950, 2400)
    return home, away, _evidence([restart], out), kin


def test_engine_is_the_delivered_chain_and_unknown_variants_fail(monkeypatch) -> None:
    monkeypatch.setattr(engine, "halves", lambda: HALF)
    home, away, ev, kin = _scene()
    f = _features(home, away)
    dead = dead_ball_v2.dead_union("rule", ev, kin, HALF)
    expected = engine.chain(f, engine.DEFAULT, ev.restarts, dead)[2]
    base = dead_ball_edges.chain(f, ev, kin, "engine")
    assert np.array_equal(base, expected)
    assert (base[1900:2400] == "D").all()
    with pytest.raises(ValueError, match="unknown variant"):
        dead_ball_edges.chain(f, ev, kin, "first-control")


def test_cut_gives_the_frames_after_the_restart_to_the_restarting_team(monkeypatch) -> None:
    monkeypatch.setattr(engine, "halves", lambda: HALF)
    home, away, ev, kin = _scene()
    out = dead_ball_edges.chain(_features(home, away), ev, kin, "cut")
    assert (out[1900:2125] == "D").all()
    assert (out[2125:2400] == "H").all()  # the tag's team, from the estimate


def test_kick_dates_the_end_and_the_hand_over_by_the_ball(monkeypatch) -> None:
    monkeypatch.setattr(engine, "halves", lambda: HALF)
    home, away, ev, kin = _scene()
    speed = np.zeros(N)
    speed[2150] = 14.0  # the throw lands 1 s after the estimate
    f = _features(home, away, speed)
    out = dead_ball_edges.chain(f, ev, kin, "kick")
    assert (out[1900:2150] == "D").all() and (out[2150:2400] == "H").all()
    # Without any kick in the window the estimate stays, as in `cut`.
    same = dead_ball_edges.chain(_features(home, away), ev, kin, "kick")
    assert np.array_equal(same, dead_ball_edges.chain(_features(home, away), ev, kin, "cut"))


def test_bench_methods_cover_every_variant() -> None:
    kin = {False: np.zeros(N, dtype=bool), True: np.zeros(N, dtype=bool)}
    assert set(dead_ball_edges.bench_methods(kin)) == set(dead_ball_edges.VARIANTS)


def test_params_are_the_pre_registered_ones() -> None:
    assert Params() == Params(kick_mps=10.0, reach=2.0)


# -- the synthetic DFL tags --------------------------------------------------------------------


def test_dfl_tags_cover_ball_out_stoppages_with_the_cycled_error() -> None:
    n = 3000
    truth = np.full(n, "H", dtype=object)
    truth[:100] = "D"  # before the half's first kick: not a tagged restart
    truth[500:800] = "D"  # ball out
    truth[800:] = "A"
    truth[1200:1500] = "D"  # a foul: the frozen ball is on the pitch
    truth[2000:2300] = "D"  # ball out again
    out = np.zeros(n, dtype=bool)
    out[500:800] = True
    out[2000:2300] = True
    tags = dead_ball_edges.dfl_tags(truth, out, [(0, n)], errors_s=(-1.0, 2.0))
    assert [(t.frame, t.tag_start, t.team) for t in tags] == [
        (800 - FPS, 800 - FPS - 125, 1),
        (2300 + 2 * FPS, 2300 + 2 * FPS - 125, 1),
    ]
    assert all(not t.kind.startswith("Kick Off") for t in tags)


# -- the delivered match -----------------------------------------------------------------------


@requires_bundle
def test_the_engine_variant_reproduces_the_delivered_run() -> None:
    from tools import atd, emision

    f = engine.features(atd.load("tactical"), emision.team_slots())
    ev = dead_ball.load_evidence()
    labels = dead_ball_edges.chain(f, ev, dead_ball_edges.kinematic_for("engine"), "engine")
    assert np.array_equal(labels, engine.run()[0]["label"].to_numpy())
