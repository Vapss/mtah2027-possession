"""Lane ball-video: pixels to pitch, the plausibility filter and the merge, on synthetic data."""

from __future__ import annotations

import numpy as np

from tools import video_ball as vb

# A pitch-to-image homography: x scaled to 1000 px, y to 500 px, shifted by (100, 50).
H = np.array([[1000.0, 0.0, 100.0], [0.0, 500.0, 50.0], [0.0, 0.0, 1.0]])


def _det(frames, u, v, conf) -> dict[str, np.ndarray]:
    n = len(frames)
    return {
        "frame": np.asarray(frames, dtype=np.int64),
        "u": np.asarray(u, dtype=float),
        "v": np.asarray(v, dtype=float),
        "w": np.full(n, 6.0),
        "h": np.full(n, 6.0),
        "conf": np.asarray(conf, dtype=float),
    }


def test_to_pitch_inverts_the_pitch_to_image_homography() -> None:
    x, y = vb.to_pitch(np.stack([H, H]), np.array([600.0, 100.0]), np.array([300.0, 50.0]))
    assert np.allclose(x, [0.5, 0.0]) and np.allclose(y, [0.5, 0.0])


def test_best_per_frame_keeps_the_most_confident_box_above_the_threshold() -> None:
    frame = np.array([0, 0, 2, 2, 3])
    conf = np.array([0.2, 0.6, 0.6, 0.6, 0.1])
    best = vb.best_per_frame(frame, conf, 5, min_conf=0.15)
    assert best.tolist() == [1, -1, 2, -1, -1]  # a tie goes to the earlier row; 0.1 is dropped


def test_candidates_drop_low_confidence_and_far_off_pitch_balls() -> None:
    det = _det([0, 1, 2], [600.0, 600.0, 2000.0], [300.0, 300.0, 300.0], [0.9, 0.1, 0.9])
    x, _y, ok = vb.candidates(det, np.stack([H] * 4), 4, vb.Filter(min_conf=0.3))
    assert ok.tolist() == [True, False, False, False]  # frame 2 projects to x = 1.9
    assert np.isclose(x[0], 0.5) and np.isnan(x[1:]).all()


def test_an_isolated_ball_is_rejected_and_a_consistent_one_kept() -> None:
    n = 20
    x = np.full(n, np.nan)
    y = np.full(n, np.nan)
    x[[3, 4]] = 0.5  # two frames in a row at the same place: they support each other
    y[[3, 4]] = 0.5
    x[12], y[12] = 0.2, 0.2  # alone: nothing within five frames
    ok = ~np.isnan(x)
    ref = np.column_stack([x, y])
    keep = vb.supported(x, y, ok, ref)
    assert np.flatnonzero(keep).tolist() == [3, 4]


def test_a_ball_too_far_from_its_neighbour_for_the_speed_bound_is_rejected() -> None:
    n = 10
    x = np.full(n, np.nan)
    y = np.full(n, 0.5)
    x[2], x[3] = 0.1, 0.6  # 52 m in one frame: no ball moves at 1,300 m/s
    ok = ~np.isnan(x)
    keep = vb.supported(x, y, ok, np.column_stack([x, y]))
    assert not keep.any()


def test_the_tracking_ball_supports_a_video_ball_at_the_edge_of_a_gap() -> None:
    n = 10
    tracking = np.full((n, 2), np.nan)
    tracking[:4] = 0.5  # the tracking loses the ball after frame 3
    x = np.full(n, np.nan)
    y = np.full(n, np.nan)
    x[5], y[5] = 0.501, 0.5  # one video ball two frames later, 10 cm away
    ok = ~np.isnan(x)
    ref = tracking.copy()
    ref[5] = [x[5], y[5]]
    assert vb.supported(x, y, ok, ref)[5]


def test_merge_fills_only_the_tracking_gaps() -> None:
    tracking = np.array([[0.1, 0.1, 0.0], [np.nan, np.nan, 1.0], [np.nan, np.nan, 0.0]])
    video = np.array([[0.9, 0.9], [0.3, 0.4], [0.5, 0.5]])
    merged = vb.merge_ball(tracking, video, np.array([True, True, False]))
    assert merged[0, :2].tolist() == [0.1, 0.1]  # the tracking wins where it has a ball
    assert merged[1, :2].tolist() == [0.3, 0.4] and np.isnan(merged[1, 2])
    assert np.isnan(merged[2, 0])  # not accepted: still a gap
    assert np.isnan(tracking[1, 0])  # the input is not modified


def test_sample_frames_draws_runs_that_qualify_entirely_and_is_seeded() -> None:
    present = np.zeros(1000, dtype=bool)
    present[100:600] = True
    a = vb.sample_frames(present, [(50, 950)], n_clusters=5, length=10)
    b = vb.sample_frames(present, [(50, 950)], n_clusters=5, length=10)
    assert all(np.array_equal(a[k], b[k]) for k in a)
    assert present[a["with_ball"]].all() and not present[a["gap"]].any()
    assert ((a["gap"] >= 50) & (a["gap"] < 950)).all()
