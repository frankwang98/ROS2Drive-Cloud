from __future__ import annotations

import time
import uuid
from enum import Enum
from typing import Any

SCHEMA_VERSION = "1.0"


class MessageType(str, Enum):
    TELEMETRY = "telemetry"
    EVENT = "event"
    COMMAND = "command"
    COMMAND_ACK = "command_ack"
    HEARTBEAT = "heartbeat"


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
