#!/usr/bin/env python3
"""ht-nlcdtrees v1 + ht-levees v1: ground-view 3D context (DEV only).

Buildings are deliberately NOT touched: they were removed from the
3D pages earlier today at the user's order (ht-nobuildings v1) and
whether they return is the user's pending decision. This patch adds
the other context the reviewer asked for:

TREES - instanced low-poly trees (one InstancedMesh of trunks + one
of canopies, canopy shape from the station's existing BIOME type)
scattered from NLCD 2021 Tree Canopy Cover data baked by
build25/gen_trees_data.py (canopy >= 25% pixels over the inner
block, density rising with canopy). At build time in the scene any
baked point that lands on water at median flow (the page's own
flood fill), on steep ground, or outside the inner block is dropped,
so a tree can never stand in the river. Placement runs once, lazily,
after the ground flood exists; state on window.__htTrees.

LEVEES - for stations where the USACE National Levee Database
carries embankment lines (baked by build25/gen_levees_data.py; the
Dallas Trinity system included), each line is draped on the terrain
as a low trapezoidal embankment: 6 m crest, 3.4 m true height (a
built structure - like the staff gauge it is NOT scaled by
HT_EXAG_G; its base follows the scaled terrain), 5 m side slopes.
One merged geometry, one material. State on window.__htLevees.

No 3D bridge decks are built: the crossings live in the satellite
imagery and in HT_BRIDGES, and a deck mesh would fight the
ht-bridgegap / ht-polygap system, which cuts the water UNDER the
deck line in the imagery - a real deck would need its own gap and
occlusion logic. Noted as deliberately out of scope.

Anchors are exact strings, count-checked; failures write nothing.
Idempotent. Preservation censuses post-checked.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
try:
    from trees_data import HT_TREES
except Exception:
    HT_TREES = {}
try:
    from levees_data import HT_LEVEES
except Exception:
    HT_LEVEES = {}

MARKER = "ht-nlcdtrees v1"

BLOCK = """
// ------------------------------------------------------------------ ht-nlcdtrees v1 + ht-levees v1
// Ground-view context from real data: instanced trees scattered from
// NLCD 2021 Tree Canopy Cover (baked by build25/gen_trees_data.py;
// points on water at median flow, on steep ground or outside the
// inner block are dropped at build) and USACE National Levee
// Database embankment lines draped as low embankments (baked by
// build25/gen_levees_data.py). Buildings
// stay removed per the user's standing order - their return is his call.
const HT_TREES = __TREES__;
const HT_LEVEES = __LEVEES__;
let htGroundCtxBuilt_ = false;
function htBuildGroundContext_() {
  if (htGroundCtxBuilt_) return;
  const F = gWater && gWater.flood;
  if (!F) return;   // retry on a later level update, once the flood exists
  htGroundCtxBuilt_ = true;
  try {
    if (HT_TREES && HT_TREES.length) {
      const N = NI, wet = new Uint8Array(N * N);
      const med = flowsSorted[flowsSorted.length >> 1];
      F.fill(dHof(med) || 0, wet);
      const isWet = (x, z) => { const i = Math.round((x - IX0) / IWM * (N - 1)), j = Math.round((z - IZ0) / IWM * (N - 1)); return i >= 0 && j >= 0 && i < N && j < N && !!wet[j * N + i]; };
      const type = (typeof BIOME !== 'undefined' && BIOME.trees) || 'deciduous';
      const trunkG = new THREE.CylinderGeometry(0.14, 0.24, 2.2, 5);
      const canG = (type === 'evergreen' || type === 'cypress') ? new THREE.ConeGeometry(1.5, 4.2, 7) : new THREE.SphereGeometry(1.6, 7, 5);
      const trunkM = new THREE.MeshStandardMaterial({ color: '#5A4232', roughness: 1 });
      const canM = new THREE.MeshStandardMaterial({ color: type === 'evergreen' ? '#2E5A2E' : '#4A7A3A', roughness: 1 });
      const pts = [];
      for (const t of HT_TREES) {
        const x = t[0], z = t[1];
        if (!inInner(x, z, 4) || isWet(x, z)) continue;
        const e = elevGround(x, z);
        if (Math.abs(elevGround(x + 9, z) - e) + Math.abs(elevGround(x, z + 9) - e) > 7) continue;
        pts.push(t); if (pts.length >= 1600) break;
      }
      if (pts.length) {
        const trunks = new THREE.InstancedMesh(trunkG, trunkM, pts.length);
        const cans = new THREE.InstancedMesh(canG, canM, pts.length);
        const d = new THREE.Object3D();
        pts.forEach((t, i2) => {
          const x = t[0], z = t[1], sc = t[2], y = (elevGround(x, z) - REFE) * HT_EXAG_G;
          d.position.set(x, y + 1.0 * sc, z); d.scale.setScalar(sc);
          d.rotation.set(0, ((x * 12.9898 + z * 78.233) % 6.283 + 6.283) % 6.283, 0); d.updateMatrix();
          trunks.setMatrixAt(i2, d.matrix);
          d.position.y = y + 3.1 * sc; d.updateMatrix();
          cans.setMatrixAt(i2, d.matrix);
        });
        trunks.name = 'htTreesTrunks'; cans.name = 'htTreesCanopy';
        groundRoot.add(trunks, cans);
      }
      window.__htTrees = { baked: HT_TREES.length, placed: pts.length };
    }
    if (HT_LEVEES && HT_LEVEES.length) {
      const posA = [], idxA = []; let nSeg = 0;
      const HW = 3.0, TH = 3.4, SW = 5.0;   // crest half-width, true height, slope run (metres)
      for (const line of HT_LEVEES) {
        if (!line || line.length < 2) continue;
        let prev = null;
        for (let i2 = 0; i2 < line.length; i2++) {
          const x = line[i2][0], z = line[i2][1];
          const pa = line[Math.max(0, i2 - 1)], pb = line[Math.min(line.length - 1, i2 + 1)];
          let dx = pb[0] - pa[0], dz = pb[1] - pa[1]; const L = Math.hypot(dx, dz) || 1; dx /= L; dz /= L;
          const px = -dz, pz = dx;
          const yB = (elevGround(x, z) - REFE) * HT_EXAG_G;
          const row = [];
          for (const [off, top] of [[-(HW + SW), 0], [-HW, 1], [HW, 1], [HW + SW, 0]]) {
            const gx = x + px * off, gz = z + pz * off;
            row.push(posA.length / 3);
            posA.push(gx, top ? yB + TH : (elevGround(gx, gz) - REFE) * HT_EXAG_G - 0.4, gz);
          }
          if (prev) { for (let q = 0; q < 3; q++) { const a = prev[q], b = prev[q + 1], c2 = row[q], d2 = row[q + 1]; idxA.push(a, c2, b, b, c2, d2); } nSeg++; }
          prev = row;
        }
      }
      if (idxA.length) {
        const g = new THREE.BufferGeometry();
        g.setAttribute('position', new THREE.Float32BufferAttribute(posA, 3));
        g.setIndex(idxA); g.computeVertexNormals();
        const m = new THREE.Mesh(g, new THREE.MeshStandardMaterial({ color: '#7C6B4A', roughness: 1 }));
        m.name = 'htLevees'; groundRoot.add(m);
        window.__htLevees = { lines: HT_LEVEES.length, segments: nSeg };
      }
    }
  } catch (e) { window.__htTrees = { error: String((e && e.message) || e) }; }
}

