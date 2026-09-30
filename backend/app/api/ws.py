"""WebSocket 实时推送端点。

Web Dashboard 通过 WebSocket 订阅机器人状态变化（速度、行为、距离等）。
"""
import asyncio
import json
import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.services.robot_state import state_store
from app.services.robot_registry import robot_registry
from app.services.typed_state import typed_state

logger = logging.getLogger("robot.ws")

router = APIRouter(tags=["ws"])


@router.websocket("/ws/v1/robots/{robot_id}")
async def robot_ws_v1(websocket: WebSocket, robot_id: str):
    await websocket.accept()
    queue = robot_registry.subscribe()
    try:
        await websocket.send_text(json.dumps({
            "type": "snapshot", "robot_id": robot_id,
            "data": robot_registry.robot(robot_id),
        }))
        while True:
            msg = await queue.get()
            if msg["robot_id"] == robot_id:
                await websocket.send_text(json.dumps(msg))
    except (WebSocketDisconnect, asyncio.CancelledError):
        logger.info("WebSocket v1 客户端断开: %s", robot_id)
    finally:
        robot_registry.unsubscribe(queue)


@router.websocket("/ws/robot")
async def robot_ws(websocket: WebSocket):
    await websocket.accept()
    queue = state_store.subscribe()
    try:
        # 连接后先推送一次当前快照
        await websocket.send_text(json.dumps({"type": "snapshot", "data": state_store.snapshot()}))
        while True:
            # 有更新则推送；同时响应 ping 心跳
            try:
                msg = await queue.get()
            except asyncio.CancelledError:
                break
            await websocket.send_text(json.dumps({"type": "update", **msg}))
    except WebSocketDisconnect:
        logger.info("WebSocket 客户端断开")
    finally:
        state_store.unsubscribe(queue)


@router.websocket("/ws/v2/robots/{robot_id}/typed")
async def typed_ws(websocket: WebSocket, robot_id: str):
    """Push v2 typed payloads (runtime_status, control, trajectory, ...).

    Wire format:
        on connect: {"type": "snapshot", "robot_id": "...", "data": {...}}
        on update:  {"type": "<typed>", "robot_id": "...", "data": {...}, "ts": <float>}

    Clients can subscribe to *all* types or filter by sending
        {"action": "subscribe", "types": ["runtime_status", "control"]}
    over the socket. Default is "all". Filtering is client-side today;
    the server always pushes everything and lets the client drop what
    it does not want. (Future: server-side filter.)
    """
    await websocket.accept()
    queue = typed_state.subscribe()
    try:
        await websocket.send_text(json.dumps({
            "type": "snapshot",
            "robot_id": robot_id,
            "data": typed_state.snapshot(robot_id),
        }))
        while True:
            try:
                msg = await queue.get()
            except asyncio.CancelledError:
                break
            if msg["robot_id"] != robot_id:
                continue
            await websocket.send_text(json.dumps(msg))
    except WebSocketDisconnect:
        logger.info("typed ws 客户端断开: %s", robot_id)
    finally:
        typed_state.unsubscribe(queue)
