"""printfacts: a release's page counts, trims and cover wraps."""

import hashlib
import shutil
import sys
from pathlib import Path

import pytest
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import printfacts  # noqa: E402

pytestmark = pytest.mark.skipif(shutil.which("pdftoppm") is None or shutil.which("pdfinfo") is None,
                                reason="needs poppler's pdfinfo and pdftoppm")

SPINE = 0.5


def pdf(path, w_in, h_in, pages=1, spine_at=None):
    """A PDF of blank pages w x h inches; a red band spine_at..+SPINE in."""
    pages_ = []
    for _ in range(pages):
        im = Image.new("RGB", (round(w_in * 72), round(h_in * 72)), "white")
        if spine_at is not None:
            im.paste((200, 0, 0), (round(spine_at * 72), 0, round((spine_at + SPINE) * 72), im.height))
        pages_.append(im)
    pages_[0].save(path, "PDF", resolution=72, save_all=True, append_images=pages_[1:])


def test_facts_and_wrap(tmp_path):
    pdf(tmp_path / "the-book-v3-vol-2.pdf", 5.5, 8.5, pages=3)
    b = printfacts.BLEED
    pdf(tmp_path / "the-book-v3-cover-vol-2.pdf", 2 * 5.5 + 2 * b + SPINE, 8.5 + 2 * b, spine_at=b + 5.5)
    entries = [{"files": [{"name": "the-book-v3-vol-2.pdf"}, {"name": "the-book-v3-cover-vol-2.pdf"},
                          {"name": "the-book-v3-vol-2.epub"}]}]
    sha = lambda p: hashlib.sha256(Path(p).read_bytes()).hexdigest()
    assert printfacts.add(tmp_path, entries, sha) == []
    files = {f["name"]: f for f in entries[0]["files"]}
    assert files["the-book-v3-vol-2.pdf"]["print"] == {"pages": 3, "width": 5.5, "height": 8.5}
    wrap = files["the-book-v3-cover-vol-2.pdf"]["wrap"]
    assert wrap["spine"] == SPINE
    # the band's average, give or take the edges' blending
    rgb = [int(wrap["color"][i:i + 2], 16) for i in (1, 3, 5)]
    assert max(abs(a - b) for a, b in zip(rgb, (200, 0, 0))) <= 8
    for part, key in (("back", "back"), ("spine", "spine_image"), ("front", "front")):
        name = f"the-book-v3-cover-vol-2-{part}.webp"
        assert wrap[key] == name and name in files and files[name]["sha256"]
    assert Image.open(tmp_path / wrap["front"]).width == printfacts.WIDTH
    assert "print" not in files["the-book-v3-vol-2.epub"]


def test_cover_that_does_not_fit_is_skipped(tmp_path):
    pdf(tmp_path / "x-v1.pdf", 5.5, 8.5)
    pdf(tmp_path / "x-v1-cover.pdf", 6, 9)          # narrower than two panels
    entries = [{"files": [{"name": "x-v1.pdf"}, {"name": "x-v1-cover.pdf"}]}]
    assert printfacts.add(tmp_path, entries, lambda p: "") == ["x-v1-cover.pdf"]
    assert "wrap" not in entries[0]["files"][1]


def test_volume_cover_pairs_with_its_book_file_interior(tmp_path):
    """A volume's interior is named for its book file (-institutes-vol-1.pdf), its
    cover for the volume (-cover-vol-1.pdf): they still pair, and the Modern's too."""
    b = printfacts.BLEED
    entries = [{"files": []}]
    for tail in ("vol-1", "vol-1-modern"):
        pdf(tmp_path / f"x-v1-institutes-{tail}.pdf", 5.5, 8.5, pages=2)
        pdf(tmp_path / f"x-v1-cover-{tail}.pdf", 2 * 5.5 + 2 * b + SPINE, 8.5 + 2 * b, spine_at=b + 5.5)
        entries[0]["files"] += [{"name": f"x-v1-institutes-{tail}.pdf"}, {"name": f"x-v1-cover-{tail}.pdf"}]
    assert printfacts.add(tmp_path, entries, lambda p: "") == []
    files = {f["name"]: f for f in entries[0]["files"]}
    for tail in ("vol-1", "vol-1-modern"):
        assert files[f"x-v1-cover-{tail}.pdf"]["wrap"]["front"] == f"x-v1-cover-{tail}-front.webp"
