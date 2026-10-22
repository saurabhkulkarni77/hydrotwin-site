#!/usr/bin/env python3
"""Live-mode stall fix for the DEV station pages (dev only).

Root cause (diagnosed 2026-10-16 against the dev site): the live data
path itself is healthy — htGapAssemble completes (~23 s), soil/snow
(~4 s) and the weekly/daily ONNX sessions (~2–11 s) all succeed — but
several awaits in the live path have NO timeout, so one stalled
connection freezes Live mode forever with the status stuck at
"fetching newest daily data…":

  * loadLive():      raw fetch() of USGS IV + Open-Meteo current
  * fetchLiveSoilSnow(): raw fetch() of Open-Meteo current (its AWDB
                     calls are timed, this one was not)
  * bigModelLive():  raw fetch() of GP/ARIMA params; ort session create
  * weekly/monthly runLive(): ort.InferenceSession.create()

Fix, in two parts:

Part 1 (source patch, 3D module code): the three raw fetches are
replaced with the module's own timed fetchJson() helper (or an
AbortController-timed fetch where the response object is needed), so
the module-internal callers (act() -> loadLive / bigModelLive, which
are module-scoped and unreachable from window) are bounded too.

Part 2 (appended guarded script, all pages): wraps the window-visible
live entry points with Promise.race timeouts so every live stage is
bounded and failures surface as honest status text instead of a
silent hang:

  * fetchLiveSoilSnow -> 45 s cap, then training-median fallback
    (preserves its "never throws" contract)
  * htGapAssemble     -> 100 s cap, then throws so callers take the
    baked-assemble fallback they already implement
  * htBakedAssemble   -> 170 s cap, then throws so callers report the
    failure instead of hanging
  * ort.InferenceSession.create -> 90 s cap (wrapped as soon as the
    onnxruntime global appears)
  * loadLive          -> 60 s watchdog: status note that the feeds are
    slow and the panel still shows baked data (the original call keeps
    running in the background and wins if it lands)
  * bigModelLive      -> 300 s watchdog: status note + busy flag reset
    attempt; the original call keeps running in the background

It also annotates the weekly/monthly live status line with elapsed
seconds while a live run is in flight, so a slow-but-working run no
longer looks frozen.

Part 3 (ht-loadmodel v1, appended 2026-10-22): a "Load new model"
button next to the 3D pages' "retrain on GitHub" button. Retraining
publishes fresh weights to the hydrotwin-models Pages source
(onnx/<site>/<Model>.onnx, Cache-Control max-age=600), but an open page
keeps the sessions it already created — the daily engine caches them
in a private sessCache and the big-model engine in BIG.sess — so new
weights normally need a redeploy or a lucky reload. Part 3:
  * wraps ort.InferenceSession.create so sessions for THIS station's
    daily/big-model artifacts are proxies whose inner real session
    can be swapped atomically (engines keep their cached proxy);
  * the button fetches every neural model's artifact from the models
    source with cache:'no-store' + a cache-bust query, builds all new
    sessions first, and only then swaps them in — any failure leaves
    the previously running model untouched;
  * unchecks the "old weights (pre-drift-fix)" checkbox (dispatching
    its change event) so the UI never claims old weights while
    running new ones;
  * re-runs the forecast for the currently selected date in-browser
    (same tensor build + normalisation as the htla daily engine,
    stats extracted from the page's own HTLA_STATS at patch time) and
    writes the fan into HT3D.pred, redrawing through the app's own
    ArrowRight day-step routing like htla's panelLive3D;
  * after a load, a fetch wrapper cache-busts models-source URLs so
    the classical params JSONs (fetched per live run) are fresh too;
  * if Live mode is on, it re-clicks the htla Live button so the live
    fans recompute through the proxies with the new weights.
Only pages carrying id="retrainTop" (the 14 3D pages) get Part 3;
classic pages are untouched by it. Its block and button are refreshed
in place on every run (own marker), independent of Parts 1-2.

Idempotent: pages carrying the v2 MARKER with no old anchors left are
skipped; pages carrying only the v1 append (first deploy) are upgraded
in place (part 1 applied, marker bumped).
Run from the repo root: python3 build25/patch_livefix.py
"""
import sys
from pathlib import Path

