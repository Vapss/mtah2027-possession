"""#36 D6 -- structural holdout: the match in 22 five-minute blocks, with no ground truth.

Why this exists
---------------
The public ground truth is 17 possessions in the first five minutes, and those five minutes are the
easiest of the match: 88,2% of their frames have the ball detected against 56,9% overall
(DECISIONS 13). A system tuned there can break on the blocks where the tracker loses the ball, and
nothing measured locally would say so. This report looks at every block of the match and asks only
structural questions -- how many possessions, how long, how much `D`, which side -- next to how
much ball the tracker saw and whether the Smart Tagging agrees on who had it.

What it is not
--------------
Not a metric to optimise, and not a reconstruction of the private ground truth: it reads a
submission, the tracking and the tagging, never a label it was not given. The reference rates
(3,4 possessions per minute, 14,2 s) come from the public slice itself, so they are a sanity anchor
and not a target: #35 explains why a band around them would be circular.

Blocks
------
Each half-time video block (`games.half_video_blocks`) is cut into consecutive 7.500-frame blocks
(5 minutes at 25 fps) from its first frame; the last block of a half is shorter. BAR-ATH gives 11
per half, 22 in all, and block 1 is exactly the public ground-truth window (11.185..18.684).

How each column is computed
---------------------------
- Abstentions are filled the way the official scorer fills them
  (`possession_metrics.fill_abstentions`) before anything is counted, so an `X` inside a possession
  does not split it.
- A possession is a maximal `H` or `A` run inside a half (`possession_metrics.possession_spells`).
  It is counted in the block where it starts, with its full length, even past the block -- so the
  count and the mean say how often possessions *begin*.
- That alone would hide the failure this report is for: one possession carried across a long gap
  starts in one block and fills the next, which then shows a few short fragments. `larga` is the
  share of the block covered by the longest possession that overlaps it, clipped to the block.
- `%D` is per frame inside the block; `%H` is over the frames labelled `H` or `A`.
- Smart Tagging: a frame is *covered* when its phases vote for exactly one side
  (`smart_tagging.possession_votes`); *agreement* is the share of covered `H`/`A` frames whose label
  is that side.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

import numpy as np

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

import games  # noqa: E402
from tools import atd  # noqa: E402
from tools import smart_tagging as st  # noqa: E402
from tools.contract import read_submission  # noqa: E402

sys.path.insert(0, str(REPO_ROOT / "evaluation"))
import possession_metrics as pm  # noqa: E402

FPS = games.GAMES[games.GAME]["fps"]
BLOCK_FRAMES = 5 * 60 * FPS
# From the public slice (17 possessions in 5 minutes, mean 354,8 frames): an anchor, not a target.
# It is a mean, so the report shows the mean duration next to it, never the median.
REFERENCE_RATE = 3.4
REFERENCE_SECONDS = 14.2


@dataclass(frozen=True)
class Block:
    index: int  # 1-based, in match order
    half: int
    start: int
    stop: int  # exclusive

    @property
    def minutes(self) -> float:
        return (self.stop - self.start) / FPS / 60


@dataclass(frozen=True)
class Row:
    label: str
    minutes: float
    ball: float
    possessions: int
    rate: float
    mean_s: float
    longest: float
    dead: float
    home: float
    st_cover: float
    st_agree: float


def blocks(halves: Sequence[tuple[int, int, int]], size: int = BLOCK_FRAMES) -> list[Block]:
    """Cut each `(half, start, stop)` half-open span into consecutive blocks of `size` frames."""
    out: list[Block] = []
    for half, start, stop in halves:
        for first in range(start, stop, size):
            out.append(Block(len(out) + 1, half, first, min(first + size, stop)))
    return out


def halves(game: str = games.GAME) -> list[tuple[int, int, int]]:
    """The playing halves as `(half, start, stop)` with `stop` exclusive."""
    return [(half, start, stop + 1) for half, start, stop in games.half_video_blocks(game)]


def _share(mask: np.ndarray) -> float:
    return float(mask.mean()) if mask.size else float("nan")


def _row(
    label: str,
    spans: Sequence[tuple[int, int]],
    filled: np.ndarray,
    spells: Sequence[tuple[int, int, int]],
    present: np.ndarray,
    votes: np.ndarray,
) -> Row:
    """One table row over the union of `spans` (one block, or the whole match)."""
    index = np.concatenate([np.arange(a, b) for a, b in spans])
    codes = filled[index]
    lengths = [b - a for a, b, _ in spells if any(s <= a < e for s, e in spans)]
    clipped = [sum(max(0, min(b, e) - max(a, s)) for s, e in spans) for a, b, _ in spells]
    minutes = len(index) / FPS / 60
    alive = (codes == pm.H) | (codes == pm.A)

    vote = votes[index]
    single = (vote[:, 0] > 0) ^ (vote[:, 1] > 0)
    owner = np.where(vote[:, 0] > 0, pm.H, pm.A)
    judged = single & alive
    return Row(
        label=label,
        minutes=minutes,
        ball=_share(present[index]),
        possessions=len(lengths),
        rate=len(lengths) / minutes if minutes else float("nan"),
        mean_s=float(np.mean(lengths)) / FPS if lengths else float("nan"),
        longest=max(clipped, default=0) / len(index) if len(index) else float("nan"),
        dead=_share(codes == pm.D),
        home=float((codes == pm.H).sum() / alive.sum()) if alive.any() else float("nan"),
        st_cover=_share(single),
        st_agree=_share(codes[judged] == owner[judged]),
    )


def measure(
    labels: Sequence[str],
    present: np.ndarray,
    votes: np.ndarray,
    cut: Sequence[Block],
    runs: Sequence[tuple[int, int]],
) -> list[Row]:
    """Per-block rows, then one row for the whole match."""
    codes = pm.label_codes(list(labels))
    filled = pm.fill_abstentions(codes, list(runs))
    spells = pm.possession_spells(filled, list(runs))
    rows = [
        _row(
            f"{b.index}★" if b.index == 1 else str(b.index),
            [(b.start, b.stop)],
            filled,
            spells,
            present,
            votes,
        )
        for b in cut
    ]
    rows.append(_row("partido", list(runs), filled, spells, present, votes))
    return rows


def _pct(value: float) -> str:
    return "—" if np.isnan(value) else f"{100 * value:.1f}%".replace(".", ",")


def _dec(value: float, digits: int = 2) -> str:
    return "—" if np.isnan(value) else f"{value:.{digits}f}".replace(".", ",")


def _relative(path: str | Path) -> str:
    """Repository-relative POSIX name: outputs never carry an absolute or OS-specific path."""
    try:
        return Path(path).resolve().relative_to(REPO_ROOT).as_posix()
    except ValueError:
        return Path(path).name


def report(
    measured: dict[str, list[Row]],
    cut: Sequence[Block],
    command: str,
    commit: str | None = None,
) -> str:
    """The document. Every number comes from `measured`; nothing is typed in by hand."""
    origin = f" desde el commit `{commit}`" if commit else ""
    lines = [
        "# D6 — Holdout estructural: el partido en 22 bloques de 5 minutos",
        "",
        f"Generado por `{command}`{origin}. No se edita a mano.",
        "",
        "Diagnóstico de cordura, **no una métrica que optimizar** (#36). No usa ground truth: cada",
        "bloque se describe con la submission, el tracking y el Smart Tagging. El bloque 1★ es la",
        "ventana pública. Referencias del slice público, no objetivos: "
        f"{_dec(REFERENCE_RATE, 1)} posesiones/min, {_dec(REFERENCE_SECONDS, 1)} s de media.",
        "",
        "Columnas: `balón` = frames con balón detectado; `pos/min` = posesiones que empiezan en",
        "el bloque por minuto; `media` = su duración media; `larga` = parte del bloque que cubre",
        "la posesión más larga que lo toca (una posesión arrastrada desde el bloque anterior sale",
        "aquí, no en `pos`); `%H` sobre los frames `H`/`A`; `ST cob` = frames donde el Smart",
        "Tagging vota por un solo equipo; `ST acuerdo` = de esos, los que la submission etiqueta",
        "con ese equipo.",
    ]
    names = list(measured)
    lines += ["", "## Comparación: posesiones por minuto", ""]
    lines.append("| bloque | mitad | min | balón | " + " | ".join(f"`{n}`" for n in names) + " |")
    lines.append("|---|---:|---:|---:|" + "---:|" * len(names))
    for i, block in enumerate(cut):
        first = measured[names[0]][i]
        rates = " | ".join(_dec(measured[n][i].rate) for n in names)
        lines.append(
            f"| {first.label} | {block.half} | {_dec(first.minutes, 1)} | {_pct(first.ball)} "
            f"| {rates} |"
        )
    total = measured[names[0]][-1]
    rates = " | ".join(f"**{_dec(measured[n][-1].rate)}**" for n in names)
    lines.append(f"| **partido** | | {_dec(total.minutes, 1)} | {_pct(total.ball)} | {rates} |")

    for name, rows in measured.items():
        lines += ["", f"## `{name}`", ""]
        lines.append(
            "| bloque | balón | pos | pos/min | media | larga | %D | %H | ST cob | ST acuerdo |"
        )
        lines.append("|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|")
        for row in rows:
            cells = [
                row.label,
                _pct(row.ball),
                str(row.possessions),
                _dec(row.rate),
                f"{_dec(row.mean_s, 1)} s",
                _pct(row.longest),
                _pct(row.dead),
                _pct(row.home),
                _pct(row.st_cover),
                _pct(row.st_agree),
            ]
            if row.label == "partido":
                cells = [f"**{cell}**" for cell in cells]
            lines.append("| " + " | ".join(cells) + " |")
        # Every block counts, empty ones included: a block with no possession is the broken
        # structure this report exists to show, so it must not drop out of the range.
        per_block = rows[:-1]
        if per_block:
            rates = [row.rate for row in per_block]
            empty = sum(1 for row in per_block if row.possessions == 0)
            lines += [
                "",
                f"Rango de posesiones/min entre bloques: {_dec(min(rates))} .. {_dec(max(rates))}; "
                f"bloques sin ninguna posesión: {empty}.",
            ]
    return "\n".join(lines) + "\n"


# The paths whose state decides the numbers. A change anywhere else (docs, tests) does not.
CODE_PATHS = ("tools", "evaluation", "starter", "games.py", "configs")


def _git_commit() -> str | None:
    """HEAD, marked `-dirty` when the code that produced the numbers is not what HEAD holds.

    Untracked files count: a new module that only exists in the working tree is exactly the case
    where the named commit cannot reproduce the document.
    """

    def git(*args: str) -> subprocess.CompletedProcess:
        return subprocess.run(["git", "-C", str(REPO_ROOT), *args], capture_output=True, text=True)

    try:
        head = git("rev-parse", "--short=8", "HEAD")
        status = git("status", "--porcelain", "--", *CODE_PATHS)
    except OSError:
        return None
    if head.returncode != 0:
        return None
    dirty = status.returncode != 0 or bool(status.stdout.strip())
    return head.stdout.strip() + ("-dirty" if dirty else "")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Structural report of submissions in 22 blocks")
    parser.add_argument("submissions", nargs="+", help="frame,label CSVs to describe")
    parser.add_argument("--write", help="write the document here instead of printing it")
    parser.add_argument("--commit", default=None, help="commit to name in the header")
    args = parser.parse_args(argv)

    names = [Path(path).stem for path in args.submissions]
    clash = sorted({name for name in names if names.count(name) > 1})
    if clash:
        print(f"two inputs share a file name, the report would drop one: {clash}", file=sys.stderr)
        return 1

    try:
        runs = [(start, stop) for _half, start, stop in halves()]
        cut = blocks(halves())
        present = atd.load(games.DEFAULT_SOURCE).ball()[1]
        votes = st.possession_votes(st.load())
        measured = {}
        for name, path in zip(names, args.submissions):
            # read_submission validates; label_codes strips and upper-cases.
            labels = read_submission(path).iloc[:, 1].tolist()
            measured[name] = measure(labels, present, votes, cut, runs)
    except (OSError, ValueError) as problem:
        print(f"cannot build the block report: {problem}", file=sys.stderr)
        return 1

    command = "python tools/blocks.py " + " ".join(_relative(p) for p in args.submissions)
    if args.write:
        command += f" --write {_relative(args.write)}"
    text = report(measured, cut, command, commit=args.commit or _git_commit())
    if args.write:
        target = Path(args.write)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8", newline="\n")
        print(f"wrote {_relative(target)}")
    else:
        # The document is UTF-8 (★, —, accents); a Windows console defaults to cp1252.
        if hasattr(sys.stdout, "reconfigure"):
            sys.stdout.reconfigure(encoding="utf-8")
        sys.stdout.write(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
