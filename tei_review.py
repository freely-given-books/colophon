#!/usr/bin/env python3
"""
A side-by-side reading copy of an enriched TEI edition: the text as printed
on the left, the edition on the right, block by block, every editorial
change marked. Open the HTML file in a browser; hover over a marked word (tap
it on a phone) to see what was printed, what the machine proposed and who
decided. On a narrow screen the two texts stack, printed first, and the
options fold away.

  python3 tei_review.py EDITION.tei.xml OUT.html [--before FILE] [--after FILE]
                        [--only vol-1/]

It is for reading only. Make changes in chapters/typ and rebuild the TEI
(build_tei.py --review), then run this again.

Both columns come from the ebook renderer (tei_to_html.HtmlR), so they read
exactly as the ebook does: the left column is the orig layer (with printed
page numbers), the right the reg layer. One row is one block of the TEI; a
block the edition runs on from the one before is marked with a return
arrow instead of being joined, so the rows stay aligned.

Modern matter that is not in the TEI (a foreword, an abbreviations guide)
can be shown too, with the same --before/--after files as tei_epub.py: a
.typ file is rendered with Typst's HTML export, a .html file is a fragment.
It fills the edition column; the printed column says it is not in print.
"""

import argparse
import collections
import html
import json
import re
from pathlib import Path

from lxml import etree

from tei_extract import R, T, collapse, local, following_trailers
from tei_to_html import HtmlR, curl, finish, NOTEREF_GAP, tei_title, file_ident
import layout
from tei_epub import typst_page

TYPES = [  # (class, label, shown by default)
    ("t-emendation", "wording", True),
    ("t-omission", "words left out", True),
    ("t-grammar", "grammar (thou, hath, -eth)", True),
    ("t-spelling", "spelling", True),
    ("t-case", "capitals", True),
    ("t-punctuation", "punctuation", True),
    ("t-spacing", "spacing", False),
    ("t-abbr", "abbreviations", False),
    ("t-supplied", "supplied letters", True),
    ("t-italic", "italics", False),
    ("t-note", "notes", True),
]


class Plain(R):
    """Plain text of a TEI fragment, for tooltips."""

    def esc(self, s):
        return s

    def after_call(self, prev):
        return False

    def sup(self, inner):
        return inner

    def emph(self, inner):
        return inner

    def footnote(self, body):
        return ""


def plain(layer, el, root_moved):
    p = Plain(layer)
    p.moved = root_moved
    t = collapse(p.inline(el) if len(el) or el.text else "").strip()
    return t or "(nothing)"


