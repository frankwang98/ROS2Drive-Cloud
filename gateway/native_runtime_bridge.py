#!/usr/bin/env python3
"""ROS-free C++ runtime ⇄ ROS2Drive-Cloud MQTT v2 adapter.

Run on a trusted local network. This process is the only writer to the C++
runtime's stdin; MQTT callbacks only enqueue commands.
"""
from __future__ import annotations

import argparse
import json
import math
import queue
import subprocess
import sys
import time
from pathlib import Path

import paho.mqtt.client as mqtt

# Run from this repository without installing robot_contracts.
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "robot_contracts"))
from robot_contracts import MessageType, envelope, parse_envelope  # noqa: E402


def command_lines(kind: str, body: dict) -> list[str]:
    if kind == "mission_command":
        route = body.get("route", [])
        if not isinstance(route, list) or not 1 <= len(route) <= 5000:
            raise ValueError("mission route must contain 1..5000 points")
        mid = body.get("mission_id", "")
        if not isinstance(mid, str) or not mid or len(mid) > 128 or any(c.isspace() for c in mid):
            raise ValueError("invalid mission_id")
        kind_id = int(body.get("mission_type", 1))
        speed = float(body.get("speed_limit", 1))
        tolerance = float(body.get("goal_tolerance", .5))
        timeout = float(body.get("timeout_s", 0))
        if kind_id not in (0, 1) or not 0 < speed <= 10 or tolerance <= 0 or timeout < 0:
            raise ValueError("unsupported mission parameters")
        values = [speed, tolerance, timeout]
        if not all(math.isfinite(v) for v in values):
            raise ValueError("non-finite mission parameter")
        lines = [f"MISSION {mid} {kind_id} {speed} {tolerance} {timeout} {int(bool(body.get('allow_preempt', False)))} {len(route)}"]
        for p in route:
            x, y, yaw = float(p["x"]), float(p["y"]), float(p.get("theta", 0))
            if not all(math.isfinite(v) for v in (x, y, yaw)):
                raise ValueError("non-finite route point")
            lines.append(f"{x} {y} {yaw}")
        return lines
    if kind == "mission_cancel":
        return ["CANCEL"]
    if kind == "emergency_stop":
        if not isinstance(body.get("value"), bool):
            raise ValueError("emergency_stop requires boolean value")
        return [f"ESTOP {int(body['value'])}"]
    if kind == "command":
        action = body.get("action")
        if action == "set_paused":
            if not isinstance(body.get("value"), bool):
                raise ValueError("set_paused requires boolean")
            return ["PAUSE" if body["value"] else "RESUME"]
        if action == "acknowledge_recovery":
            return ["RECOVER"]
    raise ValueError(f"unsupported command: {kind}")


