#!/usr/bin/env python3
"""
A reader page for the web: one self-contained HTML file made from a built
EPUB, so the page reads exactly as the ebook does (the same renderer, front
matter, contents and notes), in one design for every book.

  python3 epub_reader.py BOOK.epub OUT.html [--compare URL] [--epub URL] [--pdf URL]
                         [--version v6.1]

The EPUB's pages are joined in spine order (their ids are unique through the
book; links between pages become links within the page), its images are
inlined, and its own stylesheets are kept under the reader's, so a book's
small capitals, epigraphs, lists and tables look as they do in the ebook.

The reader adds: a top bar (contents, text size, paper / light / dark, links
to the comparison page and the downloads given), a contents drawer that
follows the reading, notes that open in a card where they are called, a
progress bar, and the reader's place and settings remembered in the browser.

Scripture references become links that open the passage on the page, through
the fetch(bible) enhancer (https://fetch.bible/access/enhancer/), in the BSB
only (--bible; --bible none leaves it out). It is the one thing the page loads
from elsewhere.
"""

import argparse
import base64
import html
import mimetypes
import posixpath
import re
import zipfile

from lxml import etree

XHTML = "http://www.w3.org/1999/xhtml"
OPF = "http://www.idpf.org/2007/opf"
EPUB_NS = "http://www.idpf.org/2007/ops"
NS = {"x": XHTML, "o": OPF}


def read_epub(path):
    z = zipfile.ZipFile(path)
    container = etree.fromstring(z.read("META-INF/container.xml"))
    opf_path = container.find(".//{*}rootfile").get("full-path")
    base = posixpath.dirname(opf_path)
    opf = etree.fromstring(z.read(opf_path))
    items = {i.get("id"): i for i in opf.iterfind(".//o:manifest/o:item", NS)}
    spine = [items[r.get("idref")].get("href") for r in opf.iterfind(".//o:spine/o:itemref", NS)]
    nav = next((i.get("href") for i in items.values()
                if "nav" in (i.get("properties") or "").split()), None)
    css = [i.get("href") for i in items.values() if i.get("media-type") == "text/css"]
    title = opf.findtext(".//{http://purl.org/dc/elements/1.1/}title") or ""
    author = opf.findtext(".//{http://purl.org/dc/elements/1.1/}creator") or ""
    lang = opf.findtext(".//{http://purl.org/dc/elements/1.1/}language") or "en"

    def get(href):
        return z.read(posixpath.join(base, href) if base else href)
    return dict(get=get, spine=spine, nav=nav, css=css, title=title, author=author, lang=lang)


def data_uri(name, data):
    mt = mimetypes.guess_type(name)[0] or "application/octet-stream"
    return f"data:{mt};base64,{base64.b64encode(data).decode()}"


def body_html(xml, href, get):
    """The inner HTML of a page's body, as HTML: links to other pages made
    links within the page, images inlined, EPUB-only attributes dropped."""
    doc = etree.fromstring(xml)
    body = doc.find(f"{{{XHTML}}}body")
    for el in body.iter():
        if not isinstance(el.tag, str):
            continue
        for att in list(el.attrib):
            if att.startswith(f"{{{EPUB_NS}}}"):
                del el.attrib[att]
        if el.tag == f"{{{XHTML}}}a" and el.get("href"):
            h = el.get("href")
            if not re.match(r"[a-z]+:", h):
                page, _, frag = h.partition("#")
                el.set("href", "#" + (frag or "page-" + re.sub(r"\W+", "-", page)))
        if el.tag == f"{{{XHTML}}}img" and el.get("src") and not el.get("src").startswith("data:"):
            src = posixpath.normpath(posixpath.join(posixpath.dirname(href), el.get("src")))
            el.set("src", data_uri(src, get(src)))
    out = []
    if body.text and body.text.strip():
        out.append(html.escape(body.text))
    for c in body:
        s = etree.tostring(c, method="html", encoding="unicode")
        out.append(re.sub(r'\sxmlns(:\w+)?="[^"]*"', "", s))
    return "".join(out)


def contents(nav_xml):
    """The EPUB's contents list, hrefs made links within the page."""
    doc = etree.fromstring(nav_xml)
    toc = next((n for n in doc.iter(f"{{{XHTML}}}nav")
                if n.get(f"{{{EPUB_NS}}}type") == "toc"), None)
    if toc is None:
        return ""
    ol = toc.find(f"{{{XHTML}}}ol")
    for a in ol.iter(f"{{{XHTML}}}a"):
        page, _, frag = (a.get("href") or "").partition("#")
        a.set("href", "#" + (frag or "page-" + re.sub(r"\W+", "-", page)))
    return re.sub(r'\sxmlns(:\w+)?="[^"]*"', "",
                  etree.tostring(ol, method="html", encoding="unicode"))


