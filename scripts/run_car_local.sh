#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WORKSPACE_DIR="$(cd "${SCRIPT_DIR}/../.." && pwd)"
CAR_DIR="${WORKSPACE_DIR}/ros2_car"
ROS_DISTRO_NAME="${ROS_DISTRO:-jazzy}"

if [[ ! -f "/opt/ros/${ROS_DISTRO_NAME}/setup.bash" ]]; then
  echo "找不到 ROS2 ${ROS_DISTRO_NAME}" >&2
  exit 1
fi
if [[ ! -f "${CAR_DIR}/install/setup.bash" ]]; then
  echo "ros2_car 尚未构建：缺少 ${CAR_DIR}/install/setup.bash" >&2
  exit 1
fi

# ROS2/ament setup 脚本会读取可选的未定义变量，与 `set -u` 不兼容。
set +u
source "/opt/ros/${ROS_DISTRO_NAME}/setup.bash"
source "${CAR_DIR}/install/setup.bash"
set -u
export ROS_DOMAIN_ID="${ROS_DOMAIN_ID:-0}"

exec ros2 launch self_driving_car_demo ring_road.launch.py

