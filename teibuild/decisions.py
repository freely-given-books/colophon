"""
Applying the review's decisions (#editor) to the tokens they cover.
"""

try:
    import cydifflib as difflib     # difflib compiled: the same matches, faster
except ImportError:
    import difflib
import re
import unicodedata

import teibuild  # noqa: F401  (puts colophon on sys.path)

from teitok import Tok, local  # noqa: E402
from spelling import modernize_word_lower, apply_case_pattern  # noqa: E402

from teibuild import settings as S  # noqa: E402
from teibuild.settings import ROMAN_RE  # noqa: E402
from teibuild.words import NO_SPACE_AFTER, NO_SPACE_BEFORE, piece_text, word_strings  # noqa: E402
from teibuild.tokens import contains, in_container  # noqa: E402
from teibuild.state import SPLIT_RE  # noqa: E402


def join_tokens(ts):
    out = ""
    for t in ts:
        if not out:
            out = t
        elif t[:1] in NO_SPACE_BEFORE or out[-1:] in NO_SPACE_AFTER \
                or unicodedata.category(t[:1]).startswith("M"):
            out += t
        else:
            out += " " + t
    return out


# Grammatical archaisms: modernizing them (thou -> you, hath -> has) is a
# change of word, not of spelling, but common enough to get its own type so
# that real rewordings stay easy to find.
ARCHAIC = {"thou", "thee", "thy", "thine", "ye", "hath", "doth", "hast", "dost",
           "art", "shalt", "wilt", "saith", "unto", "wast", "wert"}


ARCHAIC_ENDING = re.compile(r"(eth|est|'st)$")


# Pairs rather than words: "be" -> "bee" is a spelling fix (Bee-hive).
ARCHAIC_PAIRS = {("be", "is"), ("be", "are"), ("be", "am"), ("an", "a")}


def classify(old, new):
    """reg/@type of a single-token editor change: case, spelling (the same
    word spelled differently), grammar (an archaic form modernized) or
    emendation (another word, a word removed or added, a changed number)."""
    if old.lower() == new.lower():
        return "case"
    if " " in new or " " in old or not old.strip() or not new.strip():
        return "emendation"
    a, b = old.lower(), new.lower()
    if re.sub(r"\D", "", a) != re.sub(r"\D", "", b):
        return "emendation"                    # citation numbers
    if a in ARCHAIC or (a, b) in ARCHAIC_PAIRS or (ARCHAIC_ENDING.search(a) and
                        difflib.SequenceMatcher(None, a, b).ratio() >= 0.5):
        return "grammar"
    if difflib.SequenceMatcher(None, a, b).ratio() < 0.6:
        return "emendation"
    return "spelling"


def recompute_word(t):
    word_strings(t)
    # expanded with editor gap fills
    parts = []
    for p in t.pieces:
        if not isinstance(p, (str, tuple)) and local(p) == "gap":
            idx = next(i for i, e in t.gaps if e is p)
            if idx in t.extra.get("gapfill", {}):
                parts.append(t.extra["gapfill"][idx][0])
                continue
        parts.append(piece_text(p, t, "exp"))
    t.expanded = "".join(parts)


def try_gapfill(t, target):
    """If a word containing illegible <gap>s was filled in by the editor,
    work out the letters that go in the gap."""
    if len(t.gaps) != 1:
        return False
    idx, gap = t.gaps[0]
    pre, post, seen = "", "", False
    for p in t.pieces:
        if p is gap:
            seen = True
            continue
        s = piece_text(p, t, "exp")
        if seen:
            post += s
        else:
            pre += s
    if target.startswith(pre) and target.endswith(post) and \
            len(target) >= len(pre) + len(post):
        letters = target[len(pre):len(target) - len(post)] if post else target[len(pre):]
        t.extra.setdefault("gapfill", {})[idx] = (
            letters, "high", "filled in by the editor from the page image", "#editor")
        recompute_word(t)
        return True
    return False


def try_macron_flip(t, target):
    """The editor corrected an n/m macron expansion (e.g. 'fron' -> 'from')."""
    for i, (idx, g) in enumerate(t.macrons):
        was_m = idx in S.MACRON_M
        letter = "n" if was_m else "m"
        parts = []
        for p in t.pieces:
            if p is g:
                parts.append(letter)
            else:
                parts.append(piece_text(p, t, "exp"))
        cand = "".join(parts)
        low = cand.lower()
        auto = apply_case_pattern(cand, modernize_word_lower(low))
        if target.lower() in (cand.lower(), auto.lower()):
            t.extra["expan"] = cand
            t.extra["expan_resp"] = "#editor"
            t.expanded = cand
            return True
    return False


