#!/usr/bin/env python3
"""Fetch USGS 3DHP waterbody polygons for all 14 stations (ht-waterbody3dhp v1).

Source (user-provided, 2026-11-10): USGS 3D Hydrography Program (3DHP)
ArcGIS REST, layer 60 of usgs_3dhp_all. Per station: envelope of
+-0.03 deg around the gauge coordinate (taken from the station page's
own metadata), where areasqkm > 1 AND featuretypelabel IN ('River','Lake').

Output: build25/waterbody3dhp_data.py with WATERBODY3DHP = {site: [poly]},
in the same baked format as polywater_data.py: a polygon is a list of
rings, a ring is a flat [lon, lat, lon, lat, ...] list, coords 6 dp,
Douglas-Peucker simplified at ~5 m. Esri rings are regrouped: a ring
contained in another becomes its hole; disjoint outers stay separate
polygons. Polygons are NOT clipped to the envelope (same as the OSM
polywater bake - the renderer drapes far vertices on terrain).
"""
import json
import math
import sys
import subprocess
import time
import urllib.parse
from pathlib import Path

SERVICE = ("https://3dhp.nationalmap.gov/arcgis/rest/services/"
           "usgs_3dhp_all/FeatureServer/60/query")

# gauge coordinates from each station page's own metadata (first lat/lon)
STATIONS = {
    "01463500": (40.22166667, -74.77805556),
    "01646500": (38.94977778, -77.12763889),
    "02320500": (29.955785, -82.9276278),
    "03294500": (38.28034736, -85.7991305),
    "05331000": (44.9444444, -93.0881111),
    "06214500": (45.800119, -108.468031),
    "06934500": (38.70980556, -91.4385),
    "07374000": (30.44566667, -91.1915556),
    "08057000": (32.7748517, -96.8219464),
    "08158000": (30.24613889, -97.6800556),
    "08313000": (35.8745, -106.1424444),
    "09380000": (36.86433333, -111.58787222),
    "11447650": (38.45566389, -121.5016167),
    "14105700": (45.60827778, -121.1899167),
}
HALF = 0.03  # envelope half-width in degrees, per the user's API pattern


def fetch(lat, lon):
    env = f"{lon-HALF},{lat-HALF},{lon+HALF},{lat+HALF}"
    feats, offset = [], 0
    while True:
        params = {
            "geometry": env, "geometryType": "esriGeometryEnvelope",
            "inSR": 4326, "spatialRel": "esriSpatialRelIntersects",
            "where": "areasqkm > 1 AND featuretypelabel IN ('River','Lake')",
            "outFields": "gnisidlabel,featuretypelabel,areasqkm,workunitid,featuredate",
            "returnGeometry": "true", "returnZ": "false", "outSR": 4326,
            "f": "json", "resultOffset": offset, "resultRecordCount": 200,
        }
        url = SERVICE + "?" + urllib.parse.urlencode(params)
        data = None
        for attempt in range(4):
            try:
                raw = subprocess.run(
                    ["curl", "-sS", "--fail", "--retry", "3", "--max-time", "180", url],
                    capture_output=True, check=True).stdout
                data = json.loads(raw)
                break
            except Exception as e:
                if attempt == 3:
                    raise
                print(f"  retry after fetch error: {e}", file=sys.stderr)
                time.sleep(3)
        if "error" in data:
            raise RuntimeError(str(data["error"]))
        feats.extend(data.get("features", []))
        if not data.get("exceededTransferLimit"):
            return feats
        offset += len(data.get("features", []))


def dp(pts, tol):
    """Douglas-Peucker on (lon, lat) points, tol in degrees."""
    if len(pts) < 3:
        return pts
    keep = [False] * len(pts)
    keep[0] = keep[-1] = True
    stack = [(0, len(pts) - 1)]
    while stack:
        a, b = stack.pop()
        if b <= a + 1:
            continue
        ax, ay = pts[a]
        bx, by = pts[b]
        dx, dy = bx - ax, by - ay
        norm = math.hypot(dx, dy) or 1e-12
        worst, wi = -1.0, -1
        for i in range(a + 1, b):
            px, py = pts[i]
            d = abs(dy * px - dx * py + bx * ay - by * ax) / norm
            if d > worst:
                worst, wi = d, i
        if worst > tol:
            keep[wi] = True
            stack.append((a, wi))
            stack.append((wi, b))
    return [p for p, k in zip(pts, keep) if k]


