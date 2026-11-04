# Working agreement

This file is the contract for anyone writing code in this repository — human or model. Read it
before your first commit. Each rule says how it is enforced; if a rule matters and nothing enforces
it, add the check, not another paragraph.

`CLAUDE.md` and `.github/copilot-instructions.md` are symlinks to this file on purpose: one source,
no drift.

---

## The task, in one paragraph

One LaLiga match, 199,319 video frames at 25 fps. For every frame, output one label: `H` home in
possession, `A` away in possession, `D` dead ball, `X` no answer. One CSV, `frame,label`, every frame
index present in order. Ranked on **`spellF1`** — whole possessions matched by temporal IoU — not on
per-frame accuracy. `macroF1` is reported and only breaks ties.

**The number to beat is `spellF1` 0.2433 on the full private match.** The scores in the README are a
5-minute public slice (7,500 graded frames, 17 possessions); they are not comparable to that number
and must never be quoted as if they were.

---

## Non-negotiables

1. **Optimise `spellF1`, report `macroF1` second.** A change that raises `macroF1` and lowers
   `spellF1` is a regression. Enforced by review and by `make score`, which prints both.
2. **`tools/assemble.py` is the only code that writes the submission file.** Jobs emit the artifact
   table; the assembler turns artifacts into `frame,label`. Enforced by
   `tests/test_assemble.py::test_assembled_submission_passes_the_official_validator`.
3. **Every artifact satisfies the contract before it is combined.** Enforced by `tools/contract.py`,
   called on load and again before writing.
4. **The match data never enters git.** No `data/`, no `*.zip`, no `*.mp4`, no file over 5 MB. The
   submission repository is public and the data is licensed for this competition only. Enforced by
   `make guard` and the `data-guard` pre-commit hook.
