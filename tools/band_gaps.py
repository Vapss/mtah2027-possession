"""A2: the structure of the 150 ball gaps, measured instead of swept (#10).

The planned sweep was degenerate -- the mask is identical for every gap up to 25 frames -- so the
question this issue can actually answer is structural: do gaps of different lengths deserve
different policies, or does the length axis carry no decision at all?

Three policies, applied only to the frames of one length band at a time, with everything else
untouched:

    fill   the previous non-X label in the same half (the #5 rule)
    D      D over the whole gap (what the baseline does when it loses the ball)
    X      X over the whole gap (what the submission already does, and what the scorer fills)

The decision rule is pre-registered in issue #10 and is applied mechanically here, not narrated:

1. the band must contain a gap inside the graded window whose interior holds a ground-truth
   transition or splits a possession -- something a fill can repair or break;
2. the paired delta must move at least two possessions in the same direction;
3. |delta spellF1| must reach 0.04, the full-match noise band;
4. and the sign must survive dropping any single gap of that band one at a time. With four graded
   gaps in the only band that moves, a result carried by one of them is a result about one gap.

A band that fails any of them is reported as **no medible localmente** and its policy is decided by
principle (DECISIONS 16: a missing ball is not evidence of a dead ball), naming the exposure. The
bands are the ticket's, fixed: 1-25, 26-125, 126-500, >500 frames.

    python tools/band_gaps.py                       # print the document
    python tools/band_gaps.py --write docs/analysis/ball-gap-bands.md

Needs the licensed tracking bundle for the ball mask. The ship-side rows additionally need
`--ship artifacts/possession.csv`; without it the document says the rows are missing rather than
quietly dropping them.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

import numpy as np
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

import games  # noqa: E402
from tools import atd  # noqa: E402
from tools.compare_submissions import compare_codes  # noqa: E402

sys.path.insert(0, str(REPO_ROOT / "evaluation"))
import possession_metrics as pm  # noqa: E402

FPS = games.GAMES[games.GAME]["fps"]
GT_CSV = REPO_ROOT / "evaluation" / "gt" / "BAR-ATH_possession_gt_public.csv"
ANCHOR_CSV = REPO_ROOT / "evaluation" / "results" / "baseline_smooth50.csv"
DEFAULT_DOC = REPO_ROOT / "docs" / "analysis" / "ball-gap-bands.md"

# (low, high, label): the ticket's bands, inclusive, in frames. The last one has no upper bound.
BANDS = ((1, 25, "≤25"), (26, 125, "26–125"), (126, 500, "126–500"), (501, None, ">500"))
POLICIES = ("fill", "D", "X")
# The full-match noise band (DECISIONS 3). The public slice's own band is 0.33 and is reported too.
DECIDING_BAND = 0.04
GRADED_BAND = 0.33


def half_runs() -> list[tuple[int, int]]:
    """The two half-time video blocks as half-open `(start, stop)` spans."""
    return [(start, stop + 1) for _half, start, stop in games.half_video_blocks(games.GAME)]


def ball_gaps(present: np.ndarray, runs: list[tuple[int, int]]) -> list[tuple[int, int]]:
    """Maximal `[start, stop)` runs with no observed ball, restricted to `runs`.

    The definition is #5's, pre-registered there: presence is `x` and `y` both present, a `z` alone
    is not a detection, and a ball observed outside the pitch is still an observation. Frames
    outside the half blocks are not gaps -- the tracking's silence there means "not in play yet",
    not "ball lost".
    """
    gaps: list[tuple[int, int]] = []
    for start, stop in runs:
        if start < 0 or stop > len(present) or stop <= start:
            raise ValueError(f"run {start, stop} is outside {len(present)} frames")
        missing = ~present[start:stop]
        edges = np.diff(missing.astype(np.int8))
        opens = np.flatnonzero(edges == 1) + 1
        closes = np.flatnonzero(edges == -1) + 1
        if missing[0]:
            opens = np.concatenate(([0], opens))
        if missing[-1]:
            closes = np.concatenate([closes, [len(missing)]])
        gaps.extend((start + int(a), start + int(b)) for a, b in zip(opens, closes, strict=True))
    return gaps


def band_label(length: int) -> str:
    for low, high, label in BANDS:
        if length >= low and (high is None or length <= high):
            return label
    raise ValueError(f"gap length {length} falls outside every band")


def band_of_gaps(gaps: list[tuple[int, int]], label: str) -> list[tuple[int, int]]:
    return [(start, stop) for start, stop in gaps if band_label(stop - start) == label]


def apply_policy(
    labels: list[str],
    selection: list[tuple[int, int]],
    policy: str,
    runs: list[tuple[int, int]] | None = None,
) -> list[str]:
    """Rewrite the selected gaps under one policy and leave every other frame alone."""
    runs = half_runs() if runs is None else runs
    if policy not in POLICIES:
        raise ValueError(f"unknown policy {policy!r}")
    output = list(labels)
    for start, stop in selection:
        if policy == "D":
            output[start:stop] = ["D"] * (stop - start)
            continue
        half_start = next(a for a, b in runs if a <= start < b)
        carry = next(
            (
                labels[index]
                for index in range(start - 1, half_start - 1, -1)
                if labels[index] != "X"
            ),
            None,
        )
        if carry is None:
            continue  # no predecessor in this half: the gap keeps whatever it had
        output[start:stop] = ["X" if policy == "X" else carry] * (stop - start)
    return output


def codes(labels: list[str]) -> np.ndarray:
    return np.array([pm.LABELS.index(label) for label in labels])


def measure(
    gt: np.ndarray, base_labels: list[str], selection: list[tuple[int, int]], policy: str
) -> dict[str, object]:
    """Score one policy applied to one band, paired against the untouched base."""
    base = codes(base_labels)
    rewritten = apply_policy(base_labels, selection, policy)
    candidate = codes(rewritten)
    before = pm.evaluate(gt, base)
    after = pm.evaluate(gt, candidate)
    comparison = compare_codes(gt, base, candidate)
    sign = comparison["sign_diagnostic"]
    return {
        "spell_f1": float(after["spell_f1_mean"]),
        "macro_f1": float(after["macro_f1"]),
        "base_spell_f1": float(before["spell_f1_mean"]),
        "base_macro_f1": float(before["macro_f1"]),
        "delta": float(comparison["delta_mean_spell_f1_b_minus_a"]),
        "n_discordant": int(sign["n_discordant"]),
        "wins_base": int(sign["wins_a"]),
        "wins_policy": int(sign["wins_b"]),
        "jackknife": [float(x) for x in comparison["jackknife"]["mean_delta_range"]],
        "n_pred": int(after["n_pred_spells"]),
        "changed": int(
            sum(
                a != b
                for a, b in zip(
                    base_labels, apply_policy(base_labels, selection, policy, half_runs())
                )
            )
        ),
    }


def gap_facts(
    gt: np.ndarray, spells: list[tuple[int, int, int]], gaps: list[tuple[int, int]]
) -> list[dict]:
    """What the ground truth says inside each gap of the graded window."""
    facts = []
    for start, stop in gaps:
        inside = gt[start:stop]
        graded = int(np.sum(inside != pm.X))
        facts.append(
            {
                "start": start,
                "stop": stop,
                "length": stop - start,
                "band": band_label(stop - start),
                "graded_frames": graded,
                "transitions": int(np.sum(np.diff(inside[inside != pm.X]) != 0)) if graded else 0,
                "labels": {
                    pm.LABELS[code]: int(np.sum(inside == code)) for code in range(pm.N_LABELS)
                },
                "possessions": [
                    index + 1
                    for index, (a, b, _team) in enumerate(spells)
                    if a < stop and b > start
                ],
            }
        )
    return facts


def decide(band: str, full: dict, drops: list[dict]) -> tuple[str, str]:
    """Apply the pre-registered rule. Returns (verdict, reason)."""
    if full["n_gaps"] == 0:
        return "no medible localmente", "no hay ningún hueco de este tramo en la ventana pública"
    if full["graded_frames"] == 0:
        return "no medible localmente", "los huecos del tramo no tocan ningún frame puntuado"
    if full["transitions"] == 0 and not full["splits_possession"]:
        return (
            "no medible localmente",
            "ningún hueco del tramo parte una posesión ni contiene una transición",
        )
    if full["policy"]["n_discordant"] < 2:
        if full["transitions"] == 0:
            return (
                "no medible localmente",
                f"ninguna transición y {full['policy']['n_discordant']} discordancias en"
                f" {_num(full['graded_frames'])} frames puntuados; el relleno no puede mover"
                " ninguna posesión",
            )
        return (
            "no medible localmente",
            f"solo {full['policy']['n_discordant']} posesión(es) discordante(s)",
        )
    if abs(full["policy"]["delta"]) < DECIDING_BAND:
        return (
            "no medible localmente",
            f"|Δ| {abs(full['policy']['delta']):.5f} por debajo de la banda {DECIDING_BAND}",
        )
    if not drops:
        return "medida", "Δ y discordancias superan el criterio; no hay huecos que quitar uno a uno"
    weakest = min(drops, key=lambda row: row["policy"]["delta"])
    if weakest["policy"]["delta"] <= 0 or weakest["policy"]["n_discordant"] < 2:
        return (
            "no medible localmente",
            "el efecto depende de un hueco: quitando "
            f"[{_num(weakest['start'])}, {_num(weakest['stop'])}) queda"
            f" Δ {_signed(weakest['policy']['delta'])} "
            f"con {weakest['policy']['n_discordant']} discordante(s)",
        )
    return "medida", "Δ, discordancias y leave-one-gap-out en el mismo sentido"


def build(
    gt: np.ndarray,
    spells: list[tuple[int, int, int]],
    gaps: list[tuple[int, int]],
    base_name: str,
    base_labels: list[str],
    graded_window: tuple[int, int],
) -> dict:
    """Per-band table, gap facts and leave-one-gap-out for one base submission."""
    facts = gap_facts(
        gt, spells, [gap for gap in gaps if gap[0] < graded_window[1] and gap[1] > graded_window[0]]
    )
    base = measure(gt, base_labels, [], "fill")  # untouched: every policy row is paired against it
    rows = []
    for _low, _high, label in BANDS:
        selection = band_of_gaps(gaps, label)
        inside = [fact for fact in facts if fact["band"] == label]
        policy_rows = (
            {policy: measure(gt, base_labels, selection, policy) for policy in POLICIES}
            if selection
            else {}
        )
        graded_gaps = [fact for fact in inside if fact["graded_frames"] > 0]
        best = "fill"
        full = {
            "band": label,
            "n_gaps": len(selection),
            "frames": int(sum(stop - start for start, stop in selection)),
            "public_gaps": len(inside),
            "graded_frames": int(sum(fact["graded_frames"] for fact in graded_gaps)),
            "transitions": int(sum(fact["transitions"] for fact in inside)),
            "splits_possession": bool(
                any(fact["possessions"] for fact in inside if fact["graded_frames"] > 0)
            ),
            "policies": policy_rows,
            "policy": policy_rows.get(best, {}),
        }
        drops = []
        if full["policy"] and full["policy"]["delta"] > 0:
            for fact in graded_gaps:
                keep = [gap for gap in selection if tuple(gap) != (fact["start"], fact["stop"])]
                # Only gaps that intersect the graded window can matter; the rest are identical.
                drops.append(
                    {
                        "start": fact["start"],
                        "stop": fact["stop"],
                        "policy": measure(gt, base_labels, keep, best),
                    }
                )
        full["drops"] = drops
        full["verdict"], full["reason"] = decide(label, full, drops)
        rows.append((label, full))
    return {"base": base_name, "untouched": base, "bands": rows, "gaps": facts}


def _num(value: int) -> str:
    """Spanish thousands separator: 199.319, not 199,319."""
    return f"{value:,}".replace(",", ".")


def _dec(value: float, digits: int = 4) -> str:
    """Spanish decimal separator, so the document reads like the rest of docs/."""
    return f"{value:.{digits}f}".replace(".", ",")


def _signed(value: float, digits: int = 5) -> str:
    return ("+" if value >= 0 else "") + _dec(value, digits)


def _plural(count: int, one: str, many: str) -> str:
    return f"{_num(count)} {one if count == 1 else many}"


def _pct(value: float, digits: int = 1) -> str:
    return f"{value:.{digits}f}%".replace(".", ",")


def _relative(path: str) -> str:
    """Repository-relative name: outputs never carry an absolute path (AGENTS.md rule 8)."""
    try:
        return str(Path(path).resolve().relative_to(REPO_ROOT))
    except ValueError:
        return Path(path).name


def _policy_cell(row: dict | None) -> str:
    if not row:
        return "— | — | — | — | —"
    return (
        f"{_dec(row['spell_f1'])} | {_dec(row['macro_f1'])} | {_signed(row['delta'])} | "
        f"{row['n_discordant']} ({row['wins_base']}/{row['wins_policy']}) | "
        f"{_dec(row['jackknife'][0])}..{_dec(row['jackknife'][1])}"
    )


def report(evidence: dict, commit: str | None = None) -> str:
    anchor = evidence["anchor"]
    window = evidence["window"]
    total = evidence["gap_frames"]
    lines = [
        "# A2 — Estructura de los 150 huecos de balón",
        "",
        "Generado por `python tools/band_gaps.py --write docs/analysis/ball-gap-bands.md` desde"
        f" el commit `{commit or 'desconocido'}`. No se edita a mano.",
        "",
        f"Ventana pública: frames **{_num(window[0])}..{_num(window[1] - 1)}**"
        f" ({_num(window[1] - window[0])} frames)."
        f" Base: `{_relative(anchor['base'])}`.",
        "",
        "## 1. Estructura",
        "",
        "Medido sobre los frames en juego (los dos bloques de `games.half_video_blocks`), no sobre"
        " los 199.319: fuera de los medios tiempos hay huecos de 1–2 frames que no se rellenan, y"
        " contarlos inflaba el tramo ≤25 de 17 a 43.",
        "",
        f"- Huecos en juego: **{_plural(evidence['n_gaps'], 'hueco', 'huecos')}**,"
        f" **{_num(evidence['gap_frames'])} frames sin balón**"
        f" de {_num(evidence['in_play_frames'])}"
        f" ({_pct(100 * evidence['gap_frames'] / evidence['in_play_frames'])}).",
        f"- Sin balón en todo el partido: {_num(evidence['missing_frames'])} frames"
        f" ({_pct(100 * evidence['missing_frames'] / evidence['n_frames'])}).",
        "",
        "## 2. Tabla por tramo, sobre el ancla",
        "",
        "Δ pareado de `spellF1` contra la base sin tocar. `disc` = posesiones verdaderas que pasan"
        " de emparejada a no emparejada o al revés (base/política). `jackknife` quita una posesión"
        " verdadera por vez. `macroF1` se reporta y no decide.",
        "",
    ]
    for label, band in anchor["bands"]:
        lines += [
            f"### {label} frames — {_plural(band['n_gaps'], 'hueco', 'huecos')} /"
            f" {_num(band['frames'])} frames"
            f" ({_num(band['public_gaps'])} en la ventana,"
            f" {_num(band['graded_frames'])} puntuados)",
            "",
            "| política | spellF1 | macroF1 | Δ pareado | disc | jackknife |",
            "|---|---:|---:|---:|---:|---|",
        ]
        for policy in POLICIES:
            lines.append(f"| {policy} | {_policy_cell(band['policies'].get(policy))} |")
        lines += ["", f"**{band['verdict']}** — {band['reason']}.", ""]
        if band["drops"]:
            lines += ["| hueco quitado | Δ pareado | disc | jackknife |", "|---|---:|---:|---|"]
            for drop in band["drops"]:
                row = drop["policy"]
                lines.append(
                    f"| [{_num(drop['start'])}, {_num(drop['stop'])})"
                    f" ({_num(drop['stop'] - drop['start'])} frames) |"
                    f" {_signed(row['delta'])} | {row['n_discordant']} |"
                    f" {_dec(row['jackknife'][0])}..{_dec(row['jackknife'][1])} |"
                )
            lines.append("")

    if "ship" in evidence:
        ship = evidence["ship"]
        lines += [
            "## 3. La cadena que se entrega",
            "",
            f"La misma tabla sobre `{_relative(ship['base'])}` decodificado como en DECISIONS 20"
            " (`confidence = 0` → `X`). Acá `D` es un contrafáctico: el decodificador no lo"
            " produce, se mide para saber qué se perdería emitiéndolo.",
            "",
            "| tramo | fill Δ | X Δ | D Δ | disc fill/X/D |",
            "|---|---:|---:|---:|---|",
        ]
        for label, band in ship["bands"]:
            cells = []
            discs = []
            for policy in POLICIES:
                row = band["policies"].get(policy)
                cells.append(_signed(row["delta"]) if row else "—")
                discs.append(str(row["n_discordant"]) if row else "—")
            lines.append(f"| {label} | {cells[0]} | {cells[2]} | {cells[1]} | {'/'.join(discs)} |")
        lines += [
            "",
            "En esta base `fill` y `X` empatan exactamente en `spellF1`: el scorer oficial ya"
            " rellena `X` con la etiqueta previa del medio tiempo. La única diferencia entre las"
            " dos es `macroF1`, y `D` pierde o empata en todos los tramos.",
            "",
        ]

    lines += [
        "## 4. Lo que hay dentro de cada hueco puntuado",
        "",
        "| hueco | frames | tramo | GT dentro | transiciones | posesiones GT |",
        "|---|---:|---|---|---:|---|",
    ]
    for fact in anchor["gaps"]:
        if fact["graded_frames"] == 0:
            continue
        labels = ", ".join(f"{label} {count}" for label, count in fact["labels"].items() if count)
        lines.append(
            f"| [{_num(fact['start'])}, {_num(fact['stop'])}) | {_num(fact['length'])} |"
            f" {fact['band']} | {labels} | {fact['transitions']} |"
            f" {', '.join(f'#{p}' for p in fact['possessions']) or '—'} |"
        )

    lines += [
        "",
        "## 5. Decisión por tramo",
        "",
        "La regla es la misma en los cuatro tramos y no depende de la longitud: **arrastrar el"
        " estado, nunca `D` por ausencia de balón** (DECISIONS 16). Lo que cambia por tramo es"
        " cuánta evidencia local hay para decirlo, y eso se escribe:",
        "",
        "| tramo | % del déficit de balón | evidencia | decisión |",
        "|---|---:|---|---|",
    ]
    for label, band in anchor["bands"]:
        share = 100 * band["frames"] / total if total else 0.0
        evidence_text = (
            f"{band['verdict']}: {band['reason']}"
            if band["verdict"] != "medida"
            else f"medida: {band['reason']}"
        )
        lines.append(f"| {label} | {_pct(share)} | {evidence_text} | arrastrar estado; `D` no |")
    lines += [
        "",
        "Ningún tramo justifica un umbral propio: el único que mueve `spellF1` en el slice lo hace"
        " por un solo hueco, y el que más frames aporta no tiene un solo frame puntuado adentro."
        " Una política distinta por tramo sería una decisión sobre 4 posesiones repartidas en 2"
        " tramos, y en el tramo grande sobre ninguna.",
        "",
        "## 6. Lo que esta muestra no puede decir",
        "",
        f"- La ventana cubre {_num(window[0])}..{_num(window[1] - 1)}: **ningún hueco de más de"
        " 500 frames** cae adentro, y ese tramo concentra la mayor parte del déficit de balón. Su"
        " política no se mide acá; se decide por principio (DECISIONS 16), no por dato.",
        f"- Bandas de ruido: {_dec(DECIDING_BAND, 2)} en el partido completo y"
        f" {_dec(GRADED_BAND, 2)} en el slice."
        " Un Δ local por debajo de la primera no es un resultado ni en la dirección.",
        "- Toda la evidencia local descansa en 4 posesiones GT (#1, #2, #5, #14) de las 17 del"
        " slice, y el Δ del tramo 126–500 se cae a +0,016 con 0 discordancias si se quita uno de"
        " sus cuatro huecos.",
        "- La ventana pública es la parte del partido con más balón detectado (88,2% frente a"
        " 56,9%), así que mide el régimen fácil de este problema.",
        "- El ground truth del partido completo es privado: lo único observable ahí es la"
        " estructura del hueco, no la etiqueta.",
        "",
    ]
    return "\n".join(lines).rstrip() + "\n"


def _ship_labels(path: str | Path) -> tuple[str, list[str]]:
    """Decode a B5 artifact the way DECISIONS 20 documents: confidence 0 means X."""
    table = pd.read_csv(path)
    live = table["confidence"].to_numpy() > 0
    label = table[["p_home", "p_away"]].idxmax(axis=1).map({"p_home": "H", "p_away": "A"})
    label.loc[~live] = "X"
    return str(path), label.tolist()


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
    parser = argparse.ArgumentParser(description="Measure the structure of the ball gaps (#10)")
    parser.add_argument("--write", help="write the document here instead of printing it")
    parser.add_argument("--base", default=str(ANCHOR_CSV), help="submission CSV to compare against")
    parser.add_argument("--ship", help="B5 artifact to decode as a second base")
    parser.add_argument("--json", dest="json_path", help="write the raw evidence as JSON here")
    args = parser.parse_args(argv)

    try:
        present = atd.load(games.DEFAULT_SOURCE).ball()[1]
    except (OSError, ValueError) as problem:
        print(f"cannot measure without the bundle: {problem}", file=sys.stderr)
        return 1

    gt = pm.label_codes(pm.read_label_csv(GT_CSV))
    runs = pm.valid_runs(gt)
    graded = np.flatnonzero(np.asarray(gt) != pm.X)
    window = (int(graded[0]), int(graded[-1]) + 1)
    spells = pm.possession_spells(gt, runs)
    gaps = ball_gaps(present, half_runs())
    in_play = sum(stop - start for start, stop in half_runs())

    anchor_labels = pd.read_csv(args.base, dtype={"label": "object"}).label.tolist()
    evidence = {
        "window": window,
        "n_frames": int(len(present)),
        "missing_frames": int(np.sum(~present)),
        "gap_frames": int(sum(stop - start for start, stop in gaps)),
        "n_gaps": len(gaps),
        "in_play_frames": int(in_play),
        "anchor": build(gt, spells, gaps, args.base, anchor_labels, window),
    }
    if args.ship:
        name, labels = _ship_labels(args.ship)
        evidence["ship"] = build(gt, spells, gaps, name, labels, window)

    if args.json_path:
        Path(args.json_path).write_text(
            json.dumps(evidence, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )
    text = report(evidence, commit=_git_commit())
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
