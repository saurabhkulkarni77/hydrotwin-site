/* ht-helperbot v4 — HydroTwin helper bot.
 *
 * A chat widget (bottom right) that answers "where is X / how do I Y"
 * questions about the digital twin. Location answers come from the
 * generated site index (helper/ht-index.json): retrieval over that
 * index always runs first, its answer is shown instantly, and its
 * entries drive the "Show me" actions. Index answers never wait on
 * the network.
 *
 * Server-side AI (v4): the optional open source model no longer runs
 * in the visitor's browser. v1-v3 loaded WebLLM on-device; the model
 * load crashed mobile Safari tabs outright (memory pressure kills
 * the web content process, worker isolation or not). Now a small
 * open source model (Qwen2.5 0.5B Instruct, GGUF) is hosted on the
 * project's own cloud (private S3 bucket + AWS Lambda llama.cpp) and
 * the bot calls its HTTPS endpoint with the question plus the
 * retrieved index entries; when the rephrased answer arrives it
 * replaces the answer text (the Show me buttons stay). ANY endpoint
 * failure (network, timeout, bad JSON, 5xx) silently keeps the index
 * answer. If AI_ENDPOINT is empty the bot is exactly the pure index
 * bot. There is no model download, no Enable button, and no worker.
 */
(function () {
  'use strict';
  if (window.__htHelperBot) return;
  window.__htHelperBot = true;

  // ------------------------------------------------------------- config
  // Lambda Function URL for the helper-bot model endpoint.
  // Empty string = endpoint off (pure index bot).
  var AI_ENDPOINT = '';
  var AI_TIMEOUT_MS = 45000;

  var scriptEl = document.currentScript || document.querySelector('script[src*="ht-helper.js"]');
  var base = scriptEl ? new URL('.', scriptEl.src).href : '../helper/';
  var rootUrl = new URL('..', base).href; // site root ('' from stations/, './' from home)
  window.__htHelperAI = { mode: AI_ENDPOINT ? 'server' : 'index', endpoint: AI_ENDPOINT || null };

  var css = ''
    + '#hthb-btn{position:fixed;right:16px;bottom:16px;z-index:99990;background:#23466E;color:#fff;border:1px solid rgba(255,255,255,.3);border-radius:999px;padding:11px 16px;font:600 14px system-ui,-apple-system,Segoe UI,Roboto,sans-serif;cursor:pointer;box-shadow:0 8px 24px rgba(0,0,0,.45)}'
    + '#hthb-btn:hover{background:#2E5A8A}'
    + '#hthb-panel{position:fixed;right:16px;bottom:66px;z-index:99990;width:min(380px,94vw);height:min(560px,78vh);display:none;flex-direction:column;background:rgba(11,19,29,.97);color:#E6EDF5;border:1px solid rgba(255,255,255,.2);border-radius:14px;box-shadow:0 14px 44px rgba(0,0,0,.55);font:13.5px/1.5 system-ui,-apple-system,Segoe UI,Roboto,sans-serif;overflow:hidden}'
    + '#hthb-panel.open{display:flex}'
    + '#hthb-head{display:flex;align-items:center;gap:8px;padding:11px 14px;background:#122539;border-bottom:1px solid rgba(255,255,255,.12)}'
    + '#hthb-head b{font-size:14px;color:#F5F6F2}#hthb-head span{color:#9FB3C8;font-size:11.5px}'
    + '#hthb-close{margin-left:auto;background:none;border:none;color:#9FB3C8;font-size:18px;cursor:pointer}'
    + '#hthb-msgs{flex:1;overflow-y:auto;padding:12px 14px;display:flex;flex-direction:column;gap:10px}'
    + '.hthb-m{max-width:92%;padding:8px 11px;border-radius:10px;white-space:pre-wrap;word-break:break-word}'
    + '.hthb-u{align-self:flex-end;background:#23466E;color:#fff}'
    + '.hthb-a{align-self:flex-start;background:#16222F;border:1px solid rgba(255,255,255,.1)}'
    + '.hthb-act{display:inline-block;margin:6px 6px 0 0;background:#2E9B57;color:#fff;border:none;border-radius:7px;padding:5px 10px;font:600 12px system-ui;cursor:pointer}'
    + '.hthb-chips{display:flex;flex-wrap:wrap;gap:6px;padding:0 14px 8px}'
    + '.hthb-chip{background:#1B2C40;color:#BFD4EA;border:1px solid rgba(255,255,255,.18);border-radius:999px;padding:4px 10px;font:12px system-ui;cursor:pointer}'
    + '#hthb-ai{margin:0 14px 10px;padding:9px 11px;background:#101E30;border:1px solid rgba(255,255,255,.14);border-radius:10px;font-size:12px;color:#BFD4EA}'
    + '.hthb-aitag{font-size:11px;color:#8FC1F2;margin-top:6px}'
    + '#hthb-form{display:flex;gap:8px;padding:10px 12px;border-top:1px solid rgba(255,255,255,.12)}'
    + '#hthb-in{flex:1;background:#0E1A24;color:#E8EEF5;border:1px solid #3A4A5E;border-radius:8px;padding:8px 10px;font:13.5px system-ui}'
    + '#hthb-send{background:#23466E;color:#fff;border:1px solid rgba(255,255,255,.25);border-radius:8px;padding:8px 13px;font:600 13px system-ui;cursor:pointer}'
    + '.hthb-hl{outline:3px solid #FFB84D !important;outline-offset:3px;transition:outline-color .3s}'
    ;
  var st = document.createElement('style'); st.textContent = css; document.head.appendChild(st);

  var btn = document.createElement('button');
  btn.id = 'hthb-btn'; btn.type = 'button'; btn.textContent = '💬 Ask HydroTwin';
  btn.setAttribute('aria-label', 'Open the HydroTwin helper bot');
  document.body.appendChild(btn);

  var panel = document.createElement('div');
  panel.id = 'hthb-panel';
  panel.setAttribute('role', 'dialog'); panel.setAttribute('aria-label', 'HydroTwin helper bot');
  panel.innerHTML = ''
    + '<div id="hthb-head"><b>HydroTwin helper</b><span>find pages, panels and controls</span>'
    + '<button id="hthb-close" type="button" aria-label="Close">×</button></div>'
    + '<div id="hthb-msgs"></div>'
    + '<div class="hthb-chips">'
    + '<button class="hthb-chip" type="button">Where is the hydrograph?</button>'
    + '<button class="hthb-chip" type="button">Lees Ferry 3D page</button>'
    + '<button class="hthb-chip" type="button">How do I change the date?</button>'
    + '<button class="hthb-chip" type="button">Which features affect flow in Dallas?</button>'
    + '</div>'
    + '<div id="hthb-ai"><b>Site AI</b> <span id="hthb-ai-status"></span></div>'
    + '<form id="hthb-form"><input id="hthb-in" type="text" autocomplete="off" placeholder="Ask where something is…">'
    + '<button id="hthb-send" type="submit">Ask</button></form>';
  document.body.appendChild(panel);

  var msgs = panel.querySelector('#hthb-msgs');
  var input = panel.querySelector('#hthb-in');
  var aiStatus = panel.querySelector('#hthb-ai-status');
  aiStatus.textContent = AI_ENDPOINT
    ? 'is on: answers are located instantly from the built-in site index, then a small open source model (Qwen2.5 0.5B) hosted on this project’s own cloud rephrases them in friendlier words. Your question and the index entries it matched are sent to that endpoint; nothing else leaves your browser, and nothing is downloaded.'
    : 'is off: answers come straight from the built-in site index.';

  function addMsg(text, who) {
    var d = document.createElement('div');
    d.className = 'hthb-m ' + (who === 'u' ? 'hthb-u' : 'hthb-a');
    d.textContent = text;
    msgs.appendChild(d); msgs.scrollTop = msgs.scrollHeight;
    return d;
  }

  // ------------------------------------------------------------ index
  var INDEX = null, indexErr = null;
  fetch(base + 'ht-index.json').then(function (r) {
    if (!r.ok) throw new Error('index ' + r.status);
    return r.json();
  }).then(function (d) {
    INDEX = d;
    window.__htHelper = { ready: true, entries: d.entries.length, stations: d.stations.length };
  }).catch(function (e) {
    indexErr = e; window.__htHelper = { ready: false, error: String(e) };
  });

  function norm(s) { return String(s || '').toLowerCase().replace(/[^a-z0-9 ]+/g, ' ').replace(/\s+/g, ' ').trim(); }
  function retrieve(q) {
    if (!INDEX) return [];
    var nq = ' ' + norm(q) + ' ';
    var toks = norm(q).split(' ').filter(function (t) { return t.length > 1; });
    var scored = [];
    for (var i = 0; i < INDEX.entries.length; i++) {
      var e = INDEX.entries[i], s = 0;
      var title = norm(e.title), text = norm(e.text);
      for (var k = 0; k < e.keywords.length; k++) {
        var kw = norm(e.keywords[k]);
        if (kw && nq.indexOf(' ' + kw + ' ') >= 0) s += 9;
        else if (kw && kw.split(' ').some(function (w) { return toks.indexOf(w) >= 0; })) s += 3;
      }
      for (var t = 0; t < toks.length; t++) {
        if (title.indexOf(toks[t]) >= 0) s += 4;
        if (text.indexOf(toks[t]) >= 0) s += 1;
      }
      if (e.kind === 'station' && (nq.indexOf(' page ') >= 0 || nq.indexOf(' open ') >= 0)) s += 7;
      if (s > 0) scored.push([s, e]);
    }
    scored.sort(function (a, b) { return b[0] - a[0]; });
    return scored.slice(0, 3).map(function (x) { return x[1]; });
  }

  function currentPagePath() {
    var p = location.pathname;
    var i = p.indexOf('/stations/');
    if (i >= 0) return p.slice(i + 1);
    if (/index\.html$/.test(p) || p.endsWith('/')) return 'index.html';
    return p.split('/').pop();
  }

  function entryUrl(e) {
    if (!e.url) return null;
    if (e.url === currentPagePath()) return null; // already here
    return rootUrl + e.url;
  }

  // ------------------------------------------------------------ show me
  var CLASSIC_ORDER = ['hts-sec-hydro', 'hts-sec-fc', 'hts-sec-models', 'hts-sec-ablation', 'hts-sec-weekly',
    'hts-sec-monthly', 'hts-sec-yearly', 'hts-sec-drift', 'hts-sec-3dchart', 'hts-sec-corr',
    'hts-sec-featimp', 'hts-sec-clusters', 'hts-sec-charts3d'];
  function highlight(el) {
    if (!el) return false;
    try { el.scrollIntoView({ block: 'center', behavior: 'smooth' }); } catch (err) { el.scrollIntoView(); }
    el.classList.add('hthb-hl');
    setTimeout(function () { el.classList.remove('hthb-hl'); }, 6000);
    return true;
  }
  function openPanelButton(label) {
    var btns = document.querySelectorAll('#htlp-bar .htlp-btn');
    for (var i = 0; i < btns.length; i++) {
      if (btns[i].textContent.trim().toLowerCase() === String(label || '').trim().toLowerCase()
        && !btns[i].classList.contains('htlp-on')) { btns[i].click(); return true; }
    }
    return false;
  }
  function showTarget(target, buttonLabel) {
    if (!target) return;
    var tries = 0;
    var iv = setInterval(function () {
      tries++;
      var el = target === 'body' ? document.body : document.querySelector(target);
      if (el) {
        var hidden = el.classList && el.classList.contains('htlp-off');
        if (hidden && buttonLabel) openPanelButton(buttonLabel);
        if (!hidden || tries > 6) {
          clearInterval(iv);
          setTimeout(function () { highlight(document.querySelector(target) || el); }, hidden ? 350 : 0);
        }
      } else if (buttonLabel && tries === 2) {
        openPanelButton(buttonLabel); // panel element is created by its boot
      }
      if (tries > 24) clearInterval(iv);
    }, 400);
  }
  function showMe(e) {
    var url = entryUrl(e);
    if (!url) { showTarget(e.target, e.button); return; }
    var sep = url.indexOf('?') >= 0 ? '&' : '?';
    location.href = url + sep + 'htshow=' + encodeURIComponent(e.target || '')
      + (e.button ? '&htbtn=' + encodeURIComponent(e.button) : '');
  }
  (function applyShowParam() {
    var qp = new URLSearchParams(location.search);
    if (qp.has('htshow')) showTarget(qp.get('htshow'), qp.get('htbtn'));
  })();

  // ------------------------------------------------------------ answers
  function fallbackAnswer(q, hits) {
    if (!hits.length) {
      return 'I could not find that in the site index. I can locate stations (try a station name or a USGS number like 08057000), pages (Data view, 3D view, home map, MLOps), panels (hydrograph, forecast, feature importance, outlooks, drift) and controls (the Date field, view switches, the PANELS bar).';
    }
    var top = hits[0];
    var out = top.title + '\n' + top.text;
    if (hits.length > 1) {
      out += '\n\nAlso relevant: ' + hits.slice(1).map(function (e) { return e.title; }).join(' · ');
    }
    return out;
  }

  // Server-side AI rephrase. The index answer is already on screen;
  // this only swaps the answer text when a good reply arrives, and
  // silently keeps the index answer on ANY failure. The Show me
  // buttons live outside the text span and are never touched.
  function askServer(q, hits, txtSpan, tag) {
    if (!AI_ENDPOINT || !hits.length) { tag.remove(); return; }
    tag.textContent = 'Asking the site AI…';
    var done = false;
    var ctrl = ('AbortController' in window) ? new AbortController() : null;
    var timer = setTimeout(function () {
      if (done) return;
      done = true;
      if (ctrl) { try { ctrl.abort(); } catch (e) { /* ignore */ } }
      tag.remove();
    }, AI_TIMEOUT_MS);
    function settle() { if (!done) { done = true; clearTimeout(timer); } }
    try {
      fetch(AI_ENDPOINT, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          question: q,
          context: hits.map(function (e) {
            return { title: e.title, text: e.text, page: e.url || 'this page' };
          }),
        }),
        signal: ctrl ? ctrl.signal : undefined,
      }).then(function (r) {
        if (!r.ok) throw new Error('endpoint ' + r.status);
        return r.json();
      }).then(function (d) {
        settle();
        var txt = d && typeof d.answer === 'string' ? d.answer.trim() : '';
        if (txt) {
          txtSpan.textContent = txt;
          tag.textContent = 'Answer rephrased by the site AI (open source Qwen2.5 0.5B, hosted by this project). Locations come from the site index.';
        } else {
          tag.remove();
        }
        msgs.scrollTop = msgs.scrollHeight;
      }).catch(function () {
        settle();
        tag.remove(); // silent: the index answer stays
      });
    } catch (e) {
      settle();
      tag.remove();
    }
  }

  function ask(q) {
    q = String(q || '').trim();
    if (!q) return;
    addMsg(q, 'u');
    if (!INDEX) {
      addMsg(indexErr ? 'The site index failed to load, so I cannot look that up right now.' : 'Loading the site index… ask again in a moment.', 'a');
      return;
    }
    var hits = retrieve(q);
    var bubble = addMsg('', 'a');
    var txtSpan = document.createElement('span');
    txtSpan.textContent = fallbackAnswer(q, hits);
    bubble.appendChild(txtSpan);
    hits.slice(0, 2).forEach(function (e) {
      var b = document.createElement('button');
      b.className = 'hthb-act'; b.type = 'button';
      b.textContent = 'Show me: ' + e.title;
      b.addEventListener('click', function () { showMe(e); });
      bubble.appendChild(document.createElement('br'));
      bubble.appendChild(b);
    });
    var tag = document.createElement('div');
    tag.className = 'hthb-aitag';
    bubble.appendChild(tag);
    msgs.scrollTop = msgs.scrollHeight;
    askServer(q, hits, txtSpan, tag);
  }

  // ------------------------------------------------------------ wiring
  var greeted = false;
  btn.addEventListener('click', function () {
    panel.classList.toggle('open');
    if (panel.classList.contains('open') && !greeted) {
      greeted = true;
      addMsg('Hi, I help visitors find things on HydroTwin: stations, pages, panels and controls. Ask me where something is, or tap “Show me” and I will take you there and highlight it.', 'a');
      input.focus();
    }
  });
  panel.querySelector('#hthb-close').addEventListener('click', function () { panel.classList.remove('open'); });
  panel.querySelector('#hthb-form').addEventListener('submit', function (ev) {
    ev.preventDefault(); ask(input.value); input.value = '';
  });
  Array.prototype.forEach.call(panel.querySelectorAll('.hthb-chip'), function (chip) {
    chip.addEventListener('click', function () { ask(chip.textContent); });
  });
})();
