#!/usr/bin/env python3
"""
thml_to_tei.py: a CCEL ThML file as TEI in the subset the pipeline reads.

A ThML file of our own reads the same way: a transcription made from scans
(Boston's Crook in the Lot, from McMillan's Whole Works), with a publisherID
other than "ccel"; the header then names its DC.Publisher and printSourceInfo
instead of CCEL.

CCEL (ccel.org) publishes its texts as ThML, an HTML-like XML. A book's
untouched ThML is its provenance, as the TCP file is for an EEBO book
(source/<id>.thml.xml); the tools read it through sources.load(), which
converts it with this module in memory, so there is no intermediate file.

  ThML                         TEI
  div1                         div[@type="chapter"][@n], numbered in order
  div1 type="Work"             unwrapped: its div2s are the chapters (Owen)
  div2, div3 ... inside it     div[@type="section"][@n], numbered per parent
  div1 "Title Page"            front/titlePage (docTitle, byline/docAuthor,
  (or type="Titlepage")        epigraph; a page of p.h1-h4 lines: title
                               lines, then the "By ..." lines as byline)
  div1 "Contents", "Indexes"   div[@type="contents"], div[@type="index"]
                               (CCEL's own apparatus; SKIP_DIVISIONS)
  h1-h4 (first in a div)       head
  h1-h4 after the text began   signed (at the end of the div) or
                               p[@rend="center"]
  p                            p (@class Centered or text-align:center
                               -> @rend="center")
  p opening with a small-caps  sp/speaker + p (CCEL's dialogue labels,
  "Name:" (span.sc)            "Christian:"; as a TCP text encodes them)
  blockquote                   quote (its p's kept)
  verse / l                    quote / lg / l
  argument                     argument/p[@rend="inset"] (a chapter's summary)
  p.intro (+ "Sections.")      argument/p[@rend="inset"] (Calvin's section lists)
  p.introHead (other)          head (a chapter's title under its number)
  note                         note[@place="foot"] (a note's one p unwrapped)
  pb                           pb[@n] (the printed edition CCEL followed)
  ul / ol, li                  list, item (CCEL's indexes)
  span.sc, or font-variant:small-caps style (small capitals)
                               seg[@rend="smallcaps"]
  br                           lb
  i / em, b / strong           hi[@rend="italic"] / hi[@rend="bold"]
  scripRef                     ref[@type="scripture"][@cRef] (OSIS reference)
  ThML ids                     @xml:id ccel-<id>

The text itself is kept exactly, straight quotes and "--" included: the
machine pass records any typographic change (TYPOGRAPHY in editorial.py).
CCEL texts carry no line information, so the TEI is paragraph-faithful,
not line-faithful; the header says so. Some (Owen) keep the page breaks of
the printed edition they follow, as pb.

  python3 thml_to_tei.py grace.thml.xml [out.xml]   # write the TEI, to look at
"""

import copy
import re
import sys
from pathlib import Path

from lxml import etree

NS = "http://www.tei-c.org/ns/1.0"
T = "{%s}" % NS
XML_NS = "http://www.w3.org/XML/1998/namespace"


def tei(tag, parent=None, text=None, **attrs):
    el = etree.Element(T + tag) if parent is None else etree.SubElement(parent, T + tag)
    if text:
        el.text = text
    for k, v in attrs.items():
        if v is not None:
            el.set("{%s}id" % XML_NS if k == "xml_id" else k, v)
    return el


def xid(el):
    i = el.get("id")
    return f"ccel-{i}" if i else None


def first(el, path):
    found = el.find(path)
    return " ".join("".join(found.itertext()).split()) if found is not None else None


INLINE = {"i": ("hi", "italic"), "em": ("hi", "italic"),
          "b": ("hi", "bold"), "strong": ("hi", "bold")}


def inline(src, dst):
    """Copy src's text and inline children into dst (text kept exactly)."""
    dst.text = src.text
    for c in src:
        if not isinstance(c.tag, str):
            continue                      # comments, processing instructions
        n = c.tag
        if n == "br":
            el = tei("lb", dst)
        elif n == "pb":
            el = tei("pb", dst, n=c.get("n"), xml_id=xid(c))
        elif n in INLINE:
            tag, rend = INLINE[n]
            el = tei(tag, dst, rend=rend)
            inline(c, el)
        elif n == "scripRef":
            osis = c.get("osisRef", "")
            el = tei("ref", dst, type="scripture",
                     cRef=osis.split(":", 1)[1] if ":" in osis else None)
            inline(c, el)
        elif n == "note":
            el = tei("note", dst, place="foot", n=c.get("n"), xml_id=xid(c))
            kids = [x for x in c if isinstance(x.tag, str)]
            if len(kids) == 1 and kids[0].tag == "p" and not (c.text or "").strip():
                inline(kids[0], el)     # a note of one paragraph: its text
            else:
                inline(c, el)
        elif n in ("span", "a", "font", "sup", "sub", "name", "added", "foreign", "cite"):
            el = tei("hi" if n in ("sup", "sub") else "seg", dst,
                     rend=n if n in ("sup", "sub") else
                     "smallcaps" if smallcaps(c) else None)
            inline(c, el)
        else:
            raise ValueError(f"ThML <{n}> inside a paragraph is not handled yet "
                             f"(id {c.get('id')})")
        el.tail = c.tail


