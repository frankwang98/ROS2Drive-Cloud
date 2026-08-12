# 下行控制链路测试
from app.api.control import ControlCommand, COMMAND_TOPIC_MAP, control
from app.services.command_publisher import CommandPublisher


class _FakeClient:
    """模拟 paho-mqtt 发布客户端。"""

    def __init__(self):
        self.published = []

    def connect(self, *args, **kwargs):
        return 0

    def loop_start(self):
        pass

    def loop_stop(self):
        pass

    def disconnect(self):
        pass

    def publish(self, topic, payload, qos=0):
        self.published.append((topic, payload))
        return self

    def wait_for_publish(self, timeout=5):
        pass


def test_command_publisher_topic(monkeypatch):
    """验证 CommandPublisher 发布到正确 command 主题。"""
    import json

    from app.services import command_publisher as cp_mod

    fake = _FakeClient()
    # 让单例的 mqtt_client 指向 fake，避免真实网络连接
    cp_mod.command_publisher._mqtt_client = fake

    ok = cp_mod.command_publisher.publish("car01", "control_algo", 1)
    assert ok is True
    topic, payload = fake.published[0]
    assert topic == "robot/car01/command/control_algo"
    data = json.loads(payload)
    assert data["action"] == "control_algo"
    assert data["value"] == 1


def test_control_api_publishes(monkeypatch):
    """验证 /api/control 通过 command_publisher 真正发布指令。"""
    from app.services import command_publisher as cp_mod

    fake = _FakeClient()
    cp_mod.command_publisher._mqtt_client = fake

    resp = control(ControlCommand(action="toggle_pause", value=True))
    assert resp["ok"] is True
    assert resp["command_topic"] == "robot/car01/command/pause"
    assert fake.published and fake.published[0][0] == "robot/car01/command/pause"


def test_control_api_unknown_action():
    """未知指令应被拒绝。"""
    resp = control(ControlCommand(action="not_a_real_command"))
    assert resp["ok"] is False
    assert "未知指令" in resp["error"]


def test_command_topic_map_complete():
    """验证 control 侧 action 与 command 主题映射齐全。"""
    assert COMMAND_TOPIC_MAP["set_control_algo"] == ("control_algo", "Int32")
    assert COMMAND_TOPIC_MAP["toggle_pause"] == ("pause", "Bool")
    assert COMMAND_TOPIC_MAP["clear_trail"] == ("clear_trail", "Bool")
