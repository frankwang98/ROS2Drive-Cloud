#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
VENV_DIR="${REPO_DIR}/.venv-gateway"

python3 -m venv --system-site-packages "${VENV_DIR}"
"${VENV_DIR}/bin/pip" install -r "${REPO_DIR}/gateway/requirements.txt" \
  "${REPO_DIR}/robot_contracts"

echo "Gateway 本地环境已创建：${VENV_DIR}"

