#!/usr/bin/env python3
"""USGS 3DHP waterbody scenery (ht-waterbody3dhp v2).

User direction (2026-11-10): improve the 3D scenery with the USGS 3D
Hydrography Program (3DHP) waterbody polygons he found through its
ArcGIS REST API; change nothing else. v1 rendered the polygons as
filled water in the ht-polywater colour, which is invisible over the
river it traces. v2 renders them the way his standalone River Twin app
renders the same 3DHP data (river-twin/banks.mjs): BANK OUTLINE LINES
only, no fill.

REFERENCE STYLE (banks.mjs + river-twin/data/*-banks.json): the bank
paths are stroked in two passes - a 6 m pass at alpha 0.2 (halo) under
a 2.5 m pass at alpha 1 (lineWidthM = 2.5), round joins and caps - and
the stroke mask blends the surface colour 0.85 toward cyan
rgb(0.025, 0.70, 0.78). This scene has no terrain-shader hook, so the
same look is built as draped triangle strips: a 6 m halo strip at
opacity 0.17 (0.2 x 0.85) under a 2.5 m core strip at opacity 0.85,
both in that cyan, miter-joined (clamped, which reads as round at
these widths), seated on the ribbon's water-surface profile near the
channel and draped on the terrain farther out - the same seating
ht-polywater and v1 used, lifted slightly so the lines sit on top of
the polygon water. Segments crossing the terrain block are skipped,
exactly as v1 skipped in-block triangles: the ribbon owns the river
inside the block. Rebuilt on the same buildRibbon cadence.

SCENERY ONLY: no model, data, panel, chart, bot, layout or text
changes. Stations/polygons with no data keep the existing rendering.

Anchors and chain position mirror patch_polywater.py: this patcher
runs immediately AFTER patch_polywater.py in the dev chain and
injects before window.HT3. Idempotent: pages already carrying
ht-waterbody3dhp v2 are skipped; pages carrying v1 have the v1 block
spliced out and replaced (the bake-back commits mean dev pages carry
v1, so the upgrade path is the normal one).
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from waterbody3dhp_data import WATERBODY3DHP

MARKER = "ht-waterbody3dhp v2"
OLD_MARKER = "ht-waterbody3dhp v1"
MARKER_COUNT = 2  # census of the marker inside a patched page

RENDERER = """
// ht-waterbody3dhp v2: baked USGS 3DHP waterbody polygons (River/Lake,
// areasqkm > 1) drawn as cyan bank outline lines, River Twin style: a
// 2.5 m core line blended 0.85 toward rgb(0.025, 0.70, 0.78) over a 6 m
// halo at 0.2 strength, round joins, no fill. Seated on the ribbon's
// water-surface profile like ht-polywater. Data: build25/waterbody3dhp_data.py.
const WATERBODY3DHP = __DATA__;
const HTWB3_CYAN = new THREE.Color(0.025, 0.70, 0.78);
let htWb3Meta = null, htWb3Strips = null;
function htWb3Build() {
  if (!WATERBODY3DHP) { htWb3Strips = []; return; }
  const samples = (ribbonPts || []).filter((p) => !p.brk);
  if (!samples.length) return;   // ribbon not ready yet; retried on next rebuild
  const inBlk = (x, z, m) => x > IX0 - m && x < IX0 + IWM + m && z > IZ0 - m && z < IZ0 + IWM + m;
  const meta = [];
  const strips = { halo: { pos: [], vmeta: [], idx: [] }, core: { pos: [], vmeta: [], idx: [] } };
  for (const poly of WATERBODY3DHP) {
    for (const ring of poly) {
      let pts = [];
      for (let i = 0; i + 1 < ring.length; i += 2) pts.push([mx(ring[i]), mz(ring[i + 1])]);
      pts = pts.filter((p, i) => i === 0 || (p[0] - pts[i - 1][0]) * (p[0] - pts[i - 1][0]) + (p[1] - pts[i - 1][1]) * (p[1] - pts[i - 1][1]) > 1e-9);
      if (pts.length < 2) continue;
      let closed = false;
      if ((pts[0][0] - pts[pts.length - 1][0]) * (pts[0][0] - pts[pts.length - 1][0]) + (pts[0][1] - pts[pts.length - 1][1]) * (pts[0][1] - pts[pts.length - 1][1]) <= 1e-9) { closed = true; pts.pop(); }
      const n = pts.length;
      if (n < 2 || (closed && n < 3)) continue;
      const pmeta = [], mit = [];
      for (let i = 0; i < n; i++) {
        const x = pts[i][0], z = pts[i][1];
        let bk = -1, bd = Infinity;
        for (let k = 0; k < samples.length; k++) { const dx = samples[k].x - x, dz = samples[k].z - z, d = dx * dx + dz * dz; if (d < bd) { bd = d; bk = k; } }
        const sm = samples[bk], near = bd <= 500 * 500;
        const dOut = Math.max(IX0 - sm.x, sm.x - (IX0 + IWM), IZ0 - sm.z, sm.z - (IZ0 + IWM), 0);
        pmeta.push(meta.length);
        meta.push({ bed: sm.bed, top: sm.top, taper: OUT_DROP * Math.max(0, 1 - dOut / 200), near, gy: near ? 0 : elevGround(x, z) });
        const pa = pts[(i - 1 + n) % n], pb = pts[(i + 1) % n];
        let d1x, d1z, d2x, d2z;
        if (closed) { d1x = x - pa[0]; d1z = z - pa[1]; d2x = pb[0] - x; d2z = pb[1] - z; }
        else if (i === 0) { d1x = d2x = pts[1][0] - x; d1z = d2z = pts[1][1] - z; }
        else if (i === n - 1) { d1x = d2x = x - pts[n - 2][0]; d1z = d2z = z - pts[n - 2][1]; }
        else { d1x = x - pa[0]; d1z = z - pa[1]; d2x = pb[0] - x; d2z = pb[1] - z; }
        const l1 = Math.hypot(d1x, d1z) || 1, l2 = Math.hypot(d2x, d2z) || 1;
        d1x /= l1; d1z /= l1; d2x /= l2; d2z /= l2;
        let mvx = -(d1z + d2z), mvz = d1x + d2x;
        const ml = Math.hypot(mvx, mvz);
        if (ml < 1e-6) { mvx = -d1z; mvz = d1x; } else { mvx /= ml; mvz /= ml; }
        const cosH = Math.max(0.5, mvx * -d1z + mvz * d1x);
        mit.push([mvx, mvz, Math.min(2.0, 1 / cosH)]);
      }
      const segCount = closed ? n : n - 1;
      for (let e = 0; e < segCount; e++) {
        const i2 = (e + 1) % n;
        const ax = pts[e][0], az = pts[e][1], bx = pts[i2][0], bz = pts[i2][1];
        if (inBlk((ax + bx) / 2, (az + bz) / 2, 40)) continue;
        for (const key of ['halo', 'core']) {
          const half = key === 'core' ? 1.25 : 3.0;
          const S = strips[key], base = S.pos.length / 3;
          const eax = mit[e][0] * half * mit[e][2], eaz = mit[e][1] * half * mit[e][2];
          const ebx = mit[i2][0] * half * mit[i2][2], ebz = mit[i2][1] * half * mit[i2][2];
          S.pos.push(ax + eax, 0, az + eaz, ax - eax, 0, az - eaz, bx + ebx, 0, bz + ebz, bx - ebx, 0, bz - ebz);
          S.vmeta.push(pmeta[e], pmeta[e], pmeta[i2], pmeta[i2]);
          S.idx.push(base, base + 1, base + 2, base + 1, base + 3, base + 2);
        }
      }
    }
  }
  htWb3Meta = meta; htWb3Strips = [];
  const mk = (key, opacity, lift, order, name) => {
    const S = strips[key];
    if (!S.pos.length) return;
    const g = new THREE.BufferGeometry();
    g.setAttribute('position', new THREE.BufferAttribute(new Float32Array(S.pos), 3));
    g.setIndex(S.idx); g.computeBoundingSphere();
    const mat = new THREE.MeshBasicMaterial({ color: HTWB3_CYAN, transparent: true, opacity, side: THREE.DoubleSide, depthWrite: false });
    mat.toneMapped = false;
    const mesh = new THREE.Mesh(g, mat);
    mesh.name = name; mesh.frustumCulled = false; mesh.renderOrder = order;
    groundRoot.add(mesh);
    htWb3Strips.push({ mesh, vmeta: S.vmeta, lift });
  };
  mk('halo', 0.17, 0.16, 3, 'htWb3BankHalo');
  mk('core', 0.85, 0.19, 4, 'htWb3BankCore');
}
function htWb3Update(dH) {
  if (htWb3Strips === null) htWb3Build();
  if (!htWb3Strips || !htWb3Strips.length) return;
  const add = Math.max(0.3, dH + 0.3);
  for (const st of htWb3Strips) {
    const pa = st.mesh.geometry.attributes.position;
    for (let v = 0; v < st.vmeta.length; v++) { const m = htWb3Meta[st.vmeta[v]];
      pa.array[3 * v + 1] = (m.near ? Math.max(m.bed + add, m.top + 0.8) - REFE - OUT_DROP + m.taper : m.gy - REFE - 0.34) + st.lift; }
    pa.needsUpdate = true;
  }
}
const htBuildRibbonWb3 = buildRibbon;
buildRibbon = function (dH, w) { htBuildRibbonWb3(dH, w); htWb3Update(dH); };   // ht-waterbody3dhp v2: same rebuild cadence as the ribbon
window.HT3 = {"""

ANCHOR = "window.HT3 = {"


def strip_v1(s: str):
    """Remove the v1 injection (it sits between its banner comment and
    the window.HT3 anchor it ends with). Returns None if the block is
    not found in the expected shape."""
    i = s.find("// " + OLD_MARKER)
    if i < 1 or s[i - 1] != "\n":
        return None
    j = s.find(ANCHOR, i)
    if j < 0:
        return None
    return s[: i - 1] + s[j:]


def patch_3d(path: Path) -> str:
    s = path.read_text(encoding="utf-8")
    if MARKER in s:
        return "skip (current)"
    upgraded = False
    if OLD_MARKER in s:
        if s.count(OLD_MARKER) != MARKER_COUNT:
            return f"FAIL v1 census {s.count(OLD_MARKER)} (want {MARKER_COUNT}) before upgrade"
        s2 = strip_v1(s)
        if s2 is None:
            return "FAIL v1 block not spliceable"
        s = s2
        upgraded = True
        if OLD_MARKER in s or "WATERBODY3DHP" in s:
            return "FAIL v1 residue after splice"
    else:
        if "WATERBODY3DHP" in s:
            return "FAIL name collision: WATERBODY3DHP already present"
        if s.count("ht-polywater v1") != 2:
            return f"FAIL polywater census {s.count('ht-polywater v1')} (want 2): run after patch_polywater"
    if s.count(ANCHOR) != 1:
        return f"FAIL anchor count {s.count(ANCHOR)} (want 1): window.HT3"
    site = path.name.replace("USGS-", "").replace("-3d.html", "")
    data = WATERBODY3DHP.get(site)
    payload = json.dumps(data, separators=(",", ":")) if data else "null"
    s = s.replace(ANCHOR, RENDERER.replace("__DATA__", payload), 1)
    if s.count(MARKER) != MARKER_COUNT:
        return f"FAIL post-check marker count {s.count(MARKER)} (want {MARKER_COUNT})"
    if s.count(OLD_MARKER) != 0:
        return f"FAIL post-check v1 count {s.count(OLD_MARKER)} (want 0)"
    if s.count("htWb3Bank") != 2:
        return f"FAIL post-check bank census {s.count('htWb3Bank')} (want 2)"
    if s.count("ht-riverwater v1") != 5:
        return f"FAIL riverwater census {s.count('ht-riverwater v1')} (want 5)"
    if s.count("ht-smooth v2") != 13:
        return f"FAIL smooth census {s.count('ht-smooth v2')} (want 13)"
    if s.count("ht-flowline v1") != 2:
        return f"FAIL flowline census {s.count('ht-flowline v1')} (want 2)"
    path.write_text(s, encoding="utf-8")
    tag = " [upgraded from v1]" if upgraded else ""
    return f"patched ({len(data) if data else 0} polygons){tag}"


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
