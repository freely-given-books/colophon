"""
The sentences to read, from the gap marker's scores (gapmark.py): the
policy's steps 4 and 5.

  ./fgb marked GAPMARK.json READ.txt [--share 0.15] [--sample 0.05] [--seed N]

A sentence (split after . ! ?) scores as its strongest word:
  wrong  -log p of a small word in the text (high: the model finds it unlikely)
  gap    how strongly a small word was expected where the text has another
Sentences tied on that score (many reach the 15.0 cap: Of Temptation 608 of
1,368) rank by their next-strongest words, then by reading order, so the top
share spans the book rather than filling from its first chapters.
The top --share of the text by words, highest scores first, then a random
--sample of the rest as a check, each listed in reading order as
"NN score sentence" (NN the file's number), the strongest word marked
[[word]](the model's guess?). The sample's seed is in its heading, so a
sample can be drawn again.
"""

import json
import random
import re
from pathlib import Path

from proof.gapmark import SMALL, bare


def word_score(w, lp, best, blp):
    if lp is None:                       # the model gave no scores for this word
        return 0.0
    wrong = -lp if bare(w) in SMALL and lp > -15.5 else 0.0
    if bare(w) in SMALL and lp <= -15.0:
        wrong = 15.0
    gap = 0.0
    if best and best != bare(w) and blp > -3.0 and lp < blp - 2.0:
        gap = (blp + 3.0) * 3 + min(6.0, (blp - lp))      # confident small-word guess, text differs
    return max(wrong, gap)


def sentences(data):
    """[(file, first word, last word, score, strongest word)] in reading order."""
    out = []
    for f, recs in data.items():
        start, best_s, best_i = 0, 0.0, None
        for i, (w, lp, b, blp) in enumerate(recs):
            s = word_score(w, lp, b, blp)
            if s > best_s:
                best_s, best_i = s, i
            if re.search(r"[.!?][”’\"')\]]*$", w) or i == len(recs) - 1:
                out.append((f, start, i, best_s, best_i))
                start, best_s, best_i = i + 1, 0.0, None
    return out


def line(data, s):
    f, a, b, score, mark = s
    recs = data[f]
    words = [f"[[{recs[i][0]}]]" + (f"({recs[i][2]}?)" if recs[i][2] else "") if i == mark
             else recs[i][0] for i in range(a, b + 1)]
    num = re.search(r"\d+", Path(f).stem)
    return f"{num.group(0) if num else Path(f).stem} {score:4.1f} {' '.join(words)}"


def strength(data, s):
    """A sentence's rank key: its word scores, strongest first (the first is its score)."""
    f, a, b, _, _ = s
    return sorted((word_score(*data[f][i]) for i in range(a, b + 1)), reverse=True)


def choose(data, share=0.15, sample=0.05, seed=None):
    """(top, sample, total words, words in top, seed)."""
    sents = sentences(data)
    total = sum(b - a + 1 for _, a, b, _, _ in sents)
    budget, top, used = share * total, [], 0
    for s in sorted(sents, key=lambda s: [-x for x in strength(data, s)]):
        if used >= budget:
            break
        top.append(s)
        used += s[2] - s[1] + 1
    chosen = set(map(id, top))
    rest = [s for s in sents if id(s) not in chosen]
    seed = random.randrange(10 ** 6) if seed is None else seed
    rng = random.Random(seed)
    pool, picked, n = rest[:], [], 0
    rng.shuffle(pool)
    for s in pool:
        if n >= sample * total:
            break
        picked.append(s)
        n += s[2] - s[1] + 1
    order = {id(s): k for k, s in enumerate(sents)}
    by_order = lambda ss: sorted(ss, key=lambda s: order[id(s)])
    return by_order(top), by_order(picked), total, used, seed


def main(a):
    data = json.loads(Path(a.gapmark).read_text(encoding="utf-8"))
    top, picked, total, used, seed = choose(data, a.share, a.sample, a.seed)
    out = [f"# top {a.share:.0%} ({used} of {total} words)"]
    out += [line(data, s) for s in top]
    out += [f"# random {a.sample:.0%} sample (seed {seed})"]
    out += [line(data, s) for s in picked]
    Path(a.out).write_text("\n".join(out) + "\n", encoding="utf-8")
    print(f"{len(top)} sentences ({used} words) by score, {len(picked)} as a check -> {a.out}")
