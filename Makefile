# Every command the team runs lives here. If a step is only in someone's shell history, it did
# not happen.

PY ?= .venv/bin/python
RUFF ?= .venv/bin/ruff
PYTEST ?= .venv/bin/pytest

ARTIFACTS ?= artifacts
SUBMISSIONS ?= submissions
BASELINE ?= evaluation/results/baseline_smooth125.csv
GRAPHIFY ?= graphify
GRAPH_OUT ?= graphify-out
POSTPROCESS_INPUT ?= runs/argmin_baseline.csv
POSTPROCESS_OUTPUT ?= runs/postprocessed.csv

.PHONY: help venv install dev test lint fmt guard ingest demo submission validate score score-baselines graph graph-check postprocess verify-b6 ci clean

help:  ## list the targets
	@grep -hE '^[a-z-]+:.*?## ' $(MAKEFILE_LIST) | sed 's/:.*## /\t/' | expand -t22

venv:  ## create the pinned environment (Python 3.12, not the system interpreter)
	uv venv --python 3.12 .venv

install: venv  ## runtime dependencies only -- numpy and pandas
	uv pip install --python $(PY) -r requirements.txt

dev: install  ## runtime plus pytest and ruff
	uv pip install --python $(PY) -r requirements-dev.txt

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

verify-b6:  ## reproduce B6 public evidence and compare hashes and metrics to its manifest
	$(PY) tools/verify_b6.py

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

ci: lint test guard demo submission validate score  ## exactly what GitHub Actions runs

clean:  ## remove generated outputs (never touches data/ or evaluation/results/)
	rm -rf $(ARTIFACTS) runs $(GRAPH_OUT) $(SUBMISSIONS)/*.csv $(SUBMISSIONS)/*.tmp
