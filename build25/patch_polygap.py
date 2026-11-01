#!/usr/bin/env python3
"""ht-polygap v1: the polygon water stops at bridge decks too.

Defect (Saurabh's screenshot, 2026-11-01, Dallas 3D page): the blue
river still paints straight ACROSS a bridge deck. Root cause found the
same day: the 3D scene has TWO water layers in the same colour.
ht-bridgegap v1 (2026-10-31) cut the baked OSM bridge crossings into
the RIBBON (buildRibbon) only; the second layer, the ht-polywater v1
polygon mesh (triangulated OSM water polygons seated on the ribbon
profile, drawn +0.05 m over it), was never gapped, so at every crossing
outside the detailed block the polygon water still covers the deck.
(The classic station pages draw no water geometry at all - they are
statistics pages - so this defect and this fix are 3D-only.)

Fix: cut the same crossing bands out of the baked POLYWATER rings.
The crossings are read from the page's own HT_BRIDGES table (baked by
ht-bridgegap v1 from build25/bridgegap_data.py - the single source of
truth, not a second dataset), projected onto the baked 3DEP profile
(build25/realriver_data.py, the same profile the ribbon gaps use).
Each ring is clipped in curvilinear (arclength s, signed lateral d)
coordinates: Sutherland-Hodgman half-plane clips at s = sc - w and
s = sc + w remove the band, with new boundary vertices placed on the
path frame at the band edges, so the polygon water stops exactly at
the deck edges and the (already gapped) ribbon shows the same gap.
Details that keep the cut honest:

- a polygon is only cut at a crossing it actually covers (profile
  points in the band inside it, or a band-grid point inside it);
  off-channel water bodies whose shores merely project into the same
  arclength range are never sliced (the (s, d) frame is meaningless
  kilometres from the centreline);
- ring edges near a band are subdivided to <= 8 m first, because the
  clip interpolates along edges in (s, d) space and long edges drift
  off their true course where the river frame bends;
- invariant: a cut can only remove water. If a clipped polygon's net
  area grows, the original is kept for that crossing.

Nothing else in the page changes: the splice replaces only the
POLYWATER array and adds the marker comment above it. Water colour,
opacity, seating, the ribbon and its gaps, panels and the helper are
untouched. Idempotent: pages carrying the marker are skipped.
Run from the repo root: python3 build25/patch_polygap.py
"""
import glob, json, math, os, re, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
try:
    from realriver_data import HT_RIVER_PROFILES
except Exception:
    HT_RIVER_PROFILES = {}

MARKER = 'ht-polygap v1'
MARKER_LINE = '/* ht-polygap v1: bridge bands cut out of the polygon water (build25/patch_polygap.py) */\n'
PW_MARK = 'const POLYWATER ='
BR_MARK = 'const HT_BRIDGES ='
M0C = 156543.03392


def _lon2px(lon): return (lon + 180.0) / 360.0 * 256.0


def _lat2px(lat):
    r = math.radians(lat)
    return (1.0 - math.log(math.tan(r) + 1.0 / math.cos(r)) / math.pi) / 2.0 * 256.0


class Frame:
    """The pages' Web Mercator frame (identical formulas to the pages)."""

    def __init__(self, lat, lon):
        self.lat, self.lon = lat, lon
        self.m0 = M0C * math.cos(math.radians(lat))
        self.gx, self.gy = _lon2px(lon), _lat2px(lat)

    def mx(self, lon): return (_lon2px(lon) - self.gx) * self.m0

    def mz(self, lat): return (_lat2px(lat) - self.gy) * self.m0

    def inv_x(self, x): return self.lon + (x / self.m0) * (360.0 / 256.0)

    def inv_z(self, z):
        Y = self.gy + z / self.m0
        return math.degrees(math.atan(math.sinh(math.pi * (1.0 - 2.0 * Y / 256.0))))


def extract_json(html, marker):
    i = html.index(marker)
    j = i + len(marker)
    while html[j] in ' =':
        j += 1
    d = 0
    k = j
    while True:
        if html[k] == '[':
            d += 1
        elif html[k] == ']':
            d -= 1
            if d == 0:
                break
        k += 1
    return html[j:k + 1], (j, k + 1)


