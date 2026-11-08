"""pda-gateway：PDA 接入网关（uvicorn pda.gateway.app:app --port 8100）。

职责（技术方案 §8.2）：PDS 统一登录 → 校验 pda:chat:use 与模型权限 → 写会话上下文（供插件反查用户）→
转发 hermes API Server（流式）→ 出站二次脱敏 → 会话列表 → 审计。hermes 只拿到会话 ID，不接触用户凭证。
"""

from __future__ import annotations

import base64
import hashlib
import json
import secrets
import time
import uuid
from collections.abc import AsyncIterator
from typing import Any
from urllib.parse import urlencode

import httpx
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, RedirectResponse, StreamingResponse
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from pda.hermes_plugins.pd_common import CtxStore
from pda.hermes_plugins.pds_guard import mask_text


class GatewaySettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="PDA_", env_file=".env", extra="ignore")

    public_url: str = "http://127.0.0.1:8100"
    pds_issuer: str = "http://127.0.0.1:9000"
    client_id: str = "pda-gateway"
    client_secret: str = "pda-gateway-dev-secret"
    hermes_url: str = "http://127.0.0.1:8642"
    hermes_api_key: str = "change-me"
    default_model: str = "default"
    redis_url: str | None = None
    session_idle_seconds: int = 1800


cfg = GatewaySettings()
store = CtxStore(cfg.redis_url)
app = FastAPI(title="PDA 接入网关", version="0.1.0")
_logins: dict[str, dict[str, Any]] = {}  # 登录中的 state（生产放 Redis）
_sessions: dict[str, dict[str, Any]] = {}  # 浏览器会话（生产放 Redis）
_conversations: dict[str, list[dict[str, Any]]] = {}  # 最近对话（生产落库）
COOKIE = "pda_sid"


