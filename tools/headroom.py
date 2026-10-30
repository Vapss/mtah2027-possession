"""Headroom audit: where the delivered chain loses its public spellF1 (DECISIONS 40).

    python tools/headroom.py                                  # print the document
    python tools/headroom.py --write docs/analysis/headroom.md

A diagnostic, not a method: it replaces one component of the delivered chain with the public
ground truth at a time and scores the result on the public slice and on the gap-transplant bench
(`tools/bench.py`). It chooses nothing -- no rule, constant or variant is selected with it -- and
says where a better rule would have room to win:

- **oracle D**: our carried team everywhere, `D` exactly where the truth has it (and its two
  halves: only removing our false `D`, only adding the `D` we miss);
- **oracle team**: our `D`, the true team on the frames where we name a team (`H`/`A`) and the
  truth calls live. Our abstentions (`X`) stay: the scorer fills them from their neighbours
  (`fill_abstentions`), so giving them the truth would credit what the scorer never sees
  (DECISIONS 41).

It also splits the live frames that carry the wrong team by their distance to the nearest true
change of label, and counts the tagged restarts that carry no team (`engine.restart_controls`
skips them). Aggregates only; nothing frame by frame leaves this module.
"""

from __future__ import annotations

import argparse
import sys
from collections import Counter
from collections.abc import Callable, Sequence
from pathlib import Path

import numpy as np

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from tools import bench, dead_ball, engine  # noqa: E402
from tools import blocks as bl  # noqa: E402

FPS = engine.FPS
BANDS_S = ((0, 1), (1, 2), (2, 4), (4, 8), (8, None))
ORACLES = (
    "oracle D",
    "oracle D: only remove our false D",
    "oracle D: only add the D we miss",
    "oracle team on the live frames",
)
_LETTER = {bench.pm.H: "H", bench.pm.A: "A", bench.pm.D: "D"}


def truth_letters(gt: np.ndarray) -> np.ndarray:
    """`H/A/D` where the truth grades a frame, `""` elsewhere."""
    out = np.full(len(gt), "", dtype=object)
    for code, letter in _LETTER.items():
        out[np.asarray(gt) == code] = letter
    return out


def oracles(carried: np.ndarray, labels: np.ndarray, truth: np.ndarray) -> dict[str, np.ndarray]:
    """The delivered labels with one component taken from the truth (`truth_letters`).

    `carried` is the decoded team before `D` is laid over it (`engine.labels(state)`), `labels`
    the delivered `H/A/D/X`.
    """
    carried, labels, truth = (np.asarray(x, dtype=object) for x in (carried, labels, truth))
    is_d, live = truth == "D", (truth == "H") | (truth == "A")
    oracle_d = carried.copy()
    oracle_d[is_d] = "D"
    remove_false = labels.copy()
    false_d = (labels == "D") & live
    remove_false[false_d] = carried[false_d]
    add_missed = labels.copy()
    add_missed[is_d] = "D"
    # Only frames we name a team on: an abstention (`X`) is filled by the scorer from its
    # neighbours (`fill_abstentions`), so the truth is not given to it here.
    oracle_team = labels.copy()
    both_live = ((labels == "H") | (labels == "A")) & live
    oracle_team[both_live] = truth[both_live]
    return dict(zip(ORACLES, (oracle_d, remove_false, add_missed, oracle_team)))


def scorer_filled(labels: np.ndarray) -> np.ndarray:
    """`X` filled as the official temporal metrics see it (forward, then back-filled at the head):
    the official `possession_metrics.fill_abstentions` over one run, in letters."""
    labels = np.asarray(labels, dtype=object)
    codes = np.full(len(labels), bench.pm.X, dtype=np.int64)
    for letter, code in bench._CODES.items():
        codes[labels == letter] = code
    filled = bench.pm.fill_abstentions(codes, [(0, len(labels))])
    letters = {code: letter for letter, code in bench._CODES.items()}
    return np.array([letters[int(c)] for c in filled], dtype=object)


def team_error(labels: np.ndarray, truth: np.ndarray, window: tuple[int, int]) -> dict:
    """The live frames with the wrong team inside `window`, by distance to a true change (s).

    Counted on the labels the official `spellF1` sees (`scorer_filled`); `unlabelled` is how many
    of the window's frames we left as `X`.
    """
    a, b = window
    raw, truth = np.asarray(labels, dtype=object)[a:b], np.asarray(truth, dtype=object)[a:b]
    labels = scorer_filled(raw)
    live = (labels != "D") & ((truth == "H") | (truth == "A"))
    wrong = live & (labels != truth)
    changes = np.flatnonzero(truth[1:] != truth[:-1]) + 1
    idx = np.arange(b - a)
    if changes.size:
        nearest = np.abs(idx[:, None] - changes[None, :]).min(axis=1)
    else:
        nearest = np.full(b - a, np.iinfo(np.int64).max)
    bands = {}
    for lo, hi in BANDS_S:
        top = np.iinfo(np.int64).max if hi is None else hi * FPS
        key = f"{lo}-{hi if hi is not None else 'inf'} s"
        bands[key] = int((wrong & (nearest >= lo * FPS) & (nearest < top)).sum())
    lead = np.flatnonzero(raw != "X")
    head = int(lead[0]) if lead.size else b - a
    return {
        "live": int(live.sum()),
        "wrong": int(wrong.sum()),
        "unlabelled": int((raw == "X").sum()),
        "leading_unlabelled_s": head / FPS,
        "leading_wrong_after_fill": int(wrong[:head].sum()),
        "wrong_by_distance_to_a_change": bands,
    }


