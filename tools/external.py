"""External validation corpus: public labelled matches in the shape our methods take.

    python tools/external.py --describe                  # ground-truth structure, per match
    python tools/external.py --score --write docs/analysis/external.md

Why it exists
-------------
Every decision so far is taken on 17 possessions (the public five minutes) and on a
gap-transplant bench that still scores those same 17. The Sportec/DFL open dataset (IDSSE: Bassek
et al., Scientific Data 12:195, 2025, CC-BY 4.0, figshare doi:10.6084/m9.figshare.28196177) has
seven full Bundesliga matches with per-frame tracking of the ball and of every player at 25 Hz,
and on each ball frame the two attributes our ground truth is made of: `BallStatus` (0 dead,
1 alive) and `BallPossession` (1 home, 2 away). Seven whole matches instead of five minutes.

What this module does
---------------------
1. **Load** one match into the same inputs our methods take: an `engine.Features` (nearest home
   and away player to the ball in metres, ball present, ball speed, ball inside the pitch) and a
   `dead_ball.Evidence` (ball out of the pitch, ball inside it, a still field). Smart Tagging
   does not exist here, so `Evidence.restarts` is always empty: a method that needs restarts
   runs without them.
2. **Label** each frame `D` where `BallStatus` is 0, else `H`/`A` from `BallPossession`,
   `X` where neither says (in practice, only the gap between the halves). That is the definition
   our own labels follow: dead where the corrected tracking marks the ball dead, otherwise the
   team it names.
3. **Degrade** a match to resemble our automatic tracking: our match's ball-presence pattern,
   half by half, is laid over the external match and the ball is deleted where ours was not seen
   (`degrade`, the same deletion as `tools/bench.py`). The external match keeps its own players,
   ground truth and possession structure; only the amount and length of missing ball are ours.
4. **Score** any `(features, evidence) -> labels` method, the signature of `tools/bench.py`, on
   every match with the official `possession_metrics.evaluate`, clean or degraded.

Frames, halves, coordinates
---------------------------
- DFL frames are 25 Hz, like ours (`engine.FPS`; the parser checks the timestamps), numbered `N`
  from 10.000 in the first half and 100.000 in the second. Each half becomes one contiguous run;
  the two runs are concatenated with `HALF_GAP` frames of nothing between them (no ball, no
  players, `X` in the ground truth), so the official scorer finds the halves from the labels
  exactly as it does on our match, and no speed, smoothing window or carried state can cross the
  break.
- DFL positions are metres from the centre spot, `x` along the length. They are shifted to a
  corner origin, `[0, L] x [0, W]` with the pitch size from the file, so the in/out-of-pitch test
  is the same rectangle test as ours on the normalised export.
- Home is the match information's `HomeTeamId`, away its `GuestTeamId`. Referees are dropped.

What it is not
--------------
Not the competition's ground truth and not Metrica's tracking. DFL tracking is optical (TRACAB
Gen5) and operator-corrected: the ball is never missing, identities are clean, and their
`BallStatus` covers every referee stoppage (fouls, substitutions), not only a ball that leaves
the pitch. Their possession definition may differ from Metrica's. `describe` measures the
differences; read them before choosing a parameter on this corpus. The data lives outside the
repository (`MTAH_EXTERNAL_DIR`, default `~/Downloads/external-football-data`) and never enters
git; the parsed cache sits next to it.
"""

from __future__ import annotations

import argparse
import contextlib
import dataclasses
import importlib
import os
import re
import sys
from collections.abc import Callable, Iterator, Sequence
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from tools import ball_gaps, bench, dead_ball, emision, engine  # noqa: E402

sys.path.insert(0, str(REPO_ROOT / "evaluation"))
import possession_metrics as pm  # noqa: E402

FPS = engine.FPS  # DFL positions are 25 Hz too; `load` checks the timestamps say so
HALF_GAP = 250  # frames of nothing between the halves: 10 s, wider than any window we smooth over
SECTIONS = ("firstHalf", "secondHalf")
MATCHES = ("J03WMX", "J03WN1", "J03WOH", "J03WOY", "J03WPY", "J03WQQ", "J03WR9")
CACHE_VERSION = 1

Method = Callable[[engine.Features, dead_ball.Evidence], np.ndarray]


def data_dir() -> Path:
    """Where the external data lives: never inside the repository."""
    return Path(
        os.environ.get("MTAH_EXTERNAL_DIR") or Path.home() / "Downloads" / "external-football-data"
    )


# -- parsing -----------------------------------------------------------------------------------

