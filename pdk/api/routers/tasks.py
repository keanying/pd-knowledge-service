"""任务中心（SYS-01）。"""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from pdk.auth.context import AuthContext
from pdk.auth.deps import require
from pdk.core.errors import BizError, ErrorCode, not_found
from pdk.core.response import Page, R, ok
from pdk.db.models import DocVersion, Task, TaskStatus
from pdk.db.session import get_session
from pdk.ingest import runner

router = APIRouter(prefix="/api/v1/tasks", tags=["任务中心"])


class TaskView(BaseModel):
    id: str
    type: str
    ref_id: str
    scenic_id: str | None
    status: str
    step: str | None
    progress: int
    error: str | None
    retries: int
    created_by: str | None
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None
    model_config = {"from_attributes": True}


def _scenic_filter(q, ctx: AuthContext):
    return q.where(Task.scenic_id.in_(sorted(ctx.scenic_ids_with_group)))


@router.get("", summary="任务列表")
async def list_tasks(status: str | None = None, type: str | None = None, page: int = Query(1, ge=1),
                     page_size: int = Query(20, ge=1, le=100), ctx: AuthContext = Depends(require("pdk:task:manage", "pdk:doc:upload")),
                     s: AsyncSession = Depends(get_session)) -> R[Page[TaskView]]:
    q = _scenic_filter(select(Task), ctx)
    if not ctx.has("pdk:task:manage"):
        q = q.where(Task.created_by == ctx.user_id)
    if status:
        q = q.where(Task.status == status)
    if type:
        q = q.where(Task.type == type)
    total = (await s.execute(q.with_only_columns(func.count(Task.id)))).scalar_one()
    rows = (await s.execute(q.order_by(Task.created_at.desc()).offset((page - 1) * page_size).limit(page_size))).scalars().all()
    return ok(Page(total=total, items=[TaskView.model_validate(t) for t in rows]))


@router.post("/{task_id}:retry", summary="重试失败任务")
async def retry(task_id: str, ctx: AuthContext = Depends(require("pdk:task:manage")),
                s: AsyncSession = Depends(get_session)) -> R[TaskView]:
    t = await s.get(Task, task_id)
    if t is None or (t.scenic_id and t.scenic_id not in ctx.scenic_ids_with_group):
        raise not_found("任务")
    if t.status not in (TaskStatus.FAILED, TaskStatus.CANCELLED):
        raise BizError(ErrorCode.INVALID_STATE, "只有失败或已取消的任务可以重试")
    v = await s.get(DocVersion, t.ref_id)
    if v is not None:
        v.status, v.error = "pending", None
    t.status, t.retries, t.error = TaskStatus.QUEUED, t.retries + 1, None
    await s.commit()
    runner.dispatch(t.id, t.ref_id, "parse")
    return ok(TaskView.model_validate(t))


@router.post("/{task_id}:cancel", summary="取消排队中的任务")
async def cancel(task_id: str, ctx: AuthContext = Depends(require("pdk:task:manage")),
                 s: AsyncSession = Depends(get_session)) -> R[TaskView]:
    t = await s.get(Task, task_id)
    if t is None or (t.scenic_id and t.scenic_id not in ctx.scenic_ids_with_group):
        raise not_found("任务")
    if t.status != TaskStatus.QUEUED:
        raise BizError(ErrorCode.INVALID_STATE, "只能取消排队中的任务")
    t.status = TaskStatus.CANCELLED
    await s.commit()
    return ok(TaskView.model_validate(t))
