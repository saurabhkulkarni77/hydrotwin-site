#!/usr/bin/env python3
"""Mobile geometry for the floating satellite panels
(ht-mobilepanels v1).

User report (2026-11-10, phone screenshot, Rio Grande 08313000):
the "Monthly outlook" PANELS button lights up green when tapped,
but no panel ever appears. Reproduced headlessly at a 390x844
phone viewport: the monthly panel DOES open - display:block,
populated with real data - at rect x=466, entirely right of the
390 px screen; the yearly panel opens at x=918. Both are
position:fixed with desktop side-by-side slot offsets
(#htwk-panel left:14px, #htmo-panel left:466px, #htyr-panel
left:918px, all width:440px/max-width:94vw), so on any viewport
narrower than the slot offset the panel is 100% off-screen and
the tap looks like a no-op. Weekly (left:14px) is the only
outlook that survives a phone. The feature-importance panel
(#htfi-panel, width:min(430px,94vw) anchored right:12px) also
measures wider than a phone viewport once its rows lay out, so
its box can spill past the right edge.

Fix, deliberately narrow: one <style> block whose rules live
entirely inside @media (max-width: 760px). On phone-width
viewports the four satellite panels become bottom sheets -
left/right 8px, width auto, capped at the viewport height with
their own vertical scroll, stacked above the centred Live bar
(#htla-bar, z-index 9999) so the panel the user just tapped is
fully readable. Desktop geometry, dragging, the maximize state
and every panel's content are untouched (the media query simply
stops applying; on phones the head-drag affordance is inert
because the !important sheet anchor wins over the inline drag
position - the collapse button and the PANELS toggle still
close the panel, which is what the phone UI offers anyway).

Panels verified as already fine on a phone and deliberately NOT
re-anchored: #ht-drift-panel (right:18px, width:308px - fully
visible, measured) and #ht-dacp-panel (centred, max-width:94vw,
wraps - fully visible, measured).

Runs late in the dev chain (after patch_tileslift.py); the
panels it styles are added by patch_weekly / patch_monthly /
patch_yearly / patch_featimp, all earlier steps. Idempotent:
pages already carrying the marker are skipped.
"""
import sys
from pathlib import Path

MARKER = "ht-mobilepanels v1"
MARKER_COUNT = 1
ANCHOR = "</head>"

BLOCK = """<style>/* ht-mobilepanels v1 - phone geometry for the floating
   satellite panels (see build25/patch_mobilepanels.py). Desktop
   slots are fixed left offsets (weekly 14px, monthly 466px,
   yearly 918px) that fall entirely off-screen on phones; inside
   this media query only, the panels become bottom sheets. */
@media (max-width: 760px) {
  #htwk-panel, #htmo-panel, #htyr-panel {
    left: 8px !important; right: 8px !important;
    width: auto !important; max-width: none !important;
    bottom: 8px !important;
    max-height: calc(100dvh - 16px) !important;
    overflow-y: auto !important;
    z-index: 10002 !important;
  }
  #htfi-panel {
    left: 8px !important; right: 8px !important;
    width: auto !important; max-width: none !important;
    z-index: 10001 !important;
  }
}
</style>
</head>"""


def patch_3d(path: Path) -> str:
    s = path.read_text(encoding="utf-8")
    if MARKER in s:
        return "skip (current)"
    # The style rules only make sense once the panels exist.
    for need in ("#htmo-panel", "#htyr-panel", "#htwk-panel"):
        if need not in s:
            return f"FAIL prerequisite {need} missing (runs after the outlook patchers)"
    if s.count(ANCHOR) != 1:
        return f"FAIL anchor count {s.count(ANCHOR)} (want 1): </head>"
    s = s.replace(ANCHOR, BLOCK, 1)
    if s.count(MARKER) != MARKER_COUNT:
        return f"FAIL post-check marker count {s.count(MARKER)} (want {MARKER_COUNT})"
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
