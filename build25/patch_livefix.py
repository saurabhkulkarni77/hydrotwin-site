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

This patcher APPENDS one guarded script (no edits to existing code).
At page load it wraps the window-visible live entry points with
Promise.race timeouts so every live stage is bounded and failures
surface as honest status text instead of a silent hang:

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

Idempotent: pages carrying the MARKER are skipped.
Run from the repo root: python3 build25/patch_livefix.py
"""
import sys
from pathlib import Path

MARKER = "ht-livefix v1"

JS_BODY = r"""
<script>
/* ht-livefix v1 - bound every live stage with a timeout (dev).
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


def patch_page(s):
    if MARKER in s:
        return s
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
    print(f"patch_livefix: {n_new} page(s) newly patched, {n_skip} already, "
          f"{n_warn} skipped-with-warning, {len(pages)} pages scanned")
    return 0


if __name__ == "__main__":
    sys.exit(main())
