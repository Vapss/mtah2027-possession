"""The raw ATD tracking file: one reader, validated against the export it was written for.

`data/<source>/<game>_<source>_atd.txt` is FIFA/EPTS raw tracking, one record per video frame:

    frame_id:px,py,pz;px,py,pz;...;bx,by,bz

- `frame_id` counts **1..N**, so `video_frame = frame_id - 1`. A submission is indexed by video
  frame, and this subtraction is the only place the two clocks meet.
- one slot per tracked object, `NaN,NaN,NaN` when the object is not on the pitch.
- the ball is the **last** field, after the last `;`.

That last point is the trap. Reading "the first position of every line" as the ball gives 40.0%
presence and a phantom 52,239-frame gap, because the first slot is a player who is often present
while the ball is not. The last field gives the measured 113,488 / 199,319 (56.9%) for the tactical
recording.

Presence is `not NaN` on **x and y**, never on all three channels: only 9,909 of those 113,488
present balls carry a z, so requiring three would report the ball missing 95% of the time while it
is plainly there.

What is asserted
----------------
The three invariants from the backlog, as measured on the delivered file rather than assumed:

1. the records are numbered 1..N with no gap, and N is `games.source_frames(source)`;
2. during play a median of 22 slots are occupied (21-22 across the match);
3. halftime is *not* empty: the median is 12 players and the ball is detected on 18,961 of the
   20,156 halftime frames. The plan's "almost nobody at halftime" was wrong, and it matters: the
   tracking does not stop, so neither "no players" nor "no ball" can be a dead-ball signal (#27).

A file that does not match the fingerprint of the export it claims to be is rejected at load time,
because every downstream number would otherwise be silently wrong.
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import numpy as np

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

import games  # noqa: E402

# Three channels per slot: two pitch/image coordinates and a third the export fills only sometimes.
CHANNELS = 3
FIELDS = 3


@dataclass(frozen=True)
class Fingerprint:
    """What the delivered file for one source measurably is.

    Only the numbers that identify the export live here. The record count is not duplicated: it
    comes from `games.source_frames()`, which is the same constant the submission length uses, so
    the two cannot drift apart.
    """

    slots: int
    ball_present: int
    play_median_players: int | None = None
    halftime_median_players: int | None = None


# Measured on the delivered bundle (2024-25 LaLiga J2, BAR-ATH). Broadcast is a different export:
# 51 slots, no halves mapping of its own, so it gets no player-count invariants.
FINGERPRINTS = {
    "tactical": Fingerprint(
        slots=46,
        ball_present=113488,
        play_median_players=22,
        halftime_median_players=12,
    ),
    "broadcast": Fingerprint(slots=51, ball_present=83121),
}


class ATDError(ValueError):
    """The tracking file is not the export this module knows how to read."""

    def __init__(self, path: object, problems: list[str]) -> None:
        self.problems = list(problems)
        detail = "\n".join(f"  - {problem}" for problem in self.problems)
        super().__init__(f"{path}: {len(self.problems)} problem(s)\n{detail}")


class Tracking:
    """A parsed tracking file, indexed by video frame.

    One instance per file, shared through `load()`, so the arrays are read-only: a job that writes
    through `players()` would corrupt every other caller in the process.
    """

    __slots__ = ("_ball", "_frames", "_players")

    def __init__(self, players: np.ndarray, ball: np.ndarray) -> None:
        for array in (players, ball):
            array.flags.writeable = False
        self._players = players
        self._ball = ball
        self._frames = np.arange(len(players), dtype=np.int64)
        self._frames.flags.writeable = False

    def __len__(self) -> int:
        return len(self._frames)

    def __repr__(self) -> str:
        return f"Tracking(frames={len(self)}, slots={self.n_slots})"

    @property
    def n_slots(self) -> int:
        """How many tracked objects each record carries (players, plus the ball as a field)."""
        return int(self._players.shape[1])

    @property
    def players_array(self) -> np.ndarray:
        """The whole table, `(frames, slots, 3)`, read-only. For vectorised work."""
        return self._players

    def frames(self) -> np.ndarray:
        """Video frames in order, `0..len(self)-1`. The file's ids minus one."""
        return self._frames

    def ball(self) -> tuple[np.ndarray, np.ndarray]:
        """Ball positions `(frames, 3)` and a `(frames,)` presence mask.

        Present means x and y are known -- see the module docstring for why z cannot be required.
        An absent ball is all-`NaN` in the position table.
        """
        return self._ball, ~np.isnan(self._ball[:, 0])

    def players(self, frame: int) -> np.ndarray:
        """The slots of one video frame, `(slots, 3)`, `NaN` where nothing is tracked."""
        index = int(frame)
        if not 0 <= index < len(self):
            raise IndexError(
                f"video frame {index} is outside this file (0..{len(self) - 1}); "
                "the file's own ids start at 1, so frame = frame_id - 1"
            )
        return self._players[index]


