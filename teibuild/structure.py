"""
Structure: paragraphs split, run-in "I. ... II. ..." made into lists,
the review's list shapes and the headings the edition adds.
"""

from lxml import etree

import teibuild  # noqa: F401  (puts colophon on sys.path)

from teitok import T, Tok, local  # noqa: E402
import layout  # noqa: E402

from teibuild.settings import NUMERAL_RE, ROMAN_RE, XML_NS  # noqa: E402
from teibuild.tokens import (  # noqa: E402
    ancestors,
    contains,
    has_words,
    in_container,
    new_container,
    relink)
from teibuild.state import (  # noqa: E402
    EDITION_HEADS,
    HEAD_MODE,
    LIST_SHAPE,
    MADE_LISTS,
    NOTE_SEQ,
    NO_SPACE_RUN_ON,
    ROOT,
    SETTINGS)


def has_content(ts):
    return any(t.kind not in ("space", "noise") for t in ts)


def split_container(ct, tok):
    kids = ct.children
    i = next(k for k, c in enumerate(kids) if contains(c, tok))
    c = kids[i]
    if c is tok or c.kind == "group":
        left, right = kids[:i], kids[i:]
    else:
        cl, cr = split_container(c, tok)
        left = kids[:i] + ([cl] if has_content(cl.children) else [])
        right = [cr] + kids[i + 1:]
    r = new_container(local(ct.el), like=ct.el)
    ct.children, r.children = left, right
    relink(ct)
    relink(r)
    return ct, r


def block_of(tok):
    """The block a token stands in: a child of its division, or a paragraph
    of a speech (sp)."""
    a = tok.parent
    while a is not None and not (a.el.getparent() is not None and
                                 (local(a.el.getparent()) == "div" or
                                  (local(a.el.getparent()) == "sp" and
                                   local(a.el) != "speaker"))):
        a = a.parent
    return a


def wrap_label(labels):
    """Put the printed list numeral (e.g. 'II' + '.') in a <label>,
    wherever it sits (directly in the item or inside an italic run)."""
    par = labels[0].parent
    if par is None or labels[1].parent is not par:
        return False
    if par.kind == "container" and local(par.el) == "label":
        return True                 # printed in a <label> already
    kids = par.children
    i0 = next(k for k, c in enumerate(kids) if c is labels[0])
    i1 = next(k for k, c in enumerate(kids) if c is labels[1])
    lab = new_container("label")
    lab.children = kids[i0:i1 + 1]
    relink(lab)
    par.children = kids[:i0] + [lab] + kids[i1 + 1:]
    relink(par)
    return True


def merge_lists(log):
    """Lists the review made from neighbouring paragraphs ("1. ..." and
    "2. ..." each a <p>) are one list: join a new list to the one before it
    when nothing but space lies between."""
    for lst in MADE_LISTS:
        par = lst.parent
        if par is None or lst not in par.children:
            continue
        k = par.children.index(lst)
        j = k - 1
        while j >= 0 and par.children[j].kind in ("space", "noise"):
            j -= 1
        prev = par.children[j] if j >= 0 else None
        if prev is not None and prev.kind == "container" and local(prev.el) == "p":
            # a list ending the paragraph before (printed, or its run-in
            # "1. ... 3." set out): the new items carry it on (Gouge's "4. Good will", a
            # brace printed after items 1-3); only the nesting changes
            inner = [c for c in prev.children if c.kind not in ("space", "noise")]
            if inner and inner[-1].kind == "container" and local(inner[-1].el) == "list":
                prev = inner[-1]
                if prev.el.get("type") == lst.el.get("type"):
                    while prev.children and prev.children[-1].kind == "space":
                        prev.children.pop()
                    for c in lst.children:      # printed as paragraphs (orig layer)
                        if c.kind == "container" and local(c.el) == "item":
                            c.el.set("change", "#review")
                    prev.children += [Tok("space", ["\n"])] + [c for c in lst.children]
                    relink(prev)
                    del par.children[j + 1:k + 1]
                    relink(par)
                continue
        if prev is not None and prev.kind == "container" and local(prev.el) == "list" \
                and prev.el.get("change") == "#review" and prev in MADE_LISTS \
                and prev.el.get("type") == lst.el.get("type"):
            prev.children += [Tok("space", ["\n"])] + [c for c in lst.children]
            relink(prev)
            del par.children[j + 1:k + 1]
            relink(par)


