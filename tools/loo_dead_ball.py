"""Leave-one-match-out validation of the DFL rule that fixed the dead-ball onset constants.

Pre-registered in ``docs/proposals/lane-loo-dead-v3.md`` before the first run. Nothing here reads
the public ground truth, the video or the licensed bundle: the only input is the open DFL/IDSSE
corpus (CC-BY 4.0) in ``MTAH_EXTERNAL_DIR``.

The question is not whether ``onset`` beats W1 on the seven DFL matches. That was measured, and the
constants were chosen on those same seven matches, so the "7/7" is an in-sample number. The question
is whether the *rule that chooses the constants* survives a match it did not see: fit on six,
apply to the seventh, rotate. If it does, the DFL evidence is out-of-sample and can be cited as
such; if it does not, the honest label for the DFL support is "in-sample on 7 matches".

Usage::

    MTAH_EXTERNAL_DIR=... python tools/loo_dead_ball.py --write docs/analysis/loo-dead-ball.md
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass
from math import comb
from pathlib import Path

import numpy as np

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from tools import dead_ball_v2, dead_ball_v3  # noqa: E402

# The candidate set the constants were chosen from (lane-dead-v3.md, section 2.1), unchanged. W1 is
# not a candidate: it is the baseline every fold is compared against.
ONSET_MPS = (3.0, 3.25, 3.5, 3.75)
ONSET_CAP_S = (10.0, 20.0, 40.0)
PRECISION_FLOOR = 0.90
W1 = "W1"


def candidates() -> dict[str, dead_ball_v3.Params | None]:
    """``W1`` plus every ``onset`` constant pair, named as in the lane document."""
    out: dict[str, dead_ball_v3.Params | None] = {W1: None}
    for mps in ONSET_MPS:
        for cap in ONSET_CAP_S:
            out[f"onset<{mps:g}/{cap:g}s"] = dead_ball_v3.Params(mps, cap)
    return out


@dataclass(frozen=True)
class MatchStats:
    """One match, every candidate: frame counts and the edge offsets of its detected runs."""

    match: str
    counts: dict[str, dict[str, int]]
    starts: dict[str, np.ndarray]


def match_stats(
    match: str, cands: dict[str, dead_ball_v3.Params | None] | None = None
) -> MatchStats:
    """Measure every candidate on one DFL match. The expensive part; runs once per match."""
    from tools import external

    cands = cands or candidates()
    raw = external.raw(match)
    counts = {name: {"hits": 0, "said": 0, "true": 0, "graded": 0} for name in cands}
    starts: dict[str, list[np.ndarray]] = {name: [] for name in cands}
    for section in raw.sections:
        players = np.concatenate([section.home, section.away], axis=1)
        n = len(players)
        w1 = dead_ball_v2.kinematic_mask(players, (), [(0, n)], "rule")
        known, window = dead_ball_v3.p90_window(players)
        dead, graded = section.status == 0, section.status >= 0
        for name, params in cands.items():
            mask = (
                w1 if params is None else dead_ball_v3.extend_onsets(w1, known, window, (), params)
            )
            for key, value in dead_ball_v3.frame_counts(mask, dead, graded).items():
                counts[name][key] += value
            a, _ = dead_ball_v3.edge_offsets(mask, dead)
            starts[name].append(a)
    return MatchStats(
        match,
        counts,
        {name: np.concatenate(parts) if parts else np.empty(0) for name, parts in starts.items()},
    )


def pooled(rows: Sequence[MatchStats], name: str) -> dict[str, float]:
    """Frame rates and start error of one candidate over a set of matches."""
    counts = {"hits": 0, "said": 0, "true": 0, "graded": 0}
    starts = []
    for row in rows:
        for key in counts:
            counts[key] += row.counts[name][key]
        starts.append(row.starts[name])
    a = np.concatenate(starts) if starts else np.empty(0)
    out = dead_ball_v3.rates(counts)
    out["start_abs_median_s"] = float(np.median(np.abs(a))) if a.size else float("inf")
    out["runs"] = int(a.size)
    return out


def select(rows: Sequence[MatchStats], names: Sequence[str] | None = None) -> str:
    """The lane's rule, applied to a subset: precision >= 0.90, then smallest |start| error.

    Ties on the error go to the higher F1, as they did on the full corpus (40 s over 20 s). A
    remaining tie goes to the shorter cap: less extension is the more conservative choice.
    """
    names = [n for n in (names or candidates()) if n != W1]
    eligible = []
    for name in names:
        stats = pooled(rows, name)
        if stats["precision"] >= PRECISION_FLOOR:
            eligible.append((name, stats))
    if not eligible:
        raise ValueError("no candidate keeps the frame precision floor")
    best = min(
        eligible, key=lambda item: (item[1]["start_abs_median_s"], -item[1]["f1"], _cap(item[0]))
    )
    return best[0]


def _cap(name: str) -> float:
    return float(name.rsplit("/", 1)[1].rstrip("s")) if "/" in name else 0.0


def folds(matches: Sequence[str]) -> list[tuple[list[str], str]]:
    """Every match held out once, in a fixed order."""
    return [([m for m in matches if m != held], held) for held in matches]


def _sign_p(wins: int, n: int) -> float:
    """Exact two-sided sign test: P(X >= wins) + P(X <= n - wins), X ~ Bin(n, 1/2)."""
    if n == 0:
        return 1.0
    tail = sum(comb(n, k) for k in range(wins, n + 1)) / 2**n
    return (
        min(1.0, 2 * tail)
        if wins > n / 2
        else min(1.0, 2 * sum(comb(n, k) for k in range(0, wins + 1)) / 2**n)
    )


def run(matches: Sequence[str] | None = None) -> dict:
    """Fit on six, apply to the seventh, rotate. No ground truth is read anywhere."""
    from tools import external

    matches = list(matches or external.MATCHES)
    rows = {match: match_stats(match) for match in matches}
    out_folds = []
    for train, held in folds(matches):
        chosen = select([rows[m] for m in train])
        test = rows[held]
        got, base = pooled([test], chosen), pooled([test], W1)
        out_folds.append(
            {
                "held_out": held,
                "chosen": chosen,
                "precision": got["precision"],
                "recall": got["recall"],
                "f1": got["f1"],
                "start_abs_median_s": got["start_abs_median_s"],
                "w1_precision": base["precision"],
                "w1_recall": base["recall"],
                "w1_f1": base["f1"],
                "w1_start_abs_median_s": base["start_abs_median_s"],
                "f1_delta": got["f1"] - base["f1"],
                "start_delta_s": got["start_abs_median_s"] - base["start_abs_median_s"],
                "wins": bool(got["f1"] > base["f1"]),
            }
        )
    wins = sum(f["wins"] for f in out_folds)
    full = select([rows[m] for m in matches])
    return {
        "matches": matches,
        "folds": out_folds,
        "full_fit": full,
        "stability": dict(Counter(f["chosen"] for f in out_folds)),
        "wins": wins,
        "sign_p": _sign_p(wins, len(out_folds)),
        "median_f1_delta": float(np.median([f["f1_delta"] for f in out_folds])),
        "median_start_gain_s": float(np.median([-f["start_delta_s"] for f in out_folds])),
    }


def report(result: dict, command: str = "") -> str:
    """A markdown page with the fold table and the reading of the decision rule."""
    lines = [
        "# Dead-ball onset: leave-one-match-out on DFL",
        "",
        f"Generado por `{command}`. No lee ground truth ni vídeo: solo el corpus",
        "DFL/IDSSE (CC-BY 4.0). Regla de selección, métricas y criterio de decisión:",
        "`docs/proposals/lane-loo-dead-v3.md`, commiteado antes de la primera corrida.",
        "",
        "| partido fuera | constante elegida en los otros 6 | precisión | recall | F1 "
        "| \\|inicio\\| (s) | F1 de W1 | \\|inicio\\| de W1 (s) | ΔF1 |",
        "|---|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for f in result["folds"]:
        lines.append(
            f"| {f['held_out']} | {f['chosen']} | {f['precision']:.3f} | {f['recall']:.3f} | "
            f"{f['f1']:.3f} | {f['start_abs_median_s']:.2f} | {f['w1_f1']:.3f} | "
            f"{f['w1_start_abs_median_s']:.2f} | {f['f1_delta']:+.4f} |"
        )
    lines += [
        "",
        "- Constante elegida con los 7 partidos (lo que ya estaba publicado): "
        f"**{result['full_fit']}**.",
        f"- Estabilidad de la elección entre pliegues: {result['stability']}.",
        f"- Gana a W1 en F1 fuera de muestra: **{result['wins']}/{len(result['folds'])}** "
        f"(test de signos bilateral p = {result['sign_p']:.3f}).",
        f"- ΔF1 mediano fuera de muestra: **{result['median_f1_delta']:+.4f}**; "
        f"ganancia mediana de \\|inicio\\|: **{result['median_start_gain_s']:.2f} s**.",
        "",
        "## Cómo se lee",
        "",
        "Criterio escrito antes de correr: la evidencia de DFL para `onset` es **fuera de",
        "muestra** si gana a W1 en al menos 6 de 7 pliegues y la constante elegida es la misma en",
        "al menos 5. Si no, el 7/7 publicado es un ajuste sobre los mismos siete partidos y así",
        "hay que declararlo.",
        "",
    ]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Leave-one-match-out on the DFL dead-ball corpus")
    parser.add_argument("--matches", nargs="*", help="subset of DFL match ids (default: all seven)")
    parser.add_argument("--json", type=Path, help="write the raw result here")
    parser.add_argument("--write", type=Path, help="write the markdown page here")
    args = parser.parse_args(argv)
    result = run(args.matches)
    text = report(result, "python tools/loo_dead_ball.py --write docs/analysis/loo-dead-ball.md")
    if args.json:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(
            json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )
    if args.write:
        args.write.parent.mkdir(parents=True, exist_ok=True)
        args.write.write_text(text + "\n", encoding="utf-8")
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