5. **Labels come from code, never from a person.** No hand-editing a label file, no hand-correcting a
   model frame by frame, no using the private ground truth. That is a disqualification, not a style
   issue. No data produced by a person about this match either, not even to train or validate
   (the organisers' clarification, rule 9). Hand-annotated *external* datasets are allowed when
   their licence or their publisher's stated terms allow it: DFL/IDSSE is CC-BY 4.0, and Metrica's
   open sample data has no licence file but its publisher (the organiser) offers it for use with an
   acknowledgement of the source, which the technical document gives.
6. **The repository must regenerate the submitted file.** Same data plus this code plus the
   documented command = byte-identical CSV. Anything stochastic in the labelling path breaks this,
   which is why an LLM may write code and documentation but does not label frames through a sampling
   API.
7. **Do not edit `evaluation/`, `starter/` or `games.py`.** They are the organisers' reference and
   read-only, and they are excluded from lint for the same reason. If something there is genuinely
   wrong, open an issue upstream.
8. **Determinism.** Fixed seeds, no network at run time, no timestamps or absolute paths inside
   outputs.
9. **The public ground truth and the video are for checks, never for choices.** The organisers'
   clarification takes precedence over every other document, and the team applies its strictest
   reading (DECISIONS 44). No constant, rule or decision to include a piece of the delivered chain
   rests on the public 5-minute ground truth, on an instrument scored against it (the slice, the
   bench, the headroom audit) or on the video; anything that needs tuning is tuned on external data.
   Scoring a chain that is already decided is an automatic check and is fine; choosing between
   variants with it is not. No output is ever checked against the video. Enforced by review and by
   the pre-registration in `docs/DECISIONS.md`: the rule that decides is written before measuring.
10. **Nothing derived from the match data reaches an AI service except aggregates.** No tracking
    rows, frame-level labels, images or video in prompts, tool output or agent briefs: jobs print
    counts, shares and scores only. The data itself never leaves the machine.

---

## The artifact contract

Every job — dead-ball detection, the possession engine, ball recovery — emits the same table and
nothing else:

```
frame,p_home,p_away,p_dead,confidence
0,0.05,0.12,0.83,0.91
1,0.04,0.11,0.85,0.92
...
```

- `frame`: 0..199318, one row each, in order. Length comes from `games.source_frames()`.
- `p_home`, `p_away`, `p_dead`: probabilities in `[0, 1]` summing to 1 per row.
- `confidence`: how much this job wants its opinion to count, `[0, 1]`. `0` means "I abstain on this
  frame" and the assembler gives it no weight. If every artifact abstains on a frame, the assembler
  emits `X` for it; a label is never chosen by the order of the probability columns.
- A job that only produces hard labels uses `tools/onehot.py` to emit its table.

Name the file after the job: `artifacts/dead_ball.csv`, `artifacts/possession.csv`. The assembler
reads every `*.csv` in `artifacts/` and combines them by confidence, or by an explicit
`--weight name=value`.

---

## Commands

```bash
make dev           # environment from uv.lock (versions in pyproject.toml), plus pytest and ruff
make test          # the harness suite
make lint          # ruff check + format --check
make demo          # encode a shipped baseline as an artifact (no match data needed)
make submission    # artifacts/*.csv -> submissions/submission.csv
make validate      # the organisers' own validator over submissions/
make score         # score submissions/ with --bootstrap 1000, append to runs/ledger.jsonl
make f0a           # #20 F0a: pinned baseline chain + the #34 artifact when present
make guard         # licensed data / oversized file check
make ci            # everything above, in order
make graph-check   # build the code graph and prove it cannot be committed (CI runs this too)
make graph         # the same, plus the HTML view, in graphify-out/ (optional, dev only)
```

Never run the scorer by hand with different flags. `--bootstrap 1000` is the default here because
the public ground truth cannot rank two plausible methods on its own.

---

## The code graph (optional, dev only)

`make graph` builds a navigable graph of this repository with [graphify](https://graphify.com):
`graphify-out/graph.json`, `GRAPH_REPORT.md` (god nodes, communities) and `graph.html`. It is a
**reading aid, not part of the pipeline**:

- It never runs at submission time and is not a project dependency. Install it out of tree with
  `uv tool install graphifyy`; `make dev` does not install it and CI does not need it.
- Code is parsed locally with tree-sitter. Nothing is uploaded. The semantic pass over docs and
  PDFs needs an LLM key and is deliberately **not** used here: the graph is built `--code-only`,
  so every edge is grounded in the AST, with no model in the loop.
- `graphify-out/` is gitignored. Do not commit the graph: it goes stale on the next commit and
  reviewing a JSON snapshot hides the diff that matters.
- CI runs `make graph-check`, which builds the graph and fails if the output is no longer ignored
  or if `GRAPH_REPORT.md` names a different commit than `HEAD`. That is what keeps this section a
  rule instead of a paragraph: drop the `.gitignore` line and the build goes red.
- Treat it as a map, not as a source of truth. The graph is a snapshot of the commit it was built
  from -- `GRAPH_REPORT.md` names that commit, and `graphify update .` re-extracts after changes.
  A "god node" is an invitation to read `file:line`, never a reason to change code.

## Definition of done for a pull request

- [ ] `make lint` clean, `make test` green.
- [ ] The job emits a contract-valid artifact; `make submission` then `make validate` both pass.
- [ ] Numbers in the description come from `make score`, not from memory: `spellF1`, `macroF1`,
      possession count and fragmentation, before and after.
- [ ] `runs/ledger.jsonl` has the run.
- [ ] No data, no notebook output cells containing match video, no derived frame-level tracking
      export. Those are redistribution.
- [ ] `docs/DECISIONS.md` gets an entry if the PR chooses a rule, a threshold or a trade-off that
      someone else would otherwise have to guess.

---

## Evaluation protocol

The public ground truth is 7,500 graded frames: 17 possessions, 21 segments. On the shipped baseline,
1,000 bootstrap draws give a 5-95 percentile interval of **0.2667 .. 0.5939** for `spellF1` — the
scorer prints "gaps below ~0.33 are within noise". The ~0.04 band in `EVALUATION.md` is calibrated
over the full match; the two are not interchangeable.

- Report `spellF1` first, `macroF1` second, then possession count against the true 17 and the
  fragmentation ratio.
- Treat a local `spellF1` delta under ~0.3 as undecided, not as a win. Use it for direction only.
- One number per run, in the ledger. Never tune against a single window and call it generalisation.
- `X` is a legal answer: `spellF1` fills an abstention with your previous label in the same half, so
  abstaining is free inside a possession and expensive across a hand-over. Do not use it as a safety
  net without measuring it.

---

## Branches and ownership

- `main` tracks `upstream` and is never committed to; it must stay fast-forwardable.
- `dev` is the integration branch. Everyone branches `feat/<job>` from `dev` and opens a PR into
  `dev`.
- `feat/dead-ball`, `feat/possession-engine`, `feat/ball-recovery` own the three signals.
  `docs/technical-report` runs from day one — it is a graded deliverable, not a write-up after the
  fact.
- Do not force-push `dev`. Do not rewrite anyone else's branch.

---

## Style

- Python 3.9+ compatible syntax, type hints on public functions, `from __future__ import
  annotations`.
- numpy and pandas only for anything the pipeline needs at submission time. Extra libraries are fine
  for exploration but must not enter the path that regenerates the file — the organisers have to be
  able to run it.
- Comments explain *why*, and they are the place to state the competition rule that motivated a
  threshold. A comment that repeats the code has no value.
- Prefer a small module with a test over a notebook. Notebooks are for looking at data; anything that
  produces an artifact or a ledger number is a module.

---

## Where things live

```
tools/atd.py          the raw tracking reader: frames(), players(frame), ball() + the export's invariants
tools/contract.py     the two formats and the checks for them
tools/assemble.py     artifacts -> submission. The only writer.
tools/onehot.py       frame,label -> artifact, for existing label files
tools/score.py        scorer wrapper: bootstrap on, ledger appended
tools/guard_data.py   licensed-data and oversized-file guard (stdlib only)
tests/                contract, round-trip, known-score, regression, guard
configs/              assembler config: weights, abstain threshold
runs/                 scoreboard, ledger, run summaries (gitignored)
graphify-out/         code graph from `make graph` (optional, gitignored -- see above)
artifacts/            job outputs, one CSV per job (gitignored)
submissions/          the graded file, generated by `make submission` (gitignored; commit the real
                      entry explicitly at deadline with `git add -f`)
docs/DECISIONS.md     rules and trade-offs that are not obvious from the code
docs/analysis/        measurements behind a decision (generated by tools/characterize_d.py)
```
