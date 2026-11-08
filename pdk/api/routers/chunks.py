"""切片预览与编辑（CHK-07）、上下文（pdk_get_context）。编辑已发布的切片只重算该切片向量。"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from pdk.auth.context import AuthContext
from pdk.auth.deps import require
from pdk.chunking.base import ChunkDraft, chunk_key
from pdk.core.errors import BizError, ErrorCode, not_found
from pdk.core.response import Page, R, ok
from pdk.db.models import Chunk, DocStatus, Document, DocVersion
from pdk.db.session import get_session
from pdk.enrich.pii import detect, mask
from pdk.ingest.vectors import embed_rows, main_collection
from pdk.services.audit import audit
from pdk.storage.vectors import get_vector_store

router = APIRouter(prefix="/api/v1", tags=["切片"])


class ChunkView(BaseModel):
    id: str
    chunk_id: str
    seq: int
    chunk_type: str
    content: str
    title_path: str | None
    page_no: int | None
    tags: list[str]
    pii_types: list[str]
    enabled: bool
    edited: bool


def _view(c: Chunk, reveal: bool) -> ChunkView:
    content = c.content if reveal or not c.pii_types else mask(c.content, c.pii_types)[0]
    return ChunkView(id=c.id, chunk_id=c.chunk_key, seq=c.seq, chunk_type=c.chunk_type, content=content,
                     title_path=c.title_path, page_no=c.page_no, tags=c.tags or [], pii_types=c.pii_types or [],
                     enabled=c.enabled, edited=c.edited)


async def _version(s: AsyncSession, ctx: AuthContext, version_id: str, action: str) -> tuple[DocVersion, Document]:
    v = await s.get(DocVersion, version_id)
    if v is None:
        raise not_found("版本")
    d = await s.get(Document, v.document_id)
    assert d is not None
    ctx.require_kb(d.kb_id, action)
    if d.security_level > ctx.max_security_level:
        raise BizError(ErrorCode.SECURITY_LEVEL_EXCEEDED)
    return v, d


@router.get("/versions/{version_id}/chunks", summary="切片列表")
async def list_chunks(version_id: str, keyword: str | None = None, page: int = Query(1, ge=1),
                      page_size: int = Query(50, ge=1, le=200), ctx: AuthContext = Depends(require("pdk:doc:view")),
                      s: AsyncSession = Depends(get_session)) -> R[Page[ChunkView]]:
    await _version(s, ctx, version_id, "read")
    q = select(Chunk).where(Chunk.version_id == version_id).order_by(Chunk.seq)
    if keyword:
        q = q.where(Chunk.content.contains(keyword))
    rows = (await s.execute(q)).scalars().all()
    reveal = ctx.has("pdk:doc:edit") and ctx.can_kb(rows[0].kb_id, "write") if rows else False
    return ok(Page(total=len(rows), items=[_view(c, reveal) for c in rows[(page - 1) * page_size: page * page_size]]))


class ChunkUpdate(BaseModel):
    content: str | None = Field(None, min_length=1, max_length=8000)
    enabled: bool | None = None
    tags: list[str] | None = None


@router.put("/chunks/{chunk_row_id}", summary="编辑 / 启用 / 禁用切片")
async def update_chunk(chunk_row_id: str, req: ChunkUpdate, ctx: AuthContext = Depends(require("pdk:doc:edit")),
                       s: AsyncSession = Depends(get_session)) -> R[ChunkView]:
    c = await s.get(Chunk, chunk_row_id)
    if c is None:
        raise not_found("切片")
    _, d = await _version(s, ctx, c.version_id, "write")
    live = d.current_version_id == c.version_id and d.status == DocStatus.PUBLISHED
    store, col = get_vector_store(), main_collection()
    old_key = c.chunk_key
    if req.content is not None and req.content != c.content:
        draft = ChunkDraft(seq=c.seq, text=req.content, embed_text=req.content, title_path=c.title_path)
        c.content = req.content
        c.embed_text = f"{c.title_path}\n{req.content}" if c.title_path else req.content
        c.content_hash = draft.content_hash
        c.chunk_key = chunk_key(d.id, c.content_hash, 1000 + c.seq)  # 人工编辑的切片单独消歧
        c.pii_types = detect(req.content)
        c.edited = True
    if req.tags is not None:
        c.tags = req.tags
    if req.enabled is not None:
        c.enabled = req.enabled
    await s.commit()
    if live:
        if old_key != c.chunk_key or not c.enabled:
            await store.delete(col, [old_key])
        if c.enabled:
            await store.upsert(col, await embed_rows([c], d))
    audit.emit(ctx, "ADMIN_OP", f"编辑切片：{d.title}#{c.seq}", target_type="pdk:kb", target_ids=d.kb_id,
               scenic_id=d.scenic_id, chunk=c.chunk_key)
    return ok(_view(c, True))


@router.get("/chunks/{chunk_id}/context", summary="切片上下文（前后相邻切片）")
async def context(chunk_id: str, window: int = Query(1, ge=0, le=5),
                  ctx: AuthContext = Depends(require("pdk:search:use", "pdk:doc:view")),
                  s: AsyncSession = Depends(get_session)) -> R[list[ChunkView]]:
    row = (await s.execute(select(Chunk, Document).join(Document, Document.id == Chunk.document_id)
                           .where(Chunk.chunk_key == chunk_id, Chunk.version_id == Document.current_version_id,
                                  Document.status == DocStatus.PUBLISHED))).first()
    if row is None:
        raise not_found("切片")
    c, d = row
    ctx.require_kb(d.kb_id, "read")
    if d.security_level > ctx.max_security_level:
        raise BizError(ErrorCode.SECURITY_LEVEL_EXCEEDED)
    rows = (await s.execute(select(Chunk).where(Chunk.version_id == c.version_id, Chunk.enabled.is_(True),
                                                Chunk.seq.between(c.seq - window, c.seq + window))
                            .order_by(Chunk.seq))).scalars().all()
    return ok([_view(x, False) for x in rows])
