"""Shared fixtures. Imports `tools` and `games` from the repository root, no install step."""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tools.contract import N_FRAMES  # noqa: E402


@pytest.fixture(scope="session")
def repo_root() -> Path:
    return REPO_ROOT


@pytest.fixture(scope="session")
def data_available() -> bool:
    """The match bundle is gated; tests that need it skip instead of failing."""
    return (REPO_ROOT / "data" / "tactical" / "BAR-ATH_tactical_atd.txt").is_file()


@pytest.fixture
def all_x() -> pd.DataFrame:
    """A legal but useless submission: every frame abstains."""
    return pd.DataFrame({"frame": np.arange(N_FRAMES), "label": ["X"] * N_FRAMES})


@pytest.fixture
def artifact_factory():
    """Build an artifact table with constant probabilities."""

    def build(
        p_home: float = 0.2, p_away: float = 0.3, p_dead: float = 0.5, confidence: float = 1.0
    ) -> pd.DataFrame:
        return pd.DataFrame(
            {
                "frame": np.arange(N_FRAMES),
                "p_home": p_home,
                "p_away": p_away,
                "p_dead": p_dead,
                "confidence": confidence,
            }
        )

    return build
