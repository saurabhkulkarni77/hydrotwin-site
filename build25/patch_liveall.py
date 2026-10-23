#!/usr/bin/env python3
"""One Live action for every chart on the page (ht-liveall v2, dev only).

Diagnosis (2026-10-19, browser-verified): on the CLASSIC station pages
Live did not exist at all — no daily live engine (window.loadLive /
htGapAssemble / htBakedAssemble / fetchLiveSoilSnow are all undefined:
they live in the 3D pages' module and in patchers that only touch
*-3d.html), and the outlook panels render their Live buttons only on
3D pages (their runLive code is present on classic but unreachable and
would refuse with 'live assembly unavailable'). On the 3D pages the
machinery works, but it is fragmented: a readout-only 'live' action, a
separate 'big model' action (selected model only), and one Live button
per outlook panel — no single action pulls current data and recomputes
every chart, and nothing badges the page as LIVE.

This patch adds, to every station page (classic + 3D):
  * a master bar: "▶ LIVE — pull today's data · all charts",
    a ● LIVE badge with a data-through line, an "old weights
    (pre-drift-fix)" toggle (Task C), and a ↩ baked button;
  * on CLASSIC pages only, the missing live layer, mirroring the 3D
    implementations exactly (same feeds, same feature windows, same
    math): htGapAssemble (baked HT_DATA extended with USGS daily
    values + Open-Meteo forecast/archive), htBakedAssemble (baked
    tail), fetchLiveSoilSnow (NRCS AWDB / Open-Meteo / SNOTEL with
    the training-median fallbacks), a daily forecast engine for all
    10 models (ONNX via the same remote-first URLs as bigModelLive,
    GP via the verbatim GPForecast, ARIMA/SARIMA via the verbatim
    ARIMAForecast/armaMean; GCN has no browser build — it stays
    baked and is labelled as such), live renderers for the daily
    board / forecast / day canvases, and live outlook runs
    (weekly/monthly/yearly) drawn with the panels' own chart code
    semantics (same tensor build, same DACP q_end band, same issue
    line wording);
  * on 3D pages, a driver for the app's own live paths: it dispatches
    the app's keyboard routing ('g' = live readout, 'b' = big-model
    forecast) and clicks each outlook panel's own Live button
    (re-clicking while a panel reports 'still loading'), then badges
    the page from the panels' own status lines;
  * the old-weights series (Task C): ../oldfc/<site>.json carries the
    pre-drift-fix baked HT_DATA.pred tails (last 400 issue days,
    extracted from the station pages at commit 0908430a8e). On
    classic pages the old fan is drawn on the daily board alongside
    the current fan; on 3D pages an 'Old weights (pre-fix)' model is
    appended to D.models/D.pred (the LiveAR precedent), and both
    classes get an old-vs-current fan table in the master bar. The
    browser ONNX/params stacks are byte-identical before and after
    the drift fix (verified by tree diff), so there are no distinct
    old weights to run live — in Live mode the old series is the old
    baked fan at its true issue dates, labelled as such.

v2 (2026-10-19, user request): the master bar is DRAGGABLE. On the 3D
pages the sticky bar covers the page's own top strip (station title
chip and the top buttons — LiveAR demo / retrain on GitHub / Compare
models), and the user could not reach them. The bar now carries a ⠿
grip at its left end and can be pointer-dragged (mouse + touch, via
Pointer Events) from the grip or any non-interactive part of the bar —
never from its buttons, the old-weights checkbox/label, or links, which
keep working as clicks. While dragged the bar is position:fixed and
clamped fully inside the viewport; on release it stays where dropped
and the position is remembered in sessionStorage for the page session,
so Live runs and panel re-renders do not snap it back to the top.
Double-clicking the grip resets it to the default position.

Position refresh (2026-10-22, user request): the master bar no
longer sits in the top strip at all — on the 3D pages its full-width
sticky bar crowded the page's own top buttons (station title chip and
the LiveAR demo / retrain on GitHub / Compare models row). The
default position is now a compact fit-content cluster fixed in the
middle of the viewport (horizontally centered; 34% from the top —
above vertical center, which is what clears the bottom-anchored Flow
& forecast dock on shorter viewports and the gauge label at center),
with the full border / radius / shadow treatment the dragged
(.htla-moved) state already had. Dragging works as before — the
moved state now also clears the centering transform so drop
coordinates stay exact — and the grip double-click reset returns the
bar to the centered default instead of the top. z-index stays 9999:
above the 3D canvas, below the pages' modal/popover layers (unchanged
stacking). The same component serves the classic pages, so they get
the same centered default. NOTE: the block marker stays "ht-liveall
v2" — the CI census (tests/test_site_integrity.py, mirrored by
patch_lazy_panels.py) pins that marker at exactly 1 per page, so the
refresh is applied as an in-place CSS swap inside the existing v2
block (anchors POS_OLD_* below, each asserted to match exactly once),
not as a version bump.

RMSE field (2026-10-22, user request): the bar also carries a small
readout immediately after the old-weights checkbox label —
"RMSE old <A> · new <B> · Δ <B-A>" for the page's station, from the
drift fix's A-vs-B backtest (both protocols evaluated on the same
untouched WY2026 windows; mean across the 10 served daily models,
log10 cfs; the same per-model figures the Model drift panel shows).
A tooltip on the field states that basis. Like the position refresh
it is an in-place edit inside the existing v2 block (anchors
RMSE_OLD_* below, signature ht-rmsefield v1 in the bar CSS),
applied to v2 pages on the refresh path and to fresh installs
alike. The values are a fixed historical backtest, so a later
"Load new model" hot-load does not change them, and the tooltip
never claims otherwise.

Idempotent: pages carrying the v2 MARKER whose bar CSS already has
the centered default are skipped; v2 pages with the old sticky CSS
get the in-place position refresh; pages carrying only a v1 block
are upgraded in place (the v1 <script> block is removed and the v2
block appended, exactly one block either way).

Pull-forward (ht-pullfwd v1, 2026-10-23, user request: "when we pull
new data can we save it in s3 and make calendar forward to wherever
new data is"): a companion script block (PULLFWD_JS below, its own
<script> appended before </body>, signature ht-pullfwd v1) plus, on
classic pages only, two count-checked clamp swaps in the stats
script. The pull-snapshots workflow (scripts/pull_snapshots.py)
publishes the same fresh series the LIVE pull fetches to the DEV
bucket at data/pulls/<station>/<date>.json with a manifest.json;
on load the block reads the manifest, sets the date input's max to
the station's latest pulled date and extends the page's own data
arrays with the snapshot series (fresh values also overwrite the
overlap window — the pull's fresh-wins rule), so the calendar, the
arrow keys and play reach the new data for every visitor. After a
LIVE pull it watches __htla.issue and lands the calendar on the
pull's issue date (on 3D it also writes the pull's fans into
HT3D.pred when the manifest extension made panelLive3D return
early). On classic pages the stats script captured its day bound
in a const (N = D.n), so setDay's clamp and the play loop's wrap
are re-pointed at Math.max(N, window.__htPullN || 0) — with no
extension the expressions reduce to the baked behavior exactly.
Like the position/RMSE refreshes this is applied to v2 pages on the
refresh path and to fresh installs alike; the block marker stays
"ht-liveall v2" (the CI census pins it at exactly 1 per page).

Run from the repo root: python3 build25/patch_liveall.py
"""
import re
import sys
from pathlib import Path

MARKER = "ht-liveall v2"
OLD_MARKERS = ("ht-liveall v1",)
# The old blocks were inserted as "\n<script>\n" + JS + "\n</script>\n"
# with the JS starting "\n/* ht-liveall vN */"; the JS contains no
# literal "</script>", so a non-greedy match to the first close tag is
# exact.
OLD_BLOCK_RE = re.compile(r"\n?<script>\s*/\* ht-liveall v[12] \*/.*?</script>\n?", re.S)
# Position refresh anchors (2026-10-22): exact CSS fragments of the v2
# block as baked into the branch pages, and their centered-default
# replacements. Each OLD fragment must occur exactly once per page
# (asserted in main); POS_SIG marks a page as already refreshed.
POS_SIG = "#htla-bar{position:fixed;left:50%;"
POS_OLD_BAR = ("#htla-bar{position:sticky;top:0;z-index:9999;display:flex;gap:10px;"
               "align-items:center;flex-wrap:wrap;")
POS_NEW_BAR = ("#htla-bar{position:fixed;left:50%;top:34%;transform:translate(-50%,-50%);"
               "z-index:9999;display:flex;gap:10px;align-items:center;flex-wrap:wrap;"
               "justify-content:center;width:fit-content;max-width:min(600px,94vw);")
POS_OLD_BORDER = "background:rgba(8,20,14,.96);border-bottom:2px solid #2E9B57;padding:8px 12px;"
POS_NEW_BORDER = ("background:rgba(8,20,14,.96);border:2px solid #2E9B57;border-radius:10px;"
                  "box-shadow:0 10px 30px rgba(0,0,0,.55);padding:8px 12px;")
POS_OLD_MOVED = "#htla-bar.htla-moved{position:fixed;margin:0;"
POS_NEW_MOVED = "#htla-bar.htla-moved{position:fixed;transform:none;margin:0;"
# RMSE field refresh anchors (2026-10-22): exact fragments of the v2
# block as baked into the branch pages. Each OLD fragment must occur
# exactly once per page (asserted in _apply_rmse); RMSE_SIG (inside
# the replacement CSS, as a CSS comment) marks a page as refreshed.
RMSE_SIG = "ht-rmsefield v1"
RMSE_TITLE = ("WY2026 backtest - mean RMSE (log10 cfs) across the 10 served "
              "daily models: old = pre-drift-fix weights, new = retrained "
              "weights (drift fix, Oct 2026). Same A-vs-B figures as the "
              "Model drift panel.")
RMSE_OLD_CSS = "#htla-oldlab{cursor:pointer;color:#C9CED6;font-weight:600}"
RMSE_NEW_CSS = (RMSE_OLD_CSS
                + "/* ht-rmsefield v1 */#htla-rmse{color:#9FB3C8;"
                  "font-weight:600;font-size:12px;white-space:nowrap}")
RMSE_OLD_HTML = ("old weights (pre-drift-fix)</label>'\n"
                 "    + '<span id=\"htla-oldnote\"></span>'")
