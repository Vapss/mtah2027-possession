"""Unpack the downloaded bundle into `data/`, idempotently and without clobbering anything.

The gated download arrives as eight zips in the repository root, each holding one file under a
Google-Drive style prefix. `games.asset_paths()` is the only description of where those files
belong, so this script derives its whole destination map from that function instead of spelling
filenames out a second time.

    python tools/ingest.py                # repo-root zips -> data/
    python tools/ingest.py --dry-run      # say what would happen, touch nothing
    python tools/ingest.py --force        # replace files that differ

Rules, because a half-unpacked bundle is worse than none:

- A destination that already holds the same bytes (same sha256) is *present*, not rewritten -- even
  under `--force`. Re-running ingest is therefore a no-op on a good tree, and mtimes stay put.
- A destination that differs and is tracked by git aborts the run before anything is written.
  `data/README.md` ships inside the bundle and is also committed; overwriting it with a different
  copy would dirty the tree without anyone noticing.
- Anything else that differs is left alone unless `--force`, and reported as a conflict.

Exit status: 0 when the bundle is in place (the two `.mp4` are allowed to be missing -- see
below), 1 when a conflict, a tracked-file mismatch, or an unreadable bundle stops the run.
"""

from __future__ import annotations

import argparse
import hashlib
import os
import subprocess
import sys
import tempfile
import zipfile
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

import games  # noqa: E402

# Every archive is the same export, so the wrapper is a constant rather than a guess. Checking it
# is what turns "the bundle changed shape" into a readable error instead of a silently empty data/.
BUNDLE_PREFIX = (
    "More Than A Hack 2027 - Initial Challenge - 16/"
    "More Than A Hack 2027 - Initial Challenge - Dataset/"
)
ZIP_GLOB = "More Than A Hack 2027 - Initial Challenge - 16-*.zip"
DEFAULT_DEST = REPO_ROOT / "data"
DATASET_README = "README.md"
CHUNK = 1 << 20

# The bundle genuinely ships no video: the two recordings are downloaded separately (DATA.md).
# They are listed by games.asset_paths() all the same, so the coverage table has to be able to
# tell "expected to be absent" from "ingest failed".
VIDEO_ASSETS = {f"{source}/video" for source in games.SOURCES}


class IngestError(Exception):
    """The bundle is not shaped the way games.py describes; nothing has been written yet."""


@dataclass(frozen=True)
class PlannedFile:
    """One file the bundle wants to place, still inside its archive."""

    archive: Path
    member: str
    rel: str
    size: int


@dataclass
class Totals:
    """What a run actually did, for the summary line."""

    written: int = 0
    written_bytes: int = 0
    present: int = 0
    conflicts: int = 0


def destination_index(dest: Path) -> dict[str, str]:
    """Bundle-relative path -> human label, derived from the paths games.py publishes.

    Deriving it means a rename upstream is one edit in games.py and nothing here needs to know a
    filename. The dataset README is the one member that is not an asset: it ships at the bundle
    root and is already committed, so it is indexed by name and handled by the hash rules.
    """
    index: dict[str, str] = {}
    for source in games.SOURCES:
        paths = games.asset_paths(data_dir=str(dest), source=source)
        for asset, path in paths.items():
            index[Path(path).relative_to(dest).as_posix()] = f"{source}/{asset}"
    index[DATASET_README] = "dataset README"
    return index


def strip_prefix(member: str) -> str | None:
    """The path inside the dataset, or None when the member is not from this bundle."""
    if not member.startswith(BUNDLE_PREFIX):
        return None
    return member[len(BUNDLE_PREFIX) :]


