#!/usr/bin/env python3
"""Live outlook resilience for the DEV 3D station pages (ht-outlookfix).

Why this exists (found 2026-11-11, Rio Grande screenshot + all-station
live-pull sweep):

The live window assembly demands a 30-day consecutive run of USGS daily
values ending at the newest date. USGS daily values often have a fresh
hole near today (Potomac 01646500: 2026-11-07 missing, final run = 3
days; Cincinnati 03294500: holes 2026-11-04 + 2026-11-09, run = 1;
Lees Ferry 09380000: last value 2026-11-06, run = 9). One missing day
threw every assembly copy, so the outlook panels fell back to the slow
full-record download and, under any slowness, died on 30 s fetch aborts
("signal is aborted without reason") or on htBakedAssemble's unguarded
weather read ("Cannot read properties of undefined (reading 'time')").
Nothing retried a failed panel and the master LIVE bar stayed on
"pulling live data..." forever, so one transient failure looked like a
permanently broken page, with the panels left on stale baked dead-ends
("no baked monthly forecast ... Pick a date in that range") - and the
monthly lead strip kept printing that dead end even under a LIVE panel.

Parts (string surgery / appends, each independently anchored and
skipped with a warning when its anchor is not exactly as expected):

  S  (v1) htGapAssemble: when the final run is short, end the window at
     the newest date that still completes a 30-day consecutive run. No
     value is fabricated - the window ends a few days early and the
     panel shows that issue date honestly.
  S2 (v2) htBakedAssemble: the same tolerance for the fallback's own
     scan (it has an identical strict copy), so a transient gap failure
     no longer lands on a deterministic throw for hole-y stations.
  G  (v2) htBakedAssemble: guard the archive-weather read (w.daily) so
     a failed chunk fetch reports "weather archive unavailable"
     instead of crashing on '.time'.
  S3 (v2) the daily live fan's private assembly copy in ht-liveall:
     same hole tolerance, so the fan can render for hole-y stations.
  R  (v1) one appended watcher script: auto-retries a panel whose live
     run failed (max 3 per streak, reset on success or a fresh master
     pull); writes an honest completion/failure note into the LIVE bar
     if a pull never completes; swaps the monthly lead strip's baked
     dead-end for a pointer to the LIVE forecast when the panel above
     is live; adds a Live-button hint to the weekly/monthly "no baked
     forecast" issue lines (the yearly panel already explains this).

Nothing else changes: no models, no data, no layout. Idempotent: pages
carrying the v2 marker (with S3 applied) are skipped; v1 pages are
upgraded in place. Run from the repo root:
python3 build25/patch_outlookfix.py  (3D station pages only).
"""
import sys
from pathlib import Path

MARKER = "ht-outlookfix v2"
V1 = "ht-outlookfix v1"

# ------------------------------ Part S ---------------------------------
GAP_FN = "async function htGapAssemble() {"
BAKED_FN = "async function htBakedAssemble() {"
FIND_S = """  let k = dates.length - 1;
  while (k > 0 && dn[k] - dn[k - 1] === 1) k--;
  const run = dates.slice(k);
  if (run.length < 30) throw new Error('no 30-day consecutive run at the end');"""
REPL_S = """  let k = dates.length - 1;
  while (k > 0 && dn[k] - dn[k - 1] === 1) k--;
  let run = dates.slice(k);
  if (run.length < 30) {
    /* ht-outlookfix v1: a fresh hole near today (a day USGS has not
     * published yet, or a provisional gap) must not force the slow
     * full-record fallback: end the window at the newest date that still
     * completes a 30-day consecutive run. No value is fabricated - the
     * window simply ends a few days early, and the issue date shows it. */
    let fixed = null;
    for (let e = dates.length - 1; e >= 29 && !fixed; e--) {
      let c = 1;
      while (e - c >= 0 && dn[e - c + 1] - dn[e - c] === 1) c++;
      if (c >= 30) fixed = dates.slice(e - c + 1, e + 1);
    }
    if (!fixed) throw new Error('no 30-day consecutive run at the end');
    run = fixed;
  }"""

# ------------------------------ Part S2 --------------------------------
BIG_FN = "async function bigModelLive() {"
FIND_S2 = """    let k = dates.length - 1;
    while (k > 0 && dn[k] - dn[k - 1] === 1) k--;
    const run = dates.slice(k);
    if (run.length < 30) throw new Error('no 30-day consecutive run at the end');"""
REPL_S2 = """    let k = dates.length - 1;
    while (k > 0 && dn[k] - dn[k - 1] === 1) k--;
    let run = dates.slice(k);
    if (run.length < 30) {
      /* ht-outlookfix v2: same hole tolerance as htGapAssemble - end
       * the window at the newest date that completes a 30-day run
       * instead of throwing when USGS has a fresh hole near today. */
      let fixed = null;
      for (let e = dates.length - 1; e >= 29 && !fixed; e--) {
        let c = 1;
        while (e - c >= 0 && dn[e - c + 1] - dn[e - c] === 1) c++;
        if (c >= 30) fixed = dates.slice(e - c + 1, e + 1);
      }
      if (!fixed) throw new Error('no 30-day consecutive run at the end');
      run = fixed;
    }"""