def smallcaps(el):
    """CCEL's small capitals: span.sc, or (Goold's Owen) an inline
    font-variant:small-caps style."""
    return el.get("class") == "sc" or \
        re.search(r"font-variant:\s*small-caps", el.get("style") or "") is not None


def section_summary(src):
    """p.intro, and the p.introHead "Sections." over them (Beveridge's
    Calvin: each chapter's summary of its numbered sections)."""
    c = src.get("class")
    return c == "intro" or (c == "introHead" and
                            "".join(src.itertext()).strip().rstrip(".") == "Sections")


def in_summary(src, dst):
    """A plain paragraph between two of a chapter's section summaries is one
    of them that CCEL left unmarked (Calvin II.8, its "29.")."""
    k = len(dst) - 1
    while k >= 0 and dst[k].tag == T + "pb":
        k -= 1
    nxt = src.getnext()
    while nxt is not None and (not isinstance(nxt.tag, str) or nxt.tag == "pb"):
        nxt = nxt.getnext()
    return not src.get("class") and k >= 0 and dst[k].tag == T + "argument" and \
        nxt is not None and nxt.tag == "p" and nxt.get("class") == "intro"


def centred(src):
    return (src.get("class") or "").lower() == "centered" or \
        re.search(r"text-align:\s*center", src.get("style") or "") is not None


def speaker(src):
    """The span.sc "Name:" opening a dialogue paragraph, or None."""
    first = next((c for c in src if isinstance(c.tag, str)), None)
    if first is None or first.tag != "span" or first.get("class") != "sc" or \
            (src.text or "").strip() or len(first):
        return None
    return first if (first.text or "").strip().endswith(":") else None


def block(src, dst):
    """One ThML block element as TEI, appended to dst."""
    n = src.tag
    if n == "p" and speaker(src) is not None:
        span = speaker(src)
        sp = tei("sp", dst, xml_id=xid(src))
        tei("speaker", sp, span.text, xml_id=xid(span))
        sp[-1].tail = " "
        p = tei("p", sp, rend="center" if centred(src) else None)
        rest = copy.copy(src)
        rest.remove(rest[0])
        rest.text = (span.tail or "").lstrip()
        inline(rest, p)
    elif n == "p" and (section_summary(src) or in_summary(src, dst)):
        # a chapter's list of its sections (Beveridge's Calvin: "Sections."
        # and p.intro, one per section), gathered into one argument and set
        # off as Owen's summaries are: indented both sides
        # (a page break inside the list goes into it, so it stays one)
        k = len(dst) - 1
        while k >= 0 and dst[k].tag == T + "pb":
            k -= 1
        last = dst[k] if k >= 0 else None
        if last is not None and last.tag == T + "argument" and \
                not (last.tail or "").strip():
            arg = last
            for pb in list(dst)[k + 1:]:
                arg.append(pb)          # moves it (and its tail) inside
        else:
            arg = tei("argument", dst)
        inline(src, tei("p", arg, xml_id=xid(src), rend="inset"))
    elif n == "p" and src.get("class") == "introHead":
        # a chapter's title under its "CHAPTER 2." (Beveridge's Calvin)
        inline(src, tei("head", dst, xml_id=xid(src)))
    elif n == "p":
        p = tei("p", dst, xml_id=xid(src), rend="center" if centred(src) else None)
        inline(src, p)
    elif n == "blockquote":
        q = tei("quote", dst, xml_id=xid(src))
        blocks(src, q)
    elif n == "verse":
        q = tei("quote", dst, xml_id=xid(src))
        lg = tei("lg", q)
        lg.text = src.text
        for c in src:
            if not isinstance(c.tag, str):
                continue
            if c.tag != "l":
                raise ValueError(f"ThML <verse> holds <{c.tag}> (id {c.get('id')})")
            l_ = tei("l", lg, xml_id=xid(c))
            inline(c, l_)
            l_.tail = c.tail
    elif re.fullmatch(r"h[1-6]", n):
        h = tei("head", dst, xml_id=xid(src))
        inline(src, h)
    elif n == "pb":
        tei("pb", dst, n=src.get("n"), xml_id=xid(src))
    elif n in ("ul", "ol"):
        # (CCEL's indexes; SKIP_DIVISIONS leaves them out)
        lst = tei("list", dst, xml_id=xid(src))
        lst.text = src.text
        for c in src:
            if not isinstance(c.tag, str):
                continue
            if c.tag != "li":
                raise ValueError(f"ThML <{n}> holds <{c.tag}> (id {c.get('id')})")
            inline(c, tei("item", lst, xml_id=xid(c)))
            lst[-1].tail = c.tail
    elif n == "argument":
        # a chapter's summary (Owen's, under the chapter head), set off as
        # printed: indented both sides (the review's #block(inset: ...))
        p = tei("p", tei("argument", dst, xml_id=xid(src)), rend="inset")
        inline(src, p)
    elif re.fullmatch(r"div\d?", n):
        division(src, dst, "section", str(1 + sum(
            1 for c in dst if isinstance(c.tag, str) and c.tag == T + "div")))
    else:
        raise ValueError(f"ThML block <{n}> is not handled yet (id {src.get('id')})")


