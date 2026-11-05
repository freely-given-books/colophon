"""The OCR engines, each reading a bundle's pages into <engine>/pages/.

  tesseract  CPU, several pages at a time; .txt, .tsv (word boxes), .hocr
  kraken     GPU, one batch call; .txt, and ALTO (.xml) with alto=True
  glm        GLM-OCR through Ollama, GPU, a page at a time; .txt, .json;
             retry_loops: the pages where it looped, again with a repeat penalty

Every run skips pages already read, so it can be stopped and resumed. The
GPU engines are never run side by side: run() takes one engine at a time.
"""

import base64
import concurrent.futures as cf
import json
import os
import shutil
import subprocess
import sys
import urllib.request
from pathlib import Path

TESSERACT_ARGS = ["--oem", "1", "--psm", "3", "-l", "eng"]
GLM = {"model": "glm-ocr:bf16", "prompt": "Text Recognition:",
       "options": {"temperature": 0, "num_ctx": 16384, "num_predict": 8192}}


def tesseract(bundle, pages, jobs=4):
    if not shutil.which("tesseract"):
        sys.exit("tesseract is not installed")
    out = bundle.engine_dir("tesseract")
    version = subprocess.run(["tesseract", "--version"], capture_output=True,
                             text=True).stdout.split("\n")[0]
    bundle.manifest("tesseract", {"version": version, "args": " ".join(TESSERACT_ARGS)})
    todo = [n for n in pages if not (out / f"{n:06d}.tsv").exists()]
    images = {n: bundle.page(n) for n in todo}     # rendered before the threads start

    def one(n):
        subprocess.run(["tesseract", str(images[n]), str(out / f"{n:06d}"), *TESSERACT_ARGS,
                        "txt", "tsv", "hocr"], check=True, capture_output=True)
        return n

    with cf.ThreadPoolExecutor(jobs) as ex:
        for n in ex.map(one, todo):
            print(f"tesseract: page {n}", flush=True)
    return len(todo)


def kraken(bundle, pages, alto=False, device="cuda:0"):
    exe, model = os.environ.get("FGB_KRAKEN"), os.environ.get("FGB_KRAKEN_MODEL")
    if not exe or not model:
        sys.exit("kraken: set FGB_KRAKEN (the kraken executable) and FGB_KRAKEN_MODEL "
                 "(a recognition model, e.g. CATMuS-Print fondue large)")
    out = bundle.engine_dir("kraken")
    bundle.manifest("kraken", {"model": Path(model).name, "device": device,
                               "version": subprocess.run([exe, "--version"], capture_output=True,
                                                         text=True).stdout.strip()})
    done = 0
    for suffix, fmt in ((".txt", []), (".xml", ["-a"])) if alto else ((".txt", []),):
        pairs = []
        for n in pages:
            dest = out / f"{n:06d}{suffix}"
            if not dest.exists():
                pairs += ["-i", str(bundle.page(n)), str(dest)]
        if pairs:
            log = bundle.dir / "kraken.log"
            with open(log, "a") as f:
                r = subprocess.run([exe, "-d", device, *fmt, *pairs, "segment", "-bl",
                                    "ocr", "-m", model], stdout=f, stderr=subprocess.STDOUT)
            if r.returncode:
                sys.exit(f"kraken failed (see {log})")
            done = max(done, len(pairs) // 3)    # pages, not passes
    return done


def looped(text, rec):
    """GLM ran away on a page: it hit the length limit, failed, or one
    four-word phrase repeats 8 times or more."""
    if rec.get("done_reason") == "length" or rec.get("status") != "recognized":
        return True
    words = text.split()
    if len(words) > 40:
        grams = [" ".join(words[i:i + 4]) for i in range(len(words) - 3)]
        return max(grams.count(g) for g in set(grams)) >= 8
    return False


def glm(bundle, pages, retry_loops=False):
    """retry_loops: read again, with a repeat penalty, the pages where GLM
    looped; the first reading is kept as NNNNNN.first.json."""
    url = os.environ.get("FGB_OLLAMA", "http://localhost:11434").rstrip("/") + "/api/generate"
    out = bundle.engine_dir("glm")
    bundle.manifest("glm", {"model": GLM["model"], "prompt": GLM["prompt"], **GLM["options"]})
    done = 0
    for n in pages:
        rec_f, txt_f = out / f"{n:06d}.json", out / f"{n:06d}.txt"
        options = GLM["options"]
        if retry_loops:
            if not rec_f.exists() or (out / f"{n:06d}.first.json").exists():
                continue
            if not looped(txt_f.read_text(encoding="utf-8") if txt_f.exists() else "",
                          json.loads(rec_f.read_text(encoding="utf-8"))):
                continue
            rec_f.rename(out / f"{n:06d}.first.json")
            options = {**options, "repeat_penalty": 1.15, "repeat_last_n": 256}
        elif rec_f.exists():
            continue
        body = json.dumps({**GLM, "options": options, "stream": False, "images": [
            base64.b64encode(bundle.page(n).read_bytes()).decode()]}).encode()
        rec = {"pdf_page": n, **({"retry": "repeat_penalty 1.15, repeat_last_n 256"}
                                 if retry_loops else {})}
        for attempt in (1, 2):       # a token-repeat loop or a timeout: once more
            try:
                req = urllib.request.Request(url, body, {"Content-Type": "application/json"})
                r = json.load(urllib.request.urlopen(req, timeout=600))
                rec.update(status="recognized", response=r["response"],
                           done_reason=r.get("done_reason"))
                break
            except Exception as e:  # noqa: BLE001
                rec.update(status="error", error=str(e), attempt=attempt)
        if rec["status"] == "recognized":
            (out / f"{n:06d}.txt").write_text(rec["response"], encoding="utf-8")
        (out / f"{n:06d}.json").write_text(json.dumps(rec, ensure_ascii=False), encoding="utf-8")
        print(f"glm: page {n} {rec['status']}", flush=True)
        done += 1
    return done


ENGINES = {"tesseract": tesseract, "kraken": kraken, "glm": glm}


def run(bundle, engine, pages, **kw):
    """One engine over the pages (a GPU engine alone on the GPU)."""
    if engine not in ENGINES:
        sys.exit(f"no engine {engine!r} (one of {', '.join(ENGINES)})")
    return ENGINES[engine](bundle, pages, **kw)
