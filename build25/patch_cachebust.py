#!/usr/bin/env python3
"""Cache-busting build stamp for the DEV station pages. (ht-cachebust v1)

Problem: after a deploy, the user's phone keeps serving the OLD page and,
worse, the old runtime data files — the station pages build almost every
URL they load at runtime ('../weekly/' + site + '.json',
'../onnx_w/' + site + '/' + model + '.onnx', template literals), and
none of those URLs ever changes when the underlying file is redeployed.
Result: "Don't see buttons", "github still black", "can't find live AR
demo" — a stale-cache loop that hard-refresh advice never fixed for good.

Fix, in two parts, both applied by this patcher to stations/*.html:

1. A tiny runtime interceptor, injected as the FIRST element of <head>
   (before the importmap, the ORT CDN script and every page script):
   it wraps window.fetch and XMLHttpRequest.open and appends
   ?htv=<build id> (or &htv=) to same-origin requests only. Because it
   intercepts the call, it stamps URLs no matter how the page code
   built them — concatenation, template literals, variables — which
   covers every sidecar JSON fetch (weekly/monthly/dacp/dacpw/dacpm/
   corr/soilsnow/params/chart3d) and the ONNX model loads
   (ort.InferenceSession.create fetches the model through the global
   fetch). Absolute URLs to other hosts (USGS, Open-Meteo, macrostrat,
   NLDI, Esri tiles, jsdelivr CDN) are left untouched, as are data:,
   blob:, about: and mailto: URLs. A URL that already carries htv=
   gets its value REPLACED, never a second parameter.

2. Static stamping of the module loads the fetch wrapper cannot see:
   the importmap entry and import()/from specifiers that point at
   relative .js/.mjs files (classic pages: ../assets/3dchart/
   three.module.js and ../assets/3dchart/embed.mjs). Same replace-
   never-duplicate rule, so re-runs converge.

The build id comes from the HT_BUILD_ID env var, injected by
deploy-dev.yml as "<github.run_id>-<github.sha>", so it changes on
EVERY deploy run. This patcher runs LAST in the deploy chain (after
patch_compare_wm.py, before the bake commit-back), and unlike the
feature patchers it does not skip pages that already carry the marker:
the committed-back pages contain last deploy's block, so on each run
the old marked block is removed and a fresh one with the new id is
inserted — exactly one block per page, always.

Known limitation: embed.mjs's own sibling imports (./OrbitControls.js,
./graph.mjs, ./graph-data.mjs, ./data.mjs) resolve against embed.mjs's
URL and drop its query string, so they cannot be stamped from the
page; they change only with deliberate 3D-chart feature work, and the
files they sit next to (embed.mjs itself, chart3d sidecars) ARE
stamped/fetched fresh every deploy.

Run from the repo root: HT_BUILD_ID=<id> python3 build25/patch_cachebust.py
"""
import os
import re
import sys
from pathlib import Path

MARKER = "ht-cachebust v1"

BLOCK_RE = re.compile(
    r"<!-- ht-cachebust v1 -->.*?<!-- /ht-cachebust v1 -->\n?", re.S)
HEAD_RE = re.compile(r"<head\s*>", re.I)
IMPORTMAP_RE = re.compile(r'(<script type="importmap">)(.*?)(</script>)', re.S)
IMPORTMAP_URL_RE = re.compile(r'"(\.{1,2}/[^"]+)"')
IMPORT_SPEC_RE = re.compile(
    r"""(\bimport\s*\(\s*|\bfrom\s+|\bimport\s+)(['"`])"""
    r"""(\.{1,2}/[^'"`]+?\.(?:mjs|js)(?:\?[^'"`]*)?)\2""")

