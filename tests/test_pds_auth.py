"""PDS 鉴权模式：用桩替代 JWKS 验签与 PDS 快照接口，验证功能权限、知识库实例权限、降级与事件失效。"""

from __future__ import annotations

import hashlib
import hmac
import json
import time

import pytest

from pdk.auth.pds_client import PdsUnavailable
from tests.conftest import ok

DOC = "# 退票规则\n\n团体票提前 3 天可全额退票，联系电话 13900001111。\n"


class FakeVerifier:
    async def verify(self, token: str) -> dict:
        uid, _, ver = token.partition("@")
        return {"sub": uid, "uid": uid, "name": uid, "authz_ver": int(ver or 0)}


class FakePds:
    def __init__(self):
        self.snaps: dict[str, dict] = {}
        self.calls = 0
        self.down = False

    async def snapshot(self, subject, app=None):
        self.calls += 1
        if self.down:
            raise PdsUnavailable()
        return self.snaps[subject]

    async def register_resource(self, *a, **kw):
        return {}

    async def audit(self, events):
        return None


def snap(uid, perms, kbs=(), admin=(), version=1, scenic=("S001",)):
    return {"version": version, "app": "pdk", "user": {"id": uid, "name": uid, "scenicId": scenic[0]},
            "permissions": list(perms), "scenicScope": list(scenic), "maxSecurityLevel": 1,
            "resources": {"pdk:kb": {"read": list(kbs), "write": [], "admin": list(admin)}}}


@pytest.fixture
def pds(monkeypatch):
    monkeypatch.setenv("PDK_AUTH_MODE", "pds")
    monkeypatch.setenv("PDK_PDS_WEBHOOK_SECRET", "s3cret")
    from pdk.auth import deps, jwt_verifier, pds_client
    from pdk.config import get_settings

    get_settings.cache_clear()
    fake = FakePds()
    pds_client.set_pds(fake)  # type: ignore[arg-type]
    jwt_verifier.set_verifier(FakeVerifier())  # type: ignore[arg-type]
    monkeypatch.setattr(deps, "get_verifier", lambda: FakeVerifier())
    yield fake
    pds_client.set_pds(None)
    jwt_verifier.set_verifier(None)


def bearer(uid, ver=0):
    return {"Authorization": f"Bearer {uid}@{ver}"}


ADMIN_PERMS = ["pdk:console:access", "pdk:kb:view", "pdk:kb:create", "pdk:doc:upload", "pdk:doc:view", "pdk:search:use"]


async def test_kb_permissions_and_search(pds, client, wait):
    pds.snaps["admin"] = snap("admin", ADMIN_PERMS)
    assert (await client.get("/api/v1/me")).json()["code"] == 20001
    kb = ok(await client.post("/api/v1/kbs", json={"name": "票务库"}, headers=bearer("admin")))
    # 新建后 PDS 授予负责人管理权（这里模拟快照刷新）
    pds.snaps["admin"] = snap("admin", ADMIN_PERMS, admin=[kb["id"]], version=2)
    ok(await client.post(f"/api/v1/kbs/{kb['id']}/documents", files={"file": ("退票.md", DOC.encode())},
                         headers=bearer("admin", 2)))
    await wait()

    # 有检索权但没有该库的查看权：没有可访问的知识库
    pds.snaps["zhang"] = snap("zhang", ["pdk:search:use"])
    r = (await client.post("/api/v1/search", json={"query": "团体票退票"}, headers=bearer("zhang"))).json()
    assert r["code"] == 21003
    # 授予该库查看权后（权限版本变大立即刷新）可检索，手机号掩码
    pds.snaps["zhang"] = snap("zhang", ["pdk:search:use"], kbs=[kb["id"]], version=3)
    res = ok(await client.post("/api/v1/search", json={"query": "团体票退票"}, headers=bearer("zhang", 3)))
    assert res["items"] and "139****1111" in res["items"][0]["text"]
    # 只缩小不扩大：指定一个无权的库
    r = (await client.post("/api/v1/search", json={"query": "退票", "kb_ids": ["kb_other"]}, headers=bearer("zhang", 3))).json()
    assert r["code"] == 21003
    # 无功能权限
    r = (await client.post("/api/v1/kbs", json={"name": "x"}, headers=bearer("zhang", 3))).json()
    assert r["code"] == 21001
    # 其他景区
    pds.snaps["li"] = snap("li", ["pdk:search:use"], kbs=[kb["id"]], scenic=("S002",))
    assert ok(await client.post("/api/v1/search", json={"query": "团体票退票"}, headers=bearer("li")))["items"] == []


