"""
Spacing: the review's spaces between words the edition keeps apart.
"""

import teibuild  # noqa: F401  (puts colophon on sys.path)

from teitok import Tok, local  # noqa: E402

from teibuild.tokens import View, contains, relink  # noqa: E402


def is_changed(t):
    return t.kind == "group" or (t.kind in ("word", "punct") and t.resp == "#editor")


def between_blocks(x):
    """Whitespace between two blocks (in a division, list ...), not inside
    one: a run-on join there is the block's @rend, not a spacing choice."""
    par = x.parent
    return isinstance(par, View) or par is None or par.el is None or \
        local(par.el) in ("div", "list", "body", "front", "back", "text", "group",
                          "lg", "sp", "closer", "opener", "epigraph",
                          "table", "row")      # between cells: the reading joins them


def apply_spacing(root_tok, order, sp, log, label, skip_notes=True, owner=None):
    """order: target indices in reading order with their block number,
    [(j, block)]; sp[j]: space before target word j in the review.
    Compare every pair of neighbouring review words owned by different
    tokens with the space between those tokens in the source, and record
    each difference as a spacing decision."""
    leaves = []

    def walk(t):
        for c in t.children or []:
            if c.kind == "container":
                if skip_notes and local(c.el) == "note":
                    leaves.append(c)        # a note between words: not a space
                    continue
                walk(c)
            else:
                leaves.append(c)
    walk(root_tok)
    pos = {id(x): i for i, x in enumerate(leaves)}
    j2leaf = {}
    in_group = {id(c): x for x in leaves if x.kind == "group" for c in x.children}
    for j, tok in (owner or {}).items():
        leaf = tok if id(tok) in pos else in_group.get(id(tok))
        if leaf is not None:
            j2leaf[j] = leaf
    for x in leaves:
        if x.kind in ("word", "punct", "group"):
            js = x.extra.get("tidx")
            if js is None and x.kind == "group":
                js = [j for c in x.children for j in c.extra.get("tidx", [])]
            for j in js or []:
                j2leaf[j] = x
    for (j, blk), (j2, blk2) in zip(order, order[1:]):
        if blk != blk2:
            continue
        a, b = j2leaf.get(j), j2leaf.get(j2)
        if a is None or b is None or a is b or id(a) not in pos or id(b) not in pos:
            continue
        ia, ib = pos[id(a)], pos[id(b)]
        if ia >= ib:
            continue
        # a table read into its sentence goes column by column, not in
        # document order: the space between two of its cells is the
        # extractor's join, not the source's whitespace (inline_cell)
        ca, cb = inline_cell(a), inline_cell(b)
        if (ca is not None or cb is not None) and ca is not cb:
            continue
        between = leaves[ia + 1:ib]
        # indentation between two words' elements renders as a space too
        spaces = [x for x in between if x.kind == "space" or
                  (x.kind == "noise" and "".join(p for p in x.pieces if isinstance(p, str)).strip() == "")
                  or (x.kind == "spacing" and x.reg == " ")]     # the machine's (page_break_spaces)
        want = sp[j2]
        if not want:
            # whitespace between two blocks is not removed here: a block run
            # on without a space says so itself (@rend="run-on")
            if spaces and all(between_blocks(x) for x in spaces):
                continue
            spaces = [x for x in spaces if not between_blocks(x)]
        # a reading may carry its own space (a spaced dash, DASH = " — ")
        padded = (a.kind in ("word", "punct") and (a.reg or "").endswith(" ")) or \
            (b.kind in ("word", "punct") and (b.reg or "").startswith(" "))
        if want == (bool(spaces) or padded):
            continue
        if want and b.extra.get("midword"):
            continue            # b's reading starts inside a word; its space is in it
        if want:
            if is_changed(b) and b.extra.get("tidx", [None])[0] == j2:
                pad(b, lead=" ")
            elif is_changed(a) and (a.extra.get("tidx") or [None])[-1] == j:
                pad(a, trail=" ")
            else:
                s = Tok("spacing", [""])
                s.reg = " "
                par = a.parent
                k = next(i for i, c in enumerate(par.children) if contains(c, a))
                par.children.insert(k + 1, s)
                relink(par)
            log.append((label, "spacing", "(none)", "space"))
        else:
            for x in spaces:
                x.kind = "spacing"
                x.reg, x.resp = "", "#editor"
            log.append((label, "spacing", "space", "(none)"))


def inline_cell(t):
    """The table cell that holds token t, or None. (Whether the review reads
    its table into the sentence is not yet marked when spacing is applied;
    a table set as lines or a list puts its cells in blocks of their own.)"""
    while t is not None:
        if t.kind == "container" and local(t.el) == "cell":
            return t.el
        t = t.parent
    return None


def pad(t, lead="", trail=""):
    l0, t0 = t.extra.get("pad", ("", ""))
    t.extra["pad"] = (l0 + lead, t0 + trail)
    t.reg = lead + (t.reg or "") + trail
