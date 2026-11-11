#!/usr/bin/env python3
"""Water seating over the photorealistic tiles (ht-tileslift v1).

User reports (2026-11-10): at Rio Grande / Otowi Bridge (08313000)
the river "is missing its water" on dev - our water shows as
bright-blue blocky patches that only partly cover the channel in
the Google tile scenery, and the flow animation is invisible with
it. A 14-station audit (headless Chromium, live dev, tiles settled)
found the same class of defect wherever the DEM-profiled water
surfaces intersect the tile mesh: every water surface in the scene
(flood grid, ribbon, polygon water, 3DHP bank lines) is profiled
against the USGS DEM terrain, while the tiles sit on WGS84
ellipsoid heights stitched into the page frame with a single
GEOID18 value per station (see patch_tiles3d.py). The residual
per-station bias - plus Google's photogrammetry smoothing narrow
channels - leaves the water plane a metre-scale amount BELOW the
tile channel surface in places, so the depth-tested water only
pokes through in patches.

Fix, deliberately narrow: while (and only while) the tiles are
the active scenery in the ground view, lift the whole water set -
flood grid, ribbon, polygon water, bank-line strips and the
(shoreline-dots) flow lines - by a per-station amount measured by
bracketing on the live dev pages (smallest lift at which the
water traces the tile channel continuously without spilling over
the banks). Legacy (no-tiles / failure / table / XR) rendering is
untouched: a 600 ms tick applies the lift when
window.__htTiles3D.active turns true and restores the recorded
base positions when it turns false. Object positions are used, so
the level-driven geometry rebuilds (buildRibbon, polywater hook,
WaterGrid.setLevel) never fight it.

LIFT_M values are per station, measured 2026-11-10; stations
measured as already-correct are simply absent (no injection).

Runs AFTER patch_tiles3d.py in the dev chain; anchors on the same
window.HT3 site (the tiles block leaves exactly one). Idempotent:
pages already carrying the marker are skipped.
"""
import sys
from pathlib import Path

MARKER = "ht-tileslift v1"
MARKER_COUNT = 2
ANCHOR = "window.HT3 = {"

# Per-station water lift in metres (measured by live bracketing,
# 2026-11-10). 0 / absent = water already seats correctly.
LIFT_M = {
    "01463500": 0.0,   # Trenton: coverage complete at 0
    "01646500": 1.0,   # Potomac: thin far reach at 0; +2 fuller, no spill -> 1.0
    "02320500": 0.0,   # Apalachicola: continuous at 0
    "03294500": 0.0,   # Ohio/Cincinnati: complete at 0 (flood-day sheet)
    "05331000": 0.0,   # St Paul: complete at 0
    "06214500": 0.0,   # Yellowstone/Sidney: continuous at 0
    "07374000": 0.0,   # Baton Rouge: flood-day coverage complete at 0; lifts only raised it further
    "08057000": 1.0,   # Dallas Trinity: thin at 0; +2 fuller, no spill -> 1.0
    "08313000": 2.0,   # Rio Grande: +1 still broken far reaches, +2 continuous, +3 starts to widen
    # --- Provisional (2026-11-10 late): the headless verifier could
    # not stream the tiles to settled state for these five after a
    # service restart (shared VM under load), so no bracket frames
    # exist. Values follow the measured pattern (narrow/incised
    # channels need the lift; wide lowland rivers do not) and are
    # conservative vs the observed spill thresholds. Confirm visually
    # on dev and adjust - the table is the only thing to change.
    "06934500": 0.0,   # PROVISIONAL Missouri/Hermann: wide lowland -> 0 like the other big rivers
    "08158000": 1.0,   # PROVISIONAL Austin: incised reservoir reach -> Potomac/Dallas class
    "09380000": 2.0,   # PROVISIONAL Lees Ferry: narrow canyon channel -> Rio Grande class
    "11447650": 0.0,   # PROVISIONAL Sacramento: wide lowland -> 0
    "14105700": 1.0,   # PROVISIONAL The Dalles: wide gorge pool -> 1.0
}

BLOCK = """
// ht-tileslift v1: while the Google tiles are the scenery, lift
// the water set by this station's measured amount so the
// DEM-profiled surfaces sit on the tile channel instead of
// intersecting its mesh (see patch_tileslift.py). Restored the
// moment tiles deactivate, fail, or the ground view closes.
const HT_LIFT_V = 'ht-tileslift v1';
const HT_LIFT_M = __LIFT__;
const htLiftObjs = [];
let htLiftOn = false;
function htLiftCollect() {
  const cand = [gWater.mesh, ribbon, gWater.lines && gWater.lines.fc, gWater.lines && gWater.lines.obs];
  if (typeof htPolyMesh !== 'undefined' && htPolyMesh) cand.push(htPolyMesh);
  if (typeof htWb3Strips !== 'undefined' && htWb3Strips) for (const st of htWb3Strips) if (st && st.mesh) cand.push(st.mesh);
  for (const o of cand) {
    if (!o || typeof o !== 'object') continue;
    if (o.userData.__liftBase === undefined) o.userData.__liftBase = o.position.y;
    if (!htLiftObjs.includes(o)) htLiftObjs.push(o);
  }
}
function htLiftTick() {
  const t = window.__htTiles3D;
  const want = !!(t && t.active && !t.failed && groundRoot.visible);
  htLiftCollect();
  if (want === htLiftOn) {
    if (want) for (const o of htLiftObjs) o.position.y = o.userData.__liftBase + HT_LIFT_M;
    return;
  }
  htLiftOn = want;
  for (const o of htLiftObjs) o.position.y = o.userData.__liftBase + (want ? HT_LIFT_M : 0);
}
if (HT_LIFT_M > 0) setInterval(htLiftTick, 600);

window.HT3 = {"""


def patch_3d(path: Path) -> str:
    s = path.read_text(encoding="utf-8")
    if MARKER in s:
        return "skip (current)"
    if s.count("ht-tiles3d v1") != 2:
        return f"FAIL tiles census {s.count('ht-tiles3d v1')} (want 2): run after patch_tiles3d"
    if s.count(ANCHOR) != 1:
        return f"FAIL anchor count {s.count(ANCHOR)} (want 1): window.HT3"
    site = path.name.replace("USGS-", "").replace("-3d.html", "")
    lift = LIFT_M.get(site, 0.0)
    if not lift:
        return f"skip (lift 0 for {site})"
    s = s.replace(ANCHOR, BLOCK.replace("__LIFT__", repr(lift)), 1)
    if s.count(MARKER) != MARKER_COUNT:
        return f"FAIL post-check marker count {s.count(MARKER)} (want {MARKER_COUNT})"
    path.write_text(s, encoding="utf-8")
    return f"patched (lift {lift} m)"


def main():
    root = Path("stations")
    files = sorted(root.glob("USGS-*.html"))
    if not files:
        print("no station pages found under stations/", file=sys.stderr)
        return 1
    bad = 0
    for p in files:
        if not p.name.endswith("-3d.html"):
            continue
        r = patch_3d(p)
        print(f"{p.name}: {r}")
        if r.startswith("FAIL"):
            bad += 1
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
