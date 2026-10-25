"""The raw ATD reader: the one module allowed to know the tracking file format.

The delivered `*_atd.txt` is `frame_id:player;player;...:ball`, and the ball is the **last** field.
That is the trap this suite exists to lock down: reading "the first position of every line" as the
ball gives 40.0% presence and a phantom 52,239-frame gap, while the last field gives the measured
113,488 / 199,319 (56.9%).

Two layers are tested separately.

- The *delivered* file is the interesting case, so those tests read it and skip on a checkout
  without the bundle, exactly like `test_smart_tagging.py`.
- The *format* is tested on small synthetic files, so a change in writer, delimiter or field order
  fails without needing 195 MB of tracking data. Every number below was measured on the delivered
  file; none is copied from an earlier run of the module.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

import games
from tools import atd

ATD_TXT = Path(games.asset_paths()["atd_raw"])
N_FRAMES = games.source_frames()

# Measured on data/tactical/BAR-ATH_tactical_atd.txt, 2024-25 LaLiga J2 BAR-ATH.
EXPECTED_SLOTS = 46
EXPECTED_BALL_PRESENT = 113488
PLAY_MEDIAN_PLAYERS = 22
HALFTIME_MEDIAN_PLAYERS = 12
FIRST_BALL_FRAME = 4192
# The ball is detected from video frame 11187: two frames after the kickoff Smart Tagging marks at
# 11185, which is the frame the tracking first reports it moving.
KICKOFF_BALL_FRAME = 11187
KICKOFF_BALL_XY = (0.50431, 0.48090)


@pytest.fixture(scope="module")
def tracking() -> atd.Tracking:
    if not ATD_TXT.is_file():
        pytest.skip("match bundle not unpacked -- see data/README.md")
    return atd.load()


def record(
    frame_id: int,
    slots: int = 3,
    ball: tuple[str, ...] = ("NaN", "NaN", "NaN"),
    players: list[tuple[str, str, str]] | None = None,
) -> str:
    """One ATD line, shaped like the export: id, the player slots, the ball last."""
    cells = players if players is not None else [("NaN", "NaN", "NaN")] * slots
    body = ";".join(",".join(cell) for cell in cells)
    return f"{frame_id}:{body}:{','.join(ball)}\n"


def write(tmp_path: Path, *lines: str) -> Path:
    path = tmp_path / "BAR-ATH_tactical_atd.txt"
    path.write_text("".join(lines), encoding="ascii")
    return path


def test_frames_are_the_video_frames(tracking: atd.Tracking) -> None:
    """The file counts 1..N; a submission counts 0..N-1. One subtraction, done once, here."""
    frames = tracking.frames()
    assert frames.dtype == np.int64
    assert np.array_equal(frames, np.arange(N_FRAMES))
    assert len(tracking) == N_FRAMES


def test_ball_is_the_last_field(tmp_path: Path) -> None:
    """A player sits in the first slot with a tempting triplet; the ball is the last field."""
    path = write(
        tmp_path,
        record(1, ball=("0.10", "0.20", "NaN"), players=[("0.90", "0.90", "0.90")]),
        record(2, ball=("0.11", "0.21", "NaN"), players=[("0.91", "0.91", "0.91")]),
    )
    positions, present = atd.read(path, expected_frames=2).ball()

    assert present.tolist() == [True, True]
    assert np.allclose(positions[:, :2], [[0.10, 0.20], [0.11, 0.21]])
    assert np.isnan(positions[0, 2])


def test_presence_does_not_require_the_z_channel(tmp_path: Path) -> None:
    """Only 9,909 of the 113,488 present balls have all three channels; z is mostly missing."""
    path = write(tmp_path, record(1, ball=("0.5", "0.5", "NaN")))
    positions, present = atd.read(path, expected_frames=1).ball()

    assert present.tolist() == [True]
    assert np.isnan(positions[0, 2])


def test_an_absent_ball_is_all_nan(tmp_path: Path) -> None:
    path = write(tmp_path, record(1))
    positions, present = atd.read(path, expected_frames=1).ball()

    assert present.tolist() == [False]
    assert np.isnan(positions).all()


def test_players_returns_the_slots_of_one_frame(tmp_path: Path) -> None:
    path = write(
        tmp_path,
        record(1, players=[("0.1", "0.2", "0.3"), ("NaN", "NaN", "NaN")]),
        record(2, players=[("0.4", "0.5", "0.6"), ("0.7", "0.8", "0.9")]),
    )
    tracking = atd.read(path, expected_frames=2)

    assert tracking.n_slots == 2
    assert np.allclose(tracking.players(1), [[0.4, 0.5, 0.6], [0.7, 0.8, 0.9]])
    assert np.isnan(tracking.players(0)[1]).all()


def test_players_rejects_a_frame_outside_the_file(tmp_path: Path) -> None:
    path = write(tmp_path, record(1))
    tracking = atd.read(path, expected_frames=1)

    for frame in (-1, 1):
        with pytest.raises(IndexError, match="outside"):
            tracking.players(frame)


def test_delivered_players_match_an_independent_parse(tracking: atd.Tracking) -> None:
    """One frame in ten thousand, re-read from the text without going through the reader."""
    lines = ATD_TXT.read_text(encoding="ascii").splitlines()
    for frame in (0, KICKOFF_BALL_FRAME, 50000, 110000, N_FRAMES - 1):
        _, players, ball = lines[frame].split(":")
        cells = [cell for slot in players.split(";") for cell in slot.split(",")]
        expected = np.array([float(cell) for cell in cells])
        assert np.allclose(
            tracking.players(frame), expected.reshape(EXPECTED_SLOTS, 3), equal_nan=True
        )
        positions, present = tracking.ball()
        assert np.allclose(
            positions[frame], [float(cell) for cell in ball.split(",")], equal_nan=True
        )
        assert present[frame] == (not ball.startswith("NaN"))


def test_delivered_fingerprint(tracking: atd.Tracking) -> None:
    """The three invariants the reader asserts, measured here rather than trusted."""
    assert len(tracking) == N_FRAMES
    assert tracking.n_slots == EXPECTED_SLOTS
    _, present = tracking.ball()
    assert int(present.sum()) == EXPECTED_BALL_PRESENT


def test_ball_is_present_most_of_the_time_but_never_all_of_it(tracking: atd.Tracking) -> None:
    _, present = tracking.ball()

    assert present[FIRST_BALL_FRAME]
    assert not present[:FIRST_BALL_FRAME].any()
    assert 0.5 < present.mean() < 0.65


def test_players_are_on_the_pitch_during_play_and_thin_out_at_halftime(
    tracking: atd.Tracking,
) -> None:
    """The plan said "almost nobody at halftime". Measured: a median of 12, not zero.

    The premise is worth keeping as a test because it is what `D` has to be built on (#27): the
    tracking does not stop at halftime, so "no players" cannot be a dead-ball signal either.
    """
    counts = (~np.isnan(tracking.players_array[:, :, 0])).sum(axis=1)
    blocks = games.half_video_blocks(games.GAME)
    play = np.zeros(N_FRAMES, dtype=bool)
    for _, first, last in blocks:
        play[first : last + 1] = True
    halftime = np.zeros(N_FRAMES, dtype=bool)
    halftime[blocks[0][2] + 1 : blocks[1][1]] = True

    assert int(np.median(counts[play])) == PLAY_MEDIAN_PLAYERS
    assert int(np.median(counts[halftime])) == HALFTIME_MEDIAN_PLAYERS
    assert counts[halftime].max() < counts[play].max()


def test_kickoff_ball_is_where_the_kickoff_was(tracking: atd.Tracking) -> None:
    """A cross-check of the frame alignment that does not use the file's own ids."""
    positions, present = tracking.ball()

    assert np.allclose(positions[KICKOFF_BALL_FRAME, :2], KICKOFF_BALL_XY, atol=1e-4)
    # Not a claim about the kickoff itself: the ball is simply not tracked until it is struck.
    assert not present[KICKOFF_BALL_FRAME - 1]


def test_arrays_are_read_only(tracking: atd.Tracking) -> None:
    """`load()` hands out one shared instance, so nobody may write through it."""
    with pytest.raises(ValueError):
        tracking.ball()[0][0, 0] = 0.5
    with pytest.raises(ValueError):
        tracking.players(0)[0, 0] = 0.5


def test_read_rejects_identifiers_that_skip_a_frame(tmp_path: Path) -> None:
    path = write(tmp_path, record(1), record(2), record(4))

    with pytest.raises(atd.ATDError, match="frame_id"):
        atd.read(path, expected_frames=3)


def test_read_rejects_a_record_without_its_ball_field(tmp_path: Path) -> None:
    path = write(tmp_path, "1:NaN,NaN,NaN;NaN,NaN,NaN\n")

    with pytest.raises(atd.ATDError, match="field"):
        atd.read(path, expected_frames=1)


def test_read_rejects_a_changed_slot_count(tmp_path: Path) -> None:
    path = write(tmp_path, record(1, slots=3), record(2, slots=2))

    with pytest.raises(atd.ATDError, match="slot"):
        atd.read(path, expected_frames=2)


def test_read_rejects_the_wrong_number_of_records(tmp_path: Path) -> None:
    path = write(tmp_path, record(1), record(2))

    with pytest.raises(atd.ATDError, match="records"):
        atd.read(path, expected_frames=3)


def test_read_rejects_a_coordinate_that_is_not_a_number(tmp_path: Path) -> None:
    path = write(tmp_path, record(1, players=[("abc", "0.2", "0.3")]))

    with pytest.raises(atd.ATDError, match="record 1"):
        atd.read(path, expected_frames=1)


def test_read_rejects_a_ball_with_the_wrong_number_of_channels(tmp_path: Path) -> None:
    path = write(tmp_path, record(1, ball=("0.5", "0.5")))

    with pytest.raises(atd.ATDError, match="record 1"):
        atd.read(path, expected_frames=1)


def test_cli_reports_the_fingerprint(tracking: atd.Tracking, capsys: pytest.CaptureFixture) -> None:
    assert atd.main([]) == 0
    output = capsys.readouterr().out
    assert str(N_FRAMES) in output
    assert str(EXPECTED_SLOTS) in output
    assert "113488" in output
