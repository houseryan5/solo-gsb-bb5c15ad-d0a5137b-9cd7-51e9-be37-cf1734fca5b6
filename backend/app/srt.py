"""SRT subtitle parsing."""
from __future__ import annotations

import re
from dataclasses import dataclass, field

_TIME_RE = re.compile(
    r"(\d{1,2}):(\d{2}):(\d{2})[,.](\d{1,3})\s*-->\s*"
    r"(\d{1,2}):(\d{2}):(\d{2})[,.](\d{1,3})"
)
_TAG_RE = re.compile(r"<[^>]+>")          # <i>, <font ...>, etc.
_BRACE_RE = re.compile(r"\{[^}]*\}")      # {\an8} style overrides


def parse_timecode(h: str, m: str, s: str, ms: str) -> float:
    return int(h) * 3600 + int(m) * 60 + int(s) + int(ms.ljust(3, "0")) / 1000.0


def format_timecode(seconds: float) -> str:
    if seconds < 0:
        seconds = 0.0
    ms = round(seconds * 1000)
    h, rem = divmod(ms, 3600_000)
    m, rem = divmod(rem, 60_000)
    s, ms = divmod(rem, 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


@dataclass
class Cue:
    index: int
    start: float
    end: float
    raw_text: str                # original multi-line text
    norm_text: str = ""          # normalized display text
    token_ids: list[int] = field(default_factory=list)
    # extra/missing chips to render inline: {at_pos, issue_id, kind}
    chips: list[dict] = field(default_factory=list)

    @property
    def start_tc(self) -> str:
        return format_timecode(self.start)

    @property
    def end_tc(self) -> str:
        return format_timecode(self.end)

    def to_dict(self) -> dict:
        return {
            "index": self.index, "start": self.start, "end": self.end,
            "start_tc": self.start_tc, "end_tc": self.end_tc,
            "raw_text": self.raw_text, "norm_text": self.norm_text,
            "token_ids": self.token_ids, "chips": self.chips,
        }


def _clean_text(lines: list[str]) -> str:
    text = "\n".join(lines).strip()
    text = _TAG_RE.sub("", text)
    text = _BRACE_RE.sub("", text)
    return text.strip()


def parse_srt(content: str) -> list[Cue]:
    """Parse SRT content. Tolerates BOM, CRLF and missing cue numbers."""
    content = content.lstrip("﻿").replace("\r\n", "\n").replace("\r", "\n")
    blocks = re.split(r"\n[ \t]*\n", content.strip())
    cues: list[Cue] = []
    seq = 0
    for block in blocks:
        lines = [ln.strip() for ln in block.split("\n") if ln.strip() != ""]
        if not lines:
            continue
        tc_line = 0
        if _TIME_RE.search(lines[0]):
            tc_line = 0
        elif len(lines) > 1 and _TIME_RE.search(lines[1]):
            tc_line = 1
        else:
            continue
        m = _TIME_RE.search(lines[tc_line])
        assert m is not None
        start = parse_timecode(*m.groups()[:4])
        end = parse_timecode(*m.groups()[4:])
        text = _clean_text(lines[tc_line + 1:])
        if not text:
            continue
        seq += 1
        cues.append(Cue(index=seq, start=start, end=end, raw_text=text))
    return cues
