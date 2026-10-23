#!/usr/bin/env python3
"""Pull the fresh data series for all HydroTwin stations and stage
per-station snapshot JSONs + a manifest for upload to the DEV S3 bucket
(data/pulls/<station>/<pull-date>.json, data/pulls/manifest.json).

This mirrors, feed for feed, what the station pages' LIVE pull
(htGapAssemble in build25/patch_liveall.py) fetches in the browser:

  * USGS NWIS daily values (waterservices.usgs.gov/nwis/dv),
    parameterCd 00060 — except Sacramento 11447650, which uses 72137
    (tidally filtered), exactly like the pages;
  * Open-Meteo daily weather (tmax/tmin/precip): the forecast API
    (past_days) merged with the archive API, archive values winning on
    overlap — the pages' putWx order.

Window: baked-end - 50 days -> today (UTC). The overlap with the baked
range lets the pages refresh revised USGS values with the same
fresh-wins rule the live assembly uses; the tail past the baked end is
the new data the calendar forwards to.

Stdlib only. Output (under --out, default ./pull_out):
  stations/<site>.json  one snapshot per station
  manifest.json         {generated_at, stations: {<site>: {latest_date,
                        latest_aligned, pulled_at, snapshot_key}}}
The snapshot_key is filled in by the workflow (it owns the dated S3
key); this script writes it with the same dated name when --s3-prefix
is given (used by the workflow: data/pulls).
"""
import argparse
import json
import re
import sys
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
STATIONS_DIR = ROOT / "stations"
DAY = timedelta(days=1)


def iso(dt):
    return dt.strftime("%Y-%m-%d")


