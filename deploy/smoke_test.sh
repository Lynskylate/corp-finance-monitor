#!/usr/bin/env bash
#
# smoke_test.sh — Phase 1B minimal smoke test
#   1. /healthz responds 200
#   2. Manual sync completes without error
#
set -euo pipefail

cd "$(dirname "$0")/.."

BASE_URL="${BASE_URL:-http://127.0.0.1:8080}"
REPO_PATH="${REPO_PATH:-$(pwd)}"
CONFIG="${CONFIG:-${REPO_PATH}/config.yaml}"
CFM_BIN="${CFM_BIN:-${REPO_PATH}/.venv/bin/cfm}"
CFM_CMD="${CFM_CMD:-${CFM_BIN}}"

echo "==> Smoke 1: /healthz"
curl -sf "${BASE_URL}/healthz" \
  | python3 -c "import sys,json; d=json.load(sys.stdin); assert d.get('ok')==True, f'unexpected: {d}'; print('OK')"

echo "==> Smoke 2: manual sync"
${CFM_CMD} sync -c "${CONFIG}" --source cninfo
echo "OK"

echo "==> All smoke tests passed."