MARKER = "ht-livefix v2"
OLD_MARKER = "ht-livefix v1"

# ---------------- part 1: timed-fetch source replacements ----------------
# Each (old, new) must occur exactly once on pages that carry the 3D
# module's live code; pages without the code are skipped per-anchor.
PART1 = [
    # fetchLiveSoilSnow: Open-Meteo current conditions (was raw fetch)
    ("const rw = await fetch(`https://api.open-meteo.com/v1/forecast?latitude=${D.lat}&longitude=${D.lon}&current=soil_temperature_6cm,soil_moisture_3_9cm,snow_depth&timezone=auto`).then(r => r.json()).catch(() => null);",
     "const rw = await fetchJson(`https://api.open-meteo.com/v1/forecast?latitude=${D.lat}&longitude=${D.lon}&current=soil_temperature_6cm,soil_moisture_3_9cm,snow_depth&timezone=auto`, 20000).catch(() => null);"),
    # loadLive: USGS instantaneous values (was raw fetch, no catch)
    ("fetch(`https://waterservices.usgs.gov/nwis/iv/?format=json&sites=${D.site}&parameterCd=00060&siteStatus=all`).then(r => r.json()),",
     "fetchJson(`https://waterservices.usgs.gov/nwis/iv/?format=json&sites=${D.site}&parameterCd=00060&siteStatus=all`, 30000),"),
    # loadLive: Open-Meteo current conditions (was raw fetch)
    ("fetch(`https://api.open-meteo.com/v1/forecast?latitude=${D.lat}&longitude=${D.lon}&current=temperature_2m,precipitation,weather_code,wind_speed_10m,soil_temperature_6cm,soil_moisture_3_9cm,snow_depth&timezone=auto`).then(r => r.json()).catch(() => null)",
     "fetchJson(`https://api.open-meteo.com/v1/forecast?latitude=${D.lat}&longitude=${D.lon}&current=temperature_2m,precipitation,weather_code,wind_speed_10m,soil_temperature_6cm,soil_moisture_3_9cm,snow_depth&timezone=auto`, 20000).catch(() => null)"),
    # bigModelLive: GP/ARIMA params fetch (was raw fetch; response object needed)
    ("const r = await fetch(u); if (!r.ok) continue; P = await r.json();",
     "const r = await fetch(u, { signal: (function () { const c = new AbortController(); setTimeout(() => c.abort(), 20000); return c.signal; })() }); if (!r.ok) continue; P = await r.json();"),
]

