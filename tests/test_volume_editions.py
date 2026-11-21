"""A print volume's two release units, Classic and Modern English (release.py):
which of its files are whose, its record's two lists of books, and the gate on
its books' Modern sign-offs, in a git repository made for the test (its tags
are plain annotated tags, never signed). A volume without a -modern print file
is one unit, as before.

  uv run --project colophon --group dev pytest colophon/tests
"""

import sys
import tomllib
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import fgb  # noqa: E402
import release  # noqa: E402
from test_release_editions import FILES, commit, edit, git, tag  # noqa: E402

VOLUME = '''title = "Vol"
author = "A"
books = ["a/x", "a/y"]
print = {print}
'''

VOLUME_FILES = {
    "vol.typ": '#include "../x/chapters/typ/chapter-01.typ"\n'
               '#include "../y/chapters/typ/chapter-01.typ"\n',
    "vol-modern.typ": '#include "../x/chapters/modern/chapter-01.typ"\n'
                      '#include "../y/chapters/modern/chapter-01.typ"\n',
    "cover.typ": '#let cover(edition: none) = [Vol #edition]\n#cover()\n',
    "cover-modern.typ": '#import "cover.typ": cover\n#cover(edition: [Modern English])\n',
}


def make_library(tmp_path, monkeypatch, modern=True):
    for b in ("x", "y"):
        for rel, text in FILES.items():
            p = tmp_path / "books" / "a" / b / rel
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(text, encoding="utf-8")
    vol = tmp_path / "books" / "a" / "vol"
    vol.mkdir(parents=True)
    files = dict(VOLUME_FILES)
    if not modern:
        del files["vol-modern.typ"], files["cover-modern.typ"]
    for rel, text in files.items():
        (vol / rel).write_text(text, encoding="utf-8")
    prints = '["vol.typ", "vol-modern.typ"]' if modern else '["vol.typ"]'
    (vol / "volume.toml").write_text(VOLUME.format(print=prints), encoding="utf-8")
    git(tmp_path, "init", "-q", "-b", "main")
    git(tmp_path, "config", "user.email", "test@example.org")
    git(tmp_path, "config", "user.name", "Test")
    git(tmp_path, "config", "tag.gpgSign", "false")
    git(tmp_path, "config", "commit.gpgSign", "false")
    commit(tmp_path, "the books and the volume")
    monkeypatch.setattr(fgb, "REPO", tmp_path)
    monkeypatch.setattr(release, "REPO", tmp_path)
    monkeypatch.setattr(release, "SIGNERS", tmp_path / "allowed_signers")
    monkeypatch.setattr(release, "REVISIONS", tmp_path / "books" / "revisions.json")
    monkeypatch.setattr(release, "PUBLISHING", tmp_path / "books" / "publishing.toml")
    return vol


@pytest.fixture
def vol(tmp_path, monkeypatch):
    """A print volume of a/x and a/y, with a Modern English print file."""
    return make_library(tmp_path, monkeypatch)


@pytest.fixture
def classic_vol(tmp_path, monkeypatch):
    """A print volume with only its Classic print file."""
    return make_library(tmp_path, monkeypatch, modern=False)


def sign_books(repo, edition_tags=("v1",), modern_tags=("v1",)):
    for b in ("x", "y"):
        for v in edition_tags:
            tag(repo, f"a/{b}/{v}")
        for v in modern_tags:
            tag(repo, f"a/{b}/modern/{v}")


def test_editions(vol):
    assert release.editions(vol) == [release.CLASSIC, release.MODERN]
    assert release.unit(vol, release.MODERN) == "a/vol/modern"
    assert release.edition_title(fgb.Book(vol), release.MODERN) == "Vol (Modern English)"


def test_classic_only_volume_is_one_unit(classic_vol):
    assert release.editions(classic_vol) == [release.CLASSIC]
    s = release.state(classic_vol)
    assert s["build"] is None and s["name"] == "a/vol"
    # a Modern sign-off makes it two, as for a book
    tag(classic_vol.parents[2], "a/vol/modern/v1")
    assert release.editions(classic_vol) == [release.CLASSIC, release.MODERN]


def test_classification(vol):
    which = release.classifier(vol)
    assert which("vol-modern.typ") == which("cover-modern.typ") == release.MODERN
    assert which("vol.typ") == release.CLASSIC
    # cover-modern.typ imports cover.typ; volume.toml is read by neither build
    assert which("cover.typ") is None and which("volume.toml") is None


def test_own_files_hold_back_their_edition(vol):
    repo = vol.parents[2]
    sign_books(repo)
    edit(vol, "RELEASE.toml", 'summary = "Vol."\n')
    tag(repo, "a/vol/v1")
    tag(repo, "a/vol/modern/v1")
    edit(vol, "vol-modern.typ", VOLUME_FILES["vol-modern.typ"] + "// a note\n")
    c, m = release.state(vol), release.state(vol, release.MODERN)
    assert not c["changed"] and m["changed"] == ["books/a/vol/vol-modern.typ"]
    edit(vol, "vol.typ", VOLUME_FILES["vol.typ"] + "// a note\n")
    c = release.state(vol)
    assert c["changed"] == ["books/a/vol/vol.typ"]
    edit(vol, "cover.typ", VOLUME_FILES["cover.typ"] + "// a note\n")
    c, m = release.state(vol), release.state(vol, release.MODERN)
    assert "books/a/vol/cover.typ" in c["changed"] and "books/a/vol/cover.typ" in m["changed"]


def test_record_writes_both_lists(vol, capsys):
    repo = vol.parents[2]
    sign_books(repo, ("v1", "v2"), ("v1",))
    release.record_volume(vol)
    rec = tomllib.loads((vol / "RELEASE.toml").read_text(encoding="utf-8"))
    assert rec["book"] == [{"book": "a/x", "version": "v2"}, {"book": "a/y", "version": "v2"}]
    assert rec["modern"]["book"] == [{"book": "a/x", "version": "v1"},
                                     {"book": "a/y", "version": "v1"}]
    assert rec["modern"]["summary"] == ""
    # the hand-filled summaries are kept; the lists are brought up to date
    text = (vol / "RELEASE.toml").read_text(encoding="utf-8")
    text = text.replace('summary = ""', 'summary = "Vol."', 1)
    text = text.replace('summary = ""', 'summary = "Vol, modern."', 1)
    (vol / "RELEASE.toml").write_text(text, encoding="utf-8")
    tag(repo, "a/x/modern/v2")
    release.record_volume(vol)
    again = (vol / "RELEASE.toml").read_text(encoding="utf-8")
    rec = tomllib.loads(again)
    assert rec["summary"] == "Vol." and rec["modern"]["summary"] == "Vol, modern."
    assert rec["modern"]["book"][0] == {"book": "a/x", "version": "v2"}
    assert "Modern:  a/x: v2 (was v1)" in capsys.readouterr().out
    release.record_volume(vol)
    assert (vol / "RELEASE.toml").read_text(encoding="utf-8") == again


def test_made_from_each_edition(vol):
    repo = vol.parents[2]
    sign_books(repo)
    release.record_volume(vol)
    commit(repo, "the record")
    c, m = release.state(vol), release.state(vol, release.MODERN)
    assert [x["tag"] for x in c["made_from"]] == ["a/x/v1", "a/y/v1"]
    assert [x["tag"] for x in m["made_from"]] == ["a/x/modern/v1", "a/y/modern/v1"]
    # a change to a book's Modern files holds back the Modern volume only
    edit(vol.parent / "x", "chapters/modern/chapter-01.typ", "= Chapter One\nnewer\n")
    c, m = release.state(vol), release.state(vol, release.MODERN)
    assert not any(x["changed"] for x in c["made_from"])
    assert m["made_from"][0]["changed"] == ["books/a/x/chapters/modern/chapter-01.typ"]
    # and a Classic change the Classic volume only
    edit(vol.parent / "y", "chapters/typ/chapter-01.typ", "= Chapter One\nwordes\n")
    c, m = release.state(vol), release.state(vol, release.MODERN)
    assert c["made_from"][1]["changed"] == ["books/a/y/chapters/typ/chapter-01.typ"]
    assert not m["made_from"][1]["changed"]


def test_modern_record_gate(vol):
    repo = vol.parents[2]
    sign_books(repo)
    # a record from before the volume had a Modern English edition
    edit(vol, "RELEASE.toml", 'summary = ""\n\n' + release.VOLUME_BOOKS + "\n")
    s = release.state(vol, release.MODERN)
    assert release.gate_record(s, trial=True)[0].startswith("no [modern] table")
    release.record_volume(vol)
    s = release.state(vol, release.MODERN)
    assert release.gate_record(s, trial=True) == ["no summary in RELEASE.toml [modern]"]
    s["record"]["modern"]["summary"] = "Vol, modern."
    assert release.gate_record(s, trial=True) == []
    # a book's Modern signed off again: the volume must be recorded again
    tag(repo, "a/x/modern/v2")
    s = release.state(vol, release.MODERN)
    s["record"]["modern"]["summary"] = "Vol, modern."
    bad = release.gate_record(s, trial=True)
    assert len(bad) == 1 and "a/x: made from v1, but its newest sign-off is v2" in bad[0]


def test_modern_gate_needs_the_books_modern_signed(vol):
    repo = vol.parents[2]
    sign_books(repo, modern_tags=())
    release.record_volume(vol)
    s = release.state(vol, release.MODERN)
    s["record"]["modern"]["summary"] = "Vol, modern."
    assert release.gate_record(s, trial=True) == [
        f"a/{b}: its Modern English edition is not signed off (./fgb release record "
        "a/vol names each book's newest)" for b in ("x", "y")]


def test_classic_only_record_unchanged(classic_vol, capsys):
    sign_books(classic_vol.parents[2])
    release.record_volume(classic_vol)
    assert (classic_vol / "RELEASE.toml").read_text(encoding="utf-8") == "\n".join([
        "# Release record of Vol: a print volume made of the editions of",
        "# other books (volume.toml). ./fgb release checks it; the editor signs a",
        "# version off with a signed tag, a/vol/vN (./fgb release sign).",
        "",
        "# One or two sentences for the release catalog: the volume, its books.",
        'summary = ""',
        "",
        "# The signed versions of the books this volume is made from, each",
        "# one's newest sign-off: ./fgb release record a/vol writes them again",
        "# after a book is signed off again (then sign the volume off again).",
        "",
        "[[book]]", 'book = "a/x"', 'version = "v1"', "",
        "[[book]]", 'book = "a/y"', 'version = "v1"', ""])
    assert capsys.readouterr().out.splitlines()[:2] == ["  a/x: v1", "  a/y: v1"]


def test_volume_entry_made_from_modern(vol):
    repo = vol.parents[2]
    sign_books(repo)
    release.record_volume(vol)
    commit(repo, "the record")
    tag(repo, "a/vol/modern/v1")
    s = release.state(vol, release.MODERN)
    s["signed"] = False
    e = release.entry(s, fgb.Book(vol), [])
    assert e["unit"] == "a/vol/modern" and e["edition"] == release.MODERN
    assert [m["tag"] for m in e["made_from"]] == ["a/x/modern/v1", "a/y/modern/v1"]
    assert "based_on" not in e and e["title"] == "Vol (Modern English)"
