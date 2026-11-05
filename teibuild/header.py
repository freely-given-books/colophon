"""
The TEI header additions (editorialDecl, respStmt, revisionDesc), and
writing the file.
"""

import re
from datetime import date
from pathlib import Path
from lxml import etree

import teibuild  # noqa: F401  (puts colophon on sys.path)

from teitok import NS, T  # noqa: E402

from teibuild import settings as S  # noqa: E402
from teibuild.settings import XML_NS  # noqa: E402


REVIEW_DATE = re.compile(rb'(<change xml:id="review" when=")(\d{4}-\d{2}-\d{2})"')


def write_tei(tree, out):
    """Write the TEI. The review's date (revisionDesc) is today's only when
    something else changed: a rebuild that decides nothing new leaves the
    file as it was."""
    new = etree.tostring(tree, xml_declaration=True, encoding="UTF-8")
    out = Path(out)
    if out.exists():
        old = out.read_bytes()
        m = REVIEW_DATE.search(old)
        if m and REVIEW_DATE.sub(lambda n: n.group(1) + m.group(2) + b'"', new, count=1) == old:
            return
    out.write_bytes(new)


def add_header(root, editor_name):
    hdr = root.find(T + "teiHeader")
    fd = hdr.find(T + "fileDesc")
    ts = fd.find(T + "titleStmt")
    if S.AUTHOR:
        name, why = S.AUTHOR
        for a in ts.findall(T + "author"):
            a.text = name
        ns_ = fd.find(T + "notesStmt")
        if ns_ is None:
            ns_ = etree.Element(T + "notesStmt")
            fd.insert(list(fd).index(fd.find(T + "sourceDesc")), ns_)
        etree.SubElement(ns_, T + "note", type="attribution").text = why
    for xid, resp, name in (
            ("editor", "review of modernized spelling, emendations, list structure",
             editor_name),
            ("auto", "automatic spelling modernization, abbreviation expansion and "
             "reconstruction of illegible letters (build_tei.py)", "Machine pass")):
        rs = etree.SubElement(ts, T + "respStmt")
        r = etree.SubElement(rs, T + "resp")
        r.text = resp
        n = etree.SubElement(rs, T + "name")
        n.set("{%s}id" % XML_NS, xid)
        n.text = name
    ed = hdr.find(T + "encodingDesc")
    if ed is None:
        ed = etree.Element(T + "encodingDesc")
        hdr.insert(list(hdr).index(fd) + 1, ed)
    decl = etree.SubElement(ed, T + "editorialDecl")
    ccel = S.SOURCE_KIND == "thml"
    paras = [
        ("This file is the CCEL text (converted from ThML) with editorial layers "
         "added inline; nothing of it has been removed." if ccel else
         "This file is the EEBO-TCP transcription with editorial layers added "
         "inline; nothing of the transcription has been removed."),
        "choice/orig holds the text as printed; choice/reg holds the modern "
        "reading. reg/@resp says who decided it (#auto = machine, #editor = "
        "reviewed by hand); reg/@type is spelling, case, punctuation, spacing, "
        "grammar (an archaic form modernized: thou, hath, -eth), reference (a "
        "scripture reference in the modern style: Heb. xii. 5 as Heb 12:5) or "
        "emendation (another word, or a word added or removed). "
        "Where the editor overrode the machine, the editor's reg comes first and "
        "the machine's proposal follows as a second reg[@resp='#auto'].",
        "choice/abbr + choice/expan: macron abbreviations (e.g. frō = from) "
        "and superscript contractions (yᵉ = the).",
        "supplied: letters or words lost to illegible print, with @cert and a "
        "comment giving the evidence; the TCP gap element is kept inside.",
        "Spelling regularized: u/v, i/j, silent final e, doubled consonants, "
        "-ie to -y, -nesse to -ness, and a word list. Grammatical forms "
        "(hath, doth, thou, thee, thy, ye, shalt, wilt, art, hast, dost) are "
        "retained. Footnote text is left in original spelling.",
        "list[@change='#review']: run-in enumerations (I. ... II. ...) set out as "
        "numbered lists; the printed numerals are kept in label.",
        "head[@type='edition']: section title used by this edition; the printed "
        "heading is kept in the preceding head. @change='#review' points at "
        "the revisionDesc entry for these structural changes.",
        "Line breaks are those of the TCP transcription (newlines in the text; "
        "g[@ref='char:EOLhyphen'] marks a word hyphenated at line end). "
        "pb/@n is the printed page, pb/@facs the page image.",
    ]
    if ccel:
        # a modern source has no abbreviations, illegible print, period
        # spelling or transcription line breaks; say what it does have
        tcp_only = ("choice/abbr", "supplied:", "Spelling regularized", "Line breaks")
        paras = [x for x in paras if not x.startswith(tcp_only)]
        paras.append("The text is CCEL's, paragraph by paragraph; CCEL gives no page "
                     "or line information. quote: a block quotation or verse set off "
                     "in the source.")
        if S.TYPOGRAPHY:
            paras.append("reg[@type='punctuation'][@resp='#auto']: CCEL's straight "
                         "quotes curled and its -- set as an em dash.")
    # encodings added for editions that rework the text more (moved notes,
    # italics, merges ...): documented only when the file uses them
    used = [(xp, txt) for xp, txt in (
        (".//t:note[@target]", "note/@target points at the anchor where this edition "
         "places the note; the note itself stays where it was printed."),
        (".//t:reg[@type='spacing']", "reg[@type='spacing']: a space this edition adds "
         "(empty orig) or removes (empty reg) between words."),
        (".//t:*[@prev]", "@prev/@next link blocks this edition runs together into one "
         "paragraph; they stay separate elements as printed."),
        (".//t:p[@rend='quote']", "p[@rend='quote']: a paragraph this edition sets as a "
         "quotation."),
        (".//t:*[@rend='inset']", "@rend='inset': a paragraph or quotation this edition "
         "sets off, indented on both sides."),
        (".//t:p[@rend='center']", "p[@rend='center']: a paragraph centered in the "
         "source, and in this edition."),
        (".//t:lg[@rend='paragraphs']", "lg[@rend='paragraphs']: verse this edition "
         "sets a line to a paragraph."),
        (".//t:item[@rend='paragraph']", "item[@rend='paragraph']: a printed list item "
         "this edition sets as a paragraph."),
        (".//t:list[@rend='inline']", "list[@rend='inline']: a printed list this "
         "edition runs into its sentence."),
        (".//t:label[@type='head']", "label[@type='head']: a heading this edition adds "
         "(its level in @n); it is not printed text."),
        (".//t:*[@rend='run-on']", "@rend='run-on': a block this edition runs on "
         "from the one before without a space between them."),
        (".//t:list[@style='indent']", "list[@style='indent']: a printed list this "
         "edition sets one step in, under the numbered paragraph it belongs to."),
        (".//t:table[@style='indent']", "table[@style='indent']: a brace whose "
         "branches this edition sets one step in, as list[@style='indent']."),
        (".//t:note[@rend='mark']", "note[@rend='mark']: a note this edition sets "
         "with its printed mark (@n, e.g. *), not a number."),
        (".//t:list[@rend]", "list/@rend: the numbering this edition gives a list "
         "(a Typst numbering pattern, e.g. 'a)'); item/@n on its first item: the "
         "number it starts from."),
        (".//t:epigraph[@rend='quote']", "epigraph[@rend='quote']: a scripture "
         "epigraph this edition sets as a quotation in the text."),
        (".//t:cell[@rend='nested']", "cell[@rend='nested']: a branch of a brace "
         "table this edition sets as an item under the branch before it."),
        (".//t:table[@rend='inline']", "table[@rend='inline']: a brace table this "
         "edition reads into one sentence, column by column."),
        (".//t:head[@next]", "head[@next]: a run-in head this edition sets as "
         "the opening words of its paragraph (p/@prev), not as a bold line."),
        (".//t:head[@prev]", "head[@prev]: a printed heading this edition runs on "
         "into the paragraph before it (a margin note or catchword set as a head)."),
        (".//t:p[@rend='epigraph']", "p[@rend='epigraph']: a paragraph holding a "
         "scripture text (reference and verse) this edition sets as an epigraph."),
        (".//t:head[@type='short']", "head[@type='short']: the short form of this "
         "edition's title, used in running heads."),
        (".//t:reg/t:hi", "hi inside reg: words of this edition's reading set in italic."),
        (".//t:list[@subtype='printed']", "list[@subtype='printed']: a list printed as "
         "one that this edition numbers; the printed numerals are kept in label."),
        (".//t:list[@rend='diagram']", "list[@rend='diagram']: a diagram printed "
         "as a list (a genealogy set as a tree), which this edition sets whole, "
         "like an illustration, never across two pages."),
        (".//t:seg[@type='after-list']", "seg[@type='after-list']: words printed at the "
         "end of a list's last item that this edition sets after the list, as a "
         "paragraph (the printed order is kept)."),
        (".//t:table[@rend='parallel']", "table[@rend='parallel']: two tables "
         "printed one against the other (@n 1 and 2, in document order), "
         "which this edition sets as two columns, item against item."),
        (".//t:seg[@type='opening']", "seg[@rend='smallcaps'][@type='opening']: the "
         "first word of a division, printed in capitals after a drop cap, which this "
         "edition sets in small capitals."),
        (".//t:seg[@rend='smallcaps'][@ana='#edition-only']",
         "seg[@rend='smallcaps'][@ana='#edition-only']: words this edition sets in "
         "small capitals (printed in capitals, or emphasized)."),
        (".//t:seg[@type='supplied']", "Text the transcription lacks (pages missing "
         "from the copy it was made from) is transcribed from another copy and put in "
         "at the gap: seg[@type='supplied'] where it runs on in a paragraph, and every "
         "block or division brought in carries @change pointing at the revisionDesc "
         "entry that names the copy. The gap itself is kept, filled with an empty "
         "supplied."),
        (".//t:seg[@type='transcription']", "seg[@type='transcription']: words the "
         "transcription misread or left out, set as printed (read on the page image); "
         "a comment inside gives the transcription's reading and the evidence, and "
         "@change points at the revisionDesc entry."),
    ) if root.find(xp, {"t": NS}) is not None]
    paras += [txt for _, txt in used]
    cats = [(c, d) for c, d in (
        ("print-only", "in the printed text but not in this edition (italics set "
         "roman, a note dropped)"),
        ("edition-only", "added by this edition (italics, a note)"),
        ("in-edition", "a printed trailer this edition keeps (trailers are otherwise "
         "left out)"),
    ) if root.find(f".//*[@ana='#{c}']") is not None]
    for ptxt in paras:
        p = etree.SubElement(decl, T + "p")
        p.text = ptxt
    if cats:
        cd = etree.SubElement(ed, T + "classDecl")
        tx = etree.SubElement(cd, T + "taxonomy")
        tx.set("{%s}id" % XML_NS, "edition-layers")
        for c, d in cats:
            cat = etree.SubElement(tx, T + "category")
            cat.set("{%s}id" % XML_NS, c)
            cd_ = etree.SubElement(cat, T + "catDesc")
            cd_.text = d
    rd = hdr.find(T + "revisionDesc")
    if rd is None:
        rd = etree.SubElement(hdr, T + "revisionDesc")
    ch = etree.Element(T + "change")
    ch.set("{%s}id" % XML_NS, "review")
    ch.set("when", date.today().isoformat())
    ch.set("who", "#editor")
    ch.text = ("Enriched edition built from the CCEL text and the reviewed Typst chapters."
               if S.SOURCE_KIND == "thml" else
               "Enriched edition built from the TCP file and the reviewed Typst chapters.")
    ch.tail = rd.text
    rd.insert(0, ch)
