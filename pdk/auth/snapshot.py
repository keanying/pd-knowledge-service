"""PDS 权限快照（GET /api/v1/authz/snapshot 的返回），以及 PDK 侧的便捷判断。"""

from __future__ import annotations

import time
from typing import Any

from pydantic import BaseModel, Field

# 资源动作包含关系：admin ⊃ write ⊃ read
_ACTION_IMPLIED_BY = {"read": ("read", "write", "admin"), "write": ("write", "admin"), "admin": ("admin",)}


class SnapshotUser(BaseModel):
    id: str
    name: str | None = None
    scenicId: str | None = None
    deptId: str | None = None


class AuthzSnapshot(BaseModel):
    version: int = 0
    app: str = "pdk"
    user: SnapshotUser
    permissions: set[str] = Field(default_factory=set)
    dataScopes: dict[str, Any] = Field(default_factory=dict)
    scenicScope: set[str] = Field(default_factory=set)
    # {资源类型: {read/write/admin: [资源 ID]}}
    resources: dict[str, dict[str, set[str]]] = Field(default_factory=dict)
    maxSecurityLevel: int = 0
    maskPolicies: list[Any] = Field(default_factory=list)
    expiresIn: int = 300
    roles: list[str] = Field(default_factory=list)
    visible: set[str] = Field(default_factory=set)

    # ---- PDK 本地字段（不来自 PDS）----
    fetched_at: float = Field(default_factory=time.time)
    # 开发模式：不限制资源实例（仍按景区、密级过滤）
    unrestricted_resources: bool = False

    def has(self, permission: str) -> bool:
        return permission in self.permissions

    def accessible(self, resource_type: str, action: str = "read") -> set[str] | None:
        """可访问的资源 ID 集合；返回 None 表示不限制（仅开发模式）。"""
        if self.unrestricted_resources:
            return None
        by_action = self.resources.get(resource_type, {})
        out: set[str] = set()
        for a in _ACTION_IMPLIED_BY.get(action.lower(), (action.lower(),)):
            out |= set(by_action.get(a, ()))
        return out

    def can_access(self, resource_type: str, resource_id: str, action: str = "read") -> bool:
        ids = self.accessible(resource_type, action)
        return ids is None or resource_id in ids

    def data_scope(self, permission: str) -> dict[str, Any] | None:
        return self.dataScopes.get(permission)
