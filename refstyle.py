#!/usr/bin/env python3
"""
refstyle.py: scripture references in the modern style, in a book's review.

  python3 refstyle.py BOOK_DIR [--write] [--report FILE]

Rewrites the references in chapters/typ/*.typ the way the edition gives
them (the editor's rule, 2026-10-27), then `fgb sync` folds the change into
the TEI as reg readings (the orig layer keeps them as printed):

  citation   "Heb. xii. 5", "Psal. 119. 9", "1Co 3:22", "(Rom. 8.28)"
             -> "Heb 12:5", "Ps 119:9", "1 Cor 3:22", "(Rom 8:28)": the SBL
             abbreviation without its stop, Arabic chapter:verse, en dash
             in a range ("Ps. 7. 1-3" -> "Ps 7:1–3"), "ult." as the last verse,
             a book of one chapter by verse ("Jude 14,15" -> "Jude 14, 15")
  prose      a reference the sentence reads aloud ("as Paul says in Rom. 8.
             28") keeps the book's name spelled out: "in Romans 8:28"
             a book's name set in italic ("#emph[Gen.] 31. 42.", Gouge) is set
             roman with the rest
  lists      numbers after the chapter read against the KJV: verses, or a
             chapter going on ("Gen. 2. 22, 1. 27" -> "Gen 2:22; 1:27", "Job 22.
             3. & 35. 7." -> "Job 22:3; 35:7"); with --stops, verses set off by
             stops too ("Eph. 6. 5. 6. 7." -> "Eph 6:5, 6, 7", Perkins, Gouge,
             Brooks), a margin note's numbered head left out ("Luke 16. 19. 2.
             In bringing"); readings that could go either way are reported
             "ambiguous", a verse out of order "check"
  partial    "ver. 5", "vers. 5, 6", "chap. 14. 31" -> "v. 5", "vv. 5, 6",
             "ch. 14:31" ("Ver." / "Chap." opening a sentence: "Verse",
             "Chapter"); "verse 5" written out and Latin "cap." are kept

A reference whose chapter or verse the KJV doesn't have is left as printed
and listed (refs.py lists them too). Without --write, only the report.
"""

import argparse
import re
import sys
from pathlib import Path

from lxml import etree

import refs

ABBR = dict(zip(refs.BOOKS, """Gen Exod Lev Num Deut Josh Judg Ruth 1_Sam 2_Sam 1_Kgs 2_Kgs
1_Chr 2_Chr Ezra Neh Esth Job Ps Prov Eccl Song Isa Jer Lam Ezek Dan Hos Joel Amos Obad Jonah
Mic Nah Hab Zeph Hag Zech Mal Matt Mark Luke John Acts Rom 1_Cor 2_Cor Gal Eph Phil Col
1_Thess 2_Thess 1_Tim 2_Tim Titus Phlm Heb Jas 1_Pet 2_Pet 1_John 2_John 3_John Jude
Rev""".split()))
ABBR = {k: v.replace("_", " ") for k, v in ABBR.items()}

# books of one chapter are cited by verse alone: "Jude 5", "Phlm 9"
ONE_CHAPTER = {"Obadiah", "Philemon", "2 John", "3 John", "Jude"}

# a reference read as part of the sentence: the book is named in full
PROSE_BEFORE = {"in", "of", "from", "at", "to", "unto", "by", "with", "read"}

# names as printed, case kept: a book starts with a capital ("is 40" is not
# Isaiah); short aliases that are English words need the stop ("Am.", "Is.")
WORDLIKE = {"is", "am", "ho", "so", "da", "ge", "le", "ex", "nu", "lu", "joe", "ru", "jud",
            "mar", "pro", "act", "song", "sol", "can", "jam", "phi", "col", "rut", "est",
            "jon", "hag", "oba", "lam", "dan", "job", "mark", "acts", "john", "jude",
            "ruth", "ezra", "joel", "amos", "jonah", "luke", "titus"}

