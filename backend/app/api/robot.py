"""机器人状态 REST API。"""
from fastapi import APIRouter, HTTPException

from app.services.robot_state import state_store
from app.services.robot_registry import robot_registry
from app.api.control import ControlCommand, control

router = APIRouter(prefix="/api/robot", tags=["robot"])
v1_router = APIRouter(prefix="/api/v1/robots", tags=["robots-v1"])


@v1_router.get("")
def list_robots():
    return {"robots": robot_registry.robots()}


@v1_router.get("/{robot_id}")
def get_robot(robot_id: str):
    return robot_registry.robot(robot_id)


@v1_router.get("/{robot_id}/commands/{command_id}")
def get_command(robot_id: str, command_id: str):
    command = robot_registry.command(command_id)
    if command is None or command.get("robot_id") != robot_id:
        raise HTTPException(status_code=404, detail="command not found")
    return command


@v1_router.post("/{robot_id}/commands")
def create_command(robot_id: str, command: ControlCommand):
    command.robot_id = robot_id
    return control(command)


@router.get("/status")
def get_status():
    """获取机器人整体状态快照。"""
    return state_store.snapshot()


@router.get("/topics")
def list_topics():
    """列出当前已上报的 ROS2 话题及最新值。"""
    snap = state_store.snapshot()
    return {
        "connected": snap["connected"],
        "last_update": snap["last_update"],
        "topics": snap["topics"],
    }


@router.get("/topics/{topic}")
def get_topic(topic: str):
    """获取指定话题的最新值。"""
    value = state_store.get_topic(topic)
    if value is None:
        return {"topic": topic, "value": None}
    return {"topic": topic, "value": value}
