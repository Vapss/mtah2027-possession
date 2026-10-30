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
    ev = dead_ball.Evidence((), np.ones(10, dtype=bool), ev.inside, ev.still)
    donor = np.array([True, False, False, True])
    f2, ev2 = bench.degrade(f, ev, (3, 7), donor)
    gone = [True] * 4 + [False, False] + [True] * 4
    assert f2.present.tolist() == gone
    assert f2.in_pitch.tolist() == gone
    assert ev2.inside.tolist() == gone and ev2.out.tolist() == gone
    assert np.isnan(f2.home_m[4:6]).all() and np.isnan(f2.away_m[4:6]).all()
    assert not np.isnan(f2.home_m[3]) and not np.isnan(f2.away_m[6])
    # Speed needs this frame and the previous one: the frame after the gap has none either.
    assert np.isnan(f2.speed_mps[4:7]).all() and f2.speed_mps[3] == 3.0
    assert f.present.all() and ev.out.all()  # the inputs are not modified


def test_spell_f1_matches_the_official_evaluate() -> None:
    import sys

    sys.path.insert(0, str(bench.REPO_ROOT / "evaluation"))
    import possession_metrics as pm

    gt = pm.label_codes(["X", "H", "H", "D", "A", "A", "A", "X"])
    labels = np.array(["X", "H", "H", "H", "A", "X", "A", "X"], dtype=object)
    runs = pm.valid_runs(gt)
    expected = pm.evaluate(gt, pm.label_codes(list(labels)))["spell_f1_mean"]
    assert bench.spell_f1(gt, labels, runs) == float(expected)


@requires_bundle
def test_the_rebuilt_floor_reproduces_its_public_score() -> None:
    f, ev, gt, cut = bench.load()
    rows = bench.bench(bench.METHODS["smooth50"], f, ev, gt, cut)
    assert round(rows[0]["spell_f1"], 4) == 0.3256  # the organisers' published public value
    assert len(rows) == 20  # the clean slice plus 19 full five-minute donors
