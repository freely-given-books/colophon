"""
Rebuilding TEI elements from (possibly annotated) tokens: choice/orig/reg,
abbr/expan, supplied.
"""

import copy
import re
from lxml import etree

import teibuild  # noqa: F401  (puts colophon on sys.path)

from teitok import T, local  # noqa: E402

from teibuild import settings as S  # noqa: E402
from teibuild.words import NO_SPACE_BEFORE  # noqa: E402


class Builder:
    def __init__(self, el):
        self.el = el

    def text(self, s):
        if not s:
            return
        if len(self.el):
            last = self.el[-1]
            last.tail = (last.tail or "") + s
        else:
            self.el.text = (self.el.text or "") + s

    def elem(self, e):
        e.tail = None
        self.el.append(e)


def put_pieces(b, pieces, tok, keep_noise=False):
    for p in pieces:
        if isinstance(p, str):
            b.text(p)
        elif isinstance(p, tuple):
            # pretty-print indentation inside a word is not a real space;
            # drop it so the enriched file reads correctly without heuristics
            if keep_noise:
                b.text(p[1])
        else:
            n = local(p)
            if n == "gap":
                idx = next(i for i, e in tok.gaps if e is p)
                if idx in S.GAP_FIXES or idx in tok.extra.get("gapfill", {}):
                    b.elem(make_supplied(p, idx, tok))
                    continue
            b.elem(p)


def make_supplied(gap, idx, tok):
    fill = tok.extra.get("gapfill", {}).get(idx)
    if fill is not None:
        letters, cert, note, resp = fill
    else:
        letters, cert, note, *who = S.GAP_FIXES[idx]
        resp = who[0] if who else "#auto"
    s = etree.Element(T + "supplied")
    s.set("reason", gap.get("reason", "illegible"))
    s.set("cert", cert)
    s.set("resp", resp)
    s.text = letters
    # keep the original <gap> inside for full provenance
    g = copy.deepcopy(gap)
    g.tail = None
    # XML comments may not hold "--" or end in "-"
    s.append(etree.Comment(" " + re.sub(r"-{2,}", "\u2013", note).rstrip("-") + " "))
    s.append(g)
    s[-1].tail = None
    return s


def rebuild(el, toks):
    for c in list(el):
        el.remove(c)
    el.text = None
    b = Builder(el)
    for t in toks:
        emit(b, t)


def emit(b, t):
    if t.kind in ("space", "noise"):
        b.text(t.pieces[0])
    elif t.kind == "spacing":
        ch = etree.Element(T + "choice")
        o = etree.SubElement(ch, T + "orig")
        o.text = t.pieces[0] or None
        r = etree.SubElement(ch, T + "reg")
        r.text = t.reg or None
        r.set("resp", t.resp or "#editor")
        r.set("type", "spacing")
        b.elem(ch)
    elif t.kind == "atom":
        b.elem(t.el)
    elif t.kind == "container":
        rebuild(t.el, t.children)
        b.elem(t.el)
    elif t.kind == "group":
        ch = etree.Element(T + "choice")
        o = etree.SubElement(ch, T + "orig")
        ob = Builder(o)
        for sub in t.children:
            emit(ob, sub)
        r = etree.SubElement(ch, T + "reg")
        fill_reg(r, t)
        r.set("resp", t.resp)
        if t.rtype:
            r.set("type", t.rtype)
        b.elem(ch)
    elif t.kind == "punct":
        p = t.pieces[0]
        if t.reg is not None and t.reg != t.orig:
            ch = etree.Element(T + "choice")
            o = etree.SubElement(ch, T + "orig")
            ob = Builder(o)
            (ob.elem if not isinstance(p, str) else ob.text)(p)
            r = etree.SubElement(ch, T + "reg")
            fill_reg(r, t)
            r.set("resp", t.resp)
            if t.rtype:
                r.set("type", t.rtype)
            b.elem(ch)
        else:
            (b.elem if not isinstance(p, str) else b.text)(p)
    elif t.kind == "word":
        emit_word(b, t)
    for el in t.extra.get("notes_after", []) if t.kind in ("word", "punct") else []:
        b.elem(el)


def emit_word(b, t):
    has_abbr = bool(t.macrons) or any(
        not isinstance(p, (str, tuple)) and local(p) in ("expan",) for p in t.pieces)
    has_sup = any(not isinstance(p, (str, tuple)) and local(p) == "hi" for p in t.pieces)
    changed = t.reg is not None and t.reg != t.extra.get("expan", t.expanded)

    def put_orig(target):
        ob = Builder(target)
        if has_abbr or has_sup:
            ch = etree.SubElement(target, T + "choice")
            a = etree.SubElement(ch, T + "abbr")
            put_pieces(Builder(a), t.pieces, t)
            e = etree.SubElement(ch, T + "expan")
            e.text = t.extra.get("expan", t.expanded)
            if t.extra.get("expan_resp"):
                e.set("resp", t.extra["expan_resp"])
        else:
            put_pieces(ob, t.pieces, t)

    auto = t.extra.get("auto_reg")
    if t.resp == "#editor" and auto is not None and auto != t.reg:
        changed = True
    if changed:
        ch = etree.Element(T + "choice")
        o = etree.SubElement(ch, T + "orig")
        put_orig(o)
        r = etree.SubElement(ch, T + "reg")
        fill_reg(r, t)
        r.set("resp", t.resp or "#auto")
        if t.rtype:
            r.set("type", t.rtype)
        # keep the machine's proposal next to the editor's decision
        base = t.extra.get("expan", t.expanded)
        if t.resp == "#editor" and auto is not None and auto not in (t.reg, base):
            r2 = etree.SubElement(ch, T + "reg")
            r2.text = auto
            r2.set("resp", "#auto")
            r2.set("type", "spelling")
        b.elem(ch)
    elif has_abbr or has_sup:
        tmp = etree.Element("tmp")
        put_orig(tmp)
        for c in list(tmp):
            b.elem(c)
    else:
        put_pieces(b, t.pieces, t)


def fill_reg(r, t):
    """Put a token's regularized reading into <reg> r: plain text, or text
    with italics and notes/anchors where the review has them."""
    words = t.extra.get("reg_words")
    ital = t.extra.get("reg_italic")
    inner = t.extra.get("reg_inner")
    if not words or not (ital or inner):
        r.text = t.reg
        return
    sps = t.extra.get("reg_sp")
    lead, trail = t.extra.get("pad", ("", ""))
    b = Builder(r)
    b.text(lead)
    run = None                              # [italic, text]

    def flush():
        nonlocal run
        if run:
            if run[0]:
                h = etree.Element(T + "hi")
                h.text = run[1]
                b.elem(h)
            else:
                b.text(run[1])
        run = None

    for k, w in enumerate(words):
        if k:
            space = sps[k] if sps is not None else w[:1] not in NO_SPACE_BEFORE
        else:
            space = False
        it = bool(ital[k]) if ital and k < len(ital) else False
        if run is not None and run[0] == it:
            run[1] += (" " if space else "") + w
        else:
            flush()
            if space:
                b.text(" ")
            run = [it, w]
        for el in (inner or {}).get(k, []):
            flush()
            b.elem(copy.deepcopy(el) if el.getparent() is not None else el)
    flush()
    b.text(trail)
