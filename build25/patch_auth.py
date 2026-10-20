#!/usr/bin/env python3
"""Login gate for the dev site (ht-auth v1).

Static hosting (S3 / GitHub Pages) has no server side, so the gate is
client-side by construction: a tiny script in the <head> of every
page checks sessionStorage for the sign-in flag (key "ht_auth") and
bounces the browser to login.html before anything renders when the
flag is absent. login.html checks the credentials (username "admin",
password "admin" — the site owner's choice for this dev site), sets
the flag, and redirects to index.html. A second tiny script before
</body> adds an unobtrusive fixed "Log out" control (bottom-right)
that clears the flag and returns to login.html. This keeps casual
visitors out of the dev site; it is not a security boundary — the
pages and data remain publicly fetchable by URL, as on any static
host.

Scope: every page of the site — index.html, mlops.html and all
stations/*.html (classic and -3d). login.html itself is never
patched (it is the gate's destination; gating it would loop).

Placement: the gate goes immediately after <head> so it runs before
every other script (cache-bust wrapper, page code) and before first
paint; the logout boot goes immediately before </body>, where
document.body exists.

Idempotent with refresh: a page already carrying the MARKER has its
existing gate and logout blocks replaced in place by the current
GATE/LOGOUT text; if both are already current the page is skipped
unchanged.
Run from the repo root: python3 build25/patch_auth.py
"""
import re
import sys
from pathlib import Path

MARKER = "ht-auth v1"

GATE = """<script>
// ht-auth v1 gate: client-side login gate for this dev site. Runs
// before anything renders: a browser session that has not signed in
// (sessionStorage key ht_auth) is sent to the login page. Static
// hosting has no server side, so this keeps casual visitors out; it
// is not a security boundary.
try {
  if (sessionStorage.getItem('ht_auth') !== '1') {
    location.replace(
      (location.pathname.indexOf('/stations/') >= 0 ? '../' : '') +
      'login.html');
  }
} catch (e) { /* storage unavailable: let the page load */ }
</script>
"""

LOGOUT = """<script>
// ht-auth v1 logout: small fixed Log out control (bottom-right) on
// signed-in pages; clears the session flag and returns to login.
(function () {
  try {
    if (sessionStorage.getItem('ht_auth') !== '1') return;
    var b = document.createElement('button');
    b.type = 'button';
    b.textContent = 'Log out';
    b.title = 'Sign out of the HydroTwin dev site';
    b.setAttribute('style', 'position:fixed;right:14px;bottom:14px;' +
      'z-index:99999;padding:8px 14px;border-radius:9px;' +
      'border:1px solid #8FC1F2;background:rgba(12,18,28,.92);' +
      'color:#8FC1F2;font:600 13px Arial,sans-serif;cursor:pointer;' +
      'box-shadow:0 2px 10px rgba(0,0,0,.4)');
    b.addEventListener('click', function () {
      try { sessionStorage.removeItem('ht_auth'); } catch (e) {}
      location.replace(
        (location.pathname.indexOf('/stations/') >= 0 ? '../' : '') +
        'login.html');
    });
    document.body.appendChild(b);
  } catch (e) {}
})();
</script>
"""

GATE_RE = re.compile(
    r'<script>\n// ht-auth v1 gate(?:(?!</?script).)*</script>\n?', re.S)
LOGOUT_RE = re.compile(
    r'<script>\n// ht-auth v1 logout(?:(?!</?script).)*</script>\n?', re.S)
HEAD_ANCHOR = "<head>"
BODY_ANCHOR = "</body>"


def post_checks(s: str, is_station: bool) -> str | None:
    if s.count(MARKER) != 2:
        return f"FAIL post-check: marker count {s.count(MARKER)} (want 2)"
    if len(GATE_RE.findall(s)) != 1 or len(LOGOUT_RE.findall(s)) != 1:
        return "FAIL post-check: gate/logout block duplication"
    if s.count(HEAD_ANCHOR) != 1 or s.count(BODY_ANCHOR) != 1:
        return "FAIL post-check: head/body anchor count changed"
    head_end = s.find("</head>")
    body_end = s.find(BODY_ANCHOR)
    gate_at = s.find("// ht-auth v1 gate")
    logout_at = s.find("// ht-auth v1 logout")
    if not (0 <= gate_at < head_end):
        return "FAIL post-check: gate script is not inside <head>"
    if not (head_end < logout_at < body_end):
        return "FAIL post-check: logout script is not at end of <body>"
    if is_station and "window.HT_DATA" not in s:
        return "FAIL post-check: station page lost window.HT_DATA"
    return None


def patch(path: Path) -> str:
    if path.name == "login.html":
        return "skip (login page is never gated)"
    s = path.read_text(encoding="utf-8")
    is_station = path.parent.name == "stations"
    if MARKER in s:
        gates = GATE_RE.findall(s)
        logouts = LOGOUT_RE.findall(s)
        if len(gates) != 1 or len(logouts) != 1:
            return (f"FAIL refresh anchors: {len(gates)} gate(s), "
                    f"{len(logouts)} logout(s)")
        s2 = GATE_RE.sub(lambda _: GATE, s, count=1)
        s2 = LOGOUT_RE.sub(lambda _: LOGOUT, s2, count=1)
        if s2 == s:
            return "skip (marker)"
        bad = post_checks(s2, is_station)
        if bad:
            return bad
        path.write_text(s2, encoding="utf-8")
        return "refreshed"
    if s.count(HEAD_ANCHOR) != 1:
        return f"FAIL anchor head: {s.count(HEAD_ANCHOR)} occurrences"
    if s.count(BODY_ANCHOR) != 1:
        return f"FAIL anchor body: {s.count(BODY_ANCHOR)} occurrences"
    s = s.replace(HEAD_ANCHOR, HEAD_ANCHOR + "\n" + GATE, 1)
    s = s.replace(BODY_ANCHOR, LOGOUT + BODY_ANCHOR, 1)
    bad = post_checks(s, is_station)
    if bad:
        return bad
    path.write_text(s, encoding="utf-8")
    return "patched"


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
        r = patch(p)
        print(f"{p}: {r}")
        if r.startswith("FAIL"):
            bad += 1
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
