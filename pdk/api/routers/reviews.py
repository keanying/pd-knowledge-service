"""审核发布（UPD-03）：开启审核的知识库，新文档/新版本向量化后进入“待审核”，通过后发布。"""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from pdk.auth.context import AuthContext
from pdk.auth.deps import require
from pdk.core.errors import BizError, ErrorCode, not_found
from pdk.core.response import R, ok
from pdk.db.models import Document, DocVersion, VersionStatus
from pdk.db.session import get_session
from pdk.ingest.steps import step_publish
from pdk.ingest.vectors import staging_collection
from pdk.services.audit import audit
from pdk.storage.vectors import get_vector_store

router = APIRouter(prefix="/api/v1/reviews", tags=["审核"])


class ReviewItem(BaseModel):
    version_id: str
    document_id: str
    kb_id: str
    title: str
    version_no: int
    stats: dict
    created_by: str | None
    created_at: datetime


@router.get("", summary="待审核列表（本人有管理权的知识库）")
async def pending(ctx: AuthContext = Depends(require("pdk:doc:review")),
                  s: AsyncSession = Depends(get_session)) -> R[list[ReviewItem]]:
    q = (select(DocVersion, Document).join(Document, Document.id == DocVersion.document_id)
         .where(DocVersion.status == VersionStatus.PENDING_REVIEW).order_by(DocVersion.created_at))
    rows = [(v, d) for v, d in (await s.execute(q)).all() if ctx.can_kb(d.kb_id, "admin")]
    return ok([ReviewItem(version_id=v.id, document_id=d.id, kb_id=d.kb_id, title=d.title, version_no=v.version_no,
                          stats=v.stats or {}, created_by=v.created_by, created_at=v.created_at) for v, d in rows])


class ReviewReq(BaseModel):
    comment: str | None = None


async def _get(s: AsyncSession, ctx: AuthContext, version_id: str) -> tuple[DocVersion, Document]:
    v = await s.get(DocVersion, version_id)
    if v is None:
        raise not_found("版本")
    d = await s.get(Document, v.document_id)
    assert d is not None
    ctx.require_kb(d.kb_id, "admin")
    if v.status != VersionStatus.PENDING_REVIEW:
        raise BizError(ErrorCode.INVALID_STATE, "该版本不在待审核状态")
    if v.created_by == ctx.user_id and not ctx.has("pdk:update:review"):
        raise BizError(ErrorCode.NO_PERMISSION, "不能审核本人提交的版本")
    return v, d


@router.post("/{version_id}:approve", summary="审核通过并发布")
async def approve(version_id: str, req: ReviewReq, ctx: AuthContext = Depends(require("pdk:doc:review")),
                  s: AsyncSession = Depends(get_session)) -> R[None]:
    v, d = await _get(s, ctx, version_id)
    v.review_comment = req.comment
    await step_publish(s, v.id, ctx.user_id)
    audit.emit(ctx, "ADMIN_OP", f"审核通过：{d.title} v{v.version_no}", target_type="pdk:kb", target_ids=d.kb_id,
               scenic_id=d.scenic_id)
    return ok(None)


@router.post("/{version_id}:reject", summary="驳回")
async def reject(version_id: str, req: ReviewReq, ctx: AuthContext = Depends(require("pdk:doc:review")),
                 s: AsyncSession = Depends(get_session)) -> R[None]:
    v, d = await _get(s, ctx, version_id)
    v.status, v.reviewer_id, v.review_comment = VersionStatus.REJECTED, ctx.user_id, req.comment
    await s.commit()
    from pdk.db.models import Chunk

    keys = list((await s.execute(select(Chunk.chunk_key).where(Chunk.version_id == v.id))).scalars())
    await get_vector_store().delete(staging_collection(), keys)
    audit.emit(ctx, "ADMIN_OP", f"审核驳回：{d.title} v{v.version_no}", target_type="pdk:kb", target_ids=d.kb_id,
               scenic_id=d.scenic_id, reason=req.comment)
    return ok(None)
