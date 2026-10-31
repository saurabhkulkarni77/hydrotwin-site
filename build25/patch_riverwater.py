#!/usr/bin/env python3
"""River continuity + no buildings in the water (ht-riverwater v1).

User report (2026-10-29, photo of the Dallas Trinity 3D page):
"Fix rendering of river, it gets cut off [on] all stations, also
buildings are getting rendered inside water, fix it everywhere."
Scope confirmed by the user: dev only.

Both bugs live in the shared 3D scene module (classic pages have no
3D scene at all). Verified live on dev (Dallas 08057000, headless
Chromium, window.HT3 diagnostics):

BUG 1 - the river "gets cut off" at the edge of the detailed block.
  Inside the 4.1 km detailed block the water is the flood-grid surface;
  outside it, a flat ribbon strip. Two defects at the seam:
  (a) buildInner wraps the block in a continuous 60 m "skirt" curtain.
      The river's water surface runs into that curtain at both block
      crossings and stops; from low angles (riverbank / low drone -
      the user's photo) the river visibly runs into a wall.
  (b) The ribbon's y subtracts OUT_DROP (the 3 m the outer terrain is
      dropped by), so outside the block the river resumes ~3 m BELOW
      the in-block water surface (measured 2.50 / 2.69 m at the two
      Dallas crossings), and its first point can be ~180 m past the
      edge (ribbon samples were taken every 120 m).
  Fix: (a) htCutSkirt() - called once from initGroundFlood (the first
      moment the DEM, PATHM and the flood all exist) - rebuilds the
      skirt index without the quads whose top edge is low bank within
      55 m of the river path, opening a notch at each crossing.
      (b) buildRibbon lifts each point by up to OUT_DROP, tapering
      with distance outside the block over 200 m, so the strip meets
      the in-block water level at the seam; ribbon points are now
      taken every 60 m instead of every 120 m.

BUG 2 - buildings render inside the water.
  loadBuildings extruded every Microsoft footprint inside the block;
  the only filter was the block boundary - no water test anywhere.
  Dallas: 559 building vertices land in cells that are wet at the
  median-flow level (464 at the load-day level); several whole
  buildings stand in the channel.
  Fix: loadBuildings waits (bounded, 30 s) for the ground flood, then
  tests each footprint against the flood's wet cells at the
  median-flow level - the same water definition the scene renders
  (placeViews uses the same median fill to find a bank spot). A
  footprint whose centroid is wet, or with >= 4 wet boundary samples,
  or >= 30% wet samples, is skipped. If the rivers failed to load the
  filter fails open (previous behaviour) rather than dropping all
  buildings.

Anchors are exact strings of the current baked module (identical in
all 14 3D pages apart from per-station data blobs). Every replacement
is count-checked; any mismatch fails the step without writing.
Idempotent: pages already carrying the marker are skipped.
"""
import sys
from pathlib import Path

MARKER = "ht-riverwater v1"
MARKER_COUNT = 5  # docstring-free census of the marker inside a patched page

# ---------------------------------------------------------------- bug 1a
SKIRT_OLD = """  const sg = new THREE.BufferGeometry(); sg.setAttribute('position', new THREE.Float32BufferAttribute(p, 3)); sg.setIndex(ix); sg.computeVertexNormals();
  groundRoot.add(new THREE.Mesh(sg, new THREE.MeshStandardMaterial({ color: '#6B5E4C', roughness: 1, side: THREE.DoubleSide })));"""
SKIRT_NEW = """  const sg = new THREE.BufferGeometry(); sg.setAttribute('position', new THREE.Float32BufferAttribute(p, 3)); sg.setIndex(ix); sg.computeVertexNormals();
  const skm = new THREE.Mesh(sg, new THREE.MeshStandardMaterial({ color: '#6B5E4C', roughness: 1, side: THREE.DoubleSide })); skm.name = 'htSkirt'; groundRoot.add(skm);"""

