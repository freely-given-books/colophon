"""A release laid out for the books.freely.giving site: everything the site's
owner needs in one folder, to zip and send, and an IMPORT.md telling his
Claude (in the books-freelygiv-ing repository) how to bring it in.

  ./fgb export DIR                    # the newest release in dist/release/
  ./fgb export DIR --release FOLDER   # another release folder
  ./fgb export DIR --lulu FOLDER      # Lulu's print-ready ZIPs, for books
                                      # whose covers are not built here

DIR gets:
  IMPORT.md             the import, step by step, for Claude in the site repo
  site.json             per book: slug, title, author, version, summary, page
                        counts, Lulu links, files, a note for the import
  catalog.json          the release's full record (as `release make` wrote it)
  <author>/<book>/      the print PDFs and covers, EPUBs, front covers, and a
                        print-ready ZIP (interior and cover) per print PDF

Lulu links and notes come from books/publishing.toml in the books repository
(outside the book folders, so editing it never holds a signed-off book back).

A book whose cover is made outside the repository (no cover*.typ, so the
release has no cover files) still gets its front cover: the image its EPUB
uses (EPUB["cover"] in editorial.py). Its print-ready ZIP is Lulu's own, from
--lulu: the ZIP Lulu gives for download, named <product id>_print-ready.zip,
the id from the book's Lulu link (".../product-dy7vjp4.html").
"""

import json
import re
import shutil
import subprocess
import sys
import tempfile
import tomllib
import zipfile
from pathlib import Path

import fgb
import library

REPO = library.ROOT
PUBLISHING = REPO / "books" / "publishing.toml"

IMPORT = """\
# Importing release {release} into books.freely.giving

For Claude working in the `books-freelygiv-ing` repository. This folder is one
release of Freely Given Books (the editions prepared by Courtney Hicks),
laid out by `<author>/<book>/`. Read this file, `site.json`, and the site's
`CLAUDE.md` and `docs/BOOK-FILES.md`, then bring each book in as below. Show
the owner the plan (which books change, which are new) before writing.

## What is here

- `site.json`: one entry per book: `book` (`<author>/<book>`), `slug` (the
  site's book slug), `title`, `author`, `version`, `summary`, `pages` (each
  print PDF's page count), `lulu` (the paperback's Lulu page; a list, one per
  volume, for a book in volumes; `""` = none yet), `note` (anything particular
  to this book's import: follow it), `files`.
- `catalog.json`: the full release record (sign-offs, sources, witnesses,
  fidelity counts). Reference only.
- `<author>/<book>/`:
  - `<book>-vN.pdf`: the print interior; `<book>-vN-cover.pdf`: the Lulu cover
  - `<book>-vN.epub`, or `vN.M`: an ebook improved since print revision N
    (its PDF is still revision N's, which is what Lulu sells)
  - `<book>-vN-cover-front.png` (or `.jpg`): the front cover
  - `print-ready.zip` (`print-ready-vol-N.zip`): interior and cover for Lulu
    (for a few books, Lulu's own download of them, with its file names)

## Each book

1. Copy into `data/src/books/<slug>/content/`, renamed to the site's stable
   names so the R2 URLs do not change: `<slug>.pdf`, `<slug>.epub`,
   `print-ready.zip`, and the front cover as `cover.jpg` (convert a PNG;
   keep its full size). Leave other files there alone unless the book's
   `note` says otherwise.
2. In `book.yaml`: set `pages` from `site.json` (the current editions' counts
   replace the site's); make sure `mediaTypes` has `eBook`, `pdfBook` and,
   with a print-ready ZIP, `printReady` entries pointing at
   `https://files.books.freelygiv.ing/<slug>/<file>`; with a `lulu` link, a
   `printBook` entry (label `Book`, source name `Lulu`). Keep the title,
   description, tags, dates and credits; add `- person: courtney-hicks` /
   `prepared: true` to `credits` if missing.
3. The owner uploads: `npm run upload -- <slug> --force` (`--force`: the files
   replace ones already in R2). Claude does not run the upload or need the
   R2 keys.

## New books

Books not yet on the site (no `data/src/books/<slug>/`): scaffold them as
`add-book.js` would (one-element YAML array, `path`, `cover: cover.jpg`,
`license: CC0`, `addedDate` today, `sortTitle`, the `year` of first
publication), with `title` and `summary` from `site.json` for the
description; ask the owner for anything else. A new author also needs
`data/src/<person-slug>/person.yaml` and a photo (ask the owner).

A book in volumes (`pages` lists several PDFs) is best one site book per
volume, as the Institutes are (`<slug>-volume-1`, ...), each with its own
files and its own `lulu` link.

## Afterwards

`npm run build` must pass; commit the YAML, the covers and the regenerated
OG cards (`npm run og`), as the site's `CLAUDE.md` says.
"""


