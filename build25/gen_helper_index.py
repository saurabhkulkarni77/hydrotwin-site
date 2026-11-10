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


STATE_NAMES = {
    "NJ": "New Jersey", "MD": "Maryland", "FL": "Florida", "KY": "Kentucky",
    "MN": "Minnesota", "MT": "Montana", "MO": "Missouri", "LA": "Louisiana",
    "TX": "Texas", "NM": "New Mexico", "AZ": "Arizona", "CA": "California",
    "OR": "Oregon",
}
# State abbreviations that are also common English words ("or", "in",
# "la", "me") are deliberately NOT used as keywords: a question
# containing "or" would falsely boost that station. The full state
# name always works.
SAFE_ABBREVS = {"ca", "tx", "az", "mn", "ky", "mt", "mo", "nm", "fl", "nj", "md"}
# Extra truthful geographic aliases per station (city spellings and
# major nearby geography a visitor might actually type).
GEO_EXTRA = {
    "01646500": ["washington dc", "dc", "little falls"],
    "05331000": ["saint paul", "st paul", "twin cities"],
    "09380000": ["grand canyon", "lees ferry"],
    "11447650": ["sacramento", "freeport"],
    "14105700": ["the dalles"],
}


def geo_keywords(site, name):
    """State/city keywords for one station, parsed from its name.

    Station names look like "Sacramento River at Freeport, CA" (the
    Potomac adds "(near Washington DC)"). Returns the full state name,
    the city, a safe state abbreviation and any hand-listed aliases —
    so questions like "Where is the river in California?" retrieve the
    right station. Before this, the index carried only the two-letter
    abbreviation inside the name string, the word "california" matched
    nothing, and every station scored alike on the generic word
    "river", so state questions returned arbitrary stations.
    """
    import re
    kws = []
    m = re.search(r"\bat\s+(.+?),\s*([A-Z]{2})\b", name)
    if m:
        city, abbrev = m.group(1).strip().lower(), m.group(2)
        if city:
            kws.append(city)
        full = STATE_NAMES.get(abbrev)
        if full:
            kws.append(full.lower())
        if abbrev.lower() in SAFE_ABBREVS:
            kws.append(abbrev.lower())
    kws.extend(GEO_EXTRA.get(site, []))
    seen, out = set(), []
    for k in kws:
        if k and k not in seen:
            seen.add(k)
            out.append(k)
    return out