class Projector:
    """Nearest-segment projection onto the profile polyline: a uniform
    grid search (certified exact near the river) combined with a
    sample-anchored search that finds the right reach for far vertices."""

    CELL = 200.0

    def __init__(self, path):
        self.path = path
        self.S = [0.0]
        for i in range(1, len(path)):
            self.S.append(self.S[-1] + math.hypot(path[i][0] - path[i - 1][0],
                                                  path[i][1] - path[i - 1][1]))
        self.grid = {}
        C = self.CELL
        for j in range(len(path) - 1):
            ax, az = path[j]
            bx, bz = path[j + 1]
            i0, i1 = int(min(ax, bx) // C), int(max(ax, bx) // C)
            k0, k1 = int(min(az, bz) // C), int(max(az, bz) // C)
            for i in range(i0, i1 + 1):
                for k in range(k0, k1 + 1):
                    self.grid.setdefault((i, k), []).append(j)
        self.pgrid = {}
        for j, (px, pz) in enumerate(path):
            self.pgrid.setdefault((int(px // 1000.0), int(pz // 1000.0)), []).append(j)
        self._anchor_cache = {}

    def _seg(self, px, pz, j):
        path, S = self.path, self.S
        ax, az = path[j]
        bx, bz = path[j + 1]
        dx, dz = bx - ax, bz - az
        L2 = dx * dx + dz * dz or 1.0
        L = math.sqrt(L2)
        t = ((px - ax) * dx + (pz - az) * dz) / L2
        t = 0.0 if t < 0 else (1.0 if t > 1 else t)
        qx, qz = ax + dx * t, az + dz * t
        d = math.hypot(px - qx, pz - qz)
        ux, uz = dx / L, dz / L
        return d, S[j] + t * L, (px - qx) * (-uz) + (pz - qz) * ux

    @staticmethod
    def _perimeter(ci, ck, ring):
        if ring == 0:
            yield (ci, ck)
            return
        for i in range(ci - ring, ci + ring + 1):
            yield (i, ck - ring)
            yield (i, ck + ring)
        for k in range(ck - ring + 1, ck + ring):
            yield (ci - ring, k)
            yield (ci + ring, k)

    def _grid_search(self, px, pz, max_ring):
        C = self.CELL
        ci, ck = int(px // C), int(pz // C)
        best = None
        ring = 0
        while ring <= max_ring:
            for (i, k) in self._perimeter(ci, ck, ring):
                for j in self.grid.get((i, k), ()):
                    cand = self._seg(px, pz, j)
                    if best is None or cand[0] < best[0]:
                        best = cand
            if best is not None:
                dx_out = min(px - (ci - ring) * C, (ci + ring + 1) * C - px)
                dz_out = min(pz - (ck - ring) * C, (ck + ring + 1) * C - pz)
                if best[0] <= min(dx_out, dz_out):
                    return best, True
            ring += 1
        return best, False

    def _anchored_search(self, px, pz):
        C = 1000.0
        ci, ck = int(px // C), int(pz // C)
        best_i = self._anchor_cache.get((ci, ck))
        if best_i is None:
            best_d = None
            ring = 0
            while ring <= 200:
                for (i, k) in self._perimeter(ci, ck, ring):
                    for j in self.pgrid.get((i, k), ()):
                        d = math.hypot(px - self.path[j][0], pz - self.path[j][1])
                        if best_d is None or d < best_d:
                            best_d, best_i = d, j
                if best_d is not None:
                    dx_out = min(px - (ci - ring) * C, (ci + ring + 1) * C - px)
                    dz_out = min(pz - (ck - ring) * C, (ck + ring + 1) * C - pz)
                    if best_d <= min(dx_out, dz_out):
                        break
                ring += 1
            if best_i is None:
                return None
            self._anchor_cache[(ci, ck)] = best_i
        best = None
        for j in range(max(0, best_i - 10), min(len(self.path) - 1, best_i + 10)):
            cand = self._seg(px, pz, j)
            if best is None or cand[0] < best[0]:
                best = cand
        return best

    def project(self, px, pz, exact=False):
        # exact: the anchored search finds the right reach globally; the
        # grid search (capped) finds the true nearest segment whenever it
        # lies within the searched square, which covers every hairpin
        # case. An unbounded grid expansion was far too slow for
        # floodplain vertices kilometres from the centreline.
        if exact:
            best = self._anchored_search(px, pz)
            g, _cert = self._grid_search(px, pz, 12)
            if g is not None and (best is None or g[0] < best[0]):
                best = g
            if best is None or best[0] > 1500.0:
                for j in range(len(self.path) - 1):
                    cand = self._seg(px, pz, j)
                    if best is None or cand[0] < best[0]:
                        best = cand
            return best[1], best[2], best[0]
        best, certified = self._grid_search(px, pz, 12)
        if not certified:
            anch = self._anchored_search(px, pz)
            if anch is not None and (best is None or anch[0] < best[0]):
                best = anch
        if best is None:
            for j in range(len(self.path) - 1):
                cand = self._seg(px, pz, j)
                if best is None or cand[0] < best[0]:
                    best = cand
        return best[1], best[2], best[0]

    def point_at(self, s, d):
        S, path = self.S, self.path
        lo, hi = 0, len(S) - 1
        while lo < hi:
            mid = (lo + hi) // 2
            if S[mid] < s:
                lo = mid + 1
            else:
                hi = mid
        j = max(0, lo - 1)
        ax, az = path[j]
        bx, bz = path[j + 1]
        dx, dz = bx - ax, bz - az
        L = math.hypot(dx, dz) or 1.0
        ux, uz = dx / L, dz / L
        off = s - S[j]
        return (ax + ux * off + (-uz) * d, az + uz * off + ux * d)


def _sh_clip(verts, bound, keep_le, proj):
    if not verts:
        return []

    def inside(v):
        return v[0] <= bound if keep_le else v[0] >= bound

    def inter(a, b):
        t = (bound - a[0]) / (b[0] - a[0]) if b[0] != a[0] else 0.0
        d = a[1] + (b[1] - a[1]) * t
        x, z = proj.point_at(bound, d)
        return (bound, d, x, z)

    out = []
    n = len(verts)
    for i in range(n):
        cur, nxt = verts[i], verts[(i + 1) % n]
        ci, ni = inside(cur), inside(nxt)
        if ci:
            out.append(cur)
        if ci != ni:
            out.append(inter(cur, nxt))
    return out


def _ring_area(ring):
    a = 0.0
    for i in range(len(ring)):
        x0, z0 = ring[i][2], ring[i][3]
        x1, z1 = ring[(i + 1) % len(ring)][2], ring[(i + 1) % len(ring)][3]
        a += x0 * z1 - x1 * z0
    return abs(a) / 2.0


def _point_in_ring(x, z, ring):
    inside = False
    n = len(ring)
    for i in range(n):
        x0, z0 = ring[i][2], ring[i][3]
        x1, z1 = ring[(i + 1) % n][2], ring[(i + 1) % n][3]
        if ((z0 > z) != (z1 > z)) and (x < (x1 - x0) * (z - z0) / (z1 - z0) + x0):
            inside = not inside
    return inside


def _seg_point_dist(px, pz, ax, az, bx, bz):
    dx, dz = bx - ax, bz - az
    L2 = dx * dx + dz * dz or 1.0
    t = ((px - ax) * dx + (pz - az) * dz) / L2
    t = 0.0 if t < 0 else (1.0 if t > 1 else t)
    return math.hypot(px - (ax + dx * t), pz - (az + dz * t))


class PolyGapCutter:
    def __init__(self, frame, path, crossings_xzw):
        self.fr = frame
        self.proj = Projector(path)
        self.crossings = []
        for (cx, cz, w) in crossings_xzw:
            sc, _d, _dist = self.proj.project(cx, cz, exact=True)
            self.crossings.append((cx, cz, w, sc))

    def _ring_to_sd(self, flat, exact=False):
        fr = self.fr
        pts = [(fr.mx(flat[i]), fr.mz(flat[i + 1])) for i in range(0, len(flat) - 1, 2)]
        if len(pts) > 1 and abs(pts[0][0] - pts[-1][0]) < 1e-9 and abs(pts[0][1] - pts[-1][1]) < 1e-9:
            pts.pop()
        out = []
        for (x, z) in pts:
            s, d, _dist = self.proj.project(x, z, exact=exact)
            out.append((s, d, x, z))
        return out

    def _exactify(self, poly):
        out = []
        for ring in poly:
            nr = []
            for v in ring:
                s, d, _dist = self.proj.project(v[2], v[3], exact=True)
                nr.append((s, d, v[2], v[3]))
            out.append(nr)
        return out

    def _candidate(self, poly, cx, cz, w, sc):
        for ring in poly:
            n = len(ring)
            for i in range(n):
                v = ring[i]
                u = ring[(i + 1) % n]
                if abs(v[0] - sc) <= w + 40.0:
                    return True
                if (v[0] < sc - w and u[0] > sc + w) or (u[0] < sc - w and v[0] > sc + w):
                    return True
                if _seg_point_dist(cx, cz, v[2], v[3], u[2], u[3]) <= w + 400.0:
                    return True
        return False

    def _covers_path(self, poly, cx, cz, w, sc):
        """Cut-eligibility: the polygon must actually cover the river at
        this crossing (profile points in the band, or failing that any
        band-grid point - the profile can run along a bank)."""
        S, path = self.proj.S, self.proj.path
        tests = [(cx, cz)]
        for j, s in enumerate(S):
            if sc - w - 40.0 <= s <= sc + w + 40.0:
                tests.append(path[j])

        xs = [v[2] for v in poly[0]]
        zs = [v[3] for v in poly[0]]
        bb = (min(xs), max(xs), min(zs), max(zs))

        def inside(x, z):
            if x < bb[0] or x > bb[1] or z < bb[2] or z > bb[3]:
                return False
            if not _point_in_ring(x, z, poly[0]):
                return False
            return not any(_point_in_ring(x, z, h) for h in poly[1:])

        if any(inside(x, z) for (x, z) in tests):
            return True
        ns = 7
        for i in range(ns):
            s = sc - w + (2.0 * w) * (i / (ns - 1.0)) if ns > 1 else sc
            for d in range(-72, 73, 12):
                x, z = self.proj.point_at(s, float(d))
                if inside(x, z):
                    return True
        return False

    def _densify(self, poly, w, sc):
        lo, hi = sc - w - 60.0, sc + w + 60.0

        def near_band(a, b):
            return not (max(a[0], b[0]) < lo or min(a[0], b[0]) > hi)

        def subdivide(a, b, depth):
            if depth <= 0:
                return [a, b]
            if math.hypot(b[2] - a[2], b[3] - a[3]) <= 8.0:
                return [a, b]
            mxz = ((a[2] + b[2]) / 2.0, (a[3] + b[3]) / 2.0)
            s, d, _dist = self.proj.project(mxz[0], mxz[1], exact=True)
            m = (s, d, mxz[0], mxz[1])
            left = subdivide(a, m, depth - 1) if near_band(a, m) else [a, m]
            right = subdivide(m, b, depth - 1) if near_band(m, b) else [m, b]
            return left[:-1] + right

        out = []
        for ring in poly:
            if len(ring) < 2:
                out.append(ring)
                continue
            new_ring = []
            n = len(ring)
            for i in range(n):
                a, b = ring[i], ring[(i + 1) % n]
                if near_band(a, b) and math.hypot(b[2] - a[2], b[3] - a[3]) > 8.0:
                    seg = subdivide(a, b, 14)
                    new_ring.extend(seg[:-1])
                else:
                    new_ring.append(a)
            out.append(new_ring)
        return out

    def _touched(self, poly, w, sc):
        for ring in poly:
            n = len(ring)
            for i in range(n):
                v = ring[i]
                if abs(v[0] - sc) <= w:
                    return True
                s0 = v[0]
                s1 = ring[(i + 1) % n][0]
                if (s0 < sc - w and s1 > sc + w) or (s1 < sc - w and s0 > sc + w):
                    return True
        return False

    def _densify_boundary(self, verts, bound):
        """Subdivide a clipped ring's band-edge chain so the stored edge
        follows the curved path-normal line instead of one straight
        chord. On a wide bending river a single chord across the channel
        deviates from the true band edge by tens of metres (sagitta),
        which both displaces the water edge and breaks the area
        invariant on hole-rich polygons. Only edges lying on the clip
        line (both ends at s == bound, midpoint on the frame line) are
        subdivided; points are placed exactly on the frame."""
        if len(verts) < 2:
            return verts

        def on_line(v):
            return abs(v[0] - bound) < 0.01

        def subdivide(a, b, depth):
            if depth <= 0 or math.hypot(b[2] - a[2], b[3] - a[3]) <= 30.0:
                return [a, b]
            dm = (a[1] + b[1]) / 2.0
            mxz = self.proj.point_at(bound, dm)
            # guard: only true clip-line edges follow the frame line
            if math.hypot(mxz[0] - (a[2] + b[2]) / 2.0, mxz[1] - (a[3] + b[3]) / 2.0) > 15.0:
                return [a, b]
            m = (bound, dm, mxz[0], mxz[1])
            return subdivide(a, m, depth - 1)[:-1] + subdivide(m, b, depth - 1)

        out = []
        n = len(verts)
        for i in range(n):
            a, b = verts[i], verts[(i + 1) % n]
            if on_line(a) and on_line(b) and math.hypot(b[2] - a[2], b[3] - a[3]) > 30.0:
                out.extend(subdivide(a, b, 8)[:-1])
            else:
                out.append(a)
        return out

    def _clip(self, poly, w, sc):
        pieces = []
        for keep_le, bound in ((True, sc - w), (False, sc + w)):
            clipped = [self._densify_boundary(_sh_clip(ring, bound, keep_le, self.proj), bound)
                       for ring in poly]
            outers, holes = [], []
            for ci, vs in enumerate(clipped):
                if len(vs) < 3:
                    continue
                if _ring_area(vs) < 20.0:
                    continue
                (outers if ci == 0 else holes).append(vs)
            for o in outers:
                hs = []
                for h in holes:
                    # Assign by centroid or any sampled vertex, not just the
                    # first vertex: a clipped hole's first vertex can lie
                    # exactly on the band edge (the outer's own boundary
                    # there), where a point-in-ring test is arbitrary -
                    # dropping such a hole would turn its island into water.
                    cxh = sum(v[2] for v in h) / len(h)
                    czh = sum(v[3] for v in h) / len(h)
                    stride = max(1, len(h) // 8)
                    if _point_in_ring(cxh, czh, o) or any(
                            _point_in_ring(h[i][2], h[i][3], o) for i in range(0, len(h), stride)):
                        hs.append(h)
                pieces.append([o] + hs)
        return pieces

    def cut(self, polywater_ll):
        """Returns (new_polywater_ll, stats)."""
        polys = [[self._ring_to_sd(r) for r in poly] for poly in polywater_ll]
        exact = [False] * len(polys)
        stats = {'crossings_cut': 0, 'clips_rejected': 0, 'polys_before': len(polys)}
        for (cx, cz, w, sc) in self.crossings:
            new_polys, new_exact = [], []
            any_cut = False
            for pi, p in enumerate(polys):
                if not self._candidate(p, cx, cz, w, sc):
                    new_polys.append(p)
                    new_exact.append(exact[pi])
                    continue
                if not exact[pi]:
                    p = self._exactify(p)
                if not self._covers_path(p, cx, cz, w, sc):
                    new_polys.append(p)
                    new_exact.append(True)
                    continue
                p = self._densify(p, w, sc)
                if not self._touched(p, w, sc):
                    new_polys.append(p)
                    new_exact.append(True)
                    continue
                area_before = _ring_area(p[0]) - sum(_ring_area(h) for h in p[1:])
                pieces = self._clip(p, w, sc)
                area_after = sum(_ring_area(pc[0]) - sum(_ring_area(h) for h in pc[1:]) for pc in pieces)
                if area_after > area_before * 1.01 + 100.0:
                    pieces = [p]
                    stats['clips_rejected'] += 1
                else:
                    any_cut = True
                new_polys.extend(pieces)
                new_exact.extend([True] * len(pieces))
            polys, exact = new_polys, new_exact
            if any_cut:
                stats['crossings_cut'] += 1
        stats['polys_after'] = len(polys)
        fr = self.fr
        out = []
        for p in polys:
            poly_ll = []
            for ring in p:
                flat = []
                for v in ring:
                    flat += [round(fr.inv_x(v[2]), 6), round(fr.inv_z(v[3]), 6)]
                poly_ll.append(flat)
            out.append(poly_ll)
        return out, stats


def net_area_m2(polywater_ll, frame):
    def ring_area(flat):
        pts = [(frame.mx(flat[i]), frame.mz(flat[i + 1])) for i in range(0, len(flat) - 1, 2)]
        a = 0.0
        for i in range(len(pts)):
            x0, z0 = pts[i]
            x1, z1 = pts[(i + 1) % len(pts)]
            a += x0 * z1 - x1 * z0
        return abs(a) / 2.0

    tot = 0.0
    for p in polywater_ll:
        tot += ring_area(p[0]) - sum(ring_area(h) for h in p[1:])
    return tot


def patch(path):
    with open(path, encoding='utf8') as f:
        html = f.read()
    if MARKER in html:
        return 'skip'
    if 'ht-polywater v1' not in html or html.count(PW_MARK) != 1 or BR_MARK not in html:
        return 'skip-no-polywater-or-bridges'
    site = os.path.basename(path).split('-')[1]
    prof = (HT_RIVER_PROFILES.get(site) or {}).get('samples') or []
    if not prof:
        return 'skip-no-profile'
    m = re.search(r'window\.HT3D = \{[^}]*"lat":\s*(-?[\d.]+),\s*"lon":\s*(-?[\d.]+)', html)
    if not m:
        raise SystemExit(f'{path}: HT3D lat/lon not found')
    frame = Frame(float(m.group(1)), float(m.group(2)))
    pw_txt, pw_span = extract_json(html, PW_MARK)
    br_txt, _ = extract_json(html, BR_MARK)
    polywater = json.loads(pw_txt)
    bridges = json.loads(br_txt)
    if not bridges:
        return 'skip-no-crossings'
    profile = [(s[0], s[1]) for s in prof]
    try:
        cutter = PolyGapCutter(frame, profile, bridges)
        new_pw, stats = cutter.cut(polywater)
    except Exception as e:
        return f'FAILED-kept-original ({type(e).__name__}: {e})'
    a0 = net_area_m2(polywater, frame)
    a1 = net_area_m2(new_pw, frame)
    # Page-level catastrophe guard (a corrupted clip once added +130%
    # phantom water). The tolerance is relative because a cut edge is
    # stored as a straight chord where the true band edge follows the
    # curved path-normal line; the sagitta difference is a few hundred
    # m2 on a curving reach and is not phantom water - the geometry
    # audit on the triangulated result is the strict check.
    if a1 > a0 * 1.005 + 1000.0:
        return f'FAILED-kept-original (net area grew {a0:.0f} -> {a1:.0f})'
    new_txt = json.dumps(new_pw, separators=(',', ':'))
    html = html[:pw_span[0]] + new_txt + html[pw_span[1]:]
    i = html.index(PW_MARK)
    html = html[:i] + MARKER_LINE + html[i:]
    if html.count(MARKER) != 1:
        raise SystemExit(f'{path}: marker count wrong after splice')
    with open(path, 'w', encoding='utf8') as f:
        f.write(html)
    return (f"patched crossings_cut={stats['crossings_cut']}/{len(bridges)} "
            f"polys={stats['polys_before']}->{stats['polys_after']} "
            f"removed_m2={a0 - a1:.0f} rejected={stats['clips_rejected']}")


def main():
    root = sys.argv[1] if len(sys.argv) > 1 else 'stations'
    pages = sorted(glob.glob(os.path.join(root, 'USGS-*-3d.html')))
    if not pages:
        raise SystemExit(f'no station pages under {root}')
    for p in pages:
        print(patch(p), os.path.basename(p))


if __name__ == '__main__':
    main()
