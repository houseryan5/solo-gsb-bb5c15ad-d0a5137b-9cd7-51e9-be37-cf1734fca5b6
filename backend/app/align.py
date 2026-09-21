"""Word-order alignment between subtitle stream and proofreading copy.

Strategy
--------
A naive block-by-block diff cascades badly: subtitle cues wrap at
arbitrary screen positions, so a single missing word shifts every
following cue boundary and produces dozens of bogus reports.

Instead we:

1. Normalize punctuation/whitespace and tokenize the *entire* subtitle
   stream across cue boundaries (a cue break is treated exactly like a
   wrapped line).
2. Find long equal anchors with difflib (which is itself an LCS/DP
   matcher) and only run a full Needleman-Wunsch word-order DP **inside
   the regions between anchors**. This gives true substitution and gap
   pairing while staying O(n+m) on nearly-identical texts.
3. Pass over the globally unmatched equal words to detect inversions
   (words that appear on both sides but in crossed positions) and
   report them as reordering instead of paired delete+insert noise.
"""
from __future__ import annotations

from bisect import bisect_left, bisect_right
from dataclasses import dataclass, field
from difflib import SequenceMatcher

from .normalize import Token, tokenize
from .srt import Cue

# Above this many DP cells we fall back to coarse gap alignment inside
# a region (regions are normally tiny because difflib anchors bound them).
_DP_CELL_LIMIT = 300_000
# Closeness window (in tokens) for merging nearby swapped pairs into
# one reordering report.
_REORDER_WINDOW = 6

SEVERITY = {
    "missing": "high",
    "substitution": "high",
    "reorder": "high",
    "extra": "medium",
}
KIND_LABEL = {
    "missing": "缺词",
    "extra": "多词",
    "substitution": "错词",
    "reorder": "错序",
}


@dataclass
class Issue:
    id: str
    kind: str
    hyp_tokens: list[Token] = field(default_factory=list)
    ref_tokens: list[Token] = field(default_factory=list)
    pairs: list[tuple[Token, Token]] = field(default_factory=list)
    cue_index: int | None = None          # chip cue for missing words
    cue_at: int | None = None
    ref_at: int | None = None             # chip position for extra words
    order: int = 0                        # sort key (hyp stream order)

    def to_dict(self, ref_norm: str, cue_by_index: dict[int, Cue]) -> dict:
        kind = self.kind
        hyp_words = join_surfaces(self.hyp_tokens)
        ref_words = join_surfaces(self.ref_tokens)
        cue_ids = sorted({t.cue_idx for t in self.hyp_tokens if t.cue_idx is not None})
        if self.cue_index is not None and self.cue_index not in cue_ids:
            cue_ids = sorted({*cue_ids, self.cue_index})
        cue_start = cue_ids[0] if cue_ids else None
        cue_end = cue_ids[-1] if cue_ids else None
        start_tc = end_tc = None
        if cue_start is not None:
            start_tc = cue_by_index[cue_start].start_tc
            end_tc = cue_by_index[cue_end].end_tc

        if kind == "missing":
            title = f"缺词：{ref_words}"
        elif kind == "extra":
            title = f"多词：{hyp_words}"
        elif kind == "reorder":
            if hyp_words == ref_words:
                title = f"错序：「{hyp_words}」位置移动"
            else:
                title = f"错序片段：{hyp_words}（校对稿顺序 {ref_words}）"
        else:
            if len(self.pairs) <= 1:
                title = f"错词：{hyp_words} → {ref_words}"
            else:
                title = "错词片段：" + " / ".join(
                    f"{h.text}→{r.text}" for h, r in self.pairs
                )

        ref_positions = [p for t in self.ref_tokens for p in (t.start, t.end)]
        ref_span = None
        ref_context = ""
        if ref_positions:
            rs, re_ = min(ref_positions), max(ref_positions)
            ref_span = [rs, re_]
            c0, c1 = max(0, rs - 20), min(len(ref_norm), re_ + 20)
            ref_context = ("…" if c0 > 0 else "") + ref_norm[c0:c1] + (
                "…" if c1 < len(ref_norm) else "")
        elif self.ref_at is not None:
            c0 = max(0, self.ref_at - 20)
            c1 = min(len(ref_norm), self.ref_at + 20)
            ref_context = ("…" if c0 > 0 else "") + ref_norm[c0:c1] + (
                "…" if c1 < len(ref_norm) else "")

        return {
            "id": self.id,
            "kind": kind,
            "kind_label": KIND_LABEL[kind],
            "severity": SEVERITY[kind],
            "title": title,
            "hyp_text": hyp_words,
            "ref_text": ref_words,
            "cue_start": cue_start,
            "cue_end": cue_end,
            "start_tc": start_tc,
            "end_tc": end_tc,
            "hyp_token_ids": [t.id for t in self.hyp_tokens],
            "ref_token_ids": [t.id for t in self.ref_tokens],
            "pairs": [[h.id, r.id] for h, r in self.pairs],
            "ref_span": ref_span,
            "ref_context": ref_context.strip(),
            "cue_chip": (None if self.cue_index is None or self.cue_at is None
                         else {"cue_index": self.cue_index, "at": self.cue_at,
                               "label": ref_words, "issue_id": self.id}),
            "ref_chip": (None if self.ref_at is None
                         else {"at": self.ref_at, "label": hyp_words,
                               "issue_id": self.id}),
        }