def state_full(name):
    import re
    m = re.search(r",\s*([A-Z]{2})\b", name)
    return STATE_NAMES.get(m.group(1)) if m else None


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
            "drainage": st.get("drainage") or "",
        })
        river = name.split(" at ")[0] if " at " in name else name
        drainage = st.get("drainage") or ""
        geo = geo_keywords(site, name)
        sfull = state_full(name)
        state_sent = f" It is the HydroTwin station in {sfull}." if sfull else ""
        if sfull:
            # Phrase keywords: state questions are phrased exactly
            # like this ("river in California", "station in Texas"),
            # and an exact phrase match (+9) is what lets the right
            # station beat the generic-word noise every other station
            # entry scores on words like "river" and "the".
            geo = geo + [f"river in {sfull.lower()}", f"station in {sfull.lower()}",
                         f"{sfull.lower()} river", f"{sfull.lower()} station"]
        entries.append({
            "id": f"station-{site}-data",
            "kind": "station",
            "title": f"{name} (USGS {site}) — Data view",
            "text": (f"Statistics and Data view for {name}, USGS station {site} on the {river}."
                     + state_sent
                     + (f" Drainage area {drainage}. " if drainage else "")
                     + "Panels: hydrograph, 7-day forecast, "
                     "model statistics, weekly, monthly and yearly outlooks, drift, correlations, "
                     "feature importance and 3D charts."),
            "keywords": [site, name.lower(), river.lower(), "data", "statistics", "hydrograph"] + geo,
            "url": f"stations/USGS-{site}.html",
            "target": "#hts-top",
        })
        entries.append({
            "id": f"station-{site}-3d",
            "kind": "station",
            "title": f"{name} (USGS {site}) — 3D view",
            "text": (f"Interactive 3D digital twin for {name}, USGS station {site} on the {river}: "
                     "terrain, river, buildings, the date field, Ground and Table views, and panels "
                     "for the daily forecast, outlooks, confidence interval, drift and feature importance."
                     + state_sent),
            "keywords": [site, name.lower(), river.lower(), "3d", "terrain", "river", "scene", "vr"] + geo,
            "url": f"stations/USGS-{site}-3d.html",
            "target": "#ht-date",
        })
        for pid, label, desc in CLASSIC_PANELS:
            entries.append({
                "id": f"panel-{site}-{pid}",
                "kind": "panel",
                "title": f"{label} — {name}",
                "text": f"{desc} Found on the Data view page for {name} (USGS {site}), in the panel named {label}.",
                "keywords": [site, name.lower(), label.lower()] + geo
                            + ([f"{label.lower()} in {sfull.lower()}"] if sfull else []),
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
                "keywords": [site, name.lower(), label.lower(), "3d"] + geo
                            + ([f"{label.lower()} in {sfull.lower()}"] if sfull else []),
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

    # ---------------------------------------------------------------
    # Explainer entries (added 2026-11-01). The index originally held
    # only station, panel and how-to entries, so "why" questions
    # about the 3D scene had nothing true to land on: "Why water is
    # overlapping buildings in this river" fell back to the station
    # page description (the words water/river/buildings overlap it),
    # and "where do the buildings come from" failed the relevance
    # gate entirely (no keyword anywhere contained "buildings").
    # Each explainer carries the concise, truthful answer as its
    # text (that text is what the visitor sees and what the model
    # rephrases) plus phrase-rich keywords, so a why-question's
    # exact phrasing scores the +9 phrase hits that station
    # descriptions cannot match. Keyword discipline from the
    # paraphrase battery: distinctive words first (overlapping,
    # buildings, footprints, bridges), and no bare generic keywords
    # ("station", "flow", "data") that would stack +3 partials on
    # unrelated questions and disturb the measured rankings. The
    # first battery run with fat keyword lists proved the point:
    # every extra keyword is +3 of ambient score on near any
    # question (partial matching fires on words like "the"/"in"),
    # and the explainer entries crowded correct station and panel
    # entries out of the keyword top 3 on four battery questions,
    # while two rewrote hybrid top 1s away from the how-to entries
    # whose topics they share. Lists and titles are therefore kept
    # lean, and the rain/date explainers are worded around the
    # recorded day (the why) while the how-to entries own the
    # how-to phrasing. Battery before/after is in status.md.
    # ---------------------------------------------------------------
    entries.extend([
        {
            "id": "explainer-water-buildings", "kind": "explainer",
            "title": "Why the water is overlapping buildings",
            "text": "On the 3D pages the water is a modeled surface laid over the real terrain at the level the selected date gives for that station, drawn across the channel and the low ground beside it. The buildings are real building footprints, and footprints that clearly sit in the channel are removed when the pages are built: 1,068 were dropped across the 14 stations and 18,203 were kept. Where the terrain data and a footprint disagree by a small amount, or a building stands right at the bank inside the edge of the modeled water, the water surface can clip through the bottom of the building and look as if it is overlapping it. It is a limit of the data resolution in the scene, not a flood forecast for that building.",
            "keywords": ["why water is overlapping buildings", "water is overlapping buildings",
                         "water overlapping buildings", "overlapping buildings",
                         "water over buildings", "water covering buildings",
                         "water through buildings", "buildings in water",
                         "flooded buildings", "overlapping"],
            "url": None, "target": "#htd-body",
        },
        {
            "id": "explainer-bridge-gaps", "kind": "explainer",
            "title": "Why the water passes under bridges",
            "text": "The water on the 3D pages is a ribbon drawn along the channel. At each bridge crossing a gap is cut into the ribbon, so the water passes under the deck instead of painting over the road. The crossings come from OpenStreetMap bridge data baked in when the pages are built, 141 across the 14 stations. Roads that run beside the channel rather than across it are not cut.",
            "keywords": ["why does water go under bridge", "water under the bridge",
                         "water under bridge", "bridge over river",
                         "bridge gap", "water flows under bridge",
                         "highway over river", "bridges"],
            "url": None, "target": "#htd-body",
        },
        {
            "id": "explainer-buildings-source", "kind": "explainer",
            "title": "Where the buildings come from",
            "text": "The buildings on the 3D pages come from Microsoft Building Footprints, a public data set of building outlines drawn from satellite imagery. Each station page keeps the footprints around the river and drops the ones that clearly sit in the water. A building can be missing when the data set holds no outline for it, when it went up after the imagery was taken, or when the water filter removed it because its outline touched the modeled channel.",
            "keywords": ["where do the buildings come from", "buildings come from",
                         "building data", "buildings source",
                         "missing building", "why is a building missing",
                         "building footprints", "microsoft building footprints"],
            "url": None, "target": "#htd-body",
        },
        {
            "id": "explainer-data-sources", "kind": "explainer",
            "title": "Where the water and terrain data comes from",
            "text": "The flow and water level numbers come from the USGS gauge at each station. The ground in the 3D view is built from USGS 3DEP elevation data, and SRTM terrain with Esri satellite imagery gives the wider scene its shape and surface. The forecast and outlook panels come from the HydroTwin models run for each basin.",
            "keywords": ["data source", "data sources", "where does the data come from",
                         "terrain data", "elevation data",
                         "satellite imagery source", "terrain source",
                         "usgs data"],
            "url": None, "target": "#htd-body",
        },
        {
            "id": "explainer-rain-snow", "kind": "explainer",
            "title": "Why no rain or snow falls on some days",
            "text": "The rain and snow on a 3D page replay the recorded weather of the date in the Date field, taken from the Open-Meteo archive for that station. If the archive recorded rain that day, rain falls; if it recorded snow, snow falls. When the record for the day is dry, the archive holds nothing to replay, so no rain and no snow appear. It is the weather of the selected day, not a live forecast.",
            "keywords": ["why is there no rain today", "no rain today", "why no rain",
                         "why is it not raining", "why no snow", "why is it not snowing",
                         "nothing falls", "dry day no rain"],
            "url": None, "target": "#ht-date",
        },
        {
            "id": "explainer-date-level", "kind": "explainer",
            "title": "Why the river runs high on some days and low on others",
            "text": "The river in the scene is drawn for the day in the Date field: the water level and flow are the values the gauge recorded that day, so a wet day in the record shows a higher river and a dry spell shows a lower one. The hydrograph and the outlooks are drawn for the same day, and the rain or snow animation follows it too.",
            "keywords": ["why does the river change when i change the date",
                         "why does the river change", "when i change the date",
                         "water level changes with date", "date drives the scene"],
            "url": None, "target": "#ht-date",
        },
    ])

    # ---------------------------------------------------------------
    # ACE playbook merge (build25/ace/playbook.json, added 2026-11-01).
    # The ACE loop (Agentic Context Engineering, arXiv:2510.04618)
    # evolves this versioned playbook from the bot's measured
    # retrieval failures: each "entry_keywords" bullet appends
    # curator-validated keywords to one entry. Titles and texts are
    # never touched, so the embedding asset (built from title+text)
    # is unaffected. The merge is fully described by the playbook
    # file; playbook_changelog.md records every promotion with its
    # measured eval delta. A missing playbook file is not an error
    # (the index then builds exactly as before ACE).
    # ---------------------------------------------------------------
    pb_path = root / "build25" / "ace" / "playbook.json"
    if pb_path.exists():
        pb = json.loads(pb_path.read_text(encoding="utf-8"))
        extra = {}
        for b in pb.get("bullets", []):
            if b.get("type") == "entry_keywords":
                extra.setdefault(b["entry"], []).extend(b.get("add_keywords", []))
        merged = 0
        for e in entries:
            have = {k.strip().lower() for k in e["keywords"]}
            for kw in extra.get(e["id"], []):
                if kw.strip() and kw.strip().lower() not in have:
                    e["keywords"].append(kw)
                    have.add(kw.strip().lower())
                    merged += 1
        print(f"ACE playbook v{pb.get('version')}: {merged} keywords merged "
              f"into {len(extra)} entries")

    out = {"v": "ht-helperbot v1", "stations": stations, "entries": entries}
    dest = root / "helper" / "ht-index.json"
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"helper/ht-index.json: {len(stations)} stations, {len(entries)} entries")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
