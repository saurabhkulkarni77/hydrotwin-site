#!/usr/bin/env python3
"""UI/UX fixes for the DEV station pages (dev only) — ht-uiux v1.

1) 3D pages: the "Model comparison" legend in drawFlow() was drawn as a
   floating box on top of the hydrograph (lx = x1-300, ly = 140). It now
   lives in a reserved band under the panel header: the comparison list
   is computed before layout, legend items are packed into wrapped rows
   (measured text widths), and the plot top (y0) shifts down by the band
   height. Nothing else in drawFlow geometry changes — buttons stay at
   the BTNY fractions, so clickFlow()/VR raycast paths are untouched.

2) Both page types: a self-contained enhancer script (vanilla JS/CSS)
   makes every floating panel movable + expandable:
   - 3D: #hud (drag + maximize; it keeps its native hide toggle),
     #ht-drift-panel (drag by .htd-head + maximize; native toggle kept),
     #ht-dacp-panel (drag + collapse + maximize), #larpanel and
     #cmppanel (drag by header + collapse + maximize), #livepanel
     (drag + collapse + maximize), and the docked canvas panels
     (flowP in #dock, geoP/shedP in #side) get a slim header bar with
     drag + collapse + maximize.
   - Classic: #ht-drift-panel and #ht-dacp-panel (the only floaters).
   Dragging clamps to the viewport, raises z-order, never starts from
   interactive children, and a post-drag click is swallowed so toggles
   and checkboxes don't fire after a drag. Maximize is a CSS class
   (geometry via !important), so restore is exact. Panels created later
   (LiveAR/CMP/LIVE) are caught by a MutationObserver.

Idempotent: pages carrying the MARKER are skipped.
Run from the repo root: python3 build25/patch_uiux.py
"""
import sys
from pathlib import Path

MARKER = "ht-uiux v1"

# --------------------------- anchors: 3D legend ---------------------------
LEG_A_OLD = ("const x0 = 30, x1 = W * 0.69, y0 = 125, y1 = H * 0.6, win = 90, "
             "a = Math.max(0, i - win + 1), cols = win + 7;")
LEG_A_NEW = """const cmpList = (typeof CMP !== 'undefined' && CMP.on && CMP.models.length && D.flow[i] != null) ? CMP.models.map((m) => [m, cmpForecast(m, i)]).filter((x) => x[1]) : [];
  const legItems = cmpList.length ? [['Model comparison', null]].concat([['Observed', '#6FB0F0']], cmpList.map(([m]) => [D.models[m], cmpColor(m)])) : [];
  let legBandH = 0;
  if (legItems.length) { g.font = '600 20px Arial'; let cx = 30, rows = 1; legItems.forEach((it) => { const w = (it[1] ? 32 : 0) + g.measureText(it[0]).width + 30; if (cx > 30 && cx + w > W - 30) { rows++; cx = 30; } it.push(w); cx += w; }); legBandH = rows * 30 + 16; }
  const x0 = 30, x1 = W * 0.69, y0 = 125 + legBandH, y1 = H * 0.6, win = 90, a = Math.max(0, i - win + 1), cols = win + 7;"""

CMP_START = "  // multi-model comparison overlay\n"
CMP_END = "  BTN.forEach((row, r) => row.forEach(([t, ac], k) => {"
CMP_NEW = """  // multi-model comparison overlay (ht-uiux v1: legend in the reserved band under the header - never over the charts)
  if (cmpList.length) {
    cmpList.forEach(([m, fc]) => {
      g.strokeStyle = cmpColor(m); g.lineWidth = 4; g.beginPath();
      g.moveTo(X(i), Y(D.flow[i]));
      fc.forEach((v, l) => g.lineTo(X(i + l + 1), Y(v)));
      g.stroke();
    });
    let lx2 = 30, ly2 = 132;
    g.textAlign = 'left';
    legItems.forEach((it) => {
      if (lx2 > 30 && lx2 + it[2] > W - 30) { lx2 = 30; ly2 += 30; }
      if (it[1]) { g.fillStyle = it[1]; g.fillRect(lx2, ly2 - 15, 22, 6); }
      g.font = it[1] ? '20px Arial' : '600 20px Arial';
      g.fillStyle = it[1] ? '#DDE6EE' : '#FFFFFF';
      g.fillText(it[0], lx2 + (it[1] ? 32 : 0), ly2 - 3);
      lx2 += it[2];
    });
    g.textAlign = 'left';
  }
"""