def plan(zips_dir: Path, dest: Path) -> tuple[list[Path], list[PlannedFile], list[str]]:
    """Every file the archives claim, mapped to its destination-relative path.

    Nothing is written here: a bundle whose internal layout changed must fail before the first
    byte lands, otherwise a partial unpack looks like a successful one.
    """
    archives = sorted(zips_dir.glob(ZIP_GLOB))
    known = destination_index(dest)
    planned: list[PlannedFile] = []
    unexpected: list[str] = []

    for archive in archives:
        with zipfile.ZipFile(archive) as bundle:
            for info in bundle.infolist():
                if info.is_dir():
                    continue
                rel = strip_prefix(info.filename)
                if rel is None:
                    raise IngestError(
                        f"{archive.name}: member {info.filename!r} is not under the expected "
                        f"prefix\n  {BUNDLE_PREFIX}\n"
                        "The bundle layout changed; update BUNDLE_PREFIX in tools/ingest.py."
                    )
                if rel not in known:
                    unexpected.append(f"{archive.name}: {rel}")
                    continue
                planned.append(PlannedFile(archive, info.filename, rel, info.file_size))

    return archives, planned, unexpected


def sha256_file(path: Path) -> str:
    """Digest of a file on disk, read in chunks so a 200 MB tracking file is not loaded at once."""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(CHUNK):
            digest.update(chunk)
    return digest.hexdigest()


def sha256_member(bundle: zipfile.ZipFile, member: str) -> str:
    """Digest of a member without extracting it, for the present-vs-different decision."""
    digest = hashlib.sha256()
    with bundle.open(member) as handle:
        while chunk := handle.read(CHUNK):
            digest.update(chunk)
    return digest.hexdigest()


def identical(bundle: zipfile.ZipFile, planned: PlannedFile, target: Path) -> bool:
    """Is the destination already byte-identical to the archive's copy?

    Size first: a cheap rejection, and it is what makes the common "different export" case stop
    before decompressing the whole member just to prove it differs.
    """
    if target.stat().st_size != planned.size:
        return False
    return sha256_member(bundle, planned.member) == sha256_file(target)


