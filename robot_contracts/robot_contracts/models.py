from __future__ import annotations

import time
import uuid
from enum import Enum
from typing import Any

SCHEMA_VERSION = "2.0"
SESSION_ID = str(uuid.uuid4())


class MessageType(str, Enum):
    """Wire envelope message types. v2 adds typed topics alongside v1 carry-overs."""

    # v1 carry-overs
    TELEMETRY = "telemetry"
    EVENT = "event"
    COMMAND = "command"
    COMMAND_ACK = "command_ack"
    HEARTBEAT = "heartbeat"

    # v2 typed topics (vehicle → cloud)
    RUNTIME_STATUS = "runtime_status"
    FAULT = "fault"
    METRICS = "metrics"
    CONTROL = "control"
    TRAJECTORY = "trajectory"

    # v2 mission lifecycle (cloud → vehicle, vehicle → cloud)
    MISSION_COMMAND = "mission_command"
    MISSION_CANCEL = "mission_cancel"
    MISSION_FEEDBACK = "mission_feedback"
    MISSION_RESULT = "mission_result"

    # v2 direct control
    EMERGENCY_STOP = "emergency_stop"


# Mapping from MessageType to its expected payload class. Populated in payloads
# module to avoid a circular import at module load time.
PAYLOAD_TYPES: dict[str, type] = {}


def register_payload(message_type: str, payload_class: type) -> None:
    """Register a payload dataclass for a given MessageType."""
    PAYLOAD_TYPES[message_type] = payload_class


class CommandStatus(str, Enum):
    CREATED = "CREATED"
    PUBLISHED = "PUBLISHED"
    ACCEPTED = "ACCEPTED"
    EXECUTING = "EXECUTING"
    SUCCEEDED = "SUCCEEDED"
    REJECTED = "REJECTED"
    FAILED = "FAILED"
    TIMEOUT = "TIMEOUT"
    EXPIRED = "EXPIRED"
    CANCELED = "CANCELED"


def envelope(
    robot_id: str,
    message_type: MessageType | str,
    payload: dict[str, Any],
    *,
    sequence: int,
    message_id: str | None = None,
    timestamp: float | None = None,
) -> dict[str, Any]:
    """Build the canonical JSON-serializable wire envelope."""
    return {
        "schema_version": SCHEMA_VERSION,
        "session_id": SESSION_ID,
        "message_id": message_id or str(uuid.uuid4()),
        "robot_id": robot_id,
        "timestamp": timestamp if timestamp is not None else time.time(),
        "sequence": sequence,
        "type": MessageType(message_type).value,
        "payload": payload,
    }


def parse_envelope(value: Any) -> dict[str, Any]:
    """Validate required envelope fields without binding transports to Pydantic."""
    if not isinstance(value, dict):
        raise ValueError("envelope must be an object")
    required = {"schema_version", "message_id", "robot_id", "timestamp", "sequence", "type", "payload"}
    missing = required.difference(value)
    if missing:
        raise ValueError(f"missing envelope fields: {sorted(missing)}")
    if value["schema_version"] != SCHEMA_VERSION:
        raise ValueError(f"unsupported schema_version: {value['schema_version']}")
    MessageType(value["type"])
    if not isinstance(value["payload"], dict):
        raise ValueError("payload must be an object")
    return value

