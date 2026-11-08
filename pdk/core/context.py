"""请求级上下文（trace_id、当前用户景区范围），基于 contextvars，异步安全。"""

from __future__ import annotations

from contextvars import ContextVar
from dataclasses import dataclass

_trace_id: ContextVar[str | None] = ContextVar("pdk_trace_id", default=None)


def current_trace_id() -> str | None:
    return _trace_id.get()


def set_trace_id(value: str | None):
    return _trace_id.set(value)


@dataclass(frozen=True)
class ScenicScope:
    """数据库查询的景区范围。bypass=True 仅限系统任务，且必须记录原因。"""

    scenic_ids: frozenset[str]
    bypass: bool = False
    reason: str | None = None


_scenic_scope: ContextVar[ScenicScope | None] = ContextVar("pdk_scenic_scope", default=None)


def current_scenic_scope() -> ScenicScope | None:
    return _scenic_scope.get()


def set_scenic_scope(scope: ScenicScope | None):
    return _scenic_scope.set(scope)


def reset_scenic_scope(token) -> None:
    _scenic_scope.reset(token)
