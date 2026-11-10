"""
Outline levels: which paragraphs of a book are set in, and how far, by their
place in the author's numbered outline (p[@rend="levelN"], the review's
#pad(left: ...)[...]; layout.PARA_STEP a level).

Authors number points, sub-points and reasons with the same marks at every
depth (Watson's "1. ... 1. ... 1. ... 2.", Owen's "First, ... First, ...
Secondly, ..."), so the level comes from the counting, not the mark:

- a paragraph numbered 1 opens a level below the point before it;
- any other number continues the deepest open level whose last number is the
  one before it, preferring a level numbered in the same style (1. against
  (1.) against First); when more than one level could continue, it is marked
  ambiguous, for a reader to settle by sense in the book's outline.json;
- a paragraph after an edition heading starts at the heading's level, and
  the numbering under a heading carries on across it (Watson's contents
  headings stand over the points they name);
- points announced together (short paragraphs 1..k, one after another) and
  then opened one by one, the count starting again ("First, ... Secondly,
  ... Thirdly." then "First, In general ..."), are opened at the level they
  were announced at, and a later number may carry on the announced count
  (Owen's habit); the tree marks such a reopening "*";
- an unnumbered paragraph is set at the level of the numbered one before it,
  until the next heading.

Numbered paragraphs are found after any leading margin note or label
(#footnote[...], #emph[Answ.]). Levels are counted from the book's top level:
by default the depth of the paragraphs straight after edition headings, or 1.

The book's source/outline.json (optional) settles what the counting cannot:

    {"overrides": {"chapter-04.typ:3\\\\. Satan can excite": 4, ...},
     "base": {"chapter-04.typ": 2},
     "printed_heads": "^=+ (SECTION|CHAP)",
     "styles": ["digit"], "labels": ["Answ."],
     "witness": "mort.ccel.witness.xml",
     "files": ["chapter-*.typ"]}

an override keyed by the file and the paragraph's first 40 characters gives
its depth (1 = top), a numbered paragraph's or an unnumbered one's (which the
paragraphs after it then follow); "base" the depth that is level 0 in a file;
"printed_heads" the headings that are the print's own (not edition
headings), which neither anchor nor carry the numbering; "styles" the
numbering styles to read (default all: digit, paren, bracket, word, roman,
letter); "sections": false counts levels from one base for the whole file
(Watson's; by default each edition heading starts its own count, from its first
numbered point); "labels" the margin labels a number may follow (default any short
italic label); "witness" a later edition in source/ that marks each level
differently (Goold's Owen: 1. (1.) [1.] 1st. (1st.)): its paragraphs are
matched to the book's numbered ones in order, and its mark gives the depth
wherever one matches (marked "w" in the tree); the counting fills the rest.

    ./fgb outline BOOK                 the tree, ambiguous places marked "?"
    ./fgb outline BOOK --json FILE     the levels and the ambiguous places
    ./fgb outline BOOK --write         set the paragraphs in, in chapters/typ
                                       (then ./fgb sync records them)
    ./fgb outline BOOK --headings      where edition headings (=== lines, the book's
                                       EDITION_HEADINGS) would break an outline three
                                       levels deep or more into sections; each heading
                                       takes the levels above it out of the indent
"""

import json
import re
from pathlib import Path

import layout

ORDINAL_WORDS = {
    "first": 1, "firstly": 1, "secondly": 2, "second": 2, "thirdly": 3, "third": 3,
    "fourthly": 4, "fourth": 4, "fifthly": 5, "fifth": 5, "sixthly": 6, "sixth": 6,
    "seventhly": 7, "seventh": 7, "eighthly": 8, "eightly": 8, "eighth": 8, "ninthly": 9, "ninth": 9,
    "tenthly": 10, "tenth": 10, "eleventhly": 11, "twelfthly": 12,
}
ROMAN = {"i": 1, "ii": 2, "iii": 3, "iv": 4, "v": 5, "vi": 6, "vii": 7, "viii": 8,
         "ix": 9, "x": 10, "xi": 11, "xii": 12, "xiii": 13, "xiv": 14, "xv": 15}

# what may stand before a paragraph's number: margin notes and labels (any short
# italic label, "Answ.", "Quest.", "Use.", unless the book's outline.json names its own)
NOTE = r"#footnote\[(?:[^\[\]]|\[[^\]]*\])*\]\s*"
LABEL = r"[A-Z][a-z]{0,6}\."


def number_patterns(labels=None):
    lead = rf"(?:{NOTE}|#emph\[(?:{'|'.join(map(re.escape, labels)) if labels else LABEL})\]\s*)*"
    return _patterns(lead)


