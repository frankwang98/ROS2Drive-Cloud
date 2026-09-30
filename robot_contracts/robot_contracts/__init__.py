"""Versioned wire contracts shared by Backend, Gateway and simulators."""

from .models import (
    SCHEMA_VERSION,
    CommandStatus,
    MessageType,
    envelope,
    parse_envelope,
)
from .payloads import (
    ControlCommandPayload,
    FaultArrayPayload,
    FaultPayload,
    MissionCommandPayload,
    MissionFeedbackPayload,
    MissionResultPayload,
    MissionType,
    Pose2D,
    RuntimeMetricsPayload,
    RuntimeStatusPayload,
    TrajectoryPayload,
    TrajectoryPointPayload,
    encode_payload,
    parse_payload,
)

__all__ = [
    "SCHEMA_VERSION",
    "CommandStatus",
    "MessageType",
    "envelope",
    "parse_envelope",
    "Pose2D",
    "MissionType",
    "RuntimeStatusPayload",
    "FaultPayload",
    "FaultArrayPayload",
    "RuntimeMetricsPayload",
    "ControlCommandPayload",
    "TrajectoryPointPayload",
    "TrajectoryPayload",
    "MissionCommandPayload",
    "MissionFeedbackPayload",
    "MissionResultPayload",
    "encode_payload",
    "parse_payload",
]

