"""Outline levels from the author's numbering (outline.py): the counting, Owen's announced
points opened one by one, main heads in small capitals, and a later edition's marks.

  uv run --project colophon --group dev pytest colophon/tests
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import layout  # noqa: E402
import outline  # noqa: E402


def levels(text, cfg=None):
    return [(r["text"][:12], r["level"]) for r in outline.infer("c.typ", text, cfg or {})
            if r.get("numbered")]


def test_numbers_and_styles():
    assert outline.number("1\\. The best things.")[:2] == ("digit", 1)
    assert outline.number("Secondly, It fights.")[:2] == ("word", 2)
    assert outline.number("\\(3.\\) Thirdly")[:2] == ("paren", 3)
    assert outline.number("#emph[Answ.] 2. He who")[:2] == ("digit", 2)
    assert outline.number("I am the way.") is None          # the pronoun, not a numeral
    assert outline.number("Firstborn of all creation") is None


def test_counting_one_mark_at_every_depth():
    # Watson: "1." at every level; a 2 carries on the level whose last number is 1
    text = ("== T\n\n1\\. The best things: these three.\n\n1\\. Power, two ways.\n\n"
            "1\\. Supporting.\n\n2\\. Supplying.\n\n2\\. Wisdom.\n\n2\\. The worst things.\n")
    assert [lvl for _t, lvl in levels(text)] == [0, 1, 2, 2, 1, 0]
    # three open levels all at 1: a 2 could carry on any of them; the deepest, marked
    text = "== T\n\n1\\. A: two things.\n\n1\\. B: two things.\n\n1\\. C.\n\n2\\. D.\n"
    rows = [r for r in outline.infer("c.typ", text, {}) if r.get("numbered")]
    assert rows[-1]["level"] == 2 and rows[-1]["ambiguous"]


def test_announced_points_opened():
    # Owen: four heads announced, then each opened, the count starting again
    text = ("== T\n\nFirst, Its inclination.\n\nSecondly, Its contending.\n\n"
            "First, In general it lusteth, and so on at length.\n\n"
            "First, In a hidden propensity.\n\nSecondly, In actual pressing.\n\n"
            "Secondly, Its particular way of contending.\n")
    assert [lvl for _t, lvl in levels(text)] == [0, 0, 0, 1, 1, 0]


def test_announcing_point_opens_below():
    # "There are five chief subtleties": the 1 after it is the first of them, not a retake
    text = ("== T\n\n1\\. Two things.\n\n1\\. His violence in tempting.\n\n"
            "2\\. His subtlety: there are five chief subtleties.\n\n1\\. He observes the temper.\n")
    assert [lvl for _t, lvl in levels(text)] == [0, 1, 1, 2]


def test_main_head_in_small_capitals():
    text = ("== T\n\n1\\. #smallcaps[The] evil of affliction.\n\n1\\. It teaches.\n\n"
            "1\\. Sub point.\n\n2\\. #smallcaps[The] evil of temptation.\n")
    assert [lvl for _t, lvl in levels(text)][-1] == 0


def test_witness_marks_give_depth(tmp_path):
    w = tmp_path / "w.xml"
    w.write_text("<div><p>1. Its general inclination unto all evil always.</p>"
                 "<p>(1.) In an hidden close propensity unto evil always.</p>"
                 "<p>[1.] In its unexpected surprisals of the soul.</p>"
                 "<p>2. Its particular way of contending with grace.</p></div>")
    text = ("== T\n\nFirst, Its general inclination unto all evil always.\n\n"
            "First, In an hidden close propensity unto evil always.\n\n"
            "First, In its unexpected surprizals of the soul.\n\n"
            "Secondly, Its particular way of contending with grace.\n")
    cfg = {"_witness": outline.Witness(w), "_wmin": 1}     # its outermost mark here: 1.
    rows = [r for r in outline.infer("c.typ", text, cfg) if r.get("numbered")]
    assert [r["level"] for r in rows] == [0, 1, 2, 0]
    assert all(r["witness"] is not None for r in rows)


def test_write_sets_paragraphs_in(tmp_path):
    f = tmp_path / "c.typ"
    f.write_text("== T\n\n1\\. A head: two things.\n\n1\\. A point.\n\nMore of it.\n\n2\\. Another.\n")
    outline.write(f, outline.infer("c.typ", f.read_text(), {}))
    out = f.read_text()
    assert f"{layout.pad(1)}1\\. A point.{layout.PAD_END}" in out
    assert f"{layout.pad(1)}More of it.{layout.PAD_END}" in out
    # written twice, it stays the same
    outline.write(f, outline.infer("c.typ", out, {}))
    assert f.read_text() == out
