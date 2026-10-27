from __future__ import annotations

import pytest

from tools.band_gaps import _command, apply_policy, band_label, band_of_gaps, decide

RUNS = [(0, 100)]


def labels(*parts: tuple[str, int]) -> list[str]:
    return [label for label, count in parts for _ in range(count)]


@pytest.mark.parametrize(
    ("length", "expected"),
    [
        (1, "≤25"),
        (25, "≤25"),
        (26, "26–125"),
        (125, "26–125"),
        (126, "126–500"),
        (500, "126–500"),
        (501, ">500"),
        (8689, ">500"),
    ],
)
def test_band_boundaries_are_the_ticket_s(length: int, expected: str) -> None:
    assert band_label(length) == expected


def test_gaps_are_selected_by_length_not_by_position() -> None:
    gaps = [(0, 5), (10, 20), (30, 140), (150, 700)]
    assert band_of_gaps(gaps, "≤25") == [(0, 5), (10, 20)]
    assert band_of_gaps(gaps, "26–125") == [(30, 140)]
    assert band_of_gaps(gaps, "126–500") == []
    assert band_of_gaps(gaps, ">500") == [(150, 700)]


def test_policy_fill_carries_the_previous_label_inside_the_gap_only() -> None:
    source = labels(("H", 4), ("D", 3), ("A", 3))
    assert apply_policy(source, [(4, 7)], "fill", RUNS) == labels(("H", 7), ("A", 3))


def test_policy_d_and_x_overwrite_the_whole_gap() -> None:
    source = labels(("H", 4), ("A", 3), ("A", 3))
    assert apply_policy(source, [(4, 7)], "D", RUNS) == labels(("H", 4), ("D", 3), ("A", 3))
    assert apply_policy(source, [(4, 7)], "X", RUNS) == labels(("H", 4), ("X", 3), ("A", 3))


def test_fill_skips_x_when_looking_for_the_carry_value() -> None:
    source = labels(("H", 2), ("X", 1), ("D", 2), ("A", 3))
    assert apply_policy(source, [(3, 5)], "fill", RUNS) == labels(
        ("H", 2), ("X", 1), ("H", 2), ("A", 3)
    )


def test_fill_leaves_a_gap_without_predecessor_alone() -> None:
    source = labels(("X", 3), ("H", 3))
    assert apply_policy(source, [(0, 3)], "fill", RUNS) == source


def test_unknown_policy_is_rejected() -> None:
    with pytest.raises(ValueError, match="unknown policy"):
        apply_policy(["H"] * 5, [(1, 2)], "carry", RUNS)


def band_row(**overrides: object) -> dict:
    row = {
        "n_gaps": 10,
        "graded_frames": 500,
        "transitions": 1,
        "splits_possession": True,
        "policy": {"delta": 0.06, "n_discordant": 2},
    }
    row.update(overrides)
    return row


def test_decide_measures_a_band_that_passes_all_four_conditions() -> None:
    drops = [{"start": 1, "stop": 2, "policy": {"delta": 0.051, "n_discordant": 2}}]
    verdict, reason = decide("126–500", band_row(), drops)
    assert verdict == "medida"
    assert "leave-one-gap-out" in reason


def test_decide_reports_a_band_with_no_gap_as_unmeasurable() -> None:
    verdict, reason = decide(">500", band_row(n_gaps=0, graded_frames=0), [])
    assert verdict == "no medible localmente"
    assert "ningún hueco" in reason


def test_decide_reports_a_band_that_touches_no_graded_frame_as_unmeasurable() -> None:
    verdict, reason = decide("26–125", band_row(graded_frames=0), [])
    assert verdict == "no medible localmente"
    assert "ningún frame puntuado" in reason


def test_decide_reports_a_single_discordant_possession_as_unmeasurable() -> None:
    verdict, reason = decide(
        "126–500", band_row(transitions=1, policy={"delta": 0.06, "n_discordant": 1}), []
    )
    assert verdict == "no medible localmente"
    assert "discordante" in reason


def test_decide_rejects_a_delta_inside_the_noise_band() -> None:
    verdict, reason = decide("126–500", band_row(policy={"delta": 0.02, "n_discordant": 3}), [])
    assert verdict == "no medible localmente"
    assert "por debajo de la banda" in reason


def test_decide_rejects_a_result_that_dies_with_one_gap() -> None:
    drops = [
        {"start": 1, "stop": 2, "policy": {"delta": 0.055, "n_discordant": 2}},
        {"start": 5, "stop": 9, "policy": {"delta": 0.016, "n_discordant": 0}},
    ]
    verdict, reason = decide("126–500", band_row(), drops)
    assert verdict == "no medible localmente"
    assert "depende de un hueco" in reason
    assert "0,01600" in reason


def test_the_document_prints_the_command_that_actually_reproduces_it() -> None:
    """Section 3 only exists with --ship, so the printed command must carry it."""
    without_ship = _command({"anchor": {}})
    assert without_ship == "python tools/band_gaps.py --write docs/analysis/ball-gap-bands.md"
    with_ship = _command({"anchor": {}, "ship": {"base": "artifacts/possession.csv"}})
    assert "--ship artifacts/possession.csv" in with_ship
    assert with_ship.endswith("--write docs/analysis/ball-gap-bands.md")
