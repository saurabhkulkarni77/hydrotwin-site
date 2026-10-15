#!/usr/bin/env python3
"""Feature-ablation RMSE readout fix for the DEV 3D station pages — ht-ablfix v1.

Bug (reported by Saurabh): in the 3D pages' "Compare models" panel, toggling
the input-feature checkboxes (USGS / Open-Meteo / Soil / Snow) did not visibly
change any RMSE. The baked ABLATION data are correct (verified per-station
against ablation_results25.json); the failure was presentational:
cmpRenderStats() — the panel's only RMSE renderer — draws rows only for the
compare models the user has ticked (it clears #cmpstats when CMP.models is
empty). A user who toggles features first sees only the small subset label
change; no RMSE appears anywhere, and the 4 ablation models' subset RMSEs are
never shown as a set.

Fix (3D pages only; the classic pages' ablation table is a standalone
always-visible table that already updates correctly — verified, untouched):
1. The compare-panel builder gains an always-present <div id="ablstats">
   right under the Features box.
2. A new ablRenderStats() (same module scope, reads ABLATION + activeSubset)
   renders the active subset's per-station RMSE for the 4 ablation models,
   sorted, in the same style as the classic table.
3. ablRenderStats() is called from applyFeatureSubset() (every toggle) and
   when the compare panel is shown (initial render, default subset 9feat).

CMP_RMSE mutation + cmpRenderStats behaviour for ticked models are unchanged.

Idempotent: pages carrying the MARKER are skipped. Any 3D page missing an
anchor aborts the run (exit 1) rather than shipping a partial fix.
Run from the repo root: python3 build25/patch_ablfix.py
"""
import sys
from pathlib import Path

MARKER = "ht-ablfix v1"

# --- anchor 1: ablation readout container in the compare-panel builder ------
A1_OLD = "Toggle to see how each feature set affects RMSE (precomputed ablation)</div></div>';"
A1_NEW = A1_OLD + "\n    html += '<div id=\"ablstats\"></div>';"

# --- anchor 2: re-render the readout on every subset change -----------------
A2_OLD = ("  if (typeof cmpRenderStats === 'function') cmpRenderStats();\n"
          "  if (typeof v1v2Update === 'function') v1v2Update(); }")
A2_NEW = ("  if (typeof cmpRenderStats === 'function') cmpRenderStats();\n"
          "  if (typeof v1v2Update === 'function') v1v2Update();\n"
          "  if (typeof ablRenderStats === 'function') ablRenderStats(); }")

# --- anchor 3: render the readout when the compare panel is shown -----------
A3_OLD = "  if (show && dv) featToggleInit();"
A3_NEW = ("  if (show && dv) { featToggleInit(); "
          "if (typeof ablRenderStats === 'function') ablRenderStats(); }")

# --- anchor 4: the renderer itself, injected into the same module scope -----
A4_OLD = "function featToggleInit() {"
A4_NEW = """// ---------- ht-ablfix v1: always-visible ablation RMSE readout ----------
// The compare panel's Model statistics block only renders ticked models, so
// feature toggles alone changed no visible RMSE. This readout always shows
// the active subset's per-station ablation RMSE (same values as ABLATION).
function ablRenderStats() {
  const dv = document.getElementById('ablstats');
  if (!dv) return;
  const abl = (typeof ABLATION !== 'undefined' && ABLATION[activeSubset]) || {};
  const names = Object.keys(abl).sort(function(a, b) { return abl[a] - abl[b]; });
  if (!names.length) { dv.innerHTML = ''; return; }
  let html = '<div style="margin:10px 0 4px;border-top:1px solid #22303F;padding-top:8px">' +
    '<div style="color:#8FC1F2;font-weight:700;font-size:12px;margin-bottom:4px">Feature ablation RMSE <span style="color:#6B7C8F;font-weight:400;font-size:11px">\\u00B7 this station \\u00B7 precomputed \\u00B7 lower wins</span></div>';
  names.forEach(function(n) {
    html += '<div style="display:flex;justify-content:space-between;padding:2px 0;font-size:12px"><span>' + n + '</span><b>' + abl[n].toFixed(4) + '</b></div>';
  });
  dv.innerHTML = html + '</div>';
}

function featToggleInit() {"""

ANCHORS = [(A1_OLD, A1_NEW), (A2_OLD, A2_NEW), (A3_OLD, A3_NEW), (A4_OLD, A4_NEW)]


def patch(text: str, name: str) -> str:
    if MARKER in text:
        return text
    for old, new in ANCHORS:
        if text.count(old) != 1:
            raise SystemExit(f"patch_ablfix: ABORT {name}: anchor not unique/found "
                             f"({text.count(old)}x): {old[:60]!r}")
        text = text.replace(old, new, 1)
    if MARKER not in text:
        raise SystemExit(f"patch_ablfix: ABORT {name}: marker missing after patch")
    return text


def main() -> int:
    pages = sorted(Path("stations").glob("*-3d.html"))
    if not pages:
        print("patch_ablfix: no 3D station pages found (run from repo root)")
        return 1
    n_new = n_skip = 0
    for p in pages:
        s = p.read_text(encoding="utf-8")
        if MARKER in s:
            n_skip += 1
            print(f"already patched: {p.name}")
            continue
        out = patch(s, p.name)
        if out != s:
            p.write_text(out, encoding="utf-8")
            n_new += 1
            print(f"patched: {p.name}")
    print(f"patch_ablfix: {n_new} page(s) newly patched, {n_skip} already")
    return 0


if __name__ == "__main__":
    sys.exit(main())
