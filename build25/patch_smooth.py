#!/usr/bin/env python3
"""Smoother rendering + more realistic water (ht-smooth v1).

User ask (2026-10-29): "Make rendering more smooth, use advanced apis
that will give realistic scenes." Scope confirmed by the user: dev only.

Both problem areas live in the shared 3D scene module (classic pages
have no 3D scene at all). Baseline measured live on dev (Dallas
08057000, headless Chromium / SwiftShader, window.HT3 diagnostics +
rAF sampling + setLevel call counters):

SMOOTHNESS
  1. Water-surface rebuilds dominate interaction cost. During a date
     change / level transition, updateLevel() called WaterGrid.setLevel
     on (nearly) every animation frame: each call is a full flood BFS
     over the 385x385 grid, a rewrite of all 148k water vertices, a
     full index rebuild, two GPU buffer re-uploads (~5 MB), plus a
     buildRibbon() that allocates a brand-new BufferGeometry. Dozens of
     those per transition = the visible hitch when changing the date or
     pressing play.
     Fix: rebuild at most every 50 ms of accumulated frame time while
     the level is moving (plus an immediate rebuild when dirty / on the
     final settled value). At 20 rebuilds/s the water rise is visually
     identical; the skipped calls were pure waste.
  2. updateLevel() also allocated two THREE.Color objects per frame
     (a clone + a fresh Color inside the FC branch). Hoisted to module
     temps - same values, no per-frame garbage.
  3. Retina-class displays render at devicePixelRatio up to 2 = 4x the
     fragments of CSS size, the single biggest steady-state cost on
     laptops. Added an adaptive pixel-ratio controller: it watches an
     EMA of frame times and steps the ratio down toward 1 while frames
     stay > 27 ms, and back up toward the cap when there is headroom
     (< 12.5 ms). Bounds [1, min(dpr, 2)], 0.25 steps, checked every 45
     frames, disabled while an XR session is presenting.
  4. Renderer created with powerPreference 'high-performance' so
     dual-GPU laptops pick the discrete GPU for the canvas.

REALISM
  5. Terrain/layer canvas textures used a fixed anisotropy of 8. They
     now use the renderer's true maximum (up to 16): satellite detail
     stays sharp at the grazing angles of the riverbank / low-drone
     views instead of smearing.
  6. Water material: roughness 0.12 -> 0.07 and envMapIntensity 1.35
     so the existing PMREM sky environment reflects more strongly on
     the water (fresnel does the rest), and the ripple normal strength
     0.35 -> 0.45 for a livelier surface. Colour, opacity and the
     ht-riverwater behaviour are untouched.

Deliberately NOT done (evaluated, rejected on this stack):
  - WebGPU renderer: three r160's WebGPURenderer is experimental and
    has no WebXR support; these pages ship a VR button + XR controls,
    and use logarithmicDepthBuffer, which it also lacks. Stays WebGL2.
  - KTX2/Basis texture compression: the scene's textures are runtime
    tile mosaics fetched from Esri/AWS endpoints and composited on
    canvas - there is no static texture asset to transcode.
  - InstancedMesh for buildings: loadBuildings already merges all
    footprints into ONE mesh (1 draw call); instancing cannot beat it.
  - Shadow maps: a 2048px shadow camera over the 4.1 km block gives
    ~2 m texels (blotchy, not realistic) and costs a second render of
    the 1M-triangle scene every frame. Fog + PMREM + ACES already
    carry the depth cues; not worth the smoothness budget.

Anchors are exact strings of the current baked module (identical in
all 14 3D pages apart from per-station data blobs). Every replacement
is count-checked; any mismatch fails the step without writing.
Idempotent: pages already carrying the marker are skipped. Runs AFTER
patch_riverwater.py in the dev chain and does not alter any of its
behaviour (skirt notches, ribbon lift, building water exclusion).
"""
import sys
from pathlib import Path

MARKER = "ht-smooth v1"
MARKER_COUNT = 5  # census of the marker inside a patched page

# ---------------------------------------------------------------- renderer
RENDERER_OLD = """const renderer = new THREE.WebGLRenderer({ antialias: true, logarithmicDepthBuffer: !QUEST });
renderer.setPixelRatio(Math.min(devicePixelRatio, 2)); renderer.setSize(innerWidth, innerHeight); renderer.xr.enabled = true;"""
RENDERER_NEW = """const renderer = new THREE.WebGLRenderer({ antialias: true, logarithmicDepthBuffer: !QUEST, powerPreference: 'high-performance' });
renderer.setPixelRatio(Math.min(devicePixelRatio, 2)); renderer.setSize(innerWidth, innerHeight); renderer.xr.enabled = true;
// ht-smooth v1: adaptive pixel ratio - while frame times stay high, step the
// render resolution down toward 1x so orbiting stays fluid; step back up when
// there is headroom. Bounds [1, min(dpr, 2)], 0.25 steps every 45 frames,
// disabled while an XR session is presenting.
let htPR = Math.min(devicePixelRatio || 1, 2), htEma = 16, htTick = 0;
function htAdapt(dt) { if (renderer.xr.isPresenting) return; htEma += (Math.min(dt, 0.1) * 1000 - htEma) * 0.05; if (++htTick < 45) return; htTick = 0;
  const cap = Math.min(devicePixelRatio || 1, 2);
  if (htEma > 27 && htPR > 1) { htPR = Math.max(1, htPR - 0.25); renderer.setPixelRatio(htPR); }
  else if (htEma < 12.5 && htPR < cap) { htPR = Math.min(cap, htPR + 0.25); renderer.setPixelRatio(htPR); } }"""

