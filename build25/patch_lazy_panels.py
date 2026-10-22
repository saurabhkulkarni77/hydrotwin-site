#!/usr/bin/env python3
"""Panels load on click only (ht-lazypanels v1).

User order (2026-10-21): "convert all the panels to button and dont
load panels when u open any station, ppl can click on any button and
then panel should load".

What this patcher does, per station page:

CLASSIC pages (stations/USGS-<id>.html, the statistics Data view):
  The 11 statistics sections become buttons in one bar placed above
  the first section. Every section starts hidden (class htlp-off).
  The boot script(s) behind each panel are converted in place to
  <script type="text/plain" data-htlp-boot="GROUP">, which the
  browser never executes: no sidecar fetch, no chart drawing, no
  computation happens for a panel until its button is first clicked.
  The loader (one small script before </body>) then runs the panel's
  boots exactly once, in document order, by re-creating them as real
  scripts; later clicks only toggle the section's visibility and
  never refetch. Groups:
    core    - ht-statsview (builds Hydrograph, 7-day forecast,
              Model statistics and relocates the date control, the
              ablation panel, the drift panel and the DACP panel into
              their sections), the feature-ablation script + its
              init, and the ht-dacp boot. These five sections share
              one monolithic core script that cannot be split by a
              text patcher, so the first click on any of their five
              buttons initialises the core once; each section still
              appears only when its own button is clicked.
    weekly / monthly / yearly - the outlook boots (ht-weekly,
              ht-monthly, ht-yearly). The compare boots (ht-cmpwm,
              ht-cmpy) and the monthly Flow & forecast treatment
              (ht-ffmo) are NOT gated: they only poll for the outlook
              panels' control rows and fetch solely when the reader
              opens the compare box / the monthly panel exists, so
              they stay inert while the outlooks are gated.
    chart3d - the ht-3dchart module boot (was scroll-triggered).
    corr    - the ht-corr boot (was scroll-triggered).
    clusters- the ht-clusters boot (was scroll-triggered); section
              content and text are untouched, only WHEN it loads.
  The floating source panels the core relocates (#featcpanel,
  #ht-drift-panel) are held invisible by a wait-core CSS rule until
  the core has run; the loader itself moves the navigation link
  (#to3d) and the date control (#ht-datewrap) into their header /
  Hydrograph slots at startup, so navigation and the date field sit
  in their usual places from the start (the date field is wired by
  the core the moment any core panel is opened, exactly as the
  core's own init does it).

3D pages (stations/USGS-<id>-3d.html):
  The satellite panels are JS-built floating panels; their boots
  (ht-weekly, ht-monthly, ht-yearly, ht-dacp) are gated the same
  way, behind a fixed button bar (Weekly outlook / Monthly outlook /
  Yearly outlook / Confidence interval / Model drift). The drift
  panel is static baked HTML: it starts hidden (a stub CSS rule;
  its tag is a CI census anchor and stays byte-exact) and its
  button only toggles it - no fetch exists for it. Inside the 3D
  scene module, the two eager panel-data loads are gated on the
  module's own buttons via a promise gate installed in <head>:
    - the NLDI rivers/watershed IIFE waits for
      window.__htlpGate('watershed'), released by the first click
      on the module's Watershed button (#bShed);
    - the Macrostrat geologyAt() call for the gauge point waits
      for window.__htlpGate('geo'), released by the first click on
      the Geology button (#bGeo - including the module's own
      programmatic click on a terrain pick).
  The scene itself, its terrain/imagery loads and the module's
  small live beacon (USGS IV + Open-Meteo) are the station view,
  not panels, and keep loading as today.
  The Flow & forecast card (added 2026-10-22, Saurabh's order) is
  the one panel that is NOT a satellite panel: it is the scene
  module's own canvas in #dock, rendered by the module from the
  same baked data object the scene itself consumes (the selected
  date's waterline dots read the same forecast), so it has no boot
  and no sidecar that could be deferred without breaking the
  scene. It is therefore gated by visibility only, exactly like
  the drift panel: a "Daily forecast" button (first in the bar)
  toggles an html.htlp-daily-on class; the stub CSS hides the
  #dock canvas and its ht-uiux wrap until then, and the loader
  also mirrors the canvas's inline display ('block'/'none', the
  same mechanism as the module's own Geology/Watershed toggles)
  so the uiux wrap follows. The module keeps redrawing the canvas
  on date/model changes whether it is visible or not, so opening
  it always shows the current date's forecast.
  The same patcher also moves the "Δ Compare models" button from
  the top button row into that panel's canvas control row (BTN[0],
  beside live / big model): the top-row #cmpTop element is removed
  and an act() route for 'compare' is wired next to the line that
  used to wire the top button, calling the identical cmpShowPanel
  toggle. The canvas row paints fixed-width slots with terse
  labels ('model', 'lead', '⟳ big model'), so the in-panel label
  is 'Δ compare'; the panel it opens is still titled
  "Compare models". Classic pages have no top-row compare button
  (their compare toggles already live inside the weekly / monthly
  / yearly panels), so nothing moves there.

Infrastructure that stays live on both page types (no panel data):
ht-cachebust (fetch wrapper), the baked data blocks, ht-uiux
(polls/MutationObserver; only decorates panels that exist),
ht-livefix (wraps live entry points whenever they appear),
ht-liveall (builds the LIVE bar; fetches only on a Live click),
ht-noclim, the drift collapse toggle.

Idempotent with refresh, like the other build25 patchers: the stub,
bar and loader blocks are replaced in place with the current text,
gates and hidden classes are re-asserted (other patchers refresh
their sections/boots back to live form on every deploy; this
patcher therefore runs LAST in deploy-dev.yml). Every anchor is
count-checked and the patcher fails loudly without writing when a
page does not match. Post-checks re-run the CI marker census
(CLASSIC_MARKERS / THREED_MARKERS from tests/test_site_integrity.py)
on the patched text, so a census break can never ship.
Run from the repo root: python3 build25/patch_lazy_panels.py
"""
import json
import re
import sys
from pathlib import Path

