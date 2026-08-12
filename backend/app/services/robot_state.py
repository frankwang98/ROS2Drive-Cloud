"""机器人实时状态管理器。

负责：
- 维护每个机器人的最新状态快照（来自 MQTT/ZMQ 消息）
- 维护运行模式（simulation / real）与机器人位姿（x/y/heading）+ 轨迹
- 作为 WebSocket 广播的数据源
- 提供 REST API 读取当前状态

数据模型为统一 JSON，由 gateway 层从 ROS2 话题转换而来。
"""
from __future__ import annotations

import asyncio
import threading
import time
from typing import Any, Dict, List, Optional

from app.core.config import settings

# 位置相关话题（用于地图可视化）
POSITION_TOPICS = {
    "sdc/x": "x",
    "sdc/y": "y",
    "sdc/heading": "heading",
    "pose/x": "x",
    "pose/y": "y",
    "pose/heading": "heading",
    "odom/x": "x",
    "odom/y": "y",
}

# 障碍物话题（地图上绘制障碍物）
OBSTACLE_TOPICS = {
    "sdc/obstacle_count": "count",
}


class RobotStateStore:
    """线程安全地保存机器人状态、位姿与轨迹，并支持 WebSocket 订阅者推送。"""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._mode = settings.robot_mode
        self._state: Dict[str, Any] = {
            "connected": False,
            "last_update": None,
            "mode": self._mode,
            "topics": {},
        }
        # 位姿：x(m), y(m), heading(弧度)
        self._pose = {"x": 0.0, "y": 0.0, "heading": 0.0}
        # 轨迹点 [(x, y), ...]（最多保留 MAX_TRAIL 个）
        self._trail: List[tuple] = []
        self._MAX_TRAIL = 500
        self._subscribers: set[asyncio.Queue] = set()
        self._loop: Optional[asyncio.AbstractEventLoop] = None

    def attach_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        self._loop = loop

    # ---- 运行模式 ----
    def set_mode(self, mode: str) -> None:
        mode = "real" if mode == "real" else "simulation"
        with self._lock:
            self._mode = mode
            self._state["mode"] = mode
        self._broadcast("_system/mode", mode)

    def get_mode(self) -> str:
        with self._lock:
            return self._mode

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
            # 若为位姿话题，同步更新位姿与轨迹
            self._maybe_update_pose(topic, payload)
        self._broadcast(topic, payload)

    def _maybe_update_pose(self, topic: str, payload: Any) -> None:
        """根据位置话题更新位姿（x/y/heading）。"""
        if topic in POSITION_TOPICS:
            try:
                val = float(payload)
            except (TypeError, ValueError):
                return
            key = POSITION_TOPICS[topic]
            self._pose[key] = val
            if key in ("x", "y"):
                # 追加轨迹点（去重连续重复点）
                last = self._trail[-1] if self._trail else None
                if last is None or (abs(last[0] - self._pose["x"]) > 0.01 or
                                    abs(last[1] - self._pose["y"]) > 0.01):
                    self._trail.append((self._pose["x"], self._pose["y"]))
                    if len(self._trail) > self._MAX_TRAIL:
                        self._trail = self._trail[-self._MAX_TRAIL:]

    def clear_trail(self) -> None:
        """清空轨迹。"""
        with self._lock:
            self._trail = []
        self._broadcast("_system/clear_trail", True)

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
            snap = dict(self._state)
            snap["pose"] = dict(self._pose)
            snap["trail"] = list(self._trail)
            return snap

    def get_topic(self, topic: str) -> Optional[Any]:
        with self._lock:
            item = self._state["topics"].get(topic)
            return item["value"] if item else None

    def get_pose(self) -> Dict[str, float]:
        with self._lock:
            return dict(self._pose)

    def get_trail(self) -> List[tuple]:
        with self._lock:
            return list(self._trail)


# 全局单例
state_store = RobotStateStore()
