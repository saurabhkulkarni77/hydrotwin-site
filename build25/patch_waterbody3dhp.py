#!/usr/bin/env python3
"""USGS 3DHP waterbody scenery (ht-waterbody3dhp v1).

User direction (2026-11-10): improve the 3D scenery with the USGS 3D
Hydrography Program (3DHP) waterbody polygons he found through its
ArcGIS REST API; change nothing else.

WHAT: for each station, the baked 3DHP polygons (River/Lake features
with areasqkm > 1 within +-0.03 deg of the gauge; data in
build25/waterbody3dhp_data.py, fetched by gen_waterbody3dhp_data.py)
render as filled waterbody scenery, in the same manner as the
ht-polywater layer: triangulated once, seated on the ribbon's own
water-surface profile near the channel and draped on the terrain
farther out, drawn with a clone of ribbonMat (same colour behaviour),
rebuilt on the same buildRibbon cadence. The only difference is the
seat offset (+0.12 m vs polywater's +0.05 m) so the two polygon layers
never z-fight where they overlap.

SCENERY ONLY: no model, data, panel, chart, bot, layout or text
changes. Stations/polygons with no data keep the existing rendering.

Anchors and chain position mirror patch_polywater.py: this patcher
runs immediately AFTER patch_polywater.py in the dev chain, injects
before window.HT3, and post-checks the same censuses polywater does.
Idempotent: pages already carrying ht-waterbody3dhp v1 are skipped.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from waterbody3dhp_data import WATERBODY3DHP

MARKER = "ht-waterbody3dhp v1"
MARKER_COUNT = 2  # census of the marker inside a patched page

RENDERER = """
// ht-waterbody3dhp v1: baked USGS 3DHP waterbody polygons (River/Lake,
// areasqkm > 1) rendered as filled water scenery, seated on the ribbon's
// water-surface profile like ht-polywater. Data: build25/waterbody3dhp_data.py.
const WATERBODY3DHP = __DATA__;
let htWb3Mesh = null, htWb3Meta = null;
function htWb3Build() {
  if (htWb3Mesh || !WATERBODY3DHP) return;
  const samples = (ribbonPts || []).filter((p) => !p.brk);
  if (!samples.length) return;
  const pos = [], meta = [], idx = [];
  const inBlk = (x, z, m) => x > IX0 - m && x < IX0 + IWM + m && z > IZ0 - m && z < IZ0 + IWM + m;
  for (const poly of WATERBODY3DHP) {
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
  if (!idx.length) { htWb3Mesh = false; return; }
  const g = new THREE.BufferGeometry();
  g.setAttribute('position', new THREE.BufferAttribute(new Float32Array(pos), 3));
  const uv = new Float32Array(pos.length); for (let i = 0; i < pos.length / 3; i++) { uv[2 * i] = pos[3 * i]; uv[2 * i + 1] = pos[3 * i + 2]; }
  g.setAttribute('uv', new THREE.BufferAttribute(uv, 2));
  const nrm = new Float32Array(pos.length); for (let i = 0; i < pos.length / 3; i++) nrm[3 * i + 1] = 1;
  g.setAttribute('normal', new THREE.BufferAttribute(nrm, 3));
  g.setIndex(idx); g.computeBoundingSphere();
  const mat = ribbonMat.clone(); mat.side = THREE.DoubleSide;
  htWb3Mesh = new THREE.Mesh(g, mat); htWb3Mesh.name = 'htWb3Water'; htWb3Mesh.frustumCulled = false; htWb3Mesh.renderOrder = 3;
  htWb3Meta = meta; groundRoot.add(htWb3Mesh);
}
function htWb3Update(dH) {
  if (!htWb3Mesh) htWb3Build();
  if (!htWb3Mesh || htWb3Mesh === false) return;
  htWb3Mesh.material.color.copy(ribbonMat.color);
  const add = Math.max(0.3, dH + 0.3), pa = htWb3Mesh.geometry.attributes.position;
  for (let i = 0; i < htWb3Meta.length; i++) { const m = htWb3Meta[i];
    pa.array[3 * i + 1] = m.near ? Math.max(m.bed + add, m.top + 0.8) - REFE - OUT_DROP + m.taper + 0.12 : m.gy - REFE - 0.22; }
  pa.needsUpdate = true;
}
const htBuildRibbonWb3 = buildRibbon;
buildRibbon = function (dH, w) { htBuildRibbonWb3(dH, w); htWb3Update(dH); };   // ht-waterbody3dhp v1: same rebuild cadence as the ribbon
window.HT3 = {"""

ANCHOR = "window.HT3 = {"


def patch_3d(path: Path) -> str:
    s = path.read_text(encoding="utf-8")
    if MARKER in s:
        return "skip (current)"
    if s.count(ANCHOR) != 1:
        return f"FAIL anchor count {s.count(ANCHOR)} (want 1): window.HT3"
    if "WATERBODY3DHP" in s:
        return "FAIL name collision: WATERBODY3DHP already present"
    if s.count("ht-polywater v1") != 2:
        return f"FAIL polywater census {s.count('ht-polywater v1')} (want 2): run after patch_polywater"
    site = path.name.replace("USGS-", "").replace("-3d.html", "")
    data = WATERBODY3DHP.get(site)
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
