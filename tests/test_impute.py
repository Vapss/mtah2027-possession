"""Lane impute: gap intervals, ball and anchor features, and the three placement rules."""

from __future__ import annotations

import numpy as np
import pytest
from _bundle import requires_bundle

from tools import dead_ball, engine
from tools import impute as im

NONE = im.NONE
HOME = 0
AWAY = 1
CODES = np.array([0, 0, 1, 1], dtype=np.int8)


def ctrl_of(text: str) -> np.ndarray:
    """`h` home control, `a` away control, `.` none."""
    return np.array([{"h": HOME, "a": AWAY, ".": NONE}[c] for c in text], dtype=np.int8)


def mask(text: str) -> np.ndarray:
    """`b` ball seen, `.` ball missing."""
    return np.array([c == "b" for c in text])


# -- intervals ----------------------------------------------------------------------------------


def test_an_interval_needs_a_missing_ball_between_two_anchors() -> None:
    ctrl = ctrl_of("h..a..hh.a")
    present = mask("bb.bbbbbbb")
    ivs = im.intervals(ctrl, {}, present, [(0, 10)])
    # (0, 3) holds a missing frame; (3, 6) has the ball throughout; (7, 9) has it too.
    assert ivs == [im.Interval(0, 3, HOME, AWAY)]


def test_an_interval_that_ends_in_a_forced_restart_is_left_to_the_restart_rule() -> None:
    ctrl = ctrl_of("h....a....")
    present = mask("b....b....")
    forced = {3: AWAY}
    ivs = im.intervals(ctrl, forced, present, [(0, 10)])
    # (0, 3) ends at the restart; (3, 5) starts at it and is an ordinary interval.
    assert ivs == [im.Interval(3, 5, AWAY, AWAY)]


def test_intervals_never_cross_a_half() -> None:
    ctrl = ctrl_of("h...a.....")
    present = mask("b...b.....")
    assert im.intervals(ctrl, {}, present, [(0, 3), (3, 10)]) == []


# -- ball and anchor context --------------------------------------------------------------------


def test_ball_context_finds_the_last_and_next_seen_ball_inside_the_half() -> None:
    present = mask("b..b..b")
    last, nxt = im.ball_context(present, [(0, 5), (5, 7)])
    assert last.tolist() == [0, 0, 0, 3, 3, -1, 6]
    assert nxt.tolist() == [0, 3, 3, 3, -1, 6, 6]


def test_the_interpolated_ball_favours_the_team_standing_on_its_path() -> None:
    n = 5
    players = np.zeros((n, 4, 2))
    players[:, :, 1] = 30.0
    players[:, 0, 0], players[:, 1, 0] = 50.0, 90.0  # home near the middle of the path
    players[:, 2, 0], players[:, 3, 0] = 0.0, 100.0  # away at both ends
    ball = np.zeros((n, 2))
    ball[0] = (0.0, 30.0)
    ball[4] = (100.0, 30.0)
    present = mask("b...b")
    x = im.gap_features(players, CODES, ball, present, [(0, n)], np.array([2]))
    # Halfway along the path the ball is at x = 50: home at 0 m, away at 50 m.
    assert x[0, 0] == pytest.approx(-50.0)
    # Two frames (0.08 s) from the nearest seen ball, the near-weighted copy is barely discounted.
    assert x[0, 1] == pytest.approx(-50.0 / (1 + 2 / im.FPS))


def test_gap_features_are_zero_without_any_seen_ball() -> None:
    players = np.zeros((3, 4, 2))
    x = im.gap_features(players, CODES, np.zeros((3, 2)), mask("..."), [(0, 3)], np.arange(3))
    assert (x == 0).all()


def test_endpoint_features_weight_each_anchor_by_how_close_the_frame_is_to_it() -> None:
    team = ctrl_of("h...a")
    x = im.endpoint_features(team, [(0, 5)], np.array([1, 3]))
    # Frame 1 is a quarter of the way: home +1 * 0.75, away -1 * 0.25.
    assert x.tolist() == [[0.75, -0.25], [0.25, -0.75]]


def test_the_synthetic_mask_is_the_half_shifted_onto_itself() -> None:
    present = mask("bb..bbbb")
    out = im.shifted(present, [(0, 4), (4, 8)], 2)
    # First half: own mask AND the mask two frames later (wrapping); second half is all ball.
    assert out.tolist() == [False, False, False, False, True, True, True, True]


def test_hide_deletes_the_ball_like_the_bench_degrade() -> None:
    n = 6
    present = np.ones(n, dtype=bool)
    f = engine.Features(np.full(n, 1.0), np.full(n, 2.0), present, np.full(n, 3.0), present.copy())
    keep = mask("bb..bb")
    g = im.hide(f, keep)
    assert g.present.tolist() == keep.tolist()
    assert np.isnan(g.home_m[2:4]).all() and np.isnan(g.speed_mps[2:5]).all()
    assert g.speed_mps[5] == 3.0 and f.present.all()


# -- placement ----------------------------------------------------------------------------------


