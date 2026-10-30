"""Lane decode: each decoding rule on synthetic frames, then the delivered match end to end."""

from __future__ import annotations

import math

import numpy as np
import pytest
from _bundle import requires_bundle

from tools import decoder, engine

NONE = engine.NONE
H, A = 0, 1


def ctrl_of(*values: int) -> np.ndarray:
    return np.array(values, dtype=np.int8)


# -- decode: the engine's decoder, with an optional switch filter ---------------------------------


@pytest.mark.parametrize(
    "ctrl, forced",
    [
        ([NONE, NONE, H, NONE, A, A, NONE, H], None),
        ([H, NONE, NONE, NONE, H, NONE], {2: A}),
        ([NONE, A, NONE, H, NONE, NONE, A], {5: H}),
    ],
)
def test_without_a_filter_decode_is_the_engine_decoder(ctrl, forced) -> None:
    ctrl = np.array(ctrl, dtype=np.int8)
    runs = [(0, len(ctrl))]
    expected = engine.decode(ctrl, runs, dwell=1, forced=forced)
    assert decoder.decode(ctrl, runs, forced).tolist() == expected.tolist()


def test_decode_never_carries_a_state_across_runs() -> None:
    ctrl = ctrl_of(H, NONE, NONE, NONE, A, NONE)
    assert decoder.decode(ctrl, [(0, 2), (3, 6)]).tolist() == [H, H, NONE, NONE, A, A]


def test_only_switch_frames_change_the_state_but_any_control_starts_it() -> None:
    ctrl = ctrl_of(NONE, H, NONE, A, A, NONE, A)
    switch = ctrl_of(NONE, NONE, NONE, NONE, NONE, NONE, A)  # H at 1 is contested, so is A at 3-4
    assert decoder.decode(ctrl, [(0, 7)], switch=switch).tolist() == [NONE, H, H, H, H, H, A]


def test_a_forced_restart_beats_the_switch_filter() -> None:
    ctrl = ctrl_of(H, NONE, NONE, NONE)
    switch = ctrl_of(NONE, NONE, NONE, NONE)
    assert decoder.decode(ctrl, [(0, 4)], {2: A}, switch).tolist() == [H, H, A, A]


# -- V2 uncontested ------------------------------------------------------------------------------


def test_a_control_the_other_team_can_also_reach_is_contested() -> None:
    ctrl = ctrl_of(H, H, A, A, NONE)
    home_m = np.array([0.5, 0.5, 1.0, 2.0, 0.5])
    away_m = np.array([2.0, 1.2, 0.6, 0.5, 3.0])
    # home 0.5 m with away 2.0 m: clear; away 1.2 m is within reach: contested; then away
    # controls with home 1.0 m (contested) and home 2.0 m (clear). No control stays NONE.
    got = decoder.uncontested(ctrl, home_m, away_m, radius_m=1.5)
    assert got.tolist() == [H, NONE, NONE, A, NONE]


def test_an_unknown_distance_is_not_evidence_the_other_team_is_far() -> None:
    got = decoder.uncontested(ctrl_of(H), np.array([0.5]), np.array([np.nan]), radius_m=1.5)
    assert got.tolist() == [NONE]


# -- V1 mid ---------------------------------------------------------------------------------------


def test_a_change_moves_to_the_middle_of_its_hand_over() -> None:
    # H controls last at 2, A first at 8: the hand-over is (2, 8], six frames, three back.
    ctrl = ctrl_of(H, NONE, H, NONE, NONE, NONE, NONE, NONE, A, NONE)
    state = decoder.decode(ctrl, [(0, 10)])
    assert state.tolist() == [H] * 8 + [A] * 2
    moved = decoder.redate_mid(state, ctrl, [(0, 10)])
    assert moved.tolist() == [H] * 5 + [A] * 5


