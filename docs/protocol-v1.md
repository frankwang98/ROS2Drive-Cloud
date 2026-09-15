# 车云消息协议 v1

唯一代码定义位于 `robot_contracts/`。ROS2 用于车内通信，MQTT 是唯一默认车云数据面。

```json
{
  "schema_version": "1.0",
  "message_id": "uuid",
  "robot_id": "car01",
  "timestamp": 1788832800.0,
  "sequence": 123,
  "type": "telemetry",
  "payload": {}
}
```

| MQTT topic | 方向 | type |
|---|---|---|
| `robots/{robot_id}/telemetry` | Vehicle → Cloud | telemetry |
| `robots/{robot_id}/events` | Vehicle → Cloud | event |
| `robots/{robot_id}/commands` | Cloud → Vehicle | command |
| `robots/{robot_id}/command_ack` | Vehicle → Cloud | command_ack |
| `robots/{robot_id}/heartbeat` | Vehicle → Cloud | heartbeat |

Telemetry payload 为 `{name, ros_type, value}`。`sdc/odometry` 的 value 包含完整 `pose + velocity`。

Command 由 `message_id` 幂等标识。ACK 状态包括 `CREATED`、`PUBLISHED`、`ACCEPTED`、`EXECUTING`、`SUCCEEDED`、`REJECTED`、`FAILED`、`TIMEOUT`、`EXPIRED`。当前 Gateway 在 ROS publish 后返回 `SUCCEEDED`，VehicleRuntime 接入后再补齐执行中状态。

ZMQ 默认关闭，不属于 v1 正式数据面。