IV = im.Interval(0, 11, HOME, AWAY)
CANDIDATES = np.arange(1, 11)


def test_mid_puts_the_change_at_the_median_candidate() -> None:
    assert im.place_mid(IV, CANDIDATES) == 5


def test_change_follows_the_evidence_and_falls_back_to_the_median_without_it() -> None:
    ell = np.array([3.0] * 3 + [-3.0] * 7)  # home for three frames, then away
    assert im.place_change(IV, CANDIDATES, ell) == 4
    assert im.place_change(IV, CANDIDATES, np.zeros(10)) == 6  # 11 cuts, median of all
    # All the evidence says home: the change stays at q, the engine's answer.
    assert im.place_change(IV, CANDIDATES, np.full(10, 3.0)) == IV.q


def test_viterbi_places_the_forced_switch_where_the_evidence_turns() -> None:
    ell = np.array([3.0] * 6 + [-3.0] * 4)
    path = im.viterbi(IV, CANDIDATES, ell, switch_cost=1.0)
    assert path.tolist() == [HOME] * 6 + [AWAY] * 4


def test_viterbi_inserts_a_hidden_possession_only_when_the_evidence_pays_two_switches() -> None:
    same = im.Interval(0, 11, HOME, HOME)
    ell = np.array([2.0] * 3 + [-2.0] * 4 + [2.0] * 3)  # four frames of away evidence: 8 nats
    strong = im.viterbi(same, CANDIDATES, ell, switch_cost=3.0)
    assert strong.tolist() == [HOME] * 3 + [AWAY] * 4 + [HOME] * 3
    weak = im.viterbi(same, CANDIDATES, ell, switch_cost=5.0)  # two switches cost 10 > 8
    assert weak.tolist() == [HOME] * 10


def test_a_free_end_keeps_the_engine_answer_unless_the_gap_evidence_beats_a_switch() -> None:
    ell = np.array([0.0] * 8 + [-1.0] * 2)  # two frames of away evidence: 2 nats
    free = im.viterbi(IV, CANDIDATES, ell, switch_cost=3.0, end_cost=0.0)
    assert free.tolist() == [HOME] * 10  # the switch stays at q
    priced = im.viterbi(IV, CANDIDATES, ell, switch_cost=3.0)
    assert priced.tolist() == [HOME] * 8 + [AWAY] * 2  # same price anywhere: take the evidence


def test_rewrite_touches_only_interval_frames_and_skips_the_dead_and_the_seen_ones() -> None:
    state = ctrl_of("hhhhhhaaaa")
    state[1:6] = HOME  # the engine carries home up to the away control at 6
    present = mask("b..bb.b...")
    dead = np.zeros(10, dtype=bool)
    dead[5] = True
    ivs = [im.Interval(0, 6, HOME, AWAY)]
    out = im.rewrite(state, ivs, present, dead, im.Variant("mid"))
    # Candidates are frames 1 and 2 (3, 4 have the ball, 5 is dead): the median is 1.
    assert out.tolist() == [HOME] + [AWAY] * 9
    assert out[7:].tolist() == state[7:].tolist()


def test_rewrite_leaves_a_same_team_interval_alone_unless_it_decodes() -> None:
    state = np.full(6, HOME, dtype=np.int8)
    ivs = [im.Interval(0, 5, HOME, HOME)]
    present = mask("b....b")
    dead = np.zeros(6, dtype=bool)
    assert (im.rewrite(state, ivs, present, dead, im.Variant("mid")) == state).all()
    ell = np.array([0.0, -9.0, -9.0, -9.0, -9.0, 0.0])
    out = im.rewrite(state, ivs, present, dead, im.Variant("viterbi", 1), ell)
    assert out.tolist() == [HOME] + [AWAY] * 4 + [HOME]


def test_model_variants_refuse_to_run_without_log_odds() -> None:
    state = np.full(6, HOME, dtype=np.int8)
    ivs = [im.Interval(0, 5, HOME, AWAY)]
    with pytest.raises(ValueError):
        im.rewrite(state, ivs, mask("b....b"), np.zeros(6, bool), im.Variant("change"))


# -- the match ----------------------------------------------------------------------------------


@requires_bundle
def test_the_rewrite_is_deterministic_and_stays_inside_the_gap_intervals() -> None:
    from tools import atd, emision

    f = engine.features(atd.load("tactical"), emision.team_slots())
    ev = dead_ball.load_evidence()
    first = im.impute(f, ev, im.VARIANTS["V4"])
    second = im.impute(f, ev, im.VARIANTS["V4"])
    assert (first[1] == second[1]).all()
    runs = engine.halves()
    dead = dead_ball.dead_mask(ev, runs, "out")
    ctrl, state, _ = engine.chain(f, engine.D31, ev.restarts, dead)
    inside = np.zeros(len(state), dtype=bool)
    for iv in im.intervals(ctrl, engine.restart_controls(ev.restarts, ctrl), f.present, runs):
        inside[iv.p + 1 : iv.q] = True
    assert ((first[0] != state) <= inside).all()
