"""
The machine pass (#auto): readings computed from the source alone, and
the reading stream (what the modern text says, token by token).
"""

import re

import teibuild  # noqa: F401  (puts colophon on sys.path)

from teitok import T, Tok, local  # noqa: E402
from spelling import modernize_word_lower  # noqa: E402
import layout  # noqa: E402

from teibuild import settings as S  # noqa: E402
from teibuild.settings import INTERJECTIONS, LATIN_MIN_WORDS, QUOTE_MIN_WORDS  # noqa: E402
from teibuild.words import auto_reg, word_strings  # noqa: E402
from teibuild.state import BLOCK_MARK, HEAD_MODE, SPLIT_RE, SUBTITLES  # noqa: E402


def compute_auto(toks):
    """Fill tok.orig/expanded/reg for every word/punct token.

    Main text gets automatic modern spelling with the same sentence-case
    rules the earlier Typst renderer used (so an unreviewed file reads the
    same as before): the first word of a paragraph/item/signature, or the
    first word after a . ! or ?, is capitalized; a short list of common
    nouns that the 1609 printing capitalized mid-sentence is lowercased.
    Footnotes are left in original spelling (abbreviations expanded only).
    Division headings keep their printed case pattern."""
    state = {"start": True}
    latin = latin_tokens(toks) if S.LATIN_RUNS else set()

    def walk(ts, in_note, in_head):
        for t in ts:
            if t.kind == "container":
                n = local(t.el)
                if n in ("p", "item", "signed", "trailer") or n == "head":
                    state["start"], state["by"] = True, "block"
                # legacy quirk kept for continuity: an italic boundary right
                # after a full stop did not start a new sentence
                is_emph = n == "hi" and t.el.get("rend") != "sup" and S.ITALIC_SENTENCE_QUIRK

                def emph_boundary():
                    if S.ITALIC_SENTENCE_QUIRK != "after-stop" or state.get("by") == "punct":
                        state["start"] = False
                if is_emph:
                    emph_boundary()
                if n == "hi" and t.el.get("rend") != "sup" and S.QUOTE_START_CASE \
                        and not (in_note or in_head):
                    words = re.findall(r"[A-Za-z]+", "".join(t.el.itertext()))
                    state["quote_first"] = len(words) >= QUOTE_MIN_WORDS
                saved = state["start"]
                is_div_head = n == "head" and t.el.getparent() is not None \
                    and local(t.el.getparent()) == "div"
                # a table set as a list: its cells keep the printed capitals
                plain_cell = n == "cell" and table_mode(t.el) != "inline"
                # MODERNIZE_NOTES = "case": a note is set as body text (sentence case, the
                # book's LOWERCASE_COMMON_NOUNS), with its own sentences
                note_body = n == "note" and S.MODERNIZE_NOTES == "case"
                if note_body:
                    outer = dict(state)
                    state.clear()
                    state.update(start=True, by="block")
                walk(t.children, (in_note or n == "note") and not note_body,
                     in_head or is_div_head or plain_cell)
                if note_body:
                    state.clear()
                    state.update(outer)
                if n == "note":
                    state["start"] = saved
                if is_emph:
                    emph_boundary()
            elif t.kind == "word":
                word_strings(t)
                t.resp, t.rtype = "#auto", "spelling"
                if id(t) in latin:
                    state.pop("quote_first", None)
                    t.reg = t.expanded.replace("ſ", "s").replace("Ʋ", "U")
                    if not in_note:
                        state["start"] = False
                    continue
                if in_note:
                    t.reg = auto_reg(t, False, heading=True) if S.MODERNIZE_NOTES \
                        else t.expanded.replace("ſ", "s")
                    continue
                if in_head:
                    t.reg = auto_reg(t, False, heading=True)
                else:
                    t.reg = auto_reg(t, state["start"],
                                     quote_start=state.pop("quote_first", False))
                    if re.search(r"[A-Za-z]", t.expanded):
                        state["start"], state["by"] = False, None
                    state["num"] = bool(re.fullmatch(r"\d+", t.expanded))
                    state["word"] = t.expanded.lower()
            elif t.kind == "punct":
                p = t.pieces[0]
                t.orig = p if isinstance(p, str) else (p.text or "")
                t.reg = t.orig
                if not in_note and not in_head:
                    # "1." opening a paragraph is its numeral, not a sentence
                    numeral = state.get("num") and state["start"] and \
                        state.get("by") == "block" and t.orig == "."
                    state["start"] = t.orig in ".!?"
                    if t.orig == "!" and state.get("word") in INTERJECTIONS:
                        state["start"] = False      # "oh! how", "Ah! you": the sentence goes on
                    state["word"] = None
                    if not numeral:
                        state["by"] = "punct" if state["start"] else None
                    state["num"] = False
    walk(toks, False, False)
    if S.DROP_FOREIGN_GAPS or S.GAP_NOTES:
        gap_readings(toks)
    if S.EXPAND_ETC:
        expand_etc(toks)
    table_readings(toks)
    page_break_spaces(toks)
    if S.TYPOGRAPHY:
        typography(toks)
        note_spaces(toks)


