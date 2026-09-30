# 车云消息协议 v2

> v1 → v2 是 **破坏性升级**：`schema_version` 字段从 `"1.0"` 改为 `"2.0"`,
> `MessageType` 枚举扩展 9 个 typed 类型。Backend 解码 v2 envelope 必须升级
> `robot_contracts` 包。

v2 的目标：把 ROS2Drive（`ros2_car`）的 **typed ROS 2 接口** 一对一映射到 MQTT
envelope，让 Cloud 看到的是 *Runtime / Control / Trajectory / Mission*，而不是
*ROS topic*。

唯一代码定义位于 `robot_contracts/`。ROS 2 用于车内通信，MQTT 是唯一默认车云数据面。

## Envelope（v2）

```json
{
  "schema_version": "2.0",
  "message_id": "uuid",
  "robot_id": "car01",
  "timestamp": 1788832800.0,
  "sequence": 123,
  "type": "runtime_status",
  "payload": { ... }
}
```

字段含义：

| 字段 | 含义 |
|---|---|
| `schema_version` | 固定 `"2.0"`，与 v1 不兼容 |
| `message_id` | 幂等键（Mission / Command 共用）|
| `robot_id` | 与 ROS 2 `robot_namespace` 对齐，但不等价 |
| `timestamp` | Gateway 入队时间（Unix 秒）|
| `sequence` | Gateway 内单调递增计数器（topic 内单调）|
| `type` | 必须是 `MessageType` 枚举值之一 |
| `payload` | JSON object，shape 由 type 决定 |

## MessageType 枚举

| 值 | 方向 | MQTT topic | payload 类型 |
|---|---|---|---|
| `telemetry` | V→C | `robots/{id}/telemetry` | legacy scalar / odom 兼容 |
| `event` | V→C | `robots/{id}/events` | (保留 v1，结构未变) |
| `command` | C→V | `robots/{id}/commands` | legacy action/value 兼容 |
| `command_ack` | V→C | `robots/{id}/command_ack` | (保留 v1，结构未变) |
| `heartbeat` | V→C | `robots/{id}/heartbeat` | `{}` |
| **`runtime_status`** | V→C | `robots/{id}/runtime/status` | `RuntimeStatusPayload` |
| **`fault`** | V→C | `robots/{id}/runtime/faults` | `FaultArrayPayload` |
| **`metrics`** | V→C | `robots/{id}/runtime/metrics` | `RuntimeMetricsPayload` |
| **`control`** | V→C | `robots/{id}/control/command` | `ControlCommandPayload` |
| **`trajectory`** | V→C | `robots/{id}/planning/trajectory` | `TrajectoryPayload` |
| **`mission_command`** | C→V | `robots/{id}/missions/command` | `MissionCommandPayload` |
| **`mission_feedback`** | V→C | `robots/{id}/missions/feedback` | `MissionFeedbackPayload` |
| **`mission_result`** | V→C | `robots/{id}/missions/result` | `MissionResultPayload` |
| **`emergency_stop`** | C→V | `robots/{id}/emergency_stop` | `{ "value": true \| false }` |

加粗项是 v2 新增；其余为 v1 兼容保留。

## Typed payload shape（新增）

### RuntimeStatusPayload → `runtime_status`

| 字段 | ROS 2 字段 | 类型 |
|---|---|---|
| `runtime_state` | `runtime_state` | string |
| `mission_id` | `mission_id` | string |
| `mission_type` | `mission_type` | string |
| `mission_state` | `mission_state` | string |
| `mission_progress` | `mission_progress` | float [0, 1] |
| `result_reason` | `result_reason` | string |
| `localized` | `localized` | bool |
| `healthy` | `healthy` | bool |
| `recovery_required` | `recovery_required` | bool |
| `recovery_ready` | `recovery_ready` | bool |

### FaultArrayPayload → `fault`

```json
{
  "faults": [
    { "code": "LOCA_TIMEOUT", "severity": 2, "message": "loc lost", "active": true }
  ]
}
```

`severity`：`0=INFO`、`1=WARNING`、`2=ERROR`、`3=FATAL`。

