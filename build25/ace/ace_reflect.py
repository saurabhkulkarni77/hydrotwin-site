#!/usr/bin/env python3
"""ACE Reflector: read an eval run's failures and diagnose them.

Deterministic core (always runs): for every failed task, the facts —
gate decision, keyword rank and hybrid rank of the best accepted
entry, whether the accepted entry reached the hybrid candidate pool,
what the bot answered instead, and which question words the accepted
entry's keywords/title do not cover — classified into a failure
taxonomy. Diagnoses are computed from the actual retrieved-vs-
expected data; nothing is invented.

LLM pass (--llm, the project's own Qwen2.5-3B-Instruct run locally
by llama.cpp, the same GGUF the Lambda serves): for keyword-fixable
classes the model proposes up to 3 new keywords for the correct
entry. Every proposal is then validated by code: it must be short,
new, and GROUNDED — every word must appear in the question or in
the correct entry's own title/text — and it must contain at least
one reasonably distinctive word. Invalid proposals are kept in the
output with their rejection reason (auditable), never silently
dropped. With --no-llm, a deterministic n-gram miner proposes
instead, through the same validation.

Usage:
  python3 ace_reflect.py --results runs/baseline/results.json \
      --index helper/ht-index.json --out runs/cycle1/reflection.json [--llm]
"""
import argparse
import json
import re
import sys
import urllib.request
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))
import ace_lib
from ace_lib import norm

GENERIC = {
    "river", "station", "flow", "data", "page", "view", "the", "and",
    "for", "with", "what", "where", "when", "how", "why", "show",
    "me", "is", "it", "in", "on", "of", "to", "a", "an", "at", "by",
    "from", "that", "this", "there", "their", "its", "one", "some",
    "get", "see", "open", "find", "tell", "about", "near",
}
FIXABLE = {"MISSING_KEYWORDS", "WEAK_KEYWORD", "PANEL_CONFUSION", "STATION_CONFUSION",
           # a false refusal on an in-domain question is a gate-vocabulary
           # gap: the gate's vocabulary IS the index keyword/title words,
           # so a keyword bullet is exactly the fix.
           "FALSE_REFUSAL"}


def site_of(entry_id):
    m = re.search(r"-(\d{8})-", entry_id + "-")
    return m.group(1) if m else None


def classify(rec, entries_by_id):
    """Deterministic failure classification for one failed task."""
    if rec["battery"] == "gate":
        return ("FALSE_REFUSAL" if rec["expect"] == "answer" else "FALSE_PASS"), {}
    acc = rec["accept"]
    winner = rec["hy_top"][0] if rec["hy_top"] else None
    info = {
        "winner": winner,
        "kw_rank_accept": rec["kw_rank_accept"],
        "hy_rank_accept": rec["hy_rank_accept"],
        "in_candidate_pool": bool(rec["kw_rank_accept"] and rec["kw_rank_accept"] <= 10),
    }
    if not rec["gate"]:
        return "FALSE_REFUSAL", info
    if rec["kw_rank_accept"] is None:
        return "MISSING_KEYWORDS", info
    if rec["kw_rank_accept"] > 10:
        return "WEAK_KEYWORD", info
    acc_sites = {site_of(a) for a in acc}
    win_site = site_of(winner) if winner else None
    if winner and (win_site in acc_sites or
                   any(winner.replace("panel3d-", "panel-") == a or
                       a.replace("panel3d-", "panel-") == winner for a in acc)):
        return "PANEL_CONFUSION", info
    if rec["kw_rank_accept"] <= 3:
        return "COSINE_DOMINANT", info
    return "STATION_CONFUSION", info


def keyword_df(entries):
    """Document frequency of words across all entries' keywords+titles."""
    from collections import Counter
    df = Counter()
    for e in entries:
        words = set()
        for k in e["keywords"]:
            words.update(norm(k).split(" "))
        words.update(norm(e["title"]).split(" "))
        df.update(w for w in words if w)
    return df, len(entries)


def validate(kw, entry, question, df, n_entries):
    """A proposed keyword must be short, new, grounded in the
    question or the entry's own words, and carry at least one word
    that is not ambient vocabulary."""
    k = norm(kw)
    if not k:
        return False, "empty after normalization"
    words = k.split(" ")
    if len(words) > 5:
        return False, "too long (>5 words)"
    if k in {norm(x) for x in entry["keywords"]}:
        return False, "already a keyword of the entry"
    ground = set(norm(question).split(" ")) | set(norm(entry["title"] + " " + entry["text"]).split(" "))
    stray = [w for w in words if w not in ground]
    if stray:
        return False, f"ungrounded words: {stray}"
    distinctive = [w for w in words
                   if w not in GENERIC and w not in ace_lib.STOP
                   and df.get(w, 0) <= 0.6 * n_entries]
    if not distinctive:
        return False, "no distinctive word (all generic/high-frequency)"
    return True, "ok"


# ------------------------------------------------------------ LLM pass

LLM_URL = "http://127.0.0.1:18094/completion"

