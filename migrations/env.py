"""Alembic 迁移环境（异步引擎）。用法：PDK_DATABASE_URL=postgresql+asyncpg://... alembic upgrade head"""

from __future__ import annotations

import asyncio

from alembic import context
from sqlalchemy.ext.asyncio import create_async_engine

from pdk.config import get_settings
from pdk.db import models  # noqa: F401
from pdk.db.base import Base

target_metadata = Base.metadata


def run_offline() -> None:
    context.configure(url=get_settings().database_url, target_metadata=target_metadata, literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()


def _run(conn) -> None:
    context.configure(connection=conn, target_metadata=target_metadata, render_as_batch=conn.dialect.name == "sqlite")
    with context.begin_transaction():
        context.run_migrations()


async def run_online() -> None:
    engine = create_async_engine(get_settings().database_url)
    async with engine.connect() as conn:
        await conn.run_sync(_run)
    await engine.dispose()


if context.is_offline_mode():
    run_offline()
else:
    asyncio.run(run_online())
