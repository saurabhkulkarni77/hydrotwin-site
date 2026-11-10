#!/usr/bin/env python3
"""ACE (Agentic Context Engineering) for the HydroTwin helper bot —
shared library.

Implements, in Python, an exact mirror of the bot's production
retrieval path so a playbook can be evaluated offline before it is
allowed anywhere near the site:

  * `relevant()`  — the client relevance gate (helper/ht-helper.js),
  * `scored_list()` — the client keyword scoring (ht-helper.js),
  * `hybrid_order()` — the Lambda handler v3 rerank
    (build25/helper_lambda/handler.py `_rerank`): union pool over all
    entries, score = (1 - W_COS) * kw_norm + W_COS * cos, cosine
    clipped at 0, kw_norm from the client's top-10 candidates
    max-normalized, W_COS = 0.95, returns the top 3 ids.

The mirror is proven against the shipped JavaScript by
`mirror.mjs` + the `--check-mirror` mode of ace_eval.py: rankings and
gate decisions must agree on every battery question.

Playbook application mirrors the integration in
build25/gen_helper_index.py: a bullet of type "entry_keywords"
appends its keywords to that entry's keyword list (deduplicated).
Embeddings are computed from "title. text" only, so keyword bullets
never change entry vectors — the same is true on the site, where
helper/ht-emb.bin is regenerated from title+text at deploy time.
"""
import json
import re
from pathlib import Path

W_COS = 0.95          # handler.py HYBRID_W_COS (battery-tuned, shipped)
CANDIDATES_SENT = 10  # ht-helper.js retrieveCandidates(q, 10)

# Copied verbatim from helper/ht-helper.js (the gate's STOP set).
STOP = {
    "what", "where", "when", "which", "who", "why", "how",
    "is", "are", "was", "were", "do", "does", "did", "can", "could",
    "should", "would", "the", "a", "an", "and", "or", "of", "to",
    "in", "on", "at", "for", "with", "near", "me", "my", "i",
    "you", "your", "it", "its", "this", "that", "there", "tell", "please",
}

_WS = re.compile(r"\s+")
_NON = re.compile(r"[^a-z0-9 ]+")


def norm(s):
    """ht-helper.js norm(): lowercase, non [a-z0-9 ] -> space, squeeze."""
    s = _NON.sub(" ", str(s or "").lower())
    return _WS.sub(" ", s).strip()


def _toks(q):
    return [t for t in norm(q).split(" ") if len(t) > 1]


def scored_list(entries, q):
    """Mirror of ht-helper.js scoredList(): [(score, entry), ...]
    sorted by score descending, ties keep index order (stable sort
    in both V8 and Python). Only entries with score > 0 are kept."""
    nq = " " + norm(q) + " "
    toks = _toks(q)
    scored = []
    for e in entries:
        s = 0
        title = norm(e["title"])
        text = norm(e["text"])
        for kw_raw in e["keywords"]:
            kw = norm(kw_raw)
            if kw and (" " + kw + " ") in nq:
                s += 9
            elif kw and any(w in toks for w in kw.split(" ")):
                s += 3
        for t in toks:
            if t in title:
                s += 4
            if t in text:
                s += 1
        if e["kind"] == "station" and (" page " in nq or " open " in nq):
            s += 7
        if s > 0:
            scored.append((s, e))
    scored.sort(key=lambda x: -x[0])
    return scored


def retrieve(entries, q, n=3):
    return [e for _, e in scored_list(entries, q)[:n]]


def relevant(entries, q):
    """Mirror of ht-helper.js relevant() (the refusal gate)."""
    toks = [t for t in _toks(q) if t not in STOP]
    if not toks:
        return False
    for e in entries:
        title = norm(e["title"])
        for kw_raw in e["keywords"]:
            for w in norm(kw_raw).split(" "):
                if w in toks:
                    return True
        for t in toks:
            if t in title:
                return True
    return False


def hybrid_order(entries, q, entry_vecs, qvec):
    """Mirror of handler.py _rerank() for one question.

    entries: index entries in index order.
    entry_vecs: unit-normalized embedding per entry ("title. text").
    qvec: unit-normalized question embedding (raw question).
    Returns the top-3 entry ids by hybrid score."""
    import numpy as np

    cand = scored_list(entries, q)[:CANDIDATES_SENT]
    kw = {}
    top_score = 0.0
    ids = [e["id"] for e in entries]
    idset = set(ids)
    for s, e in cand:
        if e["id"] in idset and s > 0:
            kw[e["id"]] = float(s)
            top_score = max(top_score, float(s))
    cos = entry_vecs @ qvec
    cos = np.clip(cos, 0.0, None)
    scores = []
    for pos, eid in enumerate(ids):
        kw_norm = (kw.get(eid, 0.0) / top_score) if top_score else 0.0
        scores.append(((1.0 - W_COS) * kw_norm + W_COS * float(cos[pos]), pos))
    scores.sort(key=lambda x: -x[0])
    return [ids[pos] for _, pos in scores[:3]], scores


# ------------------------------------------------------------ playbook

def apply_playbook(entries, playbook):
    """Return a deep-copied entry list with the playbook's
    entry_keywords bullets merged (same semantics as the merge block
    in build25/gen_helper_index.py). Note-type bullets are knowledge
    for humans and do not change retrieval."""
    import copy

    out = copy.deepcopy(entries)
    by_id = {e["id"]: e for e in out}
    applied = []
    for b in (playbook or {}).get("bullets", []):
        if b.get("type") != "entry_keywords":
            continue
        e = by_id.get(b.get("entry"))
        if e is None:
            continue
        have = {norm(k) for k in e["keywords"]}
        for kw in b.get("add_keywords", []):
            if norm(kw) and norm(kw) not in have:
                e["keywords"].append(kw)
                have.add(norm(kw))
                applied.append((e["id"], kw))
    return out, applied


def load_index(path):
    d = json.loads(Path(path).read_text(encoding="utf-8"))
    return d["entries"]


def load_battery(path):
    d = json.loads(Path(path).read_text(encoding="utf-8"))
    return d["tasks"] if isinstance(d, dict) else d
