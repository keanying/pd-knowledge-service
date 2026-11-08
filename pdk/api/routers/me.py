from __future__ import annotations

from fastapi import APIRouter, Depends

from pdk.auth.context import AuthContext
from pdk.auth.deps import auth_context
from pdk.config import get_settings
from pdk.core.response import R, ok

router = APIRouter(prefix="/api/v1", tags=["当前用户"])


@router.get("/me", summary="当前用户、PDK 权限点与景区范围（前端按此渲染菜单与按钮）")
async def me(ctx: AuthContext = Depends(auth_context)) -> R[dict]:
    snap = ctx.snapshot
    return ok({
        "user": {"id": ctx.user_id, "name": ctx.name, "scenic_id": snap.user.scenicId, "dept_id": snap.user.deptId,
                 "emp_no": ctx.claims.get("emp_no")},
        "permissions": sorted(snap.permissions),
        "visible": sorted(snap.visible),
        "roles": snap.roles,
        "scenic_scope": sorted(snap.scenicScope),
        "max_security_level": snap.maxSecurityLevel,
        "degraded": ctx.degraded,
        "auth_mode": get_settings().auth_mode,
        "via": ctx.via,
    })