# ---------------------------------------------------------------- token utils

def join_surfaces(tokens: list[Token]) -> str:
    """Join surfaces with a space only between two non-CJK neighbors."""
    out = ""
    prev = ""
    for t in tokens:
        if out and _needs_space(prev, t.text):
            out += " "
        out += t.text
        prev = t.text
    return out


def _ascii_word(s: str) -> bool:
    return bool(s) and all(ord(c) < 0x2E80 for c in s)


def _needs_space(a: str, b: str) -> bool:
    return _ascii_word(a[-1:]) and _ascii_word(b[:1])


# ---------------------------------------------------------------- DP core


def _hash_anchors(hk: list[str], rk: list[str], ngram: int = 8,
                  max_occ: int = 2000, diag_slack: int = 40
                  ) -> list[tuple[int, int, int]]:
    """Greedy non-overlapping n-gram anchors (near O(n+m)).

    Even frequent n-grams are usable when they occur at the *same
    stream position* on both sides (typical of repetitive filler in
    identical scripts): a candidate at diagonal offset ``j-i`` is
    accepted while that offset stays within ``diag_slack`` of the
    previously accepted anchor. This makes periodic identical text
    align on the anchor fast path instead of the quadratic fallback.

    Returns (h_start, r_start, length) tuples monotonic on both axes.
    """
    # 64-bit polynomial rolling hash. Every hash hit is verified by
    # direct key comparison before acceptance, so a collision can never
    # produce a wrong anchor; mask arithmetic avoids costly %.
    BASE, MASK = 0x9E3779B1, (1 << 64) - 1
    def codes(keys):
        seed = {}
        out = []
        for k in keys:
            v = seed.get(k)
            if v is None:
                v = (hash(k) & 0xFFFFFFFF) + 1
                seed[k] = v
            out.append(v)
        return out
    hc, rc = codes(hk), codes(rk)
    high = pow(BASE, ngram - 1) & MASK

    def window_map(codes_):
        mp = {}
        if len(codes_) < ngram:
            return mp
        x = 0
        for k in range(ngram):
            x = (x * BASE + codes_[k]) & MASK
        mp.setdefault(x, []).append(0)
        for k in range(ngram, len(codes_)):
            x = ((x - codes_[k - ngram] * high) * BASE + codes_[k]) & MASK
            mp.setdefault(x, []).append(k - ngram + 1)
        return mp

    table = window_map(rc)
    used_h = bytearray(len(hk))
    used_r = bytearray(len(rk))
    hits: list[tuple[int, int]] = []
    prev_diag = 0
    # pass over hyp windows using the rolling recurrence
    x = 0
    for k in range(min(ngram, len(hc))):
        x = (x * BASE + hc[k]) & MASK
    for i in range(len(hc) - ngram + 1):
        if i:
            x = ((x - hc[i - 1] * high) * BASE + hc[i + ngram - 1]) & MASK
        if used_h[i]:
            continue
        js = table.get(x)
        if not js or len(js) > max_occ:
            continue
        best = None
        for j in js:
            # whole window must be free (j only marks the window head)
            if any(used_r[j:j + ngram]):
                continue
            # verify the hash hit, and prefer the running diagonal
            if hk[i:i + ngram] != rk[j:j + ngram]:
                continue
            if abs((j - i) - prev_diag) <= diag_slack:
                if (best is None
                        or abs((j - i) - prev_diag) < abs((best - i) - prev_diag)):
                    best = j
        if best is None:
            continue
        used_h[i:i + ngram] = b"\x01" * ngram
        used_r[best:best + ngram] = b"\x01" * ngram
        hits.append((i, best))
        prev_diag = best - i
    hits.sort()
    # enforce strict monotonicity on the reference axis and extend each
    # anchor with equal single tokens on both sides
    anchors: list[tuple[int, int, int]] = []
    prev_he = prev_re = -1
    for hs0, rs0 in hits:
        if rs0 <= prev_re or hs0 <= prev_he:
            continue
        hs, rs = hs0, rs0
        while hs - 1 > prev_he and rs - 1 > prev_re \
                and hk[hs - 1] == rk[rs - 1]:
            hs -= 1
            rs -= 1
        he, re_ = hs0 + ngram, rs0 + ngram
        while he < len(hk) and re_ < len(rk) and hk[he] == rk[re_]:
            he += 1
            re_ += 1
        anchors.append((hs, rs, he - hs))
        prev_he, prev_re = he, re_
    return anchors


