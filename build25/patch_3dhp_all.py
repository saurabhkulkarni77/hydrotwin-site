#!/usr/bin/env python3
"""ht-3dhp v1 rollout: every remaining station's polygon water is
rebuilt from USGS 3DHP, following the Dallas gate build
(build25/patch_3dhp_dallas.py, which stays in the chain ahead of
this step and owns Dallas 08057000).

Same reasoning as the Dallas build: the polygon water layer
(ht-polywater v1) was baked in October 2026 from an OpenStreetMap
pull - a frozen snapshot of a volunteer dataset. The river source
must be the dataset USGS itself maintains: the 3D Hydrography
Program (3DHP), live service 3DHP_all on hydro.nationalmap.gov,
layer 60 (Waterbody). This patcher swaps each station's POLYWATER
array for the 3DHP build in build25/water3dhp_data.py.

Unlike the Dallas step, the gap cutting here is BAKED INTO the
data module at build time rather than re-cut in the chain, and
the build record says why. The Dallas step re-cuts in the chain
because its rings are simple near-channel polygons. The NHD
waterbodies behind 3DHP are not: they merge the channel with
floodplain water kilometres off the path into single rings, and
measured three ways during the rollout those rings fold under
(s, d) frame clipping (the (s, d) image of a multi-reach ring
self-overlaps, and the clip walk interleaves the layers): the
shipped slab cutter's output carried 3,852 proper self-
intersections at Potomac (legacy page 148) and 1,661 at
Louisville (legacy 12); a laterally bounded rectangle variant
still left 1,089 at Louisville after neck splits and 800 m
tiling. So the arrays in water3dhp_data.py were produced at build
time with a real planar geometry kernel (GEOS): union of the
3DHP waterbodies >= 0.015 km2 over the legacy bake box, then

- river crossing bands differenced out as buffered path strips
  (flat caps, half-width from the water's own extent at the
  crossing, band length widened by the skew factor 1/sin(theta)
  measured from the crossing road's OSM angle, capped 3x, plus a
  3 m kerf), applied only to water components touching the path;
- road-over-water strips differenced out the same way: OSM road
  centrelines were sampled against the swapped geometry, and
  every stretch >= 15 m found in water (roads over lakes and
  wide waterbodies - the path gap system only ever cut crossings
  of the river path) was cut as a buffered road strip, half-width
  by road class.

This patcher is then a guarded splice, like every baked-data
step in the chain: it writes the swap only if the baked array is
finite, its area is sane against the legacy array, and its
proper self-intersection count does not exceed the legacy
array's on the same page. The full audit battery (deck band,
road strips, path coverage, ring hygiene, headless load) is run
against the served pages after deploy; those numbers are in the
project status log.

Provenance, recorded honestly per station in water3dhp_data.py
and in the marker line: at pull time (2026-11-01) NO rollout
station was covered by an elevation-derived (EDH) workunit in
3DHP - every waterbody carries an NHD workunit id, so all
thirteen are NHD-sourced content served through 3DHP, the same
finding as the Dallas gate build. 3DHP is the live, maintained
USGS product either way.

Idempotent: pages carrying the marker are skipped.
Run from the repo root: python3 build25/patch_3dhp_all.py
"""
import glob, json, math, os, re, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from patch_polygap import Frame, extract_json, net_area_m2
from water3dhp_data import POLYWATER_3DHP_CUT, PROVENANCE_3DHP

MARKER = 'ht-3dhp v1'
PW_MARK = 'const POLYWATER ='
DALLAS = '08057000'


def _seg_proper(a, b, c, d):
    def orient(p, q, r):
        return (q[0] - p[0]) * (r[1] - p[1]) - (q[1] - p[1]) * (r[0] - p[0])
    o1, o2 = orient(a, b, c), orient(a, b, d)
    o3, o4 = orient(c, d, a), orient(c, d, b)
    return (o1 > 0) != (o2 > 0) and (o3 > 0) != (o4 > 0) and o1 != 0 and o2 != 0 and o3 != 0 and o4 != 0


