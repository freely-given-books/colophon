#!/usr/bin/env python3
"""
Rules every book keeps: lessons from CLAUDE.md and the editor's standing
decisions, as checks. verify.py runs them as its step [6]; each returns the
places that break it (empty: kept).

  spelling_archaisms  colophon lesson 5: grammatical archaisms (hath, thou,
                      -eth) are not spellings; spelling.py never modernizes
                      them, only the editor does (reg[@type="grammar"])
  god_capitalized     the editor's rule (2026-11-01): God is always
                      capitalized; the machine never lowercases a printed
                      "God" (the editor may, for a false god)
  sweep_clean         books lesson 3 (thin spaces keyed as full ones) and
                      colophon lesson 12 (#emph[..]; swallows the ";"):
                      sweep.py's spacing and semicolon hits in chapters/typ
  quotes_curled       colophon lesson 15: no closing quotation mark set as
                      an opening one (a straight ' inside a single quotation
                      closes it), in the ebook's text and, when pdftotext is
                      installed, in the compiled chapters

  python3 rules.py BOOK_DIR      the book rules on their own
"""

import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from lxml import etree  # noqa: E402

import sweep  # noqa: E402
from teitok import T  # noqa: E402

# a word, then an opening quotation mark where a closing one belongs
WRONG_CLOSE = re.compile(r"\w[‘“](?=[\s,.;:!?)\]]|$)", re.M)


def context(text, m, before=40, after=25):
    return "…" + " ".join(text[max(0, m.start() - before):m.end() + after].split()) + "…"


# breaks of a rule kept until a signed book that relies on them is revised
# (changing them rewrites its TEI): entry -> why
KNOWN = {}


def spelling_archaisms():
    import spelling
    from teibuild.decisions import ARCHAIC
    out = []
    for table in ("MANUAL", "NAMES"):
        for k, v in getattr(spelling, table).items():
            word = k.lower()
            if word in KNOWN:
                continue
            if word in ARCHAIC and v.lower() != word:
                out.append(f"spelling.{table}: {k} -> {v} (a grammatical archaism)")
            elif word.endswith("eth") and v.lower().endswith("s"):
                # -eth made -s (approueth -> approves) is grammar; moneth ->
                # month is spelling
                out.append(f"spelling.{table}: {k} -> {v} (an archaic ending)")
    return out


def god_capitalized(tei):
    out = []
    for choice in etree.parse(str(tei)).getroot().iter(T + "choice"):
        orig = choice.find(T + "orig")
        if orig is None or not re.search(r"\bG(?:od|OD)\b", "".join(orig.itertext())):
            continue
        for reg in choice.findall(T + "reg"):
            if reg.get("resp") == "#auto" and re.search(r"\bgod\b", "".join(reg.itertext())):
                out.append(f"the machine lowercases a printed God: "
                           f"{''.join(orig.itertext())!r} -> {''.join(reg.itertext())!r}")
    return out


def sweep_clean(book):
    kinds = {k: re.compile(p) for k, p in sweep.CHECKS if k in ("spacing", "semicolon")}
    out = []
    for f in sorted((book / "chapters" / "typ").rglob("*.typ")):
        flat = sweep.prose(f.read_text(encoding="utf-8"))
        for kind, pat in kinds.items():
            for m in pat.finditer(flat):
                out.append(f"{f.relative_to(book)}: {kind} {context(flat, m)}")
    return out


def quotes_curled(tei, pdf=None):
    out = []
    with tempfile.TemporaryDirectory(prefix="fgb-rules-") as t:
        html = Path(t) / "book.html"
        r = subprocess.run([sys.executable, str(HERE / "tei_to_html.py"), str(tei), str(html)],
                           capture_output=True, text=True)
        if r.returncode:
            return [f"tei_to_html.py failed: {(r.stdout + r.stderr)[-500:]}"]
        text = re.sub(r"<[^>]+>", "", html.read_text(encoding="utf-8"))
        out += [f"ebook: closing quote set as opening {context(text, m)}"
                for m in WRONG_CLOSE.finditer(text)]
    if pdf is not None and Path(pdf).exists() and shutil.which("pdftotext"):
        text = subprocess.run(["pdftotext", "-layout", str(pdf), "-"],
                              capture_output=True, text=True).stdout
        out += [f"print: closing quote set as opening {context(text, m)}"
                for m in WRONG_CLOSE.finditer(text)]
    return out


def book_rules(book, tei, pdf=None):
    """[(rule, problems)] for one book."""
    return [("spelling_archaisms", spelling_archaisms()),
            ("god_capitalized", god_capitalized(tei)),
            ("sweep_clean", sweep_clean(book)),
            ("quotes_curled", quotes_curled(tei, pdf))]


if __name__ == "__main__":
    book = Path(sys.argv[1])
    tei = next((book / "source").glob("*.tei.xml"))
    bad = False
    for rule, problems in book_rules(book, tei):
        print(f"{rule}: {'kept' if not problems else f'{len(problems)} problem(s)'}")
        for p in problems[:20]:
            print("    " + p)
        bad |= bool(problems)
    sys.exit(1 if bad else 0)
