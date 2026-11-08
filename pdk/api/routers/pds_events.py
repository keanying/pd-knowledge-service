"""PDS 下发事件（Webhook）：验签后按事件失效权限快照缓存。

验签：hex(HMAC-SHA256(secret, timestamp + "." + nonce + "." + 原始请求体)) == X-PDS-Signature，
时间戳与当前相差不超过 5 分钟，随机串未使用过。
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import time

from fastapi import APIRouter, Request

from pdk.auth.snapshots import invalidate
from pdk.config import get_settings
from pdk.core.cache import get_cache
from pdk.core.errors import BizError, ErrorCode
from pdk.core.response import R, ok

router = APIRouter(prefix="/api/v1/pds", tags=["PDS 事件"])
log = logging.getLogger("pdk.pds.events")


def verify_signature(secret: str, timestamp: str, nonce: str, body: bytes, signature: str) -> bool:
    msg = f"{timestamp}.{nonce}.".encode() + body
    return hmac.compare_digest(hmac.new(secret.encode(), msg, hashlib.sha256).hexdigest(), signature or "")


@router.post("/events", summary="接收 PDS 下发事件（perm_tree.published / role.* / perm_node.recoded）")
async def events(request: Request) -> R[dict]:
    secret = get_settings().pds_webhook_secret
    if not secret:
        raise BizError(ErrorCode.INVALID_STATE, "未配置 PDK_PDS_WEBHOOK_SECRET，拒绝接收事件")
    h = request.headers
    body = await request.body()
    ts, nonce = h.get("x-pds-timestamp", ""), h.get("x-pds-nonce", "")
    try:
        skew = abs(time.time() - int(ts) / (1000 if len(ts) > 11 else 1))
    except ValueError:
        skew = 1e9
    if skew > 300 or not nonce or not verify_signature(secret, ts, nonce, body, h.get("x-pds-signature", "")):
        raise BizError(ErrorCode.TOKEN_INVALID, "事件签名校验失败")
    cache = get_cache()
    if await cache.get(f"pdk:pds:nonce:{nonce}"):
        raise BizError(ErrorCode.TOKEN_INVALID, "重复的事件")
    await cache.set(f"pdk:pds:nonce:{nonce}", 1, 600)
    ev = json.loads(body)
    data = ev.get("data") or {}
    users = [*data.get("added", []), *data.get("removed", [])]
    # 角色成员变化只影响相关人员；其余事件（权限树发布、角色权限变化、编码修改）全部失效
    await invalidate(users if ev.get("type") == "role.members.changed" and users else None)
    log.info("收到 PDS 事件：%s %s", ev.get("type"), ev.get("id"))
    return ok({"received": ev.get("id")})