def path(source: str = games.DEFAULT_SOURCE) -> Path:
    """The raw tracking file named by games.asset_paths(), whether or not it exists."""
    return Path(games.asset_paths(source=source)["atd_raw"])


def _scan(path: Path) -> tuple[int, int]:
    """Record count and slot count, from a single cheap pass that never builds an array."""
    with path.open("r", encoding="ascii") as handle:
        first = handle.readline()
        if not first:
            raise ATDError(path, ["the file is empty"])
        fields = first.rstrip("\n").split(":")
        if len(fields) != FIELDS:
            raise ATDError(
                path,
                [
                    f"record 1 has {len(fields)} ':'-separated fields, expected {FIELDS} "
                    "(frame_id:players:ball) -- is the ball the last field?"
                ],
            )
        slots = len(fields[1].split(";"))
        records = 1 + sum(1 for _ in handle)
    return records, slots


def _numbers(cell: str, frame_id: int, what: str, file: Path) -> np.ndarray:
    """Parse one comma-separated group, naming the record and the file when it does not parse."""
    try:
        return np.fromstring(cell, sep=",", dtype=np.float64)
    except ValueError as problem:
        raise ATDError(
            file, [f"record {frame_id}: {what} is not a list of numbers ({problem})"]
        ) from None


def read(file: str | Path, expected_frames: int | None = None) -> Tracking:
    """Parse and structurally validate one tracking file.

    `expected_frames` is the record count the caller expects -- `games.source_frames(source)` when
    reading the bundle. Passing it explicitly is what makes a truncated or extended export fail
    here instead of producing a short, perfect-looking array.
    """
    file = Path(file)
    if not file.is_file():
        raise ATDError(file, ["no such file"])

    records, slots = _scan(file)
    problems: list[str] = []
    if expected_frames is not None and records != expected_frames:
        problems.append(f"{records} records, expected {expected_frames}")
    if slots < 1:
        problems.append("the first record has no player slots")
    if problems:
        raise ATDError(file, problems)

    players = np.full((records, slots, CHANNELS), np.nan, dtype=np.float64)
    ball = np.full((records, CHANNELS), np.nan, dtype=np.float64)

    with file.open("r", encoding="ascii") as handle:
        for index, line in enumerate(handle):
            frame_id = index + 1
            fields = line.rstrip("\n").split(":")
            if len(fields) != FIELDS:
                raise ATDError(
                    file,
                    [
                        f"record {frame_id} has {len(fields)} ':'-separated fields, expected "
                        f"{FIELDS} (frame_id:players:ball)"
                    ],
                )
            if fields[0].strip() != str(frame_id):
                raise ATDError(
                    file,
                    [
                        f"frame_id column is not 1..{records} in order: record {frame_id} says "
                        f"{fields[0].strip()!r}"
                    ],
                )

            cells = fields[1].split(";")
            if len(cells) != slots:
                raise ATDError(
                    file,
                    [
                        f"record {frame_id} has {len(cells)} player slots, expected {slots} "
                        "(the count on record 1)"
                    ],
                )
            flat = _numbers(fields[1].replace(";", ","), frame_id, "a player slot", file)
            if flat.size != slots * CHANNELS:
                raise ATDError(
                    file,
                    [
                        f"record {frame_id}: {flat.size} player coordinates, expected "
                        f"{slots * CHANNELS} ({slots} slots x {CHANNELS})"
                    ],
                )
            players[index] = flat.reshape(slots, CHANNELS)

            channels = _numbers(fields[2], frame_id, "the ball field", file)
            if channels.size != CHANNELS:
                raise ATDError(
                    file,
                    [
                        f"record {frame_id}: the ball field has {channels.size} channels, "
                        f"expected {CHANNELS}"
                    ],
                )
            ball[index] = channels

    return Tracking(players, ball)


