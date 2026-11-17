"""The contract must accept good tables and reject every realistic way of being wrong.

Each negative case here is a failure mode that costs a submission outright: a wrong header, a
missing row, an off-by-one frame column, a blank cell. The organiser's validator catches them
too, but only at the end -- these catch them while the author is still in the file.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from tools.contract import (
    N_FRAMES,
    ContractError,
    artifact_problems,
    check_artifact,
    check_submission,
    submission_problems,
)


def test_valid_submission_passes(all_x: pd.DataFrame) -> None:
    assert submission_problems(all_x) == []
    check_submission(all_x)


def test_wrong_header_is_rejected(all_x: pd.DataFrame) -> None:
    renamed = all_x.rename(columns={"label": "possession"})
    with pytest.raises(ContractError, match="columns"):
        check_submission(renamed)


def test_header_case_and_space_is_tolerated(all_x: pd.DataFrame) -> None:
    renamed = all_x.rename(columns={"frame": " Frame ", "label": "LABEL"})
    assert submission_problems(renamed) == []


def test_missing_row_is_rejected(all_x: pd.DataFrame) -> None:
    short = all_x.iloc[:-1]
    with pytest.raises(ContractError, match="expected"):
        check_submission(short)


def test_frame_column_must_be_contiguous_and_ordered(all_x: pd.DataFrame) -> None:
    shuffled = all_x.copy()
    shuffled.loc[0, "frame"] = 5
    with pytest.raises(ContractError, match="in order"):
        check_submission(shuffled)


def test_unknown_label_is_rejected(all_x: pd.DataFrame) -> None:
    bad = all_x.copy()
    bad.loc[10, "label"] = "Q"
    with pytest.raises(ContractError, match="unknown label"):
        check_submission(bad)


def test_blank_label_is_rejected(all_x: pd.DataFrame) -> None:
    bad = all_x.copy()
    bad.loc[10, "label"] = ""
    with pytest.raises(ContractError, match="blank"):
        check_submission(bad)


def test_lowercase_labels_are_accepted(all_x: pd.DataFrame) -> None:
    """The official validator strips and upper-cases; so do we, or we would fail legal files."""
    lower = all_x.copy()
    lower["label"] = "x"
    assert submission_problems(lower) == []


def test_valid_artifact_passes(artifact_factory) -> None:
    artifact = artifact_factory()
    assert artifact_problems(artifact) == []
    check_artifact(artifact)


def test_probabilities_must_sum_to_one(artifact_factory) -> None:
    artifact = artifact_factory(p_home=0.2, p_away=0.3, p_dead=0.3)
    with pytest.raises(ContractError, match="sum to 1"):
        check_artifact(artifact)


def test_probabilities_must_be_in_range(artifact_factory) -> None:
    artifact = artifact_factory(p_home=1.2, p_away=-0.1, p_dead=-0.1)
    with pytest.raises(ContractError, match=r"outside \[0, 1\]"):
        check_artifact(artifact)


def test_artifact_must_have_a_frame_column(artifact_factory) -> None:
    artifact = artifact_factory().drop(columns=["frame"])
    with pytest.raises(ContractError, match="columns"):
        check_artifact(artifact)


def test_artifact_rejects_non_numeric_probability(artifact_factory) -> None:
    artifact = artifact_factory().astype({"p_home": object})
    artifact.loc[3, "p_home"] = "high"
    with pytest.raises(ContractError, match="non-numeric"):
        check_artifact(artifact)


def test_frame_count_matches_the_video() -> None:
    """The row count is not a magic number here; it comes from games.py."""
    assert N_FRAMES == 199319
    assert np.arange(N_FRAMES)[-1] == 199318
