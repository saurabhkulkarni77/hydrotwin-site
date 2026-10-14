#!/usr/bin/env python3
"""True-live gap fill for the DEV 3D station pages (dev only).

Problem: bigModelLive() re-downloads 10 years of USGS daily flow + Open-Meteo
archive weather on every click, aligns them, and takes the last consecutive
30-day run as the model window. Any single fetch failure (or a hole in the
USGS daily values, or Sacramento's dead 00060 series) kills the forecast,
and nothing anchors the window visibly at "today".

This patch (string surgery, no regex on code):
  1. Injects htGapAssemble() just before bigModelLive(). It builds the same
     {flows, wx, run, win30} structures from the page's baked daily series
     (window.HT3D, ending at the dataset end) extended to today with small
     live fetches:
       - flow: NWIS daily values, last 45 days, fresh values override baked
         on overlap (parameterCd 00060; Sacramento 11447650 uses 72137,
         the tidally filtered series it reports in the modern era);
       - weather: Open-Meteo forecast API (past_days=10, fills the newest
         days incl. today), then the archive API (last 400 days) overwrites
         wherever it has observed values.
     Alignment + last-consecutive-run + window logic is the original code's,
     verbatim. Soil/snow is untouched (fetchLiveSoilSnow at forecast time).
  2. Moves the ORIGINAL assembly block out of bigModelLive() into a sibling
     htBakedAssemble() (same code, returns the same variables) and replaces
     it in bigModelLive() with: try the gap-fill; accept it only if its
     window end >= the baked end date; otherwise use htBakedAssemble() —
     i.e. exactly the previous behavior as fallback.
  3. Adds the window end date to the forecast display lines ($st + livetxt)
     so freshness is visible: "(..., live data, ends YYYY-MM-DD ...)".

Idempotent: pages carrying the MARKER are skipped.
Run from the repo root: python3 build25/patch_live_gap.py
Only stations/*-3d.html are touched (classic pages have no big-model code).
"""
import sys
from pathlib import Path

MARKER = "ht-live-gap v1"
FN = "async function bigModelLive() {"
BLK_START = "    const today = new Date().toISOString().slice(0, 10);"
BLK_END = "    const win30 = run.slice(-30);"
RET_LINE = "    return { flows: flows, wx: wx, run: run, win30: run.slice(-30) };"
ST_FIND = ", live data${(BIG.src"
ST_REPL = ", live data, ends ${win30[29]}${(BIG.src"
LV_FIND = r"(${fcsrc} \u00b7 live data \u00b7 ${hh})"
LV_REPL = r"(${fcsrc} \u00b7 live data \u00b7 ${hh} \u00b7 ends ${win30[29]})"

