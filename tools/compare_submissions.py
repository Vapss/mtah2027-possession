"""Compare two submissions with the official possession metric and paired diagnostics.

The official scorer remains authoritative. The sign test below asks only which submission matches
more individual ground-truth possessions at IoU 0.5; it is not a significance test for spellF1.
"""

from __future__ import annotations

import argparse
import glob
import json
import math
import sys
from pathlib import Path
from typing import Any

import numpy as np

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "evaluation"))

import possession_metrics as pm  # noqa: E402

import games  # noqa: E402


def resolve_ground_truth(value: str) -> Path:
    """Resolve public/private aliases like the official evaluator, or accept a CSV path."""
    candidate = Path(value)
    if value not in {"public", "private"}:
        if not candidate.is_file():
            raise ValueError(f"ground truth does not exist: {candidate}")
        return candidate

    pattern = "*_possession_gt_public.csv" if value == "public" else "*_possession_gt.csv"
    matches = sorted(glob.glob(str(REPO_ROOT / "evaluation" / "gt" / pattern)))
    if not matches:
        raise ValueError(f"no {value} ground truth found under evaluation/gt")
    if len(matches) > 1:
        raise ValueError(f"multiple {value} ground truths found; pass an explicit CSV path")
    return Path(matches[0])


def read_codes(path: str | Path, expected_frames: int, description: str) -> np.ndarray:
    """Read and validate a frame,label table with the official submission contract."""
    try:
        table = pm.read_label_csv(path)
    except (OSError, ValueError, UnicodeError) as error:
        raise ValueError(f"cannot read {description} {path}: {error}") from error
    problem = pm.validate_submission(table, expected_frames)
    if problem:
        raise ValueError(f"invalid {description} {path}: {problem}")
    return pm.label_codes(table)


def score_spells(
    gt_spells: list[tuple[int, int, int]], pred_spells: list[tuple[int, int, int]]
) -> dict[str, Any]:
    """Recompute official spell F1 from explicit GT spells, keeping every prediction in scope."""
    overlaps = pm.spell_overlaps(gt_spells, pred_spells)
    per_iou: dict[str, dict[str, int | float]] = {}
    scores = []
    for threshold in pm.SPELL_IOUS:
        tp, fp, fn = pm.match_spells(overlaps, len(gt_spells), len(pred_spells), threshold)
        precision = tp / (tp + fp) if tp + fp else 0.0
        recall = tp / (tp + fn) if tp + fn else 0.0
        f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
        per_iou[f"{threshold:.1f}"] = {
            "spell_f1": f1,
            "n_gt": len(gt_spells),
            "n_pred": len(pred_spells),
            "n_matched": tp,
            "n_missed": fn,
            "n_spurious": fp,
        }
        scores.append(f1)
    return {
        "n_gt": len(gt_spells),
        "n_pred": len(pred_spells),
        "mean_spell_f1": float(np.mean(scores)) if scores else 0.0,
        "per_iou": per_iou,
    }


def match_flags_by_iou(
    gt_spells: list[tuple[int, int, int]], pred_spells: list[tuple[int, int, int]]
) -> dict[str, np.ndarray]:
    """Return the official one-to-one match flag for every GT possession and IoU."""
    overlaps = pm.spell_overlaps(gt_spells, pred_spells)
    return {
        f"{threshold:.1f}": pm.matched_gt_flags(overlaps, len(gt_spells), threshold)
        for threshold in pm.SPELL_IOUS
    }


