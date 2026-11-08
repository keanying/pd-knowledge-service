from __future__ import annotations

import os

os.environ.update({
    "PDK_ENV": "test",
    "PDK_AUTH_MODE": "dev",
    # 设置 PDK_TEST_DATABASE_URL 可在 PostgreSQL 上跑（需先 alembic upgrade head）
    "PDK_DATABASE_URL": os.environ.get("PDK_TEST_DATABASE_URL", "sqlite+aiosqlite:///:memory:"),
    "PDK_VECTOR_STORE": "memory",
    "PDK_EMBED_PROVIDER": "hash",
    "PDK_EMBED_DIM": "256",
    "PDK_TASK_MODE": "inline",
})

import pytest  # noqa: E402
import pytest_asyncio  # noqa: E402
from httpx import ASGITransport, AsyncClient  # noqa: E402


@pytest.fixture(autouse=True)
def _isolated(tmp_path, monkeypatch):
    """每个用例独立的对象存储、向量库、缓存与数据库。"""
    from pdk.ai import embedding
    from pdk.core import cache
    from pdk.storage import objects, vectors

    monkeypatch.setenv("PDK_OBJECT_STORE_ROOT", str(tmp_path / "objects"))
    monkeypatch.chdir(tmp_path)
    from pdk.config import get_settings

    get_settings.cache_clear()
    objects.set_object_store(None)
    vectors.set_vector_store(None)
    embedding.set_embedder(None)
    cache.set_cache(None)
    yield
    get_settings.cache_clear()


@pytest_asyncio.fixture
async def client():
    """应用生命周期在单独的任务中进出（MCP 会话管理器使用 anyio 取消域，进出必须在同一任务）。"""
    import asyncio

    from pdk.main import create_app

    app = create_app()
    started, stop = asyncio.Event(), asyncio.Event()

    async def lifespan():
        async with app.router.lifespan_context(app):
            started.set()
            await stop.wait()

    task = asyncio.create_task(lifespan())
    await started.wait()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c
    stop.set()
    await task


@pytest_asyncio.fixture
async def wait():
    from pdk.ingest.runner import wait_background

    return wait_background


def ok(resp):
    body = resp.json()
    assert resp.status_code == 200 and body["code"] == 0, body
    return body["data"]
