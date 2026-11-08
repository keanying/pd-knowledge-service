"""文档接入与版本（DOC / UPD）。上传后进入接入流水线：解析 → 切片 → 向量化 →（审核）→ 发布。"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from typing import Any
from urllib.parse import quote

from fastapi import APIRouter, Depends, File, Form, Query, UploadFile
from fastapi.responses import RedirectResponse, Response
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from pdk.api.routers.kbs import get_kb
from pdk.auth.context import AuthContext
from pdk.auth.deps import require
from pdk.config import get_settings
from pdk.core.errors import BizError, ErrorCode, not_found
from pdk.core.ids import new_id
from pdk.core.response import Page, R, ok
from pdk.db.base import utcnow
from pdk.db.models import DocStatus, Document, DocVersion, KnowledgeBase, Task, VersionStatus
from pdk.db.session import get_session
from pdk.ingest import runner
from pdk.ingest.steps import step_publish, unpublish_document
from pdk.ingest.vectors import embed_rows, main_collection
from pdk.parsers.base import SUPPORTED_TYPES, file_type_of
from pdk.services.audit import audit
from pdk.storage.objects import get_object_store, version_prefix
from pdk.storage.vectors import get_vector_store

router = APIRouter(prefix="/api/v1", tags=["文档"])


class VersionView(BaseModel):
    id: str
    version_no: int
    file_name: str
    file_size: int
    status: str
    error: str | None
    stats: dict[str, Any]
    created_by: str | None
    created_at: datetime
    published_at: datetime | None
    model_config = {"from_attributes": True}


class DocView(BaseModel):
    id: str
    kb_id: str
    scenic_id: str
    title: str
    file_type: str
    source_type: str
    security_level: int
    tags: list[str]
    effective_from: datetime | None
    effective_to: datetime | None
    owner_id: str | None
    status: str
    current_version_id: str | None
    latest_version_no: int
    created_at: datetime
    updated_at: datetime
    latest: VersionView | None = None
    model_config = {"from_attributes": True}


class DocUpdate(BaseModel):
    title: str | None = Field(None, min_length=1, max_length=256)
    tags: list[str] | None = None
    security_level: int | None = Field(None, ge=0, le=3)
    effective_from: datetime | None = None
    effective_to: datetime | None = None
    owner_id: str | None = None


def _parse_tags(raw: str | None) -> list[str]:
    if not raw:
        return []
    try:
        val = json.loads(raw)
        if isinstance(val, list):
            return [str(x) for x in val]
    except json.JSONDecodeError:
        pass
    return [t.strip() for t in raw.replace("，", ",").split(",") if t.strip()]


async def _doc(s: AsyncSession, ctx: AuthContext, doc_id: str, action: str = "read") -> Document:
    d = await s.get(Document, doc_id)
    if d is None or d.status == DocStatus.DELETED:
        raise not_found("文档")
    ctx.require_kb(d.kb_id, action)
    if d.security_level > ctx.max_security_level:
        raise BizError(ErrorCode.SECURITY_LEVEL_EXCEEDED)
    return d


async def _latest(s: AsyncSession, doc_ids: list[str]) -> dict[str, DocVersion]:
    if not doc_ids:
        return {}
    sub = (select(DocVersion.document_id, func.max(DocVersion.version_no).label("n"))
           .where(DocVersion.document_id.in_(doc_ids)).group_by(DocVersion.document_id).subquery())
    rows = (await s.execute(select(DocVersion).join(sub, (DocVersion.document_id == sub.c.document_id)
                                                     & (DocVersion.version_no == sub.c.n)))).scalars().all()
    return {v.document_id: v for v in rows}


def _view(d: Document, latest: DocVersion | None) -> DocView:
    v = DocView.model_validate(d)
    v.latest = VersionView.model_validate(latest) if latest else None
    return v


async def _store_version(s: AsyncSession, ctx: AuthContext, kb: KnowledgeBase, doc: Document, file: UploadFile,
                         data: bytes, file_hash: str) -> tuple[DocVersion, str]:
    doc.latest_version_no += 1
    no = doc.latest_version_no
    key = f"{version_prefix(doc.scenic_id, kb.id, doc.id, no)}/source.{doc.file_type}"
    await get_object_store().put(key, data, file.content_type)
    v = DocVersion(id=new_id("dv"), document_id=doc.id, kb_id=kb.id, scenic_id=doc.scenic_id, version_no=no,
                   file_name=file.filename or f"source.{doc.file_type}", file_hash=file_hash, file_size=len(data),
                   object_key=key, created_by=ctx.user_id)
    s.add(v)
    await s.commit()
    task_id = await runner.create_task("ingest", v.id, doc.scenic_id, ctx.user_id, priority=9)
    runner.dispatch(task_id, v.id)
    return v, task_id


async def _read_upload(file: UploadFile) -> tuple[bytes, str, str]:
    ft = file_type_of(file.filename or "")
    if ft not in SUPPORTED_TYPES:
        raise BizError(ErrorCode.FILE_TYPE_UNSUPPORTED, f"不支持的文件格式：{ft or '未知'}")
    data = await file.read()
    limit = get_settings().max_upload_mb * 1024 * 1024
    if len(data) > limit:
        raise BizError(ErrorCode.FILE_TOO_LARGE, f"文件超过 {get_settings().max_upload_mb}MB 上限")
    if not data:
        raise BizError(ErrorCode.VALIDATION_FAILED, "文件内容为空")
    return data, ft, hashlib.sha256(data).hexdigest()


@router.post("/kbs/{kb_id}/documents", summary="上传文档（multipart），自动进入接入流水线")
async def upload(kb_id: str, file: UploadFile = File(...), title: str | None = Form(None),
                 tags: str | None = Form(None, description="逗号分隔或 JSON 数组"),
                 security_level: int | None = Form(None, ge=0, le=3), source_type: str = Form("upload"),
                 effective_from: datetime | None = Form(None), effective_to: datetime | None = Form(None),
                 ctx: AuthContext = Depends(require("pdk:doc:upload")),
                 s: AsyncSession = Depends(get_session)) -> R[dict]:
    kb = await get_kb(s, ctx, kb_id, "write")
    data, ft, file_hash = await _read_upload(file)
    level = kb.default_security_level if security_level is None else security_level
    if level < kb.default_security_level:
        raise BizError(ErrorCode.VALIDATION_FAILED, "文档密级不能低于知识库默认密级")
    if level > ctx.max_security_level:
        raise BizError(ErrorCode.SECURITY_LEVEL_EXCEEDED, "文档密级高于本人可访问的密级，不能上传（可在 PDS 中调整本人密级）")
    dup = (await s.execute(select(Document.id, Document.title).join(DocVersion, DocVersion.document_id == Document.id)
                           .where(Document.kb_id == kb.id, DocVersion.file_hash == file_hash,
                                  Document.status != DocStatus.DELETED).limit(1))).first()
    if dup:
        raise BizError(ErrorCode.DUPLICATE_FILE, f"文件已存在：《{dup.title}》，可作为该文档的新版本上传",
                       data={"document_id": dup.id})
    doc = Document(id=new_id("d"), kb_id=kb.id, scenic_id=kb.scenic_id, title=title or (file.filename or "").rsplit(".", 1)[0],
                   file_type=ft, source_type=source_type if source_type in ("upload", "faq") else "upload",
                   security_level=level, tags=list(dict.fromkeys((kb.default_tags or []) + _parse_tags(tags))),
                   effective_from=effective_from, effective_to=effective_to, owner_id=ctx.user_id,
                   dept_id=ctx.snapshot.user.deptId, created_by=ctx.user_id)
    s.add(doc)
    await s.flush()
    v, task_id = await _store_version(s, ctx, kb, doc, file, data, file_hash)
    audit.emit(ctx, "DATA_UPLOAD", f"上传文档：{doc.title}", target_type="pdk:kb", target_ids=kb.id,
               scenic_id=kb.scenic_id, document=doc.id, size=len(data))
    return ok({"document_id": doc.id, "version_id": v.id, "task_id": task_id})


@router.post("/documents/{doc_id}/versions", summary="上传新版本（增量更新：只重算变化的切片）")
async def upload_version(doc_id: str, file: UploadFile = File(...), ctx: AuthContext = Depends(require("pdk:doc:upload")),
                         s: AsyncSession = Depends(get_session)) -> R[dict]:
    doc = await _doc(s, ctx, doc_id, "write")
    kb = await get_kb(s, ctx, doc.kb_id, "write")
    data, ft, file_hash = await _read_upload(file)
    if ft != doc.file_type and not (ft in ("md", "txt") and doc.file_type in ("md", "txt")):
        raise BizError(ErrorCode.VALIDATION_FAILED, f"新版本格式（{ft}）与原文档（{doc.file_type}）不一致")
    v, task_id = await _store_version(s, ctx, kb, doc, file, data, file_hash)
    audit.emit(ctx, "DATA_UPLOAD", f"上传新版本：{doc.title} v{v.version_no}", target_type="pdk:kb", target_ids=kb.id,
               scenic_id=kb.scenic_id, document=doc.id)
    return ok({"document_id": doc.id, "version_id": v.id, "task_id": task_id})


@router.get("/documents", summary="文档列表")
async def list_docs(kb_id: str | None = None, status: str | None = None, keyword: str | None = None,
                    tag: str | None = None, page: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=100),
                    ctx: AuthContext = Depends(require("pdk:doc:view")),
                    s: AsyncSession = Depends(get_session)) -> R[Page[DocView]]:
    q = select(Document).where(Document.status != DocStatus.DELETED, Document.security_level <= ctx.max_security_level)
    ids = ctx.kb_ids("read")
    if kb_id:
        ctx.require_kb(kb_id)
        q = q.where(Document.kb_id == kb_id)
    elif ids is not None:
        q = q.where(Document.kb_id.in_(sorted(ids)))
    if status:
        q = q.where(Document.status == status)
    if keyword:
        q = q.where(Document.title.contains(keyword))
    q = q.order_by(Document.updated_at.desc())
    if tag:  # 标签存 JSON 数组，各数据库语法不同，这里在应用层过滤（标签筛选的数据量通常不大）
        docs = [d for d in (await s.execute(q)).scalars().all() if tag in (d.tags or [])]
        total, docs = len(docs), docs[(page - 1) * page_size: page * page_size]
    else:
        total = (await s.execute(q.with_only_columns(func.count(Document.id)).order_by(None))).scalar_one()
        docs = list((await s.execute(q.offset((page - 1) * page_size).limit(page_size))).scalars().all())
    latest = await _latest(s, [d.id for d in docs])
    return ok(Page(total=total, items=[_view(d, latest.get(d.id)) for d in docs]))


@router.get("/documents/{doc_id}", summary="文档详情（含全部版本）")
async def get_doc(doc_id: str, ctx: AuthContext = Depends(require("pdk:doc:view")),
                  s: AsyncSession = Depends(get_session)) -> R[dict]:
    d = await _doc(s, ctx, doc_id)
    versions = (await s.execute(select(DocVersion).where(DocVersion.document_id == d.id)
                                .order_by(DocVersion.version_no.desc()))).scalars().all()
    tasks = (await s.execute(select(Task).where(Task.ref_id.in_([v.id for v in versions]))
                             .order_by(Task.created_at.desc()))).scalars().all()
    return ok({"document": _view(d, versions[0] if versions else None),
               "versions": [VersionView.model_validate(v) for v in versions],
               "tasks": [{"id": t.id, "version_id": t.ref_id, "status": t.status, "step": t.step, "error": t.error,
                          "created_at": t.created_at} for t in tasks]})


@router.put("/documents/{doc_id}", summary="修改文档元数据（已发布的同步更新向量库中的过滤字段）")
async def update_doc(doc_id: str, req: DocUpdate, ctx: AuthContext = Depends(require("pdk:doc:edit")),
                     s: AsyncSession = Depends(get_session)) -> R[DocView]:
    d = await _doc(s, ctx, doc_id, "write")
    if not ctx.in_data_scope("pdk:doc:edit", owner_id=d.owner_id, dept_id=d.dept_id, scenic_id=d.scenic_id):
        raise BizError(ErrorCode.NO_PERMISSION, "超出“编辑文档”的数据范围")
    changes = req.model_dump(exclude_unset=True)
    if "security_level" in changes and changes["security_level"] > ctx.max_security_level:
        raise BizError(ErrorCode.SECURITY_LEVEL_EXCEEDED)
    for k, v in changes.items():
        setattr(d, k, v)
    await s.commit()
    if d.status == DocStatus.PUBLISHED and set(changes) & {"tags", "security_level", "effective_from", "effective_to"}:
        await _resync_vectors(s, d)
    audit.emit(ctx, "ADMIN_OP", f"修改文档：{d.title}", target_type="pdk:kb", target_ids=d.kb_id,
               scenic_id=d.scenic_id, fields=sorted(changes))
    return ok(_view(d, None))


async def _resync_vectors(s: AsyncSession, d: Document) -> None:
    from pdk.db.models import Chunk

    chunks = (await s.execute(select(Chunk).where(Chunk.version_id == d.current_version_id, Chunk.enabled.is_(True)))).scalars().all()
    store = get_vector_store()
    existing = {r.pk: r for r in await store.get(main_collection(), [c.chunk_key for c in chunks])}
    from pdk.ingest.vectors import to_row

    rows = [to_row(c, d, existing[c.chunk_key].dense) for c in chunks if c.chunk_key in existing]
    missing = [c for c in chunks if c.chunk_key not in existing]
    rows += await embed_rows(missing, d)
    await store.upsert(main_collection(), rows)


@router.post("/documents/{doc_id}:offline", summary="下线（立即停止检索，保留数据）")
async def offline(doc_id: str, ctx: AuthContext = Depends(require("pdk:doc:edit")),
                  s: AsyncSession = Depends(get_session)) -> R[None]:
    d = await _doc(s, ctx, doc_id, "write")
    if d.status != DocStatus.PUBLISHED:
        raise BizError(ErrorCode.INVALID_STATE, "只有已发布的文档可以下线")
    await unpublish_document(s, d)
    audit.emit(ctx, "ADMIN_OP", f"下线文档：{d.title}", target_type="pdk:kb", target_ids=d.kb_id, scenic_id=d.scenic_id)
    return ok(None)


@router.post("/documents/{doc_id}:online", summary="重新上线当前版本")
async def online(doc_id: str, ctx: AuthContext = Depends(require("pdk:doc:edit")),
                 s: AsyncSession = Depends(get_session)) -> R[None]:
    d = await _doc(s, ctx, doc_id, "write")
    if d.status != DocStatus.OFFLINE or not d.current_version_id:
        raise BizError(ErrorCode.INVALID_STATE, "只有已下线的文档可以重新上线")
    vid = d.current_version_id
    d.current_version_id = None  # 视为首次发布：全部切片重新进入正式集合
    await s.commit()
    await step_publish(s, vid)
    return ok(None)


@router.delete("/documents/{doc_id}", summary="删除文档（软删除；立即停止检索）")
async def delete_doc(doc_id: str, ctx: AuthContext = Depends(require("pdk:doc:delete")),
                     s: AsyncSession = Depends(get_session)) -> R[None]:
    d = await _doc(s, ctx, doc_id, "write")
    if not ctx.in_data_scope("pdk:doc:delete", owner_id=d.owner_id, dept_id=d.dept_id, scenic_id=d.scenic_id):
        raise BizError(ErrorCode.NO_PERMISSION, "超出“删除文档”的数据范围")
    if d.status == DocStatus.PUBLISHED:
        await unpublish_document(s, d)
    d.status, d.deleted_at = DocStatus.DELETED, utcnow()
    await s.commit()
    audit.emit(ctx, "ADMIN_OP", f"删除文档：{d.title}", target_type="pdk:kb", target_ids=d.kb_id, scenic_id=d.scenic_id)
    return ok(None)


@router.post("/documents/{doc_id}/versions/{version_id}:rollback", summary="回滚到历史版本")
async def rollback(doc_id: str, version_id: str, ctx: AuthContext = Depends(require("pdk:doc:edit")),
                   s: AsyncSession = Depends(get_session)) -> R[None]:
    d = await _doc(s, ctx, doc_id, "write")
    v = await s.get(DocVersion, version_id)
    if v is None or v.document_id != d.id:
        raise not_found("版本")
    if v.status not in (VersionStatus.SUPERSEDED, VersionStatus.PUBLISHED):
        raise BizError(ErrorCode.INVALID_STATE, "只能回滚到曾经发布过的版本")
    await step_publish(s, v.id, ctx.user_id)
    audit.emit(ctx, "ADMIN_OP", f"回滚文档：{d.title} → v{v.version_no}", target_type="pdk:kb", target_ids=d.kb_id,
               scenic_id=d.scenic_id)
    return ok(None)


@router.post("/versions/{version_id}:reprocess", summary="重新处理（失败重试或调整配置后重跑）")
async def reprocess(version_id: str, start: str = Query("parse", pattern="^(parse|chunk|index)$"),
                    ctx: AuthContext = Depends(require("pdk:doc:edit", "pdk:task:manage")),
                    s: AsyncSession = Depends(get_session)) -> R[dict]:
    v = await s.get(DocVersion, version_id)
    if v is None:
        raise not_found("版本")
    ctx.require_kb(v.kb_id, "write")
    if v.status in (VersionStatus.PUBLISHED, VersionStatus.SUPERSEDED):
        raise BizError(ErrorCode.INVALID_STATE, "已发布的版本请上传新版本")
    v.status, v.error = VersionStatus.PENDING, None
    await s.commit()
    task_id = await runner.create_task("ingest", v.id, v.scenic_id, ctx.user_id)
    runner.dispatch(task_id, v.id, start)  # type: ignore[arg-type]
    return ok({"task_id": task_id})


@router.get("/versions/{version_id}/parse-result", summary="解析结果（结构化块，供预览与校对）")
async def parse_result(version_id: str, ctx: AuthContext = Depends(require("pdk:doc:view")),
                       s: AsyncSession = Depends(get_session)) -> R[list[dict]]:
    v = await s.get(DocVersion, version_id)
    if v is None:
        raise not_found("版本")
    await _doc(s, ctx, v.document_id)
    if not v.parsed_key:
        raise BizError(ErrorCode.INVALID_STATE, "该版本尚未解析完成")
    return ok(json.loads(await get_object_store().get(v.parsed_key)))


@router.get("/versions/{version_id}/download", summary="下载原文（单独授权、审计）")
async def download(version_id: str, ctx: AuthContext = Depends(require("pdk:doc:download")),
                   s: AsyncSession = Depends(get_session)):
    v = await s.get(DocVersion, version_id)
    if v is None:
        raise not_found("版本")
    d = await _doc(s, ctx, v.document_id)
    audit.emit(ctx, "DATA_DOWNLOAD", f"下载原文：{d.title} v{v.version_no}", target_type="pdk:kb", target_ids=d.kb_id,
               scenic_id=d.scenic_id, hitDocs=[d.title])
    store = get_object_store()
    url = await store.presign(v.object_key, 300, v.file_name)
    if url:
        return RedirectResponse(url, status_code=302)
    return Response(await store.get(v.object_key), media_type="application/octet-stream",
                    headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quote(v.file_name)}"})
