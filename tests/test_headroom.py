"""The headroom audit's oracles and error split, on hand-made labels (no match data)."""

from __future__ import annotations

import numpy as np

from tools import dead_ball, headroom

FPS = headroom.FPS


def _arr(*letters: str) -> np.ndarray:
    return np.array(list(letters), dtype=object)


def test_each_oracle_takes_exactly_one_component_from_the_truth() -> None:
    carried = _arr("H", "H", "H", "A", "A")
    labels = _arr("H", "D", "H", "A", "D")
    truth = _arr("H", "H", "D", "H", "D")
    o = headroom.oracles(carried, labels, truth)
    assert o["oracle D"].tolist() == ["H", "H", "D", "A", "D"]
    assert o["oracle D: only remove our false D"].tolist() == ["H", "H", "H", "A", "D"]
    assert o["oracle D: only add the D we miss"].tolist() == ["H", "D", "D", "A", "D"]
    # Our D stays; the truth's team only where both call the frame live.
    assert o["oracle team on the live frames"].tolist() == ["H", "D", "H", "H", "D"]
    # An abstention is left to the scorer's fill, never given the truth.
    o = headroom.oracles(_arr("H", "H"), _arr("X", "H"), _arr("A", "H"))
    assert o["oracle team on the live frames"].tolist() == ["X", "H"]


def test_the_scorer_fill_carries_forward_and_back_fills_the_head() -> None:
    assert headroom.scorer_filled(_arr("X", "X", "A", "X", "H", "X")).tolist() == list("AAAAHH")
    assert headroom.scorer_filled(_arr("X", "X")).tolist() == ["X", "X"]


def test_team_error_bands_wrong_frames_by_distance_to_a_true_change() -> None:
    n = 20 * FPS
    truth = np.full(n, "H", dtype=object)
    truth[:FPS] = "A"  # the first second is the other team's
    truth[10 * FPS :] = "A"  # one change at 10 s
    labels = truth.copy()
    labels[: 2 * FPS] = "X"  # nothing known for the first 2 s: back-filled with H
    labels[10 * FPS : 11 * FPS + 12] = "H"  # 1,5 s late on the change
    labels[15 * FPS] = "D"  # a D frame is never a wrong team
    t = headroom.team_error(labels, truth, (0, n))
    assert t["live"] == n - 1
    assert t["unlabelled"] == 2 * FPS
    assert t["leading_unlabelled_s"] == 2.0
    assert t["leading_wrong_after_fill"] == FPS  # only the A second is wrong after the fill
    assert t["wrong"] == FPS + FPS + 12
    bands = t["wrong_by_distance_to_a_change"]
    # Frame 0 is exactly 1 s before the A-to-H change at 1 s, so it is in the 1-2 s band.
    assert bands["0-1 s"] == 2 * FPS - 1 and bands["1-2 s"] == 12 + 1


def test_teamless_restarts_are_counted_by_kind() -> None:
    restarts = [
        dead_ball.Restart(10, 0, "Throw-in", None),
        dead_ball.Restart(20, 5, "Throw-in", None),
        dead_ball.Restart(30, 15, "Corner Kick", 1),
        dead_ball.Restart(40, 25, "Kick Off (Start)", None),
    ]
    assert headroom.teamless_restarts(restarts) == {"Kick Off (Start)": 1, "Throw-in": 2}
