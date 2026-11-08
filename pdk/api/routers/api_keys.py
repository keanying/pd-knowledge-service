"""开放接口密钥（SYS-03）。"""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from pdk.auth.context import AuthContext
from pdk.auth.deps import require
from pdk.core.errors import not_found
from pdk.core.response import R, ok
from pdk.db.models import ApiKey
from pdk.db.session import get_session
from pdk.services.api_keys import create_api_key
from pdk.services.audit import audit

router = APIRouter(prefix="/api/v1/api-keys", tags=["接口密钥"])


class KeyCreate(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    kb_scope: list[str] = Field(default_factory=list, description="可访问的知识库（必须是本人有管理权的库）")
    scenic_scope: list[str] = Field(default_factory=list)
    ip_whitelist: list[str] = Field(default_factory=list)
    expires_at: datetime | None = None


class KeyView(BaseModel):
    id: str
    name: str
    key_prefix: str
    kb_scope: list[str]
    scenic_scope: list[str]
    ip_whitelist: list[str]
    expires_at: datetime | None
    enabled: bool
    created_by: str | None
    created_at: datetime
    model_config = {"from_attributes": True}


@router.get("", summary="密钥列表")
async def list_keys(ctx: AuthContext = Depends(require("pdk:apikey:manage")),
                    s: AsyncSession = Depends(get_session)) -> R[list[KeyView]]:
    rows = (await s.execute(select(ApiKey).order_by(ApiKey.created_at.desc()))).scalars().all()
    return ok([KeyView.model_validate(k) for k in rows])


@router.post("", summary="创建密钥（明文只返回这一次）")
async def create(req: KeyCreate, ctx: AuthContext = Depends(require("pdk:apikey:manage"))) -> R[dict]:
    for kb in req.kb_scope:
        ctx.require_kb(kb, "admin")
    for sc in req.scenic_scope:
        ctx.require_scenic(sc)
    key, raw = await create_api_key(req.name, req.kb_scope, req.scenic_scope, req.ip_whitelist, req.expires_at, ctx.user_id)
    audit.emit(ctx, "ADMIN_OP", f"创建接口密钥：{req.name}", target_type="pdk:apikey", target_ids=key.id)
    return ok({"key": KeyView.model_validate(key), "secret": raw})


@router.post("/{key_id}:disable", summary="停用密钥")
async def disable(key_id: str, ctx: AuthContext = Depends(require("pdk:apikey:manage")),
                  s: AsyncSession = Depends(get_session)) -> R[KeyView]:
    k = await s.get(ApiKey, key_id)
    if k is None:
        raise not_found("密钥")
    k.enabled = False
    await s.commit()
    audit.emit(ctx, "ADMIN_OP", f"停用接口密钥：{k.name}", target_type="pdk:apikey", target_ids=k.id)
    return ok(KeyView.model_validate(k))
