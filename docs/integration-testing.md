# 车云联调手册

本文覆盖两种链路：不依赖 ROS2 的完整 Mock 验收，以及连接真实 `ros2_car` 的车云联调。

## 0. 前置条件

- Linux 和 Docker Compose v2
- 端口 `1884`、`8000` 未被其他服务占用
- 实车模式额外要求已构建 `ros2_car`
- ROS2 车端和 Gateway 使用相同 `ROS_DOMAIN_ID`

任何模式开始前都可以清理旧服务：

```bash
cd /home/ubuntu/dev/frank_ws/robot_platform
./scripts/run_all.sh stop
```

## 1. Cloud + Mock Vehicle

```bash
cd /home/ubuntu/dev/frank_ws/robot_platform
./scripts/run_all.sh mock
python3 scripts/verify_e2e.py
```

期望输出：

```text
PASS backend health
PASS telemetry and heartbeat
PASS command ACK
E2E PASS: Web/API → Backend → MQTT → Vehicle → ACK → Backend
```

浏览器打开 `http://localhost:8000/dashboard`，应看到车辆沿圆形轨迹移动。

可手工检查 Registry：

```bash
curl http://localhost:8000/api/v1/robots
curl http://localhost:8000/api/v1/robots/car01
```

## 2. Cloud + ros2_car

终端 A 启动车端：

```bash
cd /home/ubuntu/dev/frank_ws/ros2_car
source /opt/ros/jazzy/setup.bash
source install/setup.bash
export ROS_DOMAIN_ID=0
ros2 launch self_driving_car_demo ring_road.launch.py
```

终端 B 启动云端和 Gateway：

```bash
cd /home/ubuntu/dev/frank_ws/robot_platform
ROS_DOMAIN_ID=0 ./scripts/run_all.sh ros2
```

`ros2` 模式会停止 Simulator 和 Mock Robot，防止假 Telemetry/ACK 混入 `car01`。

## 3. 逐层验收

### ROS2 层

在终端 A 检查：

```bash
ros2 topic hz /sdc/odometry
ros2 topic echo /sdc/odometry --once
ros2 topic info /sdc/pause --verbose
```

应看到 Odometry 持续发布，并且 `sdc/pause` 存在 Gateway publisher。

### Gateway 和 MQTT 层

```bash
cd /home/ubuntu/dev/frank_ws/robot_platform
docker compose -f docker/docker-compose.yml --profile real logs -f gateway-real
```

日志应出现 MQTT 连接、ROS2 bridge topics 和 command subscription，不应持续重启。

### Cloud 状态层

```bash
curl http://localhost:8000/api/v1/robots/car01
```

确认：

- `connection.state` 为 `ONLINE`
- `connection.last_seen` 持续更新
- `telemetry.sdc/odometry` 存在
- `observed.pose` 随车辆运动变化
- `trail` 持续增加

### 下行控制和 ACK

暂停：

```bash
curl -X POST http://localhost:8000/api/v1/robots/car01/commands \
  -H 'Content-Type: application/json' \
  -d '{"action":"set_paused","value":true}'
```

响应中的 `command_id` 用于查询：

```bash
curl http://localhost:8000/api/v1/robots/car01/commands/<command_id>
```

期望最终状态为 `SUCCEEDED`，同时 RViz 中车辆停止。恢复：

```bash
curl -X POST http://localhost:8000/api/v1/robots/car01/commands \
  -H 'Content-Type: application/json' \
  -d '{"action":"set_paused","value":false}'
```

## 4. 离线检测

停止 Gateway：

```bash
docker compose -f docker/docker-compose.yml --profile real stop gateway-real
```

等待 10 秒以上，再查询机器人。`connection.state` 应变为 `OFFLINE`。重新执行 `./scripts/run_all.sh ros2` 后应恢复为 `ONLINE`。

## 5. 常见问题

- Dashboard 出现模拟圆形轨迹：旧 Simulator 仍在运行，重新执行 `./scripts/run_all.sh ros2`。
- Robot 一直 OFFLINE：检查两侧 `ROS_DOMAIN_ID`、Gateway 日志和 MQTT broker 状态。
- Gateway 报 `No module named robot_contracts`：说明运行的是旧容器配置；执行 `docker compose -f docker/docker-compose.yml --profile real up -d --force-recreate gateway-real`。
- Gateway 看不到 ROS topic：容器必须使用 host network；同时检查主机防火墙和 DDS/RMW 配置。
- 命令保持 `PUBLISHED` 后变为 `TIMEOUT`：Gateway 未收到命令或 ACK 未返回。
- 命令返回 `EXPIRED`：消息到达 Gateway 前已超过有效时间，检查网络和系统时钟。
- Humble Gateway 与 Jazzy 车端发现异常：优先在宿主机 Jazzy 环境直接运行 Gateway，以消除跨发行版/DDS 实现差异。
