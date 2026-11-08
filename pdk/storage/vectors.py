"""向量库抽象。

- 每个嵌入模型一个正式集合 pdk_chunks_{模型} 与一个预发布集合 pdk_staging_{模型}；
- 主键 pk = chunk_key（与版本无关），内容未变的切片在新版本中复用；
- **权限过滤在召回之前**：SearchFilter 由权限快照生成，Milvus 中作为 filter 表达式下推，内存实现先过滤再打分。

memory：进程内实现（开发/测试，含简易 BM25）；milvus：Milvus 2.5+（分区键、BM25 函数、混合检索 + RRF）。
"""

from __future__ import annotations

import asyncio
import math
import re
from collections import Counter
from dataclasses import dataclass, field
from typing import Protocol

FAR_FUTURE = 32503680000  # 3000-01-01


def collection_name(kind: str, model: str) -> str:
    return f"pdk_{kind}_{re.sub(r'[^0-9a-zA-Z_]', '_', model).lower()}"


@dataclass
class VectorRow:
    pk: str
    chunk_key: str
    scenic_id: str
    kb_id: str
    doc_id: str
    security_level: int
    tags: list[str]
    chunk_type: str
    effective_from: int
    effective_to: int
    text: str
    dense: list[float]


@dataclass
class SearchFilter:
    scenic_ids: list[str]
    kb_ids: list[str] | None  # None 表示不限（仅开发模式）
    max_security_level: int
    now: int
    tags: list[str] | None = None
    doc_ids: list[str] | None = None

    def match(self, r: VectorRow) -> bool:
        if r.scenic_id not in self.scenic_ids:
            return False
        if self.kb_ids is not None and r.kb_id not in self.kb_ids:
            return False
        if r.security_level > self.max_security_level:
            return False
        if not (r.effective_from <= self.now <= r.effective_to):
            return False
        if self.tags and not set(self.tags) & set(r.tags):
            return False
        return not (self.doc_ids is not None and r.doc_id not in self.doc_ids)


@dataclass
class Hit:
    pk: str
    chunk_key: str
    doc_id: str
    kb_id: str
    score: float  # 融合分（RRF）
    dense_rank: int | None = None
    bm25_rank: int | None = None
    dense_score: float | None = None
    bm25_score: float | None = None
    extra: dict = field(default_factory=dict)


class VectorStore(Protocol):
    async def ensure(self, collection: str, dim: int) -> None: ...
    async def upsert(self, collection: str, rows: list[VectorRow]) -> None: ...
    async def delete(self, collection: str, pks: list[str]) -> None: ...
    async def get(self, collection: str, pks: list[str]) -> list[VectorRow]: ...
    async def hybrid_search(self, collection: str, dense: list[float], text: str, flt: SearchFilter,
                            dense_topn: int, bm25_topn: int, rrf_k: int = 60) -> list[Hit]: ...


def rrf(rank_lists: list[list[str]], k: int = 60) -> dict[str, float]:
    scores: dict[str, float] = {}
    for ranks in rank_lists:
        for i, pk in enumerate(ranks):
            scores[pk] = scores.get(pk, 0.0) + 1.0 / (k + i + 1)
    return scores


# ---------------------------------------------------------------- 内存实现
_WORD = re.compile(r"[a-zA-Z0-9]+|[一-鿿]")


def tokenize(text: str) -> list[str]:
    """中文按字 + 相邻二字，英文数字按词（小写）。仅供内存实现的 BM25 使用。"""
    toks = _WORD.findall(text.lower())
    out = list(toks)
    for a, b in zip(toks, toks[1:], strict=False):
        if len(a) == 1 and len(b) == 1 and "一" <= a <= "鿿" and "一" <= b <= "鿿":
            out.append(a + b)
    return out