class NativeBridge:
    def __init__(self, args):
        self.args = args
        self.pending = queue.Queue(maxsize=128)
        self.sequence = 0
        self.last_mission = None
        self.last_mission_state = None
        self.proc = subprocess.Popen(
            [str(Path(args.runner).resolve()), "--scenario", args.scenario, "--dt", str(args.dt)],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True, bufsize=1,
        )
        self.client = mqtt.Client(callback_api_version=mqtt.CallbackAPIVersion.VERSION2)
        self.client.on_connect = self.on_connect
        self.client.on_message = self.on_message
        self.client.connect(args.broker, args.port, 60)
        self.client.loop_start()

    def topic(self, suffix):
        return f"{self.args.prefix}/{self.args.robot_id}/{suffix}"

    def publish(self, kind, body, suffix, qos=0):
        self.sequence += 1
        message = envelope(self.args.robot_id, kind, body, sequence=self.sequence)
        self.client.publish(self.topic(suffix), json.dumps(message, allow_nan=False), qos=qos)

    def on_connect(self, client, userdata, flags, reason_code, properties):
        if reason_code != 0:
            print(f"MQTT connect failed: {reason_code}", file=sys.stderr)
            return
        for suffix in ("missions/command", "missions/cancel", "emergency_stop", "commands"):
            client.subscribe(self.topic(suffix), qos=1)

    def on_message(self, client, userdata, message):
        try:
            data = parse_envelope(json.loads(message.payload))
            if data["robot_id"] != self.args.robot_id:
                return
            kind = data["type"]
            if kind not in ("mission_command", "mission_cancel", "emergency_stop", "command"):
                return
            self.pending.put_nowait(data)
        except (ValueError, KeyError, queue.Full) as exc:
            print(f"Dropped invalid command: {exc}", file=sys.stderr)

    def request(self, lines):
        assert self.proc.stdin and self.proc.stdout
        self.proc.stdin.write("\n".join(lines) + "\n")
        self.proc.stdin.flush()
        line = self.proc.stdout.readline()
        if not line:
            raise RuntimeError(f"native runtime exited: {self.proc.poll()}")
        return json.loads(line)

    def process_commands(self):
        for _ in range(16):
            try:
                msg = self.pending.get_nowait()
            except queue.Empty:
                break
            body, kind = msg["payload"], msg["type"]
            mid = body.get("mission_id", "")
            accepted, reason = False, ""
            try:
                if body.get("expires_at", float("inf")) < time.time():
                    raise ValueError("command expired")
                if kind == "mission_cancel" and mid != self.last_mission:
                    raise ValueError("mission_id does not match active mission")
                response = self.request(command_lines(kind, body))
                accepted = response.get("kind") == "ack" and response.get("accepted") is True
                if not accepted:
                    reason = "native runtime rejected command"
            except (ValueError, KeyError, TypeError) as exc:
                reason = str(exc)
            self.publish(MessageType.COMMAND_ACK, {
                "command_id": msg["message_id"], "status": "ACCEPTED" if accepted else "REJECTED",
                "reason": reason,
            }, "command_ack", qos=1)
            if kind == "mission_command":
                if accepted:
                    self.last_mission = mid
                    self.last_mission_state = None
                self.publish(MessageType.MISSION_FEEDBACK, {
                    "mission_id": mid, "state": "ACCEPTED" if accepted else "REJECTED",
                    "progress": 0, "reason": reason,
                }, "mission/feedback", qos=1)

    def send_frame(self, frame):
        self.publish(MessageType.TELEMETRY, {
            "name": "sdc/odometry",
            "value": {"pose": {"x": frame["x"], "y": frame["y"], "yaw": frame["yaw"]},
                      "velocity": {"linear": frame["speed"], "angular": 0}},
        }, "telemetry")
        self.publish(MessageType.RUNTIME_STATUS, {
            "runtime_state": frame["runtime_state"],
            "mission_id": frame["mission_id"],
            "mission_type": "FOLLOW_ROUTE",
            "mission_state": frame["mission_state"],
            "mission_progress": frame["mission_progress"],
            "localized": True, "healthy": frame["runtime_state"] not in ("FAULT", "ESTOP"),
            "recovery_required": False, "recovery_ready": False,
        }, "runtime/status")
        self.publish(MessageType.TRAJECTORY, {
            "mission_id": frame["mission_id"], "valid": frame["planning_ok"],
            "points": [{"pose": p, "curvature": 0, "velocity": 0,
                        "acceleration": 0, "relative_time": 0, "stop_required": False}
                       for p in frame["trajectory"][:200]],
        }, "trajectory")
        state = frame["mission_state"]
        mid = frame["mission_id"]
        if mid and (mid != self.last_mission or state != self.last_mission_state):
            self.publish(MessageType.MISSION_FEEDBACK, {
                "mission_id": mid, "state": state,
                "progress": frame["mission_progress"], "reason": "",
            }, "mission/feedback", qos=1)
            self.last_mission = mid
            self.last_mission_state = state
            if state in ("SUCCEEDED", "FAILED", "CANCELED"):
                self.publish(MessageType.MISSION_RESULT, {
                    "mission_id": mid, "success": state == "SUCCEEDED",
                    "final_state": state, "reason": "",
                }, "mission/result", qos=1)

    def run(self):
        next_step = time.monotonic()
        heartbeat_at = 0.0
        try:
            while self.proc.poll() is None:
                self.process_commands()
                frame = self.request(["STEP"])
                if frame.get("kind") != "frame":
                    raise RuntimeError("unexpected native response")
                self.send_frame(frame)
                if time.monotonic() >= heartbeat_at:
                    self.publish(MessageType.HEARTBEAT, {"mode": "simulation"}, "heartbeat")
                    heartbeat_at = time.monotonic() + 1
                next_step += self.args.dt
                time.sleep(max(0, next_step - time.monotonic()))
        finally:
            self.client.loop_stop()
            self.client.disconnect()
            if self.proc.poll() is None:
                self.proc.terminate()
                self.proc.wait(timeout=5)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runner", required=True, help="path to ROS2Drive build-native/ros2drive_live")
    parser.add_argument("--broker", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=1884)
    parser.add_argument("--prefix", default="robots")
    parser.add_argument("--robot-id", default="car01")
    parser.add_argument("--scenario", default="port_transport",
                        choices=["ring_demo", "mining_haul", "port_transport", "agriculture_route"])
    parser.add_argument("--dt", type=float, default=.05)
    args = parser.parse_args()
    if not math.isfinite(args.dt) or not 0 < args.dt <= 1:
        parser.error("--dt must be finite and in (0,1]")
    NativeBridge(args).run()


if __name__ == "__main__":
    main()
