#!/usr/bin/env python3
"""ACE Curator: turn a reflection into a candidate playbook.

The Reflector proposes; the Curator disposes — deterministically.
Rules (the paper's incremental-delta discipline, made auditable):

  * only proposals the Reflector's validation marked valid are
    eligible — ungrounded or generic keywords never enter;
  * proposals are grouped per target entry into ONE bullet per
    entry per cycle, keywords deduplicated (normalized);
  * at most 3 new keywords per entry per cycle, ranked by number
    of supporting failures, then multiword phrases before single
    words (an exact phrase match is the strong +9 lever in this
    scoring), then shorter first;
  * every bullet records its evidence (the failed questions) and
    failure classes, so the playbook can be audited bullet by
    bullet;
  * the candidate is written next to the current playbook, never
    over it — run_cycle.py promotes only on a measured win.

Usage:
  python3 ace_curate.py --reflection runs/cycle1/reflection.json \
      --playbook playbook.json --cycle 1 --out runs/cycle1/candidate.json
"""
import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path

import ace_lib
from ace_lib import norm

MAX_KW_PER_ENTRY_PER_CYCLE = 3


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--reflection", required=True)
    ap.add_argument("--playbook", required=True)
    ap.add_argument("--cycle", type=int, required=True)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()

    refl = json.loads(Path(a.reflection).read_text(encoding="utf-8"))
    current = json.loads(Path(a.playbook).read_text(encoding="utf-8"))

    support = defaultdict(Counter)     # entry -> keyword -> evidence count
    evidence = defaultdict(list)       # (entry, keyword) -> [questions]
    classes = defaultdict(set)         # entry -> failure classes
    notes = defaultdict(list)          # entry -> reflector notes
    seen_prop = valid_prop = 0
    reject_reasons = Counter()
    for f in refl["failures"]:
        if not f.get("accept"):
            continue
        entry = f["accept"][0]
        for p in f.get("proposals", []):
            seen_prop += 1
            if not p["valid"]:
                reject_reasons[p["reason"]] += 1
                continue
            valid_prop += 1
            kw = norm(p["keyword"])
            support[entry][kw] += 1
            evidence[(entry, kw)].append(f["q"])
            classes[entry].add(f["failure_class"])
            if f.get("reflector_note"):
                notes[entry].append(f["reflector_note"])

    existing = {b["entry"]: {norm(k) for k in b.get("add_keywords", [])}
                for b in current.get("bullets", []) if b.get("type") == "entry_keywords"}
    new_bullets = []
    for i, (entry, counter) in enumerate(
            sorted(support.items(), key=lambda kv: -sum(kv[1].values())), start=1):
        ranked = sorted(counter.items(),
                        key=lambda kv: (-kv[1], -len(kv[0].split(" ")), len(kv[0])))
        chosen = []
        for kw, _cnt in ranked:
            if kw in existing.get(entry, set()):
                continue
            chosen.append(kw)
            if len(chosen) >= MAX_KW_PER_ENTRY_PER_CYCLE:
                break
        if not chosen:
            continue
        ev = sorted({q for kw in chosen for q in evidence[(entry, kw)]})
        new_bullets.append({
            "id": f"pb-{a.cycle}{i:03d}",
            "cycle": a.cycle,
            "type": "entry_keywords",
            "entry": entry,
            "add_keywords": chosen,
            "evidence": ev,
            "failure_classes": sorted(classes[entry]),
            "rationale": " ".join(sorted(set(notes[entry])))[:600],
        })

    candidate = {
        "version": current.get("version", 0) + 1,
        "note": current.get("note", ""),
        "bullets": current.get("bullets", []) + new_bullets,
    }
    outp = Path(a.out)
    outp.parent.mkdir(parents=True, exist_ok=True)
    outp.write_text(json.dumps(candidate, indent=1), encoding="utf-8")
    print(f"proposals: {seen_prop} seen, {valid_prop} valid, "
          f"rejected: {dict(reject_reasons)}")
    print(f"candidate playbook v{candidate['version']}: "
          f"{len(new_bullets)} new bullets, "
          f"{sum(len(b['add_keywords']) for b in new_bullets)} new keywords")
    for b in new_bullets:
        print(f"  {b['id']} {b['entry']}: {b['add_keywords']}")
    print(f"wrote {outp}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
