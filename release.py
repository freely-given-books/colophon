"""
Book releases: which books are done, and a release of the done books that
anyone can pull and trust.

A book is done when the editor signs a version of it off: a signed git tag
<author>/<book>/v<N> on a commit whose book folder holds a RELEASE.toml
(what the edition is made from, with checksums). The tag is the sign-off;
nothing else makes a book done. A tag counts while the book's folder is as
it was tagged: after any change (a correction, a new template, a colophon
release that rewrites the TEI) the book is held back, and a release carries
its last signed version, built from the tag, until the editor signs it off
again. Books move on one at a time; none drops out of a release for it.

  ./fgb release                  every book with a RELEASE.toml or a tag:
                                 done, changed since its sign-off, or not
                                 signed off; a second line, "(Modern)", for
                                 its Modern English edition; --check also
                                 runs the gates, each edition's on its own
  ./fgb release record BOOK      write BOOK's RELEASE.toml (its source files
                                 and their checksums), to fill in and commit;
                                 for a book with a Modern English edition,
                                 with a [modern] table (added to a record
                                 that lacks one); for a print volume, the
                                 signed versions of its books (and of their
                                 Modern editions, for a volume with one)
  ./fgb release sign BOOK [N]    run the gates on BOOK, then cut the signed
                                 tag <author>/<book>/vN (the editor's step;
                                 N: one past the last version,
                                 tags or books/revisions.json)
  ./fgb release sign BOOK --point
                                 a point version, vN.1, vN.2, ...: an
                                 improved edition between Lulu revisions
  ./fgb release sign BOOK --modern [N] [--point]
                                 the same for the Modern English edition:
                                 the tag <author>/<book>/modern/vN
  ./fgb release ready BOOK       the editor calls BOOK ready to sign as it
                                 stands (the signing waits for its Lulu
                                 revision): books/publishing.toml records the
                                 date and commit, and status shows it, or
                                 that the book has changed since; --clear
                                 takes it back; --modern for the Modern
                                 English edition
  ./fgb release make             a release of every done book: the gates,
                                 then dist/release/<date>/ (PDFs, EPUBs,
                                 covers, reader and comparison pages,
                                 CATALOG.md, catalog.json,
                                 SHA256SUMS, all flat, ready to upload as
                                 a GitHub release) and a commit on the local
                                 `stable` branch, the repository with only
                                 the done books. Nothing is pushed. --trial
                                 takes unverified tags and a colophon that
                                 is not a release, and commits to
                                 `stable-trial` instead

The gates, every one of which a done book must pass:

  record    RELEASE.toml lists the sources, and their checksums match
  clean     nothing uncommitted in the book's folder
  verify    verify.py: the TEI rebuilds as committed, round trips, schema
  report    review-report.md has no edit left unapplied or unresolved
  print     the print PDFs build with nothing against Lulu's rules (a footnote
            set a page from its marker passes if RELEASE.toml's accepted_print
            lists that exact message: the editor accepted it)
  epub      the EPUB builds and passes epubcheck

Versions: a whole number vN is a print revision and matches Lulu's revision N.
A point version vN.M is an improved edition between Lulu revisions (an ebook
fix, a correction not yet sent to Lulu): its EPUBs and web pages are named
vN.M; its print stays revision N's, so a release builds the print PDFs and
covers from the vN tag and names them vN (the PDF is what Lulu has), and print
corrections made since wait for the next whole version, N+1. Its sign-off says
whether its print is still revision N's, page for page as rendered (the tag
message, the catalog).

Two editions, two releases (the editor's decision of 2026-11-17). A book
with a Modern English edition (fgb.py: EPUB["modern"], chapters/modern) is two
release units in one folder, each its own Lulu paperback, signed off and held
back on its own:

  Classic   tags <author>/<book>/vN, as before this change (the old tags and
            books/revisions.json's <author>/<book> keep counting)
  Modern    tags <author>/<book>/modern/vN, its own versions from v1 (and
            point versions vN.M), books/revisions.json id <author>/<book>/modern

Lulu sees the Modern as a book of its own: its vN is the Modern listing's Lulu
revision N, never tied to the Classic's numbers. Its next version comes only
from its own tags and revisions.json entries (a book whose Classic is at v14
signs its first Modern v1); `sign --modern N` names one (Lulu bumps a book a
revision when it is first put on sale, so a first Modern may be v2). A point
version's "print the same as vN, page for page" is checked against that
edition's own last print, so a print change in one edition never asks for a
Lulu revision of the other.

Each sign-off covers its own files and the shared ones. Which edition a file of
the folder belongs to comes from what each build reads (classifier()): the
files each edition starts from (its print and cover files, the files its EPUB
settings name, its chapters folder), and every file of the folder those name in
turn (a Typst #import/#include or image, an HTML src, a CSS url()):

  Modern    read only by the Modern build: chapters/modern/, <book>-modern.typ,
            cover-modern.typ, ebook-front-modern.html; a file read by neither,
            by its name (chapters/modern/..., "-modern", source/modern-*)
  Classic   read only by the Classic build: chapters/typ/, the Classic print
            file, ebook-front.html, the side-by-side pages' files; and source/
            (the TEI, its TCP/ThML source, supplements, witnesses, gap_fixes.py,
            outline.json, review-report.md: what the TEI is built from)
  shared    read by both, or by neither: source/editorial.py (both builds'
            settings), cover.typ (every cover-modern.typ imports it: a change
            to the Classic cover changes the Modern's), stray-notes.typ (both
            print files import it), the CSS, art/, README.md
  RELEASE.toml  its [modern] table is the Modern's, the rest the Classic's
  the TEI   the Classic's, but the Modern EPUB takes its divisions and its
            contents' headings from it: a change to those (tei_outline) holds
            the Modern back too

A change to a shared file holds back both. Comparing a Classic tag made before
this change (when it covered the Modern files too) with now ignores the Modern
files, so a book whose only changes since are the Modern's is done. A release
ships each unit that is done (or carried, built from its own tag) as its own
catalog entry with its own files; a book whose Modern is not signed off ships
its Classic alone. The comparison page (the printed text beside the edition,
from the TEI) belongs to the Classic's entry; the Modern's has its PDF, cover,
EPUB and reader page. The Modern's RELEASE.toml part:

  [modern]
  summary = "..."          # optional: the catalog's sentence or two; without
                           # it the Modern takes the book's own summary (the
                           # editor's wish: the same book, not a jarring change)
  based_on = "v2"          # the Classic version its text follows; if given, a
                           # sign-off of the Classic must exist
  accepted_print = [...]   # as the Classic's, for the Modern's print PDF

Its gates are record ([modern]), clean, print and epub, on its own files and
build; verify and report concern the TEI and are the Classic's. `ready
--modern` records it in books/publishing.toml under ["<author>/<book>/modern"]
(where its Lulu link goes too).

A print volume (a folder with a volume.toml: a paperback made of other books'
editions, fgb.py) is released like a book, with its own RELEASE.toml and signed
tag, but it is print only: its gates are record, clean and print. Its
RELEASE.toml names, as [[book]] entries, the signed version of each book it is
made from (`record` writes them, and brings them up to date when run again); it
can be signed off only when each of those is that book's newest sign-off and the
book is unchanged since, and it is held back, like a changed book, as soon as
one of its books changes after the version it names. Its versions are its own
Lulu revisions (no point versions: it has no ebook).

A print volume with a -modern print file (fgb.modern_name: owen-on-sin-modern.typ,
which includes its books' chapters/modern, and cover-modern.typ) has a Modern
English edition too, two release units as a book has: the Classic volume
(<author>/<volume>/vN, its Classic print file and cover, made from its books'
Classic sign-offs) and the Modern volume (<author>/<volume>/modern/vN,
books/revisions.json id <author>/<volume>/modern, its -modern files, made from
its books' Modern sign-offs <a>/<b>/modern/vN). Its files are whose as a book's
are (classifier(): cover.typ, which cover-modern.typ imports, and volume.toml are
shared). Its RELEASE.toml's [modern] table has a summary of its own, the
Modern volume's accepted_print, and [[modern.book]] entries that `record`
writes from each book's newest Modern sign-off:

  [modern]
  summary = "..."
  [[modern.book]]
  book = "john-owen/of-temptation"
  version = "v1"           # the tag john-owen/of-temptation/modern/v1

Each volume edition's gates (record, clean, print) build only its own print
files and cover; a change to one of its books' Modern files holds back only
the Modern volume, a Classic change only the Classic. `make` names its files as
a Modern book's (owen-on-sin-v1-modern.pdf, owen-on-sin-v1-cover-modern.pdf).

Signatures are checked against `allowed_signers` at the books repository's
root (ssh-keygen's format), so anyone can check a tag the same way:
  git -c gpg.ssh.allowedSignersFile=allowed_signers tag -v <tag>
"""

import datetime
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import tomllib
from pathlib import Path

import coverage
import fgb
import packages
import printfacts

REPO = fgb.REPO
RECORD = "RELEASE.toml"
SIGNERS = REPO / "allowed_signers"
BRANCH = "stable"
# a book's two release units (Classic, Modern English)
CLASSIC, MODERN = "classic", "modern"
# the files a book's edition is made from, beside the TCP or ThML source
SOURCE_EXTRA = ("*.supplied.xml", "*.witness.xml")


