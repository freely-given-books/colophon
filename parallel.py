"""A book's parallel page: the author's own texts beside the English, section by section.

    python parallel.py BOOK_DIR VOLUME OUT.html [--title T] [--reader URL]

For a book with a `parallel/` folder (first: Calvin's Institutes, the editor 2026-11-22/24):
`parallel/<lang>/<volume>/<file>.md` holds the text in another language for the English chapter
`chapters/typ/<volume>/<file>.typ` (Latin "la", French "fr"), and `parallel/sources.json` gives each
column's label: {"la": {"name": "Latin", "label": "..."}, "fr": {"name": "French", "label": "...",
"by_volume": {"vol-3": "..."}}, "en": {"label": "..."}, "fr_sections": {"vol-1/book-1-chapter-05":
{"11": [11, 12]}}}.

The page has one row per section: the Latin, the French and the English side by side, aligned by
section number (a paragraph opening "12." in the Markdown, "12\\." in the Typst). A French section
another edition numbers differently is placed by `fr_sections`; otherwise French section n stands
in row n, and one past the English's last stands in the last row. The reader turns any column on
or off (Latin and English at first; the choice is kept in the browser where it can be). The
editors' notes of a Latin file ("### Apparatus") are shown under its chapter, folded; the
transcription notes stay in the files.
"""

import argparse
import html
import json
import re
from pathlib import Path

ESC = html.escape


# -- the Markdown texts --------------------------------------------------------------------------

def md_parts(text):
    """(paragraphs of the text, apparatus lines) of one parallel file."""
    # a leading description comment, and any part's own
    text = re.sub(r"<!--(?!\s*(?:col|p\.))(.*?)-->", "", text, flags=re.S)
    m = re.search(r"\n###? (?:Apparatus|Notes|Unsettled)|\n## Notes on the transcription", text)
    body = text[:m.start()] if m else text
    app = []
    for am in re.finditer(r"\n### Apparatus[^\n]*\n(.*?)(?=\n##|\Z)", text, flags=re.S):
        app += [l.strip()[2:] if l.strip().startswith("- ") else l.strip()
                for l in am.group(1).splitlines() if l.strip() and not l.strip().startswith("<!--")]
    paras = [p.strip() for p in re.split(r"\n\s*\n", body) if p.strip()]
    return paras, app


def inline_md(s):
    s = re.sub(r"<!--\s*(?:col|p\.)[^>]*-->", "", s)
    s = re.sub(r"<!--.*?-->", "", s, flags=re.S)
    s = ESC(s.strip())
    s = re.sub(r"\[(\d+)-(\d+)\]", r'<sup class="app">\2</sup>', s)
    s = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", s)
    s = re.sub(r"\*(.+?)\*", r"<i>\1</i>", s)
    return s


def block_md(p):
    """One Markdown paragraph as HTML ("" for one that holds only markers)."""
    if not inline_md(p):
        return ""
    lines = [l for l in p.splitlines() if inline_md(l) or not l.strip()]
    if all(l.startswith(">") for l in lines if l.strip()):
        return "<blockquote>" + "<br>".join(inline_md(l.lstrip("> ")) for l in lines) + "</blockquote>"
    if len(lines) > 1 and not re.match(r"\s*(?:<!--.*?-->\s*)*\d+\.", lines[0]):
        return "<p>" + "<br>".join(inline_md(l) for l in lines) + "</p>"
    return "<p>" + inline_md(" ".join(lines)) + "</p>"


SEC = re.compile(r"^\s*(?:<!--[^>]*-->\s*)*(\d+)\.\s")


def md_sections(text):
    """({0: heading HTML, n: section HTML}, apparatus) of one parallel file."""
    paras, app = md_parts(text)
    secs, cur, head = {}, 0, []
    for p in paras:
        m = SEC.match(p)
        if m:
            cur = int(m.group(1))
            p = p[:m.start(1)] + p[m.end(1) + 1:]
            secs[cur] = [f'<span class="n">{cur}.</span> ' + block_md(p)[3:]]
        elif cur == 0:
            if p.startswith("## "):
                continue
            head.append(block_md(p))
        else:
            secs[cur].append(block_md(p))
    out = {n: "".join(v) for n, v in secs.items()}
    if head:
        out[0] = "".join(head)
    return out, app


