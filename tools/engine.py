"""#6 possession engine: the team in possession is the team of the last *controlled* ball.

    python tools/engine.py --out artifacts/engine.csv      # the job's artifact (contract format)
    python tools/engine.py --build runs/engine --submission submissions/engine.csv

The rule is the challenge's own definition (CHALLENGE.md, "Change of possession"): possession
changes when a player of the other team gains *controlled* possession, and while the ball is
contested or loose it stays with the last team that had it. So the engine does two things only:

1. **Detect control.** A frame is a control frame for a team when the ball is observed, that team's
   nearest player is within `radius_m` of it, the other team's nearest is not as close, and the ball
   moves no faster than `speed_mps`. A ball in flight is nobody's: measured on the public slice, the
   nearest player is right 91% of the time when the ball is slower than 2 m/s and 39% when it is
   faster than 20 m/s -- in a pass the nearest player is usually an opponent it flies past.
2. **Carry the state** between control frames, inside each half. A change needs `dwell` consecutive
   control frames of the other team, and when it happens it is dated to the first of them: the
   possession changed when control began, not when the engine became sure of it.

No smoothing window, no duration prior, no learned weight: everything is a physical threshold fixed
before measuring (DECISIONS 29), and frames before the first control of a half are `X` (the scorer
back-fills them). `D` is not decided here; that is the dead-ball stream's job (#16).
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

import games  # noqa: E402
from tools import atd, emision  # noqa: E402
from tools.contract import check_artifact, check_submission  # noqa: E402
from tools.onehot import onehot  # noqa: E402

FPS = int(games.GAMES[games.GAME]["fps"])
PITCH_M = np.asarray(games.GAMES[games.GAME]["pitch"], dtype=float)
NONE = -1  # no team: no control on this frame, or no state yet


@dataclass(frozen=True)
class Params:
    """The three thresholds. Defaults are physical, fixed before measuring (DECISIONS 29)."""

    radius_m: float = 1.5  # reach plus tracking noise: closer than this, the player can play it
    speed_mps: float = 5.0  # a fast dribble; a pass travels at 10 m/s and more
    dwell: int = 1  # consecutive frames of the other team's control needed to change possession


DEFAULT = Params()


@dataclass(frozen=True)
class Features:
    """Per-frame distances from the ball to each team's nearest player, and the ball's speed."""

    home_m: np.ndarray  # NaN where the ball is not observed
    away_m: np.ndarray
    present: np.ndarray
    speed_mps: np.ndarray  # NaN where the previous frame has no ball


def features(tracking: atd.Tracking, teams: emision.TeamSlots) -> Features:
    """Distances in metres from the tracking; nothing here depends on a threshold."""
    players = tracking.players_array[:, :, :2] * PITCH_M
    ball, present = tracking.ball()
    ball_m = ball[:, :2] * PITCH_M
    distance = np.linalg.norm(players - ball_m[:, None, :], axis=2)
    distance[~np.isfinite(distance)] = np.inf  # an absent player is never the nearest
    home = teams.codes == 0
    home_m = distance[:, home].min(axis=1)
    away_m = distance[:, ~home].min(axis=1)
    home_m[~present] = np.nan
    away_m[~present] = np.nan
    return Features(home_m, away_m, present, emision._ball_speed(ball_m, present))


def control(f: Features, params: Params = DEFAULT) -> np.ndarray:
    """`0` home control, `1` away control, `NONE` otherwise, frame by frame.

    An unknown speed (the first frame after a gap) is not evidence of a slow ball, and a tie between
    the two nearest players is a contest, not a control: both fail closed.
    """
    nearest = np.fmin(f.home_m, f.away_m)
    slow = np.nan_to_num(f.speed_mps, nan=np.inf) <= params.speed_mps
    close = f.present & (nearest <= params.radius_m) & slow
    team = np.full(len(f.present), NONE, dtype=np.int8)
    team[close & (f.home_m < f.away_m)] = 0
    team[close & (f.away_m < f.home_m)] = 1
    return team


def decode(ctrl: np.ndarray, runs: list[tuple[int, int]], dwell: int = 1) -> np.ndarray:
    """Carry the last controlling team inside each `[start, stop)` run; `NONE` outside them.

    The first control of a run sets the state at once; after that, a change needs `dwell`
    consecutive control frames of the other team and is dated to the first of them.
    """
    if dwell < 1:
        raise ValueError(f"dwell must be at least 1 frame, got {dwell}")
    state = np.full(len(ctrl), NONE, dtype=np.int8)
    for start, stop in runs:
        current, rival, streak, since = NONE, NONE, 0, start
        for i in range(start, stop):
            seen = int(ctrl[i])
            if seen in (NONE, current):
                rival, streak = NONE, 0  # a gap in the rival's control, or our own, resets it
            elif current == NONE:
                current = seen
            else:
                if seen != rival:
                    rival, streak, since = seen, 0, i
                streak += 1
                if streak >= dwell:
                    state[since:i] = seen  # the change began with the rival's first control
                    current, rival, streak = seen, NONE, 0
            state[i] = current
    return state


def labels(state: np.ndarray) -> np.ndarray:
    """`H` / `A` from the decoded state, `X` where there is none (the scorer fills it)."""
    out = np.full(len(state), "X", dtype=object)
    out[state == 0] = "H"
    out[state == 1] = "A"
    return out


def halves() -> list[tuple[int, int]]:
    return [(start, stop + 1) for _half, start, stop in games.half_video_blocks(games.GAME)]


def run(params: Params = DEFAULT) -> tuple[pd.DataFrame, dict]:
    """The engine over the delivered match: labels as a frame,label table, and aggregates."""
    f = features(atd.load("tactical"), emision.team_slots())
    ctrl = control(f, params)
    state = decode(ctrl, halves(), params.dwell)
    table = pd.DataFrame({"frame": np.arange(len(state)), "label": labels(state)})
    inside = np.zeros(len(state), dtype=bool)
    for start, stop in halves():
        inside[start:stop] = True
    summary = {
        "params": params.__dict__,
        "control_frames_share": float((ctrl != NONE)[inside].mean()),
        "labelled_share": float((state != NONE)[inside].mean()),
        "home_share": float((state == 0).sum() / max(1, (state != NONE).sum())),
    }
    return table, summary


def write_artifact(table: pd.DataFrame, out: Path) -> None:
    """The job's output in the contract format; `X` becomes confidence 0 (an abstention)."""
    artifact = check_artifact(onehot(table["label"]), out)
    out.parent.mkdir(parents=True, exist_ok=True)
    artifact.to_csv(out, index=False, lineterminator="\n")