APPARATUS = {"contents": "contents", "indexes": "index", "index": "index"}


def division(d, parent, typ, n):
    """A ThML div (any level) as a TEI div, appended to parent."""
    typ = APPARATUS.get((d.get("title") or "").strip().lower(), typ)
    div = tei("div", parent, type=typ, n=n, xml_id=xid(d))
    blocks(d, div)
    # a heading after the text began is not the division's title: at the
    # end it is a signature (the Apology's "JOHN BUNYAN."), else centred
    # (a page break before the title is not text)
    kids = [c for c in div if isinstance(c.tag, str) and c.tag != T + "pb"]
    for k, c in enumerate(kids):
        if c.tag == T + "head" and any(x.tag != T + "head" for x in kids[:k]):
            if all(x.tag == T + "head" for x in kids[k:]):
                c.tag = T + "signed"
            else:
                c.tag = T + "p"
                c.set("rend", "center")
    return div


def blocks(src, dst):
    """src's block children as TEI in dst, the space between them kept."""
    dst.text = src.text
    for c in src:
        if not isinstance(c.tag, str):
            continue
        if (c.tag in ("a", "p") and not len(c) and not (c.text or "").strip()) or \
                c.tag in ("insertIndex", "hr"):
            # an empty link target or paragraph, CCEL's index marker, a rule
            # under a subtitle (Calvin's prefaces): only the space stays
            if len(dst):
                dst[-1].tail = (dst[-1].tail or "") + (c.tail or "")
            else:
                dst.text = (dst.text or "") + (c.tail or "")
            continue
        block(c, dst)
        dst[-1].tail = c.tail


def title_page(d, front):
    """A ThML "Title Page" div as front/titlePage: the first heading is the
    title, a "By" line and the heading after it the byline, a paragraph
    holding a scripture reference the epigraph, other lines subtitles."""
    tp = tei("titlePage", front, xml_id=xid(d))
    blocks = [c for c in d if isinstance(c.tag, str) and c.tag != "pb"]
    if blocks and all(c.tag == "p" and re.fullmatch(r"h[1-6]", c.get("class") or "")
                      for c in blocks):
        # a title page set line by line in p.h1-h4 (Owen): the lines before
        # the "By ..." line are the title, that line and the rest the byline
        doc, byline = tei("docTitle", tp), None
        for c in blocks:
            text = " ".join("".join(c.itertext()).split())
            if byline is None and text.lower().startswith("by "):
                byline = tei("byline", tp)
            if byline is None:
                el = tei("titlePart", doc, type="sub" if len(doc) else "main",
                         xml_id=xid(c))
                inline(c, el)
            else:
                line = tei("seg", byline, xml_id=xid(c))
                inline(c, line)
                line.tail = " "
        if byline is not None and len(byline):
            byline[-1].tail = None
        return
    byline = None
    for c in blocks:
        text = " ".join("".join(c.itertext()).split())
        if re.fullmatch(r"h[1-6]", c.tag) and tp.find(T + "docTitle") is None:
            el = tei("titlePart", tei("docTitle", tp), type="main", xml_id=xid(c))
        elif c.tag == "p" and text.lower() == "by":
            byline = tei("byline", tp, xml_id=xid(c))
            inline(c, byline)
            continue
        elif re.fullmatch(r"h[1-6]", c.tag) and byline is not None:
            el = tei("docAuthor", byline, xml_id=xid(c))
            byline[-1].tail = None
            if byline.text:
                byline.text = byline.text + " "
            byline = None
        elif c.tag == "p" and c.find(".//scripRef") is not None:
            el = tei("p", tei("epigraph", tp), xml_id=xid(c))
        else:
            el = tei("titlePart", tp, type="sub", xml_id=xid(c))
        inline(c, el)


