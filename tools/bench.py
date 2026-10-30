"""Gap-transplant bench: score a method on the public slice under the full match's ball coverage.

    python tools/bench.py                        # every registered method
    python tools/bench.py --method engine --write docs/analysis/bench.md

Why it exists
-------------
The public ground truth is block 1, the easiest five minutes of the match: the tracker sees the ball
on 88,2% of its frames, against 56,9% overall and 19,9-36,9% in the worst blocks (DECISIONS 13, 26).
Anything that matters where the ball is missing -- gap handling, ball imputation, dead ball without
a visible ball -- cannot be measured on it, and DECISIONS 24 had to decide such policies by
principle. This bench makes them measurable against the real labels.

How
---
Every other full five-minute block of the match (19 of them: blocks 11 and 22 are shorter than five
minutes) donates its ball-presence pattern. The donor's mask is laid frame by frame over block 1:
where the donor had no ball, block 1's ball is deleted -- position, distances, speed, the
in/out-of-pitch observation. Players, Smart Tagging and ground truth stay as they are. The method
runs on the degraded match and is scored with the official metric on the public labels. One donor,
one `spellF1`; the bench reports their spread and their mean, and the mean over the low-ball donors.

What it is not
--------------
A transplanted gap is not a real one: real gaps cluster where the ball is hard to see (in the air,
in a crowded box), a transplanted gap falls wherever the donor's did. So the bench measures
robustness to the amount and length of missing ball, not to its placement. And it is still the
same 17 possessions: it ranks methods by how they degrade, it does not add ground truth. Use it with
the paired comparison, never instead of it.

Calibrated against the organisers' own full-match numbers, which nobody here has seen labels for:
the bench mean of the rebuilt `smooth` baselines is 0,0345 / 0,1854 / 0,2150 for windows 0 / 25 / 50
against the official full-match 0,0486 / 0,1996 / 0,2433 -- it predicts the loss to missing ball,
slightly pessimistic. It does NOT predict `smooth125` (bench 0,2910, official 0,2242): that one
loses on the full match because its 5 s window merges the shorter possessions of other blocks, and
the bench keeps block 1's possession structure. So: trust it for gap handling, never for a method
with its own time scale -- that is what the block report (DECISIONS 26) is for.

A method is a function `(features, evidence) -> labels`, the per-frame `H/A/D/X` array for the whole
match; register it in `METHODS`. The engine's own chains are registered here.
"""

from __future__ import annotations

import argparse
import dataclasses
import sys
from collections.abc import Callable
from pathlib import Path

import numpy as np
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from tools import atd, dead_ball, emision, engine  # noqa: E402
from tools import blocks as bl  # noqa: E402

sys.path.insert(0, str(REPO_ROOT / "evaluation"))
import possession_metrics as pm  # noqa: E402

GROUND_TRUTH = REPO_ROOT / "evaluation" / "gt" / "BAR-ATH_possession_gt_public.csv"
LOW_BALL = 0.5  # donors with less ball than this are the regime the public slice cannot show

Method = Callable[[engine.Features, dead_ball.Evidence], np.ndarray]


def _engine(f: engine.Features, ev: dead_ball.Evidence) -> np.ndarray:
    dead = dead_ball.dead_mask(ev, engine.halves(), "out")
    return engine.chain(f, engine.DEFAULT, ev.restarts, dead)[2]


def _engine_bare(f: engine.Features, ev: dead_ball.Evidence) -> np.ndarray:
    return engine.chain(f, engine.DEFAULT, None, None)[2]


def _smooth50(f: engine.Features, ev: dead_ball.Evidence) -> np.ndarray:
    """The organisers' published floor, rebuilt on the bench's features to calibrate the bench.

    Nearest player's team where the ball is seen, nobody where it is not, then the organisers' own
    `smooth` (starter/baseline.py, imported, not copied) with its +/- 50-frame window.
    """
    from starter import baseline

    codes = np.full(len(f.present), baseline.NOBODY, dtype=np.int8)
    codes[f.present & (f.home_m <= f.away_m)] = baseline.HOME
    codes[f.present & (f.away_m < f.home_m)] = baseline.AWAY
    return baseline.smooth(codes, 50)


METHODS: dict[str, Method] = {
    "engine": _engine,
    "engine-bare": _engine_bare,
    "smooth50": _smooth50,
}


def degrade(
    f: engine.Features, ev: dead_ball.Evidence, window: tuple[int, int], donor: np.ndarray
) -> tuple[engine.Features, dead_ball.Evidence]:
    """Copies of `f` and `ev` with the ball deleted inside `window` wherever `donor` is False."""
    start, stop = window
    if len(donor) != stop - start:
        raise ValueError(f"donor has {len(donor)} frames, window has {stop - start}")
    keep = np.ones(len(f.present), dtype=bool)
    keep[start:stop] = donor
    present = f.present & keep
    # A speed needs the ball on this frame and the previous one, exactly as emision._ball_speed.
    speed = np.where(present & np.concatenate(([False], present[:-1])), f.speed_mps, np.nan)
    f2 = dataclasses.replace(
        f,
        home_m=np.where(present, f.home_m, np.nan),
        away_m=np.where(present, f.away_m, np.nan),
        present=present,
        speed_mps=speed,
        in_pitch=f.in_pitch & keep,
    )
    ev2 = dataclasses.replace(ev, out=ev.out & keep, inside=ev.inside & keep)
    return f2, ev2


