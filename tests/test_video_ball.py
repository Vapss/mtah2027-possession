"""Lane ball-video: pixels to pitch, the plausibility filter and the merge, on synthetic data."""

from __future__ import annotations

import numpy as np
from _bundle import requires_bundle

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


def test_positive_crop_contains_the_label_box_and_negative_crop_stays_clear() -> None:
    rng = np.random.default_rng(0)
    for u, v in [(5.0, 5.0), (960.0, 540.0), (1915.0, 1075.0)]:
        (x0, y0), (cx, cy, w, h), negative = vb.crop_boxes(u, v, rng)
        assert 0 <= x0 <= vb.WIDTH - vb.CROP and 0 <= y0 <= vb.HEIGHT - vb.CROP
        assert np.isclose(x0 + cx, u, atol=vb.LABEL_BOX_PX / 2) and 0 < w <= vb.LABEL_BOX_PX
        assert cx - w / 2 >= 0 and cx + w / 2 <= vb.CROP and h > 0
        if negative is not None:
            nx, ny = negative
            inside = nx <= u <= nx + vb.CROP and ny <= v <= ny + vb.CROP
            assert not inside


def test_training_frames_are_equispaced_among_frames_with_ball() -> None:
    present = np.zeros(100, dtype=bool)
    present[[10, 20, 30, 40, 50, 90]] = True
    assert vb.training_frames(present, 0, 60, 3).tolist() == [10, 30, 50]


def test_out_inside_reads_the_ball_like_the_dead_ball_stream() -> None:
    ball = np.array([[0.5, 0.5, 0.0], [1.02, 0.5, 0.0], [np.nan, np.nan, 0.0]])
    out, inside = vb.out_inside(ball)
    assert out.tolist() == [False, True, False] and inside.tolist() == [True, False, False]


def test_the_excluded_window_covers_the_public_slice_with_a_minute_each_side() -> None:
    assert vb.EXCLUDED[0] <= 11185 - 1500 and vb.EXCLUDED[1] >= 18685 + 1500


def test_project_ball_is_the_inverse_of_to_pitch() -> None:
    ball = np.array([[0.25, 0.75, 0.0]])
    u, v = vb.project_ball(np.stack([H]), ball)
    x, y = vb.to_pitch(np.stack([H]), u, v)
    assert np.allclose([x[0], y[0]], [0.25, 0.75])


def test_operating_threshold_is_the_smallest_reaching_the_precision_target() -> None:
    rows = [
        {"conf": 0.1, "precision_2m": 0.8},
        {"conf": 0.3, "precision_2m": 0.91},
        {"conf": 0.5, "precision_2m": 0.96},
        {"conf": 0.7, "precision_2m": float("nan")},
    ]
    assert vb.operating_threshold(rows, 0.90) == 0.3
    assert vb.operating_threshold(rows, 0.95) == 0.5
    assert vb.operating_threshold(rows, 0.99) is None


@requires_bundle
def test_the_video_bench_without_video_reproduces_the_engine_bench() -> None:
    from tools import atd, bench, dead_ball, emision

    f, ev, gt, cut = bench.load()
    reference = bench.summary(bench.bench(bench.METHODS["engine"], f, ev, gt, cut))
    tracking = atd.load("tactical")
    ball, _present = tracking.ball()
    rows = vb.bench_video(
        vb.VARIANTS["V0"],
        "opt",
        tracking.players_array,
        emision.team_slots(),
        ball,
        dead_ball.load_evidence(),
        None,
        vb.load_matrices(),
        gt,
        cut,
    )
    assert bench.summary(rows) == reference