# -- git ---------------------------------------------------------------------

def git(*args, check=True):
    r = subprocess.run(["git", "-C", str(REPO), *map(str, args)],
                       capture_output=True, text=True)
    if check and r.returncode:
        sys.exit(f"git {' '.join(map(str, args))}: {r.stderr.strip()}")
    return r


def out(*args):
    return git(*args).stdout.strip()


# -- books and their sign-off ------------------------------------------------

def slug(d):
    """books/<author>/<book> -> <author>/<book>, the tag prefix."""
    return str(d.relative_to(REPO / "books"))


def unit(d, edition=CLASSIC):
    """One edition's tag prefix and books/revisions.json id: <author>/<book>
    for the Classic, <author>/<book>/modern for the Modern English."""
    return slug(d) + ("/modern" if edition == MODERN else "")


def tag_book(tag):
    """<author>/<book>/v3 or <author>/<book>/modern/v1 -> <author>/<book>."""
    return re.sub(r"(/modern)?/v[\d.]+$", "", tag)


def version_key(tag):
    return [int(x) for x in re.findall(r"\d+", tag.rsplit("/v", 1)[-1])]


def book_tags(d, edition=CLASSIC):
    """The sign-off tags of one edition of the book, newest version first."""
    tags = [t for t in out("tag", "-l", f"{unit(d, edition)}/v*").splitlines()
            if re.fullmatch(r"v\d+(\.\d+)*", t.rsplit("/", 1)[-1])]
    return sorted(tags, key=version_key, reverse=True)


def tag_info(tag):
    fmt = "%(objecttype)|%(taggername)|%(taggerdate:short)|%(contents:subject)"
    kind, who, date, subject = out("for-each-ref", f"refs/tags/{tag}",
                                   f"--format={fmt}").split("|", 3)
    body = out("for-each-ref", f"refs/tags/{tag}", "--format=%(contents:body)")
    return {"tag": tag, "annotated": kind == "tag", "signer": who, "date": date,
            "subject": subject, "note": re.sub(r"-----BEGIN.*", "", body,
                                               flags=re.S).strip(),
            "commit": out("rev-list", "-n1", tag),
            "version": tag.rsplit("/", 1)[-1]}


def signature(tag):
    """(ok, what): whether the tag is signed by someone in allowed_signers."""
    if not SIGNERS.exists():
        return False, "no allowed_signers file to check the signature against"
    r = git("-c", f"gpg.ssh.allowedSignersFile={SIGNERS}", "tag", "-v", tag,
            check=False)
    msg = (r.stdout + r.stderr).strip()
    if r.returncode == 0:
        good = next((l for l in msg.splitlines() if l.startswith("Good")), "good signature")
        return True, good
    if "no signature found" in msg:
        return False, "the tag is not signed"
    return False, "signature not verified: " + (msg.splitlines() or ["?"])[-1]


def changed_since(d, rev, edition=None):
    """Files of the book's folder that differ from rev (a tag, a commit),
    committed or not (git-ignored files aside). With an edition, of a book
    that has two, only those that hold that edition back (own_changes)."""
    rel = d.relative_to(REPO)
    files = set(out("diff", "--name-only", rev, "--", rel).splitlines())
    files.update(uncommitted(d))
    files = sorted(f for f in files if f)
    if edition is None or editions(d) == [CLASSIC]:
        return files
    return own_changes(d, edition, rev, files)


def uncommitted(d):
    """Files of the book's folder changed or added and not committed."""
    st = git("status", "--porcelain", "--", d.relative_to(REPO)).stdout
    return [l[3:] for l in st.splitlines() if l]


# -- the two editions: which files are whose ----------------------------------

def has_modern(bk):
    """The book has a Modern English edition (EPUB["modern"], or a volume's)."""
    e = bk.cfg.get("EPUB") or {}
    return bool(e.get("modern") or any(v.get("modern") for v in e.get("volumes", [])))


def volume_has_modern(bk):
    """A print volume has a Modern English edition: a -modern print file
    (fgb.modern_name: <volume>-modern.typ, made from its books' chapters/modern)."""
    return any(fgb.modern_name(f) for f in bk.cfg.get("PRINT") or [bk.dir.name + ".typ"])


def editions(d):
    """A book folder's release units: the Classic, and the Modern English when
    the book has one (or one was signed off). A print volume likewise: its
    Modern when it has a -modern print file (or one was signed off)."""
    bk = fgb.Book(d)
    has = volume_has_modern(bk) if bk.volume is not None else has_modern(bk)
    return [CLASSIC, MODERN] if has or book_tags(d, MODERN) else [CLASSIC]


def edition_title(bk, edition):
    if edition != MODERN:
        return bk.title
    m = ((bk.volume or {}).get("modern") if bk.volume is not None
         else (bk.cfg.get("EPUB") or {}).get("modern")) or {}
    return m.get("title") or f"{bk.title} (Modern English)"


# the paths a print, cover or ebook file names, by its kind: a Typst string
# ("cover.typ", "art/plate.jpg"), an HTML src or href, a CSS url(); comments
# (a Typst // line or tail, an HTML <!-- -->) are left out first
REFERENCES = {
    ".typ": (re.compile(r"(?m)(^|\s)//.*$"), re.compile(r'"([^"\n]{1,200}?\.[A-Za-z0-9]{1,5})"')),
    ".html": (re.compile(r"<!--.*?-->", re.S), re.compile(r'(?:src|href)="([^"]+)"')),
    ".css": (re.compile(r"/\*.*?\*/", re.S), re.compile(r"url\(\s*['\"]?([^'\")]+)")),
}
REFERENCES[".xhtml"] = REFERENCES[".html"]
# the settings of an EPUB entry that name files of the book
EPUB_FILES = ("front", "cover", "css", "before", "after", "chapters")


def references(p, d):
    """The files of the book folder d that the file p names (a Typst #import,
    #include or image, an HTML src, a CSS url())."""
    if p.suffix not in REFERENCES:
        return []
    comment, path = REFERENCES[p.suffix]
    text = comment.sub(" ", p.read_text(encoding="utf-8", errors="replace"))
    found = []
    for m in path.finditer(text):
        try:
            q = (p.parent / m.group(1)).resolve()
            if q.is_file() and q.is_relative_to(d):
                found.append(q)
        except (OSError, ValueError):
            continue
    return found


def reads(d, start):
    """Every file of the book folder that a build starting from `start` (paths
    in the folder; a folder stands for all its files) reads, as paths in the
    folder: the files themselves and whatever they name, in turn."""
    d = d.resolve()
    todo = []
    for f in start:
        p = (d / f).resolve()
        todo += sorted(x for x in p.rglob("*") if x.is_file()) if p.is_dir() else [p]
    seen = set()
    while todo:
        p = todo.pop()
        if p in seen or not p.is_file() or not p.is_relative_to(d):
            continue
        seen.add(p)
        todo += references(p, d)
    return {p.relative_to(d).as_posix() for p in seen}


def edition_inputs(bk):
    """(classic, modern): the files each edition's build starts from: its print
    and cover files, the files its EPUB settings name (fgb.build_epub's), its
    chapters (and the Classic's side-by-side pages)."""
    e = bk.cfg.get("EPUB") or {}
    base = {k: x for k, x in e.items() if k not in ("modern", "volumes")}
    if e.get("volumes"):
        classic = [{**base, **{k: x for k, x in v.items() if k != "modern"}}
                   for v in e["volumes"]]
        modern = [{**c, **v["modern"]} for c, v in zip(classic, e["volumes"])
                  if v.get("modern")]
    else:
        classic = [base]
        modern = [{**base, **e["modern"]}] if e.get("modern") else []
    named = lambda cfgs: [f for c in cfgs for k in EPUB_FILES
                          for f in ([c[k]] if isinstance(c.get(k), str) else c.get(k) or [])]
    files = (bk.cfg.get("PRINT") or [bk.dir.name + ".typ"]) + \
        (bk.cfg.get("COVERS") or sorted(p.name for p in bk.dir.glob("cover*.typ")))
    side = bk.cfg.get("SIDE_BY_SIDE", {})
    return ([f for f in files if not fgb.modern_name(f)] + named(classic) + ["chapters/typ"]
            + side.get("before", []) + side.get("after", []),
            [f for f in files if fgb.modern_name(f)] + named(modern) + ["chapters/modern"])


def classifier(d, bk=None):
    """which(path in the folder): the edition a file belongs to, CLASSIC or
    MODERN for a file only that edition's build reads, None for a shared one
    (both read it, or neither). A file neither build reads (or one gone) goes
    by its name: chapters/modern/ and "-modern" names the Modern's,
    chapters/typ/ and source/ (what the TEI is built from) the Classic's.
    editorial.py and RELEASE.toml are shared (own_changes looks into the
    record)."""
    c_in, m_in = edition_inputs(bk or fgb.Book(d))
    c, m = reads(d, c_in), reads(d, m_in)

    def which(rel):
        if rel in (RECORD, "source/editorial.py"):
            return None
        if rel in m or rel in c:
            return None if rel in m and rel in c else MODERN if rel in m else CLASSIC
        if rel.startswith("chapters/modern/") or \
                re.search(r"(^|[-_])modern([-_.]|$)", rel.rsplit("/", 1)[-1]):
            return MODERN
        if rel.startswith(("chapters/typ/", "source/")):
            return CLASSIC
        return None
    return which


