# Robot Cloud Platform ⭐

**机器人 + 云原生（Robot + Cloud Native）**

一个以 **Python** 为主语言的机器人云平台，将 ROS2 机器人（如 `ros2_car`）的**显示控制**能力上云，
通过云原生技术栈（Kubernetes）提供可观测、可扩展、可远程控制的 Web Dashboard。

> 🎯 培养方向：**机器人系统 + 云原生**

## 当前推荐运行拓扑

```text
本地进程                         Docker（仅 2 个容器）
┌──────────────┐   ROS2          ┌──────────────┐
│ ros2_car     │ ─────────────→  │              │
└──────────────┘                 │              │
        ↑                        │              │
        │ ROS2                   │              │
┌───────┴──────┐   MQTT          │ MQTT Broker  │
│ Python       │ ─────────────→  │ :1884        │
│ Gateway      │ ←─────────────  │              │
└──────────────┘                 └──────┬───────┘
                                       │ MQTT
                                ┌──────▼───────┐
                                │ Backend      │
                                │ + Frontend   │
                                │ :8000        │
                                └──────────────┘
```

- `ros2_car`：本地 ROS2 自动驾驶仿真和 RViz。
- `gateway`：本地 Python 进程，读取 ROS2 状态、发送 MQTT，并把云端命令转回 ROS2。
- `mqtt-broker`：Docker 容器。
- `backend`：Docker 容器；同时托管 REST、WebSocket 和静态 Frontend，因此不需要单独前端容器。

Simulator、Mock Robot 和容器化 Gateway 只保留为测试 profile，不属于默认启动路径。

---

## 🏗️ 整体架构

```
┌────────────────────────────────────────────────────────────┐
│                       ROS2 机器人 (ros2_car)               │
│   sensor  →  decision  →  control  →  RViz 可视化          │
└──────────────────────────┬─────────────────────────────────┘
                           │  ROS2 topics
                           ▼
┌────────────────────────────────────────────────────────────┐
│                  Gateway (消息桥接，Python)                 │
│   ROS2 topics  ⇄  MQTT  ⇄  JSON 统一数据模型                │
└──────────────────────────┬─────────────────────────────────┘
                           │  MQTT (主题消息)
                           ▼
┌────────────────────────────────────────────────────────────┐
│                   Backend (FastAPI, Python)                │
│   REST API  ·  WebSocket 实时推送  · 状态管理  · 鉴权       │
└──────────────────────────┬─────────────────────────────────┘
                           │  部署 / 编排
                           ▼
┌────────────────────────────────────────────────────────────┐
│                    Kubernetes (云原生)                      │
│   Deployment · Service · Ingress · ConfigMap · HPA         │
└──────────────────────────┬─────────────────────────────────┘
                           ▼
┌────────────────────────────────────────────────────────────┐
│                  Web Dashboard (前端)                       │
│   实时状态 · 远程控制 · 可视化面板 · 消息监控               │
└────────────────────────────────────────────────────────────┘
```

**数据流链路**：`ROS2 → MQTT → Backend → Kubernetes → Web Dashboard`

---

## 📁 目录结构

```
.
├── backend/                 # FastAPI 后端（Python）
│   └── app/
│       ├── api/             # REST / WebSocket 接口
│       ├── core/            # 配置、依赖
│       └── services/        # 业务服务（消息消费、状态管理）
├── gateway/                 # ROS2 ⇄ MQTT 消息桥接（Python）
├── k8s/                     # Kubernetes 部署清单
├── web/                     # Web Dashboard 前端
├── docker/                  # 容器化配置（Dockerfile）
├── config/                  # 运行时配置
├── docs/                    # 架构与使用文档
└── .cnb.yml                 # CNB CI 流水线
```

---

## 🧱 技术栈

| 层 | 技术 |
|----|------|
| 机器人 | ROS2 Jazzy（来自 `ros2_car`）|
| 消息总线 | MQTT（ZMQ 仅保留为实验兼容选项）|
| 后端 | Python · FastAPI · WebSocket · uvicorn |
| 云原生 | Kubernetes · Docker |
| 前端 | 原生 HTML/CSS/JavaScript + WebSocket |

---

## 🚀 快速开始

### 一键运行完整车云链路

推荐按三个终端启动。

首次准备 Gateway：

```bash
cd /home/ubuntu/dev/frank_ws/robot_platform
./scripts/setup_gateway_local.sh
```

终端 1，启动两个云端容器：

```bash
./scripts/run_cloud.sh
```

终端 2，启动本地小车：

```bash
ROS_DOMAIN_ID=0 ./scripts/run_car_local.sh
```

终端 3，启动本地 Gateway：

```bash
ROS_DOMAIN_ID=0 ./scripts/run_gateway_local.sh
```

