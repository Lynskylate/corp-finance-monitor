# corp-finance-monitor — Local Review Gates
#
# Quick reference:
#   make lint            Run ruff linter
#   make format          Auto-format with ruff
#   make format-check    Check formatting without writing
#   make fix             Auto-fix lint + format (mutating — use before gate)
#   make test            Run unit tests (excludes e2e)
#   make test-scheduling Run scheduling/full_market targeted tests
#   make gate            Full pre-push gate: lint + format-check + test
#   make gate-full       Full gate including frontend (eslint + tsc + vite build)
#   make gate-scheduling Targeted gate for scheduling/full_market changes
#   make pre-commit-install  Install git pre-commit hooks
#
# Design principles:
#   - `gate` is NON-MUTATING: lint + format-check + test, never writes files
#   - `fix` / `format` are the developer's explicit mutation commands
#   - `test` mirrors CI semantics (unittest discover, same patterns)
#
# All Python commands go through `uv run`.

UV := $(HOME)/.local/bin/uv
PYTHON := $(UV) run python

# Directories
SRC := src
TESTS := tests

# Unit test modules (all test_*.py EXCEPT e2e which requires a live service)
UNIT_TEST_MODULES := $(filter-out tests.test_e2e_deployed,$(patsubst tests/test_%.py,tests.test_%,$(wildcard tests/test_*.py)))

# Scheduling/full_market targeted tests — covers the most review-intensive subsystem
SCHEDULING_TESTS := tests.test_scheduling tests.test_scan_checkpoint tests.test_cninfo_full_market tests.test_engine_concurrency tests.test_stock_registry

.PHONY: lint format format-check fix test test-scheduling test-e2e gate gate-full gate-scheduling pre-commit-install help

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-22s\033[0m %s\n", $$1, $$2}'

# ── Formatting & Linting ────────────────────────────────────────────

format: ## Auto-format Python code with ruff (mutating)
	$(UV) run ruff format $(SRC) $(TESTS)

format-check: ## Check formatting without writing (non-mutating)
	$(UV) run ruff format --check $(SRC) $(TESTS)

lint: ## Run ruff linter (non-mutating)
	$(UV) run ruff check $(SRC) $(TESTS)

fix: ## Auto-fix lint issues + format (mutating — run before gate)
	$(UV) run ruff check --fix $(SRC) $(TESTS)
	$(UV) run ruff format $(SRC) $(TESTS)

# ── Testing ──────────────────────────────────────────────────────────

test: ## Run unit tests (excludes e2e which needs live service)
	$(PYTHON) -m unittest $(UNIT_TEST_MODULES) -v

test-scheduling: ## Run targeted tests for scheduling/full_market changes
	$(PYTHON) -m unittest $(SCHEDULING_TESTS) -v

test-e2e: ## Run e2e tests against deployed stack (requires RUN_DEPLOYED_E2E=1)
	RUN_DEPLOYED_E2E=1 $(PYTHON) -m unittest tests.test_e2e_deployed -v

# ── Review Gates (all non-mutating) ─────────────────────────────────

gate: ## Full pre-push gate: lint + format-check + test
	@echo "=== Running full review gate ==="
	@echo "--- lint ---"
	@$(UV) run ruff check $(SRC) $(TESTS) || (echo "❌ lint failed" && exit 1)
	@echo "--- format check ---"
	@$(UV) run ruff format --check $(SRC) $(TESTS) || (echo "❌ format check failed (run 'make format' to fix)" && exit 1)
	@echo "--- tests ---"
	@$(PYTHON) -m unittest $(UNIT_TEST_MODULES) -v || (echo "❌ tests failed" && exit 1)
	@echo "✅ gate passed — safe to push"

gate-full: ## Full gate including frontend: lint + format-check + test + eslint + frontend build
	@echo "=== Running full review gate (Python + Frontend) ==="
	@echo "--- Python lint ---"
	@$(UV) run ruff check $(SRC) $(TESTS) || (echo "❌ lint failed" && exit 1)
	@echo "--- Python format check ---"
	@$(UV) run ruff format --check $(SRC) $(TESTS) || (echo "❌ format check failed (run 'make format' to fix)" && exit 1)
	@echo "--- Python tests ---"
	@$(PYTHON) -m unittest $(UNIT_TEST_MODULES) -v || (echo "❌ tests failed" && exit 1)
	@echo "--- Frontend lint (eslint) ---"
	@cd frontend && npm run lint || (echo "❌ eslint failed" && exit 1)
	@echo "--- Frontend build (tsc + vite) ---"
	@cd frontend && npm run build || (echo "❌ frontend build failed" && exit 1)
	@echo "✅ full gate passed (Python + Frontend) — ready for review"

gate-scheduling: ## Targeted gate for scheduling/full_market changes
	@echo "=== Running scheduling/full_market review gate ==="
	@echo "--- lint (core files) ---"
	@$(UV) run ruff check \
		$(SRC)/corp_finance_monitor/sources/cninfo.py \
		$(SRC)/corp_finance_monitor/core/engine.py \
		$(SRC)/corp_finance_monitor/core/scheduler.py \
		|| (echo "❌ lint failed" && exit 1)
	@echo "--- format check (core files) ---"
	@$(UV) run ruff format --check \
		$(SRC)/corp_finance_monitor/sources/cninfo.py \
		$(SRC)/corp_finance_monitor/core/engine.py \
		$(SRC)/corp_finance_monitor/core/scheduler.py \
		|| (echo "❌ format check failed" && exit 1)
	@echo "--- targeted tests ---"
	@$(PYTHON) -m unittest $(SCHEDULING_TESTS) -v || (echo "❌ tests failed" && exit 1)
	@echo "✅ scheduling gate passed"

# ── Setup ────────────────────────────────────────────────────────────

pre-commit-install: ## Install git pre-commit hooks
	$(UV) run pip install pre-commit
	$(UV) run pre-commit install