# ------------------------------ Part G ---------------------------------
FIND_G = """      const d = w.daily;
      for (let i = 0; i < d.time.length; i++) {"""
REPL_G = """      const d = w && w.daily;
      if (!d || !d.time) throw new Error('live: weather archive unavailable, try again');
      for (let i = 0; i < d.time.length; i++) {"""

# ------------------------------ Part S3 --------------------------------
FIND_S3 = """      var k = dates.length - 1;
      while (k > 0 && dn[k] - dn[k - 1] === 1) k--;
      var run = dates.slice(k);
      if (run.length < 30) throw new Error('no 30-day consecutive run at the end');"""
REPL_S3 = """      var k = dates.length - 1;
      while (k > 0 && dn[k] - dn[k - 1] === 1) k--;
      var run = dates.slice(k);
      if (run.length < 30) {
        /* ht-outlookfix v2: same hole tolerance as htGapAssemble - end
         * the window at the newest date that completes a 30-day run. */
        var fixed3 = null;
        for (var e3 = dates.length - 1; e3 >= 29 && !fixed3; e3--) {
          var c3 = 1;
          while (e3 - c3 >= 0 && dn[e3 - c3 + 1] - dn[e3 - c3] === 1) c3++;
          if (c3 >= 30) fixed3 = dates.slice(e3 - c3 + 1, e3 + 1);
        }
        if (!fixed3) throw new Error('no 30-day consecutive run at the end');
        run = fixed3;
      }"""

# ------------------------------ Part R ---------------------------------
JS_BODY = r"""
<script>
/* ht-outlookfix v1 - live outlook resilience (dev). See
 * build25/patch_outlookfix.py for the full story. Watches the three
 * outlook panels + the master LIVE bar and: auto-retries failed live
 * runs a few times, writes an honest note if a pull never completes,
 * points the monthly lead strip at the LIVE forecast when the panel
 * above is live, and adds a Live-button hint to the weekly/monthly
 * 'no baked forecast' dead ends. Adds no data and changes no layout. */
(function () {
  'use strict';
  var PANELS = [
    { btn: 'htwk-live', status: 'htwk-status', tag: 'wk' },
    { btn: 'htmo-live', status: 'htmo-status', tag: 'mo' },
    { btn: 'htyr-live', status: 'htyr-status', tag: 'yr' }
  ];
  var retries = {}, wasPulling = false, pullStart = 0;
  function txt(id) { var e = document.getElementById(id); return e ? (e.textContent || '') : ''; }
  function issuedDate(st) { var m = /issued (\d{4}-\d{2}-\d{2})/.exec(st); return m ? m[1] : null; }
  setInterval(function () {
    var note = txt('htla-note');
    var pulling = note.indexOf('pulling live data') >= 0;
    if (pulling && !wasPulling) { retries = {}; pullStart = Date.now(); }
    if (!pulling) pullStart = 0;
    wasPulling = pulling;
    var allLive = true, anyFailed = false;
    PANELS.forEach(function (p) {
      var st = txt(p.status);
      if (/live outlook issued/.test(st)) { retries[p.btn] = 0; return; }
      allLive = false;
      if (/failed/.test(st)) {
        anyFailed = true;
        var n = retries[p.btn] || 0;
        if (n < 3) {
          retries[p.btn] = n + 1;
          var b = document.getElementById(p.btn);
          if (b) { try { b.click(); } catch (e) {} }
        }
      }
    });
    if (pulling && pullStart && Date.now() - pullStart > 260000) {
      var noteEl = document.getElementById('htla-note');
      if (noteEl && allLive) {
        var d = PANELS.map(function (p) { return issuedDate(txt(p.status)); });
        if (d[0] && d[1] && d[2]) {
          var latest = d.slice().sort()[2];
          noteEl.textContent = '\u25CF LIVE \u00B7 daily data through ' + latest +
            ' \u00B7 outlooks issued wk ' + d[0] + ' \u00B7 mo ' + d[1] + ' \u00B7 yr ' + d[2];
          pullStart = 0;
        }
      } else if (noteEl && anyFailed && Date.now() - pullStart > 300000) {
        var someLive = PANELS.some(function (p) { return /live outlook issued/.test(txt(p.status)); });
        noteEl.textContent = 'live pull did not complete \u2014 ' +
          (someLive ? 'some outlooks above are live; ' : '') +
          'the failed outlook says why in its panel status line. Tap that panel\u2019s \u25B6 Live button to retry.';
        pullStart = 0;
      }
    }
  }, 5000);
  function attach() {
    var ffRead = document.getElementById('htffmo-read');
    if (ffRead && !ffRead.__htofObs) {
      var fixFF = function () {
        var issue = txt('htmo-issue');
        var t = ffRead.textContent || '';
        if (issue.indexOf('LIVE outlook') >= 0 && t.indexOf('No baked monthly forecast') >= 0) {
          var m = issue.match(/issued (\d{4}-\d{2}-\d{2})/);
          var dates = t.match(/\d{4}-\d{2}-\d{2}/g) || [];
          var range = dates.length >= 3 ? ' (baked archive covers ' + dates[1] + ' \u2026 ' + dates[2] + ')' : '';
          ffRead.textContent = 'The panel above is showing the LIVE monthly forecast issued ' +
            (m ? m[1] : 'today') + ' \u2014 its 6 monthly leads are in the panel\u2019s table and chart. ' +
            'This strip inspects the baked outlook archive' + range + ', so it has no lead view for the live date.';
        }
      };
      ffRead.__htofObs = new MutationObserver(fixFF);
      ffRead.__htofObs.observe(ffRead, { childList: true, characterData: true, subtree: true });
      fixFF();
    }
    ['htwk-issue', 'htmo-issue'].forEach(function (id) {
      var el = document.getElementById(id);
      if (el && !el.__htofObs) {
        var fix = function () {
          var t = el.textContent || '';
          if (t.indexOf('no baked') >= 0 && t.indexOf('LIVE outlook') < 0 && t.indexOf('Live button') < 0) {
            el.textContent = t + ' \u2014 or press the \u25B6 Live button in this panel for a forecast issued today.';
          }
        };
        el.__htofObs = new MutationObserver(fix);
        el.__htofObs.observe(el, { childList: true, characterData: true, subtree: true });
        fix();
      }
    });
    return !!(document.getElementById('htffmo-read') &&
              document.getElementById('htwk-issue') &&
              document.getElementById('htmo-issue'));
  }
  var tries = 0;
  var iv = setInterval(function () {
    tries++;
    if (attach() || tries > 300) clearInterval(iv);
  }, 2000);
  attach();
})();
</script>
"""


