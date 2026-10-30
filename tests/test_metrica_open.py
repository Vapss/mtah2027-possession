"""Metrica's open games: the reader, the event-derived truth (E1-E5) and our shape, on synthetic
files. Only the last test reads the real sample games, and it skips when they are not here."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from tools import dead_ball
from tools import metrica_open as mo

H, A, N = mo.HOME, mo.AWAY, mo.NONE


def _events(rows: list[tuple]) -> pd.DataFrame:
    """`(team, type, subtype, start, end)` rows, 0-based frames, all in period 1."""
    return pd.DataFrame(
        {
            "team": np.array([r[0] for r in rows], dtype=np.int8),
            "type": [r[1] for r in rows],
            "subtype": [r[2] for r in rows],
            "period": 1,
            "start": [r[3] for r in rows],
            "end": [r[4] for r in rows],
            "player": "Player1",
        }
    )


def test_a_lost_pass_changes_possession_at_the_recovery_not_at_the_kick() -> None:
    ev = _events(
        [
            (A, "PASS", "", 0, 10),
            (A, "BALL LOST", "INTERCEPTION", 20, 40),
            (H, "RECOVERY", "INTERCEPTION", 38, 38),
            (H, "PASS", "", 38, 60),
        ]
    )
    truth = mo.event_truth(ev, 100, [(0, 100)])
    assert truth.team[:38].tolist() == [A] * 38  # the ball in flight stays with the loser
    assert truth.team[38:].tolist() == [H] * 62
    (change,) = truth.changes
    assert (change.frame, change.old, change.new, change.open_play) == (38, A, H, True)
    assert change.previous == 0  # the old team's last asserting event


def test_a_tackle_losers_ball_lost_after_the_recovery_does_not_hand_the_ball_back() -> None:
    ev = _events(
        [
            (A, "PASS", "", 0, 5),
            (H, "CHALLENGE", "TACKLE-WON", 20, 20),
            (H, "RECOVERY", "THEFT", 20, 20),
            (A, "CHALLENGE", "TACKLE-LOST", 21, 21),
            (A, "BALL LOST", "THEFT", 21, 21),
            (H, "PASS", "", 22, 30),
        ]
    )
    truth = mo.event_truth(ev, 50, [(0, 50)])
    assert truth.team[20:].tolist() == [H] * 30
    assert len(truth.changes) == 1
    assert truth.stray_losses == 1


def test_challenges_faults_received_and_cards_say_nothing_about_the_team() -> None:
    ev = _events(
        [
            (H, "PASS", "", 0, 5),
            (A, "CHALLENGE", "GROUND-WON", 10, 10),
            (A, "CARD", "YELLOW", 12, 12),
            (H, "PASS", "", 15, 20),
        ]
    )
    truth = mo.event_truth(ev, 30, [(0, 30)])
    assert truth.team.tolist() == [H] * 30
    assert truth.changes == ()


def test_before_the_first_asserting_event_of_a_half_nobody_has_the_ball() -> None:
    ev = _events([(A, "CHALLENGE", "AERIAL-WON", 2, 2), (A, "PASS", "", 5, 9)])
    truth = mo.event_truth(ev, 20, [(0, 20)])
    assert truth.team[:5].tolist() == [N] * 5
    assert truth.team[5:].tolist() == [A] * 15


def test_a_ball_out_is_dead_from_its_end_frame_to_the_restart_and_that_change_is_not_open_play():
    ev = _events(
        [
            (H, "PASS", "", 0, 10),
            (H, "BALL OUT", "", 10, 30),
            (A, "SET PIECE", "THROW IN", 80, 80),
            (A, "PASS", "", 80, 90),
        ]
    )
    truth = mo.event_truth(ev, 100, [(0, 100)])
    assert np.flatnonzero(truth.dead).tolist() == list(range(30, 80))
    (change,) = truth.changes
    assert (change.frame, change.kind, change.open_play) == (80, "SET PIECE", False)
    labels = truth.labels()
    assert set(labels[30:80]) == {"D"} and labels[29] == "H" and labels[80] == "A"


def test_a_goal_kick_after_a_shot_out_is_not_open_play_even_when_it_starts_with_a_recovery():
    ev = _events(
        [
            (H, "SHOT", "OFF TARGET-OUT", 0, 20),
            (A, "RECOVERY", "", 300, 300),
            (A, "PASS", "GOAL KICK", 300, 340),
        ]
    )
    truth = mo.event_truth(ev, 400, [(0, 400)])
    assert truth.dead[20:300].all() and not truth.dead[:20].any() and not truth.dead[300:].any()
    (change,) = truth.changes
    assert change.open_play is False


def test_a_foul_stops_play_at_the_challenge_but_an_advantage_does_not() -> None:
    foul = _events(
        [
            (H, "PASS", "", 0, 5),
            (A, "CHALLENGE", "TACKLE-FAULT-LOST", 10, 10),
            (H, "FAULT RECEIVED", "", 10, 10),
            (H, "SET PIECE", "FREE KICK", 60, 60),
        ]
    )
    truth = mo.event_truth(foul, 80, [(0, 80)])
    assert np.flatnonzero(truth.dead).tolist() == list(range(10, 60))
    advantage = _events(
        [
            (H, "PASS", "", 0, 5),
            (A, "CHALLENGE", "GROUND-ADVANTAGE-LOST", 10, 10),
            (H, "PASS", "", 15, 20),
        ]
    )
    assert not mo.event_truth(advantage, 30, [(0, 30)]).dead.any()


def test_a_half_never_carries_the_team_or_a_change_across_its_edge() -> None:
    ev = _events([(H, "PASS", "", 0, 5), (A, "PASS", "", 50, 55)])
    ev.loc[1, "period"] = 2
    truth = mo.event_truth(ev, 100, [(0, 50), (50, 100)])
    assert truth.team[:50].tolist() == [H] * 50 and truth.team[50:].tolist() == [A] * 50
    assert truth.changes == ()


def test_a_half_that_ends_stopped_stays_dead() -> None:
    ev = _events([(H, "PASS", "", 0, 5), (H, "BALL LOST", "END HALF", 5, 8)])
    truth = mo.event_truth(ev, 20, [(0, 20)])
    assert truth.dead[8:].all() and not truth.dead[:8].any()


def test_set_pieces_and_goal_kicks_become_restarts_with_their_team() -> None:
    ev = _events(
        [
            (A, "SET PIECE", "KICK OFF", 0, 0),
            (A, "PASS", "", 0, 10),
            (H, "SET PIECE", "THROW IN", 400, 400),
            (A, "PASS", "GOAL KICK", 900, 950),
            (H, "SET PIECE", "KICK OFF-RETAKEN", 1500, 1500),
        ]
    )
    found = mo.restarts(ev, [(0, 2000)])
    kinds = [(r.frame, r.kind, r.team) for r in found]
    assert kinds == [
        (0, dead_ball.KICK_OFF_START, A),
        (400, "Throw-in", H),
        (900, "Goal Kick", A),
        (1500, dead_ball.KICK_OFF_GOAL, H),
    ]
    assert found[1].tag_start == 400 - 125  # Smart Tagging's window: restart_s before the restart
    assert found[0].tag_start == 0  # never before the half


def _tracking_csv(path: Path, team: str, ball: list[tuple[float, float]]) -> Path:
    n = len(ball)
    head = [
        f",,,{team},,{team},,,",
        ",,,1,,2,,,",
        "Period,Frame,Time [s],Player1,,Player2,,Ball,",
    ]
    rows = []
    for i in range(n):
        period = 1 if i < n // 2 else 2
        bx, by = ball[i]
        rows.append(f"{period},{i + 1},{(i + 1) * 0.04:.2f},0.5,0.5,0.1,0.1,{bx},{by}")
    path.write_text("\n".join(head + rows) + "\n", encoding="utf-8")
    return path


def test_the_reader_and_our_shape_on_a_synthetic_game(tmp_path) -> None:
    nan = float("nan")
    # 60 frames, 30 a half; the first four carry the cases, the rest a still ball at the spot.
    ball = [(0.5, 0.5), (0.52, 0.5), (nan, nan), (1.2, 0.5)] + [(0.5, 0.5)] * 56
    home = mo.read_tracking(_tracking_csv(tmp_path / "h.csv", "Home", ball))
    away = mo.read_tracking(_tracking_csv(tmp_path / "a.csv", "Away", ball))
    assert home.names == ("Player1", "Player2") and home.players.shape == (60, 2, 2)
    events = _events([(H, "PASS", "", 0, 1)])
    game = mo.build("syn", home, away, events)
    assert game.runs == ((0, 30), (30, 60))
    f = game.features
    assert f.present[:4].tolist() == [True, True, False, True]
    assert f.in_pitch[:4].tolist() == [True, True, False, False]
    assert f.home_m[0] == pytest.approx(0.0)
    assert f.home_m[1] == pytest.approx(0.02 * 105)
    assert np.isnan(f.home_m[2])
    assert f.speed_mps[1] == pytest.approx(0.02 * 105 * 25)
    assert np.flatnonzero(game.evidence.out).tolist() == [3]


def test_the_reader_refuses_a_file_that_is_not_25_fps(tmp_path) -> None:
    path = _tracking_csv(tmp_path / "h.csv", "Home", [(0.5, 0.5)] * 4)
    text = path.read_text(encoding="utf-8").replace(",0.08,", ",0.10,")
    path.write_text(text, encoding="utf-8")
    with pytest.raises(ValueError, match="fps"):
        mo.read_tracking(path)


def test_the_reader_maps_teams_and_makes_frames_zero_based(tmp_path) -> None:
    path = tmp_path / "e.csv"
    path.write_text(
        "Team,Type,Subtype,Period,Start Frame,Start Time [s],End Frame,End Time [s],From,To,"
        "Start X,Start Y,End X,End Y\n"
        "Away,SET PIECE,KICK OFF,1,1,0.04,0,0,Player19,,NaN,NaN,NaN,NaN\n"
        "Home,PASS,,1,5,0.2,9,0.36,Player1,Player2,0.5,0.5,0.6,0.5\n",
        encoding="utf-8",
    )
    ev = mo.read_events(path)
    assert ev["team"].tolist() == [A, H]
    assert ev["start"].tolist() == [0, 4] and ev["end"].tolist() == [0, 8]
    assert ev["subtype"].tolist() == ["KICK OFF", ""]


@pytest.mark.skipif(
    not (mo.data_dir() / "g1" / "RawEventsData.csv").exists(), reason="Metrica sample games absent"
)
def test_the_real_sample_games_load_and_their_truth_has_open_play_changes() -> None:
    for name in mo.GAMES:
        game = mo.load(name)
        assert len(game.runs) == 2
        assert sum(c.open_play for c in game.truth.changes) > 150
        assert len(game.evidence.restarts) > 50
