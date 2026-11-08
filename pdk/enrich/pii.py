"""敏感信息识别与脱敏（CHK-09 / RET-07）。

识别：手机号、身份证号（校验位）、银行卡号（Luhn）、邮箱、车牌号；结果写入切片 pii_types，原文不改。
脱敏：检索结果返回前按策略掩码。规则需与 PDS 保持一致，PDS Python SDK 提供后改为调用 SDK。
"""

from __future__ import annotations

import re

PHONE = re.compile(r"(?<!\d)(1[3-9]\d)(\d{4})(\d{4})(?!\d)")
ID_CARD = re.compile(r"(?<![0-9Xx])(\d{6})(\d{8})(\d{3}[0-9Xx])(?![0-9Xx])")
BANK_CARD = re.compile(r"(?<!\d)(\d{4})(\d{8,11})(\d{4})(?!\d)")
EMAIL = re.compile(r"([A-Za-z0-9._%+-])([A-Za-z0-9._%+-]*)(@[A-Za-z0-9.-]+\.[A-Za-z]{2,})")
PLATE = re.compile(r"([京津沪渝冀豫云辽黑湘皖鲁新苏浙赣鄂桂甘晋蒙陕吉闽贵粤青藏川宁琼][A-HJ-NP-Z])([A-HJ-NP-Z0-9]{3,4})([A-HJ-NP-Z0-9挂学警港澳]{1,2})")

NAMES = {"phone": "手机号", "id_card": "身份证号", "bank_card": "银行卡号", "email": "邮箱", "plate": "车牌号"}


def _id_card_ok(s: str) -> bool:
    w = [7, 9, 10, 5, 8, 4, 2, 1, 6, 3, 7, 9, 10, 5, 8, 4, 2]
    total = sum(int(c) * k for c, k in zip(s[:17], w, strict=False))
    return "10X98765432"[total % 11] == s[17].upper()


def _luhn_ok(s: str) -> bool:
    total = 0
    for i, c in enumerate(reversed(s)):
        d = int(c)
        if i % 2:
            d = d * 2 - 9 if d * 2 > 9 else d * 2
        total += d
    return total % 10 == 0


def detect(text: str) -> list[str]:
    found = []
    if PHONE.search(text):
        found.append("phone")
    if any(_id_card_ok("".join(m.groups())) for m in ID_CARD.finditer(text)):
        found.append("id_card")
    if any(_luhn_ok("".join(m.groups())) and not PHONE.fullmatch("".join(m.groups())) for m in BANK_CARD.finditer(text)):
        found.append("bank_card")
    if EMAIL.search(text):
        found.append("email")
    if PLATE.search(text):
        found.append("plate")
    return found


def mask(text: str, types: list[str] | set[str] | None = None) -> tuple[str, int]:
    """按类型掩码，返回 (文本, 掩码处数)。types 为空表示全部类型。"""
    types = set(types or NAMES)
    count = 0

    def sub(pattern: re.Pattern, repl, check=None):
        nonlocal text, count

        def _r(m: re.Match) -> str:
            nonlocal count
            if check and not check("".join(m.groups())):
                return m.group(0)
            count += 1
            return repl(m)

        text = pattern.sub(_r, text)

    if "id_card" in types:
        sub(ID_CARD, lambda m: m.group(1)[:3] + "*" * 11 + m.group(3)[-4:], _id_card_ok)
    if "bank_card" in types:
        sub(BANK_CARD, lambda m: m.group(1) + "*" * len(m.group(2)) + m.group(3), _luhn_ok)
    if "phone" in types:
        sub(PHONE, lambda m: m.group(1) + "****" + m.group(3))
    if "email" in types:
        sub(EMAIL, lambda m: m.group(1) + "***" + m.group(3))
    if "plate" in types:
        sub(PLATE, lambda m: m.group(1) + "*" * len(m.group(2)) + m.group(3))
    return text, count
