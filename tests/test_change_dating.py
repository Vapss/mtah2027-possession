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


@requires_bundle
def test_on_the_match_no_variant_moves_a_d_or_an_x_frame() -> None:
    from tools import bench

    f, ev, _gt, _cut = bench.load()
    reference = cd.METHODS["engine"](f, ev)
    for name in cd.VARIANTS:
        labels = cd.METHODS[name](f, ev)
        assert ((labels == "D") == (reference == "D")).all()
        assert ((labels == "X") == (reference == "X")).all()


# -- the variants (pre-registered) -------------------------------------------------------------


def _features(home: list[float], away: list[float], speed: list[float]) -> engine.Features:
    n = len(home)
    return engine.Features(
        np.array(home, float),
        np.array(away, float),
        np.ones(n, bool),
        np.array(speed, float),
        np.ones(n, bool),
    )


def test_the_hand_over_begins_after_the_old_teams_last_control_or_stoppage() -> None:
    state = np.array([0, 0, 0, 0, 0, 1, 1], dtype=np.int8)
    ctrl = np.array([0, 0, N, N, N, 1, 1], dtype=np.int8)
    (h,) = cd.handovers(state, ctrl, [(0, 7)], {}, np.zeros(7, bool))
    assert (h.frame, h.old, h.new, h.after) == (5, 0, 1, 1)
    dead = np.zeros(7, bool)
    dead[3] = True
    (h,) = cd.handovers(state, ctrl, [(0, 7)], {}, dead)
    assert h.after == 3  # a re-dated change never crosses a stoppage
    assert cd.handovers(state, ctrl, [(0, 7)], {5: 1}, np.zeros(7, bool)) == []  # forced


def test_first_dates_to_the_new_teams_first_control_in_the_hand_over() -> None:
    h = cd.Handover(frame=8, old=0, new=1, after=2)
    evidence = np.array([0, 1, 0, N, 1, N, 1, N, 1], dtype=np.int8)
    assert cd.first_anchor(h, evidence) == 4  # the 1 at frame 1 is before the hand-over
    assert cd.first_anchor(h, np.full(9, N, dtype=np.int8)) == 8


def test_reception_is_the_new_teams_closest_approach_in_the_lookback() -> None:
    #           0    1    2    3    4    5    6    7    8
    home = [9.0, 9.0, 9.0, 9.0, 9.0, 9.0, 9.0, 9.0, 9.0]
    away = [0.1, 9.0, 1.2, 0.4, 0.4, 2.0, 1.0, 0.6, 0.5]
    f = _features(home, away, [1.0] * 9)
    h = cd.Handover(frame=8, old=0, new=1, after=1)
    assert cd.reception_anchor(h, f, lookback=100) == 3  # the earliest of the two 0.4 m frames
    assert cd.reception_anchor(h, f, lookback=2) == 8  # only 6, 7, 8 count: 0.5 m at 8
    assert cd.reception_anchor(h, f, lookback=4) == 4  # from 4 on: the later 0.4 m frame


def test_reception_ignores_frames_where_the_old_team_is_as_close() -> None:
    f = _features([0.2, 0.2, 9.0], [0.2, 0.1, 0.9], [1.0] * 3)
    h = cd.Handover(frame=2, old=0, new=1, after=-1)
    assert cd.reception_anchor(h, f, lookback=10) == 1  # frame 0 is a tie, not the new team's


def test_redate_moves_only_inside_the_hand_over() -> None:
    state = np.array([0, 0, 0, 0, 1, 1], dtype=np.int8)
    h = cd.Handover(frame=4, old=0, new=1, after=1)
    assert cd.redate(state, [h], [2]).tolist() == [0, 0, 1, 1, 1, 1]
    with pytest.raises(ValueError, match="outside the hand-over"):
        cd.redate(state, [h], [1])


