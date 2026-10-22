#!/usr/bin/env python3
"""Bake the basin sidecar for the homepage map-pin hover card (ht-mapbasin v1).

For every HydroTwin station, pull the same USGS NLDI data the 3D
station pages use live (basin polygon, upstream/downstream NHDPlus V2
flowlines, downstream NWIS gauges) and reduce it to a small JSON the
homepage can fetch once:

  basins/basins.json -> { "<site>": {
      "area_km2": <watershed area, same spherical method as the 3D page>,
      "rings":    simplified basin boundary rings [[lon, lat], ...],
      "dm_km":    downstream mainstem path length shown (km, <= 400),
      "um_km":    upstream mainstem path length shown (km, <= 150),
      "dm":       simplified downstream path [[lon, lat], ...],
      "um":       simplified upstream path [[lon, lat], ...],
      "down":     [{"site","name","km"}] next gauges downstream (max 4)
  }, ... }

The downstream-gauge distances replicate the 3D page's method:
build the downstream river path from the NLDI flowlines (ordered /
chain join), then place each downstream NWIS site at the cumulative
distance of its nearest path point when within 5 km.

Run offline at bake time; the site itself only reads the sidecar.
"""
import json
import math
import re
import sys
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

HERE = Path(__file__).parent
ROOT = HERE.parent
NLDI = "https://api.water.usgs.gov/nldi/linked-data/nwissite/USGS-{site}/"
UA = {"User-Agent": "HydroTwin basin hover bake/1.0"}
R_M = 6371000.0


def fetch(url, tries=3):
    last = None
    for k in range(tries):
        try:
            req = urllib.request.Request(url, headers=UA)
            with urllib.request.urlopen(req, timeout=120) as r:
                return json.loads(r.read().decode("utf-8"))
        except Exception as e:  # noqa: BLE001 - report after retries
            last = e
            time.sleep(2 * (k + 1))
    raise RuntimeError(f"fetch failed {url}: {last}")


def lines(fc):
    out = []
    for f in (fc or {}).get("features") or []:
        g = f.get("geometry")
        if not g:
            continue
        t, c = g.get("type"), g.get("coordinates")
        if t == "LineString":
            out.append(c)
        elif t == "MultiLineString":
            out.extend(c)
        elif t == "Polygon":
            out.extend(c)
        elif t == "MultiPolygon":
            for p in c:
                out.extend(p)
    return out


def hav(a, b):
    r = math.pi / 180
    dl = (b[1] - a[1]) * r
    dn = (b[0] - a[0]) * r
    h = (math.sin(dl / 2) ** 2
         + math.cos(a[1] * r) * math.cos(b[1] * r) * math.sin(dn / 2) ** 2)
    return 2 * R_M * math.asin(math.sqrt(h))


def cumdist(path):
    d = [0.0]
    for k in range(1, len(path)):
        d.append(d[-1] + hav(path[k - 1], path[k]))
    return d


def ordered(segs, start):
    if not segs:
        return []
    path = [list(p) for p in segs[0]]
    if len(segs) > 1:
        s1 = segs[1]
        e = lambda p: min(hav(p, s1[0]), hav(p, s1[-1]))  # noqa: E731
        if e(path[0]) < e(path[-1]):
            path.reverse()
    for k in range(1, len(segs)):
        s = [list(p) for p in segs[k]]
        end = path[-1]
        if hav(end, s[-1]) < hav(end, s[0]):
            s.reverse()
        if hav(end, s[0]) > 3000:
            break
        path.extend(s[1:])
    bi, bd = 0, float("inf")
    for k, p in enumerate(path):
        d = hav(p, start)
        if d < bd:
            bd, bi = d, k
    return [list(start)] + path[bi + 1:]


def chain(segs, start_near):
    left = [[list(p) for p in s] for s in segs]
    path, cur = [], list(start_near)
    while left:
        best, bd, rev = -1, float("inf"), False
        for k, s in enumerate(left):
            a, b = hav(cur, s[0]), hav(cur, s[-1])
            if a < bd:
                bd, best, rev = a, k, False
            if b < bd:
                bd, best, rev = b, k, True
        if bd > 3000 and path:
            break
        s = left.pop(best)
        if rev:
            s.reverse()
        path.extend(s)
        cur = path[-1]
    return path


def river_path(segs, start):
    if not segs:
        return []
    a, b = ordered(segs, start), chain(segs, start)
    la = cumdist(a)[-1] if len(a) > 1 else 0
    lb = cumdist(b)[-1] if len(b) > 1 else 0
    return a if la >= lb else b


def basin_area_km2(rings):
    """Same spherical ring formula as the 3D station pages."""
    best = 0.0
    for r in rings:
        a = 0.0
        for k in range(len(r) - 1):
            l1, p1 = r[k]
            l2, p2 = r[k + 1]
            a += ((l2 - l1) * math.pi / 180
                  * (2 + math.sin(p1 * math.pi / 180)
                     + math.sin(p2 * math.pi / 180)))
        best = max(best, abs(a * 6371 * 6371 / 2))
    return best


