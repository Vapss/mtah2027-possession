"""Ingest has to rebuild data/ exactly, never clobber, and respect what git already tracks.

The bundle is gated, so these tests build a tiny archive with the real internal layout instead of
touching the 400 MB of real data. What is under test is the prefix arithmetic, the overwrite rules
and the "identical bytes are already present" shortcut -- the parts where a wrong answer quietly
corrupts a working tree.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

import pytest

import games
from tools import ingest

GIT = "git"
# The glob ingest looks for; a differently named archive is reported as "no bundle zips".
ZIP_NAME = "More Than A Hack 2027 - Initial Challenge - 16-9999999999999-1-001.zip"


def bundle_payload() -> dict[str, bytes]:
    """Every non-video file the real bundle ships, with stand-in contents.

    Names come from games.py rather than being spelled out here: if an asset is renamed upstream,
    this fixture follows it, which is the same property the ingest script has to have.
    """
    payload = {}
    for source, entry in games.SOURCES.items():
        for asset in entry["assets"]:
            if asset == "video":
                continue
            rel = f"{source}/{entry['stem']}{games.SUFFIXES[asset]}"
            payload[rel] = f"{source}/{asset}\n".encode()
    payload[ingest.DATASET_README] = b"# Unpack the match data here\n"
    return payload


def build_zip(path: Path, payload: dict[str, bytes]) -> Path:
    """A zip with the bundle's real wrapper, so the prefix has to be stripped for real."""
    with zipfile.ZipFile(path, "w") as archive:
        for rel, data in payload.items():
            archive.writestr(ingest.BUNDLE_PREFIX + rel, data)
    return path


def zips_dir(tmp_path: Path) -> Path:
    directory = tmp_path / "zips"
    directory.mkdir()
    build_zip(directory / ZIP_NAME, bundle_payload())
    return directory


def read(dest: Path, rel: str) -> bytes:
    return (dest / rel).read_bytes()


def test_prefix_is_stripped_and_files_land_where_games_expects(tmp_path: Path) -> None:
    dest = tmp_path / "data"
    payload = bundle_payload()

    assert ingest.main(["--zips", str(zips_dir(tmp_path)), "--dest", str(dest)]) == 0

    assert (
        read(dest, "tactical/BAR-ATH_tactical_smart_tagging.xml")
        == payload["tactical/BAR-ATH_tactical_smart_tagging.xml"]
    )
    assert (
        read(dest, "broadcast/BAR-ATH_broadcast_atd.txt")
        == payload["broadcast/BAR-ATH_broadcast_atd.txt"]
    )
    # A member at the dataset root loses the prefix too, it does not keep a stray folder.
    assert read(dest, ingest.DATASET_README) == payload[ingest.DATASET_README]
    assert not (dest / "More Than A Hack 2027 - Initial Challenge - 16").exists()


def test_ingest_is_idempotent(tmp_path: Path) -> None:
    dest = tmp_path / "data"
    zips = zips_dir(tmp_path)
    assert ingest.main(["--zips", str(zips), "--dest", str(dest)]) == 0
    before = {path: path.stat().st_mtime_ns for path in dest.rglob("*") if path.is_file()}

    assert ingest.main(["--zips", str(zips), "--dest", str(dest)]) == 0
    after = {path: path.stat().st_mtime_ns for path in dest.rglob("*") if path.is_file()}
    assert before == after


def test_different_file_is_not_overwritten_without_force(tmp_path: Path, capsys) -> None:
    dest = tmp_path / "data"
    target = dest / "tactical" / "BAR-ATH_tactical_atd.xml"
    target.parent.mkdir(parents=True)
    target.write_bytes(b"a local edit the archive must not destroy\n")

    assert ingest.main(["--zips", str(zips_dir(tmp_path)), "--dest", str(dest)]) == 1
    assert target.read_bytes() == b"a local edit the archive must not destroy\n"
    assert "conflict" in capsys.readouterr().out


def test_force_replaces_a_different_file(tmp_path: Path) -> None:
    dest = tmp_path / "data"
    target = dest / "tactical" / "BAR-ATH_tactical_atd.xml"
    target.parent.mkdir(parents=True)
    target.write_bytes(b"stale\n")

    code = ingest.main(["--zips", str(zips_dir(tmp_path)), "--dest", str(dest), "--force"])

    assert code == 0
    assert target.read_bytes() == bundle_payload()["tactical/BAR-ATH_tactical_atd.xml"]


def test_identical_file_counts_as_present_and_is_not_rewritten(
    tmp_path: Path, capsys, monkeypatch
) -> None:
    """Same bytes means present, so a second ingest is a no-op even under --force."""
    dest = tmp_path / "data"
    zips = zips_dir(tmp_path)
    assert ingest.main(["--zips", str(zips), "--dest", str(dest)]) == 0
    capsys.readouterr()

    def refuse(*args, **kwargs):
        raise AssertionError("an identical destination must not be rewritten")

    monkeypatch.setattr(ingest, "extract", refuse)
    assert ingest.main(["--zips", str(zips), "--dest", str(dest), "--force"]) == 0
    assert "already present" in capsys.readouterr().out


def test_dry_run_writes_nothing(tmp_path: Path, capsys) -> None:
    dest = tmp_path / "data"
    zips = zips_dir(tmp_path)

    assert ingest.main(["--zips", str(zips), "--dest", str(dest), "--dry-run"]) == 0

    assert not dest.exists()
    output = capsys.readouterr().out
    assert ZIP_NAME in output
    assert "would write" in output


def test_a_tracked_file_with_different_content_aborts(tmp_path: Path) -> None:
    """data/README.md ships in the bundle and is committed; the tracked copy wins."""
    if shutil.which(GIT) is None:
        pytest.skip("git is not installed")

    repo = tmp_path / "repo"
    dest = repo / "data"
    dest.mkdir(parents=True)
    tracked = dest / ingest.DATASET_README
    tracked.write_bytes(b"the committed README\n")
    subprocess.run([GIT, "init", "-q"], cwd=repo, check=True)
    subprocess.run([GIT, "add", "data/README.md"], cwd=repo, check=True)

    code = ingest.main(["--zips", str(zips_dir(tmp_path)), "--dest", str(dest)])

    assert code == 1
    assert tracked.read_bytes() == b"the committed README\n"
    assert not (dest / "tactical").exists()


def test_an_unexpected_prefix_is_a_readable_error(tmp_path: Path, capsys) -> None:
    zips = tmp_path / "zips"
    zips.mkdir()
    with zipfile.ZipFile(zips / ZIP_NAME, "w") as archive:
        archive.writestr("some/other/folder/tactical/BAR-ATH_tactical_atd.xml", b"<xml/>")

    assert ingest.main(["--zips", str(zips), "--dest", str(tmp_path / "data")]) == 1
    assert "BUNDLE_PREFIX" in capsys.readouterr().err


def test_missing_zip_directory_says_so(tmp_path: Path, capsys) -> None:
    assert ingest.main(["--zips", str(tmp_path / "nowhere")]) == 1
    assert "no bundle zips" in capsys.readouterr().err


def test_script_runs_as_a_script(repo_root: Path) -> None:
    """`make ingest` invokes it by path, so the sys.path bootstrap has to work."""
    if not list(repo_root.glob(ingest.ZIP_GLOB)):
        pytest.skip("no bundle zips in the repository root")

    result = subprocess.run(
        [
            sys.executable,
            str(repo_root / "tools" / "ingest.py"),
            "--dry-run",
            "--zips",
            str(repo_root),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert "summary" in result.stdout
