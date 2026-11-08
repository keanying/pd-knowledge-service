"""知识库管理（KB-01 ~ KB-09）。可见范围（授权）数据保存在 PDS 资源实例 pdk:kb:{id}，PDK 只做展示与发起。"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from pdk.auth.context import AuthContext
from pdk.auth.deps import require
from pdk.auth.pds_client import get_pds
from pdk.auth.snapshots import invalidate
from pdk.config import get_settings
from pdk.core.errors import BizError, ErrorCode, not_found
from pdk.core.ids import new_id
from pdk.core.response import R, ok
from pdk.db.base import utcnow
from pdk.db.models import Chunk, DocStatus, Document, KbStatus, KnowledgeBase
from pdk.db.session import get_session
from pdk.ingest.steps import unpublish_document
from pdk.services.audit import audit
from pdk.services.pds_sync import register_kb

router = APIRouter(prefix="/api/v1/kbs", tags=["知识库"])


class KbBase(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    description: str | None = None
    category: str | None = None
    icon: str | None = None
    dept_id: str | None = None
    default_security_level: int = Field(1, ge=0, le=3)
    chunk_strategy: dict[str, Any] = Field(default_factory=dict)
    retrieval_config: dict[str, Any] = Field(default_factory=dict)
    parse_config: dict[str, Any] = Field(default_factory=dict)
    review_required: bool = False
    default_tags: list[str] = Field(default_factory=list)


class KbCreate(KbBase):
    scenic_id: str | None = Field(None, description="所属景区；集团共享库填 GROUP；为空取本人所属景区")


class KbUpdate(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=128)
    description: str | None = None
    category: str | None = None
    icon: str | None = None
    default_security_level: int | None = Field(None, ge=0, le=3)
    chunk_strategy: dict[str, Any] | None = None
    retrieval_config: dict[str, Any] | None = None
    parse_config: dict[str, Any] | None = None
    review_required: bool | None = None
    default_tags: list[str] | None = None
    status: str | None = Field(None, pattern="^(active|archived)$")


class KbView(KbBase):
    id: str
    scenic_id: str
    embed_model: str
    status: str
    owner_id: str | None
    pds_registered: bool
    created_at: datetime
    updated_at: datetime
    doc_count: int = 0
    chunk_count: int = 0
    my_actions: list[str] = Field(default_factory=list)

    model_config = {"from_attributes": True}


def _view(kb: KnowledgeBase, ctx: AuthContext, counts: dict[str, tuple[int, int]] | None = None) -> KbView:
    v = KbView.model_validate(kb)
    v.doc_count, v.chunk_count = (counts or {}).get(kb.id, (0, 0))
    v.my_actions = [a for a in ("read", "write", "admin") if ctx.can_kb(kb.id, a)]
    return v


async def get_kb(s: AsyncSession, ctx: AuthContext, kb_id: str, action: str = "read") -> KnowledgeBase:
    kb = await s.get(KnowledgeBase, kb_id)
    if kb is None or kb.status == KbStatus.DELETED:
        raise not_found("知识库")
    ctx.require_kb(kb_id, action)
    return kb


async def _counts(s: AsyncSession, kb_ids: list[str]) -> dict[str, tuple[int, int]]:
    if not kb_ids:
        return {}
    docs = dict((await s.execute(select(Document.kb_id, func.count(Document.id))
                                 .where(Document.kb_id.in_(kb_ids), Document.status != DocStatus.DELETED)
                                 .group_by(Document.kb_id))).all())
    chunks = dict((await s.execute(select(Chunk.kb_id, func.count(Chunk.id))
                                   .join(Document, (Document.id == Chunk.document_id) & (Document.current_version_id == Chunk.version_id))
                                   .where(Chunk.kb_id.in_(kb_ids)).group_by(Chunk.kb_id))).all())
    return {k: (docs.get(k, 0), chunks.get(k, 0)) for k in kb_ids}


@router.get("", summary="知识库列表（只返回有查看权限的库）")
async def list_kbs(keyword: str | None = None, scenic_id: str | None = None, category: str | None = None,
                   status: str = "active", ctx: AuthContext = Depends(require("pdk:kb:view", "pdk:search:use")),
                   s: AsyncSession = Depends(get_session)) -> R[list[KbView]]:
    q = select(KnowledgeBase).where(KnowledgeBase.status == status).order_by(KnowledgeBase.created_at.desc())
    ids = ctx.kb_ids("read")
    if ids is not None:
        q = q.where(KnowledgeBase.id.in_(sorted(ids)))
    if keyword:
        q = q.where(KnowledgeBase.name.contains(keyword))
    if scenic_id:
        q = q.where(KnowledgeBase.scenic_id == scenic_id)
    if category:
        q = q.where(KnowledgeBase.category == category)
    kbs = (await s.execute(q)).scalars().all()
    counts = await _counts(s, [k.id for k in kbs])
    return ok([_view(k, ctx, counts) for k in kbs])


@router.post("", summary="新建知识库")
async def create_kb(req: KbCreate, ctx: AuthContext = Depends(require("pdk:kb:create")),
                    s: AsyncSession = Depends(get_session)) -> R[KbView]:
    scenic = req.scenic_id or ctx.default_scenic
    if not scenic:
        raise BizError(ErrorCode.VALIDATION_FAILED, "请选择所属景区")
    ctx.require_scenic(scenic)
    if not ctx.in_data_scope("pdk:kb:create", scenic_id=scenic, dept_id=req.dept_id):
        raise BizError(ErrorCode.NO_PERMISSION, "超出“新建知识库”的数据范围")
    if req.default_security_level > ctx.max_security_level:
        raise BizError(ErrorCode.SECURITY_LEVEL_EXCEEDED, "知识库默认密级不能高于本人可访问的密级")
    from pdk.ai.embedding import get_embedder

    kb = KnowledgeBase(id=new_id("kb"), scenic_id=scenic, embed_model=get_embedder().model, owner_id=ctx.user_id,
                       created_by=ctx.user_id, **req.model_dump(exclude={"scenic_id"}))
    s.add(kb)
    await s.commit()
    kb.pds_registered = await register_kb(kb)
    await s.commit()
    await invalidate([ctx.user_id])
    audit.emit(ctx, "ADMIN_OP", f"新建知识库：{kb.name}", target_type="pdk:kb", target_ids=kb.id, scenic_id=scenic)
    return ok(_view(kb, ctx))


@router.get("/{kb_id}", summary="知识库详情")
async def get_one(kb_id: str, ctx: AuthContext = Depends(require("pdk:kb:view")),
                  s: AsyncSession = Depends(get_session)) -> R[KbView]:
    kb = await get_kb(s, ctx, kb_id)
    return ok(_view(kb, ctx, await _counts(s, [kb.id])))


@router.put("/{kb_id}", summary="修改知识库配置")
async def update_kb(kb_id: str, req: KbUpdate, ctx: AuthContext = Depends(require("pdk:kb:edit")),
                    s: AsyncSession = Depends(get_session)) -> R[KbView]:
    kb = await get_kb(s, ctx, kb_id, "write")
    changes = req.model_dump(exclude_unset=True)
    for k, v in changes.items():
        setattr(kb, k, v)
    await s.commit()
    if not kb.pds_registered or "name" in changes:
        kb.pds_registered = await register_kb(kb)
        await s.commit()
    audit.emit(ctx, "ADMIN_OP", f"修改知识库：{kb.name}", target_type="pdk:kb", target_ids=kb.id,
               scenic_id=kb.scenic_id, fields=sorted(changes))
    return ok(_view(kb, ctx, await _counts(s, [kb.id])))


@router.delete("/{kb_id}", summary="删除知识库（软删除，30 天内可恢复；立即停止检索）")
async def delete_kb(kb_id: str, ctx: AuthContext = Depends(require("pdk:kb:delete")),
                    s: AsyncSession = Depends(get_session)) -> R[None]:
    kb = await get_kb(s, ctx, kb_id, "admin")
    docs = (await s.execute(select(Document).where(Document.kb_id == kb.id, Document.status == DocStatus.PUBLISHED))).scalars().all()
    for d in docs:
        await unpublish_document(s, d)
    kb.status, kb.deleted_at = KbStatus.DELETED, utcnow()
    await s.commit()
    audit.emit(ctx, "ADMIN_OP", f"删除知识库：{kb.name}", target_type="pdk:kb", target_ids=kb.id, scenic_id=kb.scenic_id)
    return ok(None)


# ---------------- 授权（数据在 PDS） ----------------
class GrantReq(BaseModel):
    subject_type: str = Field(pattern="^(USER|POSITION|ORG|GROUP)$")
    subject_id: str
    include_children: bool = False
    action: str = Field(pattern="^(READ|WRITE|ADMIN)$")
    effect: str = Field("ALLOW", pattern="^(ALLOW|DENY)$")
    valid_from: datetime | None = None
    valid_to: datetime | None = None
    reason: str | None = None


def _need_user_token(ctx: AuthContext) -> str:
    if get_settings().auth_mode == "dev" or not ctx.token:
        raise BizError(ErrorCode.INVALID_STATE, "授权需以本人身份登录后操作（开发模式与接口密钥不可用）")
    return ctx.token


@router.get("/{kb_id}/grants", summary="查看知识库授权（来自 PDS）")
async def grants(kb_id: str, ctx: AuthContext = Depends(require("pdk:kb:grant", "pdk:kb:view")),
                 s: AsyncSession = Depends(get_session)) -> R[Any]:
    await get_kb(s, ctx, kb_id, "admin")
    return ok(await get_pds().resource_grants("pdk:kb", kb_id, _need_user_token(ctx)))


@router.post("/{kb_id}/grants", summary="新增知识库授权（写入 PDS）")
async def add_grant(kb_id: str, req: GrantReq, ctx: AuthContext = Depends(require("pdk:kb:grant")),
                    s: AsyncSession = Depends(get_session)) -> R[Any]:
    kb = await get_kb(s, ctx, kb_id, "admin")
    body = {"subjectType": req.subject_type, "subjectId": req.subject_id, "includeChildren": req.include_children,
            "action": req.action, "effect": req.effect, "reason": req.reason,
            "validFrom": req.valid_from.isoformat() if req.valid_from else None,
            "validTo": req.valid_to.isoformat() if req.valid_to else None}
    res = await get_pds().grant_resource("pdk:kb", kb_id, body, _need_user_token(ctx))
    await invalidate()
    audit.emit(ctx, "GRANT", f"知识库授权：{kb.name}", target_type="pdk:kb", target_ids=kb_id, scenic_id=kb.scenic_id,
               subject=f"{req.subject_type}:{req.subject_id}", grant=f"{req.effect} {req.action}")
    return ok(res)


@router.delete("/{kb_id}/grants/{grant_id}", summary="撤销知识库授权")
async def revoke_grant(kb_id: str, grant_id: str, ctx: AuthContext = Depends(require("pdk:kb:grant")),
                       s: AsyncSession = Depends(get_session)) -> R[None]:
    kb = await get_kb(s, ctx, kb_id, "admin")
    await get_pds().revoke_resource("pdk:kb", kb_id, grant_id, _need_user_token(ctx))
    await invalidate()
    audit.emit(ctx, "GRANT", f"撤销知识库授权：{kb.name}", target_type="pdk:kb", target_ids=kb_id, scenic_id=kb.scenic_id)
    return ok(None)
