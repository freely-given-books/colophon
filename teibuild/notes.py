"""
Notes and divisions: notes aligned apart from the body, matched and
placed where the review has them; a division reviewed as a whole.
"""

import bisect
try:
    import cydifflib as difflib     # difflib compiled: the same matches, faster
except ImportError:
    import difflib
import re
from lxml import etree

import teibuild  # noqa: F401  (puts colophon on sys.path)

from teitok import T, Tok, local  # noqa: E402

from teibuild.settings import XML_NS  # noqa: E402
from teibuild.tokens import ancestors, contains, relink  # noqa: E402
from teibuild.state import (  # noqa: E402
    EDITION_HEADS,
    PARA_LEVELS,
    LIST_SHAPE,
    NOTE_SEQ,
    NO_SPACE_RUN_ON,
    SPLIT_RE)
from teibuild.machine import stream  # noqa: E402
from teibuild.align import align  # noqa: E402
from teibuild.decisions import apply_clusters, join_sp  # noqa: E402
from teibuild.spacing import apply_spacing  # noqa: E402
from teibuild.emphasis import apply_emphasis  # noqa: E402


def split_notes(entries):
    """Body entries, and [(note Tok, its entries, anchor)] where anchor is
    the number of body entries before the note."""
    body, notes, rec = [], [], {}
    for e in entries:
        # the innermost note: a note printed inside a note is a note of its own
        note = next((c for c in reversed(e[3]) if local(c.el) == "note"), None)
        if note is None:
            body.append(e)
            continue
        if id(note) not in rec:
            rec[id(note)] = (note, [], len(body))
            notes.append(rec[id(note)])
        if e[1] == "w":
            rec[id(note)][1].append(e)
    return body, notes


def position_map(a, b):
    """Map positions (0..len) in sequence a to positions in b."""
    ops = difflib.SequenceMatcher(None, a, b, autojunk=False).get_opcodes()
    spans = [o for o in ops if o[1] < o[2]]     # the ops covering a, in order
    ends = [o[2] for o in spans]

    def f(i):
        k = bisect.bisect_right(ends, i)        # the span holding i
        if k < len(spans):
            op, i1, i2, j1, j2 = spans[k]
        elif ops and i == ops[-1][2]:           # the end of a: the last op
            op, i1, i2, j1, j2 = ops[-1]
        else:
            return len(b)
        if op == "equal":
            return j1 + (i - i1)
        return j1 + round((i - i1) * (j2 - j1) / max(1, i2 - i1))
    return f


def match_notes(src, tgt, s2t):
    """Monotonic matching of printed notes to review notes by position and
    text. src: [(anchor_in_src, text)], tgt: [(anchor_in_tgt, text)].
    Returns list of (i or None, j or None)."""
    n, m = len(src), len(tgt)
    SKIP = 1.0
    INF = float("inf")
    mapped = [s2t(a) for a, _ in src]
    src_l = [t.lower() for _, t in src]
    tgt_l = [t.lower() for _, t in tgt]

    def cost(i, j):
        d = min(abs(mapped[i] - tgt[j][0]), 400) / 100
        if d > 2 * SKIP:
            # costs more than skipping both notes, whatever the text: such a
            # match is always replaced, so its text is not compared
            return INF
        sim = difflib.SequenceMatcher(None, src_l[i], tgt_l[j]).ratio()
        return d + (1 - sim)

    D = [[INF] * (m + 1) for _ in range(n + 1)]
    P = [[None] * (m + 1) for _ in range(n + 1)]
    D[0][0] = 0
    for i in range(n + 1):
        for j in range(m + 1):
            if D[i][j] == INF:
                continue
            if i < n and D[i][j] + SKIP < D[i + 1][j]:
                D[i + 1][j], P[i + 1][j] = D[i][j] + SKIP, (i, j, "s")
            if j < m and D[i][j] + SKIP < D[i][j + 1]:
                D[i][j + 1], P[i][j + 1] = D[i][j] + SKIP, (i, j, "t")
            if i < n and j < m:
                c = D[i][j] + cost(i, j)
                if c < D[i + 1][j + 1]:
                    D[i + 1][j + 1], P[i + 1][j + 1] = c, (i, j, "m")
    out, i, j = [], n, m
    while (i, j) != (0, 0):
        pi, pj, k = P[i][j]
        out.append((pi if k in "ms" else None, pj if k in "mt" else None))
        i, j = pi, pj
    out = out[::-1]
    # Notes the review set in another order than printed (a reference moved
    # past its neighbour to the words it proves) cross: the matching above
    # cannot, and would read them as one note rewritten into another. Swap
    # two near matches when each fits the other's note much better, and pair
    # a dropped note with an added one when their texts agree.
    def c(i, j):
        return cost(i, j) if i is not None and j is not None else INF
    changed = True
    while changed:
        changed = False
        ms = [k for k, (i, j) in enumerate(out) if i is not None and j is not None]
        for x in range(len(ms)):
            for y in range(x + 1, min(x + 6, len(ms))):
                (i1, j1), (i2, j2) = out[ms[x]], out[ms[y]]
                if c(i1, j2) + c(i2, j1) < c(i1, j1) + c(i2, j2) - 0.1:
                    out[ms[x]], out[ms[y]] = (i1, j2), (i2, j1)
                    changed = True
        lone_s = [k for k, (i, j) in enumerate(out) if j is None]
        lone_t = [k for k, (i, j) in enumerate(out) if i is None]
        for ks in lone_s:
            best = min(lone_t, key=lambda kt: c(out[ks][0], out[kt][1]), default=None)
            if best is not None and c(out[ks][0], out[best][1]) < SKIP:
                out[ks] = (out[ks][0], out[best][1])
                out[best] = (None, None)
                lone_t.remove(best)
                changed = True
        out = [p for p in out if p != (None, None)]
    return out