class MemoryVectorStore:
    def __init__(self) -> None:
        self._cols: dict[str, dict[str, VectorRow]] = {}
        self._lock = asyncio.Lock()

    async def ensure(self, collection: str, dim: int) -> None:
        self._cols.setdefault(collection, {})

    async def upsert(self, collection: str, rows: list[VectorRow]) -> None:
        async with self._lock:
            col = self._cols.setdefault(collection, {})
            for r in rows:
                col[r.pk] = r

    async def delete(self, collection: str, pks: list[str]) -> None:
        async with self._lock:
            col = self._cols.get(collection, {})
            for pk in pks:
                col.pop(pk, None)

    async def get(self, collection: str, pks: list[str]) -> list[VectorRow]:
        col = self._cols.get(collection, {})
        return [col[p] for p in pks if p in col]

    def count(self, collection: str) -> int:
        return len(self._cols.get(collection, {}))

    async def hybrid_search(self, collection: str, dense: list[float], text: str, flt: SearchFilter,
                            dense_topn: int, bm25_topn: int, rrf_k: int = 60) -> list[Hit]:
        rows = [r for r in self._cols.get(collection, {}).values() if flt.match(r)]  # 先过滤
        if not rows:
            return []
        dense_scores = {r.pk: sum(a * b for a, b in zip(dense, r.dense, strict=False)) for r in rows}
        dense_rank = sorted(dense_scores, key=lambda pk: -dense_scores[pk])[:dense_topn]
        bm25_scores = _bm25(rows, text)
        bm25_rank = [pk for pk in sorted(bm25_scores, key=lambda pk: -bm25_scores[pk]) if bm25_scores[pk] > 0][:bm25_topn]
        fused = rrf([dense_rank, bm25_rank], rrf_k)
        by_pk = {r.pk: r for r in rows}
        hits = []
        for pk, score in sorted(fused.items(), key=lambda kv: -kv[1]):
            r = by_pk[pk]
            hits.append(Hit(pk=pk, chunk_key=r.chunk_key, doc_id=r.doc_id, kb_id=r.kb_id, score=score,
                            dense_rank=dense_rank.index(pk) + 1 if pk in dense_rank else None,
                            bm25_rank=bm25_rank.index(pk) + 1 if pk in bm25_rank else None,
                            dense_score=dense_scores.get(pk), bm25_score=bm25_scores.get(pk)))
        return hits


def _bm25(rows: list[VectorRow], query: str, k1: float = 1.5, b: float = 0.75) -> dict[str, float]:
    q = set(tokenize(query))
    docs = {r.pk: Counter(tokenize(r.text)) for r in rows}
    n = len(docs)
    avgdl = sum(sum(c.values()) for c in docs.values()) / max(n, 1)
    df = Counter(t for c in docs.values() for t in set(c) if t in q)
    out = {}
    for pk, c in docs.items():
        dl = sum(c.values())
        s = 0.0
        for t in q:
            f = c.get(t, 0)
            if f:
                idf = math.log(1 + (n - df[t] + 0.5) / (df[t] + 0.5))
                s += idf * f * (k1 + 1) / (f + k1 * (1 - b + b * dl / max(avgdl, 1)))
        out[pk] = s
    return out


# ---------------------------------------------------------------- Milvus 实现
_FIELDS = ["pk", "chunk_key", "scenic_id", "kb_id", "doc_id", "security_level", "tags", "chunk_type",
           "effective_from", "effective_to", "text"]
_CHUNK_TYPES = {"text": 1, "table": 2, "faq": 3, "image": 4, "aux": 9}
_CHUNK_TYPES_REV = {v: k for k, v in _CHUNK_TYPES.items()}


