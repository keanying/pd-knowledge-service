"""检索（RET）。PDA 知识工具、业务系统、命中测试台共用。"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from pdk.auth.context import AuthContext
from pdk.auth.deps import auth_context, require
from pdk.core.errors import BizError, ErrorCode
from pdk.core.response import R, ok
from pdk.db.session import get_session
from pdk.retrieval.service import SearchRequest, SearchResult, search
from pdk.services.audit import audit

router = APIRouter(prefix="/api/v1", tags=["检索"])


@router.post("/search", summary="知识检索（混合检索 + 重排，检索前按权限过滤）")
async def do_search(req: SearchRequest, request: Request, ctx: AuthContext = Depends(require("pdk:search:use")),
                    s: AsyncSession = Depends(get_session)) -> R[SearchResult]:
    if req.debug and not ctx.has("pdk:search:debug"):
        raise BizError(ErrorCode.NO_PERMISSION, "查看检索调试信息需要“命中测试台”权限")
    res = await search(s, ctx, req)
    audit.emit(ctx, "DATA_ACCESS", req.query, target_type="pdk:kb",
               target_ids=sorted({i.source.kb_id for i in res.items}),
               ip=request.client.host if request.client else None, question=req.query,
               hitDocs=sorted({i.source.doc_title for i in res.items})[:20], hitCount=len(res.items),
               masked=sum(1 for i in res.items if i.masked), latencyMs=res.latency_ms)
    return ok(res)


@router.post("/answer", summary="RAG 问答（规划中，P1）")
async def answer(ctx: AuthContext = Depends(auth_context)) -> R[None]:
    raise BizError(ErrorCode.NOT_IMPLEMENTED, "一站式问答接口建设中；智能问答请使用 PDA")
