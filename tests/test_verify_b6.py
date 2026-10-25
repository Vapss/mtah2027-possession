import hashlib
import json

import pytest

from tools import verify_b6


def test_version_mismatch_warns_and_verification_continues(tmp_path, monkeypatch, capsys):
    artifact = tmp_path / "artifact.csv"
    artifact.write_bytes(b"artifact")
    baseline = tmp_path / "baseline.csv"
    postprocessed = tmp_path / "postprocessed.csv"
    comparison_path = tmp_path / "comparison.json"
    manifest_path = tmp_path / "manifest.json"
    expected_comparison = {}
    generated = {
        "baseline": (baseline, b"baseline"),
        "postprocessed": (postprocessed, b"postprocessed"),
        "comparison": (comparison_path, b"{}\n"),
    }
    hashes = {
        "artifacts/possession.csv": hashlib.sha256(b"artifact").hexdigest(),
        "runs/argmin_baseline.csv": hashlib.sha256(b"baseline").hexdigest(),
        "runs/postprocessed.csv": hashlib.sha256(b"postprocessed").hexdigest(),
        "runs/postprocess_comparison.json": hashlib.sha256(b"{}\n").hexdigest(),
    }
    manifest_path.write_text(
        json.dumps(
            {
                "hashes_sha256": hashes,
                "versions_diagnostic": {"python": "other"},
                "comparison": {},
            }
        )
    )
    monkeypatch.setattr(verify_b6, "MANIFEST", manifest_path)
    monkeypatch.setattr(verify_b6, "ARTIFACT", artifact)
    monkeypatch.setattr(verify_b6, "BASELINE", baseline)
    monkeypatch.setattr(verify_b6, "POSTPROCESSED", postprocessed)
    monkeypatch.setattr(verify_b6, "COMPARISON", comparison_path)
    monkeypatch.setattr(verify_b6, "_current_versions", lambda: {"python": "current"})

    def write_generated(key):
        path, contents = generated[key]
        path.write_bytes(contents)
        return expected_comparison if key == "comparison" else None

    monkeypatch.setattr(verify_b6, "_make_baseline", lambda: write_generated("baseline"))
    monkeypatch.setattr(verify_b6, "_make_postprocessed", lambda: write_generated("postprocessed"))
    monkeypatch.setattr(verify_b6, "_make_comparison", lambda: write_generated("comparison"))
    monkeypatch.setattr(verify_b6, "_comparison_metrics", lambda _comparison: {})

    result = verify_b6.verify()

    assert result == hashlib.sha256(manifest_path.read_bytes()).hexdigest()
    assert "WARN verify-b6: runtime versions differ" in capsys.readouterr().err


def test_strict_versions_rejects_mismatch(tmp_path, monkeypatch):
    artifact = tmp_path / "artifact.csv"
    artifact.write_bytes(b"artifact")
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(
        json.dumps(
            {
                "versions_diagnostic": {"python": "expected"},
                "hashes_sha256": {
                    "artifacts/possession.csv": hashlib.sha256(b"artifact").hexdigest()
                },
            }
        )
    )
    monkeypatch.setattr(verify_b6, "MANIFEST", manifest_path)
    monkeypatch.setattr(verify_b6, "ARTIFACT", artifact)
    monkeypatch.setattr(verify_b6, "_current_versions", lambda: {"python": "actual"})

    with pytest.raises(ValueError, match="runtime versions differ"):
        # Stop after the version check; artifact handling is irrelevant to strict mode.
        verify_b6.verify(strict_versions=True)
