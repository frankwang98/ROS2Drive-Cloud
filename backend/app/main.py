"""FastAPI 应用入口。"""
import asyncio
import logging
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.api import control, mode, robot, system, ws
from app.core.config import settings
from app.services.mqtt_consumer import MQTTSubscriber
from app.services.command_publisher import command_publisher
from app.services.robot_state import state_store
from app.services.robot_registry import robot_registry
from app.services.zmq_consumer import ZMQSubscriber
from robot_contracts import MessageType, parse_envelope

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("robot")

app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    debug=settings.debug,
)

# CORS：允许 Web Dashboard 跨域访问
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(system.router)
app.include_router(robot.router)
app.include_router(robot.v1_router)
app.include_router(control.router)
app.include_router(mode.router)
app.include_router(ws.router)

# 托管 Web Dashboard 静态文件（web/ 目录）
# 向上逐级探测 web 目录，兼容：
#   容器内 __file__=/app/app/main.py → /app/web
#   本地 __file__=<repo>/backend/app/main.py → <repo>/web
def _find_web_dir():
    cur = Path(__file__).resolve().parent
    for _ in range(6):  # 向上探测最多 6 级
        candidate = cur / "web"
        if candidate.is_dir():
            return candidate
        cur = cur.parent
    return None

_WEB_DIR = _find_web_dir()
if _WEB_DIR:
    app.mount("/dashboard", StaticFiles(directory=_WEB_DIR, html=True), name="dashboard")
    logger.info("Web Dashboard 已挂载：%s", _WEB_DIR)
else:
    logger.warning("未找到 web/ 目录，Dashboard 不可用（/dashboard 将返回 404）")

# ---- 消息消费者（MQTT + ZMQ）----
_subscribers = []


def _on_message(topic: str, payload: dict) -> None:
    """将消息总线上的机器人数据写入状态管理器。"""
    try:
        message = parse_envelope(payload)
    except ValueError as exc:
        logger.warning("丢弃不符合协议的消息 topic=%s: %s", topic, exc)
        return
    robot_id = message["robot_id"]
    kind = MessageType(message["type"])
    body = message["payload"]
    if kind is MessageType.TELEMETRY:
        name, value = body.get("name", "unknown"), body.get("value")
        robot_registry.update_telemetry(robot_id, name, value, message["timestamp"])
        # Legacy single-robot projection; Dashboard 完全迁移后删除。
        state_store.update_topic(name, value)
    elif kind is MessageType.HEARTBEAT:
        robot_registry.heartbeat(robot_id, message["timestamp"])
    elif kind is MessageType.COMMAND_ACK:
        robot_registry.update_command_ack(robot_id, body)


@app.on_event("startup")
async def startup() -> None:
    loop = asyncio.get_running_loop()
    state_store.attach_loop(loop)
    robot_registry.attach_loop(loop)

    mqtt = MQTTSubscriber(_on_message)
    mqtt.start()
    if settings.enable_zmq:
        zmq = ZMQSubscriber(_on_message)
        zmq.start()
        _subscribers.append(zmq)
    command_publisher.start()
    _subscribers.append(mqtt)
    logger.info("机器人后端已启动：%s v%s", settings.app_name, settings.app_version)


@app.on_event("shutdown")
async def shutdown() -> None:
    for sub in _subscribers:
        sub.stop()
    command_publisher.stop()
