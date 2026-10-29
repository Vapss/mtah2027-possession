"""Running the reference baseline must reproduce the committed artifacts.

This is the cheapest honest proof that the pipeline and the data are what the repository says
they are. It needs the gated match bundle, so it skips (loudly) when the bundle is absent rather
than pretending to have checked anything.
"""

from __future__ import annotations

import fnmatch
import os
import subprocess
import sys
import tempfile
from pathlib import Path

from _bundle import requires_bundle

BASELINES = "evaluation/results/baseline_*.csv"


def _git(repo_root: Path, *args: str) -> bytes:
    return subprocess.run(["git", *args], cwd=repo_root, check=True, capture_output=True).stdout


def _normalise(data: bytes) -> bytes:
    # `starter/baseline.py` opens its output without newline="", so on Windows it writes CRLF.
    # It is the organisers' file and read-only (AGENTS.md rule 7). Everywhere else the bytes must
    # match exactly, line ends included.
    return data.replace(b"\r\n", b"\n") if os.name == "nt" else data


def _first_difference(expected: bytes, got: bytes) -> int:
    """1-based line of the first difference; a truncated file differs just after its end."""
    a, b = expected.split(b"\n"), got.split(b"\n")
    for line, (x, y) in enumerate(zip(a, b), start=1):
        if x != y:
            return line
    return min(len(a), len(b)) + 1


@requires_bundle
def test_baseline_regenerates_committed_results(repo_root) -> None:
    # Regenerate into a scratch directory, never over evaluation/results: on a mismatch the
    # committed files would be left modified in the working tree, one `git add .` away from a bad
    # commit. The scratch lives under the gitignored runs/, not pytest's tmp_path, because
    # baseline.py calls os.path.relpath(out, repo) and that raises on Windows when the checkout
    # and %TEMP% sit on different drives.
    scratch_root = repo_root / "runs"
    scratch_root.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(dir=scratch_root) as scratch:
        out = Path(scratch)
        run = subprocess.run(
            [sys.executable, "starter/baseline.py", "--out", str(out)],
            cwd=repo_root,
            capture_output=True,
            text=True,
        )
        assert run.returncode == 0, run.stdout + run.stderr
        _assert_matches_head(repo_root, out)


def _assert_matches_head(repo_root: Path, out: Path) -> None:
    # The reference is HEAD, not the working tree: a baseline someone regenerated in place, or an
    # extra variant written by `baseline.py --window`, must not become what the test compares to.
    listed = _git(repo_root, "ls-tree", "-r", "--name-only", "HEAD", "--", "evaluation/results")
    tracked = [p for p in listed.decode().splitlines() if fnmatch.fnmatch(p, BASELINES)]
    assert tracked, "no committed baselines in HEAD"
    assert sorted(Path(p).name for p in tracked) == sorted(p.name for p in out.glob("*.csv"))

    for path in tracked:
        expected = _git(repo_root, "show", f"HEAD:{path}")
        got = _normalise((out / Path(path).name).read_bytes())
        assert got == expected, (
            f"starter/baseline.py no longer reproduces {path}: first difference at line "
            f"{_first_difference(expected, got)}"
        )


@requires_bundle
def test_committed_baselines_score_the_published_value(repo_root) -> None:
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