MARKER = "ht-lazypanels v1"

# ---------------------------------------------------------------- census
# Copied from tests/test_site_integrity.py (the contract this patcher
# must keep satisfiable): every count must be identical after patching.
CLASSIC_MARKERS = {
    "ht-statsview v1": 2, "ht-soilsnow v1": 2, "ht-3dchart v1": 2,
    "ht-corr v1": 2, "ht-clusters v1": 2, "ht-dacp v1": 1,
    "ht-weekly v1": 1, "ht-monthly v1": 1, "ht-yearly v1": 1,
    "ht-ffmo v1": 1, "ht-cmpwm v1": 1, "ht-cmpy v1": 1,
    "ht-fullforms v1": 1, "ht-uiux v1": 1, "ht-livefix v2": 1,
    "ht-liveall v2": 1, "ht-noclim v1": 1, "ht-cachebust v1": 3,
    '<div id="ht-drift-panel">': 1, 'id="hts-top"': 1,
    'id="hts-sec-weekly"': 1, 'id="hts-sec-monthly"': 1,
    'id="hts-sec-yearly"': 1, 'id="hts-sec-clusters"': 1,
    'id="htdc-on"': 1, 'id="htwk-live"': 1, 'id="htmo-live"': 1,
    'id="htyr-live"': 1, 'id="htffmo-live"': 1,
}
THREED_MARKERS = {
    "ht-dacp v1": 1, "ht-weekly v1": 2, "ht-monthly v1": 1,
    "ht-yearly v1": 1, "ht-ffmo v1": 1, "ht-cmpwm v1": 1,
    "ht-cmpy v1": 1, "ht-uiux v1": 2, "ht-live-gap v1": 2,
    "ht-ablfix v1": 1, "ht-livefix v2": 1, "ht-liveall v2": 1,
    "ht-noclim v1": 1, "ht-cachebust v1": 3,
    '<div id="ht-drift-panel">': 1, 'id="htdc-on"': 1,
    'id="htwk-canvas"': 1, 'id="htwk-live"': 1, 'id="htmo-live"': 1,
    'id="htyr-live"': 1, 'id="htffmo-live"': 1,
}
CLASSIC_FORBIDDEN = ("ht-live-gap v1", "ht-ablfix v1")
THREED_FORBIDDEN = ("ht-statsview v1", "ht-soilsnow v1", "ht-3dchart v1",
                    "ht-corr v1", "ht-clusters v1", "ht-fullforms v1",
                    'id="hts-top"')