def _patterns(LEAD):
    """The number itself, by style; the text after it must begin."""
    return [
    ("digit", re.compile(rf"{LEAD}(\d{{1,2}})(?:st|nd|rd|th|dly|ly)?\\?\.[ ,]")),
    ("paren", re.compile(rf"{LEAD}\\?\((\d{{1,2}})\\?\.?\\?\)\s")),
    ("bracket", re.compile(rf"{LEAD}\\?\[(\d{{1,2}})\\?\.?\\?\]\s")),
    ("word", re.compile(rf"{LEAD}(?:#\w+\[)?([A-Z][a-z]+ly|First|Second|Third)\b\]?[,.:;▪]?\]?\s",
                        re.I)),
    ("roman", re.compile(rf"{LEAD}([IVX]{{1,4}})\\?\.\s")),
    ("letter", re.compile(rf"{LEAD}\\?\(?([a-h])\\?[.)]\s")),
    ]


NUMBER = number_patterns()
# a point that opens in small capitals ("2. #smallcaps[The] evil of desertion") is one of the
# author's main heads: the print sets a division's first word so
OPENING_CAPS = re.compile(rf"(?:{NOTE})*(?:\S+\s+)?#smallcaps\[")
# a paragraph that announces the points after it ("in two things", "these three", "as follows:")
ANNOUNCES = re.compile(r"(:|\b(?:two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|several|"
                       r"many|divers|sundry|following|these|thus|particulars?)\b)", re.I)
# a point that announces a number of points of its own
COUNTS = re.compile(r"(:\s*$|\b(?:two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|"
                    r"several|sundry|divers)\b)", re.I)
PAD = re.compile(rf"#pad\(left: [\d.]+em\)\[(?:{re.escape(layout.PAR_INDENT)}\[)?")
# blocks that are not paragraphs of the text: headings, lists, scopes, set-off blocks
NOT_PARA = ("=", "#[", "#set", "+ ", "- ", "]", "#v(", "#align", "#block", "#quote", " ")


def number(text, patterns=None, styles=None):
    """(style, n) of a paragraph's printed number, or None."""
    for style, rx in patterns or NUMBER:
        if styles and style not in styles:
            continue
        m = rx.match(text)
        if not m:
            continue
        g = m.group(1)
        if style == "word":
            n = ORDINAL_WORDS.get(g.lower())
            if n is None:
                continue
        elif style == "roman":
            n = ROMAN.get(g.lower())
            if n is None or g == "I" and not text[m.end():m.end() + 1].isupper():
                continue
        elif style == "letter":
            n = ord(g) - ord("a") + 1
        else:
            n = int(g)
        return style, n, m.end()
    return None


def strip_pad(block):
    """A paragraph's text without the #pad wrapper a level put round it (or the first-line
    indent a top-level paragraph after set-in ones is given)."""
    indent = f"{layout.PAR_INDENT}["
    if block.startswith(indent) and block.endswith("]"):
        return block[len(indent):-1]
    m = PAD.match(block)
    if not m:
        return block
    inner = block[m.end():]
    for end in (layout.PAD_END, "]"):
        if inner.endswith(end):
            return inner[: -len(end)]
    return inner


def blocks(text):
    """(first line number, block text) for each blank-line-separated block."""
    out, cur, start = [], [], None
    for ln, line in enumerate(text.split("\n"), 1):
        if line.strip():
            if not cur:
                start = ln
            cur.append(line)
        elif cur:
            out.append((start, "\n".join(cur)))
            cur = []
    if cur:
        out.append((start, "\n".join(cur)))
    return out


ANNOUNCE_WORDS = 60     # an announced point is a short paragraph


def announced(rows):
    """(depth, style, k) when the paragraphs just before are an announcement: points 1..k
    (k >= 2) at one depth, one straight after another, each short; else None."""
    run = []
    for r in reversed(rows):
        if r.get("heading") or not r.get("numbered"):
            break
        if run and (r["depth"] != run[-1]["depth"] or r["style"] != run[-1]["style"]
                    or r["n"] != run[-1]["n"] - 1):
            break
        if len(r["text"].split()) > ANNOUNCE_WORDS:
            return None
        run.append(r)
        if r["n"] == 1:
            break
    # the last point announcing points of its own ("five chief subtleties") opens them instead
    if len(run) >= 2 and run[-1]["n"] == 1 and not COUNTS.search(run[0]["text"][-200:]):
        return run[0]["depth"], run[0]["style"], run[0]["n"]
    return None


