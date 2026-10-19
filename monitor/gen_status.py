#!/usr/bin/env python3
"""Generate mlops-status.json + the pre-rendered mlops.html.

The MLOps status page (mlops.html) is data-driven: everything it shows
comes from the snapshot this script builds, which is regenerated from
the repo's own sources of truth — never hand-edited. The snapshot is
written to mlops-status.json, and mlops.html is then pre-rendered
from that same snapshot by monitor/gen_page.py, so the page displays
its data with no client-side fetch (a fetch-based first version could
sit forever on a "Loading status..." placeholder if the async chain
failed). Sources:

  * models/registry.json + models/baselines.json -> registry table,
    champions, gate settings, per-model delta vs the frozen baselines.
  * drift/drift_bake.json, drift/drift_report.json and the sidecar
    families -> the monitoring section. The drift/freshness/coverage
    computations mirror monitor/monitor.py exactly (same thresholds:
    PSI > 0.25 = breach, DACP lag allowance 14 days).
  * A GitHub Actions "list workflow runs" API response (--runs) ->
    the latest run per workflow for the pipeline-status section.
  * A GitHub issues list response for the `mlops-monitor` label
    (--issues) -> the tracking-issue link.

Usage:
  python monitor/gen_status.py [--root PATH] [--runs runs.json]
                               [--issues issues.json]
                               [--out mlops-status.json]

--runs / --issues are optional; without them the corresponding section
records nulls and the page says so. In CI, .github/workflows/status.yml
produces both files with `gh api` and commits the regenerated snapshot
with [skip ci].
"""
import argparse
import datetime as dt
import json
import pathlib

PSI_THRESHOLD = 0.25
DACP_LAG_DAYS = 14
SIDECAR_FAMILIES = ("dacp", "dacpw", "dacpm", "dacpy", "weekly",
                    "monthly", "yearly", "soilsnow", "corr", "chart3d")
REPO = "saurabhkulkarni77/hydrotwin-site"

# Display metadata for the station gauges (names as on the site map).
STATION_NAMES = {
    "01463500": "Delaware River at Trenton, NJ",
    "01646500": "Potomac River at Little Falls, MD",
    "02320500": "Suwannee River at Branford, FL",
    "03294500": "Ohio River at Louisville, KY",
    "05331000": "Mississippi River at St. Paul, MN",
    "06214500": "Yellowstone River at Billings, MT",
    "06934500": "Missouri River at Hermann, MO",
    "07374000": "Mississippi River at Baton Rouge, LA",
    "08057000": "Trinity River at Dallas, TX",
    "08158000": "Colorado River at Austin, TX",
    "08313000": "Rio Grande at Otowi Bridge, NM",
    "09380000": "Colorado River at Lees Ferry, AZ",
    "11447650": "Sacramento River at Freeport, CA",
    "14105700": "Columbia River at The Dalles, OR",
}

FEATURE_LABELS = {
    "tmax_c": "tmax (°C)",
    "tmin_c": "tmin (°C)",
    "tmean_c": "tmean (°C)",
    "precip_mm": "precip (mm)",
    "log10_flow": "log10 flow",
}

# The pipeline whose latest runs the page reports on. Keys are the
# workflow file paths exactly as returned by the Actions API.
WORKFLOWS = [
    (".github/workflows/ci.yml", "CI — site, data & model tests"),
    (".github/workflows/model-gate.yml", "Model validation gate"),
    (".github/workflows/monitor.yml", "MLOps monitor — drift & freshness"),
    (".github/workflows/retrain.yml", "CT — retrain handoff (stub)"),
    (".github/workflows/release.yml", "Release — site ZIP"),
    (".github/workflows/deploy-dev.yml", "Deploy DEV to AWS S3"),
]

