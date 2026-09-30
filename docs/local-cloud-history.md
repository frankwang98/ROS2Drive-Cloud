# ROS2Drive Cloud ⭐

**车云协同控制平台（Vehicle-Cloud Control Platform）**

ROS2Drive Cloud 是 [`ros2_car`](../ros2_car)（运行时层为 **ROS2Drive**）的云端控制面：
车端负责 *behavior → planning → control → vehicle*，云端负责 *fleet / mission / telemetry / runtime visibility / remote ops*，
两者通过标准化的车云协议形成 **Cloud ⇄ Vehicle** 闭环。

> ROS2Drive is a low-speed autonomy runtime built on ROS 2.
> ROS2Drive Cloud is its cloud control plane.
> Together they form a small but complete reference stack for low-speed autonomous driving.

---

## 角色定位

云端 **不是** 一个「把 ROS topic 搬到网页上看」的 Dashboard，而是 **车队的运营平台**：

| # | 目标 | 含义 |
|---|---|---|
| ① | **多车管理** | 同时接入 `car01 / car02 / ...`，地图上看到每辆车的在线状态、位姿、速度、任务、故障 |
| ② | **任务闭环** | Web 下发 Mission → Edge 投递到 `ExecuteMission` Action → 车端 Behavior/Planning/Control 执行 → 上报 progress → Web 反馈 |
| ③ | **Runtime 状态可视化** | 不只显示 `x/y/speed`，还要显示 autonomy 状态机、Behavior Tree 当前节点、planning/control/fault/safety 关键状态 |
| ④ | **多场景** | `ring_demo / mining_haul / port_transport / agriculture_route` 等场景在 Cloud 侧抽象成同一套 *Vehicle + Mission + Route + Map* 实体，不因场景重复开发 |
| ⑤ | **数据闭环** | 全部 telemetry / event / mission progress 落库，支持历史轨迹回放、任务回放、故障分析、Planning Debug |
| ⑥ | **一键部署** | `docker compose up -d` 拉起整套云端（默认不含 DB / 缓存 / K8s，按需加） |

> 当前仓库聚焦 **第一版最小闭环**：跑通 *Cloud + Gateway + ROS2Drive*，只承诺 telemetry 上行；
> 完整 6 个目标按 Roadmap 逐步推进。

---

## 整体架构

```text
                    ROS2Drive Cloud
┌───────────────────────────────────────────────────────────────┐
│                                                               │
│   Web Dashboard (static, served by Backend)                   │
│   ┌───────────────────────────────────────────────────────┐   │
│   │  Map · Vehicle Cards · Mission Panel · Telemetry Feed │   │
│   └───────────────────────┬───────────────────────────────┘   │
│                           │ REST / WebSocket                  │
│                           ▼                                   │
│   ┌───────────────────────────────────────────────────────┐   │
│   │              Backend (FastAPI, Python)                │   │
│   │                                                       │   │
│   │  Vehicles · Missions · Telemetry · Runtime · Events   │   │
│   └──────────────────────┬────────────────────────────────┘   │
│                          │ MQTT (telemetry / event /          │
│                          │       command / command_ack /      │
│                          │       heartbeat)                   │
└──────────────────────────┼───────────────────────────────────┘
                           │
                           │ MQTT / TLS  (robots/{id}/...)
                           │
                ┌──────────▼──────────┐
                │   Edge Gateway      │  ← runs on the vehicle side
                │   (this repo,       │     or any host that can see
                │    gateway/)        │     the vehicle's ROS 2 DDS
                └──────────┬──────────┘
                           │  ROS 2 topics + actions
                           ▼
┌──────────────────────────────────────────────────────────────┐
│                          ROS2Drive                            │
│                                                              │
│  MissionManager → BehaviorManager → Planner →                 │
│  VelocityPlanner → Controller → SafetyManager                │
│                                                              │
│  VehicleInterface (SimulatedVehicle / CAN Adapter)           │
└──────────────────────────────────────────────────────────────┘
```

**关键边界：Cloud 不直接理解 ROS topic。** Gateway 是车云之间的 *唯一* 翻译层，
负责把 ROS 2 typed 接口（Action / Topic / Service）封装成统一的 MQTT Envelope。

---

## 与 ROS2Drive 的契约

云端能下发的「正式接口」只有 **Mission**（通过 `ExecuteMission` Action）。
老的 `set_paused / set_control_algo / clear_trail` 等指令属于 *legacy* 兼容路径，仅在
第一版 telemetry-only 闭环里保留。

### ROS 2 接口表（`robot_namespace:=car01` → `/car01/...`）

