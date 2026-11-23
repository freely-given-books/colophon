#!/usr/bin/env python3
"""
Build an EPUB 3 straight from an (enriched) EEBO-TCP TEI file.

  python3 tei_epub.py EDITION.tei.xml OUT.epub --title T --author A \\
      [--front FRONT.html] [--cover COVER.jpg] [--css FILE ...] [--layer reg|orig]

One XHTML file per division (front matter, dedication, each chapter), text
rendered by tei_to_html.py. Notes are EPUB 3 footnotes (noteref + aside), so
readers that support it show them as pop-ups; others show them after the
chapter. Includes a nav document and an NCX table of contents for older
readers. Images referenced by the front matter are copied in, resolved
relative to the front-matter file.

Pages that are not in the TEI (a modern foreword, an appendix) come from
--before/--after: a .typ file is rendered with Typst's HTML export (its
footnotes become the same pop-up footnotes), a .html file is an XHTML
fragment. The contents are built from the h2/h3 headings of every page: an
h2 opens a top-level entry and the h3s after it nest under it.

Options:
  --front FILE       XHTML fragment for the front matter (its own file)
  --before FILE      extra page before the TEI divisions; repeatable, in order
  --after FILE       extra page after them; repeatable, in order
  --chapters DIR     a second edition (the Modern English): each division's text
                     from DIR/<its layout file>.typ (chapters/modern), rendered
                     with Typst's HTML export, in place of the TEI's (headings
                     at the levels the TEI's pages give them; outline levels,
                     OUTLINE_MARKS, set-off blocks, epigraphs, signatures,
                     speeches and stanzas in the Classic's markup: edition_blocks)
  --typst-root DIR   Typst --root for .typ pages (default: the folder above
                     the TEI's source/ folder, i.e. the book folder)
  --cover FILE       cover image; gets a cover page and cover-image property
  --css FILE         stylesheet, linked from every page; repeatable, in order
  --toc-depth N      deepest heading in the contents: 3 (default) or 4, for a
                     book whose sections (h4) should be listed too; keep the
                     contents to two levels (Apple Books misplaces the entries
                     after a third)
  --lang CODE        language of the text (default en)
  --identifier ID    dc:identifier (default: a UUID derived from title+author,
                     stable across rebuilds)
  --modified STAMP   dcterms:modified, e.g. 2026-09-30T00:00:00Z (default:
                     SOURCE_DATE_EPOCH if set, else now)
  plus --layer, --expand, --mark-supplied, --only-auto, --show-gaps as in
  tei_extract.py
"""

import argparse
import html
import os
import re
import subprocess
import tempfile
import uuid
import zipfile
from datetime import datetime, timezone
from pathlib import Path

from lxml import etree

import layout
from tei_to_html import (POINT_MARKS, add_text_args, divisions, epigraph_html, file_ident,
                         outline_para, renderer, xhtml)

MEDIA = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
         ".gif": "image/gif", ".svg": "image/svg+xml", ".css": "text/css",
         ".xhtml": "application/xhtml+xml", ".ncx": "application/x-dtbncx+xml"}
FIXED_TIME = (1980, 1, 1, 0, 0, 0)          # zip entry times: reproducible builds
CONTAINER = """<?xml version="1.0" encoding="UTF-8"?>
<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">
  <rootfiles>
    <rootfile full-path="OEBPS/content.opf" media-type="application/oebps-package+xml"/>
  </rootfiles>
</container>
"""


def esc(s):
    return html.escape(s, quote=True)


def modified_stamp(arg):
    if arg:
        return arg
    epoch = os.environ.get("SOURCE_DATE_EPOCH")
    t = datetime.fromtimestamp(int(epoch), timezone.utc) if epoch else datetime.now(timezone.utc)
    return t.strftime("%Y-%m-%dT%H:%M:%SZ")


def local_images(fragment, base):
    """src paths in a fragment that point at local files, resolved on disk."""
    out = []
    for src in re.findall(r'<img\b[^>]*\bsrc="([^"]+)"', fragment):
        if re.match(r"[a-z]+:", src) or src.startswith("/") or ".." in Path(src).parts:
            continue
        out.append((src, base / src))
    return out


