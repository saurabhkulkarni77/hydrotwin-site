#!/usr/bin/env python3
"""ht-waterfilter v1: scene fix - water must never clip through a building.

DIAGNOSIS (2026-11-01, from the baked data of all 14 3D pages):
ht-buildingsback v1's polygon test htInPolyWater() has never dropped a
single building. POLYWATER entries are POLYGONS (arrays of rings, each
ring a flat [lon, lat, ...] list), but the function iterates POLYWATER
as if each entry were one flat ring: its bounding boxes come out NaN
(arithmetic over ring arrays) and its point-in-ring probes index ring
objects instead of numbers, so every test silently returns false.
Only the ht-riverwater flood-grid test ever filtered, and that test
tolerates partial wetness by design (drops on centroid wet, >= 4 wet
samples, or >= 30% wet samples), so bank-edge footprints that partly
intersect the modelled water survive - and their bases sit at or below
the water surface (checked on the baked 3DEP DEM: e.g. Potomac ids
1-5 ground 13.1-13.6 m against a ~14 m channel surface; Dallas ids
281/854 ground ~118 m at channel level), so the flat water plane cuts
through them exactly as reported. Re-seating cannot fix a horizontal
overlap without floating the building, so offending footprints are
REMOVED, per the user's order ("fix that building issue in scene,
otherwise just remove them").

WHAT THIS PATCHER DOES (stdlib only - the CI runner has no shapely):
1. Bake-time exact filter. For every 3D page it parses the baked
   BAKED_BUILDINGS footprints and POLYWATER rings, projects both into
   the page's own metre frame (the same mx/mz the scene uses), and
   drops every runtime-eligible footprint (the ones loadBuildings
   would render: >= 4 raw points, >= 3 after de-duplication, all
   points inside the inner block) that INTERSECTS any water ring
   polygon or comes within MARGIN_M metres of one. Exact tests:
   vertex-in-polygon (ray casting), ring-vertex-in-footprint, and
   segment-segment intersection; distance is the true polygon
   distance. Each water ring is treated as its own water polygon
   (OSM multipolygon outer ways are separate water bodies; treating
   every ring as water is the conservative reading and matches the
   ht-buildingsback "when in doubt, drop" rule).
2. Runtime repair. The broken htInPolyWater block (identical in all
   14 pages) is replaced with a nesting-correct version (per-ring
   bounding boxes, probes per ring, plus an exact edge-crossing
   test), so the runtime filter is real if building data is ever
   re-baked from source.
3. Records window.__htWaterFilter = {dropped, marginM} after the
   BAKED_BUILDINGS literal for verification.

Idempotent: pages already carrying the marker are skipped (and the
filter itself is a fixed point - a second run would find nothing
within the margin). Any anchor mismatch fails the step without
writing. Runs AFTER patch_buildingsback.py in the dev chain.
"""
import json
import math
import re
import sys
from pathlib import Path

MARKER = "ht-waterfilter v1"
MARKER_COUNT = 2  # appended comment line + runtime repair comment
MARGIN_M = 10.0
TS = 256.0


# ------------------------------------------------------------ page parsing
def _scan(s, j):
    """(start, end) of the JSON value starting at s[j] (string-aware)."""
    depth, k, in_str, esc = 0, j, False, False
    while k < len(s):
        c = s[k]
        if in_str:
            if esc:
                esc = False
            elif c == "\\":
                esc = True
            elif c == '"':
                in_str = False
        elif c == '"':
            in_str = True
        elif c in "[{":
            depth += 1
        elif c in "]}":
            depth -= 1
            if depth == 0:
                return j, k + 1
        k += 1
    raise ValueError("unterminated JSON value")


def find_value(s, marker):
    i = s.find(marker)
    if i == -1:
        return None
    j = i + len(marker)
    while j < len(s) and s[j].isspace():
        j += 1
    if s.startswith("null", j):
        return None, (j, j + 4)
    span = _scan(s, j)
    return json.loads(s[span[0]:span[1]]), span


# ------------------------------------------------------------ projection
def lon2px(lon, z):
    return (lon + 180.0) / 360.0 * TS * (2 ** z)


def lat2px(lat, z):
    r = math.radians(lat)
    return (1 - math.log(math.tan(r) + 1 / math.cos(r)) / math.pi) / 2 * TS * (2 ** z)


