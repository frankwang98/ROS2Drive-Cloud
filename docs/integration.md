# Cloud 整合说明

保留 main 的场景控制台与 local-cloud 的后端/Gateway，并通过合并提交保留双方历史。

## 数据流

浏览器 → HTTP 后端 → MQTT → Gateway → ROS2Drive。页面每秒读取 `/api/v2/robots/{id}/snapshot`，运行状态取自车端 RuntimeStatus，位置与速度取自 Odometry，超过 5 秒显示过期/隐藏位置。页面不会把“请求已发布”当作“车端执行成功”。

新增任务 API：POST `missions`、GET `missions/{mission_id}`、POST `missions/{mission_id}/cancel`、POST `emergency-stop`，均位于上述 robots 路径下。

任务命令使用 `mission_command`，取消使用 `mission_cancel`；反馈与结果带 mission_id，驱动任务状态。命令先登记再发布，避免快速 ACK 被 PUBLISHED 覆盖；终态不被迟到 ACK 回退。Gateway 验证超时及车辆 ID，重复请求保留首次回执，MQTT 重连重订阅。

消息增加可选 session_id；同一 session 内忽略旧序号，进程重启可接受新 session。旧消息缺少 session_id 仍兼容。序号缓存与幂等缓存是进程内状态，重启不会提供持久化去重保证。

软件急停只代表经 Gateway 发布请求。清除急停后仍需根据车端 recovery_ready 执行 acknowledge_recovery；网页按钮不是硬件急停。

## 发布与联调

Cloud Pages 独立上传 site；Python CI 验证后端、Gateway 测试与契约。Docker Gateway 固定 Jazzy 和 ROS2Drive 接口提交，允许通过 ROS2DRIVE_REF 构建参数升级，升级需核对协议兼容。

尚需实际环境验证：构建 Gateway 镜像；启动 ROS2Drive；确认命名空间；下发短路线；核对接受/反馈/结果；暂停、取消；MQTT 断线重连；急停清除与安全恢复。回归测试中的 ROS 是桩对象，不能代替实车联调。