def _b64(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()


def _err(status: int, code: int, message: str) -> JSONResponse:
    return JSONResponse(status_code=status, content={"code": code, "message": message, "data": None})


async def _service_token(http: httpx.AsyncClient) -> str:
    r = await http.post(f"{cfg.pds_issuer}/oauth2/token", auth=(cfg.client_id, cfg.client_secret),
                        data={"grant_type": "client_credentials", "scope": "pds.authz.all pds.audit"})
    r.raise_for_status()
    return r.json()["access_token"]


async def _snapshot(user_id: str, app_code: str = "pda") -> dict[str, Any]:
    async with httpx.AsyncClient(timeout=5) as http:
        tok = await _service_token(http)
        r = await http.get(f"{cfg.pds_issuer}/api/v1/authz/snapshot", params={"app": app_code, "subject": user_id},
                           headers={"Authorization": f"Bearer {tok}"})
        r.raise_for_status()
        return r.json()["data"]


@app.get("/healthz")
async def healthz() -> dict:
    return {"status": "ok"}


@app.get("/auth/login")
async def login() -> RedirectResponse:
    state, verifier = _b64(secrets.token_bytes(24)), _b64(secrets.token_bytes(48))
    _logins[state] = {"verifier": verifier, "ts": time.time()}
    q = {"response_type": "code", "client_id": cfg.client_id, "redirect_uri": f"{cfg.public_url}/auth/callback",
         "scope": "openid profile", "state": state, "code_challenge_method": "S256",
         "code_challenge": _b64(hashlib.sha256(verifier.encode()).digest())}
    return RedirectResponse(f"{cfg.pds_issuer}/oauth2/authorize?{urlencode(q)}")


@app.get("/auth/callback")
async def callback(code: str, state: str):
    st = _logins.pop(state, None)
    if not st:
        return _err(401, 20001, "登录状态已失效，请重新登录")
    async with httpx.AsyncClient(timeout=10) as http:
        r = await http.post(f"{cfg.pds_issuer}/oauth2/token", auth=(cfg.client_id, cfg.client_secret), data={
            "grant_type": "authorization_code", "code": code, "redirect_uri": f"{cfg.public_url}/auth/callback",
            "code_verifier": st["verifier"]})
    if r.status_code != 200:
        return _err(401, 20001, "登录失败")
    t = r.json()
    claims = json.loads(base64.urlsafe_b64decode(t["access_token"].split(".")[1] + "=="))  # 来自 PDS 令牌端点，可信
    sid = _b64(secrets.token_bytes(32))
    _sessions[sid] = {"user_id": claims.get("uid") or claims["sub"], "name": claims.get("name"),
                      "access_token": t["access_token"], "claims": claims, "ts": time.time()}
    resp = RedirectResponse("/")
    resp.set_cookie(COOKIE, sid, httponly=True, samesite="lax")
    return resp


def _session(request: Request) -> dict[str, Any] | None:
    return _sessions.get(request.cookies.get(COOKIE, ""))


class ChatReq(BaseModel):
    message: str = Field(min_length=1, max_length=4000)
    conversation_id: str | None = None
    model: str | None = None


@app.get("/pda/me")
async def me(request: Request):
    sess = _session(request)
    if not sess:
        return _err(401, 20001, "未登录")
    snap = await _snapshot(sess["user_id"])
    return {"code": 0, "message": "成功", "data": {
        "user": {"id": sess["user_id"], "name": sess["name"]}, "can_chat": "pda:chat:use" in snap["permissions"],
        "models": sorted(p.removeprefix("pda:model:") for p in snap["permissions"] if p.startswith("pda:model:"))}}


@app.post("/pda/chat")
async def chat(req: ChatReq, request: Request):
    sess = _session(request)
    if not sess:
        return _err(401, 20001, "未登录")
    snap = await _snapshot(sess["user_id"])
    perms = set(snap["permissions"])
    if "pda:chat:use" not in perms:
        return _err(403, 21001, "暂无使用智能问答的权限，可在 PDS 申请")
    model = req.model or cfg.default_model
    if req.model and f"pda:model:{req.model}" not in perms:
        return _err(403, 21001, f"无权使用模型 {req.model}")
    conv = req.conversation_id or uuid.uuid4().hex[:12]
    session_id = f"pda-{sess['user_id']}-{conv}"
    # 会话上下文：插件按 hermes 会话 ID 反查用户；allowed_tools 是快照中已授权的工具（插件可免一次 PDS 调用）
    store.put(session_id, {
        "user_id": sess["user_id"], "scenic_id": snap["user"].get("scenicId"), "scenic_scope": snap["scenicScope"],
        "authz_ver": snap["version"], "subject_token": sess["access_token"],
        "allowed_tools": sorted(p.removeprefix("pda:tool:") for p in perms if p.startswith("pda:tool:")),
    }, cfg.session_idle_seconds)
    history = _conversations.setdefault(conv, [])
    history.append({"role": "user", "content": req.message})
    return StreamingResponse(_relay(session_id, conv, sess, model, history), media_type="text/event-stream")


def _sse(event: str, data: Any) -> bytes:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n".encode()


async def _relay(session_id: str, conv: str, sess: dict, model: str, history: list[dict]) -> AsyncIterator[bytes]:
    headers = {"Authorization": f"Bearer {cfg.hermes_api_key}", "X-Hermes-Session-Id": session_id,
               "X-Hermes-Session-Key": f"pda:user:{sess['user_id']}", "Idempotency-Key": uuid.uuid4().hex}
    answer = []
    yield _sse("progress", {"conversation_id": conv, "message": "正在思考…"})
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(120, connect=5)) as http:
            async with http.stream("POST", f"{cfg.hermes_url}/v1/chat/completions", headers=headers,
                                   json={"model": model, "stream": True, "messages": history[-20:]}) as r:
                if r.status_code != 200:
                    yield _sse("error", {"message": f"智能体服务异常（HTTP {r.status_code}）"})
                    return
                async for line in r.aiter_lines():
                    if not line.startswith("data:"):
                        continue
                    payload = line[5:].strip()
                    if payload == "[DONE]":
                        break
                    delta = (json.loads(payload).get("choices") or [{}])[0].get("delta", {}).get("content")
                    if delta:
                        answer.append(delta)
                        yield _sse("delta", {"text": mask_text(delta)})
    except httpx.HTTPError as e:
        yield _sse("error", {"message": f"无法连接智能体服务：{e.__class__.__name__}"})
        return
    full = mask_text("".join(answer))  # 出站二次脱敏
    history.append({"role": "assistant", "content": full})
    yield _sse("done", {"conversation_id": conv, "text": full})


@app.get("/pda/conversations")
async def conversations(request: Request):
    sess = _session(request)
    if not sess:
        return _err(401, 20001, "未登录")
    return {"code": 0, "message": "成功", "data": [
        {"id": cid, "title": msgs[0]["content"][:30], "turns": len(msgs) // 2} for cid, msgs in _conversations.items()
        if msgs]}
