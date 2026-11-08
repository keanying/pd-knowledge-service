"""接入流水线编排（LangGraph 状态图）。

    parse → (待校对? 中断) → chunk → index → (需审核? 中断) → publish

- 每个文档版本一条流水线实例，thread_id = version_id；
- 状态只保存 version_id 与步骤结果，大数据（解析产物、切片）都落在对象存储与数据库中，节点幂等；
- “待校对”“待审核”在图中表现为结束于中间状态：人工操作后由接口重新触发后续步骤（resume_from）。
- 检查点：开发使用内存；生产可接入 langgraph-checkpoint-postgres 的 AsyncPostgresSaver，Worker 重启后从最近节点继续。
"""

from __future__ import annotations

from typing import Literal, TypedDict

from langgraph.graph import END, START, StateGraph

from pdk.db.models import VersionStatus
from pdk.db.scenic import system_scope
from pdk.db.session import session_factory
from pdk.ingest import steps

Step = Literal["parse", "chunk", "index", "publish"]
ORDER: list[Step] = ["parse", "chunk", "index", "publish"]


class IngestState(TypedDict, total=False):
    version_id: str
    start: Step
    status: str
    done: list[str]


def _node(name: Step, fn):
    async def run(state: IngestState) -> IngestState:
        with system_scope(f"接入流水线 {name}"):
            async with session_factory()() as s:
                await fn(s, state["version_id"])
                v, _, kb = await steps.load(s, state["version_id"])
                status = v.status
                if name == "index" and not kb.review_required:
                    status = "auto_publish"
        return {"status": status, "done": [*state.get("done", []), name]}

    return run


def _route_start(state: IngestState) -> str:
    return state.get("start", "parse")


def _after_parse(state: IngestState) -> str:
    return END if state["status"] == VersionStatus.PENDING_PROOFREAD else "chunk"


def _after_index(state: IngestState) -> str:
    return "publish" if state["status"] == "auto_publish" else END


def build_graph():
    g = StateGraph(IngestState)
    g.add_node("parse", _node("parse", steps.step_parse))
    g.add_node("chunk", _node("chunk", steps.step_chunk))
    g.add_node("index", _node("index", steps.step_index))
    g.add_node("publish", _node("publish", steps.step_publish))
    g.add_conditional_edges(START, _route_start, {n: n for n in ORDER})
    g.add_conditional_edges("parse", _after_parse, {"chunk": "chunk", END: END})
    g.add_edge("chunk", "index")
    g.add_conditional_edges("index", _after_index, {"publish": "publish", END: END})
    g.add_edge("publish", END)
    return g.compile()


_graph = None


def graph():
    global _graph
    if _graph is None:
        _graph = build_graph()
    return _graph
