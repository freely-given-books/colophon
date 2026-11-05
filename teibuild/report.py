"""
Reports: --list (the occurrences editorial.py is keyed on) and the
Markdown report of review decisions.
"""

from pathlib import Path

import teibuild  # noqa: F401  (puts colophon on sys.path)

from teitok import T, local, iter_stream  # noqa: E402

from teibuild import settings as S  # noqa: E402


def list_editorial(toks, width=6):
    """Print each macron abbreviation and non-duplicate gap in document order,
    numbered exactly as MACRON_M and GAP_FIXES index them, with the printed
    page (pb/@n, pb/@facs for the page image) and the words around it."""
    words, page = [], ("?", "")
    for kind, t in iter_stream(toks):
        if kind != "tok":
            continue
        if t.kind == "atom" and t.el is not None and local(t.el) == "pb":
            page = (t.el.get("n") or "?", t.el.get("facs") or "")
        if t.kind == "word":
            words.append((t, page))
    for i, (t, (pn, facs)) in enumerate(words):
        if not (t.macrons or t.gaps):
            continue
        before = " ".join(w.expanded for w, _ in words[max(0, i - width):i])
        after = " ".join(w.expanded for w, _ in words[i + 1:i + 1 + width])
        where = f"p.{pn} {facs}".strip() + (" note" if t.in_note else "")
        for idx, _ in t.macrons:
            m = "m" if idx in S.MACRON_M else "n"
            print(f"macron {idx:4d}  [{m}]  {t.expanded!r:18}  {where}\n"
                  f"        ... {before} [{t.expanded}] {after} ...")
        for idx, g in t.gaps:
            desc = g.find(T + "desc")
            shown = desc.text if desc is not None and desc.text else "•"
            fix = S.GAP_FIXES.get(idx)
            state = f"fixed {fix[0]!r} ({fix[1]}: {fix[2]})" if fix else f"OPEN {shown!r}"
            print(f"gap    {idx:4d}  {state}  {where}\n"
                  f"        ... {before} [{t.expanded}] {after} ...")


def write_report(path, log, unresolved):
    from collections import Counter, defaultdict
    kinds = Counter(k for _, k, *_ in log)
    lines = ["# Review decisions carried into the enriched TEI", ""]
    if S.REPORT_NOTES:
        lines += ["## Please check", ""] + [f"- {n}" for n in S.REPORT_NOTES] + [""]
    lines.append("| kind | count |")
    lines.append("| --- | --- |")
    for k, n in kinds.most_common():
        lines.append(f"| {k} | {n} |")
    lines.append("")
    groups = defaultdict(list)
    for e in log:
        groups[e[1]].append(e)
    for k in ["repair", "unresolved", "split", "skipped", "gap", "expansion",
              "emendation", "grammar", "punctuation", "case", "spelling"]:
        if k not in groups:
            continue
        lines.append(f"## {k}")
        lines.append("")
        if k in ("spelling", "case", "grammar"):
            c = Counter((e[2], e[3]) for e in groups[k])
            for (a, b), n in sorted(c.items(), key=lambda x: (-x[1], x[0])):
                lines.append(f"- {a} → {b}" + (f" (×{n})" if n > 1 else ""))
        else:
            for e in groups[k]:
                lines.append(f"- [{e[0]}] {e[2]} → {e[3]}")
        lines.append("")
    if unresolved:
        lines.append("## not applied")
        lines.append("")
        for f, a, b in unresolved:
            lines.append(f"- [{f}] {a} → {b}")
    Path(path).write_text("\n".join(lines) + "\n")
