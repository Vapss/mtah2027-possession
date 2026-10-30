"""Lane dating: each rule on synthetic frames, then the delivered match end to end."""

from __future__ import annotations

import numpy as np
import pytest
from _bundle import requires_bundle

from tools import dating, engine

NONE = engine.NONE
H, A = 0, 1
FAR = 9.0  # metres: out of reach


def team_of(*values: int) -> np.ndarray:
    return np.array(values, dtype=np.int8)


def features(home_m, away_m, speed_mps, in_pitch=None) -> engine.Features:
    home_m, away_m = np.asarray(home_m, float), np.asarray(away_m, float)
    present = np.isfinite(home_m)
    inside = present if in_pitch is None else np.asarray(in_pitch, bool)
    return engine.Features(home_m, away_m, present, np.asarray(speed_mps, float), inside)


# -- touch: the control without its speed test ---------------------------------------------------


def test_a_touch_ignores_the_speed_but_keeps_the_reach_the_pitch_and_the_tie() -> None:
    f = features(
        home_m=[1.0, 1.0, 1.0, 1.0, FAR, np.nan],
        away_m=[FAR, FAR, 1.0, FAR, 1.4, np.nan],
        speed_mps=[2.0, 25.0, 2.0, np.nan, 30.0, np.nan],
        in_pitch=[True, True, True, True, True, False],
    )
    assert engine.control(f).tolist() == [H, NONE, NONE, NONE, NONE, NONE]
    assert dating.touch(f).tolist() == [H, H, NONE, H, A, NONE]


def test_every_control_frame_is_a_touch_frame() -> None:
    rng = np.random.default_rng(0)
    n = 400
    f = features(rng.uniform(0, 4, n), rng.uniform(0, 4, n), rng.uniform(0, 12, n))
    ctrl, near = engine.control(f), dating.touch(f)
    assert np.all(near[ctrl != NONE] == ctrl[ctrl != NONE])


# -- handovers: where each natural change's hand-over begins -------------------------------------


def test_the_hand_over_begins_after_the_old_teams_last_control_contested_or_not() -> None:
    ctrl = team_of(H, NONE, H, NONE, A, NONE, A)
    state = team_of(H, H, H, H, H, H, A)  # the A at 4 was a duel, the change is at 6
    (h,) = dating.handovers(state, ctrl, [(0, 7)])
    assert (h.frame, h.old, h.new, h.after) == (6, H, A, 2)


def test_a_forced_change_has_no_hand_over_and_a_forced_frame_or_a_stoppage_ends_one() -> None:
    ctrl = team_of(H, NONE, NONE, NONE, NONE, A, NONE, NONE, NONE, H)
    state = team_of(H, H, H, A, A, A, A, A, A, H)
    # 3 is a restart for A; the change back to H at 9 begins after the stoppage at 7.
    dead = np.zeros(10, dtype=bool)
    dead[7] = True
    changes = dating.handovers(state, ctrl, [(0, 10)], forced={3: A}, dead=dead)
    assert [(h.frame, h.after) for h in changes] == [(9, 7)]
    # Without the stoppage, A's last control at 5 is where it begins.
    changes = dating.handovers(state, ctrl, [(0, 10)], forced={3: A})
    assert [(h.frame, h.after) for h in changes] == [(9, 5)]


def test_a_restart_that_gives_the_old_team_the_ball_ends_the_hand_over() -> None:
    ctrl = team_of(H, NONE, NONE, NONE, A)
    state = team_of(H, H, H, H, A)
    (h,) = dating.handovers(state, ctrl, [(0, 5)], forced={2: H})
    assert h.after == 2


def test_hand_overs_never_span_two_runs() -> None:
    ctrl = team_of(H, NONE, A, NONE, NONE, A)
    state = team_of(H, H, NONE, NONE, A, A)
    assert dating.handovers(state, ctrl, [(0, 2), (3, 6)]) == []


# -- redate ---------------------------------------------------------------------------------------


def test_v_a_dates_the_change_to_the_new_teams_first_control_after_the_old_teams_last() -> None:
    ctrl = team_of(H, H, NONE, A, A, NONE, A, A)
    switch = team_of(H, H, NONE, NONE, NONE, NONE, A, A)  # A is contested at 3-4
    state = engine.decode(ctrl, [(0, 8)], 1, None, switch)
    assert state.tolist() == [H, H, H, H, H, H, A, A]
    changes = dating.handovers(state, ctrl, [(0, 8)])
    assert dating.redate(state, changes, ctrl).tolist() == [H, H, H, A, A, A, A, A]


def test_v_b_dates_it_to_the_new_teams_first_touch_at_any_speed() -> None:
    ctrl = team_of(H, NONE, NONE, NONE, A)
    near = team_of(H, NONE, A, NONE, A)  # A within reach of a fast ball at 2
    state = team_of(H, H, H, H, A)
    changes = dating.handovers(state, ctrl, [(0, 5)])
    assert dating.redate(state, changes, ctrl).tolist() == [H, H, H, H, A]
    assert dating.redate(state, changes, near).tolist() == [H, H, A, A, A]


