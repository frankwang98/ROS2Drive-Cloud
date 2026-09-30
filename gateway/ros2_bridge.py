"""ROS 2 ⇄ MQTT bridge for ROS2Drive Cloud (v2 protocol).

Vehicle → Cloud (uplink):
    ROS 2 typed topics (runtime/status, runtime/faults, runtime/metrics,
    control/command, planning/trajectory) plus legacy sdc/* scalars
    → MQTT envelopes on robots/{robot_id}/{runtime|control|planning|...|telemetry}

Cloud → Vehicle (downlink):
    robots/{robot_id}/missions/command      → mission/execute Action goal
    robots/{robot_id}/missions/feedback    → action feedback (republished)
    robots/{robot_id}/missions/result      → action result (republished)
    robots/{robot_id}/emergency_stop       → sdc/emergency_stop (Bool)
    robots/{robot_id}/commands             → legacy sdc/control_algo / pause / clear_trail

The Cloud never sees ROS 2 types directly: the bridge is the only
translation point. That is the central architectural rule documented in
README.md.
"""
from __future__ import annotations

import argparse
import json
import logging
import math
import os
import sys
import threading
import time
from dataclasses import asdict
from itertools import count
from pathlib import Path

# Make the sibling `robot_contracts/` package importable when this script is
# run as `python3 gateway/ros2_bridge.py` without manually setting PYTHONPATH.
# Order matters — insert at front so the in-tree package wins over any
# system-installed `robot_contracts` from a stale environment.
_CONTRACTS_DIR = (Path(__file__).resolve().parent.parent / "robot_contracts").resolve()
if str(_CONTRACTS_DIR) not in sys.path:
    sys.path.insert(0, str(_CONTRACTS_DIR))

# Robot contracts is the v2 wire schema; envelope() always emits
# schema_version=2.0 after the M1 upgrade.
from robot_contracts import (
    CommandStatus,
    ControlCommandPayload,
    FaultArrayPayload,
    MessageType,
    MissionCommandPayload,
    MissionFeedbackPayload,
    MissionResultPayload,
    MissionType,
    RuntimeMetricsPayload,
    RuntimeStatusPayload,
    TrajectoryPayload,
    encode_payload,
    envelope,
    parse_envelope,
    parse_payload,
)

logger = logging.getLogger("ros2_bridge")

try:
    import paho.mqtt.client as mqtt  # type: ignore
    HAS_MQTT = True
except ImportError:  # pragma: no cover
    HAS_MQTT = False


# ---------------------------------------------------------------------------
# ROS 2 ↔ payload conversion helpers
# ---------------------------------------------------------------------------


def _quat_to_yaw(q) -> float:
    """Convert a geometry_msgs/Quaternion to yaw (rotation around Z)."""
    return math.atan2(
        2.0 * (q.w * q.z + q.x * q.y),
        1.0 - 2.0 * (q.y * q.y + q.z * q.z),
    )


def runtime_status_from_msg(msg) -> RuntimeStatusPayload:
    """Convert self_driving_car_demo/msg/RuntimeStatus → typed payload."""
    return RuntimeStatusPayload(
        runtime_state=str(getattr(msg, "runtime_state", "")),
        mission_id=str(getattr(msg, "mission_id", "")),
        mission_type=str(getattr(msg, "mission_type", "")),
        mission_state=str(getattr(msg, "mission_state", "")),
        mission_progress=float(getattr(msg, "mission_progress", 0.0)),
        result_reason=str(getattr(msg, "result_reason", "")),
        localized=bool(getattr(msg, "localized", False)),
        healthy=bool(getattr(msg, "healthy", False)),
        recovery_required=bool(getattr(msg, "recovery_required", False)),
        recovery_ready=bool(getattr(msg, "recovery_ready", False)),
    )


def fault_array_from_msg(msg) -> FaultArrayPayload:
    from robot_contracts import FaultPayload
    raw_faults = list(getattr(msg, "faults", []) or [])
    faults = [
        FaultPayload(
            code=str(getattr(f, "code", "")),
            severity=int(getattr(f, "severity", 0)),
            message=str(getattr(f, "message", "")),
            active=bool(getattr(f, "active", True)),
        )
        for f in raw_faults
    ]
    return FaultArrayPayload(faults=faults)


def runtime_metrics_from_msg(msg) -> RuntimeMetricsPayload:
    return RuntimeMetricsPayload(
        loop_duration_ms=float(getattr(msg, "loop_duration_ms", 0.0)),
        configured_loop_hz=float(getattr(msg, "configured_loop_hz", 0.0)),
        trajectory_points=int(getattr(msg, "trajectory_points", 0)),
        active_faults=int(getattr(msg, "active_faults", 0)),
        runtime_state=int(getattr(msg, "runtime_state", 0)),
    )


def control_command_from_msg(msg) -> ControlCommandPayload:
    return ControlCommandPayload(
        target_speed=float(getattr(msg, "target_speed", 0.0)),
        steering_angle=float(getattr(msg, "steering_angle", 0.0)),
        brake=float(getattr(msg, "brake", 0.0)),
        emergency_stop=bool(getattr(msg, "emergency_stop", False)),
    )