# ------------------------------------------------------------- boot gates
# (signature inside the script body, loader group). Exactly one script
# per signature must exist on the page.
def _ablation_init(body: str) -> bool:
    return ("featClassicInit" in body and "readyState" in body
            and len(body) < 400)


BOOT_GATES_CLASSIC = [
    ("/* ht-statsview v1", "core", None),
    ("feature ablation (classic page)", "core", None),
    (None, "core", _ablation_init),
    ("/* ht-dacp v1 - DACP", "core", None),
    ("/* ht-weekly v1 - Weekly outlook", "weekly", None),
    ("/* ht-monthly v1 - Monthly outlook", "monthly", None),
    ("/* ht-yearly v1 - Yearly outlook", "yearly", None),
    ("// ht-3dchart v1 boot", "chart3d", None),
    ("// ht-corr v1 boot", "corr", None),
    ("// ht-clusters v1 boot", "clusters", None),
]
BOOT_GATES_3D = [
    ("/* ht-dacp v1 - DACP", "dacp", None),
    ("/* ht-weekly v1 - Weekly outlook", "weekly", None),
    ("/* ht-monthly v1 - Monthly outlook", "monthly", None),
    ("/* ht-yearly v1 - Yearly outlook", "yearly", None),
]

CLASSIC_SECTIONS = [  # (section id, loader group) in page order
    ("hts-sec-hydro", "core"),
    ("hts-sec-fc", "core"),
    ("hts-sec-models", "core"),
    ("hts-sec-ablation", "core"),
    ("hts-sec-weekly", "weekly"),
    ("hts-sec-monthly", "monthly"),
    ("hts-sec-yearly", "yearly"),
    ("hts-sec-drift", "core"),
    ("hts-sec-3dchart", "chart3d"),
    ("hts-sec-corr", "corr"),
    ("hts-sec-clusters", "clusters"),
]

# 3D scene-module gate anchors (exact, count-checked).
GATE_RIVERS_OLD = "(async () => {\n  setLoad('rivers', 'loading');"
GATE_RIVERS_NEW = ("(async () => {\n  await window.__htlpGate('watershed');"
                   "\n  setLoad('rivers', 'loading');")
GATE_GEO_OLD = ("geologyAt(D.lon, D.lat).then((u) => { geoUnits.gauge = u; "
                "drawGeo(); }).catch(() => { geoUnits.gauge = 'none'; "
                "drawGeo(); });")
GATE_GEO_NEW = ("window.__htlpGate('geo').then(() => geologyAt(D.lon, "
                "D.lat)).then((u) => { geoUnits.gauge = u; drawGeo(); })"
                ".catch(() => { geoUnits.gauge = 'none'; drawGeo(); });")

# Compare-models move anchors (3D pages, exact, count-checked): the
# top-row button element, and the module line that wired it (the
# wiring snippet is appended right after that line, inside the same
# module scope as BTN / act / cmpShowPanel).
CMP_TOP_BTN = ('<button id="cmpTop" title="Overlay 7-day forecasts of '
               'multiple models" style="padding:6px 14px;'
               'border-radius:10px;border:1px solid #8FC1F2;'
               'background:rgba(12,18,28,.88);color:#8FC1F2;'
               'font:600 14px Arial;cursor:pointer;'
               'box-shadow:0 2px 10px rgba(0,0,0,.4);">'
               'Δ Compare models</button>')
CMP_IIFE = ("(function(){ var ctop = document.getElementById('cmpTop'); "
            "if (ctop) ctop.onclick = function(){ const p = document."
            "getElementById('cmppanel'); cmpShowPanel(!p); }; })();")
CMP_SNIPPET = (
    "\n// ht-lazypanels compare move: the Compare models toggle lives "
    "in the Flow &\n// forecast panel's control row (the top-row "
    "#cmpTop button is removed by\n// this patcher); the canvas "
    "button calls the same cmpShowPanel toggle.\n"
    "BTN[0].push(['Δ compare', 'compare']);\n"
    "const actCmp0 = act;\n"
    "act = function (a) {\n"
    "  if (a === 'compare') { const p = document.getElementById("
    "'cmppanel'); cmpShowPanel(!p); return; }\n"
    "  return actCmp0(a);\n"
    "};")

