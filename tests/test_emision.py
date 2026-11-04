from __future__ import annotations

from collections import Counter
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

import games
from tools import atd, emision, smart_tagging


def test_team_metadata_maps_24_home_and_22_away_slots() -> None:
    metadata = Path(games.asset_paths(source="tactical")["atd_meta"])
    if not metadata.is_file():
        pytest.skip("match bundle not unpacked -- see data/README.md")

    teams = emision.team_slots(metadata)

    assert len(teams.codes) == 46
    assert teams.home_slots == 24
    assert teams.away_slots == 22
    assert Counter(teams.codes.tolist()) == {0: 24, 1: 22}
    assert teams.home_name == "Barcelona"
    assert teams.away_name == "Atletic Club"


def test_emission_sums_to_one_and_dead_probability_is_weak() -> None:
    players = np.full((4, 2, 3), np.nan)
    players[:, 0, :2] = (0.50, 0.50)
    ball = np.full((4, 3), np.nan)
    ball[0, :2] = (0.51, 0.50)
    ball[1, :2] = (0.50, 0.50)
    ball[3, :2] = (1.01, 0.50)
    tracking = atd.Tracking(players, ball)
    teams = emision.TeamSlots(np.array([0, 1], dtype=np.int8), "Home", "Away", 1, 1)

    result = emision.emit(tracking, teams)
    artifact = result.artifact

    assert len(artifact) == 4
    assert np.allclose(artifact[["p_home", "p_away", "p_dead"]].sum(axis=1), 1.0)
    assert artifact.p_dead.iloc[0] == pytest.approx(emision.P_DEAD_FLOOR)
    assert artifact.p_dead.iloc[3] == pytest.approx(
        emision.P_DEAD_FLOOR + emision.P_DEAD_OUT_OF_BOUNDS
    )
    expected_confidence = artifact[["p_home", "p_away"]].max(axis=1) * result.ball_present
    assert artifact.confidence.equals(expected_confidence)
    assert artifact.confidence.iloc[2] == 0.0  # no observed ball: this emission abstains
    assert artifact.p_home.iloc[2] == pytest.approx(0.49)  # uniform H/A plus the D floor
    assert np.isnan(result.ball_speed_mps[0])
    assert result.ball_speed_mps[1] > 0
    assert np.isnan(result.ball_speed_mps[2:]).all()
    assert result.ball_out_of_bounds.tolist() == [False, False, False, True]


def test_temperature_preserves_h_a_order_but_changes_confidence(monkeypatch) -> None:
    players = np.zeros((1, 2, 3))
    players[0, 0, :2] = (0.50, 0.50)
    players[0, 1, :2] = (0.55, 0.50)
    ball = np.array([[0.51, 0.50, 0.0]])
    tracking = atd.Tracking(players, ball)
    teams = emision.TeamSlots(np.array([0, 1]), "Home", "Away", 1, 1)
    monkeypatch.setattr(emision, "EMISSION_TEMPERATURE_M", 1.0)
    cold = emision.emit(tracking, teams).artifact.iloc[0]
    monkeypatch.setattr(emision, "EMISSION_TEMPERATURE_M", 4.0)
    warm = emision.emit(tracking, teams).artifact.iloc[0]
    assert cold.p_home > cold.p_away and warm.p_home > warm.p_away
    assert cold.confidence > warm.confidence


