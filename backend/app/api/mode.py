"""运行模式管理 API。

支持在仿真模式（simulation）与实车模式（real）之间动态切换。
实车模式用于接入本地 ROS2 实时数据（经 gateway/ros2_bridge.py）。
"""
from fastapi import APIRouter
from pydantic import BaseModel

from app.core.config import settings
from app.services.robot_state import state_store

router = APIRouter(prefix="/api", tags=["mode"])

VALID_MODES = {"simulation", "real"}


class ModeRequest(BaseModel):
    mode: str


@router.get("/mode")
def get_mode():
    """获取当前运行模式与模式说明。"""
    mode = state_store.get_mode()
    return {
        "mode": mode,
        "available": list(VALID_MODES),
        "description": mode_description(mode),
        "map": {
            "width": settings.map_width,
            "height": settings.map_height,
            "cell": settings.map_cell,
        },
    }


@router.post("/mode")
def set_mode(req: ModeRequest):
    """切换运行模式：simulation（仿真）/ real（实车，接入本地 ROS2）。"""
    mode = req.mode
    if mode not in VALID_MODES:
        return {"ok": False, "error": f"无效模式: {mode}，可选 {VALID_MODES}"}
    state_store.set_mode(mode)
    return {
        "ok": True,
        "mode": mode,
        "description": mode_description(mode),
    }


@router.get("/pose")
def get_pose():
    """获取机器人当前位姿（x/y/heading，米/弧度）与轨迹。"""
    return {
        "mode": state_store.get_mode(),
        "pose": state_store.get_pose(),
        "trail": state_store.get_trail(),
    }


@router.post("/clear_trail")
def clear_trail():
    """清空地图上的轨迹。"""
    state_store.clear_trail()
    return {"ok": True}


def mode_description(mode: str) -> str:
    if mode == "real":
        return "实车模式：通过 gateway/ros2_bridge.py 接入本地 ROS2 实时数据"
    return "仿真模式：由 gateway/mqtt_simulator.py 生成模拟数据（默认）"
