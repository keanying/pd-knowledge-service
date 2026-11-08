"""开放接口密钥（SYS-03）：pdk_ 开头，只保存 SHA-256 哈希，明文只在创建时返回一次。"""

from __future__ import annotations

import hashlib
import hmac
import ipaddress
import secrets
from datetime import UTC, datetime

from sqlalchemy import select

from pdk.core.errors import BizError, ErrorCode
from pdk.core.ids import new_id
from pdk.db.models import ApiKey
from pdk.db.session import session_factory


def _hash(raw: str) -> str:
    return hashlib.sha256(raw.encode()).hexdigest()


def generate() -> tuple[str, str, str]:
    raw = "pdk_" + secrets.token_urlsafe(32)
    return raw, raw[:12], _hash(raw)


async def create_api_key(name: str, kb_scope: list[str], scenic_scope: list[str], ip_whitelist: list[str],
                         expires_at: datetime | None, user_id: str) -> tuple[ApiKey, str]:
    raw, prefix, h = generate()
    async with session_factory()() as s:
        k = ApiKey(id=new_id("ak"), name=name, key_prefix=prefix, key_hash=h, kb_scope=kb_scope,
                   scenic_scope=scenic_scope, ip_whitelist=ip_whitelist, expires_at=expires_at, created_by=user_id)
        s.add(k)
        await s.commit()
        return k, raw


async def verify_api_key(raw: str, client_ip: str | None) -> ApiKey:
    async with session_factory()() as s:
        cands = (await s.execute(select(ApiKey).where(ApiKey.key_prefix == raw[:12]))).scalars().all()
    key = next((k for k in cands if hmac.compare_digest(k.key_hash, _hash(raw))), None)
    if key is None or not key.enabled:
        raise BizError(ErrorCode.TOKEN_INVALID, "接口密钥无效")
    if key.expires_at and key.expires_at.replace(tzinfo=key.expires_at.tzinfo or UTC) < datetime.now(UTC):
        raise BizError(ErrorCode.TOKEN_INVALID, "接口密钥已过期")
    if key.ip_whitelist and client_ip:
        ip = ipaddress.ip_address(client_ip)
        if not any(ip in ipaddress.ip_network(n, strict=False) for n in key.ip_whitelist):
            raise BizError(ErrorCode.NO_PERMISSION, "调用方 IP 不在白名单内")
    return key