def trajectory_point_from_msg(p) -> dict:
    pose = getattr(p, "pose", None)
    if pose is not None:
        position = pose.position
        orientation = pose.orientation
        yaw = _quat_to_yaw(orientation)
        pose_dict = {"x": position.x, "y": position.y, "theta": yaw}
    else:
        pose_dict = {"x": 0.0, "y": 0.0, "theta": 0.0}
    return {
        "pose": pose_dict,
        "curvature": float(getattr(p, "curvature", 0.0)),
        "velocity": float(getattr(p, "velocity", 0.0)),
        "acceleration": float(getattr(p, "acceleration", 0.0)),
        "relative_time": float(getattr(p, "relative_time", 0.0)),
        "stop_required": bool(getattr(p, "stop_required", False)),
    }


def trajectory_payload_from_msg(msg) -> TrajectoryPayload:
    raw_points = list(getattr(msg, "points", []) or [])
    point_dicts = [trajectory_point_from_msg(p) for p in raw_points]
    data = {
        "mission_id": str(getattr(msg, "mission_id", "")),
        "valid": bool(getattr(msg, "valid", True)),
        "points": point_dicts,
    }
    return parse_payload(MessageType.TRAJECTORY, data)


# ---------------------------------------------------------------------------
# Legacy sdc/* topics (kept for backwards compatibility)
# ---------------------------------------------------------------------------

LEGACY_TOPIC_SCHEMA = {
    "sdc/speed": ("Float64", "speed"),
    "sdc/action_id": ("Float64", "action_id"),
    "sdc/front_distance": ("Float64", "front_distance"),
    "sdc/obstacle_count": ("Float64", "obstacle_count"),
    "sdc/odometry": ("Odometry", "odometry"),
}

LEGACY_COMMAND_SCHEMA = {
    "control_algo": ("sdc/control_algo", "Int32", True),
    "pause": ("sdc/pause", "Bool", True),
    "clear_trail": ("sdc/clear_trail", "Bool", False),
}

ACTION_ALIAS = {
    "set_control_algo": "control_algo",
    "set_paused": "pause",
}


def legacy_odometry_value(msg) -> dict:
    q = msg.pose.pose.orientation
    yaw = _quat_to_yaw(q)
    return {
        "pose": {
            "x": msg.pose.pose.position.x,
            "y": msg.pose.pose.position.y,
            "yaw": yaw,
        },
        "velocity": {
            "linear": msg.twist.twist.linear.x,
            "angular": msg.twist.twist.angular.z,
        },
    }


def legacy_scalar_value(msg) -> float:
    return getattr(msg, "data", None)


# ---------------------------------------------------------------------------
# Mission Action bridge
# ---------------------------------------------------------------------------


