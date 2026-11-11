#!/usr/bin/env python3
"""Live outlook resilience for the DEV 3D station pages (ht-outlookfix v1).

Why this exists (found 2026-11-11, Rio Grande screenshot + all-station
live-pull sweep):

1. htGapAssemble() (ht-live-gap v1) demands a 30-day consecutive run of
   USGS daily values ending at the newest date. USGS daily values often
   have a fresh hole near today (Potomac 01646500: 2026-11-07 missing,
   run = 3 days; Cincinnati 03294500: holes 2026-11-04 + 2026-11-09,
   run = 1; Lees Ferry 09380000: last value 2026-11-06, run = 9). One
   missing day throws the assembly, so every outlook panel falls back to
   htBakedAssemble() - a full-record download (25 years of USGS + 400
   days of archive weather in 30 s-budget fetches). Under any slowness
   that chain aborts ("signal is aborted without reason") and ALL THREE
   panels fail at once.
   Part S (string surgery, bounded to htGapAssemble): when the final
   run is short, end the window at the newest date that still completes
   a 30-day consecutive run. No value is fabricated - the window simply
   ends a few days early and the panel shows that issue date honestly.

2. Nothing retried a failed panel and the master LIVE bar stayed on
   "pulling live data..." forever, so one transient abort looked like a
   permanently broken page, with the panels left on stale baked
   dead-ends ("no baked monthly forecast ... Pick a date in that
   range"). Part R (one appended script, same pattern as the other
   late patchers):
   - auto-retries a panel whose live run failed (max 3 per streak,
     reset on success or on a fresh master pull) - a retry reuses the
     browser-cached downloads and usually succeeds;
   - if the master pull still has not completed after ~5 minutes,
     writes an honest completion/failure note into the LIVE bar
     instead of leaving "pulling..." up forever;
   - the monthly lead strip (ht-ffmo v1) keeps printing its baked
     dead-end even while the panel above shows the LIVE forecast:
     a MutationObserver swaps that readout for a pointer to the live
     forecast in the panel above;
   - the weekly/monthly "no baked ... forecast" issue lines gain a
     pointer to the panel's own Live button (the yearly panel already
     explains this in its note; these two did not).

Nothing else changes: no models, no data, no layout. Idempotent: pages
carrying the MARKER are skipped. Part S skips with a warning if its
anchors are not exactly as expected. Run from the repo root:
python3 build25/patch_outlookfix.py  (3D station pages only).
"""
import sys
from pathlib import Path

MARKER = "ht-outlookfix v1"

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
    """Return (new_text, part_s_applied) or (None, False) on hard failure."""
    if MARKER in s:
        return s, False
    part_s = False
    gi = s.find(GAP_FN)
    bi = s.find(BAKED_FN, gi + 1) if gi >= 0 else -1
    if gi >= 0 and bi > gi:
        span = s[gi:bi]
        if span.count(FIND_S) == 1:
            s = s[:gi] + span.replace(FIND_S, REPL_S, 1) + s[bi:]
            part_s = True
    idx = s.rfind("</body>")
    if idx == -1:
        return None, False
    s = s[:idx] + JS_BODY.strip() + "\n" + s[idx:]
    if MARKER not in s:
        return None, False
    return s, part_s


def main():
    pages = sorted(Path("stations").glob("*-3d.html"))
    if not pages:
        print("no 3D station pages found (run from repo root)", file=sys.stderr)
        return 1
    n_new = n_skip = n_warn = n_part_s = 0
    for p in pages:
        s = p.read_text(encoding="utf-8")
        if MARKER in s:
            n_skip += 1
            print(f"already patched: {p.name}")
            continue
        out, part_s = patch_page(s)
        if out is None:
            n_warn += 1
            print(f"WARNING: could not patch, skipped: {p.name}")
            continue
        p.write_text(out, encoding="utf-8")
        n_new += 1
        if part_s:
            n_part_s += 1
        else:
            print(f"WARNING: Part S anchors not as expected (Part R only): {p.name}")
        print(f"patched: {p.name} (Part S: {'yes' if part_s else 'no'})")
    print(f"patch_outlookfix: {n_new} page(s) newly patched "
          f"({n_part_s} with Part S), {n_skip} already, "
          f"{n_warn} skipped-with-warning, {len(pages)} 3D pages scanned")
    return 0


if __name__ == "__main__":
    sys.exit(main())
