#!/usr/bin/env python3
"""ACE repair pass: fix a rejected candidate's gate regressions.

Cycle 2's candidate improved retrieval a lot but broke the gate
guard (39/39 -> 37/39): three new keywords carried words that are
also ordinary off-topic vocabulary ('last' in "last station",
'capital' in "capital city" and "nation s capital"), flipping two
off-topic gate-battery questions to false passes.

This tool performs the deterministic repair a Curator should:

  1. find the gate tasks the candidate broke (vs the base eval);
  2. attribute each break to individual new keywords by ablation —
     add ONE candidate keyword at a time to the base index and see
     which single additions flip that gate decision;
  3. remove the culprit keywords from the candidate; where the
     removed phrase leaves a distinctive residue word that passes
     the Reflector's own validation (grounded in the bullet's
     evidence question or the entry's title/text), substitute it —
     recorded on the bullet either way;
  4. emit the repaired candidate (base bullets + repaired new
     bullets). Promotion still requires a full re-eval through
     run_cycle.decide — this tool never promotes by itself.

Usage:
  python3 ace_repair.py --index helper/ht-index.json \
      --base-playbook playbook.json --base-eval runs/cycle2/eval_before.json \
      --candidate runs/cycle2/candidate.json \
      --candidate-eval runs/cycle2/eval_after.json \
      --out runs/cycle3/candidate.json
"""
import argparse
import json
from pathlib import Path

import ace_lib
from ace_lib import norm
import ace_reflect


def gate_flips_with_keyword(entries, base_playbook, entry_id, kw, questions):
    """Questions whose gate decision flips when this single keyword
    is added (on top of the base playbook) to its entry."""
    trial = {"version": -1, "bullets": [
        {"type": "entry_keywords", "entry": entry_id, "add_keywords": [kw]}]}
    merged = list((base_playbook or {}).get("bullets", [])) + trial["bullets"]
    trial_entries, _ = ace_lib.apply_playbook(entries, {"bullets": merged})
    base_entries, _ = ace_lib.apply_playbook(entries, base_playbook)
    return [q for q in questions
            if ace_lib.relevant(base_entries, q) != ace_lib.relevant(trial_entries, q)]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--index", required=True)
    ap.add_argument("--base-playbook", required=True)
    ap.add_argument("--base-eval", required=True)
    ap.add_argument("--candidate", required=True)
    ap.add_argument("--candidate-eval", required=True)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()

    entries = ace_lib.load_index(a.index)
    by_id = {e["id"]: e for e in entries}
    base_pb = json.loads(Path(a.base_playbook).read_text(encoding="utf-8"))
    cand = json.loads(Path(a.candidate).read_text(encoding="utf-8"))
    base_tasks = {t["q"]: t for t in json.loads(Path(a.base_eval).read_text())["tasks"]
                  if t["battery"] == "gate"}
    cand_tasks = {t["q"]: t for t in json.loads(Path(a.candidate_eval).read_text())["tasks"]
                  if t["battery"] == "gate"}
    broken = [q for q in base_tasks
              if base_tasks[q]["gate_ok"] and not cand_tasks[q]["gate_ok"]]
    print("gate tasks broken by candidate:", broken)

    base_bullet_ids = {b["id"] for b in base_pb.get("bullets", [])}
    new_bullets = [b for b in cand["bullets"] if b["id"] not in base_bullet_ids]
    df, n_entries = ace_reflect.keyword_df(entries)

    culprits = {}   # (entry, keyword) -> [broken questions it flips]
    for b in new_bullets:
        for kw in b.get("add_keywords", []):
            flips = gate_flips_with_keyword(entries, base_pb, b["entry"], kw, broken)
            if flips:
                culprits[(b["entry"], kw)] = flips
    for k, v in culprits.items():
        print("culprit keyword:", k, "flips:", v)

    repaired_bullets = []
    repair_log = []
    for b in new_bullets:
        b = dict(b)
        kept, removed = [], []
        for kw in b.get("add_keywords", []):
            (removed if (b["entry"], kw) in culprits else kept).append(kw)
        subs = []
        for kw in removed:
            # distinctive residue: words of the phrase that are not
            # themselves the flipping word(s)
            flip_words = set()
            for q in culprits[(b["entry"], kw)]:
                flip_words |= {t for t in norm(q).split(" ") if len(t) > 1
                               and t not in ace_lib.STOP}
            # (words of length 1 can never be question tokens — the
            # client filters tokens to length > 1 — so they are not
            # valid residue; a bare "s" from a possessive would be a
            # nonsense keyword)
            residue = [w for w in norm(kw).split(" ")
                       if w not in flip_words and len(w) > 1]
            entry = by_id[b["entry"]]
            for w in residue:
                if w in kept or w in subs:
                    continue
                ok, _reason = ace_reflect.validate(
                    w, entry, b["evidence"][0] if b["evidence"] else "", df, n_entries)
                if ok:
                    subs.append(w)
            repair_log.append({"bullet": b["id"], "entry": b["entry"],
                               "removed": kw, "substituted": subs,
                               "because_flips": culprits[(b["entry"], kw)]})
        b["add_keywords"] = kept + subs
        if removed:
            b["repaired"] = {"removed_keywords": removed,
                             "substituted_keywords": subs}
        if b["add_keywords"]:
            repaired_bullets.append(b)

    out_pb = {"version": base_pb.get("version", 0) + 1,
              "note": base_pb.get("note", ""),
              "bullets": base_pb.get("bullets", []) + repaired_bullets}
    outp = Path(a.out)
    outp.parent.mkdir(parents=True, exist_ok=True)
    outp.write_text(json.dumps(out_pb, indent=1), encoding="utf-8")
    (outp.parent / "repair_log.json").write_text(
        json.dumps({"broken_gate_tasks": broken, "repairs": repair_log}, indent=1),
        encoding="utf-8")
    print(f"repaired candidate v{out_pb['version']}: {len(repaired_bullets)} bullets kept "
          f"({len(new_bullets)} before repair), {len(culprits)} culprit keywords removed")
    print(f"wrote {outp} and repair_log.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
