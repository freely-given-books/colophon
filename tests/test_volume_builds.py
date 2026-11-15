"""--volume N: which print, cover and EPUB entries a working build of some volumes takes (fgb.py).

  uv run --project colophon --group dev pytest colophon/tests
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import fgb  # noqa: E402


def test_file_volume():
    assert fgb.file_volume("domestical-duties-vol-2.typ") == 2
    assert fgb.file_volume("domestical-duties-vol-1-modern.typ") == 1
    assert fgb.file_volume("cover-vol-12.typ") == 12
    assert fgb.file_volume("cover-vol-1-modern.typ") == 1
    assert fgb.file_volume("cover.typ") is None
    assert fgb.file_volume("the-revolver.typ") is None


def test_in_volumes():
    files = ["dd-vol-1.typ", "dd-vol-2.typ", "dd-vol-1-modern.typ", "cover-vol-2.typ"]
    assert [f for f in files if fgb.in_volumes(f, None)] == files
    assert [f for f in files if fgb.in_volumes(f, [1])] == ["dd-vol-1.typ", "dd-vol-1-modern.typ"]
    assert [f for f in files if fgb.in_volumes(f, [2])] == ["dd-vol-2.typ", "cover-vol-2.typ"]


def test_epub_volume():
    assert fgb.epub_volume({"files": ["vol-3/"]}, 0) == 3
    assert fgb.epub_volume({"title": "x"}, 1) == 2


def test_volume_numbers():
    assert fgb.volume_numbers(None) is None
    assert fgb.volume_numbers(["1,3", "2"]) == [1, 2, 3]
    with pytest.raises(SystemExit):
        fgb.volume_numbers(["one"])


class FakeBook:
    name = "a/b"

    def __init__(self, epub):
        self.cfg = {"EPUB": epub}


def test_check_volumes():
    bk = FakeBook({"volumes": [{"files": ["vol-1/"]}, {"files": ["vol-2/"]}]})
    fgb.check_volumes(bk, [1, 2])
    fgb.check_volumes(bk, None)
    with pytest.raises(SystemExit):
        fgb.check_volumes(bk, [3])
    with pytest.raises(SystemExit):
        fgb.check_volumes(FakeBook({"file": "b.epub"}), [1])


def test_build_epub_chooses_volumes(monkeypatch, capsys):
    built = []
    monkeypatch.setattr(fgb, "build_one_epub", lambda bk, out, e, root: built.append(e["file"]) or [e["file"]])
    bk = FakeBook({"title": "T", "volumes": [
        {"files": ["vol-1/"], "file": "v1.epub", "modern": {"file": "v1-modern.epub"}},
        {"files": ["vol-2/"], "file": "v2.epub"}]})
    assert fgb.build_epub(bk, Path("."), volumes=[1]) == ["v1.epub", "v1-modern.epub"]
    assert fgb.build_epub(bk, Path("."), volumes=[2]) == ["v2.epub"]
    assert "volume 2: no Modern English edition, skipped" in capsys.readouterr().out
    assert fgb.build_epub(bk, Path(".")) == ["v1.epub", "v1-modern.epub", "v2.epub"]
