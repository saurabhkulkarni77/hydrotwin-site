#!/usr/bin/env python3
"""ht-ribbonshade v1: fix the river ribbon shading in steep terrain.

Defect (Lees Ferry 09380000, and the same geometry code on every 3D
page): the out-of-block river is a flat ribbon strip built by
buildRibbon(). Its material is single-sided (THREE.FrontSide default)
and its normals come from computeVertexNormals(). Where the path
winds through steep canyon terrain, segments whose winding faces
down or sideways are culled or shade almost black, so the river
reads as a wide black band instead of water. The newer polygon water
layer (ht-polywater) already avoids this: it forces every normal to
+Z-up in page space (0,1,0 here) and clones the material DoubleSide.

Fix, applied to the ribbon only (nothing else changes):
  1. ribbonMat.side = THREE.DoubleSide — no segment can be culled
     when the path turns back on itself in a canyon.
  2. After computeVertexNormals() in buildRibbon, overwrite the
     ribbon normals with straight up (0,1,0): the ribbon is a water
     surface, so it must shade like the polygon water does.

Anchors are exact strings, count-checked; a mismatch fails the step
without writing. Idempotent: pages carrying the marker are skipped.
Run from the repo root: python3 build25/patch_ribbonshade.py
"""
import sys
from pathlib import Path

MARKER = "ht-ribbonshade v1"

MAT_OLD = "const ribbonMat = waterMaterial(1 / 60, false);   // ht-smooth v2: ribbon geometry carries no aEdge attribute"
MAT_NEW = (MAT_OLD + "\nribbonMat.side = THREE.DoubleSide;"
           "   // ht-ribbonshade v1: the ribbon winds through steep terrain; a single-sided"
           " material culls the segments whose winding faces away and they read as a"
           " black band (Lees Ferry). The polygon water layer is DoubleSide for the same reason.")

GEO_OLD = "  g.setIndex(ix); g.computeVertexNormals(); ribbon.geometry.dispose(); ribbon.geometry = g;"
GEO_NEW = ("  g.setIndex(ix); g.computeVertexNormals();"
           " { const na = g.attributes.normal; for (let q = 0; q < na.count; q++) na.setXYZ(q, 0, 1, 0); na.needsUpdate = true; }"
           "   // ht-ribbonshade v1: force water-surface normals straight up (as ht-polywater"
           " does) - computed normals on a winding canyon ribbon tilt with the path and shade black"
           "\n  ribbon.geometry.dispose(); ribbon.geometry = g;")


def patch(path: Path) -> str:
    s = path.read_text(encoding="utf-8")
    if MARKER in s:
        return "skip (marker)"
    for old in (MAT_OLD, GEO_OLD):
        if s.count(old) != 1:
            return f"FAIL anchor count {s.count(old)} (want 1): {old[:60]!r}"
    s = s.replace(MAT_OLD, MAT_NEW, 1).replace(GEO_OLD, GEO_NEW, 1)
    if s.count(MARKER) != 2:
        return f"FAIL post-check marker count {s.count(MARKER)} (want 2)"
    if s.count("ht-realriver v1") < 1 or s.count("ribbonMat.side = THREE.DoubleSide") != 1:
        return "FAIL post-check: ribbon fix incomplete"
    path.write_text(s, encoding="utf-8")
    return "patched"


def main():
    files = sorted(p for p in Path("stations").glob("USGS-*.html")
                   if p.name.endswith("-3d.html"))
    if not files:
        print("no 3D station pages found", file=sys.stderr)
        return 1
    bad = 0
    for p in files:
        r = patch(p)
        print(f"{p.name}: {r}")
        if r.startswith("FAIL"):
            bad += 1
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
