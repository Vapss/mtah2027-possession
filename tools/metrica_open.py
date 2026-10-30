"""Metrica's open sample games as an external judge of WHEN possession changes (lane m-dating).

    python tools/metrica_open.py --describe          # aggregates: frames, ball, players, the truth

Why it exists
-------------
Every earlier attempt to date a change of possession was judged on the public slice only, which is
17 possessions and the same ones the bench transplants (DECISIONS 37, lane-dating.md). Metrica's
open sample games 1 and 2 (github.com/metrica-sports/sample-data, open licence) carry what the slice
lacks: two whole matches of tracking at 25 fps, the same provider family as our export, and a
hand-annotated event log whose frames are synchronised to that tracking. A change of possession can
be dated from the events without our engine and without our labels.

What it loads
-------------
`load(game)` turns `RawTrackingData_{Home,Away}_Team.csv` and `RawEventsData.csv` into the shapes
the engine takes: an `engine.Features` (nearest home / away player to the ball in metres, ball
present, ball speed, ball inside the pitch) on a 105 x 68 m pitch (the size game 3's metadata
states; games 1 and 2 ship none), a `dead_ball.Evidence` whose restarts are the events' set
pieces, the playing halves and the players in metres. Both halves sit in one array with
`HALF_GAP` frames of nothing between them (`separate_halves`, as `external.build` does), so no
speed or window bridges half time; `runs` holds the halves. In the first half frame `i` is
Metrica's frame `i + 1`; later halves, and their events, are moved by the gaps before them.

The event-derived truth (`event_truth`), written down before any engine output met it
------------------------------------------------------------------------------------
- E1. An **asserting** event says that its team has the ball at its start frame: `PASS`, `SHOT`,
  `SET PIECE`, `RECOVERY`. `BALL LOST` and `BALL OUT` only confirm the team already in possession
  (a tackle is logged as the winner's `RECOVERY` and, a frame later, the loser's `BALL LOST`, which
  must not hand the ball back). `CHALLENGE`, `FAULT RECEIVED` and `CARD` say nothing about the team.
- E2. In live play the team in possession at frame `t` is the team of the latest asserting event of
  the half that starts at or before `t`. Before the first one of a half, nobody (`-1`).
- E3. A **change** is an asserting event of team `U` while `T != U` is in possession, dated at its
  start frame: the new team's first logged action on the ball (a `RECOVERY`'s frame, the receiver's
  first pass...). The ball in flight after a lost pass stays with the team that lost it, as in the
  challenge's own definition ("while the ball is loose it stays with the last team").
- E4. **Dead ball** runs from a stop to the start frame of the next asserting event. Stops: the end
  frame of a `BALL OUT`, of a `SHOT` whose subtype says `OUT` or `GOAL`, and of a `BALL LOST` whose
  subtype says `OFFSIDE`, `HAND BALL` or `END HALF`; the start frame of a `FAULT RECEIVED` and of a
  `CHALLENGE` whose subtype says `FAULT` (an `ADVANTAGE` is not one: play goes on).
- E5. A change is **open play** when its event is not a `SET PIECE` and not a goal kick (`PASS` /
  `GOAL KICK`), and no dead ball lies between the old team's last asserting event and it. Only
  those are dated by this lane: a change at a restart is the restart's, which the chain forces.

What it is not
--------------
Not the competition's ground truth: an event log has a frame for each action, not a judgment per
frame, and its possession is "who acted last" (E2), which counts more and shorter possessions than a
corrected-tracking possession. `describe` measures the time scale against ours (3.4 +/- 0.5 a
minute) and DFL's (4.58); if it is not comparable, the truth is used ONLY to date changes, never for
spellF1 verdicts. The data lives outside the repository (`MTAH_EXTERNAL_DIR`, default
`~/Downloads/external-football-data`, folder `metrica`) and never enters git.
"""

from __future__ import annotations

import argparse
import os
import sys
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from tools import dead_ball, emision, engine  # noqa: E402

