#!/usr/bin/env python3
"""Station clusters in the classic Data view (ht-clusters v1).

Adds one section to the classic statistics pages (patch_statsview
layout): the flow-regime clustering of all 14 stations, baked offline
by gen_clusters.py into ONE shared sidecar, clusters/clusters.json
(k-means on standardized regime features, k = 5 by silhouette; Ward
hierarchical clustering for the dendrogram). The section shows the
clusters themselves:

  - a PCA scatter of all stations in trait space (first two principal
    components of the same standardized features), colored by cluster
    with a shaded hull around each group, this station ringed;
  - a geographic map (US nation outline from the homepage's own
    window.MAP asset) with the stations plotted by lat/lon in the
    same cluster colors, this station ringed;
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
  <p class="hts-note">Fourteen stations, grouped by how their rivers behave &mdash; not by geography. Each station is described by its flow regime over the full daily record (2001&ndash;2026): average flow, flashiness, low-flow share, peak month, seasonal swing, plus soil moisture, soil temperature and snowpack from the NRCS gauges. A k-means clustering on those traits (k&nbsp;=&nbsp;5, chosen by silhouette score) finds five regimes. The first chart shows the groups themselves in trait space &mdash; the first two principal components of the same traits, so stations that plot close together genuinely behave alike; the map shows where each regime lives; a Ward hierarchical clustering draws the family tree below.</p>
  <div id="htclusters-root" data-site="__SITE__">
   <div class="htclusters-loading" role="status">Loading the station clusters&hellip;</div>
   <div class="htclusters-wrap" hidden>
    <p class="htclusters-this" role="status"></p>
    <p class="htclusters-blurb hts-note"></p>
    <h3 class="htclusters-h">The clusters &mdash; stations in trait space (PCA)</h3>
    <div class="htclusters-chart htclusters-pca"></div>
    <div class="htclusters-legend"></div>
    <h3 class="htclusters-h">Where the clusters live &mdash; station map</h3>
    <div class="htclusters-chart htclusters-map"></div>
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
// PCA cluster scatter, the station map and the dendrogram when the
// section nears view.
{
  const root = document.getElementById('htclusters-root');
  if (root) {
    let started = false;
    const NS = 'http://www.w3.org/2000/svg';
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
        // ---- PCA scatter: the clusters in trait space ------------------
        {
          const W = 680, H = 324, L = 48, R = 12, T = 12, B = 38;
          const svg = el('svg', { viewBox: '0 0 ' + W + ' ' + H, role: 'img' },
            root.querySelector('.htclusters-pca'));
          const pts = Object.entries(d.stations).map(([s2, st]) => ({
            s2: s2, st: st, px: st.pca[0], py: st.pca[1], cx: 0, cy: 0, ly: 0
          }));
          let xlo = Infinity, xhi = -Infinity, ylo = Infinity, yhi = -Infinity;
          pts.forEach((p) => {
            if (p.px < xlo) xlo = p.px; if (p.px > xhi) xhi = p.px;
            if (p.py < ylo) ylo = p.py; if (p.py > yhi) yhi = p.py;
          });
          const padx = (xhi - xlo) * 0.13 + 0.1, pady = (yhi - ylo) * 0.13 + 0.1;
          xlo -= padx; xhi += padx; ylo -= pady; yhi += pady;
          const X = (v) => L + ((v - xlo) / (xhi - xlo)) * (W - L - R);
          const Y = (v) => T + (1 - (v - ylo) / (yhi - ylo)) * (H - T - B);
          for (let g = Math.ceil(xlo); g <= Math.floor(xhi); g++) {
            el('line', { x1: X(g), x2: X(g), y1: T, y2: H - B, stroke: g === 0 ? '#33507a' : '#22344a', 'stroke-width': 1 }, svg);
            txt(svg, X(g), H - 24, '' + g, { 'text-anchor': 'middle', 'font-size': 9, fill: '#9FB3C8' });
          }
          for (let g = Math.ceil(ylo); g <= Math.floor(yhi); g++) {
            el('line', { x1: L, x2: W - R, y1: Y(g), y2: Y(g), stroke: g === 0 ? '#33507a' : '#22344a', 'stroke-width': 1 }, svg);
            txt(svg, L - 5, Y(g) + 3, '' + g, { 'text-anchor': 'end', 'font-size': 9, fill: '#9FB3C8' });
          }
          txt(svg, (L + W - R) / 2, H - 8,
            'PC1 \u2014 ' + d.pca.variance_pct[0].toFixed(1) + '% of variance \u00b7 snowpack & cold soils increase to the right',
            { 'text-anchor': 'middle', 'font-size': 10, fill: '#9FB3C8' });
          const ylab = txt(svg, 13, (T + H - B) / 2,
            'PC2 \u2014 ' + d.pca.variance_pct[1].toFixed(1) + '% \u00b7 bigger, steadier rivers higher',
            { 'text-anchor': 'middle', 'font-size': 10, fill: '#9FB3C8' });
          ylab.setAttribute('transform', 'rotate(-90 13 ' + ((T + H - B) / 2) + ')');
          // shaded hulls first, so points sit on top
          d.clusters.forEach((c) => {
            const hp = c.hull.map((s2) => d.stations[s2]);
            if (hp.length >= 3) {
              const mx = hp.reduce((a, st) => a + st.pca[0], 0) / hp.length;
              const my = hp.reduce((a, st) => a + st.pca[1], 0) / hp.length;
              const poly = hp.map((st) => {
                let vx = st.pca[0] - mx, vy = st.pca[1] - my;
                const len = Math.hypot(vx, vy) || 1; vx /= len; vy /= len;
                return X(st.pca[0] + vx * 0.38).toFixed(1) + ',' +
                       Y(st.pca[1] + vy * 0.38).toFixed(1);
              }).join(' ');
              el('polygon', { points: poly, fill: c.color, opacity: 0.13, stroke: c.color, 'stroke-opacity': 0.55, 'stroke-width': 1.2, 'stroke-dasharray': '5 4', 'stroke-linejoin': 'round' }, svg);
            } else if (hp.length === 2) {
              el('line', { x1: X(hp[0].pca[0]), y1: Y(hp[0].pca[1]), x2: X(hp[1].pca[0]), y2: Y(hp[1].pca[1]), stroke: c.color, 'stroke-width': 30, opacity: 0.13, 'stroke-linecap': 'round' }, svg);
            } else if (hp.length === 1) {
              el('circle', { cx: X(hp[0].pca[0]), cy: Y(hp[0].pca[1]), r: 22, fill: c.color, opacity: 0.15 }, svg);
            }
          });
          pts.forEach((p) => { p.cx = X(p.px); p.cy = Y(p.py); });
          const sp = pts.slice().sort((a, b) => a.cy - b.cy);
          sp.forEach((p, i2) => {
            p.ly = p.cy + 3;
            if (i2 > 0 && Math.abs(p.cx - sp[i2 - 1].cx) < 90 &&
                p.ly - sp[i2 - 1].ly < 12) p.ly = sp[i2 - 1].ly + 12;
          });
          sp.forEach((p) => {
            const c = d.clusters[p.st.cluster];
            if (p.s2 === site)
              el('circle', { cx: p.cx, cy: p.cy, r: 11.5, fill: 'none', stroke: '#ffffff', 'stroke-width': 2.4 }, svg);
            el('circle', { cx: p.cx, cy: p.cy, r: 6, fill: c.color, stroke: '#0b1622', 'stroke-width': 1.4 }, svg);
            const anchor = p.cx > W - 120 ? 'end' : 'start';
            const dx = anchor === 'end' ? -10 : 10;
            txt(svg, p.cx + dx, p.ly, p.st.place, {
              'text-anchor': anchor, 'font-size': 10.5,
              fill: p.s2 === site ? '#ffffff' : '#C7D3E2',
              'font-weight': p.s2 === site ? 'bold' : 'normal'
            });
          });
        }

        // ---- legend ---------------------------------------------------
        {
          const lg = root.querySelector('.htclusters-legend');
          let html = '';
          d.clusters.forEach((c) => {
            html += '<span><span class="sw" style="background:' + c.color + '"></span>' +
              c.label + ' (' + c.members.length + ')</span>';
          });
          html += '<span><span class="sw" style="background:transparent;border:2px solid #ffffff;border-radius:50%"></span>This station (' + me.place + ')</span>';
          lg.innerHTML = html;
        }

        // ---- geographic map --------------------------------------------
        {
          const MW = d.map.width, MH = d.map.height;
          const svg = el('svg', { viewBox: '0 0 ' + MW + ' ' + MH, role: 'img' },
            root.querySelector('.htclusters-map'));
          d.map.outline.forEach((line) => {
            el('path', {
              d: 'M' + line.map((q) => q[0] + ' ' + q[1]).join(' L') + ' Z',
              fill: '#132539', stroke: '#46618a', 'stroke-width': 1.6,
              'stroke-linejoin': 'round'
            }, svg);
          });
          Object.entries(d.stations).forEach(([s2, st]) => {
            const c = d.clusters[st.cluster];
            const x = st.map_xy[0], y = st.map_xy[1];
            if (s2 === site)
              el('circle', { cx: x, cy: y, r: 15, fill: 'none', stroke: '#ffffff', 'stroke-width': 3 }, svg);
            el('circle', { cx: x, cy: y, r: 8, fill: c.color, stroke: '#0b1622', 'stroke-width': 2 }, svg);
            const anchor = x > MW - 170 ? 'end' : 'start';
            const dx = anchor === 'end' ? -14 : 14;
            txt(svg, x + dx, y + 5, st.place, {
              'text-anchor': anchor, 'font-size': 19,
              fill: s2 === site ? '#ffffff' : '#C7D3E2',
              'font-weight': s2 === site ? 'bold' : 'normal'
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
          ') on standardized features. Trait space: the first two principal ' +
          'components of the same features (PC1 ' +
          d.pca.variance_pct[0].toFixed(1) + '%, PC2 ' +
          d.pca.variance_pct[1].toFixed(1) + '% of the variance); shaded ' +
          'hulls outline each cluster. Map: station locations on the US ' +
          'outline from the homepage map (us-atlas), colored by cluster. ' +
          'Ward linkage above, dashed line = the cut that gives the same ' +
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
