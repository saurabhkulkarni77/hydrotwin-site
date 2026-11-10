#!/usr/bin/env python3
"""ht-terrainreal v1: ground-view terrain realism (DEV only).

Two changes to the 3D pages' GROUND view (the table view already has
its own exaggeration control and is untouched):

1. Vertical exaggeration per station. The ground view was true scale,
   which reads as flat at low-relief stations (Dallas especially).
   HT_EXAG_G scales every scene-space Y derived from elevation -
   terrain meshes, both water layers' seating, ground labels, the
   bank camera, the realriver channel carve - by one factor, so the
   whole scene stays self-consistent. DATA space is never scaled:
   the flood fill, stage ratings, dH and the polygap/bridgegap
   geometry (x/z) are unchanged, and structures that are measuring
   instruments or built heights (the staff gauge, levee crests added
   by ht-levees v1) keep true heights on top of the scaled ground.
   Values come from the inner block's measured relief (USGS 3DEP
   1 m LiDAR DEM baked by ht-realriver v1; terrarium z15 for the two
   stations realriver excluded), percentile 0.1..99.9:
       relief < 45 m -> 2.0x | 45..140 m -> 1.5x | > 140 m -> 1.0x

2. Hillshade blended into the satellite texture. htShadeApply_
   computes a hillshade from the DEM the page already has (sun
   azimuth 215 deg / elevation 40 deg, matching the scene sun) and
   multiplies it into the satellite canvas - overview (from the
   z12 terrarium DEM) and inner block (from the 3DEP/terrarium
   inner DEM) - before the texture is created, so the imagery stops
   looking painted on. Flat ground maps to 1.0 (no global darkening);
   the geology layer composites reuse the same canvases, so they
   inherit the shading as a base.

Terrain resolution: the inner block already renders the highest
resolution terrain in the project (3DEP 1 m LiDAR via ht-realriver);
the overview mesh is 257 vertices across ~41 km (~160 m per vertex),
so a finer overview DEM would not change the rendered surface and
is deliberately not fetched.

Anchors are exact strings of the current baked module, count-checked;
any mismatch fails the step without writing. Idempotent: pages
already carrying ht-terrainreal v1 are skipped. Preservation censuses
(bridgegap, polygap, polywater, nobuildings, ribbonshade, realriver,
riverwater, smooth, flowline) are post-checked.
"""
import sys
from pathlib import Path

MARKER = "ht-terrainreal v1"

# Per-station ground-view vertical exaggeration, from the inner
# block's measured relief (percentile 0.1..99.9 of the inner DEM the
# page itself renders: baked 3DEP 1 m for 11 stations, terrarium z15
# for 06214500 / 09380000 / 14105700, which ht-realriver excludes).
# Rule: relief < 45 m -> 2.0x, 45..140 m -> 1.5x, > 140 m -> 1.0x.
EXAG = {
    # site: (exaggeration, inner relief m)
    "01463500": (2.0, 43),
    "01646500": (1.5, 107),
    "02320500": (2.0, 15),
    "03294500": (2.0, 29),
    "05331000": (1.5, 76),
    "06214500": (1.5, 106),
    "06934500": (1.5, 109),
    "07374000": (2.0, 16),
    "08057000": (2.0, 43),
    "08158000": (2.0, 42),
    "08313000": (1.0, 312),
    "09380000": (1.0, 566),
    "11447650": (2.0, 11),
    "14105700": (1.0, 153),
}

BLOCK = """
// ------------------------------------------------------------------ ht-terrainreal v1
// Ground-view vertical exaggeration for this station (HT_EXAG_G, from
// the inner block's measured relief: flat stations up to 2x so the
// valley reads in 3D, canyon stations true scale) + a hillshade pass
// multiplied into the satellite texture so the imagery stops looking
// painted on. Only scene-space Y is scaled (terrain AND water AND
// labels together); data space - flood fill, ratings, stage - is not.
const HT_EXAG_G = __EXAG__;
function htShadeApply_(canvas, dem, n, worldM) {
  if (!canvas || !dem || dem.length < n * n) return;
  try {
    const c = document.createElement('canvas'); c.width = c.height = n;
    const g = c.getContext('2d'); const img = g.createImageData(n, n); const px = img.data;
    const cell = worldM / n, az = 215 * Math.PI / 180, alt = 40 * Math.PI / 180, zen = Math.PI / 2 - alt;
    const flat = Math.cos(zen);
    for (let j = 0; j < n; j++) {
      const jm = Math.max(0, j - 1) * n, j0 = j * n, jp = Math.min(n - 1, j + 1) * n;
      const rows = Math.min(n - 1, j + 1) - Math.max(0, j - 1);
      for (let i = 0; i < n; i++) {
        const im = Math.max(0, i - 1), ip = Math.min(n - 1, i + 1);
        const dzx = (dem[j0 + ip] - dem[j0 + im]) / ((ip - im) * cell);
        const dzy = (dem[jp + i] - dem[jm + i]) / (rows * cell);
        const slope = Math.atan(Math.hypot(dzx, dzy));
        const aspect = Math.atan2(dzy, -dzx);
        let h = Math.cos(zen) * Math.cos(slope) + Math.sin(zen) * Math.sin(slope) * Math.cos(az - aspect);
        if (h < 0) h = 0;
        let v = 0.30 + 0.70 * Math.min(1, h / flat);
        const o = (j0 + i) * 4, g8 = Math.round(255 * v);
        px[o] = g8; px[o + 1] = g8; px[o + 2] = g8; px[o + 3] = 255;
      }
    }
    g.putImageData(img, 0, 0);
    const ctx = canvas.getContext('2d');
    ctx.save(); ctx.globalCompositeOperation = 'multiply'; ctx.globalAlpha = 0.9;
    ctx.drawImage(c, 0, 0, canvas.width, canvas.height); ctx.restore();
  } catch (e) { /* shading is cosmetic; never break the layer */ }
}

"""

