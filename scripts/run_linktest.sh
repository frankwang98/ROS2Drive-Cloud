#!/usr/bin/env bash
# ============================================================
# Robot Cloud Platform — 两端联调启动脚本
#
# 一键启动本地开发链路（MQTT broker + Backend + 消息模拟器），
# 并可选启动真实 ROS2 Gateway 桥接（需 ROS2 环境）或 Mock 机器人
# 用于验证「云端指令 → 总线 → 机器人侧」下行链路。
#
# 用法：
#   ./scripts/run_linktest.sh                # 默认: broker + backend + simulator + mock_robot
#   ./scripts/run_linktest.sh --with-gateway # 额外启动真实 ROS2 gateway（需 source ROS2）
#   ./scripts/run_linktest.sh --no-sim       # 不启动消息模拟器（仅下行验证）
# ============================================================
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

WITH_GATEWAY=0
WITH_SIM=1

for arg in "$@"; do
  case "$arg" in
    --with-gateway) WITH_GATEWAY=1 ;;
    --no-sim)       WITH_SIM=0 ;;
    *) echo "未知参数: $arg" >&2; exit 1 ;;
  esac
done

echo "======================================================="
echo "  Robot Cloud Platform 两端联调"
echo "  MQTT_BROKER=localhost  MQTT_PORT=1884  ZMQ_PORT=5555"
echo "======================================================="

# 1) 确保 MQTT broker 可用（优先用 docker，其次本机 mosquitto）
ensure_broker() {
  if docker version >/dev/null 2>&1; then
    if ! docker ps --format '{{.Names}}' | grep -q '^robot-mqtt$'; then
      echo ">> 启动 MQTT broker (eclipse-mosquitto)"
      docker rm -f robot-mqtt >/dev/null 2>&1 || true
      docker run -d --name robot-mqtt -p 1884:1884 \
        -v "$ROOT_DIR/docker/mosquitto.conf:/mosquitto/config/mosquitto.conf:ro" \
        eclipse-mosquitto:2
    else
      echo ">> MQTT broker 已运行"
    fi
  elif command -v mosquitto >/dev/null 2>&1; then
    echo ">> 使用本机 mosquitto（需手动监听 1884）"
  else
    echo "!! 未找到 docker 或 mosquitto，无法启动 MQTT broker" >&2
    exit 1
  fi
}

# 2) 启动 Backend
start_backend() {
  echo ">> 启动 Backend (FastAPI) :8000 (mode=simulation)"
  ( cd backend && pip install -q -r requirements.txt && \
    ROBOT_MODE=simulation uvicorn app.main:app --host 0.0.0.0 --port 8000 ) &
  BACKEND_PID=$!
}

# 3) 启动消息模拟器（可选）
start_simulator() {
  echo ">> 启动 MQTT 消息模拟器（仿真模式）"
  ( cd gateway && pip install -q paho-mqtt pyzmq && \
    python3 mqtt_simulator.py --mqtt-broker localhost --mqtt-port 1884 --mode simulation ) &
  SIM_PID=$!
}

# 4) 启动 Mock 机器人（订阅 command 主题，验证下行链路）
start_mock_robot() {
  echo ">> 启动 Mock 机器人（监听 command 下行）"
  ( cd gateway && python3 mock_robot.py --mqtt-broker localhost --mqtt-port 1884 ) &
  MOCK_PID=$!
}

# 5) 启动真实 ROS2 Gateway（可选）
start_gateway() {
  echo ">> 启动 ROS2 Gateway (ros2_bridge.py, 含下行转发)"
  ( cd gateway && python3 ros2_bridge.py --robot-id car01 \
      --mqtt-broker localhost --mqtt-port 1884 --zmq-port 5555 ) &
  GATEWAY_PID=$!
}

ensure_broker
start_backend
if [ "$WITH_SIM" = "1" ]; then start_simulator; fi
start_mock_robot
if [ "$WITH_GATEWAY" = "1" ]; then start_gateway; fi

echo ""
echo "== 联调链路已启动 =="
echo "  Dashboard:  http://localhost:8000/dashboard"
echo "  状态接口:   curl http://localhost:8000/api/robot/status"
echo "  下发指令:   curl -X POST http://localhost:8000/api/control \\"
echo "                -H 'Content-Type: application/json' \\"
echo "                -d '{\"action\":\"toggle_pause\",\"value\":true}'"
echo ""
echo "按 Ctrl+C 停止所有进程"
trap 'echo ""; echo "== 停止所有进程 =="; \
  [ -n "${BACKEND_PID:-}" ] && kill $BACKEND_PID 2>/dev/null; \
  [ -n "${SIM_PID:-}" ] && kill $SIM_PID 2>/dev/null; \
  [ -n "${MOCK_PID:-}" ] && kill $MOCK_PID 2>/dev/null; \
  [ -n "${GATEWAY_PID:-}" ] && kill $GATEWAY_PID 2>/dev/null; \
  wait 2>/dev/null; exit 0' INT TERM

wait