ROMAN = r"(?:[ivxlc]{1,9}|[IVXLC]{1,9})"
NUM = r"\d{1,3}"


def name_alternatives():
    out = []
    for n in refs.NAMES:
        words = n.split(" ")
        cap = " ".join(w if re.match(r"[123]|[ivx]+$", w) and i == 0 and len(words) > 1
                       or w == "of" else w[:1].upper() + w[1:] for i, w in enumerate(words))
        cap = re.sub(r"^(i{1,3})( |(?=[A-Z]))", lambda m: m.group(1).upper() + m.group(2), cap)
        out.append(cap)
        if cap.replace(" ", "").isalpha():
            out.append(cap.upper())        # "EPHES." (Gouge's heads)
    return sorted(set(out), key=len, reverse=True)


NAMES_RE = "|".join(re.escape(n) for n in name_alternatives()).replace(r"\ ", r"\s?")
# a numbered book's name without its number, for "1. Cor.", "2 #emph[Cor."
BARE_RE = "|".join(sorted({re.escape(n.split(" ", 1)[1][:1].upper() + n.split(" ", 1)[1][1:])
                           for n in refs.NAMES if re.match(r"[123] [a-z]", n)},
                          key=len, reverse=True)).replace(r"\ ", r"\s?")
# a number in a list is a verse unless a book's name follows it ("2 Cor 5:14,
# 15, 1 Tim. ii. 6": the 1 is the next book's)
NEXT_BOOK = rf"(?![123](?:\\?\.)?\s?(?:#emph\[)?(?:{BARE_RE})\b)"
VLIST = (rf"{NUM}(?:\s?[-–]\s?{NUM})?(?:(?:\s?,\s?|\s(?:and|&)\s){NEXT_BOOK}{NUM}"
         rf"(?![\d:])(?:\s?[-–]\s?{NUM})?)*")
# after the chapter, numbers set off by commas or "and": verses, or a chapter
# and its verse ("Gen. 2. 22, 1. 27", "Isa. 10. 17. and 27. 4."); in a book
# that sets verses off by stops too (--stops: Perkins's "Eph. 6. 5. 6. 7.") a
# stop may part them, which elsewhere ends the reference (Owen's "Matt.
# xxvi. 28. 2. Do those"). Converter.tail reads them against the KJV. An
# italic holding the reference may close inside the list ("#emph[Gen. 26. 35.
# &] 27. 46."); a number that a book's name follows is the next reference's
CLOSE_IN = r"(?(c1)|(?(c2)|(?(open)\]?|(?(nopen)\]?))))"
ONE = rf"{NUM}(?![\d#a-z]|:\d)(?:\s?[-–]\s?{NUM}|\.?\s(?:ad\s)?ult(?=\.))?"


def ref_re(stops):
    if stops:
        item = rf"(?:\s?,|\.(?:\s?(?:and|&))?|\s(?:and|&)){CLOSE_IN}\s?{NEXT_BOOK}{ONE}"
    else:
        item = (rf"(?:(?:\s?,|\s(?:and|&)){CLOSE_IN}\s?{NEXT_BOOK}{ONE}"
                rf"|\.?\s?(?:and|&){CLOSE_IN}\s?{NUM}\.\s?{ONE})")
    # an italic may hold the book's name ("#emph[Gen.] 31. 42", Gouge) or the
    # whole reference ("2 #emph[Cor. 12. 7.]"): the reference comes out roman
    return re.compile(
        rf"(?<![\w.])(?:(?P<num>[123])(?:\\?\.)?\s(?P<nopen>#emph\[)?(?P<bare>{BARE_RE})"
        rf"|(?P<open>#emph\[(?P<paren>\()?)?(?P<book>{NAMES_RE}))(?P<stop>\.?)"
        rf"(?(open)(?P<c1>\])?|(?(nopen)(?P<c2>\])?))\s?"
        rf"(?P<ch>{NUM}|{ROMAN})"
        rf"(?:(?P<sep>\s?[.:,]\s?|\.?\s(?:ver|vers|v)\.\s?)(?P<vs>{ONE}(?:{item})*|ult(?=\.)))?"
        rf"(?P<more>(?:\s?;\s?(?:{NUM}|{ROMAN})(?:\s?[.:]\s?)(?:{VLIST}))*)"
        rf"(?P<end>\.?)(?!\w|:\w)")


