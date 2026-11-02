"""
A book's source transcription, whatever form it came in, as TEI.

  source/<ID>.tcp.xml     EEBO-TCP transcription (TEI already)
  source/<id>.thml.xml    CCEL ThML, converted in memory (thml_to_tei.py)

The untouched file is the provenance; every tool that reads the source
(build_tei.py, tei_extract.py on the source, tcp_structure.py, verify.py)
goes through load(), so no converted copy has to be kept.
"""

import re
from pathlib import Path

from lxml import etree

PATTERNS = ("*.tcp.xml", "*.thml.xml")


def find(src_dir):
    """The source file in a book's source/ folder, or None."""
    for pat in PATTERNS:
        hit = next(iter(sorted(Path(src_dir).glob(pat))), None)
        if hit is not None:
            return hit
    return None


def kind(path):
    return "thml" if str(path).endswith(".thml.xml") else "tcp"


def load(path):
    """An lxml ElementTree of the source as TEI, with any supplement
    (<stem>.supplied.xml beside it) spliced in."""
    if kind(path) == "thml":
        import thml_to_tei
        tree = thml_to_tei.convert(path)
    else:
        tree = etree.parse(str(path))
    sup = supplement(path)
    if sup is not None:
        sup = etree.parse(str(sup))
        splice(tree, sup)
        correct(tree, sup)
    return tree


# ---------------------------------------------------------------------------
# Supplements: text the transcription lacks (pages missing from the copy it
# was made from), transcribed from another copy, and words it misread or left
# out (corrections), kept in their own file, so the source file stays
# untouched.  See Gouge's A68107.supplied.xml and Perkins' A09377.supplied.xml.
# ---------------------------------------------------------------------------

T = "{http://www.tei-c.org/ns/1.0}"
XML_ID = "{http://www.w3.org/XML/1998/namespace}id"


def supplement(path):
    p = Path(path)
    hit = p.with_name(p.name.split(".")[0] + ".supplied.xml")
    return hit if hit.exists() else None


def _page_after(el):
    """pb/@n of the first page break after el"""
    hit = el.xpath("following::t:pb[1]/@n", namespaces={"t": T[1:-1]})
    return hit[0] if hit else None


def _append_text(parent, text):
    if not text:
        return
    if len(parent):
        parent[-1].tail = (parent[-1].tail or "") + text
    else:
        parent.text = (parent.text or "") + text


def splice(tree, sup):
    """Put each supplement fill in at its gap (see the supplement's header):
    the gap's paragraph is split after the gap; a leading <seg> runs on in
    it, blocks follow it, divisions follow its division, and <rest/> takes
    the rest of the paragraph and the blocks after it.  Everything brought in
    carries @change pointing at a revisionDesc entry made from fill/desc."""
    root = tree.getroot()
    for fill in sup.getroot().iter(T + "fill"):
        cid = fill.get(XML_ID)
        gap = next((g for g in root.iter(T + "gap") if g.get("reason") == fill.get("gap")
                    and _page_after(g) == fill.get("pb")), None)
        if gap is None:
            raise SystemExit(f"supplement: no {fill.get('gap')} gap before page {fill.get('pb')}")
        para = gap.getparent()
        div = para.getparent()
        # the rest of the paragraph after the gap, and the blocks after it
        rest_text, gap.tail = gap.tail, None
        rest_nodes = []
        while gap.getnext() is not None:
            rest_nodes.append(gap.getnext())
            para.remove(gap.getnext())
        later = []
        while para.getnext() is not None:
            later.append(para.getnext())
            div.remove(para.getnext())
        rest = fill.find(".//" + T + "rest")
        block_at, div_at = para, div
        for el in [c for c in fill if isinstance(c.tag, str) and c.tag != T + "desc"]:
            el.set("change", "#" + cid)
            if el.tag == T + "seg":                  # runs on in the gap's paragraph
                gap.addnext(el)
            elif el.tag == T + "div":
                div_at.addnext(el)
                div_at = el
            else:
                block_at.addnext(el)
                block_at = el
        if rest is None:
            raise SystemExit("supplement: a fill needs <rest/>")
        holder = rest.getparent()
        before = rest.getprevious()
        tail = rest.tail
        holder.remove(rest)
        if before is not None:
            before.tail = (before.tail or "") + (rest_text or "")
        else:
            holder.text = (holder.text or "") + (rest_text or "")
        for n in rest_nodes:
            holder.append(n)
        _append_text(holder, tail)
        at = holder
        for b in later:
            at.addnext(b)
            at = b
        revision(root, cid, fill.findtext(T + "desc"))