class ReviewR(HtmlR):
    """HtmlR with every <choice>, <supplied> and changed italic wrapped in a
    marked span, page breaks shown in the orig column and notes collected
    per row."""

    def __init__(self, layer, prefix, printed_year):
        super().__init__(layer)
        self.prefix = prefix
        self.year = printed_year

    def footnote(self, body):
        self.note_no += 1
        n = self.note_no
        self.notes.append((n, body))
        return (f'<a class="noteref" id="{self.prefix}nr-{n}" '
                f'href="#{self.prefix}fn-{n}"><sup>{n}</sup></a>')

    public = False
    rule_name = "machine"

    def by(self, ed):
        if ed:
            return "by the editor"
        return "by rule" if self.public else "by the machine"

    def marked(self, inner, cls, tip):
        tip = html.escape(tip, quote=True).replace("\n", "&#10;")
        if not inner.strip() and self.layer == "reg":
            # nothing in the edition: a caret; a space the edition adds keeps the space
            inner = '<span class="gone">‸</span>' + inner
        return f'<span class="ch {cls}" title="{tip}">{inner}</span>'

    def choice(self, c):
        inner = super().choice(c)
        orig, abbr = c.find(T + "orig"), c.find(T + "abbr")
        if orig is not None:
            regs = c.findall(T + "reg")
            if not regs:
                return inner
            ed = [x for x in regs if x.get("resp") == "#editor"]
            au = [x for x in regs if x.get("resp") == "#auto"]
            reg = (ed or au or regs)[0]
            who = self.by(ed)
            typ = reg.get("type") or "spelling"
            typ = {"abbreviation": "abbr"}.get(typ, typ)      # one toggle for both
            printed = plain("orig", orig, self.moved)
            modern = plain("reg", reg, self.moved)
            tip = f"{self.year}: {printed}\nedition: {modern}"
            if ed and au:
                tip += f"\n{self.rule_name} proposed: {plain('reg', au[0], self.moved)}"
            tip += f"\n{typ}, {who}"
            return self.marked(inner, f"t-{typ} {'ed' if ed else 'auto'}", tip)
        if abbr is not None:
            expan = c.find(T + "expan")
            ed = expan is not None and expan.get("resp") == "#editor"
            tip = (f"printed: {plain('orig', abbr, self.moved)}\n"
                   f"expanded: {(expan.text or '') if expan is not None else ''}\n"
                   f"abbreviation, {self.by(ed)}")
            return self.marked(inner, f"t-abbr {'ed' if ed else 'auto'}", tip)
        return inner

    def node(self, c, in_numbered=False):
        if not isinstance(c.tag, str):
            return ""
        n = local(c)
        if n == "pb" and self.layer == "orig" and c.get("n"):
            return f' <span class="pb">p.&#160;{html.escape(c.get("n"))}</span> '
        out = super().node(c, in_numbered)
        if n == "supplied":
            why = " ".join(x.text.strip() for x in c
                           if isinstance(x, etree._Comment) and x.text)
            ed = c.get("resp") == "#editor"
            tip = (f"supplied: letters lost in print ({c.get('reason', '')}), "
                   f"certainty {c.get('cert', '?')}, {self.by(ed)}"
                   + (f"\n{why}" if why else ""))
            return self.marked(out, f"t-supplied {'ed' if ed else 'auto'}", tip)
        if n == "hi" and c.get("ana") in ("#print-only", "#edition-only"):
            tip = ("italic in print, roman in the edition"
                   if c.get("ana") == "#print-only"
                   else "roman in print, italic in the edition")
            return self.marked(out, "t-italic ed", tip)
        if n == "note" and out and c.get("ana") in ("#edition-only", "#print-only"):
            n_, body = self.notes[-1]
            what = ("added by the editor" if c.get("ana") == "#edition-only"
                    else "dropped from the edition")
            self.notes[-1] = (n_, f'{body} <span class="ch t-note ed">[{what}]</span>')
        if n == "note" and out and c.get("target") and self.layer == "orig":
            n_, body = self.notes[-1]
            self.notes[-1] = (n_, f'{body} <span class="ch t-note ed">'
                                  f'[moved in the edition]</span>')
        if n == "anchor" and out:
            n_, body = self.notes[-1]
            self.notes[-1] = (n_, f'{body} <span class="ch t-note ed">'
                                  f'[moved here by the editor]</span>')
        return out

    def take_notes(self):
        notes, self.notes = self.notes, []
        if not notes:
            return ""
        items = "".join(
            f'<li id="{self.prefix}fn-{n}"><a href="#{self.prefix}nr-{n}">{n}.</a> '
            f'{curl(NOTEREF_GAP.sub(r"\1", body))}</li>' for n, body in notes)
        return f'<ol class="notes">{items}</ol>'


def rows(div, o, m):
    """(orig html, reg html, css class) for each block of a division."""
    out, page = [], ""
    for c in div:
        if not isinstance(c.tag, str):
            continue
        n = local(c)
        if n == "head":
            continue
        if n == "pb":
            if c.get("n"):
                page = f'<span class="pb">p.&#160;{html.escape(c.get("n"))}</span> '
            continue
        if n in ("div", "argument") or (n == "q" and c.find(T + "p") is not None):
            if n == "div":
                oh, mh = finish(o.heading(c)), finish(m.heading(c))
                if oh or mh:
                    out.append(("".join(oh), "".join(mh), "head"))
            out += rows(c, o, m)
            continue
        ob, mb = "".join(o.blocks([c])), "".join(m.blocks([c]))
        if not ob and not mb:
            continue
        if mb and c.get("prev"):
            mb = ('<span class="runon" title="the edition runs this on from the '
                  'paragraph before">↩ runs on</span>' + mb)
        out.append((page + ob + o.take_notes(), mb + m.take_notes(), ""))
        page = ""
    return out


def counts(*els):
    c = collections.Counter()
    for el in els:
        for reg in el.iter(T + "reg"):
            if reg.get("resp") == "#editor":
                c[reg.get("type") or "spelling"] += 1
    return c


def division_units(root, cfg):
    """(ident, title or None, [part elements], whole division?) per file."""
    files = layout.book_layout(root, cfg)
    if files is not None:
        for f in files:
            yield file_ident(f["file"]), f["file"], f["title"], f["parts"]
        return
    for div in root.iter(T + "div"):
        typ = div.get("type")
        if typ == "dedication":
            ident = "dedication"
        elif typ == "chapter":
            ident = f"chapter-{int(div.get('n')):02d}"
        else:
            continue
        yield ident, f"{ident}.typ", None, div