REF_RE = ref_re(False)
MODERN_BOOK = "|".join(re.escape(n) for n in sorted(set(ABBR.values()) | set(refs.BOOKS)
                                                   | {"Psalm"}, key=len, reverse=True))
CHAIN_RE = re.compile(
    rf"(?P<pre>(?<![\w.])(?P<book>{MODERN_BOOK}) \d{{1,3}}:\d{{1,3}}(?:(?:[–,]\s?|;\s\d{{1,3}}:)\d{{1,3}})*)"
    rf"(?P<sep>,| and|, and) (?P<ch>(?!v\.)[ivxlc]{{1,9}})\. ?(?P<vs>{VLIST})(?![\w:])")
CLOSE_RE = re.compile(rf"([\s(])((?:[123]\\?\.?\s?(?:{BARE_RE})|{NAMES_RE})\.?)\](\s?(?:{NUM}|{ROMAN})\s?[.:,]\s?{NUM})")
PARTIAL_RE = re.compile(
    rf"(?<![\w.])(?P<w>ver|vers|v|Ver|Vers|V|chap|Chap|ch|Ch)\.\s?(?P<a>{NUM}|{ROMAN})"
    rf"(?:(?P<sep>\s?[.:]\s?)(?P<b>{VLIST}))?(?P<rest>(?:\s?[-–]\s?{NUM}|\s?,\s?{NUM})*)"
    rf"(?P<end>\.?)(?![\w:])")


def canon_of(name):
    return refs.NAMES.get(re.sub(r"\s+", " ", name).lower()) or \
        refs.NAMES.get(re.sub(r"\s+", "", name).lower())


def arabic(s):
    return int(s) if s.isdigit() else refs.roman(s)


def norm_verses(vs):
    vs = re.sub(r"\s?[-–]\s?", "–", vs)
    vs = re.sub(r"\s?,\s?", ", ", vs)
    return re.sub(r"\s(?:and|&)\s", ", ", vs)


def depth_at(line, pos):
    """Inside parentheses, brackets, or a footnote at pos?"""
    d = 0
    i = 0
    while i < pos:
        c = line[i]
        if c == "\\":
            i += 2
            continue
        if c in "([":
            d += 1
        elif c in ")]":
            d = max(0, d - 1)
        i += 1
    return d > 0


def ends_sentence(after):
    """Keep a reference's closing stop when a new sentence follows (or the
    paragraph ends), drop it when the sentence runs on ("Rom. 8. 28, and")."""
    s = after.lstrip()
    return not s or not (s[0].islower() or s[0] in ",;:)")


