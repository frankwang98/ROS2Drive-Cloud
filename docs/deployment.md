# Kubernetes 部署

Robot Cloud Platform 的云原生部署清单位于 `k8s/` 目录。

## 组件

| 文件 | 说明 |
|------|------|
| `namespace.yaml` | 命名空间 `robot-cloud` |
| `configmap.yaml` | 全局配置 |
| `mqtt-broker.yaml` | MQTT Broker（Eclipse Mosquitto）|
| `backend.yaml` | FastAPI 后端 Deployment + Service |
| `gateway.yaml` | ROS2 消息桥接 Deployment + Service |
| `ingress.yaml` | 外部访问入口 |
| `hpa.yaml` | 后端自动扩缩容 |

## 部署步骤

```bash
# 1. 创建命名空间
kubectl apply -f k8s/namespace.yaml

# 2. 应用所有资源
kubectl apply -f k8s/

# 3. 查看状态
kubectl get pods -n robot-cloud
kubectl get svc -n robot-cloud
```

## 镜像

镜像托管于 CNB 制品库，需先在 `cnb.cool/frankwang98/robot_platform` 构建并推送：

- `robot_platform:backend` — FastAPI 后端
- `robot_platform:gateway` — ROS2 消息桥接

构建方式见 [CI 流水线](../.cnb.yml)。

## Ingress 访问

配置 `host: robot.cloud.example.com`，将域名解析到集群 Ingress Controller 后：

- Web Dashboard: `http://robot.cloud.example.com/dashboard/`
- REST API: `http://robot.cloud.example.com/api/robot/status`
- WebSocket: `ws://robot.cloud.example.com/ws/robot`

## 弹性伸缩

通过 `hpa.yaml` 配置：
- 副本数：2 ~ 10
- 触发条件：CPU > 70% 或 内存 > 80%

## 本地开发（无需 K8s）

使用 Docker Compose 一键启动全链路：

```bash
docker compose -f docker/docker-compose.yml up --build
```

访问 `http://localhost:8000/dashboard/` 查看 Web Dashboard。
