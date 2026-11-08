"""重排模型（RET-02）。none：保持融合顺序；http：Xinference / TEI 风格的 /rerank 接口（bge-reranker-v2-m3）。"""

from __future__ import annotations

from typing import Protocol

import httpx

from pdk.config import get_settings


class Reranker(Protocol):
    name: str

    async def rerank(self, query: str, docs: list[str]) -> list[float] | None:
        """返回与 docs 一一对应的相关度（0–1）；None 表示不重排。"""
        ...


class NoopReranker:
    name = "none"

    async def rerank(self, query: str, docs: list[str]) -> list[float] | None:
        return None


class HttpReranker:
    def __init__(self, url: str, model: str):
        self.url, self.model, self.name = url.rstrip("/"), model, model

    async def rerank(self, query: str, docs: list[str]) -> list[float] | None:
        if not docs:
            return []
        async with httpx.AsyncClient(timeout=10) as http:
            r = await http.post(f"{self.url}/rerank", json={"model": self.model, "query": query, "documents": docs})
            r.raise_for_status()
        body = r.json()
        items = body.get("results") or body.get("data") or body
        scores = [0.0] * len(docs)
        for it in items:
            scores[it["index"]] = float(it.get("relevance_score", it.get("score", 0.0)))
        return scores


def get_reranker() -> Reranker:
    s = get_settings()
    return HttpReranker(s.rerank_url, s.rerank_model) if s.rerank_provider == "http" else NoopReranker()