# ------------------------------ injected UI -------------------------------
JS_BODY = r"""
<script>
/* ht-uiux v1 - movable + expandable floating panels (dev). Vanilla JS.
 * Drag by header, collapse toggle, maximize/restore for every floating
 * panel; docked canvas panels get a slim header bar. Desktop DOM only;
 * the WebXR scene and its code paths are not touched. */
(function () {
  if (window.__htUx) return; window.__htUx = 1;
  var zTop = 10000;
  var CSS = ''
    + '.htux-handle{cursor:move;touch-action:none}'
    + '.htux-ctl{display:inline-flex;gap:4px;align-items:center;margin-left:8px;vertical-align:middle;flex:none}'
    + '.htux-btn{background:rgba(35,70,110,.9);border:1px solid rgba(255,255,255,.35);color:#E6EDF5;border-radius:6px;min-width:22px;height:22px;padding:0 5px;cursor:pointer;font:600 13px/1 Arial}'
    + '.htux-btn:hover{background:rgba(47,111,176,.95)}'
    + '.htux-max{position:fixed !important;left:10px !important;top:10px !important;right:auto !important;bottom:auto !important;width:calc(100vw - 20px) !important;height:calc(100vh - 20px) !important;max-width:none !important;max-height:none !important;transform:none !important;overflow:auto !important;z-index:10060 !important;box-sizing:border-box}'
    + '#ht-drift-panel.htux-max .htd-body{max-height:none !important}'
    + '.htux-wrap{display:block}'
    + '.htux-chead{display:flex;justify-content:space-between;align-items:center;background:rgba(12,18,28,.9);color:#BFD0E0;font:600 12px Arial;padding:4px 6px 4px 10px;border-radius:10px 10px 0 0;cursor:move;touch-action:none;user-select:none;-webkit-user-select:none}'
    + '#dock .htux-wrap > canvas,#side .htux-wrap > canvas{border-radius:0 0 10px 10px}'
    + '.htux-wrap.htux-max > canvas{width:100% !important;height:auto !important}'
    + '.htux-raise{z-index:10040 !important}';
  var sty = document.createElement('style'); sty.textContent = CSS; document.head.appendChild(sty);

  function isInt(t) { return !!(t.closest && t.closest('button,input,select,textarea,label,a,.htux-ctl,.tg,#htd-toggle')); }
  function raise(el) {
    el.style.zIndex = ++zTop;
    var cont = el.closest ? el.closest('#dock,#side') : null;
    if (cont) { cont.classList.add('htux-raise'); cont.style.zIndex = ++zTop; }
  }
  function swallowClick(el) {
    var f = function (ev) { ev.stopPropagation(); ev.preventDefault(); el.removeEventListener('click', f, true); };
    el.addEventListener('click', f, true);
    setTimeout(function () { el.removeEventListener('click', f, true); }, 500);
  }
  function freeze(el) {
    if (el.dataset.htuxFrozen) return;
    var r = el.getBoundingClientRect();
    if (getComputedStyle(el).position !== 'fixed') { el.style.position = 'fixed'; el.style.width = r.width + 'px'; }
    el.style.left = r.left + 'px'; el.style.top = r.top + 'px';
    el.style.right = 'auto'; el.style.bottom = 'auto'; el.style.transform = 'none';
    el.dataset.htuxFrozen = '1';
  }
  function dragify(el, handle) {
    if (!handle || handle.dataset.htuxDrag) return; handle.dataset.htuxDrag = '1';
    handle.classList.add('htux-handle');
    handle.addEventListener('pointerdown', function (e) {
      if (e.button) return;
      if (el.classList.contains('htux-max')) return;
      if (e.target !== handle && isInt(e.target)) return;
      raise(el); freeze(el);
      var r = el.getBoundingClientRect();
      var offX = e.clientX - r.left, offY = e.clientY - r.top, sx = e.clientX, sy = e.clientY, moved = false;
      function mv(ev) {
        if (!moved && Math.abs(ev.clientX - sx) + Math.abs(ev.clientY - sy) < 4) return;
        moved = true;
        var w = el.offsetWidth;
        var nx = ev.clientX - offX, ny = ev.clientY - offY;
        nx = Math.max(-(w - 80), Math.min(window.innerWidth - 60, nx));
        ny = Math.max(0, Math.min(window.innerHeight - 34, ny));
        el.style.left = nx + 'px'; el.style.top = ny + 'px';
        ev.preventDefault();
      }
      function up() {
        document.removeEventListener('pointermove', mv, true);
        document.removeEventListener('pointerup', up, true);
        if (moved) swallowClick(el);
      }
      document.addEventListener('pointermove', mv, true);
      document.addEventListener('pointerup', up, true);
      e.preventDefault();
    });
  }
  function ctlBtn(txt, title) {
    var b = document.createElement('button'); b.type = 'button'; b.className = 'htux-btn';
    b.textContent = txt; b.title = title;
    b.addEventListener('pointerdown', function (e) { e.stopPropagation(); });
    return b;
  }
  function makeCtl() { var sp = document.createElement('span'); sp.className = 'htux-ctl'; return sp; }
  function maxBtn(el) {
    var b = ctlBtn('\u25a1', 'Expand / restore');
    b.addEventListener('click', function () {
      var on = el.classList.toggle('htux-max');
      b.textContent = on ? '\u2750' : '\u25a1';
      if (on) raise(el);
    });
    return b;
  }
  function minBtn(el, keep) {
    var b = ctlBtn('\u2013', 'Collapse / expand');
    b.addEventListener('click', function () {
      var on = el.classList.toggle('htux-min');
      Array.prototype.forEach.call(el.children, function (ch) {
        if (keep.indexOf(ch) >= 0) return;
        if (on) { ch.dataset.htuxDisp = ch.style.display || ''; ch.style.display = 'none'; }
        else if (ch.dataset.htuxDisp !== undefined) { ch.style.display = ch.dataset.htuxDisp; delete ch.dataset.htuxDisp; }
      });
      b.textContent = on ? '+' : '\u2013';
    });
    return b;
  }

  function enhHud(el) {
    if (el.querySelector('.htux-ctl')) return;
    var ctl = makeCtl(); ctl.appendChild(maxBtn(el));
    el.insertBefore(ctl, el.firstChild);
    dragify(el, el);
  }
  function enhDrift(el) {
    if (el.querySelector('.htux-ctl')) return;
    var head = el.querySelector('.htd-head') || el;
    var ctl = makeCtl(); ctl.appendChild(maxBtn(el));
    head.appendChild(ctl);
    dragify(el, head);
  }
  function enhDacp(el) {
    if (el.querySelector('.htux-ctl')) return;
    var ctl = makeCtl();
    var title = el.querySelector('.htdc-t');
    var keep = [ctl]; if (title) keep.push(title);
    ctl.appendChild(minBtn(el, keep)); ctl.appendChild(maxBtn(el));
    el.insertBefore(ctl, el.firstChild);
    ctl.style.float = 'right';
    dragify(el, el);
  }
  function enhHeadPanel(el) {  // LiveAR + CMP panels: first row is the header
    if (el.querySelector('.htux-ctl')) return;
    var head = null;
    for (var i = 0; i < el.children.length; i++) { if (el.children[i].nodeType === 1) { head = el.children[i]; break; } }
    if (!head) head = el;
    var ctl = makeCtl();
    ctl.appendChild(minBtn(el, [head])); ctl.appendChild(maxBtn(el));
    head.appendChild(ctl);
    dragify(el, head);
  }
  function enhLive(el) {
    if (el.querySelector('.htux-ctl')) return;
    var ctl = makeCtl();
    var keep = [ctl];
    Array.prototype.forEach.call(el.children, function (ch) { if (ch.tagName === 'B') keep.push(ch); });
    ctl.appendChild(minBtn(el, keep)); ctl.appendChild(maxBtn(el));
    el.insertBefore(ctl, el.firstChild);
    ctl.style.float = 'right';
    dragify(el, el);
  }
  var CV_TITLES = { dock: ['Flow & forecast'], side: ['Geology', 'Watershed'] };
  function mirror(cv, wrap) {
    wrap.style.display = (getComputedStyle(cv).display === 'none') ? 'none' : '';
  }
  function wrapCanvas(cv) {
    if (cv.closest('.htux-wrap')) return;
    var cont = cv.parentElement; if (!cont || !cont.id) return;
    if (!cv.__htuxTitle) {
      var idx = Array.prototype.filter.call(cont.querySelectorAll('canvas'), function (c) { return !!c.__htuxTitle; }).length;
      cv.__htuxTitle = (CV_TITLES[cont.id] || ['Panel'])[idx] || 'Panel';
    }
    var wrap = document.createElement('div'); wrap.className = 'htux-wrap';
    var head = document.createElement('div'); head.className = 'htux-chead';
    var t = document.createElement('span'); t.textContent = cv.__htuxTitle;
    var ctl = makeCtl();
    ctl.appendChild(minBtn(wrap, [head])); ctl.appendChild(maxBtn(wrap));
    head.appendChild(t); head.appendChild(ctl);
    wrap.appendChild(head);
    cont.insertBefore(wrap, cv); wrap.appendChild(cv);
    mirror(cv, wrap);
    new MutationObserver(function () { mirror(cv, wrap); }).observe(cv, { attributes: true, attributeFilter: ['style'] });
    dragify(wrap, head);
  }
  function scan() {
    try {
      var el;
      el = document.getElementById('hud'); if (el) enhHud(el);
      el = document.getElementById('ht-drift-panel'); if (el) enhDrift(el);
      el = document.getElementById('ht-dacp-panel'); if (el) enhDacp(el);
      el = document.getElementById('larpanel'); if (el) enhHeadPanel(el);
      el = document.getElementById('cmppanel'); if (el) enhHeadPanel(el);
      el = document.getElementById('livepanel'); if (el) enhLive(el);
      Array.prototype.forEach.call(document.querySelectorAll('#dock canvas, #side canvas'), wrapCanvas);
    } catch (e) { /* one bad panel must not break the rest */ }
  }
  scan();
  var n = 0, iv = setInterval(function () { scan(); if (++n > 90) clearInterval(iv); }, 700);
  new MutationObserver(function () { scan(); }).observe(document.body, { childList: true, subtree: true });
})();
</script>
"""


