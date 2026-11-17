"""Smart Tagging: 638 phases on the tactical clock, turned into half-open frame masks.

The real file is the interesting case -- it is the one artefact whose clock can be wrong without
anything else failing -- so most tests read it and skip on a checkout without the bundle. The
synthetic instances cover the edges the delivered file happens not to contain.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

import games
from tools import smart_tagging

SMART_TAGGING_XML = Path(games.asset_paths()["smart_tagging"])
N_FRAMES = games.source_frames()

# Read off the delivered file: 638 instances, and the per-code counts below are the ones that
# identify an export. They come from the file, not from an earlier run of this module.
EXPECTED_INSTANCES = 638
EXPECTED_COUNTS = {"SET PIECES": 59, "GOALS": 4, "BUILD UP": 22}
FIRST_SET_PIECE = 11097
KICKOFF_FIRST_HALF = 11185


@pytest.fixture(scope="module")
def instances() -> list[dict]:
    if not SMART_TAGGING_XML.is_file():
        pytest.skip("match bundle not unpacked -- see data/README.md")
    return smart_tagging.load()


def synthetic(code: str, start: int, end: int) -> dict:
    """One instance shaped like load()'s output, so mask() can be exercised without the file."""
    return {
        "id": 0,
        "code": code,
        "start_frame": start,
        "end_frame": end,
        "start_s": start / smart_tagging.FPS,
        "end_s": end / smart_tagging.FPS,
        "tags": {},
    }


def test_load_reads_every_instance(instances: list[dict]) -> None:
    assert len(instances) == EXPECTED_INSTANCES
    assert len({item["id"] for item in instances}) == EXPECTED_INSTANCES
    for item in instances:
        assert 0 <= item["start_frame"] <= item["end_frame"] <= N_FRAMES


def test_counts_match_the_delivered_file(instances: list[dict]) -> None:
    counts = smart_tagging.summary(instances)
    for code, expected in EXPECTED_COUNTS.items():
        assert counts[code] == expected, code
    assert sum(counts.values()) == EXPECTED_INSTANCES
    assert list(counts.values()) == sorted(counts.values(), reverse=True)


def test_mask_is_a_full_length_boolean_array(instances: list[dict]) -> None:
    marked = smart_tagging.mask(instances, "GOALS")
    assert marked.dtype == np.bool_
    assert marked.shape == (N_FRAMES,)
    assert marked.any()


def test_mask_is_half_open_on_the_right(instances: list[dict]) -> None:
    """The first SET PIECES is 11097..11222, and the kickoff at 11185 has to be inside it."""
    marked = smart_tagging.mask(instances, "SET PIECES")

    assert marked[KICKOFF_FIRST_HALF]
    assert marked[FIRST_SET_PIECE]
    assert not marked[FIRST_SET_PIECE - 1]
    # end_frame is exclusive: 11222 is the first frame after the phase, not part of it.
    assert marked[11221]
    assert not marked[11222]


def test_mask_matches_codes_case_insensitively(instances: list[dict]) -> None:
    canonical = smart_tagging.mask(instances, ["SET PIECES"])
    assert np.array_equal(canonical, smart_tagging.mask(instances, " set pieces "))
    assert np.array_equal(canonical, smart_tagging.mask(instances, ["SeT pIeCeS"]))


def test_empty_interval_marks_nothing() -> None:
    marked = smart_tagging.mask([synthetic("GOALS", 500, 500)], "GOALS")
    assert not marked.any()


def test_interval_past_the_end_is_clipped() -> None:
    marked = smart_tagging.mask([synthetic("GOALS", N_FRAMES - 9, N_FRAMES + 5000)], "GOALS")
    assert marked[N_FRAMES - 1]
    assert marked.sum() == 9
    assert (
        smart_tagging.mask([synthetic("GOALS", N_FRAMES + 10, N_FRAMES + 20)], "GOALS").sum() == 0
    )


def test_interval_before_the_start_is_clipped() -> None:
    marked = smart_tagging.mask([synthetic("GOALS", -50, 3)], "GOALS")
    assert marked[:3].all()
    assert not marked[3:].any()


def test_overlapping_instances_are_idempotent() -> None:
    """A frame tagged twice is still just True -- no counting, no priority between codes."""
    overlaps = [synthetic("SET PIECES", 10, 20), synthetic("Set Pieces", 15, 25)]
    marked = smart_tagging.mask(overlaps, "set pieces")
    assert marked[10:25].all()
    assert marked.sum() == 15


def test_unknown_codes_produce_an_empty_mask() -> None:
    marked = smart_tagging.mask([synthetic("GOALS", 0, 10)], ["BUILD UP", "NOT A CODE"])
    assert not marked.any()


def test_cli_reports_the_two_codes(capsys) -> None:
    if not SMART_TAGGING_XML.is_file():
        pytest.skip("match bundle not unpacked -- see data/README.md")

    assert smart_tagging.main() == 0
    output = capsys.readouterr().out
    assert "SET PIECES" in output
    assert "GOALS" in output
