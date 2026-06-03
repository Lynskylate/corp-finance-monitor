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

echo "=== pre-commit gate ==="

cd "${REPO_ROOT}"

STAGED=$(git diff --cached --name-only --diff-filter=ACM 2>/dev/null || true)
if [ -z "${STAGED}" ]; then
    echo "  No staged files, nothing to check."
    exit 0
fi

PY_FILES=$(echo "${STAGED}" | grep '\.py$' || true)
FE_FILES=$(echo "${STAGED}" | grep '^frontend/' || true)
TS_FILES=$(echo "${STAGED}" | grep '\.\(ts\|tsx\)$' || true)

# --- Python: ruff lint on staged files ---
if [ -n "${PY_FILES}" ]; then
    echo ""
    echo "--- Python: ruff check ---"
    if echo "${PY_FILES}" | tr '\n' '\0' | xargs -0 uv run ruff check --no-fix 2>&1; then
        echo -e "  ${GREEN}PASS${NC} ruff"
        pas
    else
        fail "ruff found issues in staged Python files. Fix them before committing."
    fi
fi

# --- Frontend: eslint on staged files ---
if [ -n "${FE_FILES}" ]; then
    echo ""
    echo "--- Frontend: eslint (staged) ---"
    ESLINT_FILES=$(echo "${FE_FILES}" | grep '\.\(ts\|tsx\|js\|jsx\)$' || true)
    if [ -n "${ESLINT_FILES}" ]; then
        pushd frontend > /dev/null
        if echo "${ESLINT_FILES}" | sed 's|^frontend/||' | tr '\n' '\0' | xargs -0 npx eslint --quiet 2>&1; then
            echo -e "  ${GREEN}PASS${NC} eslint"
            pas
        else
            fail "eslint found issues in staged frontend files."
        fi
        popd > /dev/null
    fi
fi

# --- Frontend: TypeScript typecheck ---
if [ -n "${TS_FILES}" ]; then
    echo ""
    echo "--- Frontend: tsc typecheck ---"
    pushd frontend > /dev/null
    if npx tsc --noEmit 2>&1; then
        echo -e "  ${GREEN}PASS${NC} tsc"
        pas
    else
        fail "TypeScript typecheck failed."
    fi
    popd > /dev/null
fi

echo ""
echo -en "pre-commit: ${GREEN}${PASSED} passed${NC}"
if [ "${FAILED}" -gt 0 ]; then
    echo -e ", ${RED}${FAILED} failed${NC}"
    echo ""
    echo "Fix the failures above and try committing again."
    exit 1
else
    echo ""
    exit 0
fi