_FRAMESET = re.compile(r'<FrameSet [^>]*?GameSection="([^"]+)"[^>]*?TeamId="([^"]+)"')
_PERSON = re.compile(r'PersonId="([^"]+)"')
_FRAME = re.compile(r'<Frame N="(\d+)"[^>]*? X="([^"]+)" Y="([^"]+)"')
_BALL = re.compile(r'BallPossession="(\d*)"[^>]*? BallStatus="(\d*)"')
_PITCH = re.compile(r'<PitchSize X="([^"]+)" Y="([^"]+)"')
_TIME = re.compile(r'T="[^"T]*T(\d\d):(\d\d):(\d\d(?:\.\d+)?)')


@dataclass(frozen=True)
class Section:
    """One half as parsed: frame numbers, the ball and its two labels, both teams' players.

    `possession` is 1 home / 2 away / 0 unknown, `status` 1 alive / 0 dead / -1 unknown, both taken
    from the ball's own frames. Player arrays are `(frames, slots, 2)` metres from the centre spot,
    `NaN` where a player is not on the pitch.
    """

    name: str
    first: int  # the frame number `N` of row 0; rows are consecutive frame numbers
    ball: np.ndarray  # (frames, 2)
    possession: np.ndarray
    status: np.ndarray
    home: np.ndarray
    away: np.ndarray


@dataclass(frozen=True)
class Raw:
    match_id: str
    pitch: tuple[float, float]  # length, width in metres
    sections: tuple[Section, ...]


def meta(path: Path) -> tuple[str, str, tuple[float, float]]:
    """`(home_team_id, guest_team_id, (length, width))` from a DFL match information file."""
    text = Path(path).read_text(encoding="utf-8")
    general = re.search(r'<General [^>]*?HomeTeamId="([^"]+)"[^>]*?GuestTeamId="([^"]+)"', text)
    pitch = re.search(r'<Environment [^>]*?PitchX="([^"]+)" PitchY="([^"]+)"', text)
    if not general or not pitch:
        raise ValueError(f"{path}: no HomeTeamId/GuestTeamId or PitchX/PitchY")
    return general.group(1), general.group(2), (float(pitch.group(1)), float(pitch.group(2)))


def parse_positions(path: Path, home_id: str, guest_id: str, match_id: str = "") -> Raw:
    """Read a DFL positions file line by line (they are ~400 MB): no XML tree is ever built.

    Every frame set is one object in one half; the ball's (`TeamId="BALL"`) fixes the half's frame
    range, and a player's frames are placed by their `N` inside it. Referees and anything that is
    neither team nor ball are skipped.
    """
    pitch = None
    sets: dict[tuple[str, str], list[tuple[str, list[str]]]] = {}
    current: list[str] | None = None
    with open(path, encoding="utf-8") as handle:
        for line in handle:
            if line.startswith("<Frame "):
                if current is not None:
                    current.append(line)
                continue
            if line.startswith("<FrameSet "):
                found = _FRAMESET.search(line)
                person = _PERSON.search(line)
                if not found or not person:
                    raise ValueError(f"{path}: unreadable FrameSet header")
                section, team = found.groups()
                if team in ("BALL", home_id, guest_id) and section in SECTIONS:
                    current = []
                    sets.setdefault((section, team), []).append((person.group(1), current))
                else:
                    current = None
            elif line.startswith("</FrameSet"):
                current = None
            elif pitch is None and "<PitchSize" in line:
                size = _PITCH.search(line)
                if size:
                    pitch = (float(size.group(1)), float(size.group(2)))
    if pitch is None:
        raise ValueError(f"{path}: no PitchSize")
    sections = []
    for name in SECTIONS:
        balls = sets.get((name, "BALL"), [])
        if len(balls) != 1:
            raise ValueError(f"{path}: {len(balls)} ball frame sets in {name}, expected 1")
        sections.append(
            _section(
                name,
                balls[0][1],
                sets.get((name, home_id), []),
                sets.get((name, guest_id), []),
                path,
            )
        )
    return Raw(match_id, pitch, tuple(sections))


def _seconds(line: str) -> float:
    """The frame's wall-clock `T` in seconds since midnight, for the frame-rate check."""
    found = _TIME.search(line)
    if not found:
        raise ValueError("a Frame line without a T timestamp")
    hours, minutes, seconds = found.groups()
    return int(hours) * 3600 + int(minutes) * 60 + float(seconds)


def _numbers(lines: list[str], path: Path) -> tuple[np.ndarray, np.ndarray]:
    frames = np.empty(len(lines), dtype=np.int64)
    xy = np.empty((len(lines), 2), dtype=float)
    for i, line in enumerate(lines):
        found = _FRAME.match(line)
        if not found:
            raise ValueError(f"{path}: unreadable Frame line")
        frames[i] = int(found.group(1))
        xy[i] = float(found.group(2)), float(found.group(3))
    return frames, xy


