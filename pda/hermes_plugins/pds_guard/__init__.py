"""pds_guard：权限守卫、脱敏与审计钩子（hermes 插件）。

- pre_tool_call：按会话反查用户 → 检查 pda:tool:{工具名}；无权限 block，高风险工具 approve（人工确认）；
  未识别到用户一律 block。hermes 对钩子超时/异常默认“失败即拒绝”。
- transform_tool_result：工具结果出站前再做一次敏感信息掩码（PDK 已按策略脱敏，这里兜底）。
- post_tool_call：记录工具调用审计（由网关汇总上报 PDS）。
"""

from __future__ import annotations

import logging
import re
from typing import Any

try:
    from pd_common import current_ctx, pds  # hermes 插件目录中的同级包
except ImportError:  # 在本仓库中运行测试
    from pda.hermes_plugins.pd_common import current_ctx, pds

log = logging.getLogger("pds_guard")

HIGH_RISK_TOOLS = {"terminal", "execute_code", "write_file", "browser", "computer_use"}
_PHONE = re.compile(r"(?<!\d)(1[3-9]\d)\d{4}(\d{4})(?!\d)")
_IDCARD = re.compile(r"(?<![0-9Xx])(\d{3})\d{11}(\d{3}[0-9Xx])(?![0-9Xx])")


def pre_tool_call(tool_name: str, args: dict | None = None, task_id: str | None = None, **kw: Any):
    c = current_ctx(kw)
    if c is None:
        return {"action": "block", "message": "未识别到登录用户，已拒绝执行工具"}
    allowed_tools = c.get("allowed_tools")
    if allowed_tools is not None and tool_name in allowed_tools:
        allowed, reason = True, ""
    else:
        try:
            allowed, reason = pds.check(c["user_id"], f"pda:tool:{tool_name}")
        except Exception as e:  # noqa: BLE001  PDS 不可用：拒绝，不默认放行
            log.warning("权限检查失败：%s", e)
            return {"action": "block", "message": "权限服务暂不可用，已拒绝执行工具"}
    if not allowed:
        return {"action": "block", "message": f"您没有使用「{tool_name}」的权限，可在 PDS 申请。{reason}"}
    if tool_name in HIGH_RISK_TOOLS:
        return {"action": "approve", "message": "高风险操作，需要人工确认", "rule_key": f"pda:{tool_name}"}
    return None


def mask_text(text: str) -> str:
    text = _IDCARD.sub(lambda m: m.group(1) + "*" * 11 + m.group(2)[-4:], text)
    return _PHONE.sub(lambda m: m.group(1) + "****" + m.group(2), text)


def transform_tool_result(tool_name: str, args: dict | None = None, result: Any = None, task_id: str | None = None, **kw: Any):
    return mask_text(result) if isinstance(result, str) else result


def post_tool_call(tool_name: str, args: dict | None = None, result: Any = None, task_id: str | None = None, **kw: Any):
    c = current_ctx(kw) or {}
    log.info("工具调用 user=%s tool=%s task=%s", c.get("user_id"), tool_name, task_id)


def register(ctx) -> None:
    ctx.register_hook("pre_tool_call", pre_tool_call)
    ctx.register_hook("transform_tool_result", transform_tool_result)
    ctx.register_hook("post_tool_call", post_tool_call)