def newest_release():
    """The newest release folder under dist/release/ (one with a catalog)."""
    found = sorted((p for p in (REPO / "dist" / "release").glob("*/catalog.json")),
                   key=lambda p: p.stat().st_mtime)
    if not found:
        sys.exit("no release in dist/release/: make one (./fgb release make) "
                 "or give --release")
    return found[-1].parent


def page_count(pdf):
    out = subprocess.run(["pdfinfo", str(pdf)], capture_output=True, text=True,
                         check=True).stdout
    return int(out.split("Pages:")[1].split()[0])


def product_id(url):
    """Lulu's product id from a shop link: .../product-dy7vjp4.html -> dy7vjp4."""
    m = re.search(r"/product-([a-z0-9]+)", url or "")
    return m.group(1) if m else None


def lulu_front(z, png, dpi=200):
    """The front panel of the cover in Lulu's print-ready ZIP, as a PNG: the
    right-hand trim of the wrap, the trim size read from the interior (whose
    pages Lulu sets with 0.125in bleed). False if the ZIP is not Lulu's shape."""
    with tempfile.TemporaryDirectory() as tmp, zipfile.ZipFile(z) as zf:
        names = zf.namelist()
        cover = next((n for n in names if n.endswith("_cover.pdf")), None)
        inner = next((n for n in names if n.endswith("_interior.pdf")), None)
        if not (cover and inner):
            return False
        zf.extract(cover, tmp)
        zf.extract(inner, tmp)
        size = lambda f: [float(x) for x in subprocess.run(
            ["pdfinfo", str(Path(tmp) / f)], capture_output=True, text=True,
            check=True).stdout.split("Page size:")[1].split("pts")[0].split(" x ")]
        (iw, ih), (cw, ch) = size(inner), size(cover)
        bleed = 9                                   # 0.125in, in points
        w, h = iw - 2 * bleed, ih - 2 * bleed       # the trim
        scale = dpi / 72
        subprocess.run(["pdftoppm", "-r", str(dpi), "-png", "-singlefile",
                        "-x", str(round((cw - bleed - w) * scale)), "-y", str(round(bleed * scale)),
                        "-W", str(round(w * scale)), "-H", str(round(h * scale)),
                        str(Path(tmp) / cover), str(png.with_suffix(""))], check=True)
    return True


def own_covers(b, d, lulu_dir, links):
    """For a book whose covers are made outside the repository: the EPUB's
    front cover image, and Lulu's print-ready ZIP(s) from lulu_dir. The
    names of the files added; what is missing, said."""
    added = []
    links = links if isinstance(links, list) else [links]
    zips = [lulu_dir / f"{product_id(u)}_print-ready.zip" if lulu_dir and product_id(u)
            else None for u in links]
    bk = fgb.Book(REPO / "books" / b["book"])
    e = bk.cfg.get("EPUB", {})
    images = [v.get("cover") for v in e.get("volumes", [])] or [e.get("cover")]
    for n, img in enumerate(images, 1):
        if not img or img.endswith(".typ") or not (bk.dir / img).exists():
            print(f"    no front cover image for {b['book']}")
            continue
        vol = f"-vol-{n}" if len(images) > 1 else ""
        z = zips[n - 1] if n <= len(zips) else None
        # Lulu's cover holds the front at print resolution; the EPUB's image
        # is often small (384px), so it is the fallback
        png = d / f"{b['folder']}-{b['version']}-cover{vol}-front.png"
        if z and z.exists() and lulu_front(z, png):
            added.append(png.name)
            continue
        name = f"{b['folder']}-{b['version']}-cover{vol}-front{Path(img).suffix}"
        shutil.copy2(bk.dir / img, d / name)
        added.append(name)
    for n, (url, z) in enumerate(zip(links, zips), 1):
        pid = product_id(url)
        name = f"print-ready-vol-{n}.zip" if len(links) > 1 else "print-ready.zip"
        if z and z.exists():
            shutil.copy2(z, d / name)
            added.append(name)
        else:
            print(f"    no print cover for {b['book']}: Lulu's "
                  f"{pid + '_print-ready.zip' if pid else 'ZIP'} "
                  + ("is not in --lulu" if lulu_dir else "(give --lulu)"))
    return added