def blob(rev, path):
    """A file's bytes at rev (None: not there); rev None: as it is on disk."""
    if rev is None:
        p = REPO / path
        return p.read_bytes() if p.is_file() else None
    r = subprocess.run(["git", "-C", str(REPO), "show", f"{rev}:{path}"], capture_output=True)
    return r.stdout if r.returncode == 0 else None


def record_part(data, edition):
    """One edition's part of a RELEASE.toml: [modern] for the Modern, the rest
    for the Classic (an unreadable record as its bytes: it differs)."""
    if data is None:
        return None
    try:
        rec = tomllib.loads(data.decode("utf-8"))
    except (UnicodeDecodeError, tomllib.TOMLDecodeError):
        return data
    return rec.get("modern") if edition == MODERN else \
        {k: v for k, v in rec.items() if k != "modern"}


def tei_outline(data):
    """A TEI's divisions and headings, in order: what the Modern EPUB takes
    from it (tei_epub.py --chapters: its pages and its contents)."""
    from lxml import etree
    try:
        root = etree.fromstring(data)
    except etree.XMLSyntaxError:
        return data
    found = []
    for el in root.iter(etree.Element):
        name = etree.QName(el).localname
        if name in ("div", "head") or (name == "label" and el.get("type") == "head"):
            found.append((name, el.get("type"), el.get("n"),
                          el.get("{http://www.w3.org/XML/1998/namespace}id"),
                          "" if name == "div" else " ".join("".join(el.itertext()).split())))
    return found


def own_changes(d, edition, rev, files):
    """Of files changed in the book's folder since rev (repository paths; rev
    None: uncommitted ones), those that hold this edition back: its own and
    the shared ones. RELEASE.toml counts for an edition when its part changed;
    the TEI, the Classic's, for the Modern too when its divisions or headings
    changed."""
    bk = fgb.Book(d)
    which = classifier(d, bk)
    base = d.relative_to(REPO).as_posix() + "/"
    tei = bk.tei.relative_to(d).as_posix()
    kept = []
    for f in files:
        rel = f[len(base):] if f.startswith(base) else f
        if rel == RECORD and rev is not None:
            hit = record_part(blob(rev, f), edition) != record_part(blob(None, f), edition)
        elif rel == tei and edition == MODERN:
            hit = rev is None or tei_outline(blob(rev, f) or b"") != \
                tei_outline(blob(None, f) or b"")
        else:
            hit = which(rel) in (None, edition)
        if hit:
            kept.append(f)
    return kept


def volume_books(rec, edition=CLASSIC):
    """The [[book]] entries of one edition of a print volume's RELEASE.toml:
    the Classic's at the top level, the Modern's in its [modern] table
    ([[modern.book]])."""
    part = modern_record(rec) if edition == MODERN else (rec or {})
    books = part.get("book", [])
    return [x for x in books if isinstance(x, dict)] if isinstance(books, list) else []


def made_from(s):
    """A print volume's books as its RELEASE.toml names them, for one of its
    editions: per book its sign-off tag there (the book's Classic tag
    <a>/<b>/vN for the Classic volume, its Modern tag <a>/<b>/modern/vN for the
    Modern), whether that tag exists, and that edition's files of the book
    changed since it (committed or not)."""
    edition = s.get("edition", CLASSIC)
    out_ = []
    for x in volume_books(s["record"], edition):
        b, v = x.get("book", ""), x.get("version", "")
        tag = f"{b}{'/modern' if edition == MODERN else ''}/{v}"
        exists = bool(b and v) and git("rev-parse", "-q", "--verify", f"refs/tags/{tag}",
                                       check=False).returncode == 0
        d = REPO / "books" / b
        # each volume prints one edition of its books: the other's files don't count
        out_.append({"book": b, "version": v, "tag": tag, "exists": exists,
                     "edition": edition,
                     "changed": changed_since(d, tag, edition)
                     if exists and d.is_dir() else []})
    return out_


def state(d, edition=CLASSIC):
    """Where one edition of a book stands: its record, its latest sign-off and
    whether that still holds. A print volume's sign-off also holds only while
    the books it is made from are as its record names them."""
    eds = editions(d)
    s = {"dir": d, "slug": slug(d), "edition": edition, "unit": unit(d, edition),
         "name": slug(d) + (" (Modern)" if edition == MODERN else ""),
         # what to build for this edition: its files only, for a book with two
         "build": edition if len(eds) > 1 else None,
         "record": None, "problems": [], "done": False,
         "volume": (d / fgb.VOLUME).exists()}
    rec = d / RECORD
    if rec.exists():
        try:
            s["record"] = tomllib.loads(rec.read_text(encoding="utf-8"))
        except tomllib.TOMLDecodeError as e:
            s["problems"].append(f"{RECORD}: {e}")
    if s["volume"]:
        s["made_from"] = made_from(s)
    tags = book_tags(d, edition)
    s["tags"] = tags
    if not tags:
        return s
    t = s["tag"] = tag_info(tags[0])
    if not t["annotated"]:
        s["problems"].append(f"{tags[0]} is a lightweight tag; a sign-off is a signed tag")
    s["signed"], s["signature"] = signature(tags[0])
    if git("merge-base", "--is-ancestor", t["commit"], "HEAD", check=False).returncode:
        s["problems"].append(f"{tags[0]} is not in this branch's history")
    s["changed"] = changed_since(d, tags[0], s["build"])
    if s["volume"]:
        # a book of the volume changed since the version it was made from: the
        # volume as signed off is no longer what its books would make now.
        # (Its record is the one at HEAD; a changed record changes the folder.)
        for m in s["made_from"]:
            s["changed"] += m["changed"]
            if not m["exists"]:
                s["problems"].append(f"{RECORD}: no sign-off {m['tag']}")
    # done: signed off by an allowed signer and unchanged since; a sign-off
    # that holds but whose signature is not verified is only taken by --trial
    s["holds"] = not s["changed"] and not s["problems"]
    s["done"] = s["holds"] and s["signed"]
    return s


# -- the gates ----------------------------------------------------------------

def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def gate_record(s, trial=False):
    rec = s["record"]
    if rec is None:
        return [f"no {RECORD} (./fgb release record {s['slug']})"]
    if s.get("volume"):
        return gate_volume_record(s, trial)
    if s.get("edition") == MODERN:
        return gate_modern_record(s)
    bad = []
    srcs = rec.get("source", [])
    if not srcs:
        bad.append(f"{RECORD} lists no [[source]]")
    for x in srcs:
        p = s["dir"] / x.get("file", "")
        if not x.get("file") or not p.is_file():
            bad.append(f"source {x.get('file')!r} is not in the book's folder")
        elif x.get("sha256") != sha256(p):
            bad.append(f"{x['file']}: checksum differs from {RECORD}")
        if not x.get("description"):
            bad.append(f"{x.get('file')}: no description in {RECORD}")
    return bad


def modern_record(rec):
    """A RELEASE.toml's [modern] table ({} when it has none)."""
    m = (rec or {}).get("modern")
    return m if isinstance(m, dict) else {}


def gate_modern_record(s):
    """The Modern English edition's part of RELEASE.toml, its [modern] table:
    based_on, the Classic version its text follows, if given, a sign-off of the
    Classic; a summary of its own only if it should differ from the book's."""
    m = s["record"].get("modern")
    if not isinstance(m, dict):
        return [f"no [modern] table in {RECORD} (./fgb release record {s['slug']} adds one)"]
    bad = []
    v = m.get("based_on")
    if v and git("rev-parse", "-q", "--verify", f"refs/tags/{s['slug']}/{v}",
                 check=False).returncode:
        bad.append(f"{RECORD} [modern] based_on: no sign-off {s['slug']}/{v}")
    return bad


def gate_volume_record(s, trial=False):
    """A print volume's record: the books of its volume.toml, in order, each at
    a version that is that book's newest sign-off, unchanged since and (but
    for a trial) signed by an allowed signer; its print files include nothing
    of any other book. The Modern volume's: its [modern] table, with a summary
    of its own and its books at their newest Modern sign-offs."""
    bk = fgb.Book(s["dir"])
    edition = s.get("edition", CLASSIC)
    bad = list(fgb.volume_problems(s["dir"]))
    if edition == MODERN:
        if not isinstance(s["record"].get("modern"), dict):
            return bad + [f"no [modern] table in {RECORD} (./fgb release record "
                          f"{s['slug']} adds one)"]
        if not modern_record(s["record"]).get("summary"):
            bad.append(f"no summary in {RECORD} [modern]")
    elif not s["record"].get("summary"):
        bad.append(f"no summary in {RECORD}")
    named = [m["book"] for m in s["made_from"]]
    if named != bk.parts():
        bad.append(f"{RECORD} names {', '.join(named) or 'no book'}; {fgb.VOLUME} has "
                   f"{', '.join(bk.parts())} (./fgb release record {s['slug']})")
    for m in s["made_from"]:
        if not m["exists"]:
            what = f"no sign-off {m['tag']}" if m["version"] or edition != MODERN else \
                "its Modern English edition is not signed off"
            bad.append(f"{m['book']}: {what} (./fgb release record "
                       f"{s['slug']} names each book's newest)")
            continue
        b = state(REPO / "books" / m["book"], edition)
        if b["tags"][0] != m["tag"]:
            bad.append(f"{m['book']}: made from {m['version']}, but its newest sign-off "
                       f"is {b['tag']['version']} (./fgb release record {s['slug']})")
        elif m["changed"]:
            bad.append(f"{m['book']}: {len(m['changed'])} file(s) changed since "
                       f"{m['version']}; sign it off again first")
        elif not (b["done"] or (trial and b["holds"])):
            bad.append(f"{m['book']} {m['version']}: " +
                       ("; ".join(b["problems"]) or b["signature"]))
    return bad


