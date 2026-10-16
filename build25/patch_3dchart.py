#!/usr/bin/env python3
"""3D forecast chart in the classic Data view (DEV only).

Adds one section to the classic statistics pages (patch_statsview layout):
an interactive Three.js chart --
X = forecast target date, Y = estimated gauge height from the station's
stage-discharge fit (orange: forecast, blue: observed-flow estimate),
Z = an environmental input on the issue date (rainfall, soil moisture,
temperature, SWE). Controls select issue date, model, lead (1-7 days)
and the Z-axis variable; clicking an orange point selects its issue date.

Integration (string surgery, following the patch_soilsnow pattern):
  - the section markup is inserted right after the Drift section in the
    statsview layout; every existing section is left untouched;
  - shared code is NOT inlined: the chart modules and the vendored
    Three.js live once in assets/3dchart/ and are loaded by relative
    path through an import map; per-station data ships as lazy sidecars
    chart3d/<site>.json (same pattern as dacp/ and soilsnow/);
  - the boot script only installs an IntersectionObserver: the module
    bundle (~1.3 MB of Three.js) and the station sidecar are fetched
    when the section first scrolls into view, so page load is unchanged;
  - the chart code (graph.mjs, graph-data.mjs, data.mjs, labels.mjs,
    vendor three.module.js / OrbitControls.js) is included unmodified;
    only the host (assets/3dchart/embed.mjs) is adapted from the original
    app.mjs
    (one station per page, scoped element lookups, lazy mount).

Only classic Data view pages are patched: the file must not be a -3d
page and must already carry the ht-statsview marker. The 3D terrain
pages have their own scene and are never touched.

Idempotent with refresh: a page already carrying the MARKER has its
existing 3D-chart section and boot script replaced in place by the
current SECTION/BOOT text (so wording fixes in this file flow into
already-baked pages on the next deploy); if both are already current
the page is skipped unchanged.
Run from the repo root: python3 build25/patch_3dchart.py
"""
import re
import sys
from pathlib import Path

MARKER = "ht-3dchart v1"