def export(rel, out, lulu_dir=None):
    cat = json.loads((rel / "catalog.json").read_text(encoding="utf-8"))
    pub = tomllib.loads(PUBLISHING.read_text(encoding="utf-8")) if PUBLISHING.exists() else {}
    site = []
    for b in cat["books"]:
        d = out / b["book"]
        d.mkdir(parents=True, exist_ok=True)
        keep = [f["name"] for f in b["files"]
                if f["name"].endswith((".pdf", ".epub", "-front.png"))]
        for n in keep:
            shutil.copy2(rel / n, d / n)
        interiors = sorted(n for n in keep if n.endswith(".pdf") and "-cover" not in n)
        covers = [n for n in keep if n.endswith(".pdf") and "-cover" in n]
        zips = []
        for i in interiors:
            vol = i[:-4].rsplit("-vol-", 1)[1] if "-vol-" in i else None
            c = [x for x in covers if x.endswith(f"-vol-{vol}.pdf")] if vol else covers
            if c:
                z = d / (f"print-ready-vol-{vol}.zip" if vol else "print-ready.zip")
                with zipfile.ZipFile(z, "w", zipfile.ZIP_STORED) as zf:
                    zf.write(rel / i, i)
                    zf.write(rel / c[0], c[0])
                zips.append(z.name)
        p = pub.get(b["book"], {})
        if not covers:
            zips += own_covers(b, d, lulu_dir, p.get("lulu", ""))
        site.append({"book": b["book"], "slug": p.get("slug", b["folder"]),
                     "title": b["title"], "author": b["author"],
                     "version": b["version"], "summary": b["summary"],
                     "pages": {n: page_count(rel / n) for n in interiors},
                     "lulu": p.get("lulu", ""), "note": p.get("note", ""),
                     "files": sorted(keep + zips)})
        print(f"  {b['book']} {b['version']}: {len(keep) + len(zips)} file(s)")
    shutil.copy2(rel / "catalog.json", out / "catalog.json")
    (out / "site.json").write_text(json.dumps(site, indent=2, ensure_ascii=False) + "\n",
                                   encoding="utf-8")
    (out / "IMPORT.md").write_text(IMPORT.format(release=cat["release"]), encoding="utf-8")
    missing = [s["book"] for s in site
               if not s["lulu"] or (isinstance(s["lulu"], list) and not all(s["lulu"]))]
    if missing:
        print(f"no Lulu link (books/publishing.toml): {', '.join(missing)}")


def main(a):
    rel = Path(a.release).resolve() if a.release else newest_release()
    out = Path(a.dir).expanduser().resolve()
    if out.exists() and any(out.iterdir()):
        # only an earlier export is ever replaced, never any other folder
        if not (out / "site.json").exists():
            sys.exit(f"{out} is not empty and is not an export: give a new folder")
        if not a.force:
            sys.exit(f"{out} holds an earlier export (--force to replace it)")
        shutil.rmtree(out)
    out.mkdir(parents=True, exist_ok=True)
    print(f"export of {rel.name} into {out}")
    export(rel, out, Path(a.lulu).expanduser().resolve() if a.lulu else None)
