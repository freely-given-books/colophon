"""
Small helpers on the token tree (teitok.Tok): containment, parents,
new containers.
"""

from lxml import etree

import teibuild  # noqa: F401  (puts colophon on sys.path)

from teitok import T, Tok, local  # noqa: E402

from teibuild.settings import XML_NS  # noqa: E402


def ancestors(tok):
    """Container tokens above tok (the element-less root is left out)."""
    a = []
    p = tok.parent
    while p is not None:
        if p.el is not None:
            a.append(p)
        p = p.parent
    return a


def in_container(tok, names):
    return any(local(a.el) in names for a in ancestors(tok))


class View:
    """A run of TEI parts (divisions and loose blocks) aligned as one unit
    with one reviewed file: the layout-mode stand-in for a division."""
    kind = "container"

    def __init__(self, children, el):
        self.children = children
        self.el = el
        self.extra = {}
        self.parent = None


def is_emph(t):
    return t.kind == "container" and local(t.el) == "hi" and t.el.get("rend") != "sup"


def contains(ct, tok):
    if ct is tok:
        return True
    if ct.kind in ("container", "group") and ct.children:
        return any(contains(c, tok) for c in ct.children)
    return False


def new_container(tag, like=None):
    el = etree.Element(T + tag)
    if like is not None:
        for k, v in like.attrib.items():
            if k != "{%s}id" % XML_NS:      # the split-off part is a new element
                el.set(k, v)
    t = Tok("container", el=el)
    t.children = []
    return t


def relink(ct):
    if isinstance(ct, View):
        return          # a layout file's parts keep their own divisions as parents
    for k, c in enumerate(ct.children):
        c.parent, c.idx = ct, k


def has_words(t):
    """Whether a token (or anything in a container) has text."""
    if t.kind in ("word", "punct"):
        return bool(t.reg if t.reg is not None else t.orig)
    return t.kind in ("container", "group") and any(has_words(c) for c in t.children or [])