# Per-station (old, new) mean RMSE in log10 cfs: the mean across the
# 10 served daily models of the drift fix's A-vs-B backtest, both
# protocols evaluated on the same untouched WY2026 windows (old =
# protocol A, pre-drift-fix; new = protocol B, the retrained recipe
# behind the served models). Source: hydrotwin_driftfix/work/
# ab_eval.json; the identical per-model values are baked into
# drift/drift_bake.json (models[*].e / .l) and shown per model in the
# Model drift panel. Pooled across stations: 0.3506 -> 0.3479.
RMSE_AB = {
    "01463500": (0.4309, 0.4051), "01646500": (0.4968, 0.4845),
    "02320500": (0.0854, 0.0891), "03294500": (0.4416, 0.4613),
    "05331000": (0.2460, 0.2386), "06214500": (0.2818, 0.2900),
    "06934500": (0.3478, 0.3583), "07374000": (0.1945, 0.1703),
    "08057000": (0.7997, 0.7890), "08158000": (0.7406, 0.7335),
    "08313000": (0.3647, 0.3478), "09380000": (0.0846, 0.0786),
    "11447650": (0.2495, 0.2731), "14105700": (0.1449, 0.1517),
}
# Pull-forward (ht-pullfwd v1, 2026-10-23): signature + classic clamp
# anchors. The stats script on classic pages captured its day bound in
# a const (N = D.n) before any patcher block runs, so the only way to
# let its calendar pass the baked end is to re-point the two places
# that bound the *current day*: setDay's clamp and the play loop's
# wrap. Both OLD fragments must occur exactly once per classic page
# (asserted in _apply_pullfwd); the replacements consult
# window.__htPullN, which the pullfwd block sets when it extends the
# page's data arrays (0 / undefined = baked behavior, exactly).
PULLFWD_SIG = "ht-pullfwd v1"
PULLFWD_CLAMP_OLD = ("function setDay(i) { S.day = Math.max(0, "
                     "Math.min(N - 1, i)); applyDay(); htSyncDate(); }")
PULLFWD_CLAMP_NEW = ("function setDay(i) { S.day = Math.max(0, "
                     "Math.min(Math.max(N, window.__htPullN || 0) - 1, i)); "
                     "applyDay(); htSyncDate(); }")
PULLFWD_WRAP_OLD = "setDay(S.day + 1 >= N ? 0 : S.day + 1)"
PULLFWD_WRAP_NEW = ("setDay(S.day + 1 >= Math.max(N, window.__htPullN || 0) "
                    "? 0 : S.day + 1)")
ROOT = Path(__file__).resolve().parent.parent
STATIONS = ROOT / "stations"

# ---------------------------------------------------------------- payloads
# Harvested verbatim from the 3D pages (they are global constants /
# functions, identical on every 3D page): the soil/snow station tables
# and the GP / ARIMA forecast engines bigModelLive uses. BIGSTATS is
# per-station and is harvested from each station's own -3d sibling.


def _extract_fn(src, sig):
    i = src.find(sig)
    if i < 0:
        raise SystemExit(f"harvest failed: {sig!r} not found")
    depth = 0
    k = src.find("{", i)
    while True:
        c = src[k]
        if c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                return src[i:k + 1]
        k += 1


def _extract_const(src, name):
    m = re.search(r"const " + name + r" = (\{.*?\});", src, re.S)
    if not m:
        raise SystemExit(f"harvest failed: const {name} not found")
    return m.group(1)


def _bigstats(src):
    i = src.find("const BIGSTATS = ")
    if i < 0:
        raise SystemExit("harvest failed: BIGSTATS not found")
    j = src.find("};", i)
    return src[i + len("const BIGSTATS = "):j + 1].strip()