def gate_report(d):
    report = d / "source" / "review-report.md"
    entries, _counts = fgb.report_entries(report)
    left = entries.get("not applied", []) + entries.get("unresolved", [])
    return [f"review-report.md: {len(left)} edit(s) not applied or unresolved"] if left else []


def gate_verify(d):
    r = subprocess.run([fgb.PY, str(fgb.HERE / "verify.py"), str(d)],
                       capture_output=True, text=True)
    if r.returncode == 0:
        return []
    failed = [l for l in r.stdout.splitlines() if l.startswith("[")
              and (l.endswith("False") or "FAILED" in l or "differs" in l)]
    return ["verify.py failed: " + ("; ".join(failed) or (r.stdout + r.stderr)[-300:])]


def gate_builds(bk, outdir, edition=None):
    """Build the print PDFs, covers and EPUB(s) into outdir, of one edition
    or (None) both. (files, problems)"""
    problems, files = [], []
    try:
        files += fgb.build_pdf(bk, outdir, covers=True, problems=problems, edition=edition)
    except SystemExit as e:
        return files, [f"print build failed: {e}"]
    try:
        files += fgb.build_epub(bk, outdir, edition=edition)
    except SystemExit as e:
        return files, problems + [f"EPUB build failed: {e}"]
    return files, problems


def run_gates(s, outdir, log=print, trial=False):
    """Every gate on one edition of a book; (built files, {gate: [problems]}).
    A print volume's: record, clean and print (it has no TEI or ebook of its
    own), each of its editions on its own print files. A Modern English edition's: record, clean, print and epub, on its
    own files and build (verify and report are the TEI's: the Classic's)."""
    d = s["dir"]
    modern = s.get("edition") == MODERN
    res = {"record": gate_record(s, trial), "clean": []}
    if not s.get("volume") and not modern:
        res["report"] = gate_report(d)
    dirty = uncommitted(d)
    if s.get("build"):
        dirty = own_changes(d, s["edition"], None, dirty)
    if dirty:
        res["clean"] = [f"uncommitted: {', '.join(dirty[:5])}" +
                        (f" and {len(dirty) - 5} more" if len(dirty) > 5 else "")]
    if s.get("volume"):
        log("  building ...")
        problems = []
        try:
            files = fgb.build_pdf(fgb.Book(d), outdir, covers=True, problems=problems,
                                  edition=s.get("build"))
        except SystemExit as e:
            files, problems = [], [f"print build failed: {e}"]
        rec = s["record"] or {}
        accepted = set((modern_record(rec) if modern else rec).get("accepted_print", []))
        res["_accepted"] = [p for p in problems if p in accepted and " footnote " in p]
        res["print"] = [p for p in problems if p not in res["_accepted"]]
        return files, res
    if not modern:
        log("  verify.py ...")
        res["verify"] = gate_verify(d)
    log("  building ...")
    files, built = gate_builds(fgb.Book(d), outdir, s.get("build"))
    res["print"] = [p for p in built if "EPUB" not in p]
    # footnotes set a page from their marker (a Typst limitation, not a Lulu
    # rule) that the editor has accepted, each by its message, in RELEASE.toml
    # ("accepted_print"); any other, or a new one, still fails the gate
    rec = s["record"] or {}
    accepted = set((modern_record(rec) if modern else rec).get("accepted_print", []))
    res["_accepted"] = [p for p in res["print"] if p in accepted and " footnote " in p]
    res["print"] = [p for p in res["print"] if p not in res["_accepted"]]
    res["epub"] = [p for p in built if "EPUB" in p]
    return files, res


def show_gates(res):
    for gate, problems in res.items():
        if gate.startswith("_"):
            continue
        extra = (f" ({len(res['_accepted'])} stray footnote(s) accepted in {RECORD})"
                 if gate == "print" and res.get("_accepted") else "")
        print(f"    {'ok  ' if not problems else 'FAIL'} {gate}{extra}")
        for p in problems:
            print(f"           {p}")


# -- commands -------------------------------------------------------------------

def candidates():
    return [d for d in fgb.book_dirs()
            if (d / RECORD).exists() or book_tags(d) or book_tags(d, MODERN)]


def units():
    """Every release unit: each candidate book's Classic, and its Modern."""
    return [state(d, ed) for d in candidates() for ed in editions(d)]


PUBLISHING = REPO / "books" / "publishing.toml"


def ready_of(s):
    """{"date", "commit"} when the editor has called this edition ready to
    sign (books/publishing.toml, under its unit: <author>/<book>[/modern])."""
    if not PUBLISHING.exists():
        return None
    r = tomllib.loads(PUBLISHING.read_text(encoding="utf-8")).get(s["unit"], {}).get("ready")
    return r if isinstance(r, dict) and r.get("commit") else None


def ready_note(s):
    r = ready_of(s)
    if not r:
        return ""
    same = not changed_since(s["dir"], r["commit"], s["build"])
    return (f"; ready to sign since {r['date']} ({r['commit']})" if same else
            f"; called ready {r['date']} ({r['commit']}), but changed since")


def edition_of(a, d):
    """The edition a command names: --modern, for a book that has one."""
    if not getattr(a, "modern", False):
        return CLASSIC
    if MODERN not in editions(d):
        sys.exit(f"{slug(d)} has no Modern English edition " +
                 ("(a -modern print file in volume.toml's print)" if (d / fgb.VOLUME).exists()
                  else "(EPUB[\"modern\"] in editorial.py)"))
    return MODERN


def cmd_ready(a):
    """Record (or with --clear take back) the editor's "ready to sign"."""
    d = fgb.find_book(a.book)
    s = state(d, edition_of(a, d))
    key = s["unit"]
    dirty = uncommitted(d)
    if s["build"]:
        dirty = own_changes(d, s["edition"], None, dirty)
    if not a.clear and dirty:
        sys.exit(f"{key}: uncommitted changes in its folder; commit them first, so "
                 "\"ready\" names the book as it stands")
    head = f'["{key}"]'
    lines = PUBLISHING.read_text(encoding="utf-8").split("\n") if PUBLISHING.exists() else []
    if head not in lines:
        if a.clear:
            print(f"{key}: not marked ready")
            return 0
        while lines and not lines[-1].strip():
            lines.pop()
        lines += ["", head]
    i = lines.index(head) + 1
    while i < len(lines) and not lines[i].startswith("["):
        if lines[i].startswith("ready ="):
            del lines[i]
            continue
        i += 1
    if not a.clear:
        commit = git("rev-parse", "--short", "HEAD").stdout.strip()
        lines.insert(lines.index(head) + 1, f'ready = {{ date = "{datetime.date.today()}", '
                     f'commit = "{commit}" }}')
    PUBLISHING.write_text("\n".join(lines).rstrip("\n") + "\n", encoding="utf-8")
    print(f"{key}: " + ("no longer marked ready" if a.clear else
                        f"ready to sign, as it stands at {commit}") +
          f" ({PUBLISHING.relative_to(REPO)}; commit it)")
    return 0


def cmd_status(a):
    books = candidates()
    if not books:
        print(f"no book has a {RECORD} or a sign-off tag yet "
              "(./fgb release record BOOK to start one)")
        return 0
    gh = os.environ.get("GITHUB_ACTIONS") == "true"
    for s in (state(d, ed) for d in books for ed in editions(d)):
        t = s.get("tag")
        if s["done"]:
            what = f"done      {t['version']}, signed off {t['date']} by {t['signer']}"
        elif t and s["holds"]:
            what = f"held back {t['version']} signed off {t['date']}, but {s['signature']}"
        elif t and s["changed"]:
            what = (f"held back {t['version']} signed off {t['date']}, but "
                    f"{len(s['changed'])} file(s) changed since")
        elif t:
            what = f"held back {t['version']}: " + "; ".join(s["problems"])
        else:
            what = "not signed off"
        if not s["done"]:
            what += ready_note(s)
        print(f"  {s['name']:58} {what}")
        for m in s.get("made_from", []):
            print(f"      made from {m['book']} "
                  f"{'Modern ' if m['edition'] == MODERN else ''}{m['version'] or '?'}" +
                  (f": {len(m['changed'])} file(s) changed since" if m["changed"] else
                   "" if m["exists"] else ": no such sign-off"))
        for f in s.get("changed", [])[:8]:
            print(f"      changed: {f}")
        if gh and t and s.get("changed"):
            print(f"::warning::{s['name']} changed since its sign-off "
                  f"({t['tag']}); the next release carries its signed version until it "
                  "is signed off again")
        bad = gate_record(s)
        for p in bad:
            print(f"      {p}")
        if a.check:
            with tempfile.TemporaryDirectory(prefix="fgb-release-") as tmp:
                _files, res = run_gates(s, Path(tmp), log=lambda *_: None)
            show_gates(res)
    return 0


