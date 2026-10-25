"""Deterministic continuous possession emissions from tracking and team metadata.

This module emits H/A evidence only. It deliberately does not decode time or detect dead-ball
states; those belong to the possession decoder and dead-ball stream respectively.
"""

from __future__ import annotations

import argparse
import json
import sys
import xml.etree.ElementTree as ET
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "evaluation"))

import possession_metrics as pm  # noqa: E402

import games  # noqa: E402
from tools import atd, smart_tagging  # noqa: E402
from tools.contract import check_artifact  # noqa: E402

FPS = int(games.GAMES[games.GAME]["fps"])
PITCH_M = tuple(float(value) for value in games.GAMES[games.GAME]["pitch"])
N_FRAMES = games.source_frames()

# Fixed physical starting point. Parameter searches belong to #22 and must be pre-registered.
SIGMA_M = 1.84
NEAREST_K = 5
CONTEXT_RADIUS_M = 10.0
VOTE_MIX = (0.80, 0.10, 0.10)  # nearest-player vote, team centroid, nearby-player count
P_DEAD_FLOOR = 0.02
P_DEAD_OUT_OF_BOUNDS = 0.15


@dataclass(frozen=True)
class TeamSlots:
    """Team identity for each raw ATD player slot, in the XML's player order."""

    codes: np.ndarray  # 0 = local/home, 1 = visiting/away
    home_name: str
    away_name: str
    home_slots: int
    away_slots: int


@dataclass(frozen=True)
class Emission:
    """The contract artifact plus frame-aligned physical context for diagnostics."""

    artifact: pd.DataFrame
    ball_present: np.ndarray
    ball_speed_mps: np.ndarray
    nearest_distance_m: np.ndarray
    home_centroid_distance_m: np.ndarray
    away_centroid_distance_m: np.ndarray
    home_players_within_10m: np.ndarray
    away_players_within_10m: np.ndarray
    ball_out_of_bounds: np.ndarray


def team_slots(xml_path: str | Path | None = None) -> TeamSlots:
    """Read home/away slot ownership from the ATD XML, failing closed on unknown identity."""
    source = Path(xml_path) if xml_path is not None else Path(games.asset_paths()["atd_meta"])
    if not source.is_file():
        raise FileNotFoundError(f"ATD metadata not found: {source}")

    root = ET.parse(source).getroot()
    teams = {
        element.attrib["id"]: (element.findtext("Name") or "").strip()
        for element in root.findall(".//Teams/Team")
    }
    scores = root.findall(".//Score")
    if len(scores) != 1:
        raise ValueError(f"expected one <Score> in {source}, found {len(scores)}")
    local_id = scores[0].attrib.get("idLocalTeam")
    visiting_id = scores[0].attrib.get("idVisitingTeam")
    if local_id not in teams or visiting_id not in teams or local_id == visiting_id:
        raise ValueError("ATD metadata does not identify distinct local and visiting teams")

    players = root.findall(".//Players/Player")
    if len(players) != atd.FINGERPRINTS["tactical"].slots:
        raise ValueError(
            f"ATD XML has {len(players)} player tracks, expected "
            f"{atd.FINGERPRINTS['tactical'].slots}"
        )
    try:
        player_ids = [int(player.attrib["id"]) for player in players]
    except (KeyError, ValueError) as error:
        raise ValueError("ATD player tracks need integer ids") from error
    if player_ids != list(range(1, len(players) + 1)):
        raise ValueError("ATD player tracks must be ordered by ids 1..N to align with raw slots")

    codes = []
    for player in players:
        owner = player.attrib.get("teamId")
        if owner == local_id:
            codes.append(0)
        elif owner == visiting_id:
            codes.append(1)
        else:
            raise ValueError(f"player track {player.attrib.get('id')} has unknown teamId {owner!r}")
    counts = Counter(codes)
    if counts != Counter({0: 24, 1: 22}):
        raise ValueError(
            f"unexpected ATD team-slot distribution: home={counts[0]}, away={counts[1]}"
        )

    slots = np.asarray(codes, dtype=np.int8)
    slots.flags.writeable = False
    return TeamSlots(slots, teams[local_id], teams[visiting_id], counts[0], counts[1])