JS_TEMPLATE = r"""
/* ht-liveall v2 */
(function () {
  'use strict';
  if (window.__htlaOn) return;
  window.__htlaOn = true;
  var $ = function (id) { return document.getElementById(id); };
  var D = window.HT_DATA || window.HT3D || {};
  var ST = D.station || {};
  var SITE = (ST.stationId || '').replace('USGS-', '') || D.site || '';
  var LAT = (ST.latitude != null ? ST.latitude : D.lat), LON = (ST.longitude != null ? ST.longitude : D.lon);
  var DAY = 864e5;
  function iso(t) { return new Date(t).toISOString().slice(0, 10); }
  function addDays(dstr, k) { return iso(Date.parse(dstr + 'T00:00:00Z') + k * DAY); }
  function dayIdx(dstr) { return Math.round((Date.parse(dstr + 'T00:00:00Z') - Date.parse((D.start || '2001-10-01') + 'T00:00:00Z')) / DAY); }
  var BAKED_END = (D.start && D.n) ? addDays(D.start, D.n - 1) : '';
  var IS3D = !!window.HT3D;
  var NEURAL = ['LSTM', 'Transformer', 'TFT', 'PatchTST', 'PILSTMv1'];
  var HTLA_STATS = __BIGSTATS__;
  var SOILST = __SOILST__;
  var SNOTEL = __SNOTEL__;
  __GP_FN__
  __ARIMA_FN__
  __ARMA_FN__

  function fetchJ(url, ms) {
    return new Promise(function (res, rej) {
      var c = new AbortController();
      var t = setTimeout(function () { c.abort(); }, ms || 30000);
      fetch(url, { signal: c.signal }).then(function (r) {
        clearTimeout(t);
        if (!r.ok) throw new Error('HTTP ' + r.status);
        return r.json();
      }).then(res, rej);
    });
  }
  function loadOrt() {
    return new Promise(function (res, rej) {
      if (typeof ort !== 'undefined') return res();
      var s = document.createElement('script');
      s.src = 'https://cdn.jsdelivr.net/npm/onnxruntime-web@1.30.0/dist/ort.min.js';
      s.onload = function () { res(); };
      s.onerror = function () { rej(new Error('onnxruntime failed to load (CDN blocked?)')); };
      document.head.appendChild(s);
    });
  }

  /* ------------------------------------------------ master bar */
  /* position refresh: default spot is a compact fit-content cluster
     fixed in the middle of the viewport (centered horizontally, above
     vertical center) — not the full-width sticky strip in the top
     band. */
  var css = '#htla-bar{position:fixed;left:50%;top:34%;transform:translate(-50%,-50%);z-index:9999;display:flex;gap:10px;align-items:center;flex-wrap:wrap;justify-content:center;width:fit-content;max-width:min(600px,94vw);'
    + 'background:rgba(8,20,14,.96);border:2px solid #2E9B57;border-radius:10px;box-shadow:0 10px 30px rgba(0,0,0,.55);padding:8px 12px;font:600 13.5px system-ui;color:#DDE6EE}'
    + '#htla-go{background:#14532D;color:#B7F4CB;border:1px solid #2E9B57;border-radius:8px;padding:7px 14px;cursor:pointer;font:700 13.5px system-ui}'
    + '#htla-go:hover{background:#1B6B3C}#htla-badge{color:#7AE07A;font-weight:800;letter-spacing:.4px}'
    + '#htla-note{color:#BFD0E0;font-weight:500}#htla-oldlab{cursor:pointer;color:#C9CED6;font-weight:600}'
    + '#htla-back{background:#33404F;color:#DDE6EE;border:1px solid rgba(255,255,255,.35);border-radius:8px;padding:6px 10px;cursor:pointer;font:600 12.5px system-ui}'
    + '#htla-oldtable{flex-basis:100%;font:500 12px system-ui;color:#C9CED6}'
    + '#htla-oldtable table{border-collapse:collapse;margin-top:4px}#htla-oldtable td,#htla-oldtable th{padding:1px 8px 1px 0;text-align:right}'
    + '#htla-oldtable td:first-child,#htla-oldtable th:first-child{text-align:left;color:#E6EDF5}'
    /* v2: the bar is draggable (grip or any non-interactive part) so it
       never has to cover the pages' own top buttons. */
    + '#htla-bar{touch-action:none}'
    + '#htla-grip{cursor:grab;touch-action:none;user-select:none;-webkit-user-select:none;color:#7AE07A;font-size:17px;line-height:1;padding:2px 3px}'
    + '#htla-grip:active{cursor:grabbing}'
    + '#htla-bar.htla-moved{position:fixed;transform:none;margin:0;border:2px solid #2E9B57;border-radius:10px;box-shadow:0 10px 30px rgba(0,0,0,.55)}';
  var style = document.createElement('style');
  style.textContent = css;
  document.head.appendChild(style);
  var bar = document.createElement('div');
  bar.id = 'htla-bar';
  bar.innerHTML = '<span id="htla-grip" title="Drag to move this bar · double-click to reset">⠿</span>'
    + '<button type="button" id="htla-go">▶ LIVE — pull today\'s data · all charts</button>'
    + '<span id="htla-badge" style="display:none">● LIVE</span>'
    + '<span id="htla-note">baked data through ' + BAKED_END + '</span>'
    + '<label id="htla-oldlab"><input type="checkbox" id="htla-old"> old weights (pre-drift-fix)</label>'
    + '<span id="htla-oldnote"></span>'
    + '<button type="button" id="htla-back" style="display:none">↩ baked</button>'
    + '<div id="htla-oldtable" style="display:none"></div>';
  document.body.insertBefore(bar, document.body.firstChild);
  function note(t) { var el = $('htla-note'); if (el) el.textContent = t; }
  function oldNote(t) { var el = $('htla-oldnote'); if (el) el.textContent = t; }

  /* ---------------- v2: drag the bar out of the way ----------------
     The v2 sticky bar covered the pages' own top strip (title chip
     + top buttons); the default spot is now the viewport middle, and
     dragging remains the way to move it elsewhere. Drag it by the ⠿
     grip or any non-interactive part (label
     / status text, badge, table): drags never start from the bar's
     buttons, the old-weights checkbox/label, or links, so those keep
     working as clicks. While dragging the bar is position:fixed and
     clamped fully inside the viewport; on release it stays put and
     the spot is kept in sessionStorage for the page session, so Live
     runs / re-renders don't snap it back. Double-click the grip to
     reset to the default centered position. The bar only ever receives
     pointer events on its own box, so the 3D scene below is safe. */
  var HTLA_POS_KEY = 'htla-bar-pos';
  function htlaClampPos(l, t) {
    var w = bar.offsetWidth, h = bar.offsetHeight;
    return [Math.max(0, Math.min(l, Math.max(0, window.innerWidth - w))),
            Math.max(0, Math.min(t, Math.max(0, window.innerHeight - h)))];
  }
  function htlaApplyPos(l, t, w) {
    var p = htlaClampPos(l, t);
    bar.classList.add('htla-moved');
    bar.style.left = p[0] + 'px';
    bar.style.top = p[1] + 'px';
    if (w) bar.style.width = w + 'px';
    return p;
  }
  function htlaSavePos() {
    try {
      var r = bar.getBoundingClientRect();
      sessionStorage.setItem(HTLA_POS_KEY, JSON.stringify({ l: Math.round(r.left), t: Math.round(r.top), w: Math.round(r.width) }));
    } catch (e) { /* storage is best-effort */ }
  }
  function htlaResetPos() {
    bar.classList.remove('htla-moved');
    bar.style.left = ''; bar.style.top = ''; bar.style.width = '';
    try { sessionStorage.removeItem(HTLA_POS_KEY); } catch (e) {}
  }
  (function htlaRestorePos() {
    try {
      var s = sessionStorage.getItem(HTLA_POS_KEY);
      if (!s) return;
      var p = JSON.parse(s);
      if (p && isFinite(p.l) && isFinite(p.t)) htlaApplyPos(p.l, p.t, p.w);
    } catch (e) { /* ignore */ }
  })();
  var htlaDrag = null, htlaLastGripTap = 0;
  bar.addEventListener('pointerdown', function (e) {
    if (e.button != null && e.button !== 0) return;
    if (e.target.closest('button, a, input, select, textarea, label')) return;
    var r = bar.getBoundingClientRect();
    if (!bar.classList.contains('htla-moved')) htlaApplyPos(r.left, r.top, r.width);
    htlaDrag = { id: e.pointerId, dx: e.clientX - r.left, dy: e.clientY - r.top,
      sx: e.clientX, sy: e.clientY, grip: !!(e.target.closest && e.target.closest('#htla-grip')) };
    try { bar.setPointerCapture(e.pointerId); } catch (err) {}
    e.preventDefault();
  });
  bar.addEventListener('pointermove', function (e) {
    if (!htlaDrag || e.pointerId !== htlaDrag.id) return;
    htlaApplyPos(e.clientX - htlaDrag.dx, e.clientY - htlaDrag.dy);
  });
  function htlaEndDrag(e) {
    if (!htlaDrag || (e && e.pointerId !== htlaDrag.id)) return;
    /* Reset is detected here, not via dblclick: the pointerdown
       preventDefault above suppresses the compatibility dblclick event.
       Two quick low-movement taps on the grip = reset. */
    var wasGrip = htlaDrag.grip;
    var movedPx = (e && isFinite(e.clientX)) ? Math.hypot(e.clientX - htlaDrag.sx, e.clientY - htlaDrag.sy) : 99;
    htlaDrag = null;
    if (wasGrip && movedPx < 5) {
      var now = Date.now();
      if (now - htlaLastGripTap < 900) { htlaLastGripTap = 0; htlaResetPos(); return; }
      htlaLastGripTap = now;
    }
    htlaSavePos();
  }
  bar.addEventListener('pointerup', htlaEndDrag);
  bar.addEventListener('pointercancel', htlaEndDrag);
  var htlaGrip = $('htla-grip');
  if (htlaGrip) htlaGrip.addEventListener('dblclick', function () { htlaResetPos(); });
  window.addEventListener('resize', function () {
    if (!bar.classList.contains('htla-moved')) return;
    var r = bar.getBoundingClientRect();
    htlaApplyPos(r.left, r.top);
    htlaSavePos();
  });

  var LA = { busy: false, on: false, issue: null, A: null, fc: {}, fcErr: {}, out: {}, old: null, oldOn: false, oldAppended: false };
  window.__htla = LA;

  /* --------------------------------------- classic live assembly layer */
  if (!window.htGapAssemble) {
    window.htGapAssemble = async function () {
      var today = iso(Date.now());
      var flows = {}, wx = {};
      var fl = D.flow || [], t0 = Date.parse((D.start || '2001-10-01') + 'T00:00:00Z');
      var i, q;
      for (i = 0; i < fl.length; i++) { q = fl[i]; if (q != null && q > 0) flows[iso(t0 + i * DAY)] = q; }
      var tx = D.tmax || [], tn = D.tmin || [], pr = D.precip || [];
      for (i = Math.max(0, fl.length - 400); i < fl.length; i++) {
        if (tx[i] != null && tn[i] != null) wx[iso(t0 + i * DAY)] = [tx[i], tn[i], pr[i] || 0];
      }
      var pcd = (SITE === '11447650') ? '72137' : '00060';
      var fStart = addDays(today, -45), wStart = addDays(today, -400);
      var ru = null, wf = null, wa = null;
      try { ru = await fetchJ('https://waterservices.usgs.gov/nwis/dv/?format=json&sites=' + SITE + '&parameterCd=' + pcd + '&startDT=' + fStart + '&endDT=' + today, 30000); } catch (e) { ru = null; }
      try { wf = await fetchJ('https://api.open-meteo.com/v1/forecast?latitude=' + LAT + '&longitude=' + LON + '&daily=temperature_2m_max,temperature_2m_min,precipitation_sum&temperature_unit=celsius&precipitation_unit=mm&timezone=auto&past_days=10&forecast_days=1', 30000); } catch (e) { wf = null; }
      try { wa = await fetchJ('https://archive-api.open-meteo.com/v1/archive?latitude=' + LAT + '&longitude=' + LON + '&start_date=' + wStart + '&end_date=' + today + '&daily=temperature_2m_max,temperature_2m_min,precipitation_sum&temperature_unit=celsius&precipitation_unit=mm&timezone=auto', 45000); } catch (e) { wa = null; }
      if (ru && ru.value) {
        for (var a = 0; a < ru.value.timeSeries.length; a++) {
          var vals = ru.value.timeSeries[a].values[0].value;
          for (var b = 0; b < vals.length; b++) {
            var qq = parseFloat(vals[b].value);
            if (qq > 0) flows[vals[b].dateTime.slice(0, 10)] = qq;
          }
        }
      }
      var putWx = function (w) {
        var d = w && w.daily; if (!d || !d.time) return;
        for (var i2 = 0; i2 < d.time.length; i2++) {
          var mx = d.temperature_2m_max[i2], mn = d.temperature_2m_min[i2];
          if (mx == null || mn == null) continue;
          wx[d.time[i2]] = [mx, mn, d.precipitation_sum[i2] || 0];
        }
      };
      putWx(wf); putWx(wa);
      var dates = Object.keys(flows).filter(function (dt) { return wx[dt]; }).sort();
      if (dates.length < 30) throw new Error('only ' + dates.length + ' aligned days');
      var dn = dates.map(function (dt) { return Math.round(Date.parse(dt + 'T00:00:00Z') / DAY); });
      var k = dates.length - 1;
      while (k > 0 && dn[k] - dn[k - 1] === 1) k--;
      var run = dates.slice(k);
      if (run.length < 30) throw new Error('no 30-day consecutive run at the end');
      return { flows: flows, wx: wx, run: run, win30: run.slice(-30) };
    };
  }
  if (!window.htBakedAssemble) {
    window.htBakedAssemble = async function () {
      var flows = {}, wx = {};
      var t0 = Date.parse((D.start || '2001-10-01') + 'T00:00:00Z');
      for (var i = 0; i < D.n; i++) {
        var dt = iso(t0 + i * DAY);
        if (D.flow[i] != null && D.flow[i] > 0) flows[dt] = D.flow[i];
        if (D.tmax[i] != null && D.tmin[i] != null) wx[dt] = [D.tmax[i], D.tmin[i], D.precip[i] || 0];
      }
      var dates = Object.keys(flows).filter(function (dt) { return wx[dt]; }).sort();
      var dn = dates.map(function (dt) { return Math.round(Date.parse(dt + 'T00:00:00Z') / DAY); });
      var k = dates.length - 1;
      while (k > 0 && dn[k] - dn[k - 1] === 1) k--;
      var run = dates.slice(k);
      return { flows: flows, wx: wx, run: run, win30: run.slice(-30) };
    };
  }
  if (!window.fetchLiveSoilSnow) {
    window.fetchLiveSoilSnow = async function () {
      var fb = { sms: HTLA_STATS.med_sms, stmpF: HTLA_STATS.med_stmp, swe: 0 };
      try {
        var trip = SOILST[SITE];
        if (trip) {
          var now = new Date(), ago = new Date(now); ago.setDate(ago.getDate() - 2);
          var rj = await fetchJ('https://wcc.sc.egov.usda.gov/awdbRestApi/services/v1/data?stationTriplets=' + trip + '&elements=SMS:-8,SMS:-2,STO:-2&duration=HOURLY&beginDate=' + iso(ago.getTime()) + '%2000:00&endDate=' + iso(now.getTime()) + '%2023:00&unitSystem=ENGLISH', 15000).catch(function () { return null; });
          for (var a = 0; a < (Array.isArray(rj) ? rj : []).length; a++) {
            var dd = rj[a].data || [];
            for (var b = 0; b < dd.length; b++) {
              var code = dd[b].stationElement && dd[b].stationElement.elementCode;
              var vs = (dd[b].values || []).filter(function (x) { return x.value != null; });
              if (!vs.length) continue;
              var last = vs[vs.length - 1].value;
              if (code === 'SMS' && fb.sms === HTLA_STATS.med_sms) fb.sms = last;
              else if (code === 'STO') fb.stmpF = last;
            }
          }
        }
      } catch (e) { /* NRCS optional */ }
      try {
        var rw = await fetchJ('https://api.open-meteo.com/v1/forecast?latitude=' + LAT + '&longitude=' + LON + '&current=soil_temperature_6cm,soil_moisture_3_9cm,snow_depth&timezone=auto', 20000).catch(function () { return null; });
        if (rw && rw.current) {
          var c = rw.current;
          if (fb.sms === HTLA_STATS.med_sms && c.soil_moisture_3_9cm != null) fb.sms = c.soil_moisture_3_9cm * 100;
          if (fb.stmpF === HTLA_STATS.med_stmp && c.soil_temperature_6cm != null) fb.stmpF = c.soil_temperature_6cm * 9 / 5 + 32;
          if (c.snow_depth != null && c.snow_depth > 0) fb.swe = c.snow_depth * 0.3937;
        }
      } catch (e) { /* Open-Meteo optional */ }
      try {
        var trips = SNOTEL[SITE] || [];
        if (trips.length) {
          var now2 = new Date(), ago2 = new Date(now2); ago2.setDate(ago2.getDate() - 7);
          var rj2 = await fetchJ('https://wcc.sc.egov.usda.gov/awdbRestApi/services/v1/data?stationTriplets=' + trips.join(',') + '&elements=WTEQ&duration=DAILY&beginDate=' + iso(ago2.getTime()) + '&endDate=' + iso(now2.getTime()) + '&unitSystem=ENGLISH', 15000).catch(function () { return null; });
          var means = [];
          for (var a2 = 0; a2 < (Array.isArray(rj2) ? rj2 : []).length; a2++) {
            var dd2 = rj2[a2].data || [];
            for (var b2 = 0; b2 < dd2.length; b2++) {
              var vs2 = (dd2[b2].values || []).filter(function (x) { return x.value != null; });
              if (vs2.length) means.push(vs2[vs2.length - 1].value);
            }
          }
          if (means.length) fb.swe = means.reduce(function (x, y) { return x + y; }, 0) / means.length;
        }
      } catch (e) { /* SNOTEL optional */ }
      return fb;
    };
  }

  /* --------------------------------------- classic daily live engine */
  var ONNX_BASE = 'https://saurabhkulkarni77.github.io/hydrotwin-models/onnx';
  var PARAMS_BASE = 'https://saurabhkulkarni77.github.io/hydrotwin-models/params';
  var PARAM_D = { 'GP RBF': 'GP_RBF', 'GP Matérn': 'GP_Matern', 'ARIMA': 'ARIMA', 'SARIMA': 'SARIMA' };
  var sessCache = {};
  async function dailyFc(model, A, ss) {
    var mu = HTLA_STATS.mu, sd = HTLA_STATS.sd, tsd = HTLA_STATS.tsd;
    var flows = A.flows, wx = A.wx, win30 = A.win30, i, j;
    if (NEURAL.indexOf(model) >= 0) {
      var flat = new Float32Array(29 * 9);
      var prev = flows[win30[0]];
      for (i = 1; i < 30; i++) {
        var dt = win30[i], t = wx[dt], q = flows[dt];
        if (!t || q == null) throw new Error('live window has gaps');
        var row = [t[0], t[1], (t[0] + t[1]) / 2, t[2], q, q > prev ? 1 : 0, ss.sms, ss.stmpF, ss.swe];
        prev = q;
        for (j = 0; j < 9; j++) { var x = j === 4 ? Math.log(row[j]) : row[j]; flat[(i - 1) * 9 + j] = (x - mu[j]) / sd[j]; }
      }
      var last = Math.log(flows[win30[29]]);
      var sess = sessCache[model];
      if (!sess) {
        var urls = [ONNX_BASE + '/' + SITE + '/' + model + '.onnx', '../onnx/' + SITE + '/' + model + '.onnx'];
        for (var u = 0; u < urls.length && !sess; u++) {
          try { sess = await ort.InferenceSession.create(urls[u]); } catch (e) { sess = null; }
        }
        if (!sess) throw new Error('model file unreachable (remote + bundled)');
        sessCache[model] = sess;
      }
      var feeds = {}; feeds[sess.inputNames[0]] = new ort.Tensor('float32', flat, [1, 29, 9]);
      var out = await sess.run(feeds);
      var diffs = Array.from(out[sess.outputNames[0]].data);
      if (diffs.length !== 7 || diffs.some(function (v) { return !isFinite(v); })) throw new Error('bad model output');
      return diffs.map(function (d, l) { return Math.exp(last + d * tsd[l]); });
    }
    if (PARAM_D[model]) {
      /* Remote-first (mirrors bigModelLive), but validate the output:
         the current hydrotwin-models GP params are an 11-feature
         generation whose SWE feature has zero training variance at
         snow-free stations (fsd = 0), which makes GPForecast return
         NaN. On a non-finite result, fall back to the bundled
         8-feature params in ../params/ — the project's own fallback
         copy — instead of failing the model. */
      var rows = [];
      var pv = flows[win30[0]];
      for (i = 1; i < 30; i++) {
        var dt2 = win30[i], t2 = wx[dt2], q2 = flows[dt2];
        rows.push([t2[0], t2[1], (t2[0] + t2[1]) / 2, t2[2], q2, q2 > pv ? 1 : 0]);
        pv = q2;
      }
      var purls = [PARAMS_BASE + '/' + SITE + '/' + PARAM_D[model] + '.json', '../params/' + SITE + '/' + PARAM_D[model] + '.json'];
      var lastErr = null;
      for (var p = 0; p < purls.length; p++) {
        var P = null;
        try { P = await fetchJ(purls[p], 20000); } catch (e) { continue; }
        if (!P) continue;
        try {
          var fcP;
          if (model === 'ARIMA' || model === 'SARIMA') {
            var series = A.run.map(function (dstr) { return Math.log(flows[dstr]); });
            fcP = ARIMAForecast(series, P).map(function (v) { return Math.exp(v); });
          } else {
            fcP = GPForecast(rows, P, ss);
          }
          if (fcP && fcP.length === 7 && fcP.every(function (v) { return isFinite(v); })) return fcP;
          lastErr = new Error('bad model output');
        } catch (e) { lastErr = e; }
      }
      throw lastErr || new Error('params unreachable (remote + bundled)');
    }
    return null; /* GCN: no browser build — stays baked, labelled as such */
  }

  /* --------------------------------------- classic live renderers */
  var COL = ['#2F80D1', '#E0852A', '#9E61CC', '#D1495B', '#8A8F98', '#1BA3A3', '#E36BA8', '#4D6E8A', '#7AE07A', '#FFD24D', '#4CC9F0', '#C9CED6'];
  var FM = null;
  function flowRange() {
    if (FM) return FM;
    var fmin = Infinity, fmax = -Infinity, i, m, l;
    for (i = 0; i < D.n; i++) { var v = D.flow[i]; if (v != null) { fmin = Math.min(fmin, v); fmax = Math.max(fmax, v); } }
    for (m = 0; m < (D.pred || []).length; m++) for (l = 0; l < D.pred[m].length; l++) for (i = 0; i < D.n; i++) { var p = D.pred[m][l][i]; if (p != null) { fmin = Math.min(fmin, p); fmax = Math.max(fmax, p); } }
    if (D.hi) for (m = 0; m < D.hi.length; m++) for (l = 0; l < D.hi[m].length; l++) for (i = 0; i < D.n; i++) { var h = D.hi[m][l][i]; if (h != null) fmax = Math.max(fmax, h); }
    FM = { lo: Math.max(1, fmin), hi: fmax };
    return FM;
  }
  function fmtQ(v) { return v == null ? '—' : Math.round(v).toLocaleString('en-US'); }
  function curModelIdx() { return (window.HT && window.HT.S) ? window.HT.S.model : 0; }

  function renderBoard() {
    var slot = $('hts-board-slot'); if (!slot) return;
    var cv = slot.querySelector('canvas'); if (!cv) return;
    var g = cv.getContext('2d'); if (!g) return;
    var W = cv.width, H = cv.height, pad = 60, top = 90, bot = H - 40, win = 90, L = 7;
    var fr = flowRange();
    var lnorm = function (v) { return Math.min(1, Math.max(0, (Math.log(v) - Math.log(fr.lo)) / (Math.log(fr.hi) - Math.log(fr.lo)))); };
    var issueI = dayIdx(LA.issue), start = issueI - win + 1, cols = win + L;
    var X = function (i) { return pad + (i - start) / (cols - 1) * (W - 2 * pad); };
    var Y = function (v) { return bot - lnorm(v) * (bot - top); };
    g.fillStyle = '#14223A'; g.beginPath(); if (g.roundRect) g.roundRect(0, 0, W, H, 30); else g.rect(0, 0, W, H); g.fill();
    var mi = curModelIdx(), mname = D.models[mi];
    g.fillStyle = '#F5F6F2'; g.font = '600 44px Arial'; g.fillText('Last 90 days of flow', pad, 60);
    g.fillStyle = '#6FB0F0'; g.fillText('— observed', 560, 60);
    g.fillStyle = '#7AE07A'; g.fillText('● LIVE', 850, 60);
    g.strokeStyle = 'rgba(255,255,255,0.12)'; g.lineWidth = 2;
    for (var k = 0; k <= 4; k++) { g.beginPath(); g.moveTo(pad, top + k * (bot - top) / 4); g.lineTo(W - pad, top + k * (bot - top) / 4); g.stroke(); }
    function line(get, color, w, dash, upto) {
      g.strokeStyle = color; g.lineWidth = w; g.setLineDash(dash || []); g.beginPath();
      var first = true;
      for (var i = start; i <= upto; i++) {
        var v = get(i); if (v == null) { first = true; continue; }
        if (first) { g.moveTo(X(i), Y(v)); first = false; } else g.lineTo(X(i), Y(v));
      }
      g.stroke(); g.setLineDash([]);
    }
    var bakedI = dayIdx(BAKED_END);
    line(function (i) { return LA.A.flows[addDays(D.start, i)]; }, '#6FB0F0', 7, null, Math.min(issueI, bakedI));
    if (issueI > bakedI) {
      g.strokeStyle = '#7AE07A'; g.lineWidth = 7; g.beginPath();
      var startedL = false;
      for (var li = bakedI; li <= issueI; li++) {
        var lv = LA.A.flows[addDays(D.start, li)]; if (lv == null) { startedL = false; continue; }
        if (!startedL) { g.moveTo(X(li), Y(lv)); startedL = true; } else g.lineTo(X(li), Y(lv));
      }
      g.stroke();
    }
    var fc = LA.fc[mname];
    if (fc) {
      g.strokeStyle = COL[mi % COL.length]; g.lineWidth = 7; g.beginPath();
      g.moveTo(X(issueI), Y(LA.A.flows[LA.issue]));
      for (var l = 1; l <= L; l++) g.lineTo(X(issueI + l), Y(fc[l - 1]));
      g.stroke();
    }
    if (LA.oldOn && LA.old) drawOldFan(g, X, Y, mname, null);
    g.fillStyle = '#FFD24D'; g.beginPath(); g.arc(X(issueI), Y(LA.A.flows[LA.issue]), 12, 0, 7); g.fill();
    g.strokeStyle = 'rgba(255,255,255,0.4)'; g.setLineDash([8, 8]); g.beginPath(); g.moveTo(X(issueI), top); g.lineTo(X(issueI), bot); g.stroke(); g.setLineDash([]);
    g.fillStyle = '#BFD0E0'; g.font = '32px Arial';
    g.fillText('today · live issued ' + LA.issue, Math.min(X(issueI) - 40, W - 460), bot + 34);
    g.fillStyle = COL[mi % COL.length];
    g.fillText('— ' + mname + ' LIVE forecast', pad, bot + 34);
  }
  function drawOldFan(g, X, Y, mname, issueOverride) {
    var O = LA.old; if (!O || !O.pred[mname]) return;
    var issueI = issueOverride != null ? issueOverride : lastOldIssue(mname);
    if (issueI == null) return;
    var row = O.pred[mname][issueI - O.from_issue];
    if (!row) return;
    g.strokeStyle = '#C9CED6'; g.lineWidth = 4; g.setLineDash([10, 8]); g.beginPath();
    var anchor = (issueOverride != null) ? (D.flow[issueI]) : (LA.A ? LA.A.flows[addDays(D.start, issueI)] : D.flow[issueI]);
    if (anchor != null) g.moveTo(X(issueI), Y(anchor));
    var started = anchor != null;
    for (var l = 1; l <= 7; l++) {
      if (row[l - 1] == null) continue;
      if (!started) { g.moveTo(X(issueI + l), Y(row[l - 1])); started = true; } else g.lineTo(X(issueI + l), Y(row[l - 1]));
    }
    g.stroke(); g.setLineDash([]);
    g.fillStyle = '#C9CED6'; g.font = '28px Arial';
    g.fillText('— old weights (pre-drift-fix, issued ' + addDays(D.start, issueI) + ')', X(issueI) - 330, 60 + 44);
  }
  function renderFc() {
    if (!window.HT || !window.HT.fcPanel) return;
    var cv = window.HT.fcPanel.c, g = cv.getContext('2d');
    var W = cv.width, H = cv.height;
    var mi = curModelIdx(), mname = D.models[mi], fc = LA.fc[mname];
    g.clearRect(0, 0, W, H); g.fillStyle = 'rgba(12,18,28,0.97)'; g.beginPath(); if (g.roundRect) g.roundRect(0, 0, W, H, 30); else g.rect(0, 0, W, H); g.fill();
    g.font = '600 54px Arial'; g.fillStyle = COL[mi % COL.length]; g.fillText(mname, 40, 80);
    g.fillStyle = '#7AE07A'; g.fillText('· LIVE', 40 + g.measureText(mname).width + 20, 80);
    g.font = '600 30px Arial'; g.fillStyle = '#9FB3C8';
    g.fillText('Lead', 30, 140); g.fillText('Date', 120, 140); g.fillText('Forecast', 270, 140);
    if (LA.oldOn) g.fillText('Old wts', 470, 140);
    g.fillText('Observed', 640, 140);
    g.font = '32px Arial';
    for (var l = 1; l <= 7; l++) {
      var y = 186 + (l - 1) * 42;
      g.fillStyle = '#F5F6F2'; g.fillText('+' + l + 'd', 30, y);
      g.fillText(addDays(LA.issue, l).slice(5), 120, y);
      g.fillText(fc ? fmtQ(fc[l - 1]) : (LA.fcErr[mname] ? 'failed' : 'baked only'), 270, y);
      if (LA.oldOn && LA.old) {
        var oi = lastOldIssue(mname);
        var orow = oi != null ? LA.old.pred[mname][oi - LA.old.from_issue] : null;
        g.fillStyle = '#C9CED6'; g.fillText(orow ? fmtQ(orow[l - 1]) : '—', 470, y); g.fillStyle = '#F5F6F2';
      }
      g.fillText('—', 640, y);
    }
    g.fillStyle = '#9FB3C8'; g.font = '28px Arial';
    g.fillText('LIVE run in-browser · data through ' + LA.issue + ' · GCN has no browser build (stays baked)', 40, H - 24);
  }
  function renderDay() {
    if (!window.HT || !window.HT.dayPanel) return;
    var cv = window.HT.dayPanel.c, g = cv.getContext('2d');
    var W = cv.width, H = cv.height;
    g.clearRect(0, 0, W, H); g.fillStyle = 'rgba(12,18,28,0.97)'; g.beginPath(); if (g.roundRect) g.roundRect(0, 0, W, H, 30); else g.rect(0, 0, W, H); g.fill();
    var d = new Date(Date.parse(LA.issue + 'T00:00:00Z'));
    g.fillStyle = '#F5F6F2'; g.font = '600 56px Arial';
    g.fillText(d.toLocaleDateString('en-GB', { timeZone: 'UTC', weekday: 'short', day: '2-digit', month: 'short', year: 'numeric' }), 40, 80);
    g.fillStyle = '#7AE07A'; g.font = '600 30px Arial'; g.fillText('● LIVE', W - 150, 80);
    var w = LA.A.wx[LA.issue] || [null, null, 0];
    var q = LA.A.flows[LA.issue];
    var prev = LA.A.flows[addDays(LA.issue, -1)];
    var rows = [
      ['tmax_c', 'High temperature', w[0] == null ? 'no data' : w[0].toFixed(1) + ' °C', '#D1495B'],
      ['tmin_c', 'Low temperature', w[1] == null ? 'no data' : w[1].toFixed(1) + ' °C', '#3A6FE0'],
      ['tmean_c', 'Mean temperature', (w[0] == null || w[1] == null) ? 'no data' : ((w[0] + w[1]) / 2).toFixed(1) + ' °C', '#E08A2B'],
      ['precip_mm', 'Total precipitation', (w[2] || 0).toFixed(1) + ' mm', '#2F80D1'],
      ['flow_cfs', "Today's river flow", q == null ? 'no data' : fmtQ(q) + ' cfs', '#1BA3A3'],
      ['rising', 'Rising or falling', (q != null && prev != null) ? (q > prev ? 'rising (1)' : 'falling (0)') : 'no data', '#2E9B57']
    ];
    rows.forEach(function (r, ri) {
      var y = 140 + ri * 52;
      g.fillStyle = r[3]; g.fillRect(28, y - 28, 10, 34);
      g.font = '600 32px Courier New'; g.fillStyle = '#CFE0F2'; g.fillText(r[0], 52, y);
      g.font = '32px Arial'; g.fillStyle = '#9FB3C8'; g.fillText(r[1], 270, y);
      g.fillStyle = '#F5F6F2'; g.textAlign = 'right'; g.fillText(r[2], W - 36, y); g.textAlign = 'left';
    });
  }
  function renderDailyAll() { renderBoard(); renderFc(); renderDay(); }

  /* --------------------------------------- classic outlook live */
  var PANELS = [
    { side: 'weekly', dir: 'onnx_w', dacp: 'dacpw', leads: 12, cv: 'htwk-canvas', issueEl: 'htwk-issue', readEl: 'htwk-read', sel: 'htwk-model', lvl: 'htwk-lvl', on: 'htwk-on', xo: 8.6, xs: 21.2, labels: [-8, -4, 0, 4, 8, 12], unit: 'w', ctxLabel: 'observed weekly mean', note: 'cfs, weekly mean flow', ctxKind: 'week', leadName: 'Wk' },
    { side: 'monthly', dir: 'onnx_m', dacp: 'dacpm', leads: 6, cv: 'htmo-canvas', issueEl: 'htmo-issue', readEl: 'htmo-read', sel: 'htmo-model', lvl: 'htmo-lvl', on: 'htmo-on', xo: 4.6, xs: 11.2, labels: [-4, -2, 0, 2, 4, 6], unit: 'mo', ctxLabel: 'observed 30-day mean', note: 'cfs, 30-day mean flow', ctxKind: 'm30', leadName: 'Mo' },
    { side: 'yearly', dir: 'onnx_y', dacp: 'dacpy', leads: 12, cv: 'htyr-canvas', issueEl: 'htyr-issue', readEl: 'htyr-read', sel: 'htyr-model', lvl: 'htyr-lvl', on: 'htyr-on', xo: 4.6, xs: 17.2, labels: [-4, -2, 0, 3, 6, 9, 12], unit: 'mo', ctxLabel: 'observed 30-day mean', note: 'cfs, 30-day block mean flow', ctxKind: 'm30', leadName: 'Blk' }
  ];
  function drawOutlook(cv, P, ctx, fc, band) {
    var g = cv.getContext('2d'); if (!g) return;
    var cw = cv.width, ch = cv.height;
    g.clearRect(0, 0, cw, ch);
    var vals = [];
    ctx.concat(fc).forEach(function (p) { if (p[1] != null) vals.push(p[1]); });
    if (band) band.forEach(function (b) { if (b) { vals.push(b[0]); vals.push(b[1]); } });
    if (!vals.length) { g.fillStyle = '#9fb4c8'; g.font = '22px system-ui'; g.fillText('no live data', 18, 40); return; }
    var lo = Math.floor(Math.log10(Math.min.apply(null, vals))), hi = Math.ceil(Math.log10(Math.max.apply(null, vals)));
    if (hi <= lo) hi = lo + 1;
    var X0 = 64, X1 = cw - 14, Y0 = 12, Y1 = ch - 30;
    function X(x) { return X0 + (x + P.xo) / P.xs * (X1 - X0); }
    function Y(v) { var t = (Math.log10(Math.max(v, 1e-9)) - lo) / (hi - lo); return Y1 - t * (Y1 - Y0); }
    g.font = '19px system-ui'; g.textBaseline = 'middle';
    for (var e = lo; e <= hi; e++) {
      var yv = Math.pow(10, e), yy = Y(yv);
      g.strokeStyle = 'rgba(255,255,255,.13)'; g.beginPath(); g.moveTo(X0, yy); g.lineTo(X1, yy); g.stroke();
      g.fillStyle = '#9fb4c8'; g.fillText(fmtQ(yv), 6, yy);
    }
    g.strokeStyle = 'rgba(255,255,255,.3)'; g.beginPath(); g.moveTo(X(0), Y0); g.lineTo(X(0), Y1); g.stroke();
    g.fillStyle = '#9fb4c8';
    P.labels.forEach(function (x) { g.fillText(x === 0 ? 'issue' : (x > 0 ? '+' + x + P.unit : x + P.unit), X(x) - 10, Y1 + 15); });
    function line(pts, style, width, dash) {
      g.save(); g.strokeStyle = style; g.lineWidth = width; g.setLineDash(dash || []);
      g.beginPath(); var started = false;
      pts.forEach(function (p) { if (p[1] == null) { started = false; return; } var xx = X(p[0]), yy2 = Y(p[1]); if (!started) { g.moveTo(xx, yy2); started = true; } else g.lineTo(xx, yy2); });
      g.stroke(); g.restore();
    }
    if (band) {
      g.save(); g.fillStyle = 'rgba(76,201,240,.16)'; g.beginPath();
      var st2 = false;
      fc.forEach(function (p, k) { if (p[1] == null || !band[k]) return; var xx = X(p[0]), yy2 = Y(band[k][1]); if (!st2) { g.moveTo(xx, yy2); st2 = true; } else g.lineTo(xx, yy2); });
      for (var b = fc.length - 1; b >= 0; b--) { if (fc[b][1] == null || !band[b]) continue; g.lineTo(X(fc[b][0]), Y(band[b][0])); }
      g.closePath(); g.fill(); g.restore();
    }
    line(ctx, '#9fb4c8', 2);
    var fcLine = fc.slice();
    var lastC = ctx.length ? ctx[ctx.length - 1] : null;
    if (lastC && lastC[1] != null) fcLine = [[0, lastC[1]]].concat(fcLine);
    line(fcLine, '#4CC9F0', 2.5);
    g.fillStyle = '#4CC9F0'; g.fillText('— forecast (LIVE)', X(1.2), Y0 + 10);
    g.fillStyle = '#9fb4c8'; g.fillText('— ' + P.ctxLabel, X(-P.xo + 0.2), Y0 + 10);
  }
  async function outlookLive(P, A, ss) {
    var sc = await fetchJ('../' + P.side + '/' + SITE + '.json', 30000);
    var stats = sc.stats, mu = stats.mu, sd = stats.sd, tsd = stats.tsd;
    var selEl = $(P.sel);
    var model = (selEl && selEl.value) || sc.models[0];
    var note2 = '';
    if (NEURAL.indexOf(model) < 0) { note2 = ' · ' + model + ' is baked-dates only — Transformer shown live'; model = 'Transformer'; }
    var flows = A.flows, wx = A.wx, win30 = A.win30;
    var flat = new Float32Array(29 * 9);
    var prev = flows[win30[0]];
    for (var i = 1; i < 30; i++) {
      var dt = win30[i], t = wx[dt], q = flows[dt];
      if (!t || q == null) throw new Error('live window has gaps');
      var row = [t[0], t[1], (t[0] + t[1]) / 2, t[2], q, q > prev ? 1 : 0, ss.sms, ss.stmpF, ss.swe];
      prev = q;
      for (var j = 0; j < 9; j++) { var x = j === 4 ? Math.log(row[j]) : row[j]; flat[(i - 1) * 9 + j] = (x - mu[j]) / sd[j]; }
    }
    var last = Math.log(flows[win30[29]]);
    if (typeof ort === 'undefined') throw new Error('onnxruntime failed to load (CDN blocked?)');
    var sess = await ort.InferenceSession.create('../' + P.dir + '/' + SITE + '/' + model + '.onnx');
    var feeds = {}; feeds[sess.inputNames[0]] = new ort.Tensor('float32', flat, [1, 29, 9]);
    var out = await sess.run(feeds);
    var diffs = Array.from(out[sess.outputNames[0]].data);
    if (diffs.length !== P.leads || diffs.some(function (v) { return !isFinite(v); })) throw new Error('bad model output');
    var preds = diffs.map(function (d, k) { return Math.exp(last + d * tsd[k]); });
    var ctx = [], j2, d2, s, c, isoD, v;
    if (P.ctxKind === 'week') {
      for (j2 = 8; j2 >= 1; j2--) {
        s = 0; c = 0;
        for (d2 = 0; d2 < 7; d2++) { isoD = addDays(win30[29], -7 * (j2 - 1) - d2); v = flows[isoD]; if (v != null && v > 0) { s += v; c++; } }
        ctx.push([-j2, c >= 4 ? s / c : null]);
      }
    } else {
      for (j2 = 4; j2 >= 1; j2--) {
        s = 0; c = 0;
        for (d2 = 0; d2 < 30; d2++) { isoD = addDays(win30[29], -30 * (j2 - 1) - d2); v = flows[isoD]; if (v != null && v > 0) { s += v; c++; } }
        ctx.push([-j2, c >= 20 ? s / c : null]);
      }
    }
    var band = null;
    var onEl = $(P.on), lvEl = $(P.lvl);
    if (!onEl || onEl.checked) {
      try {
        var dq = await fetchJ('../' + P.dacp + '/' + SITE + '.json', 30000);
        var lvl = lvEl ? lvEl.value : '90';
        var q = dq.q_end && dq.q_end[model] ? dq.q_end[model][String(lvl)] : null;
        if (q) band = preds.map(function (vv, k) { return q[k] == null ? null : [vv * Math.exp(-q[k]), vv * Math.exp(q[k])]; });
      } catch (e) { band = null; }
    }
    var cv = $(P.cv);
    if (cv) drawOutlook(cv, P, ctx, preds.map(function (vv, k) { return [k + 1, vv]; }), band);
    var issueEl = $(P.issueEl);
    if (issueEl) issueEl.textContent = 'LIVE outlook · issued ' + win30[29] + ' (window ends ' + win30[29] + ') · ' + model + ' run in-browser' + note2;
    var readEl = $(P.readEl);
    if (readEl) {
      var html = '<table class="htwk-t"><tr><th>' + P.leadName + '</th><th>Period</th><th>Forecast</th>' + (band ? '<th>DACP</th>' : '') + '</tr>';
      preds.forEach(function (vv, k) {
        var a, b2;
        if (P.ctxKind === 'week') { a = addDays(win30[29], 7 * k + 1); b2 = addDays(win30[29], 7 * k + 7); }
        else { a = addDays(win30[29], 30 * k + 1); b2 = addDays(win30[29], 30 * k + 30); }
        html += '<tr><td>' + (k + 1) + '</td><td>' + a.slice(5) + ' – ' + b2.slice(5) + '</td><td>' + fmtQ(vv) + '</td>'
          + (band ? '<td>' + (band[k] ? fmtQ(band[k][0]) + ' – ' + fmtQ(band[k][1]) : '–') + '</td>' : '') + '</tr>';
      });
      html += '</table><div class="htwk-note">' + P.note + ' · LIVE — computed in-browser from data pulled just now</div>';
      readEl.innerHTML = html;
    }
    if (P.side === 'monthly') { var fe = $('htffmo-live'); if (fe) fe.style.display = ''; }
    return { model: model, issue: win30[29], preds: preds };
  }

  /* --------------------------------------- old weights (Task C) */
  async function loadOld() {
    if (LA.old) return LA.old;
    LA.old = await fetchJ('../oldfc/' + SITE + '.json', 30000);
    return LA.old;
  }
  function lastOldIssue(mname) {
    var O = LA.old; if (!O || !O.pred[mname]) return null;
    var rows = O.pred[mname];
    for (var k = rows.length - 1; k >= 0; k--) if (rows[k][0] != null) return O.from_issue + k;
    return null;
  }
  function oldTableHTML() {
    var O = LA.old; if (!O) return '';
    var html = '<div>Old vs current weights — fan at the last baked issue '
      + addDays(D.start, lastOldIssue(D.models[0]) || 0) + ' (pre-drift-fix bake, commit 0908430a8e). '
      + 'The browser ONNX/params stacks did not change in the drift fix, so in LIVE mode the old series is this baked fan at its true dates.</div>';
    html += '<table><tr><th>Model</th><th>+1d old</th><th>+1d current</th><th>+7d old</th><th>+7d current</th></tr>';
    D.models.forEach(function (m, mi) {
      var oi = lastOldIssue(m);
      var orow = oi != null ? O.pred[m][oi - O.from_issue] : null;
      var nrow = oi != null ? [0, 1, 2, 3, 4, 5, 6].map(function (l) { return D.pred[mi][l][oi]; }) : null;
      html += '<tr><td>' + m + '</td><td>' + (orow ? fmtQ(orow[0]) : '—') + '</td><td>' + (nrow ? fmtQ(nrow[0]) : '—')
        + '</td><td>' + (orow ? fmtQ(orow[6]) : '—') + '</td><td>' + (nrow ? fmtQ(nrow[6]) : '—') + '</td></tr>';
    });
    html += '</table>';
    return html;
  }
  async function onOldToggle() {
    var box = $('htla-old');
    LA.oldOn = !!(box && box.checked);
    var tbl = $('htla-oldtable');
    if (!LA.oldOn) {
      oldNote('');
      if (tbl) tbl.style.display = 'none';
      if (!IS3D && !LA.on && window.HT) window.HT.applyDay();
      if (!IS3D && LA.on) renderDailyAll();
      return;
    }
    oldNote('loading pre-fix forecasts…');
    try { await loadOld(); } catch (e) { oldNote('old-weights data unavailable: ' + (e.message || e)); return; }
    oldNote('old weights: pre-drift-fix bake (through ' + BAKED_END + ')');
    if (tbl) { tbl.innerHTML = oldTableHTML(); tbl.style.display = ''; }
    if (IS3D) {
      if (!LA.oldAppended) {
        var O = LA.old;
        LA.oldPredRows = {};
        Object.keys(O.pred).forEach(function (m) {
          var per = [];
          for (var l2 = 0; l2 < 7; l2++) {
            var a2 = new Array(D.n).fill(null);
            O.pred[m].forEach(function (row, k2) { a2[O.from_issue + k2] = row[l2]; });
            per.push(a2);
          }
          LA.oldPredRows[m] = per;
        });
        /* LiveAR precedent: an extra model in D.models/D.pred is cycled
           and drawn by the app itself. The pseudo-model carries the old
           Transformer weights (the full per-model table is above). */
        D.models.push('Old weights (pre-fix)');
        D.pred.push(LA.oldPredRows['Transformer']);
        LA.oldAppended = true;
        oldNote('old weights added to the model cycle as "Old weights (pre-fix)" (Transformer weights; full table above)');
      }
    } else {
      if (LA.on) { renderDailyAll(); return; }
      var oi = lastOldIssue(D.models[curModelIdx()]);
      if (oi != null && window.HT) {
        window.HT.setDay(oi);
        setTimeout(function () { drawOldOverlay(); }, 60);
      }
    }
  }
  function drawOldOverlay() {
    if (IS3D || !LA.oldOn || !LA.old || LA.on) return;
    var slot = $('hts-board-slot'); if (!slot) return;
    var cv = slot.querySelector('canvas'); if (!cv || !window.HT) return;
    var g = cv.getContext('2d'); if (!g) return;
    var W = cv.width, H = cv.height, pad = 60, top = 90, bot = H - 40, win = 90, L = 7;
    var fr = flowRange();
    var lnorm = function (v) { return Math.min(1, Math.max(0, (Math.log(v) - Math.log(fr.lo)) / (Math.log(fr.hi) - Math.log(fr.lo)))); };
    var S = window.HT.S;
    var start = Math.max(0, S.day - win + 1), cols = win + L;
    var X = function (i) { return pad + (i - start) / (cols - 1) * (W - 2 * pad); };
    var Y = function (v) { return bot - lnorm(v) * (bot - top); };
    drawOldFan(g, X, Y, D.models[S.model], S.day);
  }

  /* --------------------------------------- master Live actions */
  async function goLiveClassic() {
    note('pulling live data — USGS daily values + Open-Meteo + NRCS…');
    await loadOrt();
    var A = null;
    try { A = await window.htGapAssemble(); } catch (e) { A = null; }
    if (!A || A.win30[29] < BAKED_END) {
      note('live data did not pass the baked end (' + BAKED_END + ') — newest aligned day: ' + (A ? A.win30[29] : 'unavailable') + '. Staying baked.');
      return;
    }
    var ss = { sms: HTLA_STATS.med_sms, stmpF: HTLA_STATS.med_stmp, swe: 0 };
    try { ss = await window.fetchLiveSoilSnow(); } catch (e) { /* medians */ }
    LA.A = A; LA.issue = A.win30[29];
    LA.fc = {}; LA.fcErr = {};
    for (var mi = 0; mi < D.models.length; mi++) {
      var m = D.models[mi];
      try { LA.fc[m] = await dailyFc(m, A, ss); }
      catch (e) { LA.fc[m] = null; LA.fcErr[m] = (e && e.message) || String(e); }
    }
    LA.on = true;
    renderDailyAll();
    var done = [], failed = [];
    for (var p = 0; p < PANELS.length; p++) {
      try { LA.out[PANELS[p].side] = await outlookLive(PANELS[p], A, ss); done.push(PANELS[p].side); }
      catch (e) {
        failed.push(PANELS[p].side);
        var ie = $(PANELS[p].issueEl);
        if (ie) ie.textContent = 'live ' + PANELS[p].side + ' failed: ' + ((e && e.message) || e);
      }
    }
    var hh = new Date().toTimeString().slice(0, 5);
    $('htla-badge').style.display = '';
    $('htla-back').style.display = '';
    note('● LIVE · data through ' + LA.issue + ' · pulled ' + hh + ' · daily (all models) + ' + (done.join('/') || 'no') + ' outlooks recomputed in-browser'
      + (failed.length ? ' · failed: ' + failed.join('/') : '')
      + (LA.fcErr.GCN || LA.fc.GCN === null ? ' · GCN has no browser build (stays baked)' : ''));
  }
  function key(k) {
    var e1 = new KeyboardEvent('keydown', { key: k, bubbles: true, cancelable: true });
    document.dispatchEvent(e1);
    var e2 = new KeyboardEvent('keydown', { key: k, bubbles: true, cancelable: true });
    window.dispatchEvent(e2);
    if (document.body) {
      var e3 = new KeyboardEvent('keydown', { key: k, bubbles: true, cancelable: true });
      document.body.dispatchEvent(e3);
    }
  }
  var gpRedirectOn = false;
  function installGpRedirect() {
    if (gpRedirectOn || !window.fetch) return;
    gpRedirectOn = true;
    var of = window.fetch.bind(window);
    window.fetch = function (input, init) {
      try {
        var u = (typeof input === 'string') ? input : (input && input.url) || '';
        var m = u.match(/hydrotwin-models\/params\/(\d+)\/(GP_RBF|GP_Matern)\.json/);
        if (m) input = '../params/' + m[1] + '/' + m[2] + '.json';
      } catch (e) { /* pass through */ }
      return of(input, init);
    };
  }
  function goLive3D() {
    /* The app's bigModelLive fetches GP params remote-first; the current
       remote GP params NaN at snow-free stations (zero-variance SWE).
       Route those two file fetches to the bundled copies (same repo). */
    installGpRedirect();
    note('pulling live data — driving the page\'s own live paths (readout + big model + outlooks)…');
    key('g');
    setTimeout(function () { key('b'); }, 1500);
    ['htwk-live', 'htmo-live', 'htyr-live'].forEach(function (id) { var b = $(id); if (b) b.click(); });
    panelLive3D();
    var tries = 0;
    var iv = setInterval(function () {
      tries++;
      var pending = [];
      [['htwk-status', 'htwk-live'], ['htmo-status', 'htmo-live'], ['htyr-status', 'htyr-live']].forEach(function (pair) {
        var st = $(pair[0]);
        if (st && /still loading/.test(st.textContent)) { var b2 = $(pair[1]); if (b2) b2.click(); pending.push(pair[0]); }
      });
      var lv = $('livetxt');
      var dailyEnd = '';
      if (lv) { var m = lv.textContent.match(/ends (2026-\d\d-\d\d)/); if (m) dailyEnd = m[1]; }
      var issued = [];
      ['htwk-status', 'htmo-status', 'htyr-status'].forEach(function (id) {
        var st = $(id);
        if (st) { var mm = st.textContent.match(/live outlook issued (2026-\d\d-\d\d)/); if (mm) issued.push(id.slice(2, 4) + ' ' + mm[1]); }
      });
      if (dailyEnd || issued.length) {
        $('htla-badge').style.display = '';
        note('● LIVE · daily data through ' + (dailyEnd || '…') + (issued.length ? ' · outlooks issued ' + issued.join(' · ') : '') + ' · pulled ' + new Date().toTimeString().slice(0, 5));
      }
      if (tries >= 40 || (dailyEnd && issued.length >= 3)) clearInterval(iv);
    }, 6000);
  }
  /* ---------------- 3D daily panel live integration (Part 6) --------------
     The master Live on 3D drives the app readout (loadLive/bigModelLive)
     but the Flow & forecast panel reads only the baked D.pred/D.flow, whose
     last forecast issue is 2026-09-23 and last day 2026-09-30 — so after a
     Live run the panel stayed stuck at Sep 30 with "No model forecast on
     this day". Here the classic live engine (the same dailyFc used on the
     classic pages) computes every model fan for the live issue and the
     result is written into the app data: D.flow gains the live observed
     days and D.pred[m][l][liveIdx] the live fan, then the panel day is
     stepped to the live issue through the app own ArrowRight routing so
     drawFlow() renders it. Baked restore swaps the pristine snapshot back. */
  var panelBak3D = null, bakDay3D = null;
  function stepNext() {
    /* one single window-level dispatch: the shared key() helper fires on
       document+window+body, which would step the day up to 3 times */
    window.dispatchEvent(new KeyboardEvent("keydown", { key: "ArrowRight", bubbles: true, cancelable: true }));
  }
  async function panelLive3D() {
    try {
      var D3 = window.HT3D, S = window.__htS;
      if (!D3 || !S) return;
      if (bakDay3D == null) bakDay3D = S.day;
      var A = null;
      try { A = await window.htGapAssemble(); } catch (e) { A = null; }
      if (!A || !A.win30 || A.win30[29] < BAKED_END) return;
      var ss = { sms: HTLA_STATS.med_sms, stmpF: HTLA_STATS.med_stmp, swe: 0 };
      try { var s2 = await window.fetchLiveSoilSnow(window.HT3D); if (s2) ss = s2; } catch (e) { /* medians */ }
      LA.A = A; LA.issue = A.win30[29];
      LA.fc = {}; LA.fcErr = {};
      for (var mi = 0; mi < D3.models.length; mi++) {
        var m = D3.models[mi];
        try { LA.fc[m] = await dailyFc(m, A, ss); }
        catch (e) { LA.fc[m] = null; LA.fcErr[m] = (e && e.message) || String(e); }
      }
      var liveIdx = Math.round((Date.parse(LA.issue + "T00:00:00Z") - Date.parse(D3.start + "T00:00:00Z")) / 86400000);
      if (liveIdx < D3.n) return;
      if (!panelBak3D) {
        panelBak3D = { n: D3.n, flow: D3.flow.slice(),
          pred: D3.pred.map(function (mdl) { return mdl.map(function (ld) { return ld.slice(); }); }) };
      }
      var nf = panelBak3D.flow.slice();
      for (var k = panelBak3D.n; k <= liveIdx; k++) {
        var ds = addDays(D3.start, k);
        nf[k] = (A.flows[ds] != null) ? A.flows[ds] : null;
      }
      D3.flow = nf;
      D3.pred = panelBak3D.pred.map(function (mdl, mi2) {
        var fc = LA.fc[D3.models[mi2]];
        return mdl.map(function (ld, li) {
          var c = ld.slice();
          if (fc && fc[li] != null) c[liveIdx] = fc[li];
          return c;
        });
      });
      D3.n = liveIdx + 1;
      LA.on = true;
      var bk = $("htla-back"); if (bk) bk.style.display = "";
      S.day = liveIdx - 1;
      stepNext();
      var nt = $("htla-note");
      if (nt && nt.textContent.indexOf("daily panel live") < 0) nt.textContent += " · daily panel live @ " + LA.issue;
    } catch (e) { /* panel stays baked; the readout live path is unaffected */ }
  }
  function restorePanel3D() {
    if (!panelBak3D) return;
    var D3 = window.HT3D, S = window.__htS;
    if (D3) { D3.flow = panelBak3D.flow; D3.pred = panelBak3D.pred; D3.n = panelBak3D.n; }
    panelBak3D = null;
    if (D3 && S) {
      var bd = (bakDay3D != null) ? bakDay3D : D3.n - 8;
      bd = Math.max(1, Math.min(bd, D3.n - 1));
      S.day = bd - 1;
      stepNext();
    }
  }
  async function goLive() {
    if (LA.busy) return;
    LA.busy = true;
    var btn = $('htla-go'); if (btn) btn.textContent = '⏳ LIVE — pulling data…';
    try {
      if (IS3D) goLive3D(); else await goLiveClassic();
    } catch (e) {
      note('live failed: ' + ((e && e.message) || e));
    }
    if (btn) btn.textContent = '▶ LIVE — pull today\'s data · all charts';
    LA.busy = false;
  }
  $('htla-go').addEventListener('click', goLive);
  $('htla-old').addEventListener('change', onOldToggle);
  $('htla-back').addEventListener('click', function () {
    LA.on = false;
    $('htla-badge').style.display = 'none';
    $('htla-back').style.display = 'none';
    note('baked data through ' + BAKED_END);
    if (IS3D) restorePanel3D();
    if (!IS3D && window.HT) window.HT.applyDay();
    ['htwk-back', 'htmo-back', 'htyr-back'].forEach(function (id) { var b = $(id); if (b) b.click(); });
  });
  if (!IS3D) {
    document.addEventListener('change', function (e) {
      if (!LA.on && !LA.oldOn) return;
      if (e.target && (e.target.id === 'hts-model' || e.target.id === 'hts-lead')) {
        setTimeout(function () { if (LA.on) renderDailyAll(); else drawOldOverlay(); }, 60);
      }
      if (e.target && e.target.id === 'ht-date' && LA.on) {
        LA.on = false;
        $('htla-badge').style.display = 'none';
        $('htla-back').style.display = 'none';
        note('baked data through ' + BAKED_END);
      }
    }, true);
    document.addEventListener('click', function (e) {
      if (!LA.on && !LA.oldOn) return;
      var t = e.target;
      if (t && t.closest && t.closest('[data-act]')) {
        setTimeout(function () { if (LA.on) renderDailyAll(); else drawOldOverlay(); }, 60);
      }
    }, true);
  }
})();
"""