def apply_edition_heads(log):
    """Each heading the edition adds becomes label[@type="head"] (its level
    in @n, ana="#edition-only") before the block whose first word it stands
    over; printed text is not touched."""
    for tok, level, text, f in EDITION_HEADS:
        path = path_to(ROOT["toks"], tok) or []
        conts = [c for c in path if c.kind == "container"]
        k = next((i for i in range(len(conts) - 1, 0, -1)
                  if local(conts[i - 1].el) in ("div", "item")), None)
        if k is None:
            log.append((f, "skipped", f"heading '{text}'", "no block for it"))
            continue
        blk, par = conts[k], conts[k - 1]
        if local(blk.el) == "list":     # over an item: before that item
            item = next((c for c in conts[k + 1:] if local(c.el) == "item"), None)
            items = [c for c in blk.children if c.kind == "container" and local(c.el) == "item"]
            if item is not None and items and item is not items[0]:
                blk, par = item, blk
        el = etree.Element(T + "label")
        el.set("type", "head")
        el.set("n", str(level))
        el.set("ana", "#edition-only")
        el.set("change", "#review")
        el.text = text
        i = next(j for j, c in enumerate(par.children) if c is blk)
        par.children[i:i] = [Tok("atom", el=el), Tok("space", ["\n"])]
        relink(par)
        log.append((f, "heading", "(none)", text))


def path_to(ts, tok, trail=()):
    """The containers (and groups) from the top down to tok, or None."""
    for c in ts:
        if c is tok:
            return list(trail)
        if c.kind in ("container", "group") and c.children:
            r = path_to(c.children, tok, trail + (c,))
            if r is not None:
                return r
    return None


def detach(blk, parent):
    k = next(i for i, c in enumerate(parent.children) if c is blk)
    j = k - 1 if k and parent.children[k - 1].kind in ("space", "noise") else k
    del parent.children[j:k + 1]
    relink(parent)


def append_block(parent, blk):
    parent.children += [Tok("space", ["\n"]), blk]
    relink(parent)


def nested_under(item, path):
    """Whether the containers in path put a block inside item: in it, or in
    an item that only wraps a nested list and follows it (the TCP's way of
    nesting a list under an item, which the Typst lists render as inside)."""
    if item in path:
        return True
    lst = item.parent
    if lst is None:
        return False
    sibs = [c for c in lst.children if c.kind == "container"]
    k = next((i for i, c in enumerate(sibs) if c is item), None)
    while k is not None and k + 1 < len(sibs):
        nxt = sibs[k + 1]
        inner = [c for c in nxt.children if c.kind == "container" or has_words(c)]
        if local(nxt.el) != "item" or not inner or \
                any(c.kind != "container" or local(c.el) != "list" for c in inner):
            return False
        if nxt in path:
            return True
        k += 1
    return False


