"""检索服务（技术方案 §6.1）：

权限快照 → 过滤条件 → 问题向量化 → 混合召回（稠密 + BM25，RRF 融合）→ 重排与阈值 →
去重 → 回表取当前发布版本的切片 → 按策略脱敏 → 组装引用。
"""

from __future__ import annotations

import time
from typing import Any

from pydantic import BaseModel, Field
from sqlalchemy import select

from pdk.ai.embedding import get_embedder
from pdk.ai.rerank import get_reranker
from pdk.auth.context import AuthContext
from pdk.config import get_settings
from pdk.db.models import Chunk, DocStatus, Document, KnowledgeBase
from pdk.enrich.pii import mask
from pdk.ingest.vectors import ensure_collections, main_collection
from pdk.retrieval.filters import build_filter, to_milvus_expr
from pdk.storage.vectors import get_vector_store


class SearchRequest(BaseModel):
    query: str = Field(min_length=1, max_length=2000)
    kb_ids: list[str] | None = None
    tags: list[str] | None = None
    top_k: int | None = Field(default=None, ge=1, le=50)
    rerank: bool = True
    threshold: float | None = None
    debug: bool = False


class Source(BaseModel):
    kb_id: str
    kb_name: str | None
    doc_id: str
    doc_title: str
    version_no: int | None
    page_no: int | None
    bbox: list[list[float]] | None
    title_path: str | None
    url: str


class Citation(BaseModel):
    chunk_id: str
    text: str
    score: float
    chunk_type: str
    source: Source
    masked: bool = False


class SearchResult(BaseModel):
    query: str
    items: list[Citation]
    latency_ms: int
    debug: dict[str, Any] | None = None


async def search(s, ctx: AuthContext, req: SearchRequest) -> SearchResult:
    cfg = get_settings()
    t0 = time.perf_counter()
    flt = build_filter(ctx, req.kb_ids, req.tags)
    t_filter = time.perf_counter()
    [qvec] = await get_embedder().embed([req.query])
    t_embed = time.perf_counter()
    await ensure_collections()
    hits = await get_vector_store().hybrid_search(main_collection(), qvec, req.query, flt,
                                                  cfg.search_dense_topn, cfg.search_bm25_topn)
    t_recall = time.perf_counter()

    # 回表：只取当前发布版本、启用的切片（数据库层再按景区隔离一次）
    keys = [h.chunk_key for h in hits]
    rows: dict[str, tuple[Chunk, Document]] = {}
    if keys:
        q = (select(Chunk, Document).join(Document, Document.id == Chunk.document_id)
             .where(Chunk.chunk_key.in_(keys), Chunk.version_id == Document.current_version_id,
                    Chunk.enabled.is_(True), Document.status == DocStatus.PUBLISHED))
        for c, d in (await s.execute(q)).all():
            rows[c.chunk_key] = (c, d)
    hits = [h for h in hits if h.chunk_key in rows]

    top_k = req.top_k or cfg.search_rerank_topk
    scores = None
    if req.rerank and hits:
        scores = await get_reranker().rerank(req.query, [rows[h.chunk_key][0].content for h in hits])
    t_rerank = time.perf_counter()
    if scores is not None:
        ranked = sorted(zip(hits, scores, strict=True), key=lambda x: -x[1])
        threshold = req.threshold if req.threshold is not None else cfg.search_threshold
        ranked = [(h, sc) for h, sc in ranked if sc >= threshold]
    else:
        ranked = [(h, h.score) for h in hits]
    ranked = ranked[:top_k]

    kb_names = {}
    kb_ids = {rows[h.chunk_key][0].kb_id for h, _ in ranked}
    if kb_ids:
        kb_names = dict((await s.execute(select(KnowledgeBase.id, KnowledgeBase.name).where(KnowledgeBase.id.in_(kb_ids)))).all())
    versions = {}
    from pdk.db.models import DocVersion

    vids = {rows[h.chunk_key][1].current_version_id for h, _ in ranked}
    if vids:
        versions = dict((await s.execute(select(DocVersion.id, DocVersion.version_no).where(DocVersion.id.in_(vids)))).all())

    reveal = not get_settings().mask_by_default
    items = []
    for h, sc in ranked:
        c, d = rows[h.chunk_key]
        text, masked = c.content, 0
        if c.pii_types and not reveal:
            text, masked = mask(text, c.pii_types)
        vno = versions.get(d.current_version_id)
        items.append(Citation(
            chunk_id=c.chunk_key, text=text, score=round(float(sc), 6), chunk_type=c.chunk_type, masked=masked > 0,
            source=Source(kb_id=c.kb_id, kb_name=kb_names.get(c.kb_id), doc_id=d.id, doc_title=d.title, version_no=vno,
                          page_no=c.page_no, bbox=c.bbox, title_path=c.title_path,
                          url=f"/viewer?doc={d.id}&v={vno}&page={c.page_no or 1}&chunk={c.chunk_key}"),
        ))
    t_end = time.perf_counter()
    debug = None
    if req.debug:
        debug = {
            "filter": to_milvus_expr(flt),
            "recall": [{"chunk_id": h.chunk_key, "rrf": round(h.score, 6), "dense_rank": h.dense_rank,
                        "bm25_rank": h.bm25_rank} for h in hits[:50]],
            "reranker": get_reranker().name,
            "timing_ms": {"filter": _ms(t0, t_filter), "embed": _ms(t_filter, t_embed), "recall": _ms(t_embed, t_recall),
                          "rerank": _ms(t_recall, t_rerank), "assemble": _ms(t_rerank, t_end)},
        }
    return SearchResult(query=req.query, items=items, latency_ms=_ms(t0, t_end), debug=debug)


def _ms(a: float, b: float) -> int:
    return int((b - a) * 1000)
