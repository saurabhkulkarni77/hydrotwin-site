#!/usr/bin/env python3
"""ACE eval harness — the Generator's measuring instrument.

Runs the bot's production retrieval path (client keyword scoring +
relevance gate, Lambda hybrid rerank — all mirrored locally by
ace_lib.py and proven against the shipped JavaScript) over three
batteries:

  * gate (39):       refusal correctness both ways — in-domain
                     questions must be answered, off-topic refused.
  * paraphrase (56): paraphrases with dev/held-out splits; the
                     held-out hybrid top-1 is the promotion verdict.
  * explainer (20):  questions for the six explainer entries.

Scoring follows production behaviour: a gate-failed question counts
as a miss for every ranking method (the bot refuses before any
answer is shown). Every number this script prints is computed from
the index and batteries it was given — nothing is carried over
between runs.

Usage:
  python3 ace_eval.py --index helper/ht-index.json \
      [--playbook ace/playbook.json] --label baseline \
      --out ace/runs/baseline/results.json
  python3 ace_eval.py --index ... --check-mirror --helper helper/ht-helper.js
"""
import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))

import ace_lib
import ace_embed


def load_tasks():
    tasks = []
    for name in ("gate", "paraphrase", "explainer"):
        for t in ace_lib.load_battery(HERE / "batteries" / f"{name}.json"):
            t = dict(t)
            t["battery"] = name
            tasks.append(t)
    return tasks


def run_eval(index_path, playbook=None):
    entries = ace_lib.load_index(index_path)
    applied = []
    if playbook:
        entries, applied = ace_lib.apply_playbook(entries, playbook)
    tasks = load_tasks()
    questions = sorted({t["q"] for t in tasks})
    evecs = ace_embed.entry_embeddings(entries)
    qvecs = ace_embed.question_embeddings(questions)
    qpos = {q: i for i, q in enumerate(questions)}

    results = []
    for t in tasks:
        q = t["q"]
        gate = ace_lib.relevant(entries, q)
        rec = {"battery": t["battery"], "q": q, "gate": gate}
        if t["battery"] == "gate":
            rec["expect"] = t["expect"]
            rec["gate_ok"] = (gate == (t["expect"] == "answer"))
            results.append(rec)
            continue
        rec["accept"] = t["accept"]
        rec["split"] = t.get("split", "all")
        kw = ace_lib.scored_list(entries, q)
        kw_ids = [e["id"] for _, e in kw]
        hy_top, hy_scores = ace_lib.hybrid_order(entries, q, evecs, qvecs[qpos[q]])
        hy_ids = [entries[pos]["id"] for _, pos in hy_scores]
        rec["kw_top"] = kw_ids[:3]
        rec["hy_top"] = hy_top
        rec["kw_rank_accept"] = next(
            (i + 1 for i, x in enumerate(kw_ids) if x in t["accept"]), None)
        rec["hy_rank_accept"] = next(
            (i + 1 for i, x in enumerate(hy_ids) if x in t["accept"]), None)
        for meth, ids in (("kw", kw_ids), ("hy", hy_ids)):
            rec[f"hit1_{meth}"] = bool(gate and ids[:1] and ids[0] in t["accept"])
            rec[f"hit3_{meth}"] = bool(gate and any(x in t["accept"] for x in ids[:3]))
        results.append(rec)
    return entries, applied, results


def summarize(results):
    s = {}
    gate = [r for r in results if r["battery"] == "gate"]
    s["gate"] = {
        "correct": sum(r["gate_ok"] for r in gate),
        "total": len(gate),
        "false_refusals": sum(1 for r in gate if r["expect"] == "answer" and not r["gate"]),
        "false_passes": sum(1 for r in gate if r["expect"] == "refuse" and r["gate"]),
    }
    for batt in ("paraphrase", "explainer"):
        rows = [r for r in results if r["battery"] == batt]
        sub = {}
        for split in ("all", "dev", "heldout"):
            part = rows if split == "all" else [r for r in rows if r["split"] == split]
            if not part:
                continue
            sub[split] = {
                "n": len(part),
                "gate_failed": sum(1 for r in part if not r["gate"]),
                **{f"{m}_top{k}": round(sum(r[f"hit{k}_{m}"] for r in part) / len(part), 3)
                   for m in ("kw", "hy") for k in (1, 3)},
            }
        s[batt] = sub
    retr = [r for r in results if r["battery"] != "gate"]
    s["retrieval_all"] = {
        "n": len(retr),
        **{f"{m}_top{k}": round(sum(r[f"hit{k}_{m}"] for r in retr) / len(retr), 3)
           for m in ("kw", "hy") for k in (1, 3)},
    }
    return s


