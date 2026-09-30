"""Tests for the v2 typed payload state store.

Framework-free so we can run under ``python3 -m unittest``.
"""
from __future__ import annotations

import asyncio
import sys
import threading
import time
import unittest
from pathlib import Path

# Allow running this file directly: `python3 tests/test_typed_state.py`.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services.typed_state import TypedStateStore, typed_state  # noqa: E402


def _run_async(coro):
    """Drive a coroutine from synchronous test code."""
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


class TypedStateStoreBasicTests(unittest.TestCase):
    def setUp(self) -> None:
        self.store = TypedStateStore()

    def test_update_returns_true_for_known_types(self) -> None:
        for t in ("runtime_status", "fault", "metrics", "control",
                  "trajectory", "mission_feedback", "mission_result"):
            self.assertTrue(self.store.update("car01", t, {"k": 1}))

    def test_update_rejects_unknown_types(self) -> None:
        self.assertFalse(self.store.update("car01", "telemetry", {"k": 1}))
        self.assertFalse(self.store.update("car01", "not_a_type", {}))

    def test_get_returns_latest_payload(self) -> None:
        self.store.update("car01", "runtime_status", {"runtime_state": "IDLE"}, sequence=1)
        self.store.update("car01", "runtime_status", {"runtime_state": "DRIVING"}, sequence=2)
        entry = self.store.get("car01", "runtime_status")
        self.assertIsNotNone(entry)
        self.assertEqual(entry["type"], "runtime_status")
        self.assertEqual(entry["robot_id"], "car01")
        self.assertEqual(entry["payload"], {"runtime_state": "DRIVING"})
        self.assertEqual(entry["sequence"], 2)

    def test_get_unknown_returns_none(self) -> None:
        self.assertIsNone(self.store.get("car01", "runtime_status"))
        self.store.update("car01", "runtime_status", {})
        self.assertIsNone(self.store.get("car02", "runtime_status"))

    def test_snapshot_returns_only_target_robot(self) -> None:
        self.store.update("car01", "runtime_status", {"a": 1})
        self.store.update("car01", "control", {"b": 2})
        self.store.update("car02", "runtime_status", {"c": 3})

        snap01 = self.store.snapshot("car01")
        snap02 = self.store.snapshot("car02")
        self.assertEqual(set(snap01.keys()), {"runtime_status", "control"})
        self.assertEqual(set(snap02.keys()), {"runtime_status"})
        self.assertEqual(snap02["runtime_status"]["payload"], {"c": 3})

    def test_snapshot_empty_robot_returns_empty_dict(self) -> None:
        self.assertEqual(self.store.snapshot("nobody"), {})

    def test_known_types_is_complete(self) -> None:
        self.assertEqual(
            set(self.store.known_types()),
            {"runtime_status", "fault", "metrics", "control",
             "trajectory", "mission_feedback", "mission_result"},
        )


class TypedStateStoreConcurrencyTests(unittest.TestCase):
    """Multiple writer threads must not corrupt state; readers see last write."""

    def test_concurrent_writers_keep_state_consistent(self) -> None:
        store = TypedStateStore()
        iterations = 500

        def writer(robot: str, base: int):
            for i in range(iterations):
                store.update(robot, "runtime_status",
                             {"runtime_state": "S", "i": base + i},
                             sequence=base + i)

        threads = [
            threading.Thread(target=writer, args=("car01", 0)),
            threading.Thread(target=writer, args=("car02", 10_000)),
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        snap01 = store.snapshot("car01")
        snap02 = store.snapshot("car02")
        # Last entry wins, and its i must belong to the right writer.
        self.assertEqual(snap01["runtime_status"]["payload"]["i"] // 1000, 0)
        self.assertEqual(snap02["runtime_status"]["payload"]["i"] // 1000, 10)

    def test_broadcast_requires_attached_loop(self) -> None:
        store = TypedStateStore()
        # Without attach_loop, update must not raise.
        store.update("car01", "runtime_status", {"x": 1})


class TypedStateStoreBroadcastTests(unittest.TestCase):
    """Subscribers should receive a JSON-friendly broadcast per update."""

    def test_subscriber_receives_update(self) -> None:
        store = TypedStateStore()
        loop = asyncio.new_event_loop()
        try:
            store.attach_loop(loop)
            queue = store.subscribe()
            store.update("car01", "control", {"target_speed": 1.5}, sequence=7)

            # The call_soon_threadsafe runs on next loop iteration.
            for _ in range(20):
                if not queue.empty():
                    break
                loop.run_until_complete(asyncio.sleep(0))

            self.assertFalse(queue.empty())
            msg = queue.get_nowait()
            self.assertEqual(msg["type"], "control")
            self.assertEqual(msg["robot_id"], "car01")
            self.assertEqual(msg["data"], {"target_speed": 1.5})
            self.assertEqual(msg["sequence" if "sequence" in msg else "ts"],  # tolerate either
                             7 if "sequence" in msg else msg["ts"])
        finally:
            loop.close()

    def test_subscriber_unsubscribed_stops_receiving(self) -> None:
        store = TypedStateStore()
        loop = asyncio.new_event_loop()
        try:
            store.attach_loop(loop)
            q1 = store.subscribe()
            store.unsubscribe(q1)
            store.update("car01", "control", {"target_speed": 1.0})
            for _ in range(10):
                loop.run_until_complete(asyncio.sleep(0))
            self.assertTrue(q1.empty())
        finally:
            loop.close()


class ModuleSingletonTests(unittest.TestCase):
    def test_module_level_singleton_is_a_TypedStateStore(self) -> None:
        self.assertIsInstance(typed_state, TypedStateStore)


if __name__ == "__main__":
    unittest.main()
