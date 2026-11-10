"""A print volume (fgb.py, release.py): what it may include, and its record.

  uv run --project colophon --group dev pytest colophon/tests
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import fgb  # noqa: E402


def library(tmp_path, monkeypatch, include):
    for b in ("x", "y", "z"):
        src = tmp_path / "books" / "a" / b / "source"
        src.mkdir(parents=True)
        (src / "A00001.tcp.xml").write_text("<TEI/>")
    vol = tmp_path / "books" / "a" / "vol"
    vol.mkdir()
    (vol / "volume.toml").write_text('title = "Vol"\nauthor = "A"\nbooks = ["a/x", "a/y"]\n')
    (vol / "vol.typ").write_text("".join(f'#include "{p}"\n' for p in include))
    monkeypatch.setattr(fgb, "REPO", tmp_path)
    return vol


def test_volume_includes_only_its_books(tmp_path, monkeypatch):
    vol = library(tmp_path, monkeypatch, ["../x/chapters/typ/chapter-01.typ",
                                          "../y/chapters/typ/chapter-01.typ", "part.typ"])
    assert fgb.volume_problems(vol) == []
    assert fgb.incompatible(vol) == []
    assert fgb.volumes() == [vol]
    bk = fgb.Book(vol)
    assert (bk.title, bk.author, bk.parts()) == ("Vol", "A", ["a/x", "a/y"])


def test_volume_including_another_book(tmp_path, monkeypatch):
    vol = library(tmp_path, monkeypatch, ["../x/chapters/typ/chapter-01.typ",
                                          "../z/chapters/typ/chapter-01.typ"])
    found = fgb.volume_problems(vol)
    assert len(found) == 1 and "../z/" in found[0]


def test_volume_of_a_book_not_on_the_pipeline(tmp_path, monkeypatch):
    vol = library(tmp_path, monkeypatch, [])
    (vol / "volume.toml").write_text('title = "Vol"\nbooks = ["a/x", "a/nothing"]\n')
    found = fgb.volume_problems(vol)
    assert len(found) == 1 and "a/nothing" in found[0]
