"""#15: build the delivered file twice, from scratch, and compare the bytes -- with each other and
with the file that was delivered.

    python tools/repro.py                                   # two builds agree
    python tools/repro.py --against submissions/backup.csv  # ...and equal the delivered file

Rule 3 of the competition: the repository must regenerate the submitted file -- "not approximately,
the same file". Two independent builds of the delivered chain, each in a directory this module wipes
itself under runs/repro/, are compared byte for byte. That catches anything stochastic,
time-stamped or path-dependent. It does not catch code that changed after the file was delivered:
both builds would agree on the new output. `--against` closes that, by also comparing with the
delivered file.

The delivered chain is the backup (DECISIONS 25) until a model replaces it; when that happens,
`CHAINS` gets the new builder and `--chain` its name, and the default moves with the decision.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from tools import backup, engine  # noqa: E402
from tools.f0a import _sha256 as sha256  # noqa: E402

CHAINS = {"backup": backup.build, "engine": engine.build}
WORKDIR = backup.RUNS / "repro"


def repro(chain: str = "backup", workdir: Path | None = None) -> tuple[str, str]:
    """Build `chain` twice in `workdir`/a and `workdir`/b; return both SHA-256 digests.

    `workdir` is read at call time, not bound as a default, so a test can point WORKDIR elsewhere.
    Each per-build directory is wiped here, whatever the chain does: "from scratch" must not depend
    on a chain remembering to clean up after itself.
    """
    root = WORKDIR if workdir is None else workdir
    build = CHAINS[chain]
    digests = []
    for name in ("a", "b"):
        directory = backup.wipe(root / name)
        digests.append(sha256(build(directory, directory / "submission.csv")))
    return digests[0], digests[1]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build the delivered file twice and compare")
    parser.add_argument("--chain", choices=sorted(CHAINS), default="backup")
    parser.add_argument("--against", type=Path, help="delivered file the builds must also equal")
    args = parser.parse_args(argv)
    try:
        first, second = repro(args.chain)
        delivered = sha256(args.against) if args.against else None
    except (OSError, ValueError, RuntimeError) as problem:
        print(f"repro failed: {problem}", file=sys.stderr)
        return 1
    if first != second:
        print(f"NOT reproducible: {first} != {second}", file=sys.stderr)
        return 1
    if delivered is not None and delivered != first:
        print(
            f"builds agree ({first}) but differ from {backup.shown(args.against)} ({delivered}): "
            "the code no longer regenerates the delivered file",
            file=sys.stderr,
        )
        return 1
    against = f", equal to {backup.shown(args.against)}" if delivered else ""
    print(f"reproducible: {args.chain} sha256 {first}{against}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
