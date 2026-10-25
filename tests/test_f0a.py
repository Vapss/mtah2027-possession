"""F0a must close the chain and reproduce the pinned public-slice number.

These tests run the real CLIs (onehot -> assemble -> official validator -> scorer) in a temporary
workspace with the ledger redirected, so the suite never touches `runs/f0a/` or the team ledger.
"""

from __future__ import annotations

import json

import pandas as pd
import pytest

from tools import f0a


def test_f0a_closes_the_chain_and_records_the_published_value(tmp_path) -> None:
    ledger = tmp_path / "ledger.jsonl"
    workdir = tmp_path / "f0a"

    code = f0a.main(
        [
            "--workdir",
            str(workdir),
            "--ledger",
            str(ledger),
            "--bootstrap",
            "0",
            "--note",
            "pytest",
        ]
    )

    assert code == 0
    entry = json.loads(ledger.read_text(encoding="utf-8").strip().splitlines()[-1])
    scored = entry["submissions"]
    assert len(scored) == 1
    assert scored[0]["submission"] == "submission"
    assert scored[0]["spell_f1_mean"] == pytest.approx(f0a.EXPECTED_SPELL_F1, abs=1e-6)
    assert scored[0]["macro_f1"] == pytest.approx(f0a.EXPECTED_MACRO_F1, abs=1e-6)

    assert (workdir / "artifacts" / f0a.ARTIFACT_NAME).is_file()
    assert (workdir / "submission.csv").is_file()
    assert (workdir / "submission_summary.json").is_file()


def test_f0a_does_not_score_a_pipeline_that_moved() -> None:
    row = pd.Series({"spell_f1_mean": 0.325581, "macro_f1": 0.620733})

    with pytest.raises(ValueError, match="assembly path"):
        f0a.check_expected(row, expected_spell_f1=0.5, expected_macro_f1=0.620733, tolerance=1e-6)


def test_f0a_refuses_a_workspace_with_another_artifact(tmp_path) -> None:
    artifacts = tmp_path / "artifacts"
    artifacts.mkdir()
    (artifacts / "possession.csv").write_text("frame,p_home,p_away,p_dead,confidence\n")

    with pytest.raises(ValueError, match="clean --workdir"):
        f0a.build_submission(f0a.BASELINE, tmp_path)
