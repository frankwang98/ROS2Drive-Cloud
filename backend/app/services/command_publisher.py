"""下行指令发布器。

将 Backend 收到的控制指令发布到 MQTT；ZMQ 仅为显式启用的实验兼容通道，
由 gateway 订阅后转发为 ROS2 话题，最终下发到 ros2_car 机器人侧。

支持 paho-mqtt / pyzmq；对应通道不可用时降级为记录日志（仅 MQTT）。
"""
from __future__ import annotations

import json
import logging
import threading
import time
from itertools import count
from typing import Optional

from app.core.config import settings
from robot_contracts import CommandStatus, MessageType, envelope

logger = logging.getLogger("robot.command")


class CommandPublisher:
    """向消息总线发布云端控制指令。"""

    def __init__(self) -> None:
        self._mqtt_client = None
        self._zmq_socket = None
        self._zmq_context = None
        self._lock = threading.Lock()
        self._publish_lock = threading.Lock()
        self._started = False
        self._sequence = count(1)

    def start(self) -> None:
        """建立 MQTT 下行通道，并按配置启用实验性 ZMQ。"""
        with self._lock:
            if self._started:
                return
            self._init_mqtt()
            if settings.enable_zmq:
                self._init_zmq()
            self._started = True

    def _init_mqtt(self) -> None:
        try:
            import paho.mqtt.client as mqtt
        except ImportError as e:  # pragma: no cover
            logger.warning("paho-mqtt 未安装，指令将无法经 MQTT 下发: %s", e)
            return
        self._mqtt_client = mqtt.Client(
            callback_api_version=mqtt.CallbackAPIVersion.VERSION2
        )
        self._mqtt_client.reconnect_delay_set(min_delay=1, max_delay=10)
        try:
            # 异步连接避免应用启动依赖 Broker 的瞬时就绪状态。
            self._mqtt_client.connect_async(
                settings.mqtt_broker, settings.mqtt_port, 60
            )
            self._mqtt_client.loop_start()
            logger.info("指令发布器 MQTT 正在连接 %s:%s",
                        settings.mqtt_broker, settings.mqtt_port)
        except Exception as e:  # noqa: BLE001
            logger.warning("指令发布器 MQTT 初始化失败: %s", e)

    def _init_zmq(self) -> None:
        try:
            import zmq
        except ImportError as e:  # pragma: no cover
            logger.warning("pyzmq 未安装，指令将无法经 ZMQ 下发: %s", e)
            return
        try:
            self._zmq_context = zmq.Context()
            # gateway 的 ZMQ REP 监听在 zmq_pub_port + 1（见 gateway/ros2_bridge.py）
            rep_port = settings.zmq_pub_port + 1
            self._zmq_socket = self._zmq_context.socket(zmq.REQ)
            self._zmq_socket.connect(f"tcp://{settings.mqtt_broker}:{rep_port}")
            self._zmq_socket.setsockopt(zmq.RCVTIMEO, 3000)
            self._zmq_socket.setsockopt(zmq.LINGER, 0)
            logger.info("指令发布器 ZMQ 已连接 tcp://%s:%d",
                        settings.mqtt_broker, rep_port)
        except Exception as e:  # noqa: BLE001
            logger.warning("指令发布器 ZMQ 初始化失败: %s", e)
            self._zmq_socket = None

    def publish(self, robot_id: str, command: str, value=None) -> dict:
        return self.publish_typed(robot_id, MessageType.COMMAND,
                                  {"action": command, "value": value}, "commands")

    def publish_typed(self, robot_id: str, kind, body: dict, suffix: str) -> dict:
        from app.services.robot_registry import robot_registry
        topic = f"{settings.mqtt_topic_prefix}/{robot_id}/{suffix}"
        message = envelope(robot_id, kind,
                           {**body, "expires_at": time.time() + settings.command_timeout_seconds},
                           sequence=next(self._sequence))
        message["status"] = CommandStatus.CREATED.value
        # Register BEFORE transport publication: a fast ACK must not be lost.
        robot_registry.record_command(message)
        published = False
        payload = json.dumps(message)
        with self._publish_lock:
            if self._mqtt_client is not None:
                try:
                    info = self._mqtt_client.publish(topic, payload, qos=1)
                    info.wait_for_publish(timeout=5)
                    published = info.rc == 0 and info.is_published()
                except Exception as exc:
                    logger.error("MQTT publish failed: %s", exc)
            if self._zmq_socket is not None and kind == MessageType.COMMAND:
                try:
                    self._zmq_socket.send_string(payload)
                    self._zmq_socket.recv_string()
                    published = True
                except Exception as exc:
                    logger.error("ZMQ publish failed: %s", exc)
        message["status"] = (CommandStatus.PUBLISHED if published else CommandStatus.FAILED).value
        robot_registry.record_command(message)
        return robot_registry.command(message["message_id"])

    def stop(self) -> None:
        with self._lock:
            if self._mqtt_client is not None:
                try:
                    self._mqtt_client.loop_stop()
                    self._mqtt_client.disconnect()
                except Exception:  # noqa: BLE001
                    pass
                self._mqtt_client = None
            if self._zmq_socket is not None:
                try:
                    self._zmq_socket.close()
                except Exception:  # noqa: BLE001
                    pass
                self._zmq_socket = None
            if self._zmq_context is not None:
                try:
                    self._zmq_context.term()
                except Exception:  # noqa: BLE001
                    pass
                self._zmq_context = None
            self._started = False


# 全局单例
command_publisher = CommandPublisher()

