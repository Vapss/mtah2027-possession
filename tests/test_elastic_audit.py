"""External-corpus coverage audit uses only synthetic metadata and tracking."""

from __future__ import annotations

import pandas as pd
import pytest

from tools import elastic_audit


def test_mismatched_input_fingerprint_is_rejected() -> None:
    expected = dict(elastic_audit.EXPECTED_SHA256["J03WMX"])
    elastic_audit.check_hashes("J03WMX", expected)
    expected["tracking"] = "not-the-recorded-input"
    with pytest.raises(ValueError, match="fingerprints differ"):
        elastic_audit.check_hashes("J03WMX", expected)


def test_roster_marks_reused_shirts_as_ambiguous(tmp_path) -> None:
    metadata = tmp_path / "meta.xml"
    metadata.write_text(
        '<root><Team Role="home"><Players>'
        '<Player ShirtNumber="7" PersonId="p1"/>'
        '<Player ShirtNumber="7" PersonId="p2"/>'
        '</Players></Team><Team Role="guest"><Players>'
        '<Player ShirtNumber="4" PersonId="p3"/>'
        "</Players></Team></root>",
        encoding="utf-8",
    )
    assert elastic_audit.roster(metadata) == {"home_7": None, "away_4": "p3"}


def test_audit_reports_exclusions_duplicates_and_tracking_without_filtering_dead(tmp_path) -> None:
    events = pd.DataFrame(
        {
            "period_id": [1, 1, 1, 1, 2, 3, 1, 1],
            "receiver_id": [
                "home_7",
                "home_7",
                "away_4",
                "away_4",
                "home_7",
                "home_7",
                None,
                "home_9",
            ],
            "receive_frame_id": [10, 10, 10, 11, 20, 10, None, 10],
            "spadl_type": ["pass"] * 8,
        }
    )
    tracking = tmp_path / "positions.xml"
    tracking.write_text(
        '<FrameSet GameSection="firstHalf" TeamId="BALL" PersonId="ball">\n'
        '<Frame N="10" BallPossession="1" BallStatus="0" />\n'
        "</FrameSet>\n"
        '<FrameSet GameSection="firstHalf" TeamId="home" PersonId="p1">\n'
        '<Frame N="10" />\n'
        "</FrameSet>\n",
        encoding="utf-8",
    )
    result = elastic_audit.summarize(events, {"home_7": "p1", "away_4": "p2"}, tracking)
    assert result["events"] == {
        "eligible_for_tracking_check": 5,
        "has_reception": 7,
        "invalid_period": 1,
        "missing_reception": 1,
        "receiver_not_in_roster": 1,
        "total_events": 8,
    }
    assert result["duplicate_reception_rows"] == 1
    assert result["frames_with_multiple_receivers"] == 1
    assert result["frames_with_opposing_receivers"] == 1
    assert result["actor_vs_receiver"] == {"actor_unknown": 5}
    assert result["coverage"] == {
        "ball_frame_missing": 2,
        "ball_frame_present": 3,
        "receiver_frame_missing": 1,
        "receiver_frame_present": 2,
    }
    assert result["ball_status"] == {"0": 3}
    assert result["receiver_vs_ball_owner"] == {"same": 2, "different": 1}


def test_out_and_goal_are_terminal_events_not_unmatched_players() -> None:
    events = pd.DataFrame(
        {
            "period_id": [1, 1, 1],
            "receiver_id": ["out_left", "goal_right", "unknown_1"],
            "receive_frame_id": [10, 11, 12],
            "spadl_type": ["pass", "shot", "pass"],
        }
    )
    valid, counts = elastic_audit.prepare(events, {})
    assert valid == []
    assert counts["terminal_out"] == counts["terminal_goal"] == 1
    assert counts["receiver_not_in_roster"] == 1


def test_actor_team_comparison_keeps_opponent_receptions(tmp_path) -> None:
    events = pd.DataFrame(
        {
            "period_id": [1, 1],
            "player_id": ["home_7", "home_7"],
            "receiver_id": ["home_7", "away_4"],
            "receive_frame_id": [10, 11],
            "spadl_type": ["pass", "pass"],
        }
    )
    tracking = tmp_path / "empty.xml"
    tracking.write_text("", encoding="utf-8")
    result = elastic_audit.summarize(events, {"home_7": "p1", "away_4": "p2"}, tracking)
    assert result["actor_vs_receiver"] == {"opposing_team": 1, "same_team": 1}
    assert result["coverage"]["ball_frame_missing"] == 2
