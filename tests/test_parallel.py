"""parallel.py: the Latin and French beside the English, section by section."""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import parallel  # noqa: E402

LA = """<!-- Latin text, a description the page leaves out. -->

<!-- col 9 -->

## Caput 1 [1-1]

*De re.*

1. Primum *verbum* [1-2] hic.

<!-- col 10 --> 2. Secundum,

> versus unus

### Apparatus

- [1-1] Olim C. I.
- [1-2] Sic.
"""
FR = """<!-- p. 3 -->

## Chapitre 1

1. Premier.

2. Second.

3. Troisième, que l'anglais n'a pas.
"""
EN = r"""== Chapter 1

#align(center)[#smallcaps(all: true)[OF THE THING.]]

#block(inset: (x: 1em))[1\. A synopsis by the translator.]

1\. #smallcaps[First] #emph[word] here.#footnote[A note, with \[brackets\].]

2\. Second \; and more.
"""


def book(tmp_path):
    b = tmp_path / "book"
    for rel, text in {"chapters/typ/vol-1/book-1-chapter-01.typ": EN,
                      "parallel/la/vol-1/book-1-chapter-01.md": LA,
                      "parallel/fr/vol-1/book-1-chapter-01.md": FR}.items():
        (b / rel).parent.mkdir(parents=True, exist_ok=True)
        (b / rel).write_text(text)
    (b / "parallel/sources.json").write_text(json.dumps(
        {"la": {"name": "Latin", "label": "L"}, "fr": {"name": "French", "label": "F"},
         "en": {"label": "E"}}))
    return b


def test_sections_line_up(tmp_path):
    out = tmp_path / "p.html"
    parallel.build(book(tmp_path), "vol-1", out, "T", "reader.html")
    s = out.read_text()
    assert "Book I, Chapter 1" in s
    assert "a description the page leaves out" not in s
    assert '<span class="n">2.</span> Secundum,' in s           # a section after a column marker
    assert "<blockquote>versus unus</blockquote>" in s
    assert "<i>verbum</i>" in s and '<sup class="app">2</sup>' in s
    assert "Olim C. I." in s                                    # the editors' notes, folded
    assert "A synopsis by the translator" not in s              # the translator's synopsis
    assert '<span class="sc">First</span> <i>word</i>' in s
    assert '<span class="fn">A note, with [brackets].</span>' in s
    assert "Second ; and more." in s
    # the French section the English lacks stands in the last row
    row2 = s[s.index('id="book-1-chapter-01-2"'):]
    assert "Troisième" in row2


def test_typ_html_nested():
    assert parallel.typ_html(r"#emph[a #smallcaps[b] c]") == '<i>a <span class="sc">b</span> c</i>'


def test_page_is_the_readers(tmp_path):
    """The parallel page has the reader's bar, contents, settings and its colours."""
    import json
    book = tmp_path / "b"
    (book / "chapters" / "typ" / "vol-1").mkdir(parents=True)
    (book / "parallel" / "la" / "vol-1").mkdir(parents=True)
    (book / "parallel" / "sources.json").write_text(json.dumps({"la": {"name": "Latin", "label": "L"}}))
    (book / "chapters" / "typ" / "vol-1" / "a.typ").write_text("== A\n\n1\\. In English.\n")
    (book / "parallel" / "la" / "vol-1" / "a.md").write_text("1. In Latin.\n")
    out = tmp_path / "p.html"
    parallel.build(book, "vol-1", out, "T", "reader.html")
    t = out.read_text()
    for s in ('id="bar"', 'id="toc"', 'id="settings"', 'data-theme-btn', 'data-col="la"',
              'href="#a"', 'class="prow"', "--measure", 'href="reader.html"'):
        assert s in t