class Converter:
    def __init__(self, bible, stops=False):
        self.bible = bible
        self.ref_re = ref_re(stops)
        self.log = []
        self.prose_end = None

    def valid(self, canon, c, vs):
        chs = self.bible.get(canon, [])
        if c < 1 or c > len(chs):
            return False
        try:
            nums = refs.verses(vs.replace(", ", ",")) if vs else []
        except ValueError:
            return False
        return all(1 <= v <= len(chs[c - 1]) for v in nums)

    def tail(self, canon, c, s):
        """The numbers after chapter c, as printed ("5. 6. 7", "22, 1. 27",
        "17 and 27. 4. and 55. 13"): the first verse's list and the chapters
        after it ("27:4"), and a note for the report, or None when no reading
        fits the KJV. A number may open a new chapter where a stop and its
        verse follow; of the readings that fit, verses rising in each chapter
        and then the fewest chapters win (Perkins's "Eph. 6. 5. 6. 7." is
        verses, Brooks's "Hos. 4. 17. 5. 3." chapters)."""
        chs = self.bible.get(canon, [])
        items = []
        for t in re.finditer(r"(?P<sep>^|\s?,|\.(?:\s?(?:and|&))?|\s(?:and|&))\]?\s?"
                             r"(?P<a>\d+)(?:\s?[-–]\s?(?P<b>\d+)|\.?\s(?:ad\s)?(?P<ult>ult))?", s):
            sep = t.group("sep").strip()
            items.append((sep[:1] if sep[:1] in ".," else sep and "and", int(t.group("a")),
                          int(t.group("b")) if t.group("b") else "ult" if t.group("ult") else None))
        starts = [i for i in range(1, len(items) - 1)
                  if items[i][2] is None and items[i + 1][0] == "."]
        best = []
        for k in range(1 << len(starts)):
            pick = {starts[j] for j in range(len(starts)) if k >> j & 1}
            if any(i + 1 in pick for i in pick):
                continue
            groups, viol, i = [[c, []]], 0, 0
            while i < len(items):
                if i in pick:
                    groups.append([items[i][1], []])
                    i += 1
                    continue
                groups[-1][1].append(items[i][1:])
                i += 1
            ok = True
            for ch, vs in groups:
                if not 1 <= ch <= len(chs):
                    ok = False
                    break
                last = 0
                for a, b in vs:
                    b = len(chs[ch - 1]) if b == "ult" else b
                    if not (1 <= a <= len(chs[ch - 1]) and (b is None or a < b <= len(chs[ch - 1]))):
                        ok = False
                    viol += a <= last
                    last = b or a
            if ok:
                best.append((viol, len(groups) - 1, groups))
        if not best:
            return None
        best.sort(key=lambda x: x[:2])
        viol, _, groups = best[0]
        if viol and len(items) > 2:
            return None
        note = "check" if viol else \
            "ambiguous" if any(v == 0 and g != groups for v, _, g in best[1:]) else None

        def fmt(vs, ch):
            return ", ".join(f"{a}–{len(chs[ch - 1]) if b == 'ult' else b}" if b else str(a)
                             for a, b in vs)
        return fmt(groups[0][1], c), [f"{ch}:{fmt(vs, ch)}" for ch, vs in groups[1:]], note

    def ref(self, m, line, where):
        """The reference restyled; a list after the chapter that no reading
        fits, or that ends in a numbered point ("Luke 16:19. 2. In bringing",
        Gouge), is cut back to the part that reads."""
        out = self.restyle(m, line, where)
        if out is not None:
            return out
        vs0 = m.start("vs")
        for cut in reversed([vs0 + c.start() for c in
                             re.finditer(r"(?:\.|,?\s?(?:and|&)|\s?,)\]?\s?\d", m.group("vs"))]):
            m2 = self.ref_re.match(line, m.start(), cut)
            if m2 and m2.end() == cut and m2.group("vs"):
                out = self.restyle(m2, line, where)
                if out is not None:
                    return out + line[cut:m.end()]
        self.log.append((where, "missing", m.group(0), ""))
        return m.group(0)

    def restyle(self, m, line, where):
        book, ch = m.group("book") or f"{m.group('num')} {m.group('bare')}", m.group("ch")
        canon = canon_of(book)
        if not canon:
            return m.group(0)
        if book.lower().replace(" ", "") in WORDLIKE and not m.group("stop") \
                and not m.group("vs") and canon != "Psalms":
            return m.group(0)          # "John 3", "Job 4" with no verse: a name
        if book.lower() in WORDLIKE and len(book) <= 3 and not m.group("stop") \
                and book != canon:
            return m.group(0)
        if not m.group("vs") and not m.group("stop") and not ch.isdigit():
            return m.group(0)          # "Job ii" without a stop
        if not ch.isdigit() and not m.group("stop") and not m.group("sep"):
            return m.group(0)
        if ch.isupper() and not m.group("vs"):
            return m.group(0)          # "Matt. I": a chapter alone in capitals
        try:
            c = arabic(ch)
        except KeyError:
            return m.group(0)
        vs = m.group("vs") or ""
        if vs == "ult":
            chs = self.bible.get(canon, [])
            if not 1 <= c <= len(chs):
                return m.group(0)
            vs = str(len(chs[c - 1]))
        extra, note = [], None
        closed = "]" in vs                 # the italic closed inside the list
        if closed and vs.count("]") > 1:
            return m.group(0)
        if re.search(r"\.|\]|&|\band\b|\bult\b", vs) and canon not in ONE_CHAPTER:
            read = self.tail(canon, c, vs)
            # a margin note's numbered head after the reference, not a verse
            # out of order: "#footnote[Luke 16. 19. 2. In bringing parents"
            # (Gouge); "Gen. 24. 2. 3. And prayed" (Perkins) is verses
            after = line[m.end("vs"):]
            if re.search(r"\.\]?\s?\d+$", vs) and re.match(r"\.\s(?:#emph\[)?[A-Z]", after) \
                    and not re.match(rf"\.\s(?:#emph\[)?(?:{NAMES_RE})\b", after) \
                    and (not read or read[2] == "check"):
                return None
            if not read:
                return None
            vs, extra, note = read
        vs = norm_verses(vs)
        sep = (m.group("sep") or "").strip()
        one = canon in ONE_CHAPTER
        if one and ch.lower() == "v" and not vs:
            return m.group(0)          # "#emph[Philem. v.] 2.": the verse is out of reach
        if one and (not vs or sep == ","):
            vs, c = norm_verses(f"{c}, {vs}" if vs else str(c)), 1   # "Jude 5, 7"
        elif one and (ch.lower() == "v" or c == 1) and sep in (".", ":"):
            c = 1                                                   # "Philem. v. 9"
        chapters = None
        if not self.valid(canon, c, vs):
            nums = [c] + [int(x) for x in re.findall(r"\d+", vs)]
            if sep == "," and not one and \
                    all(1 <= x <= len(self.bible.get(canon, [])) for x in nums):
                chapters = vs                                       # "Ps. 32, 109"
            else:
                self.log.append((where, "missing", m.group(0), ""))
                return m.group(0)
        more = list(extra)
        for part in re.finditer(rf"({NUM}|{ROMAN})\s?[.:]\s?({VLIST})", m.group("more")):
            c2, v2 = arabic(part.group(1)), norm_verses(part.group(2))
            if not self.valid(canon, c2, v2):
                self.log.append((where, "missing", m.group(0), ""))
                return m.group(0)
            more.append(f"{c2}:{v2}")
        prose = not depth_at(line, m.start()) and \
            (re.search(r"(\w+)(?:\s|#emph\[|\()*$", line[:m.start()]) or [None, ""])[1].lower() \
            in PROSE_BEFORE
        # a list the sentence reads ("as in Dan. xii. 2, Rom. v. 19") is spelled out throughout
        if self.prose_end is not None and \
                re.fullmatch(r"\s*(?:,|;|,?\s(?:and|or))\s*", line[self.prose_end:m.start()]):
            prose = True
        self.prose_end = m.end() if prose else None
        if prose:
            name = "Psalm" if canon == "Psalms" and not more else canon
        else:
            name = ABBR[canon]
        if one:
            new = f"{name} {vs}"
        elif chapters:
            new = f"{name} {c}, {chapters}"
        else:
            new = f"{name} {c}" + (f":{vs}" if vs else "") + "".join(f"; {x}" for x in more)
        end = m.group("end")
        if end and ends_sentence(line[m.end():]):
            new += "."
        if (m.group("open") or m.group("nopen")) and not (m.group("c1") or m.group("c2")) \
                and not closed:
            new = (m.group("open") or m.group("nopen")) + new   # the italic goes on to its "]"
        elif m.group("paren"):
            new = "(" + new              # "#emph[(Mat.] 19. 6.)"
        kind = note or ("prose" if prose else "citation")
        if new != m.group(0):
            self.log.append((where, kind, m.group(0), new))
        return new

    def chain(self, m, where):
        canon = canon_of(m.group("book"))
        ch = m.group("ch")
        if ch == "v" or not re.fullmatch(r"c{0,3}(?:xc|xl|l?x{0,3})(?:ix|iv|v?i{0,3})", ch):
            return m.group(0)          # "vv. 1", "v. 3": verses, not a chapter
        c = refs.roman(ch)
        vs = norm_verses(m.group("vs"))
        if not canon or not self.valid(canon, c, vs):
            return m.group(0)
        new = m.group("pre") + (" and " if "and" in m.group("sep") else "; ") + f"{c}:{vs}"
        self.log.append((where, "citation", m.group(0), new))
        return new

    def partial(self, m, line, where):
        w, a, b = m.group("w"), m.group("a"), m.group("b")
        verse = w.lower().startswith("v")
        if not a.isdigit() and verse:
            return m.group(0)          # "v. i"? leave
        try:
            n = arabic(a)
        except KeyError:
            return m.group(0)
        rest = m.group("rest") or ""
        if verse:
            if b:
                return m.group(0)      # "ver. 5. 6": unclear, leave
            plural = bool(rest)
            word = ("vv." if plural else "v.") if w.islower() else \
                ("Verses" if plural else "Verse")
            new = f"{word} {n}{norm_verses(rest)}"
        else:
            word = "ch." if w.islower() else "Chapter"
            new = f"{word} {n}" + (f":{norm_verses(b)}" if b else "") + norm_verses(rest)
        end = m.group("end")
        if end and ends_sentence(line[m.end():]):
            new += "."
        if new != m.group(0):
            self.log.append((where, "partial", m.group(0), new))
        return new

    def line(self, text, where):
        self.prose_end = None
        # "#emph[... his people, Deut.] 6. 7": the italic closes before the book
        text = CLOSE_RE.sub(r"]\1\2\3", text)
        # a numbered book's number left italic ("#emph[1] John 3:2", Gouge)
        def roman_number(m):
            self.log.append((where, "citation", m.group(0) + "…", m.group(1) + " …"))
            return m.group(1) + " "
        text = re.sub(rf"#emph\[([123])\.?\]\s?(?=(?:{BARE_RE})\.?\s?\d)", roman_number, text)
        text = self.ref_re.sub(lambda m: self.ref(m, text, where), text)
        # a list going on in the same book with a chapter in Roman numerals
        # ("Ezek 11:19, xxxvi. 26") -> "Ezek 11:19; 36:26"
        while True:
            new = CHAIN_RE.sub(lambda m: self.chain(m, where), text)
            if new == text:
                break
            text = new
        return PARTIAL_RE.sub(lambda m: self.partial(m, text, where), text)


