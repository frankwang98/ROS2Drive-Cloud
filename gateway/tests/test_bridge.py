import importlib.util
import json
import sys
import time
from itertools import count
from pathlib import Path
from types import SimpleNamespace

import pytest
from robot_contracts import MessageType, MissionCommandPayload, envelope

spec = importlib.util.spec_from_file_location("cloud_bridge", Path(__file__).parents[1] / "ros2_bridge.py")
bridge = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bridge)


def test_nonempty_goal_route(monkeypatch):
    class Goal:
        def __init__(self):
            self.route = []
    monkeypatch.setitem(sys.modules, "self_driving_car_demo.action", SimpleNamespace(ExecuteMission=SimpleNamespace(Goal=Goal)))
    monkeypatch.setitem(sys.modules, "geometry_msgs.msg", SimpleNamespace(Pose2D=lambda: SimpleNamespace()))
    b = bridge.MissionActionBridge(None, None, "car01", count(1))
    goal = b._build_goal_msg(MissionCommandPayload.from_dict({"mission_id": "m1", "route": [{"x": 1, "y": 2, "theta": .3}]}))
    assert len(goal.route) == 1
    assert goal.route[0].theta == .3


class FakeMQTT:
    def __init__(self, **kwargs):
        self.callbacks = {}
        self.subscriptions = []
        self.messages = []
    def message_callback_add(self, topic, callback): self.callbacks[topic] = callback
    def reconnect_delay_set(self, **kwargs): pass
    def connect_async(self, *args): pass
    def loop_start(self): pass
    def subscribe(self, topic, qos=0): self.subscriptions.append((topic, qos))
    def publish(self, topic, payload, qos=0): self.messages.append((topic, json.loads(payload)))


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(bridge, "HAS_MQTT", True)
    monkeypatch.setattr(bridge.mqtt, "Client", FakeMQTT)
    monkeypatch.setattr(bridge.threading, "Thread", lambda **kwargs: SimpleNamespace(start=lambda: None))
    forward = bridge.CommandForwarder("car01", {})
    _, mqtt = bridge.build_bridge("car01", "localhost", 1884, forward, None)
    return mqtt, forward


def test_reconnect_resubscribes(client):
    mqtt, _ = client
    for _ in range(2): mqtt.on_connect(mqtt, None, None, 0)
    assert len(mqtt.subscriptions) == 8
    assert all(qos == 1 for _, qos in mqtt.subscriptions)


def deliver(client, message):
    mqtt, _ = client
    topic = "robots/car01/commands"
    mqtt.callbacks[topic](mqtt, None, SimpleNamespace(topic=topic, payload=json.dumps(message).encode()))
    return mqtt.messages[-1][1]["payload"]


def test_expired_command_not_executed(client):
    _, forward = client
    forward.handle_legacy_command = lambda *args: pytest.fail("expired command executed")
    message = envelope("car01", MessageType.COMMAND, {"action": "pause", "value": True, "expires_at": time.time()-1}, sequence=1)
    assert deliver(client, message)["status"] == "EXPIRED"


def test_duplicate_retains_rejection(client):
    _, forward = client
    calls = []
    forward.handle_legacy_command = lambda *args: (calls.append(1) or ("REJECTED", "invalid"))
    message = envelope("car01", MessageType.COMMAND, {"action": "bad"}, sequence=1)
    assert deliver(client, message)["status"] == "REJECTED"
    assert deliver(client, message)["status"] == "REJECTED"
    assert len(calls) == 1


def test_feedback_keeps_mission_id():
    b=bridge.MissionActionBridge(None,None,"car01",count(1));mqtt=FakeMQTT();b.attach_mqtt(mqtt)
    b._on_feedback(SimpleNamespace(feedback=SimpleNamespace(state="ACTIVE",progress=.5,reason="")),"m1")
    assert mqtt.messages[-1][1]["payload"]["mission_id"] == "m1"


def test_unavailable_action_rejects_without_send():
    b=bridge.MissionActionBridge(None,SimpleNamespace(server_is_ready=lambda:False),"car01",count(1))
    mqtt=FakeMQTT();b.attach_mqtt(mqtt)
    b.send_goal(MissionCommandPayload(mission_id="m1"),"c1")
    assert mqtt.messages[-1][1]["payload"]["status"] == "REJECTED"
