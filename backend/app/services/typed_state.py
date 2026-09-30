"""Typed v2 payload store.

Mirrors robot_state.py's design: thread-safe singleton that caches the
*latest* typed payload per (robot_id, payload type). Backed only by RAM;
no DB by design (postgres/redis is intentionally out of M1 scope).

Types tracked:
    runtime_status, fault, control, metrics, trajectory,
    mission_feedback, mission_result

Telemetry (`type=telemetry` legacy scalar) keeps going through
robot_state.state_store.update_topic(), which is the existing projection
the Web Dashboard already understands.

Each typed update fires the asyncio broadcast queue so any WebSocket
subscriber can deliver the new payload to the front-end.
"""
from __future__ import annotations

import asyncio
import logging
import threading
import time
from copy import deepcopy
from typing import Any

logger = logging.getLogger("robot.typed_state")

# Stable wire names used both in robot_contracts.MessageType and in MQTT
# topics. Keep this set narrow: only the typed payload shapes, no legacy
# telemetry.
_TYPED_TYPES = frozenset({
    "runtime_status",
    "fault",
    "control",
    "metrics",
    "trajectory",
    "mission_feedback",
    "mission_result",
})


class TypedStateStore:
    """Latest-value cache keyed by (robot_id, payload_type).

    Thread-safe for writers (MQTT thread), asyncio-safe for subscribers.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        # _data[(robot_id, type)] = {"payload": dict, "ts": float, "sequence": int}
        self._data: dict[tuple[str, str], dict[str, Any]] = {}
        self._loop: asyncio.AbstractEventLoop | None = None
        self._subscribers: set[asyncio.Queue] = set()

    # ---- asyncio wiring ----

    def attach_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        self._loop = loop

    def subscribe(self, maxsize: int = 256) -> asyncio.Queue:
        queue: asyncio.Queue = asyncio.Queue(maxsize=maxsize)
        self._subscribers.add(queue)
        return queue

    def unsubscribe(self, queue: asyncio.Queue) -> None:
        self._subscribers.discard(queue)

    # ---- writer (MQTT thread) ----

    def update(
        self,
        robot_id: str,
        payload_type: str,
        payload: dict[str, Any],
        *,
        timestamp: float | None = None,
        sequence: int | None = None,
        session_id: str | None = None,
    ) -> bool:
        """Store the latest payload. Returns False if the type is unknown."""
        if payload_type not in _TYPED_TYPES:
            logger.warning("typed_state received unknown type=%s", payload_type)
            return False
        ts = timestamp if timestamp is not None else time.time()
        with self._lock:
            key = (robot_id, payload_type)
            old = self._data.get(key)
            if old:
                same_session = session_id == old.get("session_id")
                if same_session and sequence is not None and old["sequence"] is not None and sequence <= old["sequence"]:
                    return False
                if not same_session and ts < old["ts"]:
                    return False
            self._data[key] = {
                "payload": deepcopy(payload),
                "session_id": session_id,
                "received_at": time.time(),
                "ts": ts,
                "sequence": sequence,
            }
        self._broadcast(robot_id, payload_type, payload, ts)
        return True

    # ---- reader ----

    def get(self, robot_id: str, payload_type: str) -> dict[str, Any] | None:
        with self._lock:
            entry = self._data.get((robot_id, payload_type))
            if entry is None:
                return None
            return {
                "robot_id": robot_id,
                "type": payload_type,
                "payload": deepcopy(entry["payload"]),
                "ts": entry["ts"],
                "received_at": entry["received_at"],
                "sequence": entry["sequence"],
            }

    def snapshot(self, robot_id: str) -> dict[str, Any]:
        """All typed payloads for one robot."""
        with self._lock:
            return {
                ptype: {
                    "payload": deepcopy(entry["payload"]),
                    "ts": entry["ts"],
                "received_at": entry["received_at"],
                    "sequence": entry["sequence"],
                }
                for (rid, ptype), entry in self._data.items()
                if rid == robot_id
            }

    def robot_ids(self) -> tuple[str, ...]:
        """Robots known through typed telemetry, including heartbeat-free senders."""
        with self._lock:
            return tuple(sorted({rid for rid, _ in self._data}))

    def known_types(self) -> tuple[str, ...]:
        return tuple(sorted(_TYPED_TYPES))

    # ---- internal ----

    def _broadcast(
        self,
        robot_id: str,
        payload_type: str,
        payload: dict[str, Any],
        ts: float,
    ) -> None:
        if self._loop is None:
            return
        message = {
            "type": payload_type,
            "robot_id": robot_id,
            "data": payload,
            "ts": ts,
        }
        for queue in list(self._subscribers):
            def enqueue(q=queue, msg=message):
                if q.full():
                    try:
                        q.get_nowait()
                    except asyncio.QueueEmpty:
                        pass
                q.put_nowait(msg)
            self._loop.call_soon_threadsafe(enqueue)


typed_state = TypedStateStore()

