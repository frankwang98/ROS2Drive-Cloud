# robot_contracts

车云链路唯一协议定义。Backend、Gateway 和模拟工具必须从本包构造及校验消息，禁止自行维护 Envelope 字段。

当前协议版本为 `1.0`，包含 telemetry、event、command、command_ack 和 heartbeat。