class MilvusVectorStore:
    """Milvus 2.5+。集合结构见技术方案 §5.1：scenic_id 为分区键，text 开启中文分词并由 BM25 函数生成稀疏向量。"""

    def __init__(self, uri: str, token: str | None = None):
        from pymilvus import MilvusClient

        self.client = MilvusClient(uri=uri, token=token or "")
        self._ready: set[str] = set()

    async def ensure(self, collection: str, dim: int) -> None:
        if collection in self._ready:
            return
        await asyncio.to_thread(self._ensure_sync, collection, dim)
        self._ready.add(collection)

    def _ensure_sync(self, collection: str, dim: int) -> None:
        from pymilvus import DataType, Function, FunctionType, MilvusClient

        if self.client.has_collection(collection):
            self.client.load_collection(collection)
            return
        schema = MilvusClient.create_schema(auto_id=False, enable_dynamic_field=False)
        schema.add_field("pk", DataType.VARCHAR, max_length=64, is_primary=True)
        schema.add_field("chunk_key", DataType.VARCHAR, max_length=64)
        schema.add_field("scenic_id", DataType.VARCHAR, max_length=32, is_partition_key=True)
        schema.add_field("kb_id", DataType.VARCHAR, max_length=32)
        schema.add_field("doc_id", DataType.VARCHAR, max_length=32)
        schema.add_field("security_level", DataType.INT8)
        schema.add_field("tags", DataType.ARRAY, element_type=DataType.VARCHAR, max_capacity=32, max_length=32)
        schema.add_field("chunk_type", DataType.INT8)
        schema.add_field("effective_from", DataType.INT64)
        schema.add_field("effective_to", DataType.INT64)
        schema.add_field("text", DataType.VARCHAR, max_length=8192, enable_analyzer=True,
                         analyzer_params={"type": "chinese"})
        schema.add_field("dense", DataType.FLOAT_VECTOR, dim=dim)
        schema.add_field("sparse_bm25", DataType.SPARSE_FLOAT_VECTOR)
        schema.add_function(Function(name="bm25", function_type=FunctionType.BM25,
                                     input_field_names=["text"], output_field_names=["sparse_bm25"]))
        idx = self.client.prepare_index_params()
        idx.add_index("dense", index_type="HNSW", metric_type="COSINE", params={"M": 16, "efConstruction": 200})
        idx.add_index("sparse_bm25", index_type="SPARSE_INVERTED_INDEX", metric_type="BM25")
        for f in ("kb_id", "doc_id"):
            idx.add_index(f, index_type="INVERTED")
        for f in ("security_level", "effective_from", "effective_to"):
            idx.add_index(f, index_type="STL_SORT")
        self.client.create_collection(collection, schema=schema, index_params=idx)

    @staticmethod
    def _row(r: VectorRow) -> dict:
        return {"pk": r.pk, "chunk_key": r.chunk_key, "scenic_id": r.scenic_id, "kb_id": r.kb_id, "doc_id": r.doc_id,
                "security_level": r.security_level, "tags": r.tags[:32], "chunk_type": _CHUNK_TYPES.get(r.chunk_type, 1),
                "effective_from": r.effective_from, "effective_to": r.effective_to, "text": r.text[:8000],
                "dense": r.dense}

    async def upsert(self, collection: str, rows: list[VectorRow]) -> None:
        for i in range(0, len(rows), 500):
            batch = [self._row(r) for r in rows[i:i + 500]]
            await asyncio.to_thread(self.client.upsert, collection, batch)

    async def delete(self, collection: str, pks: list[str]) -> None:
        if pks:
            await asyncio.to_thread(self.client.delete, collection, ids=pks)

    async def get(self, collection: str, pks: list[str]) -> list[VectorRow]:
        if not pks:
            return []
        res = await asyncio.to_thread(self.client.get, collection, ids=pks, output_fields=_FIELDS + ["dense"])
        rows = []
        for x in res:
            d = {k: x[k] for k in _FIELDS}
            d["tags"] = list(d["tags"] or [])
            d["chunk_type"] = _CHUNK_TYPES_REV.get(int(d["chunk_type"]), "text")
            rows.append(VectorRow(**d, dense=[float(v) for v in x["dense"]]))
        return rows

    async def hybrid_search(self, collection: str, dense: list[float], text: str, flt: SearchFilter,
                            dense_topn: int, bm25_topn: int, rrf_k: int = 60) -> list[Hit]:
        from pymilvus import AnnSearchRequest, RRFRanker

        from pdk.retrieval.filters import to_milvus_expr

        expr = to_milvus_expr(flt)
        reqs = [
            AnnSearchRequest(data=[dense], anns_field="dense", param={"metric_type": "COSINE", "params": {"ef": 128}},
                             limit=dense_topn, expr=expr),
            AnnSearchRequest(data=[text], anns_field="sparse_bm25", param={"metric_type": "BM25"},
                             limit=bm25_topn, expr=expr),
        ]
        res = await asyncio.to_thread(self.client.hybrid_search, collection, reqs, RRFRanker(rrf_k),
                                      limit=max(dense_topn, bm25_topn),
                                      output_fields=["chunk_key", "doc_id", "kb_id"])
        hits = []
        for h in res[0] if res else []:
            e = h.get("entity", {})
            hits.append(Hit(pk=h["id"], chunk_key=e.get("chunk_key", h["id"]), doc_id=e.get("doc_id", ""),
                            kb_id=e.get("kb_id", ""), score=float(h["distance"])))
        return hits


_store: VectorStore | None = None


def get_vector_store() -> VectorStore:
    global _store
    if _store is None:
        from pdk.config import get_settings

        s = get_settings()
        _store = MilvusVectorStore(s.milvus_uri, s.milvus_token) if s.vector_store == "milvus" else MemoryVectorStore()
    return _store


def set_vector_store(store: VectorStore | None) -> None:
    global _store
    _store = store