def nest(heads):
    """[(file, id, level, text)] -> [(href, text, [children])]: each heading
    nests under the last heading of a higher level (h3s under the last h2,
    h4s under the last h3), or stands at the top when there is none."""
    top, stack, seen = [], [], set()
    for f, hid, lvl, text in heads:
        href = f if f not in seen else f"{f}#{hid}"
        seen.add(f)
        entry = (href, text, [])
        while stack and stack[-1][0] >= lvl:
            stack.pop()
        (stack[-1][1][2] if stack else top).append(entry)
        stack.append((lvl, entry))
    return top


def nav_doc(title, tree, landmarks, lang, css):
    def ol(entries):
        return "<ol>" + "".join(
            f'<li><a href="{h}">{esc(t)}</a>{ol(k) if k else ""}</li>' for h, t, k in entries) + "</ol>"
    marks = "".join(f'<li><a epub:type="{k}" href="{f}">{esc(t)}</a></li>'
                    for k, f, t in landmarks)
    body = [f'<nav epub:type="toc" id="toc" role="doc-toc"><h3>Contents</h3>{ol(tree)}</nav>',
            f'<nav epub:type="landmarks" id="landmarks" hidden="hidden"><ol>{marks}</ol></nav>']
    return xhtml(title, body, css, lang)


def ncx_doc(title, ident, tree):
    n = [0]

    def points(entries):
        out = ""
        for h, t, kids in entries:
            n[0] += 1
            out += (f'<navPoint id="np-{n[0]}" playOrder="{n[0]}"><navLabel><text>{esc(t)}'
                    f'</text></navLabel><content src="{h}"/>{points(kids)}</navPoint>')
        return out
    def deepest(entries):
        return 1 + max((deepest(k) for _, _, k in entries if k), default=0)
    depth = deepest(tree)
    doc = ('<?xml version="1.0" encoding="utf-8"?>\n'
           '<ncx xmlns="http://www.daisy.org/z3986/2005/ncx/" version="2005-1">'
           f'<head><meta name="dtb:uid" content="{esc(ident)}"/>'
           f'<meta name="dtb:depth" content="{depth}"/></head>'
           f"<docTitle><text>{esc(title)}</text></docTitle>"
           f"<navMap>{points(tree)}</navMap></ncx>\n")
    etree.fromstring(doc.encode("utf-8"))
    return doc


# A diagram (`#[ ... ] <diagram>`, a genealogy printed as a tree: the template's `diagram` in print)
# loses its label in Typst's HTML export, and its lists run together with the next diagram's. Each
# blank-line group of the labelled scope (one tree) is kept apart in a marked div, which
# diagram_lists turns into the ebook's `ul.diagram`, as tei_to_html writes it for the Classic.
DIAGRAM_SHOW = (
    '#show <diagram>: it => {\n'
    '  let groups = ((),)\n'
    '  for c in (if it.has("children") { it.children } else { (it,) }) {\n'
    '    if c.func() == parbreak { groups.push(()) } else { groups.last().push(c) }\n'
    '  }\n'
    '  html.elem("div", attrs: (class: "fgb-diagram"), for g in groups.filter(g => g.any(c => c.func() == list.item)) {\n'
    '    html.elem("div", attrs: (class: "fgb-tree"), g.join())\n'
    '  })\n'
    '}\n')


def diagram_lists(body):
    """Each marked tree's list becomes `ul.diagram`, its items' text out of Typst's <p>, the
    marking divs gone (the ebook's markup for a diagram, ebook.css)."""
    for d in list(body.iter("div")):
        if d.get("class") != "fgb-diagram":
            continue
        uls = [ul for t in d.findall("div") if t.get("class") == "fgb-tree" for ul in t.findall("ul")]
        for ul in uls:
            ul.set("class", "diagram")
            for li in ul.iter("li"):
                p = li.find("p")
                if p is None or li.index(p) != 0 or (li.text or "").strip():
                    continue
                kids, tail = list(p), p.tail or ""
                li.text = p.text
                li.remove(p)
                for k, c in enumerate(kids):
                    li.insert(k, c)
                if kids:
                    kids[-1].tail = (kids[-1].tail or "") + tail
                else:
                    li.text = (li.text or "") + tail
        parent, i = d.getparent(), d.getparent().index(d)
        for k, ul in enumerate(uls):
            ul.tail = None
            parent.insert(i + k, ul)
        if uls:
            uls[-1].tail = d.tail
        parent.remove(d)

