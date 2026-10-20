"""The assembler must be label-preserving, deterministic, and the only writer.

The round-trip test is the important one: encode a shipped baseline as probabilities, assemble it
back, and demand the file be byte-identical. If that ever fails, the assembler is changing labels
somewhere a teammate cannot see it.
"""

from __future__ import annotations

import subprocess
import sys

import numpy as np
import pytest

from tools.assemble import combine, decide, find_artifacts, write_submission
from tools.contract import N_FRAMES, ContractError, check_submission, read_submission
from tools.onehot import onehot

SHIPPED = "evaluation/results/baseline_smooth125.csv"


def test_round_trip_of_a_shipped_baseline_is_byte_identical(tmp_path, repo_root) -> None:
    original = repo_root / SHIPPED
    table = read_submission(original)

    artifact = onehot(table.iloc[:, 1])
    assembled = decide(combine({"baseline.csv": artifact}))
    written = write_submission(assembled, tmp_path / "submission.csv")

    assert written.read_bytes() == original.read_bytes()


def test_confidence_decides_when_artifacts_disagree(artifact_factory) -> None:
    sure_home = artifact_factory(p_home=1.0, p_away=0.0, p_dead=0.0, confidence=0.9)
    sure_away = artifact_factory(p_home=0.0, p_away=1.0, p_dead=0.0, confidence=0.1)

    combined = combine({"a_sure_home.csv": sure_home, "b_sure_away.csv": sure_away})
    labels = decide(combined)["label"]

    assert set(labels) == {"H"}


def test_explicit_weight_overrides_confidence(artifact_factory) -> None:
    sure_home = artifact_factory(p_home=1.0, p_away=0.0, p_dead=0.0, confidence=0.1)
    sure_away = artifact_factory(p_home=0.0, p_away=1.0, p_dead=0.0, confidence=0.2)

    combined = combine({"a.csv": sure_home, "b.csv": sure_away}, weights={"a.csv": 10.0})
    assert set(decide(combined)["label"]) == {"H"}


def test_all_zero_confidence_falls_back_to_unweighted_mean(artifact_factory) -> None:
    silent = artifact_factory(p_home=1.0, p_away=0.0, p_dead=0.0, confidence=0.0)

    combined = combine({"silent.csv": silent})

    assert not combined.isna().any().any()
    assert set(decide(combined)["label"]) == {"H"}


def test_abstain_below_marks_frames_as_x(artifact_factory) -> None:
    weak = artifact_factory(p_home=0.40, p_away=0.30, p_dead=0.30, confidence=1.0)

    labels = decide(combine({"weak.csv": weak}), abstain_below=0.5)["label"]

    assert set(labels) == {"X"}


def test_abstain_below_zero_never_abstains(artifact_factory) -> None:
    weak = artifact_factory(p_home=0.40, p_away=0.30, p_dead=0.30, confidence=1.0)

    labels = decide(combine({"weak.csv": weak}), abstain_below=0.0)["label"]

    assert "X" not in set(labels)


def test_x_outside_halves_only_touches_frames_outside_play(artifact_factory) -> None:
    """Half 1 is video 11185..90651, half 2 is 110808..190197, per games.py."""
    certain = artifact_factory(p_home=0.0, p_away=0.0, p_dead=1.0, confidence=1.0)

    labels = decide(combine({"certain.csv": certain}), x_outside_halves=True)["label"].to_numpy()

    assert labels[0] == "X"  # before kickoff
    assert labels[11184] == "X"  # one frame before kickoff
    assert labels[11185] == "D"  # kickoff
    assert labels[90651] == "D"  # last frame of the first half
    assert labels[90652] == "X"  # halftime
    assert labels[110807] == "X"  # still halftime
    assert labels[110808] == "D"  # second half
    assert labels[190197] == "D"  # final whistle
    assert labels[N_FRAMES - 1] == "X"


def test_assembled_submission_passes_the_official_validator(tmp_path, repo_root) -> None:
    table = read_submission(repo_root / SHIPPED)
    assembled = decide(combine({"baseline.csv": onehot(table.iloc[:, 1])}))
    written = write_submission(assembled, tmp_path / "submission.csv")

    completed = subprocess.run(
        [sys.executable, "evaluation/validate_submission.py", str(written)],
        cwd=repo_root,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 0, completed.stdout + completed.stderr
    assert "Valid" in completed.stdout


def test_assembler_refuses_an_invalid_artifact(tmp_path, artifact_factory, repo_root) -> None:
    broken = artifact_factory(p_home=0.5, p_away=0.5, p_dead=0.5)
    directory = tmp_path / "artifacts"
    directory.mkdir()
    broken.to_csv(directory / "broken.csv", index=False)

    import pandas as pd

    from tools.contract import check_artifact

    with pytest.raises(ContractError, match="sum to 1"):
        check_artifact(pd.read_csv(directory / "broken.csv"))


def test_missing_artifacts_directory_is_a_readable_error(tmp_path) -> None:
    with pytest.raises(SystemExit, match="no artifact CSV"):
        find_artifacts(tmp_path)


def test_assembler_output_is_always_contract_valid(artifact_factory) -> None:
    """Whatever the weights do, the writer's output must still satisfy the contract."""
    tables = {
        "one.csv": artifact_factory(p_home=0.34, p_away=0.33, p_dead=0.33, confidence=0.4),
        "two.csv": artifact_factory(p_home=0.10, p_away=0.10, p_dead=0.80, confidence=0.7),
    }
    submission = decide(combine(tables))
    check_submission(submission)
    assert np.isfinite(combine(tables).to_numpy()).all()
