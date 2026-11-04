"""Figures of the technical document, as SVG next to this file.

    python docs/paper/figures.py

Every figure is either a synthetic illustration (made-up positions, no match data: the licensed
data must not be published, RULES.md) or a chart of external data (Metrica's open games). The
numbers of the external chart are read from `docs/analysis/readjudication.md`, the generated report
of DECISIONS 44, so the figure cannot drift from it.
"""

from __future__ import annotations

import re
from pathlib import Path

import matplotlib

matplotlib.use("svg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.patches import Circle, FancyArrowPatch, FancyBboxPatch, Rectangle  # noqa: E402

HERE = Path(__file__).resolve().parent
REPO = HERE.parent.parent
HOME, AWAY, BALL, DEAD, GREY = "#1f5fa8", "#c0392b", "#111111", "#8a8a8a", "#bdbdbd"
plt.rcParams.update(
    {
        "font.family": "serif",
        "font.size": 8.5,
        "svg.fonttype": "none",  # text stays text: selectable in the PDF
        "axes.spines.top": False,
        "axes.spines.right": False,
        "svg.hashsalt": "possession",  # stable ids: the same figure gives the same file
    }
)


def _save(fig, name: str) -> None:
    fig.savefig(HERE / name, bbox_inches="tight", metadata={"Date": None})
    plt.close(fig)


def _pitch(ax, title: str) -> None:
    ax.set_xlim(0, 10)
    ax.set_ylim(0, 6.5)
    ax.set_aspect("equal")
    ax.axis("off")
    ax.add_patch(Rectangle((0, 0), 10, 6.5, fc="#f3f7f1", ec=GREY, lw=0.6))
    ax.set_title(title, fontsize=8.5, loc="left")


def _player(ax, x, y, colour, label=None):
    ax.add_patch(Circle((x, y), 0.32, fc=colour, ec="white", lw=0.8, zorder=3))
    if label:
        ax.text(x, y - 0.75, label, ha="center", va="top", fontsize=7, color=colour)


def _ball(ax, x, y):
    ax.add_patch(Circle((x, y), 0.15, fc="white", ec=BALL, lw=1.0, zorder=4))


def _reach(ax, x, y, colour):
    ax.add_patch(Circle((x, y), 1.5, fc="none", ec=colour, lw=0.8, ls="--", zorder=2))


def rules() -> None:
    """Four synthetic snapshots, one per rule of the engine (section 3)."""
    fig, axes = plt.subplots(1, 4, figsize=(7.0, 2.25))
    a, b, c, d = axes

    _pitch(a, "(a) control")
    _player(a, 3.0, 3.6, HOME, "home")
    _player(a, 8.0, 5.2, AWAY, "away")
    _ball(a, 3.9, 3.0)
    _reach(a, 3.9, 3.0, HOME)
    a.set_xlabel("nearest ≤ 1.5 m, rival farther,\nball ≤ 5 m/s → home controls", fontsize=6.8)

    _pitch(b, "(b) duel: no change")
    _player(b, 3.6, 3.9, HOME, "home (has it)")
    _player(b, 6.4, 3.9, AWAY, "away")
    _ball(b, 5.4, 3.3)
    _reach(b, 5.4, 3.3, GREY)
    b.set_xlabel("away is nearest, but home is\nwithin 1.5 m → possession stays", fontsize=6.8)

    _pitch(c, "(c) loose ball / pass")
    _player(c, 1.4, 2.2, HOME, "passer")
    _player(c, 8.6, 4.6, HOME, "receiver")
    _player(c, 5.6, 5.6, AWAY)
    _ball(c, 4.8, 3.5)
    c.add_patch(
        FancyArrowPatch(
            (1.9, 2.5), (8.1, 4.4), arrowstyle="-|>", mutation_scale=8, color=BALL, lw=0.8, ls=":"
        )
    )
    c.set_xlabel("nobody controls (> 5 m/s):\nthe last team keeps it", fontsize=6.8)

    _pitch(d, "(d) restart")
    d.add_patch(Rectangle((9.6, 0), 0.4, 6.5, fc="#e6e6e6", ec="none"))
    _player(d, 8.9, 2.2, AWAY, "taker")
    _player(d, 5.0, 3.6, HOME)
    _ball(d, 9.75, 1.6)
    d.text(
        4.6,
        5.6,
        "tag: Throw-in, away",
        ha="center",
        fontsize=6.6,
        bbox={"fc": "white", "ec": GREY, "lw": 0.5},
    )
    d.set_xlabel("dead until the kick; then\nthe restarting team has it", fontsize=6.8)
    for ax in axes:
        ax.axis("on")
        ax.set_xticks([])
        ax.set_yticks([])
        for side in ax.spines.values():
            side.set_visible(False)
    fig.tight_layout(w_pad=0.8)
    _save(fig, "rules.svg")


def timeline() -> None:
    """A synthetic 40 s: controls -> decoded state -> stoppages -> labels (section 3)."""
    fig, ax = plt.subplots(figsize=(7.0, 1.9))
    rows = {"controls": 3, "state": 2, "stoppages": 1, "label": 0}
    controls = [
        (1, 3, HOME),
        (5, 6, HOME),
        (9, 9.6, AWAY, "duel"),
        (12, 14, HOME),
        (19, 21, AWAY),
        (24, 25, AWAY),
    ]
    for item in controls:
        x0, x1, colour = item[:3]
        hatch = "////" if len(item) > 3 else None
        ax.add_patch(
            Rectangle(
                (x0, rows["controls"] - 0.3),
                x1 - x0,
                0.6,
                fc="white" if hatch else colour,
                ec=colour,
                hatch=hatch,
                lw=0.8,
            )
        )
    ax.text(9.3, 3.45, "duel", ha="center", fontsize=6.5, color=AWAY)
    state = [(1, 19, HOME), (19, 28, AWAY), (31, 40, HOME)]
    for x0, x1, colour in state:
        ax.add_patch(Rectangle((x0, rows["state"] - 0.3), x1 - x0, 0.6, fc=colour, ec="none"))
    ax.add_patch(Rectangle((28, rows["stoppages"] - 0.3), 3, 0.6, fc=DEAD, ec="none"))
    ax.text(29.5, 1.45, "ball out", ha="center", fontsize=6.5, color=DEAD)
    ax.annotate(
        "throw-in (home)",
        (31, 2.32),
        (34.5, 3.2),
        fontsize=6.5,
        ha="center",
        arrowprops={"arrowstyle": "-|>", "lw": 0.6, "color": BALL},
    )
    for x0, x1, colour in [
        (0, 1, "white"),
        (1, 19, HOME),
        (19, 28, AWAY),
        (28, 31, DEAD),
        (31, 40, HOME),
    ]:
        ax.add_patch(
            Rectangle(
                (x0, rows["label"] - 0.3),
                x1 - x0,
                0.6,
                fc=colour,
                ec=GREY if colour == "white" else "none",
                lw=0.5,
            )
        )
    for x0, x1, text in [(0, 1, "X"), (1, 19, "H"), (19, 28, "A"), (28, 31, "D"), (31, 40, "H")]:
        ax.text(
            (x0 + x1) / 2,
            rows["label"],
            text,
            ha="center",
            va="center",
            fontsize=7,
            color=BALL if text == "X" else "white",
        )
    ax.set_yticks(list(rows.values()), list(rows))
    ax.set_ylim(-0.6, 3.8)
    ax.set_xlim(0, 40)
    ax.set_xlabel("seconds (synthetic)")
    ax.spines["left"].set_visible(False)
    ax.tick_params(axis="y", length=0)
    _save(fig, "timeline.svg")


def pipeline() -> None:
    """The delivered chain as boxes (section 3)."""
    fig, ax = plt.subplots(figsize=(7.0, 1.55))
    ax.set_xlim(0, 100)
    ax.set_ylim(0, 22)
    ax.axis("off")
    boxes = [
        (1, 12, "Tracking (ATD)\nball + 22 players", "#eef3fa"),
        (1, 1, "Smart Tagging\nrestarts, set pieces", "#eef3fa"),
        (24, 12, "Control\n≤ 1.5 m, ≤ 5 m/s", "#ffffff"),
        (24, 1, "Restarts\nforce possession", "#ffffff"),
        (47, 12, "Duel rule\n+ decoder", "#ffffff"),
        (47, 1, "Dead ball: tags ∪\nplayers still (DFL model)", "#ffffff"),
        (73, 6.5, "Labels\nH / A / D / X", "#f4f4f4"),
    ]
    for x, y, text, fc in boxes:
        ax.add_patch(
            FancyBboxPatch((x, y), 19, 8.5, boxstyle="round,pad=0.4", fc=fc, ec=GREY, lw=0.7)
        )
        ax.text(x + 9.5, y + 4.25, text, ha="center", va="center", fontsize=7.2)
    arrows = [
        ((20.5, 16.2), (23.5, 16.2)),
        ((20.5, 5.2), (23.5, 5.2)),
        ((43.5, 16.2), (46.5, 16.2)),
        ((43.5, 8.0), (46.5, 12.5)),
        ((66.5, 16.2), (72.5, 12.5)),
        ((66.5, 5.2), (72.5, 9.0)),
    ]
    for start, end in arrows:
        ax.add_patch(
            FancyArrowPatch(start, end, arrowstyle="-|>", mutation_scale=7, color="#555555", lw=0.6)
        )
    ax.text(
        82.5,
        3.0,
        "assembled, official validator",
        ha="center",
        va="center",
        fontsize=6.5,
        color="#555555",
    )
    _save(fig, "pipeline.svg")


def readjudication() -> None:
    """DECISIONS 44 on Metrica g1 and g2: spellF1 with and without the duel rule."""
    text = (REPO / "docs/analysis/readjudication.md").read_text(encoding="utf-8")
    pattern = re.compile(
        r"^\| (g\d) \| (limpio|degradado) \| (con|sin) duelo[^|]*\| ([\d,]+) \|", re.M
    )
    values = {(g, c, w): float(v.replace(",", ".")) for g, c, w, v in pattern.findall(text)}
    if len(values) != 8:
        raise ValueError(f"expected 8 rows in readjudication.md, found {len(values)}")
    fig, ax = plt.subplots(figsize=(3.4, 2.0))
    groups = [("g1", "limpio"), ("g2", "limpio"), ("g1", "degradado"), ("g2", "degradado")]
    for i, (g, c) in enumerate(groups):
        for j, (w, colour) in enumerate([("con", HOME), ("sin", GREY)]):
            v = values[(g, c, w)]
            ax.bar(
                i + (j - 0.5) * 0.36,
                v,
                0.34,
                color=colour,
                label=("with duel rule" if w == "con" else "without (D31)") if i == 0 else None,
            )
            ax.text(i + (j - 0.5) * 0.36, v + 0.01, f"{v:.3f}", ha="center", fontsize=5.8)
    ax.set_xticks(range(4), [f"{g}\n{'clean' if c == 'limpio' else 'degraded'}" for g, c in groups])
    ax.set_ylabel("spellF1 vs. event truth")
    ax.set_ylim(0, 0.85)
    ax.legend(frameon=False, fontsize=6.5, loc="upper center", ncol=2, bbox_to_anchor=(0.5, 1.16))
    _save(fig, "readjudication.svg")


if __name__ == "__main__":
    rules()
    timeline()
    pipeline()
    readjudication()
