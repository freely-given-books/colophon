"""A book's two release units, Classic and Modern English (release.py): which
files are whose, and how each edition's sign-off holds, in a git repository
made for the test (its tags are plain annotated tags, never signed).

  uv run --project colophon --group dev pytest colophon/tests
"""

import json
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import fgb  # noqa: E402
import release  # noqa: E402

EDITORIAL = '''EPUB = {"title": "Book", "author": "A", "file": "b.epub", "front": "ebook-front.html",
        "cover": "cover.typ", "css": ["ebook.css"],
        "modern": {"chapters": "chapters/modern", "file": "b-modern.epub",
                   "title": "Book (Modern English)", "cover": "cover-modern.typ",
                   "front": "ebook-front-modern.html"}}
PRINT = ["b.typ", "b-modern.typ"]
'''

TEI = '''<TEI xmlns="http://www.tei-c.org/ns/1.0"><text><body>
<div type="chapter" n="1"><head>Chapter One</head><p>{text}</p></div>
</body></text></TEI>
'''

FILES = {
    "source/A00001.tcp.xml": "<TEI/>",
    "source/editorial.py": EDITORIAL,
    "source/b.tei.xml": TEI.format(text="words"),
    "source/review-report.md": "# report\n",
    "source/modern-glossary.md": "words\n",
    "chapters/typ/chapter-01.typ": "= Chapter One\nwords\n",
    "chapters/modern/chapter-01.typ": "= Chapter One\nmodern words\n",
    # the Classic print file and a file both print files import
    "b.typ": '#import "shared.typ": x\n#include "chapters/typ/chapter-01.typ"\n',
    "b-modern.typ": '#import "shared.typ": x\n#include "chapters/modern/chapter-01.typ"\n',
    "shared.typ": "#let x = 1\n",
    # the Modern cover is the Classic's, labelled; a comment naming a file reads nothing
    "cover.typ": '// see (cover-modern.typ)\n#image("art/plate.png")\n',
    "cover-modern.typ": '#import "cover.typ": cover\n',
    "ebook-front.html": '<p><img src="art/device.png"/></p>\n',
    "ebook-front-modern.html": '<p><img src="art/device.png"/></p>\n',
    "ebook.css": "p { margin: 0 }\n",
    "art/plate.png": "png",
    "art/device.png": "png",
    "README.md": "# Book\n",
    "RELEASE.toml": 'summary = "The book."\n',
}


def git(repo, *args):
    return subprocess.run(["git", "-C", str(repo), *args], check=True,
                          capture_output=True, text=True).stdout.strip()


@pytest.fixture
def lib(tmp_path, monkeypatch):
    """A library with one book that has a Modern English edition, committed."""
    d = tmp_path / "books" / "a" / "b"
    for rel, text in FILES.items():
        p = d / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")
    git(tmp_path, "init", "-q", "-b", "main")
    git(tmp_path, "config", "user.email", "test@example.org")
    git(tmp_path, "config", "user.name", "Test")
    git(tmp_path, "config", "tag.gpgSign", "false")
    git(tmp_path, "config", "commit.gpgSign", "false")
    commit(tmp_path, "the book")
    monkeypatch.setattr(fgb, "REPO", tmp_path)
    monkeypatch.setattr(release, "REPO", tmp_path)
    monkeypatch.setattr(release, "SIGNERS", tmp_path / "allowed_signers")
    monkeypatch.setattr(release, "REVISIONS", tmp_path / "books" / "revisions.json")
    monkeypatch.setattr(release, "PUBLISHING", tmp_path / "books" / "publishing.toml")
    return d


def commit(repo, msg):
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", msg)


def tag(repo, name):
    """An annotated tag, unsigned (the test's own repository only)."""
    git(repo, "tag", "-a", name, "-m", name)


def edit(d, rel, text):
    p = d / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")
    commit(d.parents[2], f"edit {rel}")


def test_classification(lib):
    which = release.classifier(lib)
    modern = ["chapters/modern/chapter-01.typ", "b-modern.typ", "cover-modern.typ",
              "ebook-front-modern.html", "source/modern-glossary.md"]
    classic = ["chapters/typ/chapter-01.typ", "b.typ", "ebook-front.html", "source/b.tei.xml",
               "source/A00001.tcp.xml", "source/review-report.md"]
    shared = ["source/editorial.py", "RELEASE.toml", "README.md", "shared.typ", "cover.typ",
              "art/plate.png", "art/device.png", "ebook.css"]
    assert {f: which(f) for f in modern} == dict.fromkeys(modern, release.MODERN)
    assert {f: which(f) for f in classic} == dict.fromkeys(classic, release.CLASSIC)
    assert {f: which(f) for f in shared} == dict.fromkeys(shared, None)
    # a file gone (or read by neither build) goes by its name
    assert which("chapters/modern/gone.typ") == release.MODERN
    assert which("old-modern.typ") == release.MODERN
    assert which("chapters/typ/gone.typ") == release.CLASSIC


def test_editions_and_tags(lib):
    assert release.editions(lib) == [release.CLASSIC, release.MODERN]
    tag(lib.parents[2], "a/b/v3")
    tag(lib.parents[2], "a/b/modern/v1")
    assert release.book_tags(lib) == ["a/b/v3"]
    assert release.book_tags(lib, release.MODERN) == ["a/b/modern/v1"]
    assert release.tag_book("a/b/modern/v1.2") == release.tag_book("a/b/v3") == "a/b"
    assert release.unit(lib, release.MODERN) == "a/b/modern"


def states(d):
    return release.state(d), release.state(d, release.MODERN)


def test_modern_change_holds_back_only_the_modern(lib):
    repo = lib.parents[2]
    tag(repo, "a/b/v1")
    tag(repo, "a/b/modern/v1")
    c, m = states(lib)
    assert c["holds"] and m["holds"]
    edit(lib, "chapters/modern/chapter-01.typ", "= Chapter One\nnew modern words\n")
    c, m = states(lib)
    assert c["holds"] and not c["changed"]
    assert m["changed"] == ["books/a/b/chapters/modern/chapter-01.typ"]


def test_classic_change_holds_back_only_the_classic(lib):
    repo = lib.parents[2]
    tag(repo, "a/b/v1")
    tag(repo, "a/b/modern/v1")
    edit(lib, "chapters/typ/chapter-01.typ", "= Chapter One\nwordes\n")
    edit(lib, "source/b.tei.xml", TEI.format(text="wordes"))
    c, m = states(lib)
    assert c["changed"] == ["books/a/b/chapters/typ/chapter-01.typ", "books/a/b/source/b.tei.xml"]
    assert m["holds"] and not m["changed"]


def test_tei_headings_hold_back_the_modern(lib):
    repo = lib.parents[2]
    tag(repo, "a/b/modern/v1")
    edit(lib, "source/b.tei.xml", TEI.format(text="words").replace("Chapter One", "Chapter I"))
    assert release.state(lib, release.MODERN)["changed"] == ["books/a/b/source/b.tei.xml"]


def test_shared_change_holds_back_both(lib):
    repo = lib.parents[2]
    tag(repo, "a/b/v1")
    tag(repo, "a/b/modern/v1")
    edit(lib, "cover.typ", '#image("art/plate.png", width: 50%)\n')
    c, m = states(lib)
    assert c["changed"] == m["changed"] == ["books/a/b/cover.typ"]


def test_release_record_parts(lib):
    repo = lib.parents[2]
    tag(repo, "a/b/v1")
    tag(repo, "a/b/modern/v1")
    edit(lib, "RELEASE.toml", 'summary = "The book."\n\n[modern]\nsummary = "Modern."\n')
    c, m = states(lib)
    assert c["holds"] and m["changed"] == ["books/a/b/RELEASE.toml"]
    tag(repo, "a/b/modern/v2")
    edit(lib, "RELEASE.toml", 'summary = "The book, again."\n\n[modern]\nsummary = "Modern."\n')
    c, m = states(lib)
    assert c["changed"] == ["books/a/b/RELEASE.toml"] and m["holds"]


def test_old_classic_tag_ignores_modern_files(lib):
    """A Classic tag cut before the Modern had its own covered the Modern
    files too: changes to those since do not hold the Classic back."""
    repo = lib.parents[2]
    tag(repo, "a/b/v2")
    edit(lib, "b-modern.typ", '#import "shared.typ": x\n// a note\n'
         '#include "chapters/modern/chapter-01.typ"\n')
    edit(lib, "ebook-front-modern.html", "<p>new</p>\n")
    c, m = states(lib)
    assert c["holds"] and not c["changed"]
    assert "tag" not in m and not m["done"]


def test_uncommitted_counts_per_edition(lib):
    release.state(lib)
    (lib / "chapters" / "modern" / "chapter-01.typ").write_text("dirty\n", encoding="utf-8")
    dirty = release.uncommitted(lib)
    assert release.own_changes(lib, release.CLASSIC, None, dirty) == []
    assert release.own_changes(lib, release.MODERN, None, dirty) == dirty


def test_versions_count_per_edition(lib):
    """The Modern is a Lulu book of its own: its versions start at v1 whatever
    the Classic's are, and books/revisions.json counts each under its own id."""
    repo = lib.parents[2]
    tag(repo, "a/b/v14")
    (repo / "books" / "revisions.json").write_text(json.dumps(
        {"releases": [{"release": "2026.11.10", "books": {"a/b": 14}}]}))
    assert release.last_version(lib) == 14
    assert release.last_version(lib, release.MODERN) == 0     # first Modern: v1
    tag(repo, "a/b/modern/v2")      # signed v2 on purpose: Lulu's first-sale bump
    assert release.last_version(lib, release.MODERN) == 2
    assert release.next_point(lib, release.MODERN) == "2.1"
    assert release.next_point(lib) == "14.1"
    (repo / "books" / "revisions.json").write_text(json.dumps(
        {"releases": [{"release": "2026.11.20", "books": {"a/b": 14, "a/b/modern": 3}}]}))
    assert release.last_version(lib, release.MODERN) == 3
    assert release.last_version(lib) == 14


def test_sign_versions(lib, monkeypatch):
    """sign --modern: v1 after a Classic v14, or the version the editor names."""
    repo = lib.parents[2]
    tag(repo, "a/b/v14")
    monkeypatch.setattr(fgb, "find_book", lambda *a, **k: lib)
    monkeypatch.setattr(release, "run_gates", lambda s, out, **k: ([], {"record": []}))
    tags, real_run = [], subprocess.run

    def fake_run(cmd, *a, **k):
        if "tag" in cmd and "-s" in cmd:     # the signing: noted, not run
            tags.append(cmd[cmd.index("-s") + 1])
            return SimpleNamespace(returncode=0)
        return real_run(cmd, *a, **k)
    monkeypatch.setattr(release.subprocess, "run", fake_run)
    monkeypatch.setattr(release, "signature", lambda t: (False, "not checked"))
    args = dict(book="b", note=None, point=False, modern=True)
    release.cmd_sign(SimpleNamespace(version=None, **args))
    release.cmd_sign(SimpleNamespace(version="2", **args))
    assert tags == ["a/b/modern/v1", "a/b/modern/v2"]


def test_record_adds_a_modern_table(lib, monkeypatch, capsys):
    import tomllib
    monkeypatch.setattr(fgb, "find_book", lambda *a, **k: lib)
    tag(lib.parents[2], "a/b/v2")
    release.cmd_record(SimpleNamespace(book="b"))
    rec = tomllib.loads((lib / "RELEASE.toml").read_text(encoding="utf-8"))
    assert rec["summary"] == "The book."
    assert rec["modern"] == {"based_on": "v2"}
    s = release.state(lib, release.MODERN)
    assert release.gate_record(s) == []   # no summary of its own: the book's is used


def test_modern_entry_takes_the_books_summary():
    rec = {"summary": "The book.", "modern": {"based_on": "v2"}}
    assert (release.modern_record(rec).get("summary") or rec["summary"]) == "The book."


def test_modern_record_gate(lib):
    s = release.state(lib, release.MODERN)
    assert "no [modern] table" in release.gate_record(s)[0]
    s["record"] = {"summary": "x", "modern": {"summary": "y", "based_on": "v9"}}
    assert release.gate_record(s) == ["RELEASE.toml [modern] based_on: no sign-off a/b/v9"]


def test_record_release_by_unit(lib):
    repo = lib.parents[2]
    tag(repo, "a/b/v3")
    tag(repo, "a/b/modern/v1.1")
    release.record_release("2026.11.20", list(states(lib)))
    data = json.loads((repo / "books" / "revisions.json").read_text())
    assert data["releases"][-1]["books"] == {"a/b": 3, "a/b/modern": "1.1"}


def test_build_files_per_edition():
    assert fgb.modern_name("b-modern.typ") and fgb.modern_name("cover-vol-1-modern.typ")
    assert not fgb.modern_name("b.typ") and not fgb.modern_name("cover.typ")
    assert fgb.in_edition("cover.typ", "classic") and not fgb.in_edition("cover.typ", "modern")
    assert fgb.in_edition("cover-modern.typ", None)


def test_build_epub_per_edition(monkeypatch):
    built = []
    monkeypatch.setattr(fgb, "build_one_epub",
                        lambda bk, out, e, root: built.append(e["file"]) or [e["file"]])
    bk = SimpleNamespace(name="a/b", cfg={"EPUB": {"title": "T", "file": "b.epub",
                                                  "modern": {"file": "b-modern.epub"}}})
    assert fgb.build_epub(bk, Path("."), edition="classic") == ["b.epub"]
    assert fgb.build_epub(bk, Path("."), edition="modern") == ["b-modern.epub"]
    assert fgb.build_epub(bk, Path(".")) == ["b.epub", "b-modern.epub"]


def test_asset_names_do_not_collide(lib):
    names = {release.asset_name(lib, "v2", Path(f)) for f in
             ("b.pdf", "cover.pdf", "cover-front.png", "b.epub", "b-reader.html")}
    modern = {release.asset_name(lib, "v2", Path(f)) for f in
              ("b-modern.pdf", "cover-modern.pdf", "cover-modern-front.png",
               "b-modern.epub", "b-modern-reader.html")}
    assert not names & modern and all("-modern" in n for n in modern)
