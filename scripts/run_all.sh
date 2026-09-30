#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
COMPOSE_FILE="${REPO_DIR}/docker/docker-compose.yml"
MODE="${1:-mock}"

case "${MODE}" in
  mock)
    export ROBOT_MODE=simulation
    # 防止上一次实车联调的 Gateway 与模拟车同时向 car01 发布数据。
    docker compose -f "${COMPOSE_FILE}" --profile real stop gateway-real >/dev/null 2>&1 || true
    docker compose -f "${COMPOSE_FILE}" up --build -d mqtt-broker backend simulator mock-robot
    ;;
  ros2)
    export ROBOT_MODE=real
    # 实车模式不能保留模拟数据源或 Mock ACK，否则 Dashboard 会混入假数据。
    docker compose -f "${COMPOSE_FILE}" stop simulator mock-robot >/dev/null 2>&1 || true
    docker compose -f "${COMPOSE_FILE}" --profile real up --build -d mqtt-broker backend gateway-real
    ;;
  stop)
    docker compose -f "${COMPOSE_FILE}" --profile real down
    exit 0
    ;;
  *)
    echo "Usage: $0 [mock|ros2|stop]" >&2
    exit 2
    ;;
esac

echo "等待 Backend 就绪…"
for _ in $(seq 1 60); do
  if curl --fail --silent http://localhost:8000/healthz >/dev/null; then
    echo "系统已启动：Dashboard http://localhost:8000/dashboard"
    if [[ "${MODE}" == "mock" ]]; then
      echo "运行验收：python3 scripts/verify_e2e.py"
    else
      echo "请在宿主机启动 ros2_car；Gateway 将通过 ROS_DOMAIN_ID=${ROS_DOMAIN_ID:-0} 自动发现话题。"
      echo "联调步骤见 docs/integration-testing.md"
    fi
    exit 0
  fi
  sleep 1
done

echo "Backend 未在 60 秒内就绪，请运行 docker compose -f ${COMPOSE_FILE} logs" >&2
exit 1