CSS = r"""
:root { --bg:#faf6ef; --fg:#2a1f14; --muted:#6b5a48; --rule:#c8a97e; --accent:#7a3e1a;
  --head:#4a2c10; --panel:#fdf9f3; --shadow:rgba(0,0,0,.18); --size:19px; --measure:36em; }
:root[data-theme="light"] { --bg:#ffffff; --fg:#1d1d1d; --muted:#666; --rule:#cfc6b8;
  --accent:#7a3e1a; --head:#2b2b2b; --panel:#fafafa; }
:root[data-theme="dark"] { --bg:#1b1916; --fg:#e8e1d4; --muted:#a69c8c; --rule:#5a4c3a;
  --accent:#e0b07a; --head:#efe2cc; --panel:#24211d; --shadow:rgba(0,0,0,.5); }
@media (prefers-color-scheme: dark) {
  :root:not([data-theme]) { --bg:#1b1916; --fg:#e8e1d4; --muted:#a69c8c; --rule:#5a4c3a;
    --accent:#e0b07a; --head:#efe2cc; --panel:#24211d; --shadow:rgba(0,0,0,.5); } }
html { font-size:var(--size); scroll-padding-top:4rem; -webkit-text-size-adjust:100%; }
body { margin:0; padding:0; background:var(--bg); color:var(--fg);
  font-family:"Iowan Old Style","Palatino Linotype",Palatino,"Book Antiqua",Georgia,serif;
  line-height:1.65; }
main { max-width:var(--measure); margin:0 auto; padding:4.5rem 1.25rem 6rem; }
main a { color:var(--accent); }
main p { hyphens:auto; }
/* the ebook's page breaks become space on the page */
main h2 { margin:4rem 0 2rem; padding:.7em 0; border-top:1px solid var(--rule);
  border-bottom:1px solid var(--rule); color:var(--head); font-size:1.5rem; break-after:auto; }
main h3 { padding-top:0; margin:4.5rem 0 1.5rem; color:var(--head); break-before:auto; }
main h4 { margin:2.5rem 0 1rem; color:var(--head); font-weight:600; text-align:center;
  font-size:1rem; line-height:1.45; }
main h3 + p, main h4 + p, main h2 + p, main .epigraph + p { text-indent:0; }
main > section + section { margin-top:2rem; }
section#cover { text-align:center; margin:0 0 3rem; }
section#cover img { max-width:min(100%, 380px); max-height:80vh; height:auto;
  box-shadow:0 6px 28px var(--shadow); margin:0 auto; }
section#front { text-align:center; margin:2rem 0 4rem; font-size:.92rem; color:var(--muted); }
section#front p { text-indent:0; text-align:center; margin:.4em 0; }
section#front p.title { font-size:2rem; color:var(--head); margin:0 0 .3em; line-height:1.25; }
section#front p.subtitle { font-size:1.05rem; font-style:italic; color:var(--fg); margin-bottom:1.5em; }
section#front img.licence { max-width:180px; height:auto; }
:root[data-theme="dark"] section#front img.licence { filter:invert(.85); }
sup { font-size:.68em; line-height:0; }
a.noteref { text-decoration:none; color:var(--accent); padding:0 .08em; }
aside.note { font-size:.82rem; line-height:1.5; color:var(--muted); margin:0; }
aside.note:first-of-type { margin-top:2.5rem; padding-top:.8rem; border-top:1px solid var(--rule); }
aside.note p { text-indent:0; margin:.15em 0; text-align:left; }
aside.note:target { background:color-mix(in srgb, var(--rule) 25%, transparent); }
img { max-width:100%; height:auto; }

/* the bar */
#bar { position:fixed; top:0; left:0; right:0; z-index:20; display:flex; align-items:center;
  gap:.4rem; padding:.45rem .8rem; background:color-mix(in srgb, var(--bg) 92%, transparent);
  backdrop-filter:blur(6px); border-bottom:1px solid color-mix(in srgb, var(--rule) 60%, transparent);
  font:14px/1.2 system-ui,-apple-system,"Segoe UI",sans-serif; }
#bar .t { flex:1; min-width:0; text-align:center; color:var(--muted); white-space:nowrap;
  overflow:hidden; text-overflow:ellipsis; }
#bar .t b { color:var(--fg); font-weight:600; }
#bar button, #bar a.btn { font:inherit; color:var(--fg); background:transparent;
  border:1px solid transparent; border-radius:8px; padding:.4rem .6rem; cursor:pointer;
  text-decoration:none; white-space:nowrap; }
#bar button:hover, #bar a.btn:hover { border-color:var(--rule); }
#progress { position:fixed; top:0; left:0; height:2px; background:var(--accent); z-index:21; width:0; }
@media (max-width:600px) { #bar .t { display:none; } #bar .links { margin-left:auto; }
  main p { text-align:left; } }

/* drawers and popovers */
#toc, #settings { position:fixed; z-index:30; background:var(--panel); color:var(--fg);
  font:15px/1.45 system-ui,-apple-system,"Segoe UI",sans-serif; box-shadow:0 8px 32px var(--shadow); }
#toc { top:0; left:0; bottom:0; width:min(360px, 88vw); overflow-y:auto; padding:1rem 1.1rem 2rem;
  transform:translateX(-102%); visibility:hidden; transition:transform .25s ease, visibility 0s .25s;
  border-right:1px solid var(--rule); }
#toc.open { transform:none; visibility:visible; transition:transform .25s ease; }
#toc h2 { font:600 13px system-ui,sans-serif; letter-spacing:.1em; text-transform:uppercase;
  color:var(--muted); margin:.3rem 0 1rem; padding:0; border:0; display:flex;
  justify-content:space-between; align-items:center; text-align:left; font-style:normal;
  page-break-after:auto; break-after:auto; }
#toc h2 button { font-size:20px; line-height:1; border:0; background:none; color:var(--muted); cursor:pointer; }
#toc ol { list-style:none; padding-left:0; margin:0; }
#toc ol ol { padding-left:1rem; margin:.1rem 0 .4rem; font-size:.92em; }
#toc a { display:block; color:var(--fg); text-decoration:none; padding:.22rem .4rem; border-radius:6px; }
#toc a:hover { background:color-mix(in srgb, var(--rule) 25%, transparent); }
#toc a.here { background:color-mix(in srgb, var(--rule) 40%, transparent); font-weight:600; }
#settings { top:3.2rem; right:.8rem; width:260px; border-radius:12px; padding:1rem;
  border:1px solid var(--rule); display:none; }
#settings.open { display:block; }
#settings .row { display:flex; align-items:center; justify-content:space-between; margin:.3rem 0 .8rem; }
#settings .lab { font-size:12px; letter-spacing:.08em; text-transform:uppercase; color:var(--muted); }
#settings .seg { display:flex; border:1px solid var(--rule); border-radius:8px; overflow:hidden; }
#settings .seg button { flex:1; font:inherit; padding:.45rem .7rem; border:0; background:transparent;
  color:var(--fg); cursor:pointer; }
#settings .seg button + button { border-left:1px solid var(--rule); }
#settings .seg button[aria-pressed="true"] { background:var(--fg); color:var(--bg); }
#veil { position:fixed; inset:0; z-index:25; background:rgba(0,0,0,.3); display:none; }
#veil.open { display:block; }
#card { position:fixed; left:50%; bottom:1rem; transform:translateX(-50%); z-index:35;
  width:min(560px, calc(100vw - 2rem)); max-height:45vh; overflow:auto; background:var(--panel);
  color:var(--fg); border:1px solid var(--rule); border-radius:12px; box-shadow:0 8px 32px var(--shadow);
  padding:.9rem 1.1rem 1rem; font-size:.9rem; line-height:1.5; display:none; }
#card.open { display:block; }
#card p { margin:.2em 0; text-indent:0; text-align:left; }
#card .x { float:right; border:0; background:none; color:var(--muted); font-size:20px;
  line-height:1; cursor:pointer; margin:-.2rem -.3rem 0 .5rem; }
#card .go { display:inline-block; margin-top:.4rem; font:13px system-ui,sans-serif; color:var(--accent); }
#top { position:fixed; right:1rem; bottom:1rem; z-index:15; font:13px system-ui,sans-serif;
  border:1px solid var(--rule); background:var(--panel); color:var(--fg); border-radius:20px;
  padding:.45rem .8rem; cursor:pointer; opacity:0; pointer-events:none; transition:opacity .2s; }
#top.show { opacity:.9; pointer-events:auto; }
@media print {
  #bar, #progress, #toc, #settings, #veil, #card, #top { display:none !important; }
  main { padding:0; max-width:none; } :root { --bg:#fff; --fg:#000; }
}
"""

