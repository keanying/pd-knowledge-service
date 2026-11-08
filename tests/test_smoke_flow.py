"""开发模式端到端：建库 → 上传 → 流水线 → 检索 → 新版本增量 → 下线。"""

from __future__ import annotations

from tests.conftest import ok

DOC_V1 = """# 游客须知

## 门票价格

旺季（4月1日—10月31日）门票 120 元/人，淡季 80 元/人。

## 优惠政策

60 周岁以上老人凭身份证免票。学生凭学生证半价。咨询电话 13812345678。

| 票种 | 价格 |
|---|---|
| 成人票 | 120 |
| 学生票 | 60 |
"""

DOC_V2 = DOC_V1.replace("学生凭学生证半价", "学生凭学生证享受 5 折优惠")


async def test_full_flow(client, wait):
    H = {"X-Dev-User": "u_admin", "X-Dev-Scenic": "S001"}
    kb = ok(await client.post("/api/v1/kbs", json={"name": "票务知识库", "scenic_id": "S001"}, headers=H))
    assert kb["scenic_id"] == "S001" and kb["my_actions"] == ["read", "write", "admin"]

    up = ok(await client.post(f"/api/v1/kbs/{kb['id']}/documents", headers=H,
                              files={"file": ("游客须知.md", DOC_V1.encode(), "text/markdown")}, data={"tags": "票务,价格"}))
    await wait()
    doc = ok(await client.get(f"/api/v1/documents/{up['document_id']}", headers=H))
    v1 = doc["versions"][0]
    assert doc["document"]["status"] == "published", doc
    assert v1["status"] == "published" and v1["stats"]["chunks"] >= 3

    chunks = ok(await client.get(f"/api/v1/versions/{v1['id']}/chunks", headers=H))
    assert any("门票价格" in (c["title_path"] or "") for c in chunks["items"])
    assert any("phone" in c["pii_types"] for c in chunks["items"])

    res = ok(await client.post("/api/v1/search", json={"query": "老人 免票", "debug": True}, headers=H))
    assert res["items"], res
    top = res["items"][0]
    assert top["source"]["doc_title"] == "游客须知" and top["source"]["title_path"]
    assert "scenic_id in" in res["debug"]["filter"]
    masked = [i for i in res["items"] if "138" in i["text"]]
    assert all("138****5678" in i["text"] for i in masked)

    # 其他景区的人看不到
    other = {"X-Dev-User": "u_other", "X-Dev-Scenic": "S002"}
    assert ok(await client.post("/api/v1/search", json={"query": "老人 免票"}, headers=other))["items"] == []

    # 新版本：只重算变化的切片
    ok(await client.post(f"/api/v1/documents/{up['document_id']}/versions", headers=H,
                         files={"file": ("游客须知.md", DOC_V2.encode(), "text/markdown")}))
    await wait()
    doc = ok(await client.get(f"/api/v1/documents/{up['document_id']}", headers=H))
    v2 = doc["versions"][0]
    assert v2["status"] == "published" and doc["versions"][1]["status"] == "superseded"
    assert v2["stats"]["reused"] >= 1 and v2["stats"]["embedded"] < v2["stats"]["chunks"], v2["stats"]
    res = ok(await client.post("/api/v1/search", json={"query": "学生 优惠"}, headers=H))
    assert any("5 折" in i["text"] for i in res["items"])
    assert not any("半价" in i["text"] for i in res["items"])

    # 下线后不可检索
    ok(await client.post(f"/api/v1/documents/{up['document_id']}:offline", headers=H))
    assert ok(await client.post("/api/v1/search", json={"query": "学生 优惠"}, headers=H))["items"] == []
