#!/usr/bin/env python3
"""ht-bridgegap v1 data: where do OSM bridges cross each station's river?

For every station: take the baked 3DEP river profile (build25/
realriver_data.py, page coordinates, samples every 60 m along the NLDI
path), keep the part inside the 3D scene (|x|,|z| <= WM/2 where
WM = 1280 * M0 / 2^12 in the pages' Web Mercator frame), fetch OSM ways
tagged bridge=* with highway=* or railway=* in that extent (Overpass),
project each way into page coordinates, and keep the ways that actually
cross the river path (closest approach <= 45 m, crossing angle >= 25
degrees so near-parallel ways are ignored). Each kept crossing is baked
as [x, z, halfwidth] in page coordinates: the crossing point on the
river path plus half the deck width along the river (from the way's
width / lanes tags, else a per-class default) plus a 3 m margin.

Output: build25/bridgegap_data.py with HT_BRIDGE_CROSSINGS.
Re-run manually when OSM or the profiles change; the deploy workflow
only consumes the baked file (patch_bridgegap.py), like realriver.
"""
import json, math, sys, time, urllib.parse, urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from realriver_data import HT_RIVER_PROFILES

UA = {'User-Agent': 'HydroTwin/1.0 (dev build; bridge gap data)'}
OVERPASS = 'https://overpass-api.de/api/interpreter'

CLASS_HALF = {  # half deck width in metres, before the +3 m margin
    'motorway': 11.0, 'motorway_link': 8.0, 'trunk': 10.0, 'trunk_link': 7.0,
    'primary': 8.0, 'primary_link': 6.0, 'secondary': 7.0, 'secondary_link': 6.0,
    'tertiary': 6.0, 'tertiary_link': 5.0, 'unclassified': 5.0, 'residential': 5.0,
    'service': 4.0, 'road': 6.0, 'footway': 2.5, 'path': 2.5, 'pedestrian': 2.5,
    'cycleway': 2.5, 'steps': 2.5, 'rail': 5.0,
}


def lon2px(lon):
    return (lon + 180.0) / 360.0 * 256.0


def lat2px(lat):
    s = math.sin(math.radians(lat))
    return (0.5 - math.log((1 + s) / (1 - s)) / (4 * math.pi)) * 256.0


def px2lon(px):
    return px / 256.0 * 360.0 - 180.0


def px2lat(px):
    n = math.pi * (1 - 2 * px / 256.0)
    return math.degrees(math.atan(math.sinh(n)))


class Frame:
    def __init__(self, lat, lon):
        self.m0 = 156543.03392 * math.cos(math.radians(lat))
        self.gx0, self.gy0 = lon2px(lon), lat2px(lat)
        self.wm = 1280.0 * self.m0 / 4096.0

    def mx(self, lon):
        return (lon2px(lon) - self.gx0) * self.m0

    def mz(self, lat):
        return (lat2px(lat) - self.gy0) * self.m0

    def to_lonlat(self, x, z):
        return px2lon(x / self.m0 + self.gx0), px2lat(z / self.m0 + self.gy0)


def seg_closest(px, pz, ax, az, bx, bz):
    dx, dz = bx - ax, bz - az
    l2 = dx * dx + dz * dz or 1.0
    t = max(0.0, min(1.0, ((px - ax) * dx + (pz - az) * dz) / l2))
    qx, qz = ax + dx * t, az + dz * t
    return math.hypot(px - qx, pz - qz), t, qx, qz


def halfwidth(tags):
    w = tags.get('width')
    if w:
        try:
            return max(2.0, float(str(w).split()[0].replace(',', '.')) / 2.0)
        except ValueError:
            pass
    lanes = tags.get('lanes')
    if lanes:
        try:
            return max(2.5, int(str(lanes).split(';')[0]) * 1.8 + 1.0)
        except ValueError:
            pass
    cls = tags.get('highway') or ('rail' if tags.get('railway') else '')
    return CLASS_HALF.get(cls, 6.0)


def overpass(bbox):
    q = ('[out:json][timeout:60];(way["bridge"]["highway"]({s},{w},{n},{e});'
         'way["bridge"]["railway"]({s},{w},{n},{e}););out geom;').format(**bbox)
    url = OVERPASS + '?data=' + urllib.parse.quote(q)
    last = None
    for attempt in range(4):
        try:
            req = urllib.request.Request(url, headers=UA)
            with urllib.request.urlopen(req, timeout=120) as r:
                return json.loads(r.read().decode('utf8'))
        except Exception as e:  # Overpass 502/429 under load: back off and retry
            last = e
            time.sleep(5 * (attempt + 1) ** 2)
    raise last


