#!/usr/bin/env python3
"""Baked water polygons for the out-of-block river (ht-polywater v1).

User direction (2026-10-30): "do it for all stations" - roll the
polygon-water approach from the API evaluation out to every station.

WHY: outside the inner block, the river is a ribbon strip whose width
is GUESSED from the flood fill (wet area / path length) and whose banks
are a constant-width offset of the NLDI centre-line. Real rivers have
mapped banks. The evaluation found two polygon sources:
  - NHDPlus HR, layer NHDArea (FTYPE 460 StreamRiver): authoritative,
    but its MapServer spatial queries repeatedly timed out (>280 s)
    from the build environment, so it could not be pulled here.
  - OpenStreetMap natural=water multipolygons: verified in hand at
    Dallas (Trinity = one closed 8,739-vertex ring, 9.49 km2) and now
    pulled for all 14 stations. This patcher bakes OSM.
Per-station data lives in build25/polywater_data.py (polygons
>= 15,000 m2, Douglas-Peucker 4 m, 6 dp coords; ODbL).

WHAT THE RENDERER DOES (injected before window.HT3):
  - Triangulates the baked polygons once (THREE.ShapeUtils, holes
    supported) in ground coordinates.
  - Seats every vertex on the SAME water-surface profile the ribbon
    uses (per-sample bed/top from ribbonPts, incl. the ht-riverwater
    seam taper), +0.05 m, so polygon and ribbon agree at the block
    edge and the seam stays ~0.08 m. Vertices > 500 m from the path
    (ponds, lakes) drape on the terrain instead - they can sit in
    their basin or stay buried, never float.
  - Drops triangles inside the inner block: the flood grid owns the
    block (it is flood-true; a bank polygon would clip real flood
    extent on high-flow days - at Dallas the pilot showed polygon
    and fill already agree in-block anyway).
  - Renders with a clone of ribbonMat (DoubleSide; colour re-synced
    from ribbonMat on every rebuild, so the mud/forecast colour
    behaviour is identical), and rebuilds heights whenever
    buildRibbon runs (hooked), i.e. on every level change.
  - Stations/polygons with no data simply keep the ribbon alone.

Anchors are exact strings of the current baked module (identical in
all 14 3D pages apart from per-station data blobs). Every replacement
is count-checked; any mismatch fails the step without writing.
Idempotent: pages already carrying ht-polywater v1 are skipped.
Runs AFTER patch_flowline.py in the dev chain; the ht-riverwater,
ht-smooth and ht-flowline censuses are post-checked.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from polywater_data import POLYWATER

MARKER = "ht-polywater v1"
MARKER_COUNT = 2  # census of the marker inside a patched page

RENDERER = """
// ht-polywater v1: baked OSM water polygons for the out-of-block reach,
// seated on the ribbon's own water-surface profile (true mapped banks
// instead of a guessed constant width). Data: build25/polywater_data.py.
const POLYWATER = __DATA__;
let htPolyMesh = null, htPolyMeta = null;
function htPolyBuild() {
  if (htPolyMesh || !POLYWATER) return;
  const samples = (ribbonPts || []).filter((p) => !p.brk);
  if (!samples.length) return;
  const pos = [], meta = [], idx = [];
  const inBlk = (x, z, m) => x > IX0 - m && x < IX0 + IWM + m && z > IZ0 - m && z < IZ0 + IWM + m;
  for (const poly of POLYWATER) {
    const rings = poly.map((ring) => { const v = []; for (let i = 0; i + 1 < ring.length; i += 2) v.push(new THREE.Vector2(mx(ring[i]), mz(ring[i + 1]))); return v; });
    if (!rings.length || rings[0].length < 3) continue;
    let tris; try { tris = THREE.ShapeUtils.triangulateShape(rings[0], rings.slice(1)); } catch (e) { continue; }
    const all = rings[0].concat(...rings.slice(1));
    const base = pos.length / 3;
    for (const v of all) {
      let bk = -1, bd = Infinity;
      for (let k = 0; k < samples.length; k++) { const dx = samples[k].x - v.x, dz = samples[k].z - v.y, d = dx * dx + dz * dz; if (d < bd) { bd = d; bk = k; } }
      const sm = samples[bk], near = bd <= 500 * 500;
      const dOut = Math.max(IX0 - sm.x, sm.x - (IX0 + IWM), IZ0 - sm.z, sm.z - (IZ0 + IWM), 0);
      meta.push({ bed: sm.bed, top: sm.top, taper: OUT_DROP * Math.max(0, 1 - dOut / 200), near, gy: near ? 0 : elevGround(v.x, v.y) });
      pos.push(v.x, 0, v.y);
    }
    for (const t of tris) {
      const cx = (all[t[0]].x + all[t[1]].x + all[t[2]].x) / 3, cz = (all[t[0]].y + all[t[1]].y + all[t[2]].y) / 3;
      if (inBlk(cx, cz, 40)) continue;
      idx.push(base + t[0], base + t[1], base + t[2]);
    }
  }
  if (!idx.length) { htPolyMesh = false; return; }
  const g = new THREE.BufferGeometry();
  g.setAttribute('position', new THREE.BufferAttribute(new Float32Array(pos), 3));
  const uv = new Float32Array(pos.length); for (let i = 0; i < pos.length / 3; i++) { uv[2 * i] = pos[3 * i]; uv[2 * i + 1] = pos[3 * i + 2]; }
  g.setAttribute('uv', new THREE.BufferAttribute(uv, 2));
  const nrm = new Float32Array(pos.length); for (let i = 0; i < pos.length / 3; i++) nrm[3 * i + 1] = 1;
  g.setAttribute('normal', new THREE.BufferAttribute(nrm, 3));
  g.setIndex(idx); g.computeBoundingSphere();
  const mat = ribbonMat.clone(); mat.side = THREE.DoubleSide;
  htPolyMesh = new THREE.Mesh(g, mat); htPolyMesh.name = 'htPolyWater'; htPolyMesh.frustumCulled = false; htPolyMesh.renderOrder = 2;
  htPolyMeta = meta; groundRoot.add(htPolyMesh);
}
function htPolyUpdate(dH) {
  if (!htPolyMesh) htPolyBuild();
  if (!htPolyMesh || htPolyMesh === false) return;
  htPolyMesh.material.color.copy(ribbonMat.color);
  const add = Math.max(0.3, dH + 0.3), pa = htPolyMesh.geometry.attributes.position;
  for (let i = 0; i < htPolyMeta.length; i++) { const m = htPolyMeta[i];
    pa.array[3 * i + 1] = m.near ? Math.max(m.bed + add, m.top + 0.8) - REFE - OUT_DROP + m.taper + 0.05 : m.gy - REFE - 0.3; }
  pa.needsUpdate = true;
}
const htBuildRibbon0 = buildRibbon;
buildRibbon = function (dH, w) { htBuildRibbon0(dH, w); htPolyUpdate(dH); };   // ht-polywater v1: keep the polygon water on the same rebuild cadence as the ribbon
window.HT3 = {"""

ANCHOR = "window.HT3 = {"


def patch_3d(path: Path) -> str:
    s = path.read_text(encoding="utf-8")
    if MARKER in s:
        return "skip (current)"
    if s.count(ANCHOR) != 1:
        return f"FAIL anchor count {s.count(ANCHOR)} (want 1): window.HT3"
    if "POLYWATER" in s:
        return "FAIL name collision: POLYWATER already present"
    site = path.name.replace("USGS-", "").replace("-3d.html", "")
    data = POLYWATER.get(site)
    payload = json.dumps(data, separators=(",", ":")) if data else "null"
    s = s.replace(ANCHOR, RENDERER.replace("__DATA__", payload), 1)
    if s.count(MARKER) != MARKER_COUNT:
        return f"FAIL post-check marker count {s.count(MARKER)} (want {MARKER_COUNT})"
    if s.count("ht-riverwater v1") != 5:
        return f"FAIL riverwater census {s.count('ht-riverwater v1')} (want 5)"
    if s.count("ht-smooth v2") != 13:
        return f"FAIL smooth census {s.count('ht-smooth v2')} (want 13)"
    if s.count("ht-flowline v1") != 2:
        return f"FAIL flowline census {s.count('ht-flowline v1')} (want 2)"
    path.write_text(s, encoding="utf-8")
    return f"patched ({len(data) if data else 0} polygons)"


def main():
    root = Path("stations")
    files = sorted(root.glob("USGS-*.html"))
    if not files:
        print("no station pages found under stations/", file=sys.stderr)
        return 1
    bad = 0
    for p in files:
        if not p.name.endswith("-3d.html"):
            continue  # classic pages have no 3D scene
        r = patch_3d(p)
        print(f"{p.name}: {r}")
        if r.startswith("FAIL"):
            bad += 1
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