# Typst's HTML export ignores pad, align and a block's inset and width (and drops any footnote
# inside pad or align): the page is compiled with each marked as a div (and a list set in, its
# indent), which edition_blocks turns into the markup the Classic ebook gives the same blocks
LAYOUT_SHOW = (
    '#let fgb-styled = [#set text(red); x].func()\n'
    '#show pad: it => html.elem("div", attrs: (class: "fgb-pad", "data-em": str(it.left.length.em)), it.body)\n'
    '#show align: it => html.elem("div", attrs: (class: "fgb-align", "data-align": repr(it.alignment)), it.body)\n'
    '#show v: it => html.elem("div", attrs: (class: "space"))\n'
    '#show block: it => if it.inset != (:) or it.width != auto {\n'
    '  let kids = if it.body.func() == [].func() { it.body.children } else { (it.body,) }\n'
    '  html.elem("div", attrs: (class: "fgb-block", "data-inset": repr(it.inset != (:)),\n'
    '    "data-set": repr(kids.any(c => c.func() == fgb-styled)), "data-breakable": repr(it.breakable)),\n'
    '    it.body)\n'
    '} else { it }\n'
    # the template's #speech (a hung paragraph) and #stanza (a paragraph not justified): marked
    # so the Modern ebook sets them as the Classic's p.speech and p.verse (every paragraph has
    # every field, so paragraphs are justified here and only #stanza's says otherwise)
    '#set par(justify: true)\n'
    '#show par: it => if it.hanging-indent != 0pt {\n'
    '  html.elem("div", attrs: (class: "fgb-speech"), it.body)\n'
    '} else if not it.justify {\n'
    '  html.elem("div", attrs: (class: "fgb-verse"), it.body)\n'
    '} else { it }\n'
    '#show enum: it => if it.indent != 0pt {\n'
    '  html.elem("div", attrs: (class: "fgb-enum", "data-indent": repr(it.indent)), it)\n'
    '} else { it }\n')


def _inner(el):
    """An element's content as XHTML."""
    return (html.escape(el.text, quote=False) if el.text else "") + "".join(
        etree.tostring(c, method="xml", encoding="unicode", with_tail=True) for c in el)


def _replace(el, markup):
    """Put the content of an XHTML fragment where el is (its tail kept)."""
    from lxml import html as lhtml
    new = lhtml.fragments_fromstring(markup) if markup.strip() else []
    lead = new.pop(0) if new and isinstance(new[0], str) else ""
    parent, i, tail = el.getparent(), el.getparent().index(el), el.tail or ""
    parent.remove(el)
    for k, n in enumerate(new):
        parent.insert(i + k, n)
    if new:
        new[-1].tail = (new[-1].tail or "") + tail
    else:
        lead += tail
    if lead:
        before = parent[i - 1] if i else None
        if before is None:
            parent.text = (parent.text or "") + lead
        else:
            before.tail = (before.tail or "") + lead


def _unwrap(el):
    """Replace a marker div by its content."""
    _replace(el, _inner(el))


def _paras(el):
    """A marker's paragraphs: its <p>s, or its inline content as one."""
    ps = [c for c in el if c.tag == "p"]
    return [_inner(c) for c in ps] if ps else ([_inner(el)] if _inner(el).strip() else [])


