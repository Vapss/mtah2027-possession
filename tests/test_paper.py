"""The delivery reference must survive a changed candidate and a Windows checkout."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from docs.paper import build

REVISION = "a" * 40


def test_paper_rejects_another_candidate_before_writing_or_launching_browser(
    tmp_path: Path, monkeypatch
) -> None:
    candidate = tmp_path / "candidate.csv"
    candidate.write_bytes(b"synthetic candidate, not a delivery\n")
    out = tmp_path / "paper.pdf"

    def no_browser(*args, **kwargs):
        pytest.fail("a mismatching candidate must not launch the browser")

    monkeypatch.setattr(build, "browser", no_browser)
    with pytest.raises(ValueError, match="Submission SHA-256 mismatch"):
        build.main(
            [
                "--team",
                "Test",
                "--repo",
                "https://example.org/repo",
                "--date",
                "Test",
                "--submission",
                str(candidate),
                "--out",
                str(out),
            ]
        )
    assert not out.exists()
    assert not out.with_suffix(".html").exists()


def test_paper_renders_fixed_delivery_hash_and_checkout() -> None:
    digest = build.expected_sha256()
    html = build.render("Test", "https://example.org/repo", digest, "Test", REVISION)
    assert f'expected = "{digest}"' in html
    assert f"git checkout --detach {REVISION}" in html
    assert "{{" not in html


def test_delivery_manifest_rejects_an_incomplete_hash(tmp_path: Path, monkeypatch) -> None:
    manifest = tmp_path / "delivery.json"
    manifest.write_text(json.dumps({"submission_sha256": "7a7f70b68d39"}), encoding="utf-8")
    monkeypatch.setattr(build, "DELIVERY", manifest)
    with pytest.raises(ValueError, match="complete SHA-256"):
        build.expected_sha256()


def test_csv_checkout_preserves_bytes_with_autocrlf(tmp_path: Path, repo_root: Path) -> None:
    # Exercise Git's checkout conversion without rewriting the organisers' reference files.
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True, capture_output=True)
    subprocess.run(
        ["git", "config", "core.autocrlf", "true"], cwd=tmp_path, check=True, capture_output=True
    )
    (tmp_path / ".gitattributes").write_bytes((repo_root / ".gitattributes").read_bytes())
    csv = tmp_path / "synthetic.csv"
    original = b"frame,label\n0,X\n"
    csv.write_bytes(original)
    subprocess.run(
        ["git", "add", ".gitattributes", "synthetic.csv"],
        cwd=tmp_path,
        check=True,
        capture_output=True,
    )
    csv.unlink()
    subprocess.run(
        ["git", "checkout-index", "--", "synthetic.csv"],
        cwd=tmp_path,
        check=True,
        capture_output=True,
    )
    assert csv.read_bytes() == original
