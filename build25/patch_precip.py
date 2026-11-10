#!/usr/bin/env python3
"""ht-precip v1: inject the date-driven rain/snow animation module
into every 3D station page.

The module itself lives once in assets/precip/ht-precip.mjs (it
imports 'three' through the page's own import map, adds a THREE.Points
layer to window.HT3's scene, and reads the selected date's weather
from the Open-Meteo archive). This patcher only adds one module
script tag before </body>. Idempotent: pages already carrying the
marker are skipped. Run from the repo root:
python3 build25/patch_precip.py
"""
import sys
from pathlib import Path

MARKER = "ht-precip v1"
TAG = ('\n<!-- ht-precip v1 -->\n'
       '<script type="module" src="../assets/precip/ht-precip.mjs"></script>\n</body>')


def patch(path: Path) -> str:
    s = path.read_text(encoding="utf-8")
    if MARKER in s:
        return "skip (marker)"
    if s.count("</body>") != 1:
        return f"FAIL anchor body: {s.count('</body>')} occurrences"
    s = s.replace("</body>", TAG, 1)
    if s.count(MARKER) != 1:
        return "FAIL post-check marker count"
    path.write_text(s, encoding="utf-8")
    return "patched"


def main():
    files = sorted(p for p in Path("stations").glob("USGS-*.html")
                   if p.name.endswith("-3d.html"))
    if not files:
        print("no 3D station pages found", file=sys.stderr)
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
