"""机器人控制 API（下发指令到消息总线 → 机器人侧执行）。"""
from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter(prefix="/api", tags=["control"])


class ControlCommand(BaseModel):
    action: str          # set_control_algo / toggle_pause / clear_trail
    value: object = None


# 机器人侧订阅这些指令主题（由 gateway 消费并转成 ROS2 话题）
COMMAND_TOPIC_MAP = {
    "set_control_algo": ("robot/{robot_id}/command/control_algo", "Int32"),
    "toggle_pause": ("robot/{robot_id}/command/pause", "Bool"),
    "clear_trail": ("robot/{robot_id}/command/clear_trail", "Bool"),
}


@router.post("/control")
def control(command: ControlCommand):
    """接收控制指令。"""
    if command.action not in COMMAND_TOPIC_MAP:
        return {"ok": False, "error": f"未知指令: {command.action}"}
    # 实际部署时由 gateway 从消息总线转发到机器人
    # 此处返回已受理
    return {
        "ok": True,
        "action": command.action,
        "value": command.value,
        "note": "指令已受理，将由 gateway 转发到机器人",
    }