# ------------------------------------------------------------------- main


def _apply_rmse(html, page_name):
    """Insert the ht-rmsefield v1 readout into a page's v2 bar block,
    immediately after the old-weights checkbox label. Returns the new
    html, or None when the page's station has no backtest row or
    either anchor does not match exactly once (the caller then leaves
    the page untouched and warns — the position-refresh precedent)."""
    m = re.search(r"USGS-(\d{8})", page_name)
    if not m or m.group(1) not in RMSE_AB:
        return None
    if (html.count(RMSE_OLD_CSS), html.count(RMSE_OLD_HTML)) != (1, 1):
        return None
    old, new = RMSE_AB[m.group(1)]
    text = f"RMSE old {old:.4f} · new {new:.4f} · Δ {new - old:+.4f}"
    span = f'<span id="htla-rmse" title="{RMSE_TITLE}">{text}</span>'
    new_anchor = ("old weights (pre-drift-fix)</label>'\n"
                  f"    + '{span}'\n"
                  "    + '<span id=\"htla-oldnote\"></span>'")
    return (html.replace(RMSE_OLD_CSS, RMSE_NEW_CSS)
                .replace(RMSE_OLD_HTML, new_anchor))


PULLFWD_JS = r"""
/* ht-pullfwd v1 */
(function () {
  'use strict';
  if (window.__htPullFwdOn) return;
  window.__htPullFwdOn = true;
  var D = window.HT_DATA || window.HT3D || {};
  var IS3D = !!window.HT3D;
  var SITE = ((D.station || {}).stationId || '').replace('USGS-', '') || D.site || '';
  var DAY = 864e5;
  function iso(t) { return new Date(t).toISOString().slice(0, 10); }
  function addDays(dstr, k) { return iso(Date.parse(dstr + 'T00:00:00Z') + k * DAY); }
  function dayIdx(dstr) { return Math.round((Date.parse(dstr + 'T00:00:00Z') - Date.parse((D.start || '2001-10-01') + 'T00:00:00Z')) / DAY); }
  var BAKED_N = D.n || 0;
  var PF = window.__htPullFwd = {
    site: SITE, bakedEnd: BAKED_N ? addDays(D.start, BAKED_N - 1) : '',
    latest: null, source: null, extN: 0, pullHandled: ''
  };
  if (typeof window.__htPullN !== 'number') window.__htPullN = 0;

  function fetchJ(url, ms) {
    return new Promise(function (res, rej) {
      var c = new AbortController();
      var t = setTimeout(function () { c.abort(); }, ms || 15000);
      fetch(url, { signal: c.signal, cache: 'no-store' }).then(function (r) {
        clearTimeout(t);
        if (!r.ok) throw new Error('HTTP ' + r.status);
        return r.json();
      }).then(res, rej);
    });
  }
  function setMax(dstr) {
    var el = document.getElementById('ht-date');
    if (el && dstr && (!el.max || dstr > el.max)) el.max = dstr;
  }
  /* Extend the page's own data arrays with a pulled series
     ({date: {q, tx, tn, pr}}). Fresh values overwrite the overlap
     window (the LIVE assembly's fresh-wins rule); past the baked end
     the arrays grow to the newest pulled date and forecast slots are
     null-filled (observed data only, until a LIVE pull computes fans
     for its issue date). Sets window.__htPullN, the classic stats
     script's dynamic day bound. */
  function extend(days, latest) {
    var start = D.start || '2001-10-01';
    var L = dayIdx(latest);
    if (L < 0 || !days) return false;
    function rec(k) { return days[addDays(start, k)] || null; }
    function qOf(r) { return (r && r.q != null && r.q > 0) ? r.q : null; }
    var k, r;
    if (IS3D) {
      var nf = (D.flow || []).slice();
      for (k = 0; k < BAKED_N; k++) { var q0 = qOf(rec(k)); if (q0 != null) nf[k] = q0; }
      if (L >= BAKED_N) {
        nf.length = L + 1;
        for (k = BAKED_N; k <= L; k++) { var q1 = qOf(rec(k)); nf[k] = (q1 != null) ? q1 : null; }
        D.pred = (D.pred || []).map(function (mdl) {
          return mdl.map(function (ld) {
            var c = ld.slice(); c.length = L + 1;
            for (var j = BAKED_N; j <= L; j++) if (c[j] === undefined) c[j] = null;
            return c;
          });
        });
        D.n = L + 1;
      }
      D.flow = nf;
    } else {
      var cols = [['flow', 'q'], ['tmax', 'tx'], ['tmin', 'tn'], ['precip', 'pr']];
      var ext = {};
      cols.forEach(function (pair) {
        var a = (D[pair[0]] || []).slice();
        for (k = 0; k < BAKED_N; k++) { r = rec(k); if (r && r[pair[1]] != null) a[k] = r[pair[1]]; }
        if (L >= BAKED_N) {
          a.length = L + 1;
          for (k = BAKED_N; k <= L; k++) { r = rec(k); a[k] = (r && r[pair[1]] != null) ? r[pair[1]] : null; }
        }
        ext[pair[0]] = a;
      });
      var tm = (D.tmean || []).slice();
      var rg = (D.rising || []).slice();
      var top = (L >= BAKED_N) ? L : BAKED_N - 1;
      if (L >= BAKED_N) { tm.length = L + 1; rg.length = L + 1; }
      for (k = 0; k <= top; k++) {
        r = rec(k);
        if (r && r.tx != null && r.tn != null) tm[k] = (r.tx + r.tn) / 2;
        else if (k >= BAKED_N && tm[k] === undefined) tm[k] = null;
        if (k > 0 && (k >= BAKED_N || (r && r.q != null))) {
          var qa = ext.flow[k], qb = ext.flow[k - 1];
          rg[k] = (qa != null && qb != null) ? (qa > qb ? 1 : 0) : (k >= BAKED_N ? 0 : rg[k]);
        } else if (k >= BAKED_N && rg[k] === undefined) rg[k] = 0;
      }
      cols.forEach(function (pair) { D[pair[0]] = ext[pair[0]]; });
      D.tmean = tm; D.rising = rg;
      if (L >= BAKED_N) {
        D.pred = (D.pred || []).map(function (mdl) {
          return mdl.map(function (ld) {
            var c = ld.slice(); c.length = L + 1;
            for (var j = BAKED_N; j <= L; j++) if (c[j] === undefined) c[j] = null;
            return c;
          });
        });
        D.n = L + 1;
      }
    }
    if (L >= BAKED_N) { PF.extN = L + 1; window.__htPullN = L + 1; }
    if (!PF.latest || latest > PF.latest) PF.latest = latest;
    return true;
  }
  /* After a LIVE pull: land the calendar on the pull's issue date.
     On 3D the scene already sits at the issue (panelLive3D); if the
     manifest extension had already grown HT3D.n past the issue index
     panelLive3D returned early by design — and on that path it never
     sets LA.on (verified live: LA.issue and LA.fc complete while
     LA.on stays false) — so write the pull's fans (LA.fc, already
     computed) in and step to the issue here. The watcher below
     therefore fires on LA.on OR on LA.fc holding an entry for every
     model (fc is filled per model, failures included as nulls, so
     key completeness means the fan computation has finished). On
     classic the live board already renders the pull — only the
     calendar moves (a dispatched change would exit LIVE mode). */
  function onPulled(issue) {
    setMax(issue);
    var el = document.getElementById('ht-date');
    if (el) el.value = issue;
    if (!PF.latest || issue > PF.latest) PF.latest = issue;
    PF.source = 'pull';
    if (!IS3D) return;
    var D3 = window.HT3D, S = window.__htS, LA = window.__htla;
    var li = dayIdx(issue);
    if (!D3 || !S || !LA || !LA.fc || li < BAKED_N || li >= D3.n) return;
    var wrote = false;
    (D3.models || []).forEach(function (mn, mi) {
      var fc = LA.fc[mn]; if (!fc || !D3.pred[mi]) return;
      for (var l = 0; l < 7; l++) {
        if (fc[l] != null && D3.pred[mi][l] && D3.pred[mi][l][li] == null) {
          D3.pred[mi][l][li] = fc[l]; wrote = true;
        }
      }
    });
    if (wrote) {
      /* step onto the issue even if the scene already sits there:
         the step is what makes the panel redraw with the fans just
         written into D3.pred */
      S.day = li - 1;
      window.dispatchEvent(new KeyboardEvent('keydown', { key: 'ArrowRight', bubbles: true, cancelable: true }));
    }
  }
  function fcComplete() {
    var LA = window.__htla, D3 = window.HT3D;
    if (!IS3D || !LA || !LA.fc || !D3 || !D3.models || !D3.models.length) return false;
    return D3.models.every(function (m) {
      return Object.prototype.hasOwnProperty.call(LA.fc, m);
    });
  }
  setInterval(function () {
    var LA = window.__htla;
    if (LA && LA.issue && LA.issue !== PF.pullHandled && (LA.on || fcComplete())) {
      PF.pullHandled = LA.issue;
      try { onPulled(LA.issue); } catch (e) { /* calendar stays as-is */ }
    }
  }, 1500);
  /* On load: the pull-snapshots manifest forwards the calendar to
     wherever the newest saved data is, for every visitor. */
  function loadManifest() {
    fetchJ('../data/pulls/manifest.json?htpf=' + Date.now(), 12000).then(function (man) {
      var ent = man && man.stations && man.stations[SITE];
      if (!ent || !ent.latest_date) return;
      setMax(ent.latest_date);
      if (!ent.snapshot_key) return;
      return fetchJ('../' + ent.snapshot_key + '?htpf=' + Date.now(), 20000).then(function (snap) {
        if (snap && snap.days && extend(snap.days, ent.latest_date)) PF.source = 'manifest';
      });
    }).catch(function () { /* no snapshots published yet — page stays baked */ });
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', loadManifest);
  else loadManifest();
})();
"""


