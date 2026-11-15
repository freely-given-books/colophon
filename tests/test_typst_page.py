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


@pytest.mark.skipif(shutil.which("typst") is None, reason="typst not installed")
def test_outline_levels_and_blocks(tmp_path):
    """The Modern English pages keep the outline levels and set-off blocks the Classic's have
    (Watson's Cordial ch. 3): a #pad's level and OUTLINE_MARKS marks (tei_to_html.outline_para,
    shared), a set-in list, a summary, an epigraph, a subtitle, a signature, small capitals."""
    from tei_to_html import POINT_MARKS, outline_para
    (tmp_path / "ch").mkdir()
    page = tmp_path / "ch" / "page.typ"
    pad = "#pad(left: {:.1f}em)[#par(first-line-indent: (amount: 12pt, all: true))[{}]]\n\n"
    page.write_text(
        "== Chapter III\n\n"
        "#align(center)[Showing that all things work for good.]\n\n"
        "#align(center)[\n  #block(width: 85%, breakable: false)[\n    #set par(justify: false)\n"
        "    #text(size: 0.9em, weight: 600)[Rom 8:28]\n\n"
        "    #text(style: \"italic\")[All things work together for good.]\n  ]\n]\n\n"
        "#block(inset: (x: 1em))[\n  #set par(justify: false)\n  #text(size: 0.9em)[A summary.]\n]\n\n"
        "#smallcaps[It] is plain.\n\n"
        "#par(first-line-indent: (amount: 12pt, all: true))[Secondly, a thing.]\n\n"
        + pad.format(2.0, "1\\. God’s power works for good.")
        + pad.format(4.0, "1\\. In supporting us in misery.#footnote[n-pad]")
        + "#[\n#set enum(indent: 6.0em)\n+ The best things.\n+ The worst things.\n]\n\n"
        "#[\n#set enum(indent: 24pt)\n+ A.\n]\n\n"
        "#block(inset: (x: 1em))[Set off.]\n\n"
        "#v(1em)\n\n#align(right)[Yours,]\n\n#align(right)[T. W.]\n")
    frag, k = typst_page(page, tmp_path, 1, [0] * len(POINT_MARKS), subtitle=True)
    assert k == 1 and "n-pad" in frag and "fgb-" not in frag
    assert '<h3>Chapter III</h3><p class="subtitle">Showing that all things work for good.</p>' in frag
    assert ('<div class="epigraph"><p class="epigraph-ref">Rom 8:28</p>'
            '<p class="epigraph-text">All things work together for good.</p></div>') in frag
    assert '<p class="inset summary">A summary.</p>' in frag
    assert '<p data-level="0"><span class="smallcaps">It</span> is plain.</p>' in frag
    assert ('<p class="point point0" data-level="0"><span class="omark">2.</span> '
            '<span class="smallcaps">Secondly</span>, a thing.</p>') in frag
    # the same markup as the Classic's for the same paragraph: one function sets both
    assert outline_para("1. God’s power works for good.", 1, [0] * len(POINT_MARKS)) in frag
    assert '<p class="point point1" data-level="1">(1.) God’s power works for good.</p>' in frag
    assert '<p class="point point2" data-level="2">[1.] In supporting us in misery.<a class="noteref"' in frag
    assert '<ol class="level3"><li>The best things.</li>' in frag
    assert '<ol class="indent"><li>A.</li></ol>' in frag
    assert '<p class="inset">Set off.</p>' in frag
    assert '<p class="signature signature-first">Yours,</p><p class="signature">T. W.</p>' in frag
    # without OUTLINE_MARKS a set-in paragraph is p.levelN, the rest plain; no subtitle: centred
    frag, _ = typst_page(page, tmp_path, 1)
    assert '<p class="level2">1. In supporting us in misery.' in frag
    assert "<p>Secondly, a thing.</p>" in frag
    assert '<p class="center">Showing that all things work for good.</p>' in frag