class Frame:
    """The page's own mx/mz projection + inner-block bounds."""

    def __init__(self, lat, lon):
        self.m0 = 156543.03392 * math.cos(math.radians(lat))
        self.gx0, self.gy0 = lon2px(lon, 0), lat2px(lat, 0)
        zi, iw = 15, 1024
        mpi = self.m0 / (2 ** zi)
        gxi, gyi = lon2px(lon, zi), lat2px(lat, zi)
        ipx0 = round(gxi / TS) * TS - 2 * TS
        ipy0 = round(gyi / TS) * TS - 2 * TS
        self.ix0, self.iz0 = (ipx0 - gxi) * mpi, (ipy0 - gyi) * mpi
        self.iwm = iw * mpi

    def mx(self, lo):
        return (lon2px(lo, 0) - self.gx0) * self.m0

    def mz(self, la):
        return (lat2px(la, 0) - self.gy0) * self.m0

    def in_inner(self, x, z, m=2):
        return (self.ix0 + m <= x <= self.ix0 + self.iwm - m
                and self.iz0 + m <= z <= self.iz0 + self.iwm - m)


# ------------------------------------------------------------ geometry
def pt_in_ring(x, z, ring):
    inside = False
    n = len(ring)
    j = n - 1
    for i in range(n):
        xi, zi = ring[i]
        xj, zj = ring[j]
        if ((zi > z) != (zj > z)) and (x < (xj - xi) * (z - zi) / (zj - zi) + xi):
            inside = not inside
        j = i
    return inside


def _orient(a, b, c):
    return (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])


def _on_seg(a, b, p):
    return (min(a[0], b[0]) - 1e-9 <= p[0] <= max(a[0], b[0]) + 1e-9
            and min(a[1], b[1]) - 1e-9 <= p[1] <= max(a[1], b[1]) + 1e-9)


def seg_intersect(a, b, c, d):
    o1, o2 = _orient(a, b, c), _orient(a, b, d)
    o3, o4 = _orient(c, d, a), _orient(c, d, b)
    if (o1 > 0) != (o2 > 0) and (o3 > 0) != (o4 > 0):
        return True
    if o1 == 0 and _on_seg(a, b, c):
        return True
    if o2 == 0 and _on_seg(a, b, d):
        return True
    if o3 == 0 and _on_seg(c, d, a):
        return True
    if o4 == 0 and _on_seg(c, d, b):
        return True
    return False


def pt_seg_dist(p, a, b):
    dx, dz = b[0] - a[0], b[1] - a[1]
    l2 = dx * dx + dz * dz
    if l2 == 0:
        return math.hypot(p[0] - a[0], p[1] - a[1])
    t = max(0.0, min(1.0, ((p[0] - a[0]) * dx + (p[1] - a[1]) * dz) / l2))
    return math.hypot(p[0] - (a[0] + dx * t), p[1] - (a[1] + dz * t))


def bbox(pts):
    xs = [p[0] for p in pts]
    zs = [p[1] for p in pts]
    return min(xs), max(xs), min(zs), max(zs)


CELL = 50.0   # segment-grid cell (m) for ring edge lookup
BAND = 25.0   # z-band height (m) for ray-casting edge lookup


class RingIndex:
    """One water ring, indexed so footprint tests only touch nearby edges.

    The filter never needs the true polygon distance - only whether a
    footprint intersects the ring or comes within MARGIN_M of it - so
    every test works on the small set of edges near the footprint.
    """

    def __init__(self, pts):
        self.pts = pts
        self.bb = bbox(pts)
        self.edges = [(pts[i], pts[(i + 1) % len(pts)]) for i in range(len(pts))]
        self.grid = {}
        for i, (a, b) in enumerate(self.edges):
            for cx in range(int(min(a[0], b[0]) // CELL), int(max(a[0], b[0]) // CELL) + 1):
                for cz in range(int(min(a[1], b[1]) // CELL), int(max(a[1], b[1]) // CELL) + 1):
                    self.grid.setdefault((cx, cz), []).append(i)
        self.bands = {}
        for e in self.edges:
            (xi, zi), (xj, zj) = e
            for band in range(int(min(zi, zj) // BAND), int(max(zi, zj) // BAND) + 1):
                self.bands.setdefault(band, []).append(e)

    def near_edges(self, fb, pad):
        out = set()
        for cx in range(int((fb[0] - pad) // CELL), int((fb[1] + pad) // CELL) + 1):
            for cz in range(int((fb[2] - pad) // CELL), int((fb[3] + pad) // CELL) + 1):
                out.update(self.grid.get((cx, cz), ()))
        return [self.edges[i] for i in out]

    def contains(self, x, z):
        inside = False
        for (xi, zi), (xj, zj) in self.bands.get(int(z // BAND), ()):
            if ((zi > z) != (zj > z)) and (x < (xj - xi) * (z - zi) / (zj - zi) + xi):
                inside = not inside
        return inside


def footprint_hits_water(fp, fb, ring: RingIndex) -> bool:
    """True when footprint fp intersects the ring or is within MARGIN_M."""
    rb = ring.bb
    dx = max(rb[0] - fb[1], fb[0] - rb[1], 0.0)
    dz = max(rb[2] - fb[3], fb[2] - rb[3], 0.0)
    if math.hypot(dx, dz) > MARGIN_M:
        return False
    near = ring.near_edges(fb, MARGIN_M)
    fedges = [(fp[i], fp[(i + 1) % len(fp)]) for i in range(len(fp))]
    for a, b in near:
        for c, d in fedges:
            if seg_intersect(a, b, c, d):
                return True
            if pt_seg_dist(c, a, b) <= MARGIN_M or pt_seg_dist(a, c, d) <= MARGIN_M:
                return True
    # containment either way (no edge within the margin, still inside)
    if ring.contains(fp[0][0], fp[0][1]):
        return True
    for x, z in ring.pts:
        if fb[0] <= x <= fb[1] and fb[2] <= z <= fb[3] and pt_in_ring(x, z, fp):
            return True
    return False


# ------------------------------------------------------------ runtime repair
OLD_BLOCK_START = "let htRingBoxes = null;"
OLD_BLOCK_END = "function htNearPath(pts) {"
NEW_BLOCK = r"""let htRingBoxes = null;   // ht-waterfilter v1: POLYWATER entries are polygons (arrays of rings); boxes are per RING
function htPtInRing(lon, lat, ring) { let inside = false;
  for (let i = 0, j = ring.length - 2; i < ring.length; j = i, i += 2) {
    const xi = ring[i], yi = ring[i + 1], xj = ring[j], yj = ring[j + 1];
    if (((yi > lat) !== (yj > lat)) && (lon < (xj - xi) * (lat - yi) / (yj - yi) + xi)) inside = !inside; }
  return inside; }
function htRingList() {
  if (htRingBoxes) return htRingBoxes;
  htRingBoxes = [];
  for (const poly of POLYWATER) for (const ring of poly) {
    let a = 1e9, b = -1e9, c = 1e9, d = -1e9;
    for (let i = 0; i < ring.length; i += 2) { a = Math.min(a, ring[i]); b = Math.max(b, ring[i]); c = Math.min(c, ring[i + 1]); d = Math.max(d, ring[i + 1]); }
    htRingBoxes.push([a, b, c, d, ring]);
  }
  return htRingBoxes;
}
function htSegX(x1, z1, x2, z2, x3, z3, x4, z4) {
  const d = (x2 - x1) * (z4 - z3) - (z2 - z1) * (x4 - x3); if (!d) return false;
  const t = ((x3 - x1) * (z4 - z3) - (z3 - z1) * (x4 - x3)) / d, u = ((x3 - x1) * (z2 - z1) - (z3 - z1) * (x2 - x1)) / d;
  return t >= 0 && t <= 1 && u >= 0 && u <= 1;
}
function htInPolyWater(geom) {
  if (typeof POLYWATER === 'undefined' || !POLYWATER || !POLYWATER.length || !geom || geom.length < 3) return false;
  const rings = htRingList();
  let cx = 0, cy = 0, minLo = 1e9, maxLo = -1e9, minLa = 1e9, maxLa = -1e9;
  for (const g of geom) { cx += g.lon; cy += g.lat; minLo = Math.min(minLo, g.lon); maxLo = Math.max(maxLo, g.lon); minLa = Math.min(minLa, g.lat); maxLa = Math.max(maxLa, g.lat); }
  cx /= geom.length; cy /= geom.length;
  const probes = geom.map((g) => [g.lon, g.lat]); probes.push([cx, cy]);
  for (let k = 0; k < geom.length; k++) { const a = geom[k], b = geom[(k + 1) % geom.length]; probes.push([(a.lon + b.lon) / 2, (a.lat + b.lat) / 2]); }
  const PAD = 0.0005;
  for (const [ba, bb, bc, bd, ring] of rings) {
    if (bb < minLo - PAD || ba > maxLo + PAD || bd < minLa - PAD || bc > maxLa + PAD) continue;
    for (const [lo, la] of probes) if (htPtInRing(lo, la, ring)) return true;
    for (let i = 0; i < ring.length; i += 2)
      if (ring[i] > minLo - PAD && ring[i] < maxLo + PAD && ring[i + 1] > minLa - PAD && ring[i + 1] < maxLa + PAD) return true;
    for (let k = 0; k < geom.length; k++) { const a = geom[k], b = geom[(k + 1) % geom.length];
      for (let i = 0; i + 1 < ring.length; i += 2) { const n = (i + 2) % ring.length;
        if (htSegX(a.lon, a.lat, b.lon, b.lat, ring[i], ring[i + 1], ring[n], ring[n + 1])) return true; } }
  }
  return false;
}
"""


def patch_3d(path: Path) -> str:
    s = path.read_text(encoding="utf-8")
    if MARKER in s:
        return "skip (current)"
    D, _ = find_value(s, "window.HT3D =")
    B, bspan = find_value(s, "const BAKED_BUILDINGS =")
    W, _ = find_value(s, "const POLYWATER =")
    if D is None or B is None:
        return "FAIL missing HT3D or BAKED_BUILDINGS"
    if s.count(OLD_BLOCK_START) != 1 or s.count(OLD_BLOCK_END) != 1:
        return "FAIL runtime-filter anchor count"
    fr = Frame(D["lat"], D["lon"])
    rings = []
    for poly in (W or []):
        for ring in poly:
            pts = [(fr.mx(ring[i]), fr.mz(ring[i + 1])) for i in range(0, len(ring) - 1, 2)]
            if len(pts) >= 3:
                rings.append(RingIndex(pts))
    kept, dropped = [], 0
    for el in B.get("elements", []):
        geom = el.get("geometry") or []
        drop = False
        if len(geom) >= 4 and rings:
            pts = [(fr.mx(g["lon"]), fr.mz(g["lat"])) for g in geom]
            if len(pts) > 1 and pts[0] == pts[-1]:
                pts = pts[:-1]
            if len(pts) >= 3 and all(fr.in_inner(x, z, 2) for x, z in pts):
                fb = bbox(pts)
                for ring in rings:
                    if footprint_hits_water(pts, fb, ring):
                        drop = True
                        break
        if drop:
            dropped += 1
        else:
            kept.append(el)
    B["elements"] = kept
    new_json = json.dumps(B, separators=(",", ":"), ensure_ascii=False)
    s = s[:bspan[0]] + new_json + s[bspan[1]:]
    after = bspan[0] + len(new_json)
    note = (f";\n// {MARKER}: {dropped} building footprints intersecting an OSM water polygon "
            f"(or within {MARGIN_M:.0f} m of one) removed from BAKED_BUILDINGS at bake time "
            f"by build25/patch_waterfilter.py - water must never clip through a building.\n"
            f"window.__htWaterFilter = {{\"dropped\": {dropped}, \"marginM\": {MARGIN_M:.0f}}};")
    # the original literal is followed by ';' already in the page template
    # ("const BAKED_BUILDINGS = {...};") - insert after it if present.
    if s[after:after + 1] == ";":
        s = s[:after + 1] + note[1:] + s[after + 1:]
    else:
        s = s[:after] + note + s[after:]
    i = s.find(OLD_BLOCK_START)
    j = s.find(OLD_BLOCK_END)
    if i == -1 or j == -1 or j < i:
        return "FAIL runtime-filter block span"
    s = s[:i] + NEW_BLOCK + s[j:]
    if s.count(MARKER) != MARKER_COUNT:
        return f"FAIL post-check marker count {s.count(MARKER)} (want {MARKER_COUNT})"
    if s.count("function htPtInRing") != 1 or s.count("function htInPolyWater") != 1:
        return "FAIL post-check: htPtInRing/htInPolyWater definition census != 1"
    if s.count("ht-buildingsback v1") != 3:
        return f"FAIL buildingsback census {s.count('ht-buildingsback v1')} (want 3)"
    path.write_text(s, encoding="utf-8")
    return f"patched (kept {len(kept)}, dropped {dropped} within {MARGIN_M:.0f} m of water)"


def main():
    root = Path("stations")
    files = sorted(root.glob("USGS-*-3d.html"))
    if not files:
        print("no 3D station pages found under stations/", file=sys.stderr)
        return 1
    bad = 0
    for p in files:
        r = patch_3d(p)
        print(f"{p.name}: {r}")
        if r.startswith("FAIL"):
            bad += 1
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
