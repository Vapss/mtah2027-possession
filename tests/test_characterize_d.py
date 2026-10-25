"""A0: what `D` actually is, measured instead of assumed.

The backlog spent a stream on "no ball means dead ball" before anyone looked. The measurements
here are what the rest of stream A (#5, #10, #16) has to be built on, so they are computed by a
module with tests rather than typed into a document by hand.

Every case below is synthetic: small label arrays and two-point tracks. The real numbers are
produced by `python tools/characterize_d.py`, which needs the bundle and skips without it.
"""

from __future__ import annotations

import numpy as np
import pytest

from tools import characterize_d as cd

FPS = 25
METRES = (105.3, 68.0)


def test_runs_are_half_open_and_in_order() -> None:
    labels = np.array(["H", "H", "D", "D", "A", "D"])

    runs = cd.runs(labels, "D")

    assert runs == [cd.Run(2, 4), cd.Run(5, 6)]


def test_runs_of_a_label_that_is_absent_are_empty() -> None:
    assert cd.runs(np.array(["H", "A"]), "D") == []


def test_runs_accept_the_label_at_the_very_end() -> None:
    assert cd.runs(np.array(["H", "D"]), "D") == [cd.Run(1, 2)]


def test_durations_are_in_seconds_and_share_of_the_labelled_time() -> None:
    labels = np.array(["H", "D", "D", "D", "D", "A", "D", "D"])

    rows = cd.duration_table(cd.runs(labels, "D"), FPS, len(labels))

    assert [(row.frames, row.seconds) for row in rows] == [(4, 0.16), (2, 0.08)]
    assert [round(row.share, 4) for row in rows] == [0.5, 0.25]


def test_contingency_is_precision_recall_and_lift() -> None:
    """P(D | mask) is what a detector promises; P(mask | D) is what it costs to miss."""
    labels = np.array(["D", "D", "H", "H", "D", "H"])
    mask = np.array([True, False, True, False, True, False])

    stats = cd.contingency(labels, mask, "D")

    assert (stats.hits, stats.mask_frames, stats.label_frames) == (2, 3, 3)
    assert stats.precision == pytest.approx(2 / 3)
    assert stats.recall == pytest.approx(2 / 3)
    assert stats.base_rate == pytest.approx(0.5)
    assert stats.lift == pytest.approx((2 / 3) / 0.5)


def test_contingency_of_an_empty_mask_is_not_a_division() -> None:
    stats = cd.contingency(np.array(["D", "H"]), np.array([False, False]), "D")

    assert stats.mask_frames == 0
    assert stats.precision == 0.0
    assert stats.recall == 0.0
    assert stats.lift == 0.0


def test_speed_is_metres_per_second_between_two_detections() -> None:
    """One frame moves 1/25 s; 1 m of pitch per frame is 25 m/s."""
    positions = np.array(
        [[0.0, 0.5, np.nan], [1 / METRES[0], 0.5, np.nan], [2 / METRES[0], 0.5, np.nan]]
    )
    present = np.array([True, True, True])

    speed = cd.ball_speed(positions, present, METRES, FPS)

    # Speed at index i is the movement from i-1 to i, so the first frame has no speed yet.
    assert np.allclose(speed, [np.nan, 25.0, 25.0], equal_nan=True)


def test_speed_across_a_missing_detection_is_unknown() -> None:
    positions = np.array([[0.0, 0.5, np.nan], [0.0, 0.5, np.nan], [1 / METRES[0], 0.5, np.nan]])
    present = np.array([True, False, True])

    speed = cd.ball_speed(positions, present, METRES, FPS)

    assert np.isnan(speed).all()


def test_nearest_player_distance_ignores_absent_slots() -> None:
    """An empty slot is not a player standing on the ball."""
    ball = np.array([[0.5, 0.5, np.nan]])
    players = np.zeros((1, 2, 3))
    players[0, 0] = [np.nan, np.nan, np.nan]
    players[0, 1] = [0.6, 0.5, np.nan]  # 0.1 of the length away

    distance = cd.nearest_player_distance(ball, players, METRES)

    assert distance[0] == pytest.approx(0.1 * METRES[0])


def test_nearest_player_distance_scales_x_and_y_by_their_own_length() -> None:
    """The pitch is 105.3 x 68.0: a ball at (0.3, 0.7) with a player 0.1 away in y is 6.8 m off.

    Sharing one ball column for both axes reads y = x -- and passes any test where the ball sits
    at x == y, which is exactly the test this one replaces.
    """
    ball = np.array([[0.3, 0.7, np.nan]])
    along_y = np.array([[[0.3, 0.8, np.nan]]])
    along_x = np.array([[[0.4, 0.7, np.nan]]])

    assert cd.nearest_player_distance(ball, along_y, METRES)[0] == pytest.approx(0.1 * METRES[1])
    assert cd.nearest_player_distance(ball, along_x, METRES)[0] == pytest.approx(0.1 * METRES[0])


def test_an_empty_frame_has_no_nearest_player() -> None:
    ball = np.array([[0.5, 0.5, np.nan]])
    players = np.full((1, 2, 3), np.nan)

    assert np.isnan(cd.nearest_player_distance(ball, players, METRES)).all()


def test_out_of_bounds_reads_the_ball_not_the_players() -> None:
    positions = np.array([[0.5, 0.5, np.nan], [-0.01, 0.5, np.nan], [0.5, 1.02, np.nan]])

    assert cd.out_of_bounds(positions).tolist() == [False, True, True]


def test_the_report_names_the_sample_and_every_claim() -> None:
    """A document whose numbers cannot be traced to a function is a rumour."""
    labels = np.array(["D", "D", "H", "H", "D", "H"])
    mask = np.array([True, False, True, False, True, False])
    sample = cd.Sample(
        first_frame=11185,
        last_frame=11190,
        labels=labels,
        masks=dict.fromkeys(cd.CODES, mask),
        speed=np.array([np.nan] * 6),
        nearest=np.array([np.nan] * 6),
        out_of_bounds=np.zeros(6, dtype=bool),
        ball_present=np.ones(6, dtype=bool),
    )

    text = cd.report(sample, FPS, commit="abc1234")

    assert "11185" in text and "11190" in text
    assert "abc1234" in text
    assert "SET PIECES" in text
    assert "P(D | señal)" in text
    # Two D runs of 2 frames each at 25 fps, and the share of the window they cover.
    assert "| 2 | 0,08 s |" in text
    assert "66,7%" in text


def test_cli_without_the_bundle_explains_itself(tmp_path, monkeypatch, capsys) -> None:
    def missing(*args, **kwargs):
        raise FileNotFoundError("match data not found")

    monkeypatch.setattr(cd, "load_sample", missing)
    target = tmp_path / "d.md"

    assert cd.main(["--write", str(target)]) == 1
    assert "match data not found" in capsys.readouterr().err
    assert not target.exists()