def _section(name: str, ball: list[str], home: list, away: list, path: Path) -> Section:
    frames, ball_xy = _numbers(ball, path)
    if len(frames) == 0 or np.any(np.diff(frames) != 1):
        raise ValueError(f"{path}: {name} ball frames are not consecutive")
    first, n = int(frames[0]), len(frames)
    step = _seconds(ball[-1]) - _seconds(ball[0])
    if n > 1 and abs(step / (n - 1) - 1 / FPS) > 1e-3:
        raise ValueError(f"{path}: {name} is {(n - 1) / step:.2f} Hz, the methods assume {FPS}")
    possession = np.zeros(n, dtype=np.int8)
    status = np.full(n, -1, dtype=np.int8)
    for i, line in enumerate(ball):
        found = _BALL.search(line)
        if found:
            possession[i] = int(found.group(1) or 0)
            status[i] = int(found.group(2)) if found.group(2) else -1

    def team(objects: list) -> np.ndarray:
        out = np.full((n, len(objects), 2), np.nan)
        for slot, (_person, lines) in enumerate(objects):
            at, xy = _numbers(lines, path)
            rows = at - first
            inside = (rows >= 0) & (rows < n)
            out[rows[inside], slot] = xy[inside]
        return out

    return Section(name, first, ball_xy, possession, status, team(home), team(away))


# -- the cache ---------------------------------------------------------------------------------


def _files(match_id: str, root: Path) -> tuple[Path, Path]:
    def one(pattern: str) -> Path:
        found = sorted(root.glob(pattern))
        if len(found) != 1:
            raise FileNotFoundError(f"{root}: expected one {pattern}, found {len(found)}")
        return found[0]

    return (
        one(f"DFL_02_01_matchinformation_*_DFL-MAT-{match_id}.xml"),
        one(f"DFL_04_03_positions_raw_observed_*_DFL-MAT-{match_id}.xml"),
    )


def raw(match_id: str, root: Path | None = None) -> Raw:
    """One match, parsed once and cached as `.npz` next to the data (outside the repository)."""
    root = Path(root) if root is not None else data_dir() / "idsse"
    cache = root / "cache" / f"{match_id}.v{CACHE_VERSION}.npz"
    if cache.exists():
        with np.load(cache) as z:
            sections = tuple(
                Section(
                    name,
                    int(z[f"{name}_first"]),
                    z[f"{name}_ball"],
                    z[f"{name}_possession"],
                    z[f"{name}_status"],
                    z[f"{name}_home"],
                    z[f"{name}_away"],
                )
                for name in SECTIONS
            )
            return Raw(match_id, (float(z["pitch"][0]), float(z["pitch"][1])), sections)
    info, positions = _files(match_id, root)
    home_id, guest_id, _ = meta(info)
    parsed = parse_positions(positions, home_id, guest_id, match_id)
    arrays: dict[str, np.ndarray] = {"pitch": np.asarray(parsed.pitch)}
    for s in parsed.sections:
        arrays.update(
            {
                f"{s.name}_first": np.asarray(s.first),
                f"{s.name}_ball": s.ball,
                f"{s.name}_possession": s.possession,
                f"{s.name}_status": s.status,
                f"{s.name}_home": s.home,
                f"{s.name}_away": s.away,
            }
        )
    cache.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(cache, **arrays)
    return parsed


# -- the match in our shape --------------------------------------------------------------------


@dataclass(frozen=True)
class Match:
    """An external match as our methods see it, plus its ground truth and its halves."""

    name: str
    features: engine.Features
    evidence: dead_ball.Evidence
    truth: np.ndarray  # per-frame `H`/`A`/`D`/`X`, possession_metrics labels
    runs: tuple[tuple[int, int], ...]  # the playing halves, half-open

    @property
    def codes(self) -> np.ndarray:
        return pm.label_codes(list(self.truth))


def truth_labels(possession: np.ndarray, status: np.ndarray) -> np.ndarray:
    """`D` where the ball is dead, else the team in possession; `X` where the file says neither."""
    out = np.full(len(status), "X", dtype=object)
    alive = status == 1
    out[alive & (possession == 1)] = "H"
    out[alive & (possession == 2)] = "A"
    out[status == 0] = "D"
    return out