REFLECTOR_SYSTEM = (
    "You are the Reflector in an ACE (Agentic Context Engineering) loop for a "
    "website helper bot. The bot answers visitor questions by keyword-matching "
    "them against a site index; each index entry has a title and keywords. A "
    "visitor question matched the WRONG entry. Propose up to 3 NEW keywords for "
    "the CORRECT entry that would help this question and similar ones match it. "
    "Rules: keywords are short phrases or distinctive words a visitor might "
    "type; every word must come from the question or from the correct entry's "
    "title/text; never propose generic words alone (river, station, flow, data, "
    "page); do not repeat the entry's existing keywords. Reply with JSON only: "
    "{\"keywords\": [...], \"why\": \"one short sentence\"}"
)


def llm_propose(fail):
    user = (
        f"Visitor question: {fail['q']}\n"
        f"Correct entry: {fail['target_title']}\n"
        f"Its current keywords: {', '.join(fail['target_keywords'])}\n"
        f"Correct entry text: {fail['target_text'][:300]}\n"
        f"Wrong entry the bot picked: {fail['winner_title']}\n"
        f"Failure class: {fail['failure_class']}\n"
        f"Question words the correct entry's keywords/title do NOT cover: "
        f"{', '.join(fail.get('uncovered_question_words') or [])}"
    )
    prompt = (f"<|im_start|>system\n{REFLECTOR_SYSTEM}<|im_end|>\n"
              f"<|im_start|>user\n{user}<|im_end|>\n<|im_start|>assistant\n")
    body = json.dumps({"prompt": prompt, "n_predict": 220, "temperature": 0.2,
                       "stop": ["<|im_end|>"]}).encode()
    req = urllib.request.Request(LLM_URL, data=body,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=300) as r:
        out = json.loads(r.read().decode())["content"]
    m = re.search(r"\{.*\}", out, re.S)
    if not m:
        return [], out.strip()[:200]
    try:
        d = json.loads(m.group(0))
    except Exception:
        return [], out.strip()[:200]
    return [str(k) for k in d.get("keywords", [])][:3], str(d.get("why", ""))[:300]


def ngram_propose(fail, df, n_entries):
    """Deterministic fallback proposer: question n-grams carrying a
    distinctive word, longest first."""
    toks = [t for t in norm(fail["q"]).split(" ") if len(t) > 1]
    cands = []
    for n in (4, 3, 2):
        for i in range(len(toks) - n + 1):
            g = toks[i:i + n]
            if any(w not in GENERIC and w not in ace_lib.STOP
                   and df.get(w, 0) <= 0.6 * n_entries for w in g):
                cands.append(" ".join(g))
    seen, out = set(), []
    for c in cands:
        if c not in seen:
            seen.add(c)
            out.append(c)
        if len(out) >= 3:
            break
    return out, "deterministic n-gram proposal (no LLM)"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--results", required=True)
    ap.add_argument("--index", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--llm", action="store_true")
    a = ap.parse_args()

    entries = ace_lib.load_index(a.index)
    by_id = {e["id"]: e for e in entries}
    run = json.loads(Path(a.results).read_text(encoding="utf-8"))
    df, n_entries = keyword_df(entries)

    failures = []
    for rec in run["tasks"]:
        failed = (rec["battery"] == "gate" and not rec["gate_ok"]) or \
                 (rec["battery"] != "gate" and not rec["hit1_hy"])
        if not failed:
            continue
        cls, info = classify(rec, by_id)
        f = {"battery": rec["battery"], "q": rec["q"], "split": rec.get("split"),
             "failure_class": cls, **info}
        if rec["battery"] != "gate":
            tgt = by_id.get(rec["accept"][0])
            f["accept"] = rec["accept"]
            if tgt:
                f["target_title"] = tgt["title"]
                f["target_text"] = tgt["text"]
                f["target_keywords"] = tgt["keywords"]
            w = by_id.get(info.get("winner") or "")
            f["winner_title"] = w["title"] if w else None
            qtoks = {t for t in norm(rec["q"]).split(" ") if len(t) > 1}
            if tgt:
                covered = set()
                for k in tgt["keywords"]:
                    covered.update(norm(k).split(" "))
                covered.update(norm(tgt["title"]).split(" "))
                f["uncovered_question_words"] = sorted(qtoks - covered - ace_lib.STOP)
        failures.append(f)

    n_llm = 0
    for f in failures:
        f["proposals"] = []
        if f["failure_class"] not in FIXABLE or "target_title" not in f:
            continue
        tgt = by_id[f["accept"][0]]
        raw, why = [], ""
        if a.llm:
            try:
                raw, why = llm_propose(f)
                n_llm += 1
            except Exception as e:
                raw, why = ngram_propose(f, df, n_entries)
                why = f"LLM unavailable ({e}); " + why
        else:
            raw, why = ngram_propose(f, df, n_entries)
        f["reflector_note"] = why
        for kw in raw:
            ok, reason = validate(kw, tgt, f["q"], df, n_entries)
            f["proposals"].append({"keyword": kw, "valid": ok, "reason": reason})

    outp = Path(a.out)
    outp.parent.mkdir(parents=True, exist_ok=True)
    outp.write_text(json.dumps({
        "source_results": a.results,
        "llm_used": bool(a.llm), "llm_calls": n_llm,
        "failures": failures,
    }, indent=1), encoding="utf-8")
    from collections import Counter
    print("failure classes:", dict(Counter(f["failure_class"] for f in failures)))
    print(f"failures: {len(failures)}; with valid proposals: "
          f"{sum(1 for f in failures if any(p['valid'] for p in f['proposals']))}")
    print(f"wrote {outp}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
