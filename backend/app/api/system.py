"""健康检查与元信息 API。"""
from fastapi import APIRouter

from app.core.config import settings
from app.services.robot_state import state_store

router = APIRouter(tags=["system"])


@router.get("/")
def root():
    return {
        "app": settings.app_name,
        "version": settings.app_version,
        "status": "ok",
        "mode": state_store.get_mode(),
    }


@router.get("/healthz")
def healthz():
    return {"status": "ok"}
