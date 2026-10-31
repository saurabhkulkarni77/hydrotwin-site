#!/usr/bin/env python3
"""ht-charts3d v1: the Data view's charts in 3D (classic pages).

Adds one section, after the "Features affecting discharge flow"
section, holding a single interactive 3D canvas with a mode toggle:
  - Hydrograph: the last 365 days of the page's own window.HT_DATA
    flow series as a 3D line + ribbon (log scale, like the 2D
    overview), with hover points carrying exact date and flow.
  - Features: the top 15 features from the same featimp/<site>.json
    sidecar the 2D chart uses, as 3D bars coloured by source, with
    hover tooltips carrying the exact gain share.
The renderer lives once in assets/htcharts3d/htcharts3d.mjs and is
imported lazily when the section nears the viewport; no data is
inlined or hardcoded by this patcher.

Idempotent with refresh (the section/boot are replaced in place when
the marker is present). Run from the repo root:
python3 build25/patch_charts3d.py
"""
import re
import sys
from pathlib import Path

MARKER = "ht-charts3d v1"

SECTION = """
 <section class="hts-sec" id="hts-sec-charts3d">
  <!-- ht-charts3d v1 -->
  <h2>Data charts in 3D</h2>
  <p class="hts-note">The two charts above, rendered in 3D from exactly the same data: the hydrograph is the last 365 days of this station&rsquo;s flow record (log scale), and the bars are the XGBoost feature importances from the same sidecar as the 2D chart. Drag to orbit, scroll to zoom, hover a point or a bar to read its exact values.</p>
  <div id="htc3-root" data-site="__SITE__">
   <div class="htc3-ctl">
    <button type="button" class="htc3-mode htc3-on" data-mode="hydro">Hydrograph 3D</button>
    <button type="button" class="htc3-mode" data-mode="feat">Feature importance 3D</button>
   </div>
   <div class="htc3-view">
    <canvas class="htc3-canvas" aria-label="Interactive 3D chart: drag to orbit, scroll to zoom, hover for exact values"></canvas>
    <div class="htc3-loading" role="status">Loading the 3D charts&hellip;</div>
    <div class="htc3-tip" role="status"></div>
   </div>
  </div>
  <style>
   #htc3-root .htc3-ctl{display:flex;gap:8px;margin:4px 0 10px}
   #htc3-root .htc3-mode{background:#23466E;color:#F5F6F2;border:1px solid #2E5A8A;border-radius:8px;padding:7px 12px;font:600 13px Arial;cursor:pointer}
   #htc3-root .htc3-mode.htc3-on{background:#2E9B57;border-color:#7AE07A}
   #htc3-root .htc3-view{position:relative}
   #htc3-root .htc3-canvas{display:block;width:100%;height:440px;border-radius:10px;background:#0E1A24;cursor:grab;touch-action:none}
   #htc3-root .htc3-loading{position:absolute;left:14px;top:12px;color:#9FB3C8;font-size:13px}
   #htc3-root .htc3-loading[hidden]{display:none}
   #htc3-root .htc3-tip{position:absolute;display:none;background:rgba(11,19,29,.94);color:#E6EDF5;border:1px solid rgba(255,255,255,.25);border-radius:7px;padding:5px 9px;font:12.5px Arial;pointer-events:none;max-width:300px}
  </style>
 </section>"""

BOOT = """
<script>
// ht-charts3d v1 boot: import the 3D charts module only when the
// section nears the viewport.
{
  const root = document.getElementById('htc3-root');
  if (root) {
    const start = () => import('../assets/htcharts3d/htcharts3d.mjs')
      .then((m) => m.mount(root))
      .catch((e) => {
        const l = root.querySelector('.htc3-loading');
        if (l) { l.hidden = false; l.textContent = '3D charts unavailable: ' + e.message; }
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

FI_SECTION_RE = re.compile(
    r' <section class="hts-sec(?: htlp-off)?" id="hts-sec-featimp">'
    r'(?:(?!</?section).)*</section>', re.S)
C3_SECTION_RE = re.compile(
    r' <section class="hts-sec(?: htlp-off)?" id="hts-sec-charts3d">'
    r'(?:(?!</?section).)*</section>', re.S)
C3_BOOT_RE = re.compile(
    r'\n<script>\n// ht-charts3d v1 boot(?:(?!</?script).)*</script>', re.S)
BOOT_PAIR = BOOT.removesuffix("\n</body>")


def _check(s: str) -> str | None:
    if s.count('id="hts-sec-charts3d"') != 1 or s.count('id="htc3-root"') != 1:
        return "FAIL post-check: charts3d section/root duplication"
    if s.count(MARKER) != 2:
        return f"FAIL post-check: marker count {s.count(MARKER)} (want 2)"
    if 'id="hts-sec-featimp"' not in s or "window.HT_DATA" not in s:
        return "FAIL post-check: featimp section or HT_DATA missing"
    return None


def patch(path: Path) -> str:
    s = path.read_text(encoding="utf-8")
    site = path.stem.replace("USGS-", "")
    if "ht-statsview v1" not in s:
        return "skip (not a Data view page)"
    if MARKER in s:
        secs = C3_SECTION_RE.findall(s)
        boots = C3_BOOT_RE.findall(s)
        if len(secs) != 1 or len(boots) != 1:
            return f"FAIL refresh anchors: {len(secs)} section(s), {len(boots)} boot(s)"
        if "<section" in boots[0]:
            return "FAIL refresh boot span over-matched; refusing to write"
        s2 = C3_SECTION_RE.sub(lambda _: SECTION.lstrip("\n").replace("__SITE__", site), s, count=1)
        s2 = C3_BOOT_RE.sub(lambda _: BOOT_PAIR, s2, count=1)
        if s2 == s:
            return "skip (marker)"
        bad = _check(s2)
        if bad:
            return bad
        path.write_text(s2, encoding="utf-8")
        return "refreshed"
    m = FI_SECTION_RE.search(s)
    if not m:
        return "FAIL anchor: no featimp section to follow"
    if s.count("</body>") != 1:
        return f"FAIL anchor body: {s.count('</body>')} occurrences"
    s = s[:m.end()] + SECTION.replace("__SITE__", site) + s[m.end():]
    s = s.replace("</body>", BOOT, 1)
    bad = _check(s)
    if bad:
        return bad
    path.write_text(s, encoding="utf-8")
    return "patched"


def main():
    files = sorted(p for p in Path("stations").glob("USGS-*.html")
                   if not p.name.endswith("-3d.html"))
    if not files:
        print("no classic station pages found", file=sys.stderr)
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