VOLUME_BOOKS = "# The signed versions of the books this volume is made from"
# the Modern English volume's part of its record: its [modern] table (kept as
# edited), then its books' Modern versions, which `record` writes again
VOLUME_MODERN = "# The Modern English edition of this volume"
VOLUME_MODERN_BOOKS = "# The signed Modern English versions of the books it is made from"


def volume_modern_head(d):
    """The start of a print volume's [modern] table, as `record` first writes it."""
    return "\n".join([
        VOLUME_MODERN + ": a paperback of its own, made from the",
        "# books' Modern English editions (its -modern print file), signed off on its own",
        f"# ({unit(d, MODERN)}/vN: ./fgb release sign {slug(d)} --modern), with its",
        "# own Lulu revisions. A change to this table holds back only it.",
        "[modern]",
        "# One or two sentences for the release catalog: the Modern English volume, its books.",
        'summary = ""',
        "# Stray footnotes in its print PDF the editor accepts, each by its message:",
        "# accepted_print = []",
        "", ""])


def volume_book_lines(d, edition, before, label=""):
    """One edition's [[book]] (or [[modern.book]]) entries of a print volume's
    record: each book at its newest sign-off of that edition; says each."""
    bk = fgb.Book(d)
    q = lambda v: json.dumps(v, ensure_ascii=False)
    table = "[[modern.book]]" if edition == MODERN else "[[book]]"
    lines = []
    for b in bk.parts():
        tags = book_tags(REPO / "books" / b, edition)
        v = tags[0].rsplit("/", 1)[-1] if tags else ""
        lines += [table, f"book = {q(b)}", f"version = {q(v)}", ""]
        s = state(REPO / "books" / b, edition)
        was = f" (was {before[b]})" if before.get(b, v) != v else ""
        print(f"  {label}{b}: {v or 'not signed off'}{was}" +
              ("" if not tags else
               f"; but {len(s['changed'])} file(s) changed since: sign it off again, "
               "then record again" if s["changed"] else ""))
    return lines


def record_volume(d):
    """A print volume's RELEASE.toml: written, or its [[book]] entries brought
    up to date (each book's newest sign-off), the rest kept as edited. A
    volume with a Modern English edition also gets a [modern] table, its
    [[modern.book]] entries each book's newest Modern sign-off (the table's
    head, above them, kept as edited)."""
    bk = fgb.Book(d)
    path = d / RECORD
    modern = MODERN in editions(d)
    modern_head, before_m = None, {}
    if path.exists():
        text = path.read_text(encoding="utf-8")
        if VOLUME_BOOKS not in text:
            sys.exit(f"{path.relative_to(REPO)}: no \"{VOLUME_BOOKS}\" line to write the "
                     "books' versions after; edit it by hand")
        rec = tomllib.loads(text)
        head = text[:text.index(VOLUME_BOOKS)]
        rest = text[text.index(VOLUME_BOOKS):]
        before = {m["book"]: m["version"] for m in made_from({"record": rec})}
        if VOLUME_MODERN in rest:
            if VOLUME_MODERN_BOOKS not in rest:
                sys.exit(f"{path.relative_to(REPO)}: no \"{VOLUME_MODERN_BOOKS}\" line to "
                         "write the books' Modern versions after; edit it by hand")
            modern = True
            modern_head = rest[rest.index(VOLUME_MODERN):rest.index(VOLUME_MODERN_BOOKS)]
            before_m = {m["book"]: m["version"]
                        for m in made_from({"record": rec, "edition": MODERN})}
        elif "modern" in rec:
            sys.exit(f"{path.relative_to(REPO)}: a [modern] table without the "
                     f"\"{VOLUME_MODERN}\" line; edit it by hand")
    else:
        head = "\n".join([
            f"# Release record of {bk.title}: a print volume made of the editions of",
            f"# other books ({fgb.VOLUME}). ./fgb release checks it; the editor signs a",
            f"# version off with a signed tag, {slug(d)}/vN (./fgb release sign).",
            "",
            "# One or two sentences for the release catalog: the volume, its books.",
            'summary = ""',
            "", ""])
        before = {}
    label = lambda s: s if modern else ""
    lines = [VOLUME_BOOKS + ", each",
             f"# one's newest sign-off: ./fgb release record {slug(d)} writes them again",
             "# after a book is signed off again (then sign the volume off again).", ""]
    lines += volume_book_lines(d, CLASSIC, before, label("Classic: "))
    text = head + "\n".join(lines)
    added = modern and modern_head is None
    if modern:
        lines = [VOLUME_MODERN_BOOKS + ",",
                 "# each one's newest Modern sign-off (<author>/<book>/modern/vN), written",
                 "# by ./fgb release record as for the Classic's above.", ""]
        lines += volume_book_lines(d, MODERN, before_m, label("Modern:  "))
        text += "\n" + (modern_head or volume_modern_head(d)) + "\n".join(lines)
    path.write_text(text, encoding="utf-8")
    print(f"wrote {path.relative_to(REPO)}" +
          ("" if before else ": fill in the summary, then commit it") +
          ("; added a [modern] table: fill in its summary" if added and before else ""))


def modern_table(d):
    """The [modern] table a record starts with: the Modern English edition's
    part of RELEASE.toml (gate_modern_record)."""
    tags = book_tags(d)
    v = tags[0].rsplit("/", 1)[-1] if tags else ""
    return [
        "# The Modern English edition: a paperback and ebook of its own, signed off",
        f"# on its own ({unit(d, MODERN)}/vN: ./fgb release sign BOOK --modern), with",
        "# its own Lulu revisions. A change to this table holds back only it.",
        "[modern]",
        "# The catalog uses the book's summary above; give the Modern its own only if needed:",
        '# summary = ""',
        "# The Classic version whose text it follows.",
        f"based_on = {json.dumps(v)}",
        "# Stray footnotes in its print PDF the editor accepts, each by its message:",
        "# accepted_print = []",
        ""]


def cmd_record(a):
    d = fgb.find_book(a.book, volumes_too=True)
    if (d / fgb.VOLUME).exists():
        return record_volume(d)
    path = d / RECORD
    modern = MODERN in editions(d)
    if path.exists():
        text = path.read_text(encoding="utf-8")
        if modern and "modern" not in tomllib.loads(text):
            # a table goes at the end, after every other one
            path.write_text(text.rstrip("\n") + "\n\n" + "\n".join(modern_table(d)),
                            encoding="utf-8")
            print(f"{path.relative_to(REPO)}: added a [modern] table for the Modern English "
                  "edition; check based_on, then commit it")
            return
        sys.exit(f"{path.relative_to(REPO)} exists; edit it by hand (a source's "
                 "checksum should never change: the sources are kept untouched)")
    bk = fgb.Book(d)
    files = [bk.tcp] if bk.tcp else []
    for pat in SOURCE_EXTRA:
        files += sorted(bk.src.glob(pat))
    files = [f for f in files if not git("check-ignore", "-q", f, check=False).returncode == 0]
    if not files:
        sys.exit(f"{slug(d)}: no source file found in source/")
    q = lambda v: json.dumps(v, ensure_ascii=False)
    lines = [
        f"# Release record of {bk.cfg.get('EPUB', {}).get('title', d.name)}: what this",
        "# edition is made from. ./fgb release checks it; the editor signs a version",
        f"# off with a signed tag, {slug(d)}/vN (./fgb release sign).",
        "",
        "# One or two sentences for the release catalog: the edition, its source.",
        'summary = ""',
        "",
    ]
    for f in files:
        rel = f.relative_to(d).as_posix()
        m = re.match(r"([AN]\d{5})\.tcp\.xml$", f.name)
        lines += ["[[source]]", f"file = {q(rel)}",
                  "description = " + q("EEBO-TCP " + m.group(1) if m else ""),
                  "url = " + q(f"https://github.com/textcreationpartnership/{m.group(1)}"
                               if m else ""),
                  f"sha256 = {q(sha256(f))}", ""]
    lines += ["# Copies the edition was checked against, kept or not (one per witness):",
              "# [[witness]]", '# description = ""', '# url = ""', ""]
    if modern:
        lines += modern_table(d)
    path.write_text("\n".join(lines), encoding="utf-8")
    print(f"wrote {path.relative_to(REPO)}: fill in the descriptions and the "
          "summary, then commit it")


REVISIONS = REPO / "books" / "revisions.json"


def revisions():
    """books/revisions.json: every release and the book versions in it, by
    unit: <author>/<book> for the Classic, <author>/<book>/modern for the Modern
    ({"releases": [{"release": "2026.03.16", "books": {"<author>/<book>": 2}}]})."""
    if REVISIONS.exists():
        return json.loads(REVISIONS.read_text(encoding="utf-8"))
    return {"releases": []}


