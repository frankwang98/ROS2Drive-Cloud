"""Cloud-side mission lifecycle, multi-robot and disconnect regression tests.

These tests simulate gateway messages at the Backend boundary; they do not
replace a real ROS 2 + MQTT end-to-end test.
"""
import time

from app.services.robot_registry import RobotRegistry
from app.services.typed_state import TypedStateStore


def test_mission_feedback_result_and_late_feedback():
    registry = RobotRegistry()
    registry.record_command({
        "robot_id": "car01", "message_id": "cmd-m1",
        "type": "mission_command", "status": "PUBLISHED",
        "payload": {"mission_id": "mission-1"},
    })
    registry.update_mission("car01", {"mission_id": "mission-1", "progress": 0.5})
    assert registry.mission("car01", "mission-1")["status"] == "EXECUTING"

    registry.update_mission("car01", {
        "mission_id": "mission-1", "final_state": "SUCCEEDED",
        "success": True,
    }, result=True)
    assert registry.mission("car01", "mission-1")["status"] == "SUCCEEDED"

    # A delayed MQTT feedback message must not undo a terminal result.
    registry.update_mission("car01", {"mission_id": "mission-1", "progress": 0.8})
    assert registry.mission("car01", "mission-1")["status"] == "SUCCEEDED"


def test_mission_result_cannot_cross_robot_boundary():
    registry = RobotRegistry()
    registry.record_command({
        "robot_id": "car01", "message_id": "cmd-car01",
        "type": "mission_command", "status": "PUBLISHED",
        "payload": {"mission_id": "shared-id"},
    })
    registry.record_command({
        "robot_id": "car02", "message_id": "cmd-car02",
        "type": "mission_command", "status": "PUBLISHED",
        "payload": {"mission_id": "shared-id"},
    })
    registry.update_mission("car02", {
        "mission_id": "shared-id", "final_state": "CANCELED",
        "success": False,
    }, result=True)
    assert registry.mission("car01", "shared-id")["status"] == "PUBLISHED"
    assert registry.mission("car02", "shared-id")["status"] == "CANCELED"


def test_disconnect_and_reconnect_are_based_on_receive_time():
    registry = RobotRegistry(offline_after=0.05)
    registry.heartbeat("car01")
    assert registry.robot("car01")["connection"]["state"] == "ONLINE"
    assert registry.robot("car02")["connection"]["state"] == "OFFLINE"
    # Simulate an elapsed receive deadline without a flaky wall-clock sleep.
    with registry._lock:
        registry._robots["car01"]["connection"]["last_seen"] = time.time() - 1
    assert registry.robot("car01")["connection"]["state"] == "OFFLINE"
    registry.heartbeat("car01")
    assert registry.robot("car01")["connection"]["state"] == "ONLINE"


def test_typed_telemetry_isolation_and_restart_sequence():
    store = TypedStateStore()
    assert store.update("car01", "runtime_status", {"runtime_state": "ESTOP"},
                        sequence=20, timestamp=10, session_id="before")
    assert store.update("car02", "runtime_status", {"runtime_state": "RUNNING"},
                        sequence=1, timestamp=11, session_id="other")
    assert not store.update("car01", "runtime_status", {"runtime_state": "RUNNING"},
                            sequence=19, timestamp=12, session_id="before")
    assert store.get("car01", "runtime_status")["payload"]["runtime_state"] == "ESTOP"
    assert store.update("car01", "runtime_status", {"runtime_state": "READY"},
                        sequence=1, timestamp=13, session_id="after")
    assert store.get("car02", "runtime_status")["payload"]["runtime_state"] == "RUNNING"
    assert set(store.robot_ids()) == {"car01", "car02"}
