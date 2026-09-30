import json
import time

from app.services.robot_registry import RobotRegistry, robot_registry
from app.services.typed_state import TypedStateStore
from app.services.command_publisher import CommandPublisher
from robot_contracts import MessageType, envelope


def test_early_ack_is_not_overwritten():
    r=RobotRegistry()
    r.update_command_ack("car01",{"command_id":"c1","status":"SUCCEEDED"})
    r.record_command({"robot_id":"car01","message_id":"c1","status":"PUBLISHED"})
    assert r.command("c1")["status"] == "SUCCEEDED"


def test_wrong_robot_ack_cannot_change_command():
    r=RobotRegistry();r.record_command({"robot_id":"car01","message_id":"c1","status":"PUBLISHED"})
    r.update_command_ack("car02",{"command_id":"c1","status":"SUCCEEDED"})
    assert r.command("c1")["status"] == "PUBLISHED"


def test_terminal_result_cannot_regress():
    r=RobotRegistry();r.record_command({"robot_id":"car01","message_id":"c1","status":"PUBLISHED"})
    r.update_command_ack("car01",{"command_id":"c1","status":"SUCCEEDED"})
    r.update_command_ack("car01",{"command_id":"c1","status":"ACCEPTED"})
    assert r.command("c1")["status"] == "SUCCEEDED"


def test_out_of_order_and_restart_session():
    s=TypedStateStore()
    s.update("car01","runtime_status",{"runtime_state":"ESTOP"},sequence=20,timestamp=10,session_id="a")
    assert not s.update("car01","runtime_status",{"runtime_state":"RUNNING"},sequence=19,timestamp=11,session_id="a")
    assert s.get("car01","runtime_status")["payload"]["runtime_state"] == "ESTOP"
    assert s.update("car01","runtime_status",{"runtime_state":"READY"},sequence=1,timestamp=12,session_id="b")
    assert not s.update("car01","runtime_status",{},sequence=21,timestamp=11,session_id="a")


def test_publisher_records_before_fast_ack():
    p=CommandPublisher()
    class Client:
        rc=0
        def publish(self,topic,payload,qos):
            message=json.loads(payload)
            assert robot_registry.command(message["message_id"])["status"] == "CREATED"
            robot_registry.update_command_ack(message["robot_id"],{"command_id":message["message_id"],"status":"SUCCEEDED"})
            return self
        def wait_for_publish(self,timeout):pass
        def is_published(self):return True
    p._mqtt_client=Client()
    assert p.publish("race-car","pause",True)["status"] == "SUCCEEDED"


def test_mission_result_tracks_original_request():
    r=RobotRegistry();command=envelope("car01",MessageType.MISSION_COMMAND,{"mission_id":"m1"},sequence=1);command["status"]="PUBLISHED";r.record_command(command)
    r.update_mission("car01",{"mission_id":"m1","final_state":"CANCELED","success":False},True)
    assert r.mission("car01","m1")["status"] == "CANCELED"


def test_mission_api_idempotency(monkeypatch):
    from app.api.missions import create_mission,MissionRequest
    from app.services import command_publisher as cp
    request=MissionRequest(mission_id="api-m1",route=[{"x":0,"y":0},{"x":1,"y":1}])
    calls=[]
    def publish(robot,kind,body,suffix):
        calls.append(body);message=envelope(robot,kind,body,sequence=1);message["status"]="PUBLISHED";robot_registry.record_command(message);return message
    monkeypatch.setattr(cp.command_publisher,"publish_typed",publish)
    first=create_mission("api-car",request);second=create_mission("api-car",request)
    assert first["command_id"] == second["command_id"]
    assert len(calls)==1
