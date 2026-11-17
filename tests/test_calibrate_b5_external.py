"""Synthetic tests for external calibration; no competition or external data is loaded."""

from __future__ import annotations

import numpy as np
import pytest

from tools import calibrate_b5_external as calibration
from tools import external


def test_stable_loss_brier_and_deterministic_calibration() -> None:
    margin = np.array([1.0, 1.0, -1.0, -1.0])
    home = np.array([1, 0, 1, 0])
    temperature = calibration.calibrate(margin, home)
    assert temperature == calibration.calibrate(margin, home)
    assert calibration.LOWER < temperature < calibration.UPPER
    objective = (
        calibration.loss(margin, home, temperature)
        + calibration.PENALTY * np.log(temperature / calibration.PRIOR_M) ** 2
    )
    assert objective <= calibration.loss(margin, home, calibration.PRIOR_M)
    assert calibration.loss(np.array([1000.0]), np.array([0]), 0.05) == pytest.approx(20000.0)
    assert calibration.brier(np.array([1000.0, -1000.0]), np.array([1, 0]), 0.05) == 0


def test_acceptance_requires_an_interior_candidate_and_strict_check_improvement() -> None:
    assert calibration.accepts(2.0, 0.4, 0.5)
    assert not calibration.accepts(calibration.LOWER, 0.4, 0.5)
    assert not calibration.accepts(2.0, 0.5, 0.5)
    assert not calibration.accepts(2.0, 0.5 - 1e-13, 0.5)


def test_samples_exclude_dead_outside_and_missing_team() -> None:
    ball = np.array([[0.0, 0.0], [0.0, 0.0], [60.0, 0.0], [0.0, 0.0], [0.0, 0.0]])
    home = np.tile(np.array([[[1.0, 0.0]]]), (5, 1, 1))
    away = np.tile(np.array([[[2.0, 0.0]]]), (5, 1, 1))
    away[4] = np.nan
    section = external.Section(
        "firstHalf", 0, ball, np.array([1, 2, 1, 1, 2]), np.array([1, 1, 1, 0, 1]), home, away
    )
    raw = external.Raw("synthetic", (100.0, 68.0), (section,))
    margins, labels, counts = calibration.samples(raw)
    assert margins.tolist() == [1.0, 1.0]
    assert labels.tolist() == [1, 0]
    assert counts == {
        "total": 5,
        "alive_owner": 4,
        "inside": 3,
        "eligible": 2,
        "home": 1,
        "away": 1,
    }
