"""
The book's settings: the defaults, replaced by the book's
source/editorial.py (load_tables). Read as settings.NAME, since a book
rebinds them.
"""

import re


XML_NS = "http://www.w3.org/XML/1998/namespace"


# Macron abbreviations default to a suppressed "n"; these document-order
# indices expand to "m" instead (checked by hand against context).
MACRON_M = set()


# Illegible <gap>s reconstructed from context, keyed by document-order
# index of non-duplicate gaps: (letters, certainty, evidence note).
GAP_FIXES = {}


# Capitalized common nouns lowercased when not sentence-initial.
LOWERCASE_COMMON_NOUNS = set()


# The first word of an italic run of QUOTE_MIN_WORDS or more (a quotation:
# "saith, Feed the Flock ...") keeps its printed capital under
# LOWERCASE_COMMON_NOUNS; a shorter italic run (emphasis) is lowercased.
QUOTE_START_CASE = False


QUOTE_MIN_WORDS = 5


# Notes shown under "Please check" at the top of the report.
REPORT_NOTES = []


# Margin notes modernized as well, keeping their capitals as printed (the
# default keeps notes in original spelling, abbreviations expanded); "case":
# modernized and cased as body text (sentence case, LOWERCASE_COMMON_NOUNS),
# for notes that are prose in a book that capitalizes its nouns (Edwards).
MODERNIZE_NOTES = False


# Latin found per run of text (the words between two pieces of markup): a run
# of LATIN_MIN_WORDS or more that is mostly not English, even modernized, is
# left as printed. Without it only the words in spelling.LATIN_SKIP are safe.
LATIN_RUNS = False


LATIN_MIN_WORDS = 4


# Greek/Hebrew the transcribers could not key (<gap reason="foreign">): left
# out of the reading text, with the punctuation it leaves stranded (reg/@type
# "omission"; the orig layer keeps the placeholder).
DROP_FOREIGN_GAPS = False


# Text for the reading layer in place of a gap of another kind, by reason,
# e.g. {"missing": "[{extent} of the 1622 edition are wanting here.]"}.
GAP_NOTES = {}


# "&c." read as "etc." (reg/@type "abbreviation").
EXPAND_ETC = False


# The legacy sentence rule (Perkins, Simon Magus): an italic run never opens
# a sentence, even at the start of a paragraph or after a full stop.
# "after-stop" (Gouge): an italic boundary right after . ! ? cancels the new
# sentence, but a paragraph that opens in italics still starts one.
# False: italics are ignored when deciding where a sentence starts.
ITALIC_SENTENCE_QUIRK = True


# A decorated initial printed with its word in capitals ("AS there are"):
# set the word in ordinary case at the start of the paragraph.
DROP_CAP_CASE = False


# The first word of each division, printed in capitals after a drop cap
# (GOD, AND, COnsider), set in small capitals (opening_smallcaps).
OPENING_SMALLCAPS = False


# Words this edition sets in small capitals (smallcaps_phrases): a list of
# the printed words with a little context, the small-capital words in
# brackets, matched without regard to case or spacing:
#   "salvation is [all of grace], which"   "[HE WHO SPOKE] and wrote"
# ^ and $ stand for the start and end of the block: "^[UNGODLY]$".
SMALLCAPS_PHRASES = ()


# A function of the TEI root giving the lists that are diagrams (a genealogy
# printed as a tree): list/@rend="diagram", set whole like an illustration.
DIAGRAM_LISTS = None


# A function of the TEI root giving pairs of tables printed "laid even one
# against another" (Gouge's parallel of husbands' and wives' duties):
# table/@rend="parallel" on both, set as two columns, item n against item n.
PARALLEL_TABLES = None


# The early-modern machine pass (spelling engine, sentence case, common-noun
# lowercasing). A book from a modern source (CCEL) turns it off: its words
# stay as given, and only TYPOGRAPHY and the review change them.
MODERNIZE = True


# Straight quotes curled the way Typst curls them (after a letter, digit or
# closing punctuation a quote closes, otherwise it opens) and "--" set as an
# em dash, recorded as #auto punctuation readings. For sources keyed in
# ASCII (CCEL); a TCP transcription already has its printed marks.
TYPOGRAPHY = False


DASH = "\u2014"          # what "--" becomes; " \u2014 " for a spaced dash


# The edition's attribution, when it differs from the TCP header's (a work
# printed under another's name): (author as in titleStmt, note giving the
# grounds). The printed/catalogue attribution stays in sourceDesc.
AUTHOR = None


# What the source is ("tcp" or "thml"), for the header; set by main().
SOURCE_KIND = "tcp"


def load_tables(path):
    """Replace the tables above with those defined in a book's editorial.py."""
    import runpy
    ns = runpy.run_path(str(path))
    g = globals()
    for name in ("MACRON_M", "GAP_FIXES", "LOWERCASE_COMMON_NOUNS", "REPORT_NOTES",
                 "MODERNIZE_NOTES", "LATIN_RUNS", "DROP_FOREIGN_GAPS", "GAP_NOTES",
                 "EXPAND_ETC", "ITALIC_SENTENCE_QUIRK", "DROP_CAP_CASE",
                 "MODERNIZE", "TYPOGRAPHY", "DASH", "AUTHOR", "QUOTE_START_CASE",
                 "OPENING_SMALLCAPS", "SMALLCAPS_PHRASES", "DIAGRAM_LISTS",
                 "PARALLEL_TABLES"):
        if name in ns:
            g[name] = ns[name]
    # the book's own spellings, over the shared table (e.g. Gouge keeps
    # "domestical" where the shared table has "domestic")
    import spelling
    for k, v in ns.get("SPELLING", {}).items():
        spelling.MANUAL[k] = v
        spelling.NAMES.pop(k, None)


NUMERAL_RE = re.compile(r"\d{1,2}|(?=[IVXLC]+$)[IVXLC]+", re.I)


ROMAN_RE = re.compile(r"^(?=[IVXLC]+$)M{0,3}(CM|CD|D?C{0,3})(XC|XL|L?X{0,3})(IX|IV|V?I{0,3})$",
                      re.I)


# reference abbreviations printed in lower case after a verse number's stop
# ("Rom. 12. ver. 9.", "Judges 6. v. 1."): not the start of a sentence
REF_ABBREVS = {"v", "ver", "vers", "chap", "ch", "cap", "viz"}


# an exclamation after one of these runs on: "oh! how", "Ah! you" (the word
# after it keeps its printed case)
INTERJECTIONS = {"oh", "ah", "alas", "o"}
