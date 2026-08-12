# Robot Cloud Platform ⭐

**机器人 + 云原生（Robot + Cloud Native）**

一个以 **Python** 为主语言的机器人云平台，将 ROS2 机器人（如 `ros2_car`）的**显示控制**能力上云，
通过云原生技术栈（Kubernetes）提供可观测、可扩展、可远程控制的 Web Dashboard。

> 🎯 培养方向：**机器人系统 + 云原生**

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
│   ROS2 topics  ⇄  MQTT / ZMQ  ⇄  JSON 统一数据模型          │
└──────────────────────────┬─────────────────────────────────┘
                           │  MQTT / ZMQ (主题消息)
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

**数据流链路**：`ROS2 → MQTT/ZMQ → Backend → Kubernetes → Web Dashboard`

---

## 📁 目录结构

```
.
├── backend/                 # FastAPI 后端（Python）
│   └── app/
│       ├── api/             # REST / WebSocket 接口
│       ├── core/            # 配置、依赖
│       └── services/        # 业务服务（消息消费、状态管理）
├── gateway/                 # ROS2 ⇄ MQTT/ZMQ 消息桥接（Python）
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
| 机器人 | ROS2（Humble，来自 `ros2_car`）|
| 消息总线 | MQTT / ZMQ |
| 后端 | Python · FastAPI · WebSocket · uvicorn |
| 云原生 | Kubernetes · Docker |
| 前端 | Web Dashboard（React + ROSlib / WebSocket）|

---

## 🚀 快速开始

### 后端本地启动

```bash
cd backend
pip install -r requirements.txt
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
  -d '{"action":"toggle_pause","value":true}'
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

Gateway 将这些 ROS2 话题转换为统一 JSON 模型，通过 MQTT/ZMQ 推送到云端 Backend，最终呈现在 Web Dashboard 上。

**下行（云端 → 机器人）：**

Web Dashboard 远程控制 → Backend `/api/control` → 消息总线 `robot/{id}/command/*` →
Gateway 订阅并转发 → ROS2 话题（`sdc/control_algo` / `sdc/pause` / `sdc/clear_trail`）→ ros2_car 执行。

> ros2_car 侧无需新增任何代码，只需保持发布/订阅上述 ROS2 话题即可。

---

## 📄 文档

- [架构设计](docs/architecture.md)
- [消息协议](docs/protocol.md)
- [Kubernetes 部署](docs/deployment.md)

---

## 🎓 培养目标

- **机器人系统**：ROS2 感知/决策/控制闭环、显示控制
- **云原生**：容器化、Kubernetes 编排、可观测性、DevOps 流水线