# ---------------------------------------------------------------------------
# Marking the readings in the TEI: reg/@type="reference"
# ---------------------------------------------------------------------------

PARTIAL_WORDS = {"v", "vv", "ver", "vers", "verse", "verses", "chap", "ch", "chapter", "ult"}
MODERN_NAMES = sorted(set(ABBR.values()) | set(refs.BOOKS) | {"Psalm"}, key=len, reverse=True)
MODERN_RE = re.compile(
    r"(?<!\w)(?:(?:" + "|".join(re.escape(n) for n in MODERN_NAMES) + r")\s\d{1,3}"
    r"|(?:vv?|ch)\.\s\d{1,3}|(?:Verses?|Chapter)\s\d{1,3}"
    # a reference going on in the same book: "And xl. 4, 5" -> "And 40:4, 5" (Boston)
    r"|(?<![\d:.,])\d{1,3}(?=:\d))"
    r"(?::\d{1,3})?(?:[–,]\s?\d{1,3})*(?:;\s\d{1,3}(?::\d{1,3})?(?:[–,]\s?\d{1,3})*)*\.?")
TEXT_BLOCKS = {"p", "item", "note", "head", "cell", "l", "label", "trailer", "signed",
               "salute", "dateline", "byline", "titlePart", "docTitle", "q", "quote", "bibl"}


