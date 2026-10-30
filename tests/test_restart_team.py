"""Lane restart-team: which team restarts, pinned on synthetic frames.

Each scene is placed by hand: hand-made distances drive the engine's control and the holder test,
an out-of-pitch run opens the tagged stoppage, and a team-less tag is the restart. Times are frames
at 25 fps. The last test reads the delivered match and skips without the bundle; it compares
labels in memory and pins the delivered chain by its SHA-256 prefix, nothing frame by frame.
"""

from __future__ import annotations

import hashlib

import numpy as np
import pandas as pd
import pytest
from _bundle import requires_bundle

from tools import dead_ball, engine, restart_team
from tools.restart_team import (
    KICK_OFF_GOAL,
    KICK_OFF_START,
    NONE,
    THROW_IN,
    Params,
)

FPS = restart_team.FPS
N = 2000
HALF = [(0, N)]


def _features(home, away, present=None, in_pitch=None) -> engine.Features:
    present = np.ones(len(home), dtype=bool) if present is None else present
    in_pitch = present.copy() if in_pitch is None else in_pitch
    return engine.Features(
        np.where(present, home, np.nan),
        np.where(present, away, np.nan),
        present,
        np.zeros(len(home)),
        in_pitch,
    )


def _evidence(restarts, out) -> dead_ball.Evidence:
    zeros = np.zeros(len(out), dtype=bool)
    return dead_ball.Evidence(tuple(restarts), out, ~out, zeros.copy())


def _throw_in_scene():
    """Home controls the ball, kicks it out at 450; away holds it behind the line; the tag's
    estimate is 600 (tag 475); home controls again from 700."""
    home, away = np.full(N, 10.0), np.full(N, 10.0)
    home[100:400], away[100:400] = 0.5, 5.0  # home control
    home[700:800], away[700:800] = 0.5, 5.0  # home again, after the throw
    out = np.zeros(N, dtype=bool)
    out[450:600] = True
    home[500:600], away[500:600] = 4.0, 0.5  # an away player holds it off the pitch
    in_pitch = ~out
    f = _features(home, away, in_pitch=in_pitch)
    ev = _evidence([dead_ball.Restart(600, 475, THROW_IN, None)], out)
    return f, ev


# -- the evidence --------------------------------------------------------------------------------


def test_a_team_holds_the_ball_only_when_the_other_is_clearly_farther() -> None:
    home = np.array([0.5, 0.5, 1.6, 0.5, np.inf, np.nan])
    away = np.array([2.0, 1.9, 5.0, 0.4, 1.0, 0.3])
    present = np.array([True, True, True, True, True, False])
    f = engine.Features(home, away, present, np.zeros(6), np.zeros(6, dtype=bool))
    # Out of the pitch still counts; 1,9 m is not clear; 1,6 m is out of reach; a team with nobody
    # tracked is infinitely far; an unobserved ball is nobody's.
    assert restart_team.holders(f).tolist() == [0, NONE, NONE, NONE, 1, NONE]


def test_p_names_the_one_team_holding_the_ball_in_the_tag_window() -> None:
    held = np.full(N, NONE, dtype=np.int8)
    r = dead_ball.Restart(600, 475, THROW_IN, None)
    assert restart_team.by_position(r, held, HALF) is None  # nobody holds it: abstain
    held[500:520] = 1
    assert restart_team.by_position(r, held, HALF) == 1
    held[600:700] = 0  # at and after the estimate: outside the window
    held[400:475] = 0  # before the tag: outside too
    assert restart_team.by_position(r, held, HALF) == 1
    held[530] = 0  # a home player hands the ball back inside the window: ambiguous
    assert restart_team.by_position(r, held, HALF) is None


def test_p_stays_inside_the_restart_half() -> None:
    held = np.full(N, NONE, dtype=np.int8)
    held[90:100] = 0  # the end of the previous half
    r = dead_ball.Restart(150, 60, KICK_OFF_START, None)
    assert restart_team.by_position(r, held, [(0, 100), (100, N)]) is None
    assert (
        restart_team.by_position(dead_ball.Restart(50, 0, THROW_IN, None), held, [(100, N)]) is None
    )


def test_l_is_the_opponent_of_the_team_in_possession_when_the_ball_went_out() -> None:
    state = np.full(N, NONE, dtype=np.int8)
    state[100:450] = 0
    assert restart_team.law_team(state, 450, 0) == 1
    assert restart_team.law_team(state, 50, 0) is None  # no state yet
    assert restart_team.law_team(state, 0, 0) is None  # the ball left at the half's start
    assert restart_team.law_team(state, None, 0) is None


