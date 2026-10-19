#!/usr/bin/env python3
"""Render mlops.html from the status snapshot (see gen_status.py).

The page is PRE-RENDERED at generation time: gen_status.py builds the
snapshot dict, writes it to mlops-status.json (the data source), and
renders this HTML from that same dict. No client-side fetch is needed
to display the data — an earlier fetch-based version could sit forever
on its "Loading status..." placeholder if anything in the async chain
failed, so the content is baked in and the only client script left is
a tiny staleness check (progressive enhancement; the page is complete
without it).
"""
import html as _html


def esc(s):
    return _html.escape(str(s if s is not None else ""), quote=True)


def fmt_t(iso):
    return iso.replace("T", " ").replace("Z", "") if iso else "—"


def pct(x):
    return f"{'+' if x >= 0 else ''}{x * 100:.1f}%"


def result_pill(w):
    latest = w.get("latest")
    if not latest:
        return '<span class="pill neut">no runs recorded</span>'
    c, s = latest.get("conclusion"), latest.get("status")
    if c == "success":
        return '<span class="pill ok">success</span>'
    if c == "failure":
        return '<span class="pill bad">failure</span>'
    if c in ("cancelled", "skipped"):
        return f'<span class="pill neut">{esc(c)}</span>'
    if c:
        return f'<span class="pill warn">{esc(c)}</span>'
    return f'<span class="pill warn">{esc(s or "running")}</span>'


def triggers_rows(triggers):
    out = []
    for t in triggers:
        base = t["workflow"].split("/")[-1]
        out.append(
            f'<tr><td><b>{esc(t["automation"])}</b></td>'
            f'<td>{esc(t["fires_when"])}</td>'
            f'<td>{esc(t["what_happens"])}</td>'
            f'<td><code>{esc(base)}</code></td></tr>')
    return "\n".join(out)


def registry_block(reg):
    summary = (
        f'Dataset window <b>{esc(reg["dataset_window"])}</b> · '
        f'train {esc(reg["train"])} · validation {esc(reg["validation"])}'
        f' · test {esc(reg["test"])} · daily champion '
        f'<b>{esc(reg["champions"]["daily"])}</b> · weekly champion '
        f'<b>{esc(reg["champions"]["weekly"])}</b>')
    rows = []
    for m in reg["models"]:
        stage = ('<span class="pill prod">production</span>'
                 if m["stage"] == "production"
                 else '<span class="pill cand">candidate</span>')
        if m["vs_baseline"] == "at baseline":
            vs = '<span class="pill ok">at baseline</span>'
        else:
            vs = (f'daily {pct(m["daily_delta_rel"])} · '
                  f'weekly {pct(m["weekly_delta_rel"])}')
        rows.append(
            f'<tr><td><b>{esc(m["name"])}</b></td>'
            f'<td>{esc(m["version"])}</td><td>{stage}</td>'
            f'<td class="num">{m["daily_rmse"]:.4f}</td>'
            f'<td class="num">{m["weekly_rmse"]:.4f}</td>'
            f'<td>{vs}</td></tr>')
    note = (
        f'Pooled log-flow RMSE, test era {esc(reg["test"])}. Baselines '
        f'frozen {esc(reg["baselines_frozen_at"])} in '
        f'models/baselines.json; the validation gate fails a models/** '
        f'PR when a production model regresses more than '
        f'{reg["gate"]["tolerance_rel"] * 100:g}% unless it carries '
        f'the {esc(reg["gate"]["override_label"])} label.')
    return summary, "\n".join(rows), note


