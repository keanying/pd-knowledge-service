"""嵌入模型（VEC-01）。

- hash：本地确定性向量（字 + 二字哈希到固定维度后归一化）。只用于开发与测试，**没有语义能力**；
- openai：OpenAI 兼容 /v1/embeddings（Xinference / TEI / vLLM 部署的 bge-m3 等）。
"""

from __future__ import annotations

import hashlib
import math
from typing import Protocol

import httpx

from pdk.config import get_settings
from pdk.storage.vectors import tokenize


class Embedder(Protocol):
    model: str
    dim: int

    async def embed(self, texts: list[str]) -> list[list[float]]: ...


class HashEmbedder:
    def __init__(self, dim: int = 256, model: str = "hash"):
        self.dim, self.model = dim, model

    async def embed(self, texts: list[str]) -> list[list[float]]:
        return [self._one(t) for t in texts]

    def _one(self, text: str) -> list[float]:
        v = [0.0] * self.dim
        for tok in tokenize(text):
            h = int.from_bytes(hashlib.blake2b(tok.encode(), digest_size=8).digest(), "big")
            v[h % self.dim] += 1.0 if (h >> 63) & 1 else -1.0
        n = math.sqrt(sum(x * x for x in v)) or 1.0
        return [x / n for x in v]


class OpenAIEmbedder:
    def __init__(self, url: str, model: str, dim: int, api_key: str | None = None, batch: int = 32):
        self.url, self.model, self.dim, self.batch = url.rstrip("/"), model, dim, batch
        self.headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}

    async def embed(self, texts: list[str]) -> list[list[float]]:
        out: list[list[float]] = []
        async with httpx.AsyncClient(timeout=60) as http:
            for i in range(0, len(texts), self.batch):
                r = await http.post(f"{self.url}/embeddings", headers=self.headers,
                                    json={"model": self.model, "input": texts[i:i + self.batch]})
                r.raise_for_status()
                data = sorted(r.json()["data"], key=lambda d: d["index"])
                out.extend(d["embedding"] for d in data)
        return out


_embedder: Embedder | None = None


def get_embedder() -> Embedder:
    global _embedder
    if _embedder is None:
        s = get_settings()
        if s.embed_provider == "openai":
            _embedder = OpenAIEmbedder(s.embed_url, s.embed_model, s.embed_dim, s.embed_api_key)
        else:
            _embedder = HashEmbedder(dim=s.embed_dim, model=f"hash{s.embed_dim}")
    return _embedder


def set_embedder(e: Embedder | None) -> None:
    global _embedder
    _embedder = e
