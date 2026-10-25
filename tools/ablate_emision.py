"""Run the preregistered B5 emission ablation on the public tracking window.

This is a diagnostic, not a model-selection command: it evaluates exactly three declared
variants and compares them with a nearest-player softmax whose scalar temperature is calibrated
on the same public H/A frames. The in-sample calibration is reported as such.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import numpy as np

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "evaluation"))

import possession_metrics as pm  # noqa: E402

from tools import atd, emision  # noqa: E402

THRESHOLDS = (0.55, 0.60, 0.65, 0.70, 0.80)
TEMPERATURE_BOUNDS = (0.01, 100.0)


def _normalise_pair(first: np.ndarray, second: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    total = first + second
    a = np.full(total.shape, 0.5, dtype=float)
    b = np.full(total.shape, 0.5, dtype=float)
    valid = total > 0
    a[valid] = first[valid] / total[valid]
    b[valid] = second[valid] / total[valid]
    return a, b


def _softmax_nearest(d_home: np.ndarray, d_away: np.ndarray, temperature: float) -> np.ndarray:
    logits = -np.column_stack((d_home, d_away)) / temperature
    logits -= np.max(logits, axis=1, keepdims=True)
    weights = np.exp(logits)
    return weights / weights.sum(axis=1, keepdims=True)


def _fit_temperature(d_home: np.ndarray, d_away: np.ndarray, truth: np.ndarray) -> float:
    """Golden-section minimization on the preregistered positive temperature interval."""
    lower, upper = np.log(TEMPERATURE_BOUNDS)
    ratio = (np.sqrt(5.0) - 1.0) / 2.0

    def loss(log_temperature: float) -> float:
        probs = _softmax_nearest(d_home, d_away, np.exp(log_temperature))
        return float(-np.log(np.clip(probs[np.arange(len(truth)), truth], 1e-15, 1.0)).mean())

    left = upper - ratio * (upper - lower)
    right = lower + ratio * (upper - lower)
    left_loss, right_loss = loss(left), loss(right)
    for _ in range(160):
        if left_loss <= right_loss:
            upper, right, right_loss = right, left, left_loss
            left = upper - ratio * (upper - lower)
            left_loss = loss(left)
        else:
            lower, left, left_loss = left, right, right_loss
            right = lower + ratio * (upper - lower)
            right_loss = loss(right)
    return float(np.exp((lower + upper) / 2.0))


def _speed_factor(speed_mps: np.ndarray) -> np.ndarray:
    factor = np.ones(len(speed_mps), dtype=float)
    measured = np.isfinite(speed_mps)
    factor[measured] = np.exp(
        -0.5 * np.square(speed_mps[measured] / (emision.SIGMA_M * emision.FPS))
    )
    return factor


def _confidence(vote_mass: np.ndarray, speed_mps: np.ndarray) -> np.ndarray:
    return (1.0 - np.exp(-2.0 * vote_mass)) * _speed_factor(speed_mps)


def _metrics(
    probabilities: np.ndarray, confidence: np.ndarray, output_scale: np.ndarray, truth: np.ndarray
) -> dict[str, Any]:
    predicted = probabilities.argmax(axis=1)
    class_metrics: dict[str, Any] = {}
    brier_values = []
    losses = []
    for index, label in enumerate(("H", "A")):
        is_class = truth == index
        loss = float(-np.log(np.clip(probabilities[is_class, index], 1e-15, 1.0)).mean())
        brier = float(np.mean(np.square(probabilities[:, index] - is_class.astype(float))))
        class_metrics[label] = {
            "n_actual": int(is_class.sum()),
            "log_loss": loss,
            "brier_one_vs_rest": brier,
        }
        losses.append(loss)
        brier_values.append(brier)

    def curve(signal: np.ndarray) -> list[dict[str, Any]]:
        rows = []
        for threshold in THRESHOLDS:
            chosen = signal >= threshold
            rows.append(
                {
                    "threshold": threshold,
                    "n_covered": int(chosen.sum()),
                    "coverage": float(chosen.mean()),
                    "accuracy": float(np.mean(predicted[chosen] == truth[chosen]))
                    if chosen.any()
                    else None,
                }
            )
        return rows

    selective_signal = probabilities.max(axis=1) * output_scale
    return {
        "n_frames": len(truth),
        "accuracy": float(np.mean(predicted == truth)),
        "log_loss": float(
            -np.log(np.clip(probabilities[np.arange(len(truth)), truth], 1e-15, 1.0)).mean()
        ),
        "mean_class_log_loss": float(np.mean(losses)),
        "mean_class_brier": float(np.mean(brier_values)),
        "by_class": class_metrics,
        "coverage_accuracy_by_max_p": curve(selective_signal),
        "coverage_accuracy_by_confidence": curve(confidence),
    }


def run(gt_path: str | Path | None = None) -> dict[str, Any]:
    tracking = atd.load("tactical")
    teams = emision.team_slots()
    base = emision.emit(tracking, teams)
    source = (
        Path(gt_path) if gt_path else REPO_ROOT / "evaluation/gt/BAR-ATH_possession_gt_public.csv"
    )
    table = pm.read_label_csv(source)
    problem = pm.validate_submission(table, emision.N_FRAMES)
    if problem:
        raise ValueError(f"invalid public ground truth: {problem}")
    labels = pm.label_codes(table)
    eligible = ((labels == pm.H) | (labels == pm.A)) & base.ball_present
    truth = labels[eligible]

    players = tracking.players_array[:, :, :2] * np.asarray(emision.PITCH_M)
    ball, _present = tracking.ball()
    ball_xy = ball[:, :2] * np.asarray(emision.PITCH_M)
    player_present = np.isfinite(players).all(axis=2)
    distances = np.linalg.norm(players - ball_xy[:, None, :], axis=2)
    distances[~player_present] = np.inf

    home_mask = teams.codes == 0
    away_mask = teams.codes == 1
    d_home = np.min(np.where(home_mask[None, :], distances, np.inf), axis=1)
    d_away = np.min(np.where(away_mask[None, :], distances, np.inf), axis=1)
    d_home_eval = d_home[eligible]
    d_away_eval = d_away[eligible]
    temperature = _fit_temperature(d_home_eval, d_away_eval, truth)
    baseline = _softmax_nearest(d_home_eval, d_away_eval, temperature)
    nearest_confidence = baseline.max(axis=1) * (1.0 - base.artifact["p_dead"].to_numpy()[eligible])

    # The three candidate variants are exactly those written in DECISIONS.md section 19.
    nearest = _softmax_nearest(d_home_eval, d_away_eval, emision.SIGMA_M)

    k = 3
    nearest_indices = np.argpartition(distances, kth=k - 1, axis=1)[:, :k]
    nearest_distances = np.take_along_axis(distances, nearest_indices, axis=1)
    weights3 = np.exp(-0.5 * np.square(nearest_distances / emision.SIGMA_M))
    teams3 = teams.codes[nearest_indices]
    vote3_home = np.sum(weights3 * (teams3 == 0), axis=1)
    vote3_away = np.sum(weights3 * (teams3 == 1), axis=1)
    vote3 = _normalise_pair(vote3_home, vote3_away)
    count_home, count_away = _normalise_pair(
        base.home_players_within_10m.astype(float), base.away_players_within_10m.astype(float)
    )
    centroid_home, centroid_away = _normalise_pair(
        np.exp(-0.5 * np.square(base.home_centroid_distance_m / emision.CONTEXT_RADIUS_M)),
        np.exp(-0.5 * np.square(base.away_centroid_distance_m / emision.CONTEXT_RADIUS_M)),
    )
    vote3_context = np.column_stack(
        (
            emision.VOTE_MIX[0] * vote3[0]
            + emision.VOTE_MIX[1] * centroid_home
            + emision.VOTE_MIX[2] * count_home,
            emision.VOTE_MIX[0] * vote3[1]
            + emision.VOTE_MIX[1] * centroid_away
            + emision.VOTE_MIX[2] * count_away,
        )
    )
    vote3_context /= vote3_context.sum(axis=1, keepdims=True)
    vote3_conf = _confidence(weights3.sum(axis=1), base.ball_speed_mps)

    k5 = min(emision.NEAREST_K, tracking.n_slots)
    indices5 = np.argpartition(distances, kth=k5 - 1, axis=1)[:, :k5]
    distances5 = np.take_along_axis(distances, indices5, axis=1)
    weights5 = np.exp(-0.5 * np.square(distances5 / emision.SIGMA_M))
    teams5 = teams.codes[indices5]
    v5 = _normalise_pair(
        np.sum(weights5 * (teams5 == 0), axis=1),
        np.sum(weights5 * (teams5 == 1), axis=1),
    )
    no_density = np.column_stack(
        (
            (8.0 / 9.0) * v5[0] + (1.0 / 9.0) * centroid_home,
            (8.0 / 9.0) * v5[1] + (1.0 / 9.0) * centroid_away,
        )
    )
    no_density /= no_density.sum(axis=1, keepdims=True)
    full_context = np.column_stack(
        (
            emision.VOTE_MIX[0] * v5[0]
            + emision.VOTE_MIX[1] * centroid_home
            + emision.VOTE_MIX[2] * count_home,
            emision.VOTE_MIX[0] * v5[1]
            + emision.VOTE_MIX[1] * centroid_away
            + emision.VOTE_MIX[2] * count_away,
        )
    )
    full_context /= full_context.sum(axis=1, keepdims=True)
    confidence5 = _confidence(weights5.sum(axis=1), base.ball_speed_mps)

    base_probabilities = base.artifact[["p_home", "p_away"]].to_numpy(copy=True)
    base_probabilities /= base_probabilities.sum(axis=1, keepdims=True)
    output_scale = (1.0 - base.artifact["p_dead"].to_numpy())[eligible]
    rows = {
        "argmin_temperature_calibrated_reference": _metrics(
            baseline, nearest_confidence, output_scale, truth
        ),
        "a_nearest_single": _metrics(
            nearest,
            np.exp(-np.minimum(d_home_eval, d_away_eval) / emision.SIGMA_M),
            output_scale,
            truth,
        ),
        "b_top3_vote": _metrics(vote3_context[eligible], vote3_conf[eligible], output_scale, truth),
        "c_top5_centroid_no_density": _metrics(
            no_density[eligible],
            confidence5[eligible],
            output_scale,
            truth,
        ),
        "d_top5_full_context_negative_control": _metrics(
            full_context[eligible], confidence5[eligible], output_scale, truth
        ),
    }
    rows["delivered_calibrated_argmin"] = _metrics(
        base_probabilities[eligible],
        base.artifact["confidence"].to_numpy()[eligible],
        output_scale,
        truth,
    )
    return {
        "ground_truth": str(source),
        "eligible_frames": int(eligible.sum()),
        "excluded_live_frames_without_ball": int(
            (((labels == pm.H) | (labels == pm.A)) & ~base.ball_present).sum()
        ),
        "temperature_calibration": {
            "temperature_m": temperature,
            "method": "golden-section minimum of H/A log-loss on this same public sample",
            "in_sample": True,
            "bounds": TEMPERATURE_BOUNDS,
        },
        "variants": rows,
        "interpretation": "Public-window diagnostic; no variant is selected by these metrics.",
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--gt", default=None, help="public ground-truth CSV path")
    parser.add_argument("--output", default=None, help="optional JSON output path")
    args = parser.parse_args(argv)
    result = run(args.gt)
    rendered = json.dumps(result, indent=2, sort_keys=True)
    if args.output:
        Path(args.output).write_text(rendered + "\n", encoding="utf-8")
    print(rendered)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
