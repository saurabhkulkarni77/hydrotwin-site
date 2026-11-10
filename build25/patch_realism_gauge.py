#!/usr/bin/env python3
"""ht-staffgauge v1 + ht-floodoverlay v1: physical data in the scene (DEV only).

(a) STAFF GAUGE. The ground view already had a staff (a 12.19 m post
with 1 ft red/white bands at the gauge) and a floating label with the
stage text, but nothing on the staff itself showed where the water
is. This patch seats the staff on the (exaggerated) ground at the
gauge and adds a bright waterline band that rides the staff at the
rendered water surface for the selected date, plus a small
"stage X.X ft" tag at the band (the rating-curve stage for the
selected date's discharge, the same number the floating label
shows). Both update from updateLevel's rebuild, i.e. whenever the
Date control (or model/lead) changes the level. The staff keeps its
true 1 ft bands: HT_EXAG_G moves its base, it does not stretch the
instrument.

(c) FLOOD-EXTENT OVERLAY. A toggleable hazard layer (button, bottom
left; window.__htFlood): a second flood grid over the inner block,
filled at the FORECAST stage for the selected date (the panel's
model + lead via predFor; falls back to the current stage when no
forecast exists), tinted amber and lifted 0.12 m so the forecast
extent reads against terrain and against the current water. It is
the page's own HAND-style fill - water surface minus terrain,
cell by cell - so forecast stage gets a visible consequence.
DEFAULT OFF: at most stations the forecast extent nearly coincides
with the current water and the extra tint only muddies the scene;
it is an on-demand analysis layer, not part of the default view.
Refresh is hooked to updateLevel's state key (day/model/lead/mode),
never per frame.

(b) Rain/snow intensity was verified, not changed: ht-precip v1
already scales particle count with the selected date's Open-Meteo
amount (rain: count = clamp(70..2600, mm * 130); snow: clamp(90..
2600, cm * 170)) and badges the recorded amount on screen.

Anchors are exact strings, count-checked; failures write nothing.
Idempotent. Preservation censuses post-checked.
"""
import sys
from pathlib import Path

MARKER = "ht-staffgauge v1"

