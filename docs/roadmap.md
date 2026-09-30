# All-in-One Autonomous Driving Platform Roadmap

目标：将 `ros2_car` 与 `robot_platform` 建设为可教学、可演示、可扩展的车云一体参考实现。

## Milestone 1 — Correctness

- [x] 将暂停命令改为明确的 `set_paused(bool)` 语义
- [x] ROS2 发布 `nav_msgs/Odometry`，Gateway 输出完整车辆状态
- [x] MQTT 成为默认且唯一的车云数据面，ZMQ 仅保留为显式实验选项
- [x] Backend 状态按 `robot_id` 隔离
- [x] MQTT topic 收敛为 telemetry/events/commands/command_ack/heartbeat
- [x] Command ACK、状态机、超时和幂等基础链路
- [x] Heartbeat、last_seen 和离线判定
- [x] 正确性阶段 Kubernetes Backend 固定为单副本

## Milestone 2 — Architecture

- [x] 建立 `robot_contracts` 与版本化 Envelope
- [ ] 建立无 ROS 依赖的 domain 层
- [ ] 建立统一 `VehicleRuntime`
- [ ] 拆分 `RingRoadSimNode`（ROS wiring 控制在 100–200 行）
- [ ] 拆分 Gateway 的 ROS、MQTT、telemetry、command 模块
- [ ] 建立 `MissionManager`
- [ ] 统一 `VehicleState`、`Trajectory` 和 planner/controller 接口
- [ ] 参数 YAML 化并增加校验

## Milestone 3 — Platform

- [ ] Robot Registry 与 desired/reported/observed 状态
- [ ] Mission、Command、Event、Telemetry 服务/API
- [ ] Redis 快照和云内事件流
- [ ] Backend 无状态化并恢复多副本
- [ ] 多机器人 E2E
- [ ] Fleet / Robot / Map / Mission / Debug 页面

## Milestone 4 — Engineering

- [ ] Unit / Contract / Integration / ROS / E2E 测试体系
- [ ] Structured logging、metrics、health、tracing
- [ ] 格式化、静态检查、测试、镜像和 E2E CI
- [x] Docker Compose 一键验收环境（mock 链路已验证，真实 ROS2 待人工验收）

## Milestone 5 — Teaching

- [ ] 架构、协议、时序和代码导读文档
- [ ] Normal、Obstacle、Planning Failure、Network Loss、Retry、Restart、Multi-Robot、E-Stop 场景
- [ ] 故障注入与 Replay
- [ ] 教程、截图和演示视频

## 当前验收原则

每项必须同时具备：明确契约、实现、自动化测试和文档；不以“代码已写但链路未验证”作为完成。