def _apply_pullfwd(html, page_name):
    """Append the ht-pullfwd v1 block to a page (plus, on classic
    pages, the two clamp swaps that let the stats script's calendar
    pass the baked end). Returns the new html, or None when a classic
    page's clamp anchors do not match exactly once each — in their
    old or their already-swapped form (the caller then leaves the
    page untouched and warns). Idempotent: pages already carrying
    PULLFWD_SIG are returned unchanged."""
    if PULLFWD_SIG in html:
        return html
    if not page_name.endswith("-3d.html"):
        counts = (html.count(PULLFWD_CLAMP_OLD), html.count(PULLFWD_WRAP_OLD),
                  html.count(PULLFWD_CLAMP_NEW), html.count(PULLFWD_WRAP_NEW))
        if counts == (1, 1, 0, 0):
            html = (html.replace(PULLFWD_CLAMP_OLD, PULLFWD_CLAMP_NEW)
                        .replace(PULLFWD_WRAP_OLD, PULLFWD_WRAP_NEW))
        elif counts != (0, 0, 1, 1):
            print(f"  !! {page_name}: pullfwd classic clamp anchors matched "
                  f"{counts} (want (1, 1, 0, 0) or (0, 0, 1, 1)); left untouched")
            return None
    block = "\n<script>\n" + PULLFWD_JS + "\n</script>\n"
    i = html.rfind("</body>")
    if i < 0:
        print(f"  !! {page_name}: no </body> for pullfwd block")
        return None
    return html[:i] + block + html[i:]


