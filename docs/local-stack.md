# 本地车云系统：启动与能力

## 进程边界

默认系统固定为四个组件：

| 组件 | 运行位置 | 职责 |
|---|---|---|
| `ros2_car` | 本地 | 自动驾驶闭环、车辆模型、ROS2、RViz |
| Python Gateway | 本地 | ROS2/MQTT 转换、Heartbeat、Command ACK |
| MQTT Broker | Docker | 唯一车云消息通道 |
| Backend + Frontend | Docker | Registry、API、WebSocket、Dashboard |

Docker 默认只运行两个容器。Frontend 是 Backend 内的静态资源，不单独启动容器。

## 首次准备

```bash
cd /home/ubuntu/dev/frank_ws/robot_platform
chmod +x scripts/*.sh
./scripts/setup_gateway_local.sh
```

Gateway 虚拟环境使用 `--system-site-packages`，以便访问本机 ROS2 Jazzy 的 `rclpy`。

## 启动

终端 1：

```bash
cd /home/ubuntu/dev/frank_ws/robot_platform
./scripts/run_cloud.sh
```

终端 2：

```bash
cd /home/ubuntu/dev/frank_ws/robot_platform
ROS_DOMAIN_ID=0 ./scripts/run_car_local.sh
```

终端 3：

```bash
cd /home/ubuntu/dev/frank_ws/robot_platform
ROS_DOMAIN_ID=0 ./scripts/run_gateway_local.sh
```

启动后访问：

- Dashboard：`http://localhost:8000/dashboard/`
- Backend API 文档：`http://localhost:8000/docs`
- MQTT：`localhost:1884`

## 当前能做什么

### 车端

- 在 RViz 展示环形道路、小车、规划轨迹和障碍物。
- 自动驾驶模式沿环形道路行驶和局部避障。
- PID/Bang-Bang/Ramp 速度控制切换。
- Lattice/EM 规划切换。
- Stanley/LQR/MPC 横向控制切换。
- 自动/手动模式、暂停、重置和清除轨迹。

### 车云链路

- Gateway 将速度、行为、前方距离、障碍数量和 Odometry 上传到 MQTT。
- Gateway 每两秒发送 Heartbeat。
- Backend 按 `robot_id` 保存连接状态、Telemetry、位姿和轨迹。
- Dashboard 通过 WebSocket 实时显示车辆状态和地图轨迹。
- Web/API 可以下发暂停、速度控制算法切换和清除轨迹。
- 每条 Command 有唯一 ID、过期时间、去重和 ACK 状态。

当前不会上传 RViz Marker 或原始 PointCloud2；这些大消息只在车内使用。

## 快速确认链路

```bash
curl http://localhost:8000/api/v1/robots/car01
```

正常结果应包含：

```text
connection.state = ONLINE
telemetry.sdc/odometry
observed.pose
trail
```

暂停车辆：

```bash
curl -X POST http://localhost:8000/api/v1/robots/car01/commands \
  -H 'Content-Type: application/json' \
  -d '{"action":"set_paused","value":true}'
```

恢复车辆：

```bash
curl -X POST http://localhost:8000/api/v1/robots/car01/commands \
  -H 'Content-Type: application/json' \
  -d '{"action":"set_paused","value":false}'
```

## 停止

本地 Gateway 和 `ros2_car` 分别按 `Ctrl+C`。停止云端：

```bash
docker compose -f docker/docker-compose.yml down
```

## 故障定位顺序

1. `ros2 topic hz /sdc/odometry`：确认车端输出。
2. 查看 Gateway 终端：确认 MQTT 连接和 ROS2 subscriptions。
3. `curl /api/v1/robots/car01`：确认 Heartbeat 和 Telemetry。
4. 查看 `docker compose logs backend mqtt-broker`。

如果 `connection.state=ONLINE` 但没有 Odometry，是 ROS2 topic/discovery 问题；如果始终 `OFFLINE`，是 Gateway 未运行或 MQTT 未连接。
