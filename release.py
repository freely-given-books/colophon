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
                                 signed off; --check also runs the gates
  ./fgb release record BOOK      write BOOK's RELEASE.toml (its source files
                                 and their checksums), to fill in and commit
  ./fgb release sign BOOK [N]    run the gates on BOOK, then cut the signed
                                 tag <author>/<book>/vN (the editor's step;
                                 N: one past the last version,
                                 tags or books/revisions.json)
  ./fgb release sign BOOK --point
                                 a point version, vN.1, vN.2, ...: an
                                 improved edition between Lulu revisions
  ./fgb release ready BOOK       the editor calls BOOK ready to sign as it
                                 stands (the signing waits for its Lulu
                                 revision): books/publishing.toml records the
                                 date and commit, and status shows it, or
                                 that the book has changed since; --clear
                                 takes it back
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

REPO = fgb.REPO
RECORD = "RELEASE.toml"
SIGNERS = REPO / "allowed_signers"
BRANCH = "stable"
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


def version_key(tag):
    return [int(x) for x in re.findall(r"\d+", tag.rsplit("/v", 1)[-1])]


def book_tags(d):
    """The book's sign-off tags, newest version first."""
    tags = [t for t in out("tag", "-l", f"{slug(d)}/v*").splitlines()
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


def changed_since(d, tag):
    """Files of the book's folder that differ from the tag, committed or not
    (git-ignored files aside)."""
    rel = d.relative_to(REPO)
    files = set(out("diff", "--name-only", tag, "--", rel).splitlines())
    files.update(uncommitted(d))
    return sorted(f for f in files if f)


def uncommitted(d):
    """Files of the book's folder changed or added and not committed."""
    st = git("status", "--porcelain", "--", d.relative_to(REPO)).stdout
    return [l[3:] for l in st.splitlines() if l]


def state(d):
    """Where a book stands: its record, its latest sign-off and whether that
    still holds."""
    s = {"dir": d, "slug": slug(d), "record": None, "problems": [], "done": False}
    rec = d / RECORD
    if rec.exists():
        try:
            s["record"] = tomllib.loads(rec.read_text(encoding="utf-8"))
        except tomllib.TOMLDecodeError as e:
            s["problems"].append(f"{RECORD}: {e}")
    tags = book_tags(d)
    s["tags"] = tags
    if not tags:
        return s
    t = s["tag"] = tag_info(tags[0])
    if not t["annotated"]:
        s["problems"].append(f"{tags[0]} is a lightweight tag; a sign-off is a signed tag")
    s["signed"], s["signature"] = signature(tags[0])
    if git("merge-base", "--is-ancestor", t["commit"], "HEAD", check=False).returncode:
        s["problems"].append(f"{tags[0]} is not in this branch's history")
    s["changed"] = changed_since(d, tags[0])
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


def gate_record(s):
    rec = s["record"]
    if rec is None:
        return [f"no {RECORD} (./fgb release record {s['slug']})"]
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


def gate_builds(bk, outdir):
    """Build the print PDFs, covers and EPUB(s) into outdir. (files, problems)"""
    problems, files = [], []
    try:
        files += fgb.build_pdf(bk, outdir, covers=True, problems=problems)
    except SystemExit as e:
        return files, [f"print build failed: {e}"]
    try:
        files += fgb.build_epub(bk, outdir)
    except SystemExit as e:
        return files, problems + [f"EPUB build failed: {e}"]
    return files, problems


def run_gates(s, outdir, log=print):
    """Every gate on one book; (built files, {gate: [problems]})."""
    d = s["dir"]
    res = {"record": gate_record(s), "clean": [], "report": gate_report(d)}
    dirty = uncommitted(d)
    if dirty:
        res["clean"] = [f"uncommitted: {', '.join(dirty[:5])}" +
                        (f" and {len(dirty) - 5} more" if len(dirty) > 5 else "")]
    log("  verify.py ...")
    res["verify"] = gate_verify(d)
    log("  building ...")
    files, built = gate_builds(fgb.Book(d), outdir)
    res["print"] = [p for p in built if "EPUB" not in p]
    # footnotes set a page from their marker (a Typst limitation, not a Lulu
    # rule) that the editor has accepted, each by its message, in RELEASE.toml
    # ("accepted_print"); any other, or a new one, still fails the gate
    accepted = set((s["record"] or {}).get("accepted_print", []))
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
            if (d / RECORD).exists() or book_tags(d)]


