from __future__ import annotations

import numpy as np
import pytest

from tools.postprocess import postprocess


def labels(*parts: tuple[str, int]) -> list[str]:
    return [label for label, count in parts for _ in range(count)]


def test_absorbs_short_fragment_between_same_team_runs() -> None:
    source = labels(("H", 20), ("A", 8), ("H", 22))
    result = postprocess(source, [(0, len(source))])
    assert result == ["H"] * len(source)


def test_absorbs_short_team_run_to_longer_neighbor_when_no_same_team() -> None:
    source = labels(("H", 30), ("A", 14), ("D", 40))
    result = postprocess(source, [(0, len(source))])
    assert result == ["H"] * 30 + ["D"] * 54


@pytest.mark.parametrize("short_length", [1, 14])
def test_team_run_lengths_below_minimum_are_absorbed(short_length: int) -> None:
    source = labels(("H", 20), ("A", short_length), ("H", 20))
    result = postprocess(source, [(0, len(source))])
    assert set(result) == {"H"}


@pytest.mark.parametrize("long_length", [15, 19])
def test_runs_at_or_above_minimum_survive(long_length: int) -> None:
    source = labels(("H", 20), ("A", long_length), ("H", 20))
    result = postprocess(source, [(0, len(source))])
    assert result == source


def test_merges_same_team_runs_across_14_frame_interruption_but_not_15() -> None:
    at_limit = labels(("H", 20), ("A", 14), ("H", 20))
    over_limit = labels(("H", 20), ("A", 15), ("H", 20))
    assert set(postprocess(at_limit, [(0, len(at_limit))])) == {"H"}
    assert postprocess(over_limit, [(0, len(over_limit))]) == over_limit


def test_prior_duration_and_previous_neighbor_are_deterministic_tie_breaks() -> None:
    source = labels(("H", 20), ("A", 5), ("D", 20))
    result = postprocess(source, [(0, len(source))])
    assert result == ["H"] * 25 + ["D"] * 20

    closer_to_prior = labels(("H", 20), ("A", 5), ("D", 355))
    result = postprocess(closer_to_prior, [(0, len(closer_to_prior))])
    assert result == ["H"] * 20 + ["D"] * 360

    longer_beats_closer_prior = labels(("H", 500), ("A", 5), ("D", 355))
    result = postprocess(longer_beats_closer_prior, [(0, len(longer_beats_closer_prior))])
    assert result == ["H"] * 505 + ["D"] * 355


def test_d_short_merges_only_between_same_team_neighbors() -> None:
    source = labels(("H", 20), ("D", 14), ("H", 20))
    result = postprocess(source, [(0, len(source))])
    assert result == ["H"] * len(source)


@pytest.mark.parametrize(
    "source",
    [
        labels(("H", 20), ("D", 15), ("H", 20)),
        labels(("H", 20), ("D", 14), ("A", 20)),
        labels(("D", 14), ("H", 20)),
        labels(("H", 20), ("D", 14)),
    ],
)
def test_d_long_edge_or_different_team_neighbors_are_preserved(source: list[str]) -> None:
    assert postprocess(source, [(0, len(source))]) == source


def test_does_not_cross_disjoint_runs_or_halftime_gap() -> None:
    source = labels(("H", 20), ("A", 5), ("X", 3), ("H", 20), ("A", 5), ("H", 20))
    result = postprocess(source, [(0, 25), (28, len(source))])
    assert result[:25] == ["H"] * 25
    assert result[25:28] == ["X"] * 3
    assert result[28:] == ["H"] * (len(source) - 28)


def test_same_label_at_both_sides_of_run_gap_does_not_connect_segments() -> None:
    source = labels(("H", 20), ("A", 15), ("H", 20), ("X", 3), ("H", 20), ("A", 15), ("H", 20))
    result = postprocess(source, [(0, 55), (58, len(source))])
    assert result[:55] == source[:55]
    assert result[55:58] == ["X"] * 3
    assert result[58:] == source[58:]


def test_rechecks_left_boundary_when_a_short_run_makes_d_mergeable() -> None:
    source = labels(("H", 20), ("D", 10), ("A", 10), ("H", 20))
    result = postprocess(source, [(0, len(source))])
    assert set(result) == {"H"}


@pytest.mark.parametrize("x_position", ["interior", "initial", "final"])
def test_x_is_temporarily_filled_for_structure_then_restored(x_position: str) -> None:
    source = labels(("H", 10), ("X", 1), ("H", 10))
    if x_position == "initial":
        source[0] = "X"
    elif x_position == "final":
        source[-1] = "X"
    result = postprocess(source, [(0, len(source))])
    x_positions = [i for i, value in enumerate(source) if value == "X"]
    assert result.count("X") == len(x_positions)
    assert all(result[index] == "X" for index in x_positions)


def test_all_x_run_is_unchanged() -> None:
    source = ["X"] * 12
    assert postprocess(source, [(0, len(source))]) == source


def test_frames_outside_runs_are_unchanged_and_output_length_is_preserved() -> None:
    source = labels(("A", 3), ("H", 25), ("A", 5), ("D", 20))
    result = postprocess(source, [(3, 28)])
    assert len(result) == len(source)
    assert result[:3] == source[:3]
    assert result[28:] == source[28:]


def test_repeated_calls_are_idempotent() -> None:
    source = labels(("H", 30), ("A", 5), ("D", 3), ("H", 20), ("A", 15))
    once = postprocess(source, [(0, len(source))])
    twice = postprocess(once, [(0, len(once))])
    assert twice == once
    assert np.asarray(twice, dtype="U1").tobytes() == np.asarray(once, dtype="U1").tobytes()


def test_cli_writes_byte_identical_output_for_repeated_input(tmp_path, monkeypatch) -> None:
    import pandas as pd

    from tools import postprocess as module

    n_frames = module.games.source_frames()
    source = tmp_path / "all_x.csv"
    first = tmp_path / "first.csv"
    second = tmp_path / "second.csv"
    pd.DataFrame({"frame": np.arange(n_frames), "label": "X"}).to_csv(source, index=False)
    monkeypatch.setattr(module, "_match_runs", lambda: [(10, n_frames - 10)])

    assert module.main([str(source), str(first)]) == 0
    assert module.main([str(source), str(second)]) == 0
    assert first.read_bytes() == second.read_bytes()


@pytest.mark.parametrize(
    "runs",
    [[(-1, 2)], [(2, 2)], [(2, 1)], [(0, 4), (3, 5)], [(0, 8)]],
)
def test_rejects_invalid_runs(runs: list[tuple[int, int]]) -> None:
    with pytest.raises(ValueError):
        postprocess(["H"] * 5, runs)


def test_rejects_unknown_labels() -> None:
    with pytest.raises(ValueError):
        postprocess(["H", "?", "A"], [(0, 3)])