def revision(root, cid, desc):
    """The revisionDesc entry an @change="#cid" points at."""
    hdr = root.find(T + "teiHeader")
    rd = hdr.find(T + "revisionDesc")
    if rd is None:
        rd = etree.SubElement(hdr, T + "revisionDesc")
    ch = etree.SubElement(rd, T + "change")
    ch.set(XML_ID, cid)
    ch.set("who", "#editor")
    ch.text = " ".join((desc or "").split())
    ch.tail = "\n"


def _page_texts(root, page):
    """(element, "text"|"tail") for every text node on printed page `page`:
    after <pb n=page> and before the next pb, notes included.  A page the
    print left unnumbered is named by its image instead (pb="tcp:3442:3")."""
    out, on = [], False
    for el in root.iter():
        element = isinstance(el.tag, str)
        if element and el.tag == T + "pb":
            on = page in (el.get("n"), el.get("facs"))
        elif on and element and el.text:
            out.append((el, "text"))
        if on and el.tail:
            out.append((el, "tail"))
    return out


def _flex(s):
    """s as a pattern in which any run of white space matches any other
    (the transcription breaks lines where the print did)."""
    return r"\s+".join(re.escape(w) for w in s.split()) if s.strip() else ""


def correct(tree, sup):
    """Apply the supplement's <corrections>: each <fix pb before tcp print
    after/> finds before+tcp+after in one text node of printed page pb (white
    space matching any white space; exactly once, or once as the whole of
    its text node) and sets the printed text
    there as <seg type="transcription" change="#id">, the transcription's
    reading kept in a comment inside it.  White space at either end of
    print stays outside the seg."""
    root = tree.getroot()
    for cs in sup.getroot().iter(T + "corrections"):
        cid = cs.get(XML_ID)
        for fix in cs.iter(T + "fix"):
            page, tcp, printed = fix.get("pb"), fix.get("tcp", ""), fix.get("print", "")
            before, after = fix.get("before", ""), fix.get("after", "")
            # the pieces in order, each a group: the white space between them
            # may be a line break in the transcription
            pat = "".join(f"({_flex(x)})" + (r"(\s*)" if i < 2 else "")
                          for i, x in enumerate((before, tcp, after)))
            hits = [(el, attr, m) for el, attr in _page_texts(root, page)
                    for m in re.finditer(pat, getattr(el, attr) or "")]
            if len(hits) > 1:
                # a letter or two can stand alone in its text node (a note's
                # stray "M" before a gap): the hit that is the whole node wins
                whole = [h for h in hits
                         if not (getattr(h[0], h[1]) or "").replace(h[2].group(0), "", 1).strip()]
                if len(whole) == 1:
                    hits = whole
            if len(hits) != 1:
                raise SystemExit(f"correction on p. {page}: {before!r} {tcp!r} {after!r} "
                                 f"found {len(hits)} times (needs exactly one)")
            el, attr, m = hits[0]
            text = getattr(el, attr)
            word = printed.strip()
            lead = printed[:len(printed) - len(printed.lstrip())]
            trail = printed[len(printed.rstrip()):]
            # an insertion takes the space the print sets around it; a
            # replacement keeps the transcription's spacing
            head = text[:m.start()] + m.group(1) + (m.group(2) if tcp else lead)
            tail = (m.group(4) if tcp else trail) + m.group(5) + text[m.end():]
            if not tcp and not trail and m.group(2):
                tail = m.group(2) + tail
            seg = etree.Element(T + "seg", type="transcription", change="#" + cid)
            seg.text = word
            c = etree.Comment(f" the transcription has {tcp!r}; " if tcp else
                              " not in the transcription; ")
            c.text += " ".join((fix.get("evidence") or "").split()) + " "
            seg.append(c)
            c.tail = None
            seg.tail = tail
            if attr == "text":
                el.text = head
                el.insert(0, seg)
            else:
                el.tail = head
                el.addnext(seg)
        if cs.find(T + "fix") is not None:
            revision(root, cid, cs.findtext(T + "desc"))
    return tree