CSS = """
:root { --bg:#fbfaf7; --fg:#222; --muted:#6b6b6b; --rule:#dedbd2; --panel:#f1eee6;
  --ed:#fde68a; --edln:#b45309; --auto:#7aa2d6; --gone:#c2410c; --pb:#8b7e66; }
@media (prefers-color-scheme: dark) { :root:not([data-theme="light"]) {
  --bg:#1c1b19; --fg:#e7e4dc; --muted:#a19d93; --rule:#3a3833; --panel:#26241f;
  --ed:#5b4a12; --edln:#f5b041; --auto:#6c93c9; --gone:#fb923c; --pb:#b3a78d; } }
:root[data-theme="dark"] { --bg:#1c1b19; --fg:#e7e4dc; --muted:#a19d93; --rule:#3a3833;
  --panel:#26241f; --ed:#5b4a12; --edln:#f5b041; --auto:#6c93c9; --gone:#fb923c; --pb:#b3a78d; }
* { box-sizing:border-box; }
body { margin:0; background:var(--bg); color:var(--fg);
  font:17px/1.55 "Iowan Old Style","Palatino Linotype",Palatino,Georgia,serif; }
header.top { position:sticky; top:0; z-index:5; background:var(--panel);
  border-bottom:1px solid var(--rule); padding:8px 16px;
  font:14px/1.4 system-ui,sans-serif; }
header.top h1 { font-size:16px; margin:0 0 4px; }
.controls { display:flex; flex-wrap:wrap; gap:4px 14px; align-items:center; }
.controls label { white-space:nowrap; cursor:pointer; }
.controls select { font:inherit; }
main { max-width:1500px; margin:0 auto; padding:0 16px 80px; }
section.div { margin-top:36px; }
section.div > h2 { font-size:22px; margin:0 0 4px; }
.meta { font:13px/1.5 system-ui,sans-serif; color:var(--muted); margin-bottom:10px; }
.meta code { font-size:12px; }
.row { display:grid; grid-template-columns:1fr 1fr; gap:28px;
  padding:10px 0; border-top:1px solid var(--rule); }
.row.head { font-weight:600; }
.colhead { position:sticky; top:var(--hdr,64px); z-index:4; background:var(--bg);
  font:600 12px/1 system-ui,sans-serif; letter-spacing:.06em; text-transform:uppercase;
  color:var(--muted); padding:8px 0; border-top:none; }
.row p, .row h3 { margin:0 0 .5em; }
.row h3 { font-size:1em; }
.row ul, .row ol { margin:0 0 .5em; padding-left:1.6em; }
.orig { color:var(--fg); opacity:.88; }
.ch { border-radius:2px; }
.ch.ed { background:var(--ed); box-shadow:inset 0 -1px 0 var(--edln); }
.ch.auto { text-decoration:underline dotted var(--auto); text-underline-offset:3px; }
body.no-auto .ch.auto { text-decoration:none; }
.gone { color:var(--gone); font-weight:700; }
.pb { font:11px system-ui,sans-serif; color:var(--pb); border:1px solid var(--pb);
  border-radius:3px; padding:0 3px; vertical-align:2px; white-space:nowrap; }
body.no-pages .pb { display:none; }
.row.modern > .orig { font:italic 14px/1.4 system-ui,sans-serif; color:var(--muted); }
.reg section.notes { font-size:14px; line-height:1.45; color:var(--muted);
  border-top:1px dashed var(--rule); margin-top:.6em; padding-top:4px; }
.reg section.notes p { margin:0 0 .3em; }
.reg h2, .reg h3 { font-size:1.1em; margin:.2em 0 .5em; }
.runon { font:12px system-ui,sans-serif; color:var(--muted); margin-right:6px; }
ol.notes { font-size:14px; line-height:1.45; color:var(--muted); margin:.4em 0 0;
  padding-left:0; list-style:none; border-top:1px dashed var(--rule); padding-top:4px; }
ol.notes a, a.noteref { color:inherit; text-decoration:none; }
a.noteref sup { color:var(--edln); }
body.only-orig .row > .reg, body.only-reg .row > .orig { display:none; }
body.only-orig .row, body.only-reg .row { grid-template-columns:1fr; max-width:760px; }
@media (max-width:760px) {
  .row { grid-template-columns:1fr; gap:0; }
  /* the printed text: a tinted, labelled box; the edition: plain, labelled */
  .row > .orig { background:var(--panel); border-left:3px solid var(--pb);
    border-radius:4px; padding:6px 10px; font-size:15px; margin:2px 0 8px; }
  .row > .orig:empty { display:none; }
  .row > .orig::before, body.both .row > .reg::before { display:block;
    font:600 11px/1.8 system-ui,sans-serif; letter-spacing:.06em;
    text-transform:uppercase; color:var(--muted); }
  body.both .row > .reg::before { content:"Edition"; }
  .row.head > .orig::before, body.both .row.head > .reg::before { content:none; }
  .colhead { display:none; }
  header.top { padding:6px 12px; }
  header.top h1 { font-size:13px; margin:0 0 4px; display:-webkit-box;
    -webkit-line-clamp:2; -webkit-box-orient:vertical; overflow:hidden; }
  main { padding:0 12px 80px; }
  section.div { margin-top:24px; }
  details.toc { padding:8px 12px; }
}
/* Edition / Printed / Both */
.smallcaps { font-variant:small-caps; }
.seg { display:inline-flex; border:1px solid var(--rule); border-radius:6px;
  overflow:hidden; margin:2px 0 4px; }
.seg button { font:600 13px/1 system-ui,sans-serif; padding:7px 12px; border:0;
  background:transparent; color:var(--fg); cursor:pointer; }
.seg button + button { border-left:1px solid var(--rule); }
.seg button[aria-pressed="true"] { background:var(--fg); color:var(--bg); }
/* in the edition alone, a paragraph's printed text opens under it */
.peek { display:none; font:600 11px/1 system-ui,sans-serif; letter-spacing:.04em;
  color:var(--muted); background:none; border:1px solid var(--rule);
  border-radius:10px; padding:4px 9px; margin:2px 0 6px; cursor:pointer; }
body.only-reg .peek { display:inline-block; }
body.only-reg .row.open > .orig { display:block; order:2; }
.row.open .peek { color:var(--fg); border-color:var(--pb); }
details.toc { padding:12px 16px; font:14px/1.6 system-ui,sans-serif; }
/* a run of removed words reads as one caret */
.ch:has(> .gone:only-child) + .ch:has(> .gone:only-child) > .gone { display:none; }
@media (max-width:760px) {
  .titlebar .sub { display:none; }
  .titlebar h1 { font-size:14px; }
  .about-btn { padding:2px 8px; font-size:12px; }
  .bar { gap:4px 6px; }
  .seg button, .step button { padding:6px 9px; font-size:12px; }
  .step .where { display:none; }
}
.titlebar { display:flex; flex-wrap:wrap; align-items:baseline; gap:2px 10px; margin-bottom:4px; }
.titlebar h1 { margin:0; }
.titlebar .sub { color:var(--muted); }
.read-link { margin-left:auto; font:13px system-ui,sans-serif; color:var(--fg); text-decoration:none;
  border:1px solid var(--rule); border-radius:12px; padding:3px 10px; }
.read-link + .about-btn { margin-left:0; }
.about-btn { margin-left:auto; font:13px system-ui,sans-serif; color:var(--muted); background:none;
  border:1px solid var(--rule); border-radius:12px; padding:3px 10px; cursor:pointer; }
.about-btn[aria-expanded="true"] { color:var(--fg); border-color:var(--pb); }
.about { max-width:800px; margin:12px 16px 0; padding:10px 14px; font:14px/1.5 system-ui,sans-serif;
  background:var(--panel); border:1px solid var(--rule); border-radius:8px; }
.about p { margin:.3em 0; }
mark.k.ed { background:var(--ed); box-shadow:inset 0 -1px 0 var(--edln); color:inherit; padding:0 2px; }
span.k.auto { text-decoration:underline dotted var(--auto); text-underline-offset:3px; }
.controls label .n { color:var(--muted); font-size:12px; }
.controls label[hidden] { display:none; }
details.toc > summary { cursor:pointer; color:var(--muted); width:max-content; }
details.toc a { color:inherit; }
details.opts > summary { cursor:pointer; color:var(--muted); width:max-content; }
details.opts[open] > summary { margin-bottom:4px; }
.legend { display:none; margin:6px 0 0; color:var(--muted); }
@media (max-width:760px) { .legend { display:block; } }
@media (hover:none) { .ch { cursor:pointer; } }
#tip { position:fixed; left:8px; right:8px; bottom:8px; z-index:10; max-width:640px;
  margin:0 auto; background:var(--panel); color:var(--fg); border:1px solid var(--rule);
  border-radius:8px; box-shadow:0 4px 16px rgba(0,0,0,.25); padding:10px 14px;
  font:14px/1.45 system-ui,sans-serif; white-space:pre-line; }
#tip[hidden] { display:none; }
/* previous / next change */
.bar { display:flex; flex-wrap:wrap; align-items:center; gap:4px 12px; }
.step { display:inline-flex; align-items:center; gap:6px; }
.step button { font:600 13px/1 system-ui,sans-serif; padding:7px 12px; cursor:pointer;
  border:1px solid var(--rule); border-radius:6px; background:transparent; color:var(--fg); }
.step .where { font:12px system-ui,sans-serif; color:var(--muted); }
.row.focus { outline:2px solid var(--edln); outline-offset:4px; border-radius:2px; }
"""

