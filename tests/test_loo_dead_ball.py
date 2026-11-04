"""Lane loo-dead-v3: the leave-one-match-out rule, pinned on synthetic match statistics.

No DFL file is read here: `MatchStats` is built by hand, so the selection rule, the fold
rotation and the decision arithmetic are testable in CI without the external corpus.
"""

from __future__ import annotations

import numpy as np

from tools import loo_dead_ball as loo

FPS = loo.dead_ball_v3.FPS


def row(name: str, cands: dict[str, tuple[float, float, float]]) -> loo.MatchStats:
    """One match: per candidate, `(precision, f1, start_abs_median_s)` turned into counts."""
    counts, starts = {}, {}
    for candidate, (precision, f1, start) in cands.items():
        said, graded = 400, 1000
        hits = round(precision * said)
        recall = max(1e-9, 2 * f1 * precision / max(1e-9, precision + f1) if f1 else precision)
        true = max(1, round(hits / recall))
        counts[candidate] = {"hits": hits, "said": said, "true": true, "graded": graded}
        starts[candidate] = np.full(1, start * FPS)
    return loo.MatchStats(name, counts, starts)


def test_the_precision_floor_excludes_a_candidate_that_is_more_accurate_on_edges() -> None:
    rows = [row("m1", {"a": (0.89, 0.90, 0.2), "b": (0.95, 0.80, 1.0)})]
    assert loo.select(rows, ["a", "b"]) == "b"


def test_the_smallest_start_error_wins_among_eligible_candidates() -> None:
    rows = [row("m1", {"a": (0.95, 0.90, 1.0), "b": (0.95, 0.70, 0.4)})]
    assert loo.select(rows, ["a", "b"]) == "b"


def test_a_tie_on_the_start_error_goes_to_the_higher_f1_then_the_shorter_cap() -> None:
    rows = [
        row(
            "m1",
            {
                "onset<3.25/40s": (0.95, 0.80, 0.5),
                "onset<3.25/20s": (0.95, 0.70, 0.5),
                "onset<3.5/10s": (0.95, 0.80, 0.5),
            },
        )
    ]
    assert loo.select(rows, ["onset<3.25/40s", "onset<3.25/20s"]) == "onset<3.25/40s"
    assert loo.select(rows, ["onset<3.25/40s", "onset<3.5/10s"]) == "onset<3.5/10s"


def test_the_selection_is_deterministic() -> None:
    rows = [row("m1", {"a": (0.95, 0.80, 0.5), "b": (0.95, 0.80, 0.5)})]
    assert loo.select(rows, ["a", "b"]) == loo.select(rows, ["a", "b"])


def test_every_match_is_held_out_exactly_once() -> None:
    matches = ["m1", "m2", "m3"]
    folds = loo.folds(matches)
    assert [held for _, held in folds] == matches
    for train, held in folds:
        assert held not in train
        assert sorted(train) == sorted(m for m in matches if m != held)


def test_the_sign_test_is_two_sided_and_never_below_the_seven_fold_floor() -> None:
    assert loo._sign_p(7, 7) == 0.015625
    assert loo._sign_p(6, 7) == 0.125
    assert loo._sign_p(0, 7) == 0.015625
    assert loo._sign_p(4, 7) == 1.0


def test_a_fold_that_loses_is_reported_as_a_loss() -> None:
    """The report never filters: a losing fold has to be visible in the table."""
    result = {
        "matches": ["m1"],
        "folds": [
            {
                "held_out": "m1",
                "chosen": "onset<3.25/40s",
                "precision": 0.95,
                "recall": 0.80,
                "f1": 0.70,
                "start_abs_median_s": 0.5,
                "w1_precision": 0.96,
                "w1_recall": 0.70,
                "w1_f1": 0.80,
                "w1_start_abs_median_s": 5.0,
                "f1_delta": -0.10,
                "start_delta_s": -4.5,
                "wins": False,
            }
        ],
        "full_fit": "onset<3.25/40s",
        "stability": {"onset<3.25/40s": 1},
        "wins": 0,
        "sign_p": 1.0,
        "median_f1_delta": -0.10,
        "median_start_gain_s": 4.5,
    }
    text = loo.report(result)
    assert "m1" in text
    assert "-0.1000" in text
    assert "0/1" in text
