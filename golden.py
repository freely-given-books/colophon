#!/usr/bin/env python3
"""
Golden outputs: every TEI book built and kept as text, so a change to colophon
can be shown to leave the books as they were, or exactly how it changes them.

  ./fgb golden save DIR [BOOK ...]     build the books, keep the outputs in DIR
  ./fgb golden check DIR [BOOK ...]    build them again and compare with DIR

What is kept, per book (DIR/<author>/<book>/):
  tei/      the TEI rebuilt from its source and chapters/typ (build_tei.py),
            the review report and the coverage counts (coverage.py)
  reg/ orig/  both layers extracted (tei_extract.py; orig with gaps shown)
  epub/<name>/  each EPUB unpacked: its text files, images as SHA-256
  web/      the reader and comparison pages (fgb.build_web)
  pdf/      each print PDF and cover as text (pdftotext -layout, page by
            page) with its page count and size; front panels as SHA-256

Run-to-run noise is left out: the revisionDesc review date, the EPUB's
dcterms:modified, the PDF's dates. `check` builds into DIR.new, lists every
book that differs and writes the differences to DIR.new/DIFF.txt.
"""

import concurrent.futures as cf
import difflib
import hashlib
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import zipfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import fgb  # noqa: E402

PY = sys.executable
TEXT = {".xhtml", ".html", ".xml", ".opf", ".ncx", ".css", ".txt", ".md", ".typ", ".json"}


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def run(*args, cwd=None):
    r = subprocess.run([str(a) for a in args], cwd=cwd, capture_output=True, text=True)
    if r.returncode:
        sys.exit(f"command failed: {' '.join(map(str, args))}\n{r.stdout[-3000:]}{r.stderr[-3000:]}")
    return r.stdout


def keep_epub(epub, out):
    """An EPUB unpacked as text, its modified date dropped; binaries hashed."""
    out.mkdir(parents=True)
    sums = []
    with zipfile.ZipFile(epub) as z:
        for name in sorted(z.namelist()):
            if name.endswith("/"):
                continue
            data = z.read(name)
            if Path(name).suffix in TEXT:
                text = data.decode("utf-8")
                text = re.sub(r'<meta property="dcterms:modified">[^<]*</meta>', "", text)
                dest = out / name
                dest.parent.mkdir(parents=True, exist_ok=True)
                dest.write_text(text, encoding="utf-8")
            else:
                sums.append(f"{hashlib.sha256(data).hexdigest()}  {name}\n")
    (out / "BINARIES.sha256").write_text("".join(sums), encoding="utf-8")


def keep_pdf(pdf, out):
    """A PDF as text, with its geometry: what the reader sees, page by page."""
    pages, w, h = fgb.pdf_geometry(pdf)
    text = run("pdftotext", "-layout", pdf, "-")
    (out / (pdf.stem + ".txt")).write_text(
        f"{pages} pages, {w} x {h} in\n\n{text}", encoding="utf-8")


def snapshot(book_dir, out):
    """Build one book into a scratch folder and keep its outputs in `out`."""
    bk = fgb.Book(Path(book_dir))
    if out.exists():
        shutil.rmtree(out)
    with tempfile.TemporaryDirectory(prefix="fgb-golden-") as t:
        tmp = Path(t)
        (out / "tei").mkdir(parents=True)
        run(PY, HERE / "build_tei.py", bk.tcp, out / "tei" / bk.tei.name,
            "--review", bk.chapters, "--report", out / "tei" / "review-report.md")
        tei = out / "tei" / bk.tei.name
        tei.write_text("".join(l for l in tei.read_text(encoding="utf-8").splitlines(True)
                               if 'xml:id="review"' not in l), encoding="utf-8")
        run(PY, HERE / "tei_extract.py", bk.tei, out / "reg", "--layer", "reg")
        run(PY, HERE / "tei_extract.py", bk.tei, out / "orig", "--layer", "orig", "--show-gaps")
        import coverage
        (out / "tei" / "coverage.txt").write_text(
            "".join(l + "\n" for l in coverage.summary(coverage.coverage(bk.tei))),
            encoding="utf-8")

        built = tmp / "built"
        built.mkdir()
        files = fgb.build_pdf(bk, built, covers=True)
        epubs = fgb.build_epub(bk, built)
        files += epubs
        web = fgb.build_web(bk, built, files)
        (out / "pdf").mkdir()
        (out / "web").mkdir()
        sums = []
        for f in files:
            if f.suffix == ".pdf":
                keep_pdf(f, out / "pdf")
            elif f.suffix == ".epub":
                keep_epub(f, out / "epub" / f.stem)
            else:
                sums.append(f"{sha(f)}  {f.name}\n")
        (out / "pdf" / "IMAGES.sha256").write_text("".join(sums), encoding="utf-8")
        for f in web:
            shutil.copy(f, out / "web" / f.name)