async def test_degraded_and_webhook(pds, client):
    pds.snaps["wang"] = snap("wang", ["pdk:kb:view", "pdk:kb:create"])
    ok(await client.get("/api/v1/kbs", headers=bearer("wang")))
    calls = pds.calls
    ok(await client.get("/api/v1/kbs", headers=bearer("wang")))
    assert pds.calls == calls  # 命中缓存

    # 事件验签 + 失效缓存
    body = json.dumps({"id": "e1", "type": "role.members.changed", "data": {"added": ["wang"]}}).encode()
    ts, nonce = str(int(time.time())), "n1"
    sig = hmac.new(b"s3cret", f"{ts}.{nonce}.".encode() + body, hashlib.sha256).hexdigest()
    h = {"X-PDS-Timestamp": ts, "X-PDS-Nonce": nonce, "X-PDS-Signature": sig, "Content-Type": "application/json"}
    ok(await client.post("/api/v1/pds/events", content=body, headers=h))
    assert (await client.post("/api/v1/pds/events", content=body, headers=h)).json()["code"] == 20002  # 重放
    bad = {**h, "X-PDS-Nonce": "n2"}
    assert (await client.post("/api/v1/pds/events", content=body, headers=bad)).json()["code"] == 20002  # 签名不符

    # PDS 故障：缓存已被事件清除 → 拒绝（不默认放行）
    pds.down = True
    assert (await client.get("/api/v1/kbs", headers=bearer("wang"))).json()["code"] == 50001
    # 有快照但已过期：只读降级，写操作拒绝
    pds.down = False
    ok(await client.get("/api/v1/kbs", headers=bearer("wang")))
    from pdk.core.cache import get_cache

    raw = await get_cache().get("pdk:snap:wang")
    raw["fetched_at"] = time.time() - 400
    await get_cache().set("pdk:snap:wang", raw, 3600)
    pds.down = True
    me = ok(await client.get("/api/v1/me", headers=bearer("wang")))
    assert me["degraded"] is True
    assert (await client.post("/api/v1/kbs", json={"name": "x"}, headers=bearer("wang"))).json()["code"] == 50001


async def test_api_key_and_mcp(client, wait):
    H = {"X-Dev-User": "u_admin", "X-Dev-Scenic": "S001"}
    kb = ok(await client.post("/api/v1/kbs", json={"name": "制度库", "scenic_id": "S001"}, headers=H))
    ok(await client.post(f"/api/v1/kbs/{kb['id']}/documents", headers=H, files={"file": ("退票.md", DOC.encode())}))
    await wait()
    created = ok(await client.post("/api/v1/api-keys", json={"name": "客服系统", "kb_scope": [kb["id"]], "scenic_scope": ["S001"]}, headers=H))
    assert created["secret"].startswith("pdk_")

    # MCP：initialize → tools/list → tools/call（开发模式身份）
    mh = {**H, "Accept": "application/json, text/event-stream", "Content-Type": "application/json"}
    init = {"jsonrpc": "2.0", "id": 1, "method": "initialize",
            "params": {"protocolVersion": "2025-06-18", "capabilities": {}, "clientInfo": {"name": "t", "version": "1"}}}
    r = await client.post("/mcp/", json=init, headers=mh)
    assert r.status_code == 200, r.text
    ver = r.json()["result"]["protocolVersion"]
    mh["MCP-Protocol-Version"] = ver
    tools = (await client.post("/mcp/", json={"jsonrpc": "2.0", "id": 2, "method": "tools/list"}, headers=mh)).json()
    assert {t["name"] for t in tools["result"]["tools"]} == {"pdk_search", "pdk_list_knowledge_bases"}
    call = {"jsonrpc": "2.0", "id": 3, "method": "tools/call", "params": {"name": "pdk_search", "arguments": {"query": "团体票退票"}}}
    res = (await client.post("/mcp/", json=call, headers=mh)).json()["result"]
    assert not res.get("isError"), res
    payload = res.get("structuredContent") or json.loads(res["content"][0]["text"])
    assert payload["items"][0]["source"]["doc_title"] == "退票"