def patch_page(s):
    """Apply every part whose anchor is present. Return (text, parts_set)
    or (None, set()) on hard failure (no </body> for a needed Part R)."""
    parts = set()
    # --- Part S: bounded to the htGapAssemble span ---
    gi = s.find(GAP_FN)
    bi = s.find(BAKED_FN, gi + 1) if gi >= 0 else -1
    if gi >= 0 and bi > gi:
        span = s[gi:bi]
        if V1 in span:
            parts.add("S")
        elif span.count(FIND_S) == 1:
            s = s[:gi] + span.replace(FIND_S, REPL_S, 1) + s[bi:]
            parts.add("S")
    # --- Parts S2 + G: bounded to the htBakedAssemble span ---
    bi = s.find(BAKED_FN)
    mi = s.find(BIG_FN, bi + 1) if bi >= 0 else -1
    if bi >= 0 and mi > bi:
        span = s[bi:mi]
        if "ht-outlookfix v2" in span:
            parts.add("S2")
        elif span.count(FIND_S2) == 1:
            span = span.replace(FIND_S2, REPL_S2, 1)
            parts.add("S2")
        if "weather archive unavailable" in span:
            parts.add("G")
        elif span.count(FIND_G) == 1:
            span = span.replace(FIND_G, REPL_G, 1)
            parts.add("G")
        s = s[:bi] + span + s[mi:]
    # --- Part S3: the liveall daily-fan assembly copy (unique text) ---
    if "fixed3" in s:
        parts.add("S3")
    elif s.count(FIND_S3) == 1:
        s = s.replace(FIND_S3, REPL_S3, 1)
        parts.add("S3")
    # --- Part R: append the watcher script once ---
    if V1 in s and "live outlook resilience" in s:
        parts.add("R")
    else:
        idx = s.rfind("</body>")
        if idx == -1:
            return None, set()
        s = s[:idx] + JS_BODY.strip() + "\n" + s[idx:]
        parts.add("R")
    return s, parts


def main():
    pages = sorted(Path("stations").glob("*-3d.html"))
    if not pages:
        print("no 3D station pages found (run from repo root)", file=sys.stderr)
        return 1
    want = {"S", "S2", "G", "S3", "R"}
    n_full = n_skip = n_warn = 0
    for p in pages:
        s = p.read_text(encoding="utf-8")
        if MARKER in s and "fixed3" in s:
            n_skip += 1
            print(f"already patched (v2): {p.name}")
            continue
        out, parts = patch_page(s)
        if out is None:
            n_warn += 1
            print(f"WARNING: could not patch, skipped: {p.name}")
            continue
        missing = want - parts
        if out != s:
            p.write_text(out, encoding="utf-8")
        if missing:
            n_warn += 1
            print(f"WARNING: {p.name} missing parts {sorted(missing)} "
                  f"(applied {sorted(parts)})")
        else:
            n_full += 1
            print(f"patched: {p.name} (parts {sorted(parts)})")
    print(f"patch_outlookfix: {n_full} page(s) fully patched, "
          f"{n_skip} already v2, {n_warn} with warnings, "
          f"{len(pages)} 3D pages scanned")
    return 0


if __name__ == "__main__":
    sys.exit(main())