def record_release(rid, done):
    """Add (or replace) this release in books/revisions.json; its text."""
    data = revisions()
    # a whole version as a number (Lulu's revision), a point version as "13.1"
    books = {s["unit"]: (lambda v: v[0] if len(v) == 1 else ".".join(map(str, v)))(
        version_key(s["tag"]["tag"])) for s in done}
    data["releases"] = [r for r in data["releases"] if r["release"] != rid] + \
        [{"release": rid, "books": books}]
    text = json.dumps(data, indent=2, ensure_ascii=False) + "\n"
    REVISIONS.write_text(text, encoding="utf-8")
    return text


def last_version(d, edition=CLASSIC):
    """The last version of one edition of the book: the higher of its newest
    tag and the highest in books/revisions.json under its own id (the Lulu
    revisions published before sign-off tags, which a tag from a withdrawn
    release can lag behind). Each edition counts its own: the Modern is a
    Lulu book of its own."""
    tags = book_tags(d, edition)
    tagged = version_key(tags[0])[0] if tags else 0
    return max([tagged] + [int(str(r["books"].get(unit(d, edition), 0)).split(".")[0])
                           for r in revisions()["releases"]])


def is_point(version):
    """v13.1: a point version, between Lulu revisions 13 and 14."""
    return "." in version.lstrip("v")


def print_version(version):
    """The print revision of a version: v13.1 -> v13."""
    return "v" + version.lstrip("v").split(".")[0]


def next_point(d, edition=CLASSIC):
    """The next point version of an edition: vN.(M+1) after its newest
    sign-off vN(.M)."""
    tags = book_tags(d, edition)
    name = unit(d, edition)
    if not tags:
        sys.exit(f"{name} has no sign-off: a point version follows one")
    n = version_key(tags[0])
    if n[0] < last_version(d, edition):
        sys.exit(f"{name}: revision {last_version(d, edition)} (books/revisions.json) is "
                 f"newer than its last sign-off, {tags[0]}; sign off a print revision")
    return f"{n[0]}.{(n[1] if len(n) > 1 else 0) + 1}"


def build_at(tag, outdir, epub=False, then=None, edition=None):
    """Build the book as it was at a sign-off (a checkout of the tag, with
    this colophon; the templates it imports from the cache): its print PDFs
    and covers, and with epub its EPUB(s); of one edition, or (None) all.
    then(bk, files) runs before the checkout goes (the web pages, the catalog
    entry); its result is returned with the files."""
    book = Path("books") / tag_book(tag)
    outdir.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="fgb-signed-") as tmp:
        wt = Path(tmp) / "repo"
        git("worktree", "add", "-q", "--detach", str(wt), tag)
        try:
            typ = git("-C", str(wt), "grep", "-h", "-o", "-E", packages.IMPORT_RE,
                      "--", "books/*.typ", check=False).stdout
            for m in sorted(set(typ.split())):
                packages.ensure(*m[len("@local/"):].split(":"))
            bk = fgb.Book(wt / book)
            files = fgb.build_pdf(bk, outdir, covers=True, root=wt, edition=edition)
            if epub and not bk.volume:
                files += fgb.build_epub(bk, outdir, root=wt, edition=edition)
            return files, (then(bk, files) if then else None)
        finally:
            git("worktree", "remove", "--force", str(wt), check=False)


def print_at(tag, outdir, edition=None):
    """The book's print PDFs and covers as they were at a sign-off (of one
    edition, or None: all)."""
    return build_at(tag, outdir, edition=edition)[0]


def page_images(pdf, outdir):
    """Each page of a PDF as rendered (72 ppi, grey), in page order."""
    outdir.mkdir(parents=True)
    subprocess.run(["pdftoppm", "-r", "72", "-gray", str(pdf), str(outdir / "p")],
                   check=True)
    return sorted(outdir.iterdir(), key=lambda p: int(re.findall(r"\d+", p.stem)[-1]))


def print_differences(old, new, tmp):
    """How the print PDFs and covers built now differ from those built at a
    sign-off ([] when the same page for page): file by file, the page count
    and each page's rendering. Said in a point version's sign-off."""
    old = {f.name: f for f in old if f.suffix == ".pdf"}
    new = {f.name: f for f in new if f.suffix == ".pdf"}
    bad = [f"{n}: only at the sign-off" for n in sorted(old.keys() - new.keys())]
    bad += [f"{n}: new since the sign-off" for n in sorted(new.keys() - old.keys())]
    for n in sorted(old.keys() & new.keys()):
        a = page_images(old[n], tmp / "old" / n)
        b = page_images(new[n], tmp / "new" / n)
        if len(a) != len(b):
            bad.append(f"{n}: {len(a)} pages at the sign-off, {len(b)} now")
            continue
        pages = [i + 1 for i, (x, y) in enumerate(zip(a, b)) if sha256(x) != sha256(y)]
        if pages:
            bad.append(f"{n}: {len(pages)} page(s) differ: "
                       + ", ".join(map(str, pages[:12])) + (" ..." if len(pages) > 12 else ""))
    return bad


def cmd_sign(a):
    d = fgb.find_book(a.book, volumes_too=True)
    edition = edition_of(a, d)
    s = state(d, edition)
    if a.point and a.version:
        sys.exit("give a version or --point, not both")
    if s["volume"] and (a.point or is_point(a.version or "")):
        sys.exit(f"{slug(d)} is a print volume: no point versions (it has no ebook)")
    # each edition counts its own versions (the Modern is a Lulu book of its own)
    n = next_point(d, edition) if a.point else a.version or str(last_version(d, edition) + 1)
    point = is_point(n)
    if point and n.lstrip("v").split(".")[0] != str(version_key(s["tag"]["tag"])[0]
                                                   if s.get("tag") else ""):
        sys.exit(f"a point version follows the last sign-off "
                 f"({s['tag']['tag'] if s.get('tag') else 'none'}): {n} does not")
    tag = f"{s['unit']}/v{n.lstrip('v')}"
    if git("rev-parse", "-q", "--verify", f"refs/tags/{tag}", check=False).returncode == 0:
        sys.exit(f"{tag} exists already")
    if s.get("tag") and not s["changed"]:
        sys.exit(f"{s['name']} is unchanged since {s['tag']['tag']}: nothing new to sign off")
    print(f"{s['name']}: the gates before signing off {tag}")
    with tempfile.TemporaryDirectory(prefix="fgb-release-") as tmp:
        (Path(tmp) / "now").mkdir()
        files, res = run_gates(s, Path(tmp) / "now")
        show_gates(res)
        if any(v for k, v in res.items() if not k.startswith("_")):
            sys.exit("not signed off: fix what failed above first")
        lulu = []
        if point:
            last = s["tag"]["tag"]
            print(f"  the print at {last} ...")
            # the edition's own last print: the other edition's is another book
            then = print_at(last, Path(tmp) / "then", s["build"])
            diff = print_differences(then, files, Path(tmp) / "pages")
            was = print_version(s["tag"]["version"])
            lulu = [f"Print: the same as {last.rsplit('/', 1)[-1]}, page for page "
                    f"(Lulu revision {was[1:]})." if not diff else
                    f"Print: changed since {last.rsplit('/', 1)[-1]} "
                    f"({'; '.join(diff)}); not a Lulu revision."]
            print(f"  {lulu[0]}")
    title = edition_title(fgb.Book(d), edition)
    # a print volume's tag says what it was made from, as its record does
    parts = ["Made from: " + "; ".join(
        f"{edition_title(fgb.Book(REPO / 'books' / m['book']), edition)} {m['version']} "
        f"({m['tag']})" for m in s["made_from"]) + "."] if s["volume"] else []
    based = modern_record(s["record"]).get("based_on") \
        if edition == MODERN and not s["volume"] else ""
    if based:
        parts.append(f"Based on: the Classic {based} ({slug(d)}/{based}).")
    msg = [f"{title}, v{n.lstrip('v')}"] + parts + lulu + ([a.note] if a.note else [])
    args = ["tag", "-s", tag] + [x for m in msg for x in ("-m", m)]
    r = subprocess.run(["git", "-C", str(REPO), *args])   # may ask for the key
    if r.returncode:
        sys.exit("git tag failed; nothing was signed off")
    ok, what = signature(tag)
    print(f"signed off: {tag} ({what})")
    print(f"publish the sign-off: git push origin {tag}")


def template_version(bk, edition=None):
    for f in [f for f in bk.cfg.get("PRINT") or [bk.dir.name + ".typ"]
              if fgb.in_edition(f, edition)]:
        m = re.search(r'#import "@local/(fgbooks\w*):([\d.]+)"',
                      (bk.dir / f).read_text(encoding="utf-8"))
        if m:
            return f"{m.group(1)} {m.group(2)}"
    return ""


def release_id():
    base = datetime.date.today().strftime("%Y.%m.%d")
    n, rid = 1, base
    while git("rev-parse", "-q", "--verify", f"refs/tags/{rid}", check=False).returncode == 0:
        n += 1
        rid = f"{base}.{n}"
    return rid