def _dp(pts, tol, kx, ky):
    if len(pts) <= 2:
        return pts
    keep = [False] * len(pts)
    keep[0] = keep[-1] = True
    stack = [(0, len(pts) - 1)]
    while stack:
        i0, i1 = stack.pop()
        ax, ay = pts[i0][0] * kx, pts[i0][1] * ky
        bx, by = pts[i1][0] * kx, pts[i1][1] * ky
        dx, dy = bx - ax, by - ay
        den = math.hypot(dx, dy) or 1e-12
        dmax, imax = 0.0, -1
        for i in range(i0 + 1, i1):
            px, py = pts[i][0] * kx, pts[i][1] * ky
            d = abs(dy * px - dx * py + bx * ay - by * ax) / den
            if d > dmax:
                dmax, imax = d, i
        if dmax > tol and imax > 0:
            keep[imax] = True
            stack.append((i0, imax))
            stack.append((imax, i1))
    return [p for p, k in zip(pts, keep) if k]


def simplify_rings(rings, max_points=340):
    pts_all = [p for r in rings for p in r]
    if not pts_all:
        return []
    lat0 = sum(p[1] for p in pts_all) / len(pts_all)
    kx = math.cos(math.radians(lat0))
    span = max(max(p[0] for p in pts_all) - min(p[0] for p in pts_all),
               max(p[1] for p in pts_all) - min(p[1] for p in pts_all), 0.01)
    tol = span * 0.0012
    out = []
    for _ in range(24):
        out = []
        for r in rings:
            s = _dp_ring(r, tol, kx)
            if len(s) >= 4:
                out.append([[round(x, 4), round(y, 4)] for x, y in s])
        if sum(len(r) for r in out) <= max_points:
            break
        tol *= 1.4
    return out


def _dp_ring(ring, tol, kx):
    """Douglas-Peucker on a closed ring: split at the vertex farthest
    from vertex 0 so neither arc is degenerate, simplify both arcs,
    rejoin and re-close."""
    pts = [list(p) for p in ring]
    if len(pts) > 1 and pts[0] == pts[-1]:
        pts = pts[:-1]
    if len(pts) < 4:
        return []
    j, bd = 0, -1.0
    for i, p in enumerate(pts):
        d = ((p[0] - pts[0][0]) * kx) ** 2 + (p[1] - pts[0][1]) ** 2
        if d > bd:
            bd, j = d, i
    if j == 0:
        return []
    arc1 = _dp(pts[:j + 1], tol, kx, 1.0)
    arc2 = _dp(pts[j:] + [pts[0]], tol, kx, 1.0)
    merged = arc1[:-1] + arc2
    return merged


def simplify_path(path, max_points=150):
    if len(path) <= max_points:
        return [[round(x, 4), round(y, 4)] for x, y in path]
    step = math.ceil(len(path) / max_points)
    out = [path[i] for i in range(0, len(path), step)]
    if out[-1] != path[-1]:
        out.append(path[-1])
    return [[round(x, 4), round(y, 4)] for x, y in out]


def one_station(st):
    site, start = st["site"], [st["lon"], st["lat"]]
    base = NLDI.format(site=site)
    basin = fetch(base + "basin?f=json&simplified=true")
    dmf = fetch(base + "navigation/DM/flowlines?distance=400&f=json")
    umf = fetch(base + "navigation/UM/flowlines?distance=150&f=json")
    dmg = fetch(base + "navigation/DM/nwissite?distance=400&f=json")
    rings = lines(basin)
    area = basin_area_km2(rings)
    dm_path = river_path(lines(dmf), start)
    um_path = river_path(lines(umf), start)
    dm_cum = cumdist(dm_path) if len(dm_path) > 1 else [0.0]
    down = []
    if len(dm_path) > 1:
        for f in dmg.get("features") or []:
            g = f.get("geometry") or {}
            c = g.get("coordinates")
            if not c:
                continue
            bd, bi = float("inf"), -1
            for k, p in enumerate(dm_path):
                d = hav(p, c)
                if d < bd:
                    bd, bi = d, k
            if bd < 5000:
                props = f.get("properties") or {}
                down.append({"site": (props.get("identifier") or "")
                             .replace("USGS-", ""),
                             "name": props.get("name") or "",
                             "km": round(dm_cum[bi] / 1000)})
        down = [d for d in down if d["site"] != site]
        down.sort(key=lambda d: d["km"])
        down = down[:4]
    return site, {
        "area_km2": round(area),
        "rings": simplify_rings(rings),
        "dm_km": round(dm_cum[-1] / 1000) if len(dm_path) > 1 else 0,
        "um_km": round(cumdist(um_path)[-1] / 1000) if len(um_path) > 1 else 0,
        "dm": simplify_path(dm_path),
        "um": simplify_path(um_path),
        "down": down,
    }


def main():
    src = ROOT / "index.html"
    html = src.read_text(encoding="utf-8", errors="replace")
    m = re.search(r"window\.MAP=(\{.*?\});</script>", html, re.S)
    stations = json.loads(m.group(1))["stations"]
    out = {}
    with ThreadPoolExecutor(max_workers=3) as ex:
        for site, rec in ex.map(one_station, stations):
            out[site] = rec
            print(site, "area", rec["area_km2"], "dm", rec["dm_km"],
                  "um", rec["um_km"], "down", len(rec["down"]),
                  "ringpts", sum(len(r) for r in rec["rings"]), flush=True)
    dest = ROOT / "basins" / "basins.json"
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(out, separators=(",", ":")))
    print("wrote", dest, dest.stat().st_size, "bytes")


if __name__ == "__main__":
    sys.exit(main())
