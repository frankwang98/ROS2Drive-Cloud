"""Thread-safe multi-robot registry and command lifecycle store."""
from __future__ import annotations

import asyncio
import threading
import time
from copy import deepcopy
from typing import Any

from app.core.config import settings


class RobotRegistry:
    def __init__(self, offline_after: float = 10.0) -> None:
        self._lock = threading.RLock()
        self._robots: dict[str, dict[str, Any]] = {}
        self._commands: dict[str, dict[str, Any]] = {}
        self._subscribers: set[asyncio.Queue] = set()
        self._loop: asyncio.AbstractEventLoop | None = None
        self._offline_after = offline_after

    def attach_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        self._loop = loop

    def _robot(self, robot_id: str) -> dict[str, Any]:
        return self._robots.setdefault(robot_id, {
            "robot_id": robot_id,
            "connection": {"state": "OFFLINE", "last_seen": None},
            "desired": {},
            "reported": {"mode": settings.robot_mode},
            "observed": {"pose": {"x": 0.0, "y": 0.0, "heading": 0.0}, "velocity": {}},
            "telemetry": {},
            "trail": [],
        })

    def update_telemetry(self, robot_id: str, name: str, value: Any, timestamp: float | None = None) -> None:
        now = timestamp or time.time()
        with self._lock:
            robot = self._robot(robot_id)
            robot["connection"] = {"state": "ONLINE", "last_seen": now}
            robot["telemetry"][name] = {"value": value, "ts": now}
            if name == "sdc/odometry" and isinstance(value, dict):
                pose = value.get("pose", {})
                try:
                    robot["observed"]["pose"] = {
                        "x": float(pose["x"]), "y": float(pose["y"]),
                        "heading": float(pose["yaw"]),
                    }
                    robot["observed"]["velocity"] = deepcopy(value.get("velocity", {}))
                    self._append_trail(robot)
                except (KeyError, TypeError, ValueError):
                    pass
        self._broadcast(robot_id, "telemetry", {"name": name, "value": value})

    def heartbeat(self, robot_id: str, timestamp: float | None = None) -> None:
        now = timestamp or time.time()
        with self._lock:
            self._robot(robot_id)["connection"] = {"state": "ONLINE", "last_seen": now}
        self._broadcast(robot_id, "heartbeat", {"last_seen": now})

    def record_command(self, command: dict[str, Any]) -> None:
        with self._lock:
            self._commands[command["message_id"]] = deepcopy(command)

    def update_command_ack(self, robot_id: str, payload: dict[str, Any]) -> None:
        command_id = payload.get("command_id")
        if not command_id:
            return
        with self._lock:
            command = self._commands.setdefault(command_id, {"message_id": command_id, "robot_id": robot_id})
            command.update({"status": payload.get("status"), "detail": payload.get("detail"), "updated_at": time.time()})
        self._broadcast(robot_id, "command_ack", deepcopy(command))

    def command(self, command_id: str) -> dict[str, Any] | None:
        with self._lock:
            value = self._commands.get(command_id)
            if value and value.get("status") == "PUBLISHED":
                expires_at = value.get("payload", {}).get("expires_at")
                if expires_at is not None and time.time() > expires_at:
                    value["status"] = "TIMEOUT"
                    value["updated_at"] = time.time()
            return deepcopy(value) if value else None

    def clear_trail(self, robot_id: str) -> None:
        with self._lock:
            self._robot(robot_id)["trail"] = []
        self._broadcast(robot_id, "event", {"name": "trail_cleared"})

    def robot(self, robot_id: str) -> dict[str, Any]:
        with self._lock:
            result = deepcopy(self._robot(robot_id))
        self._refresh_connection(result)
        return result

    def robots(self) -> list[dict[str, Any]]:
        with self._lock:
            result = [deepcopy(robot) for robot in self._robots.values()]
        for robot in result:
            self._refresh_connection(robot)
        return result

    def subscribe(self, maxsize: int = 256) -> asyncio.Queue:
        queue: asyncio.Queue = asyncio.Queue(maxsize=maxsize)
        self._subscribers.add(queue)
        return queue

    def unsubscribe(self, queue: asyncio.Queue) -> None:
        self._subscribers.discard(queue)

    def _append_trail(self, robot: dict[str, Any]) -> None:
        pose = robot["observed"]["pose"]
        point = (pose["x"], pose["y"])
        trail = robot["trail"]
        if not trail or abs(trail[-1][0] - point[0]) > 0.01 or abs(trail[-1][1] - point[1]) > 0.01:
            trail.append(point)
            del trail[:-500]

    def _refresh_connection(self, robot: dict[str, Any]) -> None:
        last_seen = robot["connection"]["last_seen"]
        if last_seen is None or time.time() - last_seen > self._offline_after:
            robot["connection"]["state"] = "OFFLINE"

    def _broadcast(self, robot_id: str, event_type: str, payload: dict[str, Any]) -> None:
        if self._loop is None:
            return
        message = {"type": event_type, "robot_id": robot_id, "data": payload}
        for queue in list(self._subscribers):
            def enqueue(q=queue, msg=message):
                if q.full():
                    try:
                        q.get_nowait()
                    except asyncio.QueueEmpty:
                        pass
                q.put_nowait(msg)
            self._loop.call_soon_threadsafe(enqueue)


robot_registry = RobotRegistry()
