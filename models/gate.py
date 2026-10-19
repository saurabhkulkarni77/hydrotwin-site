#!/usr/bin/env python3
"""Model validation gate for the HydroTwin registry (dev overlay).

Compares models/registry.json against the frozen models/baselines.json.

Fails (exit 1) when:
  * the registry's model set differs from the baselines' model set,
  * the registry's dataset window differs from the baselines' window,
  * any production-stage model's pooled daily or weekly RMSE regresses
    by more than the registry's tolerance (default 1% relative) versus
    its baseline.

A regression can be accepted deliberately by passing --allow-regression
(the `allow-regression` PR label; see .github/workflows/model-gate.yml),
which downgrades regressions to warnings. Structural problems always fail.

Usage: python models/gate.py [--allow-regression]
"""
import argparse
import json
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent


def load(name):
    with open(HERE / name, encoding="utf-8") as f:
        return json.load(f)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--allow-regression", action="store_true",
                    help="accept production-metric regressions (PR label override)")
    args = ap.parse_args()

    registry = load("registry.json")
    baselines = load("baselines.json")
    problems = []

    reg_models = {m["name"]: m for m in registry["models"]}
    base_names = set(baselines["daily_rmse"]) | set(baselines["weekly_rmse"])
    if set(reg_models) != base_names:
        problems.append(
            f"model set mismatch: registry={sorted(reg_models)} "
            f"baselines={sorted(base_names)}")

    window = registry["dataset"]["window"]
    bw = baselines["dataset_window"]
    if window != f"{bw['start']}/{bw['end']}":
        problems.append(
            f"dataset window mismatch: registry {window} vs baselines "
            f"{bw['start']}/{bw['end']}")

    tol = float(registry.get("gate", {}).get("tolerance_rel", 0.01))
    regressions = []
    for name, model in sorted(reg_models.items()):
        if model.get("stage") != "production":
            continue
        for metric, base_table in (("daily_rmse", baselines["daily_rmse"]),
                                   ("weekly_rmse", baselines["weekly_rmse"])):
            base = base_table.get(name)
            cur = model.get(metric)
            if base is None or cur is None:
                problems.append(f"{name}: missing {metric} (registry or baseline)")
                continue
            if cur <= 0:
                problems.append(f"{name}: non-positive {metric} {cur}")
                continue
            rel = (cur - base) / base
            status = "ok"
            if rel > tol:
                status = "REGRESSION"
                regressions.append(
                    f"{name} {metric}: {cur} vs baseline {base} "
                    f"({rel:+.2%} > tolerance {tol:.0%})")
            print(f"gate: {name:12s} {metric:11s} {cur:.4f} vs {base:.4f} "
                  f"({rel:+.2%}) {status}")

    for p in problems:
        print(f"::error::gate: {p}")

    if regressions:
        for r in regressions:
            if args.allow_regression:
                print(f"::warning::gate: regression accepted via override: {r}")
            else:
                print(f"::error::gate: {r}")
        if not args.allow_regression:
            print("gate: FAIL — production metric regression without the "
                  "'allow-regression' label")
            return 1

    if problems:
        print("gate: FAIL — structural problems above")
        return 1

    print("gate: PASS"
          + (" (with accepted regressions)" if regressions else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
