"""release make takes an unchanged edition's files from its last build
(release.Store, release.reuse): the same sign-off and tools give the same
files, so only changed books, and books whose files are gone, are built.

  uv run --project colophon --group dev pytest colophon/tests
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import release  # noqa: E402


def unit(name="a/book", tag="a/book/v2"):
    return {"unit": name, "name": name, "dir": Path("/nowhere"), "signed": True,
            "tag": {"tag": tag, "commit": "c0ffee", "version": tag.rsplit("/", 1)[-1]}}


def built(root, files):
    """Files written into a release folder, as make records them."""
    root.mkdir(parents=True, exist_ok=True)
    out = []
    for name, text in files.items():
        p = root / name
        p.write_text(text)
        out.append({"name": name, "bytes": p.stat().st_size, "sha256": release.sha256(p)})
    return out


@pytest.fixture
def made(tmp_path):
    """A first release that built one edition and kept it."""
    s = unit()
    store = release.Store(tmp_path)
    files = built(tmp_path / "2026.11.24", {"book-v2.pdf": "pdf", "book-v2.epub": "epub"})
    store.keep(s, "key1", tmp_path / "2026.11.24", files,
               {"unit": s["unit"], "carried": False, "files": files,
                "signed_off": {"tag": "a/book/v2", "signature_verified": True}})
    return tmp_path, s


def test_same_key_takes_the_files(made):
    out, s = made
    root = out / "2026.11.25"
    root.mkdir()
    files, old = release.Store(out).take(s, "key1", root)
    assert sorted(f["name"] for f in files) == ["book-v2.epub", "book-v2.pdf"]
    assert (root / "book-v2.pdf").read_text() == "pdf"
    assert old["unit"] == "a/book"


def test_other_key_or_rebuild_builds(made):
    out, s = made
    assert release.Store(out).take(s, "key2", out / "x") is None
    assert release.Store(out, use=False).take(s, "key1", out / "x") is None
    assert release.Store(out).take(unit("a/other"), "key1", out / "x") is None


def test_missing_or_damaged_file_builds(made):
    out, s = made
    store = release.Store(out)
    pdf = next(f for f in store.index["a/book"]["files"] if f["name"].endswith(".pdf"))
    p = out / ".built" / pdf["sha256"]
    p.unlink()
    p.write_text("PDF")                       # same size, other bytes
    root = out / "r"
    root.mkdir()
    assert store.take(s, "key1", root) is None
    p.unlink()
    assert store.take(s, "key1", root) is None


def test_a_new_build_drops_the_old_files(made):
    out, s = made
    store = release.Store(out)
    old = {f["sha256"] for f in store.index["a/book"]["files"]}
    files = built(out / "2026.11.25", {"book-v3.pdf": "new pdf"})
    store.keep(s, "key2", out / "2026.11.25", files, {"files": files})
    left = {p.name for p in (out / ".built").iterdir()} - {"index.json"}
    assert left == {files[0]["sha256"]} and not old & left
    assert release.Store(out).index["a/book"]["key"] == "key2"


def test_reuse_done_runs_its_cheap_gates(made, monkeypatch):
    out, s = made
    root = out / "r"
    root.mkdir()
    monkeypatch.setattr(release, "gate_record", lambda s, trial=False: [])
    monkeypatch.setattr(release, "uncommitted", lambda d: [])
    monkeypatch.setattr(release.fgb, "Book", lambda d: None)
    monkeypatch.setattr(release, "entry", lambda s, bk, files, carried=False:
                        {"fresh": True, "files": files})
    e = release.reuse(s, "key1", release.Store(out), root, False)
    assert e["fresh"] and len(e["files"]) == 2
    # a record that no longer passes, or uncommitted files: built, so the gate says why
    monkeypatch.setattr(release, "gate_record", lambda s, trial=False: ["bad"])
    assert release.reuse(s, "key1", release.Store(out), root, False) is None
    monkeypatch.setattr(release, "gate_record", lambda s, trial=False: [])
    monkeypatch.setattr(release, "uncommitted", lambda d: ["books/a/book/x.typ"])
    assert release.reuse(s, "key1", release.Store(out), root, False) is None


def test_reuse_carried_marks_it_carried(made):
    out, s = made
    root = out / "r"
    root.mkdir()
    s["signed"] = False
    e = release.reuse(s, "key1", release.Store(out), root, True, carried=True)
    assert e["carried"] is True
    assert e["signed_off"] == {"tag": "a/book/v2", "signature_verified": False}
    assert [f["name"] for f in e["files"]] == ["book-v2.pdf", "book-v2.epub"]
