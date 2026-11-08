"""业务 ID：前缀 + 时间有序的随机串（Crockford Base32），如 kb_01JB8Z3K4M2Q7R9T。"""

from __future__ import annotations

import os
import time

_ALPHABET = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"


def _b32(n: int, length: int) -> str:
    out = []
    for _ in range(length):
        out.append(_ALPHABET[n & 31])
        n >>= 5
    return "".join(reversed(out))


def new_id(prefix: str) -> str:
    ms = int(time.time() * 1000)
    rand = int.from_bytes(os.urandom(8), "big")
    return f"{prefix}_{_b32(ms, 9)}{_b32(rand, 9)}"
