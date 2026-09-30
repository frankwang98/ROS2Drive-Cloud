# 消息协议

> 本文是旧版逐 topic 协议存档。当前实现请参阅 [车云消息协议 v1](protocol-v1.md)。

本文档定义 Robot Cloud Platform 各层之间的消息格式。

## 统一消息模型

所有从 ROS2 转发到云端的数据都使用如下 JSON：

```json
{
  "robot_id": "car01",
  "topic": "sdc/speed",
  "type": "Float64",
  "mode": "simulation",   // 或 real
  "data": 2.4,
  "ts": 1690000000
}
```

| 字段 | 说明 |
|------|------|
| `robot_id` | 机器人唯一标识 |
| `topic` | 对应的 ROS2 话题名（或模拟话题名）|
| `type` | 消息类型（ROS2 类型或 `simulated`）|
| `mode` | 数据来源：`simulation`（仿真）/ `real`（实车）|
| `data` | 载荷值（JSON 可序列化）|
| `ts` | 时间戳（Unix 秒，可选）|

## 数据话题（显示控制）

来自 `ros2_car` 的实时状态：

| 话题 | 类型 | 说明 |
|------|------|------|
| `sdc/speed` | Float64 | 实时速度 (m/s) |
| `sdc/action_id` | Float64 | 行为：0加速/1巡航/2减速/3停车 |
| `sdc/front_distance` | Float64 | 前方障碍物距离 (m) |
| `sdc/obstacle_count` | Float64 | 当前障碍物数量 |
| `simulation/markers` | MarkerArray | 道路/环境可视化（含 marker_count）|
| `sensor/lidar` | PointCloud2 | LIDAR 点云元信息（宽高/步长）|
| `sdc/odometry` | Odometry | 完整位姿与线/角速度；Gateway 转为 `{pose, velocity}` |

## 控制指令话题

云端 → 机器人方向的指令（由 gateway 消费并转成 ROS2 发布）：

| 指令 | command 主题 | 机器人侧 ROS2 话题 | 类型 | 说明 |
|------|------|------|------|------|
| `set_control_algo` | `robot/{id}/command/control_algo` | `sdc/control_algo` | Int32 | 切换控制算法 (0/1/2) |
| `set_paused` | `robot/{id}/command/pause` | `sdc/pause` | Bool | 明确设置暂停状态 |
| `clear_trail` | `robot/{id}/command/clear_trail` | `sdc/clear_trail` | Bool | 清除行驶轨迹 |

### 下行指令消息格式

由 Backend `/api/control` 发布到总线的 JSON：

```json
{
  "robot_id": "car01",
  "topic": "robot/car01/command/control_algo",
  "action": "control_algo",
  "value": 1
}
```

- 简单触发型指令（如 `clear_trail`）可省略 `value`，gateway 默认按 `True` 处理。
- gateway 支持统一消息模型（`topic` + `data`）与扁平指令（`action` + `value`）两种解析。

## 传输通道

| 通道 | 用途 | 主题格式 |
|------|------|----------|
| MQTT | 默认且唯一的车云数据面 | `robot/{robot_id}/{topic}` |
| ZMQ  | 实验性兼容通道，默认关闭 | 使用 `--enable-zmq` / `ENABLE_ZMQ=true` 显式启用 |

## WebSocket 推送协议

Backend → Web Dashboard：

```json
// 连接后立即推送当前快照
{"type": "snapshot", "data": { "connected": true, "topics": {...} }}

// 实时增量更新
{"type": "update", "topic": "sdc/speed", "data": 2.4}
```