def count_self_intersections(polywater_ll, frame):
    """Proper self-intersections over all rings, grid accelerated
    (the rollout audit's own counter, kept identical)."""
    total = 0
    for poly in polywater_ll:
        for flat in poly:
            pts = [(frame.mx(flat[i]), frame.mz(flat[i + 1])) for i in range(0, len(flat) - 1, 2)]
            if len(pts) > 1 and pts[0] == pts[-1]:
                pts.pop()
            n = len(pts)
            if n < 4:
                continue
            CELL = 100.0
            grid = {}
            segs = [(pts[i], pts[(i + 1) % n]) for i in range(n)]
            for i, (a, b) in enumerate(segs):
                for cx in range(int(min(a[0], b[0]) // CELL), int(max(a[0], b[0]) // CELL) + 1):
                    for cz in range(int(min(a[1], b[1]) // CELL), int(max(a[1], b[1]) // CELL) + 1):
                        grid.setdefault((cx, cz), []).append(i)
            seen = set()
            for idxs in grid.values():
                for ii in range(len(idxs)):
                    for jj in range(ii + 1, len(idxs)):
                        i, j = idxs[ii], idxs[jj]
                        if i == j or (i, j) in seen:
                            continue
                        seen.add((i, j))
                        if abs(i - j) <= 1 or (i == 0 and j == n - 1) or (j == 0 and i == n - 1):
                            continue
                        if _seg_proper(segs[i][0], segs[i][1], segs[j][0], segs[j][1]):
                            total += 1
    return total


def patch(path):
    site = os.path.basename(path).split('-')[1]
    if site == DALLAS:
        return 'skip-dallas-owned-by-patch_3dhp_dallas'
    new_ll = POLYWATER_3DHP_CUT.get(site)
    if not new_ll:
        return 'skip-no-3dhp-data'
    with open(path, encoding='utf8') as f:
        html = f.read()
    if MARKER in html:
        return 'skip'
    if 'ht-polywater v1' not in html or html.count(PW_MARK) != 1:
        return 'skip-no-polywater'
    prov = PROVENANCE_3DHP.get(site, {})
    m = re.search(r'window\.HT3D = \{[^}]*"lat":\s*(-?[\d.]+),\s*"lon":\s*(-?[\d.]+)', html)
    if not m:
        return f'FAILED HT3D lat/lon not found - page left unwritten'
    frame = Frame(float(m.group(1)), float(m.group(2)))
    pw_txt, pw_span = extract_json(html, PW_MARK)
    old_ll = json.loads(pw_txt)
    # guards
    for poly in new_ll:
        for flat in poly:
            if any(not math.isfinite(v) for v in flat):
                return f'FAILED non-finite vertex in baked array for {site} - page left unwritten'
    a_old = net_area_m2(old_ll, frame)
    a_new = net_area_m2(new_ll, frame)
    if not (0.1 * a_old <= a_new <= 5.0 * a_old):
        return (f'FAILED baked area {a_new:.0f} m2 not sane vs legacy {a_old:.0f} m2 '
                f'for {site} - page left unwritten')
    sx_old = count_self_intersections(old_ll, frame)
    sx_new = count_self_intersections(new_ll, frame)
    if sx_new > sx_old:
        return (f'FAILED self-intersections regress {sx_old} -> {sx_new} for {site} '
                '- page left unwritten')
    n_pg = html.count('ht-polygap v1')
    n_pw = html.count('ht-polywater v1')
    marker_line = ('/* ht-3dhp v1: %s polygon water rebuilt from USGS 3DHP '
                   'waterbodies (%s); bridge bands and road strips baked in '
                   'at build time (build25/patch_3dhp_all.py) */\n'
                   % (prov.get('name', site), prov.get('source', '3DHP')))
    new_txt = json.dumps(new_ll, separators=(',', ':'))
    html = html[:pw_span[0]] + new_txt + html[pw_span[1]:]
    i = html.index(PW_MARK)
    html = html[:i] + marker_line + html[i:]
    if html.count(MARKER) != 1:
        return f'FAILED marker count wrong after splice for {site} - page left unwritten'
    if html.count('ht-polygap v1') != n_pg or html.count('ht-polywater v1') != n_pw:
        return f'FAILED downstream marker census changed for {site} - page left unwritten'
    with open(path, 'w', encoding='utf8') as f:
        f.write(html)
    return (f"patched polys={len(old_ll)}->{len(new_ll)} "
            f"area_km2={a_old / 1e6:.2f}->{a_new / 1e6:.2f} "
            f"selfx={sx_old}->{sx_new}")


def main():
    root = sys.argv[1] if len(sys.argv) > 1 else 'stations'
    pages = sorted(glob.glob(os.path.join(root, 'USGS-*-3d.html')))
    if not pages:
        raise SystemExit(f'no station pages under {root}')
    for p in pages:
        try:
            print(patch(p), os.path.basename(p), flush=True)
        except Exception as e:
            print(f'FAILED {type(e).__name__}: {e} - page left unwritten', os.path.basename(p), flush=True)


if __name__ == '__main__':
    main()
