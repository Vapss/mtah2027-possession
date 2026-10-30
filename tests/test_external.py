"""The external corpus: parser, label mapping, our shape, degradation and scorer, on synthetic data.

Only the last test reads the real IDSSE files, and it skips when they are not on this machine.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pytest

from tools import ball_gaps, dead_ball, engine, external

HOME, GUEST = "DFL-CLU-HOME", "DFL-CLU-AWAY"


def _frames(
    first: int,
    xy: list[tuple[float, float]],
    ball: list[tuple[int, int]] | None = None,
    step: float = 0.04,
) -> list[str]:
    lines = []
    for i, (x, y) in enumerate(xy):
        t = 12 * 3600 + i * step
        stamp = f"2023-05-27T{int(t // 3600):02d}:{int(t % 3600 // 60):02d}:{t % 60:06.3f}+00:00"
        extra = ""
        if ball is not None:
            extra = f' Z="0.00" BallPossession="{ball[i][0]}" BallStatus="{ball[i][1]}"'
        lines.append(
            f'<Frame N="{first + i}" T="{stamp}" X="{x:.2f}" Y="{y:.2f}" D="0.00" '
            f'S="0.00" A="0.00" M="1"{extra}/>'
        )
    return lines


def _write(path: Path, step: float = 0.04) -> Path:
    """Two halves of four frames: ball, one player per team, a referee that must be dropped."""
    out = [
        '<?xml version="1.0" encoding="UTF-8" standalone="yes" ?>',
        "<PutDataRequest>",
        "<Positions>",
        '<MetaData Type="pitch-size">',
        '<PitchSize X="105.00" Y="68.00" />',
        "</MetaData>",
    ]
    for section, first in (("firstHalf", 10000), ("secondHalf", 100000)):
        sets = [
            (
                "BALL",
                "B",
                _frames(
                    first, [(0, 0), (1, 0), (60, 0), (2, 0)], [(1, 1), (2, 1), (2, 0), (1, 1)], step
                ),
            ),
            (HOME, "P1", _frames(first + 1, [(1.5, 0), (3, 0)], step=step)),  # joins late
            (GUEST, "P2", _frames(first, [(5, 0)] * 4, step=step)),
            ("referee", "R", _frames(first, [(0, 0)] * 4, step=step)),
        ]
        for team, person, frames in sets:
            out.append(
                f'<FrameSet GameSection="{section}" MatchId="M" TeamId="{team}" '
                f'PersonId="{person}">'
            )
            out += frames
            out.append("</FrameSet>")
    out += ["</Positions>", "</PutDataRequest>"]
    path.write_text("\n".join(out) + "\n", encoding="utf-8")
    return path


def test_the_parser_reads_ball_labels_and_places_players_by_frame_number(tmp_path) -> None:
    raw = external.parse_positions(_write(tmp_path / "pos.xml"), HOME, GUEST, "M")
    assert raw.pitch == (105.0, 68.0)
    first, second = raw.sections
    assert (first.first, second.first) == (10000, 100000)
    assert first.possession.tolist() == [1, 2, 2, 1]
    assert first.status.tolist() == [1, 1, 0, 1]
    assert first.home.shape == (4, 1, 2) and first.away.shape == (4, 1, 2)  # referee dropped
    assert np.isnan(first.home[0]).all() and first.home[1, 0].tolist() == [1.5, 0.0]


def test_a_file_that_is_not_25_hz_is_refused(tmp_path) -> None:
    with pytest.raises(ValueError, match="Hz"):
        external.parse_positions(_write(tmp_path / "pos.xml", step=0.1), HOME, GUEST)


def test_dead_is_d_whatever_the_possession_and_unknown_is_x() -> None:
    labels = external.truth_labels(np.array([1, 2, 1, 2, 0]), np.array([1, 1, 0, 0, 1]))
    assert labels.tolist() == ["H", "A", "D", "D", "X"]


def test_build_moves_the_origin_to_a_corner_and_separates_the_halves(tmp_path) -> None:
    match = external.build(external.parse_positions(_write(tmp_path / "pos.xml"), HOME, GUEST))
    gap = external.HALF_GAP
    assert match.runs == ((0, 4), (4 + gap, 8 + gap))
    assert match.truth[:4].tolist() == ["H", "A", "D", "H"]
    assert (match.truth[4 : 4 + gap] == "X").all()
    f = match.features
    # Ball at the centre spot is (52.5, 34) from the corner; x = 60 from the centre is beyond L.
    assert f.in_pitch[:4].tolist() == [True, True, False, True]
    assert match.evidence.out[:4].tolist() == [False, False, True, False]
    assert np.isinf(f.home_m[0])  # the home player is not on the pitch yet
    assert f.home_m[1] == pytest.approx(0.5) and f.away_m[1] == pytest.approx(4.0)
    assert not f.present[4 : 4 + gap].any() and np.isnan(f.speed_mps[4 + gap])
    assert f.speed_mps[1] == pytest.approx(25.0)  # 1 m in one 25 Hz frame
    assert match.evidence.restarts == ()


def _match(n: int = 10, runs: tuple = ((0, 4), (6, 10))) -> external.Match:
    present = np.ones(n, dtype=bool)
    f = engine.Features(np.full(n, 1.0), np.full(n, 3.0), present, np.full(n, 1.0), present.copy())
    ev = dead_ball.Evidence((), np.zeros(n, dtype=bool), present.copy(), np.zeros(n, dtype=bool))
    truth = np.array(["H"] * n, dtype=object)
    truth[4:6] = "X"
    return external.Match("toy", f, ev, truth, runs)


def test_the_donor_halves_are_laid_from_each_half_start_and_repeated() -> None:
    match = _match()
    keep = external.keep_mask(match, [np.array([True, False, False]), np.array([False, True])])
    assert keep.tolist() == [True, False, False, True, True, True, False, True, False, True]


def test_degrade_deletes_the_ball_and_keeps_the_labels() -> None:
    match = _match()
    out = external.degrade(match, [np.array([True, False]), np.array([True])])
    assert out.features.present.tolist() == [True, False, True, False] + [True] * 6
    assert np.isnan(out.features.home_m[1]) and not out.evidence.inside[3]
    assert np.isnan(out.features.speed_mps[2])  # the previous frame has no ball now
    assert (out.truth == match.truth).all() and match.features.present.all()


def test_a_method_sees_the_external_halves_and_ours_come_back() -> None:
    ours = engine.halves()
    match = _match()
    seen = {}

    def method(f, ev):
        seen["engine"], seen["dead_ball"] = engine.halves(), dead_ball.halves()
        seen["gaps"] = ball_gaps.half_runs()
        return engine.chain(f, engine.DEFAULT, None, None)[2]

    labels = external.run(method, match)
    assert seen == {
        "engine": [(0, 4), (6, 10)],
        "dead_ball": [(0, 4), (6, 10)],
        "gaps": [(0, 4), (6, 10)],
    }
    assert labels[4:6].tolist() == ["X", "X"]  # nothing is decoded between the halves
    assert engine.halves() == ours


def test_an_oracle_scores_one_and_the_rate_is_per_graded_minute() -> None:
    n = 3000
    match = _match(n, ((0, 1500), (1600, 3000)))
    truth = np.array(["H"] * n, dtype=object)
    truth[700:800] = "D"
    truth[800:1500] = "A"
    truth[1500:1600] = "X"
    match = external.Match("toy", match.features, match.evidence, truth, match.runs)
    table = external.score(lambda f, ev: truth.copy(), [match])
    row = table.iloc[0]
    assert row["spell_f1"] == pytest.approx(1.0) and row["macro_f1"] == pytest.approx(1.0)
    assert row["n_gt"] == 3  # H, A, and the second half's H: the gap is not a possession
    assert row["gt_per_min"] == pytest.approx(3 / (2900 / 25 / 60))
    # Possessions of 28, 28 and 56 s: the time scale is reported for both sides.
    assert row["gt_median_s"] == pytest.approx(28.0) and row["pred_median_s"] == row["gt_median_s"]
    assert row["pred_under_1s"] == 0.0 and row["pred_per_min"] == row["gt_per_min"]
    assert table.iloc[-1]["match"] == "mean"


def test_a_method_that_imported_halves_by_name_is_swapped_too(monkeypatch) -> None:
    import types

    fake = types.ModuleType("tools._fake_decoder")
    fake.halves = engine.halves  # what `from tools.engine import halves` leaves behind
    monkeypatch.setitem(sys.modules, "tools._fake_decoder", fake)
    with external.halves_of(_match()):
        assert fake.halves() == [(0, 4), (6, 10)]
    assert fake.halves is engine.halves


def test_plugged_in_methods_keep_their_names_unless_they_collide(monkeypatch) -> None:
    import types

    def mine(f, ev):
        return np.array([])

    taken = dict(external.METHODS)
    plugin = types.ModuleType("tools._fake_plugin")
    plugin.METHODS = {"touch": mine, "engine": mine, "smooth50": taken["smooth50"]}
    plugin.touch = mine
    monkeypatch.setitem(sys.modules, "tools._fake_plugin", plugin)
    found = external.extra_methods("tools._fake_plugin:METHODS", taken)
    assert set(found) == {"touch", "_fake_plugin.engine", "smooth50"}  # ours is not replaced
    assert external.extra_methods("tools._fake_plugin:touch", taken) == {"touch": mine}


def test_engine_out_marks_a_ball_out_for_a_second_dead_until_it_is_back() -> None:
    n = 200
    match = _match(n, ((0, n),))
    out = np.zeros(n, dtype=bool)
    out[50:80] = True  # 1,2 s out of the pitch
    inside = ~out
    inside[80:100] = False  # not seen anywhere for a while, then back on the pitch at 100
    present = out | inside
    f = match.features
    f = engine.Features(
        np.where(present, f.home_m, np.nan),
        np.where(present, f.away_m, np.nan),
        present,
        np.where(present, f.speed_mps, np.nan),
        inside,
    )
    ev = dead_ball.Evidence((), out, inside, np.zeros(n, dtype=bool))
    labels = external.run(
        external.METHODS["engine-out"], external.Match("toy", f, ev, match.truth, match.runs)
    )
    assert (labels[50:100] == "D").all() and (labels[:50] == "H").all()
    assert (labels[100:] == "H").all()


DATA = external.data_dir() / "idsse"


@pytest.mark.skipif(not any(DATA.glob("DFL_04_03_*J03WMX.xml")), reason="IDSSE data not here")
def test_a_real_match_has_two_halves_and_only_its_gap_is_unlabelled() -> None:
    match = external.load("J03WMX")
    labels, counts = np.unique(match.truth, return_counts=True)
    assert dict(zip(labels.tolist(), counts.tolist()))["X"] == external.HALF_GAP
    assert len(match.runs) == 2
    assert match.features.present[: match.runs[0][1]].mean() > 0.99  # optical: ball almost always