JS = """
const b = document.body;
function hdr(){ document.documentElement.style.setProperty('--hdr',
  document.querySelector('header.top').offsetHeight + 'px'); }
addEventListener('resize', hdr); hdr();
document.querySelectorAll('input[data-t]').forEach(i => {
  const f = () => b.classList.toggle('hide-' + i.dataset.t, !i.checked);
  i.addEventListener('change', f); f(); });
const auto = document.getElementById('auto');
const fa = () => b.classList.toggle('no-auto', !auto.checked);
auto.addEventListener('change', fa); fa();
const pages = document.getElementById('pages');
const fp = () => b.classList.toggle('no-pages', !pages.checked);
pages.addEventListener('change', fp); fp();
// Edition / Printed / Both: phones start with the edition, wide screens with both
const narrow = matchMedia('(max-width:760px)');
const segs = document.querySelectorAll('.seg button');
function setCols(v) {
  b.classList.toggle('only-orig', v === 'orig');
  b.classList.toggle('only-reg', v === 'reg');
  b.classList.toggle('both', v === 'both');
  segs.forEach(x => x.setAttribute('aria-pressed', String(x.dataset.c === v)));
  try { localStorage.setItem(KEY + ':cols', v); } catch (e) {}
  hdr();
}
segs.forEach(x => x.addEventListener('click', () => setCols(x.dataset.c)));
let saved = null;
try { saved = localStorage.getItem(KEY + ':cols'); } catch (e) {}
setCols(saved || (narrow.matches ? 'reg' : 'both'));
// each paragraph: a button that opens its printed text under the edition's
document.querySelectorAll('.row:not(.colhead):not(.head):not(.modern)').forEach(r => {
  const o = r.querySelector(':scope > .orig'), m = r.querySelector(':scope > .reg');
  if (!o || !m || !o.textContent.trim()) return;
  const p = document.createElement('button');
  p.className = 'peek'; p.type = 'button'; p.textContent = PEEK;
  p.addEventListener('click', () => r.classList.toggle('open'));
  m.appendChild(p);
});
if (!narrow.matches) document.querySelector('details.toc').open = true;
// phones: options folded away, and a tap on a marked word shows its readings
if (narrow.matches) document.querySelector('details.opts').open = false;
document.querySelector('details.opts').addEventListener('toggle', hdr);
const tip = document.getElementById('tip');
if (matchMedia('(hover:none)').matches) {
  document.addEventListener('click', e => {
    const c = e.target.closest('.ch[title]');
    if (c) { tip.textContent = c.title; tip.hidden = false; }
    else if (!e.target.closest('#tip')) tip.hidden = true;
  });
}
tip.addEventListener('click', () => { tip.hidden = true; });
// previous / next change: rows holding a change the options above mark
function marked(c) {
  if (c.classList.contains('ed'))
    return ![...c.classList].some(t => b.classList.contains('hide-' + t));
  return auto.checked;
}
function changed() {
  const rows = [];
  document.querySelectorAll('.row .ch').forEach(c => {
    const r = c.closest('.row');
    if (r !== rows[rows.length - 1] && marked(c)) rows.push(r);
  });
  return rows;
}
const where = document.querySelector('.step .where');
function step(d) {
  const rows = changed();
  if (!rows.length) { where.textContent = 'no changes marked'; return; }
  const top = document.querySelector('header.top').offsetHeight + 40;
  const f = document.querySelector('.row.focus');
  let i = f ? rows.indexOf(f) : -1;
  const seen = i >= 0 && Math.abs(f.getBoundingClientRect().top - top) < innerHeight / 2;
  if (seen) i += d;
  else if (d > 0) i = rows.findIndex(r => r.getBoundingClientRect().top > top + 1);
  else i = rows.findLastIndex(r => r.getBoundingClientRect().top < top - 1);
  if (i < 0) i = d > 0 ? rows.length - 1 : 0;
  i = Math.min(rows.length - 1, Math.max(0, i));
  if (f) f.classList.remove('focus');
  rows[i].classList.add('focus');
  where.textContent = (i + 1) + ' / ' + rows.length;
  scrollTo({ top: rows[i].getBoundingClientRect().top + scrollY - top, behavior: 'smooth' });
}
// how many of each kind of change, counted in the edition column
document.querySelectorAll('label[data-for]').forEach(l => {
  const n = document.querySelectorAll('.reg .ch.' + l.dataset.for).length;
  l.querySelector('.n').textContent = '(' + n.toLocaleString() + ')';
  if (!n) l.hidden = true;
});
// presets: what to mark, chosen in one click; a box changed by hand is "custom"
const store = { get(k) { try { return JSON.parse(localStorage.getItem(KEY + ':' + k)); } catch (e) { return null; } },
                set(k, v) { try { localStorage.setItem(KEY + ':' + k, JSON.stringify(v)); } catch (e) {} } };
const pbtn = document.querySelectorAll('.presets button');
const tboxes = [...document.querySelectorAll('input[data-t]')];
function showPreset(k) { pbtn.forEach(x => x.setAttribute('aria-pressed', String(x.dataset.p === k))); }
function fire(i) { i.dispatchEvent(new Event('change')); }
function setPreset(k) {
  const p = PRESETS[k];
  tboxes.forEach(i => { i.checked = p.t.includes(i.dataset.t); fire(i); });
  auto.checked = p.auto; fire(auto);
  if (k === 'read') setCols('reg');
  else if (b.classList.contains('only-reg') && !narrow.matches) setCols('both');
  showPreset(k); store.set('preset', k);
}
pbtn.forEach(x => x.addEventListener('click', () => setPreset(x.dataset.p)));
[...tboxes, auto].forEach(i => i.addEventListener('change', e => {
  if (!e.isTrusted) return;
  showPreset(null); store.set('preset', 'custom');
  store.set('boxes', Object.fromEntries([...tboxes, auto].map(x => [x.dataset.t || 'auto', x.checked])));
}));
const savedPreset = store.get('preset');
if (savedPreset === 'custom' && store.get('boxes')) {
  const bx = store.get('boxes');
  [...tboxes, auto].forEach(i => { const k = i.dataset.t || 'auto'; if (k in bx) { i.checked = bx[k]; fire(i); } });
} else if (PRESETS[savedPreset]) setPreset(savedPreset);
else if (DEFAULT) setPreset(DEFAULT);
// about this page: open on a first visit
const about = document.querySelector('.about'), abtn = document.querySelector('.about-btn');
function setAbout(o) { about.hidden = !o; abtn.setAttribute('aria-expanded', String(o)); hdr(); }
abtn.addEventListener('click', () => { setAbout(about.hidden); store.set('seen', true); });
if (DEFAULT && !store.get('seen')) { setAbout(true); store.set('seen', true); }
document.getElementById('prev').onclick = () => step(-1);
document.getElementById('next').onclick = () => step(1);
document.addEventListener('keydown', e => {
  if (e.target.closest('input, select, textarea') || e.ctrlKey || e.metaKey || e.altKey) return;
  if (e.key === 'n' || e.key === 'j') step(1);
  if (e.key === 'p' || e.key === 'k') step(-1);
});
"""