def test_the_anchor_is_the_last_exit_of_the_ball_before_the_tag() -> None:
    _, ev = _throw_in_scene()
    assert restart_team.anchors(ev, HALF) == [450]
    outside = dead_ball.Evidence(
        (dead_ball.Restart(10, 0, THROW_IN, None),), ev.out, ev.inside, ev.still
    )
    assert restart_team.anchors(outside, [(100, N)]) == [None]


def test_the_variants_combine_p_and_l() -> None:
    combine = restart_team.combine
    assert [combine(v, THROW_IN, 1, 0) for v in ("law", "pos", "pos+law", "agree")] == [
        0,
        1,
        1,
        None,
    ]
    assert [combine(v, THROW_IN, None, 0) for v in ("law", "pos", "pos+law", "agree")] == [
        0,
        None,
        0,
        None,
    ]
    assert combine("agree", THROW_IN, 1, 1) == 1
    assert combine("law", KICK_OFF_START, 0, 1) is None  # the law does not know the coin toss
    with pytest.raises(ValueError, match="unknown variant"):
        combine("engine", THROW_IN, 1, 1)


def test_params_are_the_pre_registered_ones() -> None:
    assert Params() == Params(take_m=1.5, clear_m=2.0, vote_s=5.0)
    assert restart_team.DFL_ERRORS_S == (-2.0, -1.0, 0.0, 1.0, 2.0)


# -- the inference and the chain -----------------------------------------------------------------


def test_a_throw_in_goes_to_the_opponents_and_is_forced(monkeypatch) -> None:
    monkeypatch.setattr(engine, "halves", lambda: HALF)
    f, ev = _throw_in_scene()
    kin = np.zeros(N, dtype=bool)
    inf = restart_team.infer(f, ev, "agree")
    (row,) = inf.rows
    assert (row["pos"], row["law"], row["team"], row["forced"]) == (1, 1, 1, True)
    assert inf.restarts[0].team == 1
    base = restart_team.chain(f, ev, kin, "engine")
    out = restart_team.chain(f, ev, kin, "agree")
    assert (base[450:600] == "D").all() and (out[450:600] == "D").all()
    assert (base[600:700] == "H").all()  # today: the team that put the ball out, carried
    assert (out[600:700] == "A").all()  # the throw-in's team, until home controls again
    assert (out[700:800] == "H").all()


def test_the_engine_variant_leaves_team_less_restarts_unforced(monkeypatch) -> None:
    monkeypatch.setattr(engine, "halves", lambda: HALF)
    f, ev = _throw_in_scene()
    kin = np.zeros(N, dtype=bool)
    dead = dead_ball.dead_mask(ev, HALF, "out") | kin
    expected = engine.chain(f, engine.DEFAULT, ev.restarts, dead)[2]
    assert np.array_equal(restart_team.chain(f, ev, kin, "engine"), expected)
    assert restart_team.infer(f, ev, "engine").restarts == ev.restarts
    with pytest.raises(ValueError, match="unknown variant"):
        restart_team.chain(f, ev, kin, "kick")


def test_an_ambiguous_restart_is_left_unforced(monkeypatch) -> None:
    monkeypatch.setattr(engine, "halves", lambda: HALF)
    f, ev = _throw_in_scene()
    home = f.home_m.copy()
    away = f.away_m.copy()
    home[510], away[510] = 0.3, 3.0  # a home player touches it inside the window
    f2 = _features(home, away, in_pitch=f.in_pitch)
    for variant in ("pos", "agree"):
        (row,) = restart_team.infer(f2, ev, variant).rows
        assert row["pos"] is None and row["team"] is None and not row["forced"]
    kin = np.zeros(N, dtype=bool)
    assert np.array_equal(
        restart_team.chain(f2, ev, kin, "agree"), restart_team.chain(f2, ev, kin, "engine")
    )
    # P and L disagree: `agree` abstains, `pos+law` follows P.
    home[500:600], away[500:600] = 0.5, 4.0
    f3 = _features(home, away, in_pitch=f.in_pitch)
    assert restart_team.infer(f3, ev, "agree").rows[0]["team"] is None
    assert restart_team.infer(f3, ev, "pos+law").rows[0]["team"] == 0


def test_a_control_seen_in_the_window_still_cancels_a_named_restart(monkeypatch) -> None:
    monkeypatch.setattr(engine, "halves", lambda: HALF)
    f, ev = _throw_in_scene()
    home, away, in_pitch = f.home_m.copy(), f.away_m.copy(), f.in_pitch.copy()
    in_pitch[580:600] = True  # a quick throw: away controls on the pitch before the estimate
    f2 = _features(home, away, in_pitch=in_pitch)
    (row,) = restart_team.infer(f2, ev, "law").rows
    assert row["team"] == 1 and not row["forced"]  # DECISIONS 32/35: the observation rules