def extract(planned: PlannedFile, target: Path) -> int:
    """Stream one member to its destination through a temp file, so a crash leaves no half file."""
    target.parent.mkdir(parents=True, exist_ok=True)
    handle, temporary = tempfile.mkstemp(dir=str(target.parent), prefix=".ingest-", suffix=".tmp")
    try:
        with (
            zipfile.ZipFile(planned.archive) as bundle,
            bundle.open(planned.member) as source,
            os.fdopen(handle, "wb") as sink,
        ):
            written = 0
            while chunk := source.read(CHUNK):
                sink.write(chunk)
                written += len(chunk)
        os.replace(temporary, target)
        return written
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def git_tracked(directory: Path) -> set[Path]:
    """Absolute paths git has in its index under `directory`; empty outside a work tree.

    `git ls-files` is the honest source of truth here -- a plain `data/README.md` name check would
    miss a file that was renamed but is still tracked. A missing directory and a missing git are
    both "nothing is tracked", which is what makes this usable against a temp directory.
    """
    if not directory.is_dir():
        return set()
    try:
        root = subprocess.run(
            ["git", "-C", str(directory), "rev-parse", "--show-toplevel"],
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
        listing = subprocess.run(
            ["git", "-C", str(directory), "ls-files", "-z", "--full-name"],
            capture_output=True,
            text=True,
            check=True,
        ).stdout
    except (OSError, subprocess.CalledProcessError):
        return set()
    top = Path(root)
    return {(top / name).resolve() for name in listing.split("\0") if name}


def tracked_mismatches(planned: list[PlannedFile], dest: Path) -> list[str]:
    """Tracked destinations the bundle would overwrite with different content.

    Checked before the run writes anything: aborting halfway through an unpack is exactly the
    state this script exists to avoid.
    """
    tracked = git_tracked(dest)
    clashes = []
    for item in planned:
        target = (dest / item.rel).resolve()
        if target not in tracked or not target.exists():
            continue
        with zipfile.ZipFile(item.archive) as bundle:
            if not identical(bundle, item, target):
                clashes.append(f"{target} is tracked by git and the bundle's copy differs")
    return clashes


def status_of(bundle: zipfile.ZipFile, planned: PlannedFile, target: Path, force: bool) -> str:
    """`present`, `conflict` or `write` -- identical content wins over `--force` on purpose."""
    if not target.exists():
        return "write"
    if identical(bundle, planned, target):
        return "present"
    return "write" if force else "conflict"


def run(
    archives: list[Path], planned: list[PlannedFile], dest: Path, force: bool, dry: bool
) -> tuple[Totals, list[tuple[str, PlannedFile]]]:
    """Apply the plan in archive order. Returns the totals and every status per file."""
    totals = Totals()
    results: list[tuple[str, PlannedFile]] = []
    by_archive: dict[Path, list[PlannedFile]] = {}
    for item in planned:
        by_archive.setdefault(item.archive, []).append(item)

    for archive in archives:
        items = by_archive.get(archive, [])
        if not items:
            continue
        with zipfile.ZipFile(archive) as bundle:
            for item in items:
                target = dest / item.rel
                status = status_of(bundle, item, target, force)
                if status == "write":
                    if dry:
                        results.append(("would write", item))
                        continue
                    totals.written += 1
                    totals.written_bytes += extract(item, target)
                    results.append(("wrote", item))
                elif status == "present":
                    totals.present += 1
                    results.append(("present", item))
                else:
                    totals.conflicts += 1
                    results.append(("conflict", item))
    return totals, results


def coverage(dest: Path) -> list[str]:
    """Print OK/FALTA per asset straight from games.asset_paths() and return what is absent."""
    missing = []
    print("\nasset coverage (games.asset_paths)")
    print(f"  {'source':<10} {'asset':<14} {'status':<6} path")
    for source in games.SOURCES:
        for asset, path in games.asset_paths(data_dir=str(dest), source=source).items():
            found = Path(path).is_file()
            print(f"  {source:<10} {asset:<14} {'OK' if found else 'FALTA':<6} {path}")
            if not found:
                missing.append(f"{source}/{asset}")
    return missing


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Unpack the challenge data bundle into data/, without clobbering anything"
    )
    parser.add_argument(
        "--zips", default=str(REPO_ROOT), help=f"directory holding the bundle zips ({REPO_ROOT})"
    )
    parser.add_argument(
        "--dest", default=str(DEFAULT_DEST), help=f"data directory to populate ({DEFAULT_DEST})"
    )
    parser.add_argument("--dry-run", action="store_true", help="report the plan, write nothing")
    parser.add_argument("--force", action="store_true", help="replace destinations that differ")
    args = parser.parse_args(argv)

    dest = Path(args.dest)
    try:
        archives, planned, unexpected = plan(Path(args.zips), dest)
    except IngestError as problem:
        print(f"error: {problem}", file=sys.stderr)
        return 1

    if not archives:
        print(f"no bundle zips matching {ZIP_GLOB!r} in {args.zips}", file=sys.stderr)
        return 1

    clashes = tracked_mismatches(planned, dest)
    if clashes:
        print("refusing to unpack -- these files are tracked by git:", file=sys.stderr)
        for problem in clashes:
            print(f"  - {problem}", file=sys.stderr)
        return 1

    totals, results = run(archives, planned, dest, args.force, args.dry_run)

    print(f"{'would unpack' if args.dry_run else 'unpacking'} {len(archives)} zip(s) into {dest}")
    for archive in archives:
        count = sum(1 for item in planned if item.archive == archive)
        print(f"  {archive.name}  ({count} file(s))")

    print("\nfiles")
    for status, item in results:
        print(f"  {status:<11} {item.rel}")

    print("\nsummary")
    print(f"  zips read        {len(archives)}")
    print(f"  written          {totals.written} file(s), {totals.written_bytes} B")
    print(f"  already present  {totals.present} file(s)")
    print(f"  conflicts        {totals.conflicts} file(s)")
    print(f"  ignored          {len(unexpected)} member(s)")
    for line in unexpected:
        print(f"    not a known asset: {line}")

    missing = coverage(dest)
    print("\nmissing assets: " + (", ".join(missing) if missing else "none"))
    if set(missing) <= VIDEO_ASSETS:
        print("  the two .mp4 are not in the bundle; that is expected (see data/README.md)")

    required_missing = set(missing) - VIDEO_ASSETS
    if totals.conflicts:
        print("\nconflict(s) left untouched -- re-run with --force to replace them")
        return 1
    if required_missing and not args.dry_run:
        print(f"\nstill missing after unpack: {', '.join(sorted(required_missing))}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
