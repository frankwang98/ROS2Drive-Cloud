# 架构设计

## 总览

ROS2Drive Cloud 是 [`ros2_car`](../ros2_car)（运行时层为 **ROS2Drive**）的云端控制面。
核心目标不是「把 ROS topic 搬到网页上」，而是提供一个能完成 *任务下发 / 车队管理 /
状态可视化 / 远程运维* 的车云协同平台。Web Dashboard 只是用户入口之一。

## 分层架构

```
┌──────────────────────────────────────────────────────────────┐
│                  Web Dashboard (前端)                        │
│        Map · Vehicle · Mission · Alarm · Telemetry           │
└────────────────────────┬─────────────────────────────────────┘
                         │ REST / WebSocket
┌────────────────────────▼─────────────────────────────────────┐
│            Backend (FastAPI, Python)                         │
│   Vehicles · Missions · Telemetry · Runtime · Events         │
└────────────────────────┬─────────────────────────────────────┘
                         │ MQTT (v2 envelope)
┌────────────────────────▼─────────────────────────────────────┐
│    Edge Gateway (this repo, gateway/)                        │
│                                                              │
│    ROS 2 typed topics / Action  ⇄  MQTT v2 envelope          │
│    - runtime/status, runtime/faults, runtime/metrics         │
│    - control/command, planning/trajectory                    │
│    - mission/execute (action)  + emergency_stop              │
│    - 兼容 legacy sdc/* scalars                               │
└────────────────────────┬─────────────────────────────────────┘
                         │ ROS 2 typed interfaces
┌────────────────────────▼─────────────────────────────────────┐
│                          ROS2Drive                           │
│                                                              │
│  MissionManager → BehaviorManager → Planner →                │
│  VelocityPlanner → Controller → SafetyManager                │
│                                                              │
│  VehicleInterface (SimulatedVehicle / CAN Adapter)           │
└──────────────────────────────────────────────────────────────┘
```

## 关键设计

### 1. Gateway：typed 接口的唯一翻译层

> **Cloud 不直接理解 ROS 2 topic。** Gateway 是车云之间的唯一翻译层。

- 订阅 ROS2Drive 的 typed topic（`runtime/status`、`runtime/faults`、
  `runtime/metrics`、`control/command`、`planning/trajectory`），转成 v2 envelope 推到
  MQTT。
- 作为 `mission/execute` Action 的 client，把 Cloud 下发的 Mission 包成 Action goal
  发给 ROS2Drive；把 feedback / result 重新打包成 `mission_feedback` /
  `mission_result` envelope 回推 MQTT。
- 下行 `emergency_stop` 直接转成 ROS 2 `sdc/emergency_stop`（Bool）发布。
- **legacy 兼容**：旧的 `sdc/speed` / `sdc/odometry` / `sdc/control_algo` / `sdc/pause` /
  `sdc/clear_trail` 继续按 v1 envelope 上报，等 Backend 完成 v2 升级后再退役。

详细协议字段见 [`protocol-v2.md`](protocol-v2.md)；ROS 2 接口契约见
[`../ros2_car/docs/interfaces.md`](../ros2_car/docs/interfaces.md)。

### 2. Backend 状态管理

- 按 `robot_id` 隔离状态，进程内缓存 typed payload（v2 envelope）+ legacy scalars（v1
  envelope）。
- 通过 WebSocket 推送增量到 Web Dashboard，前端按 type 路由到对应组件（地图 / 卡片 /
  Mission 面板 / Fault 列表）。
- v2 envelope 要求 `schema_version=2.0`，v1 envelope 在 v2 协议下**拒绝解码**——升级
  时必须同步升级 Backend。

### 3. 部署

- 第一版目标：**Docker Compose 一键启动** Cloud 侧（MQTT broker + Backend + 静态
  Dashboard）。Gateway 与 ROS2Drive 留在本地三终端联调。
- 不引入 Kubernetes / PostgreSQL / Redis。等数据闭环与多车需求出现后再按需添加。

### 4. 前端（Web Dashboard）

- 实时车辆卡片：online / pose / speed / battery / driving_mode / autonomy_state
- 地图：每辆车一个 marker + 实时轨迹
- Mission 面板：v2 mission lifecycle（创建 / 监控 progress / 取消）
- 告警：按 `Fault.severity` 分级展示
- Runtime 状态：显示 `runtime_state` / `mission_state` / `recovery_required`

## 暂时不做（明确边界）

- 不让 Cloud 越权设置 planner / controller 作为正式任务接口——只有 Mission 是正式入口
- 不用软件 Safety 替代底盘硬件安全链路
- 不引入 Kafka / Service Mesh / 车端微服务化
- 第一版不引入 PostgreSQL / Redis / Kubernetes