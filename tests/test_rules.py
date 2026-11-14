"""Each rule in rules.py catches what it is for: a break made on purpose.

  uv run --project colophon --group dev pytest colophon/tests
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import rules  # noqa: E402
import spelling  # noqa: E402

TEI = """<TEI xmlns="http://www.tei-c.org/ns/1.0"><teiHeader><fileDesc><titleStmt>
<title>T</title></titleStmt><publicationStmt><p/></publicationStmt><sourceDesc><p/>
</sourceDesc></fileDesc></teiHeader><text><body><div type="chapter" n="1"><p>{}</p>
</div></body></text></TEI>"""


def test_spelling_archaisms(monkeypatch):
    assert rules.spelling_archaisms() == []
    monkeypatch.setitem(spelling.MANUAL, "hath", "has")
    monkeypatch.setitem(spelling.MANUAL, "loueth", "loves")
    monkeypatch.setitem(spelling.MANUAL, "moneth", "month")
    found = rules.spelling_archaisms()
    assert len(found) == 2 and "hath" in found[0] and "loueth" in found[1]


def test_god_capitalized(tmp_path):
    ok, bad = tmp_path / "ok.xml", tmp_path / "bad.xml"
    ok.write_text(TEI.format('a <choice><orig>God</orig><reg resp="#editor">god</reg>'
                             '</choice> of this world'))
    bad.write_text(TEI.format('<choice><orig>God</orig><reg resp="#auto">god</reg></choice>'))
    assert rules.god_capitalized(ok) == []
    assert len(rules.god_capitalized(bad)) == 1


def test_holy_name_capitalized(tmp_path):
    typ = tmp_path / "chapters" / "typ"
    typ.mkdir(parents=True)
    (typ / "a.typ").write_text("the Holy Ghost; sealed with that holy Spirit of promise; "
                               "his holy Ghost? no: the good and holy Spirit.\n")
    found = rules.holy_name_capitalized(tmp_path)
    assert len(found) == 1 and "his holy Ghost" in found[0]
    (typ / "b.typ").write_text("grieve not the holy Spirit of God\n")
    assert len(rules.holy_name_capitalized(tmp_path)) == 2


def test_sweep_clean(tmp_path):
    typ = tmp_path / "chapters" / "typ"
    typ.mkdir(parents=True)
    (typ / "chapter-01.typ").write_text("Words, as they should be; fine.\n")
    assert rules.sweep_clean(tmp_path) == []
    (typ / "chapter-02.typ").write_text("Cicero : Qui deos. #emph[Lo]; then\n")
    kinds = [p.split(": ")[1].split()[0] for p in rules.sweep_clean(tmp_path)]
    assert sorted(kinds) == ["semicolon", "spacing"]


def test_quotes_curled(tmp_path):
    ok, bad = tmp_path / "ok.xml", tmp_path / "bad.xml"
    ok.write_text(TEI.format("He said, ‘I’ll go,’ and went."))
    bad.write_text(TEI.format("He said, ‘I will go‘ and went."))
    assert rules.quotes_curled(ok) == []
    assert len(rules.quotes_curled(bad)) == 1
