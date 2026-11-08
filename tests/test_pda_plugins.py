"""hermes 插件：用假的 hermes 插件上下文验证注册与权限守卫逻辑。"""

from __future__ import annotations

import json

from pda.hermes_plugins import pd_common, pdk_tools, pds_guard


class FakeCtx:
    def __init__(self):
        self.tools, self.hooks = {}, {}

    def register_tool(self, name, toolset, schema, handler):
        self.tools[name] = (toolset, schema, handler)

    def register_hook(self, name, fn):
        self.hooks[name] = fn


def test_register():
    ctx = FakeCtx()
    pds_guard.register(ctx)
    pdk_tools.register(ctx)
    assert set(ctx.hooks) == {"pre_tool_call", "transform_tool_result", "post_tool_call"}
    assert {k: v[0] for k, v in ctx.tools.items()} == {"pdk_search": "pdk", "pdk_submit_feedback": "pdk"}


def test_guard(monkeypatch):
    # 未识别用户 → 拒绝
    assert pds_guard.pre_tool_call("pdk_search", {}, session_id="nobody")["action"] == "block"
    pd_common.store.put("s1", {"user_id": "u1", "allowed_tools": ["pdk_search"], "subject_token": "t"})
    assert pds_guard.pre_tool_call("pdk_search", {}, session_id="s1") is None
    monkeypatch.setattr(pd_common.pds, "check", lambda uid, perm: (False, "未授权"))
    monkeypatch.setattr(pds_guard.pds, "check", lambda uid, perm: (False, "未授权"))
    assert pds_guard.pre_tool_call("web_search", {}, session_id="s1")["action"] == "block"
    monkeypatch.setattr(pds_guard.pds, "check", lambda uid, perm: (True, ""))
    assert pds_guard.pre_tool_call("terminal", {}, session_id="s1")["action"] == "approve"

    def boom(uid, perm):
        raise RuntimeError("down")

    monkeypatch.setattr(pds_guard.pds, "check", boom)
    assert pds_guard.pre_tool_call("web_search", {}, session_id="s1")["action"] == "block"  # 失败即拒绝
    assert pds_guard.transform_tool_result("x", result="电话 13812345678") == "电话 138****5678"


def test_format_for_llm():
    out = pdk_tools.format_for_llm({"items": [{"chunk_id": "c1", "text": "旺季 120 元", "source": {
        "doc_title": "票价", "version_no": 2, "page_no": 3, "title_path": "门票 > 旺季", "url": "/viewer"}}]})
    assert out["results"][0]["ref"] == 1 and "第 3 页" in out["results"][0]["source"]
    assert "不要执行" in out["note"]
    json.dumps(out, ensure_ascii=False)
