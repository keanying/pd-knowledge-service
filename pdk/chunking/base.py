"""切片（产品文档 §4.4、技术方案 §4.3）。

默认“按结构切片”：维护标题栈得到标题路径；表格整表或按行分组（重复表头）；正文在同一标题下累积，
超长时在中文句末断开并带重叠；检索文本 = 标题路径 + 正文，展示文本 = 正文。
另提供定长切片、FAQ 切片。
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field

from pydantic import BaseModel

from pdk.parsers.base import Block

_SENT_END = re.compile(r"(?<=[。！？；!?;])|(?<=\n)")


class ChunkStrategy(BaseModel):
    mode: str = "structure"  # structure / fixed / faq
    max_len: int = 500
    overlap: int = 50
    parent_child: bool = False
    title_in_embed: bool = True


@dataclass
class ChunkDraft:
    seq: int
    text: str
    embed_text: str
    chunk_type: str = "text"
    title_path: str | None = None
    page_no: int | None = None
    bbox: list[list[float]] = field(default_factory=list)
    parent_key: str | None = None

    @property
    def content_hash(self) -> str:
        norm = re.sub(r"\s+", " ", self.text).strip()
        return hashlib.sha256(f"{self.title_path or ''}\n{norm}".encode()).hexdigest()


def chunk_key(doc_id: str, content_hash: str, dup: int) -> str:
    """与版本无关的切片键（= 向量库主键）。同一文档内容相同的切片用序号消歧。"""
    return "c_" + hashlib.sha256(f"{doc_id}:{content_hash}:{dup}".encode()).hexdigest()[:30]


def split_sentences(text: str) -> list[str]:
    return [s for s in _SENT_END.split(text) if s]


def split_long(text: str, max_len: int, overlap: int) -> list[str]:
    """在句末处断开；单句超长时硬切。每片带上一片末尾 overlap 字。"""
    if len(text) <= max_len:
        return [text]
    pieces: list[str] = []
    cur = ""
    for sent in split_sentences(text):
        while len(sent) > max_len:
            if cur:
                pieces.append(cur)
                cur = ""
            pieces.append(sent[:max_len])
            sent = sent[max_len:]
        if len(cur) + len(sent) > max_len and cur:
            pieces.append(cur)
            cur = ""
        cur += sent
    if cur:
        pieces.append(cur)
    if overlap <= 0:
        return pieces
    out = [pieces[0]]
    for prev, p in zip(pieces, pieces[1:], strict=False):
        out.append(prev[-overlap:] + p)
    return out


def _embed(title_path: str | None, text: str, strategy: ChunkStrategy) -> str:
    return f"{title_path}\n{text}" if (title_path and strategy.title_in_embed) else text


def chunk_structure(blocks: list[Block], strategy: ChunkStrategy) -> list[ChunkDraft]:
    out: list[ChunkDraft] = []
    stack: list[tuple[int, str]] = []
    buf: list[Block] = []
    section_id = 0

    def path() -> str | None:
        return " > ".join(t for _, t in stack) or None

    def emit(text: str, ctype: str, src: list[Block]) -> None:
        tp = path()
        bboxes = [b.bbox for b in src if b.bbox]
        out.append(ChunkDraft(seq=len(out), text=text, embed_text=_embed(tp, text, strategy), chunk_type=ctype,
                              title_path=tp, page_no=next((b.page_no for b in src if b.page_no), None), bbox=bboxes,
                              parent_key=f"s{section_id}" if strategy.parent_child else None))

    def flush() -> None:
        nonlocal buf
        if not buf:
            return
        text = "\n".join(b.text for b in buf).strip()
        if text:
            for piece in split_long(text, strategy.max_len, strategy.overlap):
                emit(piece, "text", buf)
        buf = []

    for b in blocks:
        if b.type in ("header", "footer"):
            continue
        if b.type == "title":
            flush()
            level = b.level or 1
            while stack and stack[-1][0] >= level:
                stack.pop()
            stack.append((level, b.text.strip()))
            section_id += 1
            continue
        if b.type == "table":
            flush()
            for piece in split_table(b.text, strategy.max_len):
                emit(piece, "table", [b])
            continue
        if b.type == "image":
            flush()
            if b.text.strip():
                emit(b.text.strip(), "image", [b])
            continue
        # 正文 / 列表 / 公式：同一标题下累积，超长再切
        if buf and sum(len(x.text) for x in buf) + len(b.text) > strategy.max_len:
            flush()
        buf.append(b)
    flush()
    return out


def split_table(md: str, max_len: int) -> list[str]:
    """小表格整表一片；大表格按行分组，每组重复表头。"""
    if len(md) <= max_len * 2:
        return [md]
    lines = md.splitlines()
    # Markdown 表格：表头 + 分隔行；HTML 表格按 <tr> 分组
    if len(lines) > 2 and set(lines[1].replace("|", "").strip()) <= set("-: "):
        head, rows = lines[:2], lines[2:]
    elif "<tr" in md.lower():
        rows = re.findall(r"<tr.*?</tr>", md, flags=re.S | re.I)
        head, rows = rows[:1], rows[1:]
        return [f"<table>{''.join(head + g)}</table>" for g in _group(rows, max_len)]
    else:
        head, rows = lines[:1], lines[1:]
    return ["\n".join(head + g) for g in _group(rows, max_len)]


def _group(rows: list[str], max_len: int) -> list[list[str]]:
    groups, cur, size = [], [], 0
    for r in rows:
        if cur and size + len(r) > max_len:
            groups.append(cur)
            cur, size = [], 0
        cur.append(r)
        size += len(r)
    if cur:
        groups.append(cur)
    return groups


def chunk_fixed(blocks: list[Block], strategy: ChunkStrategy) -> list[ChunkDraft]:
    text = "\n".join(b.text for b in blocks if b.type not in ("header", "footer"))
    return [ChunkDraft(seq=i, text=p, embed_text=p) for i, p in enumerate(split_long(text, strategy.max_len, strategy.overlap))]


_Q = re.compile(r"^\s*(?:问|Q|q)\s*[:：]\s*(.+)$")
_A = re.compile(r"^\s*(?:答|A|a)\s*[:：]\s*(.*)$")


def chunk_faq(blocks: list[Block], strategy: ChunkStrategy) -> list[ChunkDraft]:
    """FAQ：每组问答一片，检索文本 = 问题，展示文本 = 问题 + 答案。
    支持“问：/答：”文本，或两列表格（问题 | 答案）。"""
    pairs: list[tuple[str, str]] = []
    for b in blocks:
        if b.type == "table":
            lines = [ln for ln in b.text.splitlines() if ln.strip().startswith("|")]
            for ln in lines[2:]:
                cells = [c.strip() for c in ln.strip().strip("|").split("|")]
                if len(cells) >= 2 and cells[0]:
                    pairs.append((cells[0], cells[1]))
            continue
        q, a = None, []
        for ln in b.text.splitlines():
            if m := _Q.match(ln):
                if q:
                    pairs.append((q, "\n".join(a).strip()))
                q, a = m.group(1).strip(), []
            elif (m := _A.match(ln)) and q:
                a.append(m.group(1))
            elif q:
                a.append(ln)
        if q:
            pairs.append((q, "\n".join(a).strip()))
    return [ChunkDraft(seq=i, text=f"问：{q}\n答：{a}", embed_text=q, chunk_type="faq") for i, (q, a) in enumerate(pairs)]


def make_chunks(blocks: list[Block], strategy: ChunkStrategy) -> list[ChunkDraft]:
    fn = {"structure": chunk_structure, "fixed": chunk_fixed, "faq": chunk_faq}.get(strategy.mode, chunk_structure)
    return fn(blocks, strategy)
