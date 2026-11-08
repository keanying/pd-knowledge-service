"""PDS 访问令牌校验：JWKS 验签（按 kid 缓存、未知 kid 自动刷新），校验 iss / exp / aud。"""

from __future__ import annotations

import asyncio
import json
import time
from typing import Any

import httpx
import jwt

from pdk.config import Settings, get_settings
from pdk.core.errors import BizError, ErrorCode


class JwtVerifier:
    def __init__(self, settings: Settings | None = None, http: httpx.AsyncClient | None = None):
        self.s = settings or get_settings()
        self._http = http or httpx.AsyncClient(timeout=5.0)
        self._keys: dict[str, Any] = {}
        self._fetched = 0.0
        self._lock = asyncio.Lock()

    @property
    def audiences(self) -> list[str]:
        # 令牌交换得到的票据 aud=pdk；管理后台登录得到的令牌 aud=管理后台客户端 ID
        return [self.s.app_code, self.s.console_client_id]

    async def _refresh(self, force: bool = False) -> None:
        if not force and self._keys and time.time() - self._fetched < 3600:
            return
        async with self._lock:
            if not force and self._keys and time.time() - self._fetched < 3600:
                return
            if force and time.time() - self._fetched < 10:  # 防止未知 kid 刷爆 JWKS
                return
            try:
                r = await self._http.get(f"{self.s.pds_api}/oauth2/jwks")
                r.raise_for_status()
            except httpx.HTTPError as e:
                if self._keys:
                    return
                raise BizError(ErrorCode.PDS_UNAVAILABLE, "无法获取统一权限服务公钥") from e
            keys = {}
            for k in r.json().get("keys", []):
                keys[k.get("kid", "")] = jwt.PyJWK.from_json(json.dumps(k)).key
            self._keys, self._fetched = keys, time.time()

    async def verify(self, token: str) -> dict[str, Any]:
        try:
            header = jwt.get_unverified_header(token)
        except jwt.PyJWTError as e:
            raise BizError(ErrorCode.TOKEN_INVALID) from e
        kid = header.get("kid", "")
        await self._refresh()
        if kid not in self._keys:
            await self._refresh(force=True)
        key = self._keys.get(kid)
        if key is None:
            raise BizError(ErrorCode.TOKEN_INVALID, "访问令牌签名密钥未知")
        try:
            return jwt.decode(token, key=key, algorithms=["RS256", "ES256"], audience=self.audiences,
                              issuer=self.s.pds_issuer, options={"require": ["exp", "iss", "sub"]}, leeway=30)
        except jwt.ExpiredSignatureError as e:
            raise BizError(ErrorCode.UNAUTHENTICATED, "访问令牌已过期") from e
        except jwt.PyJWTError as e:
            raise BizError(ErrorCode.TOKEN_INVALID, f"访问令牌无效：{e}") from e


_verifier: JwtVerifier | None = None


def get_verifier() -> JwtVerifier:
    global _verifier
    if _verifier is None:
        _verifier = JwtVerifier()
    return _verifier


def set_verifier(v: JwtVerifier | None) -> None:
    global _verifier
    _verifier = v
