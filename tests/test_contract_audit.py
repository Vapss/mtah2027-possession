"""#21: the full-match contract test, on synthetic labels and arrays."""

from __future__ import annotations

import pandas as pd

from tools import contract_audit as ca


def labels(*parts: tuple[str, int]) -> list[str]:
    return [label for label, count in parts for _ in range(count)]


def run(lab: list[str], present: list[bool], spans=((1, 0, None),)) -> ca.Audit:
    half_spans = [(half, start, len(lab) if stop is None else stop) for half, start, stop in spans]
    return ca.audit(lab, present, half_spans=half_spans, expected_frames=len(lab))


def test_spells_are_maximal_same_team_runs() -> None:
    lab = labels(("D", 2), ("H", 3), ("D", 1), ("A", 2), ("A", 1), ("X", 2), ("H", 1))
    assert [(s.start, s.stop, s.label) for s in ca.spells(lab)] == [
        (2, 5, "H"),
        (6, 9, "A"),
        (11, 12, "H"),
    ]


def test_gaps_include_the_tail() -> None:
    present = [True, False, False, True, False]
    assert [(g.start, g.stop) for g in ca.gaps(present)] == [(1, 3), (4, 5)]


def test_a_clean_small_match_passes_every_gate() -> None:
    lab = labels(("D", 10), ("H", 200), ("D", 5), ("A", 200), ("D", 10))
    result = run(lab, [True] * len(lab))
    assert result.passed
    assert [f.gate.split()[0] for f in result.findings] == ["T1", "T2", "T3", "T4"]


def test_a_possession_longer_than_five_minutes_is_flagged() -> None:
    lab = labels(("H", ca.LONG_SPELL_FRAMES))
    result = run(lab, [True] * len(lab))
    assert not result.findings[1].passed
    assert result.findings[1].frames == [(0, ca.LONG_SPELL_FRAMES)]


def test_a_team_change_inside_a_long_ball_gap_is_flagged() -> None:
    gap = ca.LONG_GAP_FRAMES + 100
    lab = labels(("H", gap // 2), ("A", gap - gap // 2))
    present = [False] * gap
    result = run(lab, present)
    assert not result.findings[2].passed
    assert result.findings[2].frames == [(gap // 2, gap // 2 + 1)]


def test_a_restart_from_dead_ball_inside_a_gap_is_not_flagged() -> None:
    gap = ca.LONG_GAP_FRAMES + 100
    lab = labels(("D", gap // 2), ("H", gap - gap // 2))
    result = run(lab, [False] * gap)
    assert result.findings[2].passed


def test_a_block_with_only_dead_ball_is_flagged() -> None:
    lab = labels(("D", ca.BLOCK_FRAMES))
    result = run(lab, [True] * len(lab))
    assert not result.findings[3].passed


def test_x_inside_a_playing_half_is_flagged() -> None:
    lab = labels(("H", 10), ("X", 1), ("H", 10))
    result = run(lab, [True] * len(lab))
    assert not result.findings[0].passed
    assert "1 X dentro de una mitad" in result.findings[0].detail


def test_artifact_labels_follow_argmax_and_zero_confidence() -> None:
    artifact = pd.DataFrame(
        {
            "p_home": [1.0, 0.0, 0.0],
            "p_away": [0.0, 1.0, 0.0],
            "p_dead": [0.0, 0.0, 1.0],
            "confidence": [1.0, 0.0, 1.0],
        }
    )
    assert ca.artifact_labels(artifact).tolist() == ["H", "X", "D"]
    assert ca.ball_from_artifact(artifact).tolist() == [True, False, True]


def test_frames_out_of_order_fail_the_file_contract() -> None:
    lab = labels(("H", 3))
    result = ca.audit(lab, [True] * 3, frames=[0, 2, 1], half_spans=[(1, 0, 3)], expected_frames=3)
    assert not result.findings[0].passed