_BAND_WIDTH = 48


def _banded_nw(hk: list[str], rk: list[str], width: int = _BAND_WIDTH):
    """Needleman-Wunsch restricted to |j-i| <= width (rolling rows).

    Proofreading differences are local; the band is what keeps a full
    pass O(n*width) instead of O(n*m) on long repetitive scripts.
    Returns ops using absolute indices into the passed slices.
    """
    n, m = len(hk), len(rk)
    neg = -10**9
    w2 = 2 * width + 1
    prev = [neg] * w2
    prev[width] = 0
    back_rows: list[list[int] | None] = [None] * (n + 1)
    back_rows[0] = [0] * w2
    for i in range(1, n + 1):
        cur = [neg] * w2
        back = [0] * w2
        for j in range(max(1, i - width), min(m, i + width) + 1):
            c = j - i + width
            best, bt = neg, 0
            if c + 1 < w2:  # delete: (i-1, j)
                v = prev[c + 1] - 1
                if v > best:
                    best, bt = v, 1
            if c > 0:       # insert: (i, j-1)
                v = cur[c - 1] - 1
                if v > best:
                    best, bt = v, 2
            v = prev[c] + (2 if hk[i - 1] == rk[j - 1] else -1)  # diagonal
            if v > best:
                best, bt = v, 3
            cur[c] = best
            back[c] = bt
        prev = cur
        back_rows[i] = back
    i, j = n, m
    rev = []
    while i > 0 or j > 0:
        c = j - i + width
        bt = back_rows[i][c] if 0 <= c < w2 else 0
        if bt == 3:
            rev.append(("eq" if hk[i - 1] == rk[j - 1] else "sub", i - 1, j - 1))
            i -= 1
            j -= 1
        elif bt == 1:
            rev.append(("del", i - 1, None))
            i -= 1
        elif bt == 2:
            rev.append(("ins", None, j - 1))
            j -= 1
        else:
            raise ValueError("banded alignment infeasible")
    rev.reverse()
    return rev


