"""统计（OPS-01，工作台）。"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

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
    # 近 7 日：每日上传 / 发布 / 失败的版本数，以及最近动态（工作台周视图与趋势图）
    since = datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(days=6)
    rows = (await s.execute(kb_scope(select(DocVersion, Document.title, KnowledgeBase.name)
                                     .join(Document, Document.id == DocVersion.document_id)
                                     .join(KnowledgeBase, KnowledgeBase.id == DocVersion.kb_id)
                                     .where(DocVersion.created_at >= since), DocVersion.kb_id)
                            .order_by(DocVersion.created_at.desc()))).all()
    days = [(since + timedelta(days=i)).date() for i in range(7)]
    week = {d.isoformat(): {"date": d.isoformat(), "uploads": 0, "published": 0, "failed": 0, "chunks": 0} for d in days}
    events = []
    for v, title, kb_name in rows:
        created = v.created_at if v.created_at.tzinfo else v.created_at.replace(tzinfo=UTC)
        day = week.get(created.astimezone(UTC).date().isoformat())
        if day:
            day["uploads"] += 1
            day["published"] += v.status in (VersionStatus.PUBLISHED, VersionStatus.SUPERSEDED)
            day["failed"] += v.status == VersionStatus.FAILED
            day["chunks"] += int((v.stats or {}).get("chunks", 0))
        if len(events) < 12:
            events.append({"title": title, "version_no": v.version_no, "status": v.status, "kb_name": kb_name,
                           "document_id": v.document_id, "kb_id": v.kb_id, "created_at": created.isoformat()})
    mine = (await s.execute(kb_scope(select(Document.id, Document.title, Document.status, Document.kb_id, Document.updated_at)
                                     .where(Document.created_by == ctx.user_id, Document.status != DocStatus.DELETED),
                                     Document.kb_id).order_by(Document.updated_at.desc()).limit(5))).all()
    return ok({"kb_count": kbs, "doc_by_status": by_status, "doc_count": sum(by_status.values()),
               "pending_review": pending_review, "failed_tasks": failed, "open_tickets": open_tickets,
               "week": list(week.values()), "events": events,
               "my_recent": [{"id": r.id, "title": r.title, "status": r.status, "kb_id": r.kb_id,
                              "updated_at": r.updated_at} for r in mine]})