# -- the English (Typst chapters) ----------------------------------------------------------------

def bracket(s, i):
    """The index just past the ] closing the [ at s[i]."""
    depth = 0
    while i < len(s):
        c = s[i]
        if c == "\\":
            i += 2
            continue
        if c == "[":
            depth += 1
        elif c == "]":
            depth -= 1
            if depth == 0:
                return i + 1
        i += 1
    return i


def typ_html(s):
    """The Typst markup of the Institutes chapters as HTML."""
    out, i = [], 0
    while i < len(s):
        c = s[i]
        if c == "\\" and i + 1 < len(s):
            out.append(ESC(s[i + 1]))
            i += 2
            continue
        if c == "#":
            m = re.match(r"#([a-z]+)(\([^)]*\))?(\[)?", s[i:])
            if m:
                name, args = m.group(1), m.group(2) or ""
                if not m.group(3):
                    i += m.end()          # #v(...) and the like: layout only
                    continue
                j = i + m.end() - 1
                k = bracket(s, j)
                inner = typ_html(s[j + 1:k - 1])
                if name == "emph":
                    out.append(f"<i>{inner}</i>")
                elif name == "smallcaps":
                    out.append(f'<span class="sc">{inner}</span>')
                elif name == "footnote":
                    out.append(f'<span class="fn">{inner}</span>')
                elif name == "quote":
                    out.append(f"<q class=\"bq\">{inner}</q>")
                else:                      # block, align, strong...
                    out.append(inner)
                i = k
                continue
        if c == "_":
            j = s.find("_", i + 1)
            if j > i:
                out.append(f"<i>{typ_html(s[i + 1:j])}</i>")
                i = j + 1
                continue
        out.append(ESC(c))
        i += 1
    return "".join(out)


def typ_sections(text):
    """({0: title HTML, n: section HTML}) of one English chapter."""
    secs, cur, title = {}, None, ""
    for p in re.split(r"\n\s*\n", text):
        p = p.strip()
        if not p or p.startswith("//"):
            continue
        if p.startswith("="):
            title = title or ESC(p.lstrip("= ").strip())
            continue
        m = re.match(r"^(\d+)\\\.\s*(.*)", p, re.S)
        if m:
            cur = int(m.group(1))
            secs[cur] = [f'<p><span class="n">{cur}.</span> {typ_html(m.group(2))}</p>']
        elif cur is not None:
            secs[cur].append(f"<p>{typ_html(p)}</p>")
        elif p.startswith("#align"):
            secs.setdefault(0, []).append(f'<p class="sub">{typ_html(p)}</p>')
        elif not secs or cur is None:
            # Beveridge's synopsis blocks before section 1: not Calvin's, left out here
            if not p.startswith("#block"):
                secs.setdefault(0, []).append(f"<p>{typ_html(p)}</p>") if typ_html(p).strip() else None
    out = {n: "".join(v) for n, v in secs.items()}
    if not any(n for n in out):
        # a text without sections (a preface): one block
        out = {0: "".join(f"<p>{typ_html(p.strip())}</p>" for p in re.split(r"\n\s*\n", text)
                          if p.strip() and not p.strip().startswith(("=", "//")))}
    return title, out


# -- the page -----------------------------------------------------------------------------------

def chapter_rows(name, la, fr, en, frmap):
    rows = []
    keys = sorted(set(en) | set(la)) or [0]
    if any(keys) and set(la) <= {0} and set(fr) <= {0}:
        # Latin and French without sections: the whole text against the whole English
        whole = lambda d: "".join(d[n] for n in sorted(d))
        return [(None, whole(la), whole(fr), whole(en))]
    last = max(keys)
    place = {}
    for n in fr:
        for row in frmap.get(str(n), [n]):
            row = row if row in keys else (last if row > last else 0)
            place.setdefault(row, []).append(n)
    used = set()
    for n in keys:
        frs = [x for x in place.get(n, []) if x not in used]
        used.update(frs)
        rows.append((n, la.get(n, ""), "".join(fr[x] for x in frs), en.get(n, "")))
    return rows


