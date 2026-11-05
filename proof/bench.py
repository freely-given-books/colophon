"""
The planted-slip benchmark the proofread policy was chosen with (Sinners,
2026-10-25): plant known slips in a finished book's chapters, run the
proofread pass on them, count what it catches; and how much of the planted
slips the gap marker's top sentences cover at each share of the text.

  ./fgb proof-bench plant DIR [--n 20] [--seed 1]
      DIR/after (a finished book's chapters/typ, copied) -> DIR/planted, with
      DIR/planted.json: each slip's file, kind, place and word span
  ./fgb proof-bench run DIR MODEL [MODEL ...] [--book "..."]
      the proofread pass (policy settings) on DIR/planted with each model ->
      DIR/flags-planted-<model>.jsonl, scored into DIR/bake.json
  ./fgb proof-bench marker DIR GAPMARK.json [FLAGS.jsonl]
      the gap marker on DIR/planted: planted slips its top sentences cover at
      5% ... 30% of the text, alone and with a proofread's flags

With DIR/before (the same chapters before their proofread), `run` also
counts the real fixes the proofread made that the model finds again.
(From local-tools/bench/ and gapscore.py, 2026-11-05: planting, scoring
and the marker table unchanged; word positions as fixpos.py corrected them.)
"""

import difflib
import json
import random
import re
import time
from argparse import Namespace
from pathlib import Path

from proof import marked, proofread

WORD = re.compile(r"\S+")
plain = proofread.plain

SLIPS = [
    ("double", None), ("he>be", (r"\bhe\b", "be")), ("from>form", (r"\bfrom\b", "form")),
    ("them>then", (r"\bthem\b", "then")), ("of>or", (r"\bof\b", "or")), ("drop-not", (r"\bnot ", "")),
    ("the>they", (r"\bthe\b", "they")), ("is>it", (r"\bis\b", "it")), ("drop-the", (r"\bthe ", "")),
    ("and>an", (r"\band\b", "an")),
]


def plant(d, n=20, seed=1):
    rnd = random.Random(seed)
    src, dst = d / "after", d / "planted"
    texts = {f.relative_to(src): f.read_text(encoding="utf-8") for f in sorted(src.rglob("*.typ"))}
    targets = []
    for k in range(n):
        kind, rule = SLIPS[k % len(SLIPS)]
        for _ in range(200):
            rel = rnd.choice(list(texts))
            t = texts[rel]
            paras = [m for m in re.finditer(r"(?:[^\n]+\n?)+", t) if len(m.group(0)) >= 200
                     and not m.group(0).lstrip().startswith(("=", "//", "#"))]
            if not paras:
                continue
            para = rnd.choice(paras)
            seg = para.group(0)
            if rule is None:
                ws = [m for m in re.finditer(r"\b[a-z]{3,}\b", seg)]
                if not ws:
                    continue
                m = rnd.choice(ws)
                s, e, new = m.start(), m.end(), m.group(0) + " " + m.group(0)
            else:
                ms = list(re.finditer(rule[0], seg))
                if not ms:
                    continue
                m = rnd.choice(ms)
                s, e, new = m.start(), m.end(), rule[1]
            pos = para.start() + s
            if any(abs(pos - tg["pos"]) < 400 and tg["file"] == str(rel) for tg in targets):
                continue
            texts[rel] = t[:pos] + new + t[para.start() + e:]
            ctx = texts[rel][max(0, pos - 40):pos + len(new) + 40]
            targets.append({"file": str(rel), "kind": kind, "pos": pos, "new": new, "ctx": ctx})
            break
    for rel, t in texts.items():
        (dst / rel).parent.mkdir(parents=True, exist_ok=True)
        (dst / rel).write_text(t, encoding="utf-8")
    # word positions in the plain text, counted from the slip's place in the file
    for tg in targets:
        raw = (dst / tg["file"]).read_text(encoding="utf-8")
        w0 = len(WORD.findall(plain(raw[:tg["pos"]])))
        tg["w1"], tg["w2"] = w0, w0 + max(1, len(plain(tg["new"]).split()))
    (d / "planted.json").write_text(json.dumps(targets, indent=1), encoding="utf-8")
    return targets


def real_targets(d):
    """The real fixes a book's proofread made: word changes before -> after."""
    out = []
    for b in sorted((d / "before").rglob("*.typ")):
        rel = b.relative_to(d / "before")
        a = d / "after" / rel
        wb = WORD.findall(plain(b.read_text(encoding="utf-8")))
        wa = WORD.findall(plain(a.read_text(encoding="utf-8"))) if a.exists() else []
        sm = difflib.SequenceMatcher(None, wb, wa, autojunk=False)
        for tag, i1, i2, j1, j2 in sm.get_opcodes():
            if tag == "equal":
                continue
            old, new = " ".join(wb[i1:i2]), " ".join(wa[j1:j2])
            # punctuation-only and spacing changes are not what this pass hunts
            if re.sub(r"\W", "", old.lower()) == re.sub(r"\W", "", new.lower()):
                continue
            out.append({"file": str(rel), "w1": i1, "w2": max(i2, i1 + 1), "old": old, "new": new})
    return out


