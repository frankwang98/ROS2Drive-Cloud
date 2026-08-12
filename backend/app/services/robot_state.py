"""机器人实时状态管理器。

负责：
- 维护每个机器人的最新状态快照（来自 MQTT/ZMQ 消息）
- 作为 WebSocket 广播的数据源
- 提供 REST API 读取当前状态

数据模型为统一 JSON，由 gateway 层从 ROS2 话题转换而来。
"""
from __future__ import annotations

import asyncio
import threading
import time
from typing import Any, Dict, Optional

from app.core.config import settings


class RobotStateStore:
    """线程安全地保存机器人状态，并支持 WebSocket 订阅者推送。"""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._state: Dict[str, Any] = {
            "connected": False,
            "last_update": None,
            "topics": {},
        }
        self._subscribers: set[asyncio.Queue] = set()
        self._loop: Optional[asyncio.AbstractEventLoop] = None

    def attach_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        self._loop = loop

    # ---- 写入 ----
    def update_topic(self, topic: str, payload: Any) -> None:
        """更新某个机器人话题的最新值。"""
        with self._lock:
            self._state["connected"] = True
            self._state["last_update"] = time.time()
            self._state["topics"][topic] = {
                "value": payload,
                "ts": time.time(),
            }
        self._broadcast(topic, payload)

    def set_connected(self, connected: bool) -> None:
        with self._lock:
            self._state["connected"] = connected
        self._broadcast("_system/connected", connected)

    def _broadcast(self, topic: str, payload: Any) -> None:
        """异步将更新推送给所有 WebSocket 订阅者。"""
        if self._loop is None:
            return
        msg = {"topic": topic, "data": payload}
        for q in list(self._subscribers):
            self._loop.call_soon_threadsafe(q.put_nowait, msg)

    # ---- 订阅（WebSocket 广播）----
    def subscribe(self) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue()
        self._subscribers.add(q)
        return q

    def unsubscribe(self, q: asyncio.Queue) -> None:
        self._subscribers.discard(q)

    # ---- 读取 ----
    def snapshot(self) -> Dict[str, Any]:
        with self._lock:
            return dict(self._state)

    def get_topic(self, topic: str) -> Optional[Any]:
        with self._lock:
            item = self._state["topics"].get(topic)
            return item["value"] if item else None


# 全局单例
state_store = RobotStateStore()
