from __future__ import annotations

import numpy as np

from tools.dead_price import added_segments, dead_mask, fusions, report, runs


def labels(*parts: tuple[str, int]) -> list[str]:
    return [label for label, count in parts for _ in range(count)]


def test_runs_are_maximal_half_open_intervals() -> None:
    mask = np.array([0, 1, 1, 0, 1, 0], dtype=bool)
    assert runs(mask) == [(1, 3), (4, 5)]


def test_added_segments_are_only_where_the_variant_is_dead_alone() -> None:
    a = np.array([0, 1, 0, 0, 1, 1, 0], dtype=bool)
    b = np.array([0, 1, 1, 1, 1, 1, 0], dtype=bool)
    assert added_segments(a, b) == [(2, 4)]


def test_one_short_extension_is_not_a_fusion() -> None:
    a = np.array([0, 1, 1, 0, 0, 0], dtype=bool)
    b = np.array([0, 1, 1, 0, 0, 0], dtype=bool) | np.array([0, 0, 1, 1, 0, 0], dtype=bool)
    assert fusions(a, b) == 0


def test_swallowing_the_live_spell_between_two_stoppages_counts_as_a_fusion() -> None:
    a = np.array([0, 1, 1, 0, 1, 1, 0], dtype=bool)
    b = np.zeros(7, dtype=bool) | np.array([0, 1, 1, 1, 1, 1, 0], dtype=bool)
    assert fusions(a, b) == 1


def test_dead_mask_ignores_case_and_whitespace() -> None:
    assert dead_mask(["d", " H ", "D"]).tolist() == [True, False, True]


def test_report_states_the_added_time_and_the_fusion_count() -> None:
    a = labels(("H", 10), ("D", 5), ("H", 10))
    b = labels(("H", 8), ("D", 9), ("H", 8))
    text = report(a, b, "engine", "onset")
    assert "onset − engine" in text
    # a: D on 10..14, b: D on 8..16 -> four added frames in two segments, no fusion
    assert "| onset − engine | 4 |" in text
    assert "| 2 | 0 |" in text