FPS = 25  # Metrica's sample tracking: 0.04 s a frame; `read_tracking` checks the clock says so
PITCH_M = np.array([105.0, 68.0])  # game 3's metadata (FieldSize 105 x 68); games 1-2 state none
GAMES = ("g1", "g2")  # game 3 ships events and metadata but no tracking: it cannot be loaded
HALF_GAP = 250  # frames of nothing between the halves, as `external.HALF_GAP` (10 s)
HOME, AWAY, NONE = 0, 1, -1
TEAMS = {"Home": HOME, "Away": AWAY}

ASSERTING = ("PASS", "SHOT", "SET PIECE", "RECOVERY")  # E1
STOP_AT_END = {
    "BALL OUT": ("",),  # every BALL OUT, whatever its subtype
    "SHOT": ("OUT", "GOAL"),
    "BALL LOST": ("OFFSIDE", "HAND BALL", "END HALF"),
}
STOP_AT_START = {"FAULT RECEIVED": ("",), "CHALLENGE": ("FAULT",)}

# The restart kinds `dead_ball.stoppages` knows, for the set pieces turned into tagged restarts. The
# Smart Tagging window begins `restart_s` before the restart (3.5 s for a kick-off): same here.
RESTART_KIND = {
    "KICK OFF": dead_ball.KICK_OFF_GOAL,  # the first of each half becomes KICK_OFF_START
    "CORNER KICK": "Corner",
    "FREE KICK": "Free Kick",
    "THROW IN": "Throw-in",
    "PENALTY": "Penalty",
    "GOAL KICK": "Goal Kick",
}


def data_dir() -> Path:
    """Where Metrica's sample games live: never inside the repository."""
    root = (
        os.environ.get("MTAH_EXTERNAL_DIR") or Path.home() / "Downloads" / "external-football-data"
    )
    return Path(root) / "metrica"


# -- reading -----------------------------------------------------------------------------------


@dataclass(frozen=True)
class Tracking:
    """One team's file: frame numbers, halves, players `(frames, slots, 2)` normalised, the ball."""

    period: np.ndarray
    frame: np.ndarray
    names: tuple[str, ...]
    players: np.ndarray
    ball: np.ndarray  # (frames, 2), NaN where the ball is not tracked


def read_tracking(path: Path) -> Tracking:
    """A `RawTrackingData_*_Team.csv`: two banner rows, then `Period,Frame,Time [s]`, then one
    `x,y` column pair per player and one for the ball, in [0, 1] of the pitch."""
    table = pd.read_csv(path, skiprows=2)
    columns = list(table.columns)
    if columns[:3] != ["Period", "Frame", "Time [s]"] or columns[-2] != "Ball":
        raise ValueError(f"{path}: unexpected header {columns[:3]} ... {columns[-2:]}")
    names = tuple(columns[3:-2:2])
    if not all(name.startswith("Player") for name in names):
        raise ValueError(f"{path}: player columns are not in x,y pairs")
    frame = table["Frame"].to_numpy(dtype=np.int64)
    if len(frame) == 0 or frame[0] != 1 or np.any(np.diff(frame) != 1):
        raise ValueError(f"{path}: frames are not 1, 2, 3, ...")
    clock = table["Time [s]"].to_numpy(dtype=float)
    # The file rounds the clock to 0.01 s: every step is 0.04 s within that rounding.
    if len(clock) > 1 and np.abs(np.diff(clock) - 1 / FPS).max() > 0.006:
        raise ValueError(f"{path}: the clock is not {FPS} fps")
    values = table.iloc[:, 3:].to_numpy(dtype=float)
    players = values[:, :-2].reshape(len(table), len(names), 2)
    return Tracking(table["Period"].to_numpy(dtype=np.int64), frame, names, players, values[:, -2:])


