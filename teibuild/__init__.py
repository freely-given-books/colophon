"""
The stages of build_tei.py, the enriched TEI built from a source and the
reviewed chapters. In the order they depend on each other:

  settings   the book's settings (editorial.py)
  words      a token's printed, expanded and modernized forms
  tokens     helpers on the token tree
  state      state shared by the stages of one build
  emit       TEI elements rebuilt from annotated tokens
  machine    the machine pass (#auto) and the reading stream
  align      the reading stream against the reviewed text
  decisions  the review's decisions (#editor) applied
  spacing    the review's spaces
  emphasis   italics the review removed or added
  structure  splits, lists, the review's list shapes, added headings
  notes      notes matched and placed; a division reviewed as a whole
  header     the TEI header, and writing the file
  marking    small caps, openings, diagrams on the built tree
  report     --list and the review report

build_tei.py (main, build_layout) runs them.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
