"""#6: the engine's control rule and its decoder, on synthetic frames and on the delivered match."""

from __future__ import annotations

import numpy as np
import pytest
from _bundle import requires_bundle

from tools import engine

NONE = engine.NONE


def feats(home, away, speed, present=None) -> engine.Features:
    home = np.asarray(home, dtype=float)
    present = np.ones(len(home), dtype=bool) if present is None else np.asarray(present)
    return engine.Features(home, np.asarray(away, dtype=float), present, np.asarray(speed, float))


def test_control_needs_a_close_player_and_a_slow_ball() -> None:
    f = feats(home=[1.0, 1.0, 3.0, 1.0], away=[4.0, 4.0, 4.0, 0.5], speed=[2.0, 9.0, 2.0, 2.0])
    # slow+close home; fast ball; nobody close; away closer
    assert engine.control(f).tolist() == [0, NONE, NONE, 1]


def test_a_tie_and_an_unknown_speed_are_not_control() -> None:
    f = feats(home=[1.0, 1.0], away=[1.0, 3.0], speed=[2.0, np.nan])
    assert engine.control(f).tolist() == [NONE, NONE]


def test_an_unobserved_ball_is_not_control() -> None:
    f = feats(home=[1.0], away=[3.0], speed=[1.0], present=[False])
    assert engine.control(f).tolist() == [NONE]


def test_the_state_is_carried_between_controls_and_none_before_the_first() -> None:
    ctrl = np.array([NONE, NONE, 0, NONE, NONE, 1, NONE], dtype=np.int8)
    assert engine.decode(ctrl, [(0, 7)]).tolist() == [NONE, NONE, 0, 0, 0, 1, 1]


def test_a_change_needs_dwell_frames_and_is_dated_to_the_first() -> None:
    ctrl = np.array([0, NONE, 1, 1, NONE, 1, 1, 1, NONE], dtype=np.int8)
    # Two rival frames are not enough at dwell 3; three in a row are, and the change starts at 5.
    assert engine.decode(ctrl, [(0, 9)], dwell=3).tolist() == [0, 0, 0, 0, 0, 1, 1, 1, 1]


def test_the_state_never_crosses_a_run_boundary() -> None:
    ctrl = np.array([0, NONE, NONE, NONE], dtype=np.int8)
    assert engine.decode(ctrl, [(0, 2), (2, 4)]).tolist() == [0, 0, NONE, NONE]


def test_dwell_must_be_positive() -> None:
    with pytest.raises(ValueError, match="at least 1"):
        engine.decode(np.zeros(3, dtype=np.int8), [(0, 3)], dwell=0)


def test_labels_are_h_a_and_x() -> None:
    assert engine.labels(np.array([0, 1, NONE], dtype=np.int8)).tolist() == ["H", "A", "X"]


@requires_bundle
def test_the_default_engine_reproduces_its_public_score() -> None:
    """DECISIONS 29 anchors: spellF1 0,4390 on the public slice, 87,2% team accuracy on live."""
    import sys

    import pandas as pd

    sys.path.insert(0, str(engine.REPO_ROOT / "evaluation"))
    import possession_metrics as pm

    table, _summary = engine.run()
    gt = pm.label_codes(
        pd.read_csv(
            engine.REPO_ROOT / "evaluation" / "gt" / "BAR-ATH_possession_gt_public.csv"
        ).label
    )
    codes = pm.label_codes(table.label.tolist())
    assert round(float(pm.evaluate(gt, codes)["spell_f1_mean"]), 4) == 0.4390
    live = np.isin(gt, [pm.H, pm.A])
    filled = pm.fill_abstentions(codes, pm.valid_runs(gt))
    assert round(float(np.mean(filled[live] == gt[live])), 3) == 0.872
