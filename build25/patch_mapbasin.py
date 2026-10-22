#!/usr/bin/env python3
"""Basin information on the homepage map-pin hover card (ht-mapbasin v1).

User order (2026-10-21): the basin information shown on the 3D station
pages' Watershed panel should also be visible when hovering a station
pin on the homepage USA map.

What the hover card (desktop #card and the in-VR panel, both rendered
by show() in index.html) gains, per station:

  * a mini basin map: NLDI basin boundary (gold, as on the 3D pages),
    upstream path (light blue), downstream mainstem path (dark blue),
    and the gauge dot;
  * "Watershed area: N km2 (USGS drainage ...)" - the area uses the
    same spherical ring formula and the same simplified NLDI basin
    the 3D Watershed panel uses, so the numbers agree;
  * "River path: D km downstream / U km upstream" (the NLDI
    navigation distances the 3D pages fetch: DM 400 km, UM 150 km);
  * "Next gauges downstream" - up to 4 NWIS sites with distance,
    site id and name, computed exactly like the 3D panel (nearest
    point on the downstream path, within 5 km).

Data comes from basins/basins.json, baked offline by
build25/gen_basin_hover.py from USGS NLDI (basin + navigation
flowlines + downstream NWIS sites). The page fetches the sidecar
once; before it arrives the card shows "loading basin data..." and
the box refreshes itself when the fetch lands.

Implementation: exact-anchor edits inside show() (count-checked,
fail loudly) plus one marked style+script block before </body>
that is refreshed on every run, so the patcher is idempotent.
Only index.html is touched. Dev only, like every build25 patcher.
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PAGE = ROOT / "index.html"
MARKER = "ht-mapbasin v1"
BLOCK_START = "<!-- ht-mapbasin v1 start -->"
BLOCK_END = "<!-- ht-mapbasin v1 end -->"

BLOCK = BLOCK_START + """
<style>
#card{width:min(336px,88vw)}
#basinbox{margin-top:8px;border-top:1px solid rgba(140,190,240,.25);padding-top:7px}
#basinbox .bh{color:#8FC1F2;font-weight:600;margin-bottom:2px}
#basinbox canvas{width:100%;height:118px;margin:2px 0 4px}
#basinbox .bd{color:#BFD0E0;font-size:12px}
</style>
<script>
/* ht-mapbasin v1 - basin info on the homepage map-pin hover card.
   Data: basins/basins.json (USGS NLDI basin + NHDPlus V2 flowlines,
   baked by build25/gen_basin_hover.py). */
(function () {
  var B = null;
  function fmtN(n) { return n == null ? 'not available' : Math.round(n).toLocaleString('en-US'); }
  function esc(t) { return String(t == null ? '' : t).replace(/&/g, '&amp;').replace(/</g, '&lt;'); }
  function boxHTML(s) {
    var b = B && B[s.site];
    if (!B) return '<div class="bh">Basin</div><span class="bd">loading basin data&hellip;</span>';
    if (!b) return '<div class="bh">Basin</div><span class="bd">not available</span>';
    var h = '<div class="bh">Basin &middot; USGS NLDI</div><canvas id="bmap" width="560" height="230"></canvas>';
    h += '<span class="k">Watershed area:</span> ' + fmtN(b.area_km2) + ' km&sup2;' + (s.drainage ? ' (USGS drainage ' + esc(s.drainage) + ')' : '') + '<br>';
    h += '<span class="k">River path:</span> ' + fmtN(b.dm_km) + ' km downstream &middot; ' + fmtN(b.um_km) + ' km upstream<br>';
    h += '<span class="k">Next gauges downstream:</span>';
    if (b.down && b.down.length) b.down.forEach(function (d) { h += '<br><span class="bd">' + fmtN(d.km) + ' km &middot; USGS ' + esc(d.site) + ' &middot; ' + esc(String(d.name).slice(0, 40)) + '</span>'; });
    else h += '<br><span class="bd">none within the path shown</span>';
    return h;
  }
  window.htBasinHTML = function (s) { return '<div id="basinbox" data-site="' + s.site + '">' + boxHTML(s) + '</div>'; };
  window.htBasinLines = function (s) {
    var b = B && B[s.site]; if (!b) return [];
    var L = ['Basin: ' + fmtN(b.area_km2) + ' km\\u00b2 watershed \\u00b7 ' + fmtN(b.dm_km) + ' km downstream path'];
    if (b.down && b.down.length) { var d = b.down[0]; L.push('Next gauge downstream: ' + fmtN(d.km) + ' km \\u00b7 USGS ' + d.site); }
    return L;
  };
  window.htBasinDraw = function (cv, s) {
    var b = B && B[s.site]; if (!b || !b.rings || !b.rings.length) return;
    var g = cv.getContext('2d'), W = cv.width, H = cv.height;
    g.clearRect(0, 0, W, H); g.fillStyle = 'rgba(255,255,255,0.04)'; g.fillRect(0, 0, W, H);
    var pts = []; b.rings.forEach(function (r) { r.forEach(function (p) { pts.push(p); }); });
    (b.dm || []).forEach(function (p) { pts.push(p); }); (b.um || []).forEach(function (p) { pts.push(p); });
    pts.push([s.lon, s.lat]);
    var lo0 = Math.min.apply(null, pts.map(function (p) { return p[0]; })), lo1 = Math.max.apply(null, pts.map(function (p) { return p[0]; }));
    var la0 = Math.min.apply(null, pts.map(function (p) { return p[1]; })), la1 = Math.max.apply(null, pts.map(function (p) { return p[1]; }));
    var k = Math.cos((la0 + la1) / 2 * Math.PI / 180), sx = Math.max((lo1 - lo0) * k, 1e-6), sy = Math.max(la1 - la0, 1e-6);
    var sc = Math.min((W - 16) / sx, (H - 16) / sy), cx = W / 2, cy = H / 2;
    var X = function (lo) { return cx + (lo - (lo0 + lo1) / 2) * k * sc; }, Y = function (la) { return cy - (la - (la0 + la1) / 2) * sc; };
    function poly(p, stroke, w, fill) { if (!p || p.length < 2) return; g.beginPath(); p.forEach(function (q, n) { n ? g.lineTo(X(q[0]), Y(q[1])) : g.moveTo(X(q[0]), Y(q[1])); }); if (fill) { g.fillStyle = fill; g.fill(); } g.strokeStyle = stroke; g.lineWidth = w; g.stroke(); }
    b.rings.forEach(function (r) { poly(r, '#FFE680', 2, 'rgba(255,230,128,0.10)'); });
    poly(b.um, '#5CB8FF', 2); poly(b.dm, '#1E6FE0', 3);
    g.fillStyle = '#FFD24D'; g.beginPath(); g.arc(X(s.lon), Y(s.lat), 5, 0, 7); g.fill();
  };
  function refresh() {
    var box = document.getElementById('basinbox'); if (!box) return;
    var site = box.getAttribute('data-site');
    var st = (window.MAP && window.MAP.stations || []).filter(function (x) { return x.site === site; })[0];
    if (!st) return;
    box.innerHTML = boxHTML(st);
    var bc = document.getElementById('bmap'); if (bc) window.htBasinDraw(bc, st);
  }
  fetch('basins/basins.json', { cache: 'no-cache' }).then(function (r) { return r.json(); }).then(function (j) { B = j; refresh(); }).catch(function () { B = {}; refresh(); });
})();
</script>
""" + BLOCK_END

# One-time edits inside show(); skipped when the show()-side
# references are already present. (anchor, replacement, count)
RULES = [
    (
        """<canvas id="sp" width="560" height="110"></canvas><b>Click the pin to open ▶</b>`;""",
        """${window.htBasinHTML ? window.htBasinHTML(s) : ''}<canvas id="sp" width="560" height="110"></canvas><b>Click the pin to open ▶</b>`;""",
        1,
    ),
    (
        """const c = document.getElementById('sp'); spark(c.getContext('2d'), s, 4, 6, 552, 98, p.col); card.style.display = 'block';""",
        """const c = document.getElementById('sp'); spark(c.getContext('2d'), s, 4, 6, 552, 98, p.col); card.style.display = 'block';
  const bc = document.getElementById('bmap'); if (bc && window.htBasinDraw) window.htBasinDraw(bc, s);""",
        1,
    ),
    (
        """pg.fillText(`In the scene: ${s.model}${s.tidal ? ' · tidally filtered flow' : ''}`, 36, 255);""",
        """const bl = window.htBasinLines ? window.htBasinLines(s) : [];
  pg.font = '25px Arial'; pg.fillStyle = '#BFD0E0';
  bl.forEach((t, i) => pg.fillText(t, 36, 238 + i * 30));
  pg.font = '30px Arial'; pg.fillStyle = '#9FB3C8';
  pg.fillText(`In the scene: ${s.model}${s.tidal ? ' · tidally filtered flow' : ''}`, 36, 306);""",
        1,
    ),
    (
        """spark(pg, s, 36, 285, 828, 150, p.col);""",
        """spark(pg, s, 36, 330, 828, 108, p.col);""",
        1,
    ),
]

SHOW_FRAGMENTS = [
    "${window.htBasinHTML ? window.htBasinHTML(s)",
    "window.htBasinLines ? window.htBasinLines(s)",
    "const bc = document.getElementById('bmap'); if (bc && window.htBasinDraw)",
    "spark(pg, s, 36, 330, 828, 108, p.col);",
]


def main():
    if not PAGE.exists():
        print(f"!! {PAGE} not found")
        return 1
    html = PAGE.read_text(encoding="utf-8")
    out = html

    if all(f in out for f in SHOW_FRAGMENTS):
        print("  show() basin edits already present; skipping rules")
    else:
        for anchor, repl, want in RULES:
            n = out.count(anchor)
            if n != want:
                print(f"  !! anchor matched {n}x (want {want}): {anchor[:70]}...")
                return 1
            out = out.replace(anchor, repl)
        print("  show() basin edits applied")

    if BLOCK_START in out:
        out = re.sub(re.escape(BLOCK_START) + r".*?" + re.escape(BLOCK_END),
                     lambda m: BLOCK, out, flags=re.S)
        print("  loader block refreshed")
    else:
        i = out.rfind("</body>")
        if i < 0:
            print("  !! no </body> in index.html")
            return 1
        out = out[:i] + BLOCK + "\n" + out[i:]
        print("  loader block inserted")

    if out != html:
        PAGE.write_text(out, encoding="utf-8")
        print(f"index.html patched ({MARKER})")
    else:
        print("index.html unchanged")
    return 0


if __name__ == "__main__":
    sys.exit(main())
