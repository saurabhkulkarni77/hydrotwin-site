#!/usr/bin/env python3
"""ht-flowwater v1: living water on the river layers (DEV only).

The 3D pages already had a procedural ripple normal map on all water,
a discharge-driven colour ramp (clear -> mud) and a stage-driven
level. What they did not have: the ripple pattern scrolled along a
fixed world diagonal on every layer, whatever direction the river
actually flows, and nothing about the surface changed with discharge
except colour.

This patch gives the two RIVER layers (the ribbon and the OSM
polygon water, which share one material family and must stay
consistent at their seam) a flow-aligned animated shader:

  - A per-vertex aFlow attribute carries the local flowline tangent
    (from the ribbon path in buildRibbon; from the nearest path
    sample in htPolyBuild). An onBeforeCompile injection rotates the
    normal-map UV by that tangent in the vertex shader's frame -
    applied to the position part only, via a shader-side scroll
    phase uniform (htOffU) that replaces texture offset for these
    two materials - so the ripple field drifts DOWNSTREAM along the
    channel everywhere, at the same discharge-driven speed the page
    already used (sp = 0.004 + 0.03 * lq(shownQ())).
  - Foam: at high discharge a second sample of the same ripple
    texture mixes whitecap colour into the diffuse, driven by a
    uniform fed from updateLevel's existing turbidity factor t
    (log-flow scaled). The same t also raises normalScale (surface
    chop). Turbidity colour and stage-driven level are the page's
    existing behaviour and are untouched.
  - Both materials register in HT_FLOW_MATS_ and share scroll phase
    (a late-built polygon material adopts the ribbon's phase), so
    the seam between the layers does not show.
  - The bridge gaps are geometry (ht-bridgegap / ht-polygap); a
    normal-map shader cannot repaint them, and does not.

The in-block flood grid keeps the page's original world-space scroll:
inside a flooded cell there is no single flow direction to align to.

Cheap by construction: one normal map (the page's existing ripple
texture), one extra texture sample for foam, no reflections, no
per-frame allocations (uniform values are mutated in place).

Anchors are exact strings of the current baked module, count-checked;
any mismatch fails the step without writing. Idempotent.
"""
import sys
from pathlib import Path

MARKER = "ht-flowwater v1"

BLOCK = """
// ------------------------------------------------------------------ ht-flowwater v1
// Flow-aligned living water for the river layers (ribbon + polygon
// water). aFlow (per-vertex flowline tangent, stored as (fx, -fz))
// rotates the ripple normal-map UV so the pattern drifts downstream
// along the channel; htOffU is the shader-side scroll phase (these
// materials no longer use texture offset); htFoamU whitens the
// surface at high discharge. Speed, colour and level stay driven by
// the selected date's discharge/stage as before.
const HT_FLOW_MATS_ = [];
function htFlowApply_(m) {
  if (!m || HT_FLOW_MATS_.includes(m)) return m;
  m.userData.htU = { value: new THREE.Vector2(0, 0) };
  m.userData.htFoamU = { value: 0 };
  if (HT_FLOW_MATS_.length) m.userData.htU.value.copy(HT_FLOW_MATS_[0].userData.htU.value);
  const prev = m.onBeforeCompile;
  m.onBeforeCompile = (sh) => {
    if (prev) prev(sh);
    sh.uniforms.htOffU = m.userData.htU;
    sh.uniforms.htFoamU = m.userData.htFoamU;
    sh.vertexShader = 'attribute vec2 aFlow; varying vec2 vFlow;\\n' + sh.vertexShader.replace('#include <begin_vertex>', '#include <begin_vertex>\\n\\tvFlow = aFlow;');
    sh.fragmentShader = ('uniform vec2 htOffU; uniform float htFoamU; varying vec2 vFlow;\\n' + sh.fragmentShader)
      .replace('#include <normal_fragment_maps>', [
        'vec2 htFuv = mat2(vFlow.x, vFlow.y, -vFlow.y, vFlow.x) * vNormalMapUv + htOffU;',
        'vec3 htMapN = texture2D( normalMap, htFuv ).xyz * 2.0 - 1.0;',
        'htMapN.xy *= normalScale;',
        'normal = normalize( getTangentFrame( - vViewPosition, normal, htFuv ) * htMapN );',
        'float htFoamM = texture2D( normalMap, htFuv * 2.7 + vec2(0.37, 0.11) ).g;',
        'diffuseColor.rgb = mix( diffuseColor.rgb, vec3( 0.93, 0.96, 0.97 ), htFoamU * smoothstep( 0.60, 0.92, htFoamM ) );'
      ].join('\\n'));
  };
  m.customProgramCacheKey = () => 'htflow1';
  HT_FLOW_MATS_.push(m);
  return m;
}

"""

BLOCK_ANCHOR = "function waterMaterial(rep, edge = true) {"

