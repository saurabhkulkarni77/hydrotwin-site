#!/usr/bin/env python3
"""Generate the HydroTwin helper-bot site index (helper/ht-index.json).

The index is the helper bot's only source of location answers: every
station (from the chart3d sidecars, which carry the same station
metadata as the pages' own data payloads), every page, the panels on
each page type with the element the "show me" action highlights, and
how-to entries for the date field and the view switches. Nothing is
hand-typed per station: names, USGS ids, coordinates and drainage
areas come from chart3d/<site>.json at build time.

Run from the repo root: python3 build25/gen_helper_index.py
"""
import json
from pathlib import Path

CLASSIC_PANELS = [
    ("hts-sec-hydro", "Hydrograph", "The full flow record and the 90 day hydrograph for the selected date."),
    ("hts-sec-fc", "7-day forecast", "The 7 day forecast fan and interval band for the selected date and model."),
    ("hts-sec-models", "Model statistics", "Per model accuracy statistics for this station."),
    ("hts-sec-ablation", "Feature ablation", "How forecast error changes when input feature groups are removed."),
    ("hts-sec-weekly", "Weekly outlook", "The 12 week outlook of weekly mean flow."),
    ("hts-sec-monthly", "Monthly outlook", "The next 6 monthly mean flow outlook."),
    ("hts-sec-yearly", "Yearly outlook", "The next 12 monthly mean flow outlook."),
    ("hts-sec-drift", "Drift", "Model drift monitoring for this station."),
    ("hts-sec-3dchart", "3D forecast chart", "Interactive 3D chart of forecast issue date, gauge height and an environmental input."),
    ("hts-sec-corr", "Multi-factor correlation", "Correlation matrix between flow and weather, soil and snow factors."),
    ("hts-sec-featimp", "Features affecting discharge flow", "XGBoost feature importance: which inputs the flow model leans on most."),
    ("hts-sec-clusters", "Station clusters", "How this station clusters with the other HydroTwin stations."),
    ("hts-sec-charts3d", "Data charts in 3D", "The hydrograph and the feature importance chart rendered as interactive 3D charts."),
]

PANELS_3D = [
    ("dock", "Daily forecast", "The Flow and forecast card with the selected date, model and lead controls."),
    ("htwk-panel", "Weekly outlook", "The 12 week outlook of weekly mean flow."),
    ("htmo-panel", "Monthly outlook", "The next 6 monthly mean flow outlook."),
    ("htyr-panel", "Yearly outlook", "The next 12 monthly mean flow outlook."),
    ("ht-dacp-panel", "Confidence interval", "Forecast confidence intervals for this station."),
    ("ht-drift-panel", "Model drift", "Model drift monitoring for this station."),
    ("htfi-panel", "Features affecting flow", "XGBoost feature importance: which inputs the flow model leans on most."),
]


