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
echo "  targeted review gate (scheduling + full_market)"
echo "============================================"
echo ""

cd "${REPO_ROOT}"

# --- Python: ruff check ---
echo "--- Python: ruff check ---"
if uv run ruff check --no-fix 2>&1; then
    echo -e "  ${GREEN}PASS${NC} ruff lint"
    pas
else
    fail "ruff lint"
fi
echo ""

# --- Python: ruff format check ---
echo "--- Python: ruff format check ---"
if uv run ruff format --check 2>&1; then
    echo -e "  ${GREEN}PASS${NC} ruff format"
    pas
else
    fail "ruff format"
fi
echo ""

# --- Targeted tests: scheduling + full_market + concurrency + checkpoint ---
echo "--- Python: scheduling / full_market / concurrency tests ---"
TARGETED_TESTS=(
    "test_scheduling.py"
    "test_cninfo_full_market.py"
    "test_hkex_full_market.py"
    "test_stock_registry.py"
    "test_hkex_registry.py"
    "test_scan_checkpoint.py"
    "test_engine_concurrency.py"
)

for t in "${TARGETED_TESTS[@]}"; do
    echo "  running $t ..."
    if uv run python -m unittest "tests.${t%.py}" -v 2>&1; then
        echo -e "    ${GREEN}PASS${NC} $t"
        pas
    else
        fail "$t"
    fi
done
echo ""

# --- Frontend: build check (tsc only, no vite bundle) ---
echo "--- Frontend: tsc typecheck ---"
pushd frontend > /dev/null
if npx tsc --noEmit 2>&1; then
    echo -e "  ${GREEN}PASS${NC} tsc"
    pas
else
    fail "tsc typecheck"
fi
popd > /dev/null
echo ""

# --- Summary ---
echo "============================================"
echo -n "Result: ${GREEN}${PASSED} passed${NC}"
if [ "${FAILED}" -gt 0 ]; then
    echo -e ", ${RED}${FAILED} failed${NC}"
    echo ""
    echo "Review the failures before requesting review."
    exit 1
else
    echo ""
    echo ""
    echo -e "  ${GREEN}All targeted gates passed.${NC}"
    exit 0
fi
