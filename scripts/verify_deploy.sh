#!/usr/bin/env bash
#
# verify_deploy.sh — Post-deploy smoke check (Phase 2).
#
# Companion to deploy/deploy.sh and docs/DEPLOY_VERIFICATION.md.
# Exits 0 on success, non-zero on any failure.
#
# Each step prints a one-line marker ("OK" / "FAIL: <step>") so the
# output is greppable in CI logs.
#
# Usage:
#   ./scripts/verify_deploy.sh
#   BASE_URL=http://host:8190 ./scripts/verify_deploy.sh
#
set -uo pipefail

BASE_URL="${BASE_URL:-http://127.0.0.1:8190}"
REPO_PATH="${REPO_PATH:-/home/lynskylate/corp-finance-monitor}"
CFM_BIN="${CFM_BIN:-${REPO_PATH}/.venv/bin/cfm}"
CONFIG_PATH="${CONFIG_PATH:-${REPO_PATH}/config.yaml}"
CFM_USER="${CFM_USER:-cfm}"
DATA_DIR="${DATA_DIR:-${REPO_PATH}/data}"
SERVICE_NAME="${SERVICE_NAME:-cfm-api}"
TIMER_NAME="${TIMER_NAME:-cfm-sync}"

failed=0
step_count=0

run() {
  local name="$1"; shift
  step_count=$((step_count + 1))
  echo "==> [${step_count}] ${name}"
  if "$@"; then
    echo "    OK"
  else
    echo "    FAIL: ${name}"
    failed=1
  fi
}

# ── Step 1: /healthz ──────────────────────────────────────────────────────
check_healthz() {
  local body
  body="$(curl -sf --max-time 5 "${BASE_URL}/healthz" 2>/dev/null)" || return 1
  [[ "$(echo "$body" | python3 -c 'import sys,json; print(json.load(sys.stdin).get("ok"))' 2>/dev/null)" == "True" ]]
}
run "/healthz returns {\"ok\": true}" check_healthz

# ── Step 2: empty filings query ──────────────────────────────────────────
check_filings_empty() {
  local body
  body="$(curl -sf --max-time 5 "${BASE_URL}/api/filings?source=__nonexistent__" 2>/dev/null)" || return 1
  echo "$body" | python3 -c 'import sys,json; d=json.load(sys.stdin); assert d.get("items")==[]' 2>/dev/null
}
run "/api/filings?source=__nonexistent__ returns {items: []}" check_filings_empty

# ── Step 3: create subscription ──────────────────────────────────────────
check_sub_create() {
  local body
  body="$(curl -sf --max-time 5 -X POST "${BASE_URL}/api/subscriptions" \
    -H 'Content-Type: application/json' \
    -d '{"name":"verify-deploy-test","source":"cninfo","stock_code":"000725","kind":"annual","target":"https://example.com/wh"}' \
    2>/dev/null)" || return 1
  echo "$body" | python3 -c 'import sys,json; d=json.load(sys.stdin); s=d.get("subscription",{}); assert isinstance(s.get("id"), int)' 2>/dev/null
}
run "POST /api/subscriptions returns 201 with numeric id" check_sub_create

# ── Step 4: cfm-api.service active ───────────────────────────────────────
check_api_active() {
  systemctl is-active "${SERVICE_NAME}.service" 2>/dev/null | grep -qx active
}
run "${SERVICE_NAME}.service is active" check_api_active

# ── Step 5: cfm-sync.timer active ────────────────────────────────────────
check_timer_active() {
  systemctl is-active "${TIMER_NAME}.timer" 2>/dev/null | grep -qx active
}
run "${TIMER_NAME}.timer is active" check_timer_active

# ── Step 6: cfm binary lists 7 subcommands ───────────────────────────────
check_cfm_help() {
  [[ -x "${CFM_BIN}" ]] || return 1
  local out
  out="$("${CFM_BIN}" --help 2>&1)" || return 1
  for sub in run sync list runs subscribe serve init; do
    echo "$out" | grep -qE "^\s+${sub}\s+" || return 1
  done
}
run "${CFM_BIN} --help lists all 7 subcommands" check_cfm_help

# ── Step 7: data dir ownership ───────────────────────────────────────────
check_data_owner() {
  [[ -d "${DATA_DIR}" ]] || return 1
  local owner
  owner="$(stat -c '%U:%G' "${DATA_DIR}" 2>/dev/null)" || return 1
  [[ "$owner" == "${CFM_USER}:${CFM_USER}" ]]
}
run "data dir is owned by ${CFM_USER}:${CFM_USER}" check_data_owner

# ── Step 8: state databases present (after config load) ─────────────────
check_state_dbs() {
  local state_dir="${DATA_DIR}/.cfm_state"
  [[ -d "$state_dir" ]] || return 1
  # Either state.db (engine) or meta.db (storage) should be initialized
  [[ -f "${state_dir}/state.db" ]] || [[ -f "${state_dir}/meta.db" ]]
}
run "data/.cfm_state has state.db or meta.db" check_state_dbs

# ── Summary ──────────────────────────────────────────────────────────────
echo
if [[ $failed -eq 0 ]]; then
  echo "All ${step_count} smoke checks passed."
  exit 0
else
  echo "Smoke checks FAILED. See docs/DEPLOY_VERIFICATION.md for manual deep checks."
  exit 1
fi
