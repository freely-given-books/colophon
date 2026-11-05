#!/usr/bin/env python3
"""
Build an enriched TEI edition of an EEBO-TCP text.

  python3 build_tei.py SOURCE.xml OUT.xml [--review DIR] [--report FILE] [--tables FILE]

Book-specific tables (macron n/m, reconstructed gaps, nouns to lowercase,
report notes) live in the book's source/editorial.py, found next to SOURCE.

Starting from the untouched TCP transcription, this adds editorial layers
*inside* the same file, without removing anything from the original:

  <choice><abbr>fro&#x304;</abbr><expan>from</expan></choice>   macron abbreviations
  <supplied reason="illegible" ...>eu</supplied>                  reconstructed letters
  <choice><orig>mariage</orig><reg>marriage</reg></choice>        modern spelling

and, if --review points at a folder of reviewed Typst chapters (the
dedication.typ + chapter-NN.typ layout used in freely-given-books), aligns
that reviewed text against the automatic modernization and records every
review decision as its own <reg resp="#editor">, so the enriched file
reproduces the reviewed reading text while keeping the 1609 original
extractable word for word.

The stages are the modules of teibuild/ (its __init__ lists them in order);
this script reads the arguments and runs them.
"""

import argparse
import copy
import re
import sys
from pathlib import Path
from lxml import etree

sys.path.insert(0, str(Path(__file__).parent))
from teitok import T, local, tokenize  # noqa: E402
import reviewparse  # noqa: E402
import refstyle  # noqa: E402
import layout  # noqa: E402
import sources  # noqa: E402
from teibuild import settings as S  # noqa: E402
from teibuild.settings import load_tables  # noqa: E402
from teibuild.tokens import View  # noqa: E402
from teibuild.state import BLOCK_MARK, HEAD_MODE, ROOT, SETTINGS, SPLIT_RE, SUBTITLES  # noqa: E402
from teibuild.emit import rebuild  # noqa: E402
from teibuild.machine import compute_auto, stream  # noqa: E402
from teibuild.align import align  # noqa: E402
from teibuild.decisions import apply_clusters  # noqa: E402
from teibuild.structure import (  # noqa: E402
    apply_edition_heads,
    apply_list_shape,
    collect_splits,
    restructure)