JS_TEMPLATE = r"""<script>
/* ht-cachebust v1 - per-deploy build stamp (dev). Wraps fetch/XHR so
 * every same-origin runtime request (sidecar JSON, ONNX models) carries
 * ?htv=<build id>; a fresh deploy id makes the browser fetch the new
 * files instead of serving the cached ones. External hosts untouched. */
(function () {
  var BID = "__HT_BID__";
  if (!BID || window.__htcb === BID) return;
  window.__htcb = BID;
  function stamp(u) {
    try {
      if (typeof u !== "string" || !u) return u;
      if (/^(?:data:|blob:|about:|mailto:)/i.test(u)) return u;
      var hash = "";
      var hi = u.indexOf("#");
      if (hi >= 0) { hash = u.slice(hi); u = u.slice(0, hi); }
      if (/^(?:https?:)?\/\//i.test(u)) {
        var a = document.createElement("a");
        a.href = u;
        if (a.host !== location.host) return u + hash;
      }
      if (/[?&]htv=/.test(u)) {
        return u.replace(/([?&])htv=[^&]*/, "$1htv=" + BID) + hash;
      }
      return u + (u.indexOf("?") < 0 ? "?" : "&") + "htv=" + BID + hash;
    } catch (e) { return u; }
  }
  if (window.fetch) {
    var OF = window.fetch;
    window.fetch = function (input, init) {
      try {
        if (typeof input === "string") {
          input = stamp(input);
        } else if (input && typeof input.url === "string") {
          var nu = stamp(input.url);
          if (nu !== input.url) input = new Request(nu, input);
        }
      } catch (e) {}
      return OF.call(this, input, init);
    };
  }
  if (window.XMLHttpRequest) {
    var XO = XMLHttpRequest.prototype.open;
    XMLHttpRequest.prototype.open = function (method, url) {
      try { arguments[1] = stamp(url); } catch (e) {}
      return XO.apply(this, arguments);
    };
  }
})();
</script>"""


def build_id():
    raw = os.environ.get("HT_BUILD_ID", "").strip() or "local"
    bid = re.sub(r"[^A-Za-z0-9._-]", "-", raw)[:80].strip("-")
    return bid or "local"


def stamp_url(u, bid):
    """Append ?htv=<bid> to u, replacing any existing htv= value."""
    frag = ""
    if "#" in u:
        u, frag = u.split("#", 1)
        frag = "#" + frag
    if "?" in u:
        base, qs = u.split("?", 1)
        parts = [p for p in qs.split("&") if p and not p.startswith("htv=")]
        u = base + ("?" + "&".join(parts) if parts else "")
    sep = "&" if "?" in u else "?"
    return u + sep + "htv=" + bid + frag


def stamp_module_refs(s, bid):
    """Statically stamp relative module URLs (importmap + import specs).

    Returns (new_text, n_stamped)."""
    n = 0

    def sub_importmap(m):
        nonlocal n

        def sub_url(um):
            nonlocal n
            n += 1
            return '"' + stamp_url(um.group(1), bid) + '"'

        return m.group(1) + IMPORTMAP_URL_RE.sub(sub_url, m.group(2)) + m.group(3)

    s = IMPORTMAP_RE.sub(sub_importmap, s)

    def sub_spec(m):
        nonlocal n
        n += 1
        return m.group(1) + m.group(2) + stamp_url(m.group(3), bid) + m.group(2)

    s = IMPORT_SPEC_RE.sub(sub_spec, s)
    return s, n


def main():
    bid = build_id()
    block = ("<!-- " + MARKER + " -->\n"
             + JS_TEMPLATE.replace("__HT_BID__", bid)
             + "\n<!-- /" + MARKER + " -->\n")
    pages = sorted(Path("stations").glob("*.html"))
    if not pages:
        print("patch_cachebust: no stations/*.html found (run from repo root)")
        return 1
    n_new = n_ref = n_warn = n_mod = 0
    for p in pages:
        s = p.read_text(encoding="utf-8")
        had_block = MARKER in s
        if had_block:
            s = BLOCK_RE.sub("", s)
        m = HEAD_RE.search(s)
        if not m:
            n_warn += 1
            print(f"WARNING: no <head> found, skipped: {p.name}")
            continue
        s = s[:m.end()] + "\n" + block + s[m.end():]
        s, k = stamp_module_refs(s, bid)
        n_mod += k
        p.write_text(s, encoding="utf-8")
        if had_block:
            n_ref += 1
        else:
            n_new += 1
    print(f"patch_cachebust: {n_new} page(s) newly stamped, {n_ref} refreshed, "
          f"{n_mod} module ref(s) stamped, {n_warn} skipped-with-warning, "
          f"{len(pages)} pages scanned, build id {bid}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
