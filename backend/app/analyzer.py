"""问题识别：把对齐操作流归并为 缺词 / 多词 / 错序 / 错词 四类问题。

关键设计：
- 对齐在"拉平的 token 流"上进行，与字幕块边界、换行完全无关，
  因此换行差异不会引发级联误报；
- 相邻差异之间若只隔着少量相同 token（≤ MERGE_GAP），归并为一处问题——
  一次局部错乱只报一次，且能据此识别"错序"（同一批字词顺序不同）。
"""
from __future__ import annotations

from collections import Counter

from .aligner import Op, align_tokens
from .srt_parser import Cue, format_ms
from .tokenizer import tokenize

#: 两个差异片段之间若只隔着不超过该数量的相同 token，则归并为同一处问题
MERGE_GAP = 3

#: token 数上限，防止超大文件拖垮服务
MAX_TOKENS = 150_000

#: 错序判定：差异两侧共有 token（多重集交集）占比达到该阈值即视为错序
MISORDER_RATIO = 0.5

_CTX = 40  # 校对稿上下文截取的字符数


def _iter_hunks(ops: list[Op]):
    """把操作流切成差异片段，产出 (del_a_indices, ins_b_indices)。"""
    hunks = []
    cur_del: list[int] = []
    cur_ins: list[int] = []
    gap = MERGE_GAP + 1
    for op in ops:
        if op.kind == 'eq':
            gap += 1
            continue
        if (cur_del or cur_ins) and gap > MERGE_GAP:
            hunks.append((cur_del, cur_ins))
            cur_del, cur_ins = [], []
        if op.kind == 'del':
            cur_del.append(op.a)
        else:
            cur_ins.append(op.b)
        gap = 0
    if cur_del or cur_ins:
        hunks.append((cur_del, cur_ins))
    return hunks


def _classify(del_texts: list[str], ins_texts: list[str]) -> str:
    if del_texts and not ins_texts:
        return 'extra'      # 多词：字幕有、校对稿没有
    if ins_texts and not del_texts:
        return 'missing'    # 缺词：校对稿有、字幕没有
    overlap = sum((Counter(del_texts) & Counter(ins_texts)).values())
    if 2 * overlap >= max(len(del_texts), len(ins_texts)):
        return 'misorder'   # 错序：字词基本相同，顺序不同
    return 'replace'        # 错词：字词被替换


def _subtitle_excerpt(cues: list[Cue], cs: int, ce: int) -> str:
    text = ' ⏎ '.join(cues[i].text.replace('\n', ' ') for i in range(cs, ce + 1))
    return text[:160] + ('…' if len(text) > 160 else '')


