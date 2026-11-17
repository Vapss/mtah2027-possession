from __future__ import annotations

from collections import Counter
from pathlib import Path

import numpy as np
import pytest

import games
from tools import emision


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


def test_ball_speed_never_bridges_a_gap() -> None:
    ball = np.array([[0.0, 0.0], [1.0, 0.0], [5.0, 0.0], [6.0, 0.0]])
    present = np.array([True, True, False, True])
    speed = emision._ball_speed(ball, present)
    assert np.isnan(speed[0]) and np.isnan(speed[2]) and np.isnan(speed[3])
    assert speed[1] == 1.0 * emision.FPS