def signed_area(ring):
    a = 0.0
    for i in range(len(ring) - 1):
        x1, y1 = ring[i]
        x2, y2 = ring[i + 1]
        a += x1 * y2 - x2 * y1
    return a / 2.0


def point_in_ring(pt, ring):
    x, y = pt
    inside = False
    for i in range(len(ring) - 1):
        x1, y1 = ring[i]
        x2, y2 = ring[i + 1]
        if (y1 > y) != (y2 > y):
            xin = x1 + (y - y1) * (x2 - x1) / (y2 - y1)
            if xin > x:
                inside = not inside
    return inside


def clip_rect(pts, xmin, ymin, xmax, ymax):
    """Sutherland-Hodgman clip of a closed ring (pts without dup end)."""
    def clip(poly, inside, intersect):
        if not poly:
            return poly
        out = []
        prev = poly[-1]
        pin = inside(prev)
        for cur in poly:
            cin = inside(cur)
            if cin:
                if not pin:
                    out.append(intersect(prev, cur))
                out.append(cur)
            elif pin:
                out.append(intersect(prev, cur))
            prev, pin = cur, cin
        return out
    def ix_x(xedge):
        return lambda a, b: (xedge, a[1] + (b[1] - a[1]) * (xedge - a[0]) / (b[0] - a[0] or 1e-12))
    def ix_y(yedge):
        return lambda a, b: (a[0] + (b[0] - a[0]) * (yedge - a[1]) / (b[1] - a[1] or 1e-12), yedge)
    pts = clip(pts, lambda p: p[0] >= xmin, ix_x(xmin))
    pts = clip(pts, lambda p: p[0] <= xmax, ix_x(xmax))
    pts = clip(pts, lambda p: p[1] >= ymin, ix_y(ymin))
    pts = clip(pts, lambda p: p[1] <= ymax, ix_y(ymax))
    return pts


def regroup(rings):
    """rings: list of point lists. Returns polygons [[outer, hole...], ...]."""
    rings = [r for r in rings if len(r) >= 4]
    rings.sort(key=lambda r: -abs(signed_area(r)))
    outers, holes = [], []
    for r in rings:
        container = None
        for o in outers:
            if point_in_ring(r[0], o[0]):
                container = o
                break
        if container is None:
            outers.append([r])
        else:
            container.append(r)
    return outers


def main():
    result, counts = {}, {}
    for site, (lat, lon) in STATIONS.items():
        feats = fetch(lat, lon)
        counts[site] = len(feats)
        polys = []
        for f in feats:
            geom = f.get("geometry") or {}
            rings = []
            for ring in geom.get("rings", []):
                pts = [(round(x, 6), round(y, 6)) for x, y in ring]
                if len(pts) >= 2 and pts[0] == pts[-1]:
                    pts = pts[:-1]  # open the ring; DP needs distinct ends
                if len(pts) < 3:
                    continue
                clipped = clip_rect(pts, lon - 0.045, lat - 0.045,
                                    lon + 0.045, lat + 0.045)
                if len(clipped) < 3:
                    continue
                simp = dp(clipped, 5e-5)  # ~5 m
                if len(simp) >= 3:
                    simp.append(simp[0])  # re-close
                    rings.append(simp)
            for poly in regroup(rings):
                flat = []
                for ring in poly:
                    fr = []
                    for x, y in ring:
                        fr += [x, y]
                    flat.append(fr)
                polys.append(flat)
        result[site] = polys
        print(f"{site}: {len(feats)} features, {len(polys)} polygons")
    out = Path(__file__).parent / "waterbody3dhp_data.py"
    with out.open("w", encoding="utf-8") as fh:
        fh.write('"""Baked USGS 3DHP waterbody polygons (ht-waterbody3dhp v1).\n'
                 'Generated by build25/gen_waterbody3dhp_data.py from the USGS\n'
                 '3DHP ArcGIS REST service (layer 60), +-0.03 deg envelope per\n'
                 'station, areasqkm > 1, River/Lake only. Format matches\n'
                 'polywater_data.py: {site: [polygon[ring[flat lon,lat,...]]]}.\n"""\n')
        fh.write("WATERBODY3DHP = ")
        json.dump(result, fh, separators=(",", ":"))
        fh.write("\n")
    print("counts:", json.dumps(counts))
    print("wrote", out, out.stat().st_size, "bytes")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