def edition_blocks(body, counts=None, subtitle=False):
    """The blocks of a Typst page (LAYOUT_SHOW's marked divs) as the Classic ebook sets
    them (tei_to_html): a paragraph at an outline level (#pad) p.levelN, or with
    OUTLINE_MARKS (counts, the book's point counts: mark_point) every paragraph its
    point's mark and data-level; a list set in (#set enum(indent)) ol.indent / ol.levelN;
    #block(inset) p.inset (a chapter summary, its text set smaller, p.inset summary);
    #align(center) p.center (under the page's title p.subtitle, when the Classic's
    page has one: subtitle), a bold block in it
    p.subtitle.strong, an unbreakable block in it (a verse and its reference) div.epigraph; #align(right) p.signature (the first of a run signature-first);
    #speech p.speech (SPEECH_BLOCKS); #stanza p.verse;
    small capitals span.smallcaps."""
    for sp in body.iter("span"):
        style = (sp.get("style") or "").replace(" ", "")
        if style == "font-variant-caps:small-caps":
            del sp.attrib["style"]
            sp.set("class", "smallcaps")
        elif style == "font-variant-caps:all-small-caps":     # #smallcaps(all: true)
            del sp.attrib["style"]
            sp.set("class", "smallcaps all")
    # a speech or stanza mark inside another block (a summary's #set par(justify: false)) is
    # a plain paragraph of that block
    for el in list(body.iter("div")):
        if el.get("class") in ("fgb-speech", "fgb-verse") and el.getparent() is not body:
            el.tag = "p"
            del el.attrib["class"]
    for el in list(body):
        cls = el.get("class") if el.tag == "div" else None
        if el.tag == "p" and counts is not None:
            _replace(el, outline_para(_inner(el), 0, counts))
        elif cls == "fgb-pad":
            lvl = layout.em_level(float(el.get("data-em")))
            _replace(el, "".join(outline_para(t, lvl, counts) for t in _paras(el)))
        elif cls == "fgb-enum":
            em = el.get("data-indent")
            c = "indent" if em.endswith("pt") else f"level{layout.em_level(float(em[:-2]))}"
            for lst in el:
                if lst.tag in ("ol", "ul"):
                    lst.set("class", f"{c} {lst.get('class')}" if lst.get("class") else c)
            _unwrap(el)
        elif cls == "fgb-align" and el.get("data-align") == "right":
            prev = el.getprevious()
            first = not (prev is not None and prev.tag == "p" and
                         "signature" in (prev.get("class") or "").split())
            c = "signature signature-first" if first else "signature"
            _replace(el, "".join(f'<p class="{c if k == 0 else "signature"}">{t}</p>'
                                 for k, t in enumerate(_paras(el))))
        elif cls == "fgb-align" and el.get("data-align") == "center":
            blk = [c for c in el if c.get("class") == "fgb-block"]
            prev = el.getprevious()
            if len(el) == 1 and blk and not (el.text or "").strip() and \
                    blk[0].get("data-breakable") == "false":
                # an epigraph (kept whole): its verse, and its reference (the shorter) before
                # or after it
                ps = [c for c in blk[0] if c.tag == "p"] or [blk[0]]
                by_len = sorted(ps, key=lambda c: len("".join(c.itertext())))
                ref = by_len[0] if len(ps) > 1 else None
                verse = next(c for c in ps if c is not ref)
                _replace(el, epigraph_html(_inner(ref).strip() if ref is not None else "",
                                           _inner(verse).strip(),
                                           ref is not None and ps.index(verse) < ps.index(ref)))
            elif len(el) == 1 and blk and not (el.text or "").strip():
                # a printed chapter title under the heading, bold
                t = re.sub(r"^<strong>(.*)</strong>$", r"\1", _inner(blk[0]).strip(), flags=re.S)
                _replace(el, f'<p class="subtitle strong">{t}</p>')
            else:
                # a centred line under the page's title is its subtitle (a layout file's)
                c = "subtitle" if subtitle and prev is not None and prev.getprevious() is None and \
                    re.fullmatch(r"h[1-6]", prev.tag) else "center"
                _replace(el, "".join(f'<p class="{c}">{t.strip()}</p>' for t in _paras(el)))
        elif cls in ("fgb-speech", "fgb-verse"):
            # a speech in dialogue (hung) or a stanza of verse, as tei_to_html sets them
            _replace(el, f'<p class="{cls[4:]}">{_inner(el).strip()}</p>')
        elif cls == "fgb-block" and el.get("data-inset") == "true":
            c = "inset summary" if el.get("data-set") == "true" else "inset"
            _replace(el, "".join(f'<p class="{c}">{t.strip()}</p>' for t in _paras(el)))
    for el in list(body.iter("div")):       # any other marked block: its content
        if (el.get("class") or "").startswith("fgb-"):
            _unwrap(el)