def _local(e):
    return etree.QName(e).localname if isinstance(e.tag, str) else ""


def _side(choice, names):
    for name in names:
        r = choice.find("{*}" + name)
        if r is not None:
            return r
    return None


def layer_text(e, names):
    """e's text in one layer: nested choices read through `names`."""
    out = [e.text or ""]
    for c in e:
        if _local(c) == "choice":
            r = _side(c, names)
            out.append(layer_text(r, names) if r is not None else "")
        elif _local(c) and _local(c) != "note":
            out.append(layer_text(c, names))
        out.append(c.tail or "")
    return "".join(out)


READING = ("reg", "expan", "corr", "orig", "abbr", "sic")
PRINTED = ("orig", "abbr", "sic", "reg")


def segments(text_el):
    """Each block's pieces (a note is a block of its own): plain text, or
    (choice, printed text, reading text)."""
    out = []

    def walk(e, seg):
        tag = _local(e)
        if not tag:
            return
        if tag in TEXT_BLOCKS:
            seg = []
            out.append(seg)
        if tag == "choice":
            r, o = _side(e, READING), _side(e, PRINTED)
            seg.append((e, layer_text(o, PRINTED) if o is not None else "",
                        layer_text(r, READING) if r is not None else ""))
            return
        seg.append(e.text or "")
        for c in e:
            walk(c, seg)
            seg.append(c.tail or "")

    root = []
    walk(text_el, root)
    return out + [root]


