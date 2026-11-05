"""
The proofread of an edition's chapters, as decided with the editor on
2026-10-25 (measured on Sinners with 20 planted slips: 19/20, against 20/20
for a full read by Claude at about five times the tokens):

  1. proofread.py  a local model (Ollama) reads the chapters for small-word
                   slips and flags them: Qwen 3.8 27B, thinking on, the
                   "focus" prompt, 100-word chunks (17/20 alone, no false
                   alarms)
  2. gapmark.py    the same model scores every word for how unlikely it is
                   in context (top-20 next-word log-probabilities)
  3. a reader settles every flag of 1. against the sources
  4. marked.py     the sentences to read: the top 15% of the text by the
                   marker's score, and a random 5% of the rest as a check

GPU jobs, one at a time. Ollama is found at $FGB_OLLAMA (default
http://localhost:11434). Outputs belong under work/<book>/, never a temp
folder: these runs take hours. Both are resumable.

  ./fgb proof BOOK OUT.jsonl            1
  ./fgb gapmark BOOK OUT.json           2
  ./fgb marked OUT.json READ.txt        4

bench/ holds the planted-slip benchmark the policy was chosen with
(bench.py plants slips, bake.py runs models against them) and score.py
the marker's coverage at each share of the text.
"""

import os


def ollama_url():
    return os.environ.get("FGB_OLLAMA", "http://localhost:11434").rstrip("/") + "/api/generate"