# a later edition's marks, one per level, outermost first (Goold's Owen: I. 1. (1.) [1.] 1st.
# (1st.) [1st.])
WITNESS_MARKS = [
    ("roman", r"[IVX]{1,4}\."), ("digit", r"\d{1,2}\."), ("paren", r"\(\d{1,2}\.?\)"),
    ("bracket", r"\[\d{1,2}\.?\]"), ("ord", r"\d{1,2}(?:st|nd|rd|th|dly|ly)\.?"),
    ("paren-ord", r"\(\d{1,2}(?:st|nd|rd|th|dly|ly)\.?\)"),
    ("bracket-ord", r"\[\d{1,2}(?:st|nd|rd|th|dly|ly)\.?\]"),
]
WITNESS_WINDOW = 400      # paragraphs ahead of the last match to look in
WITNESS_MATCH = 0.5       # similarity of the opening words to count as the same paragraph


def norm_words(text, k=12):
    """A paragraph's first k words after its number, in a form two printings share."""
    t = re.sub(r"#\w+\[|[\]\\]", " ", text).lower().replace("ſ", "s")
    t = t.replace("v", "u").replace("j", "i")
    words = re.findall(r"[a-z]+", t)
    words = [w[:-1] if w.endswith("e") and len(w) > 3 else w for w in words]
    return " ".join(words[:k])


class Witness:
    """A later edition whose marks tell the levels: its paragraphs in order, matched to the
    book's numbered paragraphs one after another."""

    def __init__(self, path):
        from lxml import etree
        root = etree.parse(str(path)).getroot()
        marks = re.compile("|".join(f"(?P<{n.replace('-', '_')}>{rx})" for n, rx in WITNESS_MARKS))
        self.paras = []
        for el in root.iter():
            if not isinstance(el.tag, str) or etree.QName(el).localname != "p":
                continue
            t = " ".join("".join(el.itertext()).split())
            m = marks.match(t)
            if m and t[m.end():m.end() + 1] in (" ", ""):
                style = next(k for k, v in m.groupdict().items() if v).replace("_", "-")
                rank = [n for n, _ in WITNESS_MARKS].index(style)
                self.paras.append((rank, norm_words(t[m.end():])))
            else:
                self.paras.append((None, norm_words(t)))
        self.at = 0

    def rank(self, body, num_end):
        """The witness mark's rank for a numbered paragraph (body after its number), or None."""
        from difflib import SequenceMatcher
        key = norm_words(body[num_end:])
        if len(key.split()) < 4:
            return None
        best, where = 0, None
        words = key.split()
        for i in range(self.at, min(len(self.paras), self.at + WITNESS_WINDOW)):
            # word-level likeness, a little less the further ahead (the nearer of two
            # like paragraphs is the one)
            r = SequenceMatcher(None, words, self.paras[i][1].split()).ratio() \
                - 0.0005 * (i - self.at)
            if r > best:
                best, where = r, i
        if best < WITNESS_MATCH:
            return None
        self.at = where + 1
        return self.paras[where][0]