def main():
    donor_path = STATIONS / "USGS-08057000-3d.html"
    donor = donor_path.read_text(encoding="utf-8")
    soilst = _extract_const(donor, "SOILST")
    snotel = _extract_const(donor, "SNOTEL")
    gp_fn = _extract_fn(donor, "function GPForecast")
    arima_fn = _extract_fn(donor, "function ARIMAForecast")
    arma_fn = _extract_fn(donor, "function armaMean")

    pages = sorted(STATIONS.glob("*.html"))
    done = skipped = upgraded = refreshed = rmse = pullfwd = 0
    for page in pages:
        html = page.read_text(encoding="utf-8")
        if MARKER in html:
            dirty = False
            if POS_SIG not in html:
                counts = (html.count(POS_OLD_BAR), html.count(POS_OLD_BORDER),
                          html.count(POS_OLD_MOVED))
                if counts == (1, 1, 1):
                    html = (html.replace(POS_OLD_BAR, POS_NEW_BAR)
                                .replace(POS_OLD_BORDER, POS_NEW_BORDER)
                                .replace(POS_OLD_MOVED, POS_NEW_MOVED))
                    refreshed += 1
                    dirty = True
                else:
                    print(f"  !! {page.name}: v2 block present but position "
                          f"anchors matched {counts} (want (1, 1, 1)); left untouched")
                    skipped += 1
                    continue
            if RMSE_SIG not in html:
                new_html = _apply_rmse(html, page.name)
                if new_html is None:
                    print(f"  !! {page.name}: v2 block present but RMSE "
                          f"anchors did not match exactly once; left untouched")
                    skipped += 1
                    continue
                html = new_html
                rmse += 1
                dirty = True
            if PULLFWD_SIG not in html:
                new_html = _apply_pullfwd(html, page.name)
                if new_html is None:
                    print(f"  !! {page.name}: v2 block present but pullfwd "
                          f"anchors did not match; left untouched")
                    skipped += 1
                    continue
                html = new_html
                pullfwd += 1
                dirty = True
            if dirty:
                page.write_text(html, encoding="utf-8")
            else:
                skipped += 1
            continue
        if any(m in html for m in OLD_MARKERS):
            html, n_old = OLD_BLOCK_RE.subn("", html)
            if n_old != 1:
                print(f"  !! {page.name}: old block removal matched {n_old} blocks")
                continue
            upgraded += 1
        if page.name.endswith("-3d.html"):
            stats = _bigstats(html)
        else:
            sib3d = STATIONS / page.name.replace(".html", "-3d.html")
            if not sib3d.exists():
                print(f"  !! {page.name}: no -3d sibling for BIGSTATS harvest")
                continue
            stats = _bigstats(sib3d.read_text(encoding="utf-8"))
        js = (JS_TEMPLATE
              .replace("__BIGSTATS__", stats)
              .replace("__SOILST__", soilst)
              .replace("__SNOTEL__", snotel)
              .replace("__GP_FN__", gp_fn)
              .replace("__ARIMA_FN__", arima_fn)
              .replace("__ARMA_FN__", arma_fn))
        block = "\n<script>\n" + js + "\n</script>\n"
        i = html.rfind("</body>")
        if i < 0:
            print(f"  !! {page.name}: no </body>")
            continue
        html = html[:i] + block + html[i:]
        new_html = _apply_rmse(html, page.name)
        if new_html is None:
            print(f"  !! {page.name}: fresh v2 block built but RMSE "
                  f"anchors did not match exactly once; left unpatched")
            continue
        new_html = _apply_pullfwd(new_html, page.name)
        if new_html is None:
            print(f"  !! {page.name}: fresh v2 block built but pullfwd "
                  f"anchors did not match; left unpatched")
            continue
        page.write_text(new_html, encoding="utf-8")
        done += 1
        rmse += 1
        pullfwd += 1
    print(f"patch_liveall: patched {done} (upgraded {upgraded}), refreshed {refreshed}, rmse {rmse}, pullfwd {pullfwd}, skipped {skipped} (already marked)")


if __name__ == "__main__":
    sys.exit(main())