def test_a_long_hand_over_moves_at_most_half_the_cap() -> None:
    ctrl = np.full(100, NONE, dtype=np.int8)
    ctrl[0], ctrl[90] = H, A
    state = decoder.decode(ctrl, [(0, 100)])
    moved = decoder.redate_mid(state, ctrl, [(0, 100)], cap=20)
    assert int(np.flatnonzero(moved == A)[0]) == 80  # 90 - 20 // 2, not 90 - 45


def test_back_to_back_controls_do_not_move() -> None:
    ctrl = ctrl_of(H, A, A)
    state = decoder.decode(ctrl, [(0, 3)])
    assert decoder.redate_mid(state, ctrl, [(0, 3)]).tolist() == [H, A, A]


def test_a_forced_change_keeps_its_frame_and_starts_the_next_hand_over() -> None:
    ctrl = ctrl_of(H, NONE, NONE, NONE, NONE, NONE, NONE, H, NONE)
    forced = {3: A}
    state = decoder.decode(ctrl, [(0, 9)], forced)
    assert state.tolist() == [H, H, H, A, A, A, A, H, H]
    # The restart at 3 is A's last "control" before H takes it back at 7: (3, 7] -> two back.
    moved = decoder.redate_mid(state, ctrl, [(0, 9)], forced)
    assert moved.tolist() == [H, H, H, A, A, H, H, H, H]


# -- V3 touch -------------------------------------------------------------------------------------


def test_a_short_rival_spell_between_the_same_team_is_undone() -> None:
    state = np.array([H] * 5 + [A] * 3 + [H] * 5, dtype=np.int8)
    out = decoder.undo_touches(state, None, [(0, 13)], min_frames=4)
    assert out.tolist() == [H] * 13


def test_a_long_enough_rival_spell_is_a_possession() -> None:
    state = np.array([H] * 5 + [A] * 4 + [H] * 5, dtype=np.int8)
    out = decoder.undo_touches(state, None, [(0, 14)], min_frames=4)
    assert out.tolist() == state.tolist()


def test_a_stoppage_beside_the_spell_protects_it() -> None:
    state = np.array([H] * 5 + [A] * 3 + [H] * 5, dtype=np.int8)
    dead = np.zeros(13, dtype=bool)
    dead[8] = True  # H D H: the spell no longer touches the second H possession
    out = decoder.undo_touches(state, dead, [(0, 13)], min_frames=4)
    assert out.tolist() == state.tolist()


def test_a_short_spell_that_ends_the_run_or_a_forced_one_is_kept() -> None:
    state = np.array([H] * 5 + [A] * 3, dtype=np.int8)
    assert decoder.undo_touches(state, None, [(0, 8)], min_frames=4).tolist() == state.tolist()
    state = np.array([H] * 5 + [A] * 3 + [H] * 5, dtype=np.int8)
    for forced in ({5: A}, {8: H}):
        out = decoder.undo_touches(state, None, [(0, 13)], forced, min_frames=4)
        assert out.tolist() == state.tolist()


def test_a_spell_between_two_of_its_own_team_is_not_a_touch() -> None:
    # H then a short A then A again is not A-B-A: nothing to undo (and no such spell exists in a
    # decoded state anyway); a short H between H and A is not one either.
    state = np.array([H] * 5 + [A] * 2 + [NONE] + [A] * 5, dtype=np.int8)
    out = decoder.undo_touches(state, None, [(0, 13)], min_frames=4)
    assert out.tolist() == state.tolist()


# -- V4 viterbi -----------------------------------------------------------------------------------


def test_soft_control_is_half_at_the_engine_thresholds_and_zero_without_a_ball() -> None:
    f = engine.Features(
        home_m=np.array([1.5, 0.0, 1.0]),
        away_m=np.array([np.inf, 9.0, 1.0]),
        present=np.array([True, True, False]),
        speed_mps=np.array([0.0, 5.0, 1.0]),
        in_pitch=np.array([True, True, False]),
    )
    home, away = decoder.soft_control(f)
    assert home[0] == pytest.approx(0.5, abs=0.01)  # on the radius, a still ball
    assert home[1] == pytest.approx(0.5, abs=0.01)  # touching it, at the speed threshold
    assert away[0] == 0.0 and home[2] == 0.0 and away[2] == 0.0