def read_events(path: Path) -> pd.DataFrame:
    """`RawEventsData.csv`, with `team` (0 home / 1 away), 0-based `start` / `end` frames and a
    string `subtype` ("" when empty). The file's order is kept: it breaks ties between events that
    start on the same frame."""
    events = pd.read_csv(path)
    expected = {"Team", "Type", "Subtype", "Period", "Start Frame", "End Frame", "From", "To"}
    missing = expected - set(events.columns)
    if missing:
        raise ValueError(f"{path}: missing columns {sorted(missing)}")
    unknown = set(events["Team"]) - set(TEAMS)
    if unknown:
        raise ValueError(f"{path}: unknown teams {sorted(unknown)}")
    out = pd.DataFrame(
        {
            "team": events["Team"].map(TEAMS).astype(np.int8),
            "type": events["Type"].astype(str),
            "subtype": events["Subtype"].fillna("").astype(str),
            "period": events["Period"].astype(np.int64),
            # A frame of 0 is Metrica's "no end" (a kick-off): it ends where it starts.
            "start": events["Start Frame"].astype(np.int64) - 1,
            "end": np.maximum(events["End Frame"], events["Start Frame"]).astype(np.int64) - 1,
            "player": events["From"].fillna("").astype(str),
        }
    )
    return out.reset_index(drop=True)


# -- the event-derived truth -------------------------------------------------------------------


@dataclass(frozen=True)
class Change:
    """One change of team in the event truth: `old` -> `new` at `frame` (E3)."""

    frame: int
    old: int
    new: int
    kind: str  # the asserting event's type, or "GOAL KICK"
    open_play: bool  # E5
    previous: int  # the old team's last asserting event's start frame


@dataclass(frozen=True)
class Truth:
    team: np.ndarray  # per frame: 0 / 1 in live play, -1 before a half's first asserting event
    dead: np.ndarray  # E4
    changes: tuple[Change, ...]
    stray_losses: int  # BALL LOST / BALL OUT by the team NOT in possession (E1: ignored)

    def labels(self) -> np.ndarray:
        """`H` / `A` / `D` / `X` per frame, the possession_metrics alphabet."""
        out = np.full(len(self.team), "X", dtype=object)
        out[self.team == HOME] = "H"
        out[self.team == AWAY] = "A"
        out[self.dead] = "D"
        return out


def _matches(subtype: str, words: tuple[str, ...]) -> bool:
    return any(word in subtype for word in words)


def _is_stop(row) -> int | None:
    """The frame a stop event stops play at (E4), or None."""
    words = STOP_AT_END.get(row.type)
    if words is not None and _matches(row.subtype, words):
        return int(row.end)
    words = STOP_AT_START.get(row.type)
    if words is not None and _matches(row.subtype, words) and "ADVANTAGE" not in row.subtype:
        return int(row.start)
    return None


def _kind(row) -> str:
    # A goal kick is logged as the keeper's PASS, or as a BALL LOST (`GOAL KICK-INTERCEPTION`) or
    # BALL OUT when it fails: all three are the restart (review of PR #59: 13 of 38 in g1+g2).
    return "GOAL KICK" if "GOAL KICK" in row.subtype else str(row.type)


def event_truth(events: pd.DataFrame, n: int, runs: list[tuple[int, int]]) -> Truth:
    """The per-frame truth and its changes from E1-E5 (module docstring); `runs` are the halves."""
    team = np.full(n, NONE, dtype=np.int8)
    dead = np.zeros(n, dtype=bool)
    changes: list[Change] = []
    stray = 0
    order = events.sort_values("start", kind="stable")
    for start, stop in runs:
        half = order[(order["start"] >= start) & (order["start"] < stop)]
        current, since, last = NONE, start, start
        stopped: int | None = None  # the earliest stop since the last asserting event
        for row in half.itertuples(index=False):
            frame = int(row.start)
            if row.type in ASSERTING:
                if stopped is not None:
                    dead[min(stopped, frame) : frame] = True
                if current != NONE:
                    team[since:frame] = current
                if current not in (NONE, int(row.team)):
                    kind = _kind(row)
                    open_play = stopped is None and row.type != "SET PIECE" and kind != "GOAL KICK"
                    changes.append(Change(frame, current, int(row.team), kind, open_play, last))
                if current != int(row.team):
                    current, since = int(row.team), frame
                last, stopped = frame, None
            elif row.type in ("BALL LOST", "BALL OUT") and current not in (NONE, int(row.team)):
                stray += 1
            # A shot that goes out or in asserts the ball AND stops play: both apply.
            at = _is_stop(row)
            if at is not None and at >= frame:
                stopped = at if stopped is None else min(stopped, at)
        if current != NONE:
            team[since:stop] = current
        if stopped is not None:
            dead[stopped:stop] = True  # the half ends stopped: nothing resumes it
    return Truth(team, dead, tuple(changes), stray)