def test_generate_reads_public_gt_only_when_diagnostics_are_requested(
    tmp_path, monkeypatch
) -> None:
    from types import SimpleNamespace

    from tools import contract

    teams = emision.TeamSlots(np.array([0, 1]), "Home", "Away", 1, 1)
    result = SimpleNamespace(
        artifact=pd.DataFrame(
            {"frame": [0], "p_home": [0.8], "p_away": [0.1], "p_dead": [0.1], "confidence": [0.8]}
        ),
        ball_present=np.array([True]),
        nearest_distance_m=np.array([1.0]),
        ball_speed_mps=np.array([1.0]),
        ball_out_of_bounds=np.array([False]),
    )
    calls = []
    monkeypatch.setattr(emision, "team_slots", lambda *_: teams)
    monkeypatch.setattr(emision.atd, "load", lambda *_: None)
    monkeypatch.setattr(emision, "emit", lambda *_: result)
    monkeypatch.setattr(contract, "read_artifact", lambda *_: None)
    monkeypatch.setattr(emision, "public_metrics", lambda *_: calls.append("gt") or {})
    monkeypatch.setattr(emision, "smart_tagging_anchor", lambda *_: calls.append("tag") or {})

    default = emision.generate(tmp_path / "default.csv")
    assert calls == []
    assert "public_metrics" not in default
    assert "ball_present_fraction" not in default["profile"]
    diagnostic = emision.generate(tmp_path / "diagnostic.csv", diagnostics=True)
    assert calls == ["gt", "tag"]
    assert "public_metrics" in diagnostic
    assert diagnostic["profile"]["ball_present_fraction"] == 1.0


def test_metadata_team_and_smart_tagging_anchor_are_consistent() -> None:
    metadata = Path(games.asset_paths(source="tactical")["atd_meta"])
    tagging_path = smart_tagging.path()
    tracking_path = atd.path("tactical")
    if not metadata.is_file() or not tagging_path.is_file() or not tracking_path.is_file():
        pytest.skip("match bundle not unpacked -- see data/README.md")

    teams = emision.team_slots(metadata)
    instances = smart_tagging.load(tagging_path)
    counts = Counter((instance.get("tags") or {}).get("Team") for instance in instances)
    assert counts == {"Barcelona": 314, "Atletic Club": 288, "N/A": 36}

    result = emision.emit(atd.load("tactical"), teams)
    anchor = emision.smart_tagging_anchor(result, teams, instances)

    assert anchor["combined_favored_fraction"] is not None
    assert anchor["combined_favored_fraction"] > 0.5
    assert "not a training or scoring label" in anchor["use"]


def test_fixed_emission_constants_are_not_a_search_grid() -> None:
    assert emision.SIGMA_M == 1.84
    assert emision.NEAREST_K == 5
    assert emision.EMISSION_TEMPERATURE_M == 2.864606845062
    assert emision.P_DEAD_FLOOR < 0.05
    assert emision.P_DEAD_OUT_OF_BOUNDS < 0.25


def test_public_metrics_exclude_ungraded_frames_and_missing_ball_from_team_accuracy() -> None:
    artifact = pd.DataFrame(
        {
            "p_home": [0.8, 0.1, 0.1, 0.8],
            "p_away": [0.1, 0.8, 0.1, 0.1],
            "p_dead": [0.1, 0.1, 0.8, 0.1],
            "confidence": [0.8, 0.8, 0.1, 0.8],
        }
    )
    gt_path = emision.REPO_ROOT / "evaluation/gt/BAR-ATH_possession_gt_public.csv"
    if not gt_path.is_file():
        pytest.skip("public ground truth not found")
    # The public file is full-length, so build the ordinary artifact shape used by the metric.
    repeated = pd.DataFrame(
        np.tile(artifact.to_numpy(), (games.source_frames() // 4 + 1, 1))[: games.source_frames()],
        columns=["p_home", "p_away", "p_dead", "confidence"],
    )
    repeated.insert(0, "frame", np.arange(games.source_frames()))
    ball_present = np.zeros(games.source_frames(), dtype=bool)

    report = emision.public_metrics(repeated, ball_present)

    assert report["n_scored_frames"] == 7500
    assert report["n_live_team_frames_with_ball"] == 0
    assert report["n_live_team_frames_without_ball"] == report["n_live_team_frames"]
    assert report["team_accuracy_h_a"] is None
    assert "absent-ball frames are H/A-uniform" in report["team_accuracy_scope"]
    assert report["team_log_loss_h_a"] is None
    assert report["team_log_loss_h_a_with_dead_mass"] is None
    assert set(report["log_loss_by_actual_class"]) == {"H", "A", "D"}
    assert set(report["brier_one_vs_rest_by_class"]) == {"H", "A", "D"}
