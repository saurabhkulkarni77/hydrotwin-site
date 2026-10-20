#!/usr/bin/env python3
"""Monthly outlook — Flow & forecast panel upgrade for the DEV station
pages (dev only).

The daily "Flow & forecast" panel (the one in Saurabh's screenshot of
the St. Paul 3D page) has, beyond its chart: a model selector with
full model names, a lead stepper with a per-lead readout line
(period, forecast, observed, error) and a Play control that steps
through the leads. The monthly outlook panel (ht-monthly v1) had the
chart, selector, DACP controls, table and leaderboard, but not the
lead stepper / readout / play treatment. This patcher adds exactly
that to the monthly panel, on all 28 pages (classic + 3D):

  * model <select> option labels gain the ht-fullforms full names
    (values unchanged, so the monthly panel's own logic is untouched);
  * a lead strip under the monthly chart:
      [◀ Lead] [▶ Play] [Lead ▶]   Lead: Mo k of 6
      Mo k · <period start> – <period end> · forecast F cfs
             [· <lvl>% DACP lo – hi] [· observed O cfs · error ±x.x%]
    a dashed marker + chip on the chart at the selected lead, and the
    selected lead's row highlighted in the panel's own table;
  * Play steps the lead 1→6 automatically (~1.1 s per lead), pausing
    at the last lead; pressing Play at Mo 6 restarts from Mo 1.

Data comes only from the sidecars the monthly panel already loads
(../monthly/<site>.json, ../dacpm/<site>.json — browser-cached) and
the page payload's flow series, using the panel's exact block-mean
rule (30-day mean, >= 20 valid days). The strip re-drives off
window.__htS.day on a 700 ms poll, follows the panel's model select
and DACP on/level controls, and — like the step-18 compare — labels
itself as the baked outlook when the panel above is showing a LIVE
run (live runs are single-model; the stepper inspects the baked
outlook for the selected date, never presented as live).

Stage/ft: deliberately NO stage readout is added. The daily panel's
stage inset converts daily flows through the station rating curve;
a rating-curve stage computed from a 30-day MEAN flow is not an
expected water level and is not shown (see the build audit).

Append-only: this patcher adds ONE script before </body> and edits
no existing code; the monthly panel, its Live button, the step-18
compare block, the drift panel and ht-livefix are unmodified.

Idempotent: pages carrying the MARKER are skipped. Pages missing the
monthly / livefix / compare markers (pipeline order broken) are
skipped with a warning rather than written.
Run from the repo root: python3 build25/patch_ffmonthly.py
"""
import sys
from pathlib import Path

MARKER = "ht-ffmo v1"
NEED = ("ht-monthly v1", "ht-livefix v2", "ht-cmpwm v1")

