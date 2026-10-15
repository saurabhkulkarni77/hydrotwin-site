#!/usr/bin/env python3
"""Soil & snow columns in the day-inspector panel (DEV only).

Adds the three NRCS dataset columns -- sms_pct (soil moisture), stmp_f
(soil temperature), swe_in (snow water equivalent) -- to the classic
station pages' day-inspector panel, after the existing six columns.
The 3D pages have no column panel, so only classic pages are patched.

Data: daily values ship as per-station sidecars soilsnow/<site>.json
(generated offline from data25/nrcs_daily.csv, aligned to the pages' own
2001-10-01..2026-09-30 axis) and are lazy-fetched by the panel code,
following the dacp/<site>.json pattern. Days with no NRCS record stay
null and render as the panel's existing 'no data'; display values are
never gap-filled or median-filled. If the fetch fails the page behaves
exactly as before (the three rows keep showing 'no data').

This patch (string surgery, no regex on code):
  - appends sms/stmp/swe entries to the COLS registry (they flow into
    the day panel rows, the focus <select>, setFocus cycling and the
    column detail panel automatically);
  - injects the sidecar loader right after the COLS post-processing
    (fills the arrays in place, recomputes training-day mu/sd null-safe,
    then applyDay());
  - swe formats with 2 decimals (the others keep the default 1);
  - enlarges the day-panel canvas (540 -> 740 px tall) so 9 rows fit
    above the slider, and updates the (legacy) ROW() uv boxes to match;
  - drawColumnPanel: 'input channel k/6' -> k/COLS.length (soil & snow
    are channels 7-9 of the 9-feature model input), null-safe 29-day
    window stats, null-safe z-score line.

Idempotent: pages carrying the MARKER are skipped.
Run from the repo root: python3 build25/patch_soilsnow.py
"""
import sys
from pathlib import Path

MARKER = "ht-soilsnow v1"

# ---------------------------------------------------------------- COLS rows
A_OLD = "why: 'A climbing river and a draining one behave differently at the same level' },\n];"
A_NEW = """why: 'A climbing river and a draining one behave differently at the same level' },
  { key: 'sms', col: 'sms_pct', name: 'Soil moisture', src: 'NRCS AWDB · SCAN/SNOTEL · SMS -8 in', unit: '%', color: '#AD7A2A', v: [], why: 'Water stored in the soil — the catchment remembers recent rain and melt' },
  { key: 'stmp', col: 'stmp_f', name: 'Soil temperature', src: 'NRCS AWDB · SCAN/SNOTEL · STO -2 in', unit: '°F', color: '#8E6CC8', v: [], why: 'Warm soil takes meltwater in; frozen soil sheds it as runoff' },
  { key: 'swe', col: 'swe_in', name: 'Snow water equivalent', src: 'NRCS AWDB · SNOTEL WTEQ basin mean', unit: 'in', color: '#7FD1E8', v: [], why: 'Water held in the snowpack — runoff already on its way' },
];"""

# ------------------------------------------------------- fmt: swe 2 decimals
D_OLD = "c.fmt = (x) => c.key === 'rising' ? (x ? 'rising (1)' : 'falling (0)') : c.key === 'flow' ? `${Math.round(x).toLocaleString('en-US')} cfs` : `${(+x).toFixed(1)} ${c.unit}`;"
D_NEW = "c.fmt = (x) => c.key === 'rising' ? (x ? 'rising (1)' : 'falling (0)') : c.key === 'flow' ? `${Math.round(x).toLocaleString('en-US')} cfs` : c.key === 'swe' ? `${(+x).toFixed(2)} ${c.unit}` : `${(+x).toFixed(1)} ${c.unit}`;"

# ------------------------------------------------------------ sidecar loader
LOADER = """
// ---------------------------------------------------------------- soil & snow columns (ht-soilsnow v1)
// Daily sms_pct / stmp_f / swe_in (data25/nrcs_daily.csv) ship as the
// sidecar ../soilsnow/__HTSS_SITE__.json and fill the three columns above
// in place. Days with no NRCS record stay null -> the panel's 'no data';
// display values are never gap-filled or median-filled.
{
  const ssCols = COLS.filter((c) => c.key === 'sms' || c.key === 'stmp' || c.key === 'swe');
  ssCols.forEach((c) => { c.v = new Array(N).fill(null); RAWV[c.key] = c.v; c.mu = null; });
  const ssStats = (c) => {
    const vals = c.v.filter((v) => v != null);
    if (vals.length) { c.min = Math.min(...vals); c.max = Math.max(...vals); }
    const last = Math.min(TRAIN_LAST, N - 1); let s = 0, s2 = 0, n = 0;
    for (let i = 0; i <= last; i++) { const v = c.v[i]; if (v == null) continue; s += v; s2 += v * v; n++; }
    if (n >= WIN) { c.mu = s / n; c.sd = Math.sqrt(Math.max(1e-9, s2 / n - c.mu * c.mu)); }
    c.norm = (x) => (x - c.min) / ((c.max - c.min) || 1);
  };
  fetch('../soilsnow/__HTSS_SITE__.json').then((r) => { if (!r.ok) throw new Error('HTTP ' + r.status); return r.json(); }).then((J) => {
    ssCols.forEach((c) => { const a = J[c.key]; if (Array.isArray(a)) for (let i = 0; i < N && i < a.length; i++) c.v[i] = a[i]; ssStats(c); });
    applyDay();
  }).catch(() => { /* sidecar unavailable: the three rows keep showing 'no data'; the page works as before */ });
}
"""

