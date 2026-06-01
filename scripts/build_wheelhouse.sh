#!/usr/bin/env bash
set -euo pipefail

# Build wheelhouse on host (requires internet) for offline Docker install.
# Docker containers on this host cannot reach PyPI, so we pre-build wheels here.

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
WHEELHOUSE="${REPO_ROOT}/wheelhouse"

mkdir -p "${WHEELHOUSE}"
rm -f "${WHEELHOUSE}"/*.whl

cd "${REPO_ROOT}"
pip wheel --no-cache-dir -w "${WHEELHOUSE}" .

echo "Wheelhouse built: ${WHEELHOUSE}"
ls -1 "${WHEELHOUSE}"/*.whl | wc -l | xargs echo "Wheels count:"
