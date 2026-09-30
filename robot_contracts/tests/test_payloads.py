"""Tests for v2 typed payloads and the upgraded envelope contract.

These tests are framework-free (no pytest dependency) so they run under
the bare ``python3 -m unittest`` provided by the standard library.
"""
from __future__ import annotations

import math
import sys
import unittest
from pathlib import Path

# Allow `python3 tests/test_payloads.py` from any cwd.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import robot_contracts
from robot_contracts import (
    SCHEMA_VERSION,
    CommandStatus,
    ControlCommandPayload,
    FaultArrayPayload,
    FaultPayload,
    MessageType,
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
    envelope,
    parse_envelope,
    parse_payload,
)


class EnvelopeContractTests(unittest.TestCase):
    def test_schema_version_is_v2(self) -> None:
        self.assertEqual(SCHEMA_VERSION, "2.0")
        self.assertEqual(robot_contracts.SCHEMA_VERSION, "2.0")

    def test_message_type_set_is_complete(self) -> None:
        # v1 carry-overs
        self.assertEqual(MessageType.TELEMETRY.value, "telemetry")
        self.assertEqual(MessageType.COMMAND.value, "command")
        self.assertEqual(MessageType.COMMAND_ACK.value, "command_ack")
        self.assertEqual(MessageType.HEARTBEAT.value, "heartbeat")
        # v2 typed topics
        self.assertEqual(MessageType.RUNTIME_STATUS.value, "runtime_status")
        self.assertEqual(MessageType.FAULT.value, "fault")
        self.assertEqual(MessageType.METRICS.value, "metrics")
        self.assertEqual(MessageType.CONTROL.value, "control")
        self.assertEqual(MessageType.TRAJECTORY.value, "trajectory")
        # v2 mission lifecycle
        self.assertEqual(MessageType.MISSION_COMMAND.value, "mission_command")
        self.assertEqual(MessageType.MISSION_FEEDBACK.value, "mission_feedback")
        self.assertEqual(MessageType.MISSION_RESULT.value, "mission_result")
        # v2 direct control
        self.assertEqual(MessageType.EMERGENCY_STOP.value, "emergency_stop")

    def test_envelope_v2_round_trip(self) -> None:
        env = envelope(
            robot_id="car01",
            message_type=MessageType.RUNTIME_STATUS,
            payload={"runtime_state": "DRIVING"},
            sequence=7,
            message_id="m-id-1",
            timestamp=1.0,
        )
        self.assertEqual(env["schema_version"], "2.0")
        self.assertEqual(env["robot_id"], "car01")
        self.assertEqual(env["sequence"], 7)
        self.assertEqual(env["type"], "runtime_status")
        parsed = parse_envelope(env)
        self.assertEqual(parsed["schema_version"], "2.0")

    def test_parse_envelope_rejects_wrong_schema(self) -> None:
        bad = {
            "schema_version": "1.0",
            "message_id": "x",
            "robot_id": "car01",
            "timestamp": 0.0,
            "sequence": 1,
            "type": "telemetry",
            "payload": {},
        }
        with self.assertRaises(ValueError):
            parse_envelope(bad)


class PayloadRoundTripTests(unittest.TestCase):
    def test_runtime_status_round_trip(self) -> None:
        data = {
            "runtime_state": "DRIVING",
            "mission_id": "m-001",
            "mission_type": "NAVIGATE_TO",
            "mission_state": "EXECUTING",
            "mission_progress": 0.42,
            "result_reason": "",
            "localized": True,
            "healthy": True,
            "recovery_required": False,
            "recovery_ready": False,
        }
        parsed = parse_payload(MessageType.RUNTIME_STATUS, data)
        self.assertIsInstance(parsed, RuntimeStatusPayload)
        self.assertEqual(parsed.runtime_state, "DRIVING")
        self.assertEqual(parsed.mission_id, "m-001")
        self.assertTrue(parsed.localized)
        self.assertEqual(encode_payload(parsed), data)

    def test_fault_array_round_trip(self) -> None:
        data = {
            "faults": [
                {"code": "LOCA_TIMEOUT", "severity": 2, "message": "loc lost", "active": True},
                {"code": "PLAN_FAIL", "severity": 1, "message": "no path", "active": False},
            ]
        }
        parsed = parse_payload(MessageType.FAULT, data)
        self.assertIsInstance(parsed, FaultArrayPayload)
        self.assertEqual(len(parsed.faults), 2)
        self.assertIsInstance(parsed.faults[0], FaultPayload)
        self.assertEqual(parsed.faults[0].code, "LOCA_TIMEOUT")
        self.assertEqual(parsed.faults[0].severity, 2)
        # active: false must round-trip
        self.assertEqual(encode_payload(parsed), data)

    def test_runtime_metrics_round_trip(self) -> None:
        data = {
            "loop_duration_ms": 12.5,
            "configured_loop_hz": 50.0,
            "trajectory_points": 32,
            "active_faults": 1,
            "runtime_state": 2,
        }
        parsed = parse_payload(MessageType.METRICS, data)
        self.assertIsInstance(parsed, RuntimeMetricsPayload)
        self.assertEqual(parsed.trajectory_points, 32)
        self.assertEqual(encode_payload(parsed), data)

    def test_control_command_round_trip(self) -> None:
        data = {
            "target_speed": 1.2,
            "steering_angle": 0.05,
            "brake": 0.0,
            "emergency_stop": False,
        }
        parsed = parse_payload(MessageType.CONTROL, data)
        self.assertIsInstance(parsed, ControlCommandPayload)
        self.assertEqual(parsed.target_speed, 1.2)
        self.assertEqual(encode_payload(parsed), data)

    def test_trajectory_round_trip(self) -> None:
        data = {
            "mission_id": "m-002",
            "valid": True,
            "points": [
                {
                    "pose": {"x": 1.0, "y": 2.0, "theta": 0.5},
                    "curvature": 0.1,
                    "velocity": 1.5,
                    "acceleration": 0.0,
                    "relative_time": 0.5,
                    "stop_required": False,
                },
                {
                    "pose": {"x": 2.0, "y": 3.0, "theta": 0.6},
                    "curvature": 0.0,
                    "velocity": 0.0,
                    "acceleration": -1.0,
                    "relative_time": 1.0,
                    "stop_required": True,
                },
            ],
        }
        parsed = parse_payload(MessageType.TRAJECTORY, data)
        self.assertIsInstance(parsed, TrajectoryPayload)
        self.assertEqual(len(parsed.points), 2)
        self.assertIsInstance(parsed.points[0], TrajectoryPointPayload)
        self.assertIsInstance(parsed.points[0].pose, Pose2D)
        self.assertEqual(parsed.points[0].pose.x, 1.0)
        self.assertTrue(parsed.points[1].stop_required)
        self.assertEqual(encode_payload(parsed), data)


