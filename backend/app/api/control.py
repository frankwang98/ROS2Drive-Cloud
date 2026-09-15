"""机器人控制 API（下发指令到消息总线 → gateway → 机器人侧执行）。"""
from fastapi import APIRouter
from pydantic import BaseModel

from app.core.config import settings
from app.services.command_publisher import command_publisher
from app.services.robot_state import state_store
from app.services.robot_registry import robot_registry

router = APIRouter(prefix="/api", tags=["control"])


class ControlCommand(BaseModel):
    action: str          # set_control_algo / set_paused / clear_trail
    value: object = None
    robot_id: str = None  # 目标机器人 ID，缺省用默认值


# 机器人侧订阅这些指令主题（由 gateway 消费并转成 ROS2 话题）
# action -> (command 主题后缀, ROS2 消息类型)
COMMAND_TOPIC_MAP = {
    "set_control_algo": ("control_algo", "Int32"),
    "set_paused": ("pause", "Bool"),
    "clear_trail": ("clear_trail", "Bool"),
}


@router.post("/control")
def control(command: ControlCommand):
    """接收控制指令并发布到消息总线，由 gateway 转发到机器人。"""
    if command.action not in COMMAND_TOPIC_MAP:
        return {"ok": False, "error": f"未知指令: {command.action}"}

    if command.action == "set_paused" and not isinstance(command.value, bool):
        return {"ok": False, "error": "set_paused 必须提供布尔值 value"}

    command_key, _ = COMMAND_TOPIC_MAP[command.action]
    robot_id = command.robot_id or settings.default_robot_id

    # 真正发布指令到消息总线
    result = command_publisher.publish(
        robot_id, command_key, command.value
    )
    robot_registry.record_command(result)
    published = result["status"] == "PUBLISHED"

    # 本地同步副作用：清空轨迹（仿真模式轨迹由 state_store 维护）
    if command.action == "clear_trail":
        state_store.clear_trail()
        robot_registry.clear_trail(robot_id)

    return {
        "ok": published,
        "action": command.action,
        "command_id": result["message_id"],
        "status": result["status"],
        "command_topic": f"{settings.mqtt_topic_prefix}/{robot_id}/commands",
        "value": command.value,
        "published": published,
        "note": "指令已发布到消息总线，将由 gateway 转发到机器人",
    }