JS_BODY = r"""
<script>
/* ht-livefix v2 - bound every live stage with a timeout (dev).
 * See build25/patch_livefix.py for the diagnosis. Wrappers only:
 * the original functions keep their behaviour when they answer in
 * time; a stall now ends in an honest status message, not a hang. */
(function () {
  function race(p, ms, label) {
    return Promise.race([p, new Promise(function (_, rej) {
      setTimeout(function () { rej(new Error(label + ' timed out after ' + Math.round(ms / 1000) + 's')); }, ms);
    })]);
  }
  window.htRace = race;
  function note(t) { try { if (typeof $st === 'function') $st(t); } catch (e) {} }

  // The page's main script can execute after this appended script, so
  // installation is retried until every live entry point is wrapped
  // (polling lasts up to 30 minutes for very slow connections). Each
  // wrapper installs exactly once.
  var pending = { ss: true, gap: true, bk: true, ll: true, bm: true, ort: true };
  function tryWrap() {
    if (pending.ss && typeof window.fetchLiveSoilSnow === 'function' && !window.fetchLiveSoilSnow.__htfix) {
      var origSS = window.fetchLiveSoilSnow;
      var wrapSS = async function () {
        try { return await race(origSS(), 45000, 'soil/snow fetch'); }
        catch (e) {
          try { return { sms: BIGSTATS.med_sms, stmpF: BIGSTATS.med_stmp, swe: 0 }; }
          catch (e2) { return { sms: 20, stmpF: 50, swe: 0 }; }
        }
      };
      wrapSS.__htfix = true;
      window.fetchLiveSoilSnow = wrapSS;
      pending.ss = false;
    }
    if (pending.gap && typeof window.htGapAssemble === 'function' && !window.htGapAssemble.__htfix) {
      var origGap = window.htGapAssemble;
      var wrapGap = function () { return race(origGap(), 100000, 'live window assembly'); };
      wrapGap.__htfix = true;
      window.htGapAssemble = wrapGap;
      pending.gap = false;
    }
    if (pending.bk && typeof window.htBakedAssemble === 'function' && !window.htBakedAssemble.__htfix) {
      var origBk = window.htBakedAssemble;
      var wrapBk = function () { return race(origBk(), 170000, 'full live assembly'); };
      wrapBk.__htfix = true;
      window.htBakedAssemble = wrapBk;
      pending.bk = false;
    }
    if (pending.ll && typeof window.loadLive === 'function' && !window.loadLive.__htfix) {
      var origLL = window.loadLive;
      var wrapLL = function (silent) {
        var p = origLL(silent);
        race(p, 60000, 'live feeds').catch(function () {
          if (!silent) note('live: USGS/Open-Meteo feeds are slow — panel still shows baked data; the live overlay lands if the feeds answer');
        });
        return p;
      };
      wrapLL.__htfix = true;
      window.loadLive = wrapLL;
      pending.ll = false;
    }
    if (pending.bm && typeof window.bigModelLive === 'function' && !window.bigModelLive.__htfix) {
      var origBM = window.bigModelLive;
      var wrapBM = function () {
        var p = origBM();
        race(p, 300000, 'big model live').catch(function () {
          try { if (typeof BIG !== 'undefined') BIG.busy = false; } catch (e) {}
          try { if (typeof drawFlow === 'function') drawFlow(); } catch (e) {}
          note('big model: live run is taking unusually long — the panel still shows the baked forecast; results land here if the run completes');
        });
        return p;
      };
      wrapBM.__htfix = true;
      window.bigModelLive = wrapBM;
      pending.bm = false;
    }
    if (pending.ort && typeof ort !== 'undefined' && ort.InferenceSession && !ort.InferenceSession.create.__htfix) {
      var origCreate = ort.InferenceSession.create.bind(ort.InferenceSession);
      var wrapCreate = function (url) { return race(origCreate(url), 90000, 'model load'); };
      wrapCreate.__htfix = true;
      ort.InferenceSession.create = wrapCreate;
      pending.ort = false;
    }
    return !(pending.ss || pending.gap || pending.bk || pending.ll || pending.bm || pending.ort);
  }
  // Poll once a second for up to 30 minutes: on a slow connection the
  // module can take minutes to land, and the wrappers must still be
  // in place before the user's first Live click.
  var wrapTries = 0;
  var wrapTimer = setInterval(function () {
    wrapTries++;
    if (tryWrap() || wrapTries > 1800) clearInterval(wrapTimer);
  }, 1000);
  tryWrap();
  // elapsed-time annotation on the outlook status lines while a live
  // run reports 'live: fetching…' — a slow run must not look frozen.
  var liveSince = {};
  setInterval(function () {
    ['htwk-status', 'htmo-status'].forEach(function (id) {
      var el = document.getElementById(id);
      if (!el) return;
      var t = el.textContent || '';
      if (t.indexOf('live: fetching') === 0) {
        if (!liveSince[id]) liveSince[id] = Date.now();
        var s = Math.round((Date.now() - liveSince[id]) / 1000);
        var base = t.replace(/ \(\d+s\)$/, '');
        el.textContent = base + ' (' + s + 's)';
      } else {
        delete liveSince[id];
      }
    });
  }, 1000);
})();
</script>
"""


# ---------------- part 3: ht-loadmodel v1 (Load new model button) --------
import json as _json
import re as _re

LM_MARKER = "ht-loadmodel v1"
LM_STATS_RE = _re.compile(
    r"var HTLA_STATS = \{\s*mu: \[([0-9.,\-+eE ]+)\], sd: \[([0-9.,\-+eE ]+)\], "
    r"tsd: \[([0-9.,\-+eE ]+)\], med_sms: ([0-9.]+), med_stmp: ([0-9.]+) \};")