def chosen(names):
    all_books = [d for d in fgb.books() if fgb.Book(d).tei.exists()]
    if not names:
        return all_books
    return [fgb.find_book(n) for n in names]


def build_all(dirs, root, jobs):
    """snapshot() on each book, several at a time (each in its own process)."""
    root.mkdir(parents=True, exist_ok=True)
    jobs = jobs or os.cpu_count() or 2
    print(f"building {len(dirs)} books into {root}, {jobs} at a time ...")
    failed = []

    def one(d):
        t = time.time()
        name = str(d.relative_to(fgb.REPO / "books"))
        r = subprocess.run([PY, str(HERE / "golden.py"), "one", str(d), str(root / name)],
                           capture_output=True, text=True)
        return name, r, time.time() - t

    with cf.ThreadPoolExecutor(jobs) as ex:
        for name, r, secs in ex.map(one, dirs):
            print(f"  {'ok    ' if r.returncode == 0 else 'FAILED'} {name:55} {secs:5.0f}s")
            if r.returncode:
                failed.append(name)
                print((r.stdout + r.stderr)[-3000:])
    return failed


def compare(old, new):
    """Unified diffs of every file that differs between two golden trees."""
    out = []
    olds = {p.relative_to(old) for p in old.rglob("*") if p.is_file()}
    news = {p.relative_to(new) for p in new.rglob("*") if p.is_file()}
    for rel in sorted(olds | news):
        a = (old / rel).read_text(encoding="utf-8").splitlines(True) if rel in olds else []
        b = (new / rel).read_text(encoding="utf-8").splitlines(True) if rel in news else []
        if a != b:
            out.append((rel, list(difflib.unified_diff(a, b, f"golden/{rel}", f"now/{rel}", n=2))))
    return out


def main(a):
    root = Path(a.dir).resolve()
    dirs = chosen(a.books)
    if a.action == "save":
        failed = build_all(dirs, root, a.jobs)
        (root / "GOLDEN.txt").write_text(
            f"books at {fgb.git_state()}, colophon {fgb.git_state(HERE)}\n", encoding="utf-8")
        sys.exit(1 if failed else 0)
    if not root.is_dir():
        sys.exit(f"no golden outputs in {root} (./fgb golden save {a.dir})")
    new = root.with_name(root.name + ".new")
    failed = build_all(dirs, new, a.jobs)
    report, changed = [], []
    for d in dirs:
        name = str(d.relative_to(fgb.REPO / "books"))
        if name in failed:
            continue
        if not (root / name).is_dir():
            print(f"  new    {name} (not in the golden outputs)")
            continue
        diffs = compare(root / name, new / name)
        if diffs:
            changed.append(name)
            kinds = sorted({str(rel.parts[0]) for rel, _ in diffs})
            lines = sum(sum(1 for l in d if l[:1] in "+-") for _, d in diffs)
            print(f"  differs {name:54} {', '.join(kinds)} ({lines} lines)")
            report += [f"### {name}/{rel}\n" + "".join(d) for rel, d in diffs]
    (new / "DIFF.txt").write_text("\n".join(report), encoding="utf-8")
    same = len(dirs) - len(changed) - len(failed)
    print(f"\n{same} of {len(dirs)} books as golden"
          + (f"; differences in {new / 'DIFF.txt'}" if changed else ""))
    sys.exit(1 if changed or failed else 0)


if __name__ == "__main__":
    if len(sys.argv) == 4 and sys.argv[1] == "one":
        import packages
        packages.setup()
        snapshot(sys.argv[2], Path(sys.argv[3]))
    else:
        sys.exit("run through ./fgb golden")
