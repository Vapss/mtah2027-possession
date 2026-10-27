from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest

from tools import compare_submissions as compare

pm = compare.pm


def codes(text: str) -> np.ndarray:
    return pm.label_codes(np.array(list(text)))


def test_identical_submissions_match_official_score_and_have_zero_delta() -> None:
    gt = codes("HHHDDDAAADDD")
    result = compare.compare_codes(gt, gt, gt)
    official = pm.spell_scores(gt, gt, pm.valid_runs(gt))

    assert result["delta_mean_spell_f1_b_minus_a"] == 0
    assert result["a"]["mean_spell_f1"] == official["mean_f1"]
    assert result["b"]["mean_spell_f1"] == official["mean_f1"]
    assert all(row["delta_b_minus_a"] == 0 for row in result["per_iou"].values())
    assert result["sign_diagnostic"]["n_discordant"] == 0
    assert result["sign_diagnostic"]["exact_two_sided_p"] == 1


def test_comparison_is_antisymmetric_when_submission_order_is_reversed() -> None:
    gt = codes("HHHDDDAAADDD")
    changed = codes("HHHHDDAAADDD")

    ab = compare.compare_codes(gt, gt, changed)
    ba = compare.compare_codes(gt, changed, gt)

    assert ab["delta_mean_spell_f1_b_minus_a"] == -ba["delta_mean_spell_f1_b_minus_a"]
    for threshold in ab["per_iou"]:
        assert (
            ab["per_iou"][threshold]["delta_b_minus_a"]
            == -ba["per_iou"][threshold]["delta_b_minus_a"]
        )


def test_spurious_prediction_is_penalized_even_when_true_matches_are_unchanged() -> None:
    gt = codes("HHHDDDAAADDD")
    extra_spell = codes("HHHDHDAAADDD")

    result = compare.compare_codes(gt, gt, extra_spell)

    for row in result["per_iou"].values():
        assert row["a"]["n_matched"] == row["b"]["n_matched"]
        assert row["b"]["n_spurious"] == row["a"]["n_spurious"] + 1
        assert row["delta_b_minus_a"] < 0


def test_split_spell_counts_extra_piece_as_spurious() -> None:
    gt = codes("HHHHHDDDAAADDD")
    split = codes("HHDHHDDDAAADDD")

    result = compare.compare_codes(gt, split, gt)

    # The comparison's first side has two H predictions for one GT H possession.
    for row in result["per_iou"].values():
        assert row["a"]["n_pred"] == 3
        assert row["a"]["n_spurious"] >= 1
        assert row["b"]["n_spurious"] == 0


def test_jackknife_retains_predictions_and_recomputes_full_matching() -> None:
    gt = codes("HHHDDDAAADDDHHH")
    a = codes("HHHDDDAAADDDHHH")
    b = codes("HHHDDDAAADDDDDD")
    result = compare.compare_codes(gt, a, b, include_class_breakdown=True)
    gt_spells = pm.possession_spells(gt, pm.valid_runs(gt))
    pred_a = pm.possession_spells(pm.fill_abstentions(a, pm.valid_runs(gt)), pm.valid_runs(gt))
    pred_b = pm.possession_spells(pm.fill_abstentions(b, pm.valid_runs(gt)), pm.valid_runs(gt))

    assert len(result["jackknife"]["replicates"]) == len(gt_spells)
    for row in result["jackknife"]["replicates"]:
        excluded = row["excluded_gt_possession"] - 1
        remaining = gt_spells[:excluded] + gt_spells[excluded + 1 :]
        expected_a = compare.score_spells(remaining, pred_a)
        expected_b = compare.score_spells(remaining, pred_b)
        assert (
            row["counts_by_iou"]["0.5"]["a"]["n_matched"]
            == expected_a["per_iou"]["0.5"]["n_matched"]
        )
        assert (
            row["counts_by_iou"]["0.5"]["b"]["n_spurious"]
            == expected_b["per_iou"]["0.5"]["n_spurious"]
        )
        assert row["delta_mean_spell_f1"] == pytest.approx(
            expected_b["mean_spell_f1"] - expected_a["mean_spell_f1"]
        )
        assert len(pred_a) == len(gt_spells)
        assert row["n_gt_remaining"] == len(gt_spells) - 1
        class_counts = {
            name: values["n_gt"] for name, values in row["by_possession_class"]["classes"].items()
        }
        assert sum(class_counts.values()) == len(gt_spells) - 1