JS = r"""
(function () {
  const root = document.documentElement, KEY = 'fgb:' + BOOK;
  const store = { get(k) { try { return JSON.parse(localStorage.getItem(KEY + ':' + k)); } catch (e) { return null; } },
                  set(k, v) { try { localStorage.setItem(KEY + ':' + k, JSON.stringify(v)); } catch (e) {} } };
  const $ = s => document.querySelector(s);
  // settings: text size and theme
  let size = store.get('size') || 19;
  const theme = store.get('theme');
  function applySize() { root.style.setProperty('--size', size + 'px'); store.set('size', size); }
  function applyTheme(t) {
    if (t) root.dataset.theme = t; else delete root.dataset.theme;
    document.querySelectorAll('[data-theme-btn]').forEach(b =>
      b.setAttribute('aria-pressed', String(b.dataset.themeBtn === (t || 'auto'))));
    store.set('theme', t);
  }
  applySize(); applyTheme(theme);
  $('#smaller').onclick = () => { size = Math.max(14, size - 1); applySize(); };
  $('#bigger').onclick = () => { size = Math.min(28, size + 1); applySize(); };
  document.querySelectorAll('[data-theme-btn]').forEach(b => b.onclick = () =>
    applyTheme(b.dataset.themeBtn === 'auto' ? null : b.dataset.themeBtn));
  // drawers
  const toc = $('#toc'), settings = $('#settings'), veil = $('#veil'), card = $('#card');
  function closeAll() { toc.classList.remove('open'); settings.classList.remove('open');
    veil.classList.remove('open'); card.classList.remove('open'); }
  $('#open-toc').onclick = () => { closeAll(); toc.classList.add('open'); veil.classList.add('open');
    const h = toc.querySelector('a.here'); if (h) h.scrollIntoView({ block: 'center' }); };
  $('#close-toc').onclick = closeAll;
  $('#open-settings').onclick = e => { e.stopPropagation(); const o = settings.classList.contains('open');
    closeAll(); if (!o) settings.classList.add('open'); };
  veil.onclick = closeAll;
  document.addEventListener('click', e => { if (!e.target.closest('#settings, #open-settings')) settings.classList.remove('open'); });
  document.addEventListener('keydown', e => { if (e.key === 'Escape') closeAll(); });
  toc.querySelectorAll('a').forEach(a => a.addEventListener('click', closeAll));
  // notes: a card where the note is called
  document.addEventListener('click', e => {
    const a = e.target.closest('a.noteref');
    if (!a) { if (!e.target.closest('#card')) card.classList.remove('open'); return; }
    const note = document.getElementById(a.getAttribute('href').slice(1));
    if (!note) return;
    e.preventDefault();
    const body = note.cloneNode(true);
    body.querySelectorAll('a[role="doc-backlink"]').forEach(x => x.remove());
    card.innerHTML = '<button class="x" aria-label="Close">×</button>' + body.innerHTML +
      '<a class="go" href="#' + note.id + '">Go to the note</a>';
    // scripture links in the note (the enhancer's): a click passes to the original
    const orig = note.querySelectorAll('.fb-enhancer-link');
    card.querySelectorAll('.fb-enhancer-link').forEach((c, i) => c.addEventListener('click', ev => {
      ev.preventDefault(); ev.stopPropagation(); card.classList.remove('open');
      if (orig[i]) orig[i].click(); }));
    card.querySelector('.x').onclick = () => card.classList.remove('open');
    card.querySelector('.go').onclick = () => card.classList.remove('open');
    card.classList.add('open');
  });
  // where the reader is: contents highlight, progress, the place remembered
  const links = new Map();
  toc.querySelectorAll('a[href^="#"]').forEach(a => links.set(a.getAttribute('href').slice(1), a));
  const marks = [...document.querySelectorAll('main [id]')].filter(el => links.has(el.id));
  const bar = $('#progress'), top = $('#top');
  let ticking = false;
  function onScroll() {
    ticking = false;
    const h = document.documentElement.scrollHeight - innerHeight;
    bar.style.width = (h > 0 ? 100 * scrollY / h : 0) + '%';
    top.classList.toggle('show', scrollY > innerHeight * 2);
    let cur = null;
    for (const m of marks) { if (m.getBoundingClientRect().top < 120) cur = m; else break; }
    toc.querySelectorAll('a.here').forEach(a => a.classList.remove('here'));
    if (cur) { links.get(cur.id).classList.add('here'); store.set('at', cur.id); }
    store.set('y', scrollY / Math.max(1, document.documentElement.scrollHeight));
  }
  addEventListener('scroll', () => { if (!ticking) { ticking = true; requestAnimationFrame(onScroll); } });
  top.onclick = () => scrollTo({ top: 0, behavior: 'smooth' });
  // back where the reader left off (not when the address names a place)
  addEventListener('load', () => {
    const y = store.get('y');
    if (!location.hash && y) scrollTo(0, y * document.documentElement.scrollHeight);
    onScroll();
  });
})();
"""


