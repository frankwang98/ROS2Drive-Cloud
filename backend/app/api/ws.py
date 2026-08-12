"""WebSocket 实时推送端点。

Web Dashboard 通过 WebSocket 订阅机器人状态变化（速度、行为、距离等）。
"""
import asyncio
import json
import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.services.robot_state import state_store

logger = logging.getLogger("robot.ws")

router = APIRouter(tags=["ws"])


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
