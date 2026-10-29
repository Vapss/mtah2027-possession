from __future__ import annotations

import sys

import numpy as np
import pandas as pd
import pytest

from tools.ball_gaps import REPO_ROOT, ball_gaps, fill_artifact, fill_ball_gaps, half_runs


def labels(*parts: tuple[str, int]) -> list[str]:
    return [label for label, count in parts for _ in range(count)]


def present(*runs: tuple[bool, int]) -> list[bool]:
    return [state for state, count in runs for _ in range(count)]


def test_gap_is_the_missing_ball_run_and_borders_are_not_touched() -> None:
    ball = present((True, 3), (False, 4), (True, 3))
    gap = ball_gaps(ball, [(0, len(ball))])
    assert gap == [(3, 7)]


def test_runs_outside_the_half_blocks_are_not_gaps() -> None:
    ball = present((False, 2), (True, 2), (False, 2))
    assert ball_gaps(ball, [(2, 4)]) == []
    ball = present((True, 1), (False, 3), (True, 1))
    # A gap inside one half is found, the same mask outside it is ignored.
    assert ball_gaps(ball, [(1, 4)]) == [(1, 4)]


def test_leading_and_trailing_gaps_inside_a_half_are_reported() -> None:
    ball = present((False, 2), (True, 2), (False, 3))
    assert ball_gaps(ball, [(0, 7)]) == [(0, 2), (4, 7)]


def test_fill_carries_the_previous_label_and_moves_no_border() -> None:
    ball = present((True, 3), (False, 4), (True, 3))
    source = ["H"] * 3 + ["D"] * 4 + ["A"] * 3
    assert fill_ball_gaps(source, ball, [(0, 10)]) == ["H"] * 7 + ["A"] * 3


def test_fill_never_introduces_d_where_the_input_had_none() -> None:
    ball = present((True, 4), (False, 6), (True, 4))
    source = labels(("H", 2), ("A", 2), ("D", 6), ("A", 4))
    result = fill_ball_gaps(source, ball, [(0, 14)])
    assert result == labels(("H", 2), ("A", 8), ("A", 4))
    assert "D" not in result


def test_a_gap_that_follows_d_stays_d() -> None:
    ball = present((True, 4), (False, 5), (True, 4))
    source = labels(("H", 2), ("D", 2), ("D", 5), ("H", 4))
    assert fill_ball_gaps(source, ball, [(0, 13)]) == source


def test_x_between_the_gap_and_its_predecessor_is_skipped_not_carried() -> None:
    ball = present((True, 2), (False, 4), (True, 2))
    source = labels(("H", 1), ("X", 1), ("D", 4), ("A", 2))
    assert fill_ball_gaps(source, ball, [(0, 8)]) == labels(("H", 1), ("X", 1), ("H", 4), ("A", 2))


def test_gap_at_the_head_of_a_half_is_left_alone() -> None:
    ball = present((False, 3), (True, 4))
    source = labels(("X", 3), ("H", 4))
    assert fill_ball_gaps(source, ball, [(0, 7)]) == source


def test_x_with_the_ball_in_play_is_not_a_gap_and_is_not_filled() -> None:
    ball = present((True, 5))
    source = labels(("H", 2), ("X", 2), ("A", 1))
    assert fill_ball_gaps(source, ball, [(0, 5)]) == source


def test_fill_does_not_cross_a_half_boundary() -> None:
    ball = present((True, 3), (False, 3), (True, 3))
    source = labels(("H", 3), ("D", 3), ("A", 3))
    runs = [(0, 3), (6, 9)]
    assert fill_ball_gaps(source, ball, runs) == source


def test_bands_restrict_the_fill_without_changing_the_definition() -> None:
    ball = present((True, 2), (False, 6), (True, 2), (False, 2), (True, 2))
    source = labels(("A", 2), ("D", 6), ("H", 2), ("D", 2), ("A", 2))
    assert ball_gaps(ball, [(0, 14)]) == [(2, 8), (10, 12)]
    assert fill_ball_gaps(source, ball, [(0, 14)], bands=[(5, 10)]) == labels(
        ("A", 8), ("H", 2), ("D", 2), ("A", 2)
    )
    assert fill_ball_gaps(source, ball, [(0, 14)], bands=[(1, 2)]) == labels(
        ("A", 2), ("D", 6), ("H", 4), ("A", 2)
    )


def test_fill_is_idempotent() -> None:
    ball = present((True, 3), (False, 5), (True, 3))
    source = labels(("H", 3), ("D", 5), ("A", 3))
    once = fill_ball_gaps(source, ball, [(0, 11)])
    assert fill_ball_gaps(once, ball, [(0, 11)]) == once


def test_rejects_labels_outside_the_contract() -> None:
    with pytest.raises(ValueError, match="outside H/A/D/X"):
        fill_ball_gaps(["H", "Z"], present((True, 2)), [(0, 2)])


def test_rejects_mismatched_lengths() -> None:
    with pytest.raises(ValueError, match="same length"):
        fill_ball_gaps(["H", "H"], present((True, 3)), [(0, 3)])


def test_half_runs_match_the_two_video_blocks() -> None:
    assert half_runs() == [(11185, 90652), (110808, 190198)]


