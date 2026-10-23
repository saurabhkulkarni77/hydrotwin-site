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

Part 2 (ht-tuneanim-home v1, appended 2026-10-23): the homepage
edition of the "Optuna + Ray Tune" tuning badge that ht-tuneanim v1
(patch_livefix.py Part 5) put on the 14 3D station pages — Saurabh
approved extending it to the homepage. The homepage has no
model-button row, so the pill is parked directly under the #help
header box (the map header / MLOps-link area), positioned by its
script from the #help box's measured bottom edge. It polls the same
status JSON (hydrotwin-models Pages: tuning_status.json) about every
60 s and renders the same two states: RUNNING (amber glowing pill,
spinning gear, blinking dots, station + families being tuned) and
IDLE — on the homepage, the latest gated results across ALL stations
(the station whose newest family entry has the max `updated`
timestamp), naming both tools and each family's gate verdict.
Status unreachable: neutral idle pill naming both tools. A second
marked block before </body>, refreshed in place on every run
(idempotent, census-checked: badge id x1, marker x3).
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

# ---------------- part 2: ht-tuneanim-home v1 (homepage badge) --------
MARKER2 = "ht-tuneanim-home v1"
BLOCK2_START = "<!-- ht-tuneanim-home v1 start -->"
BLOCK2_END = "<!-- ht-tuneanim-home v1 end -->"

BLOCK2 = BLOCK2_START + r"""
<div id="tuneAnimBadge" class="htune htune-idle" role="status" title="Optuna + Ray Tune hyperparameter tuning (dev) — live status from the hydrotwin-models tuning registry"><span class="htune-gear" aria-hidden="true">⚙</span><span class="htune-txt" id="tuneAnimTxt">Optuna × Ray Tune · tuning status…</span><span class="htune-dots" aria-hidden="true"><i></i><i></i><i></i></span></div>
<style>
.htune{position:fixed;left:16px;top:300px;z-index:31;display:flex;align-items:center;gap:8px;max-width:min(640px,calc(100vw - 32px));padding:7px 14px;border-radius:999px;background:rgba(12,18,28,.88);border:1px solid #3A4A5E;color:#BFD0E0;font:600 13px Arial;box-shadow:0 2px 10px rgba(0,0,0,.4)}
.htune-txt{white-space:normal;line-height:1.35}
.htune-gear{display:inline-block;font-size:15px;line-height:1;color:#8FC1F2}
.htune-dots{display:none;gap:3px}
.htune-dots i{width:5px;height:5px;border-radius:50%;background:#FFB84D;display:inline-block;animation:htuneBlink 1.2s infinite}
.htune-dots i:nth-child(2){animation-delay:.2s}
.htune-dots i:nth-child(3){animation-delay:.4s}
.htune-run{border-color:#FFB84D;color:#FFE1A8;animation:htunePulse 1.6s ease-in-out infinite}
.htune-run .htune-gear{color:#FFB84D;animation:htuneSpin 2.2s linear infinite}
.htune-run .htune-dots{display:inline-flex}
.htune-pass{color:#7AE07A}
.htune-fail{color:#FF9A8A}
@keyframes htuneSpin{to{transform:rotate(360deg)}}
@keyframes htunePulse{0%,100%{box-shadow:0 2px 10px rgba(0,0,0,.4)}50%{box-shadow:0 0 14px 2px rgba(255,184,77,.45),0 2px 10px rgba(0,0,0,.4)}}
@keyframes htuneBlink{0%,80%,100%{opacity:.25}40%{opacity:1}}
</style>
<script>
/* ht-tuneanim-home v1 - homepage "Optuna + Ray Tune" tuning badge:
 * polls the tuning status JSON published from the hydrotwin-models
 * tuning registry (dev) to the models Pages source and renders an
 * animated RUNNING state while a tuning run is live, or the latest
 * quality-gate verdicts across all stations when idle. Homepage
 * edition of ht-tuneanim v1 (patch_livefix.py Part 5); the pill is
 * parked under the #help header box. */
(function () {
  'use strict';
  if (window.__httuneHomeOn) return;
  window.__httuneHomeOn = true;
  var STATUS_URL = 'https://saurabhkulkarni77.github.io/hydrotwin-models/tuning_status.json';
  var badge = document.getElementById('tuneAnimBadge');
  var txt = document.getElementById('tuneAnimTxt');
  if (!badge || !txt) return;

  function place() {
    var y = 16;
    var help = document.getElementById('help');
    if (help) {
      var r = help.getBoundingClientRect();
      if (r.height > 0) y = Math.ceil(r.bottom) + 8;
    }
    badge.style.top = y + 'px';
  }
  function fmtPct(x) {
    var n = Number(x);
    if (!isFinite(n)) return '';
    return (n > 0 ? '+' : '') + n.toFixed(2) + '%';
  }
  function safeName(t) { return /^[A-Za-z0-9][A-Za-z0-9 _-]*$/.test(t) ? t : ''; }
  function siteLabel(site) {
    var sts = (window.MAP && window.MAP.stations) || [];
    for (var i = 0; i < sts.length; i++) {
      if (sts[i].site === site) {
        var nm = sts[i].short || sts[i].name || '';
        return 'USGS ' + site + (nm ? ' (' + nm + ')' : '');
      }
    }
    return 'USGS ' + site;
  }
  function famParts(st, parts, tips) {
    Object.keys(st).forEach(function (fam) {
      var name = safeName(fam);
      var r = st[fam];
      if (!name || !r || !r.verdict) return;
      if (r.verdict === 'PASS') {
        parts.push(name + ' tuned · <span class="htune-pass">gate PASS ' +
          fmtPct(r.margin_pct) + '</span>');
      } else {
        parts.push(name + ' · <span class="htune-fail">gate FAIL — ' +
          'incumbent kept</span>');
      }
      tips.push(name + ': candidate RMSE ' + r.candidate_rmse +
        ' vs incumbent ' + r.incumbent_rmse + ' (WY2026 holdout), ' +
        r.trials + ' trials, gate ' + r.verdict + ' ' + fmtPct(r.margin_pct));
    });
  }

  function render(data) {
    if (data && data.running && data.current) {
      var c = data.current;
      var fams = (c.families || []).map(safeName).filter(Boolean).join(' + ');
      badge.classList.add('htune-run');
      badge.classList.remove('htune-idle');
      txt.textContent = 'Optuna × Ray Tune — TUNING ' + (c.station || '') +
        (fams ? ' · ' + fams : '') + ' now';
      badge.title = 'Hyperparameter tuning is RUNNING (dev): Optuna ' +
        '(TPE search) driven by Ray Tune (parallel trials + ASHA) on ' +
        'station ' + (c.station || '') + (fams ? ' — ' + fams : '') +
        '. A candidate must pass the quality gate to replace dev weights.';
      return;
    }
    badge.classList.remove('htune-run');
    badge.classList.add('htune-idle');
    var stations = (data && data.stations) || {};
    var bestSite = null, bestWhen = '';
    Object.keys(stations).forEach(function (site) {
      var st = stations[site] || {};
      Object.keys(st).forEach(function (fam) {
        var r = st[fam];
        if (r && r.updated && r.updated > bestWhen) {
          bestWhen = r.updated; bestSite = site;
        }
      });
    });
    if (bestSite) {
      var parts = [], tips = [];
      famParts(stations[bestSite], parts, tips);
      if (parts.length) {
        txt.innerHTML = 'Optuna × Ray Tune · latest — ' +
          siteLabel(bestSite) + ': ' + parts.join(' · ');
        badge.title = 'Latest tuning across HydroTwin stations (dev, ' +
          'Optuna + Ray Tune) — most recent gated run at ' +
          siteLabel(bestSite) + ': ' + tips.join('; ') +
          '. Each station page shows its own tuning results.';
        return;
      }
    }
    txt.textContent = 'Optuna × Ray Tune · hyperparameter tuning (dev)' +
      (data ? ' — no runs yet' : '');
    badge.title = 'Optuna + Ray Tune hyperparameter tuning runs in the ' +
      'hydrotwin-models dev environment; a candidate must beat the ' +
      'incumbent on the WY2026 holdout (quality gate) before it can ' +
      'replace dev weights.';
  }

  var got = false;
  function poll() {
    fetch(STATUS_URL + '?v=' + Date.now(), { cache: 'no-store' })
      .then(function (r) {
        if (!r.ok) throw new Error('http ' + r.status);
        return r.json();
      })
      .then(function (d) { got = true; render(d); },
            function () { if (!got) render(null); });
  }
  place();
  window.addEventListener('resize', place);
  setInterval(place, 5000);
  poll();
  setInterval(poll, 60000);
})();
</script>
""" + BLOCK2_END

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

    # --- part 2: ht-tuneanim-home v1 homepage tuning badge ---
    if BLOCK2_START in out:
        out = re.sub(re.escape(BLOCK2_START) + r".*?" + re.escape(BLOCK2_END),
                     lambda m: BLOCK2, out, flags=re.S)
        print("  homepage tuning badge refreshed")
    else:
        i = out.rfind("</body>")
        if i < 0:
            print("  !! no </body> in index.html")
            return 1
        out = out[:i] + BLOCK2 + "\n" + out[i:]
        print("  homepage tuning badge inserted")
    n_badge = out.count('id="tuneAnimBadge"')
    n_marker2 = out.count(MARKER2)
    if n_badge != 1 or n_marker2 != 3:
        print(f"  !! homepage badge census failed: badge={n_badge} "
              f"(want 1), {MARKER2}={n_marker2} (want 3)")
        return 1

    if out != html:
        PAGE.write_text(out, encoding="utf-8")
        print(f"index.html patched ({MARKER} + {MARKER2})")
    else:
        print("index.html unchanged")
    return 0


if __name__ == "__main__":
    sys.exit(main())