打开 `http://localhost:8000/dashboard/`。详细检查见 [本地车云联调](docs/local-stack.md)。

以下 Mock 模式仅用于没有 ROS2 时测试协议：

无需 ROS2，使用 Simulator + Mock Robot 验证完整链路：

```bash
./scripts/run_all.sh mock
python3 scripts/verify_e2e.py
```

验收覆盖：`Telemetry → Heartbeat → RobotRegistry → REST Command → MQTT → Mock Robot → ACK`。
Dashboard 地址：`http://localhost:8000/dashboard`。

Mock 的完整检查项见 [协议 E2E 手册](docs/integration-testing.md)。日常开发只需使用上面的本地三终端方式。

### 运行模式（仿真 / 实车）

平台支持两种数据来源模式，可在 Web Dashboard 右上角或 `/api/mode` 动态切换：

| 模式 | 数据源 | 适用场景 |
|------|--------|----------|
| `simulation`（默认）| `gateway/mqtt_simulator.py` | 无真实机器人的开发/演示，生成模拟数据并驱动地图小车运动 |
| `real` | `gateway/ros2_bridge.py` | 接入本地 ROS2（ros2_car）实时数据，展示真实位姿/轨迹 |

切换方式（REST）：

```bash
# 查询当前模式
curl http://localhost:8000/api/mode

# 切换为实车模式
curl -X POST http://localhost:8000/api/mode \
  -H 'Content-Type: application/json' -d '{"mode":"real"}'

# 切换回仿真模式
curl -X POST http://localhost:8000/api/mode \
  -H 'Content-Type: application/json' -d '{"mode":"simulation"}'
```

> 模式仅标识数据来源，实车模式下需自行运行 `gateway/ros2_bridge.py` 并保证 ROS2 环境已 source。

### 后端本地启动

```bash
cd backend
pip install -r requirements.txt
# 默认仿真模式；也可 ROBOT_MODE=real uvicorn ...
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

### 两端联调（含下行控制）

```bash
# 一键启动 MQTT broker + Backend + 消息模拟器 + Mock 机器人（验证下行链路）
./scripts/run_linktest.sh

# 也可用 docker compose 一键启动（broker + backend + simulator + mock-robot）
docker compose -f docker/docker-compose.yml up --build
```

启动后即可用 REST 下发控制指令并观察下行链路：

```bash
# 切换控制算法
curl -X POST http://localhost:8000/api/control \
  -H 'Content-Type: application/json' \
  -d '{"action":"set_control_algo","value":1}'

# 暂停仿真
curl -X POST http://localhost:8000/api/control \
  -H 'Content-Type: application/json' \
  -d '{"action":"set_paused","value":true}'
```

### 完整链路（容器化）

```bash
# 构建镜像
docker compose -f docker/docker-compose.yml build

# 启动（MQTT broker + backend + web）
docker compose -f docker/docker-compose.yml up
```

### Kubernetes 部署

```bash
kubectl apply -f k8s/namespace.yaml
kubectl apply -f k8s/
```

---

## 🔌 与 ros2_car 的集成

`ros2_car` 通过 ROS2 话题发布机器人实时状态（见 `gateway/` 桥接层）：

- `/sdc/speed` —— 实时速度
- `/sdc/action_id` —— 行为状态（加速/巡航/减速/停车）
- `/sdc/front_distance` —— 前方障碍物距离
- `/sdc/obstacle_count` —— 障碍物数量
- `/simulation/markers` —— 道路/环境可视化
- `/sensor/lidar` —— LIDAR 点云
- `/sdc/control_algo` —— 控制算法切换
- `/sdc/pause` —— 暂停/继续

Gateway 将这些 ROS2 话题转换为统一 JSON 模型，通过 MQTT 推送到云端 Backend，最终呈现在 Web Dashboard 上。

**下行（云端 → 机器人）：**

Web Dashboard 远程控制 → Backend `/api/v1/robots/{id}/commands` → MQTT `robots/{id}/commands` →
Gateway 订阅并转发 → ROS2 话题（`sdc/control_algo` / `sdc/pause` / `sdc/clear_trail`）→ ros2_car 执行。

> ros2_car 侧无需新增任何代码，只需保持发布/订阅上述 ROS2 话题即可。

---

## 📄 文档

- [架构设计](docs/architecture.md)
- [消息协议](docs/protocol.md)
- [车云消息协议 v1](docs/protocol-v1.md)
- [Kubernetes 部署](docs/deployment.md)
- [实车模式·接入本地 ROS2 实时数据](docs/realtime-ros2.md)

---

## 🎓 培养目标

- **机器人系统**：ROS2 感知/决策/控制闭环、显示控制
- **云原生**：容器化、Kubernetes 编排、可观测性、DevOps 流水线
