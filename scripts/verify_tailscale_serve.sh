#!/usr/bin/env bash
#
# verify_tailscale_serve.sh — smoke checks for the docker + tailscale path.
#
# Usage:
#   ./scripts/verify_tailscale_serve.sh
#   BASE_URL=https://host.tailnet.ts.net ./scripts/verify_tailscale_serve.sh
#
set -uo pipefail

TAILSCALE_BIN="${TAILSCALE_BIN:-tailscale}"
LOCAL_PORT="${LOCAL_PORT:-8080}"
LOCAL_URL="${LOCAL_URL:-http://127.0.0.1:${LOCAL_PORT}}"

command -v "${TAILSCALE_BIN}" >/dev/null 2>&1 || {
  echo "tailscale CLI not found in PATH" >&2
  exit 1
}

command -v python3 >/dev/null 2>&1 || {
  echo "python3 is required to parse JSON" >&2
  exit 1
}

status_json="$("${TAILSCALE_BIN}" status --json)"
dns_name="$(printf '%s' "${status_json}" | python3 -c 'import json,sys; print(json.load(sys.stdin)["Self"]["DNSName"].rstrip("."))')"
BASE_URL="${BASE_URL:-https://${dns_name}}"

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

check_local_healthz() {
  local body
  body="$(curl -sf --max-time 5 "${LOCAL_URL}/healthz" 2>/dev/null)" || return 1
  [[ "$(printf '%s' "${body}" | python3 -c 'import json,sys; print(json.load(sys.stdin).get("ok"))' 2>/dev/null)" == "True" ]]
}
run "local nginx path /healthz responds via ${LOCAL_URL}" check_local_healthz

check_local_filings() {
  local body
  body="$(curl -sf --max-time 5 "${LOCAL_URL}/api/filings?source=__nonexistent__" 2>/dev/null)" || return 1
  printf '%s' "${body}" | python3 -c 'import json,sys; assert json.load(sys.stdin).get("items")==[]' 2>/dev/null
}
run "local /api/filings reverse proxy works" check_local_filings

check_serve_status() {
  local status
  status="$("${TAILSCALE_BIN}" serve status 2>/dev/null)" || return 1
  [[ "${status}" == *"127.0.0.1:${LOCAL_PORT}"* ]]
}
run "tailscale serve points at 127.0.0.1:${LOCAL_PORT}" check_serve_status

check_tailnet_home() {
  curl -sf --max-time 10 "${BASE_URL}/" >/dev/null 2>&1
}
run "tailnet URL serves frontend HTML" check_tailnet_home

check_tailnet_healthz() {
  local body
  body="$(curl -sf --max-time 10 "${BASE_URL}/healthz" 2>/dev/null)" || return 1
  [[ "$(printf '%s' "${body}" | python3 -c 'import json,sys; print(json.load(sys.stdin).get("ok"))' 2>/dev/null)" == "True" ]]
}
run "tailnet URL proxies /healthz" check_tailnet_healthz

check_tailnet_filings() {
  local body
  body="$(curl -sf --max-time 10 "${BASE_URL}/api/filings?source=__nonexistent__" 2>/dev/null)" || return 1
  printf '%s' "${body}" | python3 -c 'import json,sys; assert json.load(sys.stdin).get("items")==[]' 2>/dev/null
}
run "tailnet URL proxies /api/filings" check_tailnet_filings

echo
if [[ ${failed} -eq 0 ]]; then
  echo "All ${step_count} tailscale checks passed."
  exit 0
else
  echo "Tailscale checks FAILED. Re-run scripts/setup_tailscale_serve.sh and inspect tailscale serve status."
  exit 1
fi
