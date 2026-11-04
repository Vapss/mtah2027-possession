"""DECISIONS 44: the duel rule and the short ball-outs re-decided without the ground truth.

    python tools/readjudicate.py --write docs/analysis/readjudication.md

The duel rule (DECISIONS 34) entered the delivered chain with the public slice and the bench among
its gates. Under the organisers' clarified rules, choosing a piece of the chain with the ground
truth is calibrating with it, so the rule is decided again with the judge DECISIONS 42 fixed for
rules of *whether* possession changes: the event truth of Metrica's open games g1 and g2.

Written down before measuring (DECISIONS 44, item 2): the official spellF1 against the event truth,
mean over g1 and g2, with the degraded ball of round 6 (position noise sigma = 0.85 m fixed without
labels, then our ball-presence pattern). The duel rule stays if that mean is >= the mean of
`engine.NO_DUEL`, the same chain without it; otherwise it leaves the delivery. The clean ball and
the change errors are reported as context and carry no weight. Test B (addendum A, `short_outs`)
reads only BAR-ATH's tracking and tags. Nothing here reads BAR-ATH's labels; our tracking enters
only through aggregates, in memory.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from tools import change_dating as cd  # noqa: E402
from tools import change_whether as cw  # noqa: E402
from tools import engine  # noqa: E402

CHAINS = {"con duelo (entregada)": engine.DEFAULT, "sin duelo (`engine.NO_DUEL`)": engine.NO_DUEL}
WITH, WITHOUT = CHAINS
PRIMARY = "degradado"


def conditions(game, donors) -> dict:
    """`(features, evidence, dead)` of one Metrica game, clean and degraded."""
    f, ev = cw.degraded(game, donors, cw.NOISE_SIGMA_M)
    return {
        "limpio": (game.features, game.evidence, cd.metrica_dead(game)),
        "degradado": (f, ev, cw.metrica_dead_on(game, ev)),
    }


def measure() -> list[dict]:
    """One row per game, condition and chain: spellF1 and the change errors."""
    from tools import external, metrica_open

    donors = external.our_ball_halves()
    rows = []
    for name in metrica_open.GAMES:
        game = metrica_open.load(name)
        truth = cw.metrica_truth(game)
        runs = [tuple(r) for r in game.runs]
        for cond, (f, ev, dead) in conditions(game, donors).items():
            for chain_name, params in CHAINS.items():
                scored = cw.score_metrica(
                    game, truth, cd.delivered(f, ev, runs, dead, params), runs
                )
                rows.append(
                    {
                        "game": name,
                        "condition": cond,
                        "chain": chain_name,
                        "spell_f1": scored.spell_f1,
                        "missed": len(scored.fair.missed),
                        "spurious": len(scored.fair.spurious),
                    }
                )
    return rows


def mean_spell(rows: list[dict], condition: str, chain: str) -> float:
    return float(
        np.mean(
            [r["spell_f1"] for r in rows if r["condition"] == condition and r["chain"] == chain]
        )
    )


def verdict(rows: list[dict]) -> bool:
    """The pre-registered rule: the duel rule stays when its degraded mean is >= D31's."""
    return mean_spell(rows, PRIMARY, WITH) >= mean_spell(rows, PRIMARY, WITHOUT)


