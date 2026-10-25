"""The code-graph check: buildable, and impossible to commit.

`make graph` writes `graphify-out/`; this is what CI runs, and the interesting failure is not
"graphify crashed" -- it exits non-zero and says why. The failures worth a test are the silent
ones: the graph quietly becoming a tracked file, or describing a different commit than the tree it
ships with.

The synthetic files below copy the real schema (`nodes`, `links`, `built_at_commit`), which is not
the obvious one: the first version of this check counted `edges`, read zero, and passed.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from tools import check_graph

HEAD = "8b970a79"
FULL_COMMIT = "8b970a79aa11bb22cc33dd44ee55ff66aa77bb88"


def out_dir(root: Path) -> Path:
    return root / "graphify-out"


def write_graph(
    root: Path, nodes: int = 3, links: int = 2, commit: str | None = FULL_COMMIT
) -> Path:
    out = out_dir(root)
    out.mkdir(parents=True, exist_ok=True)
    graph = {
        "directed": False,
        "multigraph": False,
        "graph": {},
        "nodes": [{"id": f"n{i}", "label": f"n{i}"} for i in range(nodes)],
        "links": [{"source": "n0", "target": "n1", "relation": "calls"} for _ in range(links)],
        "hyperedges": [],
    }
    if commit is not None:
        graph["built_at_commit"] = commit
    path = out / "graph.json"
    path.write_text(json.dumps(graph), encoding="utf-8")
    return path


def write_report(root: Path, commit: str = HEAD) -> Path:
    out = out_dir(root)
    out.mkdir(parents=True, exist_ok=True)
    path = out / "GRAPH_REPORT.md"
    path.write_text(
        "# Graph Report\n\n## Graph Freshness\n"
        f"- Built from commit: `{commit}`\n"
        "- Run `graphify update .` after code changes (no API cost).\n",
        encoding="utf-8",
    )
    return path


@pytest.fixture
def clean(monkeypatch) -> None:
    """Pretend the output is ignored and HEAD is the commit the graph names."""
    monkeypatch.setattr(check_graph, "head_commit", lambda root: HEAD)
    monkeypatch.setattr(check_graph, "ignored", lambda root, path: True)


def test_a_fresh_graph_passes(tmp_path: Path, clean: None) -> None:
    write_graph(tmp_path)
    write_report(tmp_path)

    assert check_graph.problems(out_dir(tmp_path)) == []


def test_summary_counts_links_and_reads_the_build_commit(tmp_path: Path, clean: None) -> None:
    write_graph(tmp_path, nodes=5, links=4)
    write_report(tmp_path)

    summary = check_graph.summary(out_dir(tmp_path))
    assert (summary.nodes, summary.edges) == (5, 4)
    assert summary.commit == FULL_COMMIT


def test_a_missing_graph_is_a_problem(tmp_path: Path, clean: None) -> None:
    write_report(tmp_path)

    assert any("graph.json" in problem for problem in check_graph.problems(out_dir(tmp_path)))


def test_an_empty_graph_is_a_problem(tmp_path: Path, clean: None) -> None:
    """Zero nodes means the extractor found nothing -- a green build of an empty map."""
    write_graph(tmp_path, nodes=0, links=0)
    write_report(tmp_path)

    assert any("no nodes" in problem for problem in check_graph.problems(out_dir(tmp_path)))


def test_a_graph_that_is_not_json_is_a_problem(tmp_path: Path, clean: None) -> None:
    out = out_dir(tmp_path)
    out.mkdir()
    (out / "graph.json").write_text("{not json", encoding="utf-8")
    write_report(tmp_path)

    assert any("not valid JSON" in problem for problem in check_graph.problems(out))


def test_the_schema_is_checked_not_guessed(tmp_path: Path, clean: None) -> None:
    """`edges` is the name a reasonable person would use, and it is not the name graphify uses."""
    out = out_dir(tmp_path)
    out.mkdir()
    (out / "graph.json").write_text(
        json.dumps({"nodes": [{"id": "n0"}], "edges": [{"source": "n0"}]}), encoding="utf-8"
    )
    write_report(tmp_path)

    assert any("schema changed" in problem for problem in check_graph.problems(out))


def test_a_committable_graph_is_a_problem(tmp_path: Path, clean: None, monkeypatch) -> None:
    """The whole point of .gitignore: if the output is not ignored, CI has to say so."""
    write_graph(tmp_path)
    write_report(tmp_path)
    monkeypatch.setattr(check_graph, "ignored", lambda root, path: False)

    assert any("not ignored" in problem for problem in check_graph.problems(out_dir(tmp_path)))


def test_a_graph_from_another_commit_is_a_problem(tmp_path: Path, clean: None) -> None:
    write_graph(tmp_path, commit="deadbeef" + "0" * 32)
    write_report(tmp_path, commit="deadbeef")

    problems = check_graph.problems(out_dir(tmp_path))
    assert any("deadbeef" in problem and HEAD in problem for problem in problems)


def test_a_missing_report_is_a_problem(tmp_path: Path, clean: None) -> None:
    write_graph(tmp_path)

    assert any("GRAPH_REPORT.md" in problem for problem in check_graph.problems(out_dir(tmp_path)))


def test_a_report_without_a_commit_is_a_problem(tmp_path: Path, clean: None) -> None:
    write_graph(tmp_path)
    (out_dir(tmp_path) / "GRAPH_REPORT.md").write_text("# Graph Report\n", encoding="utf-8")

    assert any(
        "Built from commit" in problem for problem in check_graph.problems(out_dir(tmp_path))
    )


def test_a_report_that_disagrees_with_the_graph_is_a_problem(
    tmp_path: Path, clean: None, monkeypatch
) -> None:
    """Both files are written by one run; if they disagree, one of them is stale."""
    write_graph(tmp_path, commit=FULL_COMMIT)
    write_report(tmp_path, commit="cafebabe")
    monkeypatch.setattr(check_graph, "head_commit", lambda root: "cafebabe")

    problems = check_graph.problems(out_dir(tmp_path))
    assert any("GRAPH_REPORT.md says cafebabe" in problem for problem in problems)


def test_a_graph_without_a_commit_cannot_be_dated(tmp_path: Path, clean: None) -> None:
    write_graph(tmp_path, commit=None)
    write_report(tmp_path)

    assert any("built_at_commit" in problem for problem in check_graph.problems(out_dir(tmp_path)))


def test_cli_is_loud_on_success_and_on_failure(
    tmp_path: Path, clean: None, capsys: pytest.CaptureFixture
) -> None:
    write_graph(tmp_path)
    write_report(tmp_path)
    out = str(out_dir(tmp_path))

    assert check_graph.main(["--out", out]) == 0
    assert "3 nodes" in capsys.readouterr().out

    write_report(tmp_path, commit="deadbeef")
    assert check_graph.main(["--out", out]) == 1
    assert "deadbeef" in capsys.readouterr().err