def test_the_switch_cost_is_the_prior_rate_and_needs_a_few_frames_of_control() -> None:
    expected = math.log((1 - 3.4 / 1500) / (3.4 / 1500))
    assert abs(decoder.SWITCH_COST - expected) < 1e-12
    assert 2 < decoder.SWITCH_COST / decoder.EMISSION_LOG_ODDS < 3


def test_viterbi_ignores_a_single_rival_frame_and_follows_a_sustained_one() -> None:
    beta = decoder.EMISSION_LOG_ODDS
    ctrl = np.full(20, NONE, dtype=np.int8)
    ctrl[0] = H
    llr = np.zeros(20)
    llr[0] = llr[8] = beta
    llr[5] = -beta  # one rival frame between two of ours: cheaper to stay than to pay two switches
    llr[12:16] = -beta  # four rival frames, nothing after: one switch pays off
    state = decoder.viterbi(llr, ctrl, [(0, 20)], cost=decoder.SWITCH_COST)
    assert state.tolist() == [H] * 12 + [A] * 8


def test_viterbi_dates_a_change_after_a_silent_gap_to_the_new_evidence() -> None:
    ctrl = np.full(12, NONE, dtype=np.int8)
    ctrl[0] = H
    llr = np.zeros(12)
    llr[0:2] = 5.0
    llr[8:12] = -5.0  # frames 2..7 carry no evidence: the change is dated to 8, not 2
    assert decoder.viterbi(llr, ctrl, [(0, 12)], cost=3.0).tolist() == [H] * 8 + [A] * 4


def test_viterbi_starts_at_the_first_control_and_obeys_a_forced_frame() -> None:
    ctrl = np.array([NONE, NONE, A, NONE, NONE, NONE], dtype=np.int8)
    llr = np.array([0.0, 0.0, -2.0, -2.0, -2.0, -2.0])
    state = decoder.viterbi(llr, ctrl, [(0, 6)], forced={4: H}, cost=50.0)
    # NONE before the first control; A after it; the restart at 4 hands it to H despite the cost.
    assert state.tolist() == [NONE, NONE, A, A, H, H]


# -- the pre-registered rule ---------------------------------------------------------------------


def _row(**overrides) -> dict:
    row = {
        "spell_f1": 0.45,
        "wins_a": 0,
        "wins_b": 0,
        "jackknife_flips": False,
        "bench_mean": 0.35,
        "bench_low": 0.28,
        "match_rate": 3.6,
        "empty_blocks": 0,
        "block_rates": [3.0, 3.0],
        "st_match": 0.73,
    }
    return {**row, **overrides}


def test_each_gate_fails_on_its_own_condition() -> None:
    measured = {
        "engine": _row(),
        "ok": _row(),
        "loses_a_possession": _row(spell_f1=0.50, wins_a=1),
        "unstable": _row(spell_f1=0.50, jackknife_flips=True),
        "worse_on_the_bench": _row(bench_mean=0.34),
        "worse_low_ball": _row(bench_low=0.26),
        "too_few_possessions": _row(match_rate=2.5),
        "halves_a_block": _row(block_rates=[3.0, 1.4]),
        "disagrees_with_tagging": _row(st_match=0.715),
    }
    passed = decoder.gates(measured)
    assert all(passed["ok"].values())
    assert not passed["loses_a_possession"]["G1"] and not passed["unstable"]["G1"]
    assert not passed["worse_on_the_bench"]["G2"] and not passed["worse_low_ball"]["G2"]
    for name in ("too_few_possessions", "halves_a_block", "disagrees_with_tagging"):
        assert not passed[name]["G3"]


