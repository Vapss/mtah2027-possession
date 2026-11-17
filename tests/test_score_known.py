"""A known submission must score its known value, and scoring must be repeatable.

This is the test that notices if the metric itself moves: `evaluation/` is the organisers' code
and nobody on the team should edit it, but a stray change to the results directory, a pandas
upgrade, or an accidental filter would show up here as a number that no longer matches the
published board.
"""

from __future__ import annotations

import shutil
import subprocess
import sys

import pandas as pd
import pytest

SHIPPED = "evaluation/results/baseline_smooth125.csv"

# The published board values for that baseline, pinned here on purpose.
# `evaluation/scoreboard.csv` is gitignored by the organisers (`.gitignore:27`), so a clean clone --
# which is what CI and every teammate starts from -- has no board to read. Reading it made this test
# pass locally and fail on the first push.
EXPECTED_MACRO_F1 = 0.581185
EXPECTED_SPELL_F1 = 0.424242


def score_one(tmp_path, repo_root, source: str) -> pd.DataFrame:
    """Score a single submission in an isolated results directory."""
    results = tmp_path / "results"
    results.mkdir(parents=True, exist_ok=True)
    shutil.copy(repo_root / source, results / "candidate.csv")
    out = tmp_path / "score"

    subprocess.run(
        [
            sys.executable,
            "evaluation/run_evaluation.py",
            "--gt",
            "public",
            "--results",
            str(results),
            "--out",
            str(out),
            "--no-detail",
        ],
        cwd=repo_root,
        check=True,
        capture_output=True,
        text=True,
    )
    return pd.read_csv(out / "scoreboard.csv")


def test_known_submission_scores_the_published_value(tmp_path, repo_root) -> None:
    board = score_one(tmp_path, repo_root, SHIPPED)
    row = board.iloc[0]

    assert row["submission"] == "candidate"
    assert row["macro_f1"] == pytest.approx(EXPECTED_MACRO_F1, abs=1e-6)
    assert row["spell_f1_mean"] == pytest.approx(EXPECTED_SPELL_F1, abs=1e-6)

    # If a colleague has run the scorer locally the board exists; use it as a second opinion, but
    # never as the source of truth -- it is gitignored and absent from every clean clone.
    published = repo_root / "evaluation" / "scoreboard.csv"
    if published.is_file():
        expected = pd.read_csv(published).set_index("submission").loc["baseline_smooth125"]
        assert row["macro_f1"] == pytest.approx(expected["macro_f1"], abs=1e-6)
        assert row["spell_f1_mean"] == pytest.approx(expected["spell_f1_mean"], abs=1e-6)


def test_scoring_is_deterministic(tmp_path, repo_root) -> None:
    first = score_one(tmp_path / "one", repo_root, SHIPPED)
    second = score_one(tmp_path / "two", repo_root, SHIPPED)
    pd.testing.assert_frame_equal(first, second)


def test_the_ranked_metric_is_spell_f1(tmp_path, repo_root) -> None:
    """Guard against optimising the wrong column: macroF1 ranks this baseline fourth."""
    board = score_one(tmp_path, repo_root, SHIPPED)
    assert "spell_f1_mean" in board.columns
    assert board.iloc[0]["spell_f1_mean"] > 0.0
