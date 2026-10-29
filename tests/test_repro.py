"""#15: the delivered file is rebuilt twice and compared; unsafe backup workdirs are refused."""

from __future__ import annotations

from pathlib import Path

import pytest
from _bundle import requires_bundle

from tools import backup, repro


@pytest.mark.parametrize("workdir", ["runs", ".", "submissions/x", "../elsewhere"])
def test_backup_refuses_a_workdir_outside_runs(workdir: str) -> None:
    # The workdir is wiped before the build: anything but a subdirectory of runs/ is refused.
    with pytest.raises(ValueError, match="subdirectory of runs/"):
        backup.build(backup.REPO_ROOT / workdir, backup.REPO_ROOT / "runs" / "x.csv")


def _fake_chain(contents: list[bytes]):
    calls = iter(contents)

    def build(workdir: Path, out: Path) -> Path:
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(next(calls))
        return out

    return build


def test_identical_builds_report_one_hash(monkeypatch, tmp_path, capsys) -> None:
    monkeypatch.setitem(repro.CHAINS, "fake", _fake_chain([b"frame,label\n0,X\n"] * 2))
    monkeypatch.setattr(repro, "WORKDIR", tmp_path)
    assert repro.main(["--chain", "fake"]) == 0
    assert "reproducible: fake sha256" in capsys.readouterr().out


def test_different_builds_fail(monkeypatch, tmp_path, capsys) -> None:
    monkeypatch.setitem(
        repro.CHAINS, "fake", _fake_chain([b"frame,label\n0,H\n", b"frame,label\n0,A\n"])
    )
    monkeypatch.setattr(repro, "WORKDIR", tmp_path)
    assert repro.main(["--chain", "fake"]) == 1
    assert "NOT reproducible" in capsys.readouterr().err


@requires_bundle
def test_the_backup_is_reproducible_and_is_the_published_file() -> None:
    first, second = repro.repro("backup")
    assert first == second
    # DECISIONS 25: the safety-net entry's SHA-256. A change here is a change of the delivered file.
    assert first.startswith("cb4eeef3617f")