| Name | 类型 | 方向 | 说明 |
|---|---|---|---|
| `mission/execute` | `ExecuteMission` Action | Cloud → Vehicle | 任务下发 / 抢占 / 取消 |
| `planning/trajectory` | `Trajectory` | Vehicle → Cloud | 稠密可跟踪轨迹 |
| `control/command` | `ControlCommand` | Vehicle → Cloud | Safety 仲裁后的最终命令 |
| `runtime/status` | `RuntimeStatus` | Vehicle → Cloud | runtime + mission 快照 |
| `runtime/faults` | `FaultArray` | Vehicle → Cloud | active faults |
| `runtime/metrics` | `RuntimeMetrics` | Vehicle → Cloud | 循环统计 |
| `runtime/health` | `std_srvs/Trigger` | Cloud → Vehicle | readiness 检查 |
| `runtime/acknowledge_recovery` | `std_srvs/Trigger` | Cloud → Vehicle | 解除 latched STOP |
| `sdc/emergency_stop` | `std_msgs/Bool` | Cloud → Vehicle | 软件急停输入 |
| `sdc/*` 标量 topic | — | Vehicle → Cloud | **仅为兼容 Gateway/HUD 存在**，新集成应使用 typed 接口 |

### Mission 类型（`ExecuteMission.action`）

`NAVIGATE_TO` · `FOLLOW_ROUTE` · `STOP` · `PARK` · `DOCK` · `RETURN_HOME`

携带 `mission_id`（幂等键）、`route`（Pose2D 列表）、`speed_limit`、`goal_tolerance`、`timeout_s`、`allow_preempt`。

### RuntimeStatus 关键字段

`runtime_state` · `mission_id` · `mission_type` · `mission_state` · `mission_progress` · `result_reason` · `localized` · `healthy` · `recovery_required` · `recovery_ready`

---

## 第一版范围（最小闭环）

只跑通 **Cloud + Gateway + ROS2Drive** 三件套，**明确不包含**：

- ❌ PostgreSQL / Redis / 任何持久化（状态全部走 Backend 进程内缓存 + 重启即丢）
- ❌ Kubernetes（部署只在 Docker Compose 上验证）
- ❌ Mission 下发链路（Web → Mission → Action）
- ❌ 多车接入（默认一个 `robot_id=car01`）
- ❌ 场景切换 UI（场景由 `ros2_car` 的 launch 参数决定，云端不感知）
- ❌ 数据回放 / 持久 telemetry 历史

**第一版只承诺：**

- ✅ Cloud：MQTT broker + Backend（FastAPI + Web Dashboard）一键起
- ✅ Gateway：把 ROS 2 旧 `sdc/*` 兼容 topic 转为 MQTT telemetry，**telemetry 只读上行**
- ✅ Web Dashboard：实时展示 `runtime/status`、`control/command`、`sdc/odometry`、legacy scalars
- ✅ Web 端下发 *legacy* 指令：`set_control_algo` / `set_paused` / `clear_trail`（这些会在 v2 被 Mission API 替换）

