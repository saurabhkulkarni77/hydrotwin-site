#!/usr/bin/env python3
"""Run one full ACE cycle for the HydroTwin helper bot:

  Generator  = the bot pipeline itself, measured by ace_eval.py
               against the CURRENT playbook;
  Reflector  = ace_reflect.py (deterministic diagnosis + the
               project's Qwen2.5-3B proposing keywords);
  Curator    = ace_curate.py (validated, capped, evidence-tagged
               candidate playbook);
  Promotion  = the candidate is evaluated on the same batteries;
               it replaces playbook.json ONLY if the gate below
               passes. Otherwise the cycle is recorded as rejected
               and the shipped playbook is untouched.

Promotion rule (fixed before the first cycle ran; no post-hoc
adjustment):
  guards — all must hold versus the current playbook measured in
    the same run:
    G1 gate battery stays perfect (39/39 decisions);
    G2 paraphrase held-out hybrid top-3 does not drop;
    G3 explainer hybrid top-1 (all) does not drop;
    G4 paraphrase held-out hybrid top-1 does not drop;
  improvement — at least one must hold:
    I1 retrieval-all hybrid top-1 strictly improves, OR
    I2 retrieval-all keyword top-1 improves by >= 0.03 while
       retrieval-all hybrid top-1 does not drop
       (the keyword ranking is the instant answer a visitor sees
       before the rerank lands).

Usage:
  python3 run_cycle.py --index helper/ht-index.json --cycle 1 [--llm]
"""
import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).parent


def run(cmd):
    print("+", " ".join(str(c) for c in cmd))
    r = subprocess.run([sys.executable] + [str(c) for c in cmd],
                       capture_output=True, text=True)
    print(r.stdout.strip())
    if r.returncode != 0:
        print(r.stderr.strip(), file=sys.stderr)
        raise SystemExit(f"step failed: {cmd[0]}")
    return r.stdout


def load_results(p):
    return json.loads(Path(p).read_text(encoding="utf-8"))


def decide(before, after):
    b, a = before["summary"], after["summary"]
    guards = {
        "G1 gate perfect": a["gate"]["correct"] == a["gate"]["total"] == b["gate"]["total"],
        "G2 heldout hy top3": a["paraphrase"]["heldout"]["hy_top3"] >= b["paraphrase"]["heldout"]["hy_top3"],
        "G3 explainer hy top1": a["explainer"]["all"]["hy_top1"] >= b["explainer"]["all"]["hy_top1"],
        "G4 heldout hy top1": a["paraphrase"]["heldout"]["hy_top1"] >= b["paraphrase"]["heldout"]["hy_top1"],
    }
    improvements = {
        "I1 retrieval hy top1": a["retrieval_all"]["hy_top1"] > b["retrieval_all"]["hy_top1"],
        "I2 retrieval kw top1 +0.03, hy not down": (
            a["retrieval_all"]["kw_top1"] >= b["retrieval_all"]["kw_top1"] + 0.03
            and a["retrieval_all"]["hy_top1"] >= b["retrieval_all"]["hy_top1"]),
    }
    return guards, improvements, all(guards.values()) and any(improvements.values())


