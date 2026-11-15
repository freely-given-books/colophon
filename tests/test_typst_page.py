"""typst_page keeps footnotes that sit inside #pad or #align (Typst's HTML export drops them)."""
import shutil
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from tei_epub import typst_page  # noqa: E402


@pytest.mark.skipif(shutil.which("typst") is None, reason="typst not installed")
def test_notes_inside_pad_and_align(tmp_path):
    (tmp_path / "ch").mkdir()
    page = tmp_path / "ch" / "page.typ"
    page.write_text("Plain.#footnote[n-plain]\n\n"
                    "#pad(left: 4.0em)[#par(first-line-indent: (amount: 12pt, all: true))[Padded.#footnote[n-pad]]]\n\n"
                    "#align(center)[Centred.#footnote[n-align]]\n")
    frag, k = typst_page(page, tmp_path, 1)
    assert k == 3
    for n in ("n-plain", "n-pad", "n-align"):
        assert n in frag
    assert "Padded." in frag and "Centred." in frag
