"""Lane st-gaps: units, the firing threshold, both datings and their floors, order and priority."""

from __future__ import annotations

import numpy as np
import pytest
from _bundle import requires_bundle

from tools import engine
from tools import st_gaps as sg

NONE = sg.NONE
HOME = 0
AWAY = 1
# 5 frames at 25 fps: the synthetic strings below are short.
FIVE = 5 / sg.FPS


def team_of(text: str) -> np.ndarray:
    """`h` home, `a` away, `.` none: control frames or Smart Tagging sides."""
    return np.array([{"h": HOME, "a": AWAY, ".": NONE}[c] for c in text], dtype=np.int8)


def flags(text: str, on: str) -> np.ndarray:
    return np.array([c == on for c in text])


def variant(unit: str = "gap", dating: str = "gap", min_s: float = FIVE, share: float = 0.5):
    return sg.Variant("T", unit, min_s, share, dating)


def switches(
    ctrl: str,
    ball: str,
    side: str,
    v: sg.Variant,
    *,
    dead: str | None = None,
    forced: dict[int, int] | None = None,
    duel: str | None = None,
) -> dict[int, int]:
    n = len(ctrl)
    return sg.st_switches(
        team_of(ctrl),
        team_of(duel) if duel is not None else None,
        forced or {},
        flags(ball, "b"),
        flags(dead, "d") if dead is not None else np.zeros(n, dtype=bool),
        team_of(side),
        [(0, n)],
        v,
    )


# -- sides and units ------------------------------------------------------------------------------


def test_a_side_needs_every_vote_on_one_team() -> None:
    votes = np.array([[1, 0], [0, 2], [1, 1], [0, 0]])
    assert sg.sides(votes).tolist() == [HOME, AWAY, NONE, NONE]


def test_a_live_gap_is_a_ball_gap_without_its_dead_frames() -> None:
    present = flags("bb......bb", "b")
    dead = flags("..dd......", "d")
    assert sg.units(present, dead, [(0, 10)], "gap") == [(2, 8)]
    assert sg.units(present, dead, [(0, 10)], "live") == [(4, 8)]


def test_a_variant_rejects_what_the_pre_registration_does_not_name() -> None:
    with pytest.raises(ValueError):
        sg.Variant("bad", "half", 5.0, 0.5, "gap")
    with pytest.raises(ValueError):
        sg.Variant("bad", "gap", 5.0, 0.5, "midpoint")
    with pytest.raises(ValueError):
        sg.Variant("bad", "gap", 5.0, 0.0, "gap")


def test_the_four_pre_registered_variants_are_the_documented_ones() -> None:
    got = {n: (v.unit, v.min_s, v.share, v.dating) for n, v in sg.VARIANTS.items()}
    assert got == {
        "V1": ("gap", 5.0, 0.5, "gap"),
        "V2": ("gap", 5.0, 0.5, "phase"),
        "V3": ("live", 5.0, 0.5, "gap"),
        "V4": ("gap", 20.0, 0.5, "gap"),
    }


# -- when a unit fires ----------------------------------------------------------------------------


def test_a_long_gap_the_tagging_gives_to_the_rival_switches_at_its_first_frame() -> None:
    #           0123456789
    ctrl = "h........."
    ball = "bb......bb"
    side = "..aaaaaa.."
    assert switches(ctrl, ball, side, variant()) == {2: AWAY}


def test_a_minority_of_rival_votes_does_not_fire() -> None:
    assert switches("h.........", "bb......bb", "..aa......", variant()) == {}


def test_the_share_is_inclusive() -> None:
    # 3 of 6 frames is exactly a half: the pre-registration says "at least X".
    assert switches("h.........", "bb......bb", "..aaa.....", variant()) == {2: AWAY}


def test_agreeing_votes_do_not_fire() -> None:
    assert switches("h.........", "bb......bb", "..hhhhhh..", variant()) == {}


def test_a_gap_shorter_than_g_does_not_fire() -> None:
    assert switches("h.........", "bb....bbbb", "..aaaa....", variant()) == {}


def test_nothing_fires_before_the_first_state_of_a_half() -> None:
    assert switches("..........", "bb......bb", "..aaaaaa..", variant()) == {}


def test_a_gap_that_is_all_dead_does_nothing() -> None:
    v = variant()
    assert switches("h.........", "bb......bb", "..aaaaaa..", v, dead="..dddddd..") == {}


def test_only_live_frames_vote_and_the_switch_lands_on_the_first_one() -> None:
    # Votes for the home side inside the stoppage do not count against the rival.
    ctrl, ball = "h.........", "bb......bb"
    side, dead = "..hhaaaa..", "..dd......"
    assert switches(ctrl, ball, side, variant(), dead=dead) == {4: AWAY}


def test_a_live_unit_measures_its_length_without_the_dead_frames() -> None:
    ctrl, ball = "h...........", "bb........bb"
    side, dead = "..aaaaaaaa..", "..dddd......"
    long_gap = variant(min_s=7 / sg.FPS)  # the ball gap has 8 frames, its live part 4
    assert switches(ctrl, ball, side, long_gap, dead=dead) == {6: AWAY}
    assert switches(ctrl, ball, side, variant("live", min_s=7 / sg.FPS), dead=dead) == {}


def test_a_restart_inside_the_unit_leaves_it_to_the_restart_rule() -> None:
    ctrl, ball, side = "h.........", "bb......bb", "..aaaaaa.."
    assert switches(ctrl, ball, side, variant(), forced={5: AWAY}) == {}


