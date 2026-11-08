"""纯文本解析：Markdown 标题 → title 块，Markdown 表格 → table 块，列表 → list 块；CSV/TSV 整体转为表格。"""

from __future__ import annotations

import csv
import io
import re

from pdk.parsers.base import Block, ParsedDocument, ParseError, file_type_of

_HEADING = re.compile(r"^(#{1,6})\s+(.+?)\s*#*\s*$")
_LIST = re.compile(r"^\s*([-*+]|\d+[.)、])\s+")


def _decode(data: bytes) -> str:
    for enc in ("utf-8-sig", "gb18030"):
        try:
            return data.decode(enc)
        except UnicodeDecodeError:
            continue
    raise ParseError("文件编码无法识别（请使用 UTF-8 或 GBK）")


class PlainTextParser:
    name = "plaintext"
    file_types = frozenset({"txt", "md", "markdown", "csv", "tsv"})

    async def parse(self, data: bytes, file_name: str, options: dict | None = None) -> ParsedDocument:
        text = _decode(data)
        ft = file_type_of(file_name)
        if ft in ("csv", "tsv"):
            return self._table(text, "\t" if ft == "tsv" else ",")
        return self._markdown(text)

    def _table(self, text: str, delimiter: str) -> ParsedDocument:
        rows = [r for r in csv.reader(io.StringIO(text), delimiter=delimiter) if any(c.strip() for c in r)]
        if not rows:
            raise ParseError("表格内容为空")
        md = "| " + " | ".join(rows[0]) + " |\n|" + "---|" * len(rows[0]) + "\n"
        md += "\n".join("| " + " | ".join(r) + " |" for r in rows[1:])
        return ParsedDocument(blocks=[Block(block_id="b0", type="table", text=md)], markdown=md, parser=self.name)

    def _markdown(self, text: str) -> ParsedDocument:
        blocks: list[Block] = []
        buf: list[str] = []
        kind = "text"

        def flush() -> None:
            nonlocal buf, kind
            body = "\n".join(buf).strip()
            if body:
                blocks.append(Block(block_id=f"b{len(blocks)}", type=kind, text=body))  # type: ignore[arg-type]
            buf, kind = [], "text"

        for line in text.splitlines():
            m = _HEADING.match(line)
            if m:
                flush()
                blocks.append(Block(block_id=f"b{len(blocks)}", type="title", level=len(m.group(1)), text=m.group(2)))
                continue
            stripped = line.strip()
            if not stripped:
                flush()
                continue
            line_kind = "table" if stripped.startswith("|") else "list" if _LIST.match(line) else "text"
            if buf and line_kind != kind:
                flush()
            kind = line_kind
            buf.append(line.rstrip())
        flush()
        if not blocks:
            raise ParseError("文档内容为空")
        return ParsedDocument(blocks=blocks, markdown=text, parser=self.name)