def main():
    root = Path(".")
    entries = []
    stations = []
    for sidecar in sorted((root / "chart3d").glob("*.json")):
        d = json.loads(sidecar.read_text(encoding="utf-8"))
        st = d["station"]
        site = st["stationId"].replace("USGS-", "")
        name = st["name"]
        stations.append({
            "site": site, "name": name,
            "lat": st["latitude"], "lon": st["longitude"],
            "drainage": st.get("drainage", ""),
        })
        river = name.split(" at ")[0] if " at " in name else name
        entries.append({
            "id": f"station-{site}-data",
            "kind": "station",
            "title": f"{name} (USGS {site}) — Data view",
            "text": (f"Statistics and Data view for {name}, USGS station {site} on the {river}. "
                     f"Drainage area {st.get('drainage', '')}. Panels: hydrograph, 7-day forecast, "
                     "model statistics, weekly, monthly and yearly outlooks, drift, correlations, "
                     "feature importance and 3D charts."),
            "keywords": [site, name.lower(), river.lower(), "data", "statistics", "hydrograph"],
            "url": f"stations/USGS-{site}.html",
            "target": "#hts-top",
        })
        entries.append({
            "id": f"station-{site}-3d",
            "kind": "station",
            "title": f"{name} (USGS {site}) — 3D view",
            "text": (f"Interactive 3D digital twin for {name}, USGS station {site} on the {river}: "
                     "terrain, river, buildings, the date field, Ground and Table views, and panels "
                     "for the daily forecast, outlooks, confidence interval, drift and feature importance."),
            "keywords": [site, name.lower(), river.lower(), "3d", "terrain", "river", "scene", "vr"],
            "url": f"stations/USGS-{site}-3d.html",
            "target": "#ht-date",
        })
        for pid, label, desc in CLASSIC_PANELS:
            entries.append({
                "id": f"panel-{site}-{pid}",
                "kind": "panel",
                "title": f"{label} — {name}",
                "text": f"{desc} Found on the Data view page for {name} (USGS {site}), in the panel named {label}.",
                "keywords": [site, name.lower(), label.lower()],
                "url": f"stations/USGS-{site}.html",
                "target": f"#{pid}",
                "button": label,
            })
        for pid, label, desc in PANELS_3D:
            entries.append({
                "id": f"panel3d-{site}-{pid}",
                "kind": "panel",
                "title": f"{label} — {name} (3D)",
                "text": f"{desc} Found on the 3D page for {name} (USGS {site}); open it from the PANELS bar at the bottom left.",
                "keywords": [site, name.lower(), label.lower(), "3d"],
                "url": f"stations/USGS-{site}-3d.html",
                "target": f"#{pid}",
                "button": label,
            })

    entries.extend([
        {
            "id": "home", "kind": "page",
            "title": "Home — USA map of all stations",
            "text": "The HydroTwin home page: a map of the USA with every station. Hover a pin for basin information, click a pin to open that station.",
            "keywords": ["home", "map", "usa", "stations", "pins", "start"],
            "url": "index.html", "target": "body",
        },
        {
            "id": "howto-date", "kind": "howto",
            "title": "How to change the date",
            "text": "Use the Date field at the top left of a station page. Pick any date from 2001-10-01 to 2026-09-30; the scene, hydrograph, forecasts and (on 3D pages) the rain or snow animation all follow the selected day.",
            "keywords": ["date", "change date", "pick a day", "calendar", "when"],
            "url": None, "target": "#ht-date",
        },
        {
            "id": "howto-views", "kind": "howto",
            "title": "How to switch between Data view, 3D view, Ground and Table",
            "text": "Each station has a Data view page (statistics) and a 3D page; the link at the top of each page switches between them. On the 3D page, the layer view button switches the scene between Ground (real terrain) and Table (tabletop model).",
            "keywords": ["switch", "view", "data view", "3d view", "ground", "table", "layer"],
            "url": None, "target": "#ht-date",
        },
        {
            "id": "howto-panels", "kind": "howto",
            "title": "How to open a panel",
            "text": "Panels load on click only. On a Data view page use the PANELS bar above the sections; on a 3D page use the PANELS bar at the bottom left. Click a panel name to open it, click again to close it.",
            "keywords": ["panel", "open panel", "panels bar", "button"],
            "url": None, "target": "#htlp-bar",
        },
        {
            "id": "howto-precip", "kind": "howto",
            "title": "Rain and snow animation",
            "text": "On a 3D station page, pick a date in the Date field: if that day had rain at the station, animated rain falls in the scene; if it had snow, animated snowfall; dry days show neither. The amount comes from the Open-Meteo archive for that day.",
            "keywords": ["rain", "snow", "precipitation", "weather", "animation"],
            "url": None, "target": "#ht-date",
        },
        {
            "id": "mlops", "kind": "page",
            "title": "MLOps status page",
            "text": "Model registry, retraining and monitoring status for the HydroTwin models.",
            "keywords": ["mlops", "models", "retraining", "registry", "monitoring", "status"],
            "url": "mlops.html", "target": "body",
        },
    ])

    out = {"v": "ht-helperbot v1", "stations": stations, "entries": entries}
    dest = root / "helper" / "ht-index.json"
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"helper/ht-index.json: {len(stations)} stations, {len(entries)} entries")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
