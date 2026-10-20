# Decisions

One entry per rule, threshold or trade-off that someone would otherwise have to reverse-engineer
from the code. Newest last. Keep entries short: what was decided, why, and what it costs.

---

## 1. A single writer for the graded file

**Decided.** `tools/assemble.py` is the only code that writes `submissions/submission.csv`. Jobs
emit `frame,p_home,p_away,p_dead,confidence` into `artifacts/`.

**Why.** The submission format is strict -- exactly 199,319 rows, frames in order, no blank cells,
labels in `H A D X` -- and a file that fails those checks scores nothing at all. With several
people producing candidate files, format bugs multiply and each one costs a whole entry. One writer
means one place to be right, and it lets a job be developed against its own signal without touching
the deliverable.

**Cost.** Every job pays the adapter cost of expressing itself as probabilities, including jobs that
only ever produce hard labels (`tools/onehot.py` handles that case).

---

## 2. Probabilities plus a confidence, not hard labels

**Decided.** The artifact carries three probabilities and a `confidence`, and the assembler combines
artifacts by weighting each one with its confidence (explicit `--weight` overrides).

**Why.** Two signals disagree about the same frame sooner or later -- dead-ball detection versus the
possession engine is exactly that case. Hard labels force a merge rule chosen by whoever writes the
merger first; probabilities let the disagreement be visible and weighted. `confidence = 0` gives a
job a clean way to abstain on frames it knows nothing about, and it maps onto the submission's own
`X` label.

**Cost.** The weighted mean is a simplicity choice, not a calibrated ensemble. If two artifacts are
strongly correlated, confidence-weighting double-counts them.

---

## 3. Bootstrap on by default

**Decided.** `make score` always runs `run_evaluation.py --bootstrap 1000`, and the ledger records
the draw count.

**Why.** The public ground truth covers 5 minutes: 7,500 graded frames, 17 possessions,
21 segments. The effective sample size is the segment count, not the frame count, so a `spellF1`
delta of a few hundredths carries no information. Measured on the shipped baseline, 1000 draws give
a 5-95 percentile interval of **0.2667 .. 0.5939** for `spellF1` -- the scorer prints "gaps below
~0.33 are within noise". On the full match the band is far tighter (~0.04, per EVALUATION.md); the
public slice is a sanity check and the two must never be quoted interchangeably.

**Cost.** Slower scoring, and a band wide enough that most "improvements" visible locally are noise.
That is the honest answer rather than a defect: it also means the public slice cannot rank two
plausible methods, so the ledger should be read for direction, not for decimals.

---

## 4. Freeze the organisers' code and lint only ours

**Decided.** `evaluation/`, `starter/` and `games.py` are read-only and excluded from ruff.

**Why.** `evaluation/run_evaluation.py` is the script that produces the official result; a local
edit makes our numbers incomparable to the board. Reformatting them would also turn every upstream
merge into a conflict, and the repository must keep tracking `upstream`.

**Cost.** Some upstream rough edges stay rough. If one is real, it belongs in an upstream issue.

---

## 5. `X` is not used as a safety net yet

**Decided.** The assembler's `--abstain-below` defaults to `0.0` and `--x-outside-halves` is off.

**Why.** `spellF1` fills an abstention with the previous label in the same half, so an `X` costs
nothing mid-possession and a lot across a hand-over, while `macroF1` charges it as a miss. Both
behaviours are measurable but neither is measured yet, and a default that silently abstains would
change every comparison in the ledger.

**Cost.** The pipeline does not exploit the free option. Whoever measures it should record the
before/after here and then change the default deliberately.

---

## 6. Data guard in pre-commit, not only in `.gitignore`

**Decided.** `tools/guard_data.py` blocks `data/`, archives, video, frame dumps and files over
5 MB, and the check runs in pre-commit and in CI.

**Why.** The downloaded bundle arrives as archives next to the repository, untracked and one
`git add -A` from being published to a public repository that the organisers will clone. `.gitignore`
covers the unpacked directory and not the archives, and it says nothing about derived frame-level
exports.

**Cost.** Legitimate large files need an explicit decision. None are expected here.
