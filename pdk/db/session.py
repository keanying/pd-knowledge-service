"""异步数据库引擎与会话。"""

from __future__ import annotations

from collections.abc import AsyncIterator
from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine

from pdk.config import get_settings

_engine: AsyncEngine | None = None
_factory: async_sessionmaker[AsyncSession] | None = None


def init_engine(url: str | None = None) -> AsyncEngine:
    global _engine, _factory
    url = url or get_settings().database_url
    if url.startswith("sqlite"):
        path = url.split("///", 1)[-1]
        if path and path != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
    _engine = create_async_engine(url, pool_pre_ping=not url.startswith("sqlite"))
    _factory = async_sessionmaker(_engine, expire_on_commit=False)
    return _engine


def engine() -> AsyncEngine:
    if _engine is None:
        init_engine()
    assert _engine is not None
    return _engine


def session_factory() -> async_sessionmaker[AsyncSession]:
    if _factory is None:
        init_engine()
    assert _factory is not None
    return _factory


async def get_session() -> AsyncIterator[AsyncSession]:
    async with session_factory()() as s:
        yield s


async def create_all() -> None:
    """开发/测试快速建表；生产使用 Alembic 迁移（alembic upgrade head）。"""
    from pdk.db import models  # noqa: F401
    from pdk.db.base import Base

    async with engine().begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def dispose() -> None:
    global _engine, _factory
    if _engine is not None:
        await _engine.dispose()
    _engine, _factory = None, None