def apply_list_shape(log):
    """The review's list layout: an item it indents under another goes into
    a list inside that item, a paragraph it indents under an item goes
    into the item, and a list it numbers in its own way (#[ #set enum(
    numbering: "a)", start: 2) ... ]) gets list/@rend (the numbering) and
    item/@n on its first item (the start); one it sets in (indent: 24pt)
    gets list/@style="indent". Printed text is not moved
    across other text: only the nesting changes."""
    last, cur = {}, None             # depth -> the latest item at that depth
    for tok, info, f in LIST_SHAPE:
        if f != cur:
            last, cur = {}, f
        path = path_to(ROOT["toks"], tok)
        conts = [c for c in path or [] if c.kind == "container"]
        d = info["depth"]
        if info["kind"] in ("+", "-"):
            k = next((i for i in range(len(conts) - 1, 0, -1)
                      if local(conts[i].el) == "item"), None)
            cell = next((c for c in reversed(conts) if local(c.el) == "cell"), None)
            if k is None and cell is not None and d == 1 and info["kind"] in ("+", "-") and \
                    not info.get("numbering") and not info.get("start") and \
                    not info.get("indent"):
                # a branch of a brace the review sets under the branch before
                if cell.el.get("rend") != "nested":
                    cell.el.set("rend", "nested")
                    cell.el.set("change", "#review")
                    log.append((f, "list", f"table cell at '{tok.orig}'",
                                "nested under the branch before"))
                continue
            if k is None and cell is not None and d == 0 and info.get("indent"):
                # a brace's branches the review sets one step in
                table = next(c for c in reversed(conts) if local(c.el) == "table")
                if table.el.get("style") != "indent":
                    table.el.set("style", "indent")
                    table.el.set("change", "#review")
                    log.append((f, "list", f"table at '{tok.orig}'", "set one step in"))
                continue
            if k is None:
                if d or info.get("numbering") or info.get("start") or info.get("indent"):
                    log.append((f, "skipped", f"list item at '{tok.orig}'", "not an item"))
                continue
            item, lst = conts[k], conts[k - 1]
            parent = last.get(d - 1) if d else None
            if parent is not None and not nested_under(parent, path):
                blocks = [c for c in parent.children if c.kind == "container"]
                sub = blocks[-1] if blocks and local(blocks[-1].el) == "list" else None
                if sub is None:
                    sub = new_container("list", like=lst.el)
                    sub.el.attrib.pop("rend", None)
                    sub.el.set("change", "#review")
                    append_block(parent, sub)
                detach(item, lst)
                if not any(c.kind == "container" and local(c.el) == "item"
                           for c in lst.children):
                    detach(lst, conts[k - 2])
                sub.children += ([Tok("space", ["\n"])] if sub.children else []) + [item]
                relink(sub)
                lst = sub
                log.append((f, "list", f"item at '{tok.orig}'", "set inside the item before"))
            num = info.get("numbering")
            if num and lst.el.get("rend") != num:
                lst.el.set("rend", num)
                lst.el.set("change", "#review")
                log.append((f, "list", f"numbering at '{tok.orig}'", num))
            if info.get("indent") and lst.el.get("style") != "indent":
                # set one step in, under the numbered paragraph it belongs to
                lst.el.set("style", "indent")
                lst.el.set("change", "#review")
                log.append((f, "list", f"list at '{tok.orig}'", "set one step in"))
            if info.get("start"):
                first = next(c for c in lst.children
                             if c.kind == "container" and local(c.el) == "item")
                if first is item:
                    item.el.set("n", str(info["start"]))
                    log.append((f, "list", f"numbering at '{tok.orig}'",
                                f"starts at {info['start']}"))
                else:
                    log.append((f, "skipped", f"list start at '{tok.orig}'",
                                "not the first item of its list"))
            last[d] = item
            for x in [x for x in last if x > d]:
                del last[x]
        else:
            parent = last.get(d - 1)
            k = next((i for i in range(len(conts) - 1, 0, -1)
                      if local(conts[i].el) in ("p", "q")), None)
            if parent is None or k is None:
                log.append((f, "skipped", f"paragraph at '{tok.orig}'",
                            "set inside a list item, but no item before it"))
                continue
            if nested_under(parent, path):
                continue
            blk = conts[k]
            detach(blk, conts[k - 1])
            append_block(parent, blk)
            log.append((f, "list", f"paragraph at '{tok.orig}'", "set inside the item before"))
    merge_lists(log)            # the lists a paragraph stood between


def first_words(ct, n):
    """The first n word/punct tokens inside a container, in order."""
    out = []

    def walk(ts):
        for t in ts:
            if len(out) >= n:
                return
            if t.kind in ("word", "punct"):
                out.append(t)
            elif t.kind == "container" and local(t.el) != "note":
                walk(t.children or [])
    walk(ct.children)
    return out


def leading(ct, tok):
    """The tokens of ct before tok, at every level down to it."""
    out = []
    for c in ct.children:
        if contains(c, tok):
            if c is not tok and c.kind == "container":
                out += leading(c, tok)
            return out
        out.append(c)
    return out


def lines_as_p(lg):
    """Verse lines the review sets as prose: one paragraph of their words
    (the line's id kept when there is one line)."""
    p = new_container("p")
    p.el.set("change", "#review")
    lines = [c for c in lg.children if c.kind == "container" and local(c.el) == "l"]
    kids = []
    for ln in lines:
        if kids:
            kids.append(Tok("space", [" "]))
        kids += ln.children
    if len(lines) == 1 and lines[0].el.get("{%s}id" % XML_NS):
        p.el.set("{%s}id" % XML_NS, lines[0].el.get("{%s}id" % XML_NS))
    p.children = kids
    relink(p)
    return p