def teamless_restarts(restarts: Sequence[dead_ball.Restart]) -> dict[str, int]:
    """Tagged restarts without a team, by kind (the engine cannot force them)."""
    return dict(sorted(Counter(r.kind for r in restarts if r.team is None).items()))


def _parts(f: engine.Features, ev: dead_ball.Evidence) -> tuple[np.ndarray, np.ndarray]:
    _, state, labels = engine.chain(f, engine.DEFAULT, ev.restarts, engine.delivered_dead(ev))
    return engine.labels(state), np.asarray(labels)


def methods(
    truth: np.ndarray,
) -> dict[str, Callable[[engine.Features, dead_ball.Evidence], np.ndarray]]:
    """Bench methods: the delivered chain and each oracle on whatever ball the bench leaves."""
    out: dict[str, Callable] = {"delivered": lambda f, ev: _parts(f, ev)[1]}
    for name in ORACLES:
        out[name] = lambda f, ev, name=name: oracles(*_parts(f, ev), truth)[name]
    return out


def measure() -> dict:
    """Every number of docs/analysis/headroom.md."""
    f, ev, gt, cut = bench.load()
    truth = truth_letters(gt)
    runs = bench.pm.valid_runs(gt)
    rows = {
        name: bench.summary(bench.bench(m, f, ev, gt, cut)) for name, m in methods(truth).items()
    }
    _, labels = _parts(f, ev)
    teamless = teamless_restarts(ev.restarts)
    return {
        "bench": rows,
        "team_error": team_error(labels, truth, runs[0]),
        "restarts": len(ev.restarts),
        "teamless_restarts": teamless,
    }


def report(result: dict, command: str, commit: str | None) -> str:
    origin = f" desde el commit `{commit}`" if commit else ""
    dec = bench._dec
    lines = [
        "# Auditoría del margen: qué componente pierde el `spellF1`",
        "",
        f"Generado por `{command}`{origin}. No se edita a mano.",
        "**Diagnóstico con la GT pública: no elige ninguna regla, constante ni variante**",
        "(decisión 40). Cada fila cambia un componente de la cadena entregada por la verdad y",
        "puntúa en el slice y en el banco de trasplante.",
        "",
        "| cadena | slice | banco (media) | banco, poco balón | peor donante |",
        "|---|---:|---:|---:|---:|",
    ]
    for name, s in result["bench"].items():
        cells = " | ".join(dec(s[key]) for key in ("clean", "mean", "low_mean", "min"))
        lines.append(f"| {name} | {cells} |")
    t = result["team_error"]
    lines += [
        "",
        "## El equipo en los frames vivos (slice limpio)",
        "",
        "Contado sobre las etiquetas que ve el `spellF1` oficial: las `X` rellenadas como hace",
        "`fill_abstentions` (hacia delante, y hacia atrás al inicio de la ventana).",
        "",
        f"Frames vivos para nosotros y para la verdad: {t['live']}; con el equipo equivocado:"
        f" {t['wrong']} ({bl._dec(100 * t['wrong'] / max(1, t['live']), 1)}%). Dejamos"
        f" {t['unlabelled']} frames de la ventana en `X`; empieza con"
        f" {bl._dec(t['leading_unlabelled_s'], 1)} s sin estado, que el scorer rellena con la"
        f" primera etiqueta: {t['leading_wrong_after_fill']} de esos frames quedan con el equipo"
        " equivocado.",
        "",
        "| distancia al cambio verdadero más cercano | frames con el equipo equivocado |",
        "|---|---:|",
    ]
    for band, count in t["wrong_by_distance_to_a_change"].items():
        lines.append(f"| {band} | {count} |")
    teamless = result["teamless_restarts"]
    lines += [
        "",
        "## Reanudaciones sin equipo",
        "",
        f"{sum(teamless.values())} de las {result['restarts']} reanudaciones etiquetadas no traen"
        " equipo; `engine.restart_controls` no las fuerza.",
        "",
        "| tipo | sin equipo |",
        "|---|---:|",
    ]
    lines += [f"| {kind} | {count} |" for kind, count in teamless.items()]
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Headroom audit of the delivered chain")
    parser.add_argument("--write", type=Path, help="write the document here instead of printing")
    args = parser.parse_args(argv)
    try:
        result = measure()
    except (OSError, ValueError) as problem:
        print(f"headroom failed: {problem}", file=sys.stderr)
        return 1
    command = "python tools/headroom.py"
    if args.write:
        command += f" --write {bl._relative(args.write)}"
    text = report(result, command, bl._git_commit())
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
