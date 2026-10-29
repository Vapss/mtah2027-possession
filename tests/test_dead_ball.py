"""#16 dead-ball stream: each rule of the stoppage model, pinned on synthetic evidence.

The synthetic match is 4,000 frames with one half `[100, 3900)`, so every rule can be placed by
hand: where a restart is, where the ball went out, when the field stood still. Times are written in
frames at 25 fps; `Params` converts its seconds the same way. One test reads the delivered match
and skips on a checkout without the bundle; it pins aggregates only, never a frame.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import pytest

import games
from tools import dead_ball
from tools.dead_ball import DEFAULT, Evidence, Restart, Stoppage

N = 4000
HALF = [(100, 3900)]
RESTART = DEFAULT.frames(DEFAULT.restart_s)  # 125: a 35 s tag's restart is 5 s in
LOOKBACK = DEFAULT.frames(DEFAULT.lookback_s)  # 1000


def evidence(
    restarts: list[Restart],
    out: list[tuple[int, int]] = (),
    still: list[tuple[int, int]] = (),
    inside: list[tuple[int, int]] = (),
) -> Evidence:
    """Evidence from half-open frame ranges; anything not listed is False."""

    def mask(ranges: list[tuple[int, int]]) -> np.ndarray:
        marked = np.zeros(N, dtype=bool)
        for start, stop in ranges:
            marked[start:stop] = True
        return marked

    return Evidence(tuple(restarts), mask(out), mask(inside), mask(still))


def restart_at(tag_start: int, kind: str = "Throw-in") -> Restart:
    offset = DEFAULT.kick_off_restart_s if kind.startswith("Kick Off") else DEFAULT.restart_s
    return Restart(tag_start + DEFAULT.frames(offset), tag_start, kind)


def spans(mask: np.ndarray) -> list[tuple[int, int]]:
    edges = np.diff(np.concatenate(([0], mask.astype(np.int8), [0])))
    return list(zip(np.flatnonzero(edges == 1).tolist(), np.flatnonzero(edges == -1).tolist()))


# --- restarts from Smart Tagging -------------------------------------------------------------


def instance(code: str, start: int, kind: str) -> dict:
    return {"code": code, "start_frame": start, "end_frame": start + 875, "tags": {"Type": kind}}


def test_restart_sits_5_s_into_a_set_piece_and_3_5_s_into_a_kick_off() -> None:
    found = dead_ball.restarts(
        [
            instance("SET PIECES", 2000, "Corner Kick"),
            instance("SET PIECES", 1000, "Kick Off (After Goal)"),
            instance("BUILD UP", 500, ""),
        ]
    )
    # Sorted by frame, and only SET PIECES: a phase of play is not a restart.
    assert found == (
        Restart(1088, 1000, "Kick Off (After Goal)"),
        Restart(2125, 2000, "Corner Kick"),
    )


# --- out-of-pitch episodes and stillness -----------------------------------------------------


def test_out_episodes_join_gaps_of_up_to_one_second_only() -> None:
    out = np.zeros(N, dtype=bool)
    out[100:110] = True
    out[135:140] = True  # 25 frames after the last out frame (109): same episode
    out[166:170] = True  # 26 frames after 139: a new episode
    assert dead_ball.out_episodes(out, merge=25) == [(100, 140, 15), (166, 170, 4)]
    assert dead_ball.out_episodes(np.zeros(5, dtype=bool), merge=25) == []


def test_stillness_is_a_smoothed_median_speed_below_walking_pace() -> None:
    speed = np.full(200, 2.0)
    speed[50:150] = 0.5
    still = dead_ball.stillness(speed)
    assert not still[:30].any() and still[70:130].all() and not still[170:].any()


def test_unknown_speed_is_never_stillness() -> None:
    speed = np.full(100, np.nan)
    assert not dead_ball.stillness(speed).any()
    speed[40:60] = 0.2  # the windows around it see only these, and they are slow
    assert dead_ball.stillness(speed)[50]


def test_field_speed_is_the_median_over_tracked_players() -> None:
    players = np.zeros((3, 3, 2))
    players[1] = [[1 / 25, 0], [2 / 25, 0], [np.nan, np.nan]]  # 1 and 2 m/s, one slot untracked
    players[2] = players[1]
    speed = dead_ball.field_speed(players)
    assert np.isnan(speed[0])
    assert speed[1] == pytest.approx(1.5)
    assert speed[2] == pytest.approx(0.0)


# --- the four variants -----------------------------------------------------------------------


def test_tag_marks_only_the_window_before_its_restart() -> None:
    ev = evidence([restart_at(2000)], out=[(1500, 1600)], still=[(1000, 2000)])
    assert spans(dead_ball.dead_mask(ev, HALF, "tag")) == [(2000, 2000 + RESTART)]


def test_out_starts_the_stoppage_at_the_last_episode_before_the_tag() -> None:
    ev = evidence([restart_at(2000)], out=[(1300, 1320), (1700, 1720)])
    assert dead_ball.stoppages(ev, HALF, "out") == [Stoppage(1700, 2000 + RESTART, "out")]


def test_out_ignores_an_episode_beyond_the_lookback() -> None:
    restart = restart_at(2000)
    ev = evidence([restart], out=[(restart.frame - LOOKBACK - 1, restart.frame - LOOKBACK + 10)])
    assert dead_ball.stoppages(ev, HALF, "out") == [Stoppage(2000, restart.frame, "tag")]


def test_a_stoppage_never_begins_before_the_previous_restart() -> None:
    first, second = restart_at(1000), restart_at(1600)
    ev = evidence([first, second], out=[(1050, 1060)])  # out, but before `first` resumed play
    found = dead_ball.stoppages(ev, HALF, "out")
    assert found[1] == Stoppage(1600, second.frame, "tag")
    ev = evidence([first, second], out=[(first.frame + 10, first.frame + 20)])
    assert dead_ball.stoppages(ev, HALF, "out")[1].start == first.frame + 10


def test_after_a_goal_the_lookback_is_two_minutes() -> None:
    goal = restart_at(3500, "Kick Off (After Goal)")
    episode = goal.frame - DEFAULT.frames(100.0)  # beyond 40 s, inside 120 s
    ev = evidence([goal], out=[(episode, episode + 5)])
    assert dead_ball.stoppages(ev, HALF, "out") == [Stoppage(episode, goal.frame, "out")]
    throw = restart_at(3500)
    ev = evidence([throw], out=[(episode, episode + 5)])
    assert dead_ball.stoppages(ev, HALF, "out")[0].source == "tag"


def test_still_reaches_back_only_when_no_ball_went_out() -> None:
    ev = evidence([restart_at(2000)], still=[(1400, 2000)])
    assert dead_ball.stoppages(ev, HALF, "out+still") == [Stoppage(1400, 2000 + RESTART, "still")]
    ev = evidence([restart_at(2000)], out=[(1800, 1810)], still=[(1400, 2000)])
    assert dead_ball.stoppages(ev, HALF, "out+still")[0] == Stoppage(1800, 2125, "out")


def test_still_is_capped_by_the_lookback_and_needs_the_frame_before_the_tag() -> None:
    restart = restart_at(2500)
    ev = evidence([restart], still=[(100, 2500)])
    assert dead_ball.stoppages(ev, HALF, "out+still")[0].start == restart.frame - LOOKBACK
    ev = evidence([restart], still=[(1000, 2400)])  # still earlier, moving just before the tag
    assert dead_ball.stoppages(ev, HALF, "out+still")[0].source == "tag"


def test_untagged_opens_a_stoppage_until_the_ball_is_seen_back_on_the_pitch() -> None:
    ev = evidence([], out=[(1000, 1030)], inside=[(1200, 1300)])
    assert dead_ball.stoppages(ev, HALF, "out+still+untagged") == [Stoppage(1000, 1200, "untagged")]
    assert not dead_ball.dead_mask(ev, HALF, "out+still").any()


def test_untagged_skips_short_episodes_and_ones_a_tagged_restart_closes() -> None:
    short = evidence([], out=[(1000, 1024)], inside=[(1200, 1300)])  # 24 frames out: noise
    assert dead_ball.stoppages(short, HALF, "out+still+untagged") == []
    restart = restart_at(1500)
    closed = evidence([restart], out=[(1000, 1030)], inside=[(1200, 1300)])
    assert [s.source for s in dead_ball.stoppages(closed, HALF, "out+still+untagged")] == ["out"]


def test_untagged_without_a_ball_back_in_stops_at_the_lookback() -> None:
    ev = evidence([], out=[(1000, 1030)])
    assert dead_ball.stoppages(ev, HALF, "out+still+untagged") == [
        Stoppage(1000, 1000 + LOOKBACK, "untagged")
    ]


def test_variants_are_cumulative() -> None:
    ev = evidence(
        [restart_at(800), restart_at(2000), restart_at(3000)],
        out=[(1800, 1810), (3300, 3340)],
        still=[(2600, 3000)],
        inside=[(3400, 3500)],
    )
    masks = [dead_ball.dead_mask(ev, HALF, variant) for variant in dead_ball.VARIANTS]
    for smaller, larger in zip(masks, masks[1:]):
        assert not (smaller & ~larger).any()
    assert all(int(a.sum()) < int(b.sum()) for a, b in zip(masks, masks[1:]))


# --- halves, kick-offs and the variant name --------------------------------------------------


def test_before_a_halfs_first_kick_the_ball_is_dead() -> None:
    kick_off = restart_at(400, "Kick Off (Start)")
    assert dead_ball.stoppages(evidence([kick_off]), HALF, "tag") == [
        Stoppage(100, kick_off.frame, "kick-off")
    ]


def test_nothing_is_marked_outside_the_halves() -> None:
    ev = evidence([restart_at(50), restart_at(3850)], out=[(3920, 3990)], inside=[(3995, 4000)])
    dead = dead_ball.dead_mask(ev, HALF, "out+still+untagged")
    assert not dead[:100].any() and not dead[3900:].any()
    # The first tag straddles the half's start and is clipped to it; the second restart (3975)
    # and the out episode fall after the half, so they open nothing.
    assert dead_ball.stoppages(ev, HALF, "out+still+untagged") == [Stoppage(100, 175, "tag")]


def test_an_unknown_variant_fails_closed() -> None:
    with pytest.raises(ValueError, match="unknown variant"):
        dead_ball.dead_mask(evidence([]), HALF, "ball-threshold")


def test_evidence_arrays_must_line_up() -> None:
    with pytest.raises(ValueError, match="differ in length"):
        Evidence((), np.zeros(3, bool), np.zeros(3, bool), np.zeros(4, bool))


# --- writing D and scoring the mask ----------------------------------------------------------


def test_apply_dead_writes_d_and_leaves_everything_else() -> None:
    labels = pd.DataFrame({"frame": np.arange(6), "label": ["H", "H", "X", "A", "A", "H"]})
    dead = np.array([False, True, True, False, False, False])
    out = dead_ball.apply_dead(labels, dead)
    assert out["label"].tolist() == ["H", "D", "D", "A", "A", "H"]
    assert labels["label"].tolist() == ["H", "H", "X", "A", "A", "H"]  # the input is not touched
    with pytest.raises(ValueError, match="mask has 5 frames"):
        dead_ball.apply_dead(labels, dead[:5])


def test_d_precision_and_recall_ignore_ungraded_frames() -> None:
    gt = np.array(["X", "D", "D", "H", "A", "D"])
    dead = np.array([True, True, False, True, False, True])
    scores = dead_ball.dead_precision_recall(gt, dead)
    assert scores["graded_frames"] == 5 and scores["hits"] == 2
    assert scores["precision"] == pytest.approx(2 / 3)
    assert scores["recall"] == pytest.approx(2 / 3)


# --- the delivered match ---------------------------------------------------------------------


@pytest.fixture(scope="module")
def delivered() -> Evidence:
    paths = games.asset_paths()
    if not (Path(paths["atd_raw"]).is_file() and Path(paths["smart_tagging"]).is_file()):
        pytest.skip("match bundle not unpacked -- see data/README.md")
    return dead_ball.load_evidence()


def test_delivered_match_aggregates(delivered: Evidence) -> None:
    # Aggregates of the recommended variant, read off the delivered match (lane-d.md): if the
    # export or a rule changes, these move and the proposal's numbers must be regenerated.
    runs = dead_ball.halves()
    found = dead_ball.stoppages(delivered, runs, "out")
    result = dead_ball.summary(found, len(delivered.out), runs)
    assert len(delivered.restarts) == 59
    assert result["stoppages_by_source"] == {"kick-off": 2, "out": 28, "tag": 29}
    assert result["dead_share_in_halves"] == pytest.approx(0.1230, abs=5e-4)