def test_sign_diagnostic_exact_two_sided_binomial_p_value() -> None:
    gt = [(i * 20, i * 20 + 10, pm.H) for i in range(6)]
    perfect = list(gt)
    no_matches: list[tuple[int, int, int]] = []

    result = compare.sign_diagnostic(gt, perfect, no_matches)

    assert result["wins_a"] == 6
    assert result["wins_b"] == 0
    assert result["ties"] == 0
    assert result["n_discordant"] == 6
    assert result["exact_two_sided_p"] == pytest.approx(0.03125)
    assert "not a test of delta spellF1" in result["scope"]
    assert "independent" in result["null_assumption"]
    assert len(result["per_possession"]) == 6
    assert result["by_duration_class"]["short"]["wins_a"] == 6


def test_sign_diagnostic_counts_wins_losses_and_ties_separately() -> None:
    gt = [(0, 10, pm.H), (20, 30, pm.A), (40, 50, pm.H)]
    pred_a = [gt[0], gt[1]]
    pred_b = [gt[1], gt[2]]

    result = compare.sign_diagnostic(gt, pred_a, pred_b)

    assert result["wins_a"] == 1
    assert result["wins_b"] == 1
    assert result["ties"] == 1
    assert result["exact_two_sided_p"] == 1.0


def test_fusion_is_scored_as_one_match_and_a_missed_opponent_possession() -> None:
    gt = codes("HHHDDDAAADDD")
    fused = codes("HHHHHHHHHDDD")

    result = compare.compare_codes(gt, fused, gt)

    assert result["per_iou"]["0.3"]["a"]["n_matched"] == 1
    assert result["per_iou"]["0.3"]["a"]["n_missed"] == 1
    assert result["per_iou"]["0.4"]["a"]["n_matched"] == 0
    assert result["per_iou"]["0.4"]["a"]["n_spurious"] == 1


def test_empty_or_mismatched_ground_truth_is_rejected() -> None:
    with pytest.raises(ValueError, match="same number of frames"):
        compare.compare_codes(codes("HH"), codes("HHH"), codes("HH"))
    with pytest.raises(ValueError, match="no graded frames"):
        compare.compare_codes(codes("XXXX"), codes("XXXX"), codes("XXXX"))
    with pytest.raises(ValueError, match="no H/A possessions"):
        compare.compare_codes(codes("DDDD"), codes("DDDD"), codes("DDDD"))


def test_invalid_submission_is_rejected(tmp_path: Path) -> None:
    bad = tmp_path / "bad.csv"
    bad.write_text("frame,label\n0,H\n2,A\n", encoding="utf-8")

    with pytest.raises(ValueError, match="invalid submission"):
        compare.read_codes(bad, 2, "submission")


def test_real_baseline_comparison_matches_official_scorer() -> None:
    root = compare.REPO_ROOT
    gt = compare.read_codes(
        root / "evaluation/gt/BAR-ATH_possession_gt_public.csv", 199319, "ground truth"
    )
    a = compare.read_codes(root / "evaluation/results/baseline_smooth50.csv", len(gt), "submission")
    b = compare.read_codes(
        root / "evaluation/results/baseline_smooth125.csv", len(gt), "submission"
    )
    result = compare.compare_codes(gt, a, b)
    official_a = pm.evaluate(gt, a, bootstrap_n=0)
    official_b = pm.evaluate(gt, b, bootstrap_n=0)

    assert result["a"]["mean_spell_f1"] == official_a["spell_f1_mean"]
    assert result["b"]["mean_spell_f1"] == official_b["spell_f1_mean"]
    for threshold in pm.SPELL_IOUS:
        key = f"{threshold:.1f}"
        assert (
            result["per_iou"][key]["a"]["n_spurious"]
            == official_a["spell_f1"][threshold]["n_spurious"]
        )
        assert (
            result["per_iou"][key]["b"]["n_spurious"]
            == official_b["spell_f1"][threshold]["n_spurious"]
        )


def test_comparison_is_deterministic() -> None:
    gt = codes("HHHDDDAAADDD")
    a = codes("HHHDDDAAADDD")
    b = codes("HHHHDDAAADDD")

    assert compare.compare_codes(gt, a, b) == compare.compare_codes(gt, a, b)


def test_duration_class_boundary_is_four_seconds() -> None:
    assert compare.duration_class((0, 99, pm.H)) == "short"
    assert compare.duration_class((0, 100, pm.H)) == "long"