def insert_after(tok, el):
    """Put element `el` right after `tok` in the token tree (after the group
    that swallowed tok, if any)."""
    par = tok.parent
    kids = par.children
    k = next(i for i, c in enumerate(kids) if contains(c, tok))
    atom = Tok("atom", el=el)
    kids.insert(k + 1, atom)
    relink(par)


def insert_before(tok, el):
    par = tok.parent
    kids = par.children
    k = next(i for i, c in enumerate(kids) if contains(c, tok))
    kids.insert(k, Tok("atom", el=el))
    relink(par)


def division_trailers(div_el):
    """Trailers ("FINIS.") inside a division, or right after it."""
    out = [c for c in div_el if local(c) == "trailer"]
    sib = div_el.getnext()
    while sib is not None and local(sib) == "trailer":
        out.append(sib)
        sib = sib.getnext()
    return out


def keep_trailers(d, review, f, log):
    """A trailer is left out of the edition unless the review ends with it;
    then it is marked ana="#in-edition" (and, if it sits outside the
    division, taken out of the review so the rest aligns cleanly)."""
    for tr in (division_trailers(d.el) if d.el is not None else []):
        words = [w.lower() for w in SPLIT_RE.findall(
            " ".join("".join(tr.itertext()).split()).replace("ſ", "s"))]
        k = max((i for i, e in enumerate(review.body) if e[1] == "m"), default=None)
        if k is None:
            continue
        tail = [e[0].lower() for e in review.body[k + 1:]]
        if tail != words:
            continue
        tr.set("ana", "#in-edition")
        tr.set("change", "#review")
        log.append((f, "trailer", " ".join(words), "kept in the edition"))
        if tr.getparent() is not d.el:
            del review.body[k:]


def left_out_trailer(e):
    """Whether a stream entry belongs to a trailer ("FINIS.") the edition
    leaves out (keep_trailers did not mark it #in-edition)."""
    return any(c.el is not None and local(c.el) == "trailer" and
               c.el.get("ana") != "#in-edition" for c in (*e[3], e[2]) if c.kind == "container")


