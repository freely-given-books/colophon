# colophon

The book pipeline of [Freely Given Books](https://github.com/freely-given-books):
early printed texts made into modern editions that keep every decision.

```
EEBO-TCP / Evans transcription, or CCEL ThML (untouched)
        │  build_tei.py  (+ the editor's reviewed Typst chapters)
        ▼
enriched TEI: the text as printed and every editorial reading, inline
        │  tei_extract.py               │  tei_epub.py
        ▼                               ▼
Typst chapters → print PDF          EPUB 3
(checked against Lulu's rules)      (checked with epubcheck)
```

The TEI is the master. Each modernized spelling, expanded abbreviation,
reconstructed letter, moved note or emendation is a `<choice>` with the
printed form kept and `@resp` saying whether the machine or the editor
decided it, so one file yields the text as printed or the edition, and a
rebuild reproduces the edition exactly.

## Use

colophon works on a books repository laid out as
`books/<author>/<book>/source/` (the source text, `editorial.py` with the
book's settings, the TEI), `chapters/typ/` and the book's Typst files, with
the Typst templates in `typst/fgbooks-typst`. It is checked out there as
the `colophon/` submodule and run through that repository's `./fgb`:

```sh
./fgb list                # books with a TEI edition
./fgb sync gouge          # fold edits in chapters/typ into the TEI
./fgb page gouge --open   # side-by-side: printed text | edition
./fgb check gouge         # rebuild, round trips, schema, compile
./fgb build gouge         # print PDFs, covers, checked EPUB into dist/
```

`library.py` finds the books repository: `$FGB_LIBRARY`, the folder
colophon is checked out in, or the nearest folder above the current one
holding `books/`.

Requirements: [uv](https://docs.astral.sh/uv/), which keeps colophon's
Python environment (`.venv`) to the exact versions in `uv.lock`; Typst; Java
with jing and `tei_all.rng` for validation, and epubcheck, both optional.
Outside `./fgb`: `uv run --project colophon python colophon/<script>.py`.

After any change to colophon, `./fgb check --all` rebuilds every book in
parallel and must find each one as committed.

`CLAUDE.md` holds the working notes: the TEI encodings, the book settings,
every script's options, and what was learned on each book.

## License

CC0 1.0 (public domain dedication), like the books.
