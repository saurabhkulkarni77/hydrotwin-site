#!/usr/bin/env python3
"""Features affecting discharge flow (ht-featimp v1).

Adds an XGBoost feature-importance panel to every station page:

CLASSIC Data view: one section (after the Multi-factor correlation
section) with a horizontal bar chart of the top 15 features by gain
importance. 3D pages: the same chart in a floating panel created by
the boot (the ht-dacp pattern), gated behind the panel button bar by
patch_lazy_panels like the other satellite panels.

Data ships as lazy per-station sidecars featimp/<site>.json, generated
by train_xgb_featimp.py (hydrotwin models pipeline): one XGBoost
regressor per station trained on the COMBINED all-sources daily table
(USGS flow + Open-Meteo weather + NRCS SCAN soil + SNOTEL snow,
2016-2026) with same-day log discharge flow as target; inputs are
same-day weather/soil/snow plus lagged USGS flow. The sidecar carries
feature labels, source tags and gain shares; the chart colours bars
by source.

Idempotent with refresh, like the other build25 patchers: a page
already carrying the MARKER has its section/panel boot replaced in
place by the current text (the refresh also matches the
ht-lazypanels gated boot form; patch_lazy_panels re-gates it later
in the same deploy run). Run from the repo root:
python3 build25/patch_featimp.py
"""
import re
import sys
from pathlib import Path

MARKER = "ht-featimp v1"

CHART_JS = r"""
    const SRC_COLORS = { 'USGS': '#4EA8E0', 'Open-Meteo': '#E8A33D', 'Soil': '#7FB069', 'Snow': '#A8D8EA' };
    const render = (root, d) => {
      const feats = (d.features || []).slice(0, 15);
      const max = Math.max.apply(null, feats.map((f) => f.share).concat([0.0001]));
      let html = '';
      for (const f of feats) {
        const c = SRC_COLORS[f.source] || '#9FB3C8';
        const pct = (f.share * 100).toFixed(1);
        const w = Math.max(1.5, f.share / max * 100);
        html += '<div class="htfi-row">'
          + '<div class="htfi-lab">' + f.name + (f.unit ? ' (' + f.unit + ')' : '')
          + ' <span class="htfi-src" style="background:' + c + '">' + f.source + '</span></div>'
          + '<div class="htfi-track"><div class="htfi-fill" style="width:' + w.toFixed(1) + '%;background:' + c + '"></div></div>'
          + '<div class="htfi-pct">' + pct + '%</div></div>';
      }
      const legend = Object.keys(SRC_COLORS).map((k) =>
        '<span class="htfi-leg"><span class="htfi-dot" style="background:' + SRC_COLORS[k] + '"></span>' + k + '</span>').join('');
      html += '<div class="htfi-legend">' + legend + '</div>'
        + '<p class="htfi-meta">' + d.model + ' &middot; test R&sup2; ' + d.test_r2_log.toFixed(2)
        + ' (log flow) &middot; trained on ' + d.n_train.toLocaleString('en-US') + ' days, '
        + d.data + '.</p>';
      return html;
    };
"""

CHART_CSS = """
   .htfi-row{display:flex;align-items:center;gap:8px;margin:5px 0}
   .htfi-lab{flex:0 0 248px;font-size:12px;color:#E6EDF5}
   .htfi-src{display:inline-block;font-size:9.5px;font-weight:700;color:#0B1520;border-radius:4px;padding:0 5px;margin-left:4px;vertical-align:1px}
   .htfi-track{flex:1;height:13px;background:#16222F;border-radius:4px;overflow:hidden}
   .htfi-fill{height:100%;border-radius:4px}
   .htfi-pct{flex:0 0 46px;font-size:12px;color:#9FB3C8;text-align:right;font-family:Arial}
   .htfi-legend{display:flex;flex-wrap:wrap;gap:14px;margin-top:10px;font-size:11px;color:#9FB3C8}
   .htfi-dot{display:inline-block;width:9px;height:9px;border-radius:2px;margin-right:5px}
   .htfi-meta{font-size:11.5px;color:#9FB3C8;margin:8px 0 0}
   .htfi-loading{color:#9FB3C8;font-size:13px;padding:10px 0}
   @media (max-width:700px){.htfi-lab{flex-basis:150px}}
"""

