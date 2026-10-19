#!/usr/bin/env python3
"""Continuous-training handoff validator (honest stub).

Heavy training does NOT run in this repo — it lives in
saurabhkulkarni77/hydrotwin-models (daily-retrain.yml, Sundays 08:00 UTC,
with drift_check.py wired in before training). This script validates a
retrain request against models/registry.json and prints the handoff
summary: which model(s), which data window, and the exact downstream
steps. It never trains anything and never claims to.

Usage: python retrain/handoff.py --model all|LSTM|... --data-end YYYY-MM-DD
       --reason "..."
"""
import argparse
import datetime as dt
import json
import os
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", required=True)
    ap.add_argument("--data-end", required=True)
    ap.add_argument("--reason", default="manual")
    args = ap.parse_args()

    registry = json.loads((ROOT / "models" / "registry.json")
                          .read_text(encoding="utf-8"))
    known = [m["name"] for m in registry["models"]]
    if args.model != "all" and args.model not in known:
        print(f"::error::unknown model {args.model!r}; known: {known}")
        return 1
    try:
        data_end = dt.date.fromisoformat(args.data_end)
    except ValueError:
        print(f"::error::--data-end must be YYYY-MM-DD, got {args.data_end!r}")
        return 1
    baked_end = dt.date.fromisoformat(
        registry["dataset"]["window"].split("/")[1])
    if data_end < baked_end:
        print(f"::error::--data-end {data_end} precedes the registry data "
              f"window end {baked_end}; a retrain must extend the window, "
              "not shrink it")
        return 1

    models = known if args.model == "all" else [args.model]
    summary = f"""## CT handoff — retrain request validated

- **Models:** {', '.join(models)}
- **Training data window:** {registry['dataset']['window'].split('/')[0]} .. {data_end}
- **Reason:** {args.reason}
- **Requested from:** hydrotwin-site, dev branch (this repo)

### Where training actually runs
`saurabhkulkarni77/hydrotwin-models` → `daily-retrain.yml`
(data refresh → `drift_check.py` → train all models on all data →
export ONNX/params). This workflow is the *request + validation* side
of continuous training only; it does not train models itself.

### Downstream steps after a models-repo run completes
1. New artifacts are baked into the site in hydrotwin-site (dev first).
2. Candidate metrics are computed on the frozen test era (WY2025-26).
3. `models/registry.json` here is updated in a PR — the **model
   validation gate** (`.github/workflows/model-gate.yml`) must pass:
   no production-stage pooled RMSE may regress >1% vs
   `models/baselines.json` without the `allow-regression` label.
4. CI (`tests/`) must pass and the dev deployment (deploy-dev) must
   pick the build up before it is considered good; promotion to
   production (main) stays a separate human decision.
"""
    print(summary)
    step_summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if step_summary:
        with open(step_summary, "a", encoding="utf-8") as f:
            f.write(summary)
    return 0


if __name__ == "__main__":
    sys.exit(main())