def fingerprint_problems(tracking: Tracking, source: str = games.DEFAULT_SOURCE) -> list[str]:
    """How `tracking` differs from the delivered export for `source`, as readable strings.

    These are fingerprints, not ideals: they say "this is the file the rest of the pipeline was
    measured against", which is exactly the assumption every downstream number rests on.
    """
    expected = FINGERPRINTS.get(source)
    if expected is None:
        return []

    problems = []
    if tracking.n_slots != expected.slots:
        problems.append(f"{tracking.n_slots} slots, expected {expected.slots} for {source}")

    _, present = tracking.ball()
    found = int(present.sum())
    if found != expected.ball_present:
        problems.append(
            f"the ball is present on {found} frames, expected {expected.ball_present} for "
            f"{source} -- check that the ball is the last field, not the first"
        )

    if expected.play_median_players is not None:
        counts = (~np.isnan(tracking.players_array[:, :, 0])).sum(axis=1)
        play, halftime = _halves_masks(len(tracking))
        for label, mask, wanted in (
            ("during play", play, expected.play_median_players),
            ("at halftime", halftime, expected.halftime_median_players),
        ):
            if not mask.any():
                continue
            found_median = int(np.median(counts[mask]))
            if found_median != wanted:
                problems.append(
                    f"median occupied slots {label} is {found_median}, expected {wanted}"
                )
    return problems


def _halves_masks(n_frames: int) -> tuple[np.ndarray, np.ndarray]:
    """Playing time and halftime, from the halves table in games.py.

    `games.half_video_blocks()` is already the mapping between the tracking clock and video frames,
    so the gap between its two blocks *is* halftime -- 20,156 frames here. Nothing is hardcoded.
    """
    play = np.zeros(n_frames, dtype=bool)
    blocks = games.half_video_blocks(games.GAME)
    for _, first, last in blocks:
        play[first : last + 1] = True
    halftime = np.zeros(n_frames, dtype=bool)
    if len(blocks) > 1:
        halftime[blocks[0][2] + 1 : blocks[1][1]] = True
    return play, halftime


@lru_cache(maxsize=2)
def _load(file: str, source: str, expected_frames: int) -> Tracking:
    tracking = read(file, expected_frames=expected_frames)
    problems = fingerprint_problems(tracking, source)
    if problems:
        raise ATDError(file, problems)
    return tracking


def load(source: str = games.DEFAULT_SOURCE) -> Tracking:
    """The bundle's tracking file for `source`, parsed once per process and validated.

    Costs about 3 s and 230 MB on the delivered tactical file; the result is cached and read-only,
    so callers may share it. Any job that needs the tracking should call this instead of reading
    the text itself.
    """
    file = path(source).resolve()
    return _load(str(file), source, games.source_frames(source))


def summary(tracking: Tracking) -> list[tuple[str, str]]:
    """The fingerprint of a loaded file, as label/value pairs for the CLI and for reports."""
    _, present = tracking.ball()
    counts = (~np.isnan(tracking.players_array[:, :, 0])).sum(axis=1)
    play, halftime = _halves_masks(len(tracking))
    rows = [
        ("frames", f"{len(tracking)}"),
        ("slots", f"{tracking.n_slots}"),
        ("ball present", f"{int(present.sum())} ({present.mean():.1%})"),
        ("first ball frame", f"{int(np.flatnonzero(present)[0]) if present.any() else 'none'}"),
    ]
    if play.any():
        rows.append(("players median during play", f"{int(np.median(counts[play]))}"))
    if halftime.any():
        rows.append(("players median at halftime", f"{int(np.median(counts[halftime]))}"))
    return rows


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Read and validate one ATD tracking file")
    parser.add_argument(
        "--source",
        default=games.DEFAULT_SOURCE,
        choices=sorted(games.SOURCES),
        help=f"which recording to read ({games.DEFAULT_SOURCE})",
    )
    args = parser.parse_args(argv)

    tracking = load(args.source)
    print(f"{games.GAME} {args.source}  {path(args.source)}")
    for label, value in summary(tracking):
        print(f"  {label:<28} {value}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
