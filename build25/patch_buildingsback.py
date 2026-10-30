#!/usr/bin/env python3
"""ht-buildingsback v1: reverse ht-nobuild (the user reversed the removal
order) and harden the building water filter.

1. Restores the loadBuildings() call site that ht-nobuild replaced, and
   restores the info-panel / attribution copy that mentioned buildings.
2. Extends the existing ht-riverwater flood-grid wet test inside
   loadBuildings with two more drop rules, applied per footprint:
   - the footprint (corners, edge midpoints, centroid) intersects an OSM
     water polygon (POLYWATER), or a water-polygon vertex falls within
     ~50 m of the footprint box;
   - the footprint comes within 100 m (centroid) / 60 m (any corner) of
     the river path corridor (PATHM).
   When in doubt, the building is dropped. Kept/dropped counts are exposed
   as window.__htBuildings for verification.

Idempotent: pages already carrying the marker are skipped. The call-site
restore tolerates pages that never had ht-nobuild applied.
"""
import glob, os, sys

MARKER = 'ht-buildingsback v1'
NOBUILD_CALL = "setLoad('buildings', 'removed'); /* ht-nobuild v1: 3D buildings layer removed at the user's request */"
ORIG_CALL = "loadBuildings().catch(() => setLoad('buildings', 'not available'));"
DEF_ANCHOR = 'async function loadBuildings() {'
COUNT_ANCHOR = 'const geos = []; const tmp = new THREE.Color(); let count = 0;'
WET_ANCHOR = '    if (inWater(pts)) continue;   // ht-riverwater v1'
WET_REPL = ('    if (inWater(pts)) { htBDropped++; continue; }   // ht-riverwater v1\n'
            '    if (htInPolyWater(el.geometry) || htNearPath(pts)) { htBDropped++; continue; }   '
            '// ht-buildingsback v1: never in water polygons or the river corridor')
END_ANCHOR = "setLoad('buildings', 'ok'); BLD.n = count;"
END_REPL = END_ANCHOR + " window.__htBuildings = { kept: count, droppedWater: htBDropped };"

HELPERS = r'''
// ------------------------------------------------------------------ ht-buildingsback v1
// Buildings restored at the user's direction, with a hard water filter on
// top of the ht-riverwater flood-grid test: drop any footprint touching an
// OSM water polygon or the river path corridor. When in doubt, drop.
let htRingBoxes = null;
function htPtInRing(lon, lat, ring) { let inside = false;
  for (let i = 0, j = ring.length - 2; i < ring.length; j = i, i += 2) {
    const xi = ring[i], yi = ring[i + 1], xj = ring[j], yj = ring[j + 1];
    if (((yi > lat) !== (yj > lat)) && (lon < (xj - xi) * (lat - yi) / (yj - yi) + xi)) inside = !inside; }
  return inside; }
function htInPolyWater(geom) {
  if (typeof POLYWATER === 'undefined' || !POLYWATER || !POLYWATER.length || !geom || geom.length < 3) return false;
  if (!htRingBoxes) { htRingBoxes = POLYWATER.map((ring) => { let a = 1e9, b = -1e9, c = 1e9, d = -1e9;
    for (let i = 0; i < ring.length; i += 2) { a = Math.min(a, ring[i]); b = Math.max(b, ring[i]); c = Math.min(c, ring[i + 1]); d = Math.max(d, ring[i + 1]); }
    return [a, b, c, d]; }); }
  let cx = 0, cy = 0, minLo = 1e9, maxLo = -1e9, minLa = 1e9, maxLa = -1e9;
  for (const g of geom) { cx += g.lon; cy += g.lat; minLo = Math.min(minLo, g.lon); maxLo = Math.max(maxLo, g.lon); minLa = Math.min(minLa, g.lat); maxLa = Math.max(maxLa, g.lat); }
  cx /= geom.length; cy /= geom.length;
  const probes = geom.map((g) => [g.lon, g.lat]); probes.push([cx, cy]);
  for (let k = 0; k < geom.length; k++) { const a = geom[k], b = geom[(k + 1) % geom.length]; probes.push([(a.lon + b.lon) / 2, (a.lat + b.lat) / 2]); }
  const PAD = 0.0005;
  for (let r = 0; r < POLYWATER.length; r++) { const bb = htRingBoxes[r];
    if (bb[1] < minLo - PAD || bb[0] > maxLo + PAD || bb[3] < minLa - PAD || bb[2] > maxLa + PAD) continue;
    const ring = POLYWATER[r];
    for (const [lo, la] of probes) if (htPtInRing(lo, la, ring)) return true;
    for (let i = 0; i < ring.length; i += 2)
      if (ring[i] > minLo - PAD && ring[i] < maxLo + PAD && ring[i + 1] > minLa - PAD && ring[i + 1] < maxLa + PAD) return true; }
  return false; }
function htNearPath(pts) {
  if (typeof PATHM === 'undefined' || !PATHM || PATHM.length < 2) return false;
  const seg = (x, z) => { let bd = Infinity;
    for (let k = 1; k < PATHM.length; k++) { const pa = PATHM[k - 1], pb = PATHM[k];
      const dx = pb[0] - pa[0], dz = pb[1] - pa[1], L2 = dx * dx + dz * dz || 1;
      let t = ((x - pa[0]) * dx + (z - pa[1]) * dz) / L2; t = Math.max(0, Math.min(1, t));
      const d = Math.hypot(x - (pa[0] + dx * t), z - (pa[1] + dz * t)); if (d < bd) bd = d; }
    return bd; };
  let cx = 0, cz = 0; for (const [x, z] of pts) { cx += x; cz += z; }
  if (seg(cx / pts.length, cz / pts.length) < 100) return true;
  for (const [x, z] of pts) if (seg(x, z) < 60) return true;
  return false; }
'''