def test_a_restart_to_the_carried_team_inside_the_unit_stops_it_firing() -> None:
    # The state stays the carried team's over the whole unit, but the restart at 5 would undo a
    # switch at 2 three frames later: the unit is the restart's, not the Smart Tagging's.
    ctrl, ball, side = "h.........", "bb......bb", "..aaaaaa.."
    assert switches(ctrl, ball, side, variant(), forced={5: HOME}) == {}
    assert switches(ctrl, ball, side, variant(dating="phase"), forced={5: HOME}) == {}


def test_phase_dating_never_walks_back_across_a_restart_inside_the_unit() -> None:
    # Without the restart the switch goes back to 1 (`phase`); the restart at 6 sits between that
    # date and the unit's rival frames, so no switch is dated before it: the unit does nothing.
    ctrl = "h.........."
    ball = "bbbb.....bb"
    side = ".aaaaaaaa.."
    assert switches(ctrl, ball, side, variant(dating="phase")) == {1: AWAY}
    assert switches(ctrl, ball, side, variant(dating="phase"), forced={6: HOME}) == {}


def test_a_restart_just_before_the_unit_does_not_stop_it() -> None:
    ctrl, ball, side = "h.........", "bb......bb", "..aaaaaa.."
    assert switches(ctrl, ball, side, variant(), forced={1: HOME}) == {2: AWAY}


def test_a_restart_on_the_switch_frame_wins() -> None:
    # The restart gives the ball to the carried team on the very frame the switch would land.
    ctrl, ball, side = "h.........", "bb......bb", "..aaaaaa.."
    assert switches(ctrl, ball, side, variant(), forced={2: HOME}) == {}


# -- dating ---------------------------------------------------------------------------------------


def test_phase_dating_goes_back_to_where_the_rival_phase_began() -> None:
    #       0123456789
    ctrl = "h.........."
    ball = "bbbb.....bb"
    side = ".aaaaaaaa.."
    assert switches(ctrl, ball, side, variant(dating="phase")) == {1: AWAY}
    assert switches(ctrl, ball, side, variant(dating="gap")) == {4: AWAY}


def test_phase_dating_never_precedes_the_carried_teams_last_control() -> None:
    ctrl = "h.h........"
    ball = "bbbb.....bb"
    side = ".aaaaaaaa.."
    assert switches(ctrl, ball, side, variant(dating="phase")) == {3: AWAY}


def test_phase_dating_never_precedes_a_restart_given_to_the_carried_team() -> None:
    ctrl = "h.........."
    ball = "bbbb.....bb"
    side = ".aaaaaaaa.."
    assert switches(ctrl, ball, side, variant(dating="phase"), forced={2: HOME}) == {3: AWAY}


def test_phase_dating_starts_inside_the_gap_when_the_phase_does() -> None:
    ctrl = "h..........."
    ball = "bb........bb"
    side = "......aaaa.."
    assert switches(ctrl, ball, side, variant(dating="phase")) == {6: AWAY}


# -- what happens after the switch ----------------------------------------------------------------


def test_units_are_judged_on_the_state_the_earlier_switches_left() -> None:
    # The second gap's votes agree with the team *before* the first switch: judged on the original
    # state they would not fire, judged in order they hand the ball back.
    #       0         1
    #       0123456789012345
    ctrl = "h..............."
    ball = "bb......bb......"
    side = "..aaaaaa..hhhhhh"
    assert switches(ctrl, ball, side, variant()) == {2: AWAY, 10: HOME}


def test_the_rival_keeps_the_ball_until_an_accepted_control() -> None:
    ctrl = team_of("h.........h.")
    present = flags("bb......bbbb", "b")
    side = team_of("..aaaaaa....")
    runs = [(0, 12)]
    clean = team_of("h.........h.")  # the carried team's control at 10 is uncontested
    duel = team_of("h...........")  # the same control is a duel: the rival still plays it
    for switch, after in ((clean, HOME), (duel, AWAY)):
        moves = sg.st_switches(ctrl, switch, {}, present, np.zeros(12, bool), side, runs, variant())
        state = engine.decode(ctrl, runs, 1, moves, switch)
        assert state[:2].tolist() == [HOME, HOME]
        assert state[2:10].tolist() == [AWAY] * 8
        assert state[10:].tolist() == [after] * 2


def test_switches_never_cross_a_half() -> None:
    ctrl = team_of("h....h.....")
    present = flags("bbbbbbb....", "b")
    side = team_of(".......aaaa")
    # The gap opens in the second half, before any of its controls: nothing is carried into it.
    runs = [(0, 5), (5, 11)]
    moves = sg.st_switches(
        ctrl, None, {}, present, np.zeros(11, bool), side, runs, variant(min_s=0.16)
    )
    assert moves == {7: AWAY}
    ctrl = team_of("h..........")
    moves = sg.st_switches(
        ctrl, None, {}, present, np.zeros(11, bool), side, runs, variant(min_s=0.16)
    )
    assert moves == {}


# -- the match ------------------------------------------------------------------------------------


@pytest.fixture(scope="module")
def match():
    from tools import atd, dead_ball, emision

    f = engine.features(atd.load("tactical"), emision.team_slots())
    ev = dead_ball.load_evidence()
    return f, ev, engine.delivered_dead(ev)


@requires_bundle
def test_a_variant_that_never_fires_is_the_delivered_chain(match) -> None:
    f, ev, dead = match
    never = sg.Variant("never", "gap", 1e6, 0.5, "gap")
    _state, labels, moves = sg.chain(f, ev, never, dead=dead)
    assert moves == {}
    assert np.array_equal(labels, engine.chain(f, engine.DEFAULT, ev.restarts, dead)[2])


@requires_bundle
def test_every_variant_is_deterministic(match) -> None:
    f, ev, dead = match
    for v in sg.VARIANTS.values():
        first = sg.chain(f, ev, v, dead=dead)
        second = sg.chain(f, ev, v, dead=dead)
        assert first[2] == second[2]
        assert np.array_equal(first[1], second[1])
