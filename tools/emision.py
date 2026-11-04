"""Team identity per tracking slot and the ball's speed: the two pieces of the old emission job
that the possession engine uses.

The emission artifact this module once wrote (a softmax over each team's nearest player) had a
temperature calibrated on the public ground truth. Under the organisers' clarified rules nothing
may be calibrated on it, so the artifact and its calibration left the repository (DECISIONS 45;
the last version is on `dev` at `8ec43a8`). What stays reads only the ATD metadata and tracking.
"""

from __future__ import annotations

import sys
import xml.etree.ElementTree as ET
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

import numpy as np

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

import games  # noqa: E402
from tools import atd  # noqa: E402

FPS = int(games.GAMES[games.GAME]["fps"])
PITCH_M = tuple(float(value) for value in games.GAMES[games.GAME]["pitch"])
N_FRAMES = games.source_frames()


@dataclass(frozen=True)
class TeamSlots:
    """Team identity for each raw ATD player slot, in the XML's player order."""

    codes: np.ndarray  # 0 = local/home, 1 = visiting/away
    home_name: str
    away_name: str
    home_slots: int
    away_slots: int


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


def _ball_speed(ball_xy_m: np.ndarray, present: np.ndarray) -> np.ndarray:
    """Frame-to-frame ball speed; gaps and half-time are never bridged."""
    speed = np.full(len(ball_xy_m), np.nan, dtype=float)
    consecutive = present[1:] & present[:-1]
    differences = np.diff(ball_xy_m, axis=0)
    indices = np.flatnonzero(consecutive) + 1
    speed[indices] = np.linalg.norm(differences[consecutive], axis=1) * FPS
    return speed