SCRIPT_RE = re.compile(r"<script([^>]*)>((?:(?!</?script).)*)</script>",
                       re.S)
STUB_RE = re.compile(
    r"\n?<script>\n/\* ht-lazypanels v1 gate stub(?:(?!</?script).)*"
    r"</script>\n?<style>/\* ht-lazypanels v1 \*/(?:(?!</?style).)*</style>",
    re.S)
BLOCK_RE = re.compile(r"<!-- ht-lazypanels v1 -->.*?</script>", re.S)

STUB_TMPL = """
<script>
/* ht-lazypanels v1 gate stub: panel data loads wait here until the
 * matching panel button is clicked (loader at the end of the page). */
window.__htlpOpen = window.__htlpOpen || {};
window.__htlpWaiters = window.__htlpWaiters || {};
window.__htlpGate = window.__htlpGate || function (key) {
  if (window.__htlpOpen[key]) return Promise.resolve();
  return new Promise(function (res) { window.__htlpWaiters[key] = res; });
};
window.__htlpRelease = window.__htlpRelease || function (key) {
  window.__htlpOpen[key] = true;
  var w = window.__htlpWaiters[key];
  if (w) { delete window.__htlpWaiters[key]; w(); }
};
__WAITCORE_JS__
</script>
<style>/* ht-lazypanels v1 */
.htlp-off{display:none !important}
#htlp-bar{display:flex;flex-wrap:wrap;gap:8px;align-items:center;margin:14px 0 4px;padding:10px 12px;background:#0E1A24;border:1px solid rgba(255,255,255,.14);border-radius:12px}
#htlp-bar .htlp-t{font:700 12.5px system-ui,-apple-system,Segoe UI,Roboto,sans-serif;color:#8FC1F2;letter-spacing:.04em;margin-right:2px}
.htlp-btn{background:#23466E;border:1px solid rgba(255,255,255,.25);color:#E6EDF5;border-radius:8px;padding:6px 12px;font:600 13px system-ui,-apple-system,Segoe UI,Roboto,sans-serif;cursor:pointer}
.htlp-btn:hover{background:#2F5A8A}
.htlp-btn.htlp-on{background:#2E9B57;border-color:#7AE07A;color:#fff}
#htlp-bar.htlp-bar3d{position:fixed;left:12px;bottom:12px;z-index:9990;max-width:min(92vw,560px);margin:0;box-shadow:0 8px 30px rgba(0,0,0,.45)}
__EXTRA_CSS__
</style>"""

WAITCORE_JS_CLASSIC = ("if (!document.documentElement.classList.contains"
                       "('htlp-core-on')) document.documentElement.classList"
                       ".add('htlp-wait-core');")
WAITCORE_CSS_CLASSIC = ("html.htlp-wait-core #featcpanel,"
                        "html.htlp-wait-core #ht-drift-panel"
                        "{display:none !important}")
# The 3D drift panel's tag is a CI census anchor and must stay byte
# exact, so it is hidden by rule, not by a class on the element.
DRIFT_CSS_3D = ("#ht-drift-panel{display:none !important}\n"
                "html.htlp-drift-on #ht-drift-panel"
                "{display:block !important}")
# Flow & forecast card: hidden until the loader turns htlp-daily-on
# (the wrap rule covers the ht-uiux header bar; the canvas rule
# covers the pre-wrap interval and any no-uiux fallback).
DAILY_CSS_3D = ("html:not(.htlp-daily-on) #dock canvas,"
                "html:not(.htlp-daily-on) #dock .htux-wrap"
                "{display:none !important}")

