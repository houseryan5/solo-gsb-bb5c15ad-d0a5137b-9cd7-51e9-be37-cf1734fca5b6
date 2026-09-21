"""Text normalization and tokenization.

The goal of normalization is to make alignment robust to purely
cosmetic differences: punctuation variants, full/half width glyphs
and whitespace (including line breaks between subtitle blocks) must
never trigger false alarms.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

# Curly quotes / dashes are folded to plain ASCII before punctuation
# stripping. All other punctuation carries no lexical value for
# proofreading and is removed.
_QUOTE_MAP = {
    "「": '"', "」": '"', "『": '"', "』": '"',
    "“": '"', "”": '"', "„": '"',
    "‘": "'", "’": "'", "‚": "'", "‛": "'",
    "—": "-", "–": "-", "―": "-", "…": "...",
}

# Latin/digit run; apostrophes/hyphens *inside* words are deleted by
# normalize_text first, so "don't" -> "dont", "co-operate" -> "cooperate".
_LATIN_RUN = re.compile(r"[A-Za-z0-9]+")
# Any non-space, non-punctuation run (covers CJK ideographs).
_OTHER_RUN = re.compile(
    r"[^0-9A-Za-z\s\.,!?;:\"'()\[\]{}<>/\\|`~@#$%^&*_+\-="
    r"，。！？；：、（）《》【】·•…]+",
)

# Ranges treated as "CJK ideographs": each character becomes one token.
_CJK_RANGES = (
    (0x3400, 0x4DBF),    # CJK Ext A
    (0x4E00, 0x9FFF),    # CJK Unified
    (0xF900, 0xFAFF),    # Compatibility Ideographs
    (0x20000, 0x2A6DF),  # Ext B
    (0x2A700, 0x2EBEF),  # Ext C-F
)


# Apostrophe/hyphen between word characters (handles don't, it's,
# co-operate, well-known — the connector is simply deleted).
_INNER_PUNCT = re.compile(r"(?<=\w)['’\-](?=\w)")


def normalize_text(text: str) -> str:
    """NFKC, quote/dash folding, punctuation removal, whitespace collapse.

    Word-internal apostrophes/hyphens are deleted (don't -> dont); other
    punctuation becomes a single space. Newlines collapse to spaces
    *within a stream*; the SRT parser joins cues separately, so a cue
    boundary behaves exactly like a line wrap — the aligner can
    therefore ignore wrapping.
    """
    text = unicodedata.normalize("NFKC", text)
    for src, dst in _QUOTE_MAP.items():
        text = text.replace(src, dst)
    text = _INNER_PUNCT.sub("", text)
    out: list[str] = []
    for ch in text:
        if ch.isspace():
            out.append(" ")
        else:
            cat = unicodedata.category(ch)
            out.append(" " if cat.startswith("P") or cat.startswith("S") else ch)
    return re.sub(r" +", " ", "".join(out)).strip()


def _is_cjk(ch: str) -> bool:
    cp = ord(ch)
    return any(lo <= cp <= hi for lo, hi in _CJK_RANGES)


@dataclass
class Token:
    id: int
    text: str          # original surface form
    key: str           # casefolded normalized key used for matching
    start: int         # char offset into normalized display string
    end: int
    cue_idx: int | None = None  # set for subtitle tokens

    def to_dict(self) -> dict:
        return {"id": self.id, "text": self.text, "start": self.start,
                "end": self.end, "cue_idx": self.cue_idx}


def _find_runs(norm: str) -> list[tuple[str, int, int]]:
    runs: list[tuple[str, int, int]] = []
    occupied = [False] * len(norm)
    for rx in (_LATIN_RUN, _OTHER_RUN):
        for m in rx.finditer(norm):
            s, e = m.span()
            if any(occupied[s:e]):
                continue
            for i in range(s, e):
                occupied[i] = True
            word = norm[s:e]
            if any(_is_cjk(c) for c in word):
                # one token per ideograph (non-CJK chars here are rare)
                for i, ch in enumerate(word):
                    runs.append((ch, s + i, s + i + 1))
            else:
                runs.append((word, s, e))
    runs.sort(key=lambda r: r[1])
    return runs


def tokenize(text: str, cue_idx: int | None = None,
             id_counter: list[int] | None = None) -> tuple[list[Token], str]:
    """Tokenize raw text. Returns (tokens, normalized_display_text).

    Latin/digit runs become one token each; each CJK ideograph becomes
    its own token. Token offsets index into the normalized display string
    so the frontend can slice exact spans.
    """
    norm = normalize_text(text)
    if id_counter is None:
        id_counter = [0]
    tokens: list[Token] = []
    for surface, s, e in _find_runs(norm):
        tokens.append(Token(
            id=id_counter[0], text=surface, key=surface.casefold(),
            start=s, end=e, cue_idx=cue_idx,
        ))
        id_counter[0] += 1
    return tokens, norm
