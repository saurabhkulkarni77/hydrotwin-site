#!/usr/bin/env python3
"""Inject the HydroTwin drift panel into every station page (idempotent).

Reads drift/drift_bake.json (repo-relative), renders a static per-station
panel, and inserts it before </body> in stations/USGS-*.html.
Pages already containing the panel div are skipped. (The check must be
the div markup itself: the bare "ht-drift-panel" string also occurs in
the stats-view CSS overrides and moveEl call on classic pages, which
false-positived the old `MARKER in html` check after apply25 stripped
the panel block — the panel was then never re-added. Fixed 2026-10-15.)

Display update 2026-10-22: the Data drift section now shows the PSI
drift cutoff explicitly — a count of features above the 0.25 cutoff at
the top of the section, a per-feature status pill (drifting / moderate /
stable against the standard PSI bands), and a legend line under the
table. Display only: PSI values still come from drift_bake.json and no
computation changes.
"""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BAKE = ROOT / "drift" / "drift_bake.json"
MARKER = "ht-drift-panel"
PANEL_DIV = '<div id="ht-drift-panel">'  # injected markup; the only safe skip check

FEAT_NAMES = {"tmax_c": "Tmax", "tmin_c": "Tmin", "tmean_c": "Tmean",
              "precip_mm": "Precip", "log10_flow": "Flow (log)"}
PILL = {"stable": "#2e9e5b", "watch": "#d9930d", "drift": "#d64545",
        "improving": "#f5c518", "no data": "#777",
        "drifting": "#d64545", "moderate": "#d9930d"}
# Standard PSI interpretation bands: above PSI_CUT a feature counts as
# drifting; at/above PSI_MOD (up to the cutoff) it is a moderate shift;
# below PSI_MOD it is stable.
PSI_CUT = 0.25
PSI_MOD = 0.10


def psi_status(v):
    if v is None:
        return "no data"
    if v > PSI_CUT:
        return "drifting"
    if v >= PSI_MOD:
        return "moderate"
    return "stable"
# Dark text on light pill backgrounds (yellow "improving": the .pill class
# default #fff text is unreadable on #f5c518; same pairing as .htd-dev).
PILL_FG = {"improving": "#111"}

CSS = """
#ht-drift-panel{position:fixed;right:18px;bottom:18px;width:308px;z-index:9999;
 background:rgba(12,18,28,.92);color:#e8eef5;border:1px solid rgba(255,255,255,.16);
 border-radius:12px;font:12px/1.45 system-ui,-apple-system,Segoe UI,Roboto,sans-serif;
 box-shadow:0 8px 30px rgba(0,0,0,.45);backdrop-filter:blur(6px)}
#ht-drift-panel .htd-head{display:flex;justify-content:space-between;align-items:center;
 padding:8px 12px;font-weight:700;font-size:12.5px;letter-spacing:.02em}
#ht-drift-panel .htd-dev{background:#d9930d;color:#111;border-radius:4px;
 padding:0 5px;margin-left:6px;font-size:10px;vertical-align:1px}
#ht-drift-panel button{background:none;border:1px solid rgba(255,255,255,.25);
 color:#e8eef5;border-radius:6px;width:22px;height:22px;cursor:pointer;font-size:14px;line-height:1}
#ht-drift-panel .htd-body{padding:0 12px 10px;max-height:46vh;overflow:auto}
#ht-drift-panel table{width:100%;border-collapse:collapse;margin:4px 0 8px}
#ht-drift-panel td,#ht-drift-panel th{padding:2px 4px;text-align:right;font-weight:400}
#ht-drift-panel td:first-child,#ht-drift-panel th:first-child{text-align:left}
#ht-drift-panel .htd-sec{font-weight:700;margin-top:6px}
#ht-drift-panel .htd-line{opacity:.85}
#ht-drift-panel .htd-foot{opacity:.6;font-size:10.5px;margin-top:2px}
#ht-drift-panel .pill{color:#fff;border-radius:8px;padding:0 7px;font-size:10.5px;
 display:inline-block;min-width:52px;text-align:center}
"""