def header(thml, path):
    h = thml.find("ThML.head")
    title = first(h, ".//DC.Title") or first(h, ".//title") or Path(path).stem
    author = first(h, ".//DC.Creator[@sub='Author']") or first(h, ".//DC.Creator")
    hdr = tei("teiHeader")
    fd = tei("fileDesc", hdr)
    ts = tei("titleStmt", fd)
    tei("title", ts, title)
    if author:
        tei("author", ts, author)
    ps = tei("publicationStmt", fd)
    # a ThML file of our own (a transcription made from scans, kept in ThML so
    # it reads like a CCEL text) names its own publisher; CCEL's are "ccel"
    ccel = (first(h, ".//publisherID") or "ccel").lower() == "ccel"
    publisher = first(h, ".//DC.Publisher") or "Christian Classics Ethereal Library"
    tei("publisher", ps, publisher)
    for tag, path_ in (("date", ".//DC.Date"), ("idno", ".//bookID")):
        v = first(h, path_)
        if v:
            tei(tag, ps, v)
    tei("p", tei("availability", ps), first(h, ".//DC.Rights") or "Public domain.")
    sd = tei("sourceDesc", fd)
    bibl = tei("bibl", sd)
    tei("title", bibl, title)
    if author:
        tei("author", bibl, author)
    src_info = first(h, ".//printSourceInfo/published") or first(h, ".//DC.Source")
    if src_info:
        tei("note", bibl, src_info)
    if ccel:
        tei("note", bibl, f"Converted from the CCEL ThML file {Path(path).name} by "
            "colophon's thml_to_tei.py. The text is kept exactly; CCEL gives no page "
            "or line information, so this transcription is paragraph-faithful, not "
            "line-faithful.")
    else:
        comments = first(h, ".//generalInfo/comments")
        tei("note", bibl, f"Converted from the ThML file {Path(path).name} by "
            "colophon's thml_to_tei.py. The text is kept exactly; it is "
            "paragraph-faithful, not line-faithful." + (f" {comments}" if comments else ""))
    ed = tei("encodingDesc", hdr)
    tei("p", tei("projectDesc", ed),
        "ThML from the Christian Classics Ethereal Library (ccel.org), "
        "converted to TEI P5 for the Freely Given Books pipeline." if ccel else
        f"A ThML transcription ({publisher}), converted to TEI P5 for the "
        "Freely Given Books pipeline.")
    lu = tei("langUsage", tei("profileDesc", hdr))
    tei("language", lu, "English", ident=first(h, ".//DC.Language") or "en")
    rd = tei("revisionDesc", hdr)
    tei("change", rd, f"Converted from {'CCEL ' if ccel else ''}ThML ({Path(path).name}).")
    return hdr


def top_divisions(body):
    """The body's divisions, a div1 of type "Work" (the whole book, its
    parts in div2s) unwrapped."""
    for d in body:
        if not isinstance(d.tag, str):
            continue
        if not re.fullmatch(r"div\d", d.tag):
            raise ValueError(f"ThML.body holds <{d.tag}>; expected div1 ...")
        if (d.get("type") or "").lower() == "work":
            for c in d:
                if not isinstance(c.tag, str) or c.tag == "pb":
                    continue
                if not re.fullmatch(r"div\d", c.tag):
                    raise ValueError(f"ThML Work div holds <{c.tag}> (id {c.get('id')})")
                yield c
        else:
            yield d


def convert(path):
    """The TEI (an lxml ElementTree) for a ThML file."""
    parser = etree.XMLParser(load_dtd=False, resolve_entities=False, no_network=True)
    thml = etree.parse(str(path), parser).getroot()
    root = etree.Element(T + "TEI", nsmap={None: NS})
    root.append(header(thml, path))
    text = tei("text", root)
    front = None
    body = tei("body", text)
    n = 0
    for d in top_divisions(thml.find("ThML.body")):
        title = (d.get("title") or "").strip().rstrip(".")
        if title.lower() == "title page" or (d.get("type") or "").lower() == "titlepage":
            if front is None:
                front = etree.Element(T + "front")
                text.insert(0, front)
            title_page(d, front)
            continue
        apparatus = (d.get("title") or "").strip().lower() in APPARATUS
        n += 0 if apparatus else 1
        division(d, body, "chapter", None if apparatus else str(n))
    return etree.ElementTree(root)


def main():
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    tree = convert(sys.argv[1])
    out = etree.tostring(tree, xml_declaration=True, encoding="UTF-8", pretty_print=False)
    if len(sys.argv) > 2:
        Path(sys.argv[2]).write_bytes(out)
    else:
        sys.stdout.buffer.write(out)


if __name__ == "__main__":
    main()
