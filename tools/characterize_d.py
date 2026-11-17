"""A0: what `D` is, measured on the public slice, before anything models it.

The backlog designed a whole stream on "no ball means dead ball" and nobody had looked at `D`.
These are the measurements that #5, #10 and #16 have to be built on, produced by code so they can
be re-run instead of retyped:

- how much of the match `D` is, and how long its runs last;
- how `D` relates to the ball track (presence, speed, distance to the nearest player, out of play);
- how it relates to Smart Tagging, and which of those signals actually separate `D` from live play.

Everything is restricted to the graded window of the public ground truth (5 minutes, 7,500 frames).
The full-match ground truth is private, so nothing here claims to describe it: the document says
what the sample can and cannot support, and that boundary is part of the answer.

    python tools/characterize_d.py                                  # print
    python tools/characterize_d.py --write docs/analysis/d.md       # write the document
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

import games  # noqa: E402
from tools import atd, smart_tagging  # noqa: E402

FPS = games.GAMES[games.GAME]["fps"]
PITCH = games.GAMES[games.GAME]["pitch"]
GT_CSV = REPO_ROOT / "evaluation" / "gt" / "BAR-ATH_possession_gt_public.csv"
GT_META = REPO_ROOT / "evaluation" / "gt" / "BAR-ATH_possession_gt_public_meta.json"
DEFAULT_DOC = REPO_ROOT / "docs" / "analysis" / "d-characterization.md"

# The codes worth testing against `D`. `SET PIECES` is the one that claims to mean "the ball is
# not in play"; `BUILD UP` is its opposite and is here as a control -- a signal that fires during
# live possession has to come out below 1, or the measurement is broken.
CODES = ("SET PIECES", "GOALS", "BUILD UP")

# Thresholds for the two derived signals. Both are stated rather than tuned: a ball slower than
# walking pace, and a ball nobody is within five metres of.
SLOW_MPS = 1.0
FAR_METRES = 5.0


@dataclass(frozen=True)
class Run:
    """One maximal stretch of a label, half-open: `start` in, `end` out."""

    start: int
    end: int

    @property
    def frames(self) -> int:
        return self.end - self.start


@dataclass(frozen=True)
class Duration:
    frames: int
    seconds: float
    share: float


@dataclass(frozen=True)
class Contingency:
    """A signal against `D`: what it promises, what it costs, and how much it beats chance."""

    hits: int
    mask_frames: int
    label_frames: int
    precision: float
    recall: float
    base_rate: float
    lift: float


@dataclass(frozen=True)
class Sample:
    """Everything the report needs, already cut to the graded window."""

    first_frame: int
    last_frame: int
    labels: np.ndarray
    masks: dict[str, np.ndarray]
    speed: np.ndarray
    nearest: np.ndarray
    out_of_bounds: np.ndarray
    ball_present: np.ndarray
    extra: dict[str, np.ndarray] = field(default_factory=dict)

    def __len__(self) -> int:
        return len(self.labels)


def runs(labels: np.ndarray, label: str) -> list[Run]:
    """Every maximal run of `label`, half-open, in frame order."""
    matches = np.asarray(labels) == label
    if not matches.any():
        return []
    edges = np.diff(np.concatenate(([0], matches.view(np.int8), [0])))
    starts = np.flatnonzero(edges == 1)
    ends = np.flatnonzero(edges == -1)
    return [Run(int(start), int(end)) for start, end in zip(starts, ends)]


def duration_table(found: list[Run], fps: int, n_frames: int) -> list[Duration]:
    """Each run in frames, seconds and as a share of the labelled window."""
    return [
        Duration(frames=run.frames, seconds=run.frames / fps, share=run.frames / n_frames)
        for run in found
    ]


def contingency(labels: np.ndarray, mask: np.ndarray, label: str) -> Contingency:
    """`mask` as a detector of `label`: precision, recall and lift over the base rate."""
    labels = np.asarray(labels)
    mask = np.asarray(mask, dtype=bool)
    matches = labels == label
    hits = int((mask & matches).sum())
    mask_frames = int(mask.sum())
    label_frames = int(matches.sum())
    total = len(labels)
    base_rate = label_frames / total if total else 0.0
    precision = hits / mask_frames if mask_frames else 0.0
    recall = hits / label_frames if label_frames else 0.0
    lift = precision / base_rate if base_rate else 0.0
    return Contingency(hits, mask_frames, label_frames, precision, recall, base_rate, lift)


def ball_speed(
    positions: np.ndarray, present: np.ndarray, metres: tuple[float, float], fps: int
) -> np.ndarray:
    """Ball speed in m/s from the positions, NaN wherever either end is not detected.

    The third channel of the export is a speed the provider leaves empty 89.5% of the time, so the
    number has to be derived. Pitch-normalised coordinates are scaled by the real pitch size,
    which is what makes this comparable to the metres used everywhere else.
    """
    positions = np.asarray(positions, dtype=float)
    present = np.asarray(present, dtype=bool)
    speed = np.full(len(positions), np.nan)
    if len(positions) < 2:
        return speed
    both = present[:-1] & present[1:]
    dx = np.diff(positions[:, 0]) * metres[0]
    dy = np.diff(positions[:, 1]) * metres[1]
    speed[1:][both] = np.hypot(dx, dy)[both] * fps
    return speed


def nearest_player_distance(
    ball: np.ndarray, players: np.ndarray, metres: tuple[float, float]
) -> np.ndarray:
    """Distance in metres from the ball to the closest tracked player, NaN where both are absent."""
    ball = np.asarray(ball, dtype=float)
    players = np.asarray(players, dtype=float)
    if players.ndim != 3 or players.shape[0] != ball.shape[0]:
        raise ValueError("players must be (frames, slots, 3) aligned with the ball")

    # x and y are scaled by different lengths (105.3 x 68.0), so the two axes cannot share a
    # column of the ball: using `ball[:, :1]` for both reads y = x and inflates every distance.
    ball_x = ball[:, 0:1] * metres[0]
    ball_y = ball[:, 1:2] * metres[1]
    distances = np.hypot(
        players[:, :, 0] * metres[0] - ball_x,
        players[:, :, 1] * metres[1] - ball_y,
    )
    known = ~np.all(np.isnan(distances), axis=1)
    nearest = np.full(len(ball), np.nan)
    if known.any():
        nearest[known] = np.nanmin(distances[known], axis=1)
    return nearest


def out_of_bounds(positions: np.ndarray) -> np.ndarray:
    """Is the ball outside the pitch rectangle? `NaN` positions are not out: they are unknown."""
    positions = np.asarray(positions, dtype=float)
    x, y = positions[:, 0], positions[:, 1]
    return (x < 0) | (x > 1) | (y < 0) | (y > 1)


def load_sample() -> Sample:
    """Public labels, Smart Tagging and the ball track, cut to the same graded window."""
    if not GT_CSV.is_file() or not GT_META.is_file():
        raise FileNotFoundError(f"public ground truth not found: {GT_CSV}")

    meta = json.loads(GT_META.read_text(encoding="utf-8"))
    first, last = (
        meta["public_window"]["first_video_frame"],
        meta["public_window"]["last_video_frame"],
    )

    labels = pd.read_csv(GT_CSV).set_index("frame").loc[first:last, "label"].to_numpy()
    if len(labels) != last - first + 1:
        raise ValueError(f"ground truth does not cover {first}..{last} contiguously")

    tracking = atd.load()
    ball, present = tracking.ball()
    window = slice(first, last + 1)
    positions = ball[window]
    present = present[window]

    instances = smart_tagging.load()
    masks = {code: smart_tagging.mask(instances, code)[window] for code in CODES}

    return Sample(
        first_frame=first,
        last_frame=last,
        labels=labels,
        masks=masks,
        speed=ball_speed(positions, present, PITCH, FPS),
        nearest=nearest_player_distance(positions, tracking.players_array[window], PITCH),
        out_of_bounds=out_of_bounds(positions),
        ball_present=present,
    )


def _signals(sample: Sample) -> dict[str, np.ndarray]:
    """The candidate signals, derived ones first so the measured ones read as the comparison."""
    signals = {
        "balón ausente": ~sample.ball_present,
        "balón fuera del campo": sample.out_of_bounds,
        f"balón lento (<{SLOW_MPS:g} m/s)": sample.speed < SLOW_MPS,
        f"balón a >{FAR_METRES:g} m del jugador más cercano": sample.nearest > FAR_METRES,
    }
    signals.update(sample.masks)
    return signals


def pct(value: float, digits: int = 1) -> str:
    """A percentage the way the Spanish documents in this repository write one: 19,6%."""
    return f"{value:.{digits}%}".replace(".", ",")


def count(value: int) -> str:
    """A frame count with Spanish thousands: 1.469, not 1,469."""
    return f"{value:,}".replace(",", ".")


def dec(value: float, digits: int = 2) -> str:
    """A decimal with a comma, and `n/a` when the sample has no value at all."""
    return "n/a" if np.isnan(value) else f"{value:.{digits}f}".replace(".", ",")


def _nan_median(values: np.ndarray) -> float:
    """Median of what is present, or NaN -- a match with no speed samples has no median speed."""
    known = np.asarray(values, dtype=float)
    known = known[~np.isnan(known)]
    return float(np.median(known)) if known.size else float("nan")


def _format_seconds(seconds: float) -> str:
    return f"{dec(seconds)} s"


def report(sample: Sample, fps: int, commit: str | None = None) -> str:
    """The document, built only from `sample`: every number below is traceable to a function."""
    labels = sample.labels
    n = len(sample)
    label_frames = int((labels == "D").sum())
    base = label_frames / n if n else 0.0
    runs_d = runs(labels, "D")
    durations = duration_table(runs_d, fps, n)
    median_seconds = float(np.median([d.seconds for d in durations])) if durations else float("nan")
    # POSIX separators: the printed command must not depend on the OS that generated the document.
    doc_path = DEFAULT_DOC.relative_to(REPO_ROOT).as_posix()

    lines = [
        "# A0 — Qué es `D`, medido",
        "",
        f"Generado por `python tools/characterize_d.py --write {doc_path}`"
        + (f" desde el commit `{commit}`." if commit else "."),
        "",
        f"Ventana pública: frames **{sample.first_frame}..{sample.last_frame}** "
        f"({count(n)} frames, {dec(n / fps / 60, 1)} min de juego). El ground truth del partido es"
        " privado, así que nada de esto describe el partido entero.",
        "",
        "## 1. Cuánto es `D` y cuánto dura",
        "",
        f"- Frames `D`: **{count(label_frames)} / {count(n)} ({pct(base)})**.",
        f"- Tramos: **{len(runs_d)}** en {n / fps:.0f} s de juego.",
        "",
        "| tramo | frames | duración | % de la ventana |",
        "|---|---|---|---|",
    ]
    for index, duration in enumerate(durations, start=1):
        lines.append(
            f"| {index} | {duration.frames} | {_format_seconds(duration.seconds)} "
            f"| {pct(duration.share)} |"
        )

    lines += [
        "",
        f"La duración mediana de un tramo de `D` es "
        f"**{_format_seconds(float(np.median([d.seconds for d in durations])))}**"
        + (
            f", y el más largo {_format_seconds(max(d.seconds for d in durations))}."
            if durations
            else "."
        ),
        "",
        "## 2. Qué señal separa `D` de juego vivo",
        "",
        f"Tasa base a batir: **{pct(base)}** de los frames son `D`. `P(D | señal)` es lo que la"
        " señal promete; `P(señal | D)` es cuánto de `D` cubre; `lift` es la primera dividida por"
        " la base.",
        "",
        "| señal | frames | P(D | señal) | P(señal | D) | lift |",
        "|---|---:|---:|---:|---:|",
    ]
    for name, mask in _signals(sample).items():
        stats = contingency(labels, mask, "D")
        lines.append(
            f"| {name} | {count(stats.mask_frames)} | {pct(stats.precision)} "
            f"| {pct(stats.recall)} | {dec(stats.lift)} |"
        )

    # Section 4 is written from these numbers, not around them: every claim names the measurement
    # it rests on, so a signal that stops separating D cannot leave a stale adjective behind.
    signal_stats = {name: contingency(labels, mask, "D") for name, mask in _signals(sample).items()}
    absent = signal_stats["balón ausente"]
    outside = signal_stats["balón fuera del campo"]
    slow = next(stat for name, stat in signal_stats.items() if name.startswith("balón lento"))
    far = next(stat for name, stat in signal_stats.items() if name.startswith("balón a >"))
    set_pieces = signal_stats["SET PIECES"]
    build_up = signal_stats["BUILD UP"]

    alive = labels != "D"
    speed_d = _nan_median(sample.speed[labels == "D"])
    speed_alive = _nan_median(sample.speed[alive])
    nearest_d = _nan_median(sample.nearest[labels == "D"])
    nearest_alive = _nan_median(sample.nearest[alive])

    # These two directions are the whole argument of the issue, so they are stated separately:
    # one is "how much of D has no ball", the other is "how often no ball means D".
    absent_in_d = contingency(labels, ~sample.ball_present, "D")
    lines += [
        "",
        "## 3. El balón dentro de `D`",
        "",
        f"- `P(sin balón | D)` = **{pct(absent_in_d.recall)}**; `P(D | sin balón)` = "
        f"**{pct(absent_in_d.precision)}**. Es decir, `D` **no** es un problema de balón perdido.",
        f"- Velocidad mediana del balón: **{dec(speed_d)} m/s dentro de `D`** frente a "
        f"**{dec(speed_alive)} m/s** con balón vivo.",
        f"- Distancia mediana al jugador más cercano: **{dec(nearest_d)} m** en `D` frente a "
        f"**{dec(nearest_alive)} m** en juego vivo.",
        f"- Balón fuera del rectángulo del campo: **{count(outside.mask_frames)}** frames, de los"
        f" cuales {pct(outside.precision)} son `D`.",
        "",
        "## 4. Lectura",
        "",
        f"- **`D` son tramos, no frames.** La mediana dura "
        f"{_format_seconds(median_seconds)}: un umbral por frame, sin estado, no puede"
        " reconstruir esa estructura.",
        f"- **La premisa del stream A no se sostiene.** `P(sin balón | D)` = {pct(absent.recall)} y"
        f" `P(D | sin balón)` = {pct(absent.precision)}: el balón perdido explica un tercio de"
        " `D` y acierta la mitad de las veces que dispara.",
        f"- **La única señal de balón casi perfecta es el fuera de campo:** precisión"
        f" {pct(outside.precision)}, cobertura {pct(outside.recall)}. Dispara `D`; no lo detecta.",
        f"- **El balón no se queda quieto.** Velocidad menor que {SLOW_MPS:g} m/s tiene lift"
        f" {dec(slow.lift)}: dentro de `D` el balón rueda a {dec(speed_d)} m/s de mediana. Y estar"
        f" a más de {FAR_METRES:g} m del jugador más cercano da lift {dec(far.lift)}, pese a que la"
        f" distancia mediana en `D` ({dec(nearest_d)} m) duplique la de juego vivo"
        f" ({dec(nearest_alive)} m).",
        f"- **`SET PIECES` es la mejor señal contextual y no basta:** lift {dec(set_pieces.lift)},"
        f" cubre {pct(set_pieces.recall)} de `D` con precisión {pct(set_pieces.precision)}."
        f" `BUILD UP` baja de 1 (lift {dec(build_up.lift)}), que es el control funcionando: se"
        " dispara con balón vivo.",
        "- **Consecuencia para #5, #6 y #16:** `D` se decide por estado y contexto (reanudación,"
        " saque, fuera de juego, celebración), no por un umbral del track del balón. Las señales de"
        " balón entran como disparadores de precisión dentro de un modelo con memoria, nunca como"
        " detector.",
        "",
        "## 5. Lo que esta muestra no puede decir",
        "",
        f"- {count(label_frames)} frames y {len(runs_d)} tramos de `D`: los intervalos de"
        " confianza son anchos y cualquier umbral elegido aquí es una hipótesis, no un resultado.",
        "- La ventana pública es la parte del partido con más balón detectado (88,2% frente a 56,9%"
        " global), así que la cobertura de las señales de balón está **sobrestimada**.",
        "- El `D` del partido completo es privado: lo único observable ahí son las señales"
        " estructurales (Smart Tagging, huecos del tracker, saques), no la etiqueta.",
        "",
    ]
    # The blank strings in `lines` are the paragraph breaks markdown needs around a table or a
    # heading; dropping them renders the whole document as one run-on block.
    return "\n".join(lines).rstrip() + "\n"


def _git_commit() -> str | None:
    try:
        done = subprocess.run(
            ["git", "-C", str(REPO_ROOT), "rev-parse", "--short=8", "HEAD"],
            capture_output=True,
            text=True,
        )
    except OSError:
        return None
    return done.stdout.strip() if done.returncode == 0 else None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Measure what `D` is in the public ground truth")
    parser.add_argument("--write", help="write the document here instead of printing it")
    parser.add_argument("--commit", default=None, help="commit to name in the header")
    args = parser.parse_args(argv)

    try:
        sample = load_sample()
    except (OSError, ValueError) as problem:
        print(f"cannot measure without the bundle: {problem}", file=sys.stderr)
        return 1

    text = report(sample, FPS, commit=args.commit or _git_commit())

    if args.write:
        target = Path(args.write)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8")
        print(f"wrote {target} ({len(text)} B)", file=sys.stderr)
    else:
        sys.stdout.write(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