def fetch_json(url, timeout=60):
    req = urllib.request.Request(url, headers={"User-Agent": "HydroTwin-PullSnapshots/1.0"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode())


def extract_ht3d(html):
    """window.HT3D is a strict-JSON object literal; extract and parse."""
    i = html.find("window.HT3D = ")
    assert i >= 0, "window.HT3D assignment not found"
    j = html.find("{", i)
    depth, in_str, esc = 0, False, False
    for k in range(j, len(html)):
        c = html[k]
        if in_str:
            if esc:
                esc = False
            elif c == "\\":
                esc = True
            elif c == '"':
                in_str = False
        else:
            if c == '"':
                in_str = True
            elif c == "{":
                depth += 1
            elif c == "}":
                depth -= 1
                if depth == 0:
                    return json.loads(html[j:k + 1])
    raise AssertionError("HT3D object is unbalanced")


def pull_station(site, lat, lon, w_start, today):
    """Return (days, latest_date, latest_aligned) for one station.
    days: {date: {"q": cfs, "tx": tmax, "tn": tmin, "pr": precip}} with
    only the fields that exist for that date."""
    pcd = "72137" if site == "11447650" else "00060"
    flows = {}
    url = ("https://waterservices.usgs.gov/nwis/dv/?format=json&sites="
           + site + "&parameterCd=" + pcd
           + "&startDT=" + w_start + "&endDT=" + today)
    try:
        ru = fetch_json(url, 45)
    except Exception as e:
        print(f"  !! {site}: USGS dv fetch failed: {e}")
        ru = None
    if ru and ru.get("value"):
        for ts in ru["value"].get("timeSeries", []):
            for v in ts["values"][0]["value"]:
                try:
                    q = float(v["value"])
                except (TypeError, ValueError):
                    continue
                if q > 0:
                    flows[v["dateTime"][:10]] = q
    wx = {}

    def put_wx(w):
        d = (w or {}).get("daily") or {}
        times = d.get("time") or []
        for i2, dt in enumerate(times):
            mx = d["temperature_2m_max"][i2]
            mn = d["temperature_2m_min"][i2]
            if mx is None or mn is None:
                continue
            wx[dt] = [mx, mn, d["precipitation_sum"][i2] or 0]

    try:
        wf = fetch_json(
            "https://api.open-meteo.com/v1/forecast?latitude=" + str(lat)
            + "&longitude=" + str(lon)
            + "&daily=temperature_2m_max,temperature_2m_min,precipitation_sum"
            + "&temperature_unit=celsius&precipitation_unit=mm&timezone=auto"
            + "&past_days=92&forecast_days=1", 45)
    except Exception as e:
        print(f"  !! {site}: Open-Meteo forecast fetch failed: {e}")
        wf = None
    try:
        wa = fetch_json(
            "https://archive-api.open-meteo.com/v1/archive?latitude=" + str(lat)
            + "&longitude=" + str(lon)
            + "&start_date=" + w_start + "&end_date=" + today
            + "&daily=temperature_2m_max,temperature_2m_min,precipitation_sum"
            + "&temperature_unit=celsius&precipitation_unit=mm&timezone=auto", 60)
    except Exception as e:
        print(f"  !! {site}: Open-Meteo archive fetch failed: {e}")
        wa = None
    put_wx(wf)
    put_wx(wa)  # archive (observed) wins on overlap, as on the pages

    days = {}
    for dt in sorted(set(flows) | set(wx)):
        rec = {}
        if dt in flows:
            rec["q"] = flows[dt]
        if dt in wx:
            rec["tx"], rec["tn"], rec["pr"] = wx[dt]
        days[dt] = rec
    flow_dates = sorted(flows)
    latest = flow_dates[-1] if flow_dates else None
    aligned = [dt for dt in flow_dates if dt in wx]
    latest_aligned = aligned[-1] if aligned else None
    return days, latest, latest_aligned


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="pull_out")
    ap.add_argument("--s3-prefix", default="data/pulls",
                    help="prefix used to compose manifest snapshot_key values")
    args = ap.parse_args()
    out = Path(args.out)
    (out / "stations").mkdir(parents=True, exist_ok=True)

    now = datetime.now(timezone.utc)
    today = iso(now)
    pulled_at = now.strftime("%Y-%m-%dT%H:%M:%SZ")

    pages = sorted(STATIONS_DIR.glob("USGS-*-3d.html"))
    assert len(pages) == 14, f"expected 14 3D station pages, found {len(pages)}"
    manifest = {"generated_at": pulled_at, "stations": {}}
    failures = 0
    for page in pages:
        d = extract_ht3d(page.read_text(encoding="utf-8"))
        site = d["site"]
        start = datetime.strptime(d["start"], "%Y-%m-%d")
        baked_end = start + (d["n"] - 1) * DAY
        w_start = iso(baked_end - 50 * DAY)
        print(f"{site}: window {w_start} -> {today} (baked end {iso(baked_end)})")
        days, latest, latest_aligned = pull_station(
            site, d["lat"], d["lon"], w_start, today)
        if latest is None:
            print(f"  !! {site}: no flow data in window; station skipped")
            failures += 1
            continue
        snap = {
            "station": site,
            "name": d.get("name", ""),
            "pulled_at": pulled_at,
            "window": {"start": w_start, "end": today},
            "baked_end": iso(baked_end),
            "latest_date": latest,
            "latest_aligned": latest_aligned,
            "days": days,
        }
        (out / "stations" / f"{site}.json").write_text(
            json.dumps(snap, separators=(",", ":")), encoding="utf-8")
        manifest["stations"][site] = {
            "latest_date": latest,
            "latest_aligned": latest_aligned,
            "pulled_at": pulled_at,
            "snapshot_key": f"{args.s3_prefix}/{site}/{today}.json",
        }
        print(f"  {site}: {len(days)} days, latest flow {latest}, "
              f"latest aligned {latest_aligned}")
    (out / "manifest.json").write_text(
        json.dumps(manifest, indent=1), encoding="utf-8")
    print(f"manifest: {len(manifest['stations'])} stations, {failures} failures")
    # A run that produced nothing usable must fail loudly (no empty manifest
    # overwriting a good one on the bucket).
    if len(manifest["stations"]) < 10:
        print("ABORT: too few stations pulled; refusing to publish")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
