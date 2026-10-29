#!/usr/bin/env python3
"""Smoother rendering + realistic water and imagery (ht-smooth v2).

User asks (2026-10-29): "Make rendering more smooth, use advanced apis
that will give realistic scenes" - and on the first cut: the river
still reads as "a flat, bright cyan strip laid over the terrain" and
the ground as "washed-out gray". Diagnosis on the live dev build
(Dallas 08057000, object-isolation screenshots): the strip is the
flood water surface itself - pale slate colour (#3F6F80) at roughness
0.12 under a bright PMREM sky reflects the sky almost uniformly, its
procedural sine-wave normals are too regular/subtle to break the
mirror up, and its shoreline is a hard stair-stepped alpha edge. The
gray terrain is the flat base colour / fog wash showing while (or
whenever) the satellite mosaic batches fail: mosaic() fired all
n*n tile requests at once with no retry, and whole batches
intermittently failed, leaving black or untextured ground.

SMOOTHNESS (v1, kept)
  1. Water-surface rebuilds throttled to at most one per 50 ms during
     level transitions (was: full 148k-cell flood fill + geometry
     rewrite + ribbon rebuild on nearly every animation frame), and
     updateLevel's per-frame Color allocations hoisted to module temps.
  2. Adaptive pixel ratio: steps render resolution down toward 1 while
     frame times stay > 27 ms, back up toward min(dpr, 2) with
     headroom; XR-safe. Renderer powerPreference 'high-performance'.
  3. Terrain canvas textures use the GPU max anisotropy (up to 16,
     was fixed 8).

REALISM (v2)
  4. Water colour deepened to a blue-green (#175D6E); roughness
     0.12 -> 0.22 and envMapIntensity -> 0.75 so the sky reflection is
     broken up instead of a flat mirror; opacity 0.88 -> 0.95 so the
     surface has body; ripple normal strength up.
  5. The sine-wave ripple texture is replaced by a tileable 512px
     value-noise fBm normal map (natural, non-repeating ripples),
     still scrolled by the render loop as before.
  6. Shoreline blend: WaterGrid.setLevel now also writes a per-vertex
     aEdge factor (share of wet neighbours) and the water shader fades
     alpha toward the waterline (onBeforeCompile), so the surface
     melts into the banks instead of ending in a hard strip edge.
     The out-of-block ribbon (no aEdge attribute) opts out via
     waterMaterial(rep, false) and gets the same colour/roughness.
  7. mosaic() fetches tiles with capped concurrency (64) and one
     retry per tile - imagery and DEM batches now arrive reliably
     instead of intermittently leaving gray/black terrain.
  8. Fog pushed back (9000/75000 -> 13000/85000) and hemisphere light
     0.9 -> 0.8 so mid-ground satellite detail is not washed out.

Deliberately NOT done (evaluated, rejected on this stack):
  - WebGPU renderer: three r160's is experimental, has no WebXR
    support (these pages ship a VR button) and no
    logarithmicDepthBuffer. Stays WebGL2.
  - KTX2/Basis compression: textures are runtime tile mosaics
    composited on canvas; no static asset to transcode.
  - InstancedMesh for buildings: already ONE merged mesh (1 draw call).
  - Shadow maps: ~2 m texels at this block size (blotchy) for a second
    render of the 1M-triangle scene every frame.
  - Higher-zoom outer imagery: quadruples an already failure-prone
    tile batch; reliability fix (7) + fog fix (8) address the actual
    complaint.

Anchors are exact strings of the current baked module (identical in
all 14 3D pages apart from per-station data blobs). Every replacement
is count-checked; any mismatch fails the step without writing.
Idempotent: pages already carrying ht-smooth v2 are skipped. Runs
AFTER patch_riverwater.py in the dev chain; the ht-riverwater v1
census is post-checked so that behaviour cannot be clobbered.
"""
import sys
from pathlib import Path

MARKER = "ht-smooth v2"
MARKER_COUNT = 13  # census of the marker inside a patched page

