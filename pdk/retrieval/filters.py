"""权限过滤（技术方案 §6.2）：由权限快照生成 SearchFilter，再转换为 Milvus 过滤表达式。

- 景区：用户景区范围 + GROUP；
- 知识库：快照中 pdk:kb 的 read 集合；请求中指定的范围只能缩小、不能扩大；
- 密级：≤ 用户最高可访问密级；
- 时效：当前时间在生效期内。
所有值来自快照或经校验的请求参数，并做转义，防止表达式注入。
"""

from __future__ import annotations

import json
import re
import time

from pdk.auth.context import AuthContext
from pdk.core.errors import BizError, ErrorCode
from pdk.db.models import GROUP_SCENIC
from pdk.storage.vectors import SearchFilter

_ID = re.compile(r"^[A-Za-z0-9_\-:.]{1,64}$")


def _safe_ids(values: list[str] | set[str], what: str) -> list[str]:
    out = sorted(set(values))
    for v in out:
        if not _ID.match(v):
            raise BizError(ErrorCode.VALIDATION_FAILED, f"{what}格式不正确")
    return out


def build_filter(ctx: AuthContext, kb_ids: list[str] | None = None, tags: list[str] | None = None,
                 doc_ids: list[str] | None = None, now: int | None = None) -> SearchFilter:
    allowed = ctx.kb_ids("read")
    if kb_ids:
        requested = set(_safe_ids(kb_ids, "知识库 ID"))
        scope = requested if allowed is None else requested & allowed
    else:
        scope = allowed
    if scope is not None and not scope:
        raise BizError(ErrorCode.NO_ACCESSIBLE_KNOWLEDGE, "没有可访问的知识库，请联系管理员在 PDS 中授权")
    return SearchFilter(
        scenic_ids=_safe_ids(ctx.scenic_ids_with_group, "景区"),
        kb_ids=None if scope is None else sorted(scope),
        max_security_level=int(ctx.max_security_level),
        now=int(now if now is not None else time.time()),
        tags=[t for t in (tags or []) if t][:20] or None,
        doc_ids=_safe_ids(doc_ids, "文档 ID") if doc_ids else None,
    )


def _list(values: list[str]) -> str:
    return json.dumps(values, ensure_ascii=False)


def to_milvus_expr(f: SearchFilter) -> str:
    parts = [f"scenic_id in {_list(f.scenic_ids)}"]
    if f.kb_ids is not None:
        parts.append(f"kb_id in {_list(f.kb_ids)}")
    parts.append(f"security_level <= {int(f.max_security_level)}")
    parts.append(f"effective_from <= {int(f.now)} and effective_to >= {int(f.now)}")
    if f.tags:
        parts.append(f"array_contains_any(tags, {_list(f.tags)})")
    if f.doc_ids is not None:
        parts.append(f"doc_id in {_list(f.doc_ids)}")
    return " and ".join(parts)


__all__ = ["build_filter", "to_milvus_expr", "GROUP_SCENIC"]