def _normalise_pair(first: np.ndarray, second: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    total = first + second
    valid = total > 0
    a = np.full(total.shape, 0.5, dtype=float)
    b = np.full(total.shape, 0.5, dtype=float)
    a[valid] = first[valid] / total[valid]
    b[valid] = second[valid] / total[valid]
    return a, b


def _ball_speed(ball_xy_m: np.ndarray, present: np.ndarray) -> np.ndarray:
    """Frame-to-frame ball speed; gaps and half-time are never bridged."""
    speed = np.full(len(ball_xy_m), np.nan, dtype=float)
    consecutive = present[1:] & present[:-1]
    differences = np.diff(ball_xy_m, axis=0)
    indices = np.flatnonzero(consecutive) + 1
    speed[indices] = np.linalg.norm(differences[consecutive], axis=1) * FPS
    return speed


def emit(tracking: atd.Tracking, teams: TeamSlots) -> Emission:
    """Compute soft H/A evidence and a weak D floor from one tactical tracking table."""
    if tracking.n_slots != len(teams.codes):
        raise ValueError(
            f"tracking has {tracking.n_slots} player slots but metadata maps {len(teams.codes)}"
        )
    players = tracking.players_array[:, :, :2] * np.asarray(PITCH_M, dtype=float)
    ball, present = tracking.ball()
    ball_xy_m = ball[:, :2] * np.asarray(PITCH_M, dtype=float)
    if players.shape[0] != len(present):
        raise ValueError("player and ball frame counts differ")

    player_present = np.isfinite(players).all(axis=2)
    distances = np.full(player_present.shape, np.inf, dtype=float)
    valid_rows = np.flatnonzero(present)
    if len(valid_rows):
        delta = players[valid_rows] - ball_xy_m[valid_rows, None, :]
        row_distances = np.linalg.norm(delta, axis=2)
        row_distances[~player_present[valid_rows]] = np.inf
        distances[valid_rows] = row_distances

    k = min(NEAREST_K, tracking.n_slots)
    nearest_indices = np.argpartition(distances, kth=k - 1, axis=1)[:, :k]
    nearest_distances = np.take_along_axis(distances, nearest_indices, axis=1)
    vote_weights = np.exp(-0.5 * np.square(nearest_distances / SIGMA_M))
    nearest_teams = teams.codes[nearest_indices]
    vote_home = np.sum(vote_weights * (nearest_teams == 0), axis=1)
    vote_away = np.sum(vote_weights * (nearest_teams == 1), axis=1)
    vote_home_p, vote_away_p = _normalise_pair(vote_home, vote_away)

    near = present[:, None] & (distances <= CONTEXT_RADIUS_M)
    home_near = np.sum(near & (teams.codes[None, :] == 0), axis=1)
    away_near = np.sum(near & (teams.codes[None, :] == 1), axis=1)
    count_home_p, count_away_p = _normalise_pair(home_near, away_near)

    centroids = np.full((len(present), 2, 2), np.nan, dtype=float)
    centroid_distances = np.full((len(present), 2), np.nan, dtype=float)
    for side in (0, 1):
        side_players = player_present & (teams.codes[None, :] == side)
        counts = side_players.sum(axis=1)
        sums = np.sum(np.where(side_players[:, :, None], players, 0.0), axis=1)
        has_players = counts > 0
        centroids[has_players, side] = sums[has_players] / counts[has_players, None]
        centroid_distances[has_players & present, side] = np.linalg.norm(
            centroids[has_players & present, side] - ball_xy_m[has_players & present], axis=1
        )
    centroid_support = np.exp(-0.5 * np.square(centroid_distances / CONTEXT_RADIUS_M))
    centroid_support[~np.isfinite(centroid_support)] = 0.0
    centroid_home_p, centroid_away_p = _normalise_pair(
        centroid_support[:, 0], centroid_support[:, 1]
    )

    team_home_p = (
        VOTE_MIX[0] * vote_home_p + VOTE_MIX[1] * centroid_home_p + VOTE_MIX[2] * count_home_p
    )
    team_away_p = (
        VOTE_MIX[0] * vote_away_p + VOTE_MIX[1] * centroid_away_p + VOTE_MIX[2] * count_away_p
    )
    team_home_p[~present] = 0.5
    team_away_p[~present] = 0.5

    ball_out = present & ((ball[:, 0] < 0) | (ball[:, 0] > 1) | (ball[:, 1] < 0) | (ball[:, 1] > 1))
    p_dead = P_DEAD_FLOOR + P_DEAD_OUT_OF_BOUNDS * ball_out.astype(float)
    p_home = (1.0 - p_dead) * team_home_p
    p_away = (1.0 - p_dead) * team_away_p

    nearest = np.min(distances, axis=1)
    nearest[~present] = np.nan
    speed = _ball_speed(ball_xy_m, present)
    evidence_mass = vote_home + vote_away
    track_support = 1.0 - np.exp(-2.0 * evidence_mass)
    # A ball moving more than the emission's spatial scale in one frame makes the frame-local
    # association less reliable. This factor changes confidence only, never the H/A label.
    speed_scale = SIGMA_M * FPS
    speed_factor = np.ones(len(speed), dtype=float)
    measured_speed = np.isfinite(speed)
    speed_factor[measured_speed] = np.exp(-0.5 * np.square(speed[measured_speed] / speed_scale))
    confidence = track_support * speed_factor
    confidence[~present] = 0.0

    artifact = pd.DataFrame(
        {
            "frame": np.arange(len(present), dtype=np.int64),
            "p_home": p_home,
            "p_away": p_away,
            "p_dead": p_dead,
            "confidence": confidence,
        }
    )
    if len(artifact) == N_FRAMES:
        check_artifact(artifact, "<emission>")
    else:
        probabilities = artifact[["p_home", "p_away", "p_dead"]].to_numpy()
        if (
            not np.isfinite(probabilities).all()
            or np.any(probabilities < 0)
            or np.any(probabilities > 1)
            or not np.allclose(probabilities.sum(axis=1), 1.0)
        ):
            raise ValueError("emission probabilities must be finite, in [0, 1], and sum to one")
    return Emission(
        artifact=artifact,
        ball_present=present,
        ball_speed_mps=speed,
        nearest_distance_m=nearest,
        home_centroid_distance_m=centroid_distances[:, 0],
        away_centroid_distance_m=centroid_distances[:, 1],
        home_players_within_10m=home_near,
        away_players_within_10m=away_near,
        ball_out_of_bounds=ball_out,
    )


def public_metrics(
    artifact: pd.DataFrame,
    ball_present: np.ndarray,
    gt_path: str | Path | None = None,
) -> dict[str, Any]:
    """Frame metrics on the public labels, for evaluation only and never model fitting."""
    source = (
        Path(gt_path)
        if gt_path is not None
        else REPO_ROOT / "evaluation/gt/BAR-ATH_possession_gt_public.csv"
    )
    table = pm.read_label_csv(source)
    problem = pm.validate_submission(table, N_FRAMES)
    if problem:
        raise ValueError(f"invalid public ground truth: {problem}")
    truth = pm.label_codes(table)
    scored = truth != pm.X
    y = truth[scored]
    probabilities = artifact[["p_home", "p_away", "p_dead"]].to_numpy(dtype=float)[scored]
    labels = np.argmax(probabilities[:, :2], axis=1)
    live = (y == pm.H) | (y == pm.A)
    live_ball_present = live & ball_present[scored]
    accuracy = (
        float(np.mean(labels[live_ball_present] == y[live_ball_present]))
        if live_ball_present.any()
        else None
    )
    live_ball_absent = live & ~ball_present[scored]
    class_loss: dict[str, float | None] = {}
    class_brier: dict[str, float | None] = {}
    for code, name in ((pm.H, "H"), (pm.A, "A"), (pm.D, "D")):
        actual = y == code
        class_loss[name] = (
            float(np.mean(-np.log(np.clip(probabilities[actual, code], 1e-12, 1.0))))
            if actual.any()
            else None
        )
        target = (y == code).astype(float)
        class_brier[name] = float(np.mean(np.square(probabilities[:, code] - target)))
    return {
        "ground_truth": str(source),
        "n_scored_frames": int(scored.sum()),
        "n_live_team_frames": int(live.sum()),
        "n_live_team_frames_with_ball": int(live_ball_present.sum()),
        "n_live_team_frames_without_ball": int(live_ball_absent.sum()),
        "team_accuracy_h_a": accuracy,
        "team_accuracy_scope": (
            "live frames with observed ball; absent-ball frames abstain (confidence=0)"
        ),
        "log_loss_by_actual_class": class_loss,
        "brier_one_vs_rest_by_class": class_brier,
    }


def smart_tagging_anchor(
    emission: Emission, teams: TeamSlots, instances: list[dict] | None = None
) -> dict[str, Any]:
    """Diagnostic only: report whether emissions favor Smart Tagging's Team during tagged phases."""
    tags = instances if instances is not None else smart_tagging.load()
    frame_home = np.zeros(N_FRAMES, dtype=np.int32)
    frame_away = np.zeros(N_FRAMES, dtype=np.int32)
    counts = Counter()
    for instance in tags:
        name = (instance.get("tags") or {}).get("Team")
        start = max(0, int(instance["start_frame"]))
        end = min(N_FRAMES, int(instance["end_frame"]))
        if name == teams.home_name:
            counts["home_instances"] += 1
            frame_home[start:end] += 1
        elif name == teams.away_name:
            counts["away_instances"] += 1
            frame_away[start:end] += 1
        elif name == "N/A":
            counts["na_instances"] += 1
    unambiguous_home = (frame_home > 0) & (frame_away == 0) & emission.ball_present
    unambiguous_away = (frame_away > 0) & (frame_home == 0) & emission.ball_present
    p_home = emission.artifact["p_home"].to_numpy()
    p_away = emission.artifact["p_away"].to_numpy()
    home_favored = p_home[unambiguous_home] > p_away[unambiguous_home]
    away_favored = p_away[unambiguous_away] > p_home[unambiguous_away]
    favored_total = int(home_favored.sum() + away_favored.sum())
    support_total = len(home_favored) + len(away_favored)
    return {
        "use": "diagnostic only; Smart Tagging Team is not a training or scoring label",
        "instances": dict(counts),
        "home_tagged_frames_with_ball": int(unambiguous_home.sum()),
        "away_tagged_frames_with_ball": int(unambiguous_away.sum()),
        "home_favored_fraction": float(home_favored.mean()) if len(home_favored) else None,
        "away_favored_fraction": float(away_favored.mean()) if len(away_favored) else None,
        "combined_favored_fraction": favored_total / support_total if support_total else None,
    }


def generate(output: str | Path, metadata: str | Path | None = None) -> dict[str, Any]:
    """Load the tactical bundle, write the artifact, and print only aggregate diagnostics."""
    teams = team_slots(metadata)
    tracking = atd.load("tactical")
    result = emit(tracking, teams)
    target = Path(output)
    target.parent.mkdir(parents=True, exist_ok=True)
    result.artifact.to_csv(target, index=False, lineterminator="\n")
    # Read-back through the contract checker catches serialization issues as well as bad arrays.
    from tools.contract import read_artifact

    read_artifact(target)
    return {
        "output": str(target),
        "frames": len(result.artifact),
        "team_identity": {
            "home": teams.home_name,
            "away": teams.away_name,
            "home_slots": teams.home_slots,
            "away_slots": teams.away_slots,
        },
        "public_metrics": public_metrics(result.artifact, result.ball_present),
        "smart_tagging_anchor": smart_tagging_anchor(result, teams),
        "profile": {
            "sigma_m": SIGMA_M,
            "nearest_k": NEAREST_K,
            "ball_present_fraction": float(result.ball_present.mean()),
            "median_nearest_player_distance_m": float(np.nanmedian(result.nearest_distance_m)),
            "median_ball_speed_mps": float(np.nanmedian(result.ball_speed_mps)),
            "ball_speed_missing_fraction": float(np.isnan(result.ball_speed_mps).mean()),
            "ball_out_of_bounds_frames": int(result.ball_out_of_bounds.sum()),
        },
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Generate continuous home/away possession emissions"
    )
    parser.add_argument(
        "--output", default=str(REPO_ROOT / "artifacts/possession.csv"), help="artifact CSV path"
    )
    parser.add_argument("--metadata", default=None, help="ATD metadata XML override")
    args = parser.parse_args(argv)
    try:
        report = generate(args.output, args.metadata)
    except (OSError, ValueError, ET.ParseError) as error:
        print(f"emission failed: {error}", file=sys.stderr)
        return 1
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
