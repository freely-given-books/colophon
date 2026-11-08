"""refstyle.py reads a reference the print set with a bare space or with its verse
straight before a note: "1 Sam 14 27." and "1 Cor 7.30#footnote[...]" (Watson, 1663).

  uv run --project colophon --group dev pytest colophon/tests
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import refs  # noqa: E402
import refstyle  # noqa: E402

CONV = refstyle.Converter(refs.load("kjv"))


def test_bare_space_before_the_verse():
    assert "1 Sam 14:27." in CONV.line("his eyes were enlightened, 1 Sam 14 27. Why", "t")
    assert "Ps 37:8." in CONV.line("puts us upon sin, Ps 37 8. Fret not", "t")


def test_verse_before_a_note():
    out = CONV.line("as if we loved not, 1 Cor 7.30#footnote[Non jubet.]", "t")
    assert "1 Cor 7:30#footnote[Non jubet.]" in out


def test_numbers_in_prose_stay():
    # a number after the chapter is a verse only before a stop, comma or note
    for s in ("read Ps 23 5 times over", "Gen 1 and 2 tell it", "Ps 119 9 ways"):
        assert ":" not in CONV.line(s, "t")
