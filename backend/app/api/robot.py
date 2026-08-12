"""机器人状态 REST API。"""
from fastapi import APIRouter

from app.services.robot_state import state_store

router = APIRouter(prefix="/api/robot", tags=["robot"])


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
