"""接入流水线的各个步骤（技术方案 §4.1）。每一步都只依赖 version_id、从数据库读取输入并把输出落库，
因此可重复执行（幂等），失败后可从任一步继续。"""

from __future__ import annotations

import json
import logging
import time
from collections import Counter

from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from pdk.chunking.base import ChunkStrategy, chunk_key, make_chunks
from pdk.core.errors import BizError, ErrorCode
from pdk.core.ids import new_id
from pdk.db.base import utcnow
from pdk.db.models import Chunk, DocStatus, Document, DocVersion, KnowledgeBase, VersionStatus
from pdk.enrich.clean import clean_blocks
from pdk.enrich.pii import detect
from pdk.ingest.vectors import embed_rows, ensure_collections, main_collection, staging_collection
from pdk.parsers.base import Block, file_type_of, get_parser
from pdk.storage.objects import get_object_store
from pdk.storage.vectors import get_vector_store

log = logging.getLogger("pdk.ingest")


async def load(s: AsyncSession, version_id: str) -> tuple[DocVersion, Document, KnowledgeBase]:
    v = await s.get(DocVersion, version_id)
    if v is None:
        raise BizError(ErrorCode.NOT_FOUND, f"文档版本不存在：{version_id}")
    d = await s.get(Document, v.document_id)
    kb = await s.get(KnowledgeBase, v.kb_id)
    assert d is not None and kb is not None
    return v, d, kb


def _stat(v: DocVersion, **kw) -> None:
    v.stats = {**(v.stats or {}), **kw}


async def step_parse(s: AsyncSession, version_id: str) -> None:
    """取原文 → 解析 → 清洗 → 保存解析产物（Markdown + 结构化块）。"""
    v, _, kb = await load(s, version_id)
    v.status = VersionStatus.PARSING
    await s.commit()
    t0 = time.perf_counter()
    store = get_object_store()
    data = await store.get(v.object_key)
    parsed = await get_parser(file_type_of(v.file_name)).parse(data, v.file_name, kb.parse_config or {})
    blocks = clean_blocks(parsed.blocks, (kb.parse_config or {}).get("clean"))
    prefix = v.object_key.rsplit("/", 1)[0]
    await store.put(f"{prefix}/parsed.md", parsed.markdown.encode(), "text/markdown")
    await store.put(f"{prefix}/content_list.json",
                    json.dumps([b.model_dump() for b in blocks], ensure_ascii=False).encode(), "application/json")
    v.parsed_key = f"{prefix}/content_list.json"
    _stat(v, parser=parsed.parser, blocks=len(blocks), parse_ms=int((time.perf_counter() - t0) * 1000))
    v.status = VersionStatus.PENDING_PROOFREAD if (kb.parse_config or {}).get("proofread") else VersionStatus.CHUNKING
    await s.commit()


async def step_chunk(s: AsyncSession, version_id: str) -> None:
    """切片 + 敏感信息识别，写入 doc_chunk（先删后写，可重复执行）。"""
    v, d, kb = await load(s, version_id)
    v.status = VersionStatus.CHUNKING
    raw = await get_object_store().get(v.parsed_key or "")
    blocks = [Block.model_validate(b) for b in json.loads(raw)]
    cfg = {"max_len": 500, "overlap": 50, **(kb.chunk_strategy or {})}
    if d.source_type == "faq":
        cfg["mode"] = "faq"
    drafts = make_chunks(blocks, ChunkStrategy.model_validate(cfg))
    if not drafts:
        raise BizError(ErrorCode.INVALID_STATE, "未切出任何切片（文档内容为空）")
    await s.execute(delete(Chunk).where(Chunk.version_id == v.id))
    seen: Counter[str] = Counter()
    pii_count = 0
    for dr in drafts:
        h = dr.content_hash
        key = chunk_key(d.id, h, seen[h])
        seen[h] += 1
        pii = detect(dr.text)
        pii_count += bool(pii)
        s.add(Chunk(id=new_id("ck"), chunk_key=key, version_id=v.id, document_id=d.id, kb_id=d.kb_id,
                    scenic_id=d.scenic_id, seq=dr.seq, chunk_type=dr.chunk_type, content=dr.text,
                    embed_text=dr.embed_text, content_hash=h, title_path=dr.title_path, page_no=dr.page_no,
                    bbox=dr.bbox or None, parent_key=dr.parent_key, tags=list(d.tags or []),
                    security_level=d.security_level, pii_types=pii))
    _stat(v, chunks=len(drafts), pii_chunks=pii_count)
    v.status = VersionStatus.EMBEDDING
    await s.commit()


