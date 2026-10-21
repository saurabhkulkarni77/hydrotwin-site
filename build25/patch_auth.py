#!/usr/bin/env python3
"""Remove the ht-auth v1 login gate from the dev site.

ht-auth v1 (installed 2026-10-20) put a client-side login gate on
every dev page: a script in <head> bounced unsigned sessions to
login.html, and a second script before </body> added a fixed
"Log out" control. The site owner ordered the gate removed on
2026-10-21, and login.html is deleted from the repo.

This patcher is the inverse of the original installer. On every
deploy it strips the gate block and the logout block from
index.html, mlops.html and all stations/*.html (classic and -3d),
and fails the deploy if any ht-auth remnant survives, so a page
baked from an older tree gets cleaned on its next deploy instead
of silently re-shipping the gate. It stays in the deploy pipeline
in the same step slot the installer occupied.

Idempotent: a page carrying no gate blocks is skipped unchanged.
Run from the repo root: python3 build25/patch_auth.py
"""
import re
import sys
from pathlib import Path

MARKER = "ht-auth v1"

GATE_RE = re.compile(
    r'<script>\n// ht-auth v1 gate(?:(?!</?script).)*</script>\n?', re.S)
LOGOUT_RE = re.compile(
    r'<script>\n// ht-auth v1 logout(?:(?!</?script).)*</script>\n?', re.S)
HEAD_ANCHOR = "<head>"
BODY_ANCHOR = "</body>"


def post_checks(before: str, after: str, is_station: bool) -> str | None:
    if MARKER in after or "ht_auth" in after:
        return "FAIL post-check: ht-auth remnant survives stripping"
    if "login.html" in after:
        return "FAIL post-check: login.html reference survives stripping"
    if after.count(HEAD_ANCHOR) != before.count(HEAD_ANCHOR):
        return "FAIL post-check: <head> anchor count changed"
    if after.count(BODY_ANCHOR) != before.count(BODY_ANCHOR):
        return "FAIL post-check: </body> anchor count changed"
    if is_station and "window.HT_DATA" not in after:
        return "FAIL post-check: station page lost window.HT_DATA"
    return None


def strip(path: Path) -> str:
    s = path.read_text(encoding="utf-8")
    is_station = path.parent.name == "stations"
    gates = GATE_RE.findall(s)
    logouts = LOGOUT_RE.findall(s)
    if not gates and not logouts:
        if MARKER in s or "ht_auth" in s:
            return "FAIL remnant: marker present but no removable block"
        return "skip (clean)"
    if len(gates) != 1 or len(logouts) != 1:
        return (f"FAIL strip anchors: {len(gates)} gate(s), "
                f"{len(logouts)} logout(s)")
    s2 = GATE_RE.sub("", s, count=1)
    s2 = LOGOUT_RE.sub("", s2, count=1)
    bad = post_checks(s, s2, is_station)
    if bad:
        return bad
    path.write_text(s2, encoding="utf-8")
    return "stripped"


def main():
    files = []
    for name in ("index.html", "mlops.html"):
        p = Path(name)
        if p.exists():
            files.append(p)
    root = Path("stations")
    files += sorted(root.glob("*.html"))
    if not files:
        print("no pages found (run from the repo root)", file=sys.stderr)
        return 1
    bad = 0
    for p in files:
        r = strip(p)
        print(f"{p}: {r}")
        if r.startswith("FAIL"):
            bad += 1
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