LOADER_TMPL = """<!-- ht-lazypanels v1 -->
<div id="htlp-bar"__BARCLASS__ role="group" aria-label="Station panels"><span class="htlp-t">PANELS</span>__BUTTONS__</div>
<script>
// ht-lazypanels v1 loader: run each panel's gated boot scripts on its
// first button click only; later clicks just toggle visibility.
(function () {
  var CFG = __CONFIG__;
  var ran = {};
  function runGroup(group) {
    if (!group || ran[group]) return; ran[group] = true;
    var boots = document.querySelectorAll(
      'script[type="text/plain"][data-htlp-boot="' + group + '"]');
    Array.prototype.forEach.call(boots, function (old) {
      var sc = document.createElement('script');
      if (old.getAttribute('data-htlp-module')) sc.type = 'module';
      sc.text = old.textContent;
      document.body.appendChild(sc);
    });
    if (CFG.mode === 'classic' && group === 'core') {
      // the core relocates the DACP panel, but that panel is created
      // by the DACP boot, which runs after the core's own init in
      // document order; finish the relocation here.
      var p = document.getElementById('ht-dacp-panel');
      var slot = document.getElementById('hts-dacp-slot');
      if (p && slot && p.parentNode !== slot) slot.appendChild(p);
      document.documentElement.classList.remove('htlp-wait-core');
      document.documentElement.classList.add('htlp-core-on');
    }
  }
  function moveEl(id, slotId) {
    var el = document.getElementById(id), slot = document.getElementById(slotId);
    if (el && slot && el.parentNode !== slot) slot.appendChild(el);
  }
  if (CFG.mode === 'classic') {
    // navigation + date control take their usual places immediately;
    // the core wires them when it initialises.
    moveEl('to3d', 'hts-nav3d');
    moveEl('ht-datewrap', 'hts-date-slot');
  }
  function panelEl(cfg) {
    if (cfg.daily) return document.querySelector('#dock canvas');
    return document.getElementById(CFG.mode === 'classic' ? cfg.sec : cfg.panel);
  }
  function isOff(el, cfg) {
    if (!el) return true;
    if (cfg && cfg.daily)
      return !document.documentElement.classList.contains('htlp-daily-on');
    if (CFG.mode === '3d' && el.id === 'ht-drift-panel')
      return !document.documentElement.classList.contains('htlp-drift-on');
    if (CFG.mode === 'classic') return el.classList.contains('htlp-off');
    return el.style.display === 'none';
  }
  function setOff(el, off, cfg) {
    if (!el) return;
    if (cfg && cfg.daily) {
      // the html class lifts the stub CSS gate; the inline display
      // mirrors the module's own Geology/Watershed canvas toggles
      // and makes the ht-uiux wrap follow via its style observer.
      document.documentElement.classList.toggle('htlp-daily-on', !off);
      el.style.display = off ? 'none' : 'block';
    }
    else if (CFG.mode === 'classic') el.classList.toggle('htlp-off', off);
    else if (el.id === 'ht-drift-panel')
      document.documentElement.classList.toggle('htlp-drift-on', !off);
    else el.style.display = off ? 'none' : '';
  }
  CFG.panels.forEach(function (cfg, i) {
    var btn = document.querySelectorAll('.htlp-btn')[i];
    if (!btn) return;
    btn.addEventListener('click', function () {
      var el = panelEl(cfg);
      var opening = isOff(el, cfg);
      if (opening) {
        setOff(el, false, cfg);
        runGroup(cfg.group);
        el = panelEl(cfg);
        setOff(el, false, cfg);
        btn.classList.add('htlp-on'); btn.setAttribute('aria-pressed', 'true');
        if (CFG.mode === 'classic' && el)
          el.scrollIntoView({ block: 'start' });
      } else {
        setOff(el, true, cfg);
        btn.classList.remove('htlp-on'); btn.setAttribute('aria-pressed', 'false');
      }
    });
  });
  if (CFG.mode === '3d') {
    // the scene module's own Geology / Watershed buttons release the
    // matching data gate on their first click (capture phase, so the
    // release lands before the module toggles the panel).
    document.addEventListener('click', function (e) {
      if (!e.target || !e.target.closest) return;
      if (e.target.closest('#bShed')) window.__htlpRelease('watershed');
      if (e.target.closest('#bGeo')) window.__htlpRelease('geo');
    }, true);
  }
})();
</script>"""


def find_scripts(s: str):
    """Yield (tag_start, tag_end, body_start, body_end, attrs, body)."""
    for m in SCRIPT_RE.finditer(s):
        yield (m.start(), m.start() + len(m.group(1)) + 8,
               m.start(2), m.end(2), m.group(1), m.group(2))


