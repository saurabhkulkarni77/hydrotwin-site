#!/usr/bin/env python3
"""Remove climatology from the station-page UI (ht-noclim v1, display only).

User order (2026-10-19): "Remove it lol" — climatology (the train-era
historical-average reference) must no longer be offered as a model/series
anywhere on the 28 station pages. Persistence stays. The scientific record
is untouched: the Climatology values remain in the embedded __wkMeta /
__moMeta / __yrMeta payloads, in models/registry.json and
models/baselines.json, and in the monitor/gate — only the DISPLAY goes.

Surfaces removed (verified by page scan, identical on classic and 3D):
  * the weekly/monthly/yearly panels' pooled-RMSE leaderboard tables
    (boardHTML) list Climatology as a "(reference)" row that is also a
    selectable model entry — the row is filtered out of the render
    (the names list is filtered; the META data itself is not modified);
  * the yearly panel draws climatology as a chart series (orange dashed,
    "- - climatology (reference)" legend), adds a Climatology column to
    its readout table (gated by showClim on rows' r[6]) and appends a
    "· climatology X cfs" segment to its hover readout — all three are
    fed by climSeries(); making climSeries return null starves every
    one of them (empty series -> no legend/line, r[6] null -> no column,
    no note), and the hover segment statement is removed outright.
The Compare panels (ht-cmpwm / ht-cmpy) and ht-ffmo contain no
climatology code (verified: 0 hits) and are not touched.

Anchors are exact source strings of the baked panel scripts; every
replacement is count-checked and the patcher fails loudly (skips the
page) on any mismatch, like the other build25 patchers.
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
STATIONS = ROOT / "stations"
MARKER = "ht-noclim v1"

# (anchor, replacement, expected count per page)
RULES = [
    (
        "var names = Object.keys(L).sort(function (a, b) { return L[a] - L[b]; });",
        "var names = Object.keys(L).sort(function (a, b) { return L[a] - L[b]; })"
        ".filter(function (n) { return n !== 'Climatology'; }); /* ht-noclim */",
        3,  # weekly + monthly + yearly boardHTML
    ),
    (
        "function climSeries(P, day) {",
        "function climSeries(P, day) { return null; /* ht-noclim: "
        "climatology reference display removed (data kept) */",
        1,  # yearly panel only
    ),
    (
        "if (r[6] != null) txt += ' · climatology ' + fmt(r[6]) + ' cfs';",
        "/* ht-noclim: climatology hover segment removed */",
        1,  # yearly hover readout
    ),
]


def main():
    pages = sorted(STATIONS.glob("*.html"))
    done = skipped = failed = 0
    for page in pages:
        html = page.read_text(encoding="utf-8")
        if MARKER in html:
            skipped += 1
            continue
        out = html
        ok = True
        for anchor, repl, want in RULES:
            n = out.count(anchor)
            if n != want:
                print(f"  !! {page.name}: anchor matched {n}x (want {want}): {anchor[:60]}...")
                ok = False
                break
            out = out.replace(anchor, repl)
        if not ok:
            failed += 1
            continue
        block = "\n<script>\n/* " + MARKER + " */\n</script>\n"
        i = out.rfind("</body>")
        if i < 0:
            print(f"  !! {page.name}: no </body>")
            failed += 1
            continue
        page.write_text(out[:i] + block + out[i:], encoding="utf-8")
        done += 1
    print(f"patch_noclim: patched {done}, skipped {skipped} (already marked), failed {failed}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