def page_break_spaces(toks):
    """A page break keyed between two words with no space (A47561:
    "leaſt<pb n="14"/>to"): the word space the printed page break stands for,
    as an #auto spacing reading."""
    def walk(ts):
        for t in ts:
            if t.kind == "container":
                walk(t.children)
        for i in range(len(ts) - 2, 0, -1):
            a, pb, b = ts[i - 1], ts[i], ts[i + 1]
            if pb.kind == "atom" and pb.el is not None and local(pb.el) == "pb" \
                    and a.kind in ("word", "punct") and b.kind in ("word", "container") \
                    and not (b.kind == "container" and local(b.el) == "note"):
                s = Tok("spacing", [""])
                s.reg, s.resp, s.parent = " ", "#auto", pb.parent
                ts.insert(i + 1, s)
        for k, c in enumerate(ts):
            c.idx = k
    walk(toks)


def note_spaces(toks):
    """TYPOGRAPHY: CCEL keys some footnotes after the word space ("he was
    <note>…</note>ready"), which would print the marker loose and glue the
    next word to it. The space moves after the note: dropped before it and
    added after it, as #auto spacing readings."""
    def walk(ts):
        for t in ts:
            if t.kind == "container":
                walk(t.children)
        for i in range(len(ts) - 2, 0, -1):
            a, sp, n = ts[i - 1], ts[i], ts[i + 1]
            if not (sp.kind == "space" and a.kind in ("word", "punct") and
                    n.kind == "container" and local(n.el) == "note" and
                    n.el.get("place") == "foot"):
                continue
            sp.kind, sp.reg, sp.resp = "spacing", "", "#auto"
            b = ts[i + 2] if i + 2 < len(ts) else None
            if b is not None and (b.kind == "word" or
                                  (b.kind == "punct" and (b.orig or "") in "“‘(\"'")):
                s = Tok("spacing", [""])
                s.reg, s.resp, s.parent = " ", "#auto", n.parent
                ts.insert(i + 2, s)
        for k, c in enumerate(ts):
            c.idx = k
    walk(toks)


TYPO_BLOCKS = {"p", "head", "item", "l", "note", "cell", "titlePart", "byline",
               "docAuthor", "signed", "trailer", "label"}


TYPO_CLOSERS = set(".,;:!?)]")


def typography(toks):
    """TYPOGRAPHY: curl straight quotes, set "--" as an em dash."""
    leaves = []

    def walk(ts):
        for t in ts:
            if t.kind == "container":
                if local(t.el) in TYPO_BLOCKS:
                    leaves.append(None)            # a block starts: nothing before
                walk(t.children)
            elif t.kind in ("word", "punct", "space", "noise"):
                leaves.append(t)
    walk(toks)
    prev = " "

    def curl(c, prev):
        closing = prev.isalnum() or prev in TYPO_CLOSERS
        if c == "'":
            return "\u2019" if closing else "\u2018"
        return "\u201d" if closing else "\u201c"

    for i, t in enumerate(leaves):
        if t is None:
            prev = " "
            continue
        if t.kind in ("space", "noise"):
            prev = " "
            continue
        cur = t.reg if t.reg is not None else t.orig
        if cur is None:
            continue
        if t.kind == "punct" and cur == "-":
            # "--", or "-" at a line end and "-" opening the next line (a
            # dash the keying split at the line break)
            j = i + 1
            if j < len(leaves) and leaves[j] is not None and \
                    leaves[j].kind in ("space", "noise") and "\n" in (leaves[j].pieces[0] or ""):
                j += 1
            nxt = leaves[j] if j < len(leaves) else None
            if nxt is not None and nxt.kind == "punct" and \
                    (nxt.reg if nxt.reg is not None else nxt.orig) == "-":
                t.reg, t.resp, t.rtype = S.DASH, "#auto", "punctuation"
                nxt.reg, nxt.resp, nxt.rtype = "", "#auto", "punctuation"
                prev = S.DASH[-1]
                continue
        if "'" in cur or '"' in cur:
            out = []
            for c in cur:
                if c in "'\"":
                    c = curl(c, prev)
                out.append(c)
                prev = c
            new = "".join(out)
            if new != cur:
                t.reg, t.resp = new, "#auto"
                if t.kind == "punct" or new.replace("\u2019", "'").replace("\u2018", "'") == \
                        (t.expanded if t.kind == "word" else cur):
                    t.rtype = "punctuation"
            continue
        if cur:
            prev = cur[-1]


