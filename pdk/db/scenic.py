"""景区隔离（数据库层）：对带 scenic_id 的模型，所有 SELECT 自动追加 scenic_id IN (范围)。

- 请求进入时由鉴权依赖根据权限快照设置范围（用户景区范围 + GROUP）；
- 后台任务以系统身份运行时，必须显式调用 system_scope(reason) 声明绕过，并记录日志；
- 未设置范围就查询带景区字段的表会直接报错，避免遗漏导致越权。

注意（SQLAlchemy 限制）：条件只作用于语句顶层出现的实体。计数请写 select(func.count(Model.id))，
不要写 select(func.count()).select_from(Model) 或对 select(Model).subquery() 计数，后两种不会被追加条件。
"""

from __future__ import annotations

import logging
from contextlib import contextmanager

from sqlalchemy import event
from sqlalchemy.orm import ORMExecuteState, Session, with_loader_criteria

from pdk.core.context import ScenicScope, current_scenic_scope, reset_scenic_scope, set_scenic_scope
from pdk.db.base import ScenicScoped
from pdk.db.models import GROUP_SCENIC

log = logging.getLogger("pdk.scenic")


class ScenicScopeMissing(RuntimeError):
    pass


@event.listens_for(Session, "do_orm_execute")
def _add_scenic_criteria(state: ORMExecuteState) -> None:
    if not state.is_select or state.is_column_load or state.is_relationship_load:
        return
    if not _touches_scoped(state):
        return
    scope = current_scenic_scope()
    if scope is None:
        raise ScenicScopeMissing("查询带景区字段的数据前必须设置景区范围（请求内由鉴权自动设置；后台任务使用 system_scope）")
    if scope.bypass:
        return
    ids = sorted(scope.scenic_ids | {GROUP_SCENIC})
    state.statement = state.statement.options(
        with_loader_criteria(ScenicScoped, lambda cls: cls.scenic_id.in_(ids), include_aliases=True)
    )


def _touches_scoped(state: ORMExecuteState) -> bool:
    for desc in state.statement.column_descriptions if hasattr(state.statement, "column_descriptions") else []:
        entity = desc.get("entity")
        if entity is not None and isinstance(entity, type) and issubclass(entity, ScenicScoped):
            return True
    try:
        froms = state.statement.get_final_froms()
    except Exception:  # noqa: BLE001
        return True
    scoped_tables = {m.local_table.name for m in ScenicScoped.__subclasses__() if hasattr(m, "local_table")}
    return any(getattr(f, "name", None) in scoped_tables for f in froms)


@contextmanager
def user_scope(scenic_ids: set[str] | frozenset[str]):
    token = set_scenic_scope(ScenicScope(frozenset(scenic_ids)))
    try:
        yield
    finally:
        reset_scenic_scope(token)


@contextmanager
def system_scope(reason: str):
    """系统任务绕过景区隔离（如流水线 Worker、定时清理）。"""
    log.info("系统任务绕过景区隔离：%s", reason)
    token = set_scenic_scope(ScenicScope(frozenset(), bypass=True, reason=reason))
    try:
        yield
    finally:
        reset_scenic_scope(token)