### RuntimeMetricsPayload → `metrics`

| 字段 | 含义 |
|---|---|
| `loop_duration_ms` | 主循环耗时 |
| `configured_loop_hz` | 配置频率 |
| `trajectory_points` | 当前 trajectory 长度 |
| `active_faults` | active fault 数量 |
| `runtime_state` | int 枚举（见 RuntimeStatus） |

### ControlCommandPayload → `control`

| 字段 | 含义 |
|---|---|
| `target_speed` | 目标速度 (m/s) |
| `steering_angle` | 目标转角 (rad) |
| `brake` | 制动 [0, 1] |
| `emergency_stop` | 软件 ESTOP 锁存 |

### TrajectoryPayload → `trajectory`

```json
{
  "mission_id": "m-001",
  "valid": true,
  "points": [
    {
      "pose": { "x": 1.0, "y": 2.0, "theta": 0.5 },
      "curvature": 0.1,
      "velocity": 1.5,
      "acceleration": 0.0,
      "relative_time": 0.5,
      "stop_required": false
    }
  ]
}
```

### MissionCommandPayload → `mission_command`

```json
{
  "mission_id": "m-002",
  "mission_type": 1,
  "mission_type_name": "FOLLOW_ROUTE",
  "route": [{ "x": 1.0, "y": 2.0, "theta": 0.5 }],
  "speed_limit": 1.5,
  "goal_tolerance": 0.3,
  "timeout_s": 60.0,
  "allow_preempt": false
}
```

`mission_type` enum：`0=NAVIGATE_TO`、`1=FOLLOW_ROUTE`、`2=STOP`、`3=PARK`、`4=DOCK`、`5=RETURN_HOME`。
`mission_type_name` 由 Gateway 写入，便于 Cloud 端直接显示。

### MissionFeedbackPayload → `mission_feedback`

```json
{ "state": "EXECUTING", "progress": 0.42, "reason": "" }
```

### MissionResultPayload → `mission_result`

```json
{ "success": true, "final_state": "ARRIVED", "reason": "goal reached" }
```

## MQTT topic 速查

| Topic | 方向 | type |
|---|---|---|
| `robots/{id}/telemetry` | V→C | `telemetry`（legacy 兼容）|
| `robots/{id}/events` | V→C | `event`（保留）|
| `robots/{id}/heartbeat` | V→C | `heartbeat` |
| `robots/{id}/runtime/status` | V→C | `runtime_status` |
| `robots/{id}/runtime/faults` | V→C | `fault` |
| `robots/{id}/runtime/metrics` | V→C | `metrics` |
| `robots/{id}/control/command` | V→C | `control` |
| `robots/{id}/planning/trajectory` | V→C | `trajectory` |
| `robots/{id}/missions/command` | C→V | `mission_command` |
| `robots/{id}/missions/feedback` | V→C | `mission_feedback` |
| `robots/{id}/missions/result` | V→C | `mission_result` |
| `robots/{id}/emergency_stop` | C→V | `emergency_stop` |
| `robots/{id}/commands` | C→V | `command`（legacy 兼容）|
| `robots/{id}/command_ack` | V→C | `command_ack` |

## 兼容与迁移

- v1 envelope（`schema_version=1.0`）被 v2 parser **拒绝**——必须先升级 Backend。
- v2 typed topics 上线后，**老的 `telemetry` topic 仍然保留**，作为 sdc/* legacy scalars
  的兼容出口。第一版 gateway 同时发 typed topics + legacy telemetry。
- `events` / `command_ack` / `heartbeat` / `commands` 结构在 v2 中保持与 v1 一致，不破坏
  现有 Backend 解析。

## 实现引用

- Python 端定义：`robot_contracts/` 包（`envelope`、`MessageType`、typed payloads）
- Gateway 桥接：`gateway/ros2_bridge.py`（typed subscription + mission action client + emergency_stop）
- ROS 2 接口契约：`../ros2_car/docs/interfaces.md`
- ROS 2 msg 定义：`../ros2_car/msg/*.msg`