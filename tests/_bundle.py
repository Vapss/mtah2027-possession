"""One place that decides whether the gated match bundle is available.

`games.py` is the authority: it resolves `MTAH_DATA_DIR`, so a bundle unpacked outside `data/` --
which is what `data/README.md` recommends for a big disk -- is still found. Hard-coding a relative
`data/tactical/...` path here would make those tests *fail* instead of skip for anyone who did the
documented thing, which is a worse bug than the one it was meant to avoid.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import games  # noqa: E402

# Both assets, because every bundle-dependent test needs the tracking file and at least one of
# them needs the Smart Tagging XML.
REQUIRED_ASSETS = ("atd_raw", "smart_tagging")


def missing_reason() -> str | None:
    """One readable line saying what is absent, or None when the bundle is complete."""
    try:
        games.require(list(REQUIRED_ASSETS))
    except (OSError, KeyError) as problem:
        return str(problem).splitlines()[0]
    return None


BUNDLE_MISSING = missing_reason()

requires_bundle = pytest.mark.skipif(
    BUNDLE_MISSING is not None,
    reason=f"match bundle not unpacked: {BUNDLE_MISSING}",
)
