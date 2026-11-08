"""FastAPI 鉴权依赖。

身份来源（按顺序）：
1. 开发模式（PDK_AUTH_MODE=dev）：请求头 X-Dev-User / X-Dev-Scenic；
2. 接口密钥：X-PDK-Api-Key（服务身份）+ 可选 X-PDS-User-Ticket（代理用户票据）；
3. Bearer：PDS 访问令牌或令牌交换票据（aud=pdk）；
4. 管理后台会话 Cookie。
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Callable

from fastapi import Depends, Request

from pdk.auth.context import AuthContext
from pdk.auth.jwt_verifier import get_verifier
from pdk.auth.sessions import COOKIE, load_session
from pdk.auth.snapshot import AuthzSnapshot, SnapshotUser
from pdk.auth.snapshots import dev_snapshot, get_snapshot
from pdk.config import get_settings
from pdk.core.context import ScenicScope, reset_scenic_scope, set_scenic_scope
from pdk.core.errors import BizError, ErrorCode

SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}


async def _from_claims(claims: dict, via: str, token: str | None = None) -> AuthContext:
    uid = claims.get("uid") or claims["sub"]
    snap, degraded = await get_snapshot(uid, int(claims.get("authz_ver") or 0))
    act = claims.get("act") or {}
    return AuthContext(user_id=uid, name=claims.get("name") or snap.user.name, snapshot=snap, via=via,
                       claims=claims, degraded=degraded, actor=act.get("sub") if isinstance(act, dict) else None,
                       token=token)


async def resolve_context(request: Request) -> AuthContext:
    s = get_settings()
    h = request.headers
    if s.auth_mode == "dev":
        uid = h.get("x-dev-user", "dev_admin")
        scenic = {x for x in h.get("x-dev-scenic", "S001").split(",") if x}
        return AuthContext(user_id=uid, name=uid, snapshot=dev_snapshot(uid, scenic), via="dev")

    api_key = h.get("x-pdk-api-key")
    if api_key:
        from pdk.services.api_keys import verify_api_key

        key = await verify_api_key(api_key, request.client.host if request.client else None)
        ticket = h.get("x-pds-user-ticket")
        if ticket:
            ctx = await _from_claims(await get_verifier().verify(ticket), "api_key")
        else:
            # 无用户票据：服务身份，只能访问密钥绑定的知识库（按集团范围、公开+内部密级）
            ctx = AuthContext(
                user_id=f"apikey:{key.id}", name=key.name, via="api_key",
                snapshot=AuthzSnapshot(user=SnapshotUser(id=f"apikey:{key.id}", name=key.name),
                                       permissions={"pdk:search:use"}, scenicScope=set(key.scenic_scope or []),
                                       maxSecurityLevel=1, unrestricted_resources=True),
            )
        ctx.api_key_id, ctx.api_key_kbs = key.id, set(key.kb_scope or [])
        return ctx

    auth = h.get("authorization", "")
    if auth.lower().startswith("bearer "):
        tok = auth[7:].strip()
        return await _from_claims(await get_verifier().verify(tok), "bearer", tok)

    sid = request.cookies.get(COOKIE)
    if sid:
        sess = await load_session(sid)
        if sess:
            return await _from_claims(sess["claims"], "session", sess["access_token"])
    raise BizError(ErrorCode.UNAUTHENTICATED)


async def auth_context(request: Request) -> AsyncIterator[AuthContext]:
    """解析身份并为本次请求设置数据库景区范围。"""
    ctx = await resolve_context(request)
    if ctx.degraded and request.method not in SAFE_METHODS:
        ctx.require_writable()
    request.state.auth = ctx
    token = set_scenic_scope(ScenicScope(frozenset(ctx.scenic_ids)))
    try:
        yield ctx
    finally:
        reset_scenic_scope(token)


def require(*permissions: str) -> Callable:
    """接口级功能权限：拥有任意一个即可。"""

    async def dep(ctx: AuthContext = Depends(auth_context)) -> AuthContext:
        if not any(ctx.has(p) for p in permissions):
            raise BizError(ErrorCode.NO_PERMISSION, f"无此功能权限：{' 或 '.join(permissions)}")
        return ctx

    return dep
