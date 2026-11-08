"""PD 插件公共代码（随插件一起拷贝到 hermes 的插件目录，只依赖 httpx 与 redis）。

- 会话上下文：接入网关写入 Redis pda:ctx:{session_id} = {user_id, scenic_id, scenic_scope, authz_ver,
  subject_token, allowed_tools[]}，插件按 hermes 会话 ID 反查当前用户（hermes 本身不接触用户凭证）；
- PDS：单点判断（pda:tool:*）与令牌交换（audience=pdk，5 分钟短时票据，按会话缓存）。
"""

from __future__ import annotations

import json
import os
import time
from typing import Any

import httpx

PDS_ISSUER = os.environ.get("PD_PDS_ISSUER", "http://127.0.0.1:9000").rstrip("/")
PDK_URL = os.environ.get("PD_PDK_URL", "http://127.0.0.1:8000").rstrip("/")
CLIENT_ID = os.environ.get("PD_PLUGIN_CLIENT_ID", "pda-plugin")
CLIENT_SECRET = os.environ.get("PD_PLUGIN_CLIENT_SECRET", "pda-plugin-dev-secret")
REDIS_URL = os.environ.get("PD_REDIS_URL")


class CtxStore:
    """会话上下文存储：生产用 Redis（网关与 hermes 共享），未配置时用进程内字典（仅测试）。"""

    def __init__(self, url: str | None = REDIS_URL):
        self._mem: dict[str, tuple[float, str]] = {}
        self._r = None
        if url:
            import redis

            self._r = redis.Redis.from_url(url, decode_responses=True)

    def get(self, session_id: str) -> dict[str, Any] | None:
        key = f"pda:ctx:{session_id}"
        if self._r is not None:
            raw = self._r.get(key)
        else:
            exp, raw = self._mem.get(key, (0, None))
            raw = raw if exp > time.time() else None
        return json.loads(raw) if raw else None

    def put(self, session_id: str, ctx: dict[str, Any], ttl: int = 1800) -> None:
        key, raw = f"pda:ctx:{session_id}", json.dumps(ctx, ensure_ascii=False)
        if self._r is not None:
            self._r.set(key, raw, ex=ttl)
        else:
            self._mem[key] = (time.time() + ttl, raw)


store = CtxStore()


class Pds:
    def __init__(self) -> None:
        self._svc: tuple[str, float] | None = None
        self._tickets: dict[str, tuple[str, float]] = {}

    def _service_token(self) -> str:
        if self._svc and self._svc[1] > time.time() + 30:
            return self._svc[0]
        r = httpx.post(f"{PDS_ISSUER}/oauth2/token", auth=(CLIENT_ID, CLIENT_SECRET), timeout=5,
                       data={"grant_type": "client_credentials", "scope": "pds.authz pds.audit"})
        r.raise_for_status()
        b = r.json()
        self._svc = (b["access_token"], time.time() + int(b.get("expires_in", 300)))
        return self._svc[0]

    def check(self, user_id: str, permission: str) -> tuple[bool, str]:
        r = httpx.post(f"{PDS_ISSUER}/api/v1/authz/check", timeout=3,
                       headers={"Authorization": f"Bearer {self._service_token()}"},
                       json={"subject": user_id, "permission": permission})
        r.raise_for_status()
        data = r.json()["data"]
        return bool(data["allowed"]), data.get("reason") or ""

    def exchange(self, session_id: str, subject_token: str, audience: str = "pdk") -> str:
        """以用户令牌换取访问目标应用的短时票据（aud=目标应用，act.sub=本插件客户端）。"""
        cached = self._tickets.get(f"{session_id}:{audience}")
        if cached and cached[1] > time.time() + 30:
            return cached[0]
        r = httpx.post(f"{PDS_ISSUER}/oauth2/token", auth=(CLIENT_ID, CLIENT_SECRET), timeout=5, data={
            "grant_type": "urn:ietf:params:oauth:grant-type:token-exchange",
            "subject_token": subject_token, "subject_token_type": "urn:ietf:params:oauth:token-type:access_token",
            "audience": audience, "scope": f"{audience}.api"})
        r.raise_for_status()
        b = r.json()
        self._tickets[f"{session_id}:{audience}"] = (b["access_token"], time.time() + int(b.get("expires_in", 300)))
        return b["access_token"]


pds = Pds()


def current_session_id(kw: dict[str, Any]) -> str | None:
    """hermes 在钩子入参中提供 session_id；工具处理函数中通过会话环境取得（API Server 场景需 POC 验证 V1）。"""
    sid = kw.get("session_id")
    if sid:
        return sid
    try:
        from gateway.session_context import get_session_env  # type: ignore[import-not-found]  # hermes 提供

        return get_session_env("HERMES_SESSION_ID")
    except Exception:  # noqa: BLE001
        return os.environ.get("HERMES_SESSION_ID")


def current_ctx(kw: dict[str, Any]) -> dict[str, Any] | None:
    sid = current_session_id(kw)
    if not sid:
        return None
    ctx = store.get(sid)
    if ctx is not None:
        ctx["session_id"] = sid
    return ctx
