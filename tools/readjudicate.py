"""DECISIONS 45, addendum A, test B: the short ball-outs re-decided without the ground truth.

    python tools/readjudicate.py --write docs/analysis/readjudication.md

DECISIONS 31 reverted its correction 2 (an out episode under a second does not open a stoppage)
with evidence from the public slice. Under the organisers' clarified rules that cannot decide, so
its premise is judged again from the tracking and the tags alone, with a rule written before
measuring: the correction stays reverted if more than half of the tagged stoppages opened by a
short episode end in a throw-in, a corner or a goal kick (restarts that only follow a ball out).

The duel rule's test on Metrica's open games, which this tool also ran, was withdrawn: Metrica's
data declares no licence, and DECISIONS 44 requires written permission before using it as evidence
(DECISIONS 45, addendum B). Nothing here reads BAR-ATH's labels.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from tools import engine  # noqa: E402

OUT_OF_PLAY = ("Throw-in", "Corner", "Goal Kick")  # restarts that only follow a ball out
SHORT_S = 1.0  # DECISIONS 31, correction 2: the minimum it would impose


def short_outs(ev=None) -> dict:
    """DECISIONS 45, addendum A, test B: the premise of DECISIONS 31's correction 2, without labels.

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
        "## Prueba B: episodios cortos fuera del campo",
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


def report(b: dict) -> str:
    return "\n".join(
        [
            "# Revisión estricta: los episodios cortos fuera del campo, sin ground truth",
            "",
            "Generado por `python tools/readjudicate.py --write docs/analysis/readjudication.md`.",
            "No se edita a mano. Nada lee las etiquetas de BAR-ATH (decisión 45, adenda A).",
            "",
            *short_outs_lines(b),
        ]
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--write", type=Path, help="write the report here instead of printing it")
    args = parser.parse_args(argv)
    text = report(short_outs())
    if args.write:
        args.write.write_text(text, encoding="utf-8", newline="\n")
    else:
        print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
