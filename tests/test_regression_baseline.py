"""Running the reference baseline must leave the committed artifacts untouched.

This is the cheapest honest proof that the pipeline and the data are what the repository says
they are. It needs the gated match bundle, so it skips (loudly) when the bundle is absent rather
than pretending to have checked anything.
"""

from __future__ import annotations

import subprocess
import sys

from _bundle import requires_bundle


@requires_bundle
def test_baseline_regenerates_committed_results(repo_root) -> None:
    subprocess.run(
        [sys.executable, "starter/baseline.py"],
        cwd=repo_root,
        check=True,
        capture_output=True,
        text=True,
    )

    diff = subprocess.run(
        ["git", "diff", "--exit-code", "--", "evaluation/results"],
        cwd=repo_root,
        capture_output=True,
        text=True,
    )

    assert diff.returncode == 0, (
        "starter/baseline.py no longer reproduces the committed baseline CSVs:\n" + diff.stdout
    )


@requires_bundle
def test_regenerated_baselines_still_score_the_published_value(repo_root) -> None:
    """Regeneration plus scoring: the two halves of reproducibility in one test."""
    board = subprocess.run(
        [sys.executable, "evaluation/run_evaluation.py", "--no-detail"],
        cwd=repo_root,
        capture_output=True,
        text=True,
        check=True,
    )
    assert "baseline_smooth125" in board.stdout
    assert "0.4242" in board.stdout
