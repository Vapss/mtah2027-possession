"""#6 / #22: the engine's pre-registered sensitivity sweep (DECISIONS 29), written as a document.

    python tools/engine_sweep.py --write docs/analysis/engine-sensitivity.md

The grid, the metrics and the selection rule were committed in DECISIONS 29 before this ran. The
document is a sensitivity map: it says whether the default sits on a plateau or on a peak. It is not
a search for the best public number -- 17 possessions cannot rank 27 configurations -- and the
default is replaced only under the rule written there.
"""

from __future__ import annotations

import argparse
import itertools
import sys
from pathlib import Path

import numpy as np
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from tools import atd, dead_ball, emision, engine  # noqa: E402
from tools import blocks as bl  # noqa: E402
from tools import smart_tagging as st  # noqa: E402
from tools.compare_submissions import compare_codes  # noqa: E402

sys.path.insert(0, str(REPO_ROOT / "evaluation"))
import possession_metrics as pm  # noqa: E402

GRID = {"radius_m": (1.0, 1.5, 2.0), "speed_mps": (3.0, 5.0, 7.0), "dwell": (1, 5, 12)}
LOW_BALL_BLOCKS = (7, 9, 11, 18)  # 19,9-36,9% ball detected (DECISIONS 26)
GROUND_TRUTH = REPO_ROOT / "evaluation" / "gt" / "BAR-ATH_possession_gt_public.csv"


def sweep() -> list[dict]:
    """One row per grid point, the default first, every number from a function."""
    f = engine.features(atd.load("tactical"), emision.team_slots())
    gt = pm.label_codes(pd.read_csv(GROUND_TRUTH).label)
    runs = engine.halves()
    cut = bl.blocks(bl.halves())
    votes = st.possession_votes(st.load())
    # The delivered chain (DECISIONS 30-32): restarts and stoppages are read once; only the engine's
    # thresholds move across the grid (which restarts apply depends on them, so the chain decides).
    evidence = dead_ball.load_evidence()
    dead = dead_ball.dead_mask(evidence, runs, "out")

    def decoded(params: engine.Params) -> np.ndarray:
        return engine.chain(f, params, evidence.restarts, dead)[2]

    default = engine.DEFAULT
    base = pm.label_codes(list(decoded(default)))
    points = [engine.Params(*p) for p in itertools.product(*GRID.values())]
    points.sort(key=lambda p: p != default)  # the default first, then grid order
    rows = []
    for params in points:
        lab = decoded(params)
        codes = pm.label_codes(list(lab))
        scored = pm.evaluate(gt, codes)
        paired = compare_codes(gt, base, codes)["sign_diagnostic"]
        structure = bl.measure(lab, f.present, votes, cut, runs)
        rows.append(
            {
                "params": params,
                "spell_f1": float(scored["spell_f1_mean"]),
                "macro_f1": float(scored["macro_f1"]),
                "wins": int(paired["wins_b"]),
                "losses": int(paired["wins_a"]),
                "p": float(paired["exact_two_sided_p"]),
                "rate": structure[-1].rate,
                "st_agree": structure[-1].st_agree,
                "st_low": float(np.mean([structure[b - 1].st_agree for b in LOW_BALL_BLOCKS])),
                "rates": [row.rate for row in structure[:-1]],
            }
        )
    return rows


def breaks_structure(rates: list[float], reference: list[float]) -> bool:
    """DECISIONS 26: a block left without possessions, or an order of magnitude off the default."""
    for rate, ref in zip(rates, reference):
        if rate == 0 and ref > 0:
            return True
        if rate > 0 and ref > 0 and max(rate / ref, ref / rate) >= 10:
            return True
    return False


def _dec(value: float, digits: int = 4) -> str:
    return f"{value:.{digits}f}".replace(".", ",")


def _pct(value: float) -> str:
    return f"{100 * value:.1f}%".replace(".", ",")


def report(rows: list[dict], command: str, commit: str | None) -> str:
    origin = f" desde el commit `{commit}`" if commit else ""
    default = rows[0]
    lines = [
        "# Motor (#6): mapa de sensibilidad pre-registrado, sobre la cadena entregada",
        "",
        f"Generado por `{command}`{origin}. No se edita a mano. Rejilla, métricas y regla de",
        "selección: decisión 29, commiteada antes de correr esto; cada fila es la cadena entregada",
        "(motor + reanudaciones + `D`, decisiones 30 y 31) con esos umbrales. En **negrita**, el",
        "default, elegido por física. `gana/pierde` = posesiones del slice público cuyo estado de",
        "acierto a IoU 0,5 cambia frente al default (test de signos; hacen falta ≥ 6 en el mismo",
        "sentido). `ST` = acuerdo con el Smart Tagging, la única señal independiente del tracking;",
        "`ST bajos` es su media en los bloques 7, 9, 11 y 18, los de menos balón.",
        "",
        "| radio | vel. | dwell | spellF1 | macroF1 | gana | pierde | pos/min | ST | ST bajos |",
        "|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for row in rows:
        p = row["params"]
        cells = [
            _dec(p.radius_m, 1),
            _dec(p.speed_mps, 0),
            str(p.dwell),
            _dec(row["spell_f1"]),
            _dec(row["macro_f1"]),
            str(row["wins"]),
            str(row["losses"]),
            _dec(row["rate"], 2),
            _pct(row["st_agree"]),
            _pct(row["st_low"]),
        ]
        if row is default:
            cells = [f"**{c}**" for c in cells]
        lines.append("| " + " | ".join(cells) + " |")

    others = rows[1:]
    # DECISIONS 29, as written: the sign test at p <= 0,031 (six of six discordant possessions),
    # more wins than losses, and no worse Smart Tagging agreement than the default.
    beats = [
        r
        for r in others
        if r["p"] <= 0.0313
        and r["wins"] > r["losses"]
        and r["st_agree"] >= default["st_agree"]
        and not breaks_structure(r["rates"], default["rates"])
    ]
    spell = [r["spell_f1"] for r in others]
    lines += [
        "",
        "## Lectura según la regla de la decisión 29",
        "",
        f"- `spellF1` de las otras 26 configuraciones: {_dec(min(spell))} .. {_dec(max(spell))} "
        f"(default {_dec(default['spell_f1'])}).",
        f"- Configuraciones que ganan al default según la regla (test de signos p ≤ 0,031, más "
        f"ganadas que perdidas, sin empeorar el acuerdo con el Smart Tagging y sin romper un "
        f"bloque): **{len(beats)}**.",
        f"- Acuerdo con el Smart Tagging: {_pct(min(r['st_agree'] for r in others))} .. "
        f"{_pct(max(r['st_agree'] for r in others))} (default {_pct(default['st_agree'])}).",
    ]
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="The engine's pre-registered sensitivity sweep")
    parser.add_argument("--write", type=Path, help="write the document here instead of printing")
    args = parser.parse_args(argv)
    try:
        rows = sweep()
    except (OSError, ValueError) as problem:
        print(f"cannot run the sweep: {problem}", file=sys.stderr)
        return 1
    command = "python tools/engine_sweep.py"
    if args.write:
        command += f" --write {bl._relative(args.write)}"
    text = report(rows, command, bl._git_commit())
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