def build(book, vol, out, title=None, reader=None):
    book = Path(book)
    cfg = json.loads((book / "parallel" / "sources.json").read_text(encoding="utf-8"))
    typdir = book / "chapters" / "typ" / vol
    langs = [l for l in ("la", "fr") if (book / "parallel" / l / vol).is_dir()]
    label = {l: (cfg.get(l, {}).get("by_volume", {}).get(vol) or cfg.get(l, {}).get("label", ""))
             for l in langs + ["en"]}
    lname = {l: cfg.get(l, {}).get("name", l) for l in langs}
    lname["en"] = cfg.get("en", {}).get("name", "English")
    chapters, nav = [], []
    for typ in sorted(typdir.glob("*.typ")):
        texts = {l: (book / "parallel" / l / vol / f"{typ.stem}.md") for l in langs}
        if not any(p.exists() for p in texts.values()):
            continue
        t, en = typ_sections(typ.read_text(encoding="utf-8"))
        parsed = {l: md_sections(p.read_text(encoding="utf-8")) if p.exists() else ({}, [])
                  for l, p in texts.items()}
        la, app = parsed.get("la", ({}, []))
        fr = parsed.get("fr", ({}, []))[0]
        rows = chapter_rows(typ.stem, la, fr, en, cfg.get("fr_sections", {}).get(f"{vol}/{typ.stem}", {}))
        anchor = typ.stem
        m = re.match(r"book-(\d)-chapter-(\d+)$", typ.stem)
        if m:
            t = f"Book {'I II III IV'.split()[int(m.group(1)) - 1]}, Chapter {int(m.group(2))}"
        nav.append(f'<option value="#{anchor}">{t}</option>')
        body = []
        for n, l, f, e in rows:
            sid = f' id="{anchor}-{n}"' if n else ""
            body.append(f'<div class="row"{sid}>'
                        + (f'<div class="c la" lang="la">{l}</div>' if "la" in langs else "")
                        + (f'<div class="c fr" lang="fr">{f or "<p class=dim>—</p>"}</div>' if "fr" in langs else "")
                        + f'<div class="c en" lang="en">{e}</div></div>')
        appx = ("<details class=\"appx\"><summary>Notes of the 1869 editors</summary><ol>"
                + "".join(f"<li>{inline_md(re.sub(r'^\[\d+-(\d+)\]\s*', '', a))}</li>" for a in app)
                + "</ol></details>") if app else ""
        chapters.append(f'<section class="ch" id="{anchor}"><h2>{t}</h2>{"".join(body)}{appx}</section>')
    title = title or book.name
    heads = "".join(f'<div class="c {l}"><b>{ESC(lname[l])}</b> <span>{ESC(label[l])}</span></div>'
                    for l in langs + ["en"])
    toggles = "".join(f'<label><input type="checkbox" data-col="{l}"> {ESC(lname[l])}</label>'
                      for l in langs + ["en"])
    page = (TEMPLATE.replace("%TITLE%", ESC(title))
            .replace("%READER%", f'<a href="{ESC(reader)}">Read the English</a>' if reader else "")
            .replace("%TOGGLES%", toggles).replace("%NAV%", "".join(nav))
            .replace("%HEADS%", heads).replace("%BODY%", "\n".join(chapters)))
    Path(out).write_text(page, encoding="utf-8")
    return out


