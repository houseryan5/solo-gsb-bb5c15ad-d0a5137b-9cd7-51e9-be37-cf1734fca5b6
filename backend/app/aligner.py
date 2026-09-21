"""跨字幕块的词序对齐。

字幕 token 流（所有字幕块拉平成一条序列）与校对稿 token 流做全局对齐：

1. 先用 difflib 找出长匹配块作为"锚点"（对长文本足够快）；
2. 锚点之间的差异区域用 Needleman-Wunsch 动态规划做词级精对齐，
   得分：匹配 +2 / 替换 -1 / 空缺 -2，替换优先于"删+插"组合；
3. 区域过大时退化为整体删除+插入（随后会被归并成一条问题，不影响正确性）。

输出为逐 token 的操作流：eq（一致）/ del（字幕多出）/ ins（字幕缺失）。
"""
from __future__ import annotations

import difflib
from collections import namedtuple

Op = namedtuple('Op', ['kind', 'a', 'b'])  # kind: 'eq' | 'del' | 'ins'

_MATCH = 2
_MISMATCH = -1
_GAP = -2
_NW_MAX_CELLS = 2_000_000  # DP 矩阵规模上限，超出则退化处理


def _nw_align(a: list[str], b: list[str],
              a0: int, a1: int, b0: int, b1: int) -> list[Op]:
    """对 a[a0:a1] 与 b[b0:b1] 做 Needleman-Wunsch 对齐。"""
    n, m = a1 - a0, b1 - b0
    if n == 0:
        return [Op('ins', -1, b0 + j) for j in range(m)]
    if m == 0:
        return [Op('del', a0 + i, -1) for i in range(n)]
    if n * m > _NW_MAX_CELLS:
        return ([Op('del', a0 + i, -1) for i in range(n)]
                + [Op('ins', -1, b0 + j) for j in range(m)])

    # 前行动态规划，tb 记录回溯方向：1=对角 2=上(删) 3=左(插)
    tb = [bytearray(m + 1) for _ in range(n + 1)]
    prev = [0.0] * (m + 1)
    for j in range(1, m + 1):
        prev[j] = prev[j - 1] + _GAP
        tb[0][j] = 3
    for i in range(1, n + 1):
        cur = [prev[0] + _GAP] + [0.0] * m
        row = tb[i]
        row[0] = 2
        ai = a[a0 + i - 1]
        for j in range(1, m + 1):
            diag = prev[j - 1] + (_MATCH if ai == b[b0 + j - 1] else _MISMATCH)
            up = prev[j] + _GAP
            left = cur[j - 1] + _GAP
            if diag >= up and diag >= left:
                cur[j] = diag
                row[j] = 1
            elif up >= left:
                cur[j] = up
                row[j] = 2
            else:
                cur[j] = left
                row[j] = 3
        prev = cur

    # 回溯
    ops: list[Op] = []
    i, j = n, m
    while i > 0 or j > 0:
        d = tb[i][j]
        if i > 0 and j > 0 and d == 1:
            if a[a0 + i - 1] == b[b0 + j - 1]:
                ops.append(Op('eq', a0 + i - 1, b0 + j - 1))
            else:  # 替换：记为相邻的 删+插，后续归并分类
                ops.append(Op('del', a0 + i - 1, -1))
                ops.append(Op('ins', -1, b0 + j - 1))
            i -= 1
            j -= 1
        elif i > 0 and (j == 0 or d == 2):
            ops.append(Op('del', a0 + i - 1, -1))
            i -= 1
        else:
            ops.append(Op('ins', -1, b0 + j - 1))
            j -= 1
    ops.reverse()
    return ops


def align_tokens(a: list[str], b: list[str]) -> list[Op]:
    """对齐两条 token 序列，返回完整操作流。"""
    if not a:
        return [Op('ins', -1, j) for j in range(len(b))]
    if not b:
        return [Op('del', i, -1) for i in range(len(a))]

    sm = difflib.SequenceMatcher(None, a, b, autojunk=False)
    ops: list[Op] = []
    ai = bi = 0
    for blk in sm.get_matching_blocks():  # 末尾自带 (len(a), len(b), 0) 哨兵
        if blk.a > ai or blk.b > bi:
            ops.extend(_nw_align(a, b, ai, blk.a, bi, blk.b))
        for k in range(blk.size):
            ops.append(Op('eq', blk.a + k, blk.b + k))
        ai = blk.a + blk.size
        bi = blk.b + blk.size
    return ops