class MissionActionBridge:
    """Thin wrapper around rclpy_action.ActionClient for mission/execute.

    Goal envelopes arrive on robots/{id}/missions/command. The bridge sends
    them as Action goals and republishes feedback/result envelopes back to
    MQTT on robots/{id}/missions/feedback and /missions/result.
    """

    def __init__(self, node, action_client, robot_id: str, sequence_counter):
        self._node = node
        self._client = action_client
        self._robot_id = robot_id
        self._sequence = sequence_counter
        self._pending: set[str] = set()
        self._mission_commands: dict[str, str] = {}
        self._active_goals: dict[str, object] = {}  # mission_id → goal_handle
        self._mqtt_client = None  # wired by attach_mqtt() after build_bridge()

    def attach_mqtt(self, mqtt_client) -> None:
        self._mqtt_client = mqtt_client

    def _publish(self, topic: str, msg_type, payload: dict) -> None:
        if self._mqtt_client is None:
            logger.debug("MQTT client not yet wired, dropping %s", topic)
            return
        env = envelope(
            robot_id=self._robot_id,
            message_type=msg_type,
            payload=payload,
            sequence=next(self._sequence),
        )
        self._mqtt_client.publish(topic, json.dumps(env), qos=1)

    def ack(self, command_id: str, status: str, detail: str = "") -> None:
        self._publish(f"robots/{self._robot_id}/command_ack", MessageType.COMMAND_ACK,
                      {"command_id": command_id, "status": status, "detail": detail})

    def send_goal(self, payload: MissionCommandPayload, command_id: str = "") -> str:
        mission_id = payload.mission_id
        if mission_id in self._mission_commands:
            self.ack(command_id, "REJECTED", "mission_id already submitted")
            return mission_id
        if not self._client.server_is_ready():
            self.ack(command_id, "REJECTED", "mission Action server unavailable")
            return mission_id
        try:
            goal_msg = self._build_goal_msg(payload)
            self._pending.add(mission_id)
            self._mission_commands[mission_id] = command_id
            send_future = self._client.send_goal_async(
                goal_msg, feedback_callback=lambda msg: self._on_feedback(msg, mission_id))
            send_future.add_done_callback(self._on_goal_response(mission_id))
        except Exception as exc:
            self._pending.discard(mission_id)
            self._mission_commands.pop(mission_id, None)
            self.ack(command_id, "FAILED", str(exc))
        return mission_id

    def cancel(self, mission_id: str, command_id: str) -> None:
        handle = self._active_goals.get(mission_id)
        if handle is None:
            self.ack(command_id, "REJECTED", "mission not active; wait for vehicle acceptance")
            return
        def done(future):
            try:
                accepted = bool(future.result().goals_canceling)
                self.ack(command_id, "ACCEPTED" if accepted else "REJECTED", "cancel request")
            except Exception as exc:
                self.ack(command_id, "FAILED", str(exc))
        handle.cancel_goal_async().add_done_callback(done)

    def _build_goal_msg(self, payload: MissionCommandPayload):
        """Build the ROS 2 ExecuteMission goal message from a typed payload."""
        # Import here to avoid importing ROS at module load time (gateway must
        # still be importable from plain Python for tests).
        from self_driving_car_demo.action import ExecuteMission  # type: ignore

        goal = ExecuteMission.Goal()
        goal.mission_id = payload.mission_id
        goal.mission_type = int(payload.mission_type)
        goal.route = []
        from geometry_msgs.msg import Pose2D as _Pose2D  # type: ignore
        for pose in payload.route:
            ros_pose = _Pose2D()
            ros_pose.x = float(pose.x)
            ros_pose.y = float(pose.y)
            ros_pose.theta = float(pose.theta)
            goal.route.append(ros_pose)
        goal.speed_limit = float(payload.speed_limit)
        goal.goal_tolerance = float(payload.goal_tolerance)
        goal.timeout_s = float(payload.timeout_s)
        goal.allow_preempt = bool(payload.allow_preempt)
        return goal

    def _on_goal_response(self, mission_id: str):
        def _cb(future):
            self._pending.discard(mission_id)
            try:
                goal_handle = future.result()
            except Exception as exc:
                self.ack(self._mission_commands.get(mission_id, ""), "FAILED", str(exc))
                return
            if goal_handle is None or not goal_handle.accepted:
                logger.warning("Mission %s rejected by vehicle", mission_id)
                self.ack(self._mission_commands.get(mission_id, ""), "REJECTED", "vehicle rejected goal")
                result_payload = MissionResultPayload(
                    mission_id=mission_id,
                    success=False,
                    final_state="REJECTED",
                    reason="vehicle rejected goal",
                )
                self._publish(
                    f"robots/{self._robot_id}/missions/result",
                    MessageType.MISSION_RESULT,
                    encode_payload(result_payload),
                )
                return
            self._active_goals[mission_id] = goal_handle
            self.ack(self._mission_commands.get(mission_id, ""), "ACCEPTED", "vehicle accepted mission")
            logger.info("Mission %s accepted by vehicle", mission_id)
            result_future = goal_handle.get_result_async()
            result_future.add_done_callback(self._on_result(mission_id))

        return _cb

    def _on_feedback(self, feedback_msg, mission_id: str):
        try:
            fb = feedback_msg.feedback
            payload = MissionFeedbackPayload(
                mission_id=mission_id,
                state=str(getattr(fb, "state", "")),
                progress=float(getattr(fb, "progress", 0.0)),
                reason=str(getattr(fb, "reason", "")),
            )
        except Exception as exc:  # noqa: BLE001
            logger.error("Bad feedback payload: %s", exc)
            return
        self._publish(
            f"robots/{self._robot_id}/missions/feedback",
            MessageType.MISSION_FEEDBACK,
            encode_payload(payload),
        )

    def _on_result(self, mission_id: str):
        def _cb(future):
            try:
                wrapped = future.result()
                r = wrapped.result
                payload = MissionResultPayload(
                    mission_id=mission_id,
                    success=bool(getattr(r, "success", False)),
                    final_state=str(getattr(r, "final_state", "")),
                    reason=str(getattr(r, "reason", "")),
                )
            except Exception as exc:  # noqa: BLE001
                logger.error("Mission %s result error: %s", mission_id, exc)
                payload = MissionResultPayload(
                    mission_id=mission_id,
                    success=False,
                    final_state="ERROR",
                    reason=str(exc),
                )
            self._active_goals.pop(mission_id, None)
            command_id = self._mission_commands.get(mission_id, "")
            final_state = payload.final_state if payload.final_state in ("SUCCEEDED", "FAILED", "CANCELED") else ("SUCCEEDED" if payload.success else "FAILED")
            self.ack(command_id, final_state, payload.reason)
            if len(self._mission_commands) > 1024:
                for old in list(self._mission_commands):
                    if old not in self._active_goals and old not in self._pending:
                        del self._mission_commands[old]
                        break
            self._publish(
                f"robots/{self._robot_id}/missions/result",
                MessageType.MISSION_RESULT,
                encode_payload(payload),
            )
        return _cb


# ---------------------------------------------------------------------------
# Command forwarder (legacy + emergency_stop)
# ---------------------------------------------------------------------------