def sign_diagnostic(
    gt_spells: list[tuple[int, int, int]],
    pred_a: list[tuple[int, int, int]],
    pred_b: list[tuple[int, int, int]],
) -> dict[str, int | float | str]:
    """Exact two-sided sign test on per-GT match status at the headline IoU only."""
    threshold = pm.SPELL_IOU_HEADLINE
    key = f"{threshold:.1f}"
    flags_a_by_iou = match_flags_by_iou(gt_spells, pred_a)
    flags_b_by_iou = match_flags_by_iou(gt_spells, pred_b)
    flags_a = flags_a_by_iou[key]
    flags_b = flags_b_by_iou[key]
    wins_a = int(np.sum(flags_a & ~flags_b))
    wins_b = int(np.sum(flags_b & ~flags_a))
    discordant = wins_a + wins_b
    tail = sum(math.comb(discordant, k) for k in range(min(wins_a, wins_b) + 1))
    p_value = min(1.0, 2.0 * tail / (2**discordant)) if discordant else 1.0
    per_possession = []
    by_duration = {
        "short": {"wins_a": 0, "wins_b": 0, "ties": 0, "delta_matched_b_minus_a": {}},
        "long": {"wins_a": 0, "wins_b": 0, "ties": 0, "delta_matched_b_minus_a": {}},
    }
    for bucket in by_duration.values():
        bucket["delta_matched_b_minus_a"] = dict.fromkeys(flags_a_by_iou, 0)
    for index, (start, stop, team) in enumerate(gt_spells):
        duration_frames = stop - start
        duration_class = "short" if duration_frames < 4 * pm.FPS else "long"
        headline_a, headline_b = bool(flags_a[index]), bool(flags_b[index])
        outcome = "tie" if headline_a == headline_b else "a" if headline_a else "b"
        bucket = by_duration[duration_class]
        bucket["wins_a" if outcome == "a" else "wins_b" if outcome == "b" else "ties"] += 1
        per_possession.append(
            {
                "gt_possession": index + 1,
                "start_frame": start,
                "stop_frame_exclusive": stop,
                "team": pm.LABELS[team],
                "duration_frames": duration_frames,
                "duration_seconds": duration_frames / pm.FPS,
                "duration_class": duration_class,
                "matched_a_by_iou": {
                    iou: bool(flags[index]) for iou, flags in flags_a_by_iou.items()
                },
                "matched_b_by_iou": {
                    iou: bool(flags[index]) for iou, flags in flags_b_by_iou.items()
                },
                "headline_outcome": outcome,
            }
        )
        for iou in flags_a_by_iou:
            bucket["delta_matched_b_minus_a"][iou] += int(flags_b_by_iou[iou][index]) - int(
                flags_a_by_iou[iou][index]
            )
    return {
        "scope": (
            f"per-GT match status at IoU {threshold:.1f}; diagnostic only, "
            "not a test of delta spellF1"
        ),
        "null_assumption": "discordant possession outcomes are independent and equally likely",
        "wins_a": wins_a,
        "wins_b": wins_b,
        "ties": len(gt_spells) - discordant,
        "n_discordant": discordant,
        "exact_two_sided_p": p_value,
        "per_possession": per_possession,
        "by_duration_class": by_duration,
    }