JS_BODY = r"""
<script>
/* ht-ffmo v1 - Monthly outlook: Flow & forecast lead treatment (dev).
 * Adds full model names to the monthly panel's model selector and a
 * lead stepper + per-lead readout + Play under its chart, mirroring
 * the daily Flow & forecast panel. Baked sidecars only; in Live mode
 * it labels itself as inspecting the baked outlook. See
 * build25/patch_ffmonthly.py for the design note. */
(function () {
  var FULL = {'ARIMA': 'Autoregressive Integrated Moving Average', 'SARIMA': 'Seasonal Autoregressive Integrated Moving Average', 'GP Matérn': 'Gaussian Process (Matérn kernel)', 'GP RBF': 'Gaussian Process (Radial Basis Function kernel)', 'LSTM': 'Long Short-Term Memory network', 'Transformer': 'Transformer (self-attention neural network)', 'TFT': 'Temporal Fusion Transformer', 'PatchTST': 'Patch Time-Series Transformer', 'GCN': 'Graph Convolutional Network', 'PILSTMv1': 'Physics-Informed LSTM, version 1'};
  var NL = 6;
  var F = { lead: 1, playing: false, timer: null, wk: null, dq: null, wkErr: false, dqErr: false, wired: false, tries: 0, lastKey: '' };
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
  function blockMean(flow, endIdx) {
    if (endIdx < 29 || endIdx >= flow.length) return null;
    var s = 0, c = 0;
    for (var j = endIdx - 29; j <= endIdx; j++) { var v = flow[j]; if (v != null && v > 0) { s += v; c++; } }
    return c >= 20 ? s / c : null;
  }
  function load() {
    var P = pay(); if (!P || !P.site) return;
    if (!F.wk && !F.wkErr && !F.wkBusy) {
      F.wkBusy = true;
      fetch('../monthly/' + P.site + '.json').then(function (r) { if (!r.ok) throw new Error('http ' + r.status); return r.json(); })
        .then(function (j) { F.wkBusy = false; F.wk = j; F.wk.idx = {}; j.dates.forEach(function (d, i) { F.wk.idx[d] = i; }); })
        .catch(function () { F.wkBusy = false; F.wkErr = true; setTimeout(function () { F.wkErr = false; }, 4000); });
    }
    if (!F.dq && !F.dqErr && !F.dqBusy) {
      F.dqBusy = true;
      fetch('../dacpm/' + P.site + '.json').then(function (r) { if (!r.ok) throw new Error('http ' + r.status); return r.json(); })
        .then(function (j) { F.dqBusy = false; F.dq = j; F.dq.idx = {}; j.dates.forEach(function (d, i) { F.dq.idx[d] = i; }); })
        .catch(function () { F.dqBusy = false; F.dqErr = true; setTimeout(function () { F.dqErr = false; }, 4000); });
    }
  }
  function curModel() {
    var sel = $('htmo-model');
    if (sel && sel.value) return sel.value;
    var P = pay(), S = window.__htS;
    if (P && S && P.models[S.model]) return P.models[S.model];
    return null;
  }
  function isLive() {
    var el = $('htmo-issue');
    return !!(el && el.textContent && el.textContent.indexOf('LIVE outlook') === 0);
  }
  function chartX(k) { return (64 + (k + 4.6) / 11.2 * (746 - 64)) / 760 * 100; }
  function stopPlay() {
    F.playing = false;
    if (F.timer) { clearInterval(F.timer); F.timer = null; }
    var b = $('htffmo-play'); if (b) b.textContent = '▶ Play';
  }
  function setLead(k) {
    F.lead = Math.max(1, Math.min(NL, k));
    render();
  }
  function build() {
    var cv = $('htmo-canvas'), sel = $('htmo-model');
    if (!cv || !sel || !cv.parentNode) return false;
    if (sel.getAttribute('data-ffmo-full') !== '1') {
      for (var i = 0; i < sel.options.length; i++) {
        var v = sel.options[i].value;
        if (FULL[v]) sel.options[i].textContent = v + ' — ' + FULL[v];
      }
      sel.setAttribute('data-ffmo-full', '1');
    }
    if ($('htffmo-strip')) { F.wired = true; return true; }
    var wrap = document.createElement('div');
    wrap.className = 'htffmo-wrap';
    cv.parentNode.insertBefore(wrap, cv);
    wrap.appendChild(cv);
    var mark = document.createElement('div');
    mark.id = 'htffmo-mark'; mark.className = 'htffmo-mark'; mark.style.display = 'none';
    mark.innerHTML = '<span class="htffmo-chip" id="htffmo-chip"></span>';
    wrap.appendChild(mark);
    var strip = document.createElement('div');
    strip.id = 'htffmo-strip'; strip.className = 'htffmo-strip';
    strip.innerHTML = '<div class="htffmo-ctl">'
      + '<button type="button" id="htffmo-prev">◀ Lead</button>'
      + '<button type="button" id="htffmo-play">▶ Play</button>'
      + '<button type="button" id="htffmo-next">Lead ▶</button>'
      + '<span class="htffmo-lab" id="htffmo-lab"></span></div>'
      + '<div class="htffmo-live" id="htffmo-live" style="display:none">The panel above is showing a LIVE run — this lead view inspects the baked outlook for the selected date, not the live run.</div>'
      + '<div class="htffmo-read" id="htffmo-read"></div>';
    wrap.parentNode.insertBefore(strip, wrap.nextSibling);
    $('htffmo-prev').addEventListener('click', function () { stopPlay(); setLead(F.lead - 1); });
    $('htffmo-next').addEventListener('click', function () { stopPlay(); setLead(F.lead + 1); });
    $('htffmo-play').addEventListener('click', function () {
      if (F.playing) { stopPlay(); render(); return; }
      if (F.lead >= NL) F.lead = 1;
      F.playing = true;
      this.textContent = '❚❚ Pause';
      render();
      F.timer = setInterval(function () {
        if (F.lead >= NL) { stopPlay(); render(); return; }
        F.lead += 1; render();
        if (F.lead >= NL) stopPlay();
      }, 1100);
    });
    sel.addEventListener('change', function () { render(); });
    var on = $('htmo-on'), lv = $('htmo-lvl');
    if (on) on.addEventListener('change', render);
    if (lv) lv.addEventListener('change', render);
    F.wired = true;
    return true;
  }
  function highlightRow(k, has) {
    var rows = document.querySelectorAll('#htmo-read table.htmo-t tr');
    for (var i = 0; i < rows.length; i++) rows[i].classList.remove('htffmo-hl');
    if (has && rows[k]) rows[k].classList.add('htffmo-hl');
  }
  function render() {
    var strip = $('htffmo-strip'); if (!strip) return;
    load();
    var P = pay(), S = window.__htS, readEl = $('htffmo-read'), labEl = $('htffmo-lab'), mark = $('htffmo-mark'), liveEl = $('htffmo-live');
    if (!P || !S) { if (readEl) readEl.textContent = ''; return; }
    var issue = isoOf(P, S.day);
    var model = curModel();
    if (liveEl) liveEl.style.display = isLive() ? '' : 'none';
    if (labEl) labEl.textContent = 'Lead: Mo ' + F.lead + ' of ' + NL + ' · monthly Flow & forecast';
    if (F.wkErr) { if (readEl) readEl.textContent = 'lead view unavailable (monthly sidecar missing)'; if (mark) mark.style.display = 'none'; highlightRow(0, false); return; }
    if (!F.wk) { if (readEl) readEl.textContent = 'loading lead view…'; return; }
    var di = F.wk.idx[issue];
    var preds = (di != null && model && F.wk.predw[model]) ? F.wk.predw[model][di] : null;
    if (!preds) {
      if (readEl) readEl.textContent = 'No baked monthly forecast for ' + issue + ' — the lead view covers ' + F.wk.dates[0] + ' … ' + F.wk.dates[F.wk.dates.length - 1] + '. Pick a date in that range.';
      if (mark) mark.style.display = 'none';
      highlightRow(0, false);
      return;
    }
    var k = F.lead, fc = preds[k - 1];
    var txt = 'Mo ' + k + ' · ' + addDays(issue, 30 * (k - 1) + 1) + ' – ' + addDays(issue, 30 * k) + ' · forecast ' + fmt(fc) + ' cfs';
    var onEl = $('htmo-on'), lvEl = $('htmo-lvl');
    var bandOn = onEl ? onEl.checked : true;
    var lvl = lvEl ? lvEl.value : '90';
    if (bandOn && F.dq && F.dq.q[model] && F.dq.q[model][lvl]) {
      var q = F.dq.q[model][lvl][k - 1] ? F.dq.q[model][lvl][k - 1][di] : null;
      if (q != null && fc != null) txt += ' · ' + lvl + '% DACP ' + fmt(fc * Math.exp(-q)) + ' – ' + fmt(fc * Math.exp(q)) + ' cfs';
    }
    var obs = blockMean(P.flow, S.day + 30 * k);
    if (obs != null && fc != null) {
      var err = (fc - obs) / obs * 100;
      txt += ' · observed ' + fmt(obs) + ' cfs · error ' + (err >= 0 ? '+' : '') + err.toFixed(1) + '%';
    } else if (obs != null) {
      txt += ' · observed ' + fmt(obs) + ' cfs';
    } else {
      txt += ' · observed — (30-day outcome not fully in the record for this date)';
    }
    txt += ' · ' + (model || '');
    if (readEl) readEl.textContent = txt;
    if (mark) {
      mark.style.display = '';
      mark.style.left = chartX(k) + '%';
      var chip = $('htffmo-chip'); if (chip) chip.textContent = 'Mo ' + k;
    }
    highlightRow(k, true);
  }
  var css = '.htffmo-wrap{position:relative}'
    + '.htffmo-mark{position:absolute;top:0;bottom:0;width:0;border-left:2px dashed #FFD24D;pointer-events:none;z-index:3}'
    + '.htffmo-chip{position:absolute;top:4px;left:5px;background:#FFD24D;color:#111;font:700 10.5px system-ui;border-radius:4px;padding:1px 5px;white-space:nowrap}'
    + '.htffmo-strip{margin:8px 0 2px;border:1px solid rgba(255,255,255,.16);border-radius:8px;padding:8px 10px;background:rgba(255,255,255,.03)}'
    + '.htffmo-ctl{display:flex;gap:8px;align-items:center;flex-wrap:wrap}'
    + '.htffmo-ctl button{background:#0E1A24;color:#e8eef5;border:1px solid rgba(255,255,255,.3);border-radius:6px;font:600 12.5px system-ui;padding:3px 8px;cursor:pointer}'
    + '.htffmo-lab{font-weight:600;color:#BFD0E0;font-size:12px}'
    + '.htffmo-read{font-size:12.5px;color:#e8eef5;margin-top:6px}'
    + '.htffmo-live{font-size:12px;color:#FFD24D;border:1px solid rgba(255,210,77,.45);border-radius:6px;padding:4px 8px;margin-top:8px}'
    + '#htmo-read table.htmo-t tr.htffmo-hl td{background:rgba(255,210,77,.14);color:#FFD24D;font-weight:700}';
  var sty = document.createElement('style'); sty.textContent = css; document.head.appendChild(sty);
  setInterval(function () {
    if (!F.wired) { F.tries++; if (build() || F.tries > 40) { /* keep polling cheaply */ } }
    if (!F.wired) return;
    var S = window.__htS; if (!S) return;
    var sel = $('htmo-model'), onEl = $('htmo-on'), lvEl = $('htmo-lvl');
    var key = S.day + '|' + (sel ? sel.value : '') + '|' + F.lead + '|' + (onEl ? onEl.checked : '') + '|' + (lvEl ? lvEl.value : '')
      + '|' + (isLive() ? 1 : 0) + '|' + (F.wk ? 1 : 0) + '|' + (F.dq ? 1 : 0) + '|' + (F.wkErr ? 1 : 0);
    if (key !== F.lastKey) { F.lastKey = key; render(); }
    else {
      var rows = document.querySelectorAll('#htmo-read table.htmo-t tr');
      if (rows.length > 1 && F.wk) {
        var di = F.wk.idx[isoOf(pay() || { start: '2001-10-01' }, S.day)];
        var has = di != null;
        var hl = document.querySelector('#htmo-read table.htmo-t tr.htffmo-hl');
        if (has && (!hl || rows[F.lead] !== hl)) highlightRow(F.lead, true);
        if (!has && hl) highlightRow(0, false);
      }
    }
  }, 700);
  build();
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
    print(f"patch_ffmonthly: {n_new} page(s) newly patched, {n_skip} already, "
          f"{n_warn} skipped-with-warning, {len(pages)} pages scanned")
    return 0


if __name__ == "__main__":
    sys.exit(main())
