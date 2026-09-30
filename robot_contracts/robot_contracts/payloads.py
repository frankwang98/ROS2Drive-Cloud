"""Typed payload shapes for v2 envelope messages.

Each payload mirrors a ROS 2 message from `ros2_car` and provides a
dataclass-based JSON-friendly view used by Gateway (encode) and any
downstream consumer (parse).

Why dataclass + manual JSON, not Pydantic:
    robot_contracts is the single source of truth for the wire schema;
    Pydantic would force a runtime dependency on every transport. By
    keeping JSON serialization in this module, transports stay thin
    and the schema remains transport-agnostic.
"""
from __future__ import annotations

import math
from dataclasses import asdict, dataclass, fields
from typing import Any, Callable

from .models import PAYLOAD_TYPES, MessageType, register_payload


def _finite_float(value: float) -> float:
    """Replace NaN/Inf with 0.0 so the payload stays JSON-encodable."""
    if not math.isfinite(value):
        return 0.0
    return float(value)


# ---------------------------------------------------------------------------
# Common primitives
# ---------------------------------------------------------------------------


@dataclass
class Pose2D:
    x: float = 0.0
    y: float = 0.0
    theta: float = 0.0

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Pose2D":
        return cls(
            x=_finite_float(data.get("x", 0.0)),
            y=_finite_float(data.get("y", 0.0)),
            theta=_finite_float(data.get("theta", 0.0)),
        )


class MissionType(int):
    """Mirror of ExecuteMission.action mission_type enum."""

    NAVIGATE_TO = 0
    FOLLOW_ROUTE = 1
    STOP = 2
    PARK = 3
    DOCK = 4
    RETURN_HOME = 5

    @classmethod
    def to_string(cls, value: int) -> str:
        return {
            cls.NAVIGATE_TO: "NAVIGATE_TO",
            cls.FOLLOW_ROUTE: "FOLLOW_ROUTE",
            cls.STOP: "STOP",
            cls.PARK: "PARK",
            cls.DOCK: "DOCK",
            cls.RETURN_HOME: "RETURN_HOME",
        }.get(value, f"UNKNOWN({value})")


# ---------------------------------------------------------------------------
# Vehicle → Cloud typed payloads
# ---------------------------------------------------------------------------


@dataclass
class RuntimeStatusPayload:
    """Mirrors ros2_car/msg/RuntimeStatus.msg."""

    runtime_state: str = ""
    mission_id: str = ""
    mission_type: str = ""  # string form of MissionType (per docs/interfaces.md)
    mission_state: str = ""
    mission_progress: float = 0.0
    result_reason: str = ""
    localized: bool = False
    healthy: bool = False
    recovery_required: bool = False
    recovery_ready: bool = False

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "RuntimeStatusPayload":
        return cls(
            runtime_state=str(data.get("runtime_state", "")),
            mission_id=str(data.get("mission_id", "")),
            mission_type=str(data.get("mission_type", "")),
            mission_state=str(data.get("mission_state", "")),
            mission_progress=_finite_float(data.get("mission_progress", 0.0)),
            result_reason=str(data.get("result_reason", "")),
            localized=bool(data.get("localized", False)),
            healthy=bool(data.get("healthy", False)),
            recovery_required=bool(data.get("recovery_required", False)),
            recovery_ready=bool(data.get("recovery_ready", False)),
        )


@dataclass
class FaultPayload:
    """Mirrors ros2_car/msg/Fault.msg."""

    code: str = ""
    severity: int = 0  # 0=INFO, 1=WARNING, 2=ERROR, 3=FATAL
    message: str = ""
    active: bool = True

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "FaultPayload":
        return cls(
            code=str(data.get("code", "")),
            severity=int(data.get("severity", 0)),
            message=str(data.get("message", "")),
            active=bool(data.get("active", True)),
        )


@dataclass
class FaultArrayPayload:
    """Mirrors ros2_car/msg/FaultArray.msg."""

    faults: list[FaultPayload] = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        if self.faults is None:
            self.faults = []

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "FaultArrayPayload":
        raw = data.get("faults", [])
        return cls(faults=[FaultPayload.from_dict(item) for item in raw])


@dataclass
class RuntimeMetricsPayload:
    """Mirrors ros2_car/msg/RuntimeMetrics.msg."""

    loop_duration_ms: float = 0.0
    configured_loop_hz: float = 0.0
    trajectory_points: int = 0
    active_faults: int = 0
    runtime_state: int = 0  # enum value, mirrored from RuntimeStatus

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "RuntimeMetricsPayload":
        return cls(
            loop_duration_ms=_finite_float(data.get("loop_duration_ms", 0.0)),
            configured_loop_hz=_finite_float(data.get("configured_loop_hz", 0.0)),
            trajectory_points=int(data.get("trajectory_points", 0)),
            active_faults=int(data.get("active_faults", 0)),
            runtime_state=int(data.get("runtime_state", 0)),
        )


@dataclass
class ControlCommandPayload:
    """Mirrors ros2_car/msg/ControlCommand.msg."""

    target_speed: float = 0.0
    steering_angle: float = 0.0
    brake: float = 0.0
    emergency_stop: bool = False

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ControlCommandPayload":
        return cls(
            target_speed=_finite_float(data.get("target_speed", 0.0)),
            steering_angle=_finite_float(data.get("steering_angle", 0.0)),
            brake=_finite_float(data.get("brake", 0.0)),
            emergency_stop=bool(data.get("emergency_stop", False)),
        )


