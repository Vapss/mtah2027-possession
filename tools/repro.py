"""#15: build the delivered file twice, from scratch, in two directories, and compare the bytes.

    python tools/repro.py       # exit 0 and one SHA-256 when both builds are identical

Rule 3 of the competition: the repository must regenerate the submitted file -- "not approximately,
the same file". This is that check end to end: two independent builds of the delivered chain, each
in its own wiped directory under runs/repro/, and the two outputs compared byte for byte. Anything
stochastic, time-stamped or path-dependent in the labelling path shows up here as two hashes.

The delivered chain is the backup (DECISIONS 25) until a model replaces it; when that happens,
`CHAINS` gets the new builder and `--chain` its name, and the default moves with the decision.
"""

from __future__ import annotations

import argparse
import hashlib
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from tools import backup  # noqa: E402

CHAINS = {"backup": backup.build}
WORKDIR = REPO_ROOT / "runs" / "repro"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def repro(chain: str = "backup", workdir: Path = WORKDIR) -> tuple[str, str]:
    """Build `chain` twice in `workdir`/a and `workdir`/b; return both SHA-256 digests."""
    build = CHAINS[chain]
    digests = []
    for name in ("a", "b"):
        out = build(workdir / name, workdir / name / "submission.csv")
        digests.append(sha256(out))
    return digests[0], digests[1]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build the delivered file twice and compare")
    parser.add_argument("--chain", choices=sorted(CHAINS), default="backup")
    args = parser.parse_args(argv)
    try:
        first, second = repro(args.chain)
    except (OSError, ValueError, RuntimeError) as problem:
        print(f"repro failed: {problem}", file=sys.stderr)
        return 1
    if first != second:
        print(f"NOT reproducible: {first} != {second}", file=sys.stderr)
        return 1
    print(f"reproducible: {args.chain} sha256 {first}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