def infer(name, text, cfg):
    """[{line, depth, level, style, n, ambiguous, numbered, text}] for one file's paragraphs."""
    overrides = cfg.get("overrides", {})
    witness = cfg.get("_witness")
    printed = re.compile(cfg.get("printed_heads", r"^=+ (SECTION|SECT\.|CHAP)"))
    patterns = number_patterns(cfg.get("labels"))
    styles = cfg.get("styles")
    rows, stack, head_k, after_head = [], [], None, False
    announced_at = {}       # depth -> the last point announced there, while it is opened
    for k, (ln, block) in enumerate(blocks(text)):
        first = block.split("\n")[0]
        if k == 0 and first.startswith("="):
            continue                                    # the file's title
        if first.startswith("="):
            if not printed.match(first):
                after_head = True
            rows.append({"line": ln, "heading": True, "text": first})
            continue
        if first.startswith(NOT_PARA):
            continue
        body = strip_pad(block)
        num = number(body, patterns, styles)
        if num is None:
            row = {"line": ln, "numbered": False, "text": body}
            if f"{name}:{body[:40]}" in overrides:
                # an unnumbered paragraph set at a depth of its own (Owen's "These then are
                # the ways ..." summing up a run, back at the level above it)
                row["depth"] = overrides[f"{name}:{body[:40]}"]
            rows.append(row)
            continue
        style, n, end = num
        wrank = witness.rank(body, end) if witness else None
        key = f"{name}:{body[:40]}"
        amb = False
        prev = next((r for r in reversed(rows) if not r.get("heading")), None)
        top = cfg.get("base", {}).get(name, 1)
        run = announced(rows)
        retake = False
        if key in overrides:
            d = overrides[key]
            stack = (stack + [(None, 0)] * d)[:d]
            stack[d - 1] = (style, n)
        elif wrank is not None:
            # the later edition's mark: its rank is the depth (counted from its outermost
            # mark in the book, fixed after the first pass)
            d = max(1, wrank - cfg.get("_wmin", 0) + top)
            stack = (stack + [(None, 0)] * d)[:d]
            stack[d - 1] = (style, n)
        elif OPENING_CAPS.match(body) and stack:
            # a main head: the top level, carrying on its numbering
            stack = (stack + [(None, 0)] * top)[:top]
            stack[top - 1] = (style, n)
        elif n == 1 and run and run[1] == style and not (after_head and head_k is not None):
            # the points just announced, now opened one by one: the same level again
            d, k = run[0], run[2]
            del stack[d:]
            stack[d - 1] = (style, n)
            announced_at[d] = k
            retake = True
        elif n == 1 and not (after_head and head_k is not None):
            # a 1 opens a level below; flagged when nothing before announces the points,
            # since it may as well start a new run at a level above
            amb = bool(stack) and prev is not None and not ANNOUNCES.search(prev["text"][-200:])
            stack.append((style, n))
        elif after_head and head_k is not None and head_k < len(stack):
            del stack[head_k + 1:]
            stack[head_k] = (style, n)
        else:
            cands = [i for i, (s, v) in enumerate(stack) if v == n - 1]
            same = [i for i in cands if stack[i][0] == style]
            pick = same or cands
            # or a level whose points were announced and are being opened ("Secondly" after
            # the first point's own sub-points)
            opened = [i for i, (s, v) in enumerate(stack)
                      if s == style and announced_at.get(i + 1, 0) >= n > v]
            if pick:
                amb = len(pick) > 1
                i = max(pick)
            elif opened:
                i = max(opened)
            else:
                near = [i for i, (s, v) in enumerate(stack) if n - 3 <= v < n]
                i = max(near) if near else None
                amb = True
            if i is None:
                stack, i = [(style, n)], 0
            del stack[i + 1:]
            stack[i] = (style, n)
        for d in [d for d in announced_at if d > len(stack)]:
            del announced_at[d]
        if after_head:
            head_k, after_head = len(stack) - 1, False
        rows.append({"line": ln, "numbered": True, "depth": len(stack), "style": style,
                     "n": n, "ambiguous": amb, "retake": retake, "witness": wrank,
                     "key": key, "text": body})
    # the depth that is level 0: before the first edition heading the file's own (else that of
    # the points straight after edition headings, or 1); under each edition heading, the depth
    # of its first numbered point, so a heading takes the levels above it out of the indent
    base = cfg.get("base", {}).get(name)
    if base is None and witness:
        # the chapter's shallowest point is its top level (a later edition's marks may start
        # a chapter below its outermost one)
        base = min((r["depth"] for r in rows if r.get("numbered")), default=1)
    if base is None:
        after = [r["depth"] for a, r in zip(rows, rows[1:])
                 if a.get("heading") and not printed.match(a["text"]) and r.get("numbered")]
        base = min(after, default=1)
    sections = cfg.get("sections", True)
    level, here = 0, base
    for k, r in enumerate(rows):
        if r.get("heading"):
            level = 0
            if sections and not printed.match(r["text"]):
                nxt = next((q for q in rows[k + 1:] if q.get("numbered") or q.get("heading")), None)
                here = nxt["depth"] if nxt is not None and nxt.get("numbered") else base
        elif r.get("numbered"):
            r["level"] = level = max(0, r["depth"] - here)
        elif "depth" in r:
            r["level"] = level = max(0, r["depth"] - here)
        else:
            r["level"] = level
    # no level left empty between two others (a later edition can skip one of its marks)
    used = sorted({r["level"] for r in rows if "level" in r})
    close = {v: k for k, v in enumerate(used)}
    for r in rows:
        if "level" in r:
            r["level"] = close[r["level"]]
    return rows


HEADINGS_FROM = 3     # a file whose levels reach this deep gets edition headings proposed
HEADED_RUN = 4        # a point headed only when this many paragraphs or more stand under it