class MissionPayloadTests(unittest.TestCase):
    def test_mission_command_to_dict_carries_mission_type_name(self) -> None:
        m = MissionCommandPayload(
            mission_id="m-003",
            mission_type=MissionType.FOLLOW_ROUTE,
            route=[Pose2D(x=1.0, y=2.0, theta=0.0)],
            speed_limit=1.5,
            goal_tolerance=0.3,
            timeout_s=60.0,
            allow_preempt=True,
        )
        d = m.to_dict()
        self.assertEqual(d["mission_id"], "m-003")
        self.assertEqual(d["mission_type"], MissionType.FOLLOW_ROUTE)
        self.assertEqual(d["mission_type_name"], "FOLLOW_ROUTE")
        self.assertEqual(d["route"][0]["x"], 1.0)
        self.assertTrue(d["allow_preempt"])

    def test_mission_command_from_dict(self) -> None:
        data = {
            "mission_id": "m-004",
            "mission_type": 4,  # DOCK
            "route": [{"x": 0.0, "y": 0.0, "theta": 0.0}],
            "speed_limit": 0.8,
            "goal_tolerance": 0.2,
            "timeout_s": 30.0,
            "allow_preempt": False,
        }
        m = parse_payload(MessageType.MISSION_COMMAND, data)
        self.assertIsInstance(m, MissionCommandPayload)
        self.assertEqual(m.mission_type, MissionType.DOCK)
        d = m.to_dict()
        self.assertEqual(d["mission_type_name"], "DOCK")

    def test_mission_feedback_round_trip(self) -> None:
        data = {"mission_id": "m-005", "state": "EXECUTING", "progress": 0.5, "reason": ""}
        fb = parse_payload(MessageType.MISSION_FEEDBACK, data)
        self.assertIsInstance(fb, MissionFeedbackPayload)
        self.assertEqual(fb.progress, 0.5)
        self.assertEqual(fb.to_dict(), data)

    def test_mission_result_round_trip(self) -> None:
        data = {"mission_id": "m-006", "success": True, "final_state": "ARRIVED", "reason": "goal reached"}
        r = parse_payload(MessageType.MISSION_RESULT, data)
        self.assertIsInstance(r, MissionResultPayload)
        self.assertTrue(r.success)
        self.assertEqual(r.final_state, "ARRIVED")
        self.assertEqual(r.to_dict(), data)


class DefensiveTests(unittest.TestCase):
    def test_nan_inf_clamped_to_zero(self) -> None:
        m = parse_payload(
            MessageType.CONTROL,
            {"target_speed": float("nan"), "steering_angle": float("inf"),
             "brake": float("-inf"), "emergency_stop": False},
        )
        self.assertEqual(m.target_speed, 0.0)
        self.assertEqual(m.steering_angle, 0.0)
        self.assertEqual(m.brake, 0.0)

    def test_unknown_type_raises(self) -> None:
        with self.assertRaises(ValueError):
            parse_payload("not_a_type", {})

    def test_non_dict_payload_raises(self) -> None:
        with self.assertRaises(ValueError):
            parse_payload(MessageType.RUNTIME_STATUS, [1, 2, 3])

    def test_missing_faults_defaults_to_empty(self) -> None:
        m = parse_payload(MessageType.FAULT, {})
        self.assertEqual(m.faults, [])


class CommandStatusRegressionTests(unittest.TestCase):
    """v1 CommandStatus enum must remain unchanged for legacy ACK payload."""

    def test_command_status_values(self) -> None:
        self.assertEqual(CommandStatus.SUCCEEDED.value, "SUCCEEDED")
        self.assertEqual(CommandStatus.REJECTED.value, "REJECTED")
        self.assertEqual(CommandStatus.TIMEOUT.value, "TIMEOUT")
        self.assertEqual(CommandStatus.EXPIRED.value, "EXPIRED")


if __name__ == "__main__":
    unittest.main()