def typst_page(path, root, first_note, counts=None, subtitle=False):
    """Render a Typst file with Typst's HTML export; return (XHTML body
    fragment, number of notes). Typst's endnotes become EPUB 3 footnotes,
    numbered on from first_note. Its blocks are set as the Classic ebook sets them
    (edition_blocks; counts: the book's OUTLINE_MARKS point counts, on a chapter;
    subtitle: the Classic's page has a subtitle under its title)."""
    from lxml import html as lhtml
    inc = "/" + Path(path).resolve().relative_to(Path(root).resolve()).as_posix()
    src = f'{LAYOUT_SHOW}{DIAGRAM_SHOW}#include "{inc}"\n'
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "page.html"
        r = subprocess.run(["typst", "compile", "--root", str(root), "--features", "html",
                            "--format", "html", "-", str(out)],
                           input=src, capture_output=True, text=True)
        if r.returncode:
            raise SystemExit(f"typst failed on {path}:\n{r.stderr}")
        body = lhtml.parse(str(out)).getroot().find("body")
    diagram_lists(body)
    edition_blocks(body, counts, subtitle)
    notes = {}
    sec = body.find(".//section[@role='doc-endnotes']")
    if sec is not None:
        for li in sec.iter("li"):
            back = li.find("sup")
            if back is not None:
                li.text = (back.tail or "") if li.text is None else li.text
                li.remove(back)
            inner = (li.text and html.escape(li.text, quote=False) or "") + "".join(
                etree.tostring(c, method="xml", encoding="unicode") for c in li)
            notes[li.get("id")] = inner
        sec.getparent().remove(sec)
    frag = "".join(etree.tostring(c, method="xml", encoding="unicode", with_tail=True)
                   for c in body)
    if body.text and body.text.strip():
        frag = html.escape(body.text, quote=False) + frag
    order, asides = [], []

    def ref(m):
        target = m.group(2)
        n = first_note + len(order)
        order.append(target)
        asides.append(f'<aside id="fn-{n}" class="note" epub:type="footnote" '
                      f'role="doc-footnote"><p><a href="#nr-{n}" role="doc-backlink">'
                      f'{n}.</a> {notes.get(target, "")}</p></aside>')
        return (f'<a class="noteref" id="nr-{n}" href="#fn-{n}" epub:type="noteref" '
                f'role="doc-noteref"><sup>{n}</sup></a>')
    frag = re.sub(r'<sup id="([^"]+)" role="doc-noteref"><a href="#([^"]+)">[^<]*</a></sup>',
                  ref, frag)
    if asides:
        frag += '<section class="notes">' + "".join(asides) + "</section>"
    return frag, len(order)


def heading_ids(body, prefix, depth=3):
    """Give every h2..h{depth} an id; return (body, [(id, level, text)])."""
    heads = []

    def add(m):
        hid = m.group(3) or f"{prefix}-h{len(heads) + 1}"
        # a heading's footnote (Gouge's "Treat. 4. §. 4.") is not in the contents
        bare = re.sub(r'<a class="noteref"[^>]*>.*?</a>', "", m.group(4), flags=re.S)
        text = html.unescape(re.sub(r"<[^>]+>", "", bare)).strip()
        heads.append((hid, int(m.group(1)), text))
        attrs = m.group(2) if m.group(3) else f'{m.group(2)} id="{hid}"'
        return f"<h{m.group(1)}{attrs}>{m.group(4)}</h{m.group(1)}>"
    levels = "".join(str(n) for n in range(2, depth + 1))
    body = re.sub(r'<h([' + levels + r'])((?:\s[^>]*?)?(?:\sid="([^"]*)")?[^>]*)>(.*?)</h\1>',
                  lambda m: add(m), body, flags=re.S)
    return body, heads