SECTION = """
 <section class="hts-sec" id="hts-sec-featimp">
  <!-- ht-featimp v1 -->
  <h2>Features affecting discharge flow</h2>
  <p class="hts-note">Which inputs this station&rsquo;s XGBoost flow model leans on most. The model is trained per station on the combined daily record &mdash; USGS flow, Open-Meteo weather, NRCS soil and SNOTEL snow, 2016&ndash;2026 &mdash; to predict daily discharge flow, and each bar is a feature&rsquo;s share of the model&rsquo;s total gain importance. Yesterday&rsquo;s flow usually dominates: rivers remember. Importance is not causation, and a feature can matter by standing in for a season or a storm pattern.</p>
  <div id="htfi-root" data-site="__SITE__">
   <div class="htfi-loading" role="status">Loading feature importances&hellip;</div>
   <div class="htfi-chart" hidden></div>
  </div>
  <style>""" + CHART_CSS + """  </style>
 </section>"""

BOOT = """
<script>
// ht-featimp v1 boot: fetch the station's XGBoost feature-importance
// sidecar and render the bar chart.
{
  const root = document.getElementById('htfi-root');
  if (root) {
    const start = async () => {
      const loading = root.querySelector('.htfi-loading');
      try {
        const site = root.dataset.site;
        const resp = await fetch('../featimp/' + site + '.json');
        if (!resp.ok) throw new Error('sidecar ' + resp.status);
        const d = await resp.json();
        __CHART_JS__
        root.querySelector('.htfi-chart').innerHTML = render(root, d);
        loading.hidden = true;
        root.querySelector('.htfi-chart').hidden = false;
      } catch (e) {
        loading.textContent = 'Feature importances unavailable: ' + e.message;
        console.error(e);
      }
    };
    start();
  }
}
</script>
</body>"""

BOOT3D = """
<script>
// ht-featimp v1 boot: build the floating feature-importance panel and
// fill it from the station's XGBoost sidecar (gated behind the panel
// button bar by ht-lazypanels, like the other satellite panels).
{
  const m = location.pathname.match(/USGS-(\\d+)-3d\\.html/);
  if (m && !document.getElementById('htfi-panel')) {
    const css = '#htfi-panel{position:fixed;right:12px;top:118px;z-index:9997;width:min(430px,94vw);max-height:76vh;overflow:auto;background:rgba(12,18,28,.94);color:#e8eef5;border:1px solid rgba(255,255,255,.16);border-radius:12px;padding:12px 16px;font:12.5px/1.5 system-ui,-apple-system,Segoe UI,Roboto,sans-serif;box-shadow:0 8px 30px rgba(0,0,0,.45)}'
      + '#htfi-panel .htfi-t{font-weight:700;color:#8FC1F2;font-size:13.5px;margin-bottom:2px}'
      + '#htfi-panel .htfi-note{font-size:11.5px;color:#9FB3C8;margin:0 0 8px}'
      + __CHART_CSS_3D__;
    const st = document.createElement('style'); st.textContent = css;
    document.head.appendChild(st);
    const panel = document.createElement('div'); panel.id = 'htfi-panel';
    panel.innerHTML = '<div class="htfi-t">Features affecting discharge flow</div>'
      + '<p class="htfi-note">XGBoost model trained per station on the combined daily record (USGS flow, Open-Meteo weather, NRCS soil, SNOTEL snow, 2016\\u20132026); bars are gain-importance shares.</p>'
      + '<div class="htfi-loading" role="status">Loading feature importances\\u2026</div><div class="htfi-chart"></div>';
    document.body.appendChild(panel);
    (async () => {
      const loading = panel.querySelector('.htfi-loading');
      try {
        const resp = await fetch('../featimp/' + m[1] + '.json');
        if (!resp.ok) throw new Error('sidecar ' + resp.status);
        const d = await resp.json();
        __CHART_JS__
        panel.querySelector('.htfi-chart').innerHTML = render(panel, d);
        loading.hidden = true;
      } catch (e) {
        loading.textContent = 'Feature importances unavailable: ' + e.message;
        console.error(e);
      }
    })();
  }
}
</script>
</body>"""


def _css3d() -> str:
    out = CHART_CSS.replace("\n", " ").replace("'", "\\'")
    return "'" + out.strip() + "'"


BOOT = BOOT.replace("__CHART_JS__", CHART_JS.strip())
BOOT3D = (BOOT3D.replace("__CHART_JS__", CHART_JS.strip())
          .replace("__CHART_CSS_3D__", _css3d()))

ANCHOR_BODY = "</body>"

FI_SECTION_RE = re.compile(
    r' <section class="hts-sec(?: htlp-off)?" id="hts-sec-featimp">'
    r'(?:(?!</?section).)*</section>', re.S)
FI_BOOT_RE = re.compile(
    r'\n<script(?: type="text/plain" data-htlp-boot="featimp")?>\n'
    r'// ht-featimp v1 boot(?:(?!</?script).)*</script>', re.S)