# the outline (a book with OUTLINE_MARKS: its numbered points are p.point<depth>,
# depth 0 the top): where the reader is in it, a map of it, and folding
OUTLINE_CSS = r"""
#bar { flex-wrap:wrap; }
#bar #where { flex-basis:100%; display:none; gap:.35rem; align-items:baseline; width:100%; margin:0;
  padding:.15rem max(0px, calc((100% - 36rem) / 2)) 0;   /* in line with the text (main's 36em) */ border:0; background:none;
  font:12.5px/1.4 system-ui,-apple-system,"Segoe UI",sans-serif; color:var(--muted);
  white-space:nowrap; overflow:hidden; cursor:pointer; text-align:left; }
#bar #where.show { display:flex; }
html { scroll-padding-top:5.5rem; }   /* room for #where, shown or not */
#where .c { display:flex; gap:.3em; min-width:0; max-width:18em; flex:0 3 auto; overflow:hidden; }
#where .c:first-child { flex:none; max-width:none; }
#where .c:last-child { max-width:none; flex-shrink:1; }
#where .c + .c::before { content:"›"; flex:none; margin-right:.05rem; color:var(--rule); }
#where .m { flex:none; color:var(--fg); font-weight:600; }
#where .lb { min-width:0; overflow:hidden; text-overflow:ellipsis; }
@media (max-width:600px) { #where .c:not(:last-child) .lb, #where .c.sub { display:none; }
  #where .c:not(:last-child) { flex:none; } }
#toc .tabs { display:flex; gap:.2rem; }
#toc .tabs button { font:inherit; letter-spacing:inherit; text-transform:inherit; color:var(--muted);
  border:0; border-bottom:2px solid transparent; background:none; padding:.2rem .3rem; cursor:pointer; }
#toc .tabs button[aria-selected="true"] { color:var(--fg); border-bottom-color:var(--accent); }
#outline .ch { font-weight:600; margin:1.1rem 0 .2rem; }
#outline .hd { font-style:italic; color:var(--muted); margin:.6rem 0 .1rem; padding-left:.4rem; }
#outline a { padding-top:.15rem; padding-bottom:.15rem; font-size:.93em; }
#outline a .m { font-weight:600; margin-right:.3em; }
#outline a.up { background:color-mix(in srgb, var(--rule) 15%, transparent); }
@media screen { .ol-hid { display:none !important; } }
main p.point .omark.fold { cursor:pointer; border-radius:4px; padding:0 .1em; margin:0 -.1em; }
main p.point .omark.fold:hover { background:color-mix(in srgb, var(--rule) 35%, transparent); }
main p.point.folded .omark.fold { color:var(--accent); }
.ol-chip { display:block; margin:.25rem 0 .9rem; padding:.2rem .75rem; font:13px system-ui,sans-serif;
  color:var(--accent); background:transparent; border:1px dashed var(--rule); border-radius:14px;
  cursor:pointer; }
/* the point the map jumps to, lit for a moment */
@keyframes ol-flash {
  from { background-color:var(--flash); box-shadow:0 0 0 .4rem var(--flash); }
  to { background-color:transparent; box-shadow:0 0 0 .4rem transparent; } }
main p.ol-flash { --flash:color-mix(in srgb, var(--accent) 22%, transparent); border-radius:2px;
  animation:ol-flash 1.6s ease-out .15s backwards; }
@media (prefers-reduced-motion: reduce) { main p.ol-flash { animation:none;
  background-color:var(--flash); box-shadow:0 0 0 .4rem var(--flash); } }
@media print { #where, .ol-chip { display:none !important; } }
"""