def opf_doc(a, ident, modified, items, spine):
    manifest = "".join(
        f'<item id="{i}" href="{h}" media-type="{m}"' + (f' properties="{p}"' if p else "") + "/>"
        for i, h, m, p in items)
    spine_xml = "".join(f'<itemref idref="{i}"/>' for i in spine)
    cover_meta = '<meta name="cover" content="cover-image"/>' if a.cover else ""
    doc = ('<?xml version="1.0" encoding="utf-8"?>\n'
           f'<package xmlns="http://www.idpf.org/2007/opf" version="3.0" '
           f'unique-identifier="bookid" xml:lang="{a.lang}">'
           '<metadata xmlns:dc="http://purl.org/dc/elements/1.1/">'
           f'<dc:identifier id="bookid">{esc(ident)}</dc:identifier>'
           f"<dc:title>{esc(a.title)}</dc:title>"
           f"<dc:creator>{esc(a.author)}</dc:creator>"
           f"<dc:language>{a.lang}</dc:language>"
           f'<meta property="dcterms:modified">{modified}</meta>{cover_meta}'
           f'</metadata><manifest>{manifest}</manifest>'
           f'<spine toc="ncx">{spine_xml}</spine></package>\n')
    etree.fromstring(doc.encode("utf-8"))
    return doc


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("tei")
    ap.add_argument("out")
    ap.add_argument("--title", required=True)
    ap.add_argument("--author", required=True)
    ap.add_argument("--front")
    ap.add_argument("--before", action="append", default=[])
    ap.add_argument("--after", action="append", default=[])
    ap.add_argument("--typst-root")
    ap.add_argument("--chapters")
    ap.add_argument("--toc-depth", type=int, default=3,
                    help="deepest heading in the contents: 3 (h3, the default) or "
                    "4 (also h4, e.g. a book's numbered sections)")
    ap.add_argument("--cover")
    ap.add_argument("--css", action="append", default=[])
    ap.add_argument("--files", action="append", default=[],
                    help="only the layout files under this path prefix (e.g. vol-1/); repeatable")
    ap.add_argument("--lang", default="en")
    ap.add_argument("--identifier")
    ap.add_argument("--modified")
    add_text_args(ap)
    a = ap.parse_args()

    ident = a.identifier or f"urn:uuid:{uuid.uuid5(uuid.NAMESPACE_URL, a.title + '|' + a.author)}"
    css_names = []
    files = {}                                   # name in OEBPS -> bytes
    items = []                                   # (id, href, media-type, properties)
    for i, c in enumerate(a.css):
        name = f"style-{i}{Path(c).suffix}" if Path(c).name in css_names else Path(c).name
        css_names.append(name)
        files[name] = Path(c).read_bytes()
        items.append((f"css-{i}", name, "text/css", None))

    spine, heads, landmarks = [], [], []

    def page(ident_, name, title, body):
        text, hs = heading_ids("\n".join(body), ident_, a.toc_depth)
        heads.extend((name, hid, lvl, t) for hid, lvl, t in hs)
        files[name] = xhtml(title, [text], css_names, a.lang).encode("utf-8")
        items.append((ident_, name, "application/xhtml+xml", None))
        spine.append(ident_)

    typst_root = Path(a.typst_root) if a.typst_root else Path(a.tei).resolve().parent.parent
    notes_used = [0]

    def extra_page(path, n, where):
        path = Path(path)
        pid = f"{where}-{n}-{re.sub(r'[^a-z0-9]+', '-', path.stem.lower())}"
        if path.suffix == ".typ":
            frag, k = typst_page(path, typst_root, notes_used[0] + 1)
            notes_used[0] += k
        else:
            frag = path.read_text(encoding="utf-8").strip()
            for m, (src, p_) in enumerate(local_images(frag, path.parent)):
                if src not in files:
                    files[src] = p_.read_bytes()
                    items.append((f"img-{pid}-{m}", src, MEDIA[p_.suffix.lower()], None))
        page(pid, pid + ".xhtml", a.title, [frag])

    if a.cover:
        cover = Path(a.cover)
        cname = "cover" + cover.suffix.lower()
        files[cname] = cover.read_bytes()
        items.append(("cover-image", cname, MEDIA[cover.suffix.lower()], "cover-image"))
        page("cover", "cover.xhtml", a.title,
             [f'<section id="cover" epub:type="cover" class="cover">'
              f'<img src="{cname}" alt="{esc(a.title)}"/></section>'])
        landmarks.append(("cover", "cover.xhtml", "Cover"))

    if a.front:
        front = Path(a.front)
        frag = front.read_text(encoding="utf-8").strip()
        for n, (src, path) in enumerate(local_images(frag, front.parent)):
            if src not in files:
                files[src] = path.read_bytes()
                items.append((f"img-{n}", src, MEDIA[path.suffix.lower()], None))
        page("front", "front.xhtml", a.title, [frag])
        landmarks.append(("titlepage", "front.xhtml", "Title Page"))

    for n, f in enumerate(a.before):
        extra_page(f, n, "before")

    root = etree.parse(a.tei).getroot()
    r = renderer(a, root)
    r.note_no = notes_used[0]                    # notes are numbered through the book
    ndiv = 0
    modern = {}
    if a.chapters:
        cdir = Path(a.chapters)
        modern = {file_ident(p.relative_to(cdir).as_posix()): p for p in cdir.rglob("*.typ")}
    cfg = layout.settings(a.tei)
    # OUTLINE_MARKS: the Modern English points marked as the Classic's are, counted through the book
    counts = [0] * len(POINT_MARKS) if cfg.get("OUTLINE_MARKS") else None
    for n, (div_id, head, lines) in enumerate(divisions(root, r, cfg, a.files)):
        name = f"{div_id}.xhtml"
        # a part page (its own title only) stays; a layout file's id may begin "part-" too
        # (Religious Affections' part-1-01-the-text), so it is told by its section's class
        part_page = bool(lines) and 'class="part"' in lines[0]
        if a.chapters and not part_page:
            if div_id not in modern:
                raise SystemExit(f"{a.chapters}: no file for {div_id}")
            frag, k = typst_page(modern[div_id], typst_root, notes_used[0] + 1, counts,
                                 any(x.startswith('<p class="subtitle">') for x in lines))
            notes_used[0] += k
            # the layout's kicker over the title ("Part II · No Certain Sign I"), as the Classic's
            kicker = next((x for x in lines if x.startswith('<p class="kicker">')), None)
            if kicker:
                frag = re.sub(r"(</h[1-6]>)", lambda m, k=kicker: m.group(1) + k, frag, count=1)
            lines = [f'<section id="{div_id}">', frag, "</section>"]
        page(div_id, name, head, lines)
        ndiv += 1
        if n == 0:
            landmarks.append(("bodymatter", name, "Start of Content"))
    if not a.chapters:
        notes_used[0] = r.note_no

    for n, f in enumerate(a.after):
        extra_page(f, n, "after")

    tree = nest(heads)
    if any(k for _, _, kids in tree for _, _, k in kids):
        print("warning: the contents go deeper than two levels; Apple Books sets the "
              "entries after a third level one level too high (lower --toc-depth)")
    files["nav.xhtml"] = nav_doc(a.title, tree, landmarks, a.lang, css_names).encode("utf-8")
    items.append(("nav", "nav.xhtml", "application/xhtml+xml", "nav"))
    files["toc.ncx"] = ncx_doc(a.title, ident, tree).encode("utf-8")
    items.append(("ncx", "toc.ncx", MEDIA[".ncx"], None))
    opf = opf_doc(a, ident, modified_stamp(a.modified), items, spine)

    with zipfile.ZipFile(a.out, "w") as z:
        def put(name, data, method=zipfile.ZIP_DEFLATED):
            info = zipfile.ZipInfo(name, FIXED_TIME)
            info.compress_type = method
            info.external_attr = 0o644 << 16
            z.writestr(info, data)
        put("mimetype", b"application/epub+zip", zipfile.ZIP_STORED)   # must be first
        put("META-INF/container.xml", CONTAINER.encode("utf-8"))
        put("OEBPS/content.opf", opf.encode("utf-8"))
        for name, data in files.items():
            put(f"OEBPS/{name}", data)
    print(f"wrote {a.out}: {ndiv} divisions, {len(a.before) + len(a.after)} extra pages, "
          f"{notes_used[0]} notes ({a.layer} layer)")


if __name__ == "__main__":
    main()