def build(r: Raw) -> Match:
    """`Features`, `Evidence`, labels and halves of a parsed match (see the module docstring)."""
    length, width = r.pitch
    offset = np.array([length / 2, width / 2])
    slots_home = max(s.home.shape[1] for s in r.sections)
    slots_away = max(s.away.shape[1] for s in r.sections)

    def pad(a: np.ndarray, slots: int) -> np.ndarray:
        return np.concatenate([a, np.full((len(a), slots - a.shape[1], 2), np.nan)], axis=1)

    parts: dict[str, list[np.ndarray]] = {k: [] for k in ("ball", "home", "away", "truth")}
    runs, at = [], 0
    for i, s in enumerate(r.sections):
        if i:
            gap = HALF_GAP
            parts["ball"].append(np.full((gap, 2), np.nan))
            parts["home"].append(np.full((gap, slots_home, 2), np.nan))
            parts["away"].append(np.full((gap, slots_away, 2), np.nan))
            parts["truth"].append(np.full(gap, "X", dtype=object))
            at += gap
        n = len(s.ball)
        parts["ball"].append(s.ball + offset)
        parts["home"].append(pad(s.home, slots_home) + offset)
        parts["away"].append(pad(s.away, slots_away) + offset)
        parts["truth"].append(truth_labels(s.possession, s.status))
        runs.append((at, at + n))
        at += n
    ball = np.concatenate(parts["ball"])
    home = np.concatenate(parts["home"])
    away = np.concatenate(parts["away"])
    present = np.isfinite(ball).all(axis=1)
    x, y = ball[:, 0], ball[:, 1]
    in_pitch = present & (x >= 0) & (x <= length) & (y >= 0) & (y <= width)

    def nearest(team: np.ndarray) -> np.ndarray:
        d = np.linalg.norm(team - ball[:, None, :], axis=2)
        d[~np.isfinite(d)] = np.inf  # an absent player is never the nearest
        out = d.min(axis=1) if d.shape[1] else np.full(len(ball), np.inf)
        out[~present] = np.nan
        return out

    features = engine.Features(
        nearest(home), nearest(away), present, emision._ball_speed(ball, present), in_pitch
    )
    speed = dead_ball.field_speed(np.concatenate([home, away], axis=1))
    evidence = dead_ball.Evidence(
        restarts=(),  # Smart Tagging does not exist for these matches
        out=present & ~in_pitch,
        inside=in_pitch,
        still=dead_ball.stillness(speed),
    )
    return Match(r.match_id, features, evidence, np.concatenate(parts["truth"]), tuple(runs))


def load(match_id: str, root: Path | None = None) -> Match:
    return build(raw(match_id, root))


def load_all(root: Path | None = None, matches: Sequence[str] = MATCHES) -> list[Match]:
    return [load(m, root) for m in matches]


# -- degradation -------------------------------------------------------------------------------


def our_ball_halves() -> list[np.ndarray]:
    """Our match's ball-presence mask, one array per playing half. Used in memory only, never
    written: it is derived from the licensed tracking. Reports aggregate it per block."""
    from tools import atd

    _, present = atd.load("tactical").ball()
    return [np.asarray(present[start:stop], dtype=bool) for start, stop in ball_gaps.half_runs()]


def keep_mask(match: Match, donors: Sequence[np.ndarray]) -> np.ndarray:
    """Per frame, is the ball kept? Donor half `i` over the match's half `i`, from its first frame,
    repeated from its start if the external half is longer; frames outside the halves are kept."""
    if len(donors) < len(match.runs):
        raise ValueError(f"{len(donors)} donor halves for {len(match.runs)} halves")
    keep = np.ones(len(match.truth), dtype=bool)
    for (start, stop), donor in zip(match.runs, donors):
        if not len(donor):
            raise ValueError("an empty donor half")
        keep[start:stop] = np.resize(np.asarray(donor, dtype=bool), stop - start)
    return keep


def degrade(match: Match, donors: Sequence[np.ndarray]) -> Match:
    """A copy of `match` with the ball deleted wherever the donor did not see it.

    The deletion is `bench.degrade`'s: position, both distances, speed (which needs this frame and
    the previous one) and the in/out-of-pitch observation. Players, stillness and labels stay.
    """
    n = len(match.truth)
    f, ev = bench.degrade(match.features, match.evidence, (0, n), keep_mask(match, donors))
    return dataclasses.replace(match, features=f, evidence=ev)


# -- scoring -----------------------------------------------------------------------------------