# -- the game in our shape ---------------------------------------------------------------------


@dataclass(frozen=True)
class Game:
    name: str
    features: engine.Features
    evidence: dead_ball.Evidence
    runs: tuple[tuple[int, int], ...]  # the playing halves, half-open, 0-based frames
    events: pd.DataFrame
    players_m: np.ndarray  # (frames, home slots + away slots, 2), metres, NaN when off the pitch
    names: tuple[str, ...]  # one per player slot, home first
    ball_m: np.ndarray  # (frames, 2), metres, NaN where untracked; in memory only, never written
    truth: Truth


def restarts(events: pd.DataFrame, runs: list[tuple[int, int]]) -> tuple[dead_ball.Restart, ...]:
    """The set pieces and goal kicks as tagged restarts, team known, window as Smart Tagging's."""
    params = dead_ball.DEFAULT
    found = []
    for start, stop in runs:
        half = events[(events["start"] >= start) & (events["start"] < stop)]
        first_kick_off = True
        for row in half.itertuples(index=False):
            key = "GOAL KICK" if _kind(row) == "GOAL KICK" else row.subtype.split("-")[0]
            if row.type != "SET PIECE" and key != "GOAL KICK":
                continue
            if "RETAKEN" in row.subtype:
                continue  # a set piece taken again: the retake, logged next, is the restart
            kind = RESTART_KIND.get(key)
            if kind is None:
                raise ValueError(f"set piece {row.subtype!r} has no restart kind")
            if key == "KICK OFF" and first_kick_off:
                kind, first_kick_off = dead_ball.KICK_OFF_START, False
            lead = params.kick_off_restart_s if kind.startswith("Kick Off") else params.restart_s
            frame = int(row.start)
            tag_start = max(start, frame - params.frames(lead))
            found.append(dead_ball.Restart(frame, tag_start, kind, int(row.team)))
    return tuple(sorted(found, key=lambda r: (r.frame, r.tag_start)))


def build(name: str, home: Tracking, away: Tracking, events: pd.DataFrame) -> Game:
    if not (np.array_equal(home.frame, away.frame) and np.array_equal(home.period, away.period)):
        raise ValueError(f"{name}: home and away tracking have different frames")
    both_ball = np.isfinite(home.ball).all(axis=1) & np.isfinite(away.ball).all(axis=1)
    if not np.allclose(home.ball[both_ball], away.ball[both_ball]):
        raise ValueError(f"{name}: the two files disagree on the ball")
    n = len(home.frame)
    runs = []
    for period in np.unique(home.period[home.period > 0]):  # period 0: the gap between halves
        at = np.flatnonzero(home.period == period)
        runs.append((int(at[0]), int(at[-1]) + 1))
    players = np.concatenate([home.players, away.players], axis=1) * PITCH_M
    ball_n = home.ball
    present = np.isfinite(ball_n).all(axis=1)
    x, y = ball_n[:, 0], ball_n[:, 1]
    inside = present & (x >= 0) & (x <= 1) & (y >= 0) & (y <= 1)
    ball = ball_n * PITCH_M

    def nearest(team: np.ndarray) -> np.ndarray:
        d = np.linalg.norm(team - ball[:, None, :], axis=2)
        d[~np.isfinite(d)] = np.inf  # an absent player is never the nearest
        out = d.min(axis=1)
        out[~present] = np.nan
        return out

    slots = len(home.names)
    features = engine.Features(
        nearest(players[:, :slots]),
        nearest(players[:, slots:]),
        present,
        emision._ball_speed(ball, present),
        inside,
    )
    evidence = dead_ball.Evidence(
        restarts=restarts(events, runs),
        out=present & ~inside,
        inside=inside,
        still=dead_ball.stillness(dead_ball.field_speed(players)),
    )
    truth = event_truth(events, n, runs)
    return Game(
        name,
        features,
        evidence,
        tuple(runs),
        events,
        players,
        home.names + away.names,
        ball,
        truth,
    )


