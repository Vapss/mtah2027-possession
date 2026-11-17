"""F0a: the whole chain -- artifact, submission, validation, score -- in one checked run.

Ticket #20 F0a asks for one thing before any modelling: prove that the path
`artifact -> submission -> validate -> score` closes, and that the number it produces is the
one the evaluation harness already publishes. A baseline that ships with the repository is the
input; no match data and no new dependency is involved.

    python tools/f0a.py                    # -> runs/f0a/, ledger entry in runs/ledger.jsonl
    python tools/f0a.py --artifact artifacts/engine.csv       # same chain, real artifact
    make f0a                               # both: the pinned baseline, then the real artifact
    make f0a ARTIFACT=artifacts/engine.csv

The baseline mode fails, loudly, when any of these stop being true:

1. The official validator accepts the assembled file.
2. `spellF1` and `macroF1` equal the pinned public-slice values. A drift here means the
   assembly path changed, not the model: F0a does not train or tune anything.
3. Rebuilding the artifact and the submission from scratch produces byte-identical files, so
   `make submission` cannot silently depend on leftover state.

The artifact mode runs the same validator, determinism check and score with a job's own artifact
(by default `artifacts/engine.csv`, the possession engine's). Its metrics are not pinned because
they come from the model, not from the assembly path; the ledger line carries the artifact hash.
When the licensed bundle is absent the artifact is missing, and the mode skips with a message
instead of failing -- the pipeline's correctness is already covered by the pinned baseline run.

Why its own directory. The documented chain writes into `artifacts/`, which also holds the real
possession artifact (`artifacts/engine.csv`). Overwriting that with a baseline would destroy it,
so F0a keeps its inputs and outputs under `runs/f0a/`, which is gitignored and disposable. The
canonical commands stay as they are.
"""

from __future__ import annotations

import argparse
import hashlib
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parent.parent
BASELINE = REPO_ROOT / "evaluation" / "results" / "baseline_smooth50.csv"
WORKDIR = REPO_ROOT / "runs" / "f0a"
ARTIFACT_NAME = "baseline_smooth50.csv"

# Published public-window score of `baseline_smooth50` (README board, EVALUATION.md). The public
# ground truth is 5 minutes and 17 possessions: this is a pipeline check, never a claim about
# generalisation to the full match.
EXPECTED_SPELL_F1 = 0.325581
EXPECTED_MACRO_F1 = 0.620733
TOLERANCE = 1e-6


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _run(args: list[object], *, capture: bool = False) -> subprocess.CompletedProcess:
    """Run one step with this interpreter, and turn a failure into the exact command and output."""
    command = [str(part) for part in args]
    completed = subprocess.run(
        [sys.executable, *command], cwd=REPO_ROOT, text=True, capture_output=capture
    )
    if completed.returncode != 0:
        detail = ((completed.stderr or "") + (completed.stdout or "")).strip()
        suffix = f":\n{detail}" if detail else ""
        raise RuntimeError(f"{' '.join(command)} exited {completed.returncode}{suffix}")
    return completed


def _check_workdir(workdir: Path, allowed: str) -> None:
    """Refuse to mix F0a's single artifact with someone else's files."""
    artifacts = workdir / "artifacts"
    if not artifacts.is_dir():
        return
    foreign = sorted(path.name for path in artifacts.glob("*.csv") if path.name != allowed)
    if foreign:
        raise ValueError(
            f"{artifacts} already holds {foreign}; use a clean --workdir so the scored "
            "submission is F0a's artifact and nothing else"
        )


def build_submission(source: Path, workdir: Path, *, encode: bool) -> tuple[Path, Path]:
    """Copy or encode one artifact and assemble it, returning (artifact, submission)."""
    name = ARTIFACT_NAME if encode else source.name
    _check_workdir(workdir, name)
    artifacts = workdir / "artifacts"
    artifacts.mkdir(parents=True, exist_ok=True)
    artifact = artifacts / name
    submission = workdir / "submission.csv"

    if encode:
        _run(["tools/onehot.py", source, "-o", artifact], capture=True)
    else:
        shutil.copyfile(source, artifact)
    _run(
        [
            "tools/assemble.py",
            "--artifacts",
            artifacts,
            "-o",
            submission,
            "--json",
            workdir / "submission_summary.json",
        ],
        capture=True,
    )
    return artifact, submission


def check_expected(
    row: pd.Series,
    expected_spell_f1: float | None,
    expected_macro_f1: float | None,
    tolerance: float,
) -> None:
    """Fail with both numbers when the chain no longer reproduces a pinned public-slice score."""
    expected = {
        name: value
        for name, value in (
            ("spell_f1_mean", expected_spell_f1),
            ("macro_f1", expected_macro_f1),
        )
        if value is not None
    }
    if not expected:
        return
    actual = {name: float(row[name]) for name in expected}
    wrong = {
        name: {"expected": expected[name], "actual": value}
        for name, value in actual.items()
        if abs(value - expected[name]) > tolerance
    }
    if wrong:
        raise ValueError(
            "the assembled submission does not reproduce the pinned public-slice value:\n"
            f"{wrong}\n"
            "F0a encodes a shipped baseline, so the difference is in the assembly path "
            "(onehot/assemble), not in a model."
        )