EDITS = [
    # apply the shader to the ribbon material at creation
    ("const ribbonMat = waterMaterial(1 / 60, false);",
     "const ribbonMat = waterMaterial(1 / 60, false); htFlowApply_(ribbonMat);   // ht-flowwater v1", 1),
    # ribbon geometry carries the flow tangent per vertex
    ("const add = Math.max(0.3, dH + 0.3), w = width / 2, p = [], uv = [], ix = []; let n = 0, prev = null;",
     "const add = Math.max(0.3, dH + 0.3), w = width / 2, p = [], uv = [], ix = [], fl = []; let n = 0, prev = null;   // ht-flowwater v1", 1),
    ("uv.push(c.x - dz * w, c.z + dx * w, c.x + dz * w, c.z - dx * w);",
     "uv.push(c.x - dz * w, c.z + dx * w, c.x + dz * w, c.z - dx * w); fl.push(dx, -dz, dx, -dz);   // ht-flowwater v1", 1),
    ("g.setAttribute('uv', new THREE.Float32BufferAttribute(uv, 2));",
     "g.setAttribute('uv', new THREE.Float32BufferAttribute(uv, 2));\n  g.setAttribute('aFlow', new THREE.Float32BufferAttribute(fl, 2));   // ht-flowwater v1", 1),
    # polygon water: same attribute (nearest path sample's tangent), same shader
    ("const pos = [], meta = [], idx = [];",
     "const pos = [], meta = [], idx = [], fl = [];   // ht-flowwater v1", 1),
    ("pos.push(v.x, 0, v.y);",
     "pos.push(v.x, 0, v.y); { const sA = samples[Math.max(0, bk - 1)], sB = samples[Math.min(samples.length - 1, bk + 1)]; let fx2 = sB.x - sA.x, fz2 = sB.z - sA.z; const fl2 = Math.hypot(fx2, fz2) || 1; fl.push(fx2 / fl2, -fz2 / fl2); }   // ht-flowwater v1", 1),
    ("g.setAttribute('uv', new THREE.BufferAttribute(uv, 2));\n  const nrm = new Float32Array(pos.length);",
     "g.setAttribute('uv', new THREE.BufferAttribute(uv, 2));\n  g.setAttribute('aFlow', new THREE.BufferAttribute(new Float32Array(fl), 2));   // ht-flowwater v1\n  const nrm = new Float32Array(pos.length);", 1),
    ("const mat = ribbonMat.clone(); mat.side = THREE.DoubleSide;",
     "const mat = ribbonMat.clone(); mat.side = THREE.DoubleSide; htFlowApply_(mat);   // ht-flowwater v1", 1),
    # scroll: river layers advance their shader phase; grid layers keep texture offset
    ("for (const m of [tWaterMat, gWaterMat, ribbonMat]) { m.normalMap.offset.x -= dt * sp; m.normalMap.offset.y += dt * sp * 0.35; }",
     "for (const m of [tWaterMat, gWaterMat]) { m.normalMap.offset.x -= dt * sp; m.normalMap.offset.y += dt * sp * 0.35; }\n  for (const m of HT_FLOW_MATS_) if (m.userData.htU) m.userData.htU.value.x -= dt * sp;   // ht-flowwater v1: river layers scroll along the flowline, same discharge-driven speed", 1),
    # foam + chop follow the turbidity factor in updateLevel
    ("for (const m of [tWaterMat, gWaterMat, ribbonMat]) m.color.copy(col);",
     "for (const m of [tWaterMat, gWaterMat, ribbonMat]) m.color.copy(col);\n  for (const m of HT_FLOW_MATS_) { if (m.userData.htFoamU) m.userData.htFoamU.value = t * 0.85; if (m.normalScale) m.normalScale.setScalar(0.7 + 0.55 * t); }   // ht-flowwater v1: foam + surface chop rise with discharge", 1),
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
    if s.count(BLOCK_ANCHOR) != 1:
        return f"FAIL block anchor count {s.count(BLOCK_ANCHOR)} (want 1)"
    for old, new, want in EDITS:
        got = s.count(old)
        if got != want:
            return f"FAIL anchor count {got} (want {want}): {old[:60]}..."
    s = s.replace(BLOCK_ANCHOR, BLOCK + BLOCK_ANCHOR, 1)
    for old, new, want in EDITS:
        s = s.replace(old, new)
    for mk, want in PRESERVE.items():
        got = s.count(mk)
        if got != want:
            return f"FAIL preserve census {mk}: {got} (want {want})"
    if s.count(MARKER) < 8:
        return f"FAIL post-check marker count {s.count(MARKER)} (want >= 8)"
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
            continue
        r = patch_3d(p)
        print(f"{p.name}: {r}")
        if r.startswith("FAIL"):
            bad += 1
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