def separate_halves(
    home: Tracking, away: Tracking, events: pd.DataFrame, gap: int = HALF_GAP
) -> tuple[Tracking, Tracking, pd.DataFrame]:
    """The files number both halves consecutively; put `gap` frames of nothing between them, as
    `external.build` does, so nothing that looks at neighbouring frames (player and ball speeds,
    stillness, change matching) bridges half time. Gap frames carry period 0 and NaN positions;
    every event of a later period moves by the gaps before it.
    """
    periods = [int(p) for p in np.unique(home.period)]
    shift = {p: gap * i for i, p in enumerate(periods)}

    def spread(t: Tracking) -> Tracking:
        parts: dict[str, list[np.ndarray]] = {"period": [], "frame": [], "players": [], "ball": []}
        for i, p in enumerate(periods):
            at = t.period == p
            if i:
                parts["period"].append(np.zeros(gap, dtype=np.int64))
                parts["frame"].append(np.full(gap, -1, dtype=np.int64))
                parts["players"].append(np.full((gap, *t.players.shape[1:]), np.nan))
                parts["ball"].append(np.full((gap, 2), np.nan))
            parts["period"].append(t.period[at])
            parts["frame"].append(t.frame[at])
            parts["players"].append(t.players[at])
            parts["ball"].append(t.ball[at])
        joined = {k: np.concatenate(v) for k, v in parts.items()}
        return Tracking(
            joined["period"], joined["frame"], t.names, joined["players"], joined["ball"]
        )

    moved = events.copy()
    offset = moved["period"].map(shift)
    if offset.isna().any():
        raise ValueError(
            f"events in periods {sorted(set(moved['period']) - set(shift))} have no tracking"
        )
    moved["start"] = moved["start"] + offset.astype(np.int64)
    moved["end"] = moved["end"] + offset.astype(np.int64)
    return spread(home), spread(away), moved


def load(name: str, root: Path | None = None) -> Game:
    folder = (Path(root) if root is not None else data_dir()) / name
    home, away, events = separate_halves(
        read_tracking(folder / "RawTrackingData_Home_Team.csv"),
        read_tracking(folder / "RawTrackingData_Away_Team.csv"),
        read_events(folder / "RawEventsData.csv"),
    )
    return build(name, home, away, events)


# -- aggregates --------------------------------------------------------------------------------


KINK_M = 0.05  # metres per frame squared (31 m/s^2): a touch or a bounce, far above a roll


def ball_kinks(game: Game) -> np.ndarray:
    """Frames where the ball's second difference exceeds `KINK_M`, three tracked frames in a row:
    where its velocity changes sharply (a touch, a bounce, a jump of the tracking)."""
    b = game.ball_m
    ok = np.isfinite(b).all(axis=1)
    accel = np.linalg.norm(b[2:] - 2 * b[1:-1] + b[:-2], axis=1)
    seen = ok[2:] & ok[1:-1] & ok[:-2]
    return np.flatnonzero(seen & (np.nan_to_num(accel) > KINK_M)) + 1


def _near_events(frames: np.ndarray, events: pd.DataFrame, reach: int = 1) -> np.ndarray:
    marks = np.unique(np.concatenate([events["start"].to_numpy(), events["end"].to_numpy()]))
    at = np.searchsorted(marks, frames)
    before = np.abs(frames - marks[np.clip(at - 1, 0, len(marks) - 1)])
    after = np.abs(marks[np.clip(at, 0, len(marks) - 1)] - frames)
    return np.minimum(before, after) <= reach