def artifact(rows: list[tuple[float, float, float, float]]) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "frame": index,
                "p_home": p_home,
                "p_away": p_away,
                "p_dead": p_dead,
                "confidence": confidence,
            }
            for index, (p_home, p_away, p_dead, confidence) in enumerate(rows)
        ]
    )


def test_artifact_repeats_the_base_and_only_speaks_inside_gaps() -> None:
    ball = present((True, 3), (False, 3), (True, 3))
    base = artifact(
        [(0.8, 0.18, 0.02, 0.8)] * 3 + [(0.49, 0.49, 0.02, 0.0)] * 3 + [(0.1, 0.88, 0.02, 0.88)] * 3
    )
    result = fill_artifact(base, ball, [(0, 9)])
    # Inside the gap the predecessor row is carried, confidence included.
    assert np.allclose(
        result.loc[3:5, ["p_home", "p_away", "p_dead"]].to_numpy(), [[0.8, 0.18, 0.02]] * 3
    )
    assert result.loc[3:5, "confidence"].tolist() == [0.8, 0.8, 0.8]
    # Outside it the job abstains, and the probabilities are the base's own: the assembler's
    # zero-weight fallback then reproduces the base row instead of inventing a tie-break.
    outside = [0, 1, 2, 6, 7, 8]
    assert result.loc[outside, "confidence"].tolist() == [0.0] * 6
    assert np.allclose(
        result.loc[outside, ["p_home", "p_away", "p_dead"]].to_numpy(),
        base.loc[outside, ["p_home", "p_away", "p_dead"]].to_numpy(),
    )


def test_artifact_carries_d_when_the_predecessor_decides_d() -> None:
    ball = present((True, 4), (False, 4), (True, 4))
    base = artifact(
        [(0.4, 0.4, 0.2, 0.4)] * 2
        + [(0.02, 0.02, 0.96, 0.96)] * 2
        + [(0.49, 0.49, 0.02, 0.0)] * 4
        + [(0.6, 0.38, 0.02, 0.6)] * 4
    )
    result = fill_artifact(base, ball, [(0, 12)])
    assert result.loc[4:7, "p_dead"].tolist() == [0.96] * 4
    assert result.loc[4:7, "confidence"].tolist() == [0.96] * 4


def test_artifact_does_not_fill_the_head_of_a_half() -> None:
    ball = present((False, 3), (True, 4))
    base = artifact([(0.49, 0.49, 0.02, 0.0)] * 3 + [(0.7, 0.28, 0.02, 0.7)] * 4)
    result = fill_artifact(base, ball, [(0, 7)])
    assert result["confidence"].tolist() == [0.0] * 7


def test_artifact_frame_column_is_preserved() -> None:
    ball = present((True, 2), (False, 2), (True, 2))
    base = artifact(
        [(0.7, 0.28, 0.02, 0.7)] * 2 + [(0.49, 0.49, 0.02, 0.0)] * 2 + [(0.7, 0.28, 0.02, 0.7)] * 2
    )
    base["frame"] = base["frame"] + 100
    assert fill_artifact(base, ball, [(0, 6)])["frame"].tolist() == list(range(100, 106))


def test_anchor_numbers_of_the_ticket_are_reproduced() -> None:
    """`baseline_smooth50` + fill must hit the +0.055 the issue quotes, or the definition drifted.

    The ticket's anchor is the only public evidence that this rule does anything: 0.3256 -> 0.3805
    on `spellF1`, 0.6207 -> 0.5105 on `macroF1`. If a future change to the gap definition, the run
    boundaries or the carry rule moves these, the PR is not measuring what it says it measures.
    """
    sys.path.insert(0, str(REPO_ROOT / "evaluation"))
    import pandas as pd
    import possession_metrics as pm

    from tools.ball_gaps import _ball_present

    try:
        ball = _ball_present()
    except (OSError, ValueError) as error:  # licensed bundle absent: CI
        pytest.skip(f"tactical tracking not available: {error}")

    base = pd.read_csv(REPO_ROOT / "evaluation" / "results" / "baseline_smooth50.csv")
    ground_truth = pm.label_codes(
        pm.read_label_csv(REPO_ROOT / "evaluation" / "gt" / "BAR-ATH_possession_gt_public.csv")
    )
    before = pm.evaluate(ground_truth, pm.label_codes(base.label))
    after = pm.evaluate(ground_truth, pm.label_codes(fill_ball_gaps(base.label, ball, half_runs())))
    assert round(float(before["spell_f1_mean"]), 4) == 0.3256
    assert round(float(after["spell_f1_mean"]), 4) == 0.3805
    assert round(float(before["macro_f1"]), 4) == 0.6207
    assert round(float(after["macro_f1"]), 4) == 0.5105


def test_mask_matches_the_tracking_export() -> None:
    """The real artifact of this rule: 150 gaps and 64,643 missing frames inside the halves."""
    from tools.ball_gaps import _ball_present

    try:
        ball = _ball_present()
    except (OSError, ValueError) as error:  # licensed bundle absent: CI
        pytest.skip(f"tactical tracking not available: {error}")
    gaps = ball_gaps(ball, half_runs())
    assert len(gaps) == 150
    assert sum(stop - start for start, stop in gaps) == 64643
    assert int(np.median([stop - start for start, stop in gaps])) == 268