def align_tokens(hyp: list[Token], ref: list[Token]):
    """Produce global ops over absolute token indices.

    Hybrid strategy:

    * hash-anchored n-grams pin down the identical bulk of the text in
      O(n+m); the regions between anchors are aligned exactly with
      Needleman-Wunsch when small, or difflib (LCS) when larger;
    * if anchors cover too little (heavily rewritten or highly
      repetitive copy), run one banded Needleman-Wunsch over the whole
      streams — local differences stay inside a narrow band, giving
      O(n*B) even on pathological periodic text where difflib is
      quadratic.

    Returns (eq_pairs, raw_ops); raw_ops is a stream-ordered list of
    (tag, hi_or_None, rj_or_None) covering every token.
    """
    hk = [t.key for t in hyp]
    rk = [t.key for t in ref]
    n, m = len(hk), len(rk)

    def region_ops(i1: int, i2: int, j1: int, j2: int):
        h, r = hk[i1:i2], rk[j1:j2]
        if not h and not r:
            return []
        cells = (len(h) + 1) * (len(r) + 1)
        if cells <= _DP_CELL_LIMIT:
            return _needleman_wunsch_keys(h, r)
        if len(h) * len(r) <= 4_000_000:
            sm = SequenceMatcher(None, h, r, autojunk=False)
            ops = []
            for tag, a1, a2, b1, b2 in sm.get_opcodes():
                if tag == "equal":
                    for k in range(a2 - a1):
                        ops.append(("eq", a1 + k, b1 + k))
                elif tag == "replace":
                    ops.extend(("sub", a1 + k, b1 + k)
                               for k in range(min(a2 - a1, b2 - b1)))
                    for k in range(b2 - b1, a2 - a1):
                        ops.append(("del", a1 + k, None))
                    for k in range(a2 - a1, b2 - b1):
                        ops.append(("ins", None, b1 + k))
                elif tag == "delete":
                    ops.extend(("del", a1 + k, None) for k in range(a2 - a1))
                else:
                    ops.extend(("ins", None, b1 + k) for k in range(b2 - b1))
            return ops
        return ([("del", k, None) for k in range(len(h))]
                + [("ins", None, k) for k in range(len(r))])

    anchors = _hash_anchors(hk, rk)
    covered = sum(L for _, _, L in anchors)
    use_anchors = covered >= 0.5 * min(n, m)
    # A single giant unanchored region means the anchors failed (e.g.
    # periodic text); fall back to the banded global pass instead.
    if use_anchors:
        ends = [(0, 0)] + [(a + L, b + L) for a, b, L in anchors]
        starts = anchors + [(n, m, 0)]
        for (he, re_), (hs, rs, _) in zip(ends, starts):
            if max(hs - he, rs - re_) > 240:
                use_anchors = False
                break

    raw_ops: list[tuple[str, int | None, int | None]] = []
    eq_pairs: list[tuple[int, int]] = []

    if use_anchors:
        cur_h = cur_r = 0
        for a, b, L in anchors:
            for t, ai, bj in region_ops(cur_h, a, cur_r, b):
                raw_ops.append((t, None if ai is None else cur_h + ai,
                                None if bj is None else cur_r + bj))
                if t == "eq":
                    eq_pairs.append((cur_h + ai, cur_r + bj))
            for k in range(L):
                raw_ops.append(("eq", a + k, b + k))
                eq_pairs.append((a + k, b + k))
            cur_h, cur_r = a + L, b + L
        for t, ai, bj in region_ops(cur_h, n, cur_r, m):
            raw_ops.append((t, None if ai is None else cur_h + ai,
                            None if bj is None else cur_r + bj))
            if t == "eq":
                eq_pairs.append((cur_h + ai, cur_r + bj))
    else:
        width = max(_BAND_WIDTH, abs(n - m) + 16)
        for t, ai, bj in _banded_nw(hk, rk, width):
            raw_ops.append((t, ai, bj))
            if t == "eq":
                eq_pairs.append((ai, bj))
    return eq_pairs, raw_ops


