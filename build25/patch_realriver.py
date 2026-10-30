#!/usr/bin/env python3
"""ht-realriver v1: seat the river on USGS 3DEP elevation instead of the
coarse terrarium/SRTM terrain.

Two parts, both baked at build time into build25/realriver_data.py and
build25/realdem_data.py:

1. Bed profile + channel carve (all stations with an NLDI path). The baked
   profile samples the 3DEP DEM (1 m LiDAR mosaic where the catalog has it)
   along the NLDI navigation path every 60 m. At runtime the patch wraps
   initTableFlood: each ribbon point's bed is replaced by the baked thalweg
   elevation and its top is capped at bed + 0.6 m, so the water surface is
   derived from the real channel instead of the 160 m terrain grid. It also
   carves the outer terrain mesh: vertices within ~110 m of the path are
   lowered to at most bed - 0.3 m (fading out to 320 m), so the coarse mesh
   stops bridging over the channel and burying the water (measured on the
   live Dallas page before this fix: 51% of ribbon vertices and 54% of
   near-path polygon vertices were below the outer mesh surface). The OSM
   polygon layer reads the same ribbon points, so it is reseated too.

2. Inner-block DEM swap (stations whose inner block has LiDAR-grade 3DEP
   coverage, baked as a terrarium-encoded PNG): the inner detail-elevation
   mosaic call is rerouted to a baked canvas decoded from the 1 m DEM, so
   the in-block terrain - and with it the flood grid - follows the real
   channel. Any failure falls back to the original tile mosaic.

Idempotent: pages already carrying the marker are skipped. Fails loudly if
an anchor is missing so template drift surfaces in CI.
"""
import glob, json, os, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
try:
    from realriver_data import HT_RIVER_PROFILES
except Exception:
    HT_RIVER_PROFILES = {}
try:
    from realdem_data import HT_DEM15
except Exception:
    HT_DEM15 = {}

MARKER = 'ht-realriver v1'
HT3_ANCHOR = 'window.HT3 = {'
CALL = "const ic = await mosaic(URL_T, ZI, NI_T, ITX0, ITY0, IW, (d, n) => setLoad('detail elevation', d < n ? `${d}/${n}` : 'ok'));"
REPL = ("const ic = await (window.__htDEM15 ? await __htDEM15() : null) || "
        "await mosaic(URL_T, ZI, NI_T, ITX0, ITY0, IW, (d, n) => setLoad('detail elevation', d < n ? `${d}/${n}` : 'ok')); "
        "/* ht-realriver v1: inner DEM from baked 3DEP 1 m data when available */")