GAP_HELPER = """/* ht-live-gap v1 - true-live gap fill (dev). Builds the forecast window
 * from the baked daily series (window.HT3D) extended to today with small
 * live fetches, instead of re-downloading 10 years on every click.
 * Flow: USGS NWIS daily values, last 45 days; fresh values override baked
 * on overlap (revised values win). Sacramento 11447650 reports tidally
 * filtered flow as parameter 72137 in the modern era (its 00060 ended
 * 2015), so it is fetched with 72137.
 * Weather: Open-Meteo forecast API (past_days) fills the newest days
 * including today; the archive API (last 400 days) then overwrites
 * wherever it has observed values. A missing flow day breaks the
 * consecutive run honestly - no value is ever fabricated.
 * Soil/snow still comes from fetchLiveSoilSnow() at forecast time. */
async function htGapAssemble() {
  const H = window.HT3D || {};
  const today = new Date().toISOString().slice(0, 10);
  const dayMs = 864e5;
  const iso = (t) => new Date(t).toISOString().slice(0, 10);
  const J = async (u, ms) => { try { return await fetchJson(u, ms); } catch (e) { return null; } };
  const flows = {}, wx = {};
  const fl = H.flow || [];
  const t0 = Date.parse((H.start || '2001-10-01') + 'T00:00:00Z');
  for (let i = 0; i < fl.length; i++) {
    const q = fl[i];
    if (q != null && q > 0) flows[iso(t0 + i * dayMs)] = q;
  }
  const pcd = (D.site === '11447650') ? '72137' : '00060';
  const fStart = iso(Date.parse(today + 'T00:00:00Z') - 45 * dayMs);
  const wStart = iso(Date.parse(today + 'T00:00:00Z') - 400 * dayMs);
  const [ru, wf, wa] = await Promise.all([
    J(`https://waterservices.usgs.gov/nwis/dv/?format=json&sites=${D.site}&parameterCd=${pcd}&startDT=${fStart}&endDT=${today}`, 30000),
    J(`https://api.open-meteo.com/v1/forecast?latitude=${D.lat}&longitude=${D.lon}&daily=temperature_2m_max,temperature_2m_min,precipitation_sum&temperature_unit=celsius&precipitation_unit=mm&timezone=auto&past_days=10&forecast_days=1`, 30000),
    J(`https://archive-api.open-meteo.com/v1/archive?latitude=${D.lat}&longitude=${D.lon}&start_date=${wStart}&end_date=${today}&daily=temperature_2m_max,temperature_2m_min,precipitation_sum&temperature_unit=celsius&precipitation_unit=mm&timezone=auto`, 30000)
  ]);
  if (ru && ru.value) for (const ts of ru.value.timeSeries) for (const v of ts.values[0].value) {
    const q = parseFloat(v.value);
    if (q > 0) flows[v.dateTime.slice(0, 10)] = q;
  }
  const putWx = (w) => {
    const d = w && w.daily; if (!d || !d.time) return;
    for (let i = 0; i < d.time.length; i++) {
      const tx = d.temperature_2m_max[i], tn = d.temperature_2m_min[i];
      if (tx == null || tn == null) continue;
      wx[d.time[i]] = [tx, tn, d.precipitation_sum[i] || 0];
    }
  };
  putWx(wf); putWx(wa);
  const dates = Object.keys(flows).filter(dt => wx[dt]).sort();
  if (dates.length < 30) throw new Error('only ' + dates.length + ' aligned days');
  const dn = dates.map(dt => Math.round(Date.parse(dt + 'T00:00:00Z') / 864e5));
  let k = dates.length - 1;
  while (k > 0 && dn[k] - dn[k - 1] === 1) k--;
  const run = dates.slice(k);
  if (run.length < 30) throw new Error('no 30-day consecutive run at the end');
  return { flows: flows, wx: wx, run: run, win30: run.slice(-30) };
}

"""

NEW_HEAD = """    // ht-live-gap v1: gap-fill first; fall back to the original assembly
    // (htBakedAssemble) whenever the live window cannot beat the baked end.
    let flows, wx, run, win30;
    {
      let A = null;
      try { A = await htGapAssemble(); } catch (e1) { A = null; }
      const H3 = window.HT3D || {};
      const bN = (H3.flow || []).length;
      const bEnd = (H3.start && bN) ? new Date(Date.parse(H3.start + 'T00:00:00Z') + (bN - 1) * 864e5).toISOString().slice(0, 10) : '';
      if (A && A.win30[29] >= bEnd) { flows = A.flows; wx = A.wx; run = A.run; win30 = A.win30; }
      else { const B = await htBakedAssemble(); flows = B.flows; wx = B.wx; run = B.run; win30 = B.win30; }
    }"""


def patch_page(s):
    """Return patched page text, or None if anchors are not as expected."""
    if MARKER in s:
        return s  # already patched; caller treats as no-op
    if s.count(FN) != 1 or s.count(ST_FIND) != 1 or s.count(LV_FIND) != 1:
        return None
    fn_idx = s.find(FN)
    blk_start = s.find(BLK_START, fn_idx)
    if blk_start == -1:
        return None
    blk_end = s.find(BLK_END, blk_start)
    if blk_end == -1:
        return None
    blk_end += len(BLK_END)
    block = s[blk_start:blk_end]
    if not (1000 <= len(block) <= 3000):
        return None
    if "startDT=2016-10-01" not in block or "archive-api.open-meteo.com" not in block:
        return None
    baked_fn = ("async function htBakedAssemble() {\n"
                + block.replace(BLK_END, RET_LINE)
                + "\n}\n\n")
    out = (s[:fn_idx]
           + GAP_HELPER
           + baked_fn
           + s[fn_idx:blk_start]
           + NEW_HEAD
           + s[blk_end:])
    out = out.replace(ST_FIND, ST_REPL, 1)
    out = out.replace(LV_FIND, LV_REPL, 1)
    if MARKER not in out or "htBakedAssemble" not in out:
        return None
    return out


def main():
    pages = sorted(Path("stations").glob("*-3d.html"))
    if not pages:
        print("no 3D station pages found (run from repo root)", file=sys.stderr)
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
    print(f"patch_live_gap: {n_new} page(s) newly patched, {n_skip} already, "
          f"{n_warn} skipped-with-warning, {len(pages)} 3D pages scanned")
    return 0


if __name__ == "__main__":
    sys.exit(main())
