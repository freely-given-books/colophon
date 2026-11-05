"""The scan bundle: its pages, its manifest and the witness export."""

import hashlib
import json
import re
import shutil
import subprocess
import time
from pathlib import Path

DPI = 300
IMAGES = (".png", ".jpg", ".jpeg", ".tif", ".tiff", ".jp2")
# both page-marker forms: the bundle's ("--- PDF page 3 ---") and the
# export's ("--- Source PDF page 3 (OCR sequence 3) ---")
PAGE_MARK = re.compile(r"^--- (?:Source )?PDF page (\d+)\b.*---\s*$", re.M)


class Bundle:
    def __init__(self, path):
        self.dir = Path(path)
        src = self.dir / "source"
        self.pdf = next(src.glob("*.pdf"), None)
        self.images = sorted(p for p in src.iterdir() if p.suffix.lower() in IMAGES) \
            if src.is_dir() else []
        if self.pdf is None and not self.images:
            raise SystemExit(f"{src}: no scan (a .pdf, or page images)")

    @property
    def name(self):
        return self.dir.name

    def page_count(self):
        if self.pdf is None:
            return len(self.images)
        info = subprocess.run(["pdfinfo", str(self.pdf)], capture_output=True, text=True).stdout
        return int(re.search(r"^Pages:\s+(\d+)", info, re.M).group(1))

    def page(self, n):
        """pages/NNNNNN.png, page n of the scan (from 1) at 300 dpi, made once."""
        out = self.dir / "pages" / f"{n:06d}.png"
        if out.exists():
            return out
        out.parent.mkdir(exist_ok=True)
        if self.pdf is not None:
            subprocess.run(["pdftoppm", "-f", str(n), "-l", str(n), "-r", str(DPI), "-png",
                            "-singlefile", str(self.pdf), str(out.with_suffix(""))], check=True)
        else:
            img = self.images[n - 1]
            if img.suffix.lower() == ".png":
                shutil.copy(img, out)
            else:
                subprocess.run(["magick", str(img), str(out)], check=True)
        return out

    def engine_dir(self, engine):
        d = self.dir / engine / "pages"
        d.mkdir(parents=True, exist_ok=True)
        return d

    def manifest(self, engine, settings):
        """Record the scan's checksum and an engine's settings (first run only)."""
        path = self.dir / "manifest.json"
        m = json.loads(path.read_text()) if path.exists() else {}
        if "scan_sha256" not in m:
            scans = [self.pdf] if self.pdf is not None else self.images
            h = hashlib.sha256()
            for s in scans:
                h.update(s.read_bytes())
            m["scan"] = [s.name for s in scans] if len(scans) > 1 else scans[0].name
            m["scan_sha256"] = h.hexdigest()
            m["dpi"] = DPI
            # how pages are made: an OCR reading depends on the image as much as the engine
            poppler = subprocess.run(["pdftoppm", "-v"], capture_output=True, text=True).stderr
            m["render"] = (f"pdftoppm -r {DPI} -png ({poppler.split(chr(10))[0].strip()})"
                           if self.pdf is not None else "the page images as given (PNG copied, "
                           "others converted with ImageMagick)")
        m.setdefault("engines", {}).setdefault(
            engine, {**settings, "started": time.strftime("%Y-%m-%dT%H:%M:%S%z")})
        path.write_text(json.dumps(m, indent=1) + "\n")

    def export(self, engine, out=None):
        """<engine>/full-text.txt, and the witness file collate.py reads
        (<out>, default <bundle>.<engine>.witness.txt beside the bundle)."""
        pages = sorted(self.engine_dir(engine).glob("*.txt"))
        if not pages:
            raise SystemExit(f"{self.dir / engine}: no pages read yet")
        full, witness = [], []
        for seq, p in enumerate(pages, 1):
            n = int(p.stem)
            text = p.read_text(encoding="utf-8").rstrip("\n")
            full.append(f"--- PDF page {n} ---\n\n{text}\n")
            witness.append(f"--- Source PDF page {n} (OCR sequence {seq}) ---\n\n{text}\n")
        (self.dir / engine / "full-text.txt").write_text("\n".join(full), encoding="utf-8")
        out = Path(out) if out else self.dir.parent / f"{self.name}.{engine}.witness.txt"
        out.write_text("\n".join(witness), encoding="utf-8")
        return out


def pages_of(text):
    """{page: text} of an exported or bundle full text."""
    out, marks = {}, list(PAGE_MARK.finditer(text))
    for k, m in enumerate(marks):
        end = marks[k + 1].start() if k + 1 < len(marks) else len(text)
        out[int(m.group(1))] = text[m.end():end].strip("\n")
    return out