def pill(status):
    style = f"background:{PILL.get(status, '#777')}"
    if status in PILL_FG:
        style += f";color:{PILL_FG[status]}"
    return f'<span class="pill" style="{style}">{status}</span>'


def render(station, d):
    data = d["data"]
    frows = ""
    for f, name in FEAT_NAMES.items():
        v = data["features"].get(f)
        frows += (f"<tr><td>{name}</td>"
                  f"<td>{'—' if v is None else f'{v:.3f}'}</td>"
                  f"<td>{pill(psi_status(v))}</td></tr>")
    vals = [v for v in data["features"].values() if v is not None]
    n_drift = sum(1 for v in vals if v > PSI_CUT)
    mrows = ""
    for m, mv in d["models"].items():
        e = "—" if mv["e"] is None else f"{mv['e']:.3f}"
        l = "—" if mv["l"] is None else f"{mv['l']:.3f}"
        p = "—" if mv["pct"] is None else f"{mv['pct']:+.1f}%"
        mrows += (f"<tr><td>{m}</td><td>{e}</td><td>{l}</td><td>{p}</td>"
                  f"<td>{pill(mv['s'])}</td></tr>")
    worst = FEAT_NAMES.get(data["worst"], data["worst"] or "—")
    psi_txt = "—" if data["psi"] is None else f"{data['psi']:.2f}"
    return f"""<style>{CSS}</style>
<div id="ht-drift-panel">
  <div class="htd-head"><span>Model drift<span class="htd-dev">DEV</span></span>
  <button id="htd-toggle" aria-label="collapse">–</button></div>
  <div class="htd-body" id="htd-body">
    <div class="htd-sec">Data drift {pill(data['status'])}</div>
    <div class="htd-line"><b>{n_drift} of {len(vals)}</b> features above the 0.25 drift cutoff.</div>
    <div class="htd-line">Inputs, most recent 12 months (Oct 2025–Sep 2026) vs full training record (2001–26). Worst: {worst}, PSI {psi_txt}.</div>
    <table><tr><th>Feature</th><th>PSI</th><th></th></tr>{frows}</table>
    <div class="htd-line">Drift cutoff: PSI &gt; 0.25 = drifting · 0.10–0.25 = moderate shift · &lt; 0.10 = stable.</div>
    <div class="htd-sec">Concept drift</div>
    <div class="htd-line">Forecast RMSE (log flow) on WY2026 — backtest A (trained through 2023) vs B (trained through 2024):</div>
    <table><tr><th>Model</th><th>A</th><th>B</th><th>Δ</th><th></th></tr>{mrows}</table>
    <div class="htd-foot">PSI &gt; 0.25 = significant input shift · Δ &gt; +15% = model degrading.
    Served models retrained on the full record through Sep 2026 (drift fix, Oct 2026); concept drift = untouched-WY2026 backtest.</div>
  </div>
</div>
<script>document.getElementById('htd-toggle').addEventListener('click',function(){{var b=document.getElementById('htd-body');var h=b.style.display==='none';b.style.display=h?'':'none';this.textContent=h?'–':'+';}});</script>
"""


def main():
    bake = json.loads(BAKE.read_text())
    changed = 0
    for page in sorted((ROOT / "stations").glob("USGS-*.html")):
        stem = page.stem.replace("-3d", "")
        station = stem.replace("USGS-", "")
        if station not in bake:
            print("skip (no drift data):", page.name)
            continue
        html = page.read_text(errors="ignore")
        if PANEL_DIV in html:
            print("already patched:", page.name)
            continue
        block = render(station, bake[station])
        idx = html.rfind("</body>")
        if idx == -1:
            print("no </body>:", page.name)
            continue
        page.write_text(html[:idx] + block + html[idx:])
        changed += 1
        print("patched:", page.name)
    print(f"done, {changed} page(s) patched")


if __name__ == "__main__":
    main()
