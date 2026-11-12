"""
The light pass: a TCP book's printed text (its orig layer) against OCR
witnesses of the same print, to find words the transcription left out or
misread.

  ./fgb collate BOOK OUT_DIR WITNESS.txt WITNESS.txt [...] [--agree N]

BOOK_DIR: books/<author>/<book> (needs source/*.tei.xml). WITNESS: OCR text
in the witness-export layout ("--- Source PDF page N ..." lines between
pages): source/ocr/<scan>.glm.witness.txt, .tesseract.witness.txt, or a
bundle's export (ocr/bundle.py: ./fgb ocr export). A place is listed only when at
least N witnesses (default: all) differ from the TCP there.

Two passes, both into OUT_DIR:
  extra.md     witness words the TCP lacks (dropped words: Perkins "Lombard,",
               "though"), or a different word ("of" for "or")
  --modern     compare words in modern spelling: for witnesses of a later
               printing or a modern text, which respell (waies -> ways)
  nearmiss.md  one-word swaps the witnesses agree on but that look like
               spelling (this/his, them/then, bough/bought): the first pass
               filters these as noise

Everything listed is a candidate only: read each on the page image before
it goes in the book's supplement (<corrections>, colophon 0.33.0). OCR
engines share misreads (b/h, long s), and a turned letter in the print
("aud") is what was printed. First run: Perkins, Christian Oeconomie,
2026-11-01 (8 TCP errors out of ~40 candidates); its output is the test
this must reproduce (moved from local-tools/tcp_collate.py, 2026-11-05).
"""
import argparse, difflib, re, subprocess, sys, tempfile
from pathlib import Path

COLOPHON = Path(__file__).resolve().parent.parent


# --modern: words compared in modern spelling (colophon's spelling.py), for
# witnesses of a later printing or a modern text, which respell (waies ->
# ways, knowes -> knows); off for OCR of the TCP's own printing
MODERN = {"on": False}
_modern = {}          # word -> its modern spelling


ROMAN = re.compile(r"(?=[ivxlc]{2,}$)c{0,3}(xc|xl|l?x{0,3})(ix|iv|v?i{0,3})$")


def modern_words(ws):
    """--modern: "&" read as "and"; roman numerals (chapter numbers of
    references, which a later text sets otherwise) left out. Without it
    the words as they were: an "&" is not a word."""
    if not MODERN["on"]:
        return [w for w in ws if w != "&"]
    return ["and" if w == "&" else w for w in ws if not ROMAN.match(w.lower())]


def norm(w):
    if MODERN.get("on"):
        lw = w.lower().replace("ſ", "s")
        if lw not in _modern:
            from spelling import modernize_word_lower
            _modern[lw] = modernize_word_lower(lw)
        w = _modern[lw]
    w = w.lower().replace("ſ", "s").replace("f", "s")   # Tesseract reads long s as f
    w = w.replace("v", "u").replace("j", "i").replace("y", "i").replace("w", "uu")
    w = re.sub(r"(.)\1+", r"\1", w)
    return w[:-1] if len(w) > 3 and w.endswith("e") else w


def similar(x, y):
    return difflib.SequenceMatcher(None, norm(x), norm(y)).ratio() > 0.7


HEAD = {norm(w) for w in "of chap chapter epistle dedicatorie signature".split()}


def typ_files(tei, d):
    """The extracted chapter files in reading order: the book's layout (files may sit in
    folders, part-1/...), else the classic dedication first, then by name."""
    import layout
    from lxml import etree
    cfg = layout.settings(tei)
    files = layout.book_layout(etree.parse(str(tei)).getroot(), cfg) if cfg.get("LAYOUT") else None
    if files:
        return [d / f["file"] for f in files if (d / f["file"]).exists()]
    return sorted(d.rglob("*.typ"), key=lambda p: (p.stem != "dedication", str(p.relative_to(d))))


def tcp_words(book):
    """The orig layer's body words (margin notes out: OCR seldom has them)."""
    tei = next((book / "source").glob("*.tei.xml"))
    with tempfile.TemporaryDirectory() as d:
        subprocess.run([sys.executable, str(COLOPHON / "tei_extract.py"), str(tei), d,
                        "--layer", "orig", "--expand"], check=True, capture_output=True)
        files = typ_files(tei, Path(d))
        out = []
        for p in files:
            t = re.sub(r"#footnote\[[^\]]*\]", " ", p.read_text())
            t = re.sub(r"#\w+(\.\w+)*(\([^)]*\))?", " ", t)
            out.append(re.sub(r"^==+ .*$", " ", t, flags=re.M))
    return modern_words(re.findall(r"[A-Za-zſ]+|&", "\n".join(out)))