def gate_boots(s: str, gates) -> tuple[str, str | None]:
    """Convert each gated boot's opening tag to inert text/plain form."""
    edits = []
    found = set()
    scripts = list(find_scripts(s))
    for sig, group, pred in gates:
        hits = []
        for (ts, te, bs, be, attrs, body) in scripts:
            ok = (sig in body) if sig else pred(body)
            if ok:
                hits.append((ts, te, attrs))
        if len(hits) != 1:
            return s, f"FAIL boot gate {sig or 'pred'}: {len(hits)} hits"
        ts, te, attrs = hits[0]
        found.add(group)
        if "data-htlp-boot" in attrs:
            if f'data-htlp-boot="{group}"' not in attrs:
                return s, f"FAIL boot gate {sig}: gated for another group"
            continue  # already gated for this group (refresh)
        is_module = 'type="module"' in attrs
        new_tag = ('<script type="text/plain" data-htlp-boot="' + group + '"'
                   + (' data-htlp-module="1"' if is_module else '') + '>')
        edits.append((ts, te, new_tag))
    for ts, te, new_tag in sorted(edits, reverse=True):
        s = s[:ts] + new_tag + s[te:]
    return s, None


def section_label(s: str, sec_id: str) -> str | None:
    m = re.search(r'<section[^>]*id="' + sec_id + r'"[^>]*>', s)
    if not m:
        return None
    tail = s[m.end():m.end() + 3000]
    h = re.search(r"<h2[^>]*>(.*?)</h2>", tail, re.S)
    if not h:
        return None
    txt = re.sub(r"<[^>]+>", "", h.group(1))
    return re.sub(r"\s+", " ", txt).strip()


def hide_classic_section(s: str, sec_id: str) -> tuple[str, str | None]:
    if f'<section class="hts-sec htlp-off" id="{sec_id}">' in s:
        return s, None  # already hidden (refresh)
    pat = re.compile(r'<section class="hts-sec" id="' + sec_id + r'"')
    n = len(pat.findall(s))
    if n != 1:
        return s, f"FAIL section {sec_id}: {n} tags"
    return pat.sub(r'<section class="hts-sec htlp-off" id="' + sec_id + '"',
                   s, count=1), None


def build_bar_loader(mode: str, panels_cfg: list) -> str:
    buttons = "".join(
        '<button type="button" class="htlp-btn" aria-pressed="false">'
        + cfg["label"] + "</button>" for cfg in panels_cfg)
    bar = LOADER_TMPL.replace("__BARCLASS__",
                              ' class="htlp-bar3d"' if mode == "3d" else "")
    bar = bar.replace("__BUTTONS__", buttons)
    bar = bar.replace("__CONFIG__", json.dumps(
        {"mode": mode, "panels": panels_cfg}, ensure_ascii=False))
    return bar


def upsert_block(s: str, new_block: str) -> tuple[str, str | None]:
    if BLOCK_RE.search(s):
        return BLOCK_RE.sub(lambda _: new_block, s, count=1), None
    if s.count("</body>") != 1:
        return s, "FAIL anchor body"
    return s.replace("</body>", new_block + "\n</body>", 1), None


def upsert_stub(s: str, mode: str) -> tuple[str, str | None]:
    stub = STUB_TMPL.replace(
        "__WAITCORE_JS__",
        WAITCORE_JS_CLASSIC if mode == "classic" else "")
    stub = stub.replace(
        "__EXTRA_CSS__",
        WAITCORE_CSS_CLASSIC if mode == "classic"
        else DRIFT_CSS_3D + "\n" + DAILY_CSS_3D)
    stub = stub.lstrip("\n")
    if STUB_RE.search(s):
        return STUB_RE.sub(lambda _: "\n" + stub, s, count=1), None
    if s.count("</head>") != 1:
        return s, "FAIL anchor head"
    return s.replace("</head>", stub + "\n</head>", 1), None


def post_checks(s: str, mode: str) -> str | None:
    table = CLASSIC_MARKERS if mode == "classic" else THREED_MARKERS
    for marker, expected in table.items():
        if s.count(marker) != expected:
            return (f"FAIL post-check census {marker!r}: "
                    f"{s.count(marker)} != {expected}")
    for marker in (CLASSIC_FORBIDDEN if mode == "classic"
                   else THREED_FORBIDDEN):
        if marker in s:
            return f"FAIL post-check forbidden {marker!r}"
    if s.count(MARKER) != 4:
        return f"FAIL post-check marker count {s.count(MARKER)} (want 4)"
    return None


