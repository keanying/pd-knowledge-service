"""与 PDS 同步：权限清单、知识库资源实例注册。"""

from __future__ import annotations

import logging

from pdk.auth.manifest import build_manifest
from pdk.auth.pds_client import get_pds
from pdk.config import get_settings
from pdk.db.models import KnowledgeBase

log = logging.getLogger("pdk.pds")


async def sync_manifest() -> dict:
    return await get_pds().register_manifest(build_manifest())


async def register_kb(kb: KnowledgeBase) -> bool:
    """把知识库注册为 PDS 资源实例 pdk:kb:{id}；失败不阻断业务，下次编辑或定时任务重试。"""
    if get_settings().auth_mode == "dev":
        return False
    try:
        await get_pds().register_resource("pdk:kb", kb.id, kb.name, kb.scenic_id, kb.owner_id)
        return True
    except Exception as e:  # noqa: BLE001
        log.warning("知识库注册到 PDS 失败（稍后重试）：kb=%s %s", kb.id, e)
        return False
