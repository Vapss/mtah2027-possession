"""#6: the engine's control rule and its decoder, on synthetic frames and on the delivered match."""

from __future__ import annotations

import numpy as np
import pytest
from _bundle import requires_bundle

from tools import engine

NONE = engine.NONE


def feats(home, away, speed, present=None, in_pitch=None) -> engine.Features:
    home = np.asarray(home, dtype=float)
    present = np.ones(len(home), dtype=bool) if present is None else np.asarray(present)
    in_pitch = present.copy() if in_pitch is None else np.asarray(in_pitch)
    away = np.asarray(away, dtype=float)
    return engine.Features(home, away, present, np.asarray(speed, float), in_pitch)


def test_control_needs_a_close_player_and_a_slow_ball() -> None:
    f = feats(home=[1.0, 1.0, 3.0, 1.0], away=[4.0, 4.0, 4.0, 0.5], speed=[2.0, 9.0, 2.0, 2.0])
    # slow+close home; fast ball; nobody close; away closer
    assert engine.control(f).tolist() == [0, NONE, NONE, 1]


def test_a_tie_and_an_unknown_speed_are_not_control() -> None:
    f = feats(home=[1.0, 1.0], away=[1.0, 3.0], speed=[2.0, np.nan])
    assert engine.control(f).tolist() == [NONE, NONE]


def test_an_unobserved_ball_is_not_control() -> None:
    f = feats(home=[1.0], away=[3.0], speed=[1.0], present=[False])
    assert engine.control(f).tolist() == [NONE]


def test_a_ball_outside_the_pitch_is_not_control() -> None:
    # DECISIONS 31: a player picking the ball up off the pitch does not take possession.
    f = feats(home=[0.5, 0.5], away=[3.0, 3.0], speed=[1.0, 1.0], in_pitch=[True, False])
    assert engine.control(f).tolist() == [0, NONE]


def test_a_restart_forces_possession_whatever_the_dwell() -> None:
    ctrl = np.array([0, NONE, NONE, NONE, 0, NONE], dtype=np.int8)
    # Frame 2 is an away restart: away has the ball from 2 even at dwell 5, until home controls.
    state = engine.decode(ctrl, [(0, 6)], dwell=5, forced={2: 1})
    assert state.tolist() == [0, 0, 1, 1, 1, 1]
    # Without the restart, home keeps it throughout.
    assert engine.decode(ctrl, [(0, 6)], dwell=5).tolist() == [0] * 6


def test_the_state_is_carried_between_controls_and_none_before_the_first() -> None:
    ctrl = np.array([NONE, NONE, 0, NONE, NONE, 1, NONE], dtype=np.int8)
    assert engine.decode(ctrl, [(0, 7)]).tolist() == [NONE, NONE, 0, 0, 0, 1, 1]


def test_a_change_needs_dwell_frames_and_is_dated_to_the_first() -> None:
    ctrl = np.array([0, NONE, 1, 1, NONE, 1, 1, 1, NONE], dtype=np.int8)
    # Two rival frames are not enough at dwell 3; three in a row are, and the change starts at 5.
    assert engine.decode(ctrl, [(0, 9)], dwell=3).tolist() == [0, 0, 0, 0, 0, 1, 1, 1, 1]


def test_the_state_never_crosses_a_run_boundary() -> None:
    ctrl = np.array([0, NONE, NONE, NONE], dtype=np.int8)
    assert engine.decode(ctrl, [(0, 2), (2, 4)]).tolist() == [0, 0, NONE, NONE]


def test_dwell_must_be_positive() -> None:
    with pytest.raises(ValueError, match="at least 1"):
        engine.decode(np.zeros(3, dtype=np.int8), [(0, 3)], dwell=0)


def test_labels_are_h_a_and_x() -> None:
    assert engine.labels(np.array([0, 1, NONE], dtype=np.int8)).tolist() == ["H", "A", "X"]


