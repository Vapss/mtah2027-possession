# Every command the team runs lives here. If a step is only in someone's shell history, it did
# not happen.

# uv puts the venv's executables in bin/ on Linux and macOS and in Scripts/ on Windows.
ifeq ($(OS),Windows_NT)
VENV_BIN ?= .venv/Scripts
else
VENV_BIN ?= .venv/bin
endif
PY ?= $(VENV_BIN)/python
RUFF ?= $(VENV_BIN)/ruff
PYTEST ?= $(VENV_BIN)/pytest

ARTIFACTS ?= artifacts
SUBMISSIONS ?= submissions
BASELINE ?= evaluation/results/baseline_smooth125.csv
GRAPHIFY ?= graphify
GRAPH_OUT ?= graphify-out
POSTPROCESS_INPUT ?= runs/argmin_baseline.csv
POSTPROCESS_OUTPUT ?= runs/postprocessed.csv
F0A_WORKDIR ?= runs/f0a
ARTIFACT ?= $(ARTIFACTS)/possession.csv
BACKUP_DIR ?= runs/backup
BLOCKS_INPUTS ?= evaluation/results/baseline_smooth50.csv $(SUBMISSIONS)/backup.csv $(SUBMISSIONS)/engine.csv
BLOCKS_DOC ?= docs/analysis/blocks.md

.PHONY: help install dev starter test lint fmt guard ingest demo submission validate score score-baselines graph graph-check postprocess verify-b6 f0a backup repro engine engine-sweep loo blocks ci clean

help:  ## list the targets
	@grep -hE '^[a-z-]+:.*?## ' $(MAKEFILE_LIST) | sed 's/:.*## /\t/' | expand -t22

# All three build .venv from uv.lock (#9, DECISIONS 27); the versions live in pyproject.toml and
# .python-version, nowhere else. --locked fails when uv.lock no longer matches pyproject.toml
# (--frozen would install the stale lock without a word). --inexact only adds: one target never
# uninstalls what another put there.
install:  ## the pinned runtime from uv.lock -- numpy and pandas
	uv sync --locked --no-dev --inexact

dev:  ## the pinned runtime plus pytest and ruff
	uv sync --locked --inexact

starter:  ## dev plus the notebook stack for starter/ (kloppy, matplotlib, notebook)
	uv sync --locked --inexact --group starter

test:  ## run the harness test suite
	$(PYTEST) -q

lint:  ## check formatting and lint without changing anything
	$(RUFF) check tools tests
	$(RUFF) format --check tools tests

fmt:  ## apply lint fixes and formatting
	$(RUFF) check --fix tools tests
	$(RUFF) format tools tests

guard:  ## refuse to proceed if licensed data or an oversized file is about to be committed
	$(PY) tools/guard_data.py

postprocess:  ## apply the fixed #35 cleanup to a frame,label CSV
	$(PY) tools/postprocess.py $(POSTPROCESS_INPUT) $(POSTPROCESS_OUTPUT)

backup:  ## safety-net entry (DECISIONS 25): smooth50 with ball gaps carried -> $(SUBMISSIONS)/backup.csv
	$(PY) tools/backup.py --workdir $(BACKUP_DIR) --out $(SUBMISSIONS)/backup.csv

repro:  ## #15 build the delivered file twice from scratch; compare with each other and with the delivered file
	$(PY) tools/repro.py $(if $(wildcard $(SUBMISSIONS)/engine.csv),--against $(SUBMISSIONS)/engine.csv)

engine:  ## #6 possession engine (DECISIONS 29): artifact -> assemble -> $(SUBMISSIONS)/engine.csv
	$(PY) tools/engine.py --build runs/engine --submission $(SUBMISSIONS)/engine.csv

engine-sweep:  ## #6 the pre-registered sensitivity sweep -> docs/analysis/engine-sensitivity.md
	$(PY) tools/engine_sweep.py --write docs/analysis/engine-sensitivity.md

loo:  ## #63 leave-one-match-out of the DFL dead-ball constants -> docs/analysis/loo-dead-ball.md (needs MTAH_EXTERNAL_DIR, not in CI)
	$(PY) tools/loo_dead_ball.py --json runs/loo_dead_ball/result.json --write docs/analysis/loo-dead-ball.md

blocks:  ## #36 structural report of $(BLOCKS_INPUTS) in 22 blocks -> $(BLOCKS_DOC) (run `make backup engine` first)
	$(PY) tools/blocks.py $(BLOCKS_INPUTS) --write $(BLOCKS_DOC)

verify-b6:  ## reproduce B6 public evidence and compare hashes and metrics to its manifest
	$(PY) tools/verify_b6.py

f0a:  ## run #20 F0a end to end: pinned baseline, then a job artifact when present
	$(PY) tools/f0a.py --workdir $(F0A_WORKDIR)
	$(PY) tools/f0a.py --artifact $(ARTIFACT)

ingest:  ## unpack the download zips into data/ -- idempotent, never clobbers a tracked file
	$(PY) tools/ingest.py

demo:  ## turn the shipped baseline into an artifact, so the pipeline can be exercised with no data
	mkdir -p $(ARTIFACTS)
	$(PY) tools/onehot.py $(BASELINE) -o $(ARTIFACTS)/baseline_smooth125.csv

submission:  ## assemble $(ARTIFACTS)/*.csv into the graded submission file
	$(PY) tools/assemble.py --artifacts $(ARTIFACTS) --json runs/submission_summary.json

validate:  ## run the official validator over every submission we have produced
	@set -e; found=0; for f in $(SUBMISSIONS)/*.csv; do \
	  [ -e "$$f" ] || continue; \
	  if ! out=$$($(PY) evaluation/validate_submission.py "$$f" 2>&1); then \
	    printf '%s\n' "$$out"; exit 1; \
	  fi; \
	  printf '%s: %s\n' "$$f" "$$(printf '%s' "$$out" | tail -1)"; \
	  found=$$((found + 1)); \
	done; \
	[ $$found -gt 0 ] || echo "no submission CSV in $(SUBMISSIONS)/ -- run 'make submission'"

score:  ## score $(SUBMISSIONS)/ on the public ground truth and record it in runs/ledger.jsonl
	$(PY) tools/score.py --results $(SUBMISSIONS) --bootstrap 1000 \
	  --config configs/assemble_default.json --note "make score"

score-baselines:  ## score the four shipped baselines -- the number to beat
	$(PY) tools/score.py --results evaluation/results --bootstrap 1000 --note "baselines"

graph-check:  ## build the code graph and prove it cannot be committed (CI runs this too)
	@command -v $(GRAPHIFY) >/dev/null 2>&1 || \
	  { echo "graphify is not installed: uv tool install graphifyy"; exit 1; }
	$(GRAPHIFY) extract . --code-only
	$(GRAPHIFY) cluster-only . --no-label
	$(PY) tools/check_graph.py

graph:  ## build the code graph in $(GRAPH_OUT)/ -- optional dev tool, nothing leaves the machine
	@$(MAKE) --no-print-directory graph-check PY=$(PY) GRAPHIFY=$(GRAPHIFY) GRAPH_OUT=$(GRAPH_OUT)
	$(GRAPHIFY) export html
	@echo "read $(GRAPH_OUT)/GRAPH_REPORT.md, or open $(GRAPH_OUT)/graph.html"

ci: lint test guard demo submission validate score f0a  ## exactly what GitHub Actions runs

clean:  ## remove generated outputs (never touches data/ or evaluation/results/)
	rm -rf $(ARTIFACTS) runs $(GRAPH_OUT) $(SUBMISSIONS)/*.csv $(SUBMISSIONS)/*.tmp
