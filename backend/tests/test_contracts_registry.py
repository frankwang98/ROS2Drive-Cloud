from robot_contracts import CommandStatus, MessageType, envelope, parse_envelope

from app.services.robot_registry import RobotRegistry
import time


def test_contract_round_trip():
    message = envelope("robot-001", MessageType.TELEMETRY, {
        "name": "sdc/speed", "value": 2.5,
    }, sequence=7)
    assert parse_envelope(message) == message
    assert message["schema_version"] == "1.0"


def test_registry_isolates_robots_and_tracks_connection():
    registry = RobotRegistry(offline_after=10)
    registry.update_telemetry("robot-001", "sdc/speed", 1.0)
    registry.update_telemetry("robot-002", "sdc/speed", 2.0)

    assert registry.robot("robot-001")["telemetry"]["sdc/speed"]["value"] == 1.0
    assert registry.robot("robot-002")["telemetry"]["sdc/speed"]["value"] == 2.0
    assert registry.robot("robot-001")["connection"]["state"] == "ONLINE"


def test_command_ack_updates_lifecycle():
    registry = RobotRegistry()
    command = envelope("robot-001", MessageType.COMMAND, {
        "action": "pause", "value": True,
    }, sequence=1)
    command["status"] = CommandStatus.PUBLISHED.value
    registry.record_command(command)
    registry.update_command_ack("robot-001", {
        "command_id": command["message_id"],
        "status": CommandStatus.SUCCEEDED.value,
        "detail": None,
    })
    assert registry.command(command["message_id"])["status"] == "SUCCEEDED"


def test_published_command_times_out_after_expiry():
    registry = RobotRegistry()
    command = envelope("robot-001", MessageType.COMMAND, {
        "action": "pause", "value": True, "expires_at": time.time() - 1,
    }, sequence=1)
    command["status"] = CommandStatus.PUBLISHED.value
    registry.record_command(command)
    assert registry.command(command["message_id"])["status"] == "TIMEOUT"
