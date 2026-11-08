"""知识接入与治理台（03 文档）：一期接口按模块逐步实现，这里先提供连接器目录与入口权限。"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from pdk.auth.context import AuthContext
from pdk.auth.deps import require
from pdk.core.response import R, ok

router = APIRouter(prefix="/api/v1/studio", tags=["治理台"])

CONNECTORS = [
    {"type": "feishu", "name": "飞书", "capabilities": ["incremental", "realtime", "acl"], "status": "planned", "priority": "P0"},
    {"type": "upload", "name": "文件上传", "capabilities": [], "status": "available", "priority": "P0"},
    {"type": "web", "name": "链接（网页/站点/RSS）", "capabilities": ["incremental"], "status": "planned", "priority": "P0"},
    {"type": "database", "name": "数据库", "capabilities": ["incremental"], "status": "planned", "priority": "P0"},
    {"type": "s3", "name": "对象存储", "capabilities": ["incremental"], "status": "planned", "priority": "P1"},
    {"type": "smb", "name": "共享盘", "capabilities": ["incremental"], "status": "planned", "priority": "P1"},
    {"type": "api", "name": "业务 API", "capabilities": ["incremental"], "status": "planned", "priority": "P1"},
]


@router.get("/connectors", summary="连接器目录")
async def connectors(ctx: AuthContext = Depends(require("pdk:studio:access"))) -> R[list[dict]]:
    return ok(CONNECTORS)
