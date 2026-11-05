"""
Aligning the reading stream with the reviewed text, token by token.
"""

try:
    import cydifflib as difflib     # difflib compiled: the same matches, faster
except ImportError:
    import difflib
import re
import unicodedata

import teibuild  # noqa: F401  (puts colophon on sys.path)

from teibuild.settings import NUMERAL_RE  # noqa: E402
from teibuild.state import SPLIT_RE  # noqa: E402


class UF:
    def __init__(self):
        self.p = {}

    def find(self, x):
        self.p.setdefault(x, x)
        while self.p[x] != x:
            self.p[x] = self.p[self.p[x]]
            x = self.p[x]
        return x

    def union(self, a, b):
        self.p[self.find(a)] = self.find(b)


def run_cut_ops(mw, ow, run_lens):
    """Opcodes matching the words of several runs (mw, run after run) with
    one run (ow). When the same word could match in two runs ("in" in a
    deleted epigraph and "IN" opening the paragraph after it), take the
    reading that matches more words at the start of a run; on a tie, the
    first (difflib's own)."""
    starts, k = set(), 0
    for n in run_lens:
        starts.add(k)
        k += n

    def ops_for(a, b):
        return difflib.SequenceMatcher(None, a, b, autojunk=False).get_opcodes()

    def score(ops):
        eq = sum(i2 - i1 for op, i1, i2, _j1, _j2 in ops if op == "equal")
        st = sum(1 for op, i1, _i2, j1, _j2 in ops if op == "equal" and i1 in starts and j1 == 0)
        return eq, st
    fwd = ops_for(mw, ow)
    rev = ops_for(mw[::-1], ow[::-1])
    n, m = len(mw), len(ow)
    rev = [(op, n - i2, n - i1, m - j2, m - j1) for op, i1, i2, j1, j2 in reversed(rev)]
    return rev if score(rev) > score(fwd) else fwd


def split_marks(ops, src, tgt):
    """A changed stretch with block marks on both sides, more on one side
    (a paragraph the review deletes, then a printed "2." it makes an item):
    the surplus marks and what comes before them are a stretch of their
    own, so the rest pairs mark with mark."""
    out = []
    for op, i1, i2, j1, j2 in ops:
        sm_ = [k for k in range(i1, i2) if src[k][1] == "m"]
        rm_ = [k for k in range(j1, j2) if tgt[k][1] == "m"]
        if op == "equal" or not sm_ or not rm_ or len(sm_) == len(rm_):
            out.append((op, i1, i2, j1, j2))
            continue
        if len(sm_) > len(rm_):
            si, ri = sm_[len(sm_) - len(rm_)], rm_[0]
        else:
            si, ri = sm_[0], rm_[len(rm_) - len(sm_)]
        out += [("replace", i1, si, j1, ri), ("replace", si, i2, ri, j2)]
    return out


def numeral_stops(ops, src, tgt):
    """A stop the review adds before a printed numeral it makes a "+" item
    ("husband VIII. The" -> "husband.\n+ The"): difflib pairs the review's
    stop with the numeral's and deletes the numeral. Pair the numeral and
    its stop with the item mark instead (the label), and the review's stop
    is an insertion after the word before."""
    out, k = [], 0
    while k < len(ops):
        if k + 2 < len(ops):
            (o1, a1, a2, b1, b2), (o2, c1, c2, d1, d2), (o3, e1, e2, f1, f2) = ops[k:k + 3]
            if o1 == "delete" and a2 - a1 == 1 and src[a1][1] == "w" and \
                    NUMERAL_RE.fullmatch(src[a1][0]) and \
                    o2 == "equal" and c2 - c1 == 1 and src[c1][0] in ".)" and \
                    o3 == "insert" and tgt[f1][1] == "m" and tgt[f1][0] == "+":
                out += [("insert", a1, a1, d1, d2), ("replace", a1, c2, f1, f2)]
                k += 3
                continue
        out.append(ops[k])
        k += 1
    return out


