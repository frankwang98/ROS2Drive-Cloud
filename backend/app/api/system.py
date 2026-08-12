"""健康检查与元信息 API。"""
from fastapi import APIRouter

from app.core.config import settings

router = APIRouter(tags=["system"])


@router.get("/")
def root():
    return {
        "app": settings.app_name,
        "version": settings.app_version,
        "status": "ok",
    }


@router.get("/healthz")
def healthz():
    return {"status": "ok"}
