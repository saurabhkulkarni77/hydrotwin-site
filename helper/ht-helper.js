/* ht-helperbot v3 — HydroTwin helper bot.
 *
 * A chat widget (bottom right) that answers "where is X / how do I Y"
 * questions about the digital twin. Location answers come from the
 * generated site index (helper/ht-index.json): retrieval over that
 * index always runs first and its entries drive the answer text and
 * the "Show me" actions. An optional in-browser OPEN SOURCE LLM
 * (WebLLM) can rephrase the answer, grounded on the same retrieved
 * entries passed as context; it is strictly opt-in (a one-time model
 * download starts only when the visitor presses the enable button).
 *
 * Crash isolation (v2): the model never runs on the page thread.
 *  - A WebGPU preflight (navigator.gpu + requestAdapter) runs before
 *    anything is downloaded; browsers without WebGPU get a plain
 *    message in the panel and nothing is loaded at all.
 *  - The engine lives in a dedicated Web Worker
 *    (helper/ht-llm-worker.js, CreateWebWorkerMLCEngine), so a GPU,
 *    shader-compile or out-of-memory failure can only kill the
 *    worker, never the page.
 *  - Every load step is awaited inside try/catch with a progress
 *    watchdog and a Cancel button; ANY failure latches the bot back
 *    to direct index answers for the rest of the session, with the
 *    index answer (shown immediately regardless) left in place.
 *
 * Round 2 (v3): worker isolation was not enough on iPhone Safari —
 * the OS kills the whole web content process under memory pressure
 * during the 1B weight load, the tab reloads fresh, and v2 said
 * nothing. So now:
 *  - The SMALL model (Qwen2.5 0.5B Instruct q4f16, ~400 MB class) is
 *    the default everywhere. The 1B is attempted first only on a
 *    non-mobile browser reporting >= 8 GB device memory, and even
 *    there the 0.5B remains the fallback. Stability beats size: the
 *    bot only rephrases short index answers.
 *  - A load attempt writes a marker to sessionStorage before the
 *    download starts; it is cleared only when an engine reports
 *    fully ready (which also sets a ready flag). At boot, a marker
 *    with no ready flag means the previous attempt died with the
 *    page: the panel says so plainly, AI latches off for the rest
 *    of the tab session, and nothing retries on its own. One press
 *    of the button is exactly one attempt.
 */
