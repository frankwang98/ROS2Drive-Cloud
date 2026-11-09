"""Contract tests for the native bridge's command-to-C++ protocol."""
import importlib.util
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location(
    "native_runtime_bridge", Path(__file__).resolve().parents[1] / "native_runtime_bridge.py"
)
bridge = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bridge)


def test_mission_conversion():
    lines = bridge.command_lines("mission_command", {
        "mission_id": "demo-1", "mission_type": 1, "speed_limit": 2,
        "goal_tolerance": .5, "timeout_s": 30, "allow_preempt": True,
        "route": [{"x": 1, "y": 2, "theta": .3}],
    })
    assert lines[0] == "MISSION demo-1 1 2.0 0.5 30.0 1 1"
    assert lines[1] == "1.0 2.0 0.3"


@pytest.mark.parametrize("mission_id", ["", "bad id", "x" * 129])
def test_reject_invalid_ids(mission_id):
    with pytest.raises(ValueError):
        bridge.command_lines("mission_command", {
            "mission_id": mission_id, "route": [{"x": 0, "y": 0}]
        })


def test_reject_nan_route():
    with pytest.raises(ValueError):
        bridge.command_lines("mission_command", {
            "mission_id": "ok", "route": [{"x": float("nan"), "y": 0}]
        })


def test_cancel_estop_and_pause():
    assert bridge.command_lines("mission_cancel", {}) == ["CANCEL"]
    assert bridge.command_lines("emergency_stop", {"value": True}) == ["ESTOP 1"]
    assert bridge.command_lines("command", {"action": "set_paused", "value": True}) == ["PAUSE"]