def test_class_scores_partition_the_official_matched_and_missed_counts() -> None:
    gt_spells = [(0, 150, pm.H), (200, 260, pm.A), (300, 500, pm.H)]
    pred_spells = [(0, 150, pm.H), (200, 250, pm.A), (400, 500, pm.H), (600, 650, pm.H)]

    by_class = compare.class_spell_scores(gt_spells, pred_spells)
    official = compare.score_spells(gt_spells, pred_spells)

    assert by_class["classes"]["short"]["n_gt"] == 1
    assert by_class["classes"]["long"]["n_gt"] == 2
    assert by_class["official"] is False
    assert "not additive" in by_class["additivity"]
    for key, row in official["per_iou"].items():
        short = by_class["classes"]["short"]["per_iou"][key]
        long = by_class["classes"]["long"]["per_iou"][key]
        assert short["official"] is False
        assert long["official"] is False
        assert short["n_matched"] + long["n_matched"] == row["n_matched"]
        assert short["n_missed"] + long["n_missed"] == row["n_missed"]
        assert short["n_spurious_global"] == long["n_spurious_global"] == row["n_spurious"]
        assert short["recall"] == short["n_matched"] / short["n_gt"]
        assert long["recall"] == long["n_matched"] / long["n_gt"]


def test_class_delta_isolates_a_short_only_change() -> None:
    short = (0, 50, pm.H)  # 2 s
    long = (100, 400, pm.H)  # 12 s
    result = compare.compare_class_scores([short, long], [short, long], [long])

    assert result["classes"]["short"]["delta_mean_spell_f1_b_minus_a"] == -1.0
    assert result["classes"]["short"]["delta_mean_recall_b_minus_a"] == -1.0
    assert result["classes"]["long"]["delta_mean_spell_f1_b_minus_a"] == 0.0
    assert result["classes"]["long"]["delta_mean_recall_b_minus_a"] == 0.0
    for row in result["classes"]["short"]["per_iou"].values():
        assert row["delta_spell_f1_b_minus_a"] == -1.0
        assert row["delta_recall_b_minus_a"] == -1.0
    for row in result["classes"]["long"]["per_iou"].values():
        assert row["delta_spell_f1_b_minus_a"] == 0.0
        assert row["delta_recall_b_minus_a"] == 0.0


def test_spurious_prediction_lowers_both_class_f1_without_moving_tp() -> None:
    short = (0, 50, pm.H)
    long = (100, 400, pm.H)
    spurious = (500, 550, pm.A)
    result = compare.compare_class_scores([short, long], [short, long], [short, long, spurious])

    for name in ("short", "long"):
        for row in result["classes"][name]["per_iou"].values():
            assert row["b"]["n_spurious_global"] == row["a"]["n_spurious_global"] + 1
            assert row["delta_matched_b_minus_a"] == 0
            assert row["delta_recall_b_minus_a"] == 0
            assert row["delta_spell_f1_b_minus_a"] < 0


def test_public_slice_has_the_preregistered_six_short_and_eleven_long() -> None:
    gt = compare.read_codes(compare.resolve_ground_truth("public"), 199319, "ground truth")
    spells = pm.possession_spells(gt, pm.valid_runs(gt))
    counts = {"short": 0, "long": 0}
    for spell in spells:
        counts[compare.duration_class(spell)] += 1

    assert counts == {"short": 6, "long": 11}


def test_comparison_is_json_serializable_for_the_ledger() -> None:
    result = compare.compare_codes(
        codes("HHHDDDAAADDD"),
        codes("HHHDDDAAADDD"),
        codes("HHHHDDAAADDD"),
        include_class_breakdown=True,
    )

    encoded = json.dumps(result, sort_keys=True)
    assert '"by_possession_class"' in encoded
    assert '"duration_class": "short"' in encoded
    assert '"official": false' in encoded
    assert '"recall"' in encoded
    assert "not additive" in result["by_possession_class"]["additivity"]


def test_default_output_stays_b6_compatible_and_opts_in_to_classes() -> None:
    gt = codes("HHHDDDAAADDD")
    a = codes("HHHDDDAAADDD")
    b = codes("HHHHDDAAADDD")

    legacy = compare.compare_codes(gt, a, b)
    extended = compare.compare_codes(gt, a, b, include_class_breakdown=True)

    assert "by_possession_class" not in legacy
    assert all("n_gt_remaining" not in row for row in legacy["jackknife"]["replicates"])
    assert extended["per_iou"] == legacy["per_iou"]
    assert extended["sign_diagnostic"] == legacy["sign_diagnostic"]
    assert extended["jackknife"]["replicates"][0]["n_gt_remaining"] == 1