SECTION = """
 <section class="hts-sec" id="hts-sec-3dchart">
  <!-- ht-3dchart v1 -->
  <h2>3D forecast chart</h2>
  <p class="hts-note">Interactive 3D chart built for the HydroTwin Field Lab. X: forecast target date &middot; Y: estimated gauge height (ft) &middot; Z: the selected environmental reading on the earlier issue date. Orange is the forecast, blue is the observed-flow estimate; each line joins forecasts from successive issue dates at the same lead. Both height curves come from this station&rsquo;s stage&ndash;discharge fit &mdash; they are estimates, not measured water levels, depth, or absolute elevation. Environmental readings show associations, not causation; soil and snow sensors can be far from the gauge.</p>
  <div id="ht3dc-root" data-site="__SITE__">
   <form class="ht3dc-form" aria-label="3D chart controls">
    <label>Forecast issued <input class="ht3dc-date" type="date"></label>
    <label>Model <select class="ht3dc-model"></select></label>
    <label>Lead (days) <select class="ht3dc-lead"></select></label>
    <label>Z-axis variable <select class="ht3dc-variable"></select></label>
    <button class="ht3dc-reset" type="button">Reset view</button>
   </form>
   <div class="ht3dc-main">
    <div class="ht3dc-viewport">
     <canvas class="ht3dc-canvas" aria-label="Drag to orbit, scroll to zoom, click a forecast point"></canvas>
     <div class="ht3dc-loading" role="status">Loading the 3D chart&hellip;</div>
     <div class="ht3dc-legend"><span class="ht3dc-dot ht3dc-orange"></span> Earlier forecast <span class="ht3dc-dot ht3dc-blue"></span> Observed-flow estimate</div>
     <p class="ht3dc-hint">Drag to orbit &middot; scroll to zoom &middot; click an orange point to select its issue date</p>
    </div>
    <aside class="ht3dc-details" aria-label="Selected forecast details">
     <p class="ht3dc-eyebrow">THE SELECTED EVENT</p>
     <h3 class="ht3dc-station-name">River notebook</h3>
     <dl>
      <dt>Target date</dt><dd class="ht3dc-target">&mdash;</dd>
      <dt>Predicted flow</dt><dd class="ht3dc-pred-flow">&mdash;</dd>
      <dt>Observed flow</dt><dd class="ht3dc-obs-flow">&mdash;</dd>
      <dt>Predicted gauge height</dt><dd class="ht3dc-pred-h">&mdash;</dd>
      <dt>Observed-flow gauge-height estimate</dt><dd class="ht3dc-obs-h">&mdash;</dd>
      <dt class="ht3dc-input-name">Selected input, at issue date</dt><dd class="ht3dc-input-value">&mdash;</dd>
     </dl>
     <p class="ht3dc-window" role="status"></p>
    </aside>
   </div>
  </div>
  <style>
   #ht3dc-root .ht3dc-form{display:flex;flex-wrap:wrap;align-items:end;gap:10px;margin:4px 0 12px}
   #ht3dc-root .ht3dc-form label{display:grid;gap:4px;font-size:12px;color:#9FB3C8}
   #ht3dc-root .ht3dc-form select,#ht3dc-root .ht3dc-form input{background:#0E1A24;color:#E8EEF5;border:1px solid #3A4A5E;border-radius:6px;font:600 13px Arial;padding:6px 8px}
   #ht3dc-root .ht3dc-form button{background:#23466E;color:#F5F6F2;border:1px solid #2E5A8A;border-radius:8px;padding:7px 12px;font:600 13px Arial;cursor:pointer}
   #ht3dc-root .ht3dc-form button:hover{background:#2E5A8A}
   #ht3dc-root .ht3dc-main{display:grid;grid-template-columns:minmax(0,1fr) 280px;gap:14px}
   @media (max-width:820px){#ht3dc-root .ht3dc-main{grid-template-columns:1fr}}
   #ht3dc-root .ht3dc-viewport{position:relative;height:470px;min-height:340px;border-radius:10px;overflow:hidden;background:#dbe7e9}
   #ht3dc-root .ht3dc-canvas{display:block;width:100%;height:100%;touch-action:none}
   #ht3dc-root .ht3dc-loading{position:absolute;inset:0;display:grid;place-items:center;background:#dbe7e9;color:#203e4b;font:600 14px Arial;padding:30px;text-align:center}
   #ht3dc-root .ht3dc-loading[hidden]{display:none}
   #ht3dc-root .ht3dc-legend,#ht3dc-root .ht3dc-hint{position:absolute;left:14px;right:14px;font-size:11px;pointer-events:none;color:#526f7b;margin:0}
   #ht3dc-root .ht3dc-legend{bottom:30px;display:flex;align-items:center;gap:6px}
   #ht3dc-root .ht3dc-hint{bottom:8px}
   #ht3dc-root .ht3dc-dot{width:9px;height:9px;border-radius:50%;display:inline-block}
   #ht3dc-root .ht3dc-orange{background:#d5793d}
   #ht3dc-root .ht3dc-blue{background:#247e9f;margin-left:10px}
   #ht3dc-root .ht3dc-details{background:#101E30;border:1px solid #22344C;border-radius:12px;padding:14px 16px}
   #ht3dc-root .ht3dc-eyebrow{margin:0;font-size:10px;font-weight:700;letter-spacing:1.3px;color:#8FC1F2}
   #ht3dc-root .ht3dc-station-name{margin:6px 0 10px;font-size:17px;color:#F5F6F2}
   #ht3dc-root .ht3dc-details dl{margin:0}
   #ht3dc-root .ht3dc-details dt{color:#9FB3C8;font-size:11px;margin-top:11px}
   #ht3dc-root .ht3dc-details dd{margin:3px 0 0;font-size:15.5px;font-weight:650;color:#E6EDF5}
   #ht3dc-root .ht3dc-window{color:#9FB3C8;font-size:11.5px;line-height:1.55;margin:12px 0 0}
  </style>
 </section>"""

BOOT = """
<script type="importmap">
{ "imports": { "three": "../assets/3dchart/three.module.js" } }
</script>
<script type="module">
// ht-3dchart v1 boot: mount the 3D chart only when its section nears the
// viewport, so the Three.js bundle and the station sidecar cost nothing
// until the reader actually scrolls to the chart.
{
  const root = document.getElementById('ht3dc-root');
  if (root) {
    const start = () => import('../assets/3dchart/embed.mjs')
      .then((m) => m.mount(root))
      .catch((e) => {
        const l = root.querySelector('.ht3dc-loading');
        if (l) { l.hidden = false; l.textContent = '3D chart unavailable: ' + e.message; }
        console.error(e);
      });
    if ('IntersectionObserver' in window) {
      const io = new IntersectionObserver((es) => {
        if (es.some((x) => x.isIntersecting)) { io.disconnect(); start(); }
      }, { rootMargin: '300px' });
      io.observe(root);
    } else start();
  }
}
</script>
</body>"""

ANCHOR_SECTION = '<div id="hts-drift-slot"></div>\n </section>'
ANCHOR_BODY = "</body>"

# Spans of a previously inserted section / boot script, for the refresh
# path. The section body contains no nested <section> and the boot block
# is the importmap + module script pair this patcher puts before </body>.
SECTION_RE = re.compile(
    r' <section class="hts-sec" id="hts-sec-3dchart">.*?</section>', re.S)
BOOT_RE = re.compile(
    r'\n<script type="importmap">\n'
    r'\{ "imports": \{ "three": "\.\./assets/3dchart/three\.module\.js" \} \}\n'
    r'</script>\n<script type="module">.*?</script>\n</body>', re.S)


def post_checks(s: str) -> str | None:
    for token in (MARKER, 'id="hts-sec-3dchart"', 'id="ht3dc-root"',
                  'id="hts-sec-hydro"', 'id="hts-sec-fc"', 'id="hts-sec-models"',
                  'id="hts-sec-ablation"', 'id="hts-sec-weekly"', 'id="hts-sec-drift"',
                  "ht-statsview v1", "ht-soilsnow v1", "ht-dacp v1", "ht-weekly v1",
                  "ht-drift-panel", "window.HT_DATA"):
        if token not in s:
            return f"FAIL post-check missing {token}"
    if s.count('id="ht3dc-root"') != 1 or s.count("ht-3dchart v1") != 2:
        return "FAIL post-check duplication"
    return None


def patch(path: Path) -> str:
    s = path.read_text(encoding="utf-8")
    site = path.stem.replace("USGS-", "")
    if MARKER in s:
        # Refresh path: swap the previously inserted section + boot for
        # the current text so source wording changes reach baked pages.
        secs = SECTION_RE.findall(s)
        boots = BOOT_RE.findall(s)
        if len(secs) != 1 or len(boots) != 1:
            return (f"FAIL refresh anchors: {len(secs)} section(s), "
                    f"{len(boots)} boot(s)")
        s2 = SECTION_RE.sub(lambda _: SECTION.lstrip("\n").replace(
            "__SITE__", site), s, count=1)
        s2 = BOOT_RE.sub(lambda _: BOOT, s2, count=1)
        if s2 == s:
            return "skip (marker)"
        bad = post_checks(s2)
        if bad:
            return bad
        path.write_text(s2, encoding="utf-8")
        return "refreshed"
    if "ht-statsview v1" not in s:
        return "skip (not a Data view page)"
    if s.count(ANCHOR_SECTION) != 1:
        return f"FAIL anchor section: {s.count(ANCHOR_SECTION)} occurrences"
    if s.count(ANCHOR_BODY) != 1:
        return f"FAIL anchor body: {s.count(ANCHOR_BODY)} occurrences"
    s = s.replace(ANCHOR_SECTION, ANCHOR_SECTION + SECTION.replace("__SITE__", site), 1)
    s = s.replace(ANCHOR_BODY, BOOT, 1)
    # post-checks: new section present once, all pre-existing sections intact
    bad = post_checks(s)
    if bad:
        return bad
    path.write_text(s, encoding="utf-8")
    return "patched"


def main():
    root = Path("stations")
    files = sorted(p for p in root.glob("USGS-*.html") if not p.name.endswith("-3d.html"))
    if not files:
        print("no classic station pages found under stations/", file=sys.stderr)
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