# ---------------------------------------------------------------- renderer
RENDERER_OLD = """const renderer = new THREE.WebGLRenderer({ antialias: true, logarithmicDepthBuffer: !QUEST });
renderer.setPixelRatio(Math.min(devicePixelRatio, 2)); renderer.setSize(innerWidth, innerHeight); renderer.xr.enabled = true;"""
RENDERER_NEW = """const renderer = new THREE.WebGLRenderer({ antialias: true, logarithmicDepthBuffer: !QUEST, powerPreference: 'high-performance' });
renderer.setPixelRatio(Math.min(devicePixelRatio, 2)); renderer.setSize(innerWidth, innerHeight); renderer.xr.enabled = true;
// ht-smooth v2: adaptive pixel ratio - while frame times stay high, step the
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
TEX_NEW = "function canvasTex(c) { const t = new THREE.CanvasTexture(c); t.colorSpace = THREE.SRGBColorSpace; t.anisotropy = Math.min(16, renderer.capabilities.getMaxAnisotropy()); return t; }   // ht-smooth v2: max anisotropic filtering - satellite detail stays sharp at grazing (riverbank) angles"

# ---------------------------------------------------------------- tile fetching
MOSAIC_OLD = """async function mosaic(urlOf, z, n, x0, y0, size, onTile) {
  const c = document.createElement('canvas'); c.width = c.height = size; const g = c.getContext('2d'); const t = size / n; let done = 0, fail = 0;
  const jobs = [];
  for (let j = 0; j < n; j++) for (let i = 0; i < n; i++) jobs.push(img(urlOf(z, x0 + i, y0 + j)).then((b) => { g.drawImage(b, i * t, j * t, t, t); }).catch(() => { fail++; }).finally(() => { done++; onTile && onTile(done, n * n, fail); }));
  await Promise.all(jobs); return c;
}"""
MOSAIC_NEW = """async function mosaic(urlOf, z, n, x0, y0, size, onTile) {   // ht-smooth v2: capped concurrency (64) + one retry per tile - firing all n*n requests at once intermittently failed whole batches and left gray/black terrain
  const c = document.createElement('canvas'); c.width = c.height = size; const g = c.getContext('2d'); const t = size / n; let done = 0, fail = 0;
  const jobs = [];
  for (let j = 0; j < n; j++) for (let i = 0; i < n; i++) jobs.push([urlOf(z, x0 + i, y0 + j), i * t, j * t]);
  let at = 0;
  const worker = async () => { while (at < jobs.length) { const [u, dx, dy] = jobs[at++];
      let b = null; for (let tryN = 0; tryN < 2 && !b; tryN++) { try { b = await img(u); } catch (e) { /* one retry */ } }
      if (b) g.drawImage(b, dx, dy, t, t); else fail++;
      done++; onTile && onTile(done, n * n, fail); } };
  await Promise.all(Array.from({ length: Math.min(64, jobs.length) }, worker));
  return c;
}"""

# ---------------------------------------------------------------- water look
RIPPLE_OLD = """function rippleCanvas() {   // procedural ripple normal map (no download)
  const n = 256, c = document.createElement('canvas'); c.width = c.height = n; const g = c.getContext('2d'); const im = g.createImageData(n, n);
  const hgt = new Float32Array(n * n); const waves = Array.from({ length: 14 }, (_, k) => [Math.round(Math.cos(k * 2.4) * (2 + (k % 5))), Math.round(Math.sin(k * 2.4) * (2 + (k % 4))), (k * 1.7) % 6.28, 1 / (1 + k * 0.35)]);
  for (let j = 0; j < n; j++) for (let i = 0; i < n; i++) { let s = 0; for (const [a, b, p, w] of waves) s += w * Math.sin((a * i + b * j) * 2 * Math.PI / n + p); hgt[j * n + i] = s; }
  for (let j = 0; j < n; j++) for (let i = 0; i < n; i++) { const dx = hgt[j * n + (i + 1) % n] - hgt[j * n + (i + n - 1) % n], dy = hgt[((j + 1) % n) * n + i] - hgt[((j + n - 1) % n) * n + i];
    const v = new THREE.Vector3(-dx, -dy, 2.2).normalize(); const k = 4 * (j * n + i); im.data[k] = (v.x * 0.5 + 0.5) * 255; im.data[k + 1] = (v.y * 0.5 + 0.5) * 255; im.data[k + 2] = (v.z * 0.5 + 0.5) * 255; im.data[k + 3] = 255; }
  g.putImageData(im, 0, 0); return c;
}"""
RIPPLE_NEW = """function rippleCanvas() {   // ht-smooth v2: tileable value-noise normal map (512px, 4 fBm octaves, fixed seed) - natural, non-repeating water ripple in place of the regular sine waves
  const n = 512, c = document.createElement('canvas'); c.width = c.height = n; const g = c.getContext('2d'); const im = g.createImageData(n, n);
  const hgt = new Float32Array(n * n); let seed = 1234567;
  const rnd = () => (seed = (seed * 1103515245 + 12345) & 0x7FFFFFFF) / 0x7FFFFFFF;
  const oct = [];
  for (const [p, a] of [[6, 0.5], [12, 0.28], [24, 0.16], [48, 0.09]]) { const L = new Float32Array(p * p); for (let i = 0; i < L.length; i++) L[i] = rnd() * 2 - 1; oct.push([L, p, a]); }
  const smp = (L, p, x, y) => { const fx = x / n * p, fy = y / n * p; const x0 = Math.floor(fx) % p, y0 = Math.floor(fy) % p, x1 = (x0 + 1) % p, y1 = (y0 + 1) % p;
    const tx = fx - Math.floor(fx), ty = fy - Math.floor(fy), sx = tx * tx * (3 - 2 * tx), sy = ty * ty * (3 - 2 * ty);
    const v00 = L[y0 * p + x0], v10 = L[y0 * p + x1], v01 = L[y1 * p + x0], v11 = L[y1 * p + x1];
    return (v00 + (v10 - v00) * sx) * (1 - sy) + (v01 + (v11 - v01) * sx) * sy; };
  for (let j = 0; j < n; j++) for (let i = 0; i < n; i++) { let s = 0; for (const [L, p, a] of oct) s += a * smp(L, p, i, j); hgt[j * n + i] = s; }
  for (let j = 0; j < n; j++) for (let i = 0; i < n; i++) { const dx = (hgt[j * n + (i + 1) % n] - hgt[j * n + (i + n - 1) % n]) * 2.2, dy = (hgt[((j + 1) % n) * n + i] - hgt[((j + n - 1) % n) * n + i]) * 2.2;
    const v = new THREE.Vector3(-dx, dy, 1).normalize(); const k = 4 * (j * n + i); im.data[k] = (v.x * 0.5 + 0.5) * 255; im.data[k + 1] = (v.y * 0.5 + 0.5) * 255; im.data[k + 2] = (v.z * 0.5 + 0.5) * 255; im.data[k + 3] = 255; }
  g.putImageData(im, 0, 0); return c;
}"""

WCOLOR_OLD = "const W_CLEAR = new THREE.Color('#3F6F80'), W_MUD = new THREE.Color('#7A6443');"
WCOLOR_NEW = "const W_CLEAR = new THREE.Color('#175D6E'), W_MUD = new THREE.Color('#7A6443');   // ht-smooth v2: deep blue-green water (was pale slate #3F6F80, which mirrored the sky into a flat cyan strip)"

WATER_OLD = """function waterMaterial(rep) {
  return new THREE.MeshStandardMaterial({ color: W_CLEAR.clone(), roughness: 0.12, metalness: 0.05, transparent: true, opacity: 0.88, depthWrite: false,
    normalMap: rippleTex(rep), normalScale: new THREE.Vector2(0.35, 0.35), polygonOffset: true, polygonOffsetFactor: -2, polygonOffsetUnits: -4 });
}"""
WATER_NEW = """function waterMaterial(rep, edge = true) {   // ht-smooth v2: believable water - broken sky reflection (roughness up, env down), stronger noise normals, near-opaque body, plus a shoreline alpha fade so the surface melts into the banks
  const m = new THREE.MeshStandardMaterial({ color: W_CLEAR.clone(), roughness: 0.22, metalness: 0.05, transparent: true, opacity: 0.95, depthWrite: false, envMapIntensity: 0.75,
    normalMap: rippleTex(rep), normalScale: new THREE.Vector2(0.7, 0.7), polygonOffset: true, polygonOffsetFactor: -2, polygonOffsetUnits: -4 });
  if (edge) m.onBeforeCompile = (sh) => {
    sh.vertexShader = 'attribute float aEdge; varying float vEdge;\\n' + sh.vertexShader.replace('#include <begin_vertex>', '#include <begin_vertex>\\n vEdge = aEdge;');
    sh.fragmentShader = 'varying float vEdge;\\n' + sh.fragmentShader.replace('#include <color_fragment>', '#include <color_fragment>\\n diffuseColor.a *= mix(0.08, 1.0, smoothstep(0.05, 0.95, vEdge));');
  };
  return m;
}"""

RIBBON_OLD = "const ribbonMat = waterMaterial(1 / 60);"
RIBBON_NEW = "const ribbonMat = waterMaterial(1 / 60, false);   // ht-smooth v2: ribbon geometry carries no aEdge attribute"

# ---------------------------------------------------------------- shoreline attribute
EDGE_CTOR_OLD = "this.geo.setAttribute('normal', new THREE.BufferAttribute(nor, 3));"
EDGE_CTOR_NEW = "this.geo.setAttribute('normal', new THREE.BufferAttribute(nor, 3)); this.edge = new THREE.BufferAttribute(new Float32Array(n), 1); this.geo.setAttribute('aEdge', this.edge);   // ht-smooth v2: per-vertex shoreline factor feeding the water edge fade"

EDGE_SET_OLD = "pos.needsUpdate = true; idx.needsUpdate = true; this.geo.setDrawRange(0, c); this.wetCount = w;"
EDGE_SET_NEW = """const ea = this.edge.array;   // ht-smooth v2: shoreline factor per vertex = share of wet neighbours (1 = open water, 0 = waterline)
    for (let j = 0; j < N; j++) for (let i = 0; i < N; i++) { const k = j * N + i; if (!wet[k]) { ea[k] = 0; continue; } let s2 = 0, m2 = 0;
      if (i > 0) { s2 += wet[k - 1]; m2++; } if (i < N - 1) { s2 += wet[k + 1]; m2++; } if (j > 0) { s2 += wet[k - N]; m2++; } if (j < N - 1) { s2 += wet[k + N]; m2++; } ea[k] = s2 / m2; }
    this.edge.needsUpdate = true;
    pos.needsUpdate = true; idx.needsUpdate = true; this.geo.setDrawRange(0, c); this.wetCount = w;"""

# ---------------------------------------------------------------- light / fog wash
FOG_OLD = "const FOG = new THREE.Fog('#C4D3E2', 9000, 75000);"
FOG_NEW = "const FOG = new THREE.Fog('#C4D3E2', 13000, 85000);   // ht-smooth v2: fog pushed back so mid-ground satellite detail is not washed out"

HEMI_OLD = "const hemi = new THREE.HemisphereLight('#DCE8F5', '#5A5040', 0.9);"
HEMI_NEW = "const hemi = new THREE.HemisphereLight('#DCE8F5', '#5A5040', 0.8);   // ht-smooth v2: slightly less pale sky fill washing the imagery"

# ---------------------------------------------------------------- level updates
LEVEL_OLD = """function updateLevel(dt) {
  const q = shownQ(), tgt = q == null ? null : dHof(q);
  const t = Math.max(0, Math.min(1, (lq(q || qmin) - 0.55) / 0.45));
  const col = W_CLEAR.clone().lerp(W_MUD, t); if (FC.on) col.lerp(new THREE.Color(COL[S2.model % COL.length]), 0.35);"""
LEVEL_NEW = """const HT_COL = W_CLEAR.clone(), HT_FCC = new THREE.Color(); let htLastSet = null, htSince = 0;   // ht-smooth v2: hoisted per-frame temps + water-rebuild throttle state
function updateLevel(dt) {
  const q = shownQ(), tgt = q == null ? null : dHof(q);
  const t = Math.max(0, Math.min(1, (lq(q || qmin) - 0.55) / 0.45));
  const col = HT_COL.copy(W_CLEAR).lerp(W_MUD, t); if (FC.on) col.lerp(HT_FCC.set(COL[S2.model % COL.length]), 0.35);"""

REBUILD_OLD = """  if (Math.abs(curDH - prev) > 0.004 || levelDirty) {
    W.setLevel(curDH);"""
REBUILD_NEW = """  htSince += dt;   // ht-smooth v2: rebuild the water surface at most every 50 ms while the level moves (was: every frame - each rebuild is a 148k-cell flood fill + full geometry rewrite + ribbon rebuild); always rebuild when dirty and once on the settled value
  if (levelDirty || htLastSet === null || (htSince >= 0.05 && htLastSet !== curDH) || (curDH === tgt && htLastSet !== curDH)) { htSince = 0; htLastSet = curDH;
    W.setLevel(curDH);"""

EDITS = [
    (RENDERER_OLD, RENDERER_NEW),
    (LOOP_OLD, LOOP_NEW),
    (TEX_OLD, TEX_NEW),
    (MOSAIC_OLD, MOSAIC_NEW),
    (RIPPLE_OLD, RIPPLE_NEW),
    (WCOLOR_OLD, WCOLOR_NEW),
    (WATER_OLD, WATER_NEW),
    (RIBBON_OLD, RIBBON_NEW),
    (EDGE_CTOR_OLD, EDGE_CTOR_NEW),
    (EDGE_SET_OLD, EDGE_SET_NEW),
    (FOG_OLD, FOG_NEW),
    (HEMI_OLD, HEMI_NEW),
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