完整能力按 [Roadmap](#roadmap) 推进。

---

## 🚀 快速开始（第一版最小闭环）

需要三个终端，分别启动 *Cloud / Vehicle / Gateway*。**Gateway 必须在已 source
ROS 2 环境的 shell 中启动**，否则 import `self_driving_car_demo.msg` 会失败。

### ⚠️ 前置：source ROS 2 环境（终端 2 和终端 3）

Gateway 直接 import ROS 2 自定义消息（`self_driving_car_demo.msg`），所以**必须**在
已 source ROS 2 的 shell 中运行。`source` 只对**当前终端**生效，新开终端需要重做。

**zsh**（推荐，路径设置更完整）：

```bash
source /opt/ros/jazzy/setup.zsh
source /home/ubuntu/dev/frank_ws/ros2_car/install/setup.zsh

# 验证 import 通了
python3 -c "from self_driving_car_demo.msg import RuntimeStatus; print('OK')"
```

**bash**：

```bash
source /opt/ros/jazzy/setup.bash
source /home/ubuntu/dev/frank_ws/ros2_car/install/setup.bash
```

> 脚本会自动检测你的 shell 并给出对应命令。如果忘了 source，gateway 会打印
> 明确的错误提示而不是 traceback。

### 终端 1：Cloud（MQTT broker + Backend）

```bash
cd /home/ubuntu/dev/frank_ws/robot_platform
./scripts/run_cloud.sh
```

脚本等价于：

```bash
docker compose -f docker/docker-compose.yml up --build mqtt-broker backend
```

启动后：

- MQTT broker：`localhost:1884`
- Backend + Web Dashboard：`http://localhost:8000/dashboard`
- 打开浏览器即可看到 Dashboard（首次启动时 vehicle 列表为空）

### 终端 2：Vehicle（ROS2Drive）

先 source ROS 2 环境（见上方），然后：

```bash
cd /home/ubuntu/dev/frank_ws/robot_platform
ROS_DOMAIN_ID=0 ./scripts/run_car_local.sh
```

脚本等价于：

```bash
ROS_DOMAIN_ID=0 ros2 launch self_driving_car_demo ring_road.launch.py \
    robot_id:=car01 \
    scenario:=ring_demo \
    use_rviz:=false
```

> `use_rviz:=false` 节省资源，纯看云端能不能收到消息。如需可视化可去掉。

### 终端 3：Gateway

先 source ROS 2 环境（见上方），然后：

```bash
cd /home/ubuntu/dev/frank_ws/robot_platform
ROS_DOMAIN_ID=0 ./scripts/run_gateway_local.sh
```

脚本等价于：

```bash
ROS_DOMAIN_ID=0 python3 gateway/ros2_bridge.py --robot-id car01 \
    --mqtt-broker localhost --mqtt-port 1884
```

预期日志：

```
已订阅 legacy 下行指令: robots/car01/commands
已订阅 emergency_stop: robots/car01/emergency_stop
已订阅 mission_command: robots/car01/missions/command
[typed] runtime/status
[typed] runtime/faults
[typed] runtime/metrics
[typed] control/command
[typed] planning/trajectory
[legacy] sdc/speed
[legacy] sdc/action_id
[legacy] sdc/front_distance
[legacy] sdc/obstacle_count
[legacy] sdc/odometry
Bridge 已启动，robot_id=car01，等待 ROS 2 消息…
```

**注意**：gateway 启动日志里**不应该**出现 `incompatible QoS` warning。如果出现，
说明 typed subscription 的 QoS 没和 ros2_car publisher 对齐。

启动后 Dashboard 上的 `car01` 卡片应显示 **online**，并开始出现实时 telemetry。

### 终端 4（可选）：MQTT 验证

想直接看 typed topics 是否从车端真的到达 Cloud：

```bash
# 所有 14 个 topic（应该每秒刷一次）
mosquitto_sub -h localhost -p 1884 -t 'robots/car01/#' -v | head -50

# 单条 typed topic 完整 JSON
mosquitto_sub -h localhost -p 1884 -t 'robots/car01/runtime/status' -v -C 1
mosquitto_sub -h localhost -p 1884 -t 'robots/car01/control/command' -v -C 1
mosquitto_sub -h localhost -p 1884 -t 'robots/car01/planning/trajectory' -v -C 1
```

### 一键 Mock 验证（无需 ROS 2）

只想验证 Cloud 内部协议链路时（无 ROS 2 环境），可用 Mock 模式：

```bash
docker compose -f docker/docker-compose.yml --profile demo up --build
python3 scripts/verify_e2e.py
```

覆盖：Telemetry → Heartbeat → RobotRegistry → REST Command → MQTT → Mock Robot → ACK。

---

## 🧱 技术栈

| 层 | 技术 |
|---|---|
| 车端 | ROS 2 Jazzy · `self_driving_car_demo`（Runtime + Behavior Tree + Planner/Controller/Safety） |
| 车云协议 | MQTT（Eclipse Mosquitto）· 协议 v1，定义见 [`docs/protocol-v1.md`](docs/protocol-v1.md) |
| Cloud Backend | Python · FastAPI · WebSocket · uvicorn |
| Cloud Frontend | 原生 HTML/CSS/JavaScript + WebSocket（由 Backend 静态托管） |
| 部署 | Docker Compose v2 |

---

## 📁 目录结构

```
robot_platform/
├── backend/                 # FastAPI 后端（Python）
│   └── app/
│       ├── api/             # REST / WebSocket 接口
│       ├── core/            # 配置、依赖
│       └── services/        # 业务服务（消息消费、状态管理）
├── gateway/                 # Edge Gateway：ROS 2 ⇄ MQTT 桥接（Python）
│   ├── ros2_bridge.py       # 订阅 ROS 2 topic → MQTT 上行
│   ├── mqtt_simulator.py    # 无 ROS 2 时的纯协议模拟
│   └── mock_robot.py        # Mock Vehicle：消费 Cloud 下行指令
├── robot_contracts/         # 车云协议 schema（Python 包，v1）
├── web/                     # Web Dashboard 前端（静态资源）
├── docker/                  # 容器化：Dockerfile + docker-compose
├── docs/                    # 架构 / 协议 / 联调手册
├── scripts/                 # 三终端启动 / E2E 验证脚本
└── .cnb.yml                 # CNB CI 流水线
```

---

## 🔌 与 ROS2Drive 的集成现状

**第一版只读上行（telemetry）：** Gateway 订阅 ROS 2 的兼容 `sdc/*` topic，转成 MQTT telemetry 推到 Cloud。
Web Dashboard 上能看到的字段：

| 来源 | 字段 | 说明 |
|---|---|---|
| `sdc/odometry` | `pose`, `velocity` | 驱动地图上的车与轨迹 |
| `sdc/speed` | 实时速度 (m/s) | legacy scalar |
| `sdc/action_id` | 行为编号 | legacy scalar |
| `sdc/front_distance` | 前方障碍距离 | legacy scalar |
| `sdc/obstacle_count` | 障碍物数量 | legacy scalar |

**第一版下行（legacy 兼容路径）：** Web Dashboard 远程控制 → Backend `/api/v1/robots/{id}/commands` → MQTT `robots/{id}/commands` → Gateway 转发为 ROS 2 topic（`sdc/control_algo` / `sdc/pause` / `sdc/clear_trail`）→ ROS2Drive 执行。

> ROS2Drive 侧无需新增任何代码即可接入第一版。
> **下一步** 将扩展 Gateway 接入 `mission/execute` Action 与 `runtime/*` typed 接口，把 `set_paused` / `set_control_algo` 替换为 Mission API。

详细 ROS 2 接口契约见 [`ros2_car/docs/interfaces.md`](../ros2_car/docs/interfaces.md)。

---

## 📄 文档

- 架构总览：[`docs/architecture.md`](docs/architecture.md)
- 消息协议 v1（当前实现）：[`docs/protocol-v1.md`](docs/protocol-v1.md)
- 消息协议（旧版存档）：[`docs/protocol.md`](docs/protocol.md)
- 本地三终端联调：[`docs/local-stack.md`](docs/local-stack.md)
- 协议 E2E 手册：[`docs/integration-testing.md`](docs/integration-testing.md)
- Roadmap：[`docs/roadmap.md`](docs/roadmap.md)
- ROS2Drive 侧接口契约：[`ros2_car/docs/interfaces.md`](../ros2_car/docs/interfaces.md)

---

## 🛣️ Roadmap

> 每项必须有明确契约 + 实现 + 自动化测试 + 文档，不以"代码已写但链路未验证"作为完成。

### M0 — 第一版最小闭环（本仓库当前目标）

- [x] MQTT broker + Backend 一键起（`docker compose up`）
- [x] Gateway 把 ROS 2 兼容 `sdc/*` topic 上行到 MQTT telemetry
- [x] Web Dashboard 实时展示 telemetry + legacy 下行控制
- [x] 三终端脚本化（`run_cloud.sh` / `run_car_local.sh` / `run_gateway_local.sh`）
- [x] Mock 模式 E2E 验收脚本

### M1 — Mission 闭环（替换 legacy 下行）

- [ ] Gateway 接入 `mission/execute` Action，把 Cloud Mission 投递到 ROS2Drive
- [ ] Gateway 上行 `runtime/status` / `runtime/faults` / `runtime/metrics` / `control/command` / `planning/trajectory`
- [ ] Backend 增加 `POST /missions` 与 Mission 生命周期管理
- [ ] Web Dashboard 增加 Mission 面板（创建 / 监控 / 取消）
- [ ] 退役 `/api/control` 的 `set_control_algo` / `set_paused`

### M2 — Runtime 状态可视化

- [ ] RuntimeStatus 全字段上 Dashboard（runtime_state / mission_state / progress / recovery_required）
- [ ] Behavior Tree 当前节点高亮（基于 BT XML 与 RuntimeStatus）
- [ ] Fault 实时告警栏（按 severity 分级）
- [ ] Control 限幅 / Safety 仲裁状态可视化

### M3 — 多车 & 多场景

- [ ] Gateway 支持多个 `robot_id`（`car01` / `car02` / ...）
- [ ] Backend 按 `robot_id` 隔离状态
- [ ] Web Dashboard 多车地图（聚合渲染）
- [ ] 场景由 launch 切换，Cloud 侧只抽象 *Vehicle + Mission + Route + Map*

### M4 — 数据闭环

- [ ] Telemetry / Event / Mission progress 落库
- [ ] 历史轨迹回放
- [ ] 任务回放 + 故障分析
- [ ] Replay → ROS2Drive Simulation（线下回灌）

### M5 — 工程化与可观测

- [ ] 单元 / 契约 / 集成 / E2E 测试体系
- [ ] 结构化日志、metrics、health、tracing
- [ ] CI：format / static check / unit / E2E
- [ ] Docker Compose 验收环境与 nightly 构建

### 不做（明确边界）

- 不引入 Kafka / Service Mesh / 车端微服务化
- 不让 Cloud 越权设置 planner / controller 作为正式任务接口
- 不用软件 Safety 替代底盘硬件安全链路
- 第一版不引入 PostgreSQL / Redis / Kubernetes
