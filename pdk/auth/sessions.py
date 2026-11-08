"""管理后台会话（BFF）：pdk-api 作为 PDS 的 OIDC 客户端完成授权码 + PKCE 登录，
令牌只保存在服务端（Redis/内存），浏览器只持有 HttpOnly Cookie。"""

from __future__ import annotations

import base64
import hashlib
import secrets
import time
from typing import Any
from urllib.parse import urlencode

import httpx

from pdk.config import get_settings
from pdk.core.cache import get_cache
from pdk.core.errors import BizError, ErrorCode

COOKIE = "pdk_sid"
_STATE = "pdk:oidc:state:"
_SESSION = "pdk:session:"


def _b64(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()


def redirect_uri() -> str:
    return get_settings().public_url.rstrip("/") + "/auth/callback"


async def begin_login(return_to: str | None) -> str:
    s = get_settings()
    state, verifier = _b64(secrets.token_bytes(24)), _b64(secrets.token_bytes(48))
    challenge = _b64(hashlib.sha256(verifier.encode()).digest())
    await get_cache().set(_STATE + state, {"verifier": verifier, "return_to": return_to or "/"}, 600)
    q = {
        "response_type": "code", "client_id": s.console_client_id, "redirect_uri": redirect_uri(),
        "scope": "openid profile", "state": state, "code_challenge": challenge, "code_challenge_method": "S256",
    }
    return f"{s.pds_issuer.rstrip('/')}/oauth2/authorize?{urlencode(q)}"


async def finish_login(code: str, state: str) -> tuple[str, str]:
    """用授权码换令牌，建立会话。返回 (会话 ID, 登录后跳转地址)。"""
    s = get_settings()
    cache = get_cache()
    st = await cache.get(_STATE + state)
    if not st:
        raise BizError(ErrorCode.UNAUTHENTICATED, "登录状态已失效，请重新登录")
    await cache.delete(_STATE + state)
    async with httpx.AsyncClient(timeout=10) as http:
        r = await http.post(
            f"{s.pds_api}/oauth2/token",
            data={"grant_type": "authorization_code", "code": code, "redirect_uri": redirect_uri(),
                  "code_verifier": st["verifier"]},
            auth=(s.console_client_id, s.console_client_secret),
        )
    if r.status_code != 200:
        raise BizError(ErrorCode.UNAUTHENTICATED, f"登录失败（PDS 返回 {r.status_code}）")
    tokens = r.json()
    from pdk.auth.jwt_verifier import get_verifier

    claims = await get_verifier().verify(tokens["access_token"])
    sid = _b64(secrets.token_bytes(32))
    await save_session(sid, {
        "access_token": tokens["access_token"], "refresh_token": tokens.get("refresh_token"),
        "id_token": tokens.get("id_token"), "expires_at": time.time() + int(tokens.get("expires_in", 300)),
        "claims": claims,
    })
    return sid, st["return_to"]


async def save_session(sid: str, data: dict[str, Any]) -> None:
    await get_cache().set(_SESSION + sid, data, get_settings().session_ttl)


async def load_session(sid: str) -> dict[str, Any] | None:
    """读取会话；访问令牌快过期时用刷新令牌续期，续期失败视为未登录。"""
    data = await get_cache().get(_SESSION + sid)
    if not data:
        return None
    if data["expires_at"] - time.time() > 30:
        return data
    if not data.get("refresh_token"):
        await drop_session(sid)
        return None
    s = get_settings()
    try:
        async with httpx.AsyncClient(timeout=10) as http:
            r = await http.post(f"{s.pds_api}/oauth2/token",
                                data={"grant_type": "refresh_token", "refresh_token": data["refresh_token"]},
                                auth=(s.console_client_id, s.console_client_secret))
    except httpx.HTTPError:
        return data if data["expires_at"] > time.time() else None
    if r.status_code != 200:
        await drop_session(sid)
        return None
    t = r.json()
    data.update(access_token=t["access_token"], refresh_token=t.get("refresh_token", data["refresh_token"]),
                expires_at=time.time() + int(t.get("expires_in", 300)))
    await save_session(sid, data)
    return data


async def drop_session(sid: str) -> dict[str, Any] | None:
    data = await get_cache().get(_SESSION + sid)
    await get_cache().delete(_SESSION + sid)
    return data


def logout_url(id_token: str | None) -> str:
    s = get_settings()
    q = {"post_logout_redirect_uri": s.web_url.rstrip("/") + "/"}
    if id_token:
        q["id_token_hint"] = id_token
    return f"{s.pds_issuer.rstrip('/')}/connect/logout?{urlencode(q)}"
