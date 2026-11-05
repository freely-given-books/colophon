"""
The proofread pass: a local model (Ollama) reads an edition's chapters for
typing and printing slips and flags them; it never changes the text. A
reader settles every flag against the sources.

  ./fgb proof BOOK OUT.jsonl [--model M] [--general] [--no-think] [--chunk N]
              [--files a.typ,b.typ] [--book "..."]

The defaults are the policy's (proof/__init__.py): Qwen 3.8 27B, thinking
on, the small-word "focus" prompt, 100-word chunks; --general is the wider
prompt (dropped words, wrong words, brackets, numbering, garbled Scripture)
the policy found adds nothing at that cost. Each line of OUT: {file, chunk,
seconds, flags: [{quote, issue, suggestion, confidence, found}]}, found =
the quote occurs in the file. Resumable: chunks already in OUT are skipped.
(From local-tools/local_proof.py, 2026-11-05; prompts unchanged.)
"""

import json
import os
import re
import time
import urllib.request
from pathlib import Path

from proof import ollama_url

MODEL = "qwen3.8:27b"

PROMPT = """You are proofreading a printed edition of {book}. The English is old and intentional: hath, doth, -eth, -est, ye, thee, unto, viz., namely, shew, wherein, whereby, "an universal", long sentences, Latin and Greek phrases, Scripture references like "John iii. 16". Never flag these, and never modernize style, spelling or punctuation habits.

Flag only probable typing or printing slips that a careful editor would correct:
- a word dropped or doubled ("the the", "he that condemn me" for "he that shall condemn me")
- a wrong common word that breaks the sense: he/be, the/they, of/or, form/from, then/them, it/is, not/now, its/us, these/those only if the sense requires it
- an unbalanced quotation mark, bracket or parenthesis
- a numbered sequence that skips or repeats (First, Secondly, Fourthly)
- a Scripture quotation visibly garbled (not merely worded differently from the KJV)

Never comment on Scripture references (their numbers, form, missing verses or style): they are checked separately. Read every sentence for its grammar: a "be" where "he" is needed, or a sentence missing its verb, is exactly what to find.

Text:
<<<
{text}
>>>

Answer with JSON only: {{"flags": [{{"quote": "exact words copied from the text, at most 12 words", "issue": "what is wrong, briefly", "suggestion": "the corrected words", "confidence": "high|medium|low"}}]}}. Most passages have no slips: then answer {{"flags": []}}."""


FOCUS_PROMPT = """You are checking a printed edition of {book} for one kind of slip only: small words. The English is old and intentional (hath, doth, -eth, ye, thee, unto, shew); never flag that, and never change style.

Read every sentence slowly, word by word, and ask of each small word whether it is the word the sentence needs:
- a small word missing: "the", "a", "not", "to", "of", "is", "be", "and" (for example "children of devil" for "children of the devil"; "knows that her house is the way" where the sense needs "is not")
- a small word wrong: he/be, the/they, of/or, form/from, then/them, it/is, an/and, in/is, on/no, these/those, that/than
- a word doubled ("was was")

Text:
<<<
{text}
>>>

Answer with JSON only: {{"flags": [{{"quote": "exact words copied from the text, at most 12 words", "issue": "what is wrong, briefly", "suggestion": "the corrected words", "confidence": "high|medium|low"}}]}}. If every small word is right, answer {{"flags": []}}."""


def chunks(text, size=260):
    paras = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip() and not p.lstrip().startswith("//")]
    cur, n = [], 0
    for p in paras:
        w = len(p.split())
        if cur and n + w > size:
            yield "\n\n".join(cur); cur, n = [], 0
        cur.append(p); n += w
    if cur:
        yield "\n\n".join(cur)


def plain(s):
    s = re.sub(r"#\w+(\((?:[^()]|\([^()]*\))*\))?\[", "", s)
    s = re.sub(r"(?<!\\)\]", "", s)
    return s.replace("\\", "")


def ask(model, text, book, focus=True, think=True):
    body = json.dumps({"model": model, "prompt": (FOCUS_PROMPT if focus else PROMPT).format(text=text, book=book),
                       "stream": False, "format": "json", "think": think,
                       "options": {"temperature": 0, "num_ctx": int(os.environ.get("NUM_CTX", 8192)),
                                   "num_predict": int(os.environ.get("NUM_PREDICT", 4096)) if think else 1024}}).encode()
    r = json.load(urllib.request.urlopen(urllib.request.Request(ollama_url(), body,
                                                                {"Content-Type": "application/json"}), timeout=900))
    return r["response"], r.get("eval_count", 0), r.get("total_duration", 0) / 1e9


def main(a, chdir, book):
    """a: the parsed arguments; chdir: the chapters folder; book: the book's
    description for the prompt."""
    out = Path(a.out)
    done = set()
    if out.exists():
        for line in open(out, encoding="utf-8"):
            r = json.loads(line)
            done.add((r["file"], r["chunk"]))
    paths = [chdir / f for f in a.files.split(",")] if a.files else sorted(chdir.rglob("*.typ"))
    with open(out, "a", encoding="utf-8") as fh:
        for p in paths:
            rel = str(p.relative_to(chdir))
            raw = p.read_text(encoding="utf-8")
            flat = plain(raw)
            for k, c in enumerate(chunks(raw, a.chunk)):
                if (rel, k) in done:
                    continue
                t0 = time.time()
                try:
                    resp, toks, secs = ask(a.model, plain(c), book, focus=not a.general, think=not a.no_think)
                    flags = json.loads(resp).get("flags", [])
                except Exception as e:  # noqa: BLE001  (a bad reply is recorded, the run goes on)
                    flags, secs = [{"error": str(e)}], time.time() - t0
                rec = {"file": rel, "chunk": k, "seconds": round(secs, 1), "flags": []}
                for f in flags if isinstance(flags, list) else []:
                    if not isinstance(f, dict):
                        continue
                    q = (f.get("quote") or "").strip()
                    f["found"] = bool(q) and q in flat
                    rec["flags"].append(f)
                fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
                fh.flush()
                print(rel, k, f"{secs:.0f}s", len(rec["flags"]), "flags", flush=True)
