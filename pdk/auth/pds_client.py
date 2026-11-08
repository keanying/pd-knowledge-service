"""PDS 开放接口客户端（服务身份：client_credentials）。

接口约定见 PDS《应用接入指南》：权限快照、单点判断、权限清单、资源实例、资源授权、审计上报。
"""

from __future__ import annotations

import asyncio
import base64
import logging
import time
from typing import Any

import httpx

from pdk.config import Settings, get_settings
from pdk.core.errors import BizError, ErrorCode

log = logging.getLogger("pdk.pds")


class PdsUnavailable(BizError):
    def __init__(self, message: str = "统一权限服务暂不可用"):
        super().__init__(ErrorCode.PDS_UNAVAILABLE, message)


class PdsClient:
    def __init__(self, settings: Settings | None = None, http: httpx.AsyncClient | None = None):
        self.s = settings or get_settings()
        self.base = self.s.pds_api
        self._http = http or httpx.AsyncClient(timeout=httpx.Timeout(5.0, connect=3.0))
        self._token: str | None = None
        self._token_exp: float = 0
        self._lock = asyncio.Lock()

    async def aclose(self) -> None:
        await self._http.aclose()

    # ---------- 服务令牌 ----------
    async def service_token(self) -> str:
        if self._token and time.time() < self._token_exp - 30:
            return self._token
        async with self._lock:
            if self._token and time.time() < self._token_exp - 30:
                return self._token
            basic = base64.b64encode(f"{self.s.pds_client_id}:{self.s.pds_client_secret}".encode()).decode()
            try:
                r = await self._http.post(
                    f"{self.base}/oauth2/token",
                    data={"grant_type": "client_credentials", "scope": "pds.authz pds.resource pds.manifest pds.audit"},
                    headers={"Authorization": f"Basic {basic}"},
                )
            except httpx.HTTPError as e:
                raise PdsUnavailable(f"无法连接统一权限服务：{e.__class__.__name__}") from e
            if r.status_code != 200:
                raise PdsUnavailable(f"获取 PDS 服务令牌失败（HTTP {r.status_code}）")
            body = r.json()
            self._token = body["access_token"]
            self._token_exp = time.time() + int(body.get("expires_in", 300))
            return self._token

    async def _call(self, method: str, path: str, *, as_user: str | None = None, **kw: Any) -> Any:
        token = as_user or await self.service_token()
        headers = kw.pop("headers", {}) | {"Authorization": f"Bearer {token}"}
        try:
            r = await self._http.request(method, f"{self.base}/api/v1{path}", headers=headers, **kw)
        except httpx.HTTPError as e:
            raise PdsUnavailable(f"调用统一权限服务失败：{e.__class__.__name__}") from e
        if r.status_code >= 500:
            raise PdsUnavailable(f"统一权限服务异常（HTTP {r.status_code}）")
        body = r.json() if r.content else {}
        if r.status_code >= 400 or body.get("code", 0) != 0:
            raise BizError(ErrorCode.DEPENDENCY_FAILED, f"PDS：{body.get('message') or r.status_code}")
        return body.get("data")

    # ---------- 鉴权 ----------
    async def snapshot(self, subject: str, app: str | None = None) -> dict[str, Any]:
        return await self._call("GET", "/authz/snapshot", params={"app": app or self.s.app_code, "subject": subject})

    async def check(self, subject: str, permission: str | None = None, *, resource_type: str | None = None,
                    resource_id: str | None = None, action: str | None = None) -> dict[str, Any]:
        body = {"subject": subject, "permission": permission, "resourceType": resource_type,
                "resourceId": resource_id, "action": action}
        return await self._call("POST", "/authz/check", json=body)

    # ---------- 清单与资源 ----------
    async def register_manifest(self, manifest: dict[str, Any], app: str | None = None) -> Any:
        return await self._call("POST", f"/apps/{app or self.s.app_code}/manifest", json=manifest)

    async def register_resource(self, type_: str, ref_id: str, name: str, scenic_id: str | None,
                                owner_id: str | None = None) -> Any:
        body = {"type": type_, "refId": ref_id, "name": name, "scenicId": scenic_id, "ownerId": owner_id}
        return await self._call("POST", "/resources", json=body)

    # 资源授权由用户本人发起（PDS 校验其对该资源的管理权），需传入用户访问令牌
    async def resource_grants(self, type_: str, ref_id: str, user_token: str | None = None) -> Any:
        return await self._call("GET", f"/resources/{type_}/{ref_id}/grants", as_user=user_token)

    async def grant_resource(self, type_: str, ref_id: str, grant: dict[str, Any], user_token: str) -> Any:
        return await self._call("POST", f"/resources/{type_}/{ref_id}/grants", json=grant, as_user=user_token)

    async def revoke_resource(self, type_: str, ref_id: str, grant_id: str, user_token: str) -> Any:
        return await self._call("DELETE", f"/resources/{type_}/{ref_id}/grants/{grant_id}", as_user=user_token)

    # ---------- 审计 ----------
    async def audit(self, events: list[dict[str, Any]]) -> Any:
        return await self._call("POST", "/audit/events", json={"events": events})


_client: PdsClient | None = None


def get_pds() -> PdsClient:
    global _client
    if _client is None:
        _client = PdsClient()
    return _client


def set_pds(client: PdsClient | None) -> None:
    global _client
    _client = client
