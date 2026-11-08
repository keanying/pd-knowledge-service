"""Celery Worker（PDK_TASK_MODE=celery）。解析与向量化分队列，独立扩容：

    celery -A pdk.workers.celery_app worker -Q pdk.parse -c 4 -n parse@%h
    celery -A pdk.workers.celery_app worker -Q pdk.embed -c 8 -n embed@%h
"""

from __future__ import annotations

import asyncio

from celery import Celery

from pdk.config import get_settings

celery_app = Celery("pdk", broker=get_settings().celery_broker_url)
celery_app.conf.update(task_acks_late=True, worker_prefetch_multiplier=1, task_default_queue="pdk.parse",
                       broker_connection_retry_on_startup=True)


@celery_app.task(name="pdk.ingest", bind=True, max_retries=3)
def ingest(self, task_id: str, version_id: str, start: str = "parse") -> None:
    from pdk.db.session import dispose, init_engine
    from pdk.ingest.runner import run_ingest

    async def main() -> None:
        init_engine()  # 每次 asyncio.run 都是新事件循环，连接池不能跨循环复用
        try:
            await run_ingest(task_id, version_id, start)  # type: ignore[arg-type]
        finally:
            await dispose()

    asyncio.run(main())
