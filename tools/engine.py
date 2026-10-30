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
back-fills them).

The delivered chain (`run`, DECISIONS 30) adds two things from the dead-ball stream (#16,
`tools/dead_ball.py`): each stoppage, from the ball leaving the pitch to the tagged restart, is `D`;
and **a restart hands the ball to the team that takes it** -- a throw-in, a corner, a free kick, a
goal kick -- by forcing the state at the restart frame, whatever `dwell` is (DECISIONS 31). The
restart frame is an estimate, so it is forced only when the tracking has not already seen the game
resume with a control inside the restart's window (DECISIONS 32).
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
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
    # A duel does not change possession (DECISIONS 34): a rival control only counts when the team
    # in possession has nobody within `radius_m` of the ball. False is the engine of DECISIONS 29.
    duel: bool = True


DEFAULT = Params()
# The engine before the duel rule (DECISIONS 29-32): what the research lanes measured against and
# archived. Their evidence stays reproducible against it; nothing delivered uses it.
D31 = Params(duel=False)


@dataclass(frozen=True)
class Features:
    """Per-frame distances from the ball to each team's nearest player, and the ball's speed."""

    home_m: np.ndarray  # NaN where the ball is not observed
    away_m: np.ndarray
    present: np.ndarray
    speed_mps: np.ndarray  # NaN where the previous frame has no ball
    in_pitch: np.ndarray  # the ball observed inside the pitch rectangle


def features(tracking: atd.Tracking, teams: emision.TeamSlots) -> Features:
    """Distances in metres from the tracking; nothing here depends on a threshold."""
    if tracking.n_slots != len(teams.codes):
        raise ValueError(
            f"tracking has {tracking.n_slots} player slots but metadata maps {len(teams.codes)}"
        )
    players = tracking.players_array[:, :, :2] * PITCH_M
    ball, present = tracking.ball()
    # The export normalises the pitch to [0, 1]; the dead-ball stream uses the same rectangle.
    x, y = ball[:, 0], ball[:, 1]
    in_pitch = present & (x >= 0) & (x <= 1) & (y >= 0) & (y <= 1)
    ball_m = ball[:, :2] * PITCH_M
    distance = np.linalg.norm(players - ball_m[:, None, :], axis=2)
    distance[~np.isfinite(distance)] = np.inf  # an absent player is never the nearest
    home = teams.codes == 0
    home_m = distance[:, home].min(axis=1)
    away_m = distance[:, ~home].min(axis=1)
    home_m[~present] = np.nan
    away_m[~present] = np.nan
    return Features(home_m, away_m, present, emision._ball_speed(ball_m, present), in_pitch)


def control(f: Features, params: Params = DEFAULT) -> np.ndarray:
    """`0` home control, `1` away control, `NONE` otherwise, frame by frame.

    An unknown speed (the first frame after a gap) is not evidence of a slow ball, and a tie between
    the two nearest players is a contest, not a control: both fail closed. A ball outside the pitch
    is not in play, so nobody controls it there (DECISIONS 31); the restart gives it back.
    """
    nearest = np.fmin(f.home_m, f.away_m)
    slow = np.nan_to_num(f.speed_mps, nan=np.inf) <= params.speed_mps
    close = f.in_pitch & (nearest <= params.radius_m) & slow
    team = np.full(len(f.present), NONE, dtype=np.int8)
    team[close & (f.home_m < f.away_m)] = 0
    team[close & (f.away_m < f.home_m)] = 1
    return team


def uncontested(ctrl: np.ndarray, f: Features, radius_m: float) -> np.ndarray:
    """`ctrl` where the other team's nearest player is beyond `radius_m`, `NONE` elsewhere.

    A control both teams could play is a duel. An unknown distance is not evidence that the other
    team is far, so it fails closed, like everything else in the engine.
    """
    other = np.where(ctrl == 0, f.away_m, f.home_m)
    clear = np.nan_to_num(other, nan=-np.inf) > radius_m
    return np.where((ctrl != NONE) & clear, ctrl, NONE).astype(np.int8)


def decode(
    ctrl: np.ndarray,
    runs: list[tuple[int, int]],
    dwell: int = 1,
    forced: dict[int, int] | None = None,
    switch: np.ndarray | None = None,
) -> np.ndarray:
    """Carry the last controlling team inside each `[start, stop)` run; `NONE` outside them.

    The first control of a run sets the state at once; after that, a change needs `dwell`
    consecutive control frames of the other team and is dated to the first of them. A frame in
    `forced` (a restart, DECISIONS 30) hands the ball to its team at once, whatever `dwell` is.
    With `switch` (`uncontested`), a rival control that is not in it is a duel and changes nothing.
    """
    if dwell < 1:
        raise ValueError(f"dwell must be at least 1 frame, got {dwell}")
    forced = forced or {}
    state = np.full(len(ctrl), NONE, dtype=np.int8)
    for start, stop in runs:
        current, rival, streak, since = NONE, NONE, 0, start
        for i in range(start, stop):
            seen = int(ctrl[i])
            if switch is not None and current not in (NONE, seen) and switch[i] == NONE:
                seen = NONE  # a duel: the team in possession can still play the ball
            if i in forced:
                current, rival, streak = forced[i], NONE, 0
            elif seen in (NONE, current):
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
    """The two playing halves, half-open: the one definition, in tools/ball_gaps.py."""
    from tools.ball_gaps import half_runs

    return half_runs()