def test_engine_does_not_consume_b5_temperature(monkeypatch) -> None:
    """Removed B5 entry points stay absent; even injected ones cannot affect the engine."""
    import pandas as pd

    from tools import dead_ball, emision

    n = engine.games.source_frames()
    features = feats(np.ones(n), np.full(n, 3.0), np.ones(n))
    monkeypatch.setattr(engine.atd, "load", lambda *_: None)
    monkeypatch.setattr(emision, "team_slots", lambda: None)
    monkeypatch.setattr(engine, "features", lambda *_: features)
    monkeypatch.setattr(
        dead_ball, "load_evidence", lambda: type("Evidence", (), {"restarts": ()})()
    )
    monkeypatch.setattr(engine, "delivered_dead", lambda *_: np.zeros(n, dtype=bool))

    def unexpected_emit(*_args):
        raise AssertionError("engine unexpectedly called B5 emission")

    assert not hasattr(emision, "emit")
    assert not hasattr(emision, "EMISSION_TEMPERATURE_M")
    monkeypatch.setattr(emision, "emit", unexpected_emit, raising=False)
    monkeypatch.setattr(emision, "EMISSION_TEMPERATURE_M", 0.1, raising=False)
    first, _ = engine.run()
    monkeypatch.setattr(emision, "EMISSION_TEMPERATURE_M", 100.0)
    second, _ = engine.run()
    pd.testing.assert_frame_equal(first, second)


def _restart(frame: int, tag_start: int, team: int | None):
    from tools.dead_ball import Restart

    return Restart(frame, tag_start, "Throw-in", team)


def test_a_restart_hands_the_ball_to_the_team_that_takes_it() -> None:
    from tools import dead_ball

    instances = [
        {
            "code": "SET PIECES",
            "tags": {"Team": "Atletic Club", "Type": "Throw In"},
            "start_frame": 100,
            "end_frame": 300,
        },
        {
            "code": "SET PIECES",
            "tags": {"Team": "N/A", "Type": "Throw In"},
            "start_frame": 400,
            "end_frame": 500,
        },
    ]
    # One known team, at the dead-ball stream's restart frame (5 s into the tag), away = 1.
    assert engine.restart_controls(dead_ball.restarts(instances)) == {100 + 5 * engine.FPS: 1}


def test_a_restart_already_seen_resuming_is_not_forced() -> None:
    # DECISIONS 32: a control inside [tag_start, frame) means the game resumed; the tracking wins.
    ctrl = np.full(20, NONE, dtype=np.int8)
    ctrl[7] = 0
    restarts = [_restart(10, 5, 1), _restart(18, 15, 1)]
    assert engine.restart_controls(restarts, ctrl) == {18: 1}


def test_cancelling_the_tagged_team_assignment_does_not_shorten_dead_ball(monkeypatch) -> None:
    # The paper must distinguish cancellation of the team forcing from the final D override.
    n = 20
    home, away = np.full(n, 5.0), np.full(n, 5.0)
    home[2], away[7] = 0.5, 0.5
    f = feats(home, away, np.ones(n))
    dead = np.zeros(n, dtype=bool)
    dead[5:10] = True
    restarts = (_restart(10, 5, 0),)
    monkeypatch.setattr(engine, "halves", lambda: [(0, n)])

    assert 10 not in engine.inputs(f, engine.DEFAULT, restarts, dead)[2]
    _ctrl, state, labels = engine.chain(f, engine.DEFAULT, restarts, dead)
    assert state[7] == 1
    assert np.all(labels[7:10] == "D")
    assert labels[10] == "A"


def test_two_restarts_on_one_frame_for_different_teams_are_not_forced() -> None:
    restarts = [_restart(10, 5, 0), _restart(10, 5, 1), _restart(30, 25, 0), _restart(30, 26, 0)]
    assert engine.restart_controls(restarts) == {30: 0}


def _public_score(table) -> tuple[float, float]:
    import sys

    import pandas as pd

    sys.path.insert(0, str(engine.REPO_ROOT / "evaluation"))
    import possession_metrics as pm

    gt_path = engine.REPO_ROOT / "evaluation" / "gt" / "BAR-ATH_possession_gt_public.csv"
    gt = pm.label_codes(pd.read_csv(gt_path).label)
    codes = pm.label_codes(table.label.tolist())
    live = np.isin(gt, [pm.H, pm.A])
    filled = pm.fill_abstentions(codes, pm.valid_runs(gt))
    return float(pm.evaluate(gt, codes)["spell_f1_mean"]), float(np.mean(filled[live] == gt[live]))


