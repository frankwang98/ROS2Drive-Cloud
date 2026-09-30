#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
VENV_DIR="${REPO_DIR}/.venv-gateway"
ROS_DISTRO_NAME="${ROS_DISTRO:-jazzy}"
ROS_SETUP="/opt/ros/${ROS_DISTRO_NAME}/setup.bash"

if [[ ! -f "${ROS_SETUP}" ]]; then
  echo "找不到 ${ROS_SETUP}，请设置正确的 ROS_DISTRO。" >&2
  exit 1
fi
if [[ ! -x "${VENV_DIR}/bin/python" ]]; then
  echo "Gateway 环境不存在，请先运行 ./scripts/setup_gateway_local.sh" >&2
  exit 1
fi

# ROS2 setup 脚本会探测若干可能未定义的 AMENT 变量，与 `set -u` 不兼容。
set +u
source "${ROS_SETUP}"
set -u
export ROS_DOMAIN_ID="${ROS_DOMAIN_ID:-0}"
if [[ -n "${ROS_WORKSPACE_SETUP:-}" ]]; then
  set +u
  source "${ROS_WORKSPACE_SETUP}"
  set -u
fi

exec "${VENV_DIR}/bin/python" "${REPO_DIR}/gateway/ros2_bridge.py" \
  --robot-id "${ROBOT_ID:-car01}" \
  --robot-namespace "${ROBOT_NAMESPACE:-}" \
  --mqtt-broker "${MQTT_BROKER:-localhost}" \
  --mqtt-port "${MQTT_PORT:-1884}"

