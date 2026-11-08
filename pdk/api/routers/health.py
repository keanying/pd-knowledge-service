from __future__ import annotations

from fastapi import APIRouter
from sqlalchemy import text

from pdk import __version__
from pdk.db.session import engine

router = APIRouter(tags=["健康检查"])


@router.get("/healthz", summary="存活探针")
async def healthz() -> dict:
    return {"status": "ok", "version": __version__}


@router.get("/readyz", summary="就绪探针（检查数据库）")
async def readyz() -> dict:
    async with engine().connect() as c:
        await c.execute(text("select 1"))
    return {"status": "ready"}