@requires_bundle
def test_the_engine_before_the_duel_rule_reproduces_its_public_score() -> None:
    """DECISIONS 29-32 (`engine.D31`): bare 0,4195 and 87,2% team accuracy on live; I0 0,4667;
    delivered 0,4585, all with the tagged D only (before DECISIONS 36). The research lanes measured
    against this engine."""
    spell, accuracy = _public_score(engine.run(engine.D31, dead=False, restarts=False)[0])
    assert round(spell, 4) == 0.4195
    assert round(accuracy, 3) == 0.872
    assert (
        round(_public_score(engine.run(engine.D31, restarts=False, kinematic=False)[0])[0], 4)
        == 0.4667
    )
    assert round(_public_score(engine.run(engine.D31, kinematic=False)[0])[0], 4) == 0.4585


@requires_bundle
def test_the_delivered_chain_reproduces_its_public_score() -> None:
    """DECISIONS 34-36 and 44 anchors, a reproduction check and never a target: bare (duel) 0,4757;
    tagged D only 0,5189; with the players' stoppages (W3), I0 and the delivered chain 0,5714, with
    48,2% D in the halves."""
    assert round(_public_score(engine.run(dead=False, restarts=False)[0])[0], 4) == 0.4757
    assert round(_public_score(engine.run(kinematic=False)[0])[0], 4) == 0.5189
    assert round(_public_score(engine.run(restarts=False)[0])[0], 4) == 0.5714
    table, summary = engine.run()
    assert round(_public_score(table)[0], 4) == 0.5714
    assert round(summary["dead_share"], 3) == 0.482


def test_a_duel_in_the_restart_window_does_not_cancel_the_restart() -> None:
    """DECISIONS 35: away takes a throw-in while home is within 1,5 m; the restart still applies."""
    from tools.dead_ball import Restart

    n = 30
    home = np.full(n, 5.0)
    away = np.full(n, 5.0)
    home[2], away[2] = 0.5, 3.0  # home controls before the stoppage
    away[12], home[12] = 0.5, 1.0  # a contested away control inside the restart window [10, 15)
    f = feats(home=home, away=away, speed=np.full(n, 1.0))
    restarts = (Restart(15, 10, "Throw-in", 1),)
    ctrl = engine.control(f)
    switch = engine.uncontested(ctrl, f, engine.DEFAULT.radius_m)
    # As engine.chain does now: only an accepted control cancels a restart.
    forced = engine.restart_controls(restarts, switch)
    state = engine.decode(ctrl, [(0, n)], 1, forced, switch)
    assert state[2] == 0 and state[15] == 1  # the throw-in hands the ball to away
    # Before the fix the duel cancelled the restart and was then ignored: home kept the ball.
    before = engine.decode(ctrl, [(0, n)], 1, engine.restart_controls(restarts, ctrl), switch)
    assert before[15] == 0


def _stoppage_scene():
    """Home controls at 2, an untagged stoppage over [5, 10), away's first control at 12."""
    n = 16
    home = np.full(n, 5.0)
    away = np.full(n, 5.0)
    home[2], away[12] = 0.5, 0.5
    f = feats(home=home, away=away, speed=np.full(n, 1.0))
    dead = np.zeros(n, dtype=bool)
    dead[5:10] = True
    return f, dead, [(0, n)]


def test_an_untagged_stoppage_restarts_with_its_first_accepted_control() -> None:
    """DECISIONS 45 (W3): after the stoppage the ball is away's from its first live frame."""
    f, dead, runs = _stoppage_scene()
    ctrl, switch, forced = engine.inputs(f, engine.DEFAULT, (), dead, runs)
    assert forced == {10: 1}
    state = engine.decode(ctrl, runs, 1, forced, switch)
    assert state[4] == 0 and state[10] == 1 and state[11] == 1


def test_without_the_stoppages_or_with_first_control_off_nothing_is_forced() -> None:
    f, dead, runs = _stoppage_scene()
    assert engine.inputs(f, engine.DEFAULT, (), None, runs)[2] == {}
    assert engine.inputs(f, engine.D36, (), dead, runs)[2] == {}
    ctrl, switch, forced = engine.inputs(f, engine.D36, (), dead, runs)
    assert engine.decode(ctrl, runs, 1, forced, switch)[11] == 0  # home carried to the control


def test_a_tagged_restart_inside_the_stoppage_wins_over_the_first_control() -> None:
    f, dead, runs = _stoppage_scene()
    forced = engine.inputs(f, engine.DEFAULT, (_restart(9, 6, 0),), dead, runs)[2]
    assert forced == {9: 0}  # the tag closes the stoppage: no first-control forcing
