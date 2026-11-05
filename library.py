"""
Where the books are: the library repository colophon works on, the one
holding books/<author>/<book>/ (and typst/fgbooks-typst, the templates).

  1. $FGB_LIBRARY, which the library's ./fgb wrapper sets;
  2. the folder colophon is checked out in, when it is a submodule there;
  3. the nearest folder above the current one that holds books/.

The library's own settings are in colophon.toml at its root (settings()):
  editor        the editor's full name, as the TEI header credits the review
  editor_short  the name as the press prints it ("the editions prepared by ...")
"""

import os
from pathlib import Path

HERE = Path(__file__).resolve().parent


def find():
    env = os.environ.get("FGB_LIBRARY")
    if env:
        return Path(env).resolve()
    if (HERE.parent / "books").is_dir():
        return HERE.parent
    cwd = Path.cwd().resolve()
    for d in (cwd, *cwd.parents):
        if (d / "books").is_dir():
            return d
    return cwd


ROOT = find()


def settings():
    """The library's colophon.toml ({} when it has none)."""
    import tomllib
    path = ROOT / "colophon.toml"
    return tomllib.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


def cache(name):
    """A cache folder of colophon's: $XDG_CACHE_HOME/<name>, or ~/.cache/<name>."""
    return Path(os.environ.get("XDG_CACHE_HOME") or Path.home() / ".cache") / name
