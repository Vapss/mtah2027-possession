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
    assert artifact.confidence.iloc[2] == 0.0  # no ball: abstain from this job's opinion
    assert np.isnan(result.ball_speed_mps[0])
    assert result.ball_speed_mps[1] > 0
    assert np.isnan(result.ball_speed_mps[2:]).all()
    assert result.ball_out_of_bounds.tolist() == [False, False, False, True]


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
    assert emision.P_DEAD_FLOOR < 0.05
    assert emision.P_DEAD_OUT_OF_BOUNDS < 0.25


def test_public_metrics_exclude_ungraded_frames_and_missing_ball_from_team_accuracy() -> None:
    artifact = pd.DataFrame(
        {
            "p_home": [0.8, 0.1, 0.1, 0.8],
            "p_away": [0.1, 0.8, 0.1, 0.1],
            "p_dead": [0.1, 0.1, 0.8, 0.1],
        }
    )
    gt_path = emision.REPO_ROOT / "evaluation/gt/BAR-ATH_possession_gt_public.csv"
    if not gt_path.is_file():
        pytest.skip("public ground truth not found")
    # The public file is full-length, so build the ordinary artifact shape used by the metric.
    repeated = pd.DataFrame(
        np.tile(artifact.to_numpy(), (games.source_frames() // 4 + 1, 1))[: games.source_frames()],
        columns=["p_home", "p_away", "p_dead"],
    )
    repeated.insert(0, "frame", np.arange(games.source_frames()))
    ball_present = np.zeros(games.source_frames(), dtype=bool)

    report = emision.public_metrics(repeated, ball_present)

    assert report["n_scored_frames"] == 7500
    assert report["n_live_team_frames_with_ball"] == 0
    assert report["n_live_team_frames_without_ball"] == report["n_live_team_frames"]
    assert report["team_accuracy_h_a"] is None
    assert "absent-ball frames abstain" in report["team_accuracy_scope"]
    assert set(report["log_loss_by_actual_class"]) == {"H", "A", "D"}
    assert set(report["brier_one_vs_rest_by_class"]) == {"H", "A", "D"}
