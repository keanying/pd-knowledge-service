"""流水线执行与任务记录（sys_task）。inline 模式在 API 进程内后台执行；celery 模式投递到队列由 Worker 执行。"""

from __future__ import annotations

import asyncio
import logging

from pdk.config import get_settings
from pdk.core.errors import BizError
from pdk.core.ids import new_id
from pdk.db.base import utcnow
from pdk.db.models import DocVersion, Task, TaskStatus, VersionStatus
from pdk.db.scenic import system_scope
from pdk.db.session import session_factory
from pdk.ingest.graph import Step, graph
from pdk.parsers.base import ParseError

log = logging.getLogger("pdk.ingest")
_background: set[asyncio.Task] = set()


async def create_task(type_: str, ref_id: str, scenic_id: str | None, user_id: str | None, priority: int = 5) -> str:
    async with session_factory()() as s:
        t = Task(id=new_id("tk"), type=type_, ref_id=ref_id, scenic_id=scenic_id, created_by=user_id, priority=priority)
        s.add(t)
        await s.commit()
        return t.id


async def run_ingest(task_id: str, version_id: str, start: Step = "parse") -> None:
    async with session_factory()() as s:
        t = await s.get(Task, task_id)
        if t is None or t.status == TaskStatus.CANCELLED:
            return
        t.status, t.started_at, t.step, t.error = TaskStatus.RUNNING, utcnow(), start, None
        await s.commit()
    try:
        result = await graph().ainvoke({"version_id": version_id, "start": start, "done": []},
                                       config={"configurable": {"thread_id": version_id}})
        status, error = TaskStatus.SUCCEEDED, None
        step = (result.get("done") or [start])[-1]
    except (ParseError, BizError) as e:
        status, error, step = TaskStatus.FAILED, str(e), None
    except Exception as e:  # noqa: BLE001
        log.exception("流水线失败：version=%s", version_id)
        status, error, step = TaskStatus.FAILED, f"系统错误：{e.__class__.__name__}: {e}", None
    async with session_factory()() as s:
        t = await s.get(Task, task_id)
        assert t is not None
        t.status, t.finished_at, t.error = status, utcnow(), error
        t.progress = 100 if status == TaskStatus.SUCCEEDED else t.progress
        if step:
            t.step = step
        if error:
            with system_scope("记录流水线失败"):
                v = await s.get(DocVersion, version_id)
                if v is not None:
                    v.status, v.error = VersionStatus.FAILED, error
        await s.commit()


def dispatch(task_id: str, version_id: str, start: Step = "parse") -> None:
    if get_settings().task_mode == "celery":
        from pdk.workers.celery_app import celery_app

        queue = "pdk.parse" if start in ("parse", "chunk") else "pdk.embed"
        celery_app.send_task("pdk.ingest", args=[task_id, version_id, start], queue=queue)
        return
    t = asyncio.get_running_loop().create_task(run_ingest(task_id, version_id, start))
    _background.add(t)
    t.add_done_callback(_background.discard)


async def wait_background() -> None:
    """测试用：等待进程内后台任务完成。"""
    while _background:
        await asyncio.gather(*list(_background), return_exceptions=True)
