# Robot Cloud Platform Web Dashboard

Web Dashboard 前端，通过 WebSocket 实时展示机器人状态（速度、行为、前方距离等），
并支持远程控制（切换控制算法、暂停/继续）。

本实现为**零构建**静态页面（HTML + 原生 JS + CSS），
由 Backend 以静态文件服务托管，或由 Nginx 提供。

## 运行

由 Backend 自动挂载（FastAPI StaticFiles），访问 `http://localhost:8000/dashboard/` 即可。
