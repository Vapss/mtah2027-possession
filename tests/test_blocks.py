"""#36 D6: the 22-block structural report, on synthetic labels and on the delivered match."""

from __future__ import annotations

import numpy as np
import pytest
from _bundle import requires_bundle

from tools import blocks as bl
from tools import smart_tagging as st


def labels(*parts: tuple[str, int]) -> list[str]:
    return [label for label, count in parts for _ in range(count)]


def no_votes(n: int) -> np.ndarray:
    return np.zeros((n, 2), dtype=np.int16)


def test_halves_are_cut_into_blocks_and_never_across_a_half() -> None:
    cut = bl.blocks([(1, 0, 25), (2, 30, 50)], size=10)
    assert [(b.index, b.half, b.start, b.stop) for b in cut] == [
        (1, 1, 0, 10),
        (2, 1, 10, 20),
        (3, 1, 20, 25),
        (4, 2, 30, 40),
        (5, 2, 40, 50),
    ]


def test_the_match_gives_22_blocks_and_block_1_is_the_public_window() -> None:
    cut = bl.blocks(bl.halves())
    assert len(cut) == 22
    assert (cut[0].start, cut[0].stop) == (11185, 18685)
    assert [b.half for b in cut].count(1) == 11


def test_a_possession_belongs_to_the_block_where_it_starts() -> None:
    lab = labels(("H", 8), ("A", 12))
    cut = bl.blocks([(1, 0, 20)], size=10)
    rows = bl.measure(lab, np.ones(20, dtype=bool), no_votes(20), cut, [(0, 20)])
    assert [r.possessions for r in rows] == [2, 0, 2]
    # The A spell starts in block 1 and runs into block 2: its full length counts, 12 frames.
    assert rows[0].median_s == pytest.approx(np.median([8, 12]) / bl.FPS)


def test_abstention_inside_a_possession_does_not_split_it() -> None:
    lab = labels(("H", 4), ("X", 3), ("H", 3))
    rows = bl.measure(
        lab, np.ones(10, dtype=bool), no_votes(10), bl.blocks([(1, 0, 10)]), [(0, 10)]
    )
    assert rows[-1].possessions == 1


def test_dead_and_home_shares_are_per_frame() -> None:
    lab = labels(("H", 3), ("D", 4), ("A", 1))
    row = bl.measure(lab, np.ones(8, dtype=bool), no_votes(8), bl.blocks([(1, 0, 8)]), [(0, 8)])[0]
    assert row.dead == pytest.approx(4 / 8)
    assert row.home == pytest.approx(3 / 4)


def test_smart_tagging_agreement_counts_only_single_side_live_frames() -> None:
    lab = labels(("H", 4), ("A", 2), ("D", 2))
    votes = no_votes(8)
    votes[0:2, 0] = 1  # home, labelled H: agree
    votes[2:4, 1] = 1  # away, labelled H: disagree
    votes[4:5, :] = 1  # both sides: not covered
    votes[6:8, 1] = 1  # covered, but the frames are D: not judged
    row = bl.measure(lab, np.ones(8, dtype=bool), votes, bl.blocks([(1, 0, 8)]), [(0, 8)])[0]
    assert row.st_cover == pytest.approx(6 / 8)
    assert row.st_agree == pytest.approx(2 / 4)


def test_votes_name_the_side_with_the_ball() -> None:
    instances = [
        {"code": "BUILD UP", "tags": {"Team": "Barcelona"}, "start_frame": 0, "end_frame": 2},
        {
            "code": "DEFENDING IN MIDDLE THIRD",
            "tags": {"Team": "Barcelona"},
            "start_frame": 2,
            "end_frame": 4,
        },
        {"code": "PROGRESSION", "tags": {"Team": "Atletic Club"}, "start_frame": 1, "end_frame": 3},
        {"code": "SET PIECES", "tags": {"Team": "Barcelona"}, "start_frame": 5, "end_frame": 6},
        {"code": "BUILD UP", "tags": {"Team": "N/A"}, "start_frame": 6, "end_frame": 7},
    ]
    votes = st.possession_votes(instances)[:8]
    assert votes[:, 0].tolist() == [1, 1, 0, 0, 0, 0, 0, 0]
    assert votes[:, 1].tolist() == [0, 1, 2, 1, 0, 0, 0, 0]


def test_report_names_its_command_and_carries_no_absolute_path() -> None:
    cut = bl.blocks([(1, 0, 10)])
    rows = bl.measure(labels(("H", 10)), np.ones(10, dtype=bool), no_votes(10), cut, [(0, 10)])
    text = bl.report({"demo": rows}, cut, "python tools/blocks.py demo.csv", commit="abc1234")
    assert "`python tools/blocks.py demo.csv`" in text and "abc1234" in text
    assert "1★" in text and "**partido**" in text
    assert ":\\" not in text and str(bl.REPO_ROOT) not in text


@requires_bundle
def test_the_delivered_match_reproduces_the_known_structure() -> None:
    """Anchors from the decisions: 59,3% ball over graded frames, 88,2% in the public window."""
    import pandas as pd

    runs = [(start, stop) for _half, start, stop in bl.halves()]
    cut = bl.blocks(bl.halves())
    present = bl.atd.load(bl.games.DEFAULT_SOURCE).ball()[1]
    votes = st.possession_votes(st.load())
    base = pd.read_csv(bl.REPO_ROOT / "evaluation" / "results" / "baseline_smooth50.csv")
    rows = bl.measure(base.label.tolist(), present, votes, cut, runs)
    assert len(rows) == 23
    assert round(rows[0].ball, 3) == 0.882
    assert round(rows[-1].ball, 3) == 0.593
    assert rows[0].possessions == 26  # the 26 that run_evaluation.py reports for smooth50
