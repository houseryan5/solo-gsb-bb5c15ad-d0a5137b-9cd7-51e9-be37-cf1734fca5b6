"""SRT 字幕解析。"""
from __future__ import annotations

import re
from dataclasses import dataclass

_TIME_RE = re.compile(
    r'(\d{1,2}):(\d{2}):(\d{2})[,.](\d{1,3})\s*-->\s*(\d{1,2}):(\d{2}):(\d{2})[,.](\d{1,3})'
)
_TAG_RE = re.compile(r'<[^>]+>')
_ASS_RE = re.compile(r'\{[^}]*\}')


@dataclass
class Cue:
    index: int
    start_ms: int
    end_ms: int
    text: str  # 原文（可能含换行）


def _to_ms(h: str, m: str, s: str, frac: str) -> int:
    frac = (frac + '000')[:3]  # 补齐/截断到毫秒
    return ((int(h) * 60 + int(m)) * 60 + int(s)) * 1000 + int(frac)


def format_ms(ms: int) -> str:
    """毫秒 -> SRT 时间码 HH:MM:SS,mmm"""
    ms = max(0, int(ms))
    h, rem = divmod(ms, 3_600_000)
    m, rem = divmod(rem, 60_000)
    s, milli = divmod(rem, 1000)
    return f'{h:02d}:{m:02d}:{s:02d},{milli:03d}'


def parse_srt(text: str) -> list[Cue]:
    """解析 SRT 文本为字幕块列表，容错处理序号缺失、样式标签等情况。"""
    text = text.replace('\r\n', '\n').replace('\r', '\n')
    cues: list[Cue] = []
    for block in re.split(r'\n\s*\n', text):
        lines = [ln for ln in block.split('\n') if ln.strip()]
        if not lines:
            continue
        ti = next((i for i, ln in enumerate(lines) if _TIME_RE.search(ln)), None)
        if ti is None:
            continue
        m = _TIME_RE.search(lines[ti])
        start = _to_ms(m.group(1), m.group(2), m.group(3), m.group(4))
        end = _to_ms(m.group(5), m.group(6), m.group(7), m.group(8))
        body = '\n'.join(lines[ti + 1:])
        body = _ASS_RE.sub('', _TAG_RE.sub('', body)).strip()
        if body:
            cues.append(Cue(len(cues), start, end, body))
    return cues


def decode_bytes(data: bytes) -> str:
    """按常见编码依次尝试解码上传文件。"""
    for enc in ('utf-8-sig', 'utf-8', 'gb18030', 'big5', 'latin-1'):
        try:
            return data.decode(enc)
        except (UnicodeDecodeError, LookupError):
            continue
    return data.decode('utf-8', errors='replace')
