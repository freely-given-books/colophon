"""
The gap marker: every word of a book scored for how unlikely it is in
context, from a local model's next-word probabilities (Ollama), to choose
the sentences a reader should look at (marked.py).

  ./fgb gapmark BOOK OUT.json [--model M] [--files a.typ,b.typ]

Two signals per word, from the model's top-20 guesses for the next word:
  wrong  a small word in the text the model finds very unlikely
         ("the mere pleasure or God", "coming upon then, being")
  gap    the model strongly expects a small word that is not there
         ("that a man is [not] on the very brink")
OUT: per file, [word, log-probability of the word, best small-word guess,
its log-probability]. Resumable: files already in OUT are skipped. The
model reads each paragraph from its start (prefix cache: ~0.07 s a word).
(From local-tools/gapmark.py, 2026-11-05; scoring unchanged.)
"""

import json
import re
import sys
import time
import urllib.request
from pathlib import Path

from proof import ollama_url

MODEL = "qwen3.8:27b"
SMALL = set("""a an the and or of to in on at by for from with not no nor but if is it its be he
him his her she they them then than that this these those there their we us our you ye your
was were are am has had have do did doth hath shall should will would may might can could must
so as all any one who whom which what when where while yet""".split())
WORD = re.compile(r"\S+")


def plain(s):
    s = re.sub(r"#\w+(\((?:[^()]|\([^()]*\))*\))?\[", "", s)
    s = re.sub(r"(?<!\\)\]", "", s)
    return s.replace("\\", "")


def bare(w):
    return re.sub(r"[^a-z]", "", w.lower())


def ask(model, prompt):
    body = json.dumps({"model": model, "prompt": prompt, "raw": True, "stream": False, "logprobs": True,
                       "top_logprobs": 20, "options": {"num_predict": 1, "temperature": 0, "num_ctx": 4096}}).encode()
    for attempt in (1, 2):
        r = json.load(urllib.request.urlopen(urllib.request.Request(
            ollama_url(), body, {"Content-Type": "application/json"}), timeout=300))
        if r.get("logprobs"):
            return [(t["token"], t["logprob"]) for t in r["logprobs"][0]["top_logprobs"]]
    # no logprobs twice (2026-10-27: one reply without them ended a night's
    # run): skip this word, say so
    print(f"  no logprobs: {r.get('done_reason')!r} {r.get('response', '')[:20]!r} "
          f"after …{prompt[-40:]!r}", file=sys.stderr)
    return []


def score_word(top, word):
    """(lp of the text's word or -15, best small-word guess, its lp)."""
    w = bare(word)
    lp = -15.0
    for tok, l in top:
        t = bare(tok)
        if t and (t == w or (len(t) >= 3 and w.startswith(t))):
            lp = max(lp, l)
    best = next(((bare(t), l) for t, l in top if bare(t) in SMALL), (None, -15.0))
    return lp, best[0], best[1]


def main(a, chdir):
    out = Path(a.out)
    res = json.load(open(out, encoding="utf-8")) if out.exists() else {}
    paths = [chdir / f for f in a.files.split(",")] if a.files else sorted(chdir.rglob("*.typ"))
    for p in paths:
        rel = str(p.relative_to(chdir))
        if rel in res:
            continue
        text = plain(p.read_text(encoding="utf-8"))
        words = [m for m in WORD.finditer(text)]
        recs = []
        t0 = time.time()
        # paragraphs: the model reads each from its start (context resets at blank lines)
        para_start = 0
        for i, m in enumerate(words):
            if i > 0 and "\n\n" in text[words[i - 1].end():m.start()]:
                para_start = m.start()
            if m.start() - para_start < 15:          # the first words of a paragraph: no context
                recs.append([m.group(0), 0.0, None, -15.0])
                continue
            top = ask(a.model, text[para_start:m.start()].rstrip())
            if not top:
                recs.append([m.group(0), None, None, None])     # no score
                continue
            lp, best, blp = score_word(top, m.group(0))
            recs.append([m.group(0), round(lp, 2), best, round(blp, 2)])
        res[rel] = recs
        json.dump(res, open(out, "w", encoding="utf-8"), ensure_ascii=False)
        print(rel, len(words), "words", f"{time.time() - t0:.0f}s", flush=True)
