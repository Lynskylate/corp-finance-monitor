#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

export PATH="$HOME/.local/bin:$HOME/.cargo/bin:$PATH"

GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m'

FAILED=0
PASSED=0

pas()  { PASSED=$((PASSED + 1)); }
fail() { FAILED=$((FAILED + 1)); echo -e "${RED}  FAIL${NC} $*"; }

echo "============================================"
echo "  corp-finance-monitor review gate"
echo "============================================"
echo ""

cd "${REPO_ROOT}"

# --- Python: ruff lint ---
echo "--- Python: ruff check ---"
if uv run ruff check --no-fix 2>&1; then
    echo -e "  ${GREEN}PASS${NC} ruff lint"
    pas
else
    fail "ruff lint (review with: uv run ruff check --diff)"
fi
echo ""

# --- Python: ruff format check ---
echo "--- Python: ruff format check ---"
if uv run ruff format --check 2>&1; then
    echo -e "  ${GREEN}PASS${NC} ruff format"
    pas
else
    fail "ruff format (fix with: uv run ruff format)"
fi
echo ""

# --- Python: tests ---
echo "--- Python: unit tests ---"
if uv run python -m unittest discover -s tests -p "test_*.py" -v 2>&1; then
    echo -e "  ${GREEN}PASS${NC} unit tests"
    pas
else
    fail "Python unit tests"
fi
echo ""

# --- Frontend: eslint ---
echo "--- Frontend: eslint ---"
pushd frontend > /dev/null
if npm run lint 2>&1; then
    echo -e "  ${GREEN}PASS${NC} eslint"
    pas
else
    fail "eslint"
fi
echo ""

# --- Frontend: build (tsc + vite) ---
echo "--- Frontend: build (tsc + vite) ---"
if npm run build 2>&1; then
    echo -e "  ${GREEN}PASS${NC} frontend build"
    pas
else
    fail "frontend build (tsc + vite)"
fi
popd > /dev/null
echo ""

# --- Summary ---
echo "============================================"
echo -n "Result: ${GREEN}${PASSED} passed${NC}"
if [ "${FAILED}" -gt 0 ]; then
    echo -e ", ${RED}${FAILED} failed${NC}"
    echo ""
    echo "Review the failures above before requesting code review."
    echo "Quick fixes:"
    echo "  uv run ruff check --fix    # auto-fix lint issues"
    echo "  uv run ruff format         # auto-format Python files"
    exit 1
else
    echo ""
    echo ""
    echo -e "  ${GREEN}All gates passed — ready for review.${NC}"
    exit 0
fi
