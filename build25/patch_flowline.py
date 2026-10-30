#!/usr/bin/env python3
"""No dotted river overlay + a water surface that reads as water (ht-flowline v1).

User report (2026-10-30, photo of the Dallas 08057000 3D page):
"no its not [fixed]" - the river reads as a dotted blue ribbon of dots
floating over flat satellite terrain. Object-isolation diagnosis on the
live dev build (scene census + hide-one-at-a-time screenshots) found
THREE separate dotted/overlay artefacts, none of which is the water:

  1. WaterGrid.setLine() "shoreline dots" (the visible culprit at the
     default view): updateLevel() always draws the PREDICTED water
     level's shoreline as THREE.Points - constant screen size (3.5 px),
     toneMapped off, renderOrder 3, coloured with the active model's
     colour (#2f80d1 for PILSTMv1), floating at the grid lift (0.6 m)
     over the surface. On a narrow low-flow channel the fill is only a
     few 10.7 m cells wide, so the two dotted banks merge into one
     dotted blue band - and the actual water surface under them (dark
     blue-green, alpha-faded at its edges by ht-smooth v2) is barely
     visible. At the default day (2025-01-27, 553 cfs) the live census
     reads: points visible=true, colour #2f80d1, while the surface
     itself is a 2,575-vertex sliver. The dots ARE the "river" a user
     sees. Fix: setLine() never shows the points again (both grids,
     both modes, forecast included - any dotted shoreline reads as
     this bug). Buffers stay allocated; the method is a no-op hide.

  2. buildOverlays() NLDI flow-path tubes (table/overview view): the
     upstream path is drawn as a #7CC8FF tube and the downstream path
     as a #2D8CFF tube along the NLDI centre-lines, plus pale-blue
     tributary line segments, white direction cones every 5 km and
     "km downstream" labels - a data overlay draped over the terrain,
     widely mistaken for the river itself. Fix: the whole flow-path
     block is removed. The basin outline, neighbouring-gauge pins and
     the north label stay (map furniture, not the river).

  3. The ht-smooth v2 shoreline fade could wash a narrow channel out:
     its alpha floor was 0.08 at the waterline, so the 1-2 shoreline
     vertices of a 3-cell-wide channel rendered nearly transparent.
     Fix: floor raised 0.08 -> 0.5 (edges still soften, the channel
     keeps its body).

NOT changed: the flood model, the water levels, the ribbon geometry,
ht-riverwater v1 behaviour (post-checked: census stays 5), ht-smooth
v2 (census stays 13). The ground-view station labels and their
"km downstream" tags are labels, not river geometry, and stay.

Anchors are exact strings of the current baked module (identical in
all 14 3D pages apart from per-station data blobs). Every replacement
is count-checked; any mismatch fails the step without writing.
Idempotent: pages already carrying ht-flowline v1 are skipped. Runs
AFTER patch_smooth.py in the dev chain.
"""
import sys
from pathlib import Path

MARKER = "ht-flowline v1"
MARKER_COUNT = 2  # census of the marker inside a patched page

# ---------------------------------------------------------------- overlays
OVERLAY_OLD = """  if (RIV.ut) for (const s of lines(RIV.ut)) for (const pts of drape(s, 0.004)) overlay.add(lineObj(pts, '#7FD3FF', 0.9));
  if (RIV.umPath) for (const pts of drape(RIV.umPath, 0.004)) { const t = tube(pts, 0.0025, '#7CC8FF', 0.8); t && overlay.add(t); }
  if (RIV.dmPath) {
    for (const pts of drape(RIV.dmPath, 0.004)) { const t = tube(pts, 0.0035, '#2D8CFF', 0.8); t && overlay.add(t); }
    const cd = RIV.dmDist; let next = 5000;
    for (let k = 1; k < RIV.dmPath.length; k++) {
      while (cd[k] >= next) {
        const t = (next - cd[k - 1]) / Math.max(1, cd[k] - cd[k - 1]); const a = RIV.dmPath[k - 1], b = RIV.dmPath[k];
        const p = [a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t]; const [u, v] = uvOf(p[0], p[1]);
        if (inBox(u, v)) {
          const q = local(u, v, 0.012); const [u2, v2] = uvOf(b[0], b[1]); const q2 = local(u2, v2, 0.012);
          const dir = new THREE.Vector3().subVectors(q2, q).setY(0).normalize();
          const cone = new THREE.Mesh(new THREE.ConeGeometry(0.01, 0.026, 12), new THREE.MeshBasicMaterial({ color: '#FFFFFF' }));
          cone.position.copy(q); cone.quaternion.setFromUnitVectors(new THREE.Vector3(0, 1, 0), dir); overlay.add(cone);
          if (next % 10000 === 0) { const l = label(`${next / 1000} km downstream`, 0.024, '#FFFFFF', 'rgba(30,111,224,0.85)'); l.position.copy(q).y += 0.04; overlay.add(l); }
        }
        next += 5000;
      }
    }
  }"""
OVERLAY_NEW = """  // ht-flowline v1: no NLDI flow-path overlay in the 3D scene - the tributary
  // centre-lines and the upstream/downstream path tubes (+ direction cones and
  // km labels) that used to be drawn here are removed; the river is the water
  // surface itself. Basin outline, gauge pins and the north label stay."""

# ---------------------------------------------------------------- shoreline dots
SETLINE_OLD = """  setLine(key, dH, color) {
    const L = this.lines[key]; if (dH == null || !this.flood) { L.visible = false; return; }
    const F = this.flood, N = this.N, w = this.wet2; F.fill(dH, w); const pa = L.geometry.attributes.position.array, src = this.geo.attributes.position.array; let c = 0;
    for (let j = 1; j < N - 1; j++) for (let i = 1; i < N - 1; i++) { const k = j * N + i; if (!w[k]) continue;
      if (!w[k - 1] || !w[k + 1] || !w[k - N] || !w[k + N]) { pa[3 * c] = src[3 * k]; pa[3 * c + 1] = this.yOfElev(F.wse[k]) + this.lift; pa[3 * c + 2] = src[3 * k + 2]; c++; } }
    L.geometry.attributes.position.needsUpdate = true; L.geometry.setDrawRange(0, c); L.material.color.set(color); L.visible = true;
  }"""
SETLINE_NEW = """  setLine(key, dH, color) {   // ht-flowline v1: the shoreline DOTS are never drawn - at the default view the predicted-level dots (model colour, constant screen size, floating at the grid lift over the surface) were the only visible "river": a dotted blue ribbon over a barely visible channel. The water surface mesh is the river now; the dot buffers stay allocated but hidden.
    const L = this.lines[key]; if (L) L.visible = false;
  }"""

# ---------------------------------------------------------------- edge fade floor
FADE_OLD = "diffuseColor.a *= mix(0.08, 1.0, smoothstep(0.05, 0.95, vEdge));"
FADE_NEW = "diffuseColor.a *= mix(0.5, 1.0, smoothstep(0.05, 0.95, vEdge));"

EDITS = [
    (OVERLAY_OLD, OVERLAY_NEW),
    (SETLINE_OLD, SETLINE_NEW),
    (FADE_OLD, FADE_NEW),
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
    if s.count("ht-smooth v2") != 13:
        return f"FAIL smooth census {s.count('ht-smooth v2')} (want 13)"
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
