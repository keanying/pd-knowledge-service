"""管理后台登录（BFF）：/auth/login → PDS 统一登录 → /auth/callback → 设置 HttpOnly Cookie。"""

from __future__ import annotations

from urllib.parse import urlparse

from fastapi import APIRouter, Request
from fastapi.responses import RedirectResponse

from pdk.auth import sessions
from pdk.config import get_settings

router = APIRouter(prefix="/auth", tags=["登录"])


def _safe_return(to: str | None) -> str:
    # 只允许站内相对路径，防止开放重定向
    if not to or not to.startswith("/") or to.startswith("//") or urlparse(to).netloc:
        return "/"
    return to


@router.get("/login", summary="跳转 PDS 统一登录")
async def login(return_to: str | None = None) -> RedirectResponse:
    return RedirectResponse(await sessions.begin_login(_safe_return(return_to)), status_code=302)


@router.get("/callback", summary="PDS 登录回调")
async def callback(code: str, state: str) -> RedirectResponse:
    s = get_settings()
    sid, return_to = await sessions.finish_login(code, state)
    resp = RedirectResponse(s.web_url.rstrip("/") + return_to, status_code=302)
    resp.set_cookie(sessions.COOKIE, sid, httponly=True, samesite="lax", secure=s.public_url.startswith("https"),
                    max_age=s.session_ttl, path="/")
    return resp


@router.get("/logout", summary="退出登录（同时退出 PDS）")
async def logout(request: Request) -> RedirectResponse:
    sid = request.cookies.get(sessions.COOKIE)
    data = await sessions.drop_session(sid) if sid else None
    resp = RedirectResponse(sessions.logout_url((data or {}).get("id_token")), status_code=302)
    resp.delete_cookie(sessions.COOKIE, path="/")
    return resp
