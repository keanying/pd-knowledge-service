"""PDA 在 PDS 中的权限清单（总体架构 §6.2）。工具、技能、模型新增时由网关客户端自动提交，新权限点默认无人拥有。"""

TOOLS = {"pdk_search": "知识检索工具", "pdk_submit_feedback": "知识纠错工具", "pdk_list_knowledge_bases": "列出知识库"}
MODELS = {"default": "默认模型"}


def build_manifest() -> dict:
    perms = [
        {"code": "pda:chat:use", "name": "使用智能问答", "type": "FUNCTION"},
        {"code": "pda:chat:upload", "name": "问答中上传附件", "type": "FUNCTION"},
        {"code": "pda:chat:export", "name": "导出对话", "type": "FUNCTION", "risk": "HIGH"},
        {"code": "pda:history:view", "name": "查看本人历史会话", "type": "FUNCTION"},
        {"code": "pda:memory:use", "name": "启用个人长期记忆", "type": "FUNCTION"},
        {"code": "pda:skill:manage", "name": "管理技能", "type": "FUNCTION", "risk": "HIGH"},
        {"code": "pda:admin:config", "name": "PDA 运营配置", "type": "FUNCTION", "risk": "HIGH"},
        {"code": "pda:audit:view", "name": "查看 PDA 对话审计", "type": "FUNCTION", "risk": "HIGH"},
    ]
    perms += [{"code": f"pda:tool:{k}", "name": v, "type": "AI_TOOL"} for k, v in TOOLS.items()]
    perms += [{"code": f"pda:model:{k}", "name": v, "type": "AI_MODEL"} for k, v in MODELS.items()]
    return {"name": "PDA 智能助手", "category": "QUERY", "version": "0.1.0", "accessControl": True,
            "permissions": perms, "resourceTypes": [{"type": "pda:skill", "name": "技能"}]}
