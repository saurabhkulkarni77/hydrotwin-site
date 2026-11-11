#!/usr/bin/env python3
"""Photorealistic 3D Tiles scenery (ht-tiles3d v1).

User direction (2026-11-10): make the dev 3D pages' scenery look
like Akilan's standalone River Twin app ("VR project next steps"),
keeping every panel and everything else the same, dev only.

The River Twin app (river-twin/world.mjs) renders Google
Photorealistic 3D Tiles through Cesium Ion asset 2275207 with
3d-tiles-renderer's TilesRenderer + CesiumIonAuthPlugin, a vendored
three (r185) bundle, an East/Up/South local frame at the station
(river-twin/geodesy.mjs localFrame), desktop LRU budgets of
450-1600 tiles / 256-512 MB, errorTarget 16, and an attribution
footer built from tiles.getAttributions() prefixed "Basemap:
Google Maps" with the Google logo. This patch mirrors that setup
inside the existing station pages, using the app's own vendored
files copied byte-identical into vendor3d/ (dependencies.js,
three.module.min.js, three.core.min.js, draco/, google logo,
licenses).

CREDENTIAL: a Cesium Ion token issued for this project (username
SaurabhKulkarni, free Community tier, token name "hydrotwin-dev",
asset access restricted to asset 2275207 only) is embedded in the
injected block, exactly where CesiumIonAuthPlugin expects it.
It is deliberately NOT printed by this script.

INTEGRATION DESIGN (two adaptations, everything else mirrors the
reference app):
1. Vertical datum stitch. Page ground-view y is "elevation minus
   river level at the gauge" (orthometric metres, y = e - REFE),
   while tiles geometry sits on WGS84 ellipsoid heights. The
   local frame's up translation is therefore lowered by
   REFE + N, with N the station's GEOID18 geoid height (NGS Geoid
   Height Service, fetched 2026-11-10; table below). Horizontal
   axes are already identical conventions (x east, z south,
   metres): the page's Web Mercator local projection and the
   ECEF tangent frame agree to ~2 m at the detailed-block edge
   and exactly at the gauge.
2. Renderer isolation. The vendored bundle imports symbols that
   do not exist in the page's three (r160), so it runs on its
   own r185 three behind a scoped importmap ("scopes" entry for
   ../vendor3d/), and the tiles live in their own scene drawn by
   the page renderer as a first pass (depth written) under the
   untouched page scene. The page's three, panels, charts,
   helper, models and text are not modified; the only page edit
   outside the injected block is the importmap scopes entry.
   Any failure (no WebGL, bundle load error, tiles error before
   first model, Quest headset UA) leaves the page exactly as it
   was: the legacy DEM scenery only steps aside per frame once
   the first tile model has actually arrived.

KEPT (information-carrying, never hidden): the water grid, the
ribbon, the out-of-block water surface, the 3DHP bank outline
lines, gauge staff/labels and all panels. HIDDEN once tiles are
active (pure scenery, replaced by the photorealistic tiles):
inner/outer DEM terrain meshes, the terrain skirt and the OSM
building extrusions.

Anchors and chain position mirror patch_waterbody3dhp.py: this
patcher runs LAST among the station-page patches in the dev
chain and injects before window.HT3. Idempotent: pages already
carrying ht-tiles3d v1 are skipped.
"""
import json
import re
import sys
from pathlib import Path

MARKER = "ht-tiles3d v1"
MARKER_COUNT = 2  # census of the marker inside a patched page

# Cesium Ion token "hydrotwin-dev" (asset 2275207 only). Embedded
# into the injected block; never printed.
TOKEN = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJub25jZSI6IkRDR0VvTktoakhSeTRNZ28iLCJqdGkiOiIzNTI5MDQ0YS0zMmQyLTRhZDItYTA2NC1jN2VkYzc0MTY1ODIiLCJpZCI6NTQ2ODU5LCJzdWIiOiJTYXVyYWJoS3Vsa2FybmkiLCJpc3MiOiJodHRwczovL2FwaS5jZXNpdW0uY29tIiwiYXVkIjoiaHlkcm90d2luLWRldiIsImlhdCI6MTc5NDM1NDg5OH0.FL2gKrRS4bV8J8i_O7zgiTMKVl_Gpe1cviLT-vTHssI"

