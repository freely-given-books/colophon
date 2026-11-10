"""OUTLINE_MARKS in the ebook (tei_to_html.mark_point): outline levels set full width, each
numbered point marked by its level, the counts carried through "Lastly".

  uv run --project colophon --group dev pytest colophon/tests
"""

import sys
from pathlib import Path

from lxml import etree

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import tei_to_html  # noqa: E402

T = "{http://www.tei-c.org/ns/1.0}"


def marked(paras):
    r = tei_to_html.HtmlR.__new__(tei_to_html.HtmlR)
    r.point_counts = [0] * len(tei_to_html.POINT_MARKS)
    out = []
    for level, text in paras:
        p = etree.Element(T + "p")
        if level:
            p.set("rend", f"level{level}")
        out.append(tei_to_html.HtmlR.mark_point(r, p, text))
    return out


def test_marks_by_level():
    got = marked([(0, "First, The will."), (1, "First, That which."), (1, "<em>Secondly,</em> More."),
                  (2, "First, Deeper."), (0, "Secondly, Again."), (1, "Lastly, An end.")])
    assert [c for c, _ in got] == ["point point0", "point point1", "point point1", "point point2",
                                   "point point0", "point point1"]
    marks = [t.split("</span>")[0].split(">")[-1] for _, t in got]
    assert marks == ["1.", "(1.)", "(2.)", "[1.]", "2.", "(1.)"]
    assert '<span class="smallcaps">First</span>,' in got[0][1]
    assert got[2][1].endswith("<em>Secondly,</em> More.")


def test_unnumbered_paragraphs_full_width():
    assert marked([(2, "And this is one way."), (0, "Thus it is.")]) == [
        (None, "And this is one way."), (None, "Thus it is.")]