CUTSKIRT_FN = """function htCutSkirt() {   // ht-riverwater v1: open the block skirt where the river crosses it, so the water flows through instead of running into the curtain
  const sk = groundRoot.children.find((m) => m.name === 'htSkirt'); if (!sk || !PATHM || !gWater.flood) return;
  const F = gWater.flood, med = flowsSorted[flowsSorted.length >> 1], wet = new Uint8Array(NI * NI); F.fill(dHof(med) || 0, wet);
  const pos = sk.geometry.attributes.position, nv = pos.count / 2, ix = [];
  const dPath = (x, z) => { let bd = Infinity; for (let k = 1; k < PATHM.length; k++) { const [ax, az] = PATHM[k - 1], [bx, bz] = PATHM[k];
    const dx = bx - ax, dz = bz - az, L2 = dx * dx + dz * dz || 1; let t = ((x - ax) * dx + (z - az) * dz) / L2; t = Math.max(0, Math.min(1, t));
    const d = Math.hypot(x - (ax + dx * t), z - (az + dz * t)); if (d < bd) bd = d; } return bd; };
  for (let n = 1; n < nv; n++) { const a = 2 * (n - 1);
    const mxp = (pos.getX(a) + pos.getX(a + 2)) / 2, mzp = (pos.getZ(a) + pos.getZ(a + 2)) / 2, topY = Math.min(pos.getY(a), pos.getY(a + 2));
    const ci = Math.max(0, Math.min(NI - 1, Math.round((mxp - IX0) / (IWM / (NI - 1))))), cj = Math.max(0, Math.min(NI - 1, Math.round((mzp - IZ0) / (IWM / (NI - 1)))));
    const wse = F.wse[cj * NI + ci];
    if (!(dPath(mxp, mzp) < 55 && !isNaN(wse) && topY < wse - REFE + 9)) ix.push(a, a + 1, a + 2, a + 1, a + 3, a + 2); }
  sk.geometry.setIndex(ix);
  if (curDH != null) gWater.setLevel(curDH);
}
function initGroundFlood() {"""
GROUND_OLD = "function initGroundFlood() {"
GROUND_NEW = CUTSKIRT_FN

FLOOD_OLD = "  gWater.flood = new Flood(NI, iElev, IWM / (NI - 1), seeds, 2500); gWater.pathLen = inside * 4; floodsReady.ground = true;"
FLOOD_NEW = FLOOD_OLD + " htCutSkirt();"

# ---------------------------------------------------------------- bug 1b
SAMPLE_OLD = "  smp.forEach(([x, z], n) => { if (n % 2) return; const ok = !inInner(x, z, -20) && Math.abs(x) < WM / 2 && Math.abs(z) < WM / 2 && bed[n] != null;"
SAMPLE_NEW = "  smp.forEach(([x, z], n) => { const ok = !inInner(x, z, -20) && Math.abs(x) < WM / 2 && Math.abs(z) < WM / 2 && bed[n] != null;   /* ht-riverwater v1: ribbon point every 60 m (was every 120 m) so the strip starts closer to the block edge */"

RIBBON_OLD = "    const y = Math.max(c.bed + add, c.top + 0.8) - REFE - OUT_DROP;"
RIBBON_NEW = """    const dOut = Math.max(IX0 - c.x, c.x - (IX0 + IWM), IZ0 - c.z, c.z - (IZ0 + IWM), 0);   // ht-riverwater v1: lift the ribbon by up to OUT_DROP near the block (tapering over 200 m) so it meets the in-block water at the seam
    const y = Math.max(c.bed + add, c.top + 0.8) - REFE - OUT_DROP + OUT_DROP * Math.max(0, 1 - dOut / 200);"""