LM_BTN_RE = _re.compile(
    r'<button id="loadModelTop"(?:(?!</button>).)*</button>'
    r'(<span id="loadModelStatus"(?:(?!</span>).)*</span>)?', _re.S)
LM_JS_RE = _re.compile(
    r'<script>\n/\* ht-loadmodel v1(?:(?!</?script).)*</script>\n?', _re.S)
RETRAIN_BTN_RE = _re.compile(r'<button id="retrainTop"[^>]*>[^<]*</button>')

LM_BUTTON_HTML = (
    '<button id="loadModelTop" title="Fetch the latest published model '
    'weights from hydrotwin-models and re-run the forecast with them" '
    'style="padding:6px 14px;border-radius:10px;border:1px solid #FFD24D;'
    'background:rgba(12,18,28,.88);color:#FFD24D;font:600 14px Arial;'
    'cursor:pointer;box-shadow:0 2px 10px rgba(0,0,0,.4);">Load new model'
    '</button><span id="loadModelStatus" style="align-self:center;'
    'font:600 12.5px Arial;color:#BFD0E0;max-width:360px;"></span>')

LM_JS_BODY = r"""
<script>
/* ht-loadmodel v1 - "Load new model": hot-load the latest published
 * weights from the hydrotwin-models Pages source into the open page.
 * The daily engine (ht-liveall) caches its ORT sessions privately and
 * the big-model engine caches BIG.sess, so this block wraps
 * ort.InferenceSession.create and hands those engines a proxy session
 * for this station's artifacts; the proxy's inner real session is
 * swapped atomically when the button loads fresh weights. A failed
 * load changes nothing. See build25/patch_livefix.py (Part 3). */
(function () {
  'use strict';
  if (window.__htlmOn) return;
  window.__htlmOn = true;
  var ONNX_BASE = 'https://saurabhkulkarni77.github.io/hydrotwin-models/onnx';
  var MODELS_BASE = 'https://saurabhkulkarni77.github.io/hydrotwin-models/';
  var NEURAL = ['LSTM', 'Transformer', 'TFT', 'PatchTST', 'PILSTMv1'];
  var STATS = __HTLM_STATS_JSON__;
  var D = window.HT_DATA || window.HT3D || {};
  var SITE = ((D.station && D.station.stationId) || '').replace('USGS-', '') || D.site || '';
  var epoch = 0;

  /* After a successful load, models-source fetches (the classical
   * params JSONs are fetched per live run) bypass the HTTP cache. */
  if (window.fetch) {
    var ofetch = window.fetch.bind(window);
    window.fetch = function (input, init) {
      try {
        if (epoch) {
          var u = (typeof input === 'string') ? input : (input && input.url) || '';
          if (u.indexOf(MODELS_BASE) === 0 && u.indexOf('htlm=') < 0) {
            var nu = u + (u.indexOf('?') >= 0 ? '&' : '?') + 'htlm=' + epoch;
            input = (typeof input === 'string') ? nu : new Request(nu, input);
          }
        }
      } catch (e) { /* passthrough */ }
      return ofetch(input, init);
    };
  }

  /* ---------------- session registry + proxy ---------------- */
  var reg = {};
  function modelOfUrl(u) {
    if (typeof u !== 'string' || !SITE) return null;
    var m = u.match(/\/onnx\/(\d{8})\/([A-Za-z0-9_]+)\.onnx(?:[?#].*)?$/);
    if (!m || m[1] !== SITE) return null;
    return m[2];
  }
  function curReal(model) {
    var slot = reg[model];
    if (!slot || !slot.real) throw new Error('ht-loadmodel: no live session for ' + model);
    return slot.real;
  }
  function makeProxy(model) {
    return {
      get inputNames() { return curReal(model).inputNames; },
      get outputNames() { return curReal(model).outputNames; },
      run: function (feeds, opts) { return curReal(model).run(feeds, opts); },
      release: function () { return Promise.resolve(); }
    };
  }
  var rawCreate = null, wrapInstalled = false;
  function tryInstall() {
    if (wrapInstalled) return true;
    if (typeof ort === 'undefined' || !ort.InferenceSession ||
        typeof ort.InferenceSession.create !== 'function') return false;
    if (ort.InferenceSession.create.__htlm) { wrapInstalled = true; return true; }
    var orig = ort.InferenceSession.create.bind(ort.InferenceSession);
    rawCreate = orig;
    var wrapped = function (arg, opts) {
      var model = modelOfUrl(arg);
      if (!model) return orig(arg, opts);
      var slot = reg[model];
      if (!slot) {
        slot = reg[model] = { real: null, proxy: makeProxy(model), pending: null };
        slot.pending = orig(arg, opts).then(function (s) {
          slot.real = s; slot.pending = null; return slot.proxy;
        }, function (e) { delete reg[model]; throw e; });
        return slot.pending;
      }
      if (slot.real) return Promise.resolve(slot.proxy);
      if (!slot.pending) {
        slot.pending = orig(arg, opts).then(function (s) {
          slot.real = s; slot.pending = null; return slot.proxy;
        }, function (e) { slot.pending = null; throw e; });
      }
      return slot.pending.then(function () { return slot.proxy; });
    };
    wrapped.__htlm = true;
    ort.InferenceSession.create = wrapped;
    wrapInstalled = true;
    return true;
  }
  var pollTries = 0;
  var poll = setInterval(function () {
    if (tryInstall() || ++pollTries > 240) clearInterval(poll);
  }, 500);
  tryInstall();

  function ensureOrt() {
    return new Promise(function (res, rej) {
      if (typeof ort !== 'undefined') return res();
      var s = document.createElement('script');
      s.src = 'https://cdn.jsdelivr.net/npm/onnxruntime-web@1.30.0/dist/ort.min.js';
      s.onload = function () { res(); };
      s.onerror = function () { rej(new Error('onnxruntime failed to load (CDN blocked?)')); };
      document.head.appendChild(s);
    });
  }

  /* ------------- selected-date recompute (mirrors htla dailyFc) ------------- */
  function buildWindow(day) {
    var flows = {}, wx = {}, win30 = [], i, dt;
    var t0 = Date.parse((D.start || '2001-10-01') + 'T00:00:00Z');
    for (i = day - 29; i <= day; i++) {
      if (i < 0 || i >= D.n) return null;
      dt = new Date(t0 + i * 864e5).toISOString().slice(0, 10);
      var q = D.flow[i], tx = D.tmax[i], tn = D.tmin[i];
      if (q == null || !(q > 0) || tx == null || tn == null) return null;
      flows[dt] = q; wx[dt] = [tx, tn, D.precip[i] || 0]; win30.push(dt);
    }
    return { flows: flows, wx: wx, win30: win30 };
  }
  async function runFan(sess, A, ss) {
    var mu = STATS.mu, sd = STATS.sd, tsd = STATS.tsd;
    var flows = A.flows, wx = A.wx, win30 = A.win30, i, j;
    var flat = new Float32Array(29 * 9);
    var prev = flows[win30[0]];
    for (i = 1; i < 30; i++) {
      var dt = win30[i], t = wx[dt], q = flows[dt];
      var row = [t[0], t[1], (t[0] + t[1]) / 2, t[2], q, q > prev ? 1 : 0, ss.sms, ss.stmpF, ss.swe];
      prev = q;
      for (j = 0; j < 9; j++) {
        var x = j === 4 ? Math.log(row[j]) : row[j];
        flat[(i - 1) * 9 + j] = (x - mu[j]) / sd[j];
      }
    }
    var last = Math.log(flows[win30[29]]);
    var feeds = {};
    feeds[sess.inputNames[0]] = new ort.Tensor('float32', flat, [1, 29, 9]);
    var out = await sess.run(feeds);
    var diffs = Array.from(out[sess.outputNames[0]].data);
    if (diffs.length !== 7 || diffs.some(function (v) { return !isFinite(v); })) {
      throw new Error('bad model output');
    }
    return diffs.map(function (d, l) { return Math.exp(last + d * tsd[l]); });
  }
  function stepKey(k) {
    window.dispatchEvent(new KeyboardEvent('keydown', { key: k, bubbles: true, cancelable: true }));
  }
  async function rerunSelectedDate(models) {
    var S = window.__htS;
    if (!S || !D.pred || !D.models || !D.flow) return '';
    var day = S.day;
    if (day == null || day < 29 || day >= D.n) {
      return ' · this date has under 30 days of history - baked forecast kept';
    }
    var A = buildWindow(day);
    if (!A) return ' · window has data gaps - baked forecast kept';
    var ss = { sms: STATS.med_sms, stmpF: STATS.med_stmp, swe: 0 };
    var done = 0;
    for (var k = 0; k < models.length; k++) {
      var m = models[k], mi = D.models.indexOf(m), slot = reg[m];
      if (mi < 0 || !slot || !slot.real) continue;
      try {
        var fan = await runFan(slot.real, A, ss);
        for (var l = 0; l < 7; l++) D.pred[mi][l][day] = fan[l];
        done++;
      } catch (e) { /* keep the baked fan for this model */ }
    }
    if (!done) return ' · recompute failed - baked forecast kept';
    if (day > 0) { S.day = day - 1; stepKey('ArrowRight'); }
    else { S.day = 0; stepKey('ArrowRight'); stepKey('ArrowLeft'); }
    return ' · forecast for ' + A.win30[29] + ' recomputed (' + done + ' models)';
  }

  function exitOldWeights() {
    var box = document.getElementById('htla-old');
    if (box && box.checked) {
      box.checked = false;
      box.dispatchEvent(new Event('change', { bubbles: true }));
    }
  }

  /* ---------------- the button ---------------- */
  var btn = document.getElementById('loadModelTop');
  var statusEl = document.getElementById('loadModelStatus');
  function setStatus(t, ok) {
    if (!statusEl) return;
    statusEl.textContent = t;
    statusEl.style.color = ok ? '#7AE07A' : '#FF8A7A';
  }
  var busy = false;
  async function loadNewModel() {
    if (busy) return;
    busy = true;
    var label = btn ? btn.textContent : '';
    if (btn) { btn.disabled = true; btn.textContent = 'Loading model...'; }
    setStatus('', true);
    try {
      if (!SITE) throw new Error('station id unavailable on this page');
      await ensureOrt();
      if (!tryInstall() || !rawCreate) throw new Error('model runtime unavailable');
      var models = NEURAL.filter(function (m) { return (D.models || []).indexOf(m) >= 0; });
      if (!models.length) throw new Error('no neural models on this page');
      var pend = models.map(function (m) { return reg[m] && reg[m].pending; })
        .filter(function (p) { return !!p; });
      if (pend.length) { try { await Promise.all(pend); } catch (e) { /* superseded below */ } }
      var ts = Date.now(), built = {}, lastMod = null, k, m2;
      for (k = 0; k < models.length; k++) {
        m2 = models[k];
        var url = ONNX_BASE + '/' + SITE + '/' + m2 + '.onnx?htlm=' + ts;
        var r = await fetch(url, { cache: 'no-store' });
        if (!r.ok) throw new Error(m2 + ': HTTP ' + r.status + ' from the models source');
        var lm = r.headers.get('last-modified');
        if (lm) lastMod = lm;
        var buf = await r.arrayBuffer();
        if (!buf.byteLength) throw new Error(m2 + ': empty model artifact');
        built[m2] = await rawCreate(new Uint8Array(buf));
      }
      /* every new session built -> swap atomically */
      for (k = 0; k < models.length; k++) {
        m2 = models[k];
        if (!reg[m2]) reg[m2] = { real: null, proxy: makeProxy(m2), pending: null };
        var old = reg[m2].real;
        reg[m2].real = built[m2];
        reg[m2].pending = null;
        if (old && old !== built[m2] && old.release) {
          try { await old.release(); } catch (e) { /* best effort */ }
        }
      }
      epoch = ts;
      exitOldWeights();
      var note = '';
      try { note = await rerunSelectedDate(models); } catch (e) { note = ''; }
      var stamp = '';
      if (lastMod) {
        var d = new Date(lastMod);
        if (!isNaN(d)) stamp = ' · weights published ' + d.toUTCString().slice(0, 16);
      }
      setStatus('New model loaded ✓' + stamp + note, true);
      if (window.__htla && window.__htla.on) {
        var g = document.getElementById('htla-go');
        if (g) { g.click(); setStatus('New model loaded ✓' + stamp + note + ' · live re-run started', true); }
      }
    } catch (e) {
      setStatus('Load failed - previous model kept (' + ((e && e.message) || e) + ')', false);
    }
    if (btn) { btn.disabled = false; btn.textContent = label; }
    busy = false;
  }
  if (btn) btn.addEventListener('click', loadNewModel);
})();
</script>
"""