def asset_name(d, version, f):
    """the-book.pdf -> the-book-v3.pdf; cover.pdf -> the-book-v3-cover.pdf:
    flat, unique names for a release's downloads."""
    stem = f.name[len(d.name):] if f.name.startswith(d.name) else "-" + f.name
    return f"{d.name}-{version}{stem}" if stem.startswith((".", "-")) else \
        f"{d.name}-{version}-{f.name}"


def colophon_release():
    """colophon's release tag if it is checked out exactly at one, clean."""
    r = subprocess.run(["git", "-C", str(fgb.HERE), "describe", "--tags",
                        "--exact-match", "--dirty"], capture_output=True, text=True)
    v = r.stdout.strip()
    return v if r.returncode == 0 and re.fullmatch(r"\d+\.\d+\.\d+", v) else None


def gitmodules_without(dropped):
    """HEAD's .gitmodules less the submodules inside dropped folders (None if
    it has none of them), so a clone of `stable` does not look for them."""
    text = git("show", "HEAD:.gitmodules", check=False).stdout
    if not text:
        return None
    keep, gone, block = [], False, []
    for line in text.splitlines(keepends=True) + ["[end]"]:
        if line.startswith("["):
            path = re.search(r"^\s*path\s*=\s*(.+?)\s*$", "".join(block), re.M)
            if path and any(path.group(1).startswith(d + "/") for d in dropped):
                gone = True
            else:
                keep += block
            block = []
        block.append(line)
    return "".join(keep) if gone else None


def stable_commit(rid, done, catalog_md, catalog_json, branch=BRANCH, extra=(),
                  carried=()):
    """A commit on the local `stable` branch: HEAD's tree with only the done
    books (every other books/<author>/<book>/ folder left out), the carried
    ones as they were at their sign-off, and the catalog. Its parent is the
    last stable commit, so `git pull` works. done and carried are units: a
    folder is HEAD's when one of its editions is done, else as tagged at its
    first carried sign-off; another edition carried beside it has its own
    files as at its own tag (the shared files are the folder's)."""
    keep = {slug(s["dir"]) for s in list(done) + list(carried)}
    env = dict(os.environ, GIT_INDEX_FILE=str(Path(tempfile.mkdtemp()) / "index"))
    g = lambda *a, inp=None: subprocess.run(["git", "-C", str(REPO), *a], env=env,
                                            input=inp, capture_output=True,
                                            text=True, check=True).stdout.strip()
    g("read-tree", "HEAD")
    drop = set()
    for path in g("ls-files", "books").splitlines():
        parts = path.split("/")
        if len(parts) >= 4 and parts[1] != "resources" and "/".join(parts[1:3]) not in keep:
            drop.add("/".join(parts[:3]))
    for p in sorted(drop):
        g("rm", "-r", "--cached", "-q", p)
    based = {s["slug"] for s in done}
    for s in carried:
        folder = f"books/{s['slug']}"
        if s["slug"] in based:
            overlay(g, s)
            continue
        based.add(s["slug"])
        g("rm", "-r", "--cached", "-q", "--ignore-unmatch", folder)
        g("read-tree", f"--prefix={folder}/", f"{s['tag']['tag']}:{folder}")
    files = [("CATALOG.md", catalog_md), ("catalog.json", catalog_json), *extra]
    modules = gitmodules_without(drop)
    if modules is not None:
        files.append((".gitmodules", modules))
    for name, text in files:
        blob = g("hash-object", "-w", "--stdin", inp=text)
        g("update-index", "--add", "--cacheinfo", f"100644,{blob},{name}")
    tree = g("write-tree")
    parent = next((r for r in (branch, f"origin/{branch}")
                   if git("rev-parse", "-q", "--verify", r, check=False).returncode == 0), None)
    if parent and out("rev-parse", f"{parent}^{{tree}}") == tree:
        return out("rev-parse", parent), False
    msg = f"Release {rid}\n\n" + "".join(
        f"{s['unit']} {s['tag']['version']} ({s['tag']['tag']})\n" for s in done) + "".join(
        f"{s['unit']} {s['tag']['version']} ({s['tag']['tag']}, carried)\n"
        for s in carried) + \
        f"\nfrom {out('rev-parse', 'HEAD')} on {out('rev-parse', '--abbrev-ref', 'HEAD')}\n"
    commit = g("commit-tree", tree, *(["-p", parent] if parent else []), inp=msg)
    git("update-ref", f"refs/heads/{branch}", commit)
    return commit, True


def overlay(g, s):
    """In the index g works on, one edition's own files of its folder (not the
    shared ones) as they were at its sign-off."""
    which = classifier(s["dir"])
    folder = f"books/{s['slug']}/"
    for path in g("ls-files", folder).splitlines():
        if which(path[len(folder):]) == s["edition"]:
            g("rm", "--cached", "-q", path)
    for line in out("ls-tree", "-r", s["tag"]["tag"], "--", folder).splitlines():
        meta, path = line.split("\t", 1)
        mode, _kind, obj = meta.split()
        if which(path[len(folder):]) == s["edition"]:
            g("update-index", "--add", "--cacheinfo", f"{mode},{obj},{path}")


def catalog(rid, entries, colophon, trial=False):
    md = [f"# Freely Given Books: release {rid}", ""]
    if trial:
        md += ["**A trial release**: its sign-offs and tools are not all checked; "
               "nothing in it is published.", ""]
    md += [
          "Get it: `git clone --recursive -b stable "
          "https://github.com/freely-given-books/books.git`, then `./fgb build`.", "",
          "Every book here has been signed off by the editor: a signed tag",
          "`<author>/<book>/vN` on the commit it was checked at (a Modern English",
          "edition, its own paperback with its own Lulu revisions, has its own:",
          "`<author>/<book>/modern/vN`), and the book's files are as they were",
          "signed off (a book's two editions are signed off one by one; each tag",
          "covers its edition's own files and the shared ones). Each book was checked again for",
          "this release: its sources match the checksums in its `RELEASE.toml`, the",
          "TEI rebuilds as committed (verify.py), every review edit is applied, the",
          "print PDFs keep Lulu's rules and the EPUBs pass epubcheck. A book changed",
          "since its sign-off and not yet signed off again is carried: its signed",
          "version, built from its tag (it was checked when it was signed off).", "",
          "Check a sign-off yourself:", "",
          "```sh",
          "git -c gpg.ssh.allowedSignersFile=allowed_signers tag -v <author>/<book>/vN",
          "git diff --stat <author>/<book>/vN stable -- books/<author>/<book>   # that edition's: nothing",
          "sha256sum -c SHA256SUMS                                         # the downloads",
          "```", "",
          f"Built with colophon {colophon}.", "",
          "| Book | Author | Edition | Version | Signed off |",
          "| --- | --- | --- | --- | --- |"]
    for e in entries:
        shown = e["version"] + (" (between Lulu revisions)" if is_point(e["version"]) else "")
        ed = "Modern English" if e.get("edition") == MODERN else "Classic"
        md.append(f"| [{e['title']}](#{re.sub(r'[^a-z0-9 -]', '', e['title'].lower()).replace(' ', '-')}) | {e['author']} | {ed} | {shown} "
                  f"| {e['signed_off']['date']} |")
    for e in entries:
        md += ["", f"## {e['title']}"]
        if e["summary"]:
            md += ["", e["summary"]]
        md += ["", f"- folder: `books/{e['book']}`",
               f"- version {e['version']}: tag `{e['signed_off']['tag']}`, "
               f"signed off {e['signed_off']['date']} by {e['signed_off']['signer']}"
               + ("" if e["signed_off"]["signature_verified"] else " (signature not verified)"),
               f"- template: {e['template']}" if e["template"] else "- template: -",
               f"- print: Lulu revision {e['lulu_revision']} of "
               + ("the Modern English paperback, a Lulu book of its own"
                  if e.get("edition") == MODERN else "this paperback")]
        if e.get("based_on"):
            md.append(f"- its text follows the Classic {e['based_on']}")
        if e.get("carried"):
            md.append("- changed since this sign-off and not signed off again: this "
                      "release carries the signed version, built from its tag")
        if is_point(e["version"]):
            md.append(f"- a point version: an improved ebook after Lulu revision "
                      f"{print_version(e['version'])[1:]}; the print PDFs are that "
                      f"revision's ({print_version(e['version'])}, built from its tag)")
        if e.get("made_from"):
            md.append("- a print volume, made from: " + ", ".join(
                f"{m['book']} {m['version']} (`{m['tag']}`)" for m in e["made_from"]))
        if e["signed_off"]["note"]:
            md.append(f"- sign-off note: {e['signed_off']['note']}")
        for x in e["sources"]:
            link = f" <{x['url']}>" if x.get("url") else ""
            md.append(f"- source: {x['description']}{link}, `{x['file']}` "
                      f"(sha256 `{x['sha256'][:16]}…`)")
        for w in e["witnesses"]:
            link = f" <{w['url']}>" if w.get("url") else ""
            md.append(f"- witness: {w.get('description', '')}{link}")
        md.append("- files: " + ", ".join(f"`{f['name']}`" for f in e["files"]))
        if e["coverage"] is None:
            continue
        md += ["", "Fidelity to the source (counted from the TEI's record of every "
               "decision; ./fgb coverage):", ""]
        md += [f"- {line}" for line in coverage.summary(e["coverage"])]
    data = {"release": rid, "colophon": colophon, "books": entries}
    return "\n".join(md) + "\n", json.dumps(data, indent=2, ensure_ascii=False) + "\n"


