"""解析器接口与统一的内部文档模型（技术方案 §4.2）。

解析器按接口抽象：MinerUParser（一期）/ PlainTextParser（TXT/MD/CSV）/ 后续 ASRParser（音视频）、
PDPParser（客户 PDP 平台就绪后）。所有解析器都输出 ParsedDocument，下游切片只依赖这个模型。
"""

from __future__ import annotations

from typing import Literal, Protocol

from pydantic import BaseModel

BlockType = Literal["title", "text", "table", "image", "equation", "list", "header", "footer"]


class Block(BaseModel):
    block_id: str
    type: BlockType
    level: int | None = None  # 标题层级（1 起）
    text: str  # 表格为 Markdown/HTML
    page_no: int | None = None
    bbox: list[float] | None = None  # 原文坐标，用于高亮
    time_range: tuple[float, float] | None = None  # 音视频时间戳


class ParsedDocument(BaseModel):
    blocks: list[Block]
    markdown: str
    parser: str
    meta: dict = {}


class ParseError(Exception):
    """解析失败，message 为中文原因（文件加密、损坏、超页数、超时等）。"""


class Parser(Protocol):
    name: str
    file_types: frozenset[str]

    async def parse(self, data: bytes, file_name: str, options: dict | None = None) -> ParsedDocument: ...


# MinerU 支持的格式（产品文档 DOC-02）；TXT/MD/CSV 直接读取
MINERU_TYPES = frozenset({"pdf", "png", "jpg", "jpeg", "doc", "docx", "ppt", "pptx", "xls", "xlsx", "rtf",
                          "odt", "ods", "odp", "epub", "ofd", "html", "mhtml", "htm"})
TEXT_TYPES = frozenset({"txt", "md", "markdown", "csv", "tsv"})
SUPPORTED_TYPES = MINERU_TYPES | TEXT_TYPES


def file_type_of(file_name: str) -> str:
    return file_name.rsplit(".", 1)[-1].lower() if "." in file_name else ""


def get_parser(file_type: str) -> Parser:
    from pdk.config import get_settings
    from pdk.parsers.mineru import MinerUParser
    from pdk.parsers.plaintext import PlainTextParser

    if file_type in TEXT_TYPES:
        return PlainTextParser()
    if file_type in MINERU_TYPES:
        url = get_settings().mineru_url
        if not url:
            raise ParseError("未配置 MinerU 解析服务（PDK_MINERU_URL），当前只能处理 TXT/MD/CSV 文件")
        return MinerUParser(url)
    raise ParseError(f"不支持的文件格式：{file_type or '未知'}")