def patch_3d_legend(s):
    if s.count(LEG_A_OLD) != 1:
        return None
    i = s.find(CMP_START)
    j = s.find(CMP_END)
    if i < 0 or j < 0 or j <= i:
        return None
    span = s[i:j]
    if "Model comparison" not in span or "cmpFcs" not in span or "roundRect" not in span:
        return None
    n_btn = s.count("BTN.forEach")
    # Span surgery FIRST (indices are only valid on the unmodified string),
    # then the LEG_A replacement, whose position is re-found afterwards.
    s = s[:i] + CMP_NEW + s[j:]
    if s.count("BTN.forEach") != n_btn:
        return None
    if s.count(LEG_A_OLD) != 1:
        return None
    s = s.replace(LEG_A_OLD, LEG_A_NEW, 1)
    if "cmpList" not in s or "legItems" not in s or "Model comparison" not in s:
        return None
    if "lx = x1 - 300" in s or s.count("function drawFlow()") != 1:
        return None
    return s


def patch_page(s):
    if MARKER in s:
        return s
    out = s
    if "window.HT3D =" in s:  # payload assignment: only real 3D pages (both types merely reference it in the DACP script)
        out = patch_3d_legend(out)
        if out is None:
            return None
    if out.count("</body>") != 1:
        return None
    out = out.replace("</body>", JS_BODY + "\n</body>", 1)
    if MARKER not in out:
        return None
    return out


def main():
    pages = sorted(Path("stations").glob("*.html"))
    if not pages:
        print("no station pages found (run from repo root)", file=sys.stderr)
        return 1
    n_new = n_skip = n_warn = 0
    for p in pages:
        s = p.read_text(encoding="utf-8")
        if MARKER in s:
            n_skip += 1
            print(f"already patched: {p.name}")
            continue
        out = patch_page(s)
        if out is None:
            n_warn += 1
            print(f"WARNING: anchors not as expected, skipped: {p.name}")
            continue
        p.write_text(out, encoding="utf-8")
        n_new += 1
        print(f"patched: {p.name}")
    print(f"patch_uiux: {n_new} page(s) newly patched, {n_skip} already, "
          f"{n_warn} skipped-with-warning, {len(pages)} pages scanned")
    return 0


if __name__ == "__main__":
    sys.exit(main())
