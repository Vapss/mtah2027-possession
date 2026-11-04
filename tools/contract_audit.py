"""#21 A4: full-match contract test for the delivered submission.

    python tools/contract_audit.py --submission submissions/engine.csv \\
        --artifact runs/engine/artifacts/engine.csv \\
        --ball-artifact artifacts/possession.csv \\
        --write docs/analysis/contract-audit.md

Why
---
The public slice is 17 possessions in five minutes and the ball is detected on 88.2% of its
frames; the full match is 56.9%. A defect that only appears where the ball is missing cannot be
seen in the slice, and the transplant bank reuses the same 17 possessions. This tool asks a
different question, at full-match scale: is the delivered file structurally *possible* under the
documented policy? It never reads the ground truth, the video, the Smart Tagging or the ball's
coordinates -- only the submission, the artifact, and per-frame ball presence.

The four gates are pre-registered in `docs/experiments/contrato-partido-completo.md`; the
thresholds are written there before the first run and are not swept.

What it does not do
-------------------
It does not score. A pass means "no impossible structure", not "correct possession". A fail
localises the frames and the ball gap; the decision it feeds is the lead's, never an automatic
parameter change.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

import games  # noqa: E402

FPS = int(games.GAMES[games.GAME]["fps"])
N_FRAMES = games.GAMES[games.GAME]["n_video_frames"]
LABELS = ("H", "A", "D", "X")
LONG_SPELL_FRAMES = 300 * FPS  # T2: no possession may last five minutes
LONG_GAP_FRAMES = 500  # T3: the band #10 could not measure in the slice
BLOCK_FRAMES = 5 * 60 * FPS  # T4: the same 5-minute blocks as tools/blocks.py
MAX_D_BLOCK = 0.85  # T4


@dataclass(frozen=True)
class Spell:
    start: int  # inclusive
    stop: int  # exclusive
    label: str

    @property
    def frames(self) -> int:
        return self.stop - self.start


@dataclass(frozen=True)
class Gap:
    start: int
    stop: int

    @property
    def frames(self) -> int:
        return self.stop - self.start


@dataclass
class Finding:
    gate: str
    passed: bool
    detail: str
    frames: list[tuple[int, int]] = field(default_factory=list)


@dataclass
class Audit:
    findings: list[Finding]
    spells: list[Spell]
    gaps: list[Gap]
    long_gaps: list[Gap]
    blocked: list[dict[str, float | int]] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return all(finding.passed for finding in self.findings)


def spells(labels: Sequence[str]) -> list[Spell]:
    """Maximal runs of the same H or A label; D and X break a possession."""
    out: list[Spell] = []
    start = 0
    for index in range(1, len(labels) + 1):
        if index == len(labels) or labels[index] != labels[start]:
            if labels[start] in ("H", "A"):
                out.append(Spell(start, index, labels[start]))
            start = index
    return out


def gaps(present: Sequence[bool]) -> list[Gap]:
    """Maximal runs with no ball observed, half-open."""
    out: list[Gap] = []
    start: int | None = None
    for index, seen in enumerate(present):
        if not seen and start is None:
            start = index
        elif seen and start is not None:
            out.append(Gap(start, index))
            start = None
    if start is not None:
        out.append(Gap(start, len(present)))
    return out


def artifact_labels(artifact: pd.DataFrame) -> np.ndarray:
    """The labels `tools/assemble.py` would read from an artifact (no threshold)."""
    probability = artifact[["p_home", "p_away", "p_dead"]].to_numpy(dtype=float)
    labels = np.array(["H", "A", "D"])[probability.argmax(axis=1)]
    labels[artifact["confidence"].to_numpy(dtype=float) <= 0.0] = "X"
    return labels


def ball_from_artifact(artifact: pd.DataFrame) -> np.ndarray:
    """`confidence = max(p_home, p_away) * ball_present`, so zero means no ball observed."""
    return artifact["confidence"].to_numpy(dtype=float) > 0.0


def ball_from_tracking() -> np.ndarray:
    """Ball presence from the licensed bundle, the same source `tools/blocks.py` uses."""
    from tools import atd

    return atd.load(games.DEFAULT_SOURCE).ball()[1]


def halves() -> list[tuple[int, int, int]]:
    return [(half, start, stop + 1) for half, start, stop in games.half_video_blocks(games.GAME)]


def audit(
    labels: Sequence[str],
    present: Sequence[bool],
    frames: Sequence[int] | None = None,
    half_spans: Sequence[tuple[int, int, int]] | None = None,
    from_artifact: Sequence[str] | None = None,
    expected_frames: int | None = None,
) -> Audit:
    """Run the four pre-registered gates on aligned arrays."""
    labels = list(labels)
    present = list(present)
    n = len(labels)
    expected = N_FRAMES if expected_frames is None else expected_frames
    frames = list(range(n)) if frames is None else list(frames)
    half_spans = halves() if half_spans is None else list(half_spans)
    findings: list[Finding] = []

    # T1 -- file contract.
    problems: list[str] = []
    if n != expected:
        problems.append(f"{n} filas, se esperaban {expected}")
    if frames != list(range(n)):
        problems.append("los frames no son 0..n-1 en orden")
    if any(label not in LABELS for label in labels):
        problems.append("hay una etiqueta fuera de {H,A,D,X}")
    inside = np.zeros(n, dtype=bool)
    for _half, start, stop in half_spans:
        inside[start:stop] = True
    array = np.asarray(labels)
    x_inside = int(np.sum((array == "X") & inside))
    if x_inside:
        problems.append(f"{x_inside} X dentro de una mitad")
    if from_artifact is not None and not np.array_equal(array, np.asarray(from_artifact)):
        mismatch = int(np.sum(array != np.asarray(from_artifact)))
        problems.append(f"{mismatch} frames difieren del artefacto")
    findings.append(
        Finding("T1 contrato del archivo", not problems, "; ".join(problems) or "cumple")
    )

    # T2 -- no possession longer than five minutes.
    possession = spells(labels)
    long_spells = [spell for spell in possession if spell.frames >= LONG_SPELL_FRAMES]
    detail = (
        f"{len(long_spells)} posesiones ≥ {LONG_SPELL_FRAMES} frames; "
        f"la más larga {max((s.frames for s in possession), default=0)} frames"
    )
    findings.append(
        Finding(
            "T2 ninguna posesión > 5 min",
            not long_spells,
            detail,
            [(spell.start, spell.stop) for spell in long_spells],
        )
    )

    # T3 -- no direct H<->A transition inside a long ball gap.
    ball_gaps = gaps(present)
    long_gaps = [gap for gap in ball_gaps if gap.frames >= LONG_GAP_FRAMES]
    direct: list[tuple[int, int]] = []
    restarts = 0
    for gap in long_gaps:
        for index in range(gap.start + 1, gap.stop):
            before, after = labels[index - 1], labels[index]
            if before in ("H", "A") and after in ("H", "A") and before != after:
                direct.append((index, gap.frames))
            elif before == "D" and after in ("H", "A"):
                restarts += 1
    findings.append(
        Finding(
            "T3 transiciones sin balón",
            not direct,
            f"{len(long_gaps)} huecos ≥ {LONG_GAP_FRAMES} frames; "
            f"{len(direct)} transiciones H<->A dentro; {restarts} D->H/A (reanudaciones)",
            [(index, index + 1) for index, _ in direct],
        )
    )

    # T4 -- no degenerate 5-minute block.
    blocked: list[dict[str, float | int]] = []
    bad_blocks: list[int] = []
    for half, start, stop in half_spans:
        for first in range(start, stop, BLOCK_FRAMES):
            last = min(first + BLOCK_FRAMES, stop)
            block = array[first:last]
            dead = float(np.mean(block == "D")) if last > first else 0.0
            starts = sum(1 for spell in possession if first <= spell.start < last)
            blocked.append(
                {
                    "half": half,
                    "start": first,
                    "stop": last,
                    "dead": round(dead, 3),
                    "possessions": starts,
                }
            )
            if dead > MAX_D_BLOCK or starts == 0:
                bad_blocks.append(len(blocked))
    findings.append(
        Finding(
            "T4 ningún bloque degenerado",
            not bad_blocks,
            f"{len(blocked)} bloques; {len(bad_blocks)} fuera de gate"
            + (f" ({bad_blocks})" if bad_blocks else ""),
        )
    )

    return Audit(findings, possession, ball_gaps, long_gaps, blocked)


def _git_commit() -> str | None:
    try:
        return subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=REPO_ROOT,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return None


def report(result: Audit, command: str, source: str) -> str:
    commit = _git_commit()
    origin = f" desde el commit `{commit}`" if commit else ""
    lines = [
        "# Contrato a escala completa: la entrega en los 199.319 frames",
        "",
        f"Generado por `{command}`{origin}. No se edita a mano.",
        "",
        "Pre-registro: `docs/experiments/contrato-partido-completo.md`.",
        "No lee ground truth, video, Smart Tagging ni coordenadas: solo la submission, el",
        "artefacto y la presencia de balón.",
        "",
        f"**Insumo:** {source}",
        "",
        "## Veredicto",
        "",
        "| gate | resultado | detalle |",
        "|---|---|---|",
    ]
    for finding in result.findings:
        lines.append(
            f"| {finding.gate} | {'pasa' if finding.passed else '**falla**'} | {finding.detail} |"
        )
    lines += ["", f"**{'PASA' if result.passed else 'FALLA'}** el contrato estructural.", ""]
    lines += [
        "Una falla de T1 es mecánica: dice dónde el archivo no cumple el contrato, no que la",
        "etiqueta",
        "sea incorrecta. El scorer oficial rellena las `X` dentro de una mitad con la etiqueta",
        "anterior",
        "(y con la primera conocida al inicio), así que la métrica de ranking puede no",
        "moverse; las",
        "métricas por frame sí las cobran. Ningún umbral se ajusta acá: la decisión es del lead.",
        "",
    ]

    longest = sorted(result.spells, key=lambda spell: spell.frames, reverse=True)[:5]
    lines += [
        "## Posesiones más largas",
        "",
        "| inicio | fin | frames | segundos | equipo |",
        "|---:|---:|---:|---:|:---:|",
    ]
    for spell in longest:
        lines.append(
            f"| {spell.start} | {spell.stop} | {spell.frames} | {spell.frames / FPS:.1f} "
            f"| {spell.label} |"
        )

    lines += [
        "",
        "## Huecos de balón",
        "",
        f"- Huecos: {len(result.gaps)}; el más largo "
        f"{max((gap.frames for gap in result.gaps), default=0)} frames.",
        f"- Huecos >= {LONG_GAP_FRAMES} frames: {len(result.long_gaps)}.",
    ]
    if result.long_gaps:
        lines += ["", "| inicio | fin | frames | segundos |", "|---:|---:|---:|---:|"]
        for gap in result.long_gaps[:10]:
            lines.append(f"| {gap.start} | {gap.stop} | {gap.frames} | {gap.frames / FPS:.1f} |")
        if len(result.long_gaps) > 10:
            lines.append(f"| ... | | | ({len(result.long_gaps) - 10} mas) |")

    lines += [
        "",
        "## Bloques de 5 minutos",
        "",
        "| # | mitad | inicio | %D | posesiones |",
        "|---:|---:|---:|---:|---:|",
    ]
    for index, block in enumerate(result.blocked, start=1):
        lines.append(
            f"| {index} | {block['half']} | {block['start']} | {block['dead']:.1%} "
            f"| {block['possessions']} |"
        )
    lines.append("")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Full-match contract test for a submission")
    parser.add_argument("--submission", type=Path, required=True)
    parser.add_argument("--artifact", type=Path, help="the job artifact the submission came from")
    parser.add_argument(
        "--ball-artifact",
        type=Path,
        help="an emission artifact whose confidence encodes ball presence (confidence > 0)",
    )
    parser.add_argument(
        "--from-tracking",
        action="store_true",
        help="read ball presence from the licensed bundle instead of an artifact",
    )
    parser.add_argument("--write", type=Path, help="write the markdown report here")
    parser.add_argument("--json", type=Path, help="write the machine-readable result here")
    args = parser.parse_args(argv)

    submission = pd.read_csv(args.submission)
    if list(submission.columns) != ["frame", "label"]:
        print("submission must have exactly frame,label", file=sys.stderr)
        return 1
    labels = submission["label"].astype(str).str.upper().to_numpy()

    from_artifact = None
    if args.artifact:
        artifact = pd.read_csv(args.artifact)
        from_artifact = artifact_labels(artifact)

    if args.ball_artifact:
        ball = ball_from_artifact(pd.read_csv(args.ball_artifact))
        source = f"presencia de balón desde `{args.ball_artifact}` (confidence > 0)"
    elif args.from_tracking:
        ball = ball_from_tracking()
        source = "presencia de balón desde el bundle licenciado (`atd.load(...).ball()`)"
    else:
        print("give --ball-artifact or --from-tracking", file=sys.stderr)
        return 1

    result = audit(
        labels,
        ball,
        frames=submission["frame"].to_numpy(),
        from_artifact=from_artifact,
        expected_frames=len(submission),
    )
    pieces = ["python tools/contract_audit.py"]
    for flag, value in (
        ("--submission", args.submission),
        ("--artifact", args.artifact),
        ("--ball-artifact", args.ball_artifact),
    ):
        if value:
            pieces += [flag, str(value)]
    if args.from_tracking:
        pieces.append("--from-tracking")
    command = " ".join(pieces)
    text = report(result, command, source)
    print(text)
    if args.write:
        args.write.parent.mkdir(parents=True, exist_ok=True)
        args.write.write_text(text, encoding="utf-8")
    if args.json:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(
            json.dumps(
                {
                    "passed": result.passed,
                    "findings": [
                        {"gate": f.gate, "passed": f.passed, "detail": f.detail}
                        for f in result.findings
                    ],
                },
                indent=2,
            ),
            encoding="utf-8",
        )
    return 0 if result.passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
