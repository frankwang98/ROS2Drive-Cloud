# 实车模式 · 接入本地 ROS2 实时数据

本文档说明如何将平台切换为 **实车模式（real）**，接入本地 `ros2_car` 的 ROS2 实时数据，
并在 Web Dashboard 上实时展示车辆位姿、朝向与轨迹。

## 两种模式速览

| 模式 | 数据源 | 适用场景 |
|------|--------|----------|
| **simulation（仿真，默认）** | `gateway/mqtt_simulator.py` | 无真实机器人时开发/演示，生成模拟数据并驱动地图 |
| **real（实车）** | `gateway/ros2_bridge.py` | 接入本地 ROS2，读取 `ros2_car` 实时话题并上云 |

切换入口：
- **Web Dashboard**：右上角「仿真模式 / 实车模式」按钮
- **REST**：`GET /api/mode` 查询、`POST /api/mode` 切换
- **环境变量**：后端启动时 `ROBOT_MODE=real`（默认 `simulation`）

## 接入步骤

推荐直接使用项目提供的一键入口：

```bash
# ros2_car 已在宿主机运行，且两侧 ROS_DOMAIN_ID 一致
ROS_DOMAIN_ID=0 ./scripts/run_all.sh ros2
```

该命令启动 MQTT、Backend 和使用 host network 的 Gateway。Dashboard 位于 `http://localhost:8000/dashboard`。

### 1. 启动后端（实车模式）

```bash
cd backend
pip install -r requirements.txt
ROBOT_MODE=real uvicorn app.main:app --host 0.0.0.0 --port 8000
```

### 2. 启动 ROS2 Gateway 桥接（机器人侧）

确保已 `source` ROS2 环境，并已运行 `ros2_car`：

```bash
source /opt/ros/humble/setup.bash
cd robot_platform
pip install ./robot_contracts -r gateway/requirements.txt
python3 gateway/ros2_bridge.py --robot-id car01 \
    --mqtt-broker <backend-host> --mqtt-port 1884 --zmq-port 5555
```

- `ros2_bridge.py` 订阅 `sdc/speed`、`sdc/action_id`、`sdc/front_distance`、`sdc/obstacle_count`、
  `sdc/odometry`、`simulation/markers`、`sensor/lidar` 等话题，转换为 Envelope v1 后经 MQTT 推送到 Backend。
- 同时订阅云端 `robots/{id}/commands`，转发为 ROS2 下行话题，并在 `command_ack` 返回执行结果。

> 当前标准接口是 `sdc/odometry`（`nav_msgs/Odometry`）。旧的拆分坐标字段只作为 Backend 兼容读取，不应再由新车端发布。

### 3. 打开 Dashboard

浏览器访问 `http://<backend-host>:8000/dashboard`，右上角切换到「实车模式」，
地图面板将实时显示车辆位置（蓝色圆点）、朝向箭头与行驶轨迹。

## 位姿数据

实车模式下，以下话题驱动地图可视化：

| 话题 | 类型 | 含义 |
|------|------|------|
| `sdc/odometry` | nav_msgs/Odometry | 位姿、线速度与角速度 |

Backend 从 Odometry 原子更新位姿，并自动累积轨迹（最多 500 点），供地图绘制与「清除轨迹」使用。

## 注意事项

- 实车模式仅标识数据来源，需自行保证 `ros2_car` 与 `ros2_bridge.py` 运行在同一网络（可 bridge 到 MQTT broker）。
- 无真实机器人时请切回 **仿真模式**（`POST /api/mode {"mode":"simulation"}`），由模拟器驱动数据。
