"""键值缓存：配置了 Redis 用 Redis（多实例共享），否则用进程内存（仅开发/单实例）。值为 JSON。"""

from __future__ import annotations

import json
import time
from typing import Any, Protocol


class Cache(Protocol):
    async def get(self, key: str) -> Any | None: ...
    async def set(self, key: str, value: Any, ttl: int) -> None: ...
    async def delete(self, *keys: str) -> None: ...
    async def delete_prefix(self, prefix: str) -> None: ...


class MemoryCache:
    def __init__(self) -> None:
        self._data: dict[str, tuple[float, str]] = {}

    async def get(self, key: str) -> Any | None:
        item = self._data.get(key)
        if item is None:
            return None
        exp, raw = item
        if exp < time.time():
            self._data.pop(key, None)
            return None
        return json.loads(raw)

    async def set(self, key: str, value: Any, ttl: int) -> None:
        self._data[key] = (time.time() + ttl, json.dumps(value, ensure_ascii=False, default=str))

    async def delete(self, *keys: str) -> None:
        for k in keys:
            self._data.pop(k, None)

    async def delete_prefix(self, prefix: str) -> None:
        for k in [k for k in self._data if k.startswith(prefix)]:
            self._data.pop(k, None)


class RedisCache:
    def __init__(self, url: str) -> None:
        from redis.asyncio import Redis

        self._r = Redis.from_url(url, decode_responses=True)

    async def get(self, key: str) -> Any | None:
        raw = await self._r.get(key)
        return None if raw is None else json.loads(raw)

    async def set(self, key: str, value: Any, ttl: int) -> None:
        await self._r.set(key, json.dumps(value, ensure_ascii=False, default=str), ex=ttl)

    async def delete(self, *keys: str) -> None:
        if keys:
            await self._r.delete(*keys)

    async def delete_prefix(self, prefix: str) -> None:
        async for k in self._r.scan_iter(match=prefix + "*", count=500):
            await self._r.delete(k)


_cache: Cache | None = None


def get_cache() -> Cache:
    global _cache
    if _cache is None:
        from pdk.config import get_settings

        url = get_settings().redis_url
        _cache = RedisCache(url) if url else MemoryCache()
    return _cache


def set_cache(cache: Cache | None) -> None:
    global _cache
    _cache = cache