def witness_words(path):
    t = Path(path).read_text()
    t = re.sub(r"^--- (?:Source )?PDF page (\d+).*$", r" PAGE\1 ", t, flags=re.M)
    return modern_words(re.findall(r"PAGE\d+|[A-Za-zſ]+|&", re.sub(r"-\n\s*", "", t)))


def page_of(b, j):
    for k in range(min(j, len(b) - 1), -1, -1):
        if b[k].startswith("PAGE"):
            return int(b[k][4:])
    return 0


def passes(a, b):
    """{tcp index: (extra words, context, scan page)} and {tcp index: word}"""
    sm = difflib.SequenceMatcher(None, [norm(w) for w in a], [norm(w) for w in b], autojunk=False)
    extra, swap = {}, {}
    for op, i1, i2, j1, j2 in sm.get_opcodes():
        if op == "equal":
            continue
        tw, ws = a[i1:i2], [w for w in b[j1:j2] if not w.startswith("PAGE")]
        if op == "replace" and len(tw) == 1 and len(ws) == 1:
            swap[i1] = ws[0]
        if tw and difflib.SequenceMatcher(None, norm("".join(tw)), norm("".join(ws))).ratio() > 0.8:
            continue                                      # split or joined across a line
        starts = {norm(b[k + 1]) for k in range(max(0, j1 - 4), min(len(b) - 1, j2 + 4))
                  if b[k].startswith("PAGE")}             # catchwords
        left = [w for w in ws if len(w) >= 2 and norm(w) not in HEAD and norm(w) not in starts
                and not any(similar(w, t) for t in tw)]
        if left:
            extra[(i1, i2)] = (left, " ".join(b[max(0, j1 - 8):j2 + 6]), page_of(b, j1))
    return extra, swap


def main(a_):
    MODERN["on"] = bool(getattr(a_, "modern", False))
    need = a_.agree or len(a_.witness)
    a = tcp_words(Path(a_.book))
    res = [passes(a, witness_words(w)) for w in a_.witness]
    names = [Path(w).name.split(".")[1] if Path(w).name.count(".") > 1 else Path(w).stem for w in a_.witness]
    ctx = lambda i1, i2: f"{' '.join(a[max(0, i1 - 8):i1])} [{' '.join(a[i1:i2])}] {' '.join(a[i2:i2 + 6])}"

    rows, cands = [], []
    for (i1, i2), (words, c, page) in sorted(res[0][0].items()):
        seen = [(names[0], c)]
        for n, (extra, _) in zip(names[1:], res[1:]):
            hit = next((v for (k1, k2), v in extra.items() if k1 <= i2 + 1 and i1 <= k2 + 1
                        and any(similar(x, y) for x in words for y in v[0])), None)
            if hit:
                seen.append((n, hit[1]))
        if len(seen) >= need:
            cands.append({"n": len(rows) + 1, "kind": "extra", "page": page, "words": words,
                          "tcp": ctx(i1, i2), "witnesses": dict(seen)})
            rows.append(f"{len(rows) + 1}. scan p. {page}: extra {' '.join(words)}\n   TCP: …{ctx(i1, i2)}…\n"
                        + "".join(f"   {n}: …{c}…\n" for n, c in seen))
    near = []
    for i, w in sorted(res[0][1].items()):
        same = [r[1].get(i) for r in res]
        if sum(1 for x in same if x and norm(x) == norm(w)) >= need and norm(w) != norm(a[i]):
            near.append(f"- {ctx(i, i + 1)}  →  {w}")
            cands.append({"n": len(cands) + 1, "kind": "nearmiss", "page": None, "words": [w],
                          "tcp": ctx(i, i + 1), "witnesses": {}})
    out = Path(a_.out); out.mkdir(parents=True, exist_ok=True)
    (out / "extra.md").write_text("# Words the witnesses have that the TCP lacks\n\n" + "\n".join(rows))
    (out / "nearmiss.md").write_text("# One-word swaps the witnesses agree on\n\n" + "\n".join(near) + "\n")
    # for crops.py: each candidate's place, to cut its printed lines from the page
    import json
    (out / "candidates.json").write_text(json.dumps(cands, indent=1, ensure_ascii=False) + "\n")
    print(f"{len(rows)} extra-word places, {len(near)} near misses -> {out}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("book"); ap.add_argument("out"); ap.add_argument("witness", nargs="+")
    ap.add_argument("--agree", type=int)
    ap.add_argument("--modern", action="store_true")
    main(ap.parse_args())
