#!/usr/bin/env python3
"""ht-bridgegap v1: water passes UNDER bridges.

Defect (Saurabh's screenshot, 2026-10-31): the out-of-block river
ribbon is one continuous strip, so where a road or rail bridge crosses
the river the blue water paints straight over the highway deck.

Fix: build25/gen_bridgegap_data.py bakes, per station, the OSM bridge
crossings of the river (build25/bridgegap_data.py: [x, z, halfwidth]
in page coordinates, halfwidth = half the deck width along the river
plus a 3 m margin). This patch injects a small block before the
window.HT3 anchor that wraps buildRibbon: for each call it rebuilds
the ribbon point list with exact gap intervals cut at the crossings —
interpolated boundary cross-sections at each interval edge, the
points inside dropped, and a {brk} break between the two edges, which
is the ribbon builder's own mechanism for separate strips. The
original point list is restored after the build, so every other
consumer of ribbonPts (realriver reseat, polygon water seating) sees
the untouched path, and water levels/seating are unchanged everywhere
outside the gaps. Stations with no crossings get an empty list and
the wrapper passes straight through.

Exposes window.__htBridgeGaps = {crossings, gaps, removedPts} from the
last build for verification.

Anchors are exact strings, count-checked; a mismatch fails the step
without writing. Idempotent: pages carrying the marker are skipped.
Run from the repo root: python3 build25/patch_bridgegap.py
"""
import glob, json, os, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
try:
    from bridgegap_data import HT_BRIDGE_CROSSINGS
except Exception:
    HT_BRIDGE_CROSSINGS = {}

MARKER = 'ht-bridgegap v1'
HT3_ANCHOR = 'window.HT3 = {'

BLOCK = r'''
// ------------------------------------------------------------------ ht-bridgegap v1
// Water passes under bridges: baked OSM bridge crossings of this river
// ([x, z, halfwidth] in page coordinates, from build25/bridgegap_data.py).
// buildRibbon is wrapped so its point list gets an exact gap cut at each
// crossing: interpolated boundary sections at the interval edges, points
// inside dropped, a {brk} break between the edges. The original list is
// restored afterwards; nothing else about the water changes.
const HT_BRIDGES = __HT_BRIDGES_JSON__;
window.__htBridgeGaps = { crossings: HT_BRIDGES.length, gaps: 0, removedPts: 0 };
function htGapPts(pts) {
  const runs = []; let cur = null;
  for (const p of pts) { if (!p || p.brk) { cur = null; continue; } if (!cur) { cur = []; runs.push(cur); } cur.push(p); }
  const out = []; let gaps = 0, removed = 0;
  runs.forEach((run, ri) => {
    if (ri > 0) out.push({ brk: true });
    if (run.length < 2 || !HT_BRIDGES.length) { for (const p of run) out.push(p); return; }
    const S = [0];
    for (let i = 1; i < run.length; i++) S.push(S[i - 1] + Math.hypot(run[i].x - run[i - 1].x, run[i].z - run[i - 1].z));
    const ivs = [];
    for (const c of HT_BRIDGES) {
      let best = null;
      for (let j = 0; j + 1 < run.length; j++) {
        const ax = run[j].x, az = run[j].z, dx = run[j + 1].x - ax, dz = run[j + 1].z - az, L2 = dx * dx + dz * dz || 1;
        let t = ((c[0] - ax) * dx + (c[1] - az) * dz) / L2; t = Math.max(0, Math.min(1, t));
        const d = Math.hypot(c[0] - (ax + dx * t), c[1] - (az + dz * t));
        if (!best || d < best.d) best = { d, s: S[j] + t * Math.sqrt(L2) };
      }
      if (best && best.d < 80) ivs.push([best.s - c[2], best.s + c[2]]);
    }
    if (!ivs.length) { for (const p of run) out.push(p); return; }
    ivs.sort((a, b) => a[0] - b[0]);
    const merged = [ivs[0].slice()];
    for (let m = 1; m < ivs.length; m++) { const last = merged[merged.length - 1];
      if (ivs[m][0] <= last[1]) last[1] = Math.max(last[1], ivs[m][1]); else merged.push(ivs[m].slice()); }
    const nodeAt = (s) => { let j = 0; while (j < run.length - 2 && S[j + 1] < s) j++;
      const seg = S[j + 1] - S[j] || 1, t = (s - S[j]) / seg, A = run[j], B = run[j + 1];
      return { x: A.x + (B.x - A.x) * t, z: A.z + (B.z - A.z) * t, bed: A.bed + (B.bed - A.bed) * t, top: A.top + (B.top - A.top) * t }; };
    let nodes = run.map((p, ix) => ({ s: S[ix], p }));
    for (const iv of merged) { nodes.push({ s: iv[0], p: nodeAt(iv[0]) }); nodes.push({ s: iv[1], p: nodeAt(iv[1]) }); }
    nodes.sort((a, b) => a.s - b.s);
    const dedup = [];
    for (const nd of nodes) { if (dedup.length && Math.abs(nd.s - dedup[dedup.length - 1].s) < 0.01) continue; dedup.push(nd); }
    let pending = null;
    for (const nd of dedup) {
      const inside = merged.some((iv) => nd.s > iv[0] + 0.01 && nd.s < iv[1] - 0.01);
      if (inside) { removed++; continue; }
      if (pending !== null && nd.s >= pending - 0.01) { out.push({ brk: true }); gaps++; pending = null; }
      out.push(nd.p);
      for (const iv of merged) if (Math.abs(nd.s - iv[0]) < 0.01) pending = iv[1];
    }
  });
  window.__htBridgeGaps = { crossings: HT_BRIDGES.length, gaps, removedPts: removed };
  return out;
}
const htBridgeGap0 = buildRibbon;
buildRibbon = function (dH, w) {
  if (!HT_BRIDGES.length || !ribbonPts || !ribbonPts.length) { htBridgeGap0(dH, w); return; }
  const saved = ribbonPts; ribbonPts = htGapPts(saved);
  try { htBridgeGap0(dH, w); } finally { ribbonPts = saved; }
};
'''


def patch(path):
    with open(path, encoding='utf8') as f:
        html = f.read()
    if MARKER in html:
        return 'skip'
    site = os.path.basename(path).split('-')[1]
    crossings = HT_BRIDGE_CROSSINGS.get(site) or []
    if html.count(HT3_ANCHOR) != 1:
        raise SystemExit(f'{path}: HT3 anchor found {html.count(HT3_ANCHOR)} times')
    block = BLOCK.replace('__HT_BRIDGES_JSON__', json.dumps(crossings, separators=(',', ':')))
    html = html.replace(HT3_ANCHOR, block + '\n' + HT3_ANCHOR, 1)
    with open(path, 'w', encoding='utf8') as f:
        f.write(html)
    return f'patched crossings={len(crossings)}'


def main():
    root = sys.argv[1] if len(sys.argv) > 1 else 'stations'
    pages = sorted(glob.glob(os.path.join(root, 'USGS-*-3d.html')))
    if not pages:
        raise SystemExit(f'no station pages under {root}')
    for p in pages:
        print(patch(p), os.path.basename(p))


if __name__ == '__main__':
    main()
