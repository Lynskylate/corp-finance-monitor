#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

export PATH="$HOME/.local/bin:$HOME/.cargo/bin:$PATH"

GREEN='\033[0;32m'
RED='\033[0;31m'
NC='\033[0m'

echo "=== quick test (local-only, no network) ==="
cd "${REPO_ROOT}"

FAILED=0

QUICK_TESTS=(
    "test_cninfo_classification.py"
    "test_release_contract.py"
    "test_disk_storage_pagination.py"
    "test_scan_checkpoint.py"
    "test_stock_registry.py"
)

for t in "${QUICK_TESTS[@]}"; do
    if uv run python -m unittest "tests.${t%.py}" -v 2>&1; then
        echo -e "  ${GREEN}PASS${NC} $t"
    else
        echo -e "  ${RED}FAIL${NC} $t"
        FAILED=$((FAILED + 1))
    fi
done

echo ""
if [ "${FAILED}" -gt 0 ]; then
    echo -e "${RED}${FAILED} quick test(s) failed.${NC}"
    exit 1
else
    echo -e "${GREEN}All quick tests passed.${NC}"
    exit 0
fi