def patch(path):
    with open(path, encoding='utf8') as f:
        html = f.read()
    if MARKER in html:
        return 'skip'
    # 1. restore the call site (if ht-nobuild had removed it)
    if html.count(NOBUILD_CALL) == 1:
        html = html.replace(NOBUILD_CALL, ORIG_CALL, 1)
    elif html.count(ORIG_CALL) != 1:
        raise SystemExit(f'{path}: neither nobuild nor original call site found exactly once')
    # 2. restore copy (lenient: only when the nobuild wording is present)
    if html.count('Real ground and imagery around the gauge.') == 1:
        html = html.replace('Real ground and imagery around the gauge.',
                            'Real ground, imagery and buildings around the gauge.', 1)
    attr_old = '(USGS 3DEP, SRTM) · Rivers, watershed, gauges'
    if html.count(attr_old) == 1:
        html = html.replace(attr_old,
                            '(USGS 3DEP, SRTM) · Buildings: Microsoft Building Footprints (ODbL) · Rivers, watershed, gauges', 1)
    # 3. helpers + filter + counters
    for anchor in (DEF_ANCHOR, COUNT_ANCHOR, WET_ANCHOR, END_ANCHOR):
        if html.count(anchor) != 1:
            raise SystemExit(f'{path}: anchor {anchor[:50]!r} found {html.count(anchor)} times (expected 1)')
    html = html.replace(DEF_ANCHOR, HELPERS + '\n' + DEF_ANCHOR, 1)
    html = html.replace(COUNT_ANCHOR, COUNT_ANCHOR + ' let htBDropped = 0; /* ht-buildingsback v1 */', 1)
    html = html.replace(WET_ANCHOR, WET_REPL, 1)
    html = html.replace(END_ANCHOR, END_REPL, 1)
    with open(path, 'w', encoding='utf8') as f:
        f.write(html)
    return 'patched'


def main():
    root = sys.argv[1] if len(sys.argv) > 1 else 'stations'
    pages = sorted(glob.glob(os.path.join(root, 'USGS-*-3d.html')))
    if not pages:
        raise SystemExit(f'no station pages under {root}')
    for p in pages:
        print(patch(p), os.path.basename(p))


if __name__ == '__main__':
    main()