def split_quote(q, pts, log):
    """A source quotation the review breaks up (CCEL puts prose and verse in
    one blockquote): split it at each point; a part after a new paragraph
    mark leaves the quotation (its paragraphs become the edition's own), a
    part after a new quote mark is a quotation of its own."""
    div = q.parent
    parts, cur = [(q, None)], q
    for tok, kind, _labels, _o, _f in pts:
        if kind == "unquote" and parts[-1][1] is None and \
                not any(has_content([c]) for c in leading(cur, tok)):
            parts[-1] = (cur, "unquote")        # from its first word on
            continue
        _left, right = split_container(cur, tok)
        parts.append((right, kind))
        cur = right
    out = []
    for ct, kind in parts:
        if kind is None:
            if has_content(ct.children):
                out.append(ct)
        elif kind == ">":
            ct.el.set("change", "#review")
            out.append(ct)
        else:
            for c in ct.children:
                if c.kind == "container" and local(c.el) == "lg":
                    out.append(lines_as_p(c))
                elif c.kind == "container":
                    c.el.set("change", "#review")
                    out.append(c)
    i = div.children.index(q)
    repl = []
    for k, t in enumerate(out):
        if k:
            repl.append(Tok("space", ["\n"]))
        repl.append(t)
    div.children[i:i + 1] = repl
    relink(div)
    log.append((pts[0][4], "split", "quotation",
                f"{len(parts) - 1} split(s) at " + ", ".join(s[0].orig or "" for s in pts)))


