"""A paragraph set in by its outline level: the review's #pad(left: 2.4em)[...] reads as
level 2, and the print writes it back the same way (p[@rend="level2"]).

  uv run --project colophon --group dev pytest colophon/tests
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from lxml import etree  # noqa: E402
import layout  # noqa: E402
import reviewparse  # noqa: E402


def test_review_reads_levels():
    r = reviewparse.parse_review(
        "== T\n\n2\\. Spiritual mercies.\n\n"
        f"{layout.pad(2)}1\\. The Word Preached.{layout.PAD_END}\n\n"
        f"{layout.pad(1)}Quest. How?{layout.PAD_END}\n", inline_headings=True)
    assert [lvl for _j, lvl in r.para_levels] == [2, 1]
    # the paragraph's words are text, not layout
    assert "Word" in [t for t, _k, _i in r.body]


def test_level_written_back():
    p = etree.fromstring('<p xmlns="http://www.tei-c.org/ns/1.0" rend="level3">x</p>')
    assert layout.para_level(p) == 3 and layout.pad(3).startswith("#pad(left: 6.0em)[#par(")
    p.set("rend", "inset")
    assert layout.para_level(p) == 0