def load() -> tuple[engine.Features, dead_ball.Evidence, np.ndarray, list[bl.Block]]:
    f = engine.features(atd.load("tactical"), emision.team_slots())
    ev = dead_ball.load_evidence()
    gt = pm.label_codes(pd.read_csv(GROUND_TRUTH).label)
    return f, ev, gt, bl.blocks(bl.halves())


def bench(method: Method, f, ev, gt, cut) -> list[dict]:
    """One row per donor: its ball share and the method's public spellF1 under its mask."""
    window = (cut[0].start, cut[0].stop)
    size = window[1] - window[0]
    rows = [
        {
            "donor": "1★ (sin trasplante)",
            "ball": float(f.present[window[0] : window[1]].mean()),
            "spell_f1": float(
                pm.evaluate(gt, pm.label_codes(list(method(f, ev))))["spell_f1_mean"]
            ),
        }
    ]
    for block in cut[1:]:
        if block.stop - block.start < size:
            continue  # a shorter block cannot cover the whole window
        donor = f.present[block.start : block.start + size]
        f2, ev2 = degrade(f, ev, window, donor)
        codes = pm.label_codes(list(method(f2, ev2)))
        rows.append(
            {
                "donor": str(block.index),
                "ball": float(donor.mean()),
                "spell_f1": float(pm.evaluate(gt, codes)["spell_f1_mean"]),
            }
        )
    return rows


def summary(rows: list[dict]) -> dict:
    donors = rows[1:]
    low = [r["spell_f1"] for r in donors if r["ball"] < LOW_BALL]
    values = [r["spell_f1"] for r in donors]
    return {
        "clean": rows[0]["spell_f1"],
        "mean": float(np.mean(values)),
        "min": float(np.min(values)),
        "low_mean": float(np.mean(low)) if low else float("nan"),
        "n_low": len(low),
    }


def _dec(value: float) -> str:
    return "—" if np.isnan(value) else f"{value:.4f}".replace(".", ",")


def report(results: dict[str, list[dict]], command: str, commit: str | None) -> str:
    origin = f" desde el commit `{commit}`" if commit else ""
    names = list(results)
    lines = [
        "# Banco de trasplante de huecos",
        "",
        f"Generado por `{command}`{origin}. No se edita a mano. Cada fila es un bloque donante: su",
        "patrón de balón ausente se trasplanta sobre la ventana pública (bloque 1★), y se puntúa",
        "contra su ground truth: robustez a la cantidad y longitud de balón perdido, no al lugar.",
        "",
        "| donante | balón | " + " | ".join(f"`{n}`" for n in names) + " |",
        "|---|---:|" + "---:|" * len(names),
    ]
    first = results[names[0]]
    for i, row in enumerate(first):
        cells = " | ".join(_dec(results[n][i]["spell_f1"]) for n in names)
        lines.append(f"| {row['donor']} | {100 * row['ball']:.1f}% | {cells} |".replace(".", ","))
    lines += [
        "",
        "| resumen | " + " | ".join(f"`{n}`" for n in names) + " |",
        "|---|" + "---:|" * len(names),
    ]
    stats = {n: summary(results[n]) for n in names}
    for key, label in [
        ("clean", "sin trasplante"),
        ("mean", "media de donantes"),
        ("low_mean", f"media de donantes con < {int(100 * LOW_BALL)}% de balón"),
        ("min", "peor donante"),
    ]:
        lines.append(f"| {label} | " + " | ".join(_dec(stats[n][key]) for n in names) + " |")
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Gap-transplant bench on the public slice")
    parser.add_argument("--method", action="append", choices=sorted(METHODS))
    parser.add_argument("--write", type=Path, help="write the document here instead of printing")
    args = parser.parse_args(argv)
    names = args.method or list(METHODS)
    try:
        f, ev, gt, cut = load()
        results = {name: bench(METHODS[name], f, ev, gt, cut) for name in names}
    except (OSError, ValueError) as problem:
        print(f"cannot run the bench: {problem}", file=sys.stderr)
        return 1
    command = "python tools/bench.py" + "".join(f" --method {n}" for n in (args.method or []))
    if args.write:
        command += f" --write {bl._relative(args.write)}"
    text = report(results, command, bl._git_commit())
    if args.write:
        args.write.parent.mkdir(parents=True, exist_ok=True)
        args.write.write_text(text, encoding="utf-8", newline="\n")
        print(f"wrote {bl._relative(args.write)}")
    else:
        if hasattr(sys.stdout, "reconfigure"):
            sys.stdout.reconfigure(encoding="utf-8")
        sys.stdout.write(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