def run(
    *,
    baseline: Path,
    artifact_path: Path | None,
    workdir: Path,
    bootstrap: int,
    ledger: Path | None,
    note: str,
    expected_spell_f1: float | None,
    expected_macro_f1: float | None,
    tolerance: float,
) -> dict[str, object]:
    workdir.mkdir(parents=True, exist_ok=True)
    source = baseline if artifact_path is None else artifact_path
    encode = artifact_path is None

    artifact, submission = build_submission(source, workdir, encode=encode)

    validation = _run(["evaluation/validate_submission.py", submission], capture=True)
    validator_line = (validation.stdout or "").strip().splitlines()[-1]

    with tempfile.TemporaryDirectory(prefix="rerun-", dir=workdir) as temporary:
        second_artifact, second_submission = build_submission(
            source, Path(temporary), encode=encode
        )
        if second_artifact.read_bytes() != artifact.read_bytes():
            raise ValueError(f"{artifact} is not byte-identical when rebuilt")
        if second_submission.read_bytes() != submission.read_bytes():
            raise ValueError(f"{submission} is not byte-identical when rebuilt")

    score_command: list[object] = [
        "tools/score.py",
        "--results",
        workdir,
        "--out",
        workdir / "score",
        "--bootstrap",
        bootstrap,
        "--config",
        "configs/assemble_default.json",
        "--note",
        note,
    ]
    if ledger is None:
        score_command.append("--no-ledger")
    else:
        score_command += ["--ledger", ledger]
    _run(score_command, capture=True)

    board = pd.read_csv(workdir / "score" / "scoreboard.csv")
    row = board.loc[board["submission"] == submission.stem]
    if len(row) != 1:
        raise ValueError(f"expected one scoreboard row for {submission.stem}, found {len(row)}")
    row = row.iloc[0]
    check_expected(row, expected_spell_f1, expected_macro_f1, tolerance)

    return {
        "artifact": artifact,
        "submission": submission,
        "artifact_sha256": _sha256(artifact),
        "submission_sha256": _sha256(submission),
        "validator": validator_line,
        "spell_f1": float(row["spell_f1_mean"]),
        "macro_f1": float(row["macro_f1"]),
        "poss": int(row["poss"]),
        "ledger": ledger,
        "mode": "baseline" if encode else "artifact",
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline", default=str(BASELINE), help="frame,label CSV to encode")
    parser.add_argument(
        "--artifact",
        default=None,
        help="job artifact to take through the same chain (e.g. artifacts/engine.csv); "
        "missing means skip, because it needs the licensed bundle",
    )
    parser.add_argument("--workdir", default=None, help="disposable F0a workspace")
    parser.add_argument("--bootstrap", type=int, default=1000, help="segment-bootstrap draws")
    parser.add_argument("--ledger", default=str(REPO_ROOT / "runs" / "ledger.jsonl"))
    parser.add_argument("--no-ledger", action="store_true")
    parser.add_argument("--note", default=None)
    parser.add_argument("--expected-spell-f1", type=float, default=None)
    parser.add_argument("--expected-macro-f1", type=float, default=None)
    parser.add_argument("--tolerance", type=float, default=TOLERANCE)
    args = parser.parse_args(argv)

    artifact_path = Path(args.artifact) if args.artifact else None
    if artifact_path is not None and not artifact_path.is_file():
        print(
            f"SKIP f0a artifact: {artifact_path} is missing -- it needs the licensed tactical "
            "bundle (python tools/engine.py --out artifacts/engine.csv); nothing scored"
        )
        return 0

    if args.workdir:
        workdir = Path(args.workdir)
    else:
        workdir = WORKDIR if artifact_path is None else WORKDIR / "artifact"
    if args.note:
        note = args.note
    elif artifact_path is None:
        note = "f0a"
    else:
        note = f"f0a artifact {_sha256(artifact_path)[:12]}"

    expected_spell = args.expected_spell_f1
    expected_macro = args.expected_macro_f1
    if artifact_path is None:
        # The shipped baseline has published values, so the pipeline check is exact. A job's own
        # artifact has whatever score the model produces; pinning it here would hide regressions
        # or invent agreement.
        expected_spell = EXPECTED_SPELL_F1 if expected_spell is None else expected_spell
        expected_macro = EXPECTED_MACRO_F1 if expected_macro is None else expected_macro

    ledger = None if args.no_ledger else Path(args.ledger)
    try:
        result = run(
            baseline=Path(args.baseline),
            artifact_path=artifact_path,
            workdir=workdir,
            bootstrap=args.bootstrap,
            ledger=ledger,
            note=note,
            expected_spell_f1=expected_spell,
            expected_macro_f1=expected_macro,
            tolerance=args.tolerance,
        )
    except (OSError, RuntimeError, ValueError, KeyError) as error:
        print(f"FAIL f0a: {error}", file=sys.stderr)
        return 1

    print(
        f"OK f0a [{result['mode']}] spellF1 {result['spell_f1']:.6f}  "
        f"macroF1 {result['macro_f1']:.6f}  poss {result['poss']}"
    )
    print(f"  artifact   {result['artifact']}  sha256 {result['artifact_sha256']}")
    print(f"  submission {result['submission']}  sha256 {result['submission_sha256']}")
    print(f"  validator  {result['validator']}")
    print("  rebuild    byte-identical artifact and submission")
    if result["ledger"] is not None:
        print(f"  ledger     {result['ledger']}")
    print(
        "  note       public slice: 17 possessions, diagnostic only -- not a generalisation claim"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
