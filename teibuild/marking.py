"""
Marking the built tree: small-caps phrases, openings in capitals,
diagram lists.
"""

import re
from lxml import etree

import teibuild  # noqa: F401  (puts colophon on sys.path)

from teitok import T, local  # noqa: E402

from teibuild import settings as S  # noqa: E402


SC_CONTAINERS = ("p", "l", "item", "head", "cell", "hi", "q", "seg", "label")


SC_READING = {"reg", "expan", "corr"}           # the printed text is the other one


SC_SILENT = {"note", "anchor", "pb", "lb", "milestone", "fw"}


def smallcaps_phrases(root, phrases):
    """SMALLCAPS_PHRASES: wrap each phrase's words in
    seg[@rend="smallcaps"][@ana="#edition-only"]. An entry is the printed text
    with a little context around it and the small-capital words in brackets
    ("salvation is [all of grace], which"; ^ and $ for the block's start and
    end: "^[UNGODLY]$"); it is matched in one block (or one italic run)
    without regard to case or spacing, and must be found exactly once and
    cover whole elements (a <choice> is not split)."""
    if not phrases:
        return

    def printed(el):
        """The printed text of an element: a choice's orig (abbr, sic), not
        its readings; notes, anchors and comments add nothing."""
        if not isinstance(el.tag, str) or local(el) in SC_SILENT:
            return ""
        if local(el) == "choice":
            return "".join(printed(c) for c in el if local(c) not in SC_READING)
        return (el.text or "") + "".join(printed(c) + (c.tail or "") for c in el)

    def atoms(el):
        """el's content: [text or element], text from el.text and the tails."""
        items = [el.text or ""]
        for c in el:
            items += [c, c.tail or ""]
        return items

    def norm(items):
        """The items' printed text, lowercase, spaces collapsed and trimmed,
        between \\x02 and \\x03 (^ and $), and for each character the
        (item, offset) it came from."""
        chars, where = [], []
        for i, it in enumerate(items):
            t = it if isinstance(it, str) else printed(it)
            for o, ch in enumerate(t):
                ch = " " if ch.isspace() else ch.lower()
                if ch == " " and (not chars or chars[-1] == " "):
                    continue
                chars.append(ch)
                where.append((i, o))
        while chars and chars[-1] == " ":
            chars.pop()
            where.pop()
        return "\x02" + "".join(chars) + "\x03", [(-1, -1)] + where + [(-1, -1)]

    blocks = [el for el in root.iter(*[T + n for n in SC_CONTAINERS])]
    for entry in phrases:
        m = re.fullmatch(r"(.*)\[(.+)\](.*)", entry, re.S)
        if not m:
            raise ValueError(f"SMALLCAPS_PHRASES: no [words] in {entry!r}")
        before, words, after = (" ".join(x.lower().split()) for x in m.groups())
        before = before + " " if m.group(1).endswith(" ") and before else before
        after = " " + after if m.group(3).startswith(" ") and after else after
        before = "\x02" + before[1:] if before.startswith("^") else before
        after = after[:-1] + "\x03" if after.endswith("$") else after
        found = []
        for el in blocks:
            items = atoms(el)
            text, where = norm(items)
            k = text.find(before + words + after)
            while k >= 0:
                found.append((el, items, where, k + len(before)))
                k = text.find(before + words + after, k + 1)
        if len(found) != 1:
            raise ValueError(f"SMALLCAPS_PHRASES: {entry!r} found {len(found)} times")
        el, items, where, start = found[0]
        (i, o), (j, q) = where[start], where[start + len(words) - 1]
        for idx, off, at_end in ((i, o, False), (j, q, True)):
            if not isinstance(items[idx], str):
                n = len(printed(items[idx]))
                if (at_end and off != n - 1) or (not at_end and off != 0):
                    raise ValueError(f"SMALLCAPS_PHRASES: {entry!r} splits an element")
        seg = etree.Element(T + "seg")
        seg.set("rend", "smallcaps")
        seg.set("ana", "#edition-only")
        # the items before, inside and after the phrase
        head, inner, tail = items[:i], [], []
        if isinstance(items[i], str):
            head.append(items[i][:o])
            first = items[i][o:]
        else:
            first = items[i]
        if i == j:
            if isinstance(first, str):
                inner, tail = [first[:q - o + 1]], [first[q - o + 1:]]
            else:
                inner = [first]
        else:
            inner = [first] + items[i + 1:j]
            last = items[j]
            if isinstance(last, str):
                inner.append(last[:q + 1])
                tail.append(last[q + 1:])
            else:
                inner.append(last)
        tail += items[j + 1:]
        for c in list(el):
            c.tail = None
            el.remove(c)

        def fill(parent, seq):
            parent.text, prev = None, None
            for it in seq:
                if isinstance(it, str):
                    if prev is None:
                        parent.text = (parent.text or "") + it
                    else:
                        prev.tail = (prev.tail or "") + it
                else:
                    parent.append(it)
                    prev = it
        fill(seg, inner)
        fill(el, head + [seg] + tail)