@contextlib.contextmanager
def halves_of(match: Match) -> Iterator[None]:
    """Run a bench-style method on an external match: the halves it asks for are this match's.

    Our methods take their halves from `engine.halves`, `dead_ball.halves` or
    `ball_gaps.half_runs`, all of which describe BAR-ATH. This swaps them for the duration of one
    call and restores them, so a method registered for the bench runs here unchanged. The swap is
    by identity across every loaded `tools.*` module, so a module that did
    `from tools.engine import halves` is swapped too. A method that reads anything else of our match
    (Smart Tagging, the raw tracking, `games.half_video_blocks`) is not portable and must not be
    scored here.
    """
    runs = [tuple(r) for r in match.runs]
    originals = {id(f) for f in (engine.halves, dead_ball.halves, ball_gaps.half_runs)}
    saved = []
    for name, module in list(sys.modules.items()):
        if module is None or not (name == "tools" or name.startswith("tools.")):
            continue
        for attr in ("halves", "half_runs"):
            if id(getattr(module, attr, None)) in originals:
                saved.append((module, attr, getattr(module, attr)))
                setattr(module, attr, lambda *_a, **_k: list(runs))
    try:
        yield
    finally:
        for module, attr, value in saved:
            setattr(module, attr, value)


def run(method: Method, match: Match) -> np.ndarray:
    with halves_of(match):
        labels = np.asarray(method(match.features, match.evidence), dtype=object)
    if len(labels) != len(match.truth):
        raise ValueError(f"method gave {len(labels)} labels for {len(match.truth)} frames")
    return labels


def structure(codes: np.ndarray, runs: Sequence[tuple[int, int]]) -> dict:
    """Possession structure of one label sequence: rates per graded minute, lengths, `D`."""
    runs = [tuple(r) for r in runs]
    graded = sum(stop - start for start, stop in runs)
    minutes = graded / FPS / 60
    spells = pm.possession_spells(codes, runs)
    lengths = np.array([stop - start for start, stop, _code in spells], dtype=float) / FPS
    dead = [s for s in pm.segments(codes, runs) if s[2] == pm.LABELS.index("D")]
    dead_s = np.array([stop - start for start, stop, _ in dead], dtype=float) / FPS
    inside = np.zeros(len(codes), dtype=bool)
    for start, stop in runs:
        inside[start:stop] = True
    return {
        "minutes": minutes,
        "possessions": len(spells),
        "per_min": len(spells) / minutes if minutes else float("nan"),
        "mean_s": float(lengths.mean()) if lengths.size else float("nan"),
        "median_s": float(np.median(lengths)) if lengths.size else float("nan"),
        "under_1s": float((lengths < 1).mean()) if lengths.size else float("nan"),
        "under_3s": float((lengths < 3).mean()) if lengths.size else float("nan"),
        "dead_share": float((codes[inside] == pm.LABELS.index("D")).mean()),
        "stoppages_per_min": len(dead) / minutes if minutes else float("nan"),
        "median_stoppage_s": float(np.median(dead_s)) if dead_s.size else float("nan"),
    }


TIME_SCALE = ("per_min", "mean_s", "median_s", "under_1s", "under_3s")


def score(
    method: Method,
    matches: Sequence[Match],
    degraded: bool = False,
    donors: Sequence[np.ndarray] | None = None,
) -> pd.DataFrame:
    """One row per match and a `mean` row: official spellF1 / macroF1, possession counts.

    `degraded=True` lays our ball-presence pattern over each match first (`donors`, default
    `our_ball_halves()`). `gt_per_min` is the ground truth's possessions per graded minute, the
    domain check against our ~3,4 on the public slice.
    """
    if degraded and donors is None:
        donors = our_ball_halves()
    rows = []
    for match in matches:
        m = degrade(match, donors) if degraded else match
        gt = match.codes
        pred = pm.label_codes(list(run(method, m)))
        result = pm.evaluate(gt, pred)
        runs = pm.valid_runs(gt)
        filled = pm.fill_abstentions(pred, runs)
        truth, said = structure(gt, runs), structure(filled, runs)
        row = {
            "match": match.name,
            "ball": float(
                m.features.present[np.concatenate([np.arange(a, b) for a, b in match.runs])].mean()
            ),
            "spell_f1": float(result["spell_f1_mean"]),
            "macro_f1": float(result["macro_f1"]),
            "team_acc": float(result["team_acc_gt_alive"]),
            "n_gt": int(result["n_gt_spells"]),
            "n_pred": int(result["n_pred_spells"]),
            "pred_dead": said["dead_share"],
        }
        # The time scale, for prediction and truth side by side: a decoder that splits or merges
        # possessions shows here before it shows in spellF1.
        for key in TIME_SCALE:
            row[f"gt_{key}"], row[f"pred_{key}"] = truth[key], said[key]
        rows.append(row)
    table = pd.DataFrame(rows)
    mean = table.drop(columns="match").mean(numeric_only=True)
    return pd.concat(
        [table, pd.DataFrame([{"match": "mean", **mean.to_dict()}])], ignore_index=True
    )


# -- the methods scored here (pre-registered in docs/proposals/lane-external.md) ---------------


