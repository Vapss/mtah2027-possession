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

---

## 7. Ingest decides by content hash, not by filename or flags

**Decided.** `tools/ingest.py` treats a destination whose bytes already match the archive as
*present*, never rewrites it -- even under `--force` -- and aborts the whole run before writing
anything if a destination is tracked by git and differs.

**Why.** The bundle ships a `README.md` that is byte-identical to the committed `data/README.md`, so
a name-based rule would either skip a real asset or overwrite a tracked file. Re-running ingest on a
good tree has to be a no-op that leaves mtimes alone, otherwise "did the data change?" becomes
unanswerable. The preflight exists because a half-unpacked tree looks like a successful run.

**Cost.** Proving "present" means hashing both sides: cheap for the 8 small assets, slower for the
196 MB tracking file. Accepted, because a wrong overwrite costs more than a few seconds of I/O.

---

## 8. Smart Tagging intervals are half-open, unlike the reference loader

**Decided.** `tools/smart_tagging.py` maps `<start>`/`<end>` to `round(seconds * 25)` and treats
`end_frame` as exclusive: `[start_frame, end_frame)`.

**Why.** Every other interval in this repository is half-open, and a mask that disagrees by one frame
per instance is the kind of error that survives review. `starter/load_smart_tagging.py` is inclusive
and is not imported: it is read-only reference code, it prints from a time-base check, and importing
it would make our pipeline depend on a file the organisers may change. The one-frame difference is
documented in the module docstring instead.

**Cost.** Our counts differ from the reference by at most 59 frames on `SET PIECES`. Verified on the
delivered file: union of the 59 intervals is 43,987 frames (22.1% of the match); `GOALS` covers
16,503 frames (8.3%) because the annotator tags the whole goal sequence, not the restart.

---

## 9. Our contract is deliberately stricter than the official validator

**Decided.** `tools/contract.py` rejects a submission with an extra column and one with a leading
index column. `evaluation/validate_submission.py` -- the file that decides the competition -- accepts
both.

**Why.** Measured, not assumed. A probe compared the two on the same files, and they agree on the
five cases that actually happen (a trailing blank line, an Excel BOM, CRLF endings, quoted labels, a
header written as `frame, label`): all five pass both. They disagree on exactly two, and in the safe
direction -- we are the strict one. That order matters: a harness stricter than the organiser blocks
a file that might have scored, which is annoying and visible. The opposite order silently ships a
file that scores nothing.

**Cost.** `make submission && make validate` can block a file the official validator would have
accepted. If that ever happens to a real submission, the fix is to relax `SUBMISSION_COLUMNS` in
`tools/contract.py` and record it here, not to hand-edit the CSV.

---

## 10. CI does not run the tests that need the match data

**Decided.** The bundle-dependent tests skip themselves in CI: 10 of 60 on a clean clone, 50 pass.
The authoritative gate is `make ci` **run locally with the bundle unpacked**; GitHub Actions proves
the harness works on a machine that has no data.

**Why.** The data is gated and licensed for the competition only -- it cannot be in the repository or
in a public CI cache, and putting it there is the one rule that ends a submission. The ten skipped
tests are precisely the ones carrying this repository's real claims: the byte-identical regeneration
of the four baselines, the 638 Smart Tagging instances, and the 43,987 frames of `SET PIECES`. Losing
them in CI is the price of not shipping the data.

**Cost.** A green check in GitHub no longer means "the numbers still hold", and someone will read it
that way. Two mitigations are available and neither is implemented: a small synthetic bundle fixture
so ingest and Smart Tagging parsing run on every push (the 638-instance assertions would still need
real data), or a documented rule that the PR checklist item is a pasted local `make ci`. Until one
exists, treat CI as a syntax gate and the local run as the evidence.

---

## 11. The pandas version is part of the contract until there is a lock

**Decided.** `requirements.txt` stays as the organisers wrote it -- `numpy`, `pandas`, unpinned -- and
we accept the risk until `uv lock` lands. The risk is recorded here rather than silently tolerated.

**Why.** `tests/test_regression_baseline.py` proves reproducibility by regenerating the four shipped
baselines and demanding `git diff` come back empty. That is a byte-level assertion on pandas' CSV
writer. It passes on pandas 3.0.6 (the version in the venv this repository was verified against), and
it can fail on another version for reasons that have nothing to do with our code.

**Cost.** If it fails, the message says "starter/baseline.py no longer reproduces the committed
baseline CSVs", which points at the organisers' script and not at the dependency -- a misleading
error, which is worse than a plain failure. Pinning the interpreter and the two libraries closes it;
that is task E1, and it is a deliverable requirement anyway ("pinned dependencies").
