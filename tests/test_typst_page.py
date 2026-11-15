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


@pytest.mark.skipif(shutil.which("typst") is None, reason="typst not installed")
def test_diagram_lists(tmp_path):
    """A `<diagram>` scope keeps its trees apart, each a ul.diagram with plain item text (Perkins ch. 5)."""
    (tmp_path / "ch").mkdir()
    page = tmp_path / "ch" / "page.typ"
    page.write_text("Before.\n\n#[\n- Isaac\n  - Esau.\n  - Jacob.\n\n- Samuel\n  - Aaron.\n] <diagram>\n\n"
                    "#[\n- Abraham.\n- Isaac.\n] <diagram>\n\nAfter.\n\n- a plain list\n")
    frag, _ = typst_page(page, tmp_path, 1)
    assert frag.count('<ul class="diagram">') == 3
    assert '<ul class="diagram"><li>Isaac<ul><li>Esau.</li><li>Jacob.</li></ul></li></ul>' in frag
    assert '<ul class="diagram"><li>Samuel<ul><li>Aaron.</li></ul></li></ul>' in frag
    assert '<ul class="diagram"><li>Abraham.</li><li>Isaac.</li></ul>' in frag
    assert "fgb-" not in frag and "<ul><li>a plain list</li></ul>" in frag