def monitor_block(mo):
    stations = mo["stations"]
    worst = stations[0]
    feat_note = ""
    if mo.get("breach_feature"):
        label = next(s["worst_feature_label"] for s in stations
                     if s["breach"])
        feat_note = f" — every breach is on {esc(label)}"
    summary = (
        f'<b>{mo["breach_count"]} of {mo["stations_total"]} stations</b>'
        f' above the drift threshold (PSI &gt; {mo["psi_threshold"]})'
        f'{feat_note}. Worst: <b>{esc(worst["name"] or worst["site"])}'
        f'</b> (USGS {esc(worst["site"])}) at PSI '
        f'<b>{worst["psi"]:.3f}</b>.')
    rows = []
    for s in stations:
        if s["psi"] > mo["psi_threshold"]:
            pill = '<span class="pill bad">drift</span>'
        elif s["psi"] > 0.10:
            pill = '<span class="pill warn">watch</span>'
        else:
            pill = '<span class="pill ok">stable</span>'
        name = f' — {esc(s["name"])}' if s["name"] else ""
        rows.append(
            f'<tr><td><b>{esc(s["site"])}</b>{name}</td>'
            f'<td>{esc(s["worst_feature_label"])}</td>'
            f'<td class="num">{s["psi"]:.3f}</td><td>{pill}</td></tr>')
    f = mo["freshness"]
    current = (f'(matches the data axis end {esc(f["axis_end"])})'
               if f["drift_report_current"]
               else f'(data axis ends {esc(f["axis_end"])})')
    cov = mo["coverage"]
    cov_txt = (f'all sidecar families complete '
               f'({", ".join(cov["families"])})' if cov["ok"]
               else 'problems: ' + esc("; ".join(cov["problems"])))
    fresh = (
        f'Freshness: drift report current through '
        f'<b>{esc(f["drift_report_recent_end"])}</b> {current} · daily '
        f'DACP sidecars reach <b>{esc(f["dacp_latest"])}</b> '
        f'({f["dacp_lag_days"]} days before the axis end) · '
        f'Coverage: {cov_txt}')
    issue = mo.get("issue")
    if issue:
        issue_line = (
            f'Tracking issue: <a href="{esc(issue["url"])}">'
            f'#{issue["number"]} — {esc(issue["title"])}</a> '
            f'({esc(issue["state"])}, updated '
            f'{esc(fmt_t(issue["updated_at"]))} UTC). The monitor opens '
            f'or updates it automatically on any breach.')
    else:
        issue_line = ("No monitor tracking issue recorded in this "
                      "snapshot.")
    return summary, "\n".join(rows), fresh, issue_line


def pipeline_rows(workflows):
    out = []
    for w in workflows:
        latest = w.get("latest")
        if latest:
            title = esc(latest.get("title") or f'#{latest["run_id"]}')
            event = esc(latest.get("event"))
            when = esc(fmt_t(latest.get("updated_at")))
            link = (f'<a href="{esc(latest.get("url"))}">'
                    f'run #{latest["run_id"]}</a>')
        else:
            title = event = when = "—"
            link = ""
        out.append(
            f'<tr><td><b>{esc(w["name"])}</b></td><td>{title}</td>'
            f'<td>{result_pill(w)}</td><td>{event}</td><td>{when}</td>'
            f'<td>{link}</td></tr>')
    return "\n".join(out)


PAGE_HEAD = """<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>HydroTwin · MLOps Level 2 status</title>
<style>
html,body{margin:0;background:#0E1A24;font-family:Arial,sans-serif;color:#E6EDF5}
a{color:#8FC1F2}
header,main,footer{max-width:1060px;margin:0 auto;padding:0 16px}
header{padding-top:20px}
.back{font-size:13px;text-decoration:none}
h1{color:#fff;font-size:24px;margin:8px 0 4px}
h2{color:#8FC1F2;font-size:17px;margin:0 0 10px}
.sub{color:#BFD9F5;font-size:14px;line-height:1.5;margin:4px 0}
.muted{color:#9FB3C8;font-size:13px;line-height:1.5}
section{background:rgba(12,18,28,.9);border:1px solid rgba(143,193,242,.25);border-radius:10px;padding:16px 18px;margin:16px 0;overflow-x:auto}
table{width:100%;border-collapse:collapse;font-size:13.5px;line-height:1.45}
th{color:#9FB3C8;text-align:left;font-weight:600;padding:6px 8px;border-bottom:1px solid rgba(143,193,242,.35);white-space:nowrap}
td{padding:6px 8px;border-bottom:1px solid rgba(140,190,240,.15);vertical-align:top}
tr:last-child td{border-bottom:none}
.num{text-align:right;font-variant-numeric:tabular-nums;white-space:nowrap}
.pill{display:inline-block;padding:1px 9px;border-radius:9px;font-size:12px;font-weight:bold;white-space:nowrap}
.ok{background:#2e9e5b;color:#fff}
.warn{background:#d9930d;color:#14100a}
.bad{background:#d64545;color:#fff}
.prod{background:#2b7fd9;color:#fff}
.cand{background:#5b7186;color:#fff}
.neut{background:#3c4c5c;color:#E6EDF5}
.banner{border-radius:10px;padding:10px 14px;margin:12px 0;font-size:13.5px;line-height:1.45}
.banner.warnb{background:rgba(217,147,13,.18);border:1px solid #d9930d;color:#F5D9A0}
.kv{font-size:14px;line-height:1.6;margin:2px 0}
.kv b{color:#fff}
footer{padding-bottom:26px}
code{color:#BFD9F5;font-size:12.5px}
</style>
</head><body>
<header>
<a class="back" href="index.html">&larr; HydroTwin map</a>
<h1>MLOps &mdash; Level 2 pipeline status</h1>
<p class="sub">What this MLOps setup contains: CI tests for the pages, data and models on
every change; a model registry guarded by a validation gate; weekly drift monitoring;
validated retrain handoffs to the training repo; and versioned releases. This page shows
the current state of that system, pre-rendered from
<a href="mlops-status.json"><code>mlops-status.json</code></a> &mdash; see
<a href="https://github.com/saurabhkulkarni77/hydrotwin-site/blob/dev/MLOPS.md">MLOPS.md</a>
for the full design.</p>
<p class="muted" id="gen" data-generated-at="%%GENERATED_AT%%">Snapshot generated %%GENERATED_AT_FMT%% UTC &middot; source repo %%REPO%% &middot; data file mlops-status.json</p>
<div class="banner warnb" id="stale" hidden></div>
</header>
<main>
<section id="sec-triggers"><h2>Automation triggers</h2>
<table><thead><tr><th>Automation</th><th>Fires when</th><th>What happens</th><th>Workflow</th></tr></thead>
<tbody id="tb-triggers">
%%TRIGGERS%%
</tbody></table></section>

<section id="sec-registry"><h2>Model registry</h2>
<p class="kv" id="reg-summary">%%REG_SUMMARY%%</p>
<table><thead><tr><th>Model</th><th>Version</th><th>Stage</th><th class="num">Daily RMSE</th><th class="num">Weekly RMSE</th><th>vs baseline</th></tr></thead>
<tbody id="tb-registry">
%%REGISTRY%%
</tbody></table>
<p class="muted" id="reg-note">%%REG_NOTE%%</p></section>
"""