OUTLINE_JS = r"""
(function () {
  const pts = [...document.querySelectorAll('main p.point')];
  if (!pts.length) return;
  const KEY = 'fgb:' + BOOK + ':fold';
  const $ = s => document.querySelector(s);
  const ORD = /^(first|second|third|fourth|fifth|sixth|seventh|eighth|ninth|tenth|eleventh|twelfth|last)(ly)?\b[,.;:]?\s*/i;
  function words(p) {
    const c = p.cloneNode(true);
    c.querySelectorAll('.omark, a.noteref, sup').forEach(x => x.remove());
    return c.textContent.replace(/\s+/g, ' ').trim();
  }
  function label(t) {
    t = t.replace(ORD, '');
    const m = t.match(/^(.{12,80}?)[.;:?!](\s|$)/);
    let s = m ? m[1] : t;
    if (s.length > 72) s = s.slice(0, 72).replace(/\s+\S*$/, '') + '…';
    return s.charAt(0).toUpperCase() + s.slice(1);
  }
  const esc = s => s.replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' })[c]);
  // the tree: each point owns the paragraphs after it up to the next point or heading,
  // but for one the edition sets back at a level above (data-level)
  const nodes = [], seq = [], owner = new Map();
  let n = 0;
  document.querySelectorAll('main > section').forEach(sec => {
    let stack = [], heads = [];
    for (const el of sec.children) {
      const h = /^H([1-6])$/.exec(el.tagName);
      if (h) {
        const lv = +h[1];
        heads = heads.filter(x => x.lv < lv).concat([{ lv, text: el.textContent.trim(), el }]);
        stack = [];
        seq.push({ el, heads, node: null });
      } else if (el.matches('p.point')) {
        const depth = +((/\bpoint(\d)\b/.exec(el.className) || [0, 0])[1]);
        while (stack.length && stack[stack.length - 1].depth >= depth) stack.pop();
        const om = el.querySelector('.omark'), t = words(el);
        const mark = om ? om.textContent.trim() : ((ORD.exec(t) || [''])[0].replace(/[,.;:\s]+$/, ''));
        const node = { el, depth, lvl: +(el.dataset.level || depth), mark, label: label(t), parent: stack[stack.length - 1] || null,
                       kids: [], body: [], heads, folded: false, chip: null, om };
        if (node.parent) node.parent.kids.push(node);
        if (!el.id) el.id = 'pt-' + (++n);
        stack.push(node); nodes.push(node); seq.push({ el, heads, node });
      } else if (stack.length && !el.matches('aside, [id^="page-"]')) {
        if (el.dataset.level) while (stack.length > 1 && stack[stack.length - 1].lvl > +el.dataset.level) stack.pop();
        stack[stack.length - 1].body.push(el); owner.set(el, stack[stack.length - 1]);
      }
    }
  });
  // folding: a folded point keeps its own paragraphs; its points, and theirs, wait
  // behind a chip where the first of them was (never text at the point's own level)
  const count = nd => nd.kids.reduce((a, k) => { const c = count(k); return [a[0] + 1 + c[0], a[1] + 1 + k.body.length + c[1]]; },
                                     [0, 0]);
  nodes.forEach(nd => {
    if (!nd.kids.length) return;
    const [k, p] = count(nd), b = document.createElement('button');
    b.className = 'ol-chip';
    b.textContent = '▸ ' + k + (k === 1 ? ' point' : ' points') + (p > k ? ', ' + p + ' paragraphs' : '');
    b.onclick = () => { nd.folded = false; apply(); };
    nd.kids[0].el.before(b); nd.chip = b;
    if (nd.om) { nd.om.classList.add('fold'); nd.om.title = 'Fold or open this point';
      nd.om.onclick = () => { nd.folded = !nd.folded; apply(); }; }
  });
  function apply() {
    nodes.forEach(nd => {
      const gone = !!nd.parent && (nd.parent.gone || nd.parent.folded);
      nd.gone = gone;
      nd.el.classList.toggle('ol-hid', gone);
      nd.el.classList.toggle('folded', nd.folded && !!nd.chip);
      nd.body.forEach(el => el.classList.toggle('ol-hid', gone));
      if (nd.chip) nd.chip.classList.toggle('ol-hid', gone || !nd.folded);
    });
    visible = seq.filter(s => !s.node || !s.node.gone);
    onScroll();
  }
  let level = 0;
  try { level = +JSON.parse(localStorage.getItem(KEY)) || 0; } catch (e) {}
  function setLevel(l) {
    level = l;
    try { localStorage.setItem(KEY, JSON.stringify(l)); } catch (e) {}
    nodes.forEach(nd => nd.folded = !!l && nd.depth === l - 1);
    document.querySelectorAll('[data-fold-btn]').forEach(b => b.setAttribute('aria-pressed', String(+b.dataset.foldBtn === l)));
    apply();
  }
  document.querySelectorAll('[data-fold-btn]').forEach(b => b.onclick = () => {
    const el = current() && current().el, y = el && el.getBoundingClientRect().top;
    setLevel(+b.dataset.foldBtn);
    if (el && !el.classList.contains('ol-hid')) scrollBy(0, el.getBoundingClientRect().top - y);
  });
  // a place the reader goes to (a note, a contents or outline link) is opened first
  function reveal(el) {
    let nd = owner.get(el) || nodes.find(x => x.el === el);
    if (!nd) return;
    for (let p = nd.parent; p; p = p.parent) p.folded = false;
    apply();
  }
  document.addEventListener('click', e => {
    const a = e.target.closest('a[href^="#"]');
    if (a && a.getAttribute('href').length > 1) {
      const t = document.getElementById(a.getAttribute('href').slice(1));
      if (t) reveal(t.closest('main > section > *') || t);
    }
  }, true);
  // where the reader is: the headings and points above the line under the bar
  const where = $('#where');
  let visible = seq;
  // the reader's line: a third of the way down the page below the bar, where the eye
  // reads, not the bar's edge (a long paragraph would name the point before it)
  function current() {
    const top = $('#bar').getBoundingClientRect().bottom, line = top + (innerHeight - top) / 3;
    let lo = 0, hi = visible.length - 1, at = -1;
    while (lo <= hi) { const mid = (lo + hi) >> 1;
      if (visible[mid].el.getBoundingClientRect().top < line) { at = mid; lo = mid + 1; } else hi = mid - 1; }
    return at < 0 ? null : visible[at];
  }
  let ticking = false, here = null;
  function onScroll() {
    ticking = false;
    const s = current();
    here = s;
    if (!s) { where.classList.remove('show'); return; }
    const chain = [];
    for (let p = s.node; p; p = p.parent) chain.unshift(p);
    const top = s.heads[0], sub = s.heads.length > 1 ? s.heads[s.heads.length - 1] : null;
    where.innerHTML = (top ? '<span class="c"><span class="m">' + esc(top.text) + '</span></span>' : '') +
      (sub ? '<span class="c sub"><span class="lb">' + esc(sub.text) + '</span></span>' : '') +
      chain.map(p => '<span class="c"><span class="m">' + esc(p.mark) + '</span> <span class="lb">' +
                     esc(p.label) + '</span></span>').join('');
    where.classList.add('show');
  }
  addEventListener('scroll', () => { if (!ticking) { ticking = true; requestAnimationFrame(onScroll); } });
  // the map: every chapter's headings and points, the reader's place marked
  const list = $('#toc-list'), map = $('#outline'), tabs = document.querySelectorAll('#toc [data-tab]');
  function tab(t) {
    tabs.forEach(b => b.setAttribute('aria-selected', String(b.dataset.tab === t)));
    list.hidden = t !== 'contents'; map.hidden = t !== 'outline';
    if (t === 'outline') drawMap();
  }
  tabs.forEach(b => b.onclick = () => tab(b.dataset.tab));
  // the point jumped to lit for a moment, so the eye finds it
  let flashed = null;
  function flash(el) {
    if (!el) return;
    if (flashed) { flashed.classList.remove('ol-flash'); clearTimeout(flashed.flashTimer); }
    void el.offsetWidth;          // the animation starts again on the same point
    el.classList.add('ol-flash'); flashed = el;
    el.flashTimer = setTimeout(() => el.classList.remove('ol-flash'), 2200);
  }
  function drawMap() {
    const up = new Set();
    for (let p = here && here.node; p; p = p.parent) up.add(p);
    let out = '';
    seq.forEach(s => {
      if (!s.node) {
        const lv = s.heads[s.heads.length - 1];
        if (s.heads.length === 1) out += '<div class="ch">' + esc(lv.text) + '</div>';
        else if (seq.some(x => x.node && x.heads.includes(lv))) out += '<div class="hd">' + esc(lv.text) + '</div>';
        return;
      }
      const nd = s.node;
      out += '<a href="#' + nd.el.id + '" style="padding-left:' + (0.4 + nd.depth * 1.1) + 'rem"' +
        (here && here.node === nd ? ' class="here"' : up.has(nd) ? ' class="up"' : '') +
        '><span class="m">' + esc(nd.mark) + '</span>' + esc(nd.label) + '</a>';
    });
    map.innerHTML = out;
    map.querySelectorAll('a').forEach(a => a.addEventListener('click', () => {
      $('#close-toc').click();
      flash(document.getElementById(a.getAttribute('href').slice(1)));
    }));
    const h = map.querySelector('a.here') || map.querySelector('a.up');
    if (h) h.scrollIntoView({ block: 'center' });
  }
  $('#open-toc').addEventListener('click', () => tab('contents'));
  where.onclick = () => { $('#open-toc').click(); tab('outline'); };
  setLevel(level);
  if (location.hash) { const t = document.getElementById(location.hash.slice(1)); if (t) reveal(t.closest('main > section > *') || t); }
})();
"""