def flag_spans(text_dir, flagfile):
    """[(file, first word, last word)] of a proofread's flags whose quote is found."""
    spans = []
    for line in open(flagfile, encoding="utf-8"):
        r = json.loads(line)
        t = plain((text_dir / r["file"]).read_text(encoding="utf-8"))
        for fl in r["flags"]:
            q = (fl.get("quote") or "").strip()
            i = t.find(q) if q else -1
            if i >= 0:
                w1 = len(WORD.findall(t[:i]))
                spans.append((r["file"], w1, w1 + len(q.split())))
    return spans


def hits(targets, spans):
    return [any(f == t["file"] and a - 3 <= t["w2"] and t["w1"] <= b + 3 for f, a, b in spans)
            for t in targets]


def score(d, flagfile):
    planted = json.loads((d / "planted.json").read_text(encoding="utf-8"))
    spans = flag_spans(d / "planted", flagfile)
    hit = hits(planted, spans)
    nflags = sum(len(json.loads(line)["flags"]) for line in open(flagfile, encoding="utf-8"))
    false = sum(1 for s in spans if not hits(planted, [s]).count(True))
    return {"planted": len(planted), "caught": sum(hit), "flags": nflags, "false_alarms": false,
            "missed": [f"{p['kind']}: …{p['ctx'][20:80]}…" for p, h in zip(planted, hit) if not h]}


def run(d, models, book):
    out = d / "bake.json"
    res = json.loads(out.read_text(encoding="utf-8")) if out.exists() else {}
    for m in models:
        ff = d / f"flags-planted-{m.replace(':', '_')}.jsonl"
        if m not in res:
            t0 = time.time()
            proofread.main(Namespace(out=str(ff), files=None, chunk=100, model=m, general=False,
                                     no_think=not m.startswith("qwen")), d / "planted", book)
            res[m] = {**score(d, ff), "minutes": round((time.time() - t0) / 60, 1)}
            if (d / "before").is_dir():
                fb = d / f"flags-before-{m.replace(':', '_')}.jsonl"
                proofread.main(Namespace(out=str(fb), files=None, chunk=100, model=m, general=False,
                                         no_think=not m.startswith("qwen")), d / "before", book)
                real = real_targets(d)
                res[m]["real_fixes"] = len(real)
                res[m]["real_caught"] = sum(hits(real, flag_spans(d / "before", fb)))
            out.write_text(json.dumps(res, indent=1, ensure_ascii=False), encoding="utf-8")
        r = res[m]
        print(f"{m:24} caught {r['caught']}/{r['planted']}  false alarms {r['false_alarms']}  "
              f"({r['minutes']} min)", flush=True)


def marker(d, gapmark, flagfile=None):
    data = json.loads(Path(gapmark).read_text(encoding="utf-8"))
    targets = json.loads((d / "planted.json").read_text(encoding="utf-8"))
    sents = marked.sentences(data)
    total = sum(b - a + 1 for _, a, b, _, _ in sents)
    hit2 = hits(targets, flag_spans(d / "planted", flagfile)) if flagfile else [False] * len(targets)
    if flagfile:
        print(f"the proofread alone: {sum(hit2)}/{len(targets)}")
    order = sorted(sents, key=lambda s: -s[3])
    for share in (0.05, 0.08, 0.10, 0.12, 0.15, 0.20, 0.25, 0.30):
        budget, chosen, used = share * total, [], 0
        for s in order:
            if used >= budget:
                break
            chosen.append(s)
            used += s[2] - s[1] + 1
        cov = [any(f == t["file"] and a - 1 <= t["w1"] <= b + 1 for f, a, b, _, _ in chosen)
               for t in targets]
        both = [c or h for c, h in zip(cov, hit2)]
        missed = [t["kind"] for t, b in zip(targets, both) if not b]
        print(f"read {share:4.0%} of text ({used} words): marker covers {sum(cov):2}/{len(targets)}, "
              f"with the proofread {sum(both):2}/{len(targets)}  missed {missed}")


def main(a):
    d = Path(a.dir)
    if a.action == "plant":
        t = plant(d, a.n, a.seed)
        print(f"{len(t)} slips planted in {d / 'planted'}")
    elif a.action == "run":
        run(d, a.models, a.book)
    else:
        marker(d, a.models[0], a.models[1] if len(a.models) > 1 else None)