def test_l_reads_the_variant_own_chain_in_frame_order(monkeypatch) -> None:
    """Two throw-ins with no control between them: the second goes to the opponents of the
    first's team, which only the variant's own chain knows."""
    monkeypatch.setattr(engine, "halves", lambda: HALF)
    f, ev = _throw_in_scene()
    home, away = f.home_m.copy(), f.away_m.copy()
    home[700:800], away[700:800] = 10.0, 10.0  # nobody controls after the first throw
    out = ev.out.copy()
    out[650:780] = True  # straight out again
    in_pitch = ~out
    f2 = _features(home, away, in_pitch=in_pitch)
    second = dead_ball.Restart(900, 775, THROW_IN, None)
    ev2 = _evidence([ev.restarts[0], second], out)
    rows = restart_team.infer(f2, ev2, "law").rows
    assert [(r["law"], r["team"]) for r in rows] == [(1, 1), (0, 0)]


def test_a_kick_off_after_a_goal_goes_to_the_team_that_conceded(monkeypatch) -> None:
    monkeypatch.setattr(engine, "halves", lambda: HALF)
    home, away = np.full(N, 10.0), np.full(N, 10.0)
    home[100:300], away[100:300] = 5.0, 0.5  # away attacks
    out = np.zeros(N, dtype=bool)
    out[320:400] = True  # the ball in the net
    home[1300:1400], away[1300:1400] = 0.2, 10.0  # a home player at the centre spot
    f = _features(home, away, in_pitch=~out)
    ev = _evidence([dead_ball.Restart(1400, 1312, KICK_OFF_GOAL, None)], out)
    (row,) = restart_team.infer(f, ev, "agree").rows
    assert (row["pos"], row["law"], row["team"]) == (0, 0, 0)
    # A home control at the centre spot inside the window cancels the forcing: the engine already
    # starts from that control (DECISIONS 32).
    assert not row["forced"]


def _half_starts(p1: int | None, p2: int | None):
    """Two halves, each opening with a team-less kick-off whose window shows `p1` / `p2`."""
    runs = [(0, 1000), (1000, N)]
    home, away = np.full(N, 10.0), np.full(N, 10.0)
    for start, p in ((0, p1), (1000, p2)):
        if p is not None:
            near = slice(start + 10, start + 50)
            (home if p == 0 else away)[near] = 0.3
    present = np.ones(N, dtype=bool)
    f = _features(home, away, present, in_pitch=np.zeros(N, dtype=bool))  # no control in windows
    restarts = [
        dead_ball.Restart(87, 0, KICK_OFF_START, None),
        dead_ball.Restart(1087, 1000, KICK_OFF_START, None),
    ]
    return f, _evidence(restarts, np.zeros(N, dtype=bool)), runs


def test_half_start_kick_offs_check_each_other_by_law(monkeypatch) -> None:
    f, ev, runs = _half_starts(0, 1)
    monkeypatch.setattr(engine, "halves", lambda: runs)
    teams = {
        v: [r["team"] for r in restart_team.infer(f, ev, v).rows] for v in restart_team.VARIANTS[1:]
    }
    assert teams == {"law": [None, None], "pos": [0, 1], "pos+law": [0, 1], "agree": [0, 1]}
    # One half unseen: P with the law fills it as the other half's opponents; `agree` needs both.
    f, ev, runs = _half_starts(None, 1)
    rows = restart_team.infer(f, ev, "pos+law", runs=runs).rows
    assert [(r["pos"], r["law"], r["team"]) for r in rows] == [(None, 0, 0), (1, None, 1)]
    assert [r["team"] for r in restart_team.infer(f, ev, "agree", runs=runs).rows] == [None, None]
    # The same team on both halves contradicts the law: `agree` abstains on both.
    f, ev, runs = _half_starts(1, 1)
    assert [r["team"] for r in restart_team.infer(f, ev, "agree", runs=runs).rows] == [None, None]


def test_a_forced_half_start_fills_the_frames_before_the_first_control(monkeypatch) -> None:
    f, ev, runs = _half_starts(0, 1)
    monkeypatch.setattr(engine, "halves", lambda: runs)
    home, away, in_pitch = f.home_m.copy(), f.away_m.copy(), f.in_pitch.copy()
    home[300:400], away[300:400] = 5.0, 0.5  # the first control of the first half: away
    in_pitch[300:400] = True
    f2 = _features(home, away, in_pitch=in_pitch)
    kin = np.zeros(N, dtype=bool)
    base = restart_team.chain(f2, ev, kin, "engine")
    out = restart_team.chain(f2, ev, kin, "agree")
    assert (base[:87] == "D").all() and (out[:87] == "D").all()  # before the kick: unchanged
    assert (base[87:300] == "X").all()  # today: no state before the first control
    assert (out[87:300] == "H").all()  # the kick-off's team, from the estimate
    assert (out[300:400] == "A").all()
    assert (out[1087:1100] == "A").all()  # the second half's kick-off


