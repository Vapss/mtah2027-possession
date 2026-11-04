"""Prove Python builds and their subprocesses can be monitored for ground-truth access."""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest
from _bundle import requires_bundle

ROOT = Path(__file__).resolve().parent.parent
GUARD = Path(__file__).parent / "gt_guard"


def guarded(code: str, *args: str, synthetic: bool = False) -> subprocess.CompletedProcess:
    env = os.environ.copy()
    env["POSSESSION_GT_GUARD_ROOT"] = str(ROOT)
    env["POSSESSION_SYNTHETIC_BUILD"] = "1" if synthetic else "0"
    env["PYTHONPATH"] = os.pathsep.join((str(GUARD), str(ROOT), env.get("PYTHONPATH", "")))
    with tempfile.TemporaryDirectory(prefix="gt-audit-") as directory:
        log = Path(directory) / "attempts.log"
        started = Path(directory) / "started.log"
        env["POSSESSION_GT_GUARD_LOG"] = str(log)
        env["POSSESSION_GT_GUARD_STARTED"] = str(started)
        result = subprocess.run(
            [sys.executable, "-c", code, *args], cwd=ROOT, env=env, capture_output=True, text=True
        )
        result.gt_attempted = log.exists()
        result.guarded_processes = (
            len(set(started.read_text().splitlines())) if started.exists() else 0
        )
        return result


@pytest.mark.parametrize("child", [False, True])
def test_guard_rejects_read_in_parent_and_subprocess(child: bool) -> None:
    # Even a nonexistent filename is refused before access, so no match data is read.
    read = "open('evaluation/gt/nonexistent.csv').read()"
    code = (
        "import subprocess, sys; subprocess.run([sys.executable, '-c', "
        + repr(read)
        + "], check=True)"
        if child
        else read
    )
    result = guarded(code)
    assert result.returncode != 0
    assert result.gt_attempted
    assert "GT access forbidden during submission build" in result.stderr


def test_guard_records_a_blocked_read_even_when_caught() -> None:
    code = "try:\n open('evaluation/gt/nonexistent.csv')\nexcept PermissionError:\n pass"
    result = guarded(code)
    assert result.returncode == 0
    assert result.gt_attempted


def test_repro_build_runs_with_synthetic_inputs_and_gt_guard() -> None:
    # Work directories are restricted to runs/ by the real pipeline; use a fresh child there.
    runs = ROOT / "runs"
    runs.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="gt-guard-", dir=runs) as workdir:
        code = (
            "from pathlib import Path; import sys; from tools import repro; "
            "a,b = repro.repro(workdir=Path(sys.argv[1])); assert a == b"
        )
        result = guarded(code, workdir, synthetic=True)
    assert result.returncode == 0, result.stderr
    assert not result.gt_attempted
    # repro + 2 builds * (engine, assembler, validator): a dropped hook must not pass silently.
    assert result.guarded_processes >= 7


@requires_bundle
def test_repro_build_with_real_inputs_never_opens_ground_truth() -> None:
    runs = ROOT / "runs"
    runs.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="gt-guard-real-", dir=runs) as workdir:
        code = (
            "from pathlib import Path; import sys; from tools import repro; "
            "a,b = repro.repro(workdir=Path(sys.argv[1])); assert a == b"
        )
        result = guarded(code, workdir)
    assert result.returncode == 0, result.stderr
    assert not result.gt_attempted
    assert result.guarded_processes >= 7
