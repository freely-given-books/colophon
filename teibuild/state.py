"""
State shared by the stages of one build: the reading stream's marks and
the layout's modes, set by main() and the stages.
"""

import teibuild  # noqa: F401  (puts colophon on sys.path)

import reviewparse  # noqa: E402


SPLIT_RE = reviewparse.TOKEN_RE


BLOCK_MARK = {"p": "¶", "item": "-", "signed": "¶", "trailer": "¶", "sp": "¶"}


# Layout mode (a book with LAYOUT in editorial.py): division heads are text
# of the file, marked "H" (a heading line) or "¶" (a run-in heading, for the
# div types in RUN_IN_DIVS). None: heads are skipped, the classic behaviour.
HEAD_MODE = {"on": False, "run_in": set()}


SUBTITLES = set()       # layout subtitles: printed heads set as a centred line


# CLOSER_PLAIN: openers and closers are set as plain paragraphs (a salute,
# a signature), which the review may run on into the text or split
SETTINGS = {"closer_plain": False}


NOTE_SEQ = {"n": 0}


NO_SPACE_RUN_ON = set()     # id(tok): a merge at tok joins without a space


MADE_LISTS = []


LIST_SHAPE = []         # (tok, list_info entry, file), in reading order


EDITION_HEADS = []      # (tok, level, text, file): headings the edition adds


ROOT = {"toks": []}
