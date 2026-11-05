"""
Emphasis: italics the review removed or added.
"""

import teibuild  # noqa: F401  (puts colophon on sys.path)

from teitok import local  # noqa: E402

from teibuild.tokens import is_emph, new_container, relink  # noqa: E402


INLINE = {"hi", "seg", "q", "foreign", "name", "bibl", "term", "ref", "label"}


def apply_emphasis(d, tflags, log, f):
    """Compare italics with the review. A printed italic run (<hi>) with any
    word set roman in the review becomes ana="#print-only"; words italic in
    the review but roman in the edition are wrapped in <hi ana=
    "#edition-only">; a reading that is partly italic gets <hi> in its reg."""

    def want(t):
        """'i' italic, 'r' roman, 'x' no opinion, '' no target words;
        or 'm' for a reading whose words differ."""
        if t.kind not in ("word", "punct", "group"):
            return ""
        if "tflags" in t.extra:
            fl = t.extra["tflags"]
        elif t.kind == "group":
            fl = [x for c in t.children for x in sorted(tflags.get(id(c), []))]
        else:
            fl = sorted(tflags.get(id(t), []))
        vals = {("x" if not isinstance(v, bool) else "i" if v else "r") for _, v in fl}
        vals.discard("x")
        if not vals:
            return "x" if fl else ""
        if len(vals) == 1:
            return vals.pop()
        t.extra["reg_italic"] = [v is True for _, v in fl]
        return "m"

    def leaves(t, skip_notes=True):
        for c in t.children or []:
            if c.kind == "container":
                if skip_notes and local(c.el) == "note":
                    continue
                yield from leaves(c, skip_notes)
            elif c.kind in ("word", "punct", "group"):
                yield c

    # 1. printed italics the review set (partly) roman
    def walk_hi(t):
        for c in t.children or []:
            if c.kind != "container":
                continue
            if is_emph(c) and not c.el.get("ana"):
                ws = [want(x) for x in leaves(c)]
                if any(w in ("r", "m") for w in ws):
                    c.el.set("ana", "#print-only")
                    c.el.set("change", "#review")
                    log.append((f, "italic", "printed italic", "set roman"))
            walk_hi(c)
    walk_hi(d)

    def plain_leaves(t):
        for c in t.children or []:
            if c.kind == "container":
                if local(c.el) == "note":
                    continue
                if is_emph(c) and c.el.get("ana") != "#print-only":
                    continue
                yield from plain_leaves(c)
            elif c.kind in ("word", "punct", "group"):
                yield c

    # 2. italics the edition adds
    def walk_add(t, italic):
        kids = t.children or []
        need = []
        for c in kids:
            if c.kind == "container":
                if local(c.el) == "note":
                    need.append("break")
                    continue
                # words already under a printed italic inside c need nothing
                inner = [want(x) for x in plain_leaves(c)]
                if not inner and any(True for _ in leaves(c)):
                    need.append("neutral")
                    continue
                c_it = italic or (is_emph(c) and c.el.get("ana") != "#print-only")
                inline = local(c.el) in INLINE and not (
                    local(c.el) == "q" and local(c.el.getparent()) == "div")
                if inline and not c_it and inner and \
                        all(w in ("i", "x", "") for w in inner) and "i" in inner:
                    need.append("wrap")
                else:
                    need.append("break" if inner else "neutral")
            elif c.kind in ("word", "punct", "group"):
                w = want(c)
                if w == "m" and italic:
                    need.append("break")
                elif w == "i" and not italic:
                    need.append("wrap")
                elif w in ("x", "") and not italic:
                    need.append("neutral")
                else:
                    need.append("break")
            elif c.kind in ("space", "noise"):
                need.append("neutral")
            else:
                need.append("break")                  # anchors, notes, pb ...
        runs, k = [], 0
        while k < len(kids):
            if need[k] != "wrap":
                k += 1
                continue
            e = k
            while e + 1 < len(kids) and need[e + 1] in ("wrap", "neutral"):
                e += 1
            while need[e] != "wrap":
                e -= 1
            runs.append((k, e))
            k = e + 1
        for a, b in reversed(runs):
            h = new_container("hi")
            h.el.set("ana", "#edition-only")
            h.el.set("change", "#review")
            h.children = kids[a:b + 1]
            relink(h)
            kids[a:b + 1] = [h]
            h.parent = t
            log.append((f, "italic", "roman in print", "set italic"))
        relink(t)
        for c in kids:
            if c.kind == "container":
                walk_add(c, italic or (is_emph(c) and c.el.get("ana") != "#print-only"))
    walk_add(d, False)