def _engine_out(f: engine.Features, ev: dead_ball.Evidence) -> np.ndarray:
    """The bare engine plus the one `D` rule that needs no Smart Tagging: a ball observed out of
    the pitch for at least a second is dead until it is next seen inside (dead_ball's `untagged`
    stoppage, its constants unchanged). With no restarts, every other source of `D` is silent."""
    dead = dead_ball.dead_mask(ev, dead_ball.halves(), "out+still+untagged")
    return engine.chain(f, engine.DEFAULT, None, dead)[2]


METHODS: dict[str, Method] = {
    "engine-bare": bench.METHODS["engine-bare"],
    "engine-out": _engine_out,
    "smooth50": bench.METHODS["smooth50"],
    # The delivered chain needs Smart Tagging restarts for both its D and its restart control;
    # without them it is `engine-bare` exactly. Scored to show that, not as a separate method.
    "engine": bench.METHODS["engine"],
}


# -- the report --------------------------------------------------------------------------------


def _dec(value: float, digits: int = 4) -> str:
    return "—" if value is None or np.isnan(value) else f"{value:.{digits}f}".replace(".", ",")


def _pct(value: float) -> str:
    return f"{100 * value:.1f}%".replace(".", ",")


def describe_table(matches: Sequence[Match], public: dict | None) -> list[str]:
    """Ground-truth structure per match, next to our public slice's: the domain check."""
    lines = [
        "| partido | min | posesiones | /min | media s | mediana s | < 1 s | < 3 s | %D "
        "| paradas/min | mediana parada s |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    rows = [(m.name, structure(m.codes, m.runs)) for m in matches]
    if public is not None:
        rows.append(("BAR-ATH público (bloque 1)", public))
    for name, s in rows:
        lines.append(
            f"| {name} | {_dec(s['minutes'], 1)} | {s['possessions']} | {_dec(s['per_min'], 2)} "
            f"| {_dec(s['mean_s'], 1)} | {_dec(s['median_s'], 1)} | {_pct(s['under_1s'])} "
            f"| {_pct(s['under_3s'])} | {_pct(s['dead_share'])} "
            f"| {_dec(s['stoppages_per_min'], 2)} | {_dec(s['median_stoppage_s'], 1)} |"
        )
    return lines


def score_table(tables: dict[str, pd.DataFrame], column: str) -> list[str]:
    names = list(tables)
    first = tables[names[0]]
    lines = [
        "| partido | balón | " + " | ".join(f"`{n}`" for n in names) + " |",
        "|---|---:|" + "---:|" * len(names),
    ]
    for i, match in enumerate(first["match"]):
        cells = " | ".join(_dec(tables[n][column].iloc[i]) for n in names)
        lines.append(f"| {match} | {_pct(first['ball'].iloc[i])} | {cells} |")
    return lines


def time_scale_table(tables: dict[str, pd.DataFrame]) -> list[str]:
    """Per match: the truth's possessions per minute, median length and share under a second,
    then the same three for every method -- where a time-scale error is visible."""
    names = list(tables)
    first = tables[names[0]]
    head = ["verdad"] + [f"`{n}`" for n in names]
    lines = [
        "| partido | " + " | ".join(f"{h} /min | {h} mediana s | {h} < 1 s" for h in head) + " |",
        "|---|" + "---:|---:|---:|" * len(head),
    ]
    for i, match in enumerate(first["match"]):
        cells = [(first["gt_per_min"], first["gt_median_s"], first["gt_under_1s"])]
        cells += [
            (tables[n]["pred_per_min"], tables[n]["pred_median_s"], tables[n]["pred_under_1s"])
            for n in names
        ]
        text = " | ".join(
            f"{_dec(r.iloc[i], 2)} | {_dec(m.iloc[i], 1)} | {_pct(u.iloc[i])}" for r, m, u in cells
        )
        lines.append(f"| {match} | {text} |")
    return lines


def paired(a: pd.DataFrame, b: pd.DataFrame) -> dict:
    """`a` against `b` over the same matches: means, wins, and which one misses the truth's rate.

    `a_further` counts the matches where `a`'s predicted possessions per minute are further from
    the ground truth's than `b`'s -- the time-scale half of a comparison.
    """
    sa, sb = a["spell_f1"].to_numpy()[:-1], b["spell_f1"].to_numpy()[:-1]
    gt = a["gt_per_min"].to_numpy()[:-1]
    ra, rb = a["pred_per_min"].to_numpy()[:-1], b["pred_per_min"].to_numpy()[:-1]
    return {
        "a": float(sa.mean()),
        "b": float(sb.mean()),
        "a_wins": int((sa > sb).sum()),
        "b_wins": int((sb > sa).sum()),
        "a_further": int((np.abs(ra - gt) > np.abs(rb - gt)).sum()),
        "n": len(sa),
    }


def pair_table(
    clean: dict[str, pd.DataFrame], degraded: dict[str, pd.DataFrame], pairs: Sequence[str]
) -> list[str]:
    """One row per `A:B` pair and setting: the numbers a pre-registered comparison reads."""
    lines = [
        "| A : B | escenario | spellF1 A | spellF1 B | Δ A−B | A gana | B gana "
        "| ritmo de A más lejos de la verdad |",
        "|---|---|---:|---:|---:|---:|---:|---:|",
    ]
    for pair in pairs:
        a, _, b = pair.partition(":")
        for setting, tables in (("degradado", degraded), ("limpio", clean)):
            p = paired(tables[a], tables[b])
            lines.append(
                f"| `{a}` : `{b}` | {setting} | {_dec(p['a'])} | {_dec(p['b'])} "
                f"| {_dec(p['a'] - p['b'])} | {p['a_wins']}/{p['n']} | {p['b_wins']}/{p['n']} "
                f"| {p['a_further']}/{p['n']} |"
            )
    return lines


def wins(tables: dict[str, pd.DataFrame], column: str = "spell_f1") -> list[str]:
    """For every pair, on how many matches the row method beats the column one."""
    names = list(tables)
    lines = [
        "| gana a → | " + " | ".join(f"`{n}`" for n in names) + " |",
        "|---|" + "---:|" * len(names),
    ]
    for a in names:
        va = tables[a][column].to_numpy()[:-1]
        cells = []
        for b in names:
            vb = tables[b][column].to_numpy()[:-1]
            cells.append("—" if a == b else f"{int((va > vb).sum())}/{len(va)}")
        lines.append(f"| `{a}` | " + " | ".join(cells) + " |")
    return lines


def report(
    matches: Sequence[Match],
    clean: dict[str, pd.DataFrame],
    degraded: dict[str, pd.DataFrame],
    donor_ball: Sequence[float],
    public: dict | None,
    ours: dict[str, dict] | None,
    command: str,
    commit: str | None,
    pairs: Sequence[str] = (),
) -> str:
    origin = f" desde el commit `{commit}`" if commit else ""
    donors = ", ".join(_pct(b) for b in donor_ball)
    lines = [
        "# Corpus externo: IDSSE (DFL, 7 partidos)",
        "",
        f"Generado por `{command}`{origin}. No se edita a mano. Ground truth: `D` donde",
        "`BallStatus` = 0, si no el equipo de `BallPossession`. Puntuado con",
        "`possession_metrics.evaluate`. Protocolo y lectura: `docs/proposals/lane-external.md`.",
        "",
        "## Estructura del ground truth (dominio)",
        "",
        *describe_table(matches, public),
        "",
        "## spellF1 — limpio (tracking DFL completo)",
        "",
        *score_table(clean, "spell_f1"),
        "",
        f"## spellF1 — degradado (balón de BAR-ATH por mitad: {donors})",
        "",
        *score_table(degraded, "spell_f1"),
        "",
        "## macroF1 — limpio",
        "",
        *score_table(clean, "macro_f1"),
        "",
        "## macroF1 — degradado",
        "",
        *score_table(degraded, "macro_f1"),
        "",
        "## Escala temporal por partido — limpio",
        "",
        *time_scale_table(clean),
        "",
        "## Escala temporal por partido — degradado",
        "",
        *time_scale_table(degraded),
        "",
        "## Posesiones por minuto y %D predichos (media de partidos)",
        "",
        "| método | /min limpio | /min degradado | %D limpio | %D degradado |",
        "|---|---:|---:|---:|---:|",
    ]
    gt_rate = clean[next(iter(clean))]["gt_per_min"].iloc[-1]
    for name in clean:
        c, d = clean[name].iloc[-1], degraded[name].iloc[-1]
        lines.append(
            f"| `{name}` | {_dec(c['pred_per_min'], 2)} | {_dec(d['pred_per_min'], 2)} "
            f"| {_pct(c['pred_dead'])} | {_pct(d['pred_dead'])} |"
        )
    lines.append(f"| ground truth | {_dec(gt_rate, 2)} | {_dec(gt_rate, 2)} | | |")
    lines += [
        "",
        "## Partidos ganados (spellF1), limpio",
        "",
        *wins(clean),
        "",
        "## Partidos ganados (spellF1), degradado",
        "",
        *wins(degraded),
        "",
    ]
    if pairs:
        lines += ["## Pares pre-registrados", "", *pair_table(clean, degraded, pairs), ""]
    if ours:
        lines += [
            "## Comparación con nuestros instrumentos",
            "",
            "| método | público (bloque 1) | banco: media | banco: < 50% balón "
            "| externo limpio | externo degradado |",
            "|---|---:|---:|---:|---:|---:|",
        ]
        for name, s in ours.items():
            lines.append(
                f"| `{name}` | {_dec(s['clean'])} | {_dec(s['mean'])} | {_dec(s['low_mean'])} "
                f"| {_dec(clean[name]['spell_f1'].iloc[-1])} "
                f"| {_dec(degraded[name]['spell_f1'].iloc[-1])} |"
            )
        lines.append("")
    return "\n".join(lines)


def extra_methods(spec: str, taken: dict[str, Method]) -> dict[str, Method]:
    """`MODULE:ATTR` -> methods to score: a dict of them, or one callable named after `ATTR`.

    A name already taken by a different function is prefixed with the module's last component,
    so a plugged-in `engine` never silently replaces ours.
    """
    module_name, _, attr = spec.partition(":")
    found = getattr(importlib.import_module(module_name), attr or "METHODS")
    found = {attr: found} if callable(found) else dict(found)
    prefix = module_name.rsplit(".", 1)[-1]
    out: dict[str, Method] = {}
    for name, method in found.items():
        if name in taken and taken[name] is not method:
            name = f"{prefix}.{name}"
        out[name] = method
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="External validation corpus (IDSSE / DFL)")
    parser.add_argument("--describe", action="store_true", help="ground-truth structure only")
    parser.add_argument("--score", action="store_true", help="score METHODS, clean and degraded")
    parser.add_argument("--method", action="append", help="score only these (default: all)")
    parser.add_argument(
        "--extra",
        action="append",
        default=[],
        metavar="MODULE:ATTR",
        help="also score a dict of bench-style methods, or one, e.g. tools.decoder:METHODS",
    )
    parser.add_argument(
        "--pair",
        action="append",
        default=[],
        metavar="A:B",
        help="also tabulate A against B: means, wins, which rate is further from the truth",
    )
    parser.add_argument("--no-bench", action="store_true", help="skip our bench and public rows")
    parser.add_argument("--write", type=Path, help="write the document here instead of printing")
    args = parser.parse_args(argv)
    from tools import blocks as bl

    if not (args.describe or args.score):
        parser.error("say --describe or --score")
    try:
        matches = load_all()
        public = None
        gt_path = REPO_ROOT / "evaluation" / "gt" / "BAR-ATH_possession_gt_public.csv"
        if gt_path.exists():
            gt = pm.label_codes(pd.read_csv(gt_path).label)
            public = structure(gt, pm.valid_runs(gt))
        if not args.score:
            text = "\n".join(describe_table(matches, public)) + "\n"
        else:
            methods, extras = dict(METHODS), {}
            for spec in args.extra:
                extras.update(extra_methods(spec, methods))
            methods.update(extras)
            names = args.method or list(methods)
            paired_names = {n for pair in args.pair for n in pair.split(":")}
            if any(pair.count(":") != 1 for pair in args.pair):
                raise ValueError(f"a --pair is A:B, got {args.pair}")
            unknown = sorted((set(names) | paired_names) - set(methods))
            if unknown:
                raise ValueError(f"unknown method(s) {unknown}; known: {sorted(methods)}")
            names = list(names) + sorted(paired_names - set(names))
            donors = our_ball_halves()
            clean = {n: score(methods[n], matches) for n in names}
            degraded = {n: score(methods[n], matches, True, donors) for n in names}
            ours = None
            if not args.no_bench:
                # Public and bench for our registered methods and for every plugged-in one: the
                # extras share the bench signature by construction.
                loaded = bench.load()
                benched = {**bench.METHODS, **extras}
                ours = {
                    n: bench.summary(bench.bench(benched[n], *loaded))
                    for n in names
                    if n in benched
                }
            command = "python tools/external.py --score"
            command += "".join(f" --extra {e}" for e in args.extra)
            command += "".join(f" --method {n}" for n in (args.method or []))
            command += "".join(f" --pair {pair}" for pair in args.pair)
            if args.no_bench:
                command += " --no-bench"
            if args.write:
                command += f" --write {bl._relative(args.write)}"
            ball = [float(d.mean()) for d in donors]
            text = report(
                matches, clean, degraded, ball, public, ours, command, bl._git_commit(), args.pair
            )
    except (OSError, ValueError) as problem:
        print(f"external corpus failed: {problem}", file=sys.stderr)
        return 1
    if args.write:
        args.write.parent.mkdir(parents=True, exist_ok=True)
        args.write.write_text(text, encoding="utf-8", newline="\n")
        print(f"wrote {bl._relative(args.write)}")
    else:
        if hasattr(sys.stdout, "reconfigure"):
            sys.stdout.reconfigure(encoding="utf-8")
        sys.stdout.write(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
