#!/usr/bin/env python3
"""Bake levee centrelines for the 3D station pages.

Source: USACE National Levee Database, public FeatureServer
(NLD2_PUBLIC_v1, layer 10 "Embankments" - the physical levee
embankment lines; layer 6 "Alignment_Lines" as fallback), queried
per station over the page's inner ground block plus a margin.

Why the NLD rather than OpenStreetMap levee tags: the NLD is the
authoritative federal inventory (the Dallas Trinity system included)
and its REST endpoint is reliable from the build environment, while
Overpass levee coverage is patchy.

Lines are converted into the page's own ground coordinates (metres
east/south of the gauge, the same mx/mz frame the scene uses),
simplified to >= 10 m vertex spacing, clipped to the inner block
plus 250 m, and split wherever a gap longer than 150 m appears.
Output: build25/levees_data.py -> HT_LEVEES = {site: [[[x, z], ...]]}
Consumed by build25/patch_realism_context.py, which drapes each
line on the terrain as a low trapezoidal embankment.

Run from the repo root:  python3 build25/gen_levees_data.py
A station whose query fails or has no NLD embankments is baked as
an empty list (with a warning) rather than failing the bake.
"""
import json
import math
import re
import sys
import urllib.parse
import urllib.request
from pathlib import Path

NLD = "https://services2.arcgis.com/FiaPA4ga0iQKduv3/arcgis/rest/services/NLD2_PUBLIC_v1/FeatureServer"
LAYERS = [10, 6]          # Embankments, then Alignment_Lines
TS = 256
ZI = 15


def lon2px(lon, z):
    return (lon + 180) / 360 * TS * 2 ** z


def lat2px(lat, z):
    s = math.sin(math.radians(lat))
    return (0.5 - math.log((1 + s) / (1 - s)) / (4 * math.pi)) * TS * 2 ** z


def px2lon(px, z):
    return px / (TS * 2 ** z) * 360 - 180


def px2lat(py, z):
    return math.degrees(math.atan(math.sinh(math.pi * (1 - 2 * py / (TS * 2 ** z)))))


def frame(lat, lon):
    """Page-exact ground frame: mx/mz converters + inner block extent."""
    m0 = 156543.03392 * math.cos(math.radians(lat))
    gx0, gy0 = lon2px(lon, 0), lat2px(lat, 0)
    mx = lambda lo: (lon2px(lo, 0) - gx0) * m0
    mz = lambda la: (lat2px(la, 0) - gy0) * m0
    gxi, gyi = lon2px(lon, ZI), lat2px(lat, ZI)
    ipx0 = (round(gxi / TS) - 2) * TS
    ipy0 = (round(gyi / TS) - 2) * TS
    mpi = m0 / 2 ** ZI
    ix0, iz0, iwm = (ipx0 - gxi) * mpi, (ipy0 - gyi) * mpi, (4 * TS) * mpi
    lon_w, lon_e = px2lon(ipx0, ZI), px2lon(ipx0 + 4 * TS, ZI)
    lat_n, lat_s = px2lat(ipy0, ZI), px2lat(ipy0 + 4 * TS, ZI)
    return mx, mz, ix0, iz0, iwm, (lon_w, lat_s, lon_e, lat_n)


def query_layer(layer, bbox):
    params = {
        "where": "1=1",
        "geometry": ",".join(str(v) for v in bbox),
        "geometryType": "esriGeometryEnvelope",
        "inSR": "4326", "outSR": "4326",
        "spatialRel": "esriSpatialRelIntersects",
        "outFields": "",
        "returnGeometry": "true",
        "f": "geojson",
    }
    url = f"{NLD}/{layer}/query?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={"User-Agent": "hydrotwin-build/1.0"})
    with urllib.request.urlopen(req, timeout=120) as r:
        j = json.load(r)
    lines = []
    for feat in j.get("features", []):
        geom = (feat or {}).get("geometry") or {}
        if geom.get("type") == "LineString":
            lines.append(geom["coordinates"])
        elif geom.get("type") == "MultiLineString":
            lines.extend(geom["coordinates"])
    return lines


def convert(lines, mx, mz, ix0, iz0, iwm, margin=250.0, min_step=10.0, gap=150.0):
    out = []
    lo_x, hi_x = ix0 - margin, ix0 + iwm + margin
    lo_z, hi_z = iz0 - margin, iz0 + iwm + margin
    for line in lines:
        cur = []
        for lo, la in line:
            x, z = mx(lo), mz(la)
            if not (lo_x <= x <= hi_x and lo_z <= z <= hi_z):
                if cur and len(cur) >= 2:
                    out.append(cur)
                cur = []
                continue
            if cur:
                lx, lz = cur[-1]
                d = math.hypot(x - lx, z - lz)
                if d > gap:
                    if len(cur) >= 2:
                        out.append(cur)
                    cur = []
                elif d < min_step:
                    continue
            cur.append([round(x, 1), round(z, 1)])
        if len(cur) >= 2:
            out.append(cur)
    # keep only lines with real length inside the block
    kept = []
    for line in out:
        length = sum(math.hypot(line[i + 1][0] - line[i][0], line[i + 1][1] - line[i][1]) for i in range(len(line) - 1))
        if length >= 60:
            kept.append(line)
    return kept


def station_latlon():
    root = Path("stations")
    out = {}
    for p in sorted(root.glob("USGS-*-3d.html")):
        s = p.read_text(encoding="utf-8")
        m = re.search(r'"site":\s*"(\d+)"', s)
        la = re.search(r'"lat":\s*(-?[\d.]+)', s)
        lo = re.search(r'"lon":\s*(-?[\d.]+)', s)
        if m and la and lo:
            out[m.group(1)] = (float(la.group(1)), float(lo.group(1)))
    return out


def main():
    stations = station_latlon()
    if not stations:
        print("no station pages found under stations/", file=sys.stderr)
        return 1
    data = {}
    for site, (lat, lon) in sorted(stations.items()):
        mx, mz, ix0, iz0, iwm, bbox = frame(lat, lon)
        # widen the query bbox a touch so lines are not cut at the frame edge
        pad = 0.01
        bbox = (bbox[0] - pad, bbox[1] - pad, bbox[2] + pad, bbox[3] + pad)
        lines = []
        used = None
        for layer in LAYERS:
            try:
                lines = query_layer(layer, bbox)
            except Exception as e:
                print(f"{site}: WARNING NLD layer {layer} query failed ({e})", file=sys.stderr)
                lines = []
            if lines:
                used = layer
                break
        conv = convert(lines, mx, mz, ix0, iz0, iwm) if lines else []
        total = sum(len(l) for l in conv)
        print(f"{site}: NLD layer {used}: {len(lines)} raw lines -> {len(conv)} lines, {total} pts")
        data[site] = conv
    out = Path(__file__).parent / "levees_data.py"
    body = (
        "# ht-levees v1 baked data: levee centrelines per station as\n"
        "# [x, z] polylines in page ground coordinates (metres from the\n"
        "# gauge), from the USACE National Levee Database (NLD2_PUBLIC_v1,\n"
        "# Embankments layer; Alignment_Lines fallback). Generated by\n"
        "# build25/gen_levees_data.py.\n"
        "HT_LEVEES = " + json.dumps(data, separators=(",", ":")) + "\n"
    )
    out.write_text(body, encoding="utf-8")
    print(f"wrote {out} ({len(body)} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