def review_division(d, review, f, log, unresolved):
    """Align one division with its review: body and notes separately.
    Trailers the edition leaves out are not aligned, so words the review
    adds at the end of the text are not matched against them (and lost)."""
    entries = [e for e in stream(d.children) if not left_out_trailer(e)]
    body, notes = split_notes(entries)
    tgt = [(t, k) for t, k, _ in review.body]
    owner = {}
    cl, st = align(body, tgt, [], f, owner)
    for j0 in getattr(review, "epigraphs", ()):
        # a printed paragraph the review sets as a scripture epigraph
        jw = next((j for j in range(j0 + 1, len(tgt)) if j in owner), None)
        if jw is None:
            continue
        anc = ancestors(owner[jw])
        p = next((a for a in anc if local(a.el) in ("p", "epigraph")), None)
        if p is not None and local(p.el) == "p" and p.el.get("rend") != "epigraph" and \
                not any(local(a.el) == "epigraph" for a in anc):
            p.el.set("rend", "epigraph")
            p.el.set("change", "#review")
            log.append((f, "epigraph", owner[jw].orig, "set as a scripture epigraph"))
    for j0 in getattr(review, "insets", ()):
        # a printed paragraph the review sets off, indented on both sides
        jw = next((j for j in range(j0 + 1, len(tgt)) if j in owner), None)
        if jw is None:
            continue
        p = next((a for a in ancestors(owner[jw]) if local(a.el) in ("p", "q")), None)
        if p is not None and p.el.get("rend") != "inset":
            p.el.set("rend", "inset")
            p.el.set("change", "#review")
            log.append((f, "inset", owner[jw].orig, "set off, indented both sides"))
    for j0, lvl in getattr(review, "para_levels", ()):
        # set in by its place in the outline: applied after the review's
        # paragraph splits, so each part keeps its own level
        jw = next((j for j in range(j0 + 1, len(tgt)) if j in owner), None)
        if jw is not None:
            PARA_LEVELS.append((owner[jw], lvl, f))
    tflags = {}            # id(tok) -> [(target index, italic flag)]
    for j, tok in owner.items():
        tflags.setdefault(id(tok), []).append((j, review.body[j][2]))
    s2t = position_map([e[0] for e in body], [t for t, _ in tgt])

    src = [(a, " ".join(e[0] for e in es)) for _, es, a in notes]
    tn = [(n["anchor"], " ".join(t for t, _ in n["toks"])) for n in review.notes]
    pairs = match_notes(src, tn, s2t)

    note_spacing = []      # (note Tok, review note, owner) for the spacing pass
    placed = {}            # target index -> [elements to put after that word]
    before_first = []      # elements before the first word of the division

    def prev_word(j):
        k = j - 1
        while k >= 0 and tgt[k][1] != "w":
            k -= 1
        return k

    for i, j in pairs:
        if i is None:                      # a note the editor added
            nt = review.notes[j]
            el = etree.Element(T + "note")
            el.set("ana", "#edition-only")
            el.set("resp", "#editor")
            el.set("change", "#review")
            words = [t for t, _ in nt["toks"]]
            sps = nt.get("sp")
            el.text = join_sp(words, sps if sps and len(sps) == len(words) else None)
            k = prev_word(nt["anchor"])
            (placed.setdefault(k, []) if k >= 0 else before_first).append(el)
            log.append((f, "note", "(none)", el.text))
            continue
        note_tok, es, a = notes[i]
        if j is None:                      # a printed note the editor dropped
            note_tok.el.set("ana", "#print-only")
            note_tok.el.set("change", "#review")
            log.append((f, "note", " ".join(e[0] for e in es), "(dropped)"))
            continue
        nt = review.notes[j]
        if nt.get("mark") and nt["mark"] == note_tok.el.get("n"):
            # set with its printed mark, not a number
            if note_tok.el.get("rend") != "mark":
                note_tok.el.set("rend", "mark")
                note_tok.el.set("change", "#review")
                log.append((f, "note", " ".join(e[0] for e in es)[:40],
                            f"set with its mark {nt['mark']}"))
        elif nt.get("mark"):
            unresolved.append((f, "note mark", f"{nt['mark']} (printed: {note_tok.el.get('n')})"))
        elif note_tok.el.get("rend") == "mark":
            del note_tok.el.attrib["rend"]
        nowner = {}
        ncl, _ = align(es, [(t, "w") for t, _ in nt["toks"]], [], f + " note", nowner)
        for jj, tok in nowner.items():
            tflags.setdefault(id(tok), []).append((jj, nt["toks"][jj][1]))
        apply_clusters(ncl, log, unresolved, f + " note", None,
                       lambda jj, nt=nt: nt["toks"][jj][1], lambda jj, nt=nt: nt["sp"][jj])
        note_spacing.append((note_tok, nt, nowner))
        # does the review keep the note where it was printed?
        k = prev_word(nt["anchor"])
        # the printed word before it; a printed number the review leaves
        # out ("1." of a list the edition numbers itself) is passed over
        kept = {id(o) for o in owner.values()}
        ws = [e for e in body[:a] if e[1] == "w"]
        n = 0
        while n < len(ws) and id(ws[-1 - n][2]) not in kept and \
                re.fullmatch(r"\d{1,3}|[ivxlcIVXLC]{1,6}|[.)]", ws[-1 - n][0]):
            n += 1
        if not any(re.fullmatch(r"\d{1,3}|[ivxlcIVXLC]{1,6}", e[0]) for e in ws[len(ws) - n:]):
            n = 0
        src_prev = ws[-1 - n] if n < len(ws) else None
        if k < 0 or src_prev is None:
            if k < 0 and src_prev is None:
                continue
        elif owner.get(k) is src_prev[2] and \
                max(x for x, o in owner.items() if o is src_prev[2]) == k:
            continue
        NOTE_SEQ["n"] += 1
        aid = f"rn{NOTE_SEQ['n']}"
        anchor = etree.Element(T + "anchor")
        anchor.set("{%s}id" % XML_NS, aid)
        anchor.set("change", "#review")
        note_tok.el.set("target", "#" + aid)
        note_tok.el.set("change", "#review")
        (placed.setdefault(k, []) if k >= 0 else before_first).append(anchor)
        log.append((f, "note moved", " ".join(e[0] for e in es)[:40],
                    "after '" + (tgt[k][0] if k >= 0 else "(start)") + "'"))

    apply_clusters(cl, log, unresolved, f, placed, lambda j: review.body[j][2],
                   lambda j: review.body_sp[j])
    # the edition's own headings, placed before the block they stand over
    for pos, level, text in getattr(review, "edition_heads", []):
        jw = next((x for x in range(pos, len(tgt)) if tgt[x][1] == "w"), None)
        tok = owner.get(jw) if jw is not None else None
        if tok is None:
            unresolved.append((f, "edition heading", text))
        else:
            EDITION_HEADS.append((tok, level, text, f))
    # list items and the blocks set inside them (reviewparse list_info),
    # placed after restructure() has made the review's lists
    for j, info in sorted(getattr(review, "list_info", {}).items()):
        jw = next((x for x in range(j + 1, len(tgt)) if tgt[x][1] == "w"), None)
        tok = owner.get(jw) if jw is not None else None
        if tok is not None:
            LIST_SHAPE.append((tok, info, f))
        elif info["depth"] or info.get("numbering") or info.get("start") or info.get("indent"):
            unresolved.append((f, "list shape", tgt[jw][0] if jw is not None else "(end)"))
    # words the review left alone but put a note after
    in_cluster = {j for _ts, _n, idxs in cl for j in idxs}
    for k, els in placed.items():
        if k in in_cluster:
            continue
        tok = owner.get(k)
        if tok is None:
            unresolved.append((f, "note position", tgt[k][0]))
            continue
        for el in reversed(els):
            insert_after(tok, el)
    first = next((e for e in body if e[1] == "w"), None)
    for el in before_first:
        insert_before(first[2], el)
    apply_emphasis(d, tflags, log, f)
    order, blk = [], 0
    for j, (t, k, _) in enumerate(review.body):
        if k == "m":
            blk += 1
        else:
            order.append((j, blk))
    apply_spacing(d, order, review.body_sp, log, f, owner=owner)
    for note_tok, nt, nowner in note_spacing:
        apply_spacing(note_tok, [(jj, 0) for jj in range(len(nt["toks"]))], nt["sp"],
                      log, f + " note", skip_notes=False, owner=nowner)
    # a block the review runs on without a space ("Psalm 37:" + "6. And ...")
    first_j = {}
    for j, tok in sorted(owner.items()):
        first_j.setdefault(id(tok), j)
    where = {id(e[2]): k for k, e in reversed(list(enumerate(body)))}
    for x in st:
        if x["at"] is not None and x["src_marks"] and not x["tgt_marks"]:
            # the first word of the joined block that the review keeps
            j = None
            for e in body[where.get(id(x["at"][2]), len(body)):]:
                if e[1] == "m":
                    break
                j = first_j.get(id(e[2]))
                if j is not None:
                    break
            if j is not None and not review.body_sp[j]:
                NO_SPACE_RUN_ON.add(id(x["at"][2]))
    return st, body