def fmt_row(name, s):
    v = s["retrieval_all"]
    return (f"| {name} | {s['gate']['correct']}/{s['gate']['total']} | "
            f"{s['paraphrase']['heldout']['hy_top1']:.3f} | "
            f"{s['paraphrase']['heldout']['hy_top3']:.3f} | "
            f"{v['hy_top1']:.3f} | {v['kw_top1']:.3f} | "
            f"{s['explainer']['all']['hy_top1']:.3f} |")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--index", required=True)
    ap.add_argument("--cycle", type=int, required=True)
    ap.add_argument("--llm", action="store_true")
    a = ap.parse_args()

    work = HERE / "runs" / f"cycle{a.cycle}"
    work.mkdir(parents=True, exist_ok=True)
    playbook = HERE / "playbook.json"
    current = json.loads(playbook.read_text(encoding="utf-8"))

    run([HERE / "ace_eval.py", "--index", a.index, "--playbook", playbook,
         "--label", f"cycle {a.cycle} before (playbook v{current['version']})",
         "--out", work / "eval_before.json"])
    refl_cmd = [HERE / "ace_reflect.py", "--results", work / "eval_before.json",
                "--index", a.index, "--out", work / "reflection.json"]
    if a.llm:
        refl_cmd.append("--llm")
    run(refl_cmd)
    run([HERE / "ace_curate.py", "--reflection", work / "reflection.json",
         "--playbook", playbook, "--cycle", a.cycle,
         "--out", work / "candidate.json"])
    run([HERE / "ace_eval.py", "--index", a.index, "--playbook", work / "candidate.json",
         "--label", f"cycle {a.cycle} candidate",
         "--out", work / "eval_after.json"])

    before = load_results(work / "eval_before.json")
    after = load_results(work / "eval_after.json")
    candidate = json.loads((work / "candidate.json").read_text(encoding="utf-8"))
    guards, improvements, promote = decide(before, after)

    lines = [
        f"# ACE cycle {a.cycle} — report",
        "",
        "| run | gate | paraphrase held-out hy top1 | hy top3 | retrieval hy top1 | retrieval kw top1 | explainer hy top1 |",
        "| --- | --- | --- | --- | --- | --- | --- |",
        fmt_row(f"playbook v{current['version']} (before)", before["summary"]),
        fmt_row(f"candidate v{candidate['version']}", after["summary"]),
        "",
        "Promotion guards: " + "; ".join(
            f"{k} {'PASS' if v else 'FAIL'}" for k, v in guards.items()),
        "Improvements: " + "; ".join(
            f"{k} {'YES' if v else 'no'}" for k, v in improvements.items()),
        "",
        f"**Decision: {'PROMOTED' if promote else 'REJECTED'}** — candidate "
        f"v{candidate['version']} {'replaces' if promote else 'does not replace'} "
        f"playbook v{current['version']}.",
        "",
        "New bullets in the candidate:",
    ]
    old_ids = {b["id"] for b in current.get("bullets", [])}
    for b in candidate["bullets"]:
        if b["id"] not in old_ids:
            lines.append(f"- `{b['id']}` **{b['entry']}** += {b['add_keywords']} "
                         f"(evidence: {len(b['evidence'])} failed questions; "
                         f"classes: {', '.join(b['failure_classes'])})")
    (work / "report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))

    if promote:
        shutil.copyfile(work / "candidate.json", playbook)
        with open(HERE / "playbook_changelog.md", "a", encoding="utf-8") as f:
            f.write(f"\n## v{candidate['version']} — cycle {a.cycle} (PROMOTED)\n\n")
            f.write("Measured on the full battery set in the same run "
                    "(see runs/cycle" + str(a.cycle) + "/report.md):\n\n")
            f.write(f"- gate: {before['summary']['gate']['correct']}/{before['summary']['gate']['total']}"
                    f" -> {after['summary']['gate']['correct']}/{after['summary']['gate']['total']}\n")
            f.write(f"- paraphrase held-out hybrid top-1: "
                    f"{before['summary']['paraphrase']['heldout']['hy_top1']:.3f} -> "
                    f"{after['summary']['paraphrase']['heldout']['hy_top1']:.3f}\n")
            f.write(f"- retrieval-all hybrid top-1: "
                    f"{before['summary']['retrieval_all']['hy_top1']:.3f} -> "
                    f"{after['summary']['retrieval_all']['hy_top1']:.3f}; keyword top-1: "
                    f"{before['summary']['retrieval_all']['kw_top1']:.3f} -> "
                    f"{after['summary']['retrieval_all']['kw_top1']:.3f}\n\n")
            for b in candidate["bullets"]:
                if b["id"] not in old_ids:
                    f.write(f"- `{b['id']}` {b['entry']} += {b['add_keywords']} "
                            f"(evidence: {'; '.join(b['evidence'])})\n")
        print("playbook.json promoted; changelog appended")
    else:
        with open(HERE / "playbook_changelog.md", "a", encoding="utf-8") as f:
            f.write(f"\n## cycle {a.cycle} candidate v{candidate['version']} — REJECTED\n\n"
                    f"Failed the promotion gate (guards: "
                    + "; ".join(f"{k} {'PASS' if v else 'FAIL'}" for k, v in guards.items())
                    + "). Playbook unchanged. Detail in runs/cycle"
                    + str(a.cycle) + "/report.md.\n")
        print("candidate rejected; playbook unchanged (rejection logged)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
