"""pdk-api 入口：uvicorn pdk.main:app"""

from __future__ import annotations

import logging
import uuid
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from pdk import __version__
from pdk.api.routers import (
    api_keys,
    auth,
    chunks,
    documents,
    feedback,
    health,
    kbs,
    me,
    pds_events,
    reviews,
    search,
    stats,
    studio,
    tasks,
)
from pdk.config import get_settings
from pdk.core.context import current_trace_id, set_trace_id
from pdk.core.errors import BizError, ErrorCode
from pdk.core.logging import setup_logging
from pdk.db import scenic  # noqa: F401  注册景区隔离钩子
from pdk.db.session import create_all, dispose, init_engine
from pdk.services.audit import audit

log = logging.getLogger("pdk")
WEB_DIST = Path(__file__).resolve().parent.parent / "web" / "dist"


def _err(code: ErrorCode, message: str | None = None, data=None, trace_id: str | None = None) -> JSONResponse:
    return JSONResponse(status_code=code.http_status,
                        content={"code": code.code, "message": message or code.message, "data": data, "trace_id": trace_id})


def create_app() -> FastAPI:
    s = get_settings()
    from pdk.mcp.server import build_mcp

    mcp_server, mcp_asgi = build_mcp()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        init_engine()
        if s.database_url.startswith("sqlite"):
            await create_all()  # 开发：SQLite 自动建表；PostgreSQL 使用 alembic upgrade head
        audit.start()
        if s.sync_manifest_on_startup and s.auth_mode == "pds":
            from pdk.services.pds_sync import sync_manifest

            try:
                await sync_manifest()
                log.info("已向 PDS 提交权限清单")
            except Exception as e:  # noqa: BLE001
                log.warning("提交权限清单失败：%s", e)
        async with mcp_server.session_manager.run():
            yield
        await audit.stop()
        await dispose()

    app = FastAPI(title="PDK 知识服务", version=__version__, lifespan=lifespan,
                  description="知识库 · 检索 · 知识更新。统一响应 {code, message, data, trace_id}；权限由 PDS 统一控制。")

    @app.middleware("http")
    async def trace(request: Request, call_next):
        tid = request.headers.get("x-trace-id") or uuid.uuid4().hex[:16]
        set_trace_id(tid)
        resp = await call_next(request)
        resp.headers["X-Trace-Id"] = tid
        return resp

    @app.exception_handler(BizError)
    async def biz(request: Request, e: BizError):
        return _err(e.error, e.message, e.data, current_trace_id())

    @app.exception_handler(RequestValidationError)
    async def invalid(request: Request, e: RequestValidationError):
        first = e.errors()[0] if e.errors() else {}
        loc = ".".join(str(x) for x in first.get("loc", [])[1:])
        return _err(ErrorCode.VALIDATION_FAILED, f"参数校验失败：{loc} {first.get('msg', '')}".strip())

    @app.exception_handler(StarletteHTTPException)
    async def http_exc(request: Request, e: StarletteHTTPException):
        code = {404: ErrorCode.NOT_FOUND, 401: ErrorCode.UNAUTHENTICATED, 403: ErrorCode.NO_PERMISSION}.get(
            e.status_code, ErrorCode.BAD_REQUEST)
        return JSONResponse(status_code=e.status_code, content={"code": code.code, "message": str(e.detail), "data": None})

    @app.exception_handler(Exception)
    async def unknown(request: Request, e: Exception):
        log.exception("未处理的异常：%s %s", request.method, request.url.path)
        return _err(ErrorCode.INTERNAL)

    if s.cors_origins:
        app.add_middleware(CORSMiddleware, allow_origins=s.cors_origins, allow_credentials=True,
                           allow_methods=["*"], allow_headers=["*"])

    for r in (health, auth, me, kbs, documents, chunks, reviews, search, feedback, tasks, api_keys, stats,
              pds_events, studio):
        app.include_router(r.router)
    app.mount("/mcp", mcp_asgi)

    # 随 pdk-api 发布管理后台：web/dist 存在时提供静态页面（单页应用回退到 index.html）
    if WEB_DIST.is_dir():
        @app.get("/{path:path}", include_in_schema=False)
        async def spa(path: str):
            f = (WEB_DIST / path).resolve()
            if path and f.is_file() and str(f).startswith(str(WEB_DIST)):
                return FileResponse(f)
            return FileResponse(WEB_DIST / "index.html")

    return app


setup_logging(json_format=get_settings().env != "dev")
app = create_app()