BLOCK = """
// ------------------------------------------------------------------ ht-staffgauge v1 + ht-floodoverlay v1
// The staff gauge gains a waterline band + stage tag that track the
// selected date (band rides at the rendered water surface at the
// gauge; tag shows the rating stage). The staff keeps true 1 ft
// bands - the exaggeration moves its base, never stretches it.
// The flood overlay (default OFF) fills the inner block at forecast
// stage so a forecast has a visible consequence.
let htStaffBand_ = null, htStaffTag_ = null, htStaffTagVal_ = '';
function htStaffUpdate_() {
  try {
    if (!htStaffBand_) {
      htStaffBand_ = new THREE.Mesh(new THREE.BoxGeometry(1.15, 0.22, 1.15), new THREE.MeshBasicMaterial({ color: '#FFD94D', toneMapped: false }));
      htStaffBand_.name = 'htStaffBand'; gaugeMark.add(htStaffBand_);
    }
    const gy = (elevGround(0, 0) - REFE) * HT_EXAG_G;
    gaugeMark.position.y = gy;
    let wy = null;
    const F = gWater && gWater.flood;
    if (F) {
      const N = NI, i = Math.round((0 - IX0) / IWM * (N - 1)), j = Math.round((0 - IZ0) / IWM * (N - 1));
      const wse = F.wse[j * N + i];
      if (!isNaN(wse)) wy = (wse - REFE + 0.05) * HT_EXAG_G;
    }
    if (wy === null) wy = gy + Math.max(0, curDH || 0) * HT_EXAG_G + 0.3 * HT_EXAG_G;
    htStaffBand_.position.y = wy - gy;
    const q = shownQ();
    if (q != null) {
      const st = stageFt(q).toFixed(1);
      if (st !== htStaffTagVal_) {
        htStaffTagVal_ = st;
        if (htStaffTag_) { gaugeMark.remove(htStaffTag_); if (htStaffTag_.material.map) htStaffTag_.material.map.dispose(); htStaffTag_.material.dispose(); }
        htStaffTag_ = label('stage ' + st + ' ft', 0.03, '#13233A', 'rgba(255,217,77,0.95)', true);
        gaugeMark.add(htStaffTag_);
      }
      if (htStaffTag_) htStaffTag_.position.set(3.0, htStaffBand_.position.y, 0);
    }
    window.__htStaff = { baseY: +gy.toFixed(2), waterY: +wy.toFixed(2), stage: htStaffTagVal_ };
  } catch (e) { /* the gauge tag is cosmetic; never break the level update */ }
}
let htFloodGrid_ = null, htFloodOn_ = false, htFloodBtn_ = null;
function htFloodEnsure_() {
  if (htFloodGrid_) return htFloodGrid_;
  const mat = new THREE.MeshBasicMaterial({ color: '#FF9E2C', transparent: true, opacity: 0.38, depthWrite: false, polygonOffset: true, polygonOffsetFactor: -4, polygonOffsetUnits: -4 });
  const g = new WaterGrid(NI, (i) => IX0 + i / (NI - 1) * IWM, (j) => IZ0 + j / (NI - 1) * IWM, (e) => (e - REFE + 0.05) * HT_EXAG_G + 0.12, groundRoot, mat, 3.5, 0.6);
  g.mesh.renderOrder = 2; g.mesh.visible = false; g.mesh.name = 'htFloodOverlay';
  htFloodGrid_ = g; return g;
}
function htFloodRefresh_() {
  if (!htFloodOn_) return;
  try {
    const g = htFloodEnsure_();
    if (!gWater.flood) { g.mesh.visible = false; return; }
    g.flood = gWater.flood;
    const p = predFor(S2.model, S2.day - S2.lead, S2.lead);
    const q = p != null ? p : shownQ();
    if (q == null) { g.mesh.visible = false; return; }
    g.setLevel(dHof(q));
    g.mesh.visible = S2.mode === 'ground';
    if (htFloodBtn_) htFloodBtn_.textContent = '\\u{1F30A} Flood extent at ' + (p != null ? 'forecast' : 'current') + ' stage ' + stageFt(q).toFixed(1) + ' ft - tap to hide';
    window.__htFloodState = { stageFt: +stageFt(q).toFixed(2), forecast: p != null, wet: g.wetCount };
  } catch (e) { /* overlay is optional; never break the level update */ }
}
function htFloodToggle_() {
  htFloodOn_ = !htFloodOn_;
  const g = htFloodEnsure_();
  if (!htFloodOn_) { g.mesh.visible = false; if (htFloodBtn_) htFloodBtn_.textContent = '\\u{1F30A} Flood extent (forecast stage)'; }
  else htFloodRefresh_();
}
{
  const b = document.createElement('button');
  b.id = 'ht-flood-btn';
  b.textContent = '\\u{1F30A} Flood extent (forecast stage)';
  b.style.cssText = 'position:fixed;left:14px;top:196px;z-index:29;padding:6px 11px;border-radius:999px;border:1px solid rgba(255,158,44,.55);background:rgba(12,18,28,.88);color:#FFD9A0;font:600 12.5px Arial;cursor:pointer;box-shadow:0 2px 10px rgba(0,0,0,.4)';
  b.addEventListener('click', () => htFloodToggle_());
  document.body.appendChild(b); htFloodBtn_ = b;
}
window.__htFlood = { get on() { return htFloodOn_; }, toggle: () => htFloodToggle_(), refresh: () => htFloodRefresh_() };

"""

HT3_ANCHOR = "window.HT3 = {"

EDITS = [
    ("if (gGaugeLabel) gGaugeLabel.position.y = 30 + Math.max(0, curDH);",
     "if (gGaugeLabel) gGaugeLabel.position.y = 30 + Math.max(0, curDH);\n    htStaffUpdate_();   // ht-staffgauge v1", 1),
    ("W.setLine('obs', null); } }",
     "W.setLine('obs', null); }\n    if (htFloodOn_) htFloodRefresh_();   // ht-floodoverlay v1\n  }", 1),
]

PRESERVE = {
    "ht-bridgegap v1": 1,
    "ht-polygap v1": 1,
    "ht-polywater v1": 2,
    "ht-nobuildings v1": 2,
    "ht-ribbonshade v1": 2,
    "ht-riverwater v1": 5,
    "ht-smooth v2": 13,
    "ht-flowline v1": 2,
}


def patch_3d(path: Path) -> str:
    s = path.read_text(encoding="utf-8")
    if MARKER in s:
        return "skip (current)"
    if s.count(HT3_ANCHOR) != 1:
        return f"FAIL HT3 anchor count {s.count(HT3_ANCHOR)} (want 1)"
    for old, new, want in EDITS:
        got = s.count(old)
        if got != want:
            return f"FAIL anchor count {got} (want {want}): {old[:60]}..."
    s = s.replace(HT3_ANCHOR, BLOCK + HT3_ANCHOR, 1)
    for old, new, want in EDITS:
        s = s.replace(old, new)
    for mk, want in PRESERVE.items():
        got = s.count(mk)
        if got != want:
            return f"FAIL preserve census {mk}: {got} (want {want})"
    if s.count(MARKER) < 2 or s.count("ht-floodoverlay v1") < 2:
        return f"FAIL post-check marker counts staff={s.count(MARKER)} flood={s.count('ht-floodoverlay v1')}"
    path.write_text(s, encoding="utf-8")
    return "patched"


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