PAGE_TAIL = """
<section id="sec-monitor"><h2>Drift monitoring</h2>
<p class="kv" id="mon-summary">%%MON_SUMMARY%%</p>
<table><thead><tr><th>Station</th><th>Worst feature</th><th class="num">PSI</th><th>Status</th></tr></thead>
<tbody id="tb-monitor">
%%MONITOR%%
</tbody></table>
<p class="kv" id="mon-fresh" style="margin-top:10px">%%MON_FRESH%%</p>
<p class="kv" id="mon-issue">%%MON_ISSUE%%</p></section>

<section id="sec-pipeline"><h2>Pipeline status &mdash; latest workflow runs</h2>
<table><thead><tr><th>Workflow</th><th>Latest run</th><th>Result</th><th>Event</th><th>Finished (UTC)</th><th></th></tr></thead>
<tbody id="tb-pipeline">
%%PIPELINE%%
</tbody></table>
<p class="muted">Full history: <a href="https://github.com/saurabhkulkarni77/hydrotwin-site/actions">Actions tab</a> &middot;
<a href="https://github.com/saurabhkulkarni77/hydrotwin-site/releases">Releases</a></p></section>
</main>
<footer><p class="muted">Pre-rendered from <code>mlops-status.json</code> by
<code>monitor/gen_status.py</code>; the snapshot is regenerated and committed by the
status workflow after pipeline runs complete. If the snapshot is stale, the values
above are the last generated state &mdash; the repo&rsquo;s Actions tab is always
current.</p></footer>
<script>
(function(){var g=document.getElementById("gen");if(!g)return;
var t=Date.parse(g.getAttribute("data-generated-at"));if(!isFinite(t))return;
var age=(Date.now()-t)/864e5;
if(age>10){var s=document.getElementById("stale");if(s){s.hidden=false;
s.textContent="This snapshot is "+Math.floor(age)+" days old \\u2014 the refresh workflow may not have run recently; values below are the last generated state.";}}})();
</script>
</body></html>
"""


def render_html(status):
    reg = status["registry"]
    reg_summary, reg_rows, reg_note = registry_block(reg)
    mon = status["monitoring"]
    mon_summary, mon_rows, mon_fresh, mon_issue = monitor_block(mon)
    page = PAGE_HEAD + PAGE_TAIL
    page = page.replace("%%GENERATED_AT%%", esc(status["generated_at"]))
    page = page.replace("%%GENERATED_AT_FMT%%",
                        esc(fmt_t(status["generated_at"])))
    page = page.replace("%%REPO%%", esc(status["repo"]))
    page = page.replace("%%TRIGGERS%%", triggers_rows(status["triggers"]))
    page = page.replace("%%REG_SUMMARY%%", reg_summary)
    page = page.replace("%%REGISTRY%%", reg_rows)
    page = page.replace("%%REG_NOTE%%", esc(reg_note))
    page = page.replace("%%MON_SUMMARY%%", mon_summary)
    page = page.replace("%%MONITOR%%", mon_rows)
    page = page.replace("%%MON_FRESH%%", mon_fresh)
    page = page.replace("%%MON_ISSUE%%", mon_issue)
    page = page.replace("%%PIPELINE%%", pipeline_rows(status["workflows"]))
    return page
