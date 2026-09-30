"""Mission requests and unified read model for the dashboard."""
from __future__ import annotations

import math
import time
from typing import Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.core.config import settings
from app.services.command_publisher import command_publisher
from app.services.robot_registry import robot_registry
from app.services.typed_state import typed_state
from robot_contracts import MessageType

router = APIRouter(prefix="/api/v2/robots", tags=["missions-v2"])


class Pose(BaseModel):
    x: float = Field(allow_inf_nan=False)
    y: float = Field(allow_inf_nan=False)
    theta: float = Field(default=0.0, allow_inf_nan=False)


class MissionRequest(BaseModel):
    mission_id: str = Field(min_length=1, max_length=128)
    mission_type: int = Field(default=1, ge=0, le=5)
    route: list[Pose] = Field(default_factory=list, max_length=5000)
    speed_limit: float = Field(default=1.0, gt=0, le=10, allow_inf_nan=False)
    goal_tolerance: float = Field(default=0.5, gt=0, allow_inf_nan=False)
    timeout_s: float = Field(default=300, ge=0, allow_inf_nan=False)
    allow_preempt: bool = False


def find_mission(robot_id: str, mission_id: str):
    return robot_registry.mission(robot_id, mission_id)


@router.post("/{robot_id}/missions")
def create_mission(robot_id: str, request: MissionRequest):
    if request.mission_type in (0, 1) and not request.route:
        raise HTTPException(422, "NavigateTo/FollowRoute requires a route")
    existing = find_mission(robot_id, request.mission_id)
    body = request.model_dump()
    if existing:
        old = {k: v for k, v in existing["payload"].items() if k != "expires_at"}
        if old != body:
            raise HTTPException(409, "mission_id is already used for another request")
        return {"command_id": existing["message_id"], "status": existing["status"], "mission_id": request.mission_id}
    result = command_publisher.publish_typed(robot_id, MessageType.MISSION_COMMAND, body, "missions/command")
    return {"command_id": result["message_id"], "status": result["status"], "mission_id": request.mission_id}


@router.get("/{robot_id}/missions/{mission_id}")
def get_mission(robot_id: str, mission_id: str):
    result = find_mission(robot_id, mission_id)
    if result is None:
        raise HTTPException(404, "mission not found")
    return result


@router.post("/{robot_id}/missions/{mission_id}/cancel")
def cancel_mission(robot_id: str, mission_id: str):
    result = command_publisher.publish_typed(robot_id, MessageType.MISSION_CANCEL, {"mission_id": mission_id}, "missions/cancel")
    return {"command_id": result["message_id"], "status": result["status"]}


class SafetyRequest(BaseModel):
    value: bool


@router.post("/{robot_id}/emergency-stop")
def emergency_stop(robot_id: str, request: SafetyRequest):
    result = command_publisher.publish_typed(robot_id, MessageType.EMERGENCY_STOP, request.model_dump(), "emergency_stop")
    return {"command_id": result["message_id"], "status": result["status"]}


@router.get("/{robot_id}/snapshot")
def snapshot(robot_id: str):
    return {"robot": robot_registry.robot(robot_id), "typed": typed_state.snapshot(robot_id), "server_time": time.time()}
