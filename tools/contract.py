"""Schema checks for the two table formats this repository produces.

Only numpy and pandas, so the checks run anywhere the official scorer runs.

    submission : frame,label                               one row per tactical video frame
    artifact   : frame,p_home,p_away,p_dead,confidence     a job's intermediate signal

Both are checked here rather than only at submission time, because a broken intermediate
table is far cheaper to diagnose than a broken submission: the organiser's validator runs
once, at the end, and it says "invalid" after the work is already done.

The official contract lives in SUBMISSION.md and evaluation/validate_submission.py. This
module mirrors it and adds the checks the intermediate table needs. It is not a replacement
for the official validator -- `make validate` runs the real one.
"""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path

import numpy as np
import pandas as pd

from games import source_frames

N_FRAMES = source_frames()
LABELS = ("H", "A", "D", "X")
SUBMISSION_COLUMNS = ("frame", "label")
ARTIFACT_COLUMNS = ("frame", "p_home", "p_away", "p_dead", "confidence")
PROB_COLUMNS = ("p_home", "p_away", "p_dead")
PROB_TOL = 1e-6


class ContractError(ValueError):
    """A table does not satisfy the format contract."""

    def __init__(self, path: object, problems: Iterable[str]) -> None:
        self.problems = list(problems)
        detail = "\n".join(f"  - {problem}" for problem in self.problems)
        super().__init__(f"{path}: {len(self.problems)} contract problem(s)\n{detail}")


def _normalised_columns(df: pd.DataFrame) -> list[str]:
    return [str(column).strip().lower() for column in df.columns]


def _frame_problems(df: pd.DataFrame, expected: tuple[str, ...]) -> list[str]:
    found = _normalised_columns(df)
    if tuple(found) != expected:
        return [f"columns are {found}, expected {list(expected)}"]
    return []


def _count_problems(df: pd.DataFrame) -> list[str]:
    if len(df) != N_FRAMES:
        return [f"{len(df)} data rows, expected {N_FRAMES}"]
    return []


def _ordered_frame_problems(df: pd.DataFrame) -> list[str]:
    frames = pd.to_numeric(df.iloc[:, 0], errors="coerce")
    if frames.isna().any():
        bad = int(frames.isna().sum())
        return [f"{bad} frame value(s) are not integers"]
    expected = np.arange(N_FRAMES)
    if not np.array_equal(frames.to_numpy(), expected):
        first = int(np.flatnonzero(frames.to_numpy() != expected)[0])
        return [f"frame column is not 0..{N_FRAMES - 1} in order (first mismatch at row {first})"]
    return []


def submission_problems(df: pd.DataFrame) -> list[str]:
    """Every way `df` fails to be a submission file, as readable strings."""
    problems = _frame_problems(df, SUBMISSION_COLUMNS)
    if problems:
        return problems
    problems += _count_problems(df)
    if problems:
        return problems
    problems += _ordered_frame_problems(df)

    raw = df.iloc[:, 1]
    if raw.isna().any():
        problems.append(f"{int(raw.isna().sum())} blank label cell(s)")
        return problems
    labels = raw.astype(str).str.strip().str.upper()
    blank = labels == ""
    if blank.any():
        problems.append(f"{int(blank.sum())} blank label cell(s)")
        return problems
    unknown = sorted(set(labels) - set(LABELS))
    if unknown:
        problems.append(f"unknown label(s) {unknown}, allowed {list(LABELS)}")
    return problems


def artifact_problems(df: pd.DataFrame) -> list[str]:
    """Every way `df` fails to be an intermediate artifact, as readable strings."""
    problems = _frame_problems(df, ARTIFACT_COLUMNS)
    if problems:
        return problems
    problems += _count_problems(df)
    if problems:
        return problems
    problems += _ordered_frame_problems(df)

    numeric = df.copy()
    for column in ARTIFACT_COLUMNS[1:]:
        numeric[column] = pd.to_numeric(numeric[column], errors="coerce")
    if numeric[list(ARTIFACT_COLUMNS[1:])].isna().any().any():
        problems.append("non-numeric or blank value in a probability column")
        return problems

    for column in ARTIFACT_COLUMNS[1:]:
        values = numeric[column].to_numpy()
        if values.min() < -PROB_TOL or values.max() > 1 + PROB_TOL:
            problems.append(
                f"{column} outside [0, 1] (min {values.min():.3f}, max {values.max():.3f})"
            )

    totals = numeric[list(PROB_COLUMNS)].sum(axis=1).to_numpy()
    off = np.abs(totals - 1.0) > PROB_TOL
    if off.any():
        first = int(np.flatnonzero(off)[0])
        problems.append(
            f"{int(off.sum())} row(s) whose H/A/D probabilities do not sum to 1 "
            f"(row {first} sums to {totals[first]:.6f})"
        )
    return problems


def check_submission(df: pd.DataFrame, path: object = "<dataframe>") -> pd.DataFrame:
    """Raise ContractError unless `df` is a valid submission."""
    problems = submission_problems(df)
    if problems:
        raise ContractError(path, problems)
    return df


def check_artifact(df: pd.DataFrame, path: object = "<dataframe>") -> pd.DataFrame:
    """Raise ContractError unless `df` is a valid intermediate artifact."""
    problems = artifact_problems(df)
    if problems:
        raise ContractError(path, problems)
    return df


def read_submission(path: str | Path) -> pd.DataFrame:
    """Read and validate a submission file. Blank cells stay blank so they can be reported."""
    df = pd.read_csv(path, keep_default_na=False, dtype={"label": "str"})
    return check_submission(df, path)


def read_artifact(path: str | Path) -> pd.DataFrame:
    """Read and validate an intermediate artifact file."""
    df = pd.read_csv(path)
    return check_artifact(df, path)
