"""MinerU 解析适配器（独立部署的 mineru-api 服务，多实例经 MinerU Router 负载均衡）。

调用 POST {url}/file_parse 取回 Markdown 与结构化 content_list，转换为内部文档模型。
MinerU 的 HTTP 接口在不同版本间有变化：适配器只依赖 content_list 中的通用字段
（type / text / text_level / page_idx / bbox / table_body / img_caption），部署时锁定版本并在此兼容转换。
"""

from __future__ import annotations

import json
from typing import Any

import httpx

from pdk.config import get_settings
from pdk.parsers.base import Block, ParsedDocument, ParseError


class MinerUParser:
    name = "mineru"

    def __init__(self, base_url: str):
        self.base_url = base_url.rstrip("/")

    async def parse(self, data: bytes, file_name: str, options: dict | None = None) -> ParsedDocument:
        s = get_settings()
        opts = options or {}
        form = {
            "backend": opts.get("backend", s.mineru_backend),
            "lang_list": opts.get("lang", "ch"),
            "formula_enable": str(opts.get("formula", True)).lower(),
            "table_enable": str(opts.get("table", True)).lower(),
            "return_md": "true",
            "return_content_list": "true",
        }
        try:
            async with httpx.AsyncClient(timeout=s.mineru_timeout) as http:
                r = await http.post(f"{self.base_url}/file_parse", data=form, files={"files": (file_name, data)})
        except httpx.TimeoutException as e:
            raise ParseError("解析超时，请稍后重试或更换解析模式") from e
        except httpx.HTTPError as e:
            raise ParseError(f"无法连接解析服务：{e.__class__.__name__}") from e
        if r.status_code != 200:
            raise ParseError(f"解析服务返回错误（HTTP {r.status_code}）：{r.text[:200]}")
        return convert_response(r.json())


def convert_response(body: dict[str, Any]) -> ParsedDocument:
    """兼容 {results: {文件名: {md_content, content_list}}} 与扁平 {md_content, content_list} 两种结构。"""
    result = body
    if "results" in body and isinstance(body["results"], dict) and body["results"]:
        result = next(iter(body["results"].values()))
    content_list = result.get("content_list") or []
    if isinstance(content_list, str):
        content_list = json.loads(content_list)
    blocks = convert_content_list(content_list)
    if not blocks:
        raise ParseError("未解析出任何内容（可能是空白文档或纯图片且未开启 OCR）")
    return ParsedDocument(blocks=blocks, markdown=result.get("md_content") or "", parser="mineru",
                          meta={"backend": body.get("backend"), "version": body.get("version")})


def convert_content_list(items: list[dict[str, Any]]) -> list[Block]:
    blocks: list[Block] = []
    for i, it in enumerate(items):
        t = it.get("type", "text")
        page = it.get("page_idx")
        common = {"block_id": f"b{i}", "page_no": page + 1 if isinstance(page, int) else None,
                  "bbox": [float(x) for x in it["bbox"]] if it.get("bbox") else None}
        if t == "text":
            text = (it.get("text") or "").strip()
            if not text:
                continue
            level = it.get("text_level")
            if level:
                blocks.append(Block(type="title", level=int(level), text=text, **common))
            else:
                blocks.append(Block(type="text", text=text, **common))
        elif t == "table":
            caption = " ".join(it.get("table_caption") or [])
            body = it.get("table_body") or ""
            if body:
                blocks.append(Block(type="table", text=(caption + "\n" + body).strip(), **common))
        elif t == "image":
            caption = " ".join(it.get("image_caption") or it.get("img_caption") or [])
            if caption:
                blocks.append(Block(type="image", text=caption, **common))
        elif t == "equation":
            if it.get("text"):
                blocks.append(Block(type="equation", text=it["text"], **common))
        elif t in ("list", "header", "footer"):
            text = it.get("text") or "\n".join(it.get("list_items") or [])
            if text:
                blocks.append(Block(type=t, text=text, **common))  # type: ignore[arg-type]
    return blocks