def restart_controls(restarts: Sequence, ctrl: np.ndarray | None = None) -> dict[int, int]:
    """`{frame: team}`: the restarts that hand the ball to their team (DECISIONS 30, 32).

    `restarts` are the dead-ball stream's own (`dead_ball.Restart`, carrying `team`), so a stoppage
    and the possession it opens meet on the same frame. A restart is skipped when its team is
    unknown, when another restart on the same frame names the other team (an ambiguous tag is not
    resolved by XML order), or when `ctrl` already shows a control inside `[tag_start, frame)`:
    the game has resumed and the tracking's observation beats the restart's estimated frame.
    """
    teams: dict[int, set[int]] = {}
    for r in restarts:
        if r.team is None:
            continue
        if ctrl is not None and np.any(ctrl[r.tag_start : r.frame] != NONE):
            continue
        teams.setdefault(r.frame, set()).add(r.team)
    return {frame: next(iter(team)) for frame, team in teams.items() if len(team) == 1}


def chain(
    f: Features,
    params: Params,
    restarts: Sequence | None,
    dead: np.ndarray | None,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """The delivered chain on precomputed inputs: `(ctrl, state, labels)`.

    Control, decode with the restarts that apply under these thresholds, then `D` over the
    stoppages. Shared by `run` and the sensitivity sweep, so the sweep measures what is delivered.
    """
    ctrl = control(f, params)
    forced = restart_controls(restarts, ctrl) if restarts is not None else None
    switch = uncontested(ctrl, f, params.radius_m) if params.duel else None
    state = decode(ctrl, halves(), params.dwell, forced, switch)
    out = labels(state)
    if dead is not None:
        out[np.asarray(dead, dtype=bool)] = "D"
    return ctrl, state, out


def run(
    params: Params = DEFAULT, *, dead: bool = True, restarts: bool = True
) -> tuple[pd.DataFrame, dict]:
    """The delivered chain over the match (DECISIONS 30): labels and aggregates.

    `dead=False, restarts=False` is the bare engine of DECISIONS 29; `restarts=False` is I0.
    """
    from tools import dead_ball

    f = features(atd.load("tactical"), emision.team_slots())
    evidence = dead_ball.load_evidence() if (dead or restarts) else None
    mask = dead_ball.dead_mask(evidence, halves(), "out") if dead else None
    ctrl, state, lab = chain(f, params, evidence.restarts if restarts else None, mask)
    table = pd.DataFrame({"frame": np.arange(len(lab)), "label": lab})
    inside = np.zeros(len(state), dtype=bool)
    for start, stop in halves():
        inside[start:stop] = True
    summary = {
        "params": params.__dict__,
        "dead": dead,
        "restarts": restarts,
        "dead_share": float((table["label"].to_numpy() == "D")[inside].mean()),
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


def build(
    workdir: Path,
    out: Path,
    params: Params = DEFAULT,
    *,
    dead: bool = True,
    restarts: bool = True,
) -> Path:
    """The delivered chain for this engine: artifact -> assemble -> validator (tools/repro.py)."""
    from tools import backup
    from tools.f0a import _run

    workdir = backup.wipe(workdir)
    out = out.resolve()
    artifact = workdir / "artifacts" / "engine.csv"
    # Its own process, like every step of a delivered chain (DECISIONS 28): two repro builds must
    # not share the cached tracking or any module state.
    flags = ["--radius", params.radius_m, "--speed", params.speed_mps, "--dwell", params.dwell]
    if not params.duel:
        flags.append("--no-duel")
    if not dead:
        flags.append("--bare")
    elif not restarts:
        flags.append("--no-restarts")
    _run(["tools/engine.py", "--out", artifact, *flags])
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
    parser.add_argument("--no-duel", action="store_true", help="a duel changes possession (D29)")
    parser.add_argument("--bare", action="store_true", help="the engine alone: no D, no restarts")
    parser.add_argument("--no-restarts", action="store_true", help="I0: D but no restart control")
    args = parser.parse_args(argv)
    params = Params(args.radius, args.speed, args.dwell, not args.no_duel)
    chain = {"dead": not args.bare, "restarts": not (args.bare or args.no_restarts)}
    try:
        if args.build:
            out = build(args.build, args.submission, params, **chain)
            print(f"wrote {out}")
            return 0
        table, summary = run(params, **chain)
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
