"""Export proofreading results as timecoded checklists."""
from __future__ import annotations

import csv
import io

_KIND_ORDER = ["missing", "substitution", "reorder", "extra"]


def _sorted_issues(issues: list[dict]) -> list[dict]:
    order = {k: n for n, k in enumerate(_KIND_ORDER)}
    return sorted(issues, key=lambda d: (
        d.get("start_tc") or "99:99:99,999",
        order.get(d["kind"], 9),
        d["id"],
    ))


def export_csv(issues: list[dict]) -> str:
    """Excel-friendly UTF-8-BOM CSV with SMPTE timecodes."""
    buf = io.StringIO()
    buf.write("﻿")
    w = csv.writer(buf)
    w.writerow(["编号", "类型", "严重度", "开始时间码", "结束时间码",
                "字幕块", "字幕原文", "校对稿内容", "校对稿上下文"])
    for d in _sorted_issues(issues):
        cue = ""
        if d.get("cue_start") is not None:
            cue = (str(d["cue_start"])
                   if d.get("cue_end") == d.get("cue_start")
                   else f"{d['cue_start']}-{d['cue_end']}")
        w.writerow([
            d["id"], d["kind_label"], d["severity"],
            d.get("start_tc") or "", d.get("end_tc") or "", cue,
            d.get("hyp_text") or "", d.get("ref_text") or "",
            d.get("ref_context") or "",
        ])
    return buf.getvalue()


def export_markdown(issues: list[dict]) -> str:
    lines = ["# 字幕核校清单", "",
             f"共 {len(issues)} 处问题。", ""]
    for n, d in enumerate(_sorted_issues(issues), 1):
        tc = ""
        if d.get("start_tc"):
            tc = f"`{d['start_tc']} → {d.get('end_tc') or d['start_tc']}` "
        lines.append(
            f"{n}. **[{d['kind_label']}] {tc}** {d['title']}")
        if d.get("cue_start") is not None:
            lines.append(f"   - 字幕块：{d['cue_start']}")
        if d.get("ref_context"):
            lines.append(f"   - 校对稿上下文：{d['ref_context']}")
        lines.append("")
    return "\n".join(lines)
