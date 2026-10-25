"""Rebuild and verify the ignored B6 evidence files against the checked-in manifest."""

from __future__ import annotations

import hashlib
import json
import platform
import sys
from pathlib import Path

import numpy as np
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

import games  # noqa: E402
from tools.compare_submissions import compare_files, resolve_ground_truth  # noqa: E402
from tools.contract import check_submission, read_artifact  # noqa: E402
from tools.postprocess import postprocess  # noqa: E402

MANIFEST = REPO_ROOT / "docs/evidence/b6_public_manifest.json"
ARTIFACT = REPO_ROOT / "artifacts/possession.csv"
BASELINE = REPO_ROOT / "runs/argmin_baseline.csv"
POSTPROCESSED = REPO_ROOT / "runs/postprocessed.csv"
COMPARISON = REPO_ROOT / "runs/postprocess_comparison.json"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _current_versions() -> dict[str, str]:
    return {
        "python": platform.python_version(),
        "numpy": np.__version__,
        "pandas": pd.__version__,
    }


def _make_baseline() -> None:
    if not ARTIFACT.is_file():
        raise FileNotFoundError(
            "missing artifacts/possession.csv; generate it with the licensed tactical bundle: "
            "python tools/emision.py --output artifacts/possession.csv"
        )
    artifact = read_artifact(ARTIFACT)
    predicted = artifact[["p_home", "p_away"]].idxmax(axis=1).map({"p_home": "H", "p_away": "A"})
    predicted.loc[artifact["confidence"] == 0] = "X"
    baseline = check_submission(
        pd.DataFrame({"frame": artifact["frame"], "label": predicted}), BASELINE
    )
    BASELINE.parent.mkdir(parents=True, exist_ok=True)
    baseline.to_csv(BASELINE, index=False, lineterminator="\n")


def _make_postprocessed() -> None:
    source = check_submission(pd.read_csv(BASELINE), BASELINE)
    before = source["label"].astype(str).str.strip().str.upper().tolist()
    runs = [(start, stop + 1) for _half, start, stop in games.half_video_blocks(games.GAME)]
    after = postprocess(before, runs)
    result = check_submission(
        pd.DataFrame({"frame": source["frame"], "label": after}), POSTPROCESSED
    )
    POSTPROCESSED.parent.mkdir(parents=True, exist_ok=True)
    result.to_csv(POSTPROCESSED, index=False, lineterminator="\n")


def _make_comparison() -> dict[str, object]:
    comparison = compare_files(BASELINE, POSTPROCESSED, resolve_ground_truth("public"))
    COMPARISON.parent.mkdir(parents=True, exist_ok=True)
    COMPARISON.write_text(json.dumps(comparison, indent=2, sort_keys=True) + "\n")
    return comparison


def _comparison_metrics(comparison: dict[str, object]) -> dict[str, object]:
    before = comparison["a"]
    after = comparison["b"]
    sign = comparison["sign_diagnostic"]
    per_iou = comparison["per_iou"]
    return {
        "n_gt": comparison["n_gt_possessions"],
        "n_pred_before": before["n_pred"],
        "n_pred_after": after["n_pred"],
        "delta_mean_spell_f1": comparison["delta_mean_spell_f1_b_minus_a"],
        "n_discordant": sign["n_discordant"],
        "sign_test_p": sign["exact_two_sided_p"],
        "by_iou": {
            iou: {
                side: {
                    "tp": values["n_matched"],
                    "fp": values["n_spurious"],
                    "fn": values["n_missed"],
                    "precision": (
                        values["n_matched"] / (values["n_matched"] + values["n_spurious"])
                        if values["n_matched"] + values["n_spurious"]
                        else 0.0
                    ),
                    "recall": (
                        values["n_matched"] / (values["n_matched"] + values["n_missed"])
                        if values["n_matched"] + values["n_missed"]
                        else 0.0
                    ),
                    "f1": values["spell_f1"],
                }
                for side, values in (("before", per_iou[iou]["a"]), ("after", per_iou[iou]["b"]))
            }
            for iou in ("0.3", "0.5", "0.7")
        },
    }


def verify() -> str:
    manifest = json.loads(MANIFEST.read_text())
    expected_hashes = manifest["hashes_sha256"]
    if not ARTIFACT.is_file():
        _make_baseline()
    actual_artifact_hash = _sha256(ARTIFACT)
    expected_artifact_hash = expected_hashes["artifacts/possession.csv"]
    if actual_artifact_hash != expected_artifact_hash:
        raise ValueError(
            "artifacts/possession.csv SHA-256 mismatch: "
            f"expected {expected_artifact_hash}, got {actual_artifact_hash}"
        )

    versions = _current_versions()
    if versions != manifest["versions"]:
        raise ValueError(
            f"runtime versions differ: expected {manifest['versions']}, got {versions}"
        )

    _make_baseline()
    _make_postprocessed()
    comparison = _make_comparison()
    actual_metrics = _comparison_metrics(comparison)
    if actual_metrics != manifest["comparison"]:
        raise ValueError(
            "comparison metrics differ from manifest:\n"
            + json.dumps({"expected": manifest["comparison"], "actual": actual_metrics}, indent=2)
        )

    actual_hashes = {
        "artifacts/possession.csv": _sha256(ARTIFACT),
        "runs/argmin_baseline.csv": _sha256(BASELINE),
        "runs/postprocessed.csv": _sha256(POSTPROCESSED),
        "runs/postprocess_comparison.json": _sha256(COMPARISON),
    }
    mismatches = {
        name: {"expected": expected_hashes[name], "actual": actual}
        for name, actual in actual_hashes.items()
        if expected_hashes[name] != actual
    }
    if mismatches:
        raise ValueError("evidence file hash mismatch:\n" + json.dumps(mismatches, indent=2))
    return _sha256(MANIFEST)


def main() -> int:
    try:
        manifest_hash = verify()
    except (OSError, KeyError, ValueError) as error:
        print(f"FAIL verify-b6: {error}", file=sys.stderr)
        return 1
    print(f"OK verify-b6 manifest_sha256={manifest_hash}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
