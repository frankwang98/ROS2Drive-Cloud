"""MQTT 消息消费者。

订阅 gateway 转发过来的机器人消息（JSON），写入状态管理器。
支持 paho-mqtt；broker 未就绪时自动重连。
"""
from __future__ import annotations

import json
import logging
import threading
from typing import Callable, Optional

from app.core.config import settings

logger = logging.getLogger("robot.mqtt")


class MQTTSubscriber:
    """后台线程订阅 MQTT 主题并回调处理。"""

    def __init__(self, on_message: Callable[[str, dict], None]) -> None:
        self.on_message = on_message
        self._client = None
        self._thread: Optional[threading.Thread] = None
        self._running = False

    def _import_client(self):
        try:
            import paho.mqtt.client as mqtt
            return mqtt
        except ImportError as e:  # pragma: no cover
            logger.warning("paho-mqtt 未安装，MQTT 订阅不可用: %s", e)
            return None

    def start(self) -> None:
        mqtt = self._import_client()
        if mqtt is None:
            return
        self._running = True

        def on_connect(client, userdata, flags, reason_code, properties=None):
            # paho-mqtt VERSION2 回调签名为 (client, userdata, flags, reason_code, properties)
            rc = getattr(reason_code, "value", reason_code)
            logger.info("MQTT 已连接, rc=%s", rc)
            client.subscribe(f"{settings.mqtt_topic_prefix}/#")

        def on_message(client, userdata, msg):
            try:
                payload = json.loads(msg.payload.decode("utf-8"))
                self.on_message(msg.topic, payload)
            except Exception as e:  # noqa: BLE001
                logger.error("解析 MQTT 消息失败: %s", e)

        self._client = mqtt.Client(
            callback_api_version=mqtt.CallbackAPIVersion.VERSION2
        )
        self._client.on_connect = on_connect
        self._client.on_message = on_message

        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def _run(self) -> None:
        while self._running:
            try:
                self._client.connect(settings.mqtt_broker, settings.mqtt_port, 60)
                self._client.loop_forever()
            except Exception as e:  # noqa: BLE001
                logger.warning("MQTT 连接失败，重试中: %s", e)
                import time

                time.sleep(5)

    def stop(self) -> None:
        self._running = False
        if self._client:
            try:
                self._client.disconnect()
            except Exception:  # noqa: BLE001
                pass
