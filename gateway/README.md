# Gateway — ROS2 ⇄ MQTT/ZMQ 桥接层

作用：连接 `ros2_car` 机器人（ROS2 话题）与云端消息总线（MQTT/ZMQ），
既是 **上行**（机器人状态 → 云端）桥接，也是 **下行**（云端指令 → 机器人）转发。

## 数据流

**上行（机器人状态 → 云端）：**

```
ROS2 topics (sdc/speed, sdc/action_id, sdc/front_distance, ...)
      ↓ 订阅
gateway 将消息转换为统一 JSON
      ↓ 发布
MQTT topic: robot/{robot_id}/sdc/speed
ZMQ PUB :   tcp://*:5555
```

**下行（云端指令 → 机器人）：**

```
MQTT topic: robot/{robot_id}/command/control_algo
ZMQ REP :   tcp://*:5556
      ↓ 订阅 / 接收
gateway 解析指令并转换为 ROS2 消息
      ↓ 发布
ROS2 topics (sdc/control_algo, sdc/pause, sdc/clear_trail)
```

可在机器人侧（宿主机或同网段容器）运行，也可作为 sidecar 部署。

## 文件说明

| 文件 | 作用 |
|------|------|
| `ros2_bridge.py` | 主桥接程序（上行订阅 + 下行转发）|
| `mqtt_simulator.py` | 无真实 ROS2 环境时，向总线发送模拟上行数据 |
| `mock_robot.py` | 无真实机器人时，订阅 command 验证下行链路 |

## 运行

真实 ROS2 环境（需 `source /opt/ros/humble/setup.bash`）：

```bash
python3 ros2_bridge.py --robot-id car01 \
    --mqtt-broker localhost --mqtt-port 1884 --zmq-port 5555
```

参数：

| 参数 | 默认 | 说明 |
|------|------|------|
| `--robot-id` | car01 | 机器人 ID |
| `--mqtt-broker` | localhost | MQTT broker 地址 |
| `--mqtt-port` | 1884 | MQTT 端口 |
| `--zmq-port` | 5555 | ZMQ 上行 PUB 端口（下行 REP 为 +1）|

## 下行指令映射

| command 主题 | ROS2 话题 | 类型 | 说明 |
|------|------|------|------|
| `robot/{id}/command/control_algo` | `sdc/control_algo` | Int32 | 切换控制算法 |
| `robot/{id}/command/pause` | `sdc/pause` | Bool | 暂停/继续 |
| `robot/{id}/command/clear_trail` | `sdc/clear_trail` | Bool | 清除轨迹 |