def _lm_extract_stats(s):
    m = LM_STATS_RE.search(s)
    if not m:
        return None
    def arr(g):
        return [float(x) for x in g.split(",")]
    mu, sd, tsd = arr(m.group(1)), arr(m.group(2)), arr(m.group(3))
    if len(mu) != 9 or len(sd) != 9 or len(tsd) != 7:
        return None
    return {"mu": mu, "sd": sd, "tsd": tsd,
            "med_sms": float(m.group(4)), "med_stmp": float(m.group(5))}


def apply_loadmodel(s):
    """Part 3: insert/refresh the Load-new-model button + script.

    Only pages carrying the retrain button (the 14 3D pages) are
    touched; anything else is returned unchanged. Returns the new
    text, or None on anchor trouble."""
    if 'id="retrainTop"' not in s:
        return s
    stats = _lm_extract_stats(s)
    if stats is None:
        return None
    out = LM_BTN_RE.sub("", s)
    out = LM_JS_RE.sub("", out)
    btns = RETRAIN_BTN_RE.findall(out)
    if len(btns) != 1 or out.count('id="retrainTop"') != 1:
        return None
    m = RETRAIN_BTN_RE.search(out)
    out = out[:m.end()] + LM_BUTTON_HTML + out[m.end():]
    if out.count("</body>") != 1:
        return None
    js = LM_JS_BODY.replace("__HTLM_STATS_JSON__", _json.dumps(stats))
    out = out.replace("</body>", js.strip() + "\n</body>", 1)
    if out.count('id="loadModelTop"') != 1:
        return None
    if out.count(LM_MARKER) != 1:
        return None
    return out


