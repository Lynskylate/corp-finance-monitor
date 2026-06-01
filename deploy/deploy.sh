#!/usr/bin/env bash
#
# deploy.sh — Local CD for corp-finance-monitor (Phase 1B)
#
# Shell-based deployment (no ansible dependency).
# Variables documented in deploy/VARIABLES.md.
#
# Usage:
#   sudo ./deploy.sh
#
set -euo pipefail

# ── Configurable defaults ──────────────────────────────────────────────────
REPO_PATH="${REPO_PATH:-/home/lynskylate/corp-finance-monitor}"
VENV_PATH="${VENV_PATH:-${REPO_PATH}/.venv}"
DATA_DIR="${DATA_DIR:-${REPO_PATH}/data}"
CONFIG_PATH="${CONFIG_PATH:-${REPO_PATH}/config.yaml}"
DIST_PATH="${DIST_PATH:-${REPO_PATH}/dist}"
LISTEN_HOST="${LISTEN_HOST:-127.0.0.1}"
LISTEN_PORT="${LISTEN_PORT:-8080}"
SERVICE_NAME="${SERVICE_NAME:-cfm-api}"
SYNC_SERVICE_NAME="${SYNC_SERVICE_NAME:-cfm-sync}"
TIMER_NAME="${TIMER_NAME:-cfm-sync}"
LOG_DIR="${LOG_DIR:-/var/log/cfm}"
CFM_USER="${CFM_USER:-cfm}"
# install_method: "uv" (default) or "pip" (fallback)
INSTALL_METHOD="${INSTALL_METHOD:-uv}"

# ── 1. Create system user ──────────────────────────────────────────────────
if ! id -u "${CFM_USER}" &>/dev/null; then
  echo "==> Creating user '${CFM_USER}'"
  useradd --system --no-create-home --shell /usr/sbin/nologin "${CFM_USER}"
fi

# ── 2. Create directories ─────────────────────────────────────────────────
echo "==> Creating directories"
install -d -o "${CFM_USER}" -g "${CFM_USER}" -m 755 "${DATA_DIR}"
install -d -o "${CFM_USER}" -g "${CFM_USER}" -m 755 "${DATA_DIR}/.cfm_state"
install -d -o "${CFM_USER}" -g "${CFM_USER}" -m 755 "${DATA_DIR}/filings"
install -d -o "${CFM_USER}" -g "${CFM_USER}" -m 755 "${LOG_DIR}"

# ── 3. Install project ────────────────────────────────────────────────────
if [[ "${INSTALL_METHOD}" == "uv" ]]; then
  echo "==> Installing via uv (dist/*.whl)"
  if [[ ! -f "${DIST_PATH}/corp_finance_monitor-0.1.0-py3-none-any.whl" ]]; then
    echo "   Building wheel first..."
    uv build --directory "${REPO_PATH}"
  fi
  uv pip install --python "${VENV_PATH}/bin/python" \
    "${DIST_PATH}/corp_finance_monitor-0.1.0-py3-none-any.whl"
elif [[ "${INSTALL_METHOD}" == "pip" ]]; then
  echo "==> Installing via pip (dist/*.whl)"
  if [[ ! -d "${VENV_PATH}" ]]; then
    python3 -m venv "${VENV_PATH}"
  fi
  "${VENV_PATH}/bin/pip" install \
    "${DIST_PATH}/corp_finance_monitor-0.1.0-py3-none-any.whl"
fi
chown -R "${CFM_USER}:${CFM_USER}" "${VENV_PATH}"

# ── 4. Verify install ────────────────────────────────────────────────────
echo "==> Verifying installation"
"${VENV_PATH}/bin/cfm" --help > /dev/null 2>&1 || {
  echo "ERROR: cfm command not found at ${VENV_PATH}/bin/cfm"
  exit 1
}
echo "    cfm binary OK"

# ── 5. Install systemd units ──────────────────────────────────────────────
echo "==> Installing systemd units"
SYSTEMD_SRC="${REPO_PATH}/deploy/systemd"
for unit in cfm-api.service cfm-sync.service cfm-sync.timer; do
  sed \
    -e "s|{{ REPO_PATH }}|${REPO_PATH}|g" \
    -e "s|{{ VENV_PATH }}|${VENV_PATH}|g" \
    -e "s|{{ CONFIG_PATH }}|${CONFIG_PATH}|g" \
    -e "s|{{ LISTEN_HOST }}|${LISTEN_HOST}|g" \
    -e "s|{{ LISTEN_PORT }}|${LISTEN_PORT}|g" \
    -e "s|{{ CFM_USER }}|${CFM_USER}|g" \
    -e "s|{{ LOG_DIR }}|${LOG_DIR}|g" \
    "${SYSTEMD_SRC}/${unit}.in" > "/etc/systemd/system/${unit}"
  chmod 644 "/etc/systemd/system/${unit}"
done
systemctl daemon-reload

# ── 5. Enable & start ─────────────────────────────────────────────────────
echo "==> Enabling and starting services"
systemctl enable "${SERVICE_NAME}"
systemctl restart "${SERVICE_NAME}"
systemctl enable "${TIMER_NAME}"
systemctl start "${TIMER_NAME}"

echo "==> Deployment complete."
echo "    API: http://${LISTEN_HOST}:${LISTEN_PORT}/healthz"
echo "    Sync timer: ${TIMER_NAME} (daily)"
