"""统计（OPS-01，工作台）。"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from pdk.auth.context import AuthContext
from pdk.auth.deps import require
from pdk.core.response import R, ok
from pdk.db.models import (
    DocStatus,
    Document,
    DocVersion,
    KbStatus,
    KnowledgeBase,
    Task,
    TaskStatus,
    Ticket,
    VersionStatus,
)
from pdk.db.session import get_session

router = APIRouter(prefix="/api/v1/stats", tags=["统计"])


@router.get("/overview", summary="工作台概览（按本人可见范围）")
async def overview(ctx: AuthContext = Depends(require("pdk:console:access")),
                   s: AsyncSession = Depends(get_session)) -> R[dict]:
    ids = ctx.kb_ids("read")

    def kb_scope(q, col):
        return q if ids is None else q.where(col.in_(sorted(ids)))

    kbs = (await s.execute(kb_scope(select(func.count(KnowledgeBase.id)).where(KnowledgeBase.status == KbStatus.ACTIVE),
                                    KnowledgeBase.id))).scalar_one()
    by_status = dict((await s.execute(kb_scope(select(Document.status, func.count(Document.id))
                                               .where(Document.status != DocStatus.DELETED), Document.kb_id)
                                      .group_by(Document.status))).all())
    pending_review = (await s.execute(kb_scope(select(func.count(DocVersion.id))
                                               .where(DocVersion.status == VersionStatus.PENDING_REVIEW), DocVersion.kb_id))).scalar_one()
    failed = (await s.execute(select(func.count(Task.id)).where(Task.status == TaskStatus.FAILED,
                                                                Task.scenic_id.in_(sorted(ctx.scenic_ids_with_group))))).scalar_one()
    open_tickets = (await s.execute(select(func.count(Ticket.id)).where(Ticket.status == "open"))).scalar_one()
    return ok({"kb_count": kbs, "doc_by_status": by_status, "doc_count": sum(by_status.values()),
               "pending_review": pending_review, "failed_tasks": failed, "open_tickets": open_tickets})