def patch_classic(path: Path) -> str:
    s = path.read_text(encoding="utf-8")
    s, err = gate_boots(s, BOOT_GATES_CLASSIC)
    if err:
        return err
    panels_cfg = []
    for sec_id, group in CLASSIC_SECTIONS:
        label = section_label(s, sec_id)
        if not label:
            return f"FAIL section label {sec_id}"
        s, err = hide_classic_section(s, sec_id)
        if err:
            return err
        panels_cfg.append({"sec": sec_id, "label": label, "group": group})
    s, err = upsert_stub(s, "classic")
    if err:
        return err
    s, err = upsert_block(s, build_bar_loader("classic", panels_cfg))
    if err:
        return err
    bad = post_checks(s, "classic")
    if bad:
        return bad
    if s != path.read_text(encoding="utf-8"):
        path.write_text(s, encoding="utf-8")
        return "patched"
    return "skip (current)"


def patch_3d(path: Path) -> str:
    s = path.read_text(encoding="utf-8")
    s, err = gate_boots(s, BOOT_GATES_3D)
    if err:
        return err
    # scene-module data gates
    if GATE_RIVERS_NEW in s:
        pass
    elif s.count(GATE_RIVERS_OLD) == 1:
        s = s.replace(GATE_RIVERS_OLD, GATE_RIVERS_NEW, 1)
    else:
        return "FAIL rivers gate anchor"
    if GATE_GEO_NEW in s:
        pass
    elif s.count(GATE_GEO_OLD) == 1:
        s = s.replace(GATE_GEO_OLD, GATE_GEO_NEW, 1)
    else:
        return "FAIL geo gate anchor"
    # Compare models belongs to the Flow & forecast panel (Saurabh,
    # 2026-10-22): remove the top-row #cmpTop button and wire the
    # same cmpShowPanel toggle into the panel's canvas control row.
    if "const actCmp0 = act;" in s:
        pass
    elif s.count(CMP_IIFE) == 1:
        s = s.replace(CMP_IIFE, CMP_IIFE + CMP_SNIPPET, 1)
    else:
        return "FAIL compare wiring anchor"
    n_cmp = s.count(CMP_TOP_BTN)
    if n_cmp == 1:
        s = s.replace(CMP_TOP_BTN, "", 1)
    elif n_cmp == 0 and 'id="cmpTop"' not in s:
        pass  # already removed, and no refresh step restored it
    else:
        return "FAIL cmpTop button anchor"
    # the static drift panel starts hidden behind its button (by the
    # stub CSS rule; its tag is a census anchor and stays untouched)
    if s.count('<div id="ht-drift-panel">') != 1:
        return "FAIL drift panel tag"
    panels_cfg = [
        {"panel": "dock", "label": "Daily forecast", "group": None,
         "daily": True},
        {"panel": "htwk-panel", "label": "Weekly outlook",
         "group": "weekly"},
        {"panel": "htmo-panel", "label": "Monthly outlook",
         "group": "monthly"},
        {"panel": "htyr-panel", "label": "Yearly outlook",
         "group": "yearly"},
        {"panel": "ht-dacp-panel", "label": "Confidence interval",
         "group": "dacp"},
        {"panel": "ht-drift-panel", "label": "Model drift", "group": None},
    ]
    s, err = upsert_stub(s, "3d")
    if err:
        return err
    s, err = upsert_block(s, build_bar_loader("3d", panels_cfg))
    if err:
        return err
    bad = post_checks(s, "3d")
    if bad:
        return bad
    if s != path.read_text(encoding="utf-8"):
        path.write_text(s, encoding="utf-8")
        return "patched"
    return "skip (current)"


def main():
    root = Path("stations")
    files = sorted(root.glob("USGS-*.html"))
    if not files:
        print("no station pages found under stations/", file=sys.stderr)
        return 1
    bad = 0
    for p in files:
        r = patch_3d(p) if p.name.endswith("-3d.html") else patch_classic(p)
        print(f"{p.name}: {r}")
        if r.startswith("FAIL"):
            bad += 1
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
