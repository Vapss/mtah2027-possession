"""The data guard must block the files that would violate the licence, and nothing else.

The submission repository is public and the match data is licensed for the competition only, so
these are not style checks: committing the bundle is redistribution.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tools.guard_data import main, offences


def test_archive_is_blocked(tmp_path) -> None:
    archive = tmp_path / "match.zip"
    archive.write_bytes(b"PK\x03\x04 not really a zip")
    assert offences([archive])


def test_video_is_blocked(tmp_path) -> None:
    video = tmp_path / "BAR-ATH_tactical.mp4"
    video.write_bytes(b"\x00" * 16)
    assert any("mp4" in problem for problem in offences([video]))


def test_oversized_file_is_blocked(tmp_path) -> None:
    big = tmp_path / "export.csv"
    big.write_bytes(b"0" * 6_000_000)
    assert any("MB" in problem for problem in offences([big]))


def test_data_directory_is_blocked(repo_root) -> None:
    """The bundle is redistribution; the one committed README in data/ is not."""
    assert offences([repo_root / "data" / "README.md"]) == []

    bundled = repo_root / "data" / "tactical" / "BAR-ATH_tactical_atd.txt"
    if not bundled.is_file():
        pytest.skip("match bundle not unpacked")
    assert any("data/" in problem for problem in offences([bundled]))


def test_source_file_is_allowed(tmp_path) -> None:
    source = tmp_path / "solver.py"
    source.write_text("print('hello')\n", encoding="utf-8")
    assert offences([source]) == []


def test_exit_status_signals_a_blocked_file(tmp_path, capsys) -> None:
    archive = tmp_path / "bundle.zip"
    archive.write_bytes(b"PK\x03\x04")
    assert main([str(archive)]) == 1
    assert "refusing to commit" in capsys.readouterr().out


def test_exit_status_is_zero_when_clean(tmp_path, capsys) -> None:
    source = tmp_path / "clean.py"
    source.write_text("x = 1\n", encoding="utf-8")
    assert main([str(source)]) == 0
    assert "data guard ok" in capsys.readouterr().out


def test_repository_itself_is_clean(capsys) -> None:
    """The real check: nothing currently staged or untracked would violate the licence."""
    code = main([])
    output = capsys.readouterr().out
    assert code == 0, output
    assert "data guard ok" in output


def test_guard_does_not_need_third_party_imports() -> None:
    """It runs in pre-commit before the environment exists, so stdlib only."""
    text = Path(__file__).resolve().parent.parent / "tools" / "guard_data.py"
    source = text.read_text(encoding="utf-8")
    forbidden = [
        name for name in ("import numpy", "import pandas", "import pytest") if name in source
    ]
    assert forbidden == [], f"guard_data.py must stay stdlib-only, found {forbidden}"