def table_mode(cell_el):
    t = next((a for a in cell_el.iterancestors() if local(a) == "table"), None)
    return layout.table_reading(t)[0] if t is not None else None


def cell_leaves(ct):
    """Word and punctuation tokens of a cell, notes left out."""
    out = []

    def walk(ts):
        for t in ts:
            if t.kind == "container":
                if local(t.el) != "note":
                    walk(t.children)
            elif t.kind in ("word", "punct"):
                out.append(t)
    walk(ct.children)
    return out


def table_readings(toks):
    """A table set as a list (layout.table_reading) gets the tidying a list
    needs, as machine readings: a brace's items lose their printed number and
    trailing comma, open with a capital and, in the last column, end with a
    full stop; a label loses its trailing comma; a row-wise table's number
    cells are left out; a table read inline into its sentence has its cells
    joined with commas."""
    def cells_of(t):
        out = {}

        def walk(ts):
            for c in ts:
                if c.kind == "container":
                    if local(c.el) == "cell":
                        out[c.el] = c
                    else:
                        walk(c.children)
        walk(t.children)
        return out

    def omit(x, typ="omission"):
        x.reg, x.rtype, x.resp = "", typ, "#auto"

    def reading(x):
        return x.reg if x.reg is not None else (x.orig or "")

    def strip_comma(ls):
        if ls and ls[-1].kind == "punct" and ls[-1].orig == ",":
            omit(ls[-1], "punctuation")
            return True
        return False

    def visit(ts):
        for t in ts:
            if t.kind != "container":
                continue
            if local(t.el) != "table":
                visit(t.children)
                continue
            mode, blocks = layout.table_reading(t.el)
            cells = cells_of(t)
            if mode == "inline":
                cs = [cells[c] for _m, cl in blocks for c in cl if c in cells]
                for k, ct in enumerate(cs):
                    ls = [x for x in cell_leaves(ct) if reading(x)]
                    if not ls:
                        continue
                    if k == len(cs) - 1:
                        strip_comma(ls)
                    elif not (ls[-1].kind == "punct" and ls[-1].orig == ","):
                        last = ls[-1]
                        last.reg = reading(last) + ","
                        last.rtype, last.resp = "punctuation", "#auto"
                continue
            last_col = max((i for i, (m, _c) in enumerate(blocks) if m == "¶"), default=-1)
            for i, (marker, cl) in enumerate(blocks):
                cts = [cells[c] for c in cl if c in cells]
                if mode == "rows":
                    if marker == "+" and len(cts) > 1 and \
                            re.fullmatch(layout.NUMBER_CELL, " ".join(
                                "".join(cts[0].el.itertext()).split())):
                        for x in cell_leaves(cts[0]):
                            omit(x)
                    continue
                for ct in cts:
                    ls = cell_leaves(ct)
                    if marker == "¶":
                        strip_comma(ls)
                        continue
                    # an item: printed number, trailing comma, capital, stop
                    if len(ls) >= 2 and ls[0].kind == "word" and \
                            re.fullmatch(r"\d{1,2}", reading(ls[0])) and \
                            ls[1].kind == "punct" and ls[1].orig in ".)":
                        omit(ls[0])
                        omit(ls[1])
                    live = [x for x in ls if reading(x)]
                    strip_comma(live)
                    live = [x for x in live if reading(x)]
                    first = next((x for x in live if x.kind == "word"), None)
                    if first is not None and reading(first)[:1].islower():
                        first.reg = reading(first)[:1].upper() + reading(first)[1:]
                        first.rtype, first.resp = "case", "#auto"
                    final = i > last_col
                    if final and live and not re.search(
                            r"[.!?:;][\s)\]]*$", "".join(reading(x) for x in live)):
                        last = live[-1]
                        last.reg = reading(last) + "."
                        last.rtype, last.resp = "punctuation", "#auto"
    visit(toks)


