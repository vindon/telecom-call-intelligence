# Telecom Call Intelligence — Developer Makefile
# ──────────────────────────────────────────────────────────────────────
# Usage: make <target>
# All targets assume the project virtualenv is activated (.venv/).

.PHONY: help install install-dev lock test test-fast test-cov lint format \
        type-check check run run-batches dashboard demo clean clean-outputs

PYTHON   := .venv/bin/python
PIP      := .venv/bin/pip
PYTEST   := .venv/bin/pytest
RUFF     := .venv/bin/ruff
MYPY     := .venv/bin/mypy

# ── Help ───────────────────────────────────────────────────────────────

help:
	@echo ""
	@echo "  Telecom Call Intelligence — Available make targets"
	@echo "  ─────────────────────────────────────────────────"
	@echo "  install         Install production dependencies"
	@echo "  install-dev     Install dev dependencies (pytest, ruff, mypy)"
	@echo "  lock            Regenerate requirements*.lock from requirements*.txt"
	@echo "  test            Run full unit test suite"
	@echo "  test-fast       Run tests, skip @slow and @integration marks"
	@echo "  test-cov        Run tests with coverage report"
	@echo "  lint            Run ruff linter on all source files"
	@echo "  format          Auto-format with ruff"
	@echo "  type-check      Run mypy on pipeline/"
	@echo "  check           lint + type-check + test (full pre-push gate)"
	@echo "  run             Run a 3-call smoke test"
	@echo "  run-batches     Run 5×20 = 100 calls (full production run)"
	@echo "  dashboard       Start the Streamlit analytics dashboard"
	@echo "  demo            Start the live demo app (localhost:8001)"
	@echo "  clean           Remove __pycache__, .pyc, pytest cache"
	@echo ""

# ── Install ────────────────────────────────────────────────────────────

install:
	$(PIP) install -r requirements.lock

install-dev:
	$(PIP) install -r requirements.lock -r requirements-dev.lock
	$(PYTHON) -m pre_commit install

# Regenerate the .lock files after editing a requirements*.txt spec.
# Requires `uv` (https://docs.astral.sh/uv/): brew install uv
lock:
	uv pip compile requirements.txt -o requirements.lock
	uv pip compile requirements-dev.txt -o requirements-dev.lock
	uv pip compile requirements-dashboard.txt -o requirements-dashboard.lock

# ── Tests ──────────────────────────────────────────────────────────────

test:
	$(PYTEST) tests/ -v --tb=short

test-fast:
	$(PYTEST) tests/ -v --tb=short -m "not slow and not integration"

test-cov:
	$(PYTEST) tests/ -v --tb=short \
		--cov=pipeline --cov-report=term-missing --cov-report=html --cov-fail-under=85
	@echo "\n  Coverage HTML report: htmlcov/index.html"

# ── Code quality ───────────────────────────────────────────────────────

lint:
	$(RUFF) check pipeline/ tests/ api/ run_pipeline.py run_batches.py \
		merge_outputs.py qa_audit.py dashboard/

format:
	$(RUFF) format pipeline/ tests/ api/ run_pipeline.py run_batches.py \
		merge_outputs.py qa_audit.py dashboard/

type-check:
	$(MYPY) pipeline/ --ignore-missing-imports

# Runs in pre-commit's own isolated environment, not .venv — installing
# semgrep alongside project deps downgrades opentelemetry and breaks the
# Langfuse tracing integration (pipeline/tracing.py). First run installs
# semgrep into that isolated env and is slower; later runs are cached.
security-scan:
	pre-commit run semgrep --all-files

check: lint type-check test

# ── Run pipeline ───────────────────────────────────────────────────────

run:
	$(PYTHON) run_pipeline.py --n 3

run-batches:
	$(PYTHON) run_batches.py --batches 5 --n 20

dashboard:
	.venv/bin/streamlit run dashboard/app.py

demo:            ## Live demo app — open http://localhost:8001
	@echo "  Open http://localhost:8001 in your browser"
	.venv/bin/uvicorn demo.app:app --host 0.0.0.0 --port 8001 --reload

# ── Cleanup ────────────────────────────────────────────────────────────

clean:
	find . -type d -name __pycache__ -not -path './.venv/*' -exec rm -rf {} + 2>/dev/null || true
	find . -name "*.pyc" -not -path './.venv/*' -delete 2>/dev/null || true
	rm -rf .pytest_cache htmlcov .coverage coverage.xml 2>/dev/null || true
	@echo "  Clean done."

clean-outputs:
	@echo "  Removing run outputs (keeping summary.json for dashboard cold-start)..."
	find outputs/ -name "call_results_*.csv" -delete 2>/dev/null || true
	find outputs/ -name "full_results_*.json" -delete 2>/dev/null || true
	find outputs/ -name "qa_report_*.json" -delete 2>/dev/null || true
	find outputs/ -name "insights_*.json" -delete 2>/dev/null || true
	find outputs/ -name "decisions_*.json" -delete 2>/dev/null || true
	find outputs/ -name "run_manifest_*.json" -delete 2>/dev/null || true
	find outputs/ -name "audit_log_*.json" -delete 2>/dev/null || true
	find outputs/ -name ".checkpoint_*.jsonl" -delete 2>/dev/null || true
	find outputs/ -name ".react_quota_exhausted" -delete 2>/dev/null || true
	@echo "  Outputs cleaned."