(function () {
  'use strict';
  if (window.__htHelperBot) return;
  window.__htHelperBot = true;

  var scriptEl = document.currentScript || document.querySelector('script[src*="ht-helper.js"]');
  var base = scriptEl ? new URL('.', scriptEl.src).href : '../helper/';
  var rootUrl = new URL('..', base).href; // site root ('' from stations/, './' from home)
  var WEBLLM_URL = 'https://cdn.jsdelivr.net/npm/@mlc-ai/web-llm@0.2.79/+esm';
  var WORKER_URL = base + 'ht-llm-worker.js';
  var MODEL_BIG = { id: 'Llama-3.2-1B-Instruct-q4f16_1-MLC', label: 'Llama 3.2 1B', size: 'about 800 MB' };
  var MODEL_SMALL = { id: 'Qwen2.5-0.5B-Instruct-q4f16_1-MLC', label: 'Qwen2.5 0.5B (small)', size: 'about 400 MB' };
  // The 0.5B build is the default everywhere: the 1B build (~880 MB
  // with runtime) gets iPhone Safari tabs killed under memory pressure
  // mid-load, and this bot only rephrases short index answers. The 1B
  // is attempted first ONLY on a non-mobile browser that reports at
  // least 8 GB of device memory, and even there the 0.5B stays as the
  // automatic fallback.
  function isMobileLike() {
    var ua = navigator.userAgent || '';
    if (/iPhone|iPad|iPod|Android|Mobile|Silk/i.test(ua)) return true;
    // iPads on iOS 13+ present a desktop Mac user agent; touch points tell.
    if (/Macintosh/.test(ua) && typeof navigator.maxTouchPoints === 'number' && navigator.maxTouchPoints > 1) return true;
    return false;
  }
  var bigDesktop = !isMobileLike()
    && typeof navigator.deviceMemory === 'number' && navigator.deviceMemory >= 8;
  var MODELS = bigDesktop ? [MODEL_BIG, MODEL_SMALL] : [MODEL_SMALL];
  window.__htHelperPlan = { models: MODELS.map(function (m) { return m.id; }), bigDesktop: bigDesktop };

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
    + '#hthb-ai button{background:#23466E;color:#fff;border:1px solid rgba(255,255,255,.25);border-radius:7px;padding:5px 10px;font:600 12px system-ui;cursor:pointer;margin-top:6px}'
    + '#hthb-ai button:disabled{opacity:.55;cursor:default}'
    + '#hthb-ai-cancel{margin-left:6px;background:#3A2A22 !important}'
    + '#hthb-ai .hthb-prog{color:#8FC1F2;margin-top:5px;min-height:14px}'
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
    + '<div id="hthb-ai"><b>Optional open source AI</b> (a small model, Qwen2.5 0.5B, that runs in your browser via WebLLM; '
    + 'needs WebGPU, built into current desktop Chrome and Edge and the newest Safari). '
    + 'One-time download of about 400 MB; nothing is sent to a server. The helper already works without it, straight from the site index.'
    + '<br><button id="hthb-ai-btn" type="button">Enable open source AI</button>'
    + '<button id="hthb-ai-cancel" type="button" style="display:none">Cancel</button>'
    + '<div class="hthb-prog" id="hthb-ai-prog"></div></div>'
    + '<form id="hthb-form"><input id="hthb-in" type="text" autocomplete="off" placeholder="Ask where something is…">'
    + '<button id="hthb-send" type="submit">Ask</button></form>';
  document.body.appendChild(panel);

  var msgs = panel.querySelector('#hthb-msgs');
  var input = panel.querySelector('#hthb-in');
  var aiProg = panel.querySelector('#hthb-ai-prog');
  var aiBtn = panel.querySelector('#hthb-ai-btn');
  var aiCancel = panel.querySelector('#hthb-ai-cancel');

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

  // ------------------------------------------------------------ WebLLM engine state
  // `engine` is a WebWorkerMLCEngine proxy; the real engine lives in
  // ht-llm-worker.js. Anything thrown or rejected on that side is
  // contained here: the worst case is losing AI phrasing, never the page.
  var engine = null, engineBusy = false, engineLabel = '';
  function askLLM(q, hits, bubble) {
    if (!engine || engineBusy) return;
    engineBusy = true;
    var settled = false;
    var timer = setTimeout(function () { // a dead worker must not wedge later asks
      if (!settled) { settled = true; engineBusy = false; }
    }, 45000);
    function finish() {
      if (!settled) { settled = true; clearTimeout(timer); engineBusy = false; }
    }
    var ctx = hits.map(function (e) {
      return { title: e.title, text: e.text, page: e.url || 'this page' };
    });
    var messages = [
      { role: 'system', content: 'You are the HydroTwin helper bot. Answer ONLY from the site index entries given in the user message; never invent pages, panels or stations. Keep the answer to 2 or 3 short sentences, name the page and the panel or control, and be concrete. If the entries do not cover the question, say what you could not find and what you can locate instead.' },
      { role: 'user', content: 'Question: ' + q + '\n\nSite index entries:\n' + JSON.stringify(ctx, null, 1) },
    ];
    try {
      engine.chat.completions.create({ messages: messages, temperature: 0.2, max_tokens: 220 })
        .then(function (res) {
          if (settled) return;
          var txt = res && res.choices && res.choices[0] && res.choices[0].message
            ? String(res.choices[0].message.content || '').trim() : '';
          if (txt) bubble.textContent = txt + '\n\n(from the site index, via the in-browser ' + engineLabel + ' model)';
        })
        .catch(function () { /* keep the index answer already shown */ })
        .finally(finish);
    } catch (e) { finish(); /* keep the index answer already shown */ }
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
    var bubble = addMsg(fallbackAnswer(q, hits), 'a');
    hits.slice(0, 2).forEach(function (e) {
      var b = document.createElement('button');
      b.className = 'hthb-act'; b.type = 'button';
      b.textContent = 'Show me: ' + e.title;
      b.addEventListener('click', function () { showMe(e); });
      bubble.appendChild(document.createElement('br'));
      bubble.appendChild(b);
    });
    msgs.scrollTop = msgs.scrollHeight;
    if (engine && hits.length) askLLM(q, hits, bubble);
  }

  // ------------------------------------------------------------ WebLLM loading (opt-in, crash-isolated)
  var llmLoading = false;   // a load attempt is in flight
  var llmDead = false;      // latched off for this session (unsupported or failed)
  var llmWorker = null;     // the worker hosting the engine
  var llmWatchdog = null;   // progress watchdog interval id
  var llmLastProgress = 0;  // last init-progress timestamp
  var loadSeq = 0;          // attempt counter; stale attempts may not touch the UI

  // ------------------------------------------------------------ reload detection
  // sessionStorage survives the same-tab reload iOS Safari performs
  // when it kills the web content process, so it can carry the one
  // signal the killed page could not: "a model load was in flight".
  // startLoad() sets the attempt marker (and clears any stale ready
  // flag) just before the download begins; the marker is cleared only
  // when an engine reports fully ready, which also sets the ready
  // flag. Controlled endings (success, failure, unsupported, cancel)
  // all clear it. At boot, a marker with no ready flag therefore
  // means the previous attempt died with the page itself.
  var SS_ATTEMPT = 'ht_llm_attempt', SS_READY = 'ht_llm_ready', SS_BLOCKED = 'ht_llm_blocked';
  function ssGet(k) { try { return sessionStorage.getItem(k); } catch (e) { return null; } }
  function ssSet(k, v) { try { sessionStorage.setItem(k, v); } catch (e) { /* private mode */ } }
  function ssDel(k) { try { sessionStorage.removeItem(k); } catch (e) { /* ignore */ } }
  var INTERRUPTED_MSG = 'It looks like the open source AI load was interrupted because the page reloaded — '
    + 'this device likely cannot hold the model in memory. AI phrasing is off for this visit and nothing '
    + 'will be downloaded. The built in guide still answers everything from the site index.';
  var llmInterruptedFresh = false;
  if (ssGet(SS_ATTEMPT) && !ssGet(SS_READY)) {
    llmInterruptedFresh = true;
    ssSet(SS_BLOCKED, '1');   // keep AI latched off for the rest of this tab session
    ssDel(SS_ATTEMPT);
  }
  if (llmInterruptedFresh || ssGet(SS_BLOCKED)) {
    llmDead = true;
    aiBtn.disabled = true; aiBtn.textContent = 'AI unavailable here';
    aiProg.textContent = INTERRUPTED_MSG;
    window.__htHelperLLM = { ready: false, interrupted: true };
    if (llmInterruptedFresh) addMsg(INTERRUPTED_MSG, 'a'); // say it in the chat too, once
  }

  function shortErr(err) {
    return String((err && err.message) || err || 'unknown error').replace(/\s+/g, ' ').slice(0, 140);
  }
  function killWorker() {
    if (llmWatchdog) { clearInterval(llmWatchdog); llmWatchdog = null; }
    if (llmWorker) { try { llmWorker.terminate(); } catch (e) { /* already gone */ } llmWorker = null; }
  }
  function dropEngine(note) { // engine died after a successful load
    engine = null; engineBusy = false; engineLabel = '';
    window.__htHelperLLM = { ready: false, error: 'engine stopped' };
    killWorker();
    aiProg.textContent = note;
    aiBtn.disabled = false; aiBtn.textContent = 'Enable open source AI';
  }

  // Preflight: never even offer a download where WebGPU cannot run.
  function webgpuSupport() {
    return new Promise(function (resolve) {
      var done = false;
      function finish(ok, why) { if (!done) { done = true; resolve({ ok: ok, why: why }); } }
      try {
        if (!('gpu' in navigator) || !navigator.gpu || typeof navigator.gpu.requestAdapter !== 'function') {
          finish(false, 'no WebGPU in this browser'); return;
        }
        var to = setTimeout(function () { finish(false, 'WebGPU check timed out'); }, 8000);
        navigator.gpu.requestAdapter().then(function (adapter) {
          clearTimeout(to);
          finish(!!adapter, adapter ? '' : 'no WebGPU adapter available');
        }).catch(function (e) { clearTimeout(to); finish(false, shortErr(e)); });
      } catch (e) { finish(false, shortErr(e)); }
    });
  }

  // One load attempt for one model, fully inside a fresh worker.
  // Resolves with the engine proxy; rejects on ANY failure (download,
  // compile, OOM, worker error, 90 s progress stall, cancel).
  function loadModel(mlc, model, seq) {
    return new Promise(function (resolve, reject) {
      var settled = false;
      function ok(v) { if (!settled) { settled = true; if (llmWatchdog) { clearInterval(llmWatchdog); llmWatchdog = null; } resolve(v); } }
      function bad(e) { if (!settled) { settled = true; killWorker(); reject(e); } }
      try {
        llmWorker = new Worker(WORKER_URL, { type: 'module' });
      } catch (e) { bad(e); return; }
      llmWorker.onerror = function (ev) {
        bad(new Error('AI worker error' + (ev && ev.message ? ': ' + ev.message : '')));
      };
      llmLastProgress = Date.now();
      llmWatchdog = setInterval(function () {
        if (seq !== loadSeq) { bad(new Error('cancelled')); return; }
        if (Date.now() - llmLastProgress > 90000) bad(new Error('loading stalled (no progress for 90 seconds)'));
      }, 1000);
      var pending;
      try {
        pending = mlc.CreateWebWorkerMLCEngine(llmWorker, model.id, {
          initProgressCallback: function (p) {
            if (seq !== loadSeq) return;
            llmLastProgress = Date.now();
            var pct = (p && typeof p.progress === 'number') ? ' (' + Math.round(p.progress * 100) + '%)' : '';
            aiProg.textContent = 'Loading ' + model.label + ': ' + (p && p.text ? p.text : 'working…') + pct;
          },
        }, { context_window_size: 1024 }); // short context: far less memory than the model default
      } catch (e) { bad(e); return; }
      Promise.resolve(pending).then(function (eng) {
        if (seq !== loadSeq) { bad(new Error('cancelled')); return; }
        // From here on, a worker death only costs AI phrasing.
        if (llmWorker) llmWorker.onerror = function () {
          dropEngine('The AI worker stopped, so AI phrasing is off. The guide keeps answering from the site index.');
        };
        ok(eng);
      }, bad);
    });
  }

  function aiUnsupported(why) {
    ssDel(SS_ATTEMPT); // controlled ending: never report this as an interrupted load
    llmDead = true; llmLoading = false;
    aiCancel.style.display = 'none';
    aiBtn.disabled = true; aiBtn.textContent = 'AI not available in this browser';
    aiProg.textContent = 'This browser cannot run the on-device AI model (' + why + '). It needs WebGPU, '
      + 'built into current desktop Chrome and Edge and the newest Safari. Nothing was downloaded, and the '
      + 'helper keeps answering everything from the built-in site index.';
    window.__htHelperLLM = { ready: false, unsupported: true, error: why };
  }
  function aiFailed(detail) {
    ssDel(SS_ATTEMPT); // controlled ending: never report this as an interrupted load
    llmDead = true; llmLoading = false;
    killWorker();
    aiCancel.style.display = 'none';
    aiBtn.disabled = true; aiBtn.textContent = 'AI unavailable here';
    aiProg.textContent = 'The on-device AI model could not run in this browser' + (detail ? ' (' + detail + ')' : '')
      + ', so AI phrasing is off for this visit. The helper keeps answering everything from the built-in site index.';
    window.__htHelperLLM = { ready: false, error: detail || 'load failed' };
  }

  function startLoad() {
    var seq = ++loadSeq;
    llmLoading = true;
    aiBtn.disabled = true; aiBtn.textContent = 'Loading…';
    aiCancel.style.display = '';
    aiProg.textContent = 'Checking whether this browser can run the on-device model…';
    webgpuSupport().then(function (sup) {
      if (seq !== loadSeq) return; // cancelled meanwhile
      if (!sup.ok) { aiUnsupported(sup.why); return null; }
      // The load is now committed: mark the attempt so that if the OS
      // kills this page mid-load, the reloaded page can say what
      // happened instead of failing silently. A new attempt also
      // supersedes any ready flag left by an earlier page view.
      ssSet(SS_ATTEMPT, String(Date.now())); ssDel(SS_READY);
      aiProg.textContent = 'Downloading the AI library…';
      return import(WEBLLM_URL);
    }).then(function (mlc) {
      if (!mlc || seq !== loadSeq) return null;
      var chain = Promise.resolve();
      var lastErr = null;
      MODELS.forEach(function (model, i) {
        chain = chain.then(function () {
          if (engine || seq !== loadSeq) return null;
          if (i > 0) aiProg.textContent = 'The standard model could not start here (' + shortErr(lastErr) + '). Trying the smaller ' + model.label + ' model (' + model.size + ')…';
          else aiProg.textContent = 'Downloading the open source model ' + model.label + ' (one time, ' + model.size + ')…';
          return loadModel(mlc, model, seq).then(function (eng) {
            if (seq !== loadSeq) return;
            engine = eng; engineLabel = model.label;
            ssDel(SS_ATTEMPT); ssSet(SS_READY, model.id); // fully ready: the only clean exit for the marker
            window.__htHelperLLM = { ready: true, model: model.id };
            llmLoading = false;
            aiCancel.style.display = 'none';
            aiBtn.disabled = true; aiBtn.textContent = 'AI on';
            aiProg.textContent = 'Open source AI is on (' + model.label + ', in your browser; it runs in a background worker, separate from the page). Answers still come from the site index.';
            try { localStorage.setItem('htHelperLLM', '1'); } catch (e) { /* private mode */ }
          }).catch(function (err) { lastErr = err; });
        });
      });
      return chain.then(function () {
        if (seq !== loadSeq || engine) return;
        aiFailed(shortErr(lastErr));
      });
    }).catch(function (err) {
      if (seq !== loadSeq) return;
      aiFailed(shortErr(err));
    });
  }

  aiBtn.addEventListener('click', function () {
    try {
      if (engine) { aiProg.textContent = 'Open source AI is already on.'; return; }
      if (llmLoading || llmDead) return;
      startLoad();
    } catch (e) { aiFailed(shortErr(e)); }
  });
  aiCancel.addEventListener('click', function () {
    if (!llmLoading) return;
    loadSeq++; // invalidate the in-flight attempt; its late callbacks become no-ops
    ssDel(SS_ATTEMPT); // controlled ending: never report this as an interrupted load
    llmLoading = false;
    killWorker();
    aiCancel.style.display = 'none';
    aiBtn.disabled = false; aiBtn.textContent = 'Enable open source AI';
    aiProg.textContent = 'Download cancelled. Nothing was installed; the helper keeps answering from the site index.';
  });
  try {
    if (!llmDead && localStorage.getItem('htHelperLLM') === '1') {
      aiProg.textContent = 'You enabled the open source AI before; its files are already downloaded, so enabling is quick.';
    }
  } catch (e) { /* ignore */ }

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
