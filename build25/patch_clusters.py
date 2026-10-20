#!/usr/bin/env python3
"""Station clusters in the classic Data view (ht-clusters v1).

Adds one section to the classic statistics pages (patch_statsview
layout): the flow-regime clustering of all 14 stations, baked offline
by gen_clusters.py into ONE shared sidecar, clusters/clusters.json
(k-means on standardized regime features, k = 5 by silhouette; Ward
hierarchical clustering for the dendrogram). The section shows:

  - regime curves: each cluster's mean monthly log-flow pattern with
    this station's own pattern overlaid (thick, dashed);
  - a scatter of all stations (peak-flow month vs mean log10 flow),
    colored by cluster, this station ringed;
  - the Ward dendrogram, leaves colored by cluster, cut line at k = 5;
  - a line naming this station's cluster and its sibling stations,
    plus a plain-language description of the cluster.

Placement: right after the correlation section (ht-corr) when the page
has one, else after the 3D chart section, else after the Drift section
(the same anchor chain patch_corr uses). Classic Data view pages only:
the file must not be a -3d page and must carry the ht-statsview
marker; the 3D terrain pages have no Data view sections and are never
touched (same rule as ht-corr / ht-3dchart). Vanilla JS + SVG only;
the sidecar is fetched lazily when the section nears the viewport.

Idempotent with refresh: a page already carrying the MARKER has its
existing clusters section and boot script replaced in place by the
current SECTION/BOOT text; if both are already current the page is
skipped unchanged.
Run from the repo root: python3 build25/patch_clusters.py
"""
import re
import sys
from pathlib import Path

MARKER = "ht-clusters v1"

SECTION = """
 <section class="hts-sec" id="hts-sec-clusters">
  <!-- ht-clusters v1 -->
  <h2>Station clusters</h2>
  <p class="hts-note">Fourteen stations, grouped by how their rivers behave &mdash; not by geography. Each station is described by its flow regime over the full daily record (2001&ndash;2026): average flow, flashiness, low-flow share, peak month, seasonal swing, plus soil moisture, soil temperature and snowpack from the NRCS gauges. A k-means clustering on those traits (k&nbsp;=&nbsp;5, chosen by silhouette score) finds five regimes; a Ward hierarchical clustering draws the family tree below.</p>
  <div id="htclusters-root" data-site="__SITE__">
   <div class="htclusters-loading" role="status">Loading the station clusters&hellip;</div>
   <div class="htclusters-wrap" hidden>
    <p class="htclusters-this" role="status"></p>
    <p class="htclusters-blurb hts-note"></p>
    <h3 class="htclusters-h">Regime curves &mdash; mean monthly flow by cluster</h3>
    <div class="htclusters-chart htclusters-curves"></div>
    <div class="htclusters-legend"></div>
    <h3 class="htclusters-h">Where the stations sit &mdash; peak month vs average flow</h3>
    <div class="htclusters-chart htclusters-scatter"></div>
    <h3 class="htclusters-h">Family tree &mdash; Ward dendrogram</h3>
    <div class="htclusters-chart htclusters-dendro"></div>
    <p class="htclusters-note hts-note"></p>
   </div>
  </div>
  <style>
   #htclusters-root .htclusters-h{font-size:13px;color:#E6EDF5;margin:16px 0 4px}
   #htclusters-root .htclusters-this{font-size:14px;color:#E6EDF5;margin:6px 0 2px}
   #htclusters-root .htclusters-this b{color:#FFD24D}
   #htclusters-root .htclusters-chart svg{width:100%;height:auto;display:block}
   #htclusters-root .htclusters-legend{display:flex;flex-wrap:wrap;gap:6px 14px;margin-top:6px;font-size:11px;color:#9FB3C8}
   #htclusters-root .htclusters-legend .sw{display:inline-block;width:10px;height:10px;border-radius:2px;margin-right:5px;vertical-align:-1px}
   #htclusters-root .htclusters-loading{color:#9FB3C8;font-size:13px;padding:10px 0}
   #htclusters-root .htclusters-note{margin-top:10px}
  </style>
 </section>"""

BOOT = """
<script>
// ht-clusters v1 boot: fetch the shared clusters sidecar and draw the
// regime curves, scatter and dendrogram when the section nears view.
{
  const root = document.getElementById('htclusters-root');
  if (root) {
    let started = false;
    const NS = 'http://www.w3.org/2000/svg';
    const MON = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
    const el = (tag, attrs, parent) => {
      const n = document.createElementNS(NS, tag);
      for (const k in attrs) n.setAttribute(k, attrs[k]);
      if (parent) parent.appendChild(n);
      return n;
    };
    const txt = (parent, x, y, s, attrs) => {
      const t = el('text', Object.assign({ x: x, y: y }, attrs || {}), parent);
      t.textContent = s;
      return t;
    };
    const fmtFlow = (v) => {
      const f = Math.pow(10, v);
      if (f >= 1000) return Math.round(f / 100) / 10 + 'k';
      return '' + Math.round(f);
    };
    const start = async () => {
      if (started) return; started = true;
      const loading = root.querySelector('.htclusters-loading');
      try {
        const site = root.dataset.site;
        const resp = await fetch('../clusters/clusters.json');
        if (!resp.ok) throw new Error('sidecar ' + resp.status);
        const d = await resp.json();
        const me = d.stations[site];
        if (!me) throw new Error('station not in sidecar');
        const myC = d.clusters[me.cluster];
        const sibs = myC.members.filter((s) => s !== site)
          .map((s) => d.stations[s].place);
        root.querySelector('.htclusters-this').innerHTML =
          'This station: <b>' + myC.label + '</b> &mdash; ' + myC.tag +
          (sibs.length
            ? ' &mdash; grouped with ' + sibs.join(', ') + '.'
            : ' &mdash; it stands alone; no other station groups with it.');
        root.querySelector('.htclusters-blurb').textContent = myC.blurb;
        const allCurves = [];
        d.clusters.forEach((c) => allCurves.push(c.monthly_log10));
        allCurves.push(me.monthly_log10);
        let lo = Infinity, hi = -Infinity;
        allCurves.forEach((cv) => cv.forEach((v) => {
          if (v < lo) lo = v; if (v > hi) hi = v;
        }));
        lo = Math.floor((lo - 0.08) * 10) / 10; hi = Math.ceil((hi + 0.08) * 10) / 10;

        // ---- regime curves -------------------------------------------
        {
          const W = 680, H = 216, L = 44, R = 8, T = 8, B = 24;
          const svg = el('svg', { viewBox: '0 0 ' + W + ' ' + H, role: 'img' },
            root.querySelector('.htclusters-curves'));
          const X = (m) => L + (m / 11) * (W - L - R);
          const Y = (v) => T + (1 - (v - lo) / (hi - lo)) * (H - T - B);
          for (let g = Math.ceil(lo * 2) / 2; g <= hi; g += 0.5) {
            el('line', { x1: L, x2: W - R, y1: Y(g), y2: Y(g), stroke: '#22344a', 'stroke-width': 1 }, svg);
            txt(svg, L - 5, Y(g) + 3, fmtFlow(g), { 'text-anchor': 'end', 'font-size': 9, fill: '#9FB3C8' });
          }
          for (let m = 0; m < 12; m++)
            txt(svg, X(m), H - 8, MON[m], { 'text-anchor': 'middle', 'font-size': 9, fill: '#9FB3C8' });
          txt(svg, 4, T + 8, 'cfs', { 'font-size': 9, fill: '#9FB3C8' });
          const line = (vals, attrs) => {
            const pts = vals.map((v, m) => X(m).toFixed(1) + ',' + Y(v).toFixed(1)).join(' ');
            el('polyline', Object.assign({ points: pts, fill: 'none' }, attrs), svg);
          };
          d.clusters.forEach((c) => {
            if (c.id !== me.cluster)
              line(c.monthly_log10, { stroke: c.color, 'stroke-width': 2, opacity: 0.75 });
          });
          line(myC.monthly_log10, { stroke: myC.color, 'stroke-width': 2.4, opacity: 0.95 });
          line(me.monthly_log10, { stroke: '#ffffff', 'stroke-width': 5, opacity: 0.35, 'stroke-dasharray': '7 4', 'stroke-linecap': 'round' });
          line(me.monthly_log10, { stroke: myC.color, 'stroke-width': 3.2, 'stroke-dasharray': '7 4', 'stroke-linecap': 'round' });
          me.monthly_log10.forEach((v, m) =>
            el('circle', { cx: X(m), cy: Y(v), r: 2.6, fill: myC.color, stroke: '#0b1622', 'stroke-width': 1 }, svg));
        }

        // ---- legend ---------------------------------------------------
        {
          const lg = root.querySelector('.htclusters-legend');
          let html = '';
          d.clusters.forEach((c) => {
            html += '<span><span class="sw" style="background:' + c.color + '"></span>' +
              c.label + ' (' + c.members.length + ')</span>';
          });
          html += '<span><span class="sw" style="background:transparent;border:2px dashed #ffffff"></span>This station (' + me.place + ')</span>';
          lg.innerHTML = html;
        }

        // ---- scatter --------------------------------------------------
        {
          const W = 680, H = 300, L = 44, R = 10, T = 10, B = 34;
          const svg = el('svg', { viewBox: '0 0 ' + W + ' ' + H, role: 'img' },
            root.querySelector('.htclusters-scatter'));
          let ylo = Infinity, yhi = -Infinity;
          Object.values(d.stations).forEach((s) => {
            const v = s.features.mean_log10_flow;
            if (v < ylo) ylo = v; if (v > yhi) yhi = v;
          });
          ylo = Math.floor((ylo - 0.15) * 10) / 10; yhi = Math.ceil((yhi + 0.15) * 10) / 10;
          const X = (m) => L + ((m - 1) / 11) * (W - L - R);
          const Y = (v) => T + (1 - (v - ylo) / (yhi - ylo)) * (H - T - B);
          for (let g = Math.ceil(ylo * 2) / 2; g <= yhi; g += 0.5) {
            el('line', { x1: L, x2: W - R, y1: Y(g), y2: Y(g), stroke: '#22344a', 'stroke-width': 1 }, svg);
            txt(svg, L - 5, Y(g) + 3, fmtFlow(g), { 'text-anchor': 'end', 'font-size': 9, fill: '#9FB3C8' });
          }
          for (let m = 1; m <= 12; m++)
            txt(svg, X(m), H - 18, MON[m - 1], { 'text-anchor': 'middle', 'font-size': 9, fill: '#9FB3C8' });
          txt(svg, (L + W - R) / 2, H - 4, 'Peak-flow month', { 'text-anchor': 'middle', 'font-size': 10, fill: '#9FB3C8' });
          const pts = Object.entries(d.stations).map(([s2, s]) => ({
            s2: s2, s: s, cx: X(s.features.peak_month),
            cy: Y(s.features.mean_log10_flow), ly: 0
          })).sort((a, b) => a.cy - b.cy);
          pts.forEach((p, i) => {
            p.ly = p.cy + 3;
            if (i > 0 && Math.abs(p.cx - pts[i - 1].cx) < 90 &&
                p.ly - pts[i - 1].ly < 12) p.ly = pts[i - 1].ly + 12;
          });
          pts.forEach((p) => {
            const c = d.clusters[p.s.cluster];
            if (p.s2 === site)
              el('circle', { cx: p.cx, cy: p.cy, r: 11.5, fill: 'none', stroke: '#ffffff', 'stroke-width': 2.4 }, svg);
            el('circle', { cx: p.cx, cy: p.cy, r: 6, fill: c.color, stroke: '#0b1622', 'stroke-width': 1.4 }, svg);
            const anchor = p.cx > W - 120 ? 'end' : 'start';
            const dx = anchor === 'end' ? -10 : 10;
            txt(svg, p.cx + dx, p.ly, p.s.place, {
              'text-anchor': anchor, 'font-size': 10.5,
              fill: p.s2 === site ? '#ffffff' : '#C7D3E2',
              'font-weight': p.s2 === site ? 'bold' : 'normal'
            });
          });
        }

        // ---- dendrogram ------------------------------------------------
        {
          const dg = d.dendrogram, sites = dg.leaf_sites, n = sites.length;
          const W = 680, T = 12, LAB = 58, H = T + 196 + LAB;
          const svg = el('svg', { viewBox: '0 0 ' + W + ' ' + H, role: 'img' },
            root.querySelector('.htclusters-dendro'));
          const pad = 26, slot = (W - 2 * pad) / n;
          const pos = {};
          dg.leaf_order.forEach((leaf, i) => { pos[leaf] = pad + (i + 0.5) * slot; });
          const heightOf = {};
          for (let i = 0; i < n; i++) heightOf[i] = 0;
          const Y = (h) => T + (1 - h / dg.max_height) * 196;
          const segs = [];
          dg.merges.forEach((mg, i) => {
            const node = n + i, a = mg[0], b = mg[1], h = mg[2];
            pos[node] = (pos[a] + pos[b]) / 2;
            heightOf[node] = h;
            segs.push([pos[a], Y(heightOf[a]), pos[a], Y(h)]);
            segs.push([pos[b], Y(heightOf[b]), pos[b], Y(h)]);
            segs.push([pos[a], Y(h), pos[b], Y(h)]);
          });
          segs.forEach((sg) => el('line', {
            x1: sg[0].toFixed(1), y1: sg[1].toFixed(1),
            x2: sg[2].toFixed(1), y2: sg[3].toFixed(1),
            stroke: '#5b7ba6', 'stroke-width': 1.4
          }, svg));
          el('line', {
            x1: 0, x2: W, y1: Y(dg.cut_height), y2: Y(dg.cut_height),
            stroke: '#FFD24D', 'stroke-width': 1.2, 'stroke-dasharray': '5 4', opacity: 0.85
          }, svg);
          txt(svg, W - 4, Y(dg.cut_height) - 4, 'cut at k = ' + d.k, {
            'text-anchor': 'end', 'font-size': 9.5, fill: '#FFD24D'
          });
          dg.leaf_order.forEach((leaf) => {
            const s = d.stations[sites[leaf]];
            const c = d.clusters[s.cluster];
            el('circle', { cx: pos[leaf], cy: Y(0), r: leaf === sites.indexOf(site) ? 4.6 : 3.4, fill: c.color, stroke: leaf === sites.indexOf(site) ? '#ffffff' : '#0b1622', 'stroke-width': leaf === sites.indexOf(site) ? 2 : 1 }, svg);
            const t = txt(svg, pos[leaf] - 3, Y(0) + 10, s.place, {
              'font-size': 9.5, fill: c.color, 'text-anchor': 'end',
              transform: 'rotate(-38 ' + pos[leaf] + ' ' + (Y(0) + 10) + ')'
            });
            if (sites[leaf] === site) t.setAttribute('font-weight', 'bold');
          });
        }

        root.querySelector('.htclusters-note').textContent =
          'Method: k-means (k = ' + d.k + ', silhouette ' + d.silhouette_chosen +
          ') on standardized features; Ward linkage above, dashed line = the cut that gives the same ' +
          d.k + ' groups. One station (Freeport) forms a regime of its own. ' +
          'Full feature values are in the shared sidecar (clusters/clusters.json).';
        loading.hidden = true;
        root.querySelector('.htclusters-wrap').hidden = false;
      } catch (e) {
        loading.textContent = 'Station clusters unavailable: ' + e.message;
        console.error(e);
      }
    };
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

ANCHOR_BODY = "</body>"

CLUS_SECTION_RE = re.compile(
    r' <section class="hts-sec" id="hts-sec-clusters">'
    r'(?:(?!</?section).)*</section>', re.S)
CLUS_BOOT_RE = re.compile(
    r'\n<script>\n// ht-clusters v1 boot(?:(?!</?script).)*</script>', re.S)
CORR_SECTION_RE = re.compile(
    r' <section class="hts-sec" id="hts-sec-corr">'
    r'(?:(?!</?section).)*</section>', re.S)
SEC3D_RE = re.compile(
    r' <section class="hts-sec" id="hts-sec-3dchart">'
    r'(?:(?!</?section).)*</section>', re.S)
ANCHOR_DRIFT = '<div id="hts-drift-slot"></div>\n </section>'
BOOT_PAIR = BOOT.removesuffix("\n</body>")


def post_checks(s: str) -> str | None:
    for token in ("ht-statsview v1", "ht-soilsnow v1", "ht-dacp v1",
                  "ht-weekly v1", "ht-uiux v1", "ht-drift-panel",
                  'id="ht-drift-panel"', "window.HT_DATA"):
        if token not in s:
            return f"FAIL post-check missing {token}"
    if s.count('id="hts-sec-clusters"') != 1 or \
            s.count('id="htclusters-root"') != 1:
        return "FAIL post-check: clusters section/root duplication"
    if s.count(MARKER) != 2:
        return f"FAIL post-check: marker count {s.count(MARKER)} (want 2)"
    return None


def patch(path: Path) -> str:
    s = path.read_text(encoding="utf-8")
    site = path.stem.replace("USGS-", "")
    if MARKER in s:
        secs = CLUS_SECTION_RE.findall(s)
        boots = CLUS_BOOT_RE.findall(s)
        if len(secs) != 1 or len(boots) != 1:
            return (f"FAIL refresh anchors: {len(secs)} section(s), "
                    f"{len(boots)} boot(s)")
        if "<section" in boots[0] or "ht-drift" in boots[0]:
            return "FAIL refresh boot span over-matched; refusing to write"
        s2 = CLUS_SECTION_RE.sub(
            lambda _: SECTION.lstrip("\n").replace("__SITE__", site),
            s, count=1)
        s2 = CLUS_BOOT_RE.sub(lambda _: BOOT_PAIR, s2, count=1)
        if s2 == s:
            return "skip (marker)"
        bad = post_checks(s2)
        if bad:
            return bad
        path.write_text(s2, encoding="utf-8")
        return "refreshed"
    if "ht-statsview v1" not in s:
        return "skip (not a Data view page)"
    if s.count(ANCHOR_BODY) != 1:
        return f"FAIL anchor body: {s.count(ANCHOR_BODY)} occurrences"
    m = CORR_SECTION_RE.search(s) or SEC3D_RE.search(s)
    if m:
        s = s[:m.end()] + SECTION.replace("__SITE__", site) + s[m.end():]
    else:
        if s.count(ANCHOR_DRIFT) != 1:
            return f"FAIL anchor drift: {s.count(ANCHOR_DRIFT)} occurrences"
        s = s.replace(ANCHOR_DRIFT,
                      ANCHOR_DRIFT + SECTION.replace("__SITE__", site), 1)
    s = s.replace(ANCHOR_BODY, BOOT, 1)
    bad = post_checks(s)
    if bad:
        return bad
    path.write_text(s, encoding="utf-8")
    return "patched"


def main():
    root = Path("stations")
    files = sorted(p for p in root.glob("USGS-*.html")
                   if not p.name.endswith("-3d.html"))
    if not files:
        print("no classic station pages found under stations/",
              file=sys.stderr)
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
