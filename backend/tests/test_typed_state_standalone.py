"""Standalone tests for TypedStateStore — does NOT import the app package.

Imports only Python stdlib. Useful for running on a host where the
backend's dependencies (pydantic-settings, fastapi, ...) are not
installed. The full path-based test lives in
``test_typed_state.py``; this file mirrors it for offline validation.
"""
from __future__ import annotations

import asyncio
import sys
import threading
import unittest
from pathlib import Path

# Make typed_state.py importable without going through ``app.*``.
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app" / "services"))

# Direct import — typed_state.py has no app.* dependencies.
from typed_state import TypedStateStore  # type: ignore  # noqa: E402


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

    def test_timestamp_defaults_to_now(self) -> None:
        import time
        before = time.time()
        self.store.update("car01", "runtime_status", {})
        entry = self.store.get("car01", "runtime_status")
        self.assertIsNotNone(entry)
        self.assertGreaterEqual(entry["ts"], before)


class TypedStateStoreConcurrencyTests(unittest.TestCase):
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

    def test_broadcast_without_attached_loop_does_not_raise(self) -> None:
        store = TypedStateStore()
        # Without attach_loop, update must not raise.
        store.update("car01", "runtime_status", {"x": 1})


class TypedStateStoreBroadcastTests(unittest.TestCase):
    def test_subscriber_receives_update(self) -> None:
        store = TypedStateStore()
        loop = asyncio.new_event_loop()
        try:
            store.attach_loop(loop)
            queue = store.subscribe()
            store.update("car01", "control", {"target_speed": 1.5}, sequence=7)

            for _ in range(50):
                if not queue.empty():
                    break
                loop.run_until_complete(asyncio.sleep(0))

            self.assertFalse(queue.empty())
            msg = queue.get_nowait()
            self.assertEqual(msg["type"], "control")
            self.assertEqual(msg["robot_id"], "car01")
            self.assertEqual(msg["data"], {"target_speed": 1.5})
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
            for _ in range(20):
                loop.run_until_complete(asyncio.sleep(0))
            self.assertTrue(q1.empty())
        finally:
            loop.close()


if __name__ == "__main__":
    unittest.main()