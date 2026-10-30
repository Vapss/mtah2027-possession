"""Lane m-dating: changes, one-to-one matching, the dating error and the reference variant.

Synthetic arrays everywhere except the bundle test, which pins the reference variant to the
delivered file and skips when the match bundle is absent."""

from __future__ import annotations

import hashlib

import numpy as np
import pandas as pd
import pytest
from _bundle import requires_bundle

from tools import change_dating as cd
from tools import engine

N = engine.NONE


def test_state_changes_are_team_to_team_flips_inside_a_run() -> None:
    state = np.array([N, 0, 0, 1, 1, N, 1, 0, 0, 1], dtype=np.int8)
    # 0->1 at 3; the N gap at 5 is not a change; 1->0 at 7; a run edge at 9 hides 0->1 there.
    assert cd.state_changes(state, [(0, 9), (9, 10)]) == [(3, 1), (7, 0)]
    assert cd.state_changes(state, [(0, 10)]) == [(3, 1), (7, 0), (9, 1)]


def test_matching_is_one_to_one_same_team_within_the_tolerance_closest_first() -> None:
    truth = [(100, 1), (200, 0), (300, 1)]
    pred = [(104, 1), (102, 1), (190, 1), (420, 1)]
    pairs = cd.match(truth, pred, tolerance=50)
    # 102 is closer to 100 than 104; 190 is the wrong team for 200 and out of reach of 300.
    assert pairs == [(100, 102)]
    # Wider, 190 reaches 300 and is closer to it than 420: closest pairs first.
    assert cd.match(truth, pred, tolerance=125) == [(100, 102), (300, 190)]


def test_a_prediction_serves_one_truth_change_and_ties_go_to_the_earlier_truth() -> None:
    assert cd.match([(100, 0), (120, 0)], [(110, 0)], tolerance=50) == [(100, 110)]


def test_the_lag_is_positive_when_the_chain_is_late() -> None:
    d = cd.dating([(100, 0), (200, 1)], [(125, 0), (190, 1), (500, 0)])
    assert (d["matched"], d["missed"], d["extra"]) == (2, 0, 1)
    assert d["median"] == pytest.approx((25 / 25 + -10 / 25) / 2)
    assert d["median_abs"] == pytest.approx((1.0 + 0.4) / 2)
    assert d["late_1"] == 0.0 and d["within_1"] == 1.0


def test_a_window_counts_only_the_changes_inside_it() -> None:
    d = cd.dating([(100, 0), (900, 1)], [(101, 0), (905, 1)], window=(0, 500))
    assert (d["truth"], d["pred"], d["matched"]) == (1, 1, 1)


def test_no_matched_change_gives_nans_not_an_error() -> None:
    d = cd.dating([(100, 0)], [])
    assert d["matched"] == 0 and np.isnan(d["median"])


def test_label_changes_skip_d_and_x_and_restart_each_run() -> None:
    labels = np.array(list("HHDDAAXXAH" + "AAH"), dtype=object)
    assert cd.label_changes(labels, [(0, 10), (10, 13)]) == [(4, 1), (9, 0), (12, 0)]


def test_the_keep_mask_lays_each_donor_half_over_its_half() -> None:
    keep = cd.keep_mask([(0, 4), (4, 10)], 10, [np.array([1, 0]), np.array([0, 1, 1])])
    assert keep.astype(int).tolist() == [1, 0, 1, 0, 0, 1, 1, 0, 1, 1]


def test_the_chain_is_engine_chain_on_any_halves(monkeypatch) -> None:
    rng = np.random.default_rng(3)
    n = 400
    home = rng.uniform(0, 4, n)
    away = rng.uniform(0, 4, n)
    f = engine.Features(home, away, np.ones(n, bool), rng.uniform(0, 8, n), np.ones(n, bool))
    from tools import dead_ball

    ev = dead_ball.Evidence((), np.zeros(n, bool), np.ones(n, bool), np.zeros(n, bool))
    dead = np.zeros(n, bool)
    dead[50:60] = True
    runs = [(0, 200), (200, 400)]
    monkeypatch.setattr(engine, "halves", lambda: runs)
    expected = engine.chain(f, engine.DEFAULT, (), dead)[2]
    chain = cd.delivered(f, ev, runs, dead)
    assert cd.finish(chain.state, chain.dead).tolist() == expected.tolist()


@requires_bundle
def test_the_reference_variant_is_the_delivered_file_byte_for_byte() -> None:
    from tools import bench

    f, ev, _gt, _cut = bench.load()
    labels = cd.METHODS["engine"](f, ev)
    assert labels.tolist() == bench.METHODS["engine"](f, ev).tolist()
    table = pd.DataFrame({"frame": np.arange(len(labels)), "label": labels})
    digest = hashlib.sha256(table.to_csv(index=False, lineterminator="\n").encode()).hexdigest()
    assert digest.startswith("72c98ed4bb4a")  # DECISIONS 36: the delivered chain's SHA-256