class CommandForwarder:
    """Forwards Cloud commands to ROS 2 (legacy sdc/* + emergency_stop)."""

    def __init__(self, robot_id: str, ros_publishers: dict, recovery_client=None) -> None:
        self.robot_id = robot_id
        self.ros_publishers = ros_publishers
        self.recovery_client = recovery_client
        self._processed: dict[str, tuple[str, str | None]] = {}

    def _publish_bool(self, ros_topic: str, value) -> bool:
        from std_msgs.msg import Bool
        pub = self.ros_publishers.get(ros_topic)
        if pub is None:
            logger.warning("未找到 ROS2 发布器: %s", ros_topic)
            return False
        msg = Bool()
        if not isinstance(value, bool):
            raise ValueError("Bool command requires an explicit boolean")
        msg.data = value
        pub.publish(msg)
        logger.info("下行指令已转发到 ROS2: %s = %s", ros_topic, msg.data)
        return True

    def _publish_int(self, ros_topic: str, value) -> bool:
        from std_msgs.msg import Int32
        pub = self.ros_publishers.get(ros_topic)
        if pub is None:
            return False
        msg = Int32()
        if type(value) is not int or value not in (0, 1, 2, 3):
            raise ValueError("control_algo requires an integer from 0 to 3")
        msg.data = value
        pub.publish(msg)
        return True

    def set_emergency_stop(self, value: bool) -> None:
        self._publish_bool("sdc/emergency_stop", value)

    def handle_legacy_command(self, command_topic: str, payload: dict) -> tuple[str, str | None]:
        topic = payload.get("topic", "")
        if "/command/" in topic:
            cmd = topic.rsplit("/command/", 1)[-1]
        else:
            cmd = payload.get("action") or payload.get("command")
        value = payload.get("data", payload.get("value"))

        if not cmd:
            return CommandStatus.REJECTED.value, "missing action"
        cmd = ACTION_ALIAS.get(cmd, cmd)

        spec = LEGACY_COMMAND_SCHEMA.get(cmd)
        if spec is None:
            return CommandStatus.REJECTED.value, f"unknown command: {cmd}"
        ros_topic, msg_type, require_value = spec
        if require_value and value is None:
            return CommandStatus.REJECTED.value, "missing value"
        if not require_value and value is None:
            value = True

        if msg_type == "Int32":
            ok = self._publish_int(ros_topic, value)
        elif msg_type == "Bool":
            ok = self._publish_bool(ros_topic, value)
        else:
            return CommandStatus.REJECTED.value, f"unsupported type: {msg_type}"

        return (CommandStatus.SUCCEEDED.value if ok else CommandStatus.FAILED.value,
                None if ok else "ROS publisher unavailable")


# ---------------------------------------------------------------------------
# MQTT bridge wiring
# ---------------------------------------------------------------------------


def _make_mqtt_publisher(client, robot_id: str):
    """Return a function that publishes a typed envelope to a topic."""
    def _publish(topic: str, msg_type, payload: dict, sequence: int) -> None:
        env = envelope(
            robot_id=robot_id,
            message_type=msg_type,
            payload=payload,
            sequence=sequence,
        )
        client.publish(topic, json.dumps(env), qos=1)

    return _publish