# Every automation in this repo and what fires it. Rendered by
# mlops.html as the triggers table.
TRIGGERS = [
    {
        "automation": "CI test suite",
        "fires_when": "Every pull request, and every push to the dev branch",
        "what_happens": "267 pytest checks: station-page patch-marker "
                        "integrity, HT_DATA contracts (n=9131 from "
                        "2001-10-01), sidecar schemas, internal links.",
        "workflow": ".github/workflows/ci.yml",
    },
    {
        "automation": "Model validation gate",
        "fires_when": "Pull requests touching models/** — including "
                      "when the allow-regression label is added",
        "what_happens": "Fails the PR if a production-stage model's "
                        "pooled RMSE regresses more than 1% (relative) "
                        "against models/baselines.json, unless the PR "
                        "carries the allow-regression label.",
        "workflow": ".github/workflows/model-gate.yml",
    },
    {
        "automation": "Drift & freshness monitor",
        "fires_when": "Schedule: Mondays 09:17 UTC · or manual dispatch",
        "what_happens": "Recomputes PSI drift, freshness and sidecar "
                        "coverage from this repo's baked data; on any "
                        "breach it opens (or updates) the single "
                        "mlops-monitor tracking issue. Silent otherwise.",
        "workflow": ".github/workflows/monitor.yml",
    },
    {
        "automation": "Retrain handoff (CT)",
        "fires_when": "Manual dispatch",
        "what_happens": "Validates a retrain request (model + data "
                        "window) against models/registry.json and "
                        "records the handoff to hydrotwin-models, "
                        "where the heavy training actually runs.",
        "workflow": ".github/workflows/retrain.yml",
    },
    {
        "automation": "Release",
        "fires_when": "Push of a version tag (v*) · or manual dispatch",
        "what_happens": "Builds the GitHub-flavor site ZIP (no .github/) "
                        "and publishes it as a GitHub Release with "
                        "auto-generated notes.",
        "workflow": ".github/workflows/release.yml",
    },
    {
        "automation": "Status snapshot (this page)",
        "fires_when": "When the CI, gate, monitor, retrain or release "
                      "workflows complete · or manual dispatch",
        "what_happens": "Regenerates mlops-status.json from the "
                        "registry, baked drift data and the latest "
                        "Actions runs, and commits it back ([skip ci]) "
                        "so this page stays current.",
        "workflow": ".github/workflows/status.yml",
    },
]


def load(root, *parts):
    with open(root.joinpath(*parts), encoding="utf-8") as f:
        return json.load(f)


def rel_delta(value, baseline):
    if baseline in (None, 0):
        return None
    return (value - baseline) / baseline


def registry_section(root):
    reg = load(root, "models", "registry.json")
    base = load(root, "models", "baselines.json")
    models = []
    for m in reg["models"]:
        name = m["name"]
        bd = base["daily_rmse"].get(name)
        bw = base["weekly_rmse"].get(name)
        dd = rel_delta(m["daily_rmse"], bd)
        dw = rel_delta(m["weekly_rmse"], bw)
        at = (dd is not None and dw is not None
              and abs(dd) <= 1e-9 and abs(dw) <= 1e-9)
        models.append({
            "name": name,
            "version": m["version"],
            "stage": m["stage"],
            "daily_rmse": m["daily_rmse"],
            "weekly_rmse": m["weekly_rmse"],
            "baseline_daily_rmse": bd,
            "baseline_weekly_rmse": bw,
            "daily_delta_rel": None if dd is None else round(dd, 6),
            "weekly_delta_rel": None if dw is None else round(dw, 6),
            "vs_baseline": "at baseline" if at else "changed",
        })
    return {
        "dataset_window": reg["dataset"]["window"],
        "train": reg["dataset"]["train"],
        "validation": reg["dataset"]["validation"],
        "test": reg["dataset"]["test"],
        "champions": reg["champions"],
        "gate": {
            "tolerance_rel": reg["gate"]["tolerance_rel"],
            "override_label": reg["gate"]["override_label"],
        },
        "baselines_frozen_at": base.get("frozen_at"),
        "models": models,
    }


def monitoring_section(root):
    # Axis end from soilsnow (start + n - 1 days) — same as monitor.py.
    probe = load(root, "soilsnow", "01463500.json")
    axis_start = dt.date.fromisoformat(probe["start"])
    axis_end = axis_start + dt.timedelta(days=int(probe["n"]) - 1)

    bake = load(root, "drift", "drift_bake.json")
    stations = sorted(bake)
    rows = []
    for site in stations:
        feats = bake[site]["data"]["features"]
        worst = max(feats, key=feats.get)
        psi = feats[worst]
        rows.append({
            "site": site,
            "name": STATION_NAMES.get(site, ""),
            "worst_feature": worst,
            "worst_feature_label": FEATURE_LABELS.get(worst, worst),
            "psi": round(psi, 4),
            "baked_status": bake[site]["data"]["status"],
            "breach": psi > PSI_THRESHOLD,
        })
    rows.sort(key=lambda r: -r["psi"])
    breaches = [r for r in rows if r["breach"]]

    report = load(root, "drift", "drift_report.json")
    recent_end = dt.date.fromisoformat(report["windows"]["recent"][1])
    dacp_last = None
    for site in stations:
        dates = load(root, "dacp", f"{site}.json")["dates"]
        last = dt.date.fromisoformat(dates[-1])
        dacp_last = last if dacp_last is None else max(dacp_last, last)
    dacp_lag = (axis_end - dacp_last).days if dacp_last else None

    coverage_problems = []
    for family in SIDECAR_FAMILIES:
        files = sorted(p.stem for p in (root / family).glob("*.json"))
        if files != stations:
            coverage_problems.append(
                f"{family}/ holds {len(files)} files, expected "
                f"{len(stations)}")
            continue
        for site in stations:
            obj = load(root, family, f"{site}.json")
            if family == "chart3d":
                got = (obj.get("station") or {}).get("stationId", "")
                got = got.removeprefix("USGS-")
            else:
                got = obj.get("site")
            if got != site:
                coverage_problems.append(
                    f"{family}/{site}.json has site={got!r}")

    return {
        "psi_threshold": PSI_THRESHOLD,
        "stations_total": len(stations),
        "breach_count": len(breaches),
        "breach_feature": (breaches[0]["worst_feature"]
                           if breaches and len({b["worst_feature"]
                                                 for b in breaches}) == 1
                           else None),
        "stations": rows,
        "freshness": {
            "axis_start": str(axis_start),
            "axis_end": str(axis_end),
            "drift_report_recent_end": str(recent_end),
            "drift_report_current": recent_end == axis_end,
            "dacp_latest": str(dacp_last) if dacp_last else None,
            "dacp_lag_days": dacp_lag,
            "dacp_ok": dacp_lag is not None and dacp_lag <= DACP_LAG_DAYS,
        },
        "coverage": {
            "families": list(SIDECAR_FAMILIES),
            "ok": not coverage_problems,
            "problems": coverage_problems,
        },
    }


