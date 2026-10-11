"""
How faithfully an edition represents its source, counted from the TEI's own
record of every decision: how many printed words there are, how many the
edition changes and in what way, what it adds or takes out, and what the
transcription lacked and whether it was restored.

  ./fgb coverage [BOOK]           one book, or every TEI book

Words are the printed text's (the orig layer of text/, the header aside),
in the divisions the edition keeps: those in the book's SKIP_DIVISIONS (a
table of contents, an advertisement) are left out of every count. A gap the
TCP marks as a duplicate (text printed twice) is not missing text, and a
gap in a printed note the edition leaves out is not counted.
A <choice> counts once, under its effective reading (the editor's when there
is one, else the machine's); form = spelling, case, punctuation, spacing and
expanded abbreviations; grammar = archaic forms modernized; wording =
emendations (another word, a word added or removed, a changed number).
"""

import re
import sys
from pathlib import Path

from lxml import etree

T = "{http://www.tei-c.org/ns/1.0}"
WORD = re.compile(r"\w+(?:['’]\w+)*")
FORM = {"spelling", "case", "punctuation", "spacing"}


def words(s):
    return len(WORD.findall(s or ""))


def printed_text(el):
    """el's text as printed: <orig>/<abbr>/<sic> of every choice, not the
    readings, not notes the editor added."""
    out = []

    def walk(e):
        if not isinstance(e.tag, str):
            return
        tag = e.tag[len(T):] if e.tag.startswith(T) else e.tag
        if tag in ("reg", "expan", "corr") and e.getparent() is not None \
                and e.getparent().tag == T + "choice":
            pass
        elif tag == "note" and e.get("ana") == "#edition-only":
            pass
        elif tag == "label" and e.get("ana") == "#edition-only":
            pass
        else:
            out.append(e.text or "")
            for c in e:
                walk(c)
        out.append(e.tail or "")
    out.append(el.text or "")
    for c in el:
        walk(c)
    return " ".join(out)


def reading(choice):
    regs = choice.findall(T + "reg")
    for r in regs:
        if r.get("resp") == "#editor":
            return r
    return regs[0] if regs else choice.find(T + "expan")


def coverage(tei):
    import copy
    import layout
    skip = set(layout.settings(tei).get("SKIP_DIVISIONS", ()))
    root = etree.parse(str(tei)).getroot()
    text = copy.deepcopy(root.find(T + "text"))
    for el in list(text.iter(T + "div", T + "titlePage")):
        if el.get("type") in skip or (el.tag == T + "titlePage" and "titlePage" in skip):
            if el.getparent() is not None:
                el.getparent().remove(el)
    c = {"words": words(printed_text(text)), "form": 0, "grammar": 0, "wording": 0,
         "added": 0, "removed": 0, "by_editor": 0, "by_machine": 0,
         "gaps": 0, "restored": 0, "open": 0, "notes_added": 0, "notes_dropped": 0}
    for ch in text.iter(T + "choice"):
        if ch.find(T + "orig") is None and ch.find(T + "abbr") is None:
            continue
        r = reading(ch)
        if r is None:
            continue
        o = ch.find(T + "orig") if ch.find(T + "orig") is not None else ch.find(T + "abbr")
        n_o, n_r = words(printed_text(o)), words("".join(r.itertext()))
        kind = r.get("type") or "spelling"          # an <expan> is a spelling
        if kind in FORM:
            c["form"] += n_o
        elif kind == "grammar":
            c["grammar"] += n_o
        else:
            c["wording"] += n_o
            c["added"] += max(0, n_r - n_o)
            c["removed"] += max(0, n_o - n_r)
        c["by_editor" if r.get("resp") == "#editor" else "by_machine"] += 1
    for g in text.iter(T + "gap"):
        # text printed twice is not missing; a gap in a printed note the
        # edition leaves out is not in the edition
        if g.get("reason") == "duplicate" or any(
                a.tag == T + "note" and a.get("ana") == "#print-only"
                for a in g.iterancestors()):
            continue
        c["gaps"] += 1
        # restored: supplied letters, or a printed form the edition's reading
        # replaces (the editor filled it in the review)
        if any(a.tag == T + "supplied" or (a.tag == T + "orig" and a.getparent().tag == T + "choice"
               and reading(a.getparent()) is not None) for a in g.iterancestors()):
            c["restored"] += 1
        else:
            c["open"] += 1
    for n in text.iter(T + "note"):
        if n.get("ana") == "#edition-only":
            c["notes_added"] += 1
        elif n.get("ana") == "#print-only":
            c["notes_dropped"] += 1
    w = c["words"] or 1
    c["unchanged"] = round(100 * (1 - (c["form"] + c["grammar"] + c["wording"]) / w), 1)
    for k in ("form", "grammar", "wording"):
        c[k + "_pct"] = round(100 * c[k] / w, 1)
    return c


def summary(c):
    """The coverage as lines for a catalog or a terminal."""
    lines = [
        f"{c['words']:,} printed words; {c['unchanged']}% as printed",
        f"changed in form only (spelling, case, punctuation): {c['form']:,} words ({c['form_pct']}%)",
        f"grammar modernized (hath -> has, thou -> you): {c['grammar']:,} words ({c['grammar_pct']}%)",
        f"changed in wording (emendations): {c['wording']:,} words ({c['wording_pct']}%); "
        f"{c['added']:,} words added, {c['removed']:,} removed",
    ]
    if c["gaps"]:
        lines.append(f"gaps in the transcription: {c['gaps']}, {c['restored']} restored, "
                     f"{c['open']} left open")
    else:
        lines.append("gaps in the transcription: none")
    if c["notes_added"] or c["notes_dropped"]:
        lines.append(f"notes: {c['notes_added']} added by the editor, "
                     f"{c['notes_dropped']} printed notes left out")
    return lines


if __name__ == "__main__":
    for p in sys.argv[1:]:
        print(Path(p).name)
        for line in summary(coverage(p)):
            print("  " + line)