def _numbers(s, roman_v):
    """The numbers of a reference, a range counted out ("7–9" = 7, 8, 9)."""
    out = []
    for tok in re.findall(r"\d+|[A-Za-z]+|[-–]", s):
        if tok.isdigit() or re.fullmatch(r"[ivxlc]+|[IVXLC]+", tok) and \
                (roman_v or tok.lower() != "v"):
            n = int(tok) if tok.isdigit() else refs.roman(tok)
            if out and out[-1] == "-" and len(out) > 1 and isinstance(out[-2], int) \
                    and out[-2] < n <= out[-2] + 50:
                out.pop()
                out += list(range(out[-1] + 1, n + 1))
            else:
                out = [x for x in out if x != "-"] + [n]
        elif tok in "-–":
            out.append("-")
    return [x for x in out if x != "-"]


def _book(s):
    """The book a reference names, without its number ("Kings" for "1 Kgs")."""
    words = [w for w in re.findall(r"[A-Za-z]+", s.replace("ſ", "s"))
             if w.lower() not in PARTIAL_WORDS and not re.fullmatch(r"[ivxlc]+|[IVXLC]+", w)]
    name = " ".join(words)
    if not name:
        return ""
    # early printings' I for J and u for v: "Iohn", "Ier.", "Leuit.", "Reu."
    if not canon_of(name) and not canon_of("1 " + name):
        name = re.sub(r"^I(?=[a-z])", "J", name).replace("u", "v")
    c = canon_of(name) or canon_of("1 " + name) or canon_of(name.rstrip("h")) or \
        canon_of(name[:4]) or canon_of("1 " + name[:4]) or canon_of(name[:3])
    return re.sub(r"^[123] ", "", c) if c else "?" + name


def same_reference(orig, reg):
    """The reading only restyles a reference: the same book, the same numbers."""
    orig = orig.replace("ſ", "s")
    if _book(orig) != _book(reg):
        return False
    if "ult" in orig:
        return True
    lead = re.compile(r"^\s*(?:I{1,3}|[123])(?=\s?[A-Z])")    # "II Cor" -> "2 Cor"
    o, r = lead.sub(lambda m: str(len(m.group(0).strip()) if m.group(0).strip()[0] == "I"
                                  else m.group(0).strip()), orig), reg
    nb = _numbers(r, False)                     # the modern style has no numerals
    return nb in (_numbers(o, True), _numbers(o, False))