PUBLISHING = REPO / "books" / "publishing.toml"


def ready_of(d):
    """{"date", "commit"} when the editor has called the book ready to sign."""
    if not PUBLISHING.exists():
        return None
    r = tomllib.loads(PUBLISHING.read_text(encoding="utf-8")).get(slug(d), {}).get("ready")
    return r if isinstance(r, dict) and r.get("commit") else None


def ready_note(d):
    r = ready_of(d)
    if not r:
        return ""
    same = git("diff", "--quiet", r["commit"], "--", str(d.relative_to(REPO)),
               check=False).returncode == 0
    return (f"; ready to sign since {r['date']} ({r['commit']})" if same else
            f"; called ready {r['date']} ({r['commit']}), but changed since")


def cmd_ready(a):
    """Record (or with --clear take back) the editor's "ready to sign"."""
    d = fgb.find_book(a.book)
    key = slug(d)
    if not a.clear and git("status", "--porcelain", "--", str(d.relative_to(REPO))).stdout.strip():
        sys.exit(f"{key}: uncommitted changes in its folder; commit them first, so "
                 "\"ready\" names the book as it stands")
    head = f'["{key}"]'
    lines = PUBLISHING.read_text(encoding="utf-8").split("\n") if PUBLISHING.exists() else []
    if head not in lines:
        if a.clear:
            print(f"{key}: not marked ready")
            return 0
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
    for d in books:
        s = state(d)
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
            what += ready_note(d)
        print(f"  {s['slug']:58} {what}")
        for f in s.get("changed", [])[:8]:
            print(f"      changed: {f}")
        if gh and t and s.get("changed"):
            print(f"::warning::{s['slug']} changed since its sign-off "
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


def cmd_record(a):
    d = fgb.find_book(a.book)
    path = d / RECORD
    if path.exists():
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
    path.write_text("\n".join(lines), encoding="utf-8")
    print(f"wrote {path.relative_to(REPO)}: fill in the descriptions and the "
          "summary, then commit it")


REVISIONS = REPO / "books" / "revisions.json"


def revisions():
    """books/revisions.json: every release and the book versions in it
    ({"releases": [{"release": "2026.03.16", "books": {"<author>/<book>": 2}}]})."""
    if REVISIONS.exists():
        return json.loads(REVISIONS.read_text(encoding="utf-8"))
    return {"releases": []}


def record_release(rid, done):
    """Add (or replace) this release in books/revisions.json; its text."""
    data = revisions()
    # a whole version as a number (Lulu's revision), a point version as "13.1"
    books = {s["slug"]: (lambda v: v[0] if len(v) == 1 else ".".join(map(str, v)))(
        version_key(s["tag"]["tag"])) for s in done}
    data["releases"] = [r for r in data["releases"] if r["release"] != rid] + \
        [{"release": rid, "books": books}]
    text = json.dumps(data, indent=2, ensure_ascii=False) + "\n"
    REVISIONS.write_text(text, encoding="utf-8")
    return text


def last_version(d):
    """The last version of the book: the higher of its newest tag and the
    highest in books/revisions.json (the Lulu revisions published before
    sign-off tags, which a tag from a withdrawn release can lag behind)."""
    tags = book_tags(d)
    tagged = version_key(tags[0])[0] if tags else 0
    return max([tagged] + [int(str(r["books"].get(slug(d), 0)).split(".")[0])
                           for r in revisions()["releases"]])


def is_point(version):
    """v13.1: a point version, between Lulu revisions 13 and 14."""
    return "." in version.lstrip("v")


def print_version(version):
    """The print revision of a version: v13.1 -> v13."""
    return "v" + version.lstrip("v").split(".")[0]


def next_point(d):
    """The next point version: vN.(M+1) after the newest sign-off vN(.M)."""
    tags = book_tags(d)
    if not tags:
        sys.exit(f"{slug(d)} has no sign-off: a point version follows one")
    n = version_key(tags[0])
    if n[0] < last_version(d):
        sys.exit(f"{slug(d)}: revision {last_version(d)} (books/revisions.json) is "
                 f"newer than its last sign-off, {tags[0]}; sign off a print revision")
    return f"{n[0]}.{(n[1] if len(n) > 1 else 0) + 1}"


def build_at(tag, outdir, epub=False, then=None):
    """Build the book as it was at a sign-off (a checkout of the tag, with
    this colophon; the templates it imports from the cache): its print PDFs
    and covers, and with epub its EPUB(s). then(bk, files) runs before the
    checkout goes (the web pages, the catalog entry); its result is returned
    with the files."""
    book = Path("books") / tag.rsplit("/v", 1)[0]
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
            files = fgb.build_pdf(bk, outdir, covers=True, root=wt)
            if epub:
                files += fgb.build_epub(bk, outdir, root=wt)
            return files, (then(bk, files) if then else None)
        finally:
            git("worktree", "remove", "--force", str(wt), check=False)


def print_at(tag, outdir):
    """The book's print PDFs and covers as they were at a sign-off."""
    return build_at(tag, outdir)[0]


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
    d = fgb.find_book(a.book)
    s = state(d)
    if a.point and a.version:
        sys.exit("give a version or --point, not both")
    n = next_point(d) if a.point else a.version or str(last_version(d) + 1)
    point = is_point(n)
    if point and n.lstrip("v").split(".")[0] != str(version_key(s["tag"]["tag"])[0]
                                                   if s.get("tag") else ""):
        sys.exit(f"a point version follows the last sign-off "
                 f"({s['tag']['tag'] if s.get('tag') else 'none'}): {n} does not")
    tag = f"{slug(d)}/v{n.lstrip('v')}"
    if git("rev-parse", "-q", "--verify", f"refs/tags/{tag}", check=False).returncode == 0:
        sys.exit(f"{tag} exists already")
    if s.get("tag") and not s["changed"]:
        sys.exit(f"{slug(d)} is unchanged since {s['tag']['tag']}: nothing new to sign off")
    print(f"{slug(d)}: the gates before signing off {tag}")
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
            then = print_at(last, Path(tmp) / "then")
            diff = print_differences(then, files, Path(tmp) / "pages")
            was = print_version(s["tag"]["version"])
            lulu = [f"Print: the same as {last.rsplit('/', 1)[-1]}, page for page "
                    f"(Lulu revision {was[1:]})." if not diff else
                    f"Print: changed since {last.rsplit('/', 1)[-1]} "
                    f"({'; '.join(diff)}); not a Lulu revision."]
            print(f"  {lulu[0]}")
    title = fgb.Book(d).cfg.get("EPUB", {}).get("title", d.name)
    msg = [f"{title}, v{n.lstrip('v')}"] + lulu + ([a.note] if a.note else [])
    args = ["tag", "-s", tag] + [x for m in msg for x in ("-m", m)]
    r = subprocess.run(["git", "-C", str(REPO), *args])   # may ask for the key
    if r.returncode:
        sys.exit("git tag failed; nothing was signed off")
    ok, what = signature(tag)
    print(f"signed off: {tag} ({what})")
    print(f"publish the sign-off: git push origin {tag}")


def template_version(bk):
    for f in bk.cfg.get("PRINT") or [bk.dir.name + ".typ"]:
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
    last stable commit, so `git pull` works."""
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
    for s in carried:
        folder = f"books/{s['slug']}"
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
        f"{s['slug']} {s['tag']['version']} ({s['tag']['tag']})\n" for s in done) + "".join(
        f"{s['slug']} {s['tag']['version']} ({s['tag']['tag']}, carried)\n"
        for s in carried) + \
        f"\nfrom {out('rev-parse', 'HEAD')} on {out('rev-parse', '--abbrev-ref', 'HEAD')}\n"
    commit = g("commit-tree", tree, *(["-p", parent] if parent else []), inp=msg)
    git("update-ref", f"refs/heads/{branch}", commit)
    return commit, True


def catalog(rid, entries, colophon, trial=False):
    md = [f"# Freely Given Books: release {rid}", ""]
    if trial:
        md += ["**A trial release**: its sign-offs and tools are not all checked; "
               "nothing in it is published.", ""]
    md += [
          "Get it: `git clone --recursive -b stable "
          "https://github.com/freely-given-books/books.git`, then `./fgb build`.", "",
          "Every book here has been signed off by the editor: a signed tag",
          "`<author>/<book>/vN` on the commit it was checked at, and the book's",
          "folder is exactly as it was signed off. Each book was checked again for",
          "this release: its sources match the checksums in its `RELEASE.toml`, the",
          "TEI rebuilds as committed (verify.py), every review edit is applied, the",
          "print PDFs keep Lulu's rules and the EPUBs pass epubcheck. A book changed",
          "since its sign-off and not yet signed off again is carried: its signed",
          "version, built from its tag (it was checked when it was signed off).", "",
          "Check a sign-off yourself:", "",
          "```sh",
          "git -c gpg.ssh.allowedSignersFile=allowed_signers tag -v <author>/<book>/vN",
          "git diff --stat <author>/<book>/vN stable -- books/<author>/<book>   # nothing",
          "sha256sum -c SHA256SUMS                                         # the downloads",
          "```", "",
          f"Built with colophon {colophon}.", "",
          "| Book | Author | Version | Signed off |", "| --- | --- | --- | --- |"]
    for e in entries:
        shown = e["version"] + (" (between Lulu revisions)" if is_point(e["version"]) else "")
        md.append(f"| [{e['title']}](#{re.sub(r'[^a-z0-9 -]', '', e['title'].lower()).replace(' ', '-')}) | {e['author']} | {shown} "
                  f"| {e['signed_off']['date']} |")
    for e in entries:
        md += ["", f"## {e['title']}"]
        if e["summary"]:
            md += ["", e["summary"]]
        md += ["", f"- folder: `books/{e['book']}`",
               f"- version {e['version']}: tag `{e['signed_off']['tag']}`, "
               f"signed off {e['signed_off']['date']} by {e['signed_off']['signer']}"
               + ("" if e["signed_off"]["signature_verified"] else " (signature not verified)"),
               f"- template: {e['template']}" if e["template"] else "- template: -"]
        if e.get("carried"):
            md.append("- changed since this sign-off and not signed off again: this "
                      "release carries the signed version, built from its tag")
        if is_point(e["version"]):
            md.append(f"- a point version: an improved ebook after Lulu revision "
                      f"{print_version(e['version'])[1:]}; the print PDFs are that "
                      f"revision's ({print_version(e['version'])}, built from its tag)")
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
        md += ["", "Fidelity to the source (counted from the TEI's record of every "
               "decision; ./fgb coverage):", ""]
        md += [f"- {line}" for line in coverage.summary(e["coverage"])]
    data = {"release": rid, "colophon": colophon, "books": entries}
    return "\n".join(md) + "\n", json.dumps(data, indent=2, ensure_ascii=False) + "\n"


def entry(s, bk, files, carried=False):
    """A book's entry in the catalog."""
    e = bk.cfg.get("EPUB", {})
    rec = s["record"] or {}
    if carried:
        # its record as signed off
        r = bk.dir / RECORD
        rec = tomllib.loads(r.read_text(encoding="utf-8")) if r.exists() else rec
    t = s["tag"]
    return {
        "book": s["slug"], "folder": s["dir"].name,
        "title": e.get("title", s["dir"].name), "author": e.get("author", ""),
        "version": t["version"], "summary": rec.get("summary", ""),
        "signed_off": {"tag": t["tag"], "commit": t["commit"], "date": t["date"],
                       "signer": t["signer"], "note": t["note"],
                       "signature_verified": s["signed"]},
        "carried": carried,
        "template": template_version(bk),
        "sources": rec.get("source", []), "witnesses": rec.get("witness", []),
        "coverage": coverage.coverage(bk.tei),
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
    states = [state(d) for d in candidates()]
    signed = [s for s in states if s.get("tag")]
    done = [s for s in signed if s["done"] or (a.trial and s["holds"])]
    # a book changed since its sign-off goes out as it was signed off: built
    # from its tag, its folder in `stable` as tagged
    carried = [s for s in signed if s not in done and s["changed"] and
               not s["problems"] and (s["signed"] or a.trial)]
    for s in signed:
        if s in carried:
            print(f"carried: {s['slug']} at {s['tag']['tag']} "
                  f"({len(s['changed'])} file(s) changed since; not signed off again)")
        elif s not in done:
            why = (f"{len(s['changed'])} file(s) changed since {s['tag']['tag']}"
                   if s["changed"] else "; ".join(s["problems"]) or s["signature"])
            print(f"held back: {s['slug']} ({why})")
    if not done and not carried:
        sys.exit("no book is signed off: nothing to release")
    if root.exists():
        shutil.rmtree(root)
    root.mkdir(parents=True)
    entries, failed = [], []
    for s in done:
        d = s["dir"]
        print(f"\n== {s['slug']} {s['tag']['version']}")
        with tempfile.TemporaryDirectory(prefix="fgb-release-") as tmp:
            built, res = run_gates(s, Path(tmp))
            show_gates(res)
            if any(v for k, v in res.items() if not k.startswith("_")):
                failed.append(s["slug"])
                continue
            # a point version's print is revision N's: the PDFs and covers
            # built at the vN tag, named vN; its EPUBs carry vN.M
            version = s["tag"]["version"]
            printed = version
            if is_point(version):
                printed = print_version(version)
                print(f"  the print at {printed} ...")
                print_files = print_at(f"{s['slug']}/{printed}", Path(tmp) / "print")
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
        print(f"\n== {s['slug']} {s['tag']['version']} (carried, from its tag)")
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
                        print_at(f"{s['slug']}/{printed}", Path(tmp) / "print")
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
                                then=finish)
            except SystemExit as err:
                print(f"  failed to build from its tag: {err}")
                failed.append(s["slug"])
                continue
        entries.append(e)
    if failed:
        sys.exit(f"\nno release: {', '.join(failed)} failed a gate (above). A signed-off "
                 "book that no longer passes needs fixing and a new sign-off.")
    md, js = catalog(rid, entries, colophon, a.trial)
    (root / "CATALOG.md").write_text(md, encoding="utf-8")
    (root / "catalog.json").write_text(js, encoding="utf-8")
    sums = [f"{sha256(f)}  {f.name}" for f in sorted(root.iterdir()) if f.is_file()]
    (root / "SHA256SUMS").write_text("\n".join(sums) + "\n", encoding="utf-8")
    extra = [] if a.trial else [(REVISIONS.relative_to(REPO).as_posix(),
                                  record_release(rid, done + carried))]
    commit, new = stable_commit(rid, done, md, js, branch, extra, carried)
    rel = root.relative_to(REPO) if root.is_relative_to(REPO) else root
    print(f"\nrelease {rid}: {len(done) + len(carried)} book(s) in {rel}"
          + (f", {len(carried)} carried at their sign-off" if carried else ""))
    for e in entries:
        print(f"  {e['book']} {e['version']}: {len(e['files'])} file(s)")
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