def build_bridge(robot_id: str, mqtt_broker: str, mqtt_port: int,
                 command_forwarder: CommandForwarder,
                 mission_bridge: MissionActionBridge | None):
    """Construct MQTT client + topic subscriptions; return callback hooks."""
    if not HAS_MQTT:
        raise RuntimeError("MQTT is required: install paho-mqtt")

    sequence = count(1)
    mqtt_client = mqtt.Client(callback_api_version=mqtt.CallbackAPIVersion.VERSION2)

    publish = _make_mqtt_publisher(mqtt_client, robot_id)

    def next_seq() -> int:
        return next(sequence)

    receipt_cache = {}
    mission_receipts = set()
    cancel_receipts = set()

    def publish_ack(command_id, status, detail=""):
        receipt_cache[command_id] = (status, detail)
        if len(receipt_cache) > 1024:
            del receipt_cache[next(iter(receipt_cache))]
        ack = envelope(robot_id, MessageType.COMMAND_ACK,
                       {"command_id": command_id, "status": status, "detail": detail}, sequence=next_seq())
        mqtt_client.publish(f"robots/{robot_id}/command_ack", json.dumps(ack), qos=1)

    def checked_message(msg, kind):
        try:
            message = parse_envelope(json.loads(msg.payload.decode("utf-8")))
            if message["robot_id"] != robot_id or message["type"] != kind.value:
                return message, "REJECTED"
            if message["payload"].get("expires_at", float("inf")) < time.time():
                return message, "EXPIRED"
            return message, None
        except (ValueError, TypeError, KeyError):
            logger.warning("Invalid envelope on %s", msg.topic)
            return None, "REJECTED"

    # ---- legacy command topic (kept for compatibility) ----
    command_topic = f"robots/{robot_id}/commands"

    def on_legacy_command(client, _userdata, msg):
        try:
            message = parse_envelope(json.loads(msg.payload.decode("utf-8")))
        except Exception as exc:  # noqa: BLE001
            logger.error("解析下行指令失败: %s", exc)
            return
        command_id = message["message_id"]
        if message["payload"].get("action") == "acknowledge_recovery":
            if message["robot_id"] != robot_id or message["type"] != "command":
                publish_ack(command_id, "REJECTED", "wrong robot/type")
                return
            if message["payload"].get("expires_at", float("inf")) < time.time():
                publish_ack(command_id, "EXPIRED", "request expired")
                return
            if command_id in receipt_cache:
                status, detail = receipt_cache[command_id]
                publish_ack(command_id, status, detail)
                return
            recovery = command_forwarder.recovery_client
            if recovery is None or not recovery.service_is_ready():
                publish_ack(command_id, "REJECTED", "recovery service unavailable")
                return
            from std_srvs.srv import Trigger
            def recovery_done(future):
                try:
                    result = future.result()
                    publish_ack(command_id, "SUCCEEDED" if result.success else "REJECTED", result.message)
                except Exception as exc:
                    publish_ack(command_id, "FAILED", str(exc))
            publish_ack(command_id, "ACCEPTED", "recovery request submitted")
            recovery.call_async(Trigger.Request()).add_done_callback(recovery_done)
            return
        if command_id in command_forwarder._processed:
            status, detail = command_forwarder._processed[command_id]
        else:
            if message["robot_id"] != robot_id or message["type"] != MessageType.COMMAND.value:
                status, detail = CommandStatus.REJECTED.value, "wrong robot/type"
            elif message["payload"].get("expires_at", float("inf")) < time.time():
                status, detail = CommandStatus.EXPIRED.value, "command expired"
            else:
                try:
                    status, detail = command_forwarder.handle_legacy_command(msg.topic, message["payload"])
                except (ValueError, TypeError, OverflowError) as exc:
                    status, detail = CommandStatus.REJECTED.value, str(exc)
            command_forwarder._processed[command_id] = (status, detail)
            if len(command_forwarder._processed) > 1024:
                del command_forwarder._processed[next(iter(command_forwarder._processed))]
        ack = envelope(
            robot_id=robot_id,
            message_type=MessageType.COMMAND_ACK,
            payload={"command_id": command_id, "status": status, "detail": detail},
            sequence=next_seq(),
        )
        mqtt_client.publish(f"robots/{robot_id}/command_ack", json.dumps(ack), qos=1)

    mqtt_client.message_callback_add(command_topic, on_legacy_command)
    logger.info("已订阅 legacy 下行指令: %s", command_topic)

    # ---- emergency_stop topic ----
    estop_topic = f"robots/{robot_id}/emergency_stop"

    def on_emergency_stop(client, _userdata, msg):
        message, error = checked_message(msg, MessageType.EMERGENCY_STOP)
        if message is None:
            return
        value = message["payload"].get("value")
        if error:
            publish_ack(message["message_id"], error, "invalid/expired request")
        elif type(value) is not bool:
            publish_ack(message["message_id"], "REJECTED", "explicit boolean required")
        elif message["message_id"] in receipt_cache:
            status, detail = receipt_cache[message["message_id"]]
            publish_ack(message["message_id"], status, detail)
        else:
            ok = command_forwarder._publish_bool("sdc/emergency_stop", value)
            publish_ack(message["message_id"], "ACCEPTED" if ok else "FAILED", "forwarded to ROS; observe runtime status")

    mqtt_client.message_callback_add(estop_topic, on_emergency_stop)
    logger.info("已订阅 emergency_stop: %s", estop_topic)

    # ---- mission_command topic (v2 mission lifecycle) ----
    mission_cmd_topic = f"robots/{robot_id}/missions/command"

    def on_mission_command(client, _userdata, msg):
        message, error = checked_message(msg, MessageType.MISSION_COMMAND)
        if message is None:
            return
        if error:
            publish_ack(message["message_id"], error, "invalid/expired request")
            return
        if mission_bridge is None:
            publish_ack(message["message_id"], "REJECTED", "Mission bridge unavailable")
            return
        try:
            payload = parse_payload(MessageType.MISSION_COMMAND, message["payload"])
            if not payload.mission_id:
                raise ValueError("mission_id required")
            if message["message_id"] in mission_receipts:
                # Duplicate delivery must not resubmit a ROS Action goal.
                return
            mission_receipts.add(message["message_id"])
            if len(mission_receipts) > 2048:
                mission_receipts.clear()
                mission_receipts.add(message["message_id"])
            mission_bridge.send_goal(payload, message["message_id"])
        except Exception as exc:
            publish_ack(message["message_id"], "REJECTED", str(exc))

    mqtt_client.message_callback_add(mission_cmd_topic, on_mission_command)
    logger.info("已订阅 mission_command: %s", mission_cmd_topic)

    cancel_topic = f"robots/{robot_id}/missions/cancel"
    def on_cancel(client, userdata, msg):
        message, error = checked_message(msg, MessageType.MISSION_CANCEL)
        if message is None:
            return
        if error or mission_bridge is None:
            publish_ack(message["message_id"], error or "REJECTED", "cancel unavailable/expired")
            return
        if message["message_id"] in cancel_receipts:
            return
        cancel_receipts.add(message["message_id"])
        if len(cancel_receipts) > 2048:
            cancel_receipts.clear()
            cancel_receipts.add(message["message_id"])
        mission_bridge.cancel(message["payload"].get("mission_id", ""), message["message_id"])
    mqtt_client.message_callback_add(cancel_topic, on_cancel)

    def on_connect(client, userdata, flags, reason_code, properties=None):
        if getattr(reason_code, "value", reason_code) == 0:
            for topic in (command_topic, estop_topic, mission_cmd_topic, cancel_topic):
                client.subscribe(topic, qos=1)
    mqtt_client.on_connect = on_connect
    mqtt_client.reconnect_delay_set(min_delay=1, max_delay=10)
    mqtt_client.connect_async(mqtt_broker, mqtt_port, 60)
    mqtt_client.loop_start()

    # ---- heartbeat (keep legacy heartbeat alive for backend health detection) ----
    def heartbeat_loop():
        while True:
            env = envelope(
                robot_id=robot_id,
                message_type=MessageType.HEARTBEAT,
                payload={},
                sequence=next_seq(),
            )
            mqtt_client.publish(
                f"robots/{robot_id}/heartbeat", json.dumps(env), qos=1
            )
            time.sleep(2.0)

    threading.Thread(target=heartbeat_loop, daemon=True).start()

    return on_ros_topic_factory(mqtt_client, robot_id, next_seq), mqtt_client


