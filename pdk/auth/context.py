"""当前请求的身份与权限上下文。接口层统一通过它做功能权限、知识库实例权限、景区与密级判断。"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from pdk.auth.snapshot import AuthzSnapshot
from pdk.core.errors import BizError, ErrorCode
from pdk.db.models import GROUP_SCENIC

KB = "pdk:kb"


@dataclass
class AuthContext:
    user_id: str
    name: str | None
    snapshot: AuthzSnapshot
    via: str  # session / bearer / api_key / dev
    claims: dict[str, Any] = field(default_factory=dict)
    degraded: bool = False
    # 接口密钥调用时绑定的知识库范围（与用户权限取交集）
    api_key_id: str | None = None
    api_key_kbs: set[str] | None = None
    # 代办：经令牌交换调用时的发起方客户端（如 pda-plugin）
    actor: str | None = None
    # 用户访问令牌（代用户调用 PDS 管理接口，如知识库授权）；不记录日志
    token: str | None = field(default=None, repr=False)

    # ---------- 功能权限 ----------
    def has(self, permission: str) -> bool:
        return self.snapshot.has(permission)

    def require(self, permission: str) -> None:
        if not self.has(permission):
            raise BizError(ErrorCode.NO_PERMISSION, f"无此功能权限：{permission}")

    # ---------- 景区 / 密级 ----------
    @property
    def scenic_ids(self) -> set[str]:
        return set(self.snapshot.scenicScope)

    @property
    def scenic_ids_with_group(self) -> set[str]:
        return self.scenic_ids | {GROUP_SCENIC}

    @property
    def default_scenic(self) -> str | None:
        return self.snapshot.user.scenicId or next(iter(sorted(self.scenic_ids)), None)

    def require_scenic(self, scenic_id: str) -> None:
        if scenic_id == GROUP_SCENIC:
            return
        if scenic_id not in self.scenic_ids:
            raise BizError(ErrorCode.OUT_OF_SCENIC_SCOPE, f"超出景区范围：{scenic_id}")

    @property
    def max_security_level(self) -> int:
        return self.snapshot.maxSecurityLevel

    # ---------- 知识库实例 ----------
    def kb_ids(self, action: str = "read") -> set[str] | None:
        """可访问的知识库 ID；None 表示不限（开发模式）。接口密钥调用时与密钥绑定范围取交集。"""
        ids = self.snapshot.accessible(KB, action)
        if self.api_key_kbs is not None:
            ids = set(self.api_key_kbs) if ids is None else ids & self.api_key_kbs
        return ids

    def can_kb(self, kb_id: str, action: str = "read") -> bool:
        ids = self.kb_ids(action)
        return ids is None or kb_id in ids

    def require_kb(self, kb_id: str, action: str = "read") -> None:
        if not self.can_kb(kb_id, action):
            raise BizError(ErrorCode.NO_KB_PERMISSION, f"无此知识库的{_ACTION_NAMES.get(action, action)}权限")

    def require_writable(self) -> None:
        if self.degraded:
            raise BizError(ErrorCode.PDS_UNAVAILABLE, "统一权限服务暂不可用，当前只能查看")

    # ---------- 数据范围 ----------
    def in_data_scope(self, permission: str, *, owner_id: str | None = None, dept_id: str | None = None,
                      scenic_id: str | None = None) -> bool:
        """PDS 数据范围：ALL 不限；否则满足其一即可（本人、组织、组织子树、景区）。未声明时按本人景区范围。"""
        scope = self.snapshot.data_scope(permission)
        if scope is None:
            return scenic_id is None or scenic_id == GROUP_SCENIC or scenic_id in self.scenic_ids
        if scope.get("all") or scope.get("type") == "ALL":
            return True
        if scope.get("self") and owner_id == self.user_id:
            return True
        if dept_id and (dept_id in scope.get("orgIds", []) or dept_id in scope.get("orgTreeIds", [])):
            return True
        return bool(scenic_id and scenic_id in scope.get("scenicIds", []))

    def audit_actor(self) -> dict[str, Any]:
        return {"userId": self.user_id, "userName": self.name, "via": self.actor or self.via}


_ACTION_NAMES = {"read": "查看", "write": "编辑", "admin": "管理"}
