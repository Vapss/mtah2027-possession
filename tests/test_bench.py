"""The gap-transplant bench: its degradation is exact and it reproduces the published baseline."""

from __future__ import annotations

import numpy as np
from _bundle import requires_bundle

from tools import bench, dead_ball, engine


def _features(n: int) -> tuple[engine.Features, dead_ball.Evidence]:
    present = np.ones(n, dtype=bool)
    f = engine.Features(np.full(n, 1.0), np.full(n, 2.0), present, np.full(n, 3.0), present.copy())
    ev = dead_ball.Evidence((), np.zeros(n, dtype=bool), present.copy(), np.zeros(n, dtype=bool))
    return f, ev


def test_degrade_deletes_the_ball_only_inside_the_window_where_the_donor_had_none() -> None:
    f, ev = _features(10)
    donor = np.array([True, False, False, True])
    f2, ev2 = bench.degrade(f, ev, (3, 7), donor)
    assert f2.present.tolist() == [True] * 4 + [False, False] + [True] * 4
    assert np.isnan(f2.home_m[4:6]).all() and not np.isnan(f2.home_m[3])
    # Speed needs this frame and the previous one: the frame after the gap has none either.
    assert np.isnan(f2.speed_mps[4:7]).all() and f2.speed_mps[3] == 3.0
    assert ev2.inside.tolist() == f2.present.tolist()
    assert f.present.all()  # the input is not modified


@requires_bundle
def test_the_rebuilt_floor_reproduces_its_public_score() -> None:
    f, ev, gt, cut = bench.load()
    rows = bench.bench(bench.METHODS["smooth50"], f, ev, gt, cut)
    assert round(rows[0]["spell_f1"], 4) == 0.3256  # the organisers' published public value
    assert len(rows) == 20  # the clean slice plus 19 full five-minute donors
