"""Running the reference baseline must reproduce the committed artifacts.

This is the cheapest honest proof that the pipeline and the data are what the repository says
they are. It needs the gated match bundle, so it skips (loudly) when the bundle is absent rather
than pretending to have checked anything.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from _bundle import requires_bundle


def _lines(path: Path) -> list[bytes]:
    # `starter/baseline.py` opens its output without newline="", so on Windows it writes CRLF.
    # It is the organisers' file and read-only (AGENTS.md rule 7): compare content, not line ends.
    return path.read_bytes().replace(b"\r\n", b"\n").split(b"\n")


@requires_bundle
def test_baseline_regenerates_committed_results(repo_root, tmp_path) -> None:
    # Regenerate into tmp_path, never over evaluation/results: on a mismatch the committed files
    # would be left modified in the working tree, one `git add .` away from a bad commit.
    subprocess.run(
        [sys.executable, "starter/baseline.py", "--out", str(tmp_path)],
        cwd=repo_root,
        check=True,
        capture_output=True,
        text=True,
    )

    committed = sorted((repo_root / "evaluation" / "results").glob("baseline_*.csv"))
    assert [p.name for p in committed] == sorted(p.name for p in tmp_path.glob("*.csv"))

    for path in committed:
        expected, got = _lines(path), _lines(tmp_path / path.name)
        first = next((i for i, (e, g) in enumerate(zip(expected, got), start=1) if e != g), None)
        assert first is None and len(expected) == len(got), (
            f"starter/baseline.py no longer reproduces {path.name}: "
            f"first difference at line {first}, {len(got)} lines vs {len(expected)} committed"
        )


@requires_bundle
def test_regenerated_baselines_still_score_the_published_value(repo_root) -> None:
    """The committed baselines still score the published value, so the board is the README's."""
    board = subprocess.run(
        [sys.executable, "evaluation/run_evaluation.py", "--no-detail"],
        cwd=repo_root,
        capture_output=True,
        text=True,
        check=True,
    )
    assert "baseline_smooth125" in board.stdout
    assert "0.4242" in board.stdout