def _needleman_wunsch_keys(h: list[str], r: list[str]):
    """Local exact alignment on normalized keys (see align_tokens)."""
    n, m = len(h), len(r)
    MATCH, MISMATCH, GAP = 2, -1, -1
    dp = [[0] * (m + 1) for _ in range(n + 1)]
    for i in range(n + 1):
        dp[i][0] = i * GAP
    for j in range(m + 1):
        dp[0][j] = j * GAP
    for i in range(1, n + 1):
        row, prev = dp[i], dp[i - 1]
        for j in range(1, m + 1):
            row[j] = max(
                prev[j - 1] + (MATCH if h[i - 1] == r[j - 1] else MISMATCH),
                prev[j] + GAP, row[j - 1] + GAP)
    i, j = n, m
    rev = []
    while i > 0 or j > 0:
        if i > 0 and j > 0 and dp[i][j] == dp[i - 1][j - 1] + (
                MATCH if h[i - 1] == r[j - 1] else MISMATCH):
            rev.append(("eq" if h[i - 1] == r[j - 1] else "sub", i - 1, j - 1))
            i -= 1
            j -= 1
        elif i > 0 and (j == 0 or dp[i][j] == dp[i - 1][j] + GAP):
            rev.append(("del", i - 1, None))
            i -= 1
        else:
            rev.append(("ins", None, j - 1))
            j -= 1
    rev.reverse()
    return rev


# ---------------------------------------------------------------- reordering

def _find_reorderings(
    del_pos: list[int], ins_pos: list[int],
    hyp: list[Token], ref: list[Token],
    eq_pairs: list[tuple[int, int]],
) -> list[list[tuple[int, int]]]:
    """Find equal-keyed unmatched pairs whose positions are inverted.

    A pair (a in hyp, b in ref) is "crossed" when it moves past a matched
    anchor or past another equal-keyed unmatched pair. Crossed pairs are
    clustered by proximity into reordering groups.
    """
    del_by_key: dict[str, list[int]] = {}
    ins_by_key: dict[str, list[int]] = {}
    for i in del_pos:
        del_by_key.setdefault(hyp[i].key, []).append(i)
    for j in ins_pos:
        ins_by_key.setdefault(ref[j].key, []).append(j)

    candidates: list[tuple[int, int]] = []
    for key, di in del_by_key.items():
        rj = ins_by_key.get(key)
        if not rj:
            continue
        for a, b in zip(sorted(di), sorted(rj)):
            candidates.append((a, b))
    if not candidates:
        return []

    # Anchor arrays with prefix-max / suffix-min so each crossing test
    # stays O(log n) instead of slicing O(n) lists per candidate.
    anchors = sorted(eq_pairs)
    ax = [a for a, _ in anchors]
    ay = [b for _, b in anchors]
    pref_max: list[int] = []
    for v in ay:
        pref_max.append(v if not pref_max else max(pref_max[-1], v))
    suff_min = [0] * len(ay)
    for k in range(len(ay) - 1, -1, -1):
        v = ay[k]
        suff_min[k] = v if k == len(ay) - 1 else min(suff_min[k + 1], v)

    def crosses_anchor(a: int, b: int) -> bool:
        # anchor left of a but right of b?
        k = bisect_right(ax, a - 1)
        if k > 0 and pref_max[k - 1] > b:
            return True
        # anchor right of a but left of b?
        k = bisect_right(ax, a)
        if k < len(ay) and suff_min[k] < b:
            return True
        return False

    # A pair crossing an equal anchor has definitely moved. Plain
    # swaps between two unmatched pairs (A B -> B A) are detected with
    # a single ordered sweep (prefix-max / suffix-min), i.e. O(k log k).
    crossed = [crosses_anchor(a, b) for a, b in candidates]
    order = sorted(range(len(candidates)), key=lambda n: candidates[n][0])
    run_max = -1
    for n in order:
        b = candidates[n][1]
        if run_max > b:
            crossed[n] = True
        run_max = max(run_max, b)
    run_min = 10**18
    for n in reversed(order):
        b = candidates[n][1]
        if run_min < b:
            crossed[n] = True
        run_min = min(run_min, b)

    moved = sorted(candidates[n] for n in range(len(candidates)) if crossed[n])
    # cluster nearby pairs into one report
    groups: list[list[tuple[int, int]]] = []
    for pair in moved:
        a, b = pair
        if groups:
            ga, gb = groups[-1][-1]
            if abs(a - ga) <= _REORDER_WINDOW and abs(b - gb) <= _REORDER_WINDOW:
                groups[-1].append(pair)
                continue
        groups.append([pair])
    return groups


