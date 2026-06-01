#!/usr/bin/env bash
#
# setup_tailscale_serve.sh — publish the dockerized nginx frontend over Tailscale.
#
# Expected topology:
#   Browser -> https://<hostname>.<tailnet>.ts.net -> tailscale serve
#           -> http://127.0.0.1:8080 -> nginx -> /api/* -> backend:8080
#
# Usage:
#   ./scripts/setup_tailscale_serve.sh
#   LOCAL_PORT=8080 ./scripts/setup_tailscale_serve.sh
#
set -euo pipefail

TAILSCALE_BIN="${TAILSCALE_BIN:-tailscale}"
LOCAL_PORT="${LOCAL_PORT:-8080}"
LOCAL_URL="${LOCAL_URL:-http://127.0.0.1:${LOCAL_PORT}}"

command -v "${TAILSCALE_BIN}" >/dev/null 2>&1 || {
  echo "tailscale CLI not found in PATH" >&2
  exit 1
}

command -v python3 >/dev/null 2>&1 || {
  echo "python3 is required to parse tailscale status JSON" >&2
  exit 1
}

command -v curl >/dev/null 2>&1 || {
  echo "curl is required for local readiness checks" >&2
  exit 1
}

status_json="$("${TAILSCALE_BIN}" status --json)"
dns_name="$(printf '%s' "${status_json}" | python3 -c 'import json,sys; print(json.load(sys.stdin)["Self"]["DNSName"].rstrip("."))')"

if [[ -z "${dns_name}" ]]; then
  echo "failed to determine tailnet DNS name from tailscale status" >&2
  exit 1
fi

curl -sf --max-time 5 "${LOCAL_URL}/healthz" >/dev/null || {
  echo "local reverse proxy not ready at ${LOCAL_URL}/healthz" >&2
  echo "start the stack first: docker compose up -d --build" >&2
  exit 1
}

"${TAILSCALE_BIN}" serve --yes --bg "${LOCAL_URL}" >/dev/null

echo "tailscale serve configured for ${LOCAL_URL}"
echo "tailnet URL: https://${dns_name}"
echo
"${TAILSCALE_BIN}" serve status