def restructure(splits, log):
    """splits: list of (tok, kind, label_toks, order, file). kind '+', '¶'
    or '>' (split there), 'quote' (the block is a quotation), 'merge' (the
    block continues the previous one)."""
    LATER = ("quote", "merge", "renumber", "unlist", "inline", "headmerge")
    tables = {}
    for s in splits:
        if s[1] == "tableinline":
            tables.setdefault(id(s[0]), (s[0], []))[1].append(s)
    for tb, ss in tables.values():
        marks = [m for m, _c in layout.table_reading(tb.el)[1] if m]
        # a table that opens its paragraph: its first line is the review's
        # paragraph start, which is not a split
        kids = tb.parent.children if tb.parent is not None else []
        k = next((i for i, c in enumerate(kids) if c is tb), 0)
        opens = local(tb.parent.el) == "p" and not any(
            has_words(c) for c in kids[:k]
            if not (c.kind == "container" and local(c.el) == "note"))
        if len(ss) == len(marks) or opens and len(ss) == len(marks) - 1:
            tb.el.set("rend", "inline")
            tb.el.set("change", "#review")
            log.append((ss[0][4], "list", "table", "run into its sentence"))
            if opens and len(ss) == len(marks) and not min(ss, key=lambda x: x[3])[2]:
                # its first line ran on too (no paragraph starts there in the
                # review): the paragraph continues the one before
                ws = first_words(tb, 1)
                if ws:
                    splits.append((ws[0], "merge", [], ss[0][3], ss[0][4]))
        else:
            log.append((ss[0][4], "unresolved", "table",
                        f"{len(ss)} of its {len(marks)} lines run on; kept as is"))
    splits = [s for s in splits if s[1] != "tableinline"]
    later = [s for s in splits if s[1] in LATER]
    splits = [s for s in splits if s[1] not in LATER]
    by_block = {}
    for s in splits:
        b = block_of(s[0])
        if b is not None and local(b.el) == "quote":
            by_block.setdefault(id(b), (b, []))[1].append(s)
            continue
        if b is not None and local(b.el) == "lg" and s[1] == "¶":
            # verse the edition sets a line to a paragraph
            if b.el.get("rend") != "paragraphs":
                b.el.set("rend", "paragraphs")
                b.el.set("change", "#review")
                log.append((s[4], "verse", "lines", "set as paragraphs"))
            continue
        sg = next((a for a in ancestors(s[0]) if local(a.el) == "signed"), None)
        if sg is not None and SETTINGS["closer_plain"] and s[1] == "¶":
            # a signature the edition sets on two lines
            par = sg.parent
            _l, right = split_container(sg, s[0])
            right.el.set("change", "#review")
            i = next(k for k, c in enumerate(par.children) if c is sg)
            par.children[i + 1:i + 1] = [Tok("space", ["\n"]), right]
            relink(par)
            log.append((s[4], "split", "signature", f"new line at '{s[0].orig}'"))
            continue
        item = next((a for a in ancestors(s[0]) if local(a.el) == "item"), None)
        lst = item.parent if item is not None else None
        if s[1] == "¶" and b is not None and local(b.el) == "p" and lst is not None and \
                lst.parent is b and local(lst.el) == "list" and \
                [c for c in lst.children if c.kind == "container"][-1] is item:
            # the last item of a printed list runs on into the sentence after
            # the list ("... with the like. These therefore ought he ..."):
            # the edition sets that sentence after the list, as a paragraph.
            # Its words move out of the item to just after the list, so the
            # printed order is kept.
            _left, right = split_container(item, s[0])
            seg = new_container("seg")
            seg.el.set("type", "after-list")
            seg.el.set("change", "#review")
            seg.children = right.children
            relink(seg)
            k = next(i for i, c in enumerate(b.children) if c is lst)
            b.children[k + 1:k + 1] = [seg]
            relink(b)
            log.append((s[4], "split", "list", f"its last item runs on; set after it at '{s[0].orig}'"))
            continue
        if b is None or local(b.el) != "p":
            log.append((s[4], "skipped", f"new {s[1]} before '{s[0].orig}'",
                        "not a paragraph (e.g. a list heading); kept as is"))
            continue
        by_block.setdefault(id(b), (b, []))[1].append(s)
    for b, pts in by_block.values():
        pts.sort(key=lambda s: s[3])
        if local(b.el) == "quote":
            split_quote(b, pts, log)
            continue
        div = b.parent
        cleaned = [(b, None)]
        cur = b
        for tok, kind, labels, _o, _f in pts:
            _left, right = split_container(cur, tok)
            cleaned.append((right, (kind, labels)))
            cur = right
        if len(cleaned) > 1 and has_content(b.children) and all(
                t.kind in ("space", "noise") or t.kind == "atom" and t.el is not None
                and local(t.el) in ("pb", "lb", "milestone", "fw") for t in b.children):
            # only a page break before the first split ("<p><pb/>2. ..."):
            # it goes with the words after it, not into an empty paragraph
            cleaned[1][0].children[0:0] = b.children
            relink(cleaned[1][0])
            b.children = []
        # first segment keeps the original kind (ordinary paragraph)
        out = []
        lst = None
        first = True
        for ct, meta in cleaned:
            if first:
                first = False
                if has_content(ct.children):
                    out.append(ct)
                continue
            kind, labels = meta
            if kind in ("+", "-"):
                item = new_container("item")
                kids = ct.children
                if not labels:
                    # a printed numeral ("9.") the review took no words from:
                    # the item's label, not text
                    ws = first_words(ct, 2)
                    if len(ws) == 2 and NUMERAL_RE.fullmatch(ws[0].orig or "") and \
                            ws[1].orig in (".", ")") and not ws[0].extra.get("tidx") and \
                            not ws[1].extra.get("tidx") and ws[0].reg in (None, ws[0].orig):
                        labels = ws
                if labels:
                    wrap_label(labels)
                    kids = ct.children
                item.children = kids
                relink(item)
                if lst is not None and lst.el.get("type") != ("numbered" if kind == "+"
                                                             else "bulleted"):
                    lst = None
                if lst is None:
                    lst = new_container("list")
                    lst.el.set("type", "numbered" if kind == "+" else "bulleted")
                    lst.el.set("change", "#review")
                    out.append(lst)
                    MADE_LISTS.append(lst)
                if lst.children:
                    lst.children.append(Tok("space", ["\n"]))
                lst.children.append(item)
                relink(lst)
            else:
                lst = None
                p = new_container("p")
                p.children = ct.children
                relink(p)
                if kind == ">":
                    p.el.set("rend", "quote")
                    p.el.set("change", "#review")
                out.append(p)
        # replace b in its div with out (separated by newlines)
        i = div.children.index(b)
        repl = []
        for k, t in enumerate(out):
            if k:
                repl.append(Tok("space", ["\n"]))
            repl.append(t)
        div.children[i:i + 1] = repl
        relink(div)
        log.append((pts[0][4], "split", "paragraph",
                    f"{len(cleaned) - 1} split(s) at " +
                    ", ".join((s[2][0].orig if s[2] else s[0].orig) for s in pts)))
    merge_lists(log)
    for tok, kind, _l, _o, f in sorted(later, key=lambda s: s[3]):
        if kind == "headmerge":
            head = next((a for a in ancestors(tok) if local(a.el) == "head"), None)
            div = head.parent if head is not None else None
            prev = None
            if div is not None and div.parent is not None:
                sibs = [c for c in div.parent.children if c.kind == "container"]
                k = next(i for i, c in enumerate(sibs) if c is div)
                prev = sibs[k - 1] if k else None
                # the last paragraph of the division before
                while prev is not None and local(prev.el) == "div":
                    blocks = [c for c in prev.children if c.kind == "container"
                              and local(c.el) in ("p", "div")]
                    prev = blocks[-1] if blocks else None
            if prev is None or local(prev.el) != "p":
                log.append((f, "skipped", f"head at '{tok.orig}'", "no paragraph before it"))
                continue
            for x in (prev, head):
                if not x.el.get("{%s}id" % XML_NS):
                    NOTE_SEQ["b"] = NOTE_SEQ.get("b", 0) + 1
                    x.el.set("{%s}id" % XML_NS, f"rb{NOTE_SEQ['b']}")
            prev.el.set("next", "#" + head.el.get("{%s}id" % XML_NS))
            head.el.set("prev", "#" + prev.el.get("{%s}id" % XML_NS))
            head.el.set("change", "#review")
            log.append((f, "merge", "heading", f"run on into the paragraph before at '{tok.orig}'"))
            continue
        if kind in ("unlist", "inline"):
            anc = ancestors(tok)
            item = next((a for a in anc if local(a.el) == "item"), None)
            lst = next((a for a in anc if local(a.el) == "list"), None)
            if kind == "unlist" and item is not None:
                item.el.set("rend", "paragraph")       # set as a paragraph
                item.el.set("change", "#review")
                log.append((f, "list", f"item at '{tok.orig}'", "set as a paragraph"))
            elif kind == "inline" and lst is not None and lst.el.get("rend") != "inline":
                lst.el.set("rend", "inline")
                lst.el.set("change", "#review")
                log.append((f, "list", f"list at '{tok.orig}'", "run into its sentence"))
                if local(lst.el.getparent()) != "p":
                    # a list between paragraphs: it runs on from the one before
                    kids = lst.parent.children
                    k = next(i for i, c in enumerate(kids) if c is lst)
                    prev = next((c for c in reversed(kids[:k]) if c.kind == "container"), None)
                    if prev is not None and local(prev.el) in ("p", "q"):
                        for x in (prev, lst):
                            if not x.el.get("{%s}id" % XML_NS):
                                NOTE_SEQ["b"] = NOTE_SEQ.get("b", 0) + 1
                                x.el.set("{%s}id" % XML_NS, f"rb{NOTE_SEQ['b']}")
                        prev.el.set("next", "#" + lst.el.get("{%s}id" % XML_NS))
                        lst.el.set("prev", "#" + prev.el.get("{%s}id" % XML_NS))
            continue
        if kind == "renumber":
            # a printed bullet list the review numbers: its numerals become labels
            lst = next((a for a in ancestors(tok) if local(a.el) == "list"), None)
            if lst is None:
                log.append((f, "skipped", f"numbering at '{tok.orig}'", "not in a list"))
                continue
            if lst.el.get("type") != "numbered":
                lst.el.set("type", "numbered")
                lst.el.set("subtype", "printed")
                lst.el.set("change", "#review")
                log.append((f, "list", "printed list", "numbered"))
            if _l:
                wrap_label(_l)
            continue
        # the innermost paragraph (a <q> may itself hold paragraphs); a
        # scripture epigraph the review sets as a quotation is one block
        b = next((a for a in ancestors(tok) if local(a.el) == "p"), None) or block_of(tok)
        if SETTINGS["closer_plain"]:
            b = next((a for a in ancestors(tok) if local(a.el) in
                      ("salute", "signed", "dateline")), None) or b
        if kind == "merge" and b is not None and local(b.el) == "p" and \
                any(has_words(c) for c in leading(b, tok)):
            # text after a printed list inside the paragraph: the review
            # runs the list into the sentence
            for c in layout.p_blocks(b.el):
                if local(c) == "list" and c.get("rend") != "inline":
                    c.set("rend", "inline")
                    c.set("change", "#review")
                    log.append((f, "list", f"list before '{tok.orig}'", "run into its sentence"))
            continue
        ep = next((a for a in ancestors(tok) if local(a.el) == "epigraph"), None)
        if kind == "quote" and ep is not None:
            b = ep
        if b is None or local(b.el) not in ("p", "q", "epigraph", "salute", "signed",
                                            "dateline"):
            log.append((f, "skipped", f"{kind} at '{tok.orig}'", "not a paragraph"))
            continue
        if kind == "quote":
            b.el.set("rend", "quote")
            b.el.set("change", "#review")
            log.append((f, "quotation", tok.orig, "block set as a quotation"))
            continue
        # merge: this block continues the previous one in the edition; both
        # stay separate elements (as printed), linked by @prev/@next
        kids = b.parent.children
        k = kids.index(b)
        # the block before, passing over any the review emptied
        prev = next((c for c in reversed(kids[:k]) if c.kind == "container"
                     and (has_words(c) or local(c.el) not in ("p", "list"))), None)
        if prev is None and local(b.parent.el) in ("closer", "opener"):
            # a closer's first line runs on from the paragraph before it
            outer = b.parent.parent.children
            j = next(i for i, c in enumerate(outer) if c is b.parent)
            prev = next((c for c in reversed(outer[:j]) if c.kind == "container"), None)
        if prev is not None and local(prev.el) in ("opener", "sp"):
            # a speech's last paragraph (CCEL can end a speech mid-sentence
            # and carry the rest on in a plain paragraph after it)
            prev = next((c for c in reversed(prev.children) if c.kind == "container"
                         and (local(prev.el) != "sp" or local(c.el) == "p")), prev)
        into_item = False
        if prev is not None and local(prev.el) == "list" and prev.el.get("rend") != "inline":
            # runs on into the list's last item: it moves into that item,
            # after the item's own text (and before anything set in it later)
            items = [c for c in prev.children if c.kind == "container" and
                     local(c.el) == "item"]
            if items:
                prev, into_item = items[-1], True
        run_in_head = prev is not None and local(prev.el) == "head" and \
            prev.el.getparent().get("type") in HEAD_MODE["run_in"]
        if prev is None or local(prev.el) not in ("p", "q", "item", "salute", "signed",
                                                  "dateline", "list") and not run_in_head:
            # the last block of the division before
            before = None
            if prev is None and b.parent.parent is not None:
                sibs = [c for c in b.parent.parent.children if c.kind == "container"]
                i = next((n for n, c in enumerate(sibs) if c is b.parent), 0)
                ps = [c for c in sibs[i - 1].children if c.kind == "container"
                      and local(c.el) == "p"] if i else []
                before = ps[-1] if ps else None
            if before is not None and not has_words(before):
                # the paragraph the review took out (margin matter set as a
                # note) was aligned this side of the break: nothing runs on
                log.append((f, "list", "blocks", "emptied by the review"))
                continue
            log.append((f, "skipped", f"merge at '{tok.orig}'", "no paragraph before it"))
            continue
        if into_item:
            detach(b, b.parent)
            append_block(prev, b)
        for x in (prev, b):
            if not x.el.get("{%s}id" % XML_NS):
                NOTE_SEQ["b"] = NOTE_SEQ.get("b", 0) + 1
                x.el.set("{%s}id" % XML_NS, f"rb{NOTE_SEQ['b']}")
        prev.el.set("next", "#" + b.el.get("{%s}id" % XML_NS))
        b.el.set("prev", "#" + prev.el.get("{%s}id" % XML_NS))
        b.el.set("change", "#review")
        if id(tok) in NO_SPACE_RUN_ON:
            b.el.set("rend", "run-on")
        log.append((f, "merge", "paragraph", f"joined to the previous one at '{tok.orig}'"))
    merge_lists(log)            # lists that a run-on paragraph kept apart