# -- the synthetic DFL tags ----------------------------------------------------------------------


def test_dfl_kinds_come_from_where_the_ball_is_put_back() -> None:
    pitch = (105.0, 68.0)
    kind = restart_team.dfl_kind
    assert kind(np.array([52.0, 34.5]), pitch) == KICK_OFF_GOAL
    assert kind(np.array([40.0, -0.5]), pitch) == THROW_IN
    assert kind(np.array([40.0, 67.0]), pitch) == THROW_IN
    assert kind(np.array([0.5, 67.5]), pitch) == "Corner Kick"
    assert kind(np.array([5.5, 30.0]), pitch) == "Free Kick"
    assert kind(np.array([1.0, 30.0]), pitch) == "Goal Kick"


def test_dfl_tags_mirror_ours_with_the_cycled_error() -> None:
    n, pitch = 3000, (105.0, 68.0)
    truth = np.full(n, "H", dtype=object)
    truth[:100] = "D"  # before the half's first kick
    truth[500:800] = "D"  # ball out over the touchline
    truth[800:] = "A"
    truth[1200:1500] = "D"  # a foul: frozen ball on the pitch, a free kick
    truth[2000:2300] = "D"  # ball out over the goal line
    ball = np.tile([50.0, 30.0], (n, 1))
    ball[800] = [40.0, -0.3]  # thrown in
    ball[1500] = [60.0, 30.0]
    ball[2300] = [1.0, 30.0]  # a goal kick
    out = np.zeros(n, dtype=bool)
    out[500:800] = True
    out[2000:2300] = True
    tags, truths = restart_team.dfl_tags(truth, ball, pitch, out, [(0, n)], errors_s=(0.0, 1.0))
    assert [(t.frame, t.tag_start, t.kind, t.team) for t in tags] == [
        (100, 100 - 88, KICK_OFF_START, None),
        (800 + FPS, 800 + FPS - 125, THROW_IN, None),
        (2300, 2300 - 125, "Goal Kick", 1),
    ]
    assert truths == (0, 1, 1)


def test_accuracy_counts_decided_and_right_per_kind() -> None:
    inf = restart_team.Inference(
        (),
        (
            {"index": 0, "kind": THROW_IN, "pos": 1, "law": 0, "team": 1},
            {"index": 1, "kind": THROW_IN, "pos": None, "law": 1, "team": None},
            {"index": 2, "kind": KICK_OFF_GOAL, "pos": 0, "law": 0, "team": 0},
            {"index": 3, "kind": THROW_IN, "pos": 0, "law": 0, "team": 0},
        ),
    )
    acc = restart_team.accuracy(inf, (1, 1, 1, None))  # the last one has no true team
    assert acc["throw-in"] == {
        "n": 2,
        "team_decided": 1,
        "team_right": 1,
        "pos_decided": 1,
        "pos_right": 1,
        "law_decided": 2,
        "law_right": 1,
    }
    assert acc["all"]["team_decided"] == 2 and acc["all"]["team_right"] == 1


def test_the_smart_tagging_vote_after_a_forced_restart() -> None:
    votes = np.zeros((N, 2), dtype=np.int16)
    votes[600:700, 1] = 1  # away attacking
    votes[650:660, 0] = 1  # a split vote: not counted
    rows = [
        {"frame": 600, "team": 1, "forced": True},
        {"frame": 1500, "team": 0, "forced": True},  # no vote after it
        {"frame": 600, "team": 0, "forced": False},  # not forced: not counted
    ]
    st = restart_team.st_after(rows, votes)
    assert st == {
        "restarts_with_vote": 1,
        "restarts_majority_agree": 1,
        "frames_with_vote": 90,
        "frame_agreement": 1.0,
    }


def test_bench_methods_cover_every_variant() -> None:
    assert set(restart_team.bench_methods(np.zeros(N, dtype=bool))) == set(restart_team.VARIANTS)


# -- the delivered match -------------------------------------------------------------------------


@requires_bundle
def test_the_engine_variant_reproduces_the_delivered_run() -> None:
    from tools import atd, emision

    f = engine.features(atd.load("tactical"), emision.team_slots())
    ev = dead_ball.load_evidence()
    labels = restart_team.chain(f, ev, restart_team.match_kinematic(), "engine")
    assert np.array_equal(labels, engine.run()[0]["label"].to_numpy())
    table = pd.DataFrame({"frame": np.arange(len(labels)), "label": labels})
    csv = table.to_csv(index=False, lineterminator="\n").encode()
    assert hashlib.sha256(csv).hexdigest().startswith("72c98ed4bb4a")