"""

HT3_ANCHOR = "window.HT3 = {"

EDITS = [
    ("    W.setLevel(curDH);",
     "    W.setLevel(curDH);\n    htBuildGroundContext_();   // ht-nlcdtrees v1", 1),
    ("function placeViews() {",
     "function placeViews() {\n  htBuildGroundContext_();   // ht-nlcdtrees v1", 1),
]

PRESERVE = {
    "ht-bridgegap v1": 1,
    "ht-polygap v1": 1,
    "ht-polywater v1": 2,
    "ht-nobuildings v1": 2,
    "ht-ribbonshade v1": 2,
    "ht-riverwater v1": 5,
    "ht-smooth v2": 13,
    "ht-flowline v1": 2,
}


def patch_3d(path: Path) -> str:
    s = path.read_text(encoding="utf-8")
    if MARKER in s:
        return "skip (current)"
    site = path.name.replace("USGS-", "").replace("-3d.html", "")
    if s.count(HT3_ANCHOR) != 1:
        return f"FAIL HT3 anchor count {s.count(HT3_ANCHOR)} (want 1)"
    for old, new, want in EDITS:
        got = s.count(old)
        if got != want:
            return f"FAIL anchor count {got} (want {want}): {old[:60]}..."
    trees = HT_TREES.get(site) or []
    levees = HT_LEVEES.get(site) or []
    block = BLOCK.replace("__TREES__", json.dumps(trees, separators=(",", ":")))
    block = block.replace("__LEVEES__", json.dumps(levees, separators=(",", ":")))
    s = s.replace(HT3_ANCHOR, block + HT3_ANCHOR, 1)
    for old, new, want in EDITS:
        s = s.replace(old, new)
    for mk, want in PRESERVE.items():
        got = s.count(mk)
        if got != want:
            return f"FAIL preserve census {mk}: {got} (want {want})"
    if s.count(MARKER) < 3 or s.count("ht-levees v1") < 1:
        return f"FAIL post-check marker counts trees={s.count(MARKER)} levees={s.count('ht-levees v1')}"
    path.write_text(s, encoding="utf-8")
    return f"patched ({len(trees)} trees baked, {len(levees)} levee lines)"


def main():
    root = Path("stations")
    files = sorted(root.glob("USGS-*.html"))
    if not files:
        print("no station pages found under stations/", file=sys.stderr)
        return 1
    bad = 0
    for p in files:
        if not p.name.endswith("-3d.html"):
            continue
        r = patch_3d(p)
        print(f"{p.name}: {r}")
        if r.startswith("FAIL"):
            bad += 1
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