# ------------------------------------------------------------- panel height
E_OLD = "const dayPanel = canvasPlane(2.0, 1.35, 400);"
E_NEW = "const dayPanel = canvasPlane(2.0, 1.85, 400);   // ht-soilsnow v1: taller, 9 column rows"
F_OLD = "const ROW = (r) => [0.02, (140 + r * 52 - 40) / 540, 0.96, 52 / 540];"
F_NEW = "const ROW = (r) => [0.02, (140 + r * 52 - 40) / 740, 0.96, 52 / 740];"

# ---------------------------------------------------------- column panel bits
G_OLD = "`${C.col} · input channel ${k + 1}/6`"
G_NEW = "`${C.col} · input channel ${k + 1}/${COLS.length}`"
H_OLD = ("  const w0 = Math.max(0, i - WIN + 1), win = C.v.slice(w0, i + 1);\n"
         "  const mean = win.reduce((a, b) => a + b, 0) / win.length;")
H_NEW = ("  const w0 = Math.max(0, i - WIN + 1), winAll = C.v.slice(w0, i + 1), win = winAll.filter((v) => v != null);\n"
         "  const mean = win.length ? win.reduce((a, b) => a + b, 0) / win.length : 0;")
I_OLD = ": `Window (${win.length} d): min ${C.fmt(Math.min(...win))} · max ${C.fmt(Math.max(...win))}`, 40, y); y += 40;"
I_NEW = ": win.length ? `Window (${winAll.length} d${win.length < winAll.length ? ` · ${win.length} with data` : ''}): min ${C.fmt(Math.min(...win))} · max ${C.fmt(Math.max(...win))}` : `Window (${winAll.length} d): no data`, 40, y); y += 40;"
J_OLD = "if (C.mu != null) g.fillText(`Scaled: (x − ${C.mu.toFixed(1)}) / ${C.sd.toFixed(1)}  →  today z = ${((C.v[i] - C.mu) / C.sd).toFixed(2)}`, 40, y);"
J_NEW = "if (C.mu != null) g.fillText(C.v[i] == null ? `Scaled: (x − ${C.mu.toFixed(1)}) / ${C.sd.toFixed(1)}  →  today: no data` : `Scaled: (x − ${C.mu.toFixed(1)}) / ${C.sd.toFixed(1)}  →  today z = ${((C.v[i] - C.mu) / C.sd).toFixed(2)}`, 40, y);"

STEPS = [("cols", A_OLD, A_NEW), ("fmt", D_OLD, D_NEW), ("panel-h", E_OLD, E_NEW),
         ("row-uv", F_OLD, F_NEW), ("channel", G_OLD, G_NEW), ("win", H_OLD, H_NEW),
         ("wintext", I_OLD, I_NEW), ("scaled", J_OLD, J_NEW)]


def patch(path: Path) -> str:
    s = path.read_text(encoding="utf-8")
    if MARKER in s:
        return "skip (marker)"
    site = path.stem.replace("USGS-", "")
    for name, old, new in STEPS:
        n = s.count(old)
        if n != 1:
            return f"FAIL anchor {name}: {n} occurrences"
        s = s.replace(old, new, 1)
    # loader goes right after the (patched) fmt line's closing '});'
    anchor = D_NEW + "\n});"
    if s.count(anchor) != 1:
        return "FAIL anchor loader"
    s = s.replace(anchor, anchor + LOADER.replace("__HTSS_SITE__", site), 1)
    path.write_text(s, encoding="utf-8")
    return "patched"


def main():
    root = Path("stations")
    files = sorted(p for p in root.glob("USGS-*.html") if not p.name.endswith("-3d.html"))
    if not files:
        print("no classic station pages found under stations/", file=sys.stderr)
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
