"""Regression checks for expired commands and robot isolation."""
import time

from app.services.robot_registry import RobotRegistry


def test_expired_command_stays_timed_out_after_late_ack():
    registry = RobotRegistry()
    registry.record_command({
        "robot_id": "car01", "message_id": "expired-1",
        "status": "PUBLISHED",
        "payload": {"expires_at": time.time() - 1},
    })
    assert registry.command("expired-1")["status"] == "TIMEOUT"
    registry.update_command_ack("car01", {
        "command_id": "expired-1", "status": "SUCCEEDED",
    })
    assert registry.command("expired-1")["status"] == "TIMEOUT"


def test_late_ack_cannot_override_other_robot_timeout():
    registry = RobotRegistry()
    registry.record_command({
        "robot_id": "car01", "message_id": "expired-2",
        "status": "PUBLISHED",
        "payload": {"expires_at": time.time() - 1},
    })
    assert registry.command("expired-2")["status"] == "TIMEOUT"
    registry.update_command_ack("car02", {
        "command_id": "expired-2", "status": "SUCCEEDED",
    })
    assert registry.command("expired-2")["status"] == "TIMEOUT"