def report(rows: list[dict]) -> str:
    def dec(v: float) -> str:
        return f"{v:.4f}".replace(".", ",")

    lines = [
        "# Revisión estricta: el duelo y los episodios cortos, sin ground truth (decisión 44)",
        "",
        "Generado por `python tools/readjudicate.py --write docs/analysis/readjudication.md`.",
        "No se edita a mano. Nada lee las etiquetas de BAR-ATH.",
        "",
        "## La regla del duelo en Metrica",
        "",
        "Juez: la verdad de eventos de los partidos abiertos de Metrica g1 y g2 (decisión 42).",
        "Regla pre-registrada: la regla del duelo se queda si su `spellF1` medio degradado es ≥ el",
        "de la misma cadena sin ella.",
        "",
        "| partido | condición | cadena | spellF1 | perdidos | sobrantes |",
        "|---|---|---|---:|---:|---:|",
    ]
    for r in rows:
        lines.append(
            f"| {r['game']} | {r['condition']} | {r['chain']} | {dec(r['spell_f1'])} "
            f"| {r['missed']} | {r['spurious']} |"
        )
    lines += ["", "| condición | con duelo | sin duelo | Δ |", "|---|---:|---:|---:|"]
    for cond in ("limpio", "degradado"):
        a, b = mean_spell(rows, cond, WITH), mean_spell(rows, cond, WITHOUT)
        name = f"{cond} (decide)" if cond == PRIMARY else cond
        lines.append(f"| {name} | {dec(a)} | {dec(b)} | {dec(a - b)} |")
    keep = verdict(rows)
    lines += [
        "",
        f"**Veredicto: la regla del duelo {'se queda' if keep else 'sale de la entrega'}.**",
        "",
    ]
    return "\n".join(lines)


OUT_OF_PLAY = ("Throw-in", "Corner", "Goal Kick")  # restarts that only follow a ball out
SHORT_S = 1.0  # DECISIONS 31, correction 2: the minimum it would impose


def short_outs(ev=None) -> dict:
    """DECISIONS 44, addendum A, test B: the premise of DECISIONS 31's correction 2, without labels.

    The correction says an out episode under a second is tracking noise at the line. Each tagged
    stoppage the `out` variant opens with such an episode ends at a restart; if that restart is a
    throw-in, a corner or a goal kick, the ball did go out. Counts only: tracking and tags.
    """
    from tools import dead_ball

    ev = dead_ball.load_evidence() if ev is None else ev
    params = dead_ball.DEFAULT
    merge = params.frames(params.merge_s)
    episodes = {first: n_out for first, _stop, n_out in dead_ball.out_episodes(ev.out, merge)}
    kind_at = {r.frame: r.kind for r in ev.restarts}
    short = params.frames(SHORT_S)
    counts = {"short_out_of_play": 0, "short_other": 0, "long_out_of_play": 0, "long_other": 0}
    for stoppage in dead_ball.stoppages(ev, engine.halves(), "out"):
        if stoppage.source != "out":
            continue
        size = "short" if episodes[stoppage.start] < short else "long"
        kind = "out_of_play" if kind_at.get(stoppage.stop) in OUT_OF_PLAY else "other"
        counts[f"{size}_{kind}"] += 1
    total = counts["short_out_of_play"] + counts["short_other"]
    counts["short_share_out_of_play"] = counts["short_out_of_play"] / total if total else 0.0
    # Pre-registered: correction 2 stays reverted iff more than half of the short outs are real.
    counts["correction_2_stays_reverted"] = counts["short_share_out_of_play"] > 0.5
    return counts


def short_outs_lines(b: dict) -> list[str]:
    total = b["short_out_of_play"] + b["short_other"]
    verdict = "sigue revertida" if b["correction_2_stays_reverted"] else "se adopta"
    return [
        "## Prueba B: episodios cortos fuera del campo (sin etiquetas)",
        "",
        "Paradas etiquetadas que abre un episodio fuera del campo, por la reanudación que las",
        "cierra (saque de banda, córner o saque de puerta: solo siguen a un balón fuera).",
        "",
        "| episodio | saque de banda, córner o de puerta | otra reanudación |",
        "|---|---:|---:|",
        f"| < 1 s | {b['short_out_of_play']} | {b['short_other']} |",
        f"| ≥ 1 s | {b['long_out_of_play']} | {b['long_other']} |",
        "",
        f"{b['short_out_of_play']} de {total} cortos terminan en un balón fuera "
        f"({b['short_share_out_of_play']:.0%}). Regla: la corrección 2 sigue revertida si son más "
        f"de la mitad. **Veredicto: la corrección 2 {verdict}.**",
        "",
    ]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--write", type=Path, help="write the report here instead of printing it")
    args = parser.parse_args(argv)
    text = report(measure()) + "\n" + "\n".join(short_outs_lines(short_outs()))
    if args.write:
        args.write.write_text(text, encoding="utf-8", newline="\n")
    else:
        print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