# GEOID18 geoid heights N (metres) at each gauge, NGS Geoid Height
# Service, 2026-11-10. Page y (orthometric, e - REFE) relates to
# tiles ellipsoid height h by y = h - N - REFE.
GEOID_N = {
    "01463500": -33.2,
    "01646500": -31.881,
    "02320500": -27.856,
    "03294500": -33.361,
    "05331000": -27.437,
    "06214500": -13.517,
    "06934500": -31.928,
    "07374000": -27.068,
    "08057000": -26.572,
    "08158000": -26.005,
    "08313000": -19.41,
    "09380000": -23.459,
    "11447650": -31.019,
    "14105700": -21.498,
}

EXPECTED_IMPORTS = {
    "three": "https://cdn.jsdelivr.net/npm/three@0.160.0/build/three.module.js",
    "three/addons/": "https://cdn.jsdelivr.net/npm/three@0.160.0/examples/jsm/",
}
SCOPE_KEY = "../vendor3d/"
SCOPE_MAP = {"three": "../vendor3d/three.module.min.js"}

RENDERER = """
// ht-tiles3d v1: Google Photorealistic 3D Tiles (Cesium Ion asset
// 2275207) as the ground view scenery base. Mirrors the River Twin
// app (createImagery in river-twin/world.mjs): TilesRenderer with
// CesiumIonAuthPlugin, GLTFExtensionsPlugin (DRACO) and
// TileCompressionPlugin from the vendored bundle in ../vendor3d/,
// errorTarget 16, desktop LRU budgets, and the app's attribution
// footer. Placement uses the app's East/Up/South local frame at
// the gauge (river-twin/geodesy.mjs localFrame) with the up
// translation lowered by REFE + this station's GEOID18 geoid
// height, because page y is orthometric elevation above the
// river level at the gauge while tile heights are WGS84
// ellipsoid heights. The bundle runs on its own vendored three
// behind a scoped importmap, so the tiles live in their own
// scene, drawn by the page renderer as a first pass under the
// page scene. Legacy DEM scenery steps aside only once the
// first tile model has arrived; any failure leaves the page
// exactly as it was. Water, ribbon, bank lines, gauge, labels
// and panels are never touched.
const HT_T3_TOKEN = '__TOKEN__';
const HT_T3_GEOID_N = __GEOID__;
const htTiles = { v: 'ht-tiles3d v1', active: false, failed: false, models: 0, errors: 0, started: Date.now() };
window.__htTiles3D = htTiles;
let htT3Tiles = null, htT3Scene = null, htT3Cam = null, htT3ResV = null;
function htT3Ecef(latitude, longitude, height = 0) {
  const p = latitude * Math.PI / 180, l = longitude * Math.PI / 180, a = 6378137, e2 = 6.69437999014e-3, n = a / Math.sqrt(1 - e2 * Math.sin(p) ** 2);
  return [(n + height) * Math.cos(p) * Math.cos(l), (n + height) * Math.cos(p) * Math.sin(l), (n * (1 - e2) + height) * Math.sin(p)];
}
function htT3LocalFrame(latitude, longitude, height = 0) {
  const p = latitude * Math.PI / 180, l = longitude * Math.PI / 180, origin = htT3Ecef(latitude, longitude, height);
  const east = [-Math.sin(l), Math.cos(l), 0], up = [Math.cos(p) * Math.cos(l), Math.cos(p) * Math.sin(l), Math.sin(p)], south = [Math.sin(p) * Math.cos(l), Math.sin(p) * Math.sin(l), -Math.cos(p)];
  const dot = (a, b) => a.reduce((v, x, i) => v + x * b[i], 0);
  return [...east, -dot(east, origin), ...up, -dot(up, origin), ...south, -dot(south, origin), 0, 0, 0, 1];
}
let htT3Foot = null, htT3FootText = '', htT3FootAt = 0;
function htT3FooterShow() {
  if (htT3Foot) return;
  const d = document.createElement('div');
  d.id = 'htTiles3dCredits';
  d.style.cssText = 'position:fixed;left:10px;bottom:8px;z-index:40;max-width:74vw;padding:4px 9px;background:rgba(7,25,32,.88);color:#e4f1ee;font:11px/1.5 system-ui,Arial,sans-serif;border-radius:6px;display:none;align-items:center;gap:7px;pointer-events:none';
  d.innerHTML = '<img src="../vendor3d/google-maps-white.png" alt="Google Maps" style="height:14px;display:none"><span></span>';
  document.body.appendChild(d);
  htT3Foot = d;
}
function htT3Credits() {
  const clean = (v) => new DOMParser().parseFromString(String(v), 'text/html').body.textContent.trim();
  const values = htT3Tiles.getAttributions().filter((i) => i.type !== 'image').map((i) => clean(i.value)).filter(Boolean);
  return ['Basemap: Google Maps', ...[...new Set(values)].sort(), '3D tiles access: Cesium ion', 'Hydrology: USGS / supplied HydroTwin forecasts'].join(' · ');
}
function htT3FooterTick() {
  if (!htT3Foot) return;
  const now = performance.now();
  if (now - htT3FootAt < 600) return;
  htT3FootAt = now;
  let text = '';
  try { text = htT3Credits(); } catch (e) { return; }
  if (text !== htT3FootText) { htT3FootText = text; htT3Foot.querySelector('span').textContent = text; htT3Foot.querySelector('img').style.display = 'block'; }
  htT3Foot.style.display = 'flex';
}
let htT3Hidden = [];
function htT3HideLegacy() {
  for (const ch of groundRoot.children) {
    if (ch === ribbon || ch === gLabels || ch === gaugeMark) continue;
    if (ch === gWater.mesh || ch === gWater.lines.fc || ch === gWater.lines.obs) continue;
    if (typeof htWb3Strips !== 'undefined' && htWb3Strips && htWb3Strips.some((st) => st.mesh === ch)) continue;
    if (ch.name === 'htPolyWater' || (ch.name && ch.name.startsWith('htWb3'))) continue;
    if (ch.visible) { ch.visible = false; htT3Hidden.push(ch); }
  }
}
function htT3RestoreLegacy() {
  for (const ch of htT3Hidden) ch.visible = true;
  htT3Hidden = [];
}
function htT3Update(cam) {
  const m = htT3LocalFrame(D.lat, D.lon);
  m[7] -= (REFE + HT_T3_GEOID_N);
  htT3Tiles.group.matrix.set(...m);
  htT3Tiles.group.matrixWorldNeedsUpdate = true;
  // The tiles scene is not rendered until the first model arrives,
  // so refresh the world matrix by hand: the renderer culls the
  // ECEF bounding volumes against it on every update.
  htT3Tiles.group.updateWorldMatrix(true, false);
  if (htT3Cam !== cam) { if (htT3Cam) htT3Tiles.deleteCamera(htT3Cam); htT3Tiles.setCamera(cam); htT3Cam = cam; }
  renderer.getDrawingBufferSize(htT3ResV);
  htT3Tiles.setResolution(cam, htT3ResV);
  htT3Tiles.update();
}
const htT3OrigRender = renderer.render.bind(renderer);
renderer.render = function (s, c) {
  if (s !== scene || !htT3Tiles || renderer.xr.isPresenting) {
    if (htT3Foot && s === scene && !groundRoot.visible) htT3Foot.style.display = 'none';
    htT3OrigRender(s, c); return;
  }
  try { htT3Update(c); } catch (e) { htTiles.failed = true; htTiles.err = String(e && e.message || e).slice(0, 240); htT3Tiles = null; htT3RestoreLegacy(); htT3OrigRender(s, c); return; }
  if (!htTiles.active || !groundRoot.visible) { htT3OrigRender(s, c); return; }
  try {
    htT3HideLegacy();
    htT3OrigRender(htT3Scene, c);
    htTiles.tris = renderer.info.render.triangles; htTiles.calls = renderer.info.render.calls;
    renderer.autoClear = false;
    try { htT3OrigRender(s, c); } finally { renderer.autoClear = true; }
    htT3FooterTick();
  } catch (e) {
    htTiles.failed = true; htTiles.active = false; htTiles.err = String(e && e.message || e).slice(0, 240); renderer.autoClear = true;
    htT3RestoreLegacy();
    if (htT3Foot) htT3Foot.style.display = 'none';
    htT3OrigRender(s, c);
  }
};
(async () => {
  if (QUEST) { htTiles.skipped = 'quest'; return; }
  try { setLoad('tiles3d', 'loading'); } catch (e) {}
  try {
    const dep = await import('../vendor3d/dependencies.js');
    const T3 = await import('../vendor3d/three.module.min.js');
    // The page renderer (three r160) calls material.onBuild()
    // while compiling a material; three removed that hook after
    // r160, so restore it as a no-op on the vendored bundle's
    // Material prototype before any tile material compiles.
    if (typeof T3.Material.prototype.onBuild !== 'function') T3.Material.prototype.onBuild = function () {};
    htT3ResV = new T3.Vector2(1, 1);
    htT3Scene = new T3.Scene();
    const tiles = new dep.TilesRenderer(undefined);
    const draco = new dep.DRACOLoader().setDecoderPath('../vendor3d/draco/');
    tiles.registerPlugin(new dep.CesiumIonAuthPlugin({ apiToken: HT_T3_TOKEN, assetId: 2275207, autoRefreshToken: true, useRecommendedSettings: false }));
    tiles.registerPlugin(new dep.GLTFExtensionsPlugin({ dracoLoader: draco }));
    tiles.registerPlugin(new dep.TileCompressionPlugin({ disableMipmaps: true, compressIndex: true, compressPosition: false, compressUvs: false, compressNormals: false }));
    tiles.errorTarget = 16;
    tiles.lruCache.minSize = 450; tiles.lruCache.maxSize = 1600;
    tiles.lruCache.minBytesSize = 256 * 1024 * 1024; tiles.lruCache.maxBytesSize = 512 * 1024 * 1024;
    tiles.group.matrixAutoUpdate = false;
    htT3Scene.add(tiles.group);
    tiles.addEventListener('load-model', () => { htTiles.models++; if (!htTiles.active) { htTiles.active = true; try { setLoad('tiles3d', 'ok'); } catch (e) {} htT3FooterShow(); } });
    tiles.addEventListener('load-error', () => { htTiles.errors++; });
    htTiles.debug = () => { try { const e = tiles.group.matrixWorld.elements; return { vis: tiles.visibleTiles.size, tris: htTiles.tris || 0, calls: htTiles.calls || 0, gw: [e[12], e[13], e[14]].map((v) => Math.round(v)), cam: camera.position.toArray().map((v) => Math.round(v)), refe: Math.round(REFE), act: htTiles.active, fail: htTiles.failed, err: htTiles.err || null }; } catch (err) { return { dbgErr: String(err && err.message || err) }; } };
    htT3Tiles = tiles;
  } catch (e) {
    htTiles.failed = true;
    try { setLoad('tiles3d', 'ok'); } catch (e2) {}
  }
})();

window.HT3 = {"""