# ---------------------------------------------------------------- main flow

def analyze(cues: list[Cue], manuscript: str) -> dict:
    """Run the whole proofreading pipeline."""
    idc = [0]
    hyp: list[Token] = []
    for cue in cues:
        toks, norm = tokenize(cue.raw_text, cue_idx=cue.index, id_counter=idc)
        cue.norm_text = norm
        cue.token_ids = [t.id for t in toks]
        cue.chips = []
        hyp.extend(toks)
    ref, ref_norm = tokenize(manuscript, id_counter=idc)

    eq_pairs, raw_ops = align_tokens(hyp, ref)
    matched_h = {a: b for a, b in eq_pairs}
    matched_r = {b: a for a, b in eq_pairs}

    del_pos = sorted(i for _, i, j in raw_ops if i is not None and j is None)
    ins_pos = sorted(j for _, i, j in raw_ops if j is not None and i is None)
    reordered_h: set[int] = set()
    reordered_r: set[int] = set()
    reorder_groups = _find_reorderings(del_pos, ins_pos, hyp, ref, eq_pairs)

    issues: list[Issue] = []
    seq = 0

    def new_issue(kind: str, **kw) -> Issue:
        nonlocal seq
        seq += 1
        iss = Issue(id=f"I{seq:03d}", kind=kind, order=seq, **kw)
        issues.append(iss)
        return iss

    # --- reordering issues
    for group in reorder_groups:
        hs = [hyp[a] for a, _ in group]
        rs = [ref[b] for _, b in sorted(group, key=lambda q: q[1])]
        new_issue("reorder", hyp_tokens=hs, ref_tokens=rs,
                  pairs=list(zip(hs, rs)))
        reordered_h.update(a for a, _ in group)
        reordered_r.update(b for _, b in group)

    # --- walk ops, grouping contiguous sub/del/ins runs. Token ids are
    # globally unique, so map id -> stream position via sorted id lists.
    hyp_ids = [t.id for t in hyp]
    ref_ids = [t.id for t in ref]

    def hpos(t: Token) -> int:
        return bisect_left(hyp_ids, t.id)

    def rpos(t: Token) -> int:
        return bisect_left(ref_ids, t.id)

    run: list[tuple[str, int | None, int | None]] = []

    def flush(run_ops, start: int, end: int):
        if not run_ops:
            return
        tags = {t for t, _, _ in run_ops}
        if tags <= {"eq"}:
            return
        hs = [hyp[i] for t, i, _ in run_ops if i is not None]
        rs = [ref[j] for _, _, j in run_ops if j is not None]
        pairs = [(hyp[i], ref[j]) for t, i, j in run_ops if t == "sub"]
        # tokens already consumed by reordering reports are excluded
        hs = [t for t in hs if hpos(t) not in reordered_h]
        rs = [t for t in rs if rpos(t) not in reordered_r]
        pairs = [(h, r) for h, r in pairs
                 if hpos(h) not in reordered_h
                 and rpos(r) not in reordered_r]
        # anchors OUTSIDE the run (pure insert/delete runs have no
        # boundary token on their own side)
        prev_h = next((i for k in range(start - 1, -1, -1)
                       if (i := raw_ops[k][1]) is not None), None)
        next_h = next((i for k in range(end, len(raw_ops))
                       if (i := raw_ops[k][1]) is not None), None)
        prev_r = next((j for k in range(start - 1, -1, -1)
                       if (j := raw_ops[k][2]) is not None), None)
        next_r = next((j for k in range(end, len(raw_ops))
                       if (j := raw_ops[k][2]) is not None), None)
        if pairs:
            new_issue("substitution",
                      hyp_tokens=[h for h, _ in pairs],
                      ref_tokens=[r for _, r in pairs], pairs=pairs)
            used_h = {h.id for h, _ in pairs}
            used_r = {r.id for _, r in pairs}
            hs = [t for t in hs if t.id not in used_h]
            rs = [t for t in rs if t.id not in used_r]
        if hs:
            iss = new_issue("extra", hyp_tokens=hs)
            iss.ref_at = _ref_insert_at(prev_r, next_r, ref)
        if rs:
            iss = new_issue("missing", ref_tokens=rs)
            iss.cue_index, iss.cue_at = _hyp_insert_at(
                prev_h, next_h, hyp, cues)

    run_start = 0
    for k, op in enumerate(raw_ops):
        if op[0] == "eq":
            flush(run, run_start, k)
            run = []
            run_start = k + 1
        else:
            if not run:
                run_start = k
            run.append(op)
    flush(run, run_start, len(raw_ops))

    # attach chips to cues / ref payload
    cue_by_index = {c.index: c for c in cues}
    ref_chips: list[dict] = []
    issue_dicts = []
    for iss in sorted(issues, key=lambda x: x.order):
        d = iss.to_dict(ref_norm, cue_by_index)
        issue_dicts.append(d)
        if d["cue_chip"]:
            cue_by_index[d["cue_chip"]["cue_index"]].chips.append(d["cue_chip"])
        if d["ref_chip"]:
            chip = d["ref_chip"]
            ref_chips.append({"at": chip["at"], "label": chip["label"],
                              "issue_id": chip["issue_id"]})

    # sort chips by descending offset so zero-width insertion never shifts
    # earlier offsets during rendering
    for c in cues:
        c.chips.sort(key=lambda ch: ch["at"], reverse=True)
    ref_chips.sort(key=lambda ch: ch["at"], reverse=True)

    stats = {k: sum(1 for d in issue_dicts if d["kind"] == k)
             for k in KIND_LABEL}
    stats["total"] = len(issue_dicts)
    # per-cue linkage range into the reference
    cue_ref_spans = _cue_ref_spans(cues, hyp, ref, matched_h, ref_norm)

    return {
        "issues": issue_dicts,
        "stats": stats,
        "cues": [c.to_dict() for c in cues],
        "hyp_tokens": [t.to_dict() for t in hyp],
        "ref": {"norm_text": ref_norm,
                "tokens": [t.to_dict() for t in ref],
                "chips": ref_chips},
        "cue_ref_spans": cue_ref_spans,
        "counts": {"cues": len(cues), "hyp_words": len(hyp),
                   "ref_words": len(ref)},
    }