def page(book, body, toc, a):
    outline = 'class="point ' in body
    links = []
    if a.compare:
        links.append(f'<a class="btn" href="{html.escape(a.compare)}" title="The printed text beside this edition">Compare</a>')
    if a.epub_url:
        links.append(f'<a class="btn" href="{html.escape(a.epub_url)}">EPUB</a>')
    if a.pdf:
        links.append(f'<a class="btn" href="{html.escape(a.pdf)}">PDF</a>')
    title = html.escape(book["title"])
    author = html.escape(book["author"])
    css = "\n".join(book["get"](c).decode("utf-8") for c in book["css"])
    ver = f" · {html.escape(a.version)}" if a.version else ""
    # scripture references as links to the passage, in the one translation given
    enhancer = ("" if a.bible == "none" else
                f'\n<script type="module" crossorigin src="https://collection.fetch.bible/enhance.js" '
                f'data-trans="{html.escape(a.bible)}"></script>')
    # the outline: where the reader is under the bar, its map beside the contents,
    # and how deep the points are shown
    where = ('\n<button id="where" aria-label="Where you are in the outline; open the outline"></button>'
             if outline else "")
    tabs = ('<span class="tabs" role="tablist"><button data-tab="contents" aria-selected="true">Contents</button>'
            '<button data-tab="outline" aria-selected="false">Outline</button></span>' if outline else "Contents")
    toc_body = (f'<div id="toc-list">{toc}</div><div id="outline" hidden></div>' if outline else toc)
    fold = ('\n<div class="lab">Outline levels shown</div>\n<div class="row"><div class="seg" style="flex:1">'
            '<button data-fold-btn="0">All</button><button data-fold-btn="3">3</button>'
            '<button data-fold-btn="2">2</button><button data-fold-btn="1">1</button></div></div>'
            if outline else "")
    return f"""<!doctype html>
<html lang="{html.escape(book['lang'])}"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title} — {author}</title>
<meta name="generator" content="colophon epub_reader.py">{enhancer}
<style>{css}</style>
<style>{CSS}</style>{f"<style>{OUTLINE_CSS}</style>" if outline else ""}
</head><body>
<div id="progress"></div>
<header id="bar">
<button id="open-toc" aria-label="Contents">☰ Contents</button>
<div class="t"><b>{title}</b> · {author}{ver}</div>
<span class="links">{''.join(links)}</span>
<button id="open-settings" aria-label="Reading settings">Aa</button>{where}
</header>
<nav id="toc" aria-label="Contents"><h2>{tabs} <button id="close-toc" aria-label="Close">×</button></h2>{toc_body}</nav>
<div id="settings" role="dialog" aria-label="Reading settings">
<div class="lab">Text size</div>
<div class="row"><div class="seg" style="flex:1"><button id="smaller" aria-label="Smaller">A−</button><button id="bigger" aria-label="Larger">A+</button></div></div>
<div class="lab">Page</div>
<div class="row"><div class="seg" style="flex:1"><button data-theme-btn="auto">Auto</button><button data-theme-btn="paper">Paper</button><button data-theme-btn="light">Light</button><button data-theme-btn="dark">Dark</button></div></div>{fold}
</div>
<div id="veil"></div>
<main>{body}</main>
<div id="card" role="dialog" aria-label="Note"></div>
<button id="top">↑ Top</button>
<script>const BOOK = {repr(book['title'] + (a.version or ''))};{JS}{OUTLINE_JS if outline else ''}</script>
</body></html>
"""


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("epub")
    ap.add_argument("out")
    ap.add_argument("--compare", help="link to the comparison page")
    ap.add_argument("--epub-link", dest="epub_url", help="link to the EPUB download")
    ap.add_argument("--pdf", help="link to the PDF download")
    ap.add_argument("--version", help="the edition's version, shown in the bar (v6.1)")
    ap.add_argument("--bible", default="eng_bsb",
                    help="the translation the fetch(bible) enhancer shows for scripture "
                         "references (default eng_bsb, the BSB); none: no enhancer")
    a = ap.parse_args()
    book = read_epub(a.epub)
    parts = []
    for href in book["spine"]:
        anchor = "page-" + re.sub(r"\W+", "-", href)
        parts.append(f'<div id="{anchor}"></div>' + body_html(book["get"](href), href, book["get"]))
    toc = contents(book["get"](book["nav"])) if book["nav"] else ""
    with open(a.out, "w", encoding="utf-8") as f:
        f.write(page(book, "\n".join(parts), toc, a))
    print(f"wrote {a.out}: {len(book['spine'])} pages")


if __name__ == "__main__":
    main()