BLOCK = r'''
// ------------------------------------------------------------------ ht-realriver v1
// River seated on USGS 3DEP elevation: baked thalweg bed profile along the
// NLDI path (samples: [x, z, bedMetres] in page coordinates), a channel carve
// of the coarse outer mesh, and (where baked) a 1 m LiDAR inner-block DEM.
const HT_RIVER = __HT_RIVER_JSON__;
window.__htRiver = { matched: 0, of: 0, carved: 0, maxCut: 0, dem: HT_RIVER.dem15 ? '3dep-lidar' : 'terrarium', src: HT_RIVER.src };
if (HT_RIVER.dem15) window.__htDEM15 = async () => {
  try {
    const im = await new Promise((res, rej) => { const i2 = new Image(); i2.onload = () => res(i2); i2.onerror = rej; i2.src = 'data:image/png;base64,' + HT_RIVER.dem15; });
    const c = document.createElement('canvas'); c.width = c.height = IW;
    c.getContext('2d').drawImage(im, 0, 0, IW, IW);
    setLoad('detail elevation', 'ok');
    return c;
  } catch (e) { return null; }
};
let htNearFn = null;
function htRiverNear() {
  if (htNearFn) return htNearFn;
  const cell = 160, map = new Map();
  HT_RIVER.samples.forEach((s) => { const k = Math.floor(s[0] / cell) + ':' + Math.floor(s[1] / cell);
    if (!map.has(k)) map.set(k, []); map.get(k).push(s); });
  htNearFn = (x, z, r) => { let best = null, bd = r * r;
    const cx = Math.floor(x / cell), cz = Math.floor(z / cell), rad = Math.ceil(r / cell);
    for (let a = -rad; a <= rad; a++) for (let b = -rad; b <= rad; b++) { const lst = map.get((cx + a) + ':' + (cz + b)); if (!lst) continue;
      for (const s of lst) { const dx = s[0] - x, dz = s[1] - z, d = dx * dx + dz * dz; if (d < bd) { bd = d; best = s; } } }
    return best; };
  return htNearFn;
}
function htReseat() {
  if (!ribbonPts || !ribbonPts.length || !HT_RIVER.samples.length) return;
  const near = htRiverNear(); let m = 0, of = 0;
  for (const p of ribbonPts) { if (!p || p.brk) continue; of++;
    const s = near(p.x, p.z, 110); if (!s) continue;
    p.bed = s[2]; p.top = Math.min(p.top, s[2] + 0.6); m++; }
  window.__htRiver.matched = m; window.__htRiver.of = of;
}
function htCarve() {
  if (!ribbonPts || !ribbonPts.length || !HT_RIVER.samples.length || !oGeo || !elev) return;
  const near = htRiverNear();
  const pos = oGeo.attributes.position; let carved = 0, maxCut = 0;
  for (let k = 0; k < pos.count; k++) { const y = pos.getY(k); if (y < -300) continue;
    const x = pos.getX(k), z = pos.getZ(k);
    const s = near(x, z, 330); if (!s) continue;
    const d = Math.hypot(s[0] - x, s[1] - z);
    const target = s[2] - REFE - OUT_DROP - 0.3;
    let t = target;
    if (d > 110) t = target + (y - target) * Math.min(1, (d - 110) / 220);
    if (t < y - 30) t = y - 30;  // never gouge more than 30 m (canyon walls)
    if (t < y - 0.05) { pos.setY(k, t); carved++; if (y - t > maxCut) maxCut = y - t; } }
  if (carved) { pos.needsUpdate = true; oGeo.computeVertexNormals(); oGeo.computeBoundingSphere(); }
  window.__htRiver.carved = carved; window.__htRiver.maxCut = +maxCut.toFixed(2);
}
const htTFR = initTableFlood;
initTableFlood = function () { htTFR(); htReseat(); htCarve(); };
const htBOR = buildOuter;
buildOuter = function () { htBOR(); htCarve(); };
'''


def patch(path):
    with open(path, encoding='utf8') as f:
        html = f.read()
    if MARKER in html:
        return 'skip'
    site = os.path.basename(path).split('-')[1]
    prof = HT_RIVER_PROFILES.get(site) or {'samples': [], 'src': 'none'}
    data = {'samples': prof.get('samples') or [], 'src': prof.get('src') or 'none',
            'dem15': HT_DEM15.get(site)}
    if html.count(HT3_ANCHOR) != 1:
        raise SystemExit(f'{path}: HT3 anchor found {html.count(HT3_ANCHOR)} times')
    if html.count(CALL) != 1:
        raise SystemExit(f'{path}: inner-DEM mosaic anchor found {html.count(CALL)} times (expected 1)')
    block = BLOCK.replace('__HT_RIVER_JSON__', json.dumps(data, separators=(',', ':')))
    html = html.replace(HT3_ANCHOR, block + '\n' + HT3_ANCHOR, 1)
    html = html.replace(CALL, REPL, 1)
    with open(path, 'w', encoding='utf8') as f:
        f.write(html)
    return f"patched samples={len(data['samples'])} dem15={'yes' if data['dem15'] else 'no'}"


def main():
    root = sys.argv[1] if len(sys.argv) > 1 else 'stations'
    pages = sorted(glob.glob(os.path.join(root, 'USGS-*-3d.html')))
    if not pages:
        raise SystemExit(f'no station pages under {root}')
    for p in pages:
        print(patch(p), os.path.basename(p))


if __name__ == '__main__':
    main()
