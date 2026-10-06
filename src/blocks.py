"""Tách markdown thành các khối có kiểu: text / image / table / formula / code."""
from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass
from enum import Enum
from typing import Iterator


class BlockType(str, Enum):
    TEXT = "text"
    IMAGE = "image"
    TABLE = "table"
    FORMULA = "formula"
    CODE = "code"


# Thứ tự alternation quyết định ưu tiên khi trùng vị trí bắt đầu.
# code đứng đầu để "$$" hoặc "![" nằm trong code block không bị bắt nhầm.
_BLOCK_RE = re.compile(
    r"""
    (?P<code>^(?P<fence>```|~~~)[^\n]*\n.*?^(?P=fence)[ \t]*$)
  | (?P<formula>^\$\$.*?^\$\$[ \t]*$|\$\$[^\n]*?\$\$)
  | (?P<table><table\b.*?</table>|(?:^\|[^\n]*\|[ \t]*(?:\n|$)){2,})
  | (?P<image>!\[[^\]]*\]\([^)\s]+(?:\s+["'][^"']*["'])?\))
    """,
    re.S | re.M | re.X | re.I,
)


@dataclass(slots=True, frozen=True)
class Block:
    type: BlockType
    text: str


def segment(md: str) -> Iterator[Block]:
    """Generator: không dựng danh sách trung gian, tiết kiệm RAM."""
    pos = 0
    for m in _BLOCK_RE.finditer(md):
        if m.start() > pos:
            yield Block(BlockType.TEXT, md[pos:m.start()])
        yield Block(BlockType(m.lastgroup if m.lastgroup != "fence" else "code"), m.group(0))
        pos = m.end()
    if pos < len(md):
        yield Block(BlockType.TEXT, md[pos:])


def count_types(md: str) -> Counter:
    return Counter(b.type.value for b in segment(md) if b.type is not BlockType.TEXT)