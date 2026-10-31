#!/usr/bin/env python3
"""ht-nobuild v1: remove the 3D buildings layer (Microsoft Building Footprints
extrusions) from the 3D station pages. The single loadBuildings() call site is
replaced with a loader status note, so no buildings are ever built or rendered;
the (now uncalled) function definition is left in place, matching how the
codebase keeps other dormant helpers. BLD.n stays 0.

Idempotent: pages already carrying the marker are skipped. Fails loudly if the
call-site anchor is not found exactly once, so template drift surfaces in CI.
"""
import glob, os, re, sys

MARKER = 'ht-nobuild v1'
CALL = "loadBuildings().catch(() => setLoad('buildings', 'not available'));"
REPL = "setLoad('buildings', 'removed'); /* ht-nobuild v1: 3D buildings layer removed at the user's request */"


def patch(path):
    with open(path, encoding='utf8') as f:
        html = f.read()
    if MARKER in html:
        return 'skip'
    n = html.count(CALL)
    if n != 1:
        raise SystemExit(f'{path}: call-site anchor found {n} times (expected 1)')
    html = html.replace(CALL, REPL, 1)
    # keep user-visible copy honest: the info panel and the attribution line
    # both mention the buildings layer
    for old_copy, new_copy in [
        ('Real ground, imagery and buildings around the gauge.',
         'Real ground and imagery around the gauge.'),
        (' \u00b7 Buildings: Microsoft Building Footprints (ODbL)', ''),
    ]:
        if html.count(old_copy) != 1:
            raise SystemExit(f'{path}: copy anchor {old_copy[:40]!r} found {html.count(old_copy)} times (expected 1)')
        html = html.replace(old_copy, new_copy, 1)
    with open(path, 'w', encoding='utf8') as f:
        f.write(html)
    return 'patched'


def main():
    root = sys.argv[1] if len(sys.argv) > 1 else 'stations'
    pages = sorted(glob.glob(os.path.join(root, 'USGS-*-3d.html')))
    if not pages:
        raise SystemExit(f'no station pages under {root}')
    for p in pages:
        print(patch(p), os.path.basename(p))


if __name__ == '__main__':
    main()
