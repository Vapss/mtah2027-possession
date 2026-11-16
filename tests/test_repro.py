"""#15: the delivered file is rebuilt twice and compared; unsafe backup workdirs are refused."""

from __future__ import annotations

from pathlib import Path

import pytest
from _bundle import requires_bundle

from docs.paper.build import expected_sha256
from tools import backup, repro

ONE = b"frame,label\n0,H\n"
OTHER = b"frame,label\n0,A\n"


@pytest.mark.parametrize("workdir", ["runs", ".", "submissions/x", "../elsewhere"])
def test_backup_refuses_a_workdir_outside_runs(workdir: str) -> None:
    # The workdir is wiped before the build: anything but a subdirectory of runs/ is refused.
    with pytest.raises(ValueError, match="subdirectory of runs/"):
        backup.build(backup.REPO_ROOT / workdir, backup.REPO_ROOT / "runs" / "x.csv")


def _fake_chain(contents: list[bytes]):
    calls = iter(contents)

    def build(workdir: Path, out: Path) -> Path:
        out.write_bytes(next(calls))
        return out

    return build


@pytest.fixture
def isolated(monkeypatch, tmp_path):
    """Point runs/ and the repro workdir at tmp_path, and prove the real ones are not touched."""
    real = repro.WORKDIR
    before = sorted(real.rglob("*")) if real.exists() else None
    monkeypatch.setattr(backup, "RUNS", tmp_path.resolve())
    monkeypatch.setattr(repro, "WORKDIR", tmp_path.resolve() / "repro")
    yield tmp_path
    after = sorted(real.rglob("*")) if real.exists() else None
    assert before == after, "a fake-chain test wrote into the real runs/repro"


def test_identical_builds_report_one_hash(monkeypatch, isolated, capsys) -> None:
    monkeypatch.setitem(repro.CHAINS, "fake", _fake_chain([ONE, ONE]))
    assert repro.main(["--chain", "fake"]) == 0
    assert "reproducible: fake sha256" in capsys.readouterr().out
    assert (isolated / "repro" / "a" / "submission.csv").exists()


def test_different_builds_fail(monkeypatch, isolated, capsys) -> None:
    monkeypatch.setitem(repro.CHAINS, "fake", _fake_chain([ONE, OTHER]))
    assert repro.main(["--chain", "fake"]) == 1
    assert "NOT reproducible" in capsys.readouterr().err


def test_builds_that_agree_but_differ_from_the_delivered_file_fail(
    monkeypatch, isolated, capsys
) -> None:
    delivered = isolated / "delivered.csv"
    delivered.write_bytes(OTHER)
    monkeypatch.setitem(repro.CHAINS, "fake", _fake_chain([ONE, ONE]))
    assert repro.main(["--chain", "fake", "--against", str(delivered)]) == 1
    assert "no longer regenerates the delivered file" in capsys.readouterr().err

    delivered.write_bytes(ONE)
    monkeypatch.setitem(repro.CHAINS, "fake", _fake_chain([ONE, ONE]))
    assert repro.main(["--chain", "fake", "--against", str(delivered)]) == 0


def test_each_build_starts_from_an_empty_directory(monkeypatch, isolated) -> None:
    seen = []

    def build(workdir: Path, out: Path) -> Path:
        seen.append(sorted(p.name for p in workdir.iterdir()))
        (workdir / "cache.bin").write_bytes(b"stale")
        out.write_bytes(ONE)
        return out

    monkeypatch.setitem(repro.CHAINS, "fake", build)
    repro.repro("fake")
    repro.repro("fake")
    assert seen == [[], [], [], []]


@requires_bundle
def test_the_backup_is_reproducible_and_is_the_published_file() -> None:
    first, second = repro.repro("backup")
    assert first == second
    # DECISIONS 25: the safety-net entry's SHA-256. A change here is a change of the delivered file.
    assert first.startswith("cb4eeef3617f")


@requires_bundle
def test_the_engine_is_reproducible_and_is_the_candidate_entry() -> None:
    first, second = repro.repro("engine")
    assert first == second
    # DECISIONS 30-36: the candidate entry's SHA-256. A change here changes the delivered file.
    assert first == expected_sha256()
