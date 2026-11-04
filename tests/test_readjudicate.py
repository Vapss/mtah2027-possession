"""DECISIONS 45, test B: the verdict rule on synthetic evidence (no data needed)."""

from __future__ import annotations

import numpy as np

from tools import dead_ball, engine, readjudicate


def _evidence(restarts) -> dead_ball.Evidence:
    n = engine.halves()[-1][1]
    out = np.zeros(n, dtype=bool)
    out[19900:19910] = True  # 10 frames out (< 1 s)
    out[30000:30050] = True  # 50 frames out (2 s)
    return dead_ball.Evidence(tuple(restarts), out, ~out, np.zeros(n, dtype=bool))


def test_short_outs_counts_each_stoppage_by_episode_length_and_restart_kind() -> None:
    ev = _evidence(
        [
            dead_ball.Restart(20100, 19975, "Throw-in", 0),
            dead_ball.Restart(30300, 30175, "Free Kick", 1),
        ]
    )
    b = readjudicate.short_outs(ev)
    assert (b["short_out_of_play"], b["short_other"]) == (1, 0)
    assert (b["long_out_of_play"], b["long_other"]) == (0, 1)
    assert b["correction_2_stays_reverted"]


def test_short_outs_adopts_correction_2_when_short_episodes_end_in_other_restarts() -> None:
    ev = _evidence([dead_ball.Restart(20100, 19975, "Free Kick", 0)])
    b = readjudicate.short_outs(ev)
    assert b["short_other"] == 1 and not b["correction_2_stays_reverted"]