TEMPLATE = """<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>%TITLE% · Latin, French, English</title>
<style>
:root{--bg:#fbf8f1;--fg:#262320;--dim:#7a7268;--line:#e2dccf;--acc:#7b3f16}
@media (prefers-color-scheme:dark){:root{--bg:#1c1a17;--fg:#e9e4da;--dim:#9b9387;--line:#38332c;--acc:#e0a271}}
*{box-sizing:border-box}html{scroll-padding-top:7.5rem}
body{background:var(--bg);color:var(--fg);font:17px/1.55 Georgia,"Iowan Old Style",serif;margin:0}
header{position:sticky;top:0;z-index:2;background:var(--bg);border-bottom:1px solid var(--line);padding:.6rem 16px}
.bar{display:flex;flex-wrap:wrap;gap:.6rem 1.2rem;align-items:center;font:14px system-ui,sans-serif;max-width:1500px;margin:0 auto}
.bar h1{font:600 15px system-ui,sans-serif;margin:0;flex:1 1 100%}
.bar label{white-space:nowrap;cursor:pointer}.bar select{max-width:100%;font:inherit}
.bar a{color:var(--acc)}
main{max-width:1500px;margin:0 auto;padding:0 16px 4rem}
.heads,.row{display:grid;grid-template-columns:repeat(var(--cols,2),minmax(0,1fr));gap:1.4rem}
.heads{font:13px/1.35 system-ui,sans-serif;color:var(--dim);padding:.8rem 0;border-bottom:1px solid var(--line)}
.heads b{color:var(--fg);display:block}
.row{padding:.5rem 0;border-bottom:1px solid var(--line)}
.c p{margin:0 0 .6em}.fr{font-size:.95em}.la{font-size:.97em}
h2{font:600 1.15rem/1.3 Georgia,serif;margin:2.2rem 0 .4rem;color:var(--acc)}
.n{font:600 .8em system-ui,sans-serif;color:var(--dim)}
.sc{font-variant:small-caps}.fn{display:block;font-size:.85em;color:var(--dim);margin:.3em 0 .3em 1em}
.fn::before{content:"Note: ";font-style:italic}
blockquote{margin:.4em 0 .6em 1em}.sub{font-style:italic}
sup.app{font:600 .65em system-ui,sans-serif;color:var(--acc)}
details.appx{font-size:.88em;color:var(--dim);margin:.8rem 0}details.appx summary{cursor:pointer;font:13px system-ui,sans-serif}
.dim{color:var(--dim)}
body.no-la .la,body.no-fr .fr,body.no-en .en{display:none}
@media (max-width:760px){.heads,.row{grid-template-columns:1fr}.heads{display:none}
 .c.la::before,.c.fr::before,.c.en::before{display:block;font:600 11px system-ui,sans-serif;text-transform:uppercase;color:var(--dim)}
 .c.la::before{content:"Latin"}.c.fr::before{content:"French"}.c.en::before{content:"English"}}
</style></head><body class="no-fr">
<header><div class="bar"><h1>%TITLE% · Calvin's Latin and French beside the English</h1>
%TOGGLES% <select id="go"><option value="">Go to…</option>%NAV%</select> %READER%</div></header>
<main><div class="heads">%HEADS%</div>
%BODY%
</main>
<script>
(function(){
  var KEY="parallel-cols", on={la:true,fr:false,en:true};
  try{var s=JSON.parse(localStorage.getItem(KEY)||"null");if(s)on=s;}catch(e){}
  var boxes=document.querySelectorAll("input[data-col]");
  function apply(){
    var n=0;["la","fr","en"].forEach(function(l){document.body.classList.toggle("no-"+l,!on[l]);if(on[l]&&document.querySelector(".c."+l))n++;});
    document.documentElement.style.setProperty("--cols",Math.max(n,1));
    boxes.forEach(function(b){b.checked=!!on[b.dataset.col];});
  }
  boxes.forEach(function(b){b.addEventListener("change",function(){
    on[b.dataset.col]=b.checked;
    if(!on.la&&!on.fr&&!on.en){on[b.dataset.col]=true;}
    try{localStorage.setItem(KEY,JSON.stringify(on));}catch(e){}
    apply();});});
  document.getElementById("go").addEventListener("change",function(){if(this.value)location.hash=this.value;});
  apply();
})();
</script>
</body></html>"""


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("book")
    ap.add_argument("volume", help='the volume folder, e.g. "vol-1"')
    ap.add_argument("out")
    ap.add_argument("--title")
    ap.add_argument("--reader")
    a = ap.parse_args(argv)
    build(a.book, a.volume.rstrip("/"), a.out, a.title, a.reader)


if __name__ == "__main__":
    main()