ANCHOR = "window.HT3 = {"
IMPORTMAP_RE = re.compile(r'<script type="importmap">(.*?)</script>', re.S)


def patch_importmap(s: str):
    """Add the vendor3d scope to the page importmap. Returns the
    new string, or None on any unexpected shape."""
    m = IMPORTMAP_RE.search(s)
    if not m:
        return None
    try:
        im = json.loads(m.group(1))
    except Exception:
        return None
    if im.get("imports") != EXPECTED_IMPORTS:
        return None
    scopes = im.get("scopes", {})
    if scopes.get(SCOPE_KEY) == SCOPE_MAP and set(scopes) == {SCOPE_KEY}:
        return s  # already scoped
    if scopes:
        return None
    im["scopes"] = {SCOPE_KEY: SCOPE_MAP}
    new = json.dumps(im, separators=(",", ":"))
    return s[: m.start(1)] + new + s[m.end(1):]


def patch_3d(path: Path) -> str:
    s = path.read_text(encoding="utf-8")
    if MARKER in s:
        return "skip (current)"
    if "HT_T3_TOKEN" in s:
        return "FAIL name collision: HT_T3_TOKEN already present"
    if s.count(ANCHOR) != 1:
        return f"FAIL anchor count {s.count(ANCHOR)} (want 1): window.HT3"
    if s.count("ht-waterbody3dhp v2") != 2:
        return f"FAIL waterbody census {s.count('ht-waterbody3dhp v2')} (want 2): run after patch_waterbody3dhp"
    site = path.name.replace("USGS-", "").replace("-3d.html", "")
    geoid = GEOID_N.get(site)
    if geoid is None:
        return f"FAIL no geoid height for station {site}"
    s2 = patch_importmap(s)
    if s2 is None:
        return "FAIL importmap shape unexpected"
    s = s2
    block = RENDERER.replace("__TOKEN__", TOKEN).replace("__GEOID__", repr(geoid))
    s = s.replace(ANCHOR, block, 1)
    if s.count(MARKER) != MARKER_COUNT:
        return f"FAIL post-check marker count {s.count(MARKER)} (want {MARKER_COUNT})"
    if s.count('"scopes"') != 1:
        return f"FAIL post-check scopes count {s.count(chr(34)+'scopes'+chr(34))} (want 1)"
    if s.count("htWb3Bank") != 2:
        return f"FAIL post-check bank census {s.count('htWb3Bank')} (want 2)"
    if s.count("ht-riverwater v1") != 5:
        return f"FAIL riverwater census {s.count('ht-riverwater v1')} (want 5)"
    if s.count("ht-smooth v2") != 13:
        return f"FAIL smooth census {s.count('ht-smooth v2')} (want 13)"
    if s.count("ht-flowline v1") != 2:
        return f"FAIL flowline census {s.count('ht-flowline v1')} (want 2)"
    path.write_text(s, encoding="utf-8")
    return f"patched (geoid N {geoid} m)"


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