def entry(s, bk, files, carried=False):
    """One edition's entry in the catalog: a book's Classic, or its Modern
    English (the same "book", its own "unit", version, sign-off and files)."""
    rec = s["record"] or {}
    if carried:
        # its record as signed off
        r = bk.dir / RECORD
        rec = tomllib.loads(r.read_text(encoding="utf-8")) if r.exists() else rec
    modern = s.get("edition") == MODERN
    part = modern_record(rec) if modern else rec
    t = s["tag"]
    made = [{"book": x["book"], "version": x["version"],
             "tag": f"{x['book']}{'/modern' if modern else ''}/{x['version']}"}
            for x in volume_books(rec, MODERN if modern else CLASSIC)]
    return {
        "book": s["slug"], "unit": s["unit"], "edition": s.get("edition", CLASSIC),
        "folder": s["dir"].name,
        "title": edition_title(bk, s.get("edition")), "author": bk.author,
        "version": t["version"], "lulu_revision": version_key(t["tag"])[0],
        "summary": part.get("summary") or rec.get("summary", ""),
        **({"based_on": part.get("based_on", "")} if modern and not bk.volume else {}),
        "signed_off": {"tag": t["tag"], "commit": t["commit"], "date": t["date"],
                       "signer": t["signer"], "note": t["note"],
                       "signature_verified": s["signed"]},
        "carried": carried,
        "template": template_version(bk, s.get("build")),
        # the Modern is made from the Classic's text: the sources are the Classic's
        "sources": [] if modern else rec.get("source", []),
        "witnesses": [] if modern else rec.get("witness", []),
        **({"made_from": made} if bk.volume else {}),
        "coverage": None if bk.volume or modern else coverage.coverage(bk.tei),
        "files": files}


def cmd_make(a):
    if not shutil.which("epubcheck"):
        sys.exit("a release needs epubcheck installed")
    colophon = colophon_release()
    if not colophon and not a.trial:
        sys.exit(f"colophon is at {fgb.git_state(fgb.HERE)}, not a release: a release "
                 "is built with released tools (--trial to try one anyway)")
    colophon = colophon or fgb.git_state(fgb.HERE)
    branch = BRANCH + ("-trial" if a.trial else "")
    rid = release_id()
    root = (Path(a.out).resolve() if a.out else REPO / "dist" / "release") / rid
    # one state per edition: a book's Classic and its Modern go out (or are
    # held back, or carried) each on its own
    states = units()
    signed = [s for s in states if s.get("tag")]
    done = [s for s in signed if s["done"] or (a.trial and s["holds"])]
    # a book changed since its sign-off goes out as it was signed off: built
    # from its tag, its folder in `stable` as tagged
    carried = [s for s in signed if s not in done and s["changed"] and
               not s["problems"] and (s["signed"] or a.trial)]
    for s in signed:
        if s in carried:
            print(f"carried: {s['name']} at {s['tag']['tag']} "
                  f"({len(s['changed'])} file(s) changed since; not signed off again)")
        elif s not in done:
            why = (f"{len(s['changed'])} file(s) changed since {s['tag']['tag']}"
                   if s["changed"] else "; ".join(s["problems"]) or s["signature"])
            print(f"held back: {s['name']} ({why})")
    if not done and not carried:
        sys.exit("no book is signed off: nothing to release")
    if root.exists():
        shutil.rmtree(root)
    root.mkdir(parents=True)
    entries, failed = [], []
    for s in done:
        d = s["dir"]
        print(f"\n== {s['name']} {s['tag']['version']}")
        with tempfile.TemporaryDirectory(prefix="fgb-release-") as tmp:
            built, res = run_gates(s, Path(tmp), trial=a.trial)
            show_gates(res)
            if any(v for k, v in res.items() if not k.startswith("_")):
                failed.append(s["name"])
                continue
            # a point version's print is revision N's: the PDFs and covers
            # built at the vN tag, named vN; its EPUBs carry vN.M
            version = s["tag"]["version"]
            printed = version
            if is_point(version):
                printed = print_version(version)
                print(f"  the print at {printed} ...")
                print_files = print_at(f"{s['unit']}/{printed}", Path(tmp) / "print",
                                       s["build"])
                built = [f for f in built if f.suffix == ".epub"] + print_files
            name = lambda f: asset_name(d, version if Path(f).suffix in (".epub", ".html")
                                        else printed, Path(f))
            # the reader and the comparison page, linking to the downloads by
            # the names they have in the release
            built += fgb.build_web(fgb.Book(d), Path(tmp), built, link=name)
            files = []
            for f in built:
                dest = root / name(f)
                shutil.copy2(f, dest)
                files.append({"name": dest.name, "bytes": dest.stat().st_size,
                              "sha256": sha256(dest)})
        entries.append(entry(s, fgb.Book(d), files))
    for s in carried:
        print(f"\n== {s['name']} {s['tag']['version']} (carried, from its tag)")
        version = printed = s["tag"]["version"]
        if is_point(version):
            printed = print_version(version)
        name = lambda f, d=s["dir"], v=version, pv=printed: asset_name(
            d, v if Path(f).suffix in (".epub", ".html") else pv, Path(f))
        with tempfile.TemporaryDirectory(prefix="fgb-release-") as tmp:
            def finish(bk, built, s=s, tmp=tmp, name=name, version=version,
                       printed=printed):
                if is_point(version):
                    built = [f for f in built if f.suffix == ".epub"] + \
                        print_at(f"{s['unit']}/{printed}", Path(tmp) / "print", s["build"])
                built += fgb.build_web(bk, Path(tmp), built, link=name)
                files = []
                for f in built:
                    dest = root / name(f)
                    shutil.copy2(f, dest)
                    files.append({"name": dest.name, "bytes": dest.stat().st_size,
                                  "sha256": sha256(dest)})
                return entry(s, bk, files, carried=True)
            try:
                _, e = build_at(s["tag"]["tag"], Path(tmp) / "book", epub=True,
                                then=finish, edition=s["build"])
            except SystemExit as err:
                print(f"  failed to build from its tag: {err}")
                failed.append(s["name"])
                continue
        entries.append(e)
    if failed:
        sys.exit(f"\nno release: {', '.join(failed)} failed a gate (above). A signed-off "
                 "book that no longer passes needs fixing and a new sign-off.")
    # a book's Classic and Modern side by side, the Classic first
    entries.sort(key=lambda e: (e["book"], e.get("edition") == MODERN))
    # page counts, trims and cover wraps, so a site never opens the PDFs
    for name in printfacts.add(root, entries, sha256):
        print(f"note: {name}: its size does not fit its trim: no wrap images")
    md, js = catalog(rid, entries, colophon, a.trial)
    (root / "CATALOG.md").write_text(md, encoding="utf-8")
    (root / "catalog.json").write_text(js, encoding="utf-8")
    # for books.freely.giving's sync (export.py)
    __import__("export").site_manifest(root)
    sums =[f"{sha256(f)}  {f.name}" for f in sorted(root.iterdir()) if f.is_file()]
    (root / "SHA256SUMS").write_text("\n".join(sums) + "\n", encoding="utf-8")
    extra = [] if a.trial else [(REVISIONS.relative_to(REPO).as_posix(),
                                  record_release(rid, done + carried))]
    commit, new = stable_commit(rid, done, md, js, branch, extra, carried)
    rel = root.relative_to(REPO) if root.is_relative_to(REPO) else root
    print(f"\nrelease {rid}: {len(done) + len(carried)} book(s) in {rel}"
          + (f", {len(carried)} carried at their sign-off" if carried else ""))
    for e in entries:
        print(f"  {e['unit']} {e['version']}: {len(e['files'])} file(s)")
    print(f"`{branch}`: {'new commit' if new else 'unchanged at'} {commit[:12]}")
    if a.trial:
        print("a trial: nothing to publish (git branch -D stable-trial when done with it)")
        return
    if out("rev-parse", "--abbrev-ref", "HEAD") != "main":
        print("note: made from a branch other than main")
    print(f"\n{REVISIONS.relative_to(REPO)} has the release: commit it on main.")
    print("\nto publish it (nothing has been pushed):\n"
          f"  git push origin {BRANCH}\n"
          f"  git tag -s {rid} {BRANCH} -m 'Release {rid}' && git push origin {rid}\n"
          f"  gh release create {rid} --verify-tag --title 'Release {rid}' "
          f"--notes-file {rel}/CATALOG.md {rel}/*")


def main(a):
    if a.action in ("sign", "make") or getattr(a, "check", False):
        try:
            packages.setup()
        except packages.PackageError as e:
            sys.exit(f"fgb: {e}")
    fn = {"status": cmd_status, "record": cmd_record, "sign": cmd_sign,
          "make": cmd_make, "ready": cmd_ready}[a.action]
    sys.exit(fn(a) or 0)
