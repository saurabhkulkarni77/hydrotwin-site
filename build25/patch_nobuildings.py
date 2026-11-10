#!/usr/bin/env python3
"""ht-nobuildings v1: remove the 3D buildings layer ENTIRELY from all 14
3D station pages, at the user's direct order ("Remove buildings all
together from all stations", 2026-11-01).

This supersedes ht-buildingsback v1 (buildings restored with a water
filter) and ht-waterfilter v1 (bake-time removal of the 819 footprints
intersecting the modelled water). The Deploy DEV steps for those two
patchers are removed in the same change; their files stay in the repo
as history. The footprint data itself remains recoverable from git
history (the pre-removal page blobs at dev head 902827b0).

WHAT THIS PATCHER DOES (stdlib only, per page):
1. Empties the baked footprint data: the BAKED_BUILDINGS literal is
   rewritten as {"elements":[]}, so the served page contains zero
   building footprints. A bake note recording how many footprints were
   removed is appended after the literal.
2. Neutralizes the runtime renderer: the single loadBuildings() call
   site is replaced with a loader-status note
   (setLoad('buildings', 'removed')), the same pattern ht-nobuild v1
   used. The (now uncalled) loadBuildings definition and its dormant
   ht-buildingsback / ht-riverwater filter helpers are left in place,
   matching how the codebase keeps other dormant helpers; with an
   empty elements list the function would render nothing even if it
   were called. BLD.n stays 0.
3. Removes any window.__htWaterFilter record (ht-waterfilter v1's
   bake note), if one is present - it described a filter over a layer
   that no longer exists.
4. Keeps user-visible copy honest: the info-panel line no longer
   mentions buildings and the Microsoft Building Footprints
   attribution is removed (the same copy edits ht-nobuild v1 made).

Nothing else is touched: terrain, polygon water + ribbon, bridge gaps,
precip animation, date field, panels and the helper bot are verified
unchanged by marker census before/after.

Idempotent: pages already carrying the marker are skipped. Any anchor
mismatch fails the step without writing, so template drift surfaces
in CI instead of shipping a half-removed layer.
"""
import glob
import json
import os
import re
import sys

MARKER = "ht-nobuildings v1"
MARKER_COUNT = 2  # bake note after the literal + call-site comment
DATA_ANCHOR = "const BAKED_BUILDINGS ="
CALL = "loadBuildings().catch(() => setLoad('buildings', 'not available'));"
REPL = ("setLoad('buildings', 'removed'); /* ht-nobuildings v1: 3D buildings "
        "layer removed entirely at the user's request */")
COPY_OLD = "Real ground, imagery and buildings around the gauge."
COPY_NEW = "Real ground and imagery around the gauge."
ATTR_OLD = " \u00b7 Buildings: Microsoft Building Footprints (ODbL)"
# ht-waterfilter v1's bake note + record, if a page carries them
WF_REC = re.compile(
    r"\n// ht-waterfilter v1: [^\n]*\n"
    r"window\.__htWaterFilter = \{[^}]*\};")
COLLATERAL = ("ht-bridgegap v1", "ht-polywater v1", "ht-realriver v1",
              "ht-helperbot", "ht-precip", "ht-ribbonshade v1")


def _scan(s, j):
    """(start, end) of the JSON value starting at s[j] (string-aware)."""
    depth, k, in_str, esc = 0, j, False, False
    while k < len(s):
        c = s[k]
        if in_str:
            if esc:
                esc = False
            elif c == "\\":
                esc = True
            elif c == '"':
                in_str = False
        elif c == '"':
            in_str = True
        elif c in "[{":
            depth += 1
        elif c in "]}":
            depth -= 1
            if depth == 0:
                return j, k + 1
        k += 1
    raise ValueError("unterminated JSON value")


def find_baked(s):
    i = s.find(DATA_ANCHOR)
    if i == -1:
        return None, None
    j = i + len(DATA_ANCHOR)
    while j < len(s) and s[j].isspace():
        j += 1
    span = _scan(s, j)
    return json.loads(s[span[0]:span[1]]), span


def patch(path):
    with open(path, encoding="utf8") as f:
        s = f.read()
    if MARKER in s:
        return "skip (current)"
    before = {m: s.count(m) for m in COLLATERAL}
    n_htb = s.count("__htBuildings")

    # --- anchors, all strict: fail before writing anything
    B, span = find_baked(s)
    if B is None or "elements" not in B:
        raise SystemExit(f"{path}: BAKED_BUILDINGS literal/elements not found")
    removed = len(B["elements"])
    for name, anchor in (("call site", CALL), ("info copy", COPY_OLD),
                         ("attribution", ATTR_OLD)):
        if s.count(anchor) != 1:
            raise SystemExit(
                f"{path}: {name} anchor found {s.count(anchor)} times (expected 1)")

    # --- 1. empty the baked footprint data + bake note after the ';'
    s = s[:span[0]] + '{"elements":[]}' + s[span[1]:]
    after = span[0] + len('{"elements":[]}')
    if s[after:after + 1] != ";":
        raise SystemExit(f"{path}: BAKED_BUILDINGS literal not followed by ';'")
    note = (f"\n// {MARKER}: all {removed} building footprints removed from "
            f"BAKED_BUILDINGS at bake time by build25/patch_nobuildings.py - "
            f"the 3D buildings layer is removed entirely at the user's "
            f"request; loadBuildings() is never called (see the call site).")
    s = s[:after + 1] + note + s[after + 1:]

    # --- 2. neutralize the runtime renderer (call site)
    s = s.replace(CALL, REPL, 1)

    # --- 3. drop any ht-waterfilter bake record
    s = WF_REC.sub("", s)

    # --- 4. honest copy
    s = s.replace(COPY_OLD, COPY_NEW, 1)
    s = s.replace(ATTR_OLD, "", 1)

    # --- post-checks (still in memory; nothing written yet)
    B2, _ = find_baked(s)
    if B2 is None or len(B2.get("elements", [1])) != 0:
        raise SystemExit(f"{path}: post-check BAKED_BUILDINGS not empty")
    if s.count(MARKER) != MARKER_COUNT:
        raise SystemExit(
            f"{path}: post-check marker count {s.count(MARKER)} (want {MARKER_COUNT})")
    if s.count(CALL) != 0 or s.count("async function loadBuildings()") != 1:
        raise SystemExit(f"{path}: post-check call site / definition census wrong")
    if "__htWaterFilter" in s or "ht-waterfilter v1" in s:
        raise SystemExit(f"{path}: post-check ht-waterfilter remnants present")
    if s.count("__htBuildings") != n_htb:
        raise SystemExit(f"{path}: post-check __htBuildings census changed")
    if COPY_OLD in s or "Buildings: Microsoft Building Footprints" in s:
        raise SystemExit(f"{path}: post-check buildings copy still present")
    for m, n in before.items():
        if s.count(m) != n:
            raise SystemExit(
                f"{path}: post-check collateral marker {m!r} {n} -> {s.count(m)}")

    with open(path, "w", encoding="utf8") as f:
        f.write(s)
    return f"patched (removed {removed} footprints)"


def main():
    root = sys.argv[1] if len(sys.argv) > 1 else "stations"
    pages = sorted(glob.glob(os.path.join(root, "USGS-*-3d.html")))
    if not pages:
        raise SystemExit(f"no station pages under {root}")
    for p in pages:
        print(patch(p), os.path.basename(p))


if __name__ == "__main__":
    main()