def expand_etc(toks):
    """&c. -> etc.: the ampersand reads "etc", the c nothing."""
    def walk(ts):
        kids = [c for c in ts if c.kind != "noise"]
        for a, b in zip(kids, kids[1:]):
            if a.kind == "punct" and a.orig == "&" and b.kind == "word" and \
                    (b.expanded or "").lower() == "c":
                a.reg, a.rtype, a.resp = ("Etc" if b.expanded == "C" else "etc"), \
                    "abbreviation", "#auto"
                b.reg, b.rtype = "", "abbreviation"
                after = kids[kids.index(b) + 1] if kids.index(b) + 1 < len(kids) else None
                if not (after is not None and after.kind == "punct" and after.orig == "."):
                    a.reg += "."                  # "&c" printed without its stop
        for c in ts:
            if c.kind == "container":
                walk(c.children)
    walk(toks)


def gap_only(t):
    """The <gap> elements of a word token made of nothing but gaps."""
    els = [p for p in t.pieces if not isinstance(p, (str, tuple))]
    if not els or any(local(p) != "gap" for p in els):
        return []
    if any(isinstance(p, str) and p.strip() for p in t.pieces):
        return []
    return els


def gap_readings(toks):
    """DROP_FOREIGN_GAPS and GAP_NOTES: readings for words that are only a gap."""
    def walk(ts, in_note):
        kids = [c for c in ts if c.kind != "noise"]
        for i, t in enumerate(kids):
            if t.kind == "container":
                walk(t.children, in_note or local(t.el) == "note")
                continue
            if t.kind != "word":
                continue
            gaps = gap_only(t)
            if not gaps:
                continue
            reason = gaps[0].get("reason")
            if all(i in S.GAP_FIXES for i, _g in t.gaps):
                continue                        # filled in: <supplied>
            if reason in S.GAP_NOTES:
                t.reg = S.GAP_NOTES[reason].format(
                    extent=(gaps[0].get("extent") or "").capitalize())
                t.rtype = "editorial"
            elif reason == "foreign" and S.DROP_FOREIGN_GAPS:
                t.reg, t.rtype = "", "omission"
                prev = kids[i - 1] if i else None
                nxt = kids[i + 1] if i + 1 < len(kids) else None
                # punctuation left stranded after it: at the start of a note
                # or block it goes; mid-sentence the space before the gap goes
                first = all(k.kind in ("space", "atom") or
                            (k.kind == "word" and k.reg == "") for k in kids[:i])
                if nxt is not None and nxt.kind == "punct" and nxt.orig in ".,;:":
                    if first:
                        nxt.reg, nxt.rtype, nxt.resp = "", "omission", "#auto"
                        after = kids[i + 2] if i + 2 < len(kids) else None
                        if after is not None and after.kind == "space":
                            after.kind, after.reg, after.resp = "spacing", "", "#auto"
                    elif prev is not None and prev.kind == "space":
                        prev.kind, prev.reg, prev.resp = "spacing", "", "#auto"
                elif nxt is not None and nxt.kind == "space" and \
                        (first or (prev is not None and prev.kind == "space")):
                    nxt.kind, nxt.reg, nxt.resp = "spacing", "", "#auto"
    walk(toks, False)


def latin_tokens(toks):
    """ids of the word tokens in Latin runs (see LATIN_RUNS): a run is the
    words of one container between two child containers (italics, notes)."""
    from spelling import _SPELL

    def english(w):
        low = w.lower()
        return low in _SPELL or modernize_word_lower(low) in _SPELL

    out = set()

    def judge(run):
        words = [t for t in run if re.search(r"[A-Za-z]", t.expanded or "")]
        if len(words) < LATIN_MIN_WORDS:
            return
        texts = [t.expanded.replace("ſ", "s") for t in words]
        eng = sum(english(re.sub(r"[^A-Za-z']", "", w)) for w in texts)
        if eng * 2 < len(words):
            out.update(id(t) for t in words)

    def walk(ts):
        run = []
        for t in ts:
            if t.kind == "container":
                judge(run)
                run = []
                walk(t.children)
            elif t.kind == "word":
                word_strings(t)
                run.append(t)
        judge(run)
    walk(toks)
    return out


