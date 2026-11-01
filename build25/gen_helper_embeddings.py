#!/usr/bin/env python3
"""Generate helper/ht-emb.bin — precomputed embeddings for every
helper-bot index entry, used by the Lambda's hybrid reranker.

Why this exists: the bot's client-side retrieval is keyword scoring,
which misses paraphrased questions ("the river out west" shares no
words with "Sacramento River at Freeport, CA"). A paraphrase battery
(56 labelled questions, weights tuned on a dev split) showed a
hybrid keyword+embedding rerank lifting held-out top-1 accuracy
from 0.071 to 0.500, so the embeddings ship — measured, not assumed.
See ~/workspace/hydrotwin_dev_build/status.md for the full results.

Embeddings come from bge-small-en-v1.5 (Q8_0 GGUF, 384-dim, CLS
pooling) served by llama.cpp's llama-server in embedding mode —
the same binary family the helper Lambda already runs, and nothing
embedding-related ever runs in the visitor's browser (an in-browser
model crashed mobile Safari tabs outright in v1-v3; that lesson
stands). The embedded text per entry is "title. text" — the variant
that won the battery tuning.

Vectors are stored unit-normalized and int8-quantized with a
per-entry scale (max|component|/127). The battery was re-scored
with exactly this quantization and the accuracies were unchanged.

Asset format (helper/ht-emb.bin, ~122 KB for 314 entries):
    6 bytes   magic "HTEMB1"
    uint32le  entry count n
    uint32le  dimension d
    16 bytes  md5 of "\n".join(entry ids) — the Lambda refuses to
              rerank if the ids of the index it fetched hash
              differently, so a stale asset can never silently
              scramble the ranking
    float32le scales[n]
    int8      quantized vectors, row-major n x d, row i = entry i
              of helper/ht-index.json (same pipeline run)

Environment:
    HT_LLAMA_SERVER  path to a llama-server binary (required)
    HT_EMBED_MODEL   path to the bge-small GGUF (required)
    HT_EMBED_PORT    scratch port for the throwaway server (18123)

Run from the repo root, AFTER gen_helper_index.py:
    python3 build25/gen_helper_embeddings.py
"""
import hashlib
import json
import os
import struct
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

import numpy as np

PORT = int(os.environ.get("HT_EMBED_PORT", "18123"))
BASE = f"http://127.0.0.1:{PORT}"


def wait_health(proc, deadline_s=120):
    end = time.time() + deadline_s
    while time.time() < end:
        if proc.poll() is not None:
            raise RuntimeError("llama-server exited during model load")
        try:
            with urllib.request.urlopen(BASE + "/health", timeout=3) as r:
                if r.status == 200:
                    return
        except Exception:
            pass
        time.sleep(0.5)
    raise RuntimeError("llama-server did not become healthy")


def embed(server_proc, texts):
    out = []
    for t in texts:
        body = json.dumps({"content": t}).encode()
        req = urllib.request.Request(BASE + "/embedding", data=body,
                                     headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=120) as r:
            data = json.loads(r.read().decode())
        out.append(np.array(data[0]["embedding"][0], dtype=np.float64))
    return np.stack(out)


def main():
    server_bin = os.environ.get("HT_LLAMA_SERVER")
    model = os.environ.get("HT_EMBED_MODEL")
    if not server_bin or not model:
        print("HT_LLAMA_SERVER and HT_EMBED_MODEL must be set", file=sys.stderr)
        return 1
    root = Path(".")
    index = json.loads((root / "helper" / "ht-index.json").read_text(encoding="utf-8"))
    entries = index["entries"]
    texts = [e["title"] + ". " + e["text"] for e in entries]

    env = dict(os.environ)
    bindir = str(Path(server_bin).resolve().parent)
    env["LD_LIBRARY_PATH"] = bindir + ":" + env.get("LD_LIBRARY_PATH", "")
    proc = subprocess.Popen(
        [server_bin, "-m", model, "--embedding", "--pooling", "cls",
         "-c", "512", "-t", "2", "--host", "127.0.0.1", "--port", str(PORT)],
        stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL, env=env)
    try:
        wait_health(proc)
        vecs = embed(proc, texts)
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except Exception:
            proc.kill()

    norms = np.linalg.norm(vecs, axis=1, keepdims=True)
    unit = vecs / np.maximum(norms, 1e-9)
    scales = (np.abs(unit).max(axis=1) / 127.0).astype(np.float32)
    q = np.round(unit / scales[:, None]).clip(-127, 127).astype(np.int8)

    ids = [e["id"] for e in entries]
    id_hash = hashlib.md5("\n".join(ids).encode()).digest()
    dest = root / "helper" / "ht-emb.bin"
    with open(dest, "wb") as f:
        f.write(b"HTEMB1")
        f.write(struct.pack("<II", len(entries), unit.shape[1]))
        f.write(id_hash)
        f.write(scales.tobytes())
        f.write(q.tobytes())
    print(f"helper/ht-emb.bin: {len(entries)} entries x {unit.shape[1]} dims, "
          f"{dest.stat().st_size} bytes")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