def workflows_section(runs_data):
    latest = {}
    runs = []
    if runs_data:
        runs = (runs_data.get("workflow_runs", [])
                if isinstance(runs_data, dict) else runs_data)
    for r in runs:
        path = r.get("path")
        if path and (path not in latest
                     or r["created_at"] > latest[path]["created_at"]):
            latest[path] = r
    out = []
    for path, display in WORKFLOWS:
        r = latest.get(path)
        entry = {"file": path, "name": display, "latest": None}
        if r:
            entry["latest"] = {
                "run_id": r["id"],
                "title": r.get("display_title") or r.get("name"),
                "event": r.get("event"),
                "status": r.get("status"),
                "conclusion": r.get("conclusion"),
                "created_at": r.get("created_at"),
                "updated_at": r.get("updated_at"),
                "url": r.get("html_url"),
            }
        out.append(entry)
    return out


def issue_section(issues_data):
    issues = []
    if issues_data:
        issues = (issues_data if isinstance(issues_data, list)
                  else issues_data.get("issues", []))
    issues = [i for i in issues if "pull_request" not in i]
    if not issues:
        return None
    i = max(issues, key=lambda x: x.get("updated_at", ""))
    return {
        "number": i["number"],
        "title": i["title"],
        "state": i["state"],
        "url": i["html_url"],
        "updated_at": i.get("updated_at"),
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=None)
    ap.add_argument("--runs", default=None,
                    help="GitHub API list-workflow-runs JSON file")
    ap.add_argument("--issues", default=None,
                    help="GitHub API list-issues JSON file")
    ap.add_argument("--out", default=None)
    args = ap.parse_args()

    root = (pathlib.Path(args.root).resolve() if args.root
            else pathlib.Path(__file__).resolve().parent.parent)
    out_path = (pathlib.Path(args.out) if args.out
                else root / "mlops-status.json")

    runs_data = None
    if args.runs:
        with open(args.runs, encoding="utf-8") as f:
            runs_data = json.load(f)
    issues_data = None
    if args.issues:
        with open(args.issues, encoding="utf-8") as f:
            issues_data = json.load(f)

    monitoring = monitoring_section(root)
    monitoring["issue"] = issue_section(issues_data)

    status = {
        "schema": 1,
        "generated_at": dt.datetime.now(dt.timezone.utc)
                        .strftime("%Y-%m-%dT%H:%M:%SZ"),
        "repo": REPO,
        "links": {
            "repo": f"https://github.com/{REPO}",
            "actions": f"https://github.com/{REPO}/actions",
            "monitor_issues":
                f"https://github.com/{REPO}/issues?q=label%3Amlops-monitor",
            "releases": f"https://github.com/{REPO}/releases",
            "mlops_doc": "MLOPS.md",
            "status_json": "mlops-status.json",
        },
        "triggers": TRIGGERS,
        "registry": registry_section(root),
        "monitoring": monitoring,
        "workflows": workflows_section(runs_data),
    }
    out_path.write_text(json.dumps(status, indent=2) + "\n",
                        encoding="utf-8")

    # Pre-render mlops.html from the same snapshot (the JSON stays the
    # data source; the page needs no client-side fetch to display).
    import gen_page
    html_path = root / "mlops.html"
    html_path.write_text(gen_page.render_html(status), encoding="utf-8")
    print(f"wrote {html_path} (pre-rendered from the snapshot)")

    print(f"wrote {out_path}: {len(status['registry']['models'])} models, "
          f"{monitoring['breach_count']}/{monitoring['stations_total']} "
          f"stations breaching PSI {PSI_THRESHOLD}, workflows: "
          + ", ".join(f"{w['name'].split('—')[0].strip()}="
                      f"{(w['latest'] or {}).get('conclusion')}"
                      for w in status["workflows"]))


if __name__ == "__main__":
    main()