async def _keys(s: AsyncSession, version_id: str | None) -> set[str]:
    if not version_id:
        return set()
    rows = await s.execute(select(Chunk.chunk_key).where(Chunk.version_id == version_id, Chunk.enabled.is_(True)))
    return set(rows.scalars())


async def step_index(s: AsyncSession, version_id: str) -> None:
    """增量比对：只为“当前发布版本中没有”的切片计算向量，写入预发布集合。"""
    v, d, _ = await load(s, version_id)
    await ensure_collections()
    target = await _keys(s, v.id)
    current = await _keys(s, d.current_version_id) if d.current_version_id != v.id else set()
    new_keys = target - current
    store = get_vector_store()
    staged = {r.pk for r in await store.get(staging_collection(), sorted(new_keys))}
    todo = sorted(new_keys - staged)
    t0 = time.perf_counter()
    if todo:
        chunks = (await s.execute(select(Chunk).where(Chunk.version_id == v.id, Chunk.chunk_key.in_(todo)))).scalars().all()
        await store.upsert(staging_collection(), await embed_rows(list(chunks), d))
    _stat(v, added=len(new_keys), reused=len(target & current), removed=len(current - target),
          embedded=len(todo), embed_ms=int((time.perf_counter() - t0) * 1000))
    v.status = VersionStatus.PENDING_REVIEW
    await s.commit()


async def step_publish(s: AsyncSession, version_id: str, reviewer_id: str | None = None) -> None:
    """发布：新增切片从预发布集合进入正式集合，删除失效切片，切换当前版本。"""
    v, d, _ = await load(s, version_id)
    await ensure_collections()
    target = await _keys(s, v.id)
    current = await _keys(s, d.current_version_id) if d.current_version_id != v.id else set()
    add, remove = sorted(target - current), sorted(current - target)
    store = get_vector_store()
    staged = await store.get(staging_collection(), add)
    missing = sorted(set(add) - {r.pk for r in staged})
    if missing:  # 预发布中没有（如回滚到历史版本）：重新计算向量
        chunks = (await s.execute(select(Chunk).where(Chunk.version_id == v.id, Chunk.chunk_key.in_(missing)))).scalars().all()
        staged += await embed_rows(list(chunks), d)
    await store.upsert(main_collection(), staged)
    await store.delete(main_collection(), remove)
    await store.delete(staging_collection(), add)
    if d.current_version_id and d.current_version_id != v.id:
        await s.execute(update(DocVersion).where(DocVersion.id == d.current_version_id)
                        .values(status=VersionStatus.SUPERSEDED))
    d.current_version_id = v.id
    d.status = DocStatus.PUBLISHED
    v.status = VersionStatus.PUBLISHED
    v.published_at = utcnow()
    if reviewer_id:
        v.reviewer_id = reviewer_id
    _stat(v, published_added=len(add), published_removed=len(remove))
    await s.commit()
    log.info("文档已发布：doc=%s version=%s +%d -%d", d.id, v.id, len(add), len(remove))


async def unpublish_document(s: AsyncSession, doc: Document) -> None:
    """下线：立即从正式集合移除该文档当前版本的全部切片。"""
    keys = sorted(await _keys(s, doc.current_version_id))
    await ensure_collections()
    await get_vector_store().delete(main_collection(), keys)
    doc.status = DocStatus.OFFLINE
    await s.commit()