def restyled(orig, reg):
    """A change of words that only restyles a reference ("xii" / "12", "Psal" /
    "Ps"): every word a book's name, a numeral or v./ch., the same book and
    numbers both sides (before_after.py)."""
    words = re.findall(r"[A-Za-z]+|\d+", orig + " " + reg)
    if not words or not all(w.isdigit() or w.lower() in PARTIAL_WORDS or
                            re.fullmatch(r"[ivxlc]+|[IVXLC]+", w) or canon_of(w) or
                            canon_of("1 " + w) for w in words):
        return False
    return same_reference(orig, reg)


TYPES_TAKEN = (None, "spelling", "case", "punctuation", "spacing", "emendation")


def mark_readings(text_el):
    """reg/@type="reference" on the editor's readings that put a scripture
    reference in the modern style (refstyle.py's rewrite of the review):
    every reading inside a reference, when together they keep its book and
    numbers (a corrected verse number stays an emendation)."""
    n = 0
    for seg in segments(text_el):
        spans, pos, reg_text = [], 0, []
        for p in seg:
            t = p if isinstance(p, str) else p[2]
            spans.append((p, pos, pos + len(t)))
            reg_text.append(t)
            pos += len(t)
        reg_text = "".join(reg_text)
        if not any(not isinstance(p, str) for p in seg):
            continue
        for m in MODERN_RE.finditer(reg_text):
            inside = [k for k, (p, s, e) in enumerate(spans)
                      if not isinstance(p, str) and m.start() <= s and e <= m.end()]
            eds = [k for k in inside
                   if (r := spans[k][0][0].find("{*}reg")) is not None
                   and r.get("resp") == "#editor" and r.get("type") in TYPES_TAKEN]
            if not eds:
                continue
            k0, k1 = min(inside), max(inside)
            orig = "".join(p if isinstance(p, str) else p[1] for p, _, _ in spans[k0:k1 + 1])
            reg = "".join(p if isinstance(p, str) else p[2] for p, _, _ in spans[k0:k1 + 1])
            # the book's name may lie outside the readings ("1 Tim. 3. 1.")
            head = reg_text[m.start():spans[k0][1]]
            if same_reference(head + orig, head + reg):
                for k in eds:
                    spans[k][0][0].find("{*}reg").set("type", "reference")
                    n += 1
    return n


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("book")
    ap.add_argument("--write", action="store_true")
    ap.add_argument("--stops", action="store_true",
                    help='verses set off by stops ("Eph. 6. 5. 6. 7.": Perkins, Gouge, Brooks)')
    ap.add_argument("--report")
    a = ap.parse_args()
    conv = Converter(refs.load("kjv"), a.stops)
    book = Path(a.book)
    for f in sorted((book / "chapters" / "typ").rglob("*.typ")):
        lines = f.read_text(encoding="utf-8").split("\n")
        out = []
        for i, ln in enumerate(lines, 1):
            # the file's own headings and Typst code are left alone
            out.append(ln if ln.startswith(("#set", "#show", "#import", "#let", "//"))
                       else conv.line(ln, f"{f.relative_to(book)}:{i}"))
        if a.write and out != lines:
            f.write_text("\n".join(out), encoding="utf-8")
    rows = [f"{w}\t{k}\t{o}\t{n}" for w, k, o, n in conv.log]
    if a.report:
        Path(a.report).write_text("\n".join(rows) + "\n", encoding="utf-8")
    counts = {}
    for _, k, _, _ in conv.log:
        counts[k] = counts.get(k, 0) + 1
    print(f"{book}: " + ", ".join(f"{k} {v}" for k, v in sorted(counts.items())),
          file=sys.stderr)


if __name__ == "__main__":
    main()