@dataclass
class TrajectoryPointPayload:
    """Mirrors ros2_car/msg/TrajectoryPoint.msg."""

    pose: Pose2D = None  # type: ignore[assignment]
    curvature: float = 0.0
    velocity: float = 0.0
    acceleration: float = 0.0
    relative_time: float = 0.0
    stop_required: bool = False

    def __post_init__(self) -> None:
        if self.pose is None:
            self.pose = Pose2D()

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "TrajectoryPointPayload":
        pose_raw = data.get("pose", {})
        return cls(
            pose=Pose2D.from_dict(pose_raw) if isinstance(pose_raw, dict) else Pose2D(),
            curvature=_finite_float(data.get("curvature", 0.0)),
            velocity=_finite_float(data.get("velocity", 0.0)),
            acceleration=_finite_float(data.get("acceleration", 0.0)),
            relative_time=_finite_float(data.get("relative_time", 0.0)),
            stop_required=bool(data.get("stop_required", False)),
        )


@dataclass
class TrajectoryPayload:
    """Mirrors ros2_car/msg/Trajectory.msg."""

    mission_id: str = ""
    points: list[TrajectoryPointPayload] = None  # type: ignore[assignment]
    valid: bool = True

    def __post_init__(self) -> None:
        if self.points is None:
            self.points = []

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "TrajectoryPayload":
        raw = data.get("points", [])
        return cls(
            mission_id=str(data.get("mission_id", "")),
            points=[TrajectoryPointPayload.from_dict(item) for item in raw],
            valid=bool(data.get("valid", True)),
        )


# ---------------------------------------------------------------------------
# Cloud → Vehicle typed payloads
# ---------------------------------------------------------------------------


@dataclass
class MissionCommandPayload:
    """Mirrors ros2_car/action/ExecuteMission.action goal."""

    mission_id: str = ""
    mission_type: int = MissionType.NAVIGATE_TO
    route: list[Pose2D] = None  # type: ignore[assignment]
    speed_limit: float = 0.0
    goal_tolerance: float = 0.5
    timeout_s: float = 0.0
    allow_preempt: bool = False

    def __post_init__(self) -> None:
        if self.route is None:
            self.route = []

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "MissionCommandPayload":
        raw = data.get("route", [])
        return cls(
            mission_id=str(data.get("mission_id", "")),
            mission_type=int(data.get("mission_type", MissionType.NAVIGATE_TO)),
            route=[Pose2D.from_dict(item) for item in raw if isinstance(item, dict)],
            speed_limit=_finite_float(data.get("speed_limit", 0.0)),
            goal_tolerance=_finite_float(data.get("goal_tolerance", 0.5)),
            timeout_s=_finite_float(data.get("timeout_s", 0.0)),
            allow_preempt=bool(data.get("allow_preempt", False)),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "mission_id": self.mission_id,
            "mission_type": self.mission_type,
            "mission_type_name": MissionType.to_string(self.mission_type),
            "route": [asdict(p) for p in self.route],
            "speed_limit": self.speed_limit,
            "goal_tolerance": self.goal_tolerance,
            "timeout_s": self.timeout_s,
            "allow_preempt": self.allow_preempt,
        }


@dataclass
class MissionFeedbackPayload:
    """Mirrors ros2_car/action/ExecuteMission.action feedback."""

    mission_id: str = ""
    state: str = ""
    progress: float = 0.0
    reason: str = ""

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "MissionFeedbackPayload":
        return cls(
            mission_id=str(data.get("mission_id", "")),
            state=str(data.get("state", "")),
            progress=_finite_float(data.get("progress", 0.0)),
            reason=str(data.get("reason", "")),
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class MissionResultPayload:
    """Mirrors ros2_car/action/ExecuteMission.action result."""

    mission_id: str = ""
    success: bool = False
    final_state: str = ""
    reason: str = ""

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "MissionResultPayload":
        return cls(
            mission_id=str(data.get("mission_id", "")),
            success=bool(data.get("success", False)),
            final_state=str(data.get("final_state", "")),
            reason=str(data.get("reason", "")),
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


# ---------------------------------------------------------------------------
# Encode / parse helpers
# ---------------------------------------------------------------------------


def encode_payload(payload: Any) -> dict[str, Any]:
    """Convert a typed payload dataclass to its JSON-ready dict form."""
    if hasattr(payload, "to_dict"):
        return payload.to_dict()
    return asdict(payload)


def parse_payload(message_type: str | MessageType, data: Any) -> Any:
    """Parse a dict payload into its typed dataclass.

    Raises ValueError when the type is unknown or the payload shape is wrong.
    """
    key = MessageType(message_type).value
    cls = PAYLOAD_TYPES.get(key)
    if cls is None:
        raise ValueError(f"no payload class registered for message_type={key}")
    if not isinstance(data, dict):
        raise ValueError(f"payload for {key} must be a dict, got {type(data).__name__}")
    return cls.from_dict(data)


# Register typed payloads. Kept at module bottom to break the circular import
# between models.py and payloads.py.
register_payload(MessageType.RUNTIME_STATUS.value, RuntimeStatusPayload)
register_payload(MessageType.FAULT.value, FaultArrayPayload)
register_payload(MessageType.METRICS.value, RuntimeMetricsPayload)
register_payload(MessageType.CONTROL.value, ControlCommandPayload)
register_payload(MessageType.TRAJECTORY.value, TrajectoryPayload)
register_payload(MessageType.MISSION_COMMAND.value, MissionCommandPayload)
register_payload(MessageType.MISSION_FEEDBACK.value, MissionFeedbackPayload)
register_payload(MessageType.MISSION_RESULT.value, MissionResultPayload)


__all__: list[str] = [
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