@pytest.mark.parametrize("seed", [0, 1, 2])
def test_every_variant_keeps_the_changes_number_order_and_teams(seed: int) -> None:
    from tools import dead_ball

    rng = np.random.default_rng(seed)
    n = 3000
    f = engine.Features(
        rng.uniform(0, 3, n),
        rng.uniform(0, 3, n),
        np.ones(n, bool),
        rng.uniform(0, 12, n),
        np.ones(n, bool),
    )
    ev = dead_ball.Evidence((), np.zeros(n, bool), np.ones(n, bool), np.zeros(n, bool))
    dead = np.zeros(n, bool)
    dead[1000:1100] = True
    runs = [(0, 1500), (1500, 3000)]
    ref = cd.variant_state("engine", f, ev, runs, dead)
    base = cd.state_changes(ref.state, runs)
    for name in cd.VARIANTS:
        chain = cd.variant_state(name, f, ev, runs, dead)
        moved = cd.state_changes(chain.state, runs)
        assert [t for _, t in moved] == [t for _, t in base]
        assert all(m <= b for (m, _), (b, _) in zip(moved, base))  # only ever earlier
        assert ((chain.state == N) == (ref.state == N)).all()
        assert (cd.finish(chain.state, dead) == "D").sum() == dead.sum()


def test_an_unknown_variant_is_refused() -> None:
    with pytest.raises(ValueError, match="unknown variant"):
        cd.variant_state("touch", *_tiny())


def _tiny():
    from tools import dead_ball

    f = _features([1.0, 1.0], [2.0, 2.0], [1.0, 1.0])
    ev = dead_ball.Evidence((), np.zeros(2, bool), np.ones(2, bool), np.zeros(2, bool))
    return f, ev, [(0, 2)], np.zeros(2, bool)


def test_the_selection_follows_the_prior_order_never_the_numbers() -> None:
    ok, ko = cd.Gate("g", True, ""), cd.Gate("g", False, "")
    assert cd.select({"first": [ok, ko], "reception": [ok], "relaxed": [ok]}) == "reception"
    assert cd.select({"first": [ko], "reception": [ko], "relaxed": [ko]}) is None


# -- DFL events --------------------------------------------------------------------------------


DFL_XML = """<?xml version="1.0" encoding="UTF-8" standalone="yes" ?>
<PutDataRequest>
<Event MatchId="M" EventTime="2023-05-27T15:30:12.000+02:00" EventId="1">
 <KickOff TeamLeft="H" TeamRight="A" GameSection="firstHalf">
  <Play Player="p1" Team="H" Evaluation="successfullyCompleted"><Pass/></Play>
 </KickOff>
</Event>
<Event MatchId="M" EventTime="2023-05-27T15:30:14.000+02:00" EventId="2">
 <Play Player="p2" Team="H"><Pass/></Play>
</Event>
<Event EventId="3" CalculatedTimestamp="2023-05-27T15:30:15.000+02:00"
 EventTime="2023-05-27T15:30:16.000+02:00" CalculatedFrame="10075">
 <ShotAtGoal Team="A" Player="p3"><ShotWide/></ShotAtGoal>
</Event>
<Event MatchId="M" EventTime="2023-05-27T15:30:17.000+02:00" EventId="4">
 <Delete/>
</Event>
<Event MatchId="M" EventTime="2023-05-27T15:30:18.000+02:00" EventId="5">
 <TacklingGame WinnerTeam="A" LoserTeam="H"/>
</Event>
</PutDataRequest>
"""


def test_dfl_events_keep_asserting_events_and_the_clock_pairs(tmp_path) -> None:
    path = tmp_path / "events.xml"
    path.write_text(DFL_XML, encoding="utf-8")
    events, clock = cd.dfl_events(path)
    assert [(e.kind, e.team, e.set_piece) for e in events] == [
        ("KickOff", "H", True),
        ("Play", "H", False),
        ("ShotAtGoal", "A", False),
    ]
    assert events[1].time - events[0].time == pytest.approx(2.0)
    ((frame, stamp),) = clock
    assert frame == 10075 and stamp == pytest.approx(events[2].time - 1.0)


def test_the_dfl_shift_brings_the_acting_team_to_the_ball() -> None:
    n = 400
    home = np.full(n, 9.0)
    away = np.full(n, 9.0)
    home[[100, 200, 300]] = 0.2  # the home team touched the ball 17 frames before it was logged
    f = _features(list(home), list(away), [1.0] * n)
    assert cd.dfl_shift(f, [(117, 0, False), (217, 0, False), (317, 0, False)]) == -17
