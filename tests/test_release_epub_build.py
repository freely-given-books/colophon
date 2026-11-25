"""A point version's files from the EPUB build: the EPUBs and the front covers."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import release  # noqa: E402


def test_keeps_epubs_and_front_covers_only():
    keep = [Path("a-vol-1.epub"), Path("cover-vol-1-front.png")]
    drop = [Path("a-vol-1.pdf"), Path("cover-vol-1.pdf"), Path("x-reader.html")]
    assert [f for f in keep + drop if release.keeps_epub_build(f)] == keep
