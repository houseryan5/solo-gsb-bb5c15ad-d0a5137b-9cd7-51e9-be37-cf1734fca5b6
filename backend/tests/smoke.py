"""Smoke tests for the alignment pipeline.

Run: python -m backend.tests.smoke   (or python tests/smoke.py from backend/)
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.align import analyze  # noqa: E402
from app.srt import parse_srt  # noqa: E402


def srt_single(text: str, cue_no: int = 1) -> str:
    return (f"{cue_no}\n00:00:01,000 --> 00:00:03,000\n{text}\n")


def cases():
    # (name, srt, manuscript, expected {kind: count})
    yield (
        "pure punctuation/whitespace differences => no issues",
        "我们 坚信，长期主义\r\n终将获得回报！\r\n\r\n"
        "2\r\n00:00:03,000 --> 00:00:05,000\r\nDon't stop.\r\n",
        "我们坚信长期主义，终将获得回报。dont stop",
        {},
    )
    yield (
        "missing word",
        srt_single("我们坚信技术"),
        "我们坚信核心技术",
        {"missing": 1},
    )
    yield (
        "extra word",
        srt_single("the quick brown fox today"),
        "the quick brown fox",
        {"extra": 1},
    )
    yield (
        "substitution",
        srt_single("我们坚信未来"),
        "我们相信未来",
        {"substitution": 1},
    )
    yield (
        "local swap => single reorder",
        srt_single("桌上有茶杯和书本"),
        "桌上有书本和茶杯",
        {"reorder": 1},
    )
    yield (
        "movement across boundary => reorder, no cascade",
        "1\n00:00:01,000 --> 00:00:02,000\n然后我们快速推进\n\n"
        "2\n00:00:02,500 --> 00:00:04,000\n并且完成交付\n",
        "我们快速推进然后并且完成交付",
        {"reorder": 1},
    )
    yield (
        "missing at very start attaches chip to first cue",
        srt_single("世界你好"),
        "你好世界",
        {"reorder": 1},
    )


def main() -> int:
    failures = 0
    for name, srt_text, man, expected in cases():
        res = analyze(parse_srt(srt_text), man)
        got = {k: res["stats"][k] for k in expected}
        ok = got == expected
        if not ok:
            failures += 1
        print(f"[{'PASS' if ok else 'FAIL'}] {name}")
        print(f"       expected={expected} got={got}")
        for iss in res["issues"]:
            print(f"       - {iss['kind_label']}: {iss['title']}")
    print()
    print("ALL PASSED" if failures == 0 else f"{failures} CASE(S) FAILED")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