def test_an_old_team_touch_after_its_last_control_is_not_an_anchor() -> None:
    ctrl = team_of(H, NONE, NONE, NONE, A)
    near = team_of(H, H, NONE, A, A)
    state = team_of(H, H, H, H, A)
    changes = dating.handovers(state, ctrl, [(0, 5)])
    assert dating.redate(state, changes, near).tolist() == [H, H, H, A, A]


def test_a_redated_change_never_crosses_a_stoppage() -> None:
    ctrl = team_of(H, NONE, NONE, NONE, NONE, A)
    near = team_of(H, A, NONE, NONE, NONE, A)  # an A touch before the stoppage at 2-3
    state = team_of(H, H, H, H, H, A)
    dead = np.array([False, False, True, True, False, False])
    changes = dating.handovers(state, ctrl, [(0, 6)], dead=dead)
    assert dating.redate(state, changes, near).tolist() == [H, H, H, H, H, A]


def test_accept_keeps_the_delivered_date_where_the_anchor_is_refused() -> None:
    ctrl = team_of(H, NONE, NONE, A)
    near = team_of(H, A, NONE, A)
    state = team_of(H, H, H, A)
    changes = dating.handovers(state, ctrl, [(0, 4)])
    refuse = np.array([True, False, True, True])
    assert dating.redate(state, changes, near, refuse).tolist() == [H, H, H, A]
    assert dating.redate(state, changes, near, ~refuse).tolist() == [H, A, A, A]


@pytest.mark.parametrize("seed", range(5))
def test_redating_changes_when_never_whether(seed: int) -> None:
    """Same changes, order and teams; only frames inside a hand-over move, to the new team."""
    rng = np.random.default_rng(seed)
    n = 3000
    f = features(rng.uniform(0, 3, n), rng.uniform(0, 3, n), rng.uniform(0, 15, n))
    ctrl = engine.control(f)
    switch = engine.uncontested(ctrl, f, engine.DEFAULT.radius_m)
    runs = [(0, 1400), (1500, n)]
    forced = {300: H, 2000: A}
    state = engine.decode(ctrl, runs, 1, forced, switch)
    dead = rng.uniform(size=n) < 0.01
    changes = dating.handovers(state, ctrl, runs, forced, dead)
    out = dating.redate(state, changes, dating.touch(f))

    def sequence(s: np.ndarray) -> list[int]:
        return [int(t) for i, t in enumerate(s) if t != NONE and (i == 0 or s[i - 1] != t)]

    for start, stop in runs:
        assert sequence(out[start:stop]) == sequence(state[start:stop])
    inside = np.zeros(n, dtype=bool)
    for h in changes:
        inside[h.after + 1 : h.frame] = True
        assert not dead[h.after + 1 : h.frame].any()
    moved = out != state
    assert not (moved & ~inside).any()
    assert all(out[forced_frame] == state[forced_frame] for forced_frame in forced)
    assert len(changes) > 0 and moved.any()


# -- the per-possession IoU sign test -------------------------------------------------------------


def codes(text: str) -> np.ndarray:
    from tools.bench import pm

    return pm.label_codes(list(text))


def test_the_iou_sign_test_counts_each_true_possession_once() -> None:
    gt = codes("HHHHHHHHHHAAAAAAAAAADDHHHH")
    a = codes("HHHHHHHHHHHHHHAAAAAADDHHHH")  # the change is 4 frames late
    b = codes("HHHHHHHHHHHAAAAAAAAADDHHHH")  # 1 frame late
    result = dating.iou_sign_test(gt, a, b)
    assert (result["improved"], result["worsened"], result["ties"]) == (2, 0, 1)
    assert result["p"] == pytest.approx(0.5)
    assert result["lost_at_half"] == 0
    assert dating.iou_sign_test(gt, b, a)["lost_at_half"] == 0


def test_the_sign_test_p_is_exact_and_two_sided() -> None:
    gt = codes(("H" * 10 + "A" * 10) * 3 + "H" * 10)
    late = codes("H" * 13 + "A" * 10 + "H" * 10 + "A" * 10 + "H" * 10 + "A" * 10 + "H" * 7)
    result = dating.iou_sign_test(gt, late, gt)
    assert result["improved"] == 7 and result["worsened"] == 0
    assert result["p"] == pytest.approx(2 / 2**7)


def test_start_offsets_are_positive_when_late() -> None:
    gt = codes("H" * 25 + "A" * 50)
    late = codes("H" * 50 + "A" * 25)
    assert dating.start_offsets(gt, late) == [0.0, 1.0]


# -- the delivered match ---------------------------------------------------------------------------


@requires_bundle
def test_on_the_match_the_negative_control_is_the_delivered_chain_and_d_never_moves() -> None:
    from tools import bench

    f, ev, _gt, _cut = bench.load()
    delivered = bench.METHODS["engine"](f, ev)
    none = dating.METHODS["none"](f, ev)
    assert none.tolist() == delivered.tolist()
    for name in ("first", "touch", dating.DIAGNOSTIC):
        labels = dating.METHODS[name](f, ev)
        assert ((labels == "D") == (delivered == "D")).all()
        assert ((labels == "X") == (delivered == "X")).all()