def apply_to_token(t, target, log, label):
    if t.kind == "word" and "auto_reg" not in t.extra:
        t.extra["auto_reg"] = t.reg
    if t.kind == "punct":
        log.append((label, "punctuation", t.orig, target))
        t.reg, t.resp, t.rtype = target, "#editor", "punctuation"
        return
    old = t.reg
    if t.gaps and try_gapfill(t, target):
        log.append((label, "gap", old, target))
        t.reg, t.resp, t.rtype = target, "#editor", "spelling"
        return
    if t.macrons and try_macron_flip(t, target):
        log.append((label, "expansion", old, target))
        t.reg, t.resp, t.rtype = target, "#editor", "spelling"
        return
    t.reg, t.resp, t.rtype = target, "#editor", classify(old or "", target)
    log.append((label, t.rtype, old, target))


def join_sp(words, sps=None):
    """Join review words with the spacing the review had (sps[k]: space
    before word k), or by punctuation rules when that is unknown."""
    if sps is None:
        return join_tokens(words)
    out = ""
    for k, w in enumerate(words):
        out += (" " if k and sps[k] else "") + w
    return out


def apply_clusters(clusters, log, unresolved, label, placed=None, flag_of=None,
                   sp_of=None):
    """placed: target index -> [note elements] that the review puts after
    that target word. flag_of(j) / sp_of(j): the review's italic flag and
    space-before for target word j. A token (or group) that takes review
    words keeps them (extra["reg_words"], ["reg_sp"], ["reg_inner"],
    ["tflags"]) so its <reg> can be rebuilt with spacing, italics and notes."""
    placed = placed or {}

    def mark(t, js):
        if flag_of is not None:
            t.extra["tflags"] = [(j, flag_of(j)) for j in js]
        t.extra["tidx"] = list(js)

    def keep(t, words, js, inner):
        t.extra["reg_words"] = list(words)
        t.extra["reg_sp"] = [sp_of(j) for j in js] if sp_of else None
        if inner:
            t.extra["reg_inner"] = inner

    def joined(words, js):
        return join_sp(words, [sp_of(j) for j in js] if sp_of else None)

    for ts, new, idxs in clusters:
        inner = {k: placed[j] for k, j in enumerate(idxs) if j in placed}
        if any(in_container(t, ("trailer",)) for t in ts):
            continue
        # roman list labels are handled as structure (not in a note: there
        # "v." is a verse, "Prov. 13. 20. v."; nor in a plain paragraph:
        # Goold's "II." the edition moves into a heading is a deleted word)
        if len(ts) == 2 and not new and ts[0].kind == "word" and \
                ROMAN_RE.match(ts[0].expanded or "") and ts[1].orig == "." and \
                not in_container(ts[0], ("note",)) and \
                in_container(ts[0], ("label", "item", "list")):
            continue
        parts = [SPLIT_RE.findall(t.reg if t.reg is not None else t.orig or "") for t in ts]
        if len(ts) == 1:
            apply_to_token(ts[0], joined(new, idxs), log, label)
            mark(ts[0], idxs)
            keep(ts[0], new, idxs, inner)
            continue
        if all(len(p) == 1 for p in parts) and len(new) == len(ts):
            for k, (t, n) in enumerate(zip(ts, new)):
                if [n] != SPLIT_RE.findall(t.reg or t.orig or ""):
                    apply_to_token(t, n, log, label)
                mark(t, [idxs[k]])
                if k in inner:
                    t.extra["notes_after"] = inner[k]
            continue
        # several source tokens -> one emendation spanning them
        par = ts[0].parent
        sibs = par.children if par is not None else None
        if sibs is None or any(t.parent is not par for t in ts):
            # the tokens sit in different elements (e.g. an italic name and
            # a roman 's): share the reviewed text out over them instead
            if distribute(ts, new, log, label, idxs, mark, joined(new, idxs)):
                continue
            unresolved.append((label, " ".join(t.reg or t.orig for t in ts), join_tokens(new)))
            continue
        i0, i1 = ts[0].idx, ts[-1].idx
        span = sibs[i0:i1 + 1]
        g = Tok("group")
        g.children = span
        g.reg = joined(new, idxs)
        mark(g, idxs)
        keep(g, new, idxs, inner)
        g.resp, g.rtype = "#editor", "emendation"
        g.parent = par
        g.orig = "".join(x.orig or "".join(p for p in x.pieces if isinstance(p, str))
                         for x in span)
        sibs[i0:i1 + 1] = [g]
        for k, x in enumerate(sibs):
            x.idx = k
        log.append((label, "emendation", " ".join(t.reg or t.orig for t in ts), g.reg))