OPENING_SKIP = {"pb", "lb", "milestone", "fw", "note", "anchor", "label", "gap"}


def opening_smallcaps(blocks, root, skip=()):
    """OPENING_SMALLCAPS: the first word of each division, printed in capitals
    after a drop cap (GOD, AND, COnsider), set in small capitals:
    seg[@rend="smallcaps"][@type="opening"] around it. `blocks` are the first
    elements of each division (a layout file's parts); the first <p> in them
    is the opening paragraph. Every printed division is looked at too (Gouge's
    sections, inside a layout file: "THE first clause"): its opening block, if
    that is a <p>, into a brace that opens it, outside SKIP_DIVISIONS (`skip`).
    A word printed otherwise is left alone."""
    def first_p(els):
        for el in els:
            p = el if local(el) == "p" else el.find(f".//{T}p")
            if p is not None:
                return p
        return None

    def opening_p(div):
        for c in div:
            if not isinstance(c.tag, str) or local(c) in OPENING_SKIP | {
                    "head", "epigraph", "argument", "opener"}:
                continue
            # not a scripture text set as an epigraph ("EPHES. 6. 7. With")
            if local(c) != "p" or c.get("rend") == "epigraph" or re.match(
                    r"\W*[A-Z]+\.\s*\d", "".join(c.itertext())):
                return None
            return c
        return None

    def caps(word):
        w = word.replace("ſ", "s")
        return len(w) > 1 and w[0].isupper() and w[1].isupper()

    def wrap_text(parent, attr, owner, index):
        """Wrap the first letter word of parent.text/.tail; True if wrapped,
        False if the text holds a word printed otherwise, None if no word."""
        s = getattr(parent, attr) or ""
        m = re.search(r"[A-Za-zſ][A-Za-zſ'’-]*", s)
        if not m:
            return None
        if not caps(m.group()):
            return False
        seg = etree.Element(T + "seg")
        seg.set("rend", "smallcaps")
        seg.set("type", "opening")
        seg.text, seg.tail = m.group(), s[m.end():]
        setattr(parent, attr, s[:m.start()])
        owner.insert(index, seg)
        return True

    def walk(el):
        r = wrap_text(el, "text", el, 0)
        if r is not None:
            return r
        for c in list(el):
            n = local(c)
            if n == "choice":
                orig = c.find(T + "orig")
                word = "".join((orig if orig is not None else c).itertext())
                if not caps(word):
                    return False
                seg = etree.Element(T + "seg")
                seg.set("rend", "smallcaps")
                seg.set("type", "opening")
                seg.tail, c.tail = c.tail, None
                el.replace(c, seg)
                seg.append(c)
                return True
            if n == "seg" and c.get("type") == "opening":
                return True
            if n in ("hi", "seg", "table", "row", "cell"):
                r = walk(c)
                if r is not None:
                    return r
            elif n not in OPENING_SKIP:
                return False
            r = wrap_text(c, "tail", el, list(el).index(c) + 1)
            if r is not None:
                return r
        return None

    done = 0
    for els in blocks:
        p = first_p(els)
        if p is not None and walk(p):
            done += 1
    for div in root.iter(T + "div"):
        if any(a.get("type") in skip or local(a) in skip
               for a in (div, *div.iterancestors())):
            continue
        p = opening_p(div)
        if p is not None and walk(p):
            done += 1
    return done


def mark_diagrams(root):
    """DIAGRAM_LISTS: list/@rend="diagram" on each list the book names."""
    if S.DIAGRAM_LISTS:
        for lst in S.DIAGRAM_LISTS(root):
            lst.set("rend", "diagram")
    if S.PARALLEL_TABLES:
        for pair in S.PARALLEL_TABLES(root):
            assert len(pair) == 2, "PARALLEL_TABLES gives pairs of tables"
            for k, tb in enumerate(pair):
                tb.set("rend", "parallel")
                tb.set("n", str(k + 1))