def collect_splits(struct, stream_index, log):
    splits = []
    for s in struct:
        at = s["at"]
        if at is None:
            continue
        tok = at[2]
        Sw = [x for x in s["S"] if x[1] == "w"]
        order = stream_index.get(id(tok), 0)
        tabs = [x[2] for x in s["S"] if x[1] == "m" and x[2].kind == "container"
                and local(x[2].el) == "table"]
        if tabs and len(tabs) == len(s["src_marks"]) and s["tgt_marks"] in ([], ["¶"]):
            # a table's reading the review runs into one sentence
            # (restructure checks that every one of its marks went)
            splits += [(tb, "tableinline", list(s["tgt_marks"]), order, s["label"])
                       for tb in tabs]
            continue
        if s["tgt_marks"] == ["+"] and not s["src_marks"]:
            labels = []
            if len(Sw) >= 2 and (ROMAN_RE.match(Sw[0][0]) and Sw[1][0] == "." or
                                 NUMERAL_RE.fullmatch(Sw[0][0]) and Sw[1][0] in ".)"):
                labels = [Sw[0][2], Sw[1][2]]
            splits.append((labels[0] if labels else tok, "+", labels, order, s["label"]))
        elif s["tgt_marks"] == ["+"] and s["src_marks"] in (["¶"], ["-"]):
            labels = []
            if len(Sw) >= 2 and NUMERAL_RE.fullmatch(Sw[0][0]) and Sw[1][0] in ".)":
                labels = [Sw[0][2], Sw[1][2]]
            kind = "+" if s["src_marks"] == ["¶"] else "renumber"
            splits.append((labels[0] if labels else tok, kind, labels, order, s["label"]))
        elif s["tgt_marks"] == ["-"] and s["src_marks"] in ([], ["¶"]):
            splits.append((tok, "-", [], order, s["label"]))
        elif s["tgt_marks"] == ["¶"] and s["src_marks"] == ["-"]:
            splits.append((tok, "unlist", [], order, s["label"]))
        elif s["tgt_marks"] == ["¶"] and not s["src_marks"]:
            if in_container(tok, ("closer", "signed", "trailer")) and \
                    not (SETTINGS["closer_plain"] and in_container(tok, ("signed",))):
                continue
            splits.append((tok, "¶", [], order, s["label"]))
        elif s["tgt_marks"] == [">"] and not s["src_marks"]:
            splits.append((tok, ">", [], order, s["label"]))
        elif s["tgt_marks"] == [">"] and s["src_marks"] == ["¶"]:
            splits.append((tok, "quote", [], order, s["label"]))
        elif s["tgt_marks"] == ["¶"] and s["src_marks"] == [">"]:
            # the review takes a quotation's opening lines out of it (CCEL set
            # a line of prose as the first line of the verse)
            splits.append((tok, "unquote", [], order, s["label"]))
        elif s["src_marks"] == ["¶"] and not s["tgt_marks"] and \
                in_container(tok, ("trailer",)):
            continue          # a trailer the review left out
        elif s["src_marks"] == ["¶"] and not s["tgt_marks"]:
            splits.append((tok, "merge", [], order, s["label"]))
        elif len(s["src_marks"]) > 1 and not s["tgt_marks"] and \
                all(m in ("¶", "-", "+") for m in s["src_marks"]):
            # several blocks run together: blocks the review deletes whole
            # (margin matter moved into a note) stay, emptied; every block
            # that keeps words runs on into the text before it (a word whose
            # case the review changed puts two joins in one cluster: CCEL's
            # centred "UNGODLY" in All of Grace, run into its sentence)
            joined = False
            for mk in (x for x in s["S"] if x[1] == "m"):
                blk = mk[2]
                ws = first_words(blk, 1) if blk.kind == "container" else []
                if ws and has_words(blk):
                    splits.append((ws[0], "merge", [], order, s["label"]))
                    joined = True
            if not joined:
                log.append((s["label"], "list", "blocks", "emptied by the review"))
        elif s["src_marks"] == ["H"] and not s["tgt_marks"]:
            # a printed division head the review runs on into the text
            # before it (the TCP made a sentence a heading)
            splits.append((tok, "headmerge", [], order, s["label"]))
        elif s["src_marks"] == ["-"] and not s["tgt_marks"]:
            # a printed list inside a paragraph that the review runs into
            # its sentence; else list nesting shown differently, kept as is
            lst = next((a for a in ancestors(tok) if local(a.el) == "list"), None)
            if lst is not None and lst.el.getparent() is not None and \
                    local(lst.el.getparent()) in ("p", "div"):
                splits.append((tok, "inline", [], order, s["label"]))
            continue
        elif s["src_marks"] == ["¶"] and not s["tgt_marks"] and \
                in_container(tok, ("trailer",)):
            continue
        else:
            log.append(("structure", "unresolved", str(s["src_marks"]),
                        str(s["tgt_marks"]) + " at " + (tok.orig or "")))
    return splits
