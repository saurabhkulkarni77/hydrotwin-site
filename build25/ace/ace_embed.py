#!/usr/bin/env python3
"""Embed index entries and battery questions for the ACE harness,
with the same model and settings the site uses: bge-small-en-v1.5
Q8_0, CLS pooling, llama.cpp llama-server --embedding; entry text is
"title. text", questions are embedded raw (the shipped hybrid
configuration, hybrid/chosen_config.json).

Results are cached in ace/cache/ keyed by a hash of the exact texts,
so re-evaluating an unchanged index costs nothing. Entry embeddings
depend only on title+text — playbook keyword bullets never change
them, exactly as on the site.

Env: HT_LLAMA_SERVER (llama-server binary), HT_EMBED_MODEL (GGUF).
Defaults point at this workspace's existing copies when present.
"""
import hashlib
import json
import os
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

import numpy as np

HERE = Path(__file__).parent
CACHE = HERE / "cache"
PORT = 18093
BASE = f"http://127.0.0.1:{PORT}"

_DEV_BUILD = HERE.parent.parent  # ~/workspace/hydrotwin_dev_build (when in build25/ace this misses; env wins)


def _default_server():
    for cand in [
        os.environ.get("HT_LLAMA_SERVER"),
        "/home/hatch/workspace/hydrotwin_dev_build/localtest/llama-b12032/llama-server",
    ]:
        if cand and Path(cand).exists():
            return cand
    return None


def _default_model():
    for cand in [
        os.environ.get("HT_EMBED_MODEL"),
        "/home/hatch/workspace/hydrotwin_dev_build/hybrid/bge-small-q8_0.gguf",
    ]:
        if cand and Path(cand).exists():
            return cand
    return None


def _embed_texts(texts):
    server_bin, model = _default_server(), _default_model()
    if not server_bin or not model:
        raise SystemExit("HT_LLAMA_SERVER / HT_EMBED_MODEL not found")
    env = dict(os.environ)
    bindir = str(Path(server_bin).resolve().parent)
    env["LD_LIBRARY_PATH"] = bindir + ":" + env.get("LD_LIBRARY_PATH", "")
    proc = subprocess.Popen(
        [server_bin, "-m", model, "--embedding", "--pooling", "cls",
         "-c", "512", "-t", "2", "--host", "127.0.0.1", "--port", str(PORT)],
        stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL, env=env)
    try:
        deadline = time.time() + 120
        while True:
            try:
                with urllib.request.urlopen(BASE + "/health", timeout=5) as r:
                    if r.status == 200:
                        break
            except Exception:
                if time.time() > deadline:
                    raise SystemExit("embedding server did not come up")
                time.sleep(1)
        out = []
        for t in texts:
            body = json.dumps({"content": t}).encode()
            req = urllib.request.Request(BASE + "/embedding", data=body,
                                         headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=120) as r:
                data = json.loads(r.read().decode())
            out.append([float(x) for x in data[0]["embedding"][0]])
        return np.array(out, dtype=np.float64)
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except Exception:
            proc.kill()


def _cached(name, texts):
    CACHE.mkdir(parents=True, exist_ok=True)
    key = hashlib.md5("\x00".join(texts).encode()).hexdigest()[:16]
    path = CACHE / f"{name}-{key}.npz"
    if path.exists():
        z = np.load(path)
        return z["vecs"]
    vecs = _embed_texts(texts)
    norms = np.linalg.norm(vecs, axis=1, keepdims=True)
    vecs = vecs / np.maximum(norms, 1e-9)
    np.savez_compressed(path, vecs=vecs)
    return vecs


def entry_embeddings(entries):
    """Unit-normalized embeddings of 'title. text' per entry."""
    texts = [e["title"] + ". " + e["text"] for e in entries]
    return _cached("entries", texts)


def question_embeddings(questions):
    return _cached("questions", list(questions))