def stream(toks, skip_heads=True):
    """Flatten tokens to [(text, kind, tok, container_path)]; kind 'w' or 'm'."""
    out = []

    def has_words(t):
        if t.kind in ("word", "punct"):
            return bool(t.reg if t.reg is not None else t.orig)
        return t.kind == "container" and local(t.el) != "note" and \
            any(has_words(c) for c in t.children or [])

    def walk(ts, path, pending=False):
        # a paragraph split around a block list or table goes on as a new
        # paragraph after it (layout.p_blocks)
        par = path[-1].el if path and path[-1].el is not None else None
        split = layout.p_blocks(par) if par is not None and local(par) == "p" else []
        for t in ts:
            if t.kind == "container" and t.el in split:
                pending = True          # a new paragraph after the block ...
            elif pending and has_words(t):
                out.append(("¶", "m", t, path))   # ... if text follows it
                pending = False
            if t.kind == "container" and local(t.el) == "table":
                table(t, path)
                continue
            if t.kind == "container":
                n = local(t.el)
                if n == "head" and t.el in SUBTITLES:
                    out.append(("¶", "m", t, path))      # a block of its own
                    walk(t.children, path + (t,))
                    continue
                if skip_heads and n == "head" and local(t.el.getparent()) == "div":
                    if not HEAD_MODE["on"]:
                        continue
                    run_in = t.el.getparent().get("type") in HEAD_MODE["run_in"]
                    out.append(("¶" if run_in else "H", "m", t, path))
                    walk(t.children, path + (t,))
                    continue
                if n == "closer" and layout.closer_lines(t.el) is not None:
                    # signatories one to a line, then place and date
                    toks_of = {}

                    def index(ts_):
                        for c in ts_:
                            if c.kind == "container":
                                toks_of[c.el] = c
                                index(c.children)
                    index(t.children)
                    for el in layout.closer_lines(t.el):
                        out.append(("¶", "m", toks_of[el], path))
                        walk(toks_of[el].children, path + (t, toks_of[el]))
                    continue
                if HEAD_MODE["on"] and n == "epigraph":
                    out.append(("¶", "m", t, path))
                # an item that only wraps a nested list continues the
                # previous item (that is how the Typst lists are nested)
                list_only = n == "item" and all(
                    c.kind in ("space", "noise") or
                    (c.kind == "container" and local(c.el) == "list")
                    for c in t.children)
                # a quotation standing between paragraphs is a block of its
                # own, unless it is made of paragraphs itself
                block_q = n == "q" and t.el.getparent() is not None and \
                    local(t.el.getparent()) == "div" and t.el.find(T + "p") is None
                in_epigraph = HEAD_MODE["on"] and any(
                    local(a.el) == "epigraph" for a in path if a.el is not None)
                if n == "p" and layout.p_blocks(t.el):
                    # opened only if text comes before its first block
                    walk(t.children, path + (t,), pending=True)
                    continue
                # a quotation block of the source (CCEL blockquote, verse) is
                # the review's #quote[...]; its paragraphs open no block
                if n == "quote":
                    # (a stanza of a section made of verse is a plain block)
                    out.append(("¶" if layout.verse_division(t.el) else ">", "m", t, path))
                    walk(t.children, path + (t,))
                    continue
                in_quote = n == "p" and t.el.getparent() is not None and \
                    local(t.el.getparent()) == "quote"
                # a speech opens a block with its speaker ("Christian: ..."),
                # which its first paragraph continues
                speech = n == "p" and t.el.getparent() is not None and \
                    local(t.el.getparent()) == "sp" and \
                    t.el.getprevious() is not None and local(t.el.getprevious()) == "speaker"
                if (n in BLOCK_MARK or block_q) and not list_only and not in_epigraph \
                        and not in_quote and not speech:
                    out.append((BLOCK_MARK.get(n, "¶"), "m", t, path))
                walk(t.children, path + (t,))
            elif t.kind in ("word", "punct"):
                txt = t.reg if t.reg is not None else t.orig
                for s in SPLIT_RE.findall(txt or ""):
                    out.append((s, "w", t, path))

    def table(t, path):
        """A table in the edition's reading order (layout.table_reading)."""
        cells = {}

        def find(ts):
            for c in ts:
                if c.kind == "container":
                    if local(c.el) == "cell":
                        cells[c.el] = c
                    else:
                        find(c.children)
        find(t.children)
        _mode, blocks = layout.table_reading(t.el)
        for marker, cl in blocks:
            if marker:
                out.append((marker, "m", t, path))
            for c in cl:
                if c in cells:
                    walk(cells[c].children, path + (t, cells[c]))
    walk(toks, ())
    return out
