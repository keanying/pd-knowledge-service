"""清洗规则（PAR-05）：去页眉页脚、空白规范化、正则替换。景区级规则后续由后台配置。"""

from __future__ import annotations

import re

from pdk.parsers.base import Block


def clean_blocks(blocks: list[Block], rules: dict | None = None) -> list[Block]:
    rules = rules or {}
    drop_hf = rules.get("drop_header_footer", True)
    replaces = [(re.compile(p), r) for p, r in rules.get("regex_replace", [])]
    out = []
    for b in blocks:
        if drop_hf and b.type in ("header", "footer"):
            continue
        text = b.text.replace("　", " ").replace("\xa0", " ")
        text = re.sub(r"[ \t]+", " ", text)
        text = re.sub(r"\n{3,}", "\n\n", text).strip()
        for pat, rep in replaces:
            text = pat.sub(rep, text)
        if text:
            out.append(b.model_copy(update={"text": text}))
    return out
