"""权限快照获取与缓存。

- 缓存键 pdk:snap:{uid}，默认 5 分钟；令牌中的 authz_ver 大于缓存版本时立即刷新；
- 收到 PDS 下发事件时按人员或全部失效；
- PDS 不可用：未过期缓存照常使用；已过期但在宽限期内的缓存只允许只读请求（degraded=True）；
  缓存也没有则拒绝，不默认放行。
"""

from __future__ import annotations

import logging
import time

from pdk.auth.manifest import PERMISSION_CODES
from pdk.auth.pds_client import PdsUnavailable, get_pds
from pdk.auth.snapshot import AuthzSnapshot, SnapshotUser
from pdk.config import get_settings
from pdk.core.cache import get_cache

log = logging.getLogger("pdk.snapshot")

PREFIX = "pdk:snap:"
STALE_GRACE = 1800  # PDS 故障时过期快照可只读使用的时长（秒）


async def get_snapshot(user_id: str, min_version: int = 0) -> tuple[AuthzSnapshot, bool]:
    """返回 (快照, 是否降级)。"""
    s = get_settings()
    cache = get_cache()
    cached_raw = await cache.get(PREFIX + user_id)
    cached = AuthzSnapshot.model_validate(cached_raw) if cached_raw else None
    now = time.time()
    if cached and now - cached.fetched_at < s.snapshot_ttl and cached.version >= min_version:
        return cached, False
    try:
        data = await get_pds().snapshot(user_id)
    except PdsUnavailable:
        if cached and now - cached.fetched_at < s.snapshot_ttl + STALE_GRACE:
            log.warning("PDS 不可用，使用过期权限快照只读降级：user=%s", user_id)
            return cached, True
        raise
    snap = AuthzSnapshot.model_validate(data)
    snap.fetched_at = now
    await cache.set(PREFIX + user_id, snap.model_dump(mode="json"), s.snapshot_ttl + STALE_GRACE)
    return snap, False


async def invalidate(user_ids: list[str] | None = None) -> None:
    cache = get_cache()
    if user_ids:
        await cache.delete(*[PREFIX + u for u in user_ids])
    else:
        await cache.delete_prefix(PREFIX)


def dev_snapshot(user_id: str, scenic_ids: set[str], name: str | None = None) -> AuthzSnapshot:
    """开发模式快照：拥有 PDK 全部权限点、不限制知识库实例、最高密级。"""
    return AuthzSnapshot(
        version=0, app="pdk",
        user=SnapshotUser(id=user_id, name=name or user_id, scenicId=next(iter(sorted(scenic_ids)), None)),
        permissions=set(PERMISSION_CODES), scenicScope=set(scenic_ids), maxSecurityLevel=3,
        unrestricted_resources=True, roles=["dev"],
    )