def on_ros_topic_factory(mqtt_client, robot_id: str, next_seq):
    """Return a function that builds ROS 2 topic callbacks publishing to MQTT."""

    def publish(topic: str, msg_type_value, payload: dict):
        env = envelope(
            robot_id=robot_id,
            message_type=msg_type_value,
            payload=payload,
            sequence=next_seq(),
        )
        mqtt_client.publish(topic, json.dumps(env), qos=1)

    def publish_legacy_telemetry(topic_name: str, msg_type: str, msg):
        if msg_type == "Float64":
            value = legacy_scalar_value(msg)
        elif msg_type == "Odometry":
            value = legacy_odometry_value(msg)
        else:
            value = str(msg)
        publish(
            f"robots/{robot_id}/telemetry",
            MessageType.TELEMETRY,
            {"name": topic_name, "ros_type": msg_type, "value": value},
        )

    def publish_runtime_status(msg):
        payload = runtime_status_from_msg(msg)
        publish(
            f"robots/{robot_id}/runtime/status",
            MessageType.RUNTIME_STATUS,
            encode_payload(payload),
        )

    def publish_fault_array(msg):
        payload = fault_array_from_msg(msg)
        publish(
            f"robots/{robot_id}/runtime/faults",
            MessageType.FAULT,
            encode_payload(payload),
        )

    def publish_runtime_metrics(msg):
        payload = runtime_metrics_from_msg(msg)
        publish(
            f"robots/{robot_id}/runtime/metrics",
            MessageType.METRICS,
            encode_payload(payload),
        )

    def publish_control_command(msg):
        payload = control_command_from_msg(msg)
        publish(
            f"robots/{robot_id}/control/command",
            MessageType.CONTROL,
            encode_payload(payload),
        )

    def publish_trajectory(msg):
        payload = trajectory_payload_from_msg(msg)
        publish(
            f"robots/{robot_id}/planning/trajectory",
            MessageType.TRAJECTORY,
            encode_payload(payload),
        )

    return {
        # typed topics
        "runtime/status": publish_runtime_status,
        "runtime/faults": publish_fault_array,
        "runtime/metrics": publish_runtime_metrics,
        "control/command": publish_control_command,
        "planning/trajectory": publish_trajectory,
        # legacy
        "legacy": publish_legacy_telemetry,
    }


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main():
    logging.basicConfig(level=logging.INFO)
    parser = argparse.ArgumentParser(
        description="ROS2Drive Cloud Gateway (v2): ROS 2 ⇄ MQTT bridge"
    )
    parser.add_argument("--robot-id", default="car01", help="机器人 ID")
    parser.add_argument("--robot-namespace", default="",
                        help="ROS 2 namespace (matches ring_road.launch.py)")
    parser.add_argument("--mqtt-broker", default="localhost")
    parser.add_argument("--mqtt-port", type=int, default=1884)
    parser.add_argument("--disable-mission", action="store_true",
                        help="Skip mission action client (no rclpy_action required)")
    args = parser.parse_args()

    # Lazy ROS 2 imports so the module remains importable for tests.
    try:
        import rclpy
        from rclpy.node import Node
        from rclpy.action import ActionClient
        from std_msgs.msg import Bool as ROSBool
        from std_msgs.msg import Float64, Int32
        from nav_msgs.msg import Odometry

        from self_driving_car_demo.msg import (  # type: ignore
            ControlCommand as ROSControlCommand,
            FaultArray as ROSFaultArray,
            RuntimeMetrics as ROSRuntimeMetrics,
            RuntimeStatus as ROSRuntimeStatus,
            Trajectory as ROSTrajectory,
        )
    except ImportError as exc:
        # Pick the setup script that matches the user's shell so the hint
        # actually works. We try in order: whatever $SHELL says, then zsh,
        # then bash.
        shell_name = Path(os.environ.get("SHELL", "/bin/bash")).name
        candidates = []
        for shell in (shell_name, "zsh", "bash"):
            setup = f"/opt/ros/jazzy/setup.{shell}"
            if Path(setup).exists() and shell not in candidates:
                candidates.append(shell)

        ros_lines = "\n".join(
            f"         source /opt/ros/jazzy/setup.{s}" for s in candidates
        )
        pkg_lines = "\n".join(
            f"         source /home/ubuntu/dev/frank_ws/ros2_car/install/setup.{s}"
            for s in candidates
        )

        sys.stderr.write(
            "\n"
            f"ERROR: 无法 import ROS 2 包（{exc}）。\n"
            "       Gateway 必须跑在已 source ROS 2 环境的 shell 里。\n"
            "\n"
            "       当前 shell：{shell}\n"
            "       启动前请先执行（setup 文件按你的 shell 自动选择）：\n"
            "{ros_lines}\n"
            "{pkg_lines}\n"
            "\n"
            "       source 只对当前终端生效；新开终端必须重新 source。\n"
            "\n"
            "       如果只想验证 wire schema 而不接 ROS，\n"
            "       加 --disable-mission 并手动 mock typed topic 数据。\n"
            "\n".format(
                exc=exc, shell=shell_name,
                ros_lines=ros_lines, pkg_lines=pkg_lines,
            )
        )
        sys.exit(2)

    rclpy.init()
    node = Node(f"robot_bridge_{args.robot_id}", namespace=args.robot_namespace)

    # Downlink ROS publishers
    ros_publishers = {
        "sdc/emergency_stop": node.create_publisher(ROSBool, "sdc/emergency_stop", 10),
        "sdc/control_algo": node.create_publisher(Int32, "sdc/control_algo", 10),
        "sdc/pause": node.create_publisher(ROSBool, "sdc/pause", 10),
        "sdc/clear_trail": node.create_publisher(ROSBool, "sdc/clear_trail", 10),
    }

    from std_srvs.srv import Trigger
    recovery_client = node.create_client(Trigger, "runtime/acknowledge_recovery")
    command_forwarder = CommandForwarder(args.robot_id, ros_publishers, recovery_client)

    # Mission action bridge (optional, requires rclpy_action)
    mission_bridge: MissionActionBridge | None = None
    if not args.disable_mission:
        from self_driving_car_demo.action import ExecuteMission  # type: ignore
        action_client = ActionClient(node, ExecuteMission, "mission/execute")
        # The publisher is wired in by build_bridge() below.
        mission_bridge = MissionActionBridge(
            node=node,
            action_client=action_client,
            robot_id=args.robot_id,
            sequence_counter=count(1),
        )

    publishers, mqtt_client = build_bridge(
        args.robot_id, args.mqtt_broker, args.mqtt_port,
        command_forwarder, mission_bridge,
    )

    if mission_bridge is not None:
        mission_bridge.attach_mqtt(mqtt_client)

    # ---- typed topic subscriptions (QoS matches ros2_car publishers) ----
    # Reference: ros2_car/src/ros2/ring_road_sim_node.cpp lines 230-261
    typed_subs = [
        # (topic, msg_type, callback, qos_factory)
        # runtime/* + control/command + planning/trajectory: all reliable.
        # runtime/status and runtime/faults additionally use transient_local so
        # late subscribers still get the latest snapshot.
        ("runtime/status", ROSRuntimeStatus, publishers["runtime/status"],
            lambda: rclpy.qos.QoSProfile(
                depth=1, reliability=rclpy.qos.ReliabilityPolicy.RELIABLE,
                durability=rclpy.qos.DurabilityPolicy.TRANSIENT_LOCAL)),
        ("runtime/faults", ROSFaultArray, publishers["runtime/faults"],
            lambda: rclpy.qos.QoSProfile(
                depth=1, reliability=rclpy.qos.ReliabilityPolicy.RELIABLE,
                durability=rclpy.qos.DurabilityPolicy.TRANSIENT_LOCAL)),
        ("runtime/metrics", ROSRuntimeMetrics, publishers["runtime/metrics"],
            lambda: rclpy.qos.QoSProfile(
                depth=10, reliability=rclpy.qos.ReliabilityPolicy.RELIABLE,
                durability=rclpy.qos.DurabilityPolicy.VOLATILE)),
        ("control/command", ROSControlCommand, publishers["control/command"],
            lambda: rclpy.qos.QoSProfile(
                depth=10, reliability=rclpy.qos.ReliabilityPolicy.RELIABLE,
                durability=rclpy.qos.DurabilityPolicy.VOLATILE)),
        ("planning/trajectory", ROSTrajectory, publishers["planning/trajectory"],
            lambda: rclpy.qos.QoSProfile(
                depth=10, reliability=rclpy.qos.ReliabilityPolicy.RELIABLE,
                durability=rclpy.qos.DurabilityPolicy.VOLATILE)),
    ]

    # ---- legacy sdc/* subscriptions (QoS matches ros2_car publishers) ----
    # Most use `live_qos` (RELIABLE, depth=10); sdc/odometry uses sensor_qos
    # (BEST_EFFORT, depth=5). Subscriber QoS must match exactly or DDS will
    # refuse to deliver messages.
    def legacy_live_qos():
        return rclpy.qos.QoSProfile(
            depth=10, reliability=rclpy.qos.ReliabilityPolicy.RELIABLE,
            durability=rclpy.qos.DurabilityPolicy.VOLATILE)

    def legacy_sensor_qos():
        # SensorData QoS: BEST_EFFORT + VOLATILE + keep_last(5)
        # ROS 2 Jazzy's rclpy.qos does not expose SensorDataQoS, so build it
        # from primitives (matches rclcpp::SensorDataQoS in ros2_car).
        return rclpy.qos.QoSProfile(
            history=rclpy.qos.HistoryPolicy.KEEP_LAST,
            depth=5,
            reliability=rclpy.qos.ReliabilityPolicy.BEST_EFFORT,
            durability=rclpy.qos.DurabilityPolicy.VOLATILE,
        )

    LEGACY_QOS = {
        "sdc/speed": legacy_live_qos,
        "sdc/action_id": legacy_live_qos,
        "sdc/front_distance": legacy_live_qos,
        "sdc/obstacle_count": legacy_live_qos,
        "sdc/odometry": legacy_sensor_qos,
    }

    # Wrap every subscription callback so we can tell at a glance whether
    # the bridge is actually receiving messages, and from which topic.
    rx_counter = _RxCounter()

    for topic_name, msg_type, cb, qos_factory in typed_subs:
        wrapped = rx_counter.wrap(topic_name, cb)
        node.create_subscription(msg_type, topic_name, wrapped, qos_factory())
        print(f"[typed] {topic_name}")

    for topic_name, (msg_type_str, _legacy_key) in LEGACY_TOPIC_SCHEMA.items():
        msg_type = {"Float64": Float64, "Odometry": Odometry}[msg_type_str]
        legacy_cb = _legacy_callback_factory(
            publishers["legacy"], topic_name, msg_type_str
        )
        wrapped = rx_counter.wrap(topic_name, legacy_cb)
        node.create_subscription(msg_type, topic_name, wrapped, LEGACY_QOS[topic_name]())
        print(f"[legacy] {topic_name}")

    print(f"Bridge 已启动，robot_id={args.robot_id}，等待 ROS 2 消息…")
    print("(首条消息进入后会打印 [RX] topic，第 5 秒打印一次累计统计)")

    # Periodic stats summary so the user can confirm the bridge is alive even
    # if they are not looking at the terminal.
    import threading as _th
    def _stats_loop():
        time.sleep(5.0)
        rx_counter.print_summary(logger, since_start=True)
        while True:
            time.sleep(10.0)
            rx_counter.print_summary(logger, since_start=False)
    _th.Thread(target=_stats_loop, daemon=True).start()

    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        rclpy.shutdown()