def propose_headings(rows):
    """Where edition headings would break a deep outline into sections: the numbered points at
    the shallowest level that leaves at most HEADINGS_FROM levels under the headings, each
    with HEADED_RUN paragraphs or more under it, and any shallower point after the first of
    them (it must not read as part of the section before). [(row, paragraphs under it)]."""
    levels = [r["level"] for r in rows if "level" in r]
    if not levels or max(levels) < HEADINGS_FROM:
        return []
    at = max(0, max(levels) - (HEADINGS_FROM - 1))
    paras = [r for r in rows if "level" in r]
    out, started = [], False
    for i, r in enumerate(paras):
        if not r.get("numbered") or r["level"] > at:
            continue
        under = 0
        for q in paras[i + 1:]:
            if q.get("numbered") and q["level"] <= r["level"]:
                break
            under += 1
        if r["level"] == at and under >= HEADED_RUN or started and r["level"] < at:
            out.append((r, under))
            started = True
    return out


def load_cfg(book):
    f = Path(book) / "source" / "outline.json"
    return json.loads(f.read_text()) if f.exists() else {}


def files(book, cfg):
    d = Path(book) / "chapters" / "typ"
    out = []
    for pat in cfg.get("files", ["*.typ"]):
        out += sorted(d.glob(pat))
    return out


def tree(rows, name):
    yield f"== {name}"
    for r in rows:
        if r.get("heading"):
            yield f"   {r['line']:4}   {r['text'][:70]}"
        elif r.get("numbered"):
            mark = ("?" if r["ambiguous"] else "*" if r.get("retake")
                    else "w" if r.get("witness") is not None else " ")
            text = re.sub(r"#\w+\[|\]", "", r["text"])
            yield f" {mark} {r['line']:4} {'    ' * r['level']}{text[:64 - 4 * r['level']]}"


def write(path, rows):
    """Set each paragraph in by its level (a #pad round it), or take a level away; a paragraph
    back at the top level straight after set-in ones keeps its first-line indent, as the TEI
    gives it back (tei_extract.py, layout.after_level)."""
    at = {r["line"]: r["level"] for r in rows if "level" in r}
    out, prev = [], 0
    indent = f"{layout.PAR_INDENT}["
    for ln, block in blocks(path.read_text()):
        if ln in at:
            body = strip_pad(block)
            if body.startswith(indent) and body.endswith("]"):
                body = body[len(indent):-1]
            if at[ln]:
                block = f"{layout.pad(at[ln])}{body}{layout.PAD_END}"
            else:
                block = f"{indent}{body}]" if prev else body
            prev = at[ln]
        else:
            prev = 0
        out.append(block)
    path.write_text("\n\n".join(out) + "\n")


def main(argv=None):
    import argparse
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("book")
    ap.add_argument("--json", help="write the levels and ambiguous places to this file")
    ap.add_argument("--write", action="store_true", help="set the paragraphs in, in chapters/typ")
    ap.add_argument("--headings", action="store_true",
                    help="where edition headings would break the deep outlines into sections")
    a = ap.parse_args(argv)
    run(a.book, a.json, a.write, a.headings)


def run(book, json_out=None, write_files=False, headings=False):
    """Print the tree of every file, optionally write the levels as JSON and into chapters/typ,
    or list where edition headings would break the deep outlines into sections."""
    cfg = load_cfg(book)
    if cfg.get("witness"):
        # first pass: the outermost mark the witness uses for the book's numbered points
        cfg["_witness"] = Witness(Path(book) / "source" / cfg["witness"])
        ranks = [r["witness"] for f in files(book, cfg)
                 for r in infer(f.name, f.read_text(), cfg) if r.get("witness") is not None]
        cfg["_wmin"] = min(ranks, default=0)
        cfg["_witness"].at = 0
    result, amb = {}, 0
    for f in files(book, cfg):
        rows = infer(f.name, f.read_text(), cfg)
        result[f.name] = rows
        amb += sum(1 for r in rows if r.get("ambiguous"))
        if headings:
            for r, under in propose_headings(rows):
                print(f"{f.name}:{r['line']}  (level {r['level']}, {under} under it)  "
                      f"{re.sub(r'#\\w+\\[|\\]', '', r['text'])[:80]}")
            continue
        for line in tree(rows, f.name):
            print(line)
        if write_files:
            write(f, rows)
    numbered = sum(1 for rows in result.values() for r in rows if r.get("numbered"))
    print(f"{numbered} numbered paragraphs, {amb} ambiguous (settle in source/outline.json)")
    if json_out:
        Path(json_out).write_text(json.dumps(result, ensure_ascii=False, indent=1))
    return result


if __name__ == "__main__":
    main()
