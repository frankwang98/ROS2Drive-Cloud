"""Fleet projection must discover typed-only robots without mutating registry."""
import time
from app.api import robot
from app.services.robot_registry import RobotRegistry
from app.services.typed_state import TypedStateStore


def test_fleet_discovers_typed_only_and_expires(monkeypatch):
    registry, typed = RobotRegistry(), TypedStateStore()
    monkeypatch.setattr(robot, 'robot_registry', registry)
    monkeypatch.setattr(robot, 'typed_state', typed)
    assert robot.fleet_snapshot()['robots'] == []
    registry.heartbeat('legacy')
    typed.update('typed-only', 'runtime_status', {'runtime_state': 'RUNNING'})
    before = len(registry.robots())
    view = robot.fleet_snapshot()
    assert {s['robot']['robot_id'] for s in view['robots']} == {'legacy', 'typed-only'}
    assert all(s['robot']['connection']['state'] == 'ONLINE' for s in view['robots'])
    assert len(registry.robots()) == before
    with typed._lock:
        typed._data[('typed-only', 'runtime_status')]['received_at'] = time.time() - 20
    view = robot.fleet_snapshot()
    assert next(s for s in view['robots'] if s['robot']['robot_id'] == 'typed-only')['robot']['connection']['state'] == 'OFFLINE'


def test_specific_fleet_route_precedes_robot_id():
    paths = [route.path for route in robot.v1_router.routes]
    assert paths.index('/api/v1/robots/fleet-snapshot') < paths.index('/api/v1/robots/{robot_id}')