CORR_SECTION_RE = re.compile(
    r' <section class="hts-sec(?: htlp-off)?" id="hts-sec-corr">'
    r'(?:(?!</?section).)*</section>', re.S)
SEC3DCHART_RE = re.compile(
    r' <section class="hts-sec(?: htlp-off)?" id="hts-sec-3dchart">'
    r'(?:(?!</?section).)*</section>', re.S)
BOOT_PAIR = BOOT.removesuffix("\n</body>")
BOOT3D_PAIR = BOOT3D.removesuffix("\n</body>")


def _check_common(s: str) -> str | None:
    for token in ("ht-drift-panel", 'id="ht-drift-panel"'):
        if token not in s:
            return f"FAIL post-check missing {token}"
    return None


def patch_classic(path: Path) -> str:
    s = path.read_text(encoding="utf-8")
    site = path.stem.replace("USGS-", "")
    if "ht-statsview v1" not in s:
        return "skip (not a Data view page)"
    if MARKER in s:
        secs = FI_SECTION_RE.findall(s)
        boots = FI_BOOT_RE.findall(s)
        if len(secs) != 1 or len(boots) != 1:
            return (f"FAIL refresh anchors: {len(secs)} section(s), "
                    f"{len(boots)} boot(s)")
        if "<section" in boots[0]:
            return "FAIL refresh boot span over-matched; refusing to write"
        s2 = FI_SECTION_RE.sub(
            lambda _: SECTION.lstrip("\n").replace("__SITE__", site),
            s, count=1)
        s2 = FI_BOOT_RE.sub(lambda _: BOOT_PAIR, s2, count=1)
        if s2 == s:
            return "skip (marker)"
        bad = _check_classic(s2)
        if bad:
            return bad
        path.write_text(s2, encoding="utf-8")
        return "refreshed"
    if s.count(ANCHOR_BODY) != 1:
        return f"FAIL anchor body: {s.count(ANCHOR_BODY)} occurrences"
    m = CORR_SECTION_RE.search(s) or SEC3DCHART_RE.search(s)
    if not m:
        return "FAIL anchor: no corr/3dchart section to follow"
    s = s[:m.end()] + SECTION.replace("__SITE__", site) + s[m.end():]
    s = s.replace(ANCHOR_BODY, BOOT, 1)
    bad = _check_classic(s)
    if bad:
        return bad
    path.write_text(s, encoding="utf-8")
    return "patched"


def _check_classic(s: str) -> str | None:
    bad = _check_common(s)
    if bad:
        return bad
    if s.count('id="hts-sec-featimp"') != 1 or s.count('id="htfi-root"') != 1:
        return "FAIL post-check: featimp section/root duplication"
    if s.count(MARKER) != 2:
        return f"FAIL post-check: marker count {s.count(MARKER)} (want 2)"
    return None


def patch_3d(path: Path) -> str:
    s = path.read_text(encoding="utf-8")
    if MARKER in s:
        boots = FI_BOOT_RE.findall(s)
        if len(boots) != 1:
            return f"FAIL refresh anchors: {len(boots)} boot(s)"
        if "<section" in boots[0]:
            return "FAIL refresh boot span over-matched; refusing to write"
        s2 = FI_BOOT_RE.sub(lambda _: BOOT3D_PAIR, s, count=1)
        if s2 == s:
            return "skip (marker)"
        bad = _check_3d(s2)
        if bad:
            return bad
        path.write_text(s2, encoding="utf-8")
        return "refreshed"
    if s.count(ANCHOR_BODY) != 1:
        return f"FAIL anchor body: {s.count(ANCHOR_BODY)} occurrences"
    s = s.replace(ANCHOR_BODY, BOOT3D, 1)
    bad = _check_3d(s)
    if bad:
        return bad
    path.write_text(s, encoding="utf-8")
    return "patched"


def _check_3d(s: str) -> str | None:
    bad = _check_common(s)
    if bad:
        return bad
    if s.count(MARKER) != 1:
        return f"FAIL post-check: marker count {s.count(MARKER)} (want 1)"
    if 'id="hts-top"' in s or 'id="hts-sec-featimp"' in s:
        return "FAIL post-check: classic featimp leaked into 3D page"
    return None


def main():
    root = Path("stations")
    files = sorted(root.glob("USGS-*.html"))
    if not files:
        print("no station pages found under stations/", file=sys.stderr)
        return 1
    bad = 0
    for p in files:
        r = patch_3d(p) if p.name.endswith("-3d.html") else patch_classic(p)
        print(f"{p.name}: {r}")
        if r.startswith("FAIL"):
            bad += 1
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