def punct_after_deletion(ops, src):
    """A deletion that starts with the same mark as the text after it
    ("well . [deleted margin matter] . ¶ Under"): difflib keeps the later
    stop; keep the one after the word before instead, so the stop stays in
    its sentence and the deleted run takes the other."""
    out = list(ops)
    for k in range(1, len(out) - 1):
        p_op, d_op, n_op = out[k - 1], out[k], out[k + 1]
        if p_op[0] != "equal" or d_op[0] != "delete" or n_op[0] != "equal":
            continue
        a1, a2 = d_op[1], d_op[2]
        c1, c2, e1, e2 = n_op[1], n_op[2], n_op[3], n_op[4]
        if src[a1][1] != "w" or re.match(r"\w", src[a1][0]) or src[a1][0] != src[c1][0]:
            continue
        out[k - 1] = ("equal", p_op[1], p_op[2] + 1, p_op[3], p_op[4] + 1)
        out[k] = ("delete", a1 + 1, c1 + 1, e1 + 1, e1 + 1)
        out[k + 1] = ("equal", c1 + 1, c2, e1 + 1, e2) if c2 > c1 + 1 else None
    return [o for o in out if o is not None]


GREEK = re.compile(r"[\u0370-\u03ff\u1f00-\u1fff]")


def align_key(w):
    """A Greek word without its accents and breathings, so that a review
    correcting them (Ὀλικῶς to Ὁλικῶς) still lines up with the word as
    printed; the matched word takes the review's form all the same."""
    if not GREEK.search(w):
        return w
    return "".join(c for c in unicodedata.normalize("NFD", w) if not unicodedata.combining(c))


