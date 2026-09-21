"""文本归一化与切词。

归一化策略（在切词前完成，从源头消除"伪差异"）：
- 全角字符转半角（逐字符 NFKC）；
- 拉丁字母统一小写；
- 丢弃所有标点、符号与空白（含换行）——因此字幕换行、标点习惯、
  空白差异完全不会进入对齐阶段，避免由此产生的级联误报。

切词规则：
- CJK 字符逐字成词；
- 连续的拉丁字母 / 数字累积为一个词。

每个 token 保留其在**原文**中的字符区间，便于前端回显上下文与高亮。
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

_CJK_RE = re.compile(r'[㐀-䶿一-鿿豈-﫿]')


@dataclass
class Token:
    text: str   # 归一化后的 token 文本
    start: int  # 在原文中的起始偏移
    end: int    # 在原文中的结束偏移（开区间）


def _normalize_char(ch: str) -> str | None:
    """把单个字符映射为归一化形式；返回 None 表示丢弃（标点/符号/空白）。"""
    if ch.isspace():
        return None
    ch = unicodedata.normalize('NFKC', ch)  # 全角 -> 半角
    out = []
    for c in ch.lower():
        if c.isspace():
            continue
        cat = unicodedata.category(c)
        if cat.startswith('P') or cat.startswith('S'):  # 标点 / 符号
            continue
        out.append(c)
    return ''.join(out) or None


def tokenize(text: str) -> list[Token]:
    """把文本切成 token 序列，标点与空白被忽略。"""
    tokens: list[Token] = []
    i, n = 0, len(text)
    while i < n:
        ch = text[i]
        norm = _normalize_char(ch)
        if norm is None:
            i += 1
            continue
        if _CJK_RE.match(ch):
            tokens.append(Token(norm, i, i + 1))
            i += 1
            continue
        # 拉丁字母 / 数字：累积成一个词
        j = i
        buf = []
        while j < n:
            c = text[j]
            cn = _normalize_char(c)
            if cn is None or _CJK_RE.match(c):
                break
            buf.append(cn)
            j += 1
        tokens.append(Token(''.join(buf), i, j))
        i = j
    return tokens