def main():
    idx = json.loads((Path(__file__).resolve().parent.parent / 'helper' / 'ht-index.json').read_text())
    stations = {s['site']: s for s in idx['stations']}
    out = {}
    report = []
    for site, st in sorted(stations.items()):
        prof = (HT_RIVER_PROFILES.get(site) or {}).get('samples') or []
        fr = Frame(st['lat'], st['lon'])
        half = fr.wm / 2.0
        path = [(s[0], s[1]) for s in prof if abs(s[0]) <= half and abs(s[1]) <= half]
        if len(path) < 2:
            out[site] = []
            report.append(f'{site}: no in-scene path, skipped')
            continue
        # arclength along the path
        S = [0.0]
        for i in range(1, len(path)):
            S.append(S[-1] + math.hypot(path[i][0] - path[i - 1][0], path[i][1] - path[i - 1][1]))
        lons, lats = zip(*(fr.to_lonlat(x, z) for x, z in path))
        pad = 0.004
        bbox = {'s': min(lats) - pad, 'w': min(lons) - pad, 'n': max(lats) + pad, 'e': max(lons) + pad}
        data = overpass(bbox)
        ways = [e for e in data.get('elements', []) if e.get('type') == 'way' and e.get('geometry')]
        # spatial grid over path segments (500 m cells) for fast closest queries
        CELL = 500.0
        grid = {}
        for i in range(len(path) - 1):
            ax, az = path[i]
            bx, bz = path[i + 1]
            for gx in range(int(min(ax, bx) // CELL) - 1, int(max(ax, bx) // CELL) + 2):
                for gz in range(int(min(az, bz) // CELL) - 1, int(max(az, bz) // CELL) + 2):
                    grid.setdefault((gx, gz), []).append(i)

        def closest_on_path(px, pz):
            gx, gz = int(px // CELL), int(pz // CELL)
            cand = set()
            for a in (-1, 0, 1):
                for b in (-1, 0, 1):
                    cand.update(grid.get((gx + a, gz + b), ()))
            best = None
            for i in cand:
                d, t, qx, qz = seg_closest(px, pz, *path[i], *path[i + 1])
                if best is None or d < best[0]:
                    best = (d, S[i] + t * (S[i + 1] - S[i]), i)
            return best

        kept = []
        for way in ways:
            tags = way.get('tags') or {}
            if tags.get('highway') in ('construction', 'proposed'):
                continue  # not a built deck yet: no gap in the water for it
            pts = [(fr.mx(g['lon']), fr.mz(g['lat'])) for g in way['geometry']]
            best = None  # (dist, s_on_path, seg_index_on_path, bridge_seg_index)
            for j in range(len(pts) - 1):
                for tt in (0.0, 0.5, 1.0):
                    bx = pts[j][0] + (pts[j + 1][0] - pts[j][0]) * tt
                    bz = pts[j][1] + (pts[j + 1][1] - pts[j][1]) * tt
                    r = closest_on_path(bx, bz)
                    if r and (best is None or r[0] < best[0]):
                        best = (r[0], r[1], r[2], j)
            if best is None or best[0] > 45.0:
                continue
            d, s_star, pi, bj = best
            # crossing angle between bridge segment and river segment
            bdx, bdz = pts[bj + 1][0] - pts[bj][0], pts[bj + 1][1] - pts[bj][1]
            pdx, pdz = path[pi + 1][0] - path[pi][0], path[pi + 1][1] - path[pi][1]
            bl, pl = math.hypot(bdx, bdz) or 1.0, math.hypot(pdx, pdz) or 1.0
            cosang = abs((bdx * pdx + bdz * pdz) / (bl * pl))
            ang = math.degrees(math.acos(max(-1.0, min(1.0, cosang))))
            if ang < 25.0:
                continue
            # crossing point on the path at s_star
            i = max(0, min(len(path) - 2, next(k for k in range(len(S) - 1) if S[k + 1] >= s_star)))
            t = (s_star - S[i]) / ((S[i + 1] - S[i]) or 1.0)
            cx = path[i][0] + (path[i + 1][0] - path[i][0]) * t
            cz = path[i][1] + (path[i + 1][1] - path[i][1]) * t
            hw = min(32.0, max(4.0, halfwidth(tags) + 3.0))
            kept.append({'s': s_star, 'x': round(cx, 1), 'z': round(cz, 1), 'w': round(hw, 1),
                         'name': tags.get('name') or tags.get('ref') or tags.get('highway')
                                 or tags.get('railway') or '?', 'way': way['id'], 'dist': round(d, 1)})
        kept.sort(key=lambda c: c['s'])
        # merge crossings closer than 20 m of path (keep the wider)
        merged = []
        for c in kept:
            if merged and c['s'] - merged[-1]['s'] < 20.0:
                if c['w'] > merged[-1]['w']:
                    merged[-1] = c
            else:
                merged.append(c)
        out[site] = [[c['x'], c['z'], c['w']] for c in merged]
        names = ', '.join(f"{c['name']} (way {c['way']}, w={c['w']}m)" for c in merged)
        report.append(f"{site}: {len(ways)} bridge ways in extent, {len(merged)} crossings kept"
                      + (f" — {names}" if names else ''))
        print(report[-1], flush=True)
        time.sleep(1.0)
    dest = Path(__file__).resolve().parent / 'bridgegap_data.py'
    body = ('# ht-bridgegap v1 baked data: OSM bridge crossings of each station river,\n'
            '# generated by build25/gen_bridgegap_data.py from OpenStreetMap (ODbL) ways\n'
            '# tagged bridge=* with highway=* or railway=*, projected onto the baked\n'
            '# 3DEP river profile. Per station: [x, z, halfwidth] in page coordinates.\n'
            'HT_BRIDGE_CROSSINGS = ' + repr(out) + '\n')
    dest.write_text(body)
    print('\n'.join(report))
    print('wrote', dest, len(body), 'bytes')


if __name__ == '__main__':
    main()