def build_comparison(cues: list[Cue], script: str) -> dict:
    """主流程：切词 -> 对齐 -> 归并分类 -> 生成带时间码的问题清单。"""
    # ---- 1. 归一化 + 切词（字幕跨块拉平） --------------------------------
    a_tokens: list[str] = []
    a_cue: list[int] = []                 # token -> 字幕块序号
    a_span: list[tuple[int, int]] = []    # token -> 块内字符区间
    for ci, cue in enumerate(cues):
        for tok in tokenize(cue.text):
            a_tokens.append(tok.text)
            a_cue.append(ci)
            a_span.append((tok.start, tok.end))

    script_toks = tokenize(script)
    b_tokens = [t.text for t in script_toks]

    if max(len(a_tokens), len(b_tokens)) > MAX_TOKENS:
        raise ValueError(f'文件过大：token 数超过上限 {MAX_TOKENS}')

    # ---- 2. 词序动态规划对齐 ---------------------------------------------
    ops = align_tokens(a_tokens, b_tokens)

    # 校对稿位置 -> 字幕 token 的映射（仅 eq 点），用于给纯缺词/多词定位
    eq_pairs = [(op.b, op.a) for op in ops if op.kind == 'eq']

    def cue_before(b_pos: int) -> int | None:
        """b_pos 之前最近匹配点所属的字幕块。"""
        lo, hi = 0, len(eq_pairs) - 1
        ans = None
        while lo <= hi:
            mid = (lo + hi) // 2
            if eq_pairs[mid][0] <= b_pos:
                ans = eq_pairs[mid][1]
                lo = mid + 1
            else:
                hi = mid - 1
        return a_cue[ans] if ans is not None else None

    def cue_after(b_pos: int) -> int | None:
        lo, hi = 0, len(eq_pairs) - 1
        ans = None
        while lo <= hi:
            mid = (lo + hi) // 2
            if eq_pairs[mid][0] >= b_pos:
                ans = eq_pairs[mid][1]
                hi = mid - 1
            else:
                lo = mid + 1
        return a_cue[ans] if ans is not None else None

    def script_pos_before(a_pos: int) -> int:
        """字幕 token a_pos 之前最近匹配点在校对稿中的字符偏移（用于纯多词定位）。"""
        best = None
        for op in ops:
            if op.kind == 'eq' and op.a < a_pos:
                best = op.b
            elif op.kind == 'eq' and op.a >= a_pos:
                if best is not None:
                    return script_toks[best].end
                return script_toks[op.b].start
        if best is not None:
            return script_toks[best].end
        return 0

    # ---- 3. 归并差异并分类 ------------------------------------------------
    issues: list[dict] = []
    cue_marks: dict[int, list] = {}
    cue_issues: dict[int, list] = {}
    script_marks: list[dict] = []

    for del_idx, ins_idx in _iter_hunks(ops):
        del_texts = [a_tokens[i] for i in del_idx]
        ins_texts = [b_tokens[j] for j in ins_idx]
        itype = _classify(del_texts, ins_texts)
        iid = len(issues) + 1

        # 时间码与字幕块定位
        if del_idx:
            cs, ce = a_cue[del_idx[0]], a_cue[del_idx[-1]]
            start_ms, end_ms = cues[cs].start_ms, cues[ce].end_ms
            primary = cs
        else:
            # 纯缺词：定位到缺失点前后相邻的字幕块之间
            prev_cue = cue_before(ins_idx[0])
            next_cue = cue_after(ins_idx[0])
            if prev_cue is None and next_cue is None:
                cs = ce = primary = 0
                start_ms = end_ms = 0
            else:
                cs = prev_cue if prev_cue is not None else next_cue
                ce = next_cue if next_cue is not None else prev_cue
                primary = next_cue if next_cue is not None else prev_cue
                start_ms = cues[cs].end_ms if prev_cue is not None else cues[ce].start_ms
                end_ms = cues[ce].start_ms if next_cue is not None else cues[cs].end_ms
                if end_ms < start_ms:  # 缺失点落在同一字幕块内
                    start_ms, end_ms = end_ms, start_ms

        timecode = (format_ms(start_ms) if start_ms == end_ms
                    else f'{format_ms(start_ms)} --> {format_ms(end_ms)}')

        # 校对稿区间与上下文
        if ins_idx:
            ss = script_toks[ins_idx[0]].start
            se = script_toks[ins_idx[-1]].end
        else:
            ss = se = script_pos_before(del_idx[0])
        script_excerpt = ('…' if ss > 0 else '') \
            + script[max(0, ss - _CTX):se + _CTX] \
            + ('…' if se + _CTX < len(script) else '')

        issues.append({
            'id': iid,
            'type': itype,
            'timecode': timecode,
            'start_ms': start_ms,
            'end_ms': end_ms,
            'cue': primary,
            'cue_end': ce,
            'subtitle_tokens': del_texts,
            'script_tokens': ins_texts,
            'subtitle_excerpt': _subtitle_excerpt(cues, cs, ce),
            'script_excerpt': script_excerpt,
            'script_start': ss,
            'script_end': se,
        })

        # 高亮标记
        for i in del_idx:
            cue_marks.setdefault(a_cue[i], []).append(
                {'s': a_span[i][0], 'e': a_span[i][1], 'issue': iid})
        for c in range(cs, ce + 1):
            lst = cue_issues.setdefault(c, [])
            if iid not in lst:
                lst.append(iid)
        if ins_idx:
            for j in ins_idx:
                script_marks.append(
                    {'s': script_toks[j].start, 'e': script_toks[j].end, 'issue': iid})
        else:
            script_marks.append({'s': ss, 'e': se, 'issue': iid})

    stats = {
        'cue_count': len(cues),
        'subtitle_tokens': len(a_tokens),
        'script_tokens': len(b_tokens),
        'total': len(issues),
        'missing': sum(1 for i in issues if i['type'] == 'missing'),
        'extra': sum(1 for i in issues if i['type'] == 'extra'),
        'misorder': sum(1 for i in issues if i['type'] == 'misorder'),
        'replace': sum(1 for i in issues if i['type'] == 'replace'),
    }

    return {
        'cues': [{'i': c.index,
                  'start': format_ms(c.start_ms), 'end': format_ms(c.end_ms),
                  'start_ms': c.start_ms, 'end_ms': c.end_ms,
                  'text': c.text} for c in cues],
        'cue_marks': cue_marks,
        'cue_issues': cue_issues,
        'script': script,
        'script_marks': script_marks,
        'issues': issues,
        'stats': stats,
    }
