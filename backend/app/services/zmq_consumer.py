"""ZMQ 消息消费者（SUB 模式）。

从 gateway 的 ZMQ PUB 端口接收机器人 JSON 消息。
依赖 pyzmq；不可用时降级为仅记录日志。
"""
from __future__ import annotations

import json
import logging
import threading
from typing import Callable, Optional

from app.core.config import settings

logger = logging.getLogger("robot.zmq")


class ZMQSubscriber:
    """后台线程订阅 ZMQ PUB 主题并回调处理。"""

    def __init__(self, on_message: Callable[[str, dict], None]) -> None:
        self.on_message = on_message
        self._context = None
        self._socket = None
        self._thread: Optional[threading.Thread] = None
        self._running = False

    def start(self) -> None:
        try:
            import zmq
        except ImportError as e:  # pragma: no cover
            logger.warning("pyzmq 未安装，ZMQ 订阅不可用: %s", e)
            return
        self._running = True
        self._context = zmq.Context()
        self._socket = self._context.socket(zmq.SUB)
        self._socket.connect(f"tcp://{settings.mqtt_broker}:{settings.zmq_pub_port}")
        self._socket.setsockopt_string(zmq.SUBSCRIBE, "")

        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def _run(self) -> None:
        while self._running:
            try:
                topic = self._socket.recv_string()
                payload = json.loads(self._socket.recv_string())
                self.on_message(topic, payload)
            except Exception as e:  # noqa: BLE001
                logger.error("ZMQ 接收消息失败: %s", e)

    def stop(self) -> None:
        self._running = False
        if self._socket:
            try:
                self._socket.close()
            except Exception:  # noqa: BLE001
                pass

