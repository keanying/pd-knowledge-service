"""PDK 在 PDS 中的权限清单（总体架构 §6.1、治理台 §4）。

由 `pdk sync-manifest` 或启动时（PDK_SYNC_MANIFEST_ON_STARTUP=true）提交到 PDS；
清单可反复提交，PDS 后台改过的节点不会被覆盖。新增功能时在这里登记权限点。
"""

from __future__ import annotations

from pdk import __version__

# (编码, 名称, 类型, 父节点编码, 风险)
_NODES: list[tuple[str, str, str, str | None, str | None]] = [
    # 管理后台
    ("pdk:console:access", "进入 PDK 管理后台", "MENU", None, None),
    ("pdk:kb:view", "查看知识库", "FUNCTION", "pdk:console:access", None),
    ("pdk:kb:create", "新建知识库", "FUNCTION", "pdk:console:access", None),
    ("pdk:kb:edit", "编辑知识库配置", "FUNCTION", "pdk:console:access", None),
    ("pdk:kb:delete", "删除知识库", "FUNCTION", "pdk:console:access", "HIGH"),
    ("pdk:kb:grant", "知识库授权", "FUNCTION", "pdk:console:access", "HIGH"),
    ("pdk:doc:view", "查看文档", "FUNCTION", "pdk:console:access", None),
    ("pdk:doc:upload", "上传文档", "FUNCTION", "pdk:console:access", None),
    ("pdk:doc:edit", "编辑文档/元数据/切片", "FUNCTION", "pdk:console:access", None),
    ("pdk:doc:delete", "删除文档", "FUNCTION", "pdk:console:access", "HIGH"),
    ("pdk:doc:download", "下载原文", "FUNCTION", "pdk:console:access", "HIGH"),
    ("pdk:doc:review", "审核发布", "FUNCTION", "pdk:console:access", None),
    ("pdk:search:debug", "命中测试台", "FUNCTION", "pdk:console:access", None),
    ("pdk:update:review", "审核知识更新", "FUNCTION", "pdk:console:access", None),
    ("pdk:datasource:manage", "数据源管理", "FUNCTION", "pdk:console:access", None),
    ("pdk:model:manage", "模型配置", "FUNCTION", "pdk:console:access", "HIGH"),
    ("pdk:eval:manage", "评测管理", "FUNCTION", "pdk:console:access", None),
    ("pdk:stats:view", "运营统计", "FUNCTION", "pdk:console:access", None),
    ("pdk:task:manage", "任务中心（重试/取消）", "FUNCTION", "pdk:console:access", None),
    ("pdk:apikey:manage", "开放接口密钥管理", "FUNCTION", "pdk:console:access", "HIGH"),
    ("pdk:pda:manage", "PDA 运营配置", "FUNCTION", "pdk:console:access", None),
    # 接口能力（PDA 知识工具、业务系统）
    ("pdk:search:use", "调用检索", "API", None, None),
    ("pdk:update:submit", "提交知识纠错/更新", "API", None, None),
    # 知识接入与治理台
    ("pdk:studio:access", "进入知识接入与治理台", "MENU", None, None),
    ("pdk:source:view", "查看数据源与条目", "FUNCTION", "pdk:studio:access", None),
    ("pdk:source:manage", "数据源管理与同步控制", "FUNCTION", "pdk:studio:access", None),
    ("pdk:credential:manage", "管理接入凭证", "FUNCTION", "pdk:studio:access", "HIGH"),
    ("pdk:taxonomy:manage", "维护分类体系", "FUNCTION", "pdk:studio:access", None),
    ("pdk:label:task", "标注任务与标签模板", "FUNCTION", "pdk:studio:access", None),
    ("pdk:label:review", "复核标注", "FUNCTION", "pdk:studio:access", None),
    ("pdk:route:manage", "维护路由规则", "FUNCTION", "pdk:studio:access", None),
    ("pdk:pipeline:manage", "流水线编排", "FUNCTION", "pdk:studio:access", None),
    ("pdk:map:view", "查看知识地图", "FUNCTION", "pdk:studio:access", None),
    ("pdk:studio:cost", "查看成本", "FUNCTION", "pdk:studio:access", None),
]

PERMISSION_CODES: frozenset[str] = frozenset(n[0] for n in _NODES) | {"pdk:access"}


def build_manifest() -> dict:
    perms = []
    for code, name, type_, parent, risk in _NODES:
        p = {"code": code, "name": name, "type": type_}
        if parent:
            p["parent"] = parent
        if risk:
            p["risk"] = risk
        perms.append(p)
    return {
        "name": "PDK 知识服务",
        "category": "DATA_OUTLET",
        "version": __version__,
        "description": "知识库 · 检索 · 知识更新",
        "accessControl": True,
        "permissions": perms,
        "resourceTypes": [{"type": "pdk:kb", "name": "知识库"}],
    }
