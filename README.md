# ROS2Drive Cloud

ROS2Drive 的网页控制台与车云网关。默认打开四种场景演示，也可连接已有后端读取车端状态、下发 FollowRoute 任务、暂停、取消和请求软件急停。

## 先看网页

[打开控制台](https://frankwang98.github.io/ROS2Drive-Cloud/)。无需本地 Docker；默认操作仅作用于模拟车辆。

`site/` 是当前前端，`main` 更新由本仓库 `.github/workflows/pages.yml` 独立发布。个人主页仓库不再同步代码。GitHub Pages 仅托管静态前端，不运行 Python、MQTT 或 ROS。

## 连接 ROS2Drive

1. 在可访问车端的主机启动 MQTT 和后端：`bash scripts/run_cloud.sh`。
2. 构建并 source ROS2Drive 工作空间；设置 `ROS_WORKSPACE_SETUP=/your/workspace/install/setup.bash`，运行 `bash scripts/run_gateway_local.sh`。通过 `ROBOT_ID`、`ROBOT_NAMESPACE` 指定车与 ROS 命名空间。
3. 打开 `http://localhost:8000/dashboard/`，选择“连接后端”，输入 `http://localhost:8000` 与车辆 ID。Pages 页面连接时必须使用 HTTPS 后端，并正确配置跨域。
4. 核对实际车端地图与所选参考路线的坐标系后再下发任务。网页选场景只选择路线，不切换车端地图；在线模式不模拟装卸、计数或规划器。

Pages 展示不需要 Docker。实车模式仍需要可达的后端与 Gateway；当前后端面向受信本地网络，尚无账号鉴权，不应直接暴露公网控制接口。公网接入前需配置访问控制与 TLS。

## 目录

| 目录 | 职责 |
| --- | --- |
| `site/` | 当前静态控制台，演示与后端连接模式 |
| `backend/` | FastAPI、MQTT 状态缓存、指令与任务 API |
| `gateway/` | MQTT 与 ROS2 话题、Action、Service 桥接 |
| `robot_contracts/` | 统一消息与任务反馈契约 |
| `docker/` | 后端/MQTT；可选 Jazzy Gateway 与车端生成接口 |
| `web/` | 旧版前端，保留供迁移参考，不发布 |
| `docs/` | 协议与联调说明；旧 README 见 local-cloud-history.md |

## 验证

```bash
python -m pip install -r backend/requirements.txt -e robot_contracts
PYTHONPATH=backend:robot_contracts pytest backend/tests gateway/tests robot_contracts/tests -q
node --check site/app.js
node --check site/live-adapter.js
```

本次整合已通过 67 项测试；ROS Action 和容器构建仍需在有 ROS2/Docker 的环境联调。详见 [整合说明](docs/integration.md)。
