"""Price the time a dead-ball variant adds, without ground truth.

    python tools/dead_price.py runs/dead_v3/engine.csv runs/dead_v3/onset.csv
    python tools/dead_price.py A.csv B.csv --ball --write docs/analysis/dead-price.md

Why
---
A dead-ball variant can lose points in two ways: it can invent `D` in the middle of play, or it
can fuse two stoppages into one and erase the possession between them. Both are visible in the
labels alone, and neither needs the ground truth, so both can be audited after the organisers'
clarification (DECISIONS 44: the slice checks, it does not choose).

The audit answers three questions about the frames `B` marks `D` and `A` does not:

1. **How much and how long.** Frame count, share of the playing halves, number of added segments,
   median and maximum length. A rule that recovers an onset should add short segments at the start
   of stoppages, not long blocks.
2. **Does it fuse?** A `D` run of `B` that contains two or more `D` runs of `A` has swallowed the
   live spell between them. That is the failure the lane rejected by principle before measuring.
3. **Does the added time look dead?** With the bundle (`--ball`), how often the ball is tracked and
   how fast it moves, against the same numbers on `A`'s dead frames and on all playing frames. The
   ball is present in most true `D` frames (DECISIONS 16), so this corroborates or warns; it does
   not decide.

What it does not do
-------------------
It does not score anything and it does not compare `spellF1`. A variant can add dead-looking time
and still be wrong, and the public slice cannot arbitrate a selection (DECISIONS 44). This is the
GT-free half of the case; the other half is the external corpus.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from tools.contract import read_submission  # noqa: E402

DEAD = "D"


def dead_mask(labels: list[str]) -> np.ndarray:
    return np.asarray([label.strip().upper() == DEAD for label in labels], dtype=bool)


def runs(mask: np.ndarray) -> list[tuple[int, int]]:
    """Maximal half-open `[start, stop)` runs of True."""
    edges = np.diff(np.concatenate(([0], mask.astype(np.int8), [0])))
    starts = np.flatnonzero(edges == 1)
    stops = np.flatnonzero(edges == -1)
    return [(int(a), int(b)) for a, b in zip(starts, stops)]


def added_segments(a: np.ndarray, b: np.ndarray) -> list[tuple[int, int]]:
    """Runs of frames that `b` calls dead and `a` does not."""
    return runs(b & ~a)


def fusions(a: np.ndarray, b: np.ndarray) -> int:
    """`D` runs of `b` that contain two or more `D` runs of `a`: a live spell was swallowed."""
    inside = runs(a)
    count = 0
    for start, stop in runs(b):
        contained = sum(1 for s, _ in inside if start <= s < stop)
        if contained >= 2:
            count += 1
    return count


def share(mask: np.ndarray, inside: np.ndarray) -> float:
    total = int(inside.sum())
    return float((mask & inside).sum() / total) if total else 0.0


def playing_halves(n_frames: int) -> np.ndarray:
    import games  # noqa: E402  imported here: the helper needs the match metadata

    inside = np.zeros(n_frames, dtype=bool)
    for _half, start, stop in games.half_video_blocks(games.GAME):
        inside[start : min(stop + 1, n_frames)] = True
    return inside


def _dec(value: float, digits: int = 2) -> str:
    return f"{value:.{digits}f}".replace(".", ",")


def _num(value: int) -> str:
    return f"{value:,}".replace(",", ".")


def ball_rows(features, a: np.ndarray, b: np.ndarray, inside: np.ndarray) -> list[str]:
    """Ball presence and speed on the added frames, on `a`'s dead frames and on all play."""
    added = b & ~a
    dead_a = a & inside
    speed = features.speed_mps
    present = features.present
    rows = []
    for name, mask in (("frames añadidos", added), ("`D` de A", dead_a), ("todo el juego", inside)):
        rows.append(
            f"| {name} | {_num(int(mask.sum()))} | {_dec(float(present[mask].mean()))} | "
            f"{_dec(float(np.nanmedian(speed[mask])))} |"
        )
    return rows


def report(a_labels: list[str], b_labels: list[str], name_a: str, name_b: str) -> str:
    a = dead_mask(a_labels)
    b = dead_mask(b_labels)
    if len(a) != len(b):
        raise ValueError(f"different frame counts: {len(a)} and {len(b)}")
    inside = playing_halves(len(a))
    segs = added_segments(a, b)
    durations = np.array([stop - start for start, stop in segs], dtype=int)
    lines = [
        f"# Precio del tiempo que `{name_b}` añade a `D`",
        "",
        "Generado por `tools/dead_price.py`; no se edita a mano. Sin ground truth.",
        "",
        "| | frames | % de los medios tiempos | segmentos | mediana | máximo | fusiones |",
        "|---|---:|---:|---:|---:|---:|---:|",
        f"| {name_b} − {name_a} | {_num(int((b & ~a).sum()))} | "
        f"{_dec(100 * ((b & ~a) & inside).sum() / max(1, inside.sum()))}% | {len(segs)} | "
        f"{_num(int(np.median(durations))) if len(durations) else 0} | "
        f"{_num(int(durations.max())) if len(durations) else 0} | {fusions(a, b)} |",
        "",
        f"`D` de {name_a}: {_dec(100 * share(a, inside))}% de los medios tiempos; "
        f"de {name_b}: {_dec(100 * share(b, inside))}%.",
        "",
        "Una fusión es un tramo `D` de la variante que contiene dos o más tramos de la cadena: "
        "borraría la posesión entre dos paradas. Cero es la condición que la lane fijó por "
        "principio.",
    ]
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="price the dead time a variant adds, no GT")
    parser.add_argument("a", help="submission CSV of the reference chain")
    parser.add_argument("b", help="submission CSV of the variant")
    parser.add_argument(
        "--ball", action="store_true", help="also ball presence and speed (needs the bundle)"
    )
    parser.add_argument("--write", type=Path, help="write the table here instead of printing it")
    args = parser.parse_args(argv)

    a_labels = read_submission(args.a).label.tolist()
    b_labels = read_submission(args.b).label.tolist()
    text = report(a_labels, b_labels, Path(args.a).stem, Path(args.b).stem)

    if args.ball:
        from tools import atd, emision, engine

        features = engine.features(atd.load("tactical"), emision.team_slots())
        a, b = dead_mask(a_labels), dead_mask(b_labels)
        text += (
            "\n| conjunto | frames | balón presente | velocidad mediana (m/s) |\n"
            "|---|---:|---:|---:|\n"
            + "\n".join(ball_rows(features, a, b, playing_halves(len(a))))
            + "\n"
        )

    if args.write:
        args.write.parent.mkdir(parents=True, exist_ok=True)
        args.write.write_text(text, encoding="utf-8")
        print(f"wrote {args.write} ({len(text)} B)", file=sys.stderr)
    else:
        sys.stdout.write(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
