#!/usr/bin/env python3
"""Yearly model COMPARE panel for the DEV station pages.

Sibling of build25/patch_compare_wm.py (deploy step 18), which added
the daily-style model comparison to the weekly and monthly outlooks.
The yearly outlook (build25/patch_yearly.py) ships with the Flow &
forecast panel treatment; this patcher adds the equivalent
multi-model compare to it, on all 28 pages (14 classic + 14 3D):

  * a "Δ Compare models" toggle button in the yearly outlook's
    control row;
  * a checkbox list of every model in the baked yearly sidecar, with
    colour swatches (same palette/order as the daily compare), full
    model names (ht-fullforms map) and the pooled test RMSE next to
    each model (read at runtime from window.__yrMeta — the yearly
    panel's own leaderboard data, nothing hardcoded);
  * default selection = top 3 models by pooled RMSE;
  * an overlay chart (log scale, same axes style as the outlook
    panels): observed context blocks, observed outcomes (dashed) and
    one coloured forecast line per selected model;
  * a comparison table: rows = leads (Mo 1..12), columns = period,
    observed outcome (where the record has it) and each selected
    model's baked forecast for the selected issue date.

Data comes ONLY from the sidecar the yearly patcher already ships
(../yearly/<site>.json — the same fetch the panel itself makes; the
browser caches it). No new models, no retraining. Climatology /
Persistence appear in the yearly leaderboard as reference rows but
have no baked per-date forecasts in the sidecar, so they are not
compare-selectable (nothing to plot).

Live mode: live yearly runs exist only for the 5 neural models and
only for the single selected model, so compare is baked-only. When
the yearly panel above is showing a LIVE run (its issue line reads
"LIVE outlook …"), the compare block says so explicitly and shows
the baked comparison for the selected date — baked data is never
presented as the live run.

Append-only: one script before </body>, no existing code edited.
Idempotent: pages carrying the MARKER are skipped. Pages missing the
yearly / livefix markers (pipeline order broken) are skipped with a
warning rather than written.
Run from the repo root: python3 build25/patch_compare_y.py
"""
import sys
from pathlib import Path

MARKER = "ht-cmpy v1"
NEED = ("ht-yearly v1", "ht-livefix v2")

JS_BODY = r"""
<script>
/* ht-cmpy v1 - Yearly model compare panel (dev).
 * Adds a "Δ Compare models" toggle to the yearly outlook control row:
 * model checkboxes (full names + pooled test RMSE from the panel's
 * own __yrMeta), an overlay chart and a per-lead comparison table,
 * all from the baked yearly sidecar the panel already loads.
 * Baked-only: in Live mode it labels itself as the baked comparison
 * for the selected date. See build25/patch_compare_y.py. */
(function () {
  var FULL = {'ARIMA': 'Autoregressive Integrated Moving Average', 'SARIMA': 'Seasonal Autoregressive Integrated Moving Average', 'GP Matérn': 'Gaussian Process (Matérn kernel)', 'GP RBF': 'Gaussian Process (Radial Basis Function kernel)', 'LSTM': 'Long Short-Term Memory network', 'Transformer': 'Transformer (self-attention neural network)', 'TFT': 'Temporal Fusion Transformer', 'PatchTST': 'Patch Time-Series Transformer', 'GCN': 'Graph Convolutional Network', 'PILSTMv1': 'Physics-Informed LSTM, version 1'};
  var COL = ['#2F80D1', '#E0852A', '#9E61CC', '#D1495B', '#8A8F98', '#1BA3A3', '#E36BA8', '#4D6E8A', '#FFD24D', '#29B6F6', '#9CCC65', '#FF7043'];
  function full(n) { return FULL[n] ? n + ' — ' + FULL[n] : n; }
  function $(id) { return document.getElementById(id); }
  function fmt(v) { return (v == null || !isFinite(v)) ? '–' : Math.round(v).toLocaleString('en-US'); }
  function pay() {
    try {
      if (window.HT_DATA) { var D = window.HT_DATA; return { models: D.models, flow: D.flow, start: D.start, site: (D.station && D.station.stationId || '').replace('USGS-', '') }; }
      if (window.HT3D) { var E = window.HT3D; return { models: E.models, flow: E.flow, start: E.start, site: E.site }; }
    } catch (e) {}
    return null;
  }
  function isoOf(P, i) { return new Date(Date.parse(P.start + 'T00:00:00Z') + i * 864e5).toISOString().slice(0, 10); }
  function addDays(iso, k) { return new Date(Date.parse(iso + 'T00:00:00Z') + k * 864e5).toISOString().slice(0, 10); }
  function blockMean(flow, endIdx, span, minN) {
    if (endIdx < span - 1 || endIdx >= flow.length) return null;
    var s = 0, c = 0;
    for (var j = endIdx - span + 1; j <= endIdx; j++) { var v = flow[j]; if (v != null && v > 0) { s += v; c++; } }
    return c >= minN ? s / c : null;
  }
  function colorFor(P, name) {
    var i = P && P.models ? P.models.indexOf(name) : -1;
    if (i < 0) i = 0;
    return COL[i % COL.length];
  }

  function makeCmp(cfg) {
    var C = { data: null, idx: null, err: false, sel: null, open: false, wired: false, tries: 0 };
    function meta() { try { return cfg.meta() || {}; } catch (e) { return {}; } }
    function root() { return $(cfg.root); }
    function load() {
      var P = pay(); if (!P || !P.site || C.data || C.err || C.busy) return;
      C.busy = true;
      fetch(cfg.dir + P.site + '.json').then(function (r) { if (!r.ok) throw new Error('http ' + r.status); return r.json(); })
        .then(function (j) {
          C.busy = false;
          C.data = j; C.idx = {};
          j.dates.forEach(function (d, i) { C.idx[d] = i; });
          if (!C.sel) {
            var L = meta().leader || {};
            var ranked = j.models.slice().sort(function (a, b) { return (L[a] == null ? 1e9 : L[a]) - (L[b] == null ? 1e9 : L[b]); });
            C.sel = {}; ranked.slice(0, 3).forEach(function (m) { C.sel[m] = true; });
          }
          render();
        })
        .catch(function () { C.busy = false; C.err = true; render(); setTimeout(function () { C.err = false; }, 4000); });
    }
    function isLive() {
      var el = $(cfg.issue);
      return !!(el && el.textContent && el.textContent.indexOf('LIVE outlook') === 0);
    }
    function checksHTML() {
      var L = meta().leader || {};
      var names = C.data.models.slice().sort(function (a, b) { return (L[a] == null ? 1e9 : L[a]) - (L[b] == null ? 1e9 : L[b]); });
      var P = pay();
      return names.map(function (n) {
        var on = C.sel && C.sel[n];
        return '<label class="htcmp-row"><input type="checkbox" data-cm="' + n + '"' + (on ? ' checked' : '') + '>'
          + '<span class="htcmp-sw" style="background:' + colorFor(P, n) + '"></span>'
          + '<span class="htcmp-nm">' + full(n) + '</span>'
          + '<span class="htcmp-rm">' + (L[n] != null ? 'pooled RMSE ' + L[n].toFixed(4) : '') + '</span></label>';
      }).join('');
    }
    function draw(cv, ctx, act, series) {
      var g = cv.getContext('2d'); if (!g) return;
      var cw = cv.width, ch = cv.height;
      g.clearRect(0, 0, cw, ch);
      var vals = [];
      ctx.concat(act).forEach(function (p) { if (p[1] != null) vals.push(p[1]); });
      series.forEach(function (s) { s.pts.forEach(function (p) { if (p[1] != null) vals.push(p[1]); }); });
      if (!vals.length) { g.fillStyle = '#9fb4c8'; g.font = '22px system-ui'; g.fillText('no data for this date', 18, 40); return; }
      var lo = Math.floor(Math.log10(Math.min.apply(null, vals))), hi = Math.ceil(Math.log10(Math.max.apply(null, vals)));
      if (hi <= lo) hi = lo + 1;
      var X0 = 64, X1 = cw - 14, Y0 = 12, Y1 = ch - 30;
      function X(x) { return X0 + (x - cfg.xMin) / cfg.xSpan * (X1 - X0); }
      function Y(v) { var t = (Math.log10(Math.max(v, 1e-9)) - lo) / (hi - lo); return Y1 - t * (Y1 - Y0); }
      g.font = '19px system-ui'; g.textBaseline = 'middle';
      for (var e = lo; e <= hi; e++) {
        var yv = Math.pow(10, e), yy = Y(yv);
        g.strokeStyle = 'rgba(255,255,255,.13)'; g.beginPath(); g.moveTo(X0, yy); g.lineTo(X1, yy); g.stroke();
        g.fillStyle = '#9fb4c8'; g.fillText(fmt(yv), 6, yy);
      }
      g.strokeStyle = 'rgba(255,255,255,.3)'; g.beginPath(); g.moveTo(X(0), Y0); g.lineTo(X(0), Y1); g.stroke();
      g.fillStyle = '#9fb4c8';
      cfg.ticks.forEach(function (x) { g.fillText(x === 0 ? 'issue' : (x > 0 ? '+' + x + cfg.tickUnit : x + cfg.tickUnit), X(x) - 10, Y1 + 15); });
      function line(pts, style, width, dash) {
        g.save(); g.strokeStyle = style; g.lineWidth = width; g.setLineDash(dash || []);
        g.beginPath(); var started = false;
        pts.forEach(function (p) { if (p[1] == null) { started = false; return; } var xx = X(p[0]), yy2 = Y(p[1]); if (!started) { g.moveTo(xx, yy2); started = true; } else g.lineTo(xx, yy2); });
        g.stroke(); g.restore();
      }
      line(ctx, '#9fb4c8', 2);
      if (act.length) line(act, 'rgba(255,255,255,.85)', 2, [6, 5]);
      var lastC = ctx.length ? ctx[ctx.length - 1] : null;
      series.forEach(function (s) {
        var pts = s.pts.slice();
        if (lastC && lastC[1] != null) pts = [[0, lastC[1]]].concat(pts);
        line(pts, s.color, 2.5);
      });
      g.fillStyle = '#9fb4c8'; var obsTxt = '— observed'; g.fillText(obsTxt, X(cfg.xMin + 0.4), Y0 + 10);
      if (act.length) { g.fillStyle = '#fff'; g.fillText('- - actual outcome', X(cfg.xMin + 0.4) + g.measureText(obsTxt).width + 16, Y0 + 10); }
    }
    function render() {
      var box = $(cfg.box); if (!box || !C.open) return;
      var P = pay(), S = window.__htS;
      if (!P) { box.innerHTML = '<div class="htcmp-note">compare unavailable on this page</div>'; return; }
      if (C.err) { box.innerHTML = '<div class="htcmp-note">compare unavailable (baked ' + cfg.noun + ' forecasts sidecar missing)</div>'; return; }
      if (!C.data) { box.innerHTML = '<div class="htcmp-note">loading compare data…</div>'; load(); return; }
      if (!S) return;
      var day = S.day, issue = isoOf(P, day);
      var html = '';
      if (isLive()) html += '<div class="htcmp-live">The panel above is showing a LIVE run — this comparison uses the baked outlook for the selected date (issue ' + issue + '), not the live run.</div>';
      html += '<div class="htcmp-list">' + checksHTML() + '</div>';
      var di = C.idx[issue];
      if (di == null) {
        html += '<div class="htcmp-note">No baked ' + cfg.noun + ' forecast for ' + issue + ' — compare covers ' + C.data.dates[0] + ' … ' + C.data.dates[C.data.dates.length - 1] + '. Pick a date in that range.</div>';
        box.innerHTML = html; wireChecks(box); return;
      }
      var L2 = meta().leader || {};
      var selNames = C.data.models.filter(function (m) { return C.sel && C.sel[m]; })
        .sort(function (a, b) { return (L2[a] == null ? 1e9 : L2[a]) - (L2[b] == null ? 1e9 : L2[b]); });
      var ctx = [], act = [];
      for (var j = cfg.ctxBlocks; j >= 1; j--) ctx.push([-j, blockMean(P.flow, day - cfg.block * (j - 1), cfg.block, cfg.minN)]);
      for (var k = 1; k <= cfg.leads; k++) { var am = blockMean(P.flow, day + cfg.block * k, cfg.block, cfg.minN); if (am != null) act.push([k, am]); }
      var series = selNames.map(function (m) {
        var row = (C.data.predw[m] && C.data.predw[m][di]) || [];
        return { name: m, color: colorFor(P, m), pts: row.map(function (v, kk) { return [kk + 1, v]; }) };
      });
      html += '<div class="htcmp-leg">' + series.map(function (s) {
        return '<span class="htcmp-chip"><span class="htcmp-sw" style="background:' + s.color + '"></span>' + s.name + '</span>';
      }).join('') + (act.length ? '<span class="htcmp-chip"><span class="htcmp-sw" style="background:#fff"></span>Observed</span>' : '') + '</div>';
      html += '<canvas class="htcmp-cv" id="' + cfg.cv + '" width="760" height="300"></canvas>';
      html += '<table class="htcmp-t"><tr><th>' + cfg.leadName + '</th><th>' + cfg.periodName + '</th><th>Observed</th>'
        + series.map(function (s) { return '<th style="color:' + s.color + '">' + s.name + '</th>'; }).join('') + '</tr>';
      for (var r = 0; r < cfg.leads; r++) {
        var a = blockMean(P.flow, day + cfg.block * (r + 1), cfg.block, cfg.minN);
        html += '<tr><td>' + (r + 1) + '</td><td>' + addDays(issue, cfg.block * r + 1).slice(5) + ' – ' + addDays(issue, cfg.block * (r + 1)).slice(5) + '</td><td>' + fmt(a) + '</td>'
          + series.map(function (s) { return '<td>' + fmt(s.pts[r] ? s.pts[r][1] : null) + '</td>'; }).join('') + '</tr>';
      }
      html += '</table><div class="htcmp-note">cfs, ' + cfg.unitNote + ' · issue date ' + issue + ' · baked outlook (all models, same date) — RMSE in the list above is the pooled test RMSE (log space), all 14 stations</div>';
      box.innerHTML = html;
      wireChecks(box);
      var cv = $(cfg.cv);
      if (cv) draw(cv, ctx, act, series);
    }
    function wireChecks(box) {
      box.querySelectorAll('input[data-cm]').forEach(function (cb) {
        cb.addEventListener('change', function () {
          if (!C.sel) C.sel = {};
          C.sel[this.getAttribute('data-cm')] = this.checked;
          render();
        });
      });
    }
    function wire() {
      var r = root(); if (!r) return false;
      var ctl = r.querySelector('.' + cfg.ctlCls); if (!ctl) return false;
      if ($(cfg.btn)) { C.wired = true; return true; }
      var b = document.createElement('button');
      b.type = 'button'; b.id = cfg.btn; b.textContent = 'Δ Compare models';
      b.title = 'Overlay the baked ' + cfg.noun + ' forecasts of several models for the selected date';
      ctl.appendChild(b);
      var box = document.createElement('div');
      box.id = cfg.box; box.className = 'htcmp'; box.style.display = 'none';
      ctl.parentNode.insertBefore(box, ctl.nextSibling);
      b.addEventListener('click', function () {
        C.open = !C.open;
        box.style.display = C.open ? '' : 'none';
        b.classList.toggle('htcmp-open', C.open);
        if (C.open) { load(); render(); }
      });
      C.wired = true;
      return true;
    }
    var lastKey = '';
    var timer = setInterval(function () {
      if (!C.wired) { C.tries++; if (wire() || C.tries > 40) { if (C.wired) C.tries = 0; } }
      if (!C.open) return;
      load();
      var S = window.__htS; if (!S) return;
      var key = S.day + '|' + (isLive() ? 1 : 0) + '|' + (C.data ? 1 : 0) + '|' + (C.err ? 1 : 0) + '|'
        + (C.sel ? Object.keys(C.sel).filter(function (m) { return C.sel[m]; }).sort().join(',') : '');
      if (key !== lastKey) { lastKey = key; render(); }
    }, 700);
    wire();
    return C;
  }

  var css = '.htcmp{margin:8px 0 4px;border:1px solid rgba(255,255,255,.16);border-radius:8px;padding:8px 10px;background:rgba(255,255,255,.03)}'
    + '.htcmp-list{display:flex;flex-direction:column;gap:2px;margin-bottom:8px}'
    + '.htcmp-row{display:flex;align-items:center;gap:8px;cursor:pointer;padding:2px 4px;font-size:12.5px}'
    + '.htcmp-row input{width:15px;height:15px;flex:none}'
    + '.htcmp-sw{width:13px;height:13px;border-radius:4px;display:inline-block;flex:none}'
    + '.htcmp-nm{color:#e8eef5}'
    + '.htcmp-rm{margin-left:auto;font-size:11.5px;color:#9FB3C8;white-space:nowrap}'
    + '.htcmp-leg{display:flex;gap:12px;flex-wrap:wrap;margin:4px 0 6px;font-size:12px;color:#BFD0E0}'
    + '.htcmp-chip{display:inline-flex;align-items:center;gap:5px}'
    + '.htcmp-cv{width:100%;height:auto;display:block;background:rgba(255,255,255,.03);border:1px solid rgba(255,255,255,.12);border-radius:8px}'
    + '.htcmp-t{border-collapse:collapse;width:100%;font-size:12px;margin-top:6px}'
    + '.htcmp-t th,.htcmp-t td{border-bottom:1px solid rgba(255,255,255,.12);padding:2px 6px;text-align:right}'
    + '.htcmp-t th:first-child,.htcmp-t td:first-child,.htcmp-t td:nth-child(2){text-align:left}'
    + '.htcmp-note{opacity:.85;font-size:12px;margin-top:6px}'
    + '.htcmp-live{font-size:12px;color:#FFD24D;border:1px solid rgba(255,210,77,.45);border-radius:6px;padding:4px 8px;margin-bottom:8px}'
    + 'button.htcmp-open{background:#23466E !important;border-color:#8FC1F2 !important;color:#8FC1F2 !important}';
  var sty = document.createElement('style'); sty.textContent = css; document.head.appendChild(sty);

  makeCmp({ key: 'yr', root: 'htyr-root', ctlCls: 'htyr-ctl', issue: 'htyr-issue', btn: 'htcmpyr-btn', box: 'htcmpyr-box', cv: 'htcmpyr-cv',
            dir: '../yearly/', meta: function () { return window.__yrMeta; }, noun: 'yearly', leads: 12, block: 30, minN: 20,
            leadName: 'Mo', periodName: 'Month (30 d)', unitNote: '30-day mean flow', ctxBlocks: 4, xMin: -4.6, xSpan: 17.2,
            ticks: [-4, -2, 0, 3, 6, 9, 12], tickUnit: 'mo' });
})();
</script>
"""


def patch_page(s):
    if MARKER in s:
        return s
    for need in NEED:
        if need not in s:
            return None
    if s.count("</body>") != 1:
        return None
    out = s.replace("</body>", JS_BODY.strip() + "\n</body>", 1)
    if MARKER not in out:
        return None
    return out


def main():
    pages = sorted(Path("stations").glob("*.html"))
    if not pages:
        print("no station pages found (run from repo root)", file=sys.stderr)
        return 1
    n_new = n_skip = n_warn = 0
    for p in pages:
        s = p.read_text(encoding="utf-8")
        if MARKER in s:
            n_skip += 1
            print(f"already patched: {p.name}")
            continue
        out = patch_page(s)
        if out is None:
            n_warn += 1
            print(f"WARNING: anchors not as expected, skipped: {p.name}")
            continue
        p.write_text(out, encoding="utf-8")
        n_new += 1
        print(f"patched: {p.name}")
    print(f"patch_compare_y: {n_new} page(s) newly patched, {n_skip} already, "
          f"{n_warn} skipped-with-warning, {len(pages)} pages scanned")
    return 0


if __name__ == "__main__":
    sys.exit(main())