from teibuild.notes import keep_trailers, review_division  # noqa: E402
from teibuild.header import add_header, write_tei  # noqa: E402
from teibuild.marking import mark_diagrams, opening_smallcaps, smallcaps_phrases  # noqa: E402
from teibuild.report import list_editorial, write_report  # noqa: E402


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("source")
    ap.add_argument("out", nargs="?")
    ap.add_argument("--list", action="store_true",
                    help="list every macron abbreviation and illegible gap with its "
                    "index, page and context (for filling in editorial.py), then stop")
    ap.add_argument("--review", help="folder with dedication.typ, chapter-NN.typ")
    ap.add_argument("--report", help="write a Markdown report of review decisions")
    ap.add_argument("--editor", default="Courtney Allen Hicks")
    ap.add_argument("--tables", help="book's editorial.py (default: editorial.py "
                    "next to SOURCE, if there is one)")
    args = ap.parse_args()
    if not args.list and not args.out:
        ap.error("OUT is required unless --list is given")
    tables = Path(args.tables) if args.tables else Path(args.source).parent / "editorial.py"
    cfg = {}
    if tables.exists():
        load_tables(tables)
        import runpy
        cfg = runpy.run_path(str(tables))
    elif args.tables:
        ap.error(f"no such file: {tables}")

    S.SOURCE_KIND = sources.kind(args.source)
    src = sources.load(args.source)
    tree = copy.deepcopy(src)
    root = tree.getroot()
    text = root.find(".//" + T + "text")
    toks = tokenize(text, {"macron": 0, "gap": 0})
    compute_auto(toks)
    if args.list:
        list_editorial(toks)
        return

    files = layout.book_layout(root, cfg)
    if files is not None:
        missing = layout.check(root, files, cfg)
        if missing:
            for el, n in missing[:20]:
                print(f"  not in any file: <{local(el)}> {n} words: "
                      f"{' '.join(''.join(el.itertext()).split())[:70]}", file=sys.stderr)
            sys.exit(f"LAYOUT leaves {len(missing)} text blocks out; add them to a "
                     "file or to SKIP_DIVISIONS")
        HEAD_MODE["on"] = True
        HEAD_MODE["run_in"] = set(cfg.get("RUN_IN_DIVS", ()))
        SETTINGS["closer_plain"] = bool(cfg.get("CLOSER_PLAIN"))
        if SETTINGS["closer_plain"]:
            BLOCK_MARK.update({"salute": "¶", "dateline": "¶"})
        return build_layout(args, tree, root, text, toks, files, cfg)

    divs = []

    def find(ts):
        for t in ts:
            if t.kind == "container":
                if local(t.el) == "div" and t.el.get("type") in ("dedication", "chapter"):
                    divs.append(t)
                find(t.children)
    find(toks)

    log, unresolved, all_splits = [], [], []
    if args.review:
        R = Path(args.review)
        files = [("dedication.typ" if d.el.get("type") == "dedication"
                  else f"chapter-{int(d.el.get('n')):02d}.typ") for d in divs]
        order = 0
        for d, f in zip(divs, files):
            review = reviewparse.parse_review((R / f).read_text())
            heads = review.headings
            # headings
            sub = [c for c in d.children if c.kind == "container" and
                   local(c.el) == "head" and c.el.get("type") == "sub"]
            if sub and heads:
                title = re.sub(r"^\d+\.\s*", "", heads[0])
                hs = stream(sub[0].children, skip_heads=False)
                if hs and hs[-1][0] == ".":
                    hs = hs[:-1]
                ht = [(x, "w") for x in SPLIT_RE.findall(title)]
                hc, _ = align(hs, ht, [], f + " heading")
                apply_clusters(hc, log, unresolved, f + " heading")
            elif heads and (d.el.get("type") == "dedication" or not sub):
                d.extra["edition_head"] = heads[0]
            if review.short and review.short[0]:
                d.extra["short_head"] = review.short[0]
            keep_trailers(d, review, f, log)
            st, s = review_division(d, review, f, log, unresolved)
            index = {}
            for k, e in enumerate(s):
                index.setdefault(id(e[2]), order + k)
            order += len(s)
            all_splits += collect_splits(st, index, log)
        restructure(all_splits, log)
        ROOT["toks"] = toks
        apply_list_shape(log)

    rebuild(text, toks)
    if S.OPENING_SMALLCAPS:
        opening_smallcaps([[d.el] for d in divs], root,
                          cfg.get("SKIP_DIVISIONS", ()))
    smallcaps_phrases(root, S.SMALLCAPS_PHRASES)
    mark_diagrams(root)
    refstyle.mark_readings(text)
    for d in divs:
        if d.extra.get("edition_head"):
            h = etree.Element(T + "head")
            h.set("type", "edition")
            h.set("change", "#review")
            h.text = d.extra["edition_head"]
            first = d.el.find(T + "head")
            idx = list(d.el).index(first) + 1 if first is not None else 0
            h.tail = first.tail if first is not None else "\n"
            d.el.insert(idx, h)
            if d.extra.get("short_head"):
                sh = etree.Element(T + "head")
                sh.set("type", "short")
                sh.set("change", "#review")
                sh.text = d.extra["short_head"]
                sh.tail = h.tail
                d.el.insert(idx + 1, sh)
    add_header(root, args.editor)
    write_tei(tree, args.out)

    if args.report:
        write_report(args.report, log, unresolved)
    print(f"wrote {args.out}: {len(log)} review decisions, "
          f"{len(unresolved)} unresolved")


def build_layout(args, tree, root, text, toks, files, cfg=None):
    """main() for a book with a LAYOUT: each file is aligned as one unit with
    the parts the layout gives it; heads are part of its text."""
    by_el = {}

    def index(ts):
        for t in ts:
            if t.kind == "container":
                by_el[t.el] = t
                index(t.children)
    index(toks)
    log, unresolved, all_splits = [], [], []
    if args.review:
        R = Path(args.review)
        order = 0
        for f in files:
            fname = f["file"]
            path = R / fname
            if not path.exists():
                unresolved.append((fname, "file", "missing from the review"))
                continue
            review = reviewparse.parse_review(path.read_text(), inline_headings=True,
                                              titled=bool(f["title"]),
                                              edition_heads=bool((cfg or {}).get("EDITION_HEADINGS")))
            title = review.headings[0] if review.headings else None
            if f["title"] and title and " ".join(title.split()) != " ".join(f["title"].split()):
                unresolved.append((fname, "file title (change it in the LAYOUT)", title))
            sub = [f["subtitle"]] if f.get("subtitle") is not None else []
            SUBTITLES.update(sub)
            view = View([by_el[p] for p in sub + f["parts"]], None)
            st, s = review_division(view, review, fname, log, unresolved)
            index_ = {}
            for k, e in enumerate(s):
                index_.setdefault(id(e[2]), order + k)
            order += len(s)
            all_splits += collect_splits(st, index_, log)
        restructure(all_splits, log)
        ROOT["toks"] = toks
        apply_list_shape(log)
        apply_edition_heads(log)
    rebuild(text, toks)
    if S.OPENING_SMALLCAPS:
        opening_smallcaps([f["parts"] for f in files], root,
                          (cfg or {}).get("SKIP_DIVISIONS", ()))
    smallcaps_phrases(root, S.SMALLCAPS_PHRASES)
    mark_diagrams(root)
    refstyle.mark_readings(text)
    add_header(root, args.editor)
    write_tei(tree, args.out)
    if args.report:
        write_report(args.report, log, unresolved)
    print(f"wrote {args.out}: {len(files)} files, {len(log)} review decisions, "
          f"{len(unresolved)} unresolved")


if __name__ == "__main__":
    main()
