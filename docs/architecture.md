# 架构设计

## 总览

Robot Cloud Platform 是一个"机器人 + 云原生"平台，核心目标是将 ROS2 机器人
（如 `ros2_car`）的显示控制能力通过云原生技术栈上云，提供统一的 Web Dashboard。

## 分层架构

```
┌────────────────────────────────────────────┐
│             Web Dashboard (前端)            │
│        实时状态 · 远程控制 · 消息监控        │
└────────────────────┬───────────────────────┘
                     │ WebSocket / REST
┌────────────────────▼───────────────────────┐
│      Backend (FastAPI, Python)             │
│   REST API · WebSocket · 状态管理 · 鉴权    │
└────────────────────┬───────────────────────┘
                     │ MQTT
┌────────────────────▼───────────────────────┐
│      Gateway (ROS2 ⇄ 消息总线, Python)     │
│   ROS2 topics → 统一 JSON → MQTT            │
└────────────────────┬───────────────────────┘
                     │ ROS2 topics
┌────────────────────▼───────────────────────┐
│      ROS2 机器人 (ros2_car)                │
│   感知 → 决策 → 控制 → RViz 可视化         │
└────────────────────────────────────────────┘
```

## 关键设计

### 1. 消息桥接层（Gateway）
- 运行于机器人侧或与机器人同网段
- 订阅 ros2_car 的 ROS2 话题
- 转换为统一 JSON 模型（`{robot_id, topic, type, data}`）
- MQTT 是唯一默认车云数据面；ZMQ 仅作为显式开启的实验兼容通道

### 2. 后端状态管理（Backend）
- `RobotStateStore`：线程安全地缓存每个话题最新值
- 同时订阅 MQTT 和 ZMQ，保证多通道兼容
- 通过 WebSocket 将更新实时广播给 Web Dashboard

### 3. 云原生弹性（Kubernetes）
- Backend 多副本 + HPA 自动扩缩容
- MQTT Broker 独立部署
- Ingress 统一对外入口

### 4. 前端显示控制（Web Dashboard）
- 实时展示速度、行为、前方距离、障碍物数量
- 远程切换控制算法（PID / Bang-Bang / Ramp）
- 暂停/继续仿真、清除轨迹

## 可观测性扩展（规划）
- Prometheus 指标暴露（backend `/metrics`）
- 集中日志（Loki / EFK）
- 链路追踪（Jaeger / OpenTelemetry）
