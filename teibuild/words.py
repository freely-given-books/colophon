"""
Word strings: a token's printed, expanded and machine-modernized forms.
"""

import re

import teibuild  # noqa: F401  (puts colophon on sys.path)

from teitok import T, local  # noqa: E402
from spelling import modernize_word_lower, apply_case_pattern, AMBIGUOUS_NAMES, GRAMMAR_EXCEPTIONS  # noqa: E402

from teibuild import settings as S  # noqa: E402
from teibuild.settings import REF_ABBREVS, ROMAN_RE  # noqa: E402


def piece_text(p, tok, mode):
    """mode: 'dipl' (as printed/transcribed) or 'exp' (abbreviations
    expanded, reconstructed letters supplied)."""
    if isinstance(p, str):
        return p
    if isinstance(p, tuple):              # ("noise", ws)
        return ""
    n = local(p)
    if n == "g":
        ref = p.get("ref")
        if ref == "char:cmbAbbrStroke":
            if mode == "dipl":
                return p.text or "̄"
            idx = next(i for i, e in tok.macrons if e is p)
            return "m" if idx in S.MACRON_M else "n"
        if ref == "char:abque":
            return "ꝗ" if mode == "dipl" else "que"
        if ref == "char:V":
            return p.text or "Ʋ"
        return ""                          # EOL(un)hyphen
    if n == "gap":
        idx = next(i for i, e in tok.gaps if e is p)
        desc = p.find(T + "desc")
        d = desc.text if desc is not None and desc.text else "•"
        if mode == "exp" and idx in S.GAP_FIXES:
            return S.GAP_FIXES[idx][0]
        return d
    if n == "expan":
        if mode == "dipl":
            am = p.find(T + "am")
            return "".join(piece_text(c, tok, mode) for c in am) if am is not None else ""
        ex = p.find(T + "ex")
        return ex.text if ex is not None else ""
    # hi rend=sup, seg decorInit: plain text content
    return "".join(p.itertext())


SUP_EXPANSIONS = {"e": "the", "t": "that", "u": "thou"}


def word_strings(tok):
    tok.orig = "".join(piece_text(p, tok, "dipl") for p in tok.pieces)
    tok.expanded = "".join(piece_text(p, tok, "exp") for p in tok.pieces)
    # y with superscript letter (the thorn contraction): y^e = the, y^t = that
    m = re.fullmatch(r"([yY])([etu])", tok.orig)
    if m and any(not isinstance(p, (str, tuple)) and local(p) == "hi" for p in tok.pieces):
        e = SUP_EXPANSIONS[m.group(2)]
        tok.expanded = e.capitalize() if m.group(1) == "Y" else e


def auto_reg(tok, sentence_start, heading=False, quote_start=False):
    """Automatic modern spelling for one word of main text."""
    # long s and the hooked capital Ʋ (U/V) are letter forms, not spellings
    w = tok.expanded.replace("ſ", "s").replace("Ʋ", "U")
    # a W printed as two Vs (VVorshipfull, Vvisdome) is a letter form too
    w = re.sub(r"^V[Vv](?=[a-z])", "W", re.sub(r"^VV(?=[A-Z])", "W", w))
    if any(not isinstance(p, (str, tuple)) and local(p) == "hi" for p in tok.pieces):
        return w                     # y^e -> the (already expanded)
    if not re.fullmatch(r"[A-Za-z']+", w):
        return w
    if not S.MODERNIZE:
        return w
    low = w.lower()
    if ROMAN_RE.match(w) and w.isupper():
        return w                     # list labels I. II. III.
    # decorated initial artifact: CHristian -> Christian
    if len(w) > 2 and w[0].isupper() and w[1].isupper() and w[2:].islower():
        w = w[0] + w[1:].lower()
    elif S.DROP_CAP_CASE and len(w) > 1 and w.isupper() and any(
            not isinstance(p, (str, tuple)) and local(p) == "seg" and
            p.get("rend") == "decorInit" for p in tok.pieces):
        w = w[0] + w[1:].lower()      # AS there are -> As there are
    if low in GRAMMAR_EXCEPTIONS:
        mod = low
    else:
        mod = modernize_word_lower(low)
    if heading:
        return apply_case_pattern(w, mod)
    if sentence_start and w.islower() and low in REF_ABBREVS:
        sentence_start = False       # "Rom. 12. ver. 9.": the stop ends a number, not a sentence
    if sentence_start:
        k = 1 if mod[:1] in "'’" else 0      # ’tis, ’twas: the letter after the apostrophe
        return mod[:k + 1].upper() + mod[k + 1:] if not w.isupper() or len(w) == 1 \
            else apply_case_pattern(w, mod)
    if w[:1].isupper() and mod in S.LOWERCASE_COMMON_NOUNS and not quote_start:
        return mod
    if w[:1].isupper() and low in AMBIGUOUS_NAMES:
        return AMBIGUOUS_NAMES[low]  # "Mary" mid-sentence is the name, not "marry"
    return apply_case_pattern(w, mod)


NO_SPACE_BEFORE = set(".,;:!?)]’'")


NO_SPACE_AFTER = set("([")
