"""Page-fit faults on a rendered PDF (print_check.page_layout_faults): a heading left at a
page's foot, a chapter ending on a few lines.

  uv run --project colophon --group dev pytest colophon/tests
"""

import shutil
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import typst  # noqa: E402
import print_check  # noqa: E402

# the checks read the rendered PDF with poppler's pdftohtml (not on every CI machine)
pytestmark = pytest.mark.skipif(shutil.which("pdftohtml") is None, reason="needs poppler's pdftohtml")

PARA = "This is an ordinary line of the book's text, long enough to fill the measure well. " * 3


def pdf(tmp_path, body):
    src = tmp_path / "t.typ"
    src.write_text('#set page(width: 5.5in, height: 8.5in, margin: 0.8in)\n'
                   '#set text(size: 11pt)\n'
                   '#show heading.where(level: 1): it => { pagebreak(weak: true); '
                   'align(center, text(size: 16pt, it.body)) }\n'
                   '#show heading.where(level: 2): it => block(text(weight: "bold", it.body))\n'
                   + body)
    out = tmp_path / "t.pdf"
    typst.compile(str(src), output=str(out))
    return out


def test_heading_at_foot(tmp_path):
    # chapter I fills its first page and leaves a level-2 heading at the very foot
    paras = "\n\n".join([PARA] * 7)
    f = pdf(tmp_path, f"= Chapter I\n\n{paras}\n\n#v(1fr)\n== A Heading Here\n#pagebreak()\n{PARA}\n\n= Chapter II\n\n{PARA}\n")
    faults = print_check.page_layout_faults(f)
    assert any("foot of page 1" in x and "A Heading Here" in x for x in faults), faults


def test_short_chapter_ending(tmp_path):
    paras = "\n\n".join([PARA] * 8)     # 31 lines on page 1, 3 on page 2
    f = pdf(tmp_path, f"= Chapter I\n\n{paras}\n\nAnd a last short line.\n\n= Chapter II\n\n{PARA}\n")
    faults = print_check.page_layout_faults(f)
    assert any(x.startswith("a chapter ends on page") for x in faults), faults


def test_clean_pages(tmp_path):
    f = pdf(tmp_path, f"= Chapter I\n\n{PARA}\n\n= Chapter II\n\n{PARA}\n")
    assert print_check.page_layout_faults(f) == []
