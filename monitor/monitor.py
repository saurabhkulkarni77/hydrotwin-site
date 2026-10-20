#!/usr/bin/env python3
"""HydroTwin (dev) MLOps monitor — lightweight drift & freshness checks.

Recomputes, from this repo's own baked artifacts (no external calls):

  * Drift: per-station worst-feature PSI from drift/drift_bake.json.
    Breach: PSI > 0.25 (the project's drift threshold; <0.10 stable,
    0.10-0.25 watch, >0.25 drift).
  * Freshness: drift/drift_report.json's recent window must end on the
    site data axis end (derived from soilsnow: start + n - 1 days), and
    the daily DACP sidecars must reach within 14 days of the axis end.
  * Coverage: every sidecar family (dacp/, dacpw/, dacpm/, dacpy/,
    weekly/, monthly/, yearly/, soilsnow/, corr/, chart3d/) holds
    exactly one parseable JSON per station, with a matching site id
    (chart3d carries it as station.stationId).

Writes a Markdown report (default ./monitor_report.md) and, when running
in GitHub Actions, sets the step outputs `breach` and `breach_count`.
Exit code is 0 when the checks ran (findings are reported, not failed);
operational errors (missing/corrupt inputs) exit 1 so a broken monitor
is visible instead of silently green.

Usage: python monitor/monitor.py [--root PATH] [--report PATH]
"""
import argparse
import datetime as dt
import json
import os
import pathlib
import sys

PSI_THRESHOLD = 0.25
DACP_LAG_DAYS = 14
SIDECAR_FAMILIES = ("dacp", "dacpw", "dacpm", "dacpy", "weekly",
                    "monthly", "yearly", "soilsnow", "corr", "chart3d")


def load(root, *parts):
    with open(root.joinpath(*parts), encoding="utf-8") as f:
        return json.load(f)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=None,
                    help="repo root (default: parent of this script's dir)")
    ap.add_argument("--report", default="monitor_report.md")
    args = ap.parse_args()

    root = (pathlib.Path(args.root).resolve() if args.root
            else pathlib.Path(__file__).resolve().parent.parent)

    findings = []   # threshold breaches / inconsistencies -> issue
    notes = []      # informational

    # --- axis end from soilsnow (start + n - 1 days) -------------------
    probe = load(root, "soilsnow", "01463500.json")
    axis_start = dt.date.fromisoformat(probe["start"])
    axis_end = axis_start + dt.timedelta(days=int(probe["n"]) - 1)
    notes.append(f"Site data axis: {axis_start} .. {axis_end} "
                 f"({probe['n']} days)")

    # --- drift breaches -------------------------------------------------
    bake = load(root, "drift", "drift_bake.json")
    stations = sorted(bake)
    drift_rows = []
    for site in stations:
        feats = bake[site]["data"]["features"]
        worst = max(feats, key=feats.get)
        psi = feats[worst]
        drift_rows.append((site, worst, psi, bake[site]["data"]["status"]))
        if psi > PSI_THRESHOLD:
            findings.append(
                f"**{site}** — worst feature `{worst}` PSI **{psi:.3f}** "
                f"> {PSI_THRESHOLD} (baked status: {bake[site]['data']['status']})")
    n_drift = sum(1 for _, _, p, _ in drift_rows if p > PSI_THRESHOLD)
    notes.append(f"Drift: {n_drift}/{len(stations)} stations above PSI "
                 f"{PSI_THRESHOLD} (all on log10_flow unless noted).")

    # --- freshness -------------------------------------------------------
    report = load(root, "drift", "drift_report.json")
    recent_end = dt.date.fromisoformat(report["windows"]["recent"][1])
    if recent_end != axis_end:
        findings.append(
            f"**Freshness** — drift report recent window ends {recent_end}, "
            f"site axis ends {axis_end}.")
    else:
        notes.append(f"Freshness: drift report current through {recent_end}.")

    dacp_last = None
    for site in stations:
        dates = load(root, "dacp", f"{site}.json")["dates"]
        last = dt.date.fromisoformat(dates[-1])
        dacp_last = last if dacp_last is None else max(dacp_last, last)
    if dacp_last and (axis_end - dacp_last).days > DACP_LAG_DAYS:
        findings.append(
            f"**Freshness** — latest daily DACP sidecar date {dacp_last} lags "
            f"the axis end {axis_end} by {(axis_end - dacp_last).days} days "
            f"(> {DACP_LAG_DAYS}).")
    else:
        notes.append(f"Freshness: daily DACP sidecars reach {dacp_last}.")

    # --- sidecar coverage -------------------------------------------------
    for family in SIDECAR_FAMILIES:
        files = sorted(p.stem for p in (root / family).glob("*.json"))
        if files != stations:
            findings.append(
                f"**Coverage** — {family}/ holds {len(files)} files, "
                f"expected the {len(stations)} stations.")
            continue
        for site in stations:
            obj = load(root, family, f"{site}.json")
            if family == "chart3d":
                got = (obj.get("station") or {}).get("stationId", "")
                got = got.removeprefix("USGS-")
            else:
                got = obj.get("site")
            if got != site:
                findings.append(
                    f"**Coverage** — {family}/{site}.json has site="
                    f"{obj.get('site')!r}.")
    notes.append("Coverage: " + ", ".join(f + "/" for f in SIDECAR_FAMILIES) +
                 " checked against the station list.")

    # --- report -----------------------------------------------------------
    today = dt.datetime.now(dt.timezone.utc).date()
    lines = [
        "## HydroTwin (dev) — MLOps monitor report",
        "",
        f"Run date (UTC): {today}. Source: this repo's baked drift data "
        "and sidecars (no external calls).",
        "",
        "### Findings" if findings else "### Findings: none",
        "",
    ]
    lines += [f"- {f}" for f in findings] or ["- No threshold breaches."]
    lines += ["", "### Notes", ""] + [f"- {n}" for n in notes]
    lines += [
        "",
        "### Worst-feature PSI by station",
        "",
        "| Station | Worst feature | PSI | Baked status |",
        "|---|---|---|---|",
    ]
    for site, worst, psi, status in sorted(drift_rows, key=lambda r: -r[2]):
        lines.append(f"| {site} | {worst} | {psi:.3f} | {status} |")
    lines += [
        "",
        "Thresholds: PSI > 0.25 = drift. This issue is opened/updated by "
        "`.github/workflows/monitor.yml`; see `MLOPS.md`.",
        "",
    ]
    text = "\n".join(lines)
    pathlib.Path(args.report).write_text(text, encoding="utf-8")
    print(text)
    print(f"monitor: {len(findings)} finding(s)")

    gh_out = os.environ.get("GITHUB_OUTPUT")
    if gh_out:
        with open(gh_out, "a", encoding="utf-8") as f:
            f.write(f"breach={'true' if findings else 'false'}\n")
            f.write(f"breach_count={len(findings)}\n")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (OSError, KeyError, ValueError) as e:
        print(f"::error::monitor operational failure: {e}")
        sys.exit(1)