def patch_page(s):
    """Returns (new_text, n_part1_applied) or None on anchor trouble."""
    has_v2 = MARKER in s
    has_v1 = OLD_MARKER in s
    olds_left = [old for old, _new in PART1 if old in s]
    if has_v2 and not olds_left:
        out, n1 = s, 0
    else:
        out = s
        n1 = 0
        for old, new in PART1:
            c = out.count(old)
            if c == 1:
                out = out.replace(old, new, 1)
                n1 += 1
            elif c > 1:
                return None
        if not has_v1 and not has_v2:
            if out.count("</body>") != 1:
                return None
            out = out.replace("</body>", JS_BODY.strip() + "\n</body>", 1)
        if OLD_MARKER in out:
            out = out.replace(OLD_MARKER, MARKER)
        if MARKER not in out:
            return None
        if any(old in out for old, _new in PART1):
            return None
    out = apply_loadmodel(out)
    if out is None:
        return None
    return out, n1


def main():
    pages = sorted(Path("stations").glob("*.html"))
    if not pages:
        print("no station pages found (run from repo root)", file=sys.stderr)
        return 1
    n_new = n_skip = n_warn = 0
    for p in pages:
        s = p.read_text(encoding="utf-8")
        res = patch_page(s)
        if res is None:
            n_warn += 1
            print(f"WARNING: anchors not as expected, skipped: {p.name}")
            continue
        out, n1 = res
        if out == s:
            n_skip += 1
            print(f"already patched: {p.name}")
            continue
        p.write_text(out, encoding="utf-8")
        n_new += 1
        print(f"patched: {p.name} (part1 replacements: {n1})")
    print(f"patch_livefix: {n_new} page(s) newly patched, {n_skip} already, "
          f"{n_warn} skipped-with-warning, {len(pages)} pages scanned")
    return 0


if __name__ == "__main__":
    sys.exit(main())
