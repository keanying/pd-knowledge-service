"""切片 → 向量行；正式/预发布集合的写入与切换。"""

from __future__ import annotations

from datetime import datetime

from pdk.ai.embedding import get_embedder
from pdk.db.models import Chunk, Document
from pdk.storage.vectors import FAR_FUTURE, VectorRow, collection_name, get_vector_store


def main_collection() -> str:
    return collection_name("chunks", get_embedder().model)


def staging_collection() -> str:
    return collection_name("staging", get_embedder().model)


def _ts(d: datetime | None, default: int) -> int:
    return int(d.timestamp()) if d else default


async def embed_rows(chunks: list[Chunk], doc: Document) -> list[VectorRow]:
    if not chunks:
        return []
    vectors = await get_embedder().embed([c.embed_text for c in chunks])
    return [to_row(c, doc, v) for c, v in zip(chunks, vectors, strict=True)]


def to_row(c: Chunk, doc: Document, dense: list[float]) -> VectorRow:
    return VectorRow(
        pk=c.chunk_key, chunk_key=c.chunk_key, scenic_id=c.scenic_id, kb_id=c.kb_id, doc_id=c.document_id,
        security_level=max(c.security_level, doc.security_level), tags=list(dict.fromkeys((doc.tags or []) + (c.tags or []))),
        chunk_type=c.chunk_type, effective_from=_ts(doc.effective_from, 0), effective_to=_ts(doc.effective_to, FAR_FUTURE),
        text=c.embed_text, dense=dense,
    )


async def ensure_collections() -> None:
    store, dim = get_vector_store(), get_embedder().dim
    await store.ensure(main_collection(), dim)
    await store.ensure(staging_collection(), dim)
