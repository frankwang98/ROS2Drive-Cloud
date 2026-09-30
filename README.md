# ROS2Drive Cloud

低速无人车任务与运行管理平台的第一版前端演示。

**在线演示：https://frankwang98.asia/ROS2Drive-Cloud/**

## 当前能力

- 环道教学、矿区运输、港口运输、农业作业四个场景。
- 路线参照 ROS2Drive 的 `src/scenario/*_scenario.cpp`，复核于 2026-09-30。
- 三辆独立模拟车、任务下发/暂停/恢复/取消、模拟急停与手动恢复。
- 位置、速度、任务进度、装卸停留、事件日志与演示时间倍率。

页面明确标注模拟数据。不连接实车，不运行 ROS2 或规划控制算法；三车为独立演示，不提供碰撞检测、避障或车队调度。农业使用场景参考路线，并非车端 CoveragePathPlanner 的实时输出。

## 本地查看

无需 Docker 或安装前端依赖：

```bash
python3 -m http.server 8080 --directory site
# 打开 http://localhost:8080
```

## 文件与边界

- `site/index.html`：控制台界面。
- `site/styles.css`：响应式样式。
- `site/app.js`：场景数据、MockAdapter、UI。
- `MockAdapter` 统一提供 `dispatch/pause/cancel/estop/snapshot`，未来 LiveAdapter 对接 Gateway / API。
- 车端继续拥有实时规划控制和安全仲裁权；云端管理任务请求、状态与历史。

## 发布

演示复用 `frankwang98.github.io` 的 GitHub Pages，在 `/ROS2Drive-Cloud/` 路径发布，不需要本地 Docker。
主页仓库发布流程拉取本仓库 main 的 `site/`；主页提交或手动运行发布会立即触发，定时任务每 15 分钟检查发布（GitHub 队列可能延迟）。
本仓库提交通过 GitHub Actions 做 JavaScript 语法检查。

## 下一步

1. 将车端场景导出为版本化 JSON，避免手动维护两份几何。
2. 对齐 Mission 请求、反馈、结果与 RuntimeStatus/Fault 的协议。
3. 接入单车 Gateway，再考虑多车任务队列与调度。
