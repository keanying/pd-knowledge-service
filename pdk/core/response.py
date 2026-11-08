"""统一响应：{"code": 0, "message": "成功", "data": {...}, "trace_id": "..."}。"""

from __future__ import annotations

from typing import Generic, TypeVar

from pydantic import BaseModel

from pdk.core.context import current_trace_id

T = TypeVar("T")


class R(BaseModel, Generic[T]):
    code: int = 0
    message: str = "成功"
    data: T | None = None
    trace_id: str | None = None


def ok(data: T | None = None, message: str = "成功") -> R[T]:
    return R(code=0, message=message, data=data, trace_id=current_trace_id())


class Page(BaseModel, Generic[T]):
    total: int
    items: list[T]
