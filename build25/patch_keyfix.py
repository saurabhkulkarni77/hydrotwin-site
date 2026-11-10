#!/usr/bin/env python3
"""ht-keyfix v1: page keyboard shortcuts must not steal keys from form fields (dev only, idempotent).

Bug (reported 2026-11-01): on the 3D station pages the window-level
keydown handler treats Space as "toggle play" and calls
preventDefault() unconditionally — with no check of the event target.
Typing in the helper bot's text box (or the date field, or any input)
on a 3D page therefore lost every space, and single letters (f/m/k/l/
v/e/g/b) fired page actions mid-typing. The classic pages were fine:
their handler (ht-statsview) already returns early for INPUT/SELECT/
TEXTAREA/BUTTON targets.

Fix: insert the same kind of target guard at the top of both window
keydown handlers on every stations/*-3d.html — typing focus is
exempted, the shortcuts themselves are untouched. Also verifies the
classic pages still carry their exemption and warns if one does not.
Run from the repo root in the deploy-dev workflow.
"""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MARK = "ht-keyfix v1"
GUARD = ("/* " + MARK + ": typing in a form field is exempt from page shortcuts */ "
         "const __t = e.target; if (__t && (__t.tagName === 'INPUT' || __t.tagName === 'TEXTAREA' "
         "|| __t.tagName === 'SELECT' || __t.isContentEditable)) return; ")

ANCHOR_A = "addEventListener('keydown', (e) => { const k = e.key.toLowerCase();"
ANCHOR_B = "addEventListener('keydown', (e) => { if (e.key.toLowerCase() === 'g') act('live');"


def patch_3d(html):
    n = 0
    if ANCHOR_A in html:
        if GUARD + "const k" not in html:
            html = html.replace(ANCHOR_A,
                                "addEventListener('keydown', (e) => { " + GUARD + "const k = e.key.toLowerCase();", 1)
        n += 1
    if ANCHOR_B in html:
        if GUARD + "if (e.key" not in html:
            html = html.replace(ANCHOR_B,
                                "addEventListener('keydown', (e) => { " + GUARD + "if (e.key.toLowerCase() === 'g') act('live');", 1)
        n += 1
    return html, n


def main():
    total_a = total_pages = 0
    for page in sorted((ROOT / "stations").glob("USGS-*-3d.html")):
        html = page.read_text(encoding="utf-8")
        new, n = patch_3d(html)
        total_pages += 1
        total_a += n
        if new != html:
            page.write_text(new, encoding="utf-8")
            print(f"{page.name}: keyfix applied ({n} handler anchors)")
        else:
            print(f"{page.name}: already fixed or no anchor ({n} anchors present)")
        # Loud warning if a space-swallowing handler survives unguarded.
        for m in re.finditer(r"addEventListener\('keydown'[^;]{0,400}?' '\)\s*\{\s*e\.preventDefault", new):
            seg = new[max(0, m.start() - 400):m.start()]
            if MARK not in seg and "tagName" not in seg:
                print(f"WARNING {page.name}: unguarded space preventDefault handler remains")
    for page in sorted((ROOT / "stations").glob("USGS-*.html")):
        if page.name.endswith("-3d.html"):
            continue
        html = page.read_text(encoding="utf-8")
        if "addEventListener('keydown'" in html and "tagName === 'INPUT'" not in html:
            print(f"WARNING {page.name}: classic keydown handler lacks the INPUT exemption")
    print(f"ht-keyfix: {total_pages} 3D pages, {total_a} handler anchors handled")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