def align(src, tgt, report, label, owner=None):
    """src: stream entries; tgt: [(text, kind)]. Returns (clusters,
    structure_ops). Each cluster: (list of Tok in order, target text list,
    target indices). If `owner` is a dict it is filled with
    target index -> source Tok that received that target word."""
    a = [align_key(s[0]) for s in src]
    b = [align_key(t[0]) for t in tgt]
    sm = difflib.SequenceMatcher(None, a, b, autojunk=False)
    uf = UF()
    tok_order = []
    seen = set()
    for s in src:
        if s[1] == "w" and id(s[2]) not in seen:
            seen.add(id(s[2]))
            tok_order.append(s[2])
    # target words assigned per source word-token (by id), in order
    tgt_for = {}
    idx_for = {}
    struct = []

    def add_tgt(tok, words, idxs):
        tgt_for.setdefault(id(tok), []).extend(words)
        idx_for.setdefault(id(tok), []).extend(idxs)
        if owner is not None:
            for j in idxs:
                owner[j] = tok

    for op, i1, i2, j1, j2 in split_marks(punct_after_deletion(numeral_stops(sm.get_opcodes(), src, tgt), src), src, tgt):
        S = src[i1:i2]
        R = tgt[j1:j2]
        Sw = [s for s in S if s[1] == "w"]
        Rw = [r[0] for r in R if r[1] == "w"]
        Rwi = [j1 + k for k, r in enumerate(R) if r[1] == "w"]
        Sm = [s for s in S if s[1] == "m"]
        Rm = [r[0] for r in R if r[1] == "m"]
        if op == "equal":
            for k, (s, r) in enumerate(zip(S, R)):
                if s[1] == "w":
                    add_tgt(s[2], [r[0]], [j1 + k])
            continue
        # structure markers
        if Sm or Rm:
            def runs(seq, j0=None):
                out, cur = [], []
                for k, e in enumerate(seq):
                    if e[1] == "m":
                        out.append(cur)
                        cur = []
                    else:
                        cur.append((e, (j0 + k) if j0 is not None else None))
                out.append(cur)
                return out
            s_runs, r_runs = runs(S), runs(R, j1)
            if len(Sm) != len(Rm) and (not Sm or not Rm):
                # breaks on one side only (a paragraph split or merge):
                # cut the other side's words at the matching places
                many, one = (s_runs, r_runs) if Sm else (r_runs, s_runs)
                flat = one[0]
                mw = [e[0].lower() for run in many for e, _ in run]
                ow = [e[0].lower() for e, _ in flat]
                wops = run_cut_ops(mw, ow, [len(run) for run in many])

                def cut(p):
                    for op, a1, a2, b1, b2 in wops:
                        if a1 <= p <= a2:
                            if op == "equal":
                                return b1 + (p - a1)
                            return b1 + round((p - a1) * (b2 - b1) / max(1, a2 - a1))
                    return len(ow)
                cuts, p = [], 0
                for run in many[:-1]:
                    p += len(run)
                    cuts.append(cut(p))
                pieces, last = [], 0
                for c in cuts + [len(flat)]:
                    c = max(c, last)
                    pieces.append(flat[last:c])
                    last = c
                if Sm:
                    r_runs = pieces
                else:
                    s_runs = pieces
            # where the structure change applies: the first source word of
            # the second run
            later = [e for run in s_runs[1:] for e, _ in run]
            nxt = later[0] if later else \
                next((s for s in src[i2:] if s[1] == "w"), None)
            if Sm and not later:
                k = next(k for k, s in enumerate(S) if s[1] == "m")
                nxt = next((s for s in src[i1 + k:] if s[1] == "w"), None)
            struct.append({"src_marks": [s[0] for s in Sm], "tgt_marks": Rm,
                           "at": nxt, "S": S, "R": R, "label": label})
            if len(s_runs) == len(r_runs):
                prev = next((s for s in reversed(src[:i1]) if s[1] == "w"), None)
                for n, (sr, rr) in enumerate(zip(s_runs, r_runs)):
                    # a printed numeral ("1." "II.") the review dropped when
                    # it made the block a "+" item is the item's label, not
                    # a deleted word
                    if n and n - 1 < len(Rm) and Rm[n - 1] == "+" and len(sr) >= 2 and \
                            NUMERAL_RE.fullmatch(sr[0][0][0]) and sr[1][0][0] in ".)" and \
                            not (rr and rr[0][0][0] == sr[0][0][0]):
                        for e, _ in sr[:2]:
                            add_tgt(e[2], [e[0]], [])
                        sr = sr[2:]
                    words = [e[0] for e, _ in rr]
                    idxs = [j for _, j in rr]
                    if sr:
                        toks = [e[2] for e, _ in sr]
                        for t in toks:
                            uf.union(id(t), id(toks[0]))
                        add_tgt(toks[0], words, idxs)
                        for t in toks[1:]:
                            add_tgt(t, [], [])
                        prev = sr[-1][0]
                    elif words:
                        # inserted words: before a break they end the
                        # previous block; after one they begin the next
                        host = prev
                        if n > 0:
                            host = next((e for run in s_runs[n + 1:] for e, _ in run), None) \
                                or next((s for s in src[i2:] if s[1] == "w"), None) or prev
                        if host is not None:
                            add_tgt(host[2], words, idxs)
                            uf.union(id(host[2]), id(host[2]))
                continue
        if Sw:
            for s in Sw:
                uf.union(id(s[2]), id(Sw[0][2]))
            add_tgt(Sw[0][2], Rw, Rwi)
            for s in Sw[1:]:
                add_tgt(s[2], [], [])
            if owner is not None and len(Sw) == len(Rw):
                # as many words on both sides ("mans OVVNE" -> "man's OWN"):
                # each review word is its printed word's, so a note between
                # them is not taken as moved
                for s, j in zip(Sw, Rwi):
                    owner[j] = s[2]
        elif Rw:
            # pure insertion: attach to the previous source word token, or,
            # right after a block opens on both sides ("¶ Obs. 2. Again"),
            # to the block's first word, so it opens that block
            prev = next((s for s in reversed(src[:i1]) if s[1] == "w"), None)
            if i1 and src[i1 - 1][1] == "m" and j1 and tgt[j1 - 1][1] == "m":
                prev = next((s for s in src[i2:] if s[1] == "w"), None) or prev
            if prev is None:
                prev = next((s for s in src[i2:] if s[1] == "w"), None)
            if prev is not None:
                add_tgt(prev[2], Rw, Rwi)
                uf.union(id(prev[2]), id(prev[2]))
                report.append(f"[{label}] insertion after '{prev[0]}': {' '.join(Rw)}")
    # build clusters in reading order
    clusters = {}
    order = []
    for t in tok_order:
        r = uf.find(id(t))
        if r not in clusters:
            clusters[r] = []
            order.append(r)
        clusters[r].append(t)
    result = []
    for r in order:
        ts = clusters[r]
        cur = []
        for t in ts:
            cur.extend(SPLIT_RE.findall(t.reg if t.reg is not None else t.orig or ""))
        new, idxs = [], []
        for t in ts:
            new.extend(tgt_for.get(id(t), []))
            idxs.extend(idx_for.get(id(t), []))
        if cur != new:
            result.append((ts, new, idxs))
    return result, struct