PRESETS = {  # name: (label, change types marked, routine changes underlined)
    "read": ("Just read", [], False),
    "wording": ("Wording changes", ["t-emendation", "t-omission", "t-grammar", "t-supplied",
                                    "t-note"], False),
    "every": ("Every change", [t for t, _, _ in TYPES], True),
}

ABOUT = """<p>The left column is {source}; the right is <b>this edition</b>. Each row is one
paragraph, so you can read across.</p>
<p>A <mark class="k ed">highlighted</mark> word is one the editor changed: tap or hover over it
to see what {was}. A <span class="k auto">dotted</span> word was changed by rule: {rule},
the same way throughout. A <span class="gone">‸</span> marks where words were taken out.</p>
<p><b>Wording changes</b> (the default) marks what changes the words themselves; <b>Every
change</b> marks spelling, capitals and punctuation too; <b>Just read</b> shows the
edition plain. ◀ / ▶ (or the keys p and n) step from one marked paragraph to the next.
Under <b>Details</b> you can choose each kind of change yourself.</p>"""


def page(title, L, sections, toc, public=False, subtitle=None, reader=None):
    hide = "".join(
        f"body.hide-{t} .ch.{t}{{background:none;box-shadow:none;text-decoration:none}}"
        f"body.hide-{t} .ch.{t} .gone{{display:none}}" for t, _, _ in TYPES)
    boxes = "".join(
        f'<label data-for="{t}"><input type="checkbox" data-t="{t}"{" checked" if on else ""}> '
        f'{lab} <span class="n"></span></label>'
        for t, lab, on in TYPES)
    presets = "".join(f'<button type="button" data-p="{k}">{lab}</button>'
                      for k, (lab, _, _) in PRESETS.items())
    preset_js = "{" + ",".join(
        f'"{k}":{{t:{list(ts)!r},auto:{str(au).lower()}}}' for k, (_, ts, au) in PRESETS.items()) + "}"
    routine = "routine changes (by rule)" if public else "underline machine changes"
    sub = subtitle or L["sub"]
    head_title = f"{title}: {sub}"
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{html.escape(head_title)}</title>
<style>{CSS}{hide}
@media (max-width:760px) {{ .row > .orig::before {{ content:"{L['short']}"; }} }}</style></head>
<body>
<header class="top"><div class="titlebar"><h1>{html.escape(title)}</h1>
<span class="sub">{html.escape(sub)}</span>
{f'<a class="read-link" href="{html.escape(reader)}">Read the edition</a>' if reader else ''}<button type="button" class="about-btn" aria-expanded="false">About this page</button></div>
<div class="bar"><div class="seg" role="group" aria-label="Show"><button type="button" data-c="reg">Edition</button><button type="button" data-c="orig">{L['short']}</button><button type="button" data-c="both">Side by side</button></div>
<div class="seg presets" role="group" aria-label="Mark">{presets}</div>
<div class="step"><button type="button" id="prev" title="previous change (p)">◀</button><button type="button" id="next" title="next change (n)">▶</button><span class="where"></span></div></div>
<details class="opts"><summary>Details</summary>
<div class="controls"><span>Mark:</span>{boxes}
<label data-for="auto"><input type="checkbox" id="auto"> {routine} <span class="n"></span></label>
<label><input type="checkbox" id="pages" checked> printed page numbers</label>
</div></details></header>
<div class="about" hidden>{ABOUT.format(**L)}</div>
<details class="toc"><summary>Contents</summary><nav>{toc}</nav></details>
<main>{sections}</main>
<div id="tip" hidden></div>
<script>const PEEK = "{L['short']}", PRESETS = {preset_js}, DEFAULT = {'"wording"' if public else 'null'}, KEY = {json.dumps('fgb-compare:' + title)};{JS}</script>
</body></html>
"""


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("tei")
    ap.add_argument("out")
    ap.add_argument("--chapters", default="chapters/typ",
                    help="where the editable files are, as shown on the page")
    ap.add_argument("--before", action="append", default=[],
                    help="modern page before the text (.typ or .html); repeatable")
    ap.add_argument("--after", action="append", default=[],
                    help="modern page after the text; repeatable")
    ap.add_argument("--only", metavar="PREFIX",
                    help="only the files whose path starts with PREFIX, e.g. vol-1/ "
                    "(a big book is easier to read a volume at a time)")
    ap.add_argument("--typst-root",
                    help="Typst --root for .typ pages (default: the book folder)")
    ap.add_argument("--public", action="store_true",
                    help="the page for readers (a release): no editor's file paths, "
                         "changes said to be by rule or by the editor, opening on the "
                         "wording changes with a note on how to read it")
    ap.add_argument("--title", help="the book's title (default: the TEI's)")
    ap.add_argument("--reader", help="link to the reader page (a release's)")
    ap.add_argument("--subtitle", help='the line under it (default: "printed YEAR and this edition")')
    a = ap.parse_args()
    root = etree.parse(a.tei).getroot()
    date = root.find(f".//{T}sourceDesc//{T}date")
    m_ = re.search(r"1[5-8]\d\d", "".join(date.itertext()) if date is not None else "")
    year = m_.group(0) if m_ else "print"
    sd = root.find(f".//{T}sourceDesc")
    if "CCEL" in " ".join(sd.itertext() if sd is not None else []):
        # a CCEL text: the comparison is with the text the edition is set from
        L = dict(short="CCEL text", sub="the CCEL text and this edition", tip="CCEL",
                 source='<b>the CCEL text</b> this edition is set from (Christian Classics '
                        'Ethereal Library, ccel.org)', was="the CCEL text has",
                 rule="quotation marks and dashes set as the edition sets them",
                 missing="Not in the CCEL text.", meta="not in the CCEL text")
    else:
        L = dict(short=f"Printed {year}", sub=f"printed {year} and this edition", tip=year,
                 source=f"the text as it was <b>printed in {year}</b>", was="was printed",
                 rule="the old spelling or letterforms brought up to date (vnto → unto, ſ → s)",
                 missing=f"Not in the {year} printing.", meta=f"not in the {year} printing")
    o, m = ReviewR("orig", "o-", L["tip"]), ReviewR("reg", "m-", L["tip"])
    if a.public:
        o.public = m.public = True
        o.rule_name = m.rule_name = "rule"
    cfg = layout.settings(a.tei)
    if cfg.get("SMALLCAPS"):        # the printed column shows the capitals as printed
        m.settings = dict(getattr(m, "settings", {}), SMALLCAPS=cfg["SMALLCAPS"])
    o.index(root)
    m.index(root)
    sections, toc = [], []
    typst_root = Path(a.typst_root) if a.typst_root else Path(a.tei).resolve().parent.parent
    notes_used = [0]

    def modern(path, where):
        path = Path(path)
        if path.suffix == ".typ":
            frag, k = typst_page(path, typst_root, notes_used[0] + 1)
            notes_used[0] += k
        else:
            frag = path.read_text(encoding="utf-8").strip()
        ident = f"{where}-{re.sub(r'[^a-z0-9]+', '-', path.stem.lower())}"
        h = re.search(r"<h[1-6][^>]*>(.*?)</h[1-6]>", frag, re.S)
        name = html.unescape(re.sub(r"<[^>]+>", "", h.group(1))).strip() if h else path.stem
        sections.append(
            f'<section class="div" id="{ident}"><h2>{html.escape(name)}</h2>'
            + (f'<div class="meta">modern matter, {L["meta"]}</div>' if a.public else
               f'<div class="meta">modern matter, not in the {year} text and not in the TEI'
               f' · edit <code>{html.escape(str(path))}</code></div>')
            +
            f'<div class="row modern"><div class="orig">{L["missing"]}</div>'
            f'<div class="reg">{frag}</div></div></section>')
        toc.append(f'<a href="#{ident}">{html.escape(name)}</a>')

    for f in a.before:
        modern(f, "before")
    for ident, fname, ftitle, unit in division_units(root, cfg):
        if a.only and not fname.startswith(a.only):
            continue
        if isinstance(unit, list):              # a layout file: its parts
            div = unit
            mh = [f"<h3>{html.escape(ftitle)}</h3>"] if ftitle else []
            oh = []
            wrapper = unit
        else:
            div = unit
            mh = finish(m.heading(div))
            oh = finish(o.heading(div))
            wrapper = [div]
        name = re.sub(r"<[^>]+>", "", mh[0]) if mh else fname
        c = counts(*wrapper)
        summary = ", ".join(f"{v} {k}" for k, v in c.most_common()) or "none"
        meta = ("" if a.public else
                f'<div class="meta">edit in <code>{html.escape(a.chapters)}/{fname}'
                f'</code> · editor decisions: {summary}</div>')
        body = [f'<section class="div" id="{ident}"><h2>{name}</h2>', meta,
                f'<div class="row colhead"><div>{L["short"]}</div><div>Edition</div></div>',
                f'<div class="row head"><div class="orig">{"".join(oh)}</div>'
                f'<div class="reg">{"".join(mh)}</div></div>']
        if isinstance(unit, list):
            rs = []
            for el in unit:
                if local(el) == "div":
                    oh_, mh_ = finish(o.heading(el)), finish(m.heading(el))
                    if oh_ or mh_:
                        rs.append(("".join(oh_), "".join(mh_), "head"))
                    rs += rows(el, o, m)
                else:
                    rs += rows([el], o, m)
        else:
            rs = rows(div, o, m)
            for tr in following_trailers(div):
                rs.append(("".join(o.blocks([tr])), "".join(m.blocks([tr])), ""))
        for ob, mb, cls in rs:
            body.append(f'<div class="row {cls}"><div class="orig">{ob}</div>'
                        f'<div class="reg">{mb}</div></div>')
        body.append("</section>")
        sections.append("\n".join(body))
        toc.append(f'<a href="#{ident}">{html.escape(html.unescape(name))}</a>')
    for f in a.after:
        modern(f, "after")
    Path(a.out).write_text(
        page(a.title or tei_title(root), L, "\n".join(sections), " · ".join(toc),
             public=a.public, subtitle=a.subtitle, reader=a.reader),
        encoding="utf-8")
    extra = len(a.before) + len(a.after)
    print(f"wrote {a.out}: {len(sections) - extra} divisions, {extra} modern pages")


if __name__ == "__main__":
    main()