def _hyp_insert_at(prev_h: int | None, next_h: int | None,
                   hyp: list[Token], cues: list[Cue]
                   ) -> tuple[int | None, int | None]:
    """Locate (cue_index, char_offset_in_cue_norm) for a missing chip."""
    if prev_h is not None:
        anchor = hyp[prev_h]
        return anchor.cue_idx, anchor.end
    if next_h is not None:
        anchor = hyp[next_h]
        return anchor.cue_idx, 0
    return (cues[0].index, 0) if cues else (None, None)


def _ref_insert_at(prev_r: int | None, next_r: int | None,
                   ref: list[Token]) -> int:
    """Char offset into normalized ref text for an extra-word chip."""
    if prev_r is not None:
        return ref[prev_r].end
    if next_r is not None:
        return ref[next_r].start
    return 0


def _cue_ref_spans(cues, hyp, ref, matched_h, ref_norm):
    """Approx. reference char span each cue is linked to (for scrolling)."""
    spans = {}
    by_cue: dict[int, list[int]] = {}
    for i, t in enumerate(hyp):
        if i in matched_h:
            by_cue.setdefault(t.cue_idx, []).append(matched_h[i])
    for cue in cues:
        js = by_cue.get(cue.index, [])
        if js:
            s = min(ref[j].start for j in js)
            e = max(ref[j].end for j in js)
        else:
            s = e = 0
        spans[str(cue.index)] = [s, e]
    return spans