def describe(game: Game) -> dict:
    """Aggregates of one game (frames, ball, players, the truth's time scale), never frame data."""
    from tools import external

    runs = [tuple(r) for r in game.runs]
    inside = np.zeros(len(game.features.present), dtype=bool)
    for start, stop in runs:
        inside[start:stop] = True
    live = (game.truth.team != NONE) & ~game.truth.dead
    on = np.isfinite(game.players_m).all(axis=2)
    slot = {name: i for i, name in enumerate(game.names)}
    dist = []
    for row in game.events.itertuples(index=False):
        if row.type not in ASSERTING or row.player not in slot:
            continue
        p = game.players_m[int(row.start), slot[row.player]]
        dist.append(float(np.linalg.norm(p - game.ball_m[int(row.start)])))
    dist_a = np.array(dist)
    kinks = ball_kinks(game)
    known = dist_a[np.isfinite(dist_a)]
    codes = external.pm.label_codes(list(game.truth.labels()))
    shape = external.structure(codes, runs)
    changes = game.truth.changes
    open_play = [c for c in changes if c.open_play]
    minutes = sum(stop - start for start, stop in runs) / FPS / 60
    return {
        "game": game.name,
        "frames": int(len(inside)),
        "halves": [stop - start for start, stop in runs],
        "minutes": minutes,
        "ball": float(game.features.present[inside].mean()),
        "ball_live": float(game.features.present[live].mean()),
        "ball_dead": float(game.features.present[game.truth.dead].mean()),
        "players_on_mean": float(on.sum(axis=1)[inside].mean()),
        "player_slots": len(game.names),
        "events": len(game.events),
        "restarts": len(game.evidence.restarts),
        "changes": len(changes),
        "open_play": len(open_play),
        "open_play_per_min": len(open_play) / minutes,
        "stray_losses": game.truth.stray_losses,
        "dead_share": float(game.truth.dead[inside].mean()),
        "event_ball_m_median": float(np.median(known)) if known.size else float("nan"),
        "event_ball_within_2m": float((known <= 2).mean()) if known.size else float("nan"),
        "event_ball_known": int(known.size),
        "event_ball_all": int(dist_a.size),
        "kinks": int(kinks.size),
        "kinks_at_events": float(_near_events(kinks, game.events).mean()) if kinks.size else 0.0,
        **{f"truth_{k}": v for k, v in shape.items()},
    }


def _dec(value: float, digits: int = 2) -> str:
    return "—" if value is None or np.isnan(value) else f"{value:.{digits}f}".replace(".", ",")


def _pct(value: float) -> str:
    return f"{100 * value:.1f}%".replace(".", ",")


def describe_table(rows: list[dict]) -> list[str]:
    lines = [
        "| juego | frames | min | balón | balón vivo / muerto (verdad) | jugadores en campo "
        "| eventos | reanudaciones | cambios | en juego | en juego /min | posesiones /min "
        "| mediana s | < 1 s | %D | BALL LOST ajenos "
        "| jugador–balón en el evento: mediana m / ≤ 2 m "
        "| quiebros del balón a ±1 frame de un evento |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for r in rows:
        lines.append(
            f"| {r['game']} | {r['frames']} | {_dec(r['minutes'], 1)} | {_pct(r['ball'])} "
            f"| {_pct(r['ball_live'])} / {_pct(r['ball_dead'])} | {_dec(r['players_on_mean'], 1)} "
            f"de {r['player_slots']} | {r['events']} | {r['restarts']} | {r['changes']} "
            f"| {r['open_play']} | {_dec(r['open_play_per_min'])} "
            f"| {_dec(r['truth_per_min'])} | {_dec(r['truth_median_s'], 1)} "
            f"| {_pct(r['truth_under_1s'])} | {_pct(r['truth_dead_share'])} | {r['stray_losses']} "
            f"| {_dec(r['event_ball_m_median'])} / {_pct(r['event_ball_within_2m'])} "
            f"| {_pct(r['kinks_at_events'])} de {r['kinks']} |"
        )
    return lines


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Metrica open sample games (lane m-dating)")
    parser.add_argument("--describe", action="store_true", help="aggregates per game")
    args = parser.parse_args(argv)
    if not args.describe:
        parser.error("say --describe")
    try:
        rows = [describe(load(g)) for g in GAMES]
    except (OSError, ValueError) as problem:
        print(f"metrica failed: {problem}", file=sys.stderr)
        return 1
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    print("\n".join(describe_table(rows)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