# (old, new, expected count) - every edit is count-checked.
EDITS = [
    # terrain meshes (anchors include the trailing block close: the
    # marker comment must never be the last thing before live code)
    ("pos.setY(k, sink ? -400 : elevAt(i / (NO - 1), j / (NO - 1)) - REFE - OUT_DROP); }",
     "pos.setY(k, sink ? -400 : (elevAt(i / (NO - 1), j / (NO - 1)) - REFE - OUT_DROP) * HT_EXAG_G); }   // ht-terrainreal v1", 1),
    ("iElev[k] = e; pos.setY(k, e - REFE); }",
     "iElev[k] = e; pos.setY(k, (e - REFE) * HT_EXAG_G); }   // ht-terrainreal v1", 1),
    # in-block flood water surface
    ("(e) => e - REFE + 0.05, groundRoot, gWaterMat",
     "(e) => (e - REFE + 0.05) * HT_EXAG_G, groundRoot, gWaterMat", 1),
    # ribbon water surface
    ("const y = Math.max(c.bed + add, c.top + 0.8) - REFE - OUT_DROP + OUT_DROP * Math.max(0, 1 - dOut / 200);",
     "const y = (Math.max(c.bed + add, c.top + 0.8) - REFE - OUT_DROP + OUT_DROP * Math.max(0, 1 - dOut / 200)) * HT_EXAG_G;   // ht-terrainreal v1", 1),
    # polygon water seating (anchor includes the for-loop close)
    ("pa.array[3 * i + 1] = m.near ? Math.max(m.bed + add, m.top + 0.8) - REFE - OUT_DROP + m.taper + 0.05 : m.gy - REFE - 0.3; }",
     "pa.array[3 * i + 1] = m.near ? (Math.max(m.bed + add, m.top + 0.8) - REFE - OUT_DROP + m.taper) * HT_EXAG_G + 0.05 : (m.gy - REFE) * HT_EXAG_G - 0.3; }   // ht-terrainreal v1", 1),
    # ground labels sit on the terrain (anchor spans the whole line)
    ("const y = elevGround(x, z) - REFE; const l = label(text, h, '#FFFFFF', bg, true); l.position.set(x, y + 45, z); gLabels.add(l);",
     "const y = (elevGround(x, z) - REFE) * HT_EXAG_G; const l = label(text, h, '#FFFFFF', bg, true); l.position.set(x, y + 45, z); gLabels.add(l);   // ht-terrainreal v1", 1),
    # bank camera perch (anchor includes the if-block close)
    ("if (best) bank = new THREE.Vector3(best[0], best[2] - REFE, best[1]); }",
     "if (best) bank = new THREE.Vector3(best[0], (best[2] - REFE) * HT_EXAG_G, best[1]); }   // ht-terrainreal v1", 1),
    # realriver channel carve works on the (now scaled) outer mesh
    ("const target = s[2] - REFE - OUT_DROP - 0.3;",
     "const target = (s[2] - REFE - OUT_DROP) * HT_EXAG_G - 0.3;   // ht-terrainreal v1", 1),
    # hillshade into the satellite textures
    ("layerTex.Satellite = canvasTex(SAT_O); setLayer(layer);",
     "htShadeApply_(SAT_O, elev, PW, WM); layerTex.Satellite = canvasTex(SAT_O); setLayer(layer);   // ht-terrainreal v1", 1),
    ("layerTexI.Satellite = canvasTex(SAT_I); setLayer(layer);",
     "htShadeApply_(SAT_I, iDEM, IW, IWM); layerTexI.Satellite = canvasTex(SAT_I); setLayer(layer);   // ht-terrainreal v1", 1),
]

PRESERVE = {
    "ht-bridgegap v1": 1,
    "ht-polygap v1": 1,
    "ht-polywater v1": 2,
    "ht-nobuildings v1": 2,
    "ht-ribbonshade v1": 2,
    "ht-realriver v1": 2,
    "ht-riverwater v1": 5,
    "ht-smooth v2": 13,
    "ht-flowline v1": 2,
}

BLOCK_ANCHOR = "function waterMaterial(rep, edge = true) {"


def patch_3d(path: Path) -> str:
    s = path.read_text(encoding="utf-8")
    if MARKER in s:
        return "skip (current)"
    site = path.name.replace("USGS-", "").replace("-3d.html", "")
    if site not in EXAG:
        return f"FAIL no exaggeration entry for site {site}"
    exag, relief = EXAG[site]
    if s.count(BLOCK_ANCHOR) != 1:
        return f"FAIL block anchor count {s.count(BLOCK_ANCHOR)} (want 1)"
    for old, new, want in EDITS:
        got = s.count(old)
        if got != want:
            return f"FAIL anchor count {got} (want {want}): {old[:60]}..."
    s = s.replace(BLOCK_ANCHOR, BLOCK.replace("__EXAG__", repr(exag)) + BLOCK_ANCHOR, 1)
    for old, new, want in EDITS:
        s = s.replace(old, new)
    for mk, want in PRESERVE.items():
        got = s.count(mk)
        if got != want:
            return f"FAIL preserve census {mk}: {got} (want {want})"
    if s.count(MARKER) < 10:
        return f"FAIL post-check marker count {s.count(MARKER)} (want >= 10)"
    path.write_text(s, encoding="utf-8")
    return f"patched (EXAG {exag}x, relief {relief} m)"


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