def print_summary(s):
    g = s["gate"]
    print(f"gate: {g['correct']}/{g['total']} decisions "
          f"(false refusals {g['false_refusals']}, false passes {g['false_passes']})")
    for batt in ("paraphrase", "explainer"):
        for split, v in s[batt].items():
            print(f"{batt}/{split} (n={v['n']}, gate-failed {v['gate_failed']}): "
                  f"kw top1 {v['kw_top1']:.3f} top3 {v['kw_top3']:.3f} | "
                  f"hy top1 {v['hy_top1']:.3f} top3 {v['hy_top3']:.3f}")
    v = s["retrieval_all"]
    print(f"retrieval all (n={v['n']}): kw top1 {v['kw_top1']:.3f} top3 {v['kw_top3']:.3f} | "
          f"hy top1 {v['hy_top1']:.3f} top3 {v['hy_top3']:.3f}")


def check_mirror(index_path, helper_path):
    entries = ace_lib.load_index(index_path)
    tasks = load_tasks()
    qs = [{"q": t["q"]} for t in tasks]
    tmp = HERE / "cache" / "_mirror_qs.json"
    tmp.parent.mkdir(parents=True, exist_ok=True)
    tmp.write_text(json.dumps(qs))
    out = subprocess.run(
        ["node", str(HERE / "mirror.mjs"), str(helper_path), str(index_path), str(tmp)],
        capture_output=True, text=True)
    if out.returncode != 0:
        print(out.stderr)
        return False
    js = json.loads(out.stdout)
    bad = 0
    for t, j in zip(tasks, js):
        gate = ace_lib.relevant(entries, t["q"])
        kw = ace_lib.scored_list(entries, t["q"])[:10]
        kw_js = [(x["id"], x["score"]) for x in j["kw"]]
        kw_py = [(e["id"], s) for s, e in kw]
        if gate != j["gate"] or kw_js != kw_py:
            bad += 1
            print(f"MISMATCH {t['q']!r}: gate js={j['gate']} py={gate}; "
                  f"kw js={kw_js[:3]} py={kw_py[:3]}")
    print(f"mirror check: {len(tasks) - bad}/{len(tasks)} questions agree "
          f"(gate + keyword top-10 ids and scores)")
    return bad == 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--index", required=True)
    ap.add_argument("--playbook")
    ap.add_argument("--label", default="run")
    ap.add_argument("--out")
    ap.add_argument("--check-mirror", action="store_true")
    ap.add_argument("--helper")
    a = ap.parse_args()

    if a.check_mirror:
        if not a.helper:
            print("--check-mirror needs --helper", file=sys.stderr)
            return 2
        return 0 if check_mirror(a.index, a.helper) else 1

    playbook = None
    if a.playbook:
        playbook = json.loads(Path(a.playbook).read_text(encoding="utf-8"))
    entries, applied, results = run_eval(a.index, playbook)
    summary = summarize(results)
    print(f"== {a.label} ==")
    print_summary(summary)
    if applied:
        print(f"playbook bullets applied: {len(applied)} keyword additions")
    if a.out:
        outp = Path(a.out)
        outp.parent.mkdir(parents=True, exist_ok=True)
        outp.write_text(json.dumps({
            "label": a.label,
            "index_md5": hashlib.md5(Path(a.index).read_bytes()).hexdigest(),
            "playbook_version": (playbook or {}).get("version"),
            "applied_keywords": applied,
            "summary": summary,
            "tasks": results,
        }, indent=1), encoding="utf-8")
        print(f"wrote {outp}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
