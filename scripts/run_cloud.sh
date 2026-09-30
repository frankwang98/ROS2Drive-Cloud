#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
COMPOSE_FILE="${REPO_DIR}/docker/docker-compose.yml"

export ROBOT_MODE=real

# 默认架构只保留 mqtt-broker + backend。先停止可能残留的演示/容器 Gateway。
docker compose -f "${COMPOSE_FILE}" --profile demo --profile docker-gateway \
  stop simulator mock-robot gateway-real >/dev/null 2>&1 || true
docker compose -f "${COMPOSE_FILE}" up --build -d mqtt-broker backend

for _ in $(seq 1 60); do
  if curl --fail --silent http://localhost:8000/healthz >/dev/null; then
    echo "Cloud 已启动（2 个容器）："
    echo "  MQTT:     localhost:1884"
    echo "  Backend:  http://localhost:8000"
    echo "  Frontend: http://localhost:8000/dashboard/"
    exit 0
  fi
  sleep 1
done

echo "Backend 未在 60 秒内就绪" >&2
exit 1