def test_selection_follows_the_prior_order_not_the_score() -> None:
    ok, bad = {"G1": True, "G2": True, "G3": True}, {"G1": False, "G2": True, "G3": True}
    every = dict.fromkeys(decoder.VARIANTS, bad)
    assert decoder.select(every) is None
    assert decoder.select({**every, "viterbi": ok, "touch": ok}) == "touch"
    # The stack needs two of its parts to pass on their own.
    assert decoder.select({**every, decoder.STACK: ok, "mid": ok}) == "mid"
    assert decoder.select({**every, decoder.STACK: ok, "mid": ok, "touch": ok}) == decoder.STACK


# -- the delivered match ---------------------------------------------------------------------------


@requires_bundle
def test_on_the_match_the_baseline_is_the_delivered_engine_and_no_variant_touches_d() -> None:
    from tools import bench, dead_ball, engine

    f, ev, _gt, _cut = bench.load()
    # The lane decodes with the tagged D only; the delivered D adds the players' stoppages
    # (DECISIONS 36), so the comparison is with the delivered chain under the lane's D.
    tagged = dead_ball.dead_mask(ev, engine.halves(), "out")
    delivered = engine.chain(f, engine.DEFAULT, ev.restarts, tagged)[2]
    # The lane's baseline is the engine it measured against (DECISIONS 29-32, `engine.D31`); its V2
    # is what DECISIONS 34 integrated, so it must equal the delivered chain exactly.
    dead = dead_ball.dead_mask(ev, engine.halves(), "out")
    before = engine.chain(f, engine.D31, ev.restarts, dead)[2]
    assert (decoder.METHODS[decoder.BASELINE](f, ev) == before).all()
    # Equal on BAR-ATH; by design they differ when a contested rival control falls inside a
    # restart window or opens a half after a restart (DECISIONS 35), which this match never has.
    assert (decoder.METHODS["uncontested"](f, ev) == delivered).all()
    for method in decoder.METHODS.values():
        labels = method(f, ev)
        assert ((labels == "D") == (delivered == "D")).all()
        assert (method(f, ev) == labels).all()  # deterministic


# -- section 11: V6 and its rule against V2 --------------------------------------------------------


def test_v6_ignores_the_duel_and_dates_the_clean_change_to_its_hand_over() -> None:
    # H controls at 0 and 2; A wins a duel at 4 (H still within reach), then controls cleanly at 8.
    ctrl = ctrl_of(H, NONE, H, NONE, A, NONE, NONE, NONE, A, NONE)
    home_m = np.array([0.5, 9, 0.5, 9, 1.0, 9, 9, 9, 4.0, 9])
    away_m = np.array([3.0, 9, 3.0, 9, 0.5, 9, 9, 9, 0.5, 9])
    switch = decoder.uncontested(ctrl, home_m, away_m, radius_m=1.5)
    state = decoder.decode(ctrl, [(0, 10)], switch=switch)
    assert state.tolist() == [H] * 8 + [A] * 2  # the duel at 4 does not change possession
    # H's last control is 2, so the hand-over is (2, 8]: the change moves three frames back.
    moved = decoder.redate_mid(state, ctrl, [(0, 10)])
    assert moved.tolist() == [H] * 5 + [A] * 5


def test_v6_replaces_v2_only_through_every_gate_and_a_low_ball_bench_that_does_not_drop() -> None:
    v2 = decoder.FOLLOW_UP_BASELINE
    v6 = decoder.FOLLOW_UP
    assert decoder.adopt_follow_up({v2: _row(), v6: _row(spell_f1=0.46)})
    # G2 tolerates -0.01 on the low-ball mean; the follow-up rule does not.
    assert not decoder.adopt_follow_up({v2: _row(), v6: _row(bench_low=0.275)})
    assert not decoder.adopt_follow_up({v2: _row(), v6: _row(spell_f1=0.44)})


def test_runs_and_episodes_join_only_short_breaks() -> None:
    mask = np.array([1, 1, 0, 1, 0, 0, 0, 1], dtype=bool)
    assert decoder._true_runs(mask, 10) == [(10, 12), (13, 14), (17, 18)]
    assert decoder._episodes(mask, 0, join=1) == [(0, 4), (7, 8)]
