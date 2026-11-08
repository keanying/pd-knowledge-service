"""纠错闭环（UPD-05 / UPD-06）：PDA 点踩 / 纠错 / 更新建议 → 工单 → 指派知识库负责人。"""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from pdk.auth.context import AuthContext
from pdk.auth.deps import require
from pdk.core.errors import not_found
from pdk.core.ids import new_id
from pdk.core.response import R, ok
from pdk.db.base import utcnow
from pdk.db.models import Chunk, KnowledgeBase, Ticket
from pdk.db.session import get_session
from pdk.services.audit import audit

router = APIRouter(prefix="/api/v1", tags=["纠错与工单"])


class FeedbackReq(BaseModel):
    type: str = Field("correction", pattern="^(correction|suggestion|gap)$")
    question: str | None = None
    answer: str | None = None
    chunk_ids: list[str] = Field(default_factory=list)
    suggestion: str | None = None
    reason: str | None = None
    session_id: str | None = None


class TicketView(BaseModel):
    id: str
    type: str
    kb_id: str | None
    question: str | None
    suggestion: str | None
    reason: str | None
    chunk_ids: list[str]
    submitter_id: str | None
    assignee_id: str | None
    status: str
    created_at: datetime


def _view(t: Ticket) -> TicketView:
    return TicketView(id=t.id, type=t.type, kb_id=t.kb_id, question=t.question, suggestion=t.suggestion, reason=t.reason,
                      chunk_ids=t.chunk_keys or [], submitter_id=t.submitter_id, assignee_id=t.assignee_id,
                      status=t.status, created_at=t.created_at)


@router.post("/feedback", summary="提交纠错 / 更新建议 / 知识缺口")
async def submit(req: FeedbackReq, ctx: AuthContext = Depends(require("pdk:update:submit")),
                 s: AsyncSession = Depends(get_session)) -> R[TicketView]:
    kb_id, scenic, assignee = None, ctx.default_scenic or "GROUP", None
    if req.chunk_ids:
        row = (await s.execute(select(Chunk.kb_id, Chunk.scenic_id).where(Chunk.chunk_key.in_(req.chunk_ids)).limit(1))).first()
        if row:
            kb_id, scenic = row.kb_id, row.scenic_id
            kb = await s.get(KnowledgeBase, kb_id)
            assignee = kb.owner_id if kb else None
    t = Ticket(id=new_id("tkt"), type=req.type, kb_id=kb_id, scenic_id=scenic, question=req.question, answer=req.answer,
               chunk_keys=req.chunk_ids, suggestion=req.suggestion, reason=req.reason, session_id=req.session_id,
               submitter_id=ctx.user_id, assignee_id=assignee)
    s.add(t)
    await s.commit()
    audit.emit(ctx, "FEEDBACK", f"提交{'纠错' if req.type == 'correction' else '建议'}：{req.question or ''}",
               target_type="pdk:kb", target_ids=kb_id, scenic_id=scenic)
    return ok(_view(t))


@router.get("/tickets", summary="工单列表（有管理权的知识库 + 指派给我的）")
async def tickets(status: str | None = Query(None), ctx: AuthContext = Depends(require("pdk:update:review", "pdk:kb:view")),
                  s: AsyncSession = Depends(get_session)) -> R[list[TicketView]]:
    q = select(Ticket).order_by(Ticket.created_at.desc())
    if status:
        q = q.where(Ticket.status == status)
    rows = [t for t in (await s.execute(q)).scalars().all()
            if t.assignee_id == ctx.user_id or (t.kb_id and ctx.can_kb(t.kb_id, "admin")) or ctx.has("pdk:update:review")]
    return ok([_view(t) for t in rows])


class TicketUpdate(BaseModel):
    status: str | None = Field(None, pattern="^(open|processing|closed|rejected)$")
    assignee_id: str | None = None


@router.put("/tickets/{ticket_id}", summary="处理工单")
async def update_ticket(ticket_id: str, req: TicketUpdate, ctx: AuthContext = Depends(require("pdk:update:review", "pdk:doc:edit")),
                        s: AsyncSession = Depends(get_session)) -> R[TicketView]:
    t = await s.get(Ticket, ticket_id)
    if t is None:
        raise not_found("工单")
    if t.kb_id:
        ctx.require_kb(t.kb_id, "write")
    for k, v in req.model_dump(exclude_unset=True).items():
        setattr(t, k, v)
    if t.status in ("closed", "rejected"):
        t.closed_at = utcnow()
    await s.commit()
    return ok(_view(t))