def space_between(a, b, limit=60):
    """Whether a space token stands between word tokens a and b (b after a in
    document order), looking at most `limit` tokens ahead."""
    t = a
    for _ in range(limit):
        while t.parent is not None and t.idx is not None and \
                t.idx == len(t.parent.children) - 1:
            t = t.parent
        if t.parent is None or t.idx is None:
            return False
        t = t.parent.children[t.idx + 1]
        while t.kind in ("container", "group") and t.children:
            if contains(t, b) and t.kind == "group":
                return False
            t = t.children[0]
        if t is b:
            return False
        if t.kind == "space":
            return True
    return False


def distribute(ts, new, log, label, idxs=None, mark=None, tgt=None):
    """Cut the reviewed text into one piece per source token, by aligning
    characters, and apply each piece to its token."""
    cur = [(t.reg if t.reg is not None else t.orig or "") for t in ts]
    src = "".join(cur)
    tgt = tgt if tgt is not None else join_tokens(new)
    tgt_ns = tgt.replace(" ", "")
    sm = difflib.SequenceMatcher(None, src.lower(), tgt_ns.lower(), autojunk=False)
    ops = sm.get_opcodes()

    def mp(i):
        for op, i1, i2, j1, j2 in ops:
            if i1 <= i <= i2:
                if op == "equal":
                    return j1 + (i - i1)
                return j2 if i == i2 else j1
        return len(tgt_ns)
    bounds, pos = [], 0
    for c in cur:
        pos += len(c)
        bounds.append(mp(pos))
    bounds[-1] = len(tgt_ns)
    # map no-space offsets back into tgt (with spaces)
    ns_to_full = [ci for ci, ch in enumerate(tgt) if ch != " "] + [len(tgt)]
    # a cut just after a word's leading punctuation ("'I", "(of") moves to
    # before it: the mark opens the next token's word, and the space printed
    # between the two tokens stays in front of it
    for k in range(len(bounds) - 1):
        b = bounds[k]
        w = ns_to_full[b] if b < len(ns_to_full) else len(tgt)
        a = w
        while a > 0 and tgt[a - 1] != " " and not tgt[a - 1].isalnum():
            a -= 1
        if a < w and (a == 0 or tgt[a - 1] == " ") and w < len(tgt) and tgt[w].isalnum():
            bounds[k] = max(ns_to_full.index(a), bounds[k - 1] if k else 0)
    # a cut inside a word, between tokens printed with a space between them,
    # moves to the nearer end of that word (else the space splits the word:
    # "Revela t ion")
    for k in range(len(bounds) - 1):
        w = ns_to_full[bounds[k]] if bounds[k] < len(ns_to_full) else len(tgt)
        if not (0 < w < len(tgt) and tgt[w - 1] != " " and tgt[w] != " ") or \
                not space_between(ts[k], ts[k + 1]):
            continue
        a, z = w, w
        while a > 0 and tgt[a - 1] != " ":
            a -= 1
        while z < len(tgt) and tgt[z] != " ":
            z += 1
        to = a if w - a <= z - w else z
        b = len(tgt[:to].replace(" ", ""))       # as an offset without spaces
        bounds[k] = max(b, bounds[k - 1] if k else 0)
    for k in range(1, len(bounds)):
        bounds[k] = max(bounds[k], bounds[k - 1])
    start = 0
    pieces = []
    for b in bounds:
        b = max(b, start)
        pieces.append(tgt[ns_to_full[start]:ns_to_full[b]].strip() if start < len(ns_to_full) else "")
        start = b
    for k, (t, piece) in enumerate(zip(ts, pieces)):
        if piece != (t.reg if t.reg is not None else t.orig or ""):
            apply_to_token(t, piece, log, label)
        # a piece that begins inside a review word: no space goes before it
        w = ns_to_full[bounds[k - 1]] if k and bounds[k - 1] < len(ns_to_full) else None
        if w is not None and 0 < w < len(tgt) and tgt[w - 1] != " " and tgt[w] != " ":
            t.extra["midword"] = True
    if mark is not None and idxs:
        # each review word goes to the token whose piece holds its first letter
        starts, pos = [], 0
        for w in new:
            starts.append(pos)
            pos += len(w)
        owners = {}
        for w_i, st in enumerate(starts):
            k = next((n for n, b in enumerate(bounds) if st < b), len(ts) - 1)
            owners.setdefault(k, []).append(idxs[w_i])
        for k, t in enumerate(ts):
            mark(t, owners.get(k, []))
    return True
