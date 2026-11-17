"""Prove the code graph is buildable -- and cannot become part of the repository.

`make graph` writes `graphify-out/`; this module is the check CI runs around it. The failure worth
catching is not "graphify crashed": it exits non-zero and says why. The failures that need a test
are the silent ones.

1. **The graph did not get built, or the schema moved.** A missing, unparsable or node-less
   `graph.json` means the map is empty while the job is green. The edges live under `links` and the
   build commit under `built_at_commit`; a file without those keys is a graphify version this check
   does not understand, and guessing would hide it.
2. **The graph became committable.** `graphify-out/` must stay in `.gitignore`. If that line is
   ever dropped, the next `git add -A` publishes a derived snapshot into the submission repo, and
   nothing else in the suite would notice.
3. **The graph describes another commit.** `graph.json.built_at_commit` and the line in
   `GRAPH_REPORT.md` must both name `HEAD`. A mismatch anywhere means the map a reader trusts is
   describing code that has moved, or that the two files disagree with each other.

Only the standard library: this check runs in CI before the environment exists, and it is about
files and git, not about numpy.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_OUT = REPO_ROOT / "graphify-out"
COMMIT_LINE = re.compile(r"Built from commit:\s*`([0-9a-fA-F]+)`")
SHORT = 8


class CheckError(Exception):
    """The graph could not even be read, so there is nothing to summarise."""


@dataclass(frozen=True)
class Summary:
    """What a reader wants to know about a graph, in one line."""

    nodes: int
    edges: int
    commit: str | None


def _graph(out: Path) -> tuple[dict, list[str]]:
    """The parsed graph, or the reasons it could not be parsed."""
    path = out / "graph.json"
    if not path.is_file():
        return {}, [f"{path} is missing -- run `make graph`"]
    try:
        graph = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError) as problem:
        return {}, [f"{path} is not valid JSON ({problem})"]
    if not isinstance(graph, dict):
        return {}, [f"{path} is not a JSON object"]
    # `links`, not `edges`, and the commit is stored as `built_at_commit`: the real schema, not the
    # one a reasonable person would guess. A graph without them is a version this check does not
    # read, and a silent zero would look like an empty repository.
    missing = [key for key in ("nodes", "links") if not isinstance(graph.get(key), list)]
    if missing:
        return graph, [f"{path}: no {missing} list -- the graph schema changed"]
    return graph, []


def built_commit(graph: dict) -> str | None:
    """The commit graph.json was built from, or None if this graphify did not record one."""
    commit = graph.get("built_at_commit")
    return commit if isinstance(commit, str) and commit else None


def report_commit(out: Path) -> str | None:
    """The commit named in GRAPH_REPORT.md, or None when the report is missing or unversioned."""
    path = out / "GRAPH_REPORT.md"
    if not path.is_file():
        return None
    match = COMMIT_LINE.search(path.read_text(encoding="utf-8", errors="replace"))
    return match.group(1) if match else None


def head_commit(root: Path) -> str | None:
    """`HEAD` of `root`, abbreviated the way graphify writes it. None outside a git checkout."""
    try:
        done = subprocess.run(
            ["git", "-C", str(root), "rev-parse", "--short=8", "HEAD"],
            capture_output=True,
            text=True,
        )
    except OSError:
        return None
    if done.returncode != 0:
        return None
    return done.stdout.strip() or None


def ignored(root: Path, path: Path) -> bool:
    """Is `path` covered by an ignore rule? `git check-ignore` is the only answer that matters."""
    try:
        done = subprocess.run(
            ["git", "-C", str(root), "check-ignore", "-q", str(path)],
            capture_output=True,
        )
    except OSError:
        return False
    return done.returncode == 0


def summary(out: Path) -> Summary:
    """Counts and build commit of a readable graph. Raises CheckError when there is none."""
    graph, problems = _graph(out)
    if problems:
        raise CheckError(problems[0])
    return Summary(
        nodes=len(graph["nodes"]),
        edges=len(graph["links"]),
        commit=built_commit(graph) or report_commit(out),
    )


def problems(out: Path, root: Path | None = None) -> list[str]:
    """Every way the graph output fails to be usable, as readable strings."""
    out = Path(out)
    root = Path(root) if root is not None else out.resolve().parent

    graph, found = _graph(out)
    if found:
        return found

    if not graph["nodes"]:
        found.append(f"{out / 'graph.json'}: no nodes -- the extractor found no symbols")
    if not ignored(root, out / "graph.json"):
        found.append(
            f"{out} is not ignored by git -- `make graph` output would be committed. "
            "Add it back to .gitignore."
        )

    commit = built_commit(graph)
    in_report = report_commit(out)
    report_path = out / "GRAPH_REPORT.md"

    if commit is None:
        found.append(f"{out / 'graph.json'}: no built_at_commit -- cannot tell what it maps")
    if not report_path.is_file():
        found.append(f"{report_path} is missing -- `make graph` writes it")
    elif in_report is None:
        found.append(f"{report_path}: no 'Built from commit' line")
    elif commit is not None and in_report[:SHORT] != commit[:SHORT]:
        found.append(
            f"GRAPH_REPORT.md says {in_report[:SHORT]}, graph.json says {commit[:SHORT]} -- "
            "re-cluster so the report matches the graph"
        )

    named = commit or in_report
    head = head_commit(root)
    if named is not None and head is not None and named[:SHORT] != head[:SHORT]:
        found.append(
            f"the graph was built from {named[:SHORT]}, but HEAD is {head} -- rebuild with "
            "`make graph`"
        )
    return found


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Check the code graph in graphify-out/")
    parser.add_argument("--out", default=str(DEFAULT_OUT), help=f"graph directory ({DEFAULT_OUT})")
    args = parser.parse_args(argv)

    out = Path(args.out)
    found = problems(out)
    if found:
        print(f"the code graph is not usable ({len(found)} problem(s))", file=sys.stderr)
        for problem in found:
            print(f"  - {problem}", file=sys.stderr)
        return 1

    built = summary(out)
    share = f", built from {built.commit[:SHORT]}" if built.commit else ""
    print(f"code graph ok: {built.nodes} nodes, {built.edges} edges{share}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
