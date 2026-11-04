"""Calibrate B5 temperature on two fixed external DFL matches, never on competition data.

The method and acceptance rule were registered in docs/proposals/b5-external-calibration.md.
Input hashes are verified; the command is offline and writes aggregate results only.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path
from typing import Any

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from tools import elastic_audit, external  # noqa: E402

TRAIN, CHECK = "J03WMX", "J03WN1"
PRIOR_M = 1.0
PENALTY = 0.01
LOWER, UPPER = 0.05, 20.0
STEPS = 80
MIN_FRAMES = 1000


def nearest(players: np.ndarray, ball: np.ndarray) -> np.ndarray:
    """Distance to the nearest available player, with infinity when no player is known."""
    if players.shape[1] == 0:
        return np.full(len(ball), np.inf)
    distances = np.linalg.norm(players - ball[:, None, :], axis=2)
    distances[~np.isfinite(distances)] = np.inf
    return distances.min(axis=1)


def samples(raw: external.Raw) -> tuple[np.ndarray, np.ndarray, dict[str, int]]:
    """Return distance margins, binary DFL owners and population counts for one match."""
    margins, labels = [], []
    counts = {"total": 0, "alive_owner": 0, "inside": 0, "eligible": 0, "home": 0, "away": 0}
    length, width = raw.pitch
    for section in raw.sections:
        ball = section.ball
        counts["total"] += len(ball)
        alive = (section.status == 1) & np.isin(section.possession, (1, 2))
        counts["alive_owner"] += int(alive.sum())
        inside = (
            alive
            & np.isfinite(ball).all(axis=1)
            & (np.abs(ball[:, 0]) <= length / 2)
            & (np.abs(ball[:, 1]) <= width / 2)
        )
        counts["inside"] += int(inside.sum())

        home, away = nearest(section.home, ball), nearest(section.away, ball)
        eligible = inside & np.isfinite(home) & np.isfinite(away)
        owner = section.possession[eligible]
        counts["eligible"] += int(eligible.sum())
        counts["home"] += int((owner == 1).sum())
        counts["away"] += int((owner == 2).sum())
        margins.append(away[eligible] - home[eligible])
        labels.append((owner == 1).astype(np.int8))
    return np.concatenate(margins), np.concatenate(labels), counts


def loss(margin: np.ndarray, home: np.ndarray, temperature: float) -> float:
    """Binary log loss, calculated stably for large distance margins."""
    signed = np.where(home == 1, 1.0, -1.0)
    return float(np.logaddexp(0.0, -signed * margin / temperature).mean())


def brier(margin: np.ndarray, home: np.ndarray, temperature: float) -> float:
    z = margin / temperature
    p = np.empty_like(z, dtype=float)
    positive = z >= 0
    p[positive] = 1.0 / (1.0 + np.exp(-z[positive]))
    e = np.exp(z[~positive])
    p[~positive] = e / (1.0 + e)
    return float(np.square(p - home).mean())


def calibrate(margin: np.ndarray, home: np.ndarray) -> float:
    """Deterministic 80-step golden search with the preregistered log-scale prior."""
    lower, upper = math.log(LOWER), math.log(UPPER)
    ratio = (math.sqrt(5.0) - 1.0) / 2.0

    def objective(log_t: float) -> float:
        return loss(margin, home, math.exp(log_t)) + PENALTY * (log_t - math.log(PRIOR_M)) ** 2

    left = upper - ratio * (upper - lower)
    right = lower + ratio * (upper - lower)
    left_loss, right_loss = objective(left), objective(right)
    for _ in range(STEPS):
        if left_loss <= right_loss:
            upper, right, right_loss = right, left, left_loss
            left = upper - ratio * (upper - lower)
            left_loss = objective(left)
        else:
            lower, left, left_loss = left, right, right_loss
            right = lower + ratio * (upper - lower)
            right_loss = objective(right)
    return round(math.exp((lower + upper) / 2.0), 12)


def accepts(candidate: float, candidate_loss: float, prior_loss: float) -> bool:
    """Apply the preregistered check-match gate, without access to competition scores."""
    return LOWER < candidate < UPPER and candidate_loss < prior_loss - 1e-12


def run() -> dict[str, Any]:
    """Evaluate only the preregistered external training and check matches."""
    directory = ROOT / "runs" / "external" / "idsse"
    data = {}
    fingerprints = {}
    for match in (TRAIN, CHECK):
        metadata, tracking = external._files(match, directory)
        hashes = {
            "metadatos": elastic_audit.file_hash(metadata),
            "tracking": elastic_audit.file_hash(tracking),
        }
        expected = elastic_audit.EXPECTED_SHA256[match]
        if any(hashes[k] != expected[k] for k in hashes):
            raise ValueError(f"external input fingerprints differ for {match}")
        # Parse the fingerprinted XML directly: an unchecked cache could be stale or altered.
        home_id, away_id, _ = external.meta(metadata)
        data[match] = samples(external.parse_positions(tracking, home_id, away_id, match))
        fingerprints[match] = hashes
    if any(
        c["eligible"] < MIN_FRAMES or not c["home"] or not c["away"] for _, _, c in data.values()
    ):
        return {"status": "inconclusive_insufficient_data", "counts": {m: data[m][2] for m in data}}
    candidate = calibrate(*data[TRAIN][:2])
    metrics = {}
    for match, (margin, home, counts) in data.items():
        metrics[match] = {
            "counts": counts,
            "candidate_log_loss": loss(margin, home, candidate),
            "candidate_brier": brier(margin, home, candidate),
            "prior_log_loss": loss(margin, home, PRIOR_M),
            "prior_brier": brier(margin, home, PRIOR_M),
        }
    accepted = accepts(
        candidate, metrics[CHECK]["candidate_log_loss"], metrics[CHECK]["prior_log_loss"]
    )
    return {
        "status": "accepted_dfl_only" if accepted else "inconclusive",
        "candidate_m": candidate,
        "metrics": metrics,
        "input_sha256": fingerprints,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write", type=Path, help="write aggregate JSON instead of stdout")
    args = parser.parse_args()
    result = json.dumps(run(), sort_keys=True, indent=2) + "\n"
    if args.write:
        with args.write.open("w", encoding="utf-8", newline="\n") as destination:
            destination.write(result)
    else:
        print(result, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
