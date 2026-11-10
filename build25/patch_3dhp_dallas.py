#!/usr/bin/env python3
"""ht-3dhp v1: the Dallas polygon water is rebuilt from USGS 3DHP.

The polygon water layer (ht-polywater v1) was baked in October 2026
from an OpenStreetMap pull (build25/polywater_data.py) - a frozen
snapshot of a volunteer dataset. Saurabh's call (2026-11-01): the
river source must be the dataset USGS itself maintains. That is the
3D Hydrography Program (3DHP), the maintained successor to the
National Hydrography Dataset: live service 3DHP_all on
hydro.nationalmap.gov, layer 60 (Waterbody). This patcher swaps the
Dallas (USGS 08057000) POLYWATER array for the 3DHP build in
build25/dallas3dhp_data.py (same treatment as the legacy bake:
>= 15,000 m2 waterbodies, Douglas-Peucker 4 m, 6 dp, rings closed;
polygons limited to the rendered overview block + 2 km, rings clipped
to it). At pull time the Dallas workunits in 3DHP are NHD-sourced -
no elevation-derived hydrography workunit covers the reach yet; 3DHP
is the live USGS product and EDH replaces the NHD content area by
area as it is collected.

Dallas ONLY: this is the gate station for the source switch. Every
other page is skipped untouched.

The swap keeps every behaviour built on top of the polygon layer:

- the bridge gaps: the fresh rings are cut with patch_polygap's own
  PolyGapCutter (same crossings from the page's HT_BRIDGES table,
  same baked 3DEP profile), so the polygon water still stops at
  every bridge deck exactly where the gapped ribbon does. This step
  runs AFTER patch_polygap in the Deploy DEV chain; the page's
  ht-polygap v1 marker stays in place and stays true - the final
  baked array carries the cuts, applied by the same cutter code.
- the flood grid still owns the central block (htPolyBuild drops
  polygon triangles whose centroid lands in the block at runtime -
  source-independent).
- the ribbon, its profile, the helper, the panels and the date
  behaviour are untouched: only the POLYWATER array changes, plus
  this marker comment above it.

Idempotent: pages carrying the marker are skipped. On failure the
page is left unwritten and the step fails loudly, like every other
patcher in this chain.
Run from the repo root: python3 build25/patch_3dhp_dallas.py
"""
import glob, json, os, re, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from patch_polygap import PolyGapCutter, Frame, extract_json, net_area_m2
from dallas3dhp_data import POLYWATER_3DHP
try:
    from realriver_data import HT_RIVER_PROFILES
except Exception:
    HT_RIVER_PROFILES = {}

MARKER = 'ht-3dhp v1'
MARKER_LINE = ('/* ht-3dhp v1: Dallas polygon water rebuilt from USGS 3DHP '
               'waterbodies; bridge bands re-cut with the patch_polygap '
               'cutter (build25/patch_3dhp_dallas.py) */\n')
PW_MARK = 'const POLYWATER ='
BR_MARK = 'const HT_BRIDGES ='
SITE = '08057000'


def patch(path):
    site = os.path.basename(path).split('-')[1]
    if site != SITE:
        return 'skip-not-dallas'
    with open(path, encoding='utf8') as f:
        html = f.read()
    if MARKER in html:
        return 'skip'
    if 'ht-polywater v1' not in html or html.count(PW_MARK) != 1 or BR_MARK not in html:
        return 'skip-no-polywater-or-bridges'
    new_ll = POLYWATER_3DHP.get(SITE)
    if not new_ll:
        raise SystemExit(f'{path}: no 3DHP data baked for {SITE}')
    prof = (HT_RIVER_PROFILES.get(SITE) or {}).get('samples') or []
    if not prof:
        raise SystemExit(f'{path}: no baked profile for {SITE}')
    m = re.search(r'window\.HT3D = \{[^}]*"lat":\s*(-?[\d.]+),\s*"lon":\s*(-?[\d.]+)', html)
    if not m:
        raise SystemExit(f'{path}: HT3D lat/lon not found')
    frame = Frame(float(m.group(1)), float(m.group(2)))
    pw_txt, pw_span = extract_json(html, PW_MARK)
    br_txt, _ = extract_json(html, BR_MARK)
    old_ll = json.loads(pw_txt)
    bridges = json.loads(br_txt)
    if not bridges:
        raise SystemExit(f'{path}: page carries no bridge crossings')
    profile = [(s[0], s[1]) for s in prof]
    cutter = PolyGapCutter(frame, profile, bridges)
    cut_ll, stats = cutter.cut(new_ll)
    if stats['crossings_cut'] == 0:
        raise SystemExit(f'{path}: 3DHP swap would leave every bridge band '
                         'uncut - refusing to write')
    a_new = net_area_m2(new_ll, frame)
    a_cut = net_area_m2(cut_ll, frame)
    if a_cut > a_new * 1.005 + 1000.0:
        raise SystemExit(f'{path}: cut grew the water {a_new:.0f} -> {a_cut:.0f} m2')
    a_old = net_area_m2(old_ll, frame)
    n_pg = html.count('ht-polygap v1')
    n_pw = html.count('ht-polywater v1')
    new_txt = json.dumps(cut_ll, separators=(',', ':'))
    html = html[:pw_span[0]] + new_txt + html[pw_span[1]:]
    i = html.index(PW_MARK)
    html = html[:i] + MARKER_LINE + html[i:]
    if html.count(MARKER) != 1:
        raise SystemExit(f'{path}: marker count wrong after splice')
    if html.count('ht-polygap v1') != n_pg or html.count('ht-polywater v1') != n_pw:
        raise SystemExit(f'{path}: downstream marker census changed by splice')
    with open(path, 'w', encoding='utf8') as f:
        f.write(html)
    return (f"patched polys={len(old_ll)}->{stats['polys_after']} "
            f"crossings_cut={stats['crossings_cut']}/{len(bridges)} "
            f"area_km2={a_old / 1e6:.2f}->{a_cut / 1e6:.2f} "
            f"band_removed_m2={a_new - a_cut:.0f} rejected={stats['clips_rejected']}")


def main():
    root = sys.argv[1] if len(sys.argv) > 1 else 'stations'
    pages = sorted(glob.glob(os.path.join(root, 'USGS-*-3d.html')))
    if not pages:
        raise SystemExit(f'no station pages under {root}')
    for p in pages:
        print(patch(p), os.path.basename(p))


if __name__ == '__main__':
    main()