def build(workdir: Path, out: Path, params: Params = DEFAULT) -> Path:
    """The delivered chain for this engine: artifact -> assemble -> validator (tools/repro.py)."""
    from tools import backup
    from tools.f0a import _run

    workdir = backup.wipe(workdir)
    out = out.resolve()
    artifact = workdir / "artifacts" / "engine.csv"
    table, _summary = run(params)
    write_artifact(table, artifact)
    _run(
        [
            "tools/assemble.py",
            "--artifacts",
            artifact.parent,
            "-o",
            out,
            "--json",
            workdir / "summary.json",
        ]
    )
    _run(["evaluation/validate_submission.py", out])
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Possession engine: last controlled ball (#6)")
    parser.add_argument("--out", type=Path, help="write the artifact here")
    parser.add_argument("--labels", type=Path, help="also write the decoded frame,label CSV here")
    parser.add_argument("--build", type=Path, help="build the delivered chain in this runs/ dir")
    parser.add_argument("--submission", type=Path, default=REPO_ROOT / "submissions/engine.csv")
    parser.add_argument("--radius", type=float, default=Params.radius_m)
    parser.add_argument("--speed", type=float, default=Params.speed_mps)
    parser.add_argument("--dwell", type=int, default=Params.dwell)
    args = parser.parse_args(argv)
    params = Params(args.radius, args.speed, args.dwell)
    try:
        if args.build:
            out = build(args.build, args.submission, params)
            print(f"wrote {out}")
            return 0
        table, summary = run(params)
        if args.labels:
            check_submission(table, args.labels)
            args.labels.parent.mkdir(parents=True, exist_ok=True)
            table.to_csv(args.labels, index=False, lineterminator="\n")
        if args.out:
            write_artifact(table, args.out)
    except (OSError, ValueError, RuntimeError) as problem:
        print(f"engine failed: {problem}", file=sys.stderr)
        return 1
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
