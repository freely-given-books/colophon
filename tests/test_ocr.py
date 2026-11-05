"""The OCR bundle: pages exported in the witness layout and read back."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from ocr.bundle import Bundle, pages_of  # noqa: E402


def test_export_and_read_back(tmp_path):
    b = tmp_path / "scan-1700"
    (b / "source").mkdir(parents=True)
    (b / "source" / "a.png").write_bytes(b"")
    (b / "source" / "b.png").write_bytes(b"")
    pages = b / "kraken" / "pages"
    pages.mkdir(parents=True)
    (pages / "000001.txt").write_text("THE PREFACE\nTo the Reader.\n")
    (pages / "000002.txt").write_text("Temptation, in general\n")
    out = Bundle(b).export("kraken")
    assert out == tmp_path / "scan-1700.kraken.witness.txt"
    text = out.read_text()
    assert text.startswith("--- Source PDF page 1 (OCR sequence 1) ---\n")
    assert pages_of(text) == {1: "THE PREFACE\nTo the Reader.", 2: "Temptation, in general"}
    full = (b / "kraken" / "full-text.txt").read_text()
    assert pages_of(full) == pages_of(text)