LOOP_OLD = """renderer.setAnimationLoop(() => {
  const dt = Math.min(0.1, clock.getDelta());"""
LOOP_NEW = """renderer.setAnimationLoop(() => {
  const dt = Math.min(0.1, clock.getDelta());
  htAdapt(dt);"""

# ---------------------------------------------------------------- textures
TEX_OLD = "function canvasTex(c) { const t = new THREE.CanvasTexture(c); t.colorSpace = THREE.SRGBColorSpace; t.anisotropy = 8; return t; }"
TEX_NEW = "function canvasTex(c) { const t = new THREE.CanvasTexture(c); t.colorSpace = THREE.SRGBColorSpace; t.anisotropy = Math.min(16, renderer.capabilities.getMaxAnisotropy()); return t; }   // ht-smooth v1: max anisotropic filtering - satellite detail stays sharp at grazing (riverbank) angles"

# ---------------------------------------------------------------- water look
WATER_OLD = """function waterMaterial(rep) {
  return new THREE.MeshStandardMaterial({ color: W_CLEAR.clone(), roughness: 0.12, metalness: 0.05, transparent: true, opacity: 0.88, depthWrite: false,
    normalMap: rippleTex(rep), normalScale: new THREE.Vector2(0.35, 0.35), polygonOffset: true, polygonOffsetFactor: -2, polygonOffsetUnits: -4 });
}"""
WATER_NEW = """function waterMaterial(rep) {   // ht-smooth v1: glossier surface - lower roughness + stronger PMREM sky reflection + firmer ripple normals, for a more realistic water read
  return new THREE.MeshStandardMaterial({ color: W_CLEAR.clone(), roughness: 0.07, metalness: 0.05, transparent: true, opacity: 0.88, depthWrite: false, envMapIntensity: 1.35,
    normalMap: rippleTex(rep), normalScale: new THREE.Vector2(0.45, 0.45), polygonOffset: true, polygonOffsetFactor: -2, polygonOffsetUnits: -4 });
}"""

# ---------------------------------------------------------------- level updates
LEVEL_OLD = """function updateLevel(dt) {
  const q = shownQ(), tgt = q == null ? null : dHof(q);
  const t = Math.max(0, Math.min(1, (lq(q || qmin) - 0.55) / 0.45));
  const col = W_CLEAR.clone().lerp(W_MUD, t); if (FC.on) col.lerp(new THREE.Color(COL[S2.model % COL.length]), 0.35);"""
LEVEL_NEW = """const HT_COL = W_CLEAR.clone(), HT_FCC = new THREE.Color(); let htLastSet = null, htSince = 0;   // ht-smooth v1: hoisted per-frame temps + water-rebuild throttle state
function updateLevel(dt) {
  const q = shownQ(), tgt = q == null ? null : dHof(q);
  const t = Math.max(0, Math.min(1, (lq(q || qmin) - 0.55) / 0.45));
  const col = HT_COL.copy(W_CLEAR).lerp(W_MUD, t); if (FC.on) col.lerp(HT_FCC.set(COL[S2.model % COL.length]), 0.35);"""

REBUILD_OLD = """  if (Math.abs(curDH - prev) > 0.004 || levelDirty) {
    W.setLevel(curDH);"""
REBUILD_NEW = """  htSince += dt;   // ht-smooth v1: rebuild the water surface at most every 50 ms while the level moves (was: every frame - each rebuild is a 148k-cell flood fill + full geometry rewrite + ribbon rebuild); always rebuild when dirty and once on the settled value
  if (levelDirty || htLastSet === null || (htSince >= 0.05 && htLastSet !== curDH) || (curDH === tgt && htLastSet !== curDH)) { htSince = 0; htLastSet = curDH;
    W.setLevel(curDH);"""

EDITS = [
    (RENDERER_OLD, RENDERER_NEW),
    (LOOP_OLD, LOOP_NEW),
    (TEX_OLD, TEX_NEW),
    (WATER_OLD, WATER_NEW),
    (LEVEL_OLD, LEVEL_NEW),
    (REBUILD_OLD, REBUILD_NEW),
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
    # ht-riverwater v1 must survive untouched
    if s.count("ht-riverwater v1") != 5:
        return f"FAIL riverwater census {s.count('ht-riverwater v1')} (want 5)"
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
            continue  # classic pages have no 3D scene
        r = patch_3d(p)
        print(f"{p.name}: {r}")
        if r.startswith("FAIL"):
            bad += 1
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
