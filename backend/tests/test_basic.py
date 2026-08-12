# 测试套件
from app.core.config import get_settings


def test_settings_defaults():
    s = get_settings()
    assert s.app_name == "Robot Cloud Platform"
    assert s.port == 8000
    assert "sdc/speed" in s.robot_topics


def test_state_store_basic():
    from app.services.robot_state import RobotStateStore

    store = RobotStateStore()
    assert store.snapshot()["connected"] is False

    store.update_topic("sdc/speed", 2.4)
    snap = store.snapshot()
    assert snap["connected"] is True
    assert snap["topics"]["sdc/speed"]["value"] == 2.4

    assert store.get_topic("sdc/speed") == 2.4
    assert store.get_topic("unknown") is None
