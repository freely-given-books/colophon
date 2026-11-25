"""Print facts for a release: what a site needs to know about each print
book without opening its PDFs.

For every interior PDF in a release, its page count and trim; for every
cover PDF, the spine's width and colour and the wrap cut into three images
(back, spine, front: <cover>-back.webp, -spine.webp, -front.webp), for a
bookshelf and a book that turns over. They go into the catalog: the
interior's file record gets "print", the cover's gets "wrap", and the
images are files of the release like any other.

A cover PDF is the trim plus a 0.125in bleed all round, back + spine +
front; its interior is the same name without "-cover"
(the-book-v3-cover-vol-2.pdf <-> the-book-v3-vol-2.pdf).

Needs poppler (pdfinfo, pdftoppm) and Pillow.
"""

import re
import subprocess
import tempfile
from pathlib import Path

from PIL import Image

BLEED = 0.125          # in
DPI = 200              # the wrap's render
WIDTH = 900            # px: the front and back images (the spine at their scale)
COVER = re.compile(r"^(.+?-v\d+(?:\.\d+)?)-cover(.*)\.pdf$")


def pdf_info(pdf):
    """(pages, width in, height in) of a PDF's first page size."""
    out = subprocess.run(["pdfinfo", str(pdf)], capture_output=True, text=True,
                         check=True).stdout
    pages = int(re.search(r"^Pages:\s+(\d+)", out, re.M).group(1))
    w, h = (float(x) / 72 for x in
            re.search(r"^Page size:\s+([\d.]+) x ([\d.]+) pts", out, re.M).groups())
    return pages, w, h


def r3(x):
    return round(x, 3)


def wrap_images(cover, W, H, tw, th, spine, out):
    """Cut the cover into back, spine and front (bleed trimmed off), as webp
    files beside it in out: {"back", "spine", "front"} -> file name, and the
    spine's average colour, as #rrggbb."""
    stem = cover.name[:-len(".pdf")]
    with tempfile.TemporaryDirectory(prefix="fgb-wrap-") as tmp:
        base = Path(tmp) / "wrap"
        subprocess.run(["pdftoppm", "-r", str(DPI), "-png", "-singlefile",
                        str(cover), str(base)], check=True)
        img = Image.open(f"{base}.png").convert("RGB")
    pw, ph = img.size
    px = lambda inch: round(inch * pw / W)
    y0, height = round(BLEED * ph / H), round(th * ph / H)
    cut = lambda x0, w: img.crop((px(x0), y0, px(x0) + max(1, px(x0 + w) - px(x0)), y0 + height))
    scale = WIDTH / px(tw)
    h = round(height * scale)
    names = {}
    for part, x0, w, q in (("back", BLEED, tw, 82), ("spine", BLEED + tw, spine, 85),
                           ("front", BLEED + tw + spine, tw, 82)):
        piece = cut(x0, w)
        size = (WIDTH, h) if part != "spine" else (max(1, round(piece.width * scale)), h)
        name = f"{stem}-{part}.webp"
        piece.resize(size, Image.LANCZOS).save(out / name, "WEBP", quality=q)
        names[part] = name
        if part == "spine":
            px_ = list(piece.getdata())
            colour = "#" + "".join(f"{round(sum(c[i] for c in px_) / len(px_)):02x}"
                                   for i in range(3))
    return names, colour


def add(root, entries, sha256):
    """Add the print facts to each entry's file records, and the wrap
    images to the release (root) and its entries. Returns the names of the
    covers that could not be cut (their size does not fit their trim)."""
    skipped = []
    for e in entries:
        recs = {f["name"]: f for f in e["files"]}
        new = []
        for name, rec in recs.items():
            if not name.endswith(".pdf"):
                continue
            m = COVER.match(name)
            if not m:
                pages, w, h = pdf_info(root / name)
                rec["print"] = {"pages": pages, "width": r3(w), "height": r3(h)}
                continue
            interior = f"{m.group(1)}{m.group(2)}.pdf"
            if interior not in recs:
                # a volume's interior is named for its book file (-institutes-vol-1.pdf),
                # its cover for the volume (-cover-vol-1.pdf): the one that ends so
                likes = [n for n in recs if n.startswith(m.group(1) + "-") and not COVER.match(n)
                         and n.endswith(f"{m.group(2)}.pdf")] if m.group(2) else []
                if len(likes) != 1:
                    continue
                interior = likes[0]
            _, W, H = pdf_info(root / name)
            _, tw, th = pdf_info(root / interior)
            spine = W - 2 * tw - 2 * BLEED
            if not spine > 0 or abs(H - th - 2 * BLEED) > 0.02:
                skipped.append(name)
                continue
            names, colour = wrap_images(root / name, W, H, tw, th, spine, root)
            rec["wrap"] = {"spine": r3(spine), "color": colour, "back": names["back"],
                           "spine_image": names["spine"], "front": names["front"]}
            for n in names.values():
                p = root / n
                new.append({"name": n, "bytes": p.stat().st_size, "sha256": sha256(p)})
        e["files"] += new
    return skipped