class _RxCounter:
    """Track first-message and total counts per ROS 2 subscription."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._first_seen: dict[str, float] = {}
        self._count: dict[str, int] = {}
        self._start = time.time()

    def wrap(self, topic_name, callback):
        counter = self
        def _wrapped(msg):
            now = time.time()
            with counter._lock:
                first = topic_name not in counter._first_seen
                counter._first_seen[topic_name] = now
                counter._count[topic_name] = counter._count.get(topic_name, 0) + 1
            if first:
                logger.info("[RX first] %s", topic_name)
            callback(msg)
        return _wrapped

    def print_summary(self, log, since_start: bool) -> None:
        with self._lock:
            topics = sorted(self._count)
            total = sum(self._count.values())
            window_s = 10.0 if not since_start else (time.time() - self._start)
        if not topics:
            log.warning("[RX] 5s 内一条 ROS 2 消息都没收到，请确认 ROS2Drive 已启动")
            return
        log.info("[RX summary %ds] total=%d", int(window_s), total)
        for topic in topics:
            log.info("    %-30s %6d msgs", topic, self._count[topic])


def _legacy_callback_factory(publish_legacy, topic_name: str, msg_type: str):
    def _cb(msg):
        publish_legacy(topic_name, msg_type, msg)
    return _cb


def _mission_action_callback_factory(action_client):
    """Build a callback that creates a MissionActionBridge and wires it.

    Used when build_bridge is invoked outside the main() entry point.
    """
    raise NotImplementedError("Mission bridge is wired inside main() now")


if __name__ == "__main__":
    main()