def compare_codes(gt_codes: np.ndarray, codes_a: np.ndarray, codes_b: np.ndarray) -> dict[str, Any]:
    """Official comparison, jackknife over GT possessions, and a separate sign diagnostic."""
    if len(gt_codes) != len(codes_a) or len(gt_codes) != len(codes_b):
        raise ValueError("ground truth and both submissions must have the same number of frames")
    runs = pm.valid_runs(gt_codes)
    if not runs:
        raise ValueError("ground truth has no graded frames")

    filled_a = pm.fill_abstentions(codes_a, runs)
    filled_b = pm.fill_abstentions(codes_b, runs)
    gt_spells = pm.possession_spells(gt_codes, runs)
    if not gt_spells:
        raise ValueError("ground truth has no H/A possessions")
    pred_a = pm.possession_spells(filled_a, runs)
    pred_b = pm.possession_spells(filled_b, runs)
    official_a = pm.spell_scores(gt_codes, filled_a, runs)
    official_b = pm.spell_scores(gt_codes, filled_b, runs)

    per_iou = {}
    for threshold in pm.SPELL_IOUS:
        key = threshold
        a = official_a["per_iou"][key]
        b = official_b["per_iou"][key]
        per_iou[f"{threshold:.1f}"] = {
            "a": {
                "spell_f1": a["f1"],
                "n_gt": official_a["n_gt"],
                "n_pred": official_a["n_pred"],
                "n_matched": a["n_matched"],
                "n_missed": a["n_missed"],
                "n_spurious": a["n_spurious"],
            },
            "b": {
                "spell_f1": b["f1"],
                "n_gt": official_b["n_gt"],
                "n_pred": official_b["n_pred"],
                "n_matched": b["n_matched"],
                "n_missed": b["n_missed"],
                "n_spurious": b["n_spurious"],
            },
            "delta_b_minus_a": b["f1"] - a["f1"],
        }

    jackknife = []
    for excluded, _spell in enumerate(gt_spells):
        remaining = gt_spells[:excluded] + gt_spells[excluded + 1 :]
        score_a = score_spells(remaining, pred_a)
        score_b = score_spells(remaining, pred_b)
        fold_delta_by_iou = {
            key: score_b["per_iou"][key]["spell_f1"] - score_a["per_iou"][key]["spell_f1"]
            for key in score_a["per_iou"]
        }
        jackknife.append(
            {
                "excluded_gt_possession": excluded + 1,
                "spell_f1_a": score_a["mean_spell_f1"],
                "spell_f1_b": score_b["mean_spell_f1"],
                "delta_mean_spell_f1": score_b["mean_spell_f1"] - score_a["mean_spell_f1"],
                "delta_by_iou": fold_delta_by_iou,
                "counts_by_iou": {
                    key: {
                        "a": {
                            metric: score_a["per_iou"][key][metric]
                            for metric in ("n_matched", "n_missed", "n_spurious")
                        },
                        "b": {
                            metric: score_b["per_iou"][key][metric]
                            for metric in ("n_matched", "n_missed", "n_spurious")
                        },
                    }
                    for key in score_a["per_iou"]
                },
            }
        )
    jackknife_deltas = [row["delta_mean_spell_f1"] for row in jackknife]
    full_delta = official_b["mean_f1"] - official_a["mean_f1"]
    has_positive = any(delta > 0 for delta in jackknife_deltas)
    has_negative = any(delta < 0 for delta in jackknife_deltas)

    return {
        "n_gt_possessions": len(gt_spells),
        "a": {"n_pred": len(pred_a), "mean_spell_f1": official_a["mean_f1"]},
        "b": {"n_pred": len(pred_b), "mean_spell_f1": official_b["mean_f1"]},
        "delta_mean_spell_f1_b_minus_a": full_delta,
        "per_iou": per_iou,
        "jackknife": {
            "unit": "leave one ground-truth possession out; all predictions retained and rematched",
            "replicates": jackknife,
            "mean_delta_range": (
                [min(jackknife_deltas), max(jackknife_deltas)] if jackknife_deltas else [0.0, 0.0]
            ),
            "contains_both_positive_and_negative_deltas": has_positive and has_negative,
            "sign_differs_from_full_delta": any(
                (delta > 0 > full_delta) or (delta < 0 < full_delta) for delta in jackknife_deltas
            ),
        },
        "sign_diagnostic": sign_diagnostic(gt_spells, pred_a, pred_b),
        "interpretation": (
            "The sign-test p-value describes discordant per-ground-truth match status only. "
            "It is not inferential evidence for the official spellF1 delta; the official score "
            "also penalizes all unmatched predicted spells."
        ),
    }


def compare_files(path_a: str | Path, path_b: str | Path, gt_path: str | Path) -> dict[str, Any]:
    gt = read_codes(gt_path, games.source_frames(), "ground truth")
    a = read_codes(path_a, len(gt), "submission")
    b = read_codes(path_b, len(gt), "submission")
    return compare_codes(gt, a, b)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Compare two submissions on official spellF1")
    parser.add_argument("submission_a")
    parser.add_argument("submission_b")
    parser.add_argument("--gt", default="public", help="public, private, or a frame,label CSV path")
    args = parser.parse_args(argv)
    try:
        result = compare_files(args.submission_a, args.submission_b, resolve_ground_truth(args.gt))
    except (OSError, ValueError) as error:
        print(f"comparison failed: {error}", file=sys.stderr)
        return 1
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
