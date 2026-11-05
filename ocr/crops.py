"""The printed lines of a collation candidate, cut from the page image, so it
can be read on the print before anything goes into the book.

Lines are found through Tesseract's word boxes (<bundle>/tesseract/pages/
*.tsv): the window of lines sharing most of the candidate's context words
(fuzzily: OCR spelling and long s), on its page and the pages either side,
or on every page when the page is not known (a near miss).

  ./fgb crops CANDIDATES.json BUNDLE OUT_DIR [--per 6]
      one crop per candidate (cNNNN.png) and contact sheets of them
"""

import csv
import difflib
import json
import re
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from ocr.bundle import Bundle


def key(w):
    w = w.lower().replace("ſ", "s")
    w = re.sub(r"[^a-z0-9]", "", w).replace("v", "u").replace("j", "i").replace("y", "i")
    return re.sub(r"(.)\1", r"\1", w.replace("f", "s"))


def lines(bundle, page):
    """Tesseract's lines on a page: [{"keys", "box"}], top to bottom."""
    f = bundle.dir / "tesseract" / "pages" / f"{page:06d}.tsv"
    if not f.exists():
        return []
    with open(f, encoding="utf-8") as fh:
        rows = [r for r in csv.DictReader(fh, delimiter="\t", quoting=csv.QUOTE_NONE)
                if r["level"] == "5" and (r.get("text") or "").strip()]
    by = {}
    for r in rows:
        by.setdefault((r["block_num"], r["par_num"], r["line_num"]), []).append(r)
    out = []
    for ws in by.values():
        box = (min(int(w["left"]) for w in ws), min(int(w["top"]) for w in ws),
               max(int(w["left"]) + int(w["width"]) for w in ws),
               max(int(w["top"]) + int(w["height"]) for w in ws))
        out.append({"keys": [key(w["text"]) for w in ws], "box": box})
    return sorted(out, key=lambda x: (x["box"][1], x["box"][0]))


def find(bundle, words, page=None, n=3):
    """(score, page, box) of the n lines that best hold the words."""
    want = [k for k in map(key, words) if len(k) > 1]
    tess = sorted(int(p.stem) for p in (bundle.dir / "tesseract" / "pages").glob("*.tsv"))
    pages = [p for p in (page, page - 1, page + 1) if p in tess] if page else tess
    best = (-1, None, None)
    for p in pages:
        ls = lines(bundle, p)
        for i in range(len(ls)):
            have = [k for x in ls[i:i + n] for k in x["keys"]]
            sc = sum(any(k == h or (len(k) > 3 and difflib.SequenceMatcher(None, k, h).ratio() >= 0.75)
                         for h in have) for k in want)
            if sc > best[0]:
                b = [x["box"] for x in ls[i:i + n]]
                best = (sc, p, (min(x[0] for x in b), min(x[1] for x in b),
                                max(x[2] for x in b), max(x[3] for x in b)))
    return best


def crop(bundle, words, out, page=None, n=3):
    sc, p, box = find(bundle, words, page, n)
    if box is None:
        return None
    im = Image.open(bundle.page(p))
    im.crop((max(0, box[0] - 60), max(0, box[1] - 25), min(im.width, box[2] + 60),
             min(im.height, box[3] + 25))).save(out)
    return p, sc


def main(a):
    bundle = Bundle(a.bundle)
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    cands = json.loads(Path(a.candidates).read_text(encoding="utf-8"))
    font = ImageFont.load_default(size=22)
    tiles = []
    for c in cands:
        f = out / f"c{c['n']:04d}-{c['kind']}.png"
        # the TCP's context: the words around the place, the missing ones too
        ctx = re.sub(r"[\[\]…]", " ", c["tcp"]).split() + c["words"]
        found = crop(bundle, ctx, f, c.get("page")) if not f.exists() else (c.get("page"), None)
        if found is None:
            print(f"#{c['n']}: no matching lines")
            continue
        im = Image.open(f)
        if im.width > 1500:
            im = im.resize((1500, int(im.height * 1500 / im.width)))
        label = f"#{c['n']} {c['kind']} p{found[0]}: {' '.join(c['words'])[:60]}  |  TCP: {c['tcp'][:80]}"
        tile = Image.new("RGB", (1500, im.height + 34), "white")
        ImageDraw.Draw(tile).text((6, 4), label, fill="darkred", font=font)
        tile.paste(im, (0, 34))
        tiles.append((c["n"], tile))
    for s in range(0, len(tiles), a.per):
        group = tiles[s:s + a.per]
        sheet = Image.new("RGB", (1500, sum(t.height + 8 for _, t in group)), (200, 200, 200))
        y = 0
        for _, t in group:
            sheet.paste(t, (0, y))
            y += t.height + 8
        sheet.save(out / f"sheet-{group[0][0]:04d}-{group[-1][0]:04d}.png")
    print(f"{len(tiles)} candidates cut, {(len(tiles) + a.per - 1) // a.per} sheets in {out}")