# ---------------------------------------------------------------- bug 2
BLDSETUP_OLD = "  const geos = []; const tmp = new THREE.Color(); let count = 0;"
BLDSETUP_NEW = """  // ht-riverwater v1: never render a building in the river. Wait (bounded)
  // for the ground flood, then test footprints against its wet cells at the
  // median-flow level - the same water the scene itself renders. If the
  // rivers failed to load, wetRef stays null and nothing is filtered.
  for (let w8 = 0; w8 < 60 && !floodsReady.ground; w8++) await new Promise((r) => setTimeout(r, 500));
  let wetRef = null; const cellM = IWM / (NI - 1);
  if (floodsReady.ground && gWater.flood) { wetRef = new Uint8Array(NI * NI); const med = flowsSorted[flowsSorted.length >> 1]; gWater.flood.fill(dHof(med) || 0, wetRef); if (curDH != null) gWater.setLevel(curDH); }
  const inWater = (pts) => { if (!wetRef) return false;
    const smp = []; let cx = 0, cz = 0;
    for (let k = 0; k < pts.length; k++) { const [x1, z1] = pts[k], [x2, z2] = pts[(k + 1) % pts.length]; cx += x1; cz += z1; smp.push([x1, z1]);
      const L = Math.hypot(x2 - x1, z2 - z1), n = Math.floor(L / 10); for (let s2 = 1; s2 < n; s2++) smp.push([x1 + (x2 - x1) * s2 / n, z1 + (z2 - z1) * s2 / n]); }
    smp.push([cx / pts.length, cz / pts.length]);
    let wet = 0;
    for (const [x, z] of smp) { const i = Math.round((x - IX0) / cellM), jj = Math.round((z - IZ0) / cellM); if (i < 0 || jj < 0 || i >= NI || jj >= NI) continue;
      if (wetRef[jj * NI + i]) wet++; }
    const cc = smp[smp.length - 1], ci = Math.round((cc[0] - IX0) / cellM), cj = Math.round((cc[1] - IZ0) / cellM);
    const centroidWet = ci >= 0 && cj >= 0 && ci < NI && cj < NI && !!wetRef[cj * NI + ci];
    return centroidWet || wet >= 4 || wet >= Math.ceil(smp.length * 0.3); };
  const geos = []; const tmp = new THREE.Color(); let count = 0;"""

BLDFILTER_OLD = "    if (pts.length < 3 || !pts.every(([x, z]) => inInner(x, z, 2))) continue;"
BLDFILTER_NEW = BLDFILTER_OLD + "\n    if (inWater(pts)) continue;   // ht-riverwater v1"

EDITS = [
    (SKIRT_OLD, SKIRT_NEW),
    (GROUND_OLD, GROUND_NEW),
    (FLOOD_OLD, FLOOD_NEW),
    (SAMPLE_OLD, SAMPLE_NEW),
    (RIBBON_OLD, RIBBON_NEW),
    (BLDSETUP_OLD, BLDSETUP_NEW),
    (BLDFILTER_OLD, BLDFILTER_NEW),
]


def patch_3d(path: Path) -> str:
    s = path.read_text(encoding="utf-8")
    if MARKER in s:
        return "skip (current)"
    for old, _new in EDITS:
        if s.count(old) != 1:
            return f"FAIL anchor count {s.count(old)} (want 1): {old[:60]!r}"
    for old, new in EDITS:
        s = s.replace(old, new, 1)
    if s.count(MARKER) != MARKER_COUNT:
        return f"FAIL post-check marker count {s.count(MARKER)} (want {MARKER_COUNT})"
    path.write_text(s, encoding="utf-8")
    return "patched"


def main():
    root = Path("stations")
    files = sorted(root.glob("USGS-*.html"))
    if not files:
        print("no station pages found under stations/", file=sys.stderr)
        return 1
    bad = 0
    for p in files:
        if not p.name.endswith("-3d.html"):
            continue  # classic pages have no 3D scene; both bugs are 3D-only
        r = patch_3d(p)
        print(f"{p.name}: {r}")
        if r.startswith("FAIL"):
            bad += 1
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
