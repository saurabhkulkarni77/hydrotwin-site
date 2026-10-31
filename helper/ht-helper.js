/* ht-helperbot v1 — HydroTwin helper bot.
 *
 * A chat widget (bottom right) that answers "where is X / how do I Y"
 * questions about the digital twin. Location answers come from the
 * generated site index (helper/ht-index.json): retrieval over that
 * index always runs first and its entries drive the answer text and
 * the "Show me" actions. An optional in-browser OPEN SOURCE LLM
 * (WebLLM, Llama 3.2 1B Instruct) can rephrase the answer, grounded on
 * the same retrieved entries passed as context; it is strictly opt-in
 * (a one-time ~1 GB model download starts only when the visitor
 * presses the enable button) and any failure or slowness falls back
 * to the direct index answer, which is shown immediately regardless.
 */
(function () {
  'use strict';
  if (window.__htHelperBot) return;
  window.__htHelperBot = true;

  var scriptEl = document.currentScript || document.querySelector('script[src*="ht-helper.js"]');
  var base = scriptEl ? new URL('.', scriptEl.src).href : '../helper/';
  var rootUrl = new URL('..', base).href; // site root ('' from stations/, './' from home)
  var MODEL_ID = 'Llama-3.2-1B-Instruct-q4f16_1-MLC';
  var WEBLLM_URL = 'https://cdn.jsdelivr.net/npm/@mlc-ai/web-llm@0.2.79/+esm';

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
    + '<div id="hthb-ai"><b>Optional open source AI</b> (Llama 3.2 1B, runs in your browser via WebLLM). '
    + 'One-time download of about 1 GB; nothing is sent to a server. The helper already works without it, straight from the site index.'
    + '<br><button id="hthb-ai-btn" type="button">Enable open source AI</button>'
    + '<div class="hthb-prog" id="hthb-ai-prog"></div></div>'
    + '<form id="hthb-form"><input id="hthb-in" type="text" autocomplete="off" placeholder="Ask where something is…">'
    + '<button id="hthb-send" type="submit">Ask</button></form>';
  document.body.appendChild(panel);

  var msgs = panel.querySelector('#hthb-msgs');
  var input = panel.querySelector('#hthb-in');
  var aiProg = panel.querySelector('#hthb-ai-prog');
  var aiBtn = panel.querySelector('#hthb-ai-btn');

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

  var engine = null, engineBusy = false;
  function askLLM(q, hits, bubble) {
    if (!engine || engineBusy) return;
    engineBusy = true;
    var ctx = hits.map(function (e) {
      return { title: e.title, text: e.text, page: e.url || 'this page' };
    });
    var messages = [
      { role: 'system', content: 'You are the HydroTwin helper bot. Answer ONLY from the site index entries given in the user message; never invent pages, panels or stations. Keep the answer to 2 or 3 short sentences, name the page and the panel or control, and be concrete. If the entries do not cover the question, say what you could not find and what you can locate instead.' },
      { role: 'user', content: 'Question: ' + q + '\n\nSite index entries:\n' + JSON.stringify(ctx, null, 1) },
    ];
    engine.chat.completions.create({ messages: messages, temperature: 0.2, max_tokens: 220 })
      .then(function (res) {
        var txt = res && res.choices && res.choices[0] && res.choices[0].message
          ? String(res.choices[0].message.content || '').trim() : '';
        if (txt) bubble.textContent = txt + '\n\n(from the site index, via the in-browser Llama 3.2 1B model)';
      })
      .catch(function () { /* keep the index answer already shown */ })
      .finally(function () { engineBusy = false; });
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

  // ------------------------------------------------------------ WebLLM (opt-in)
  aiBtn.addEventListener('click', function () {
    if (engine) { aiProg.textContent = 'Open source AI is already on.'; return; }
    aiBtn.disabled = true;
    aiProg.textContent = 'Downloading the open source model (one time, about 1 GB)…';
    import(WEBLLM_URL).then(function (mlc) {
      return mlc.CreateMLCEngine(MODEL_ID, {
        initProgressCallback: function (p) {
          aiProg.textContent = 'Loading model: ' + (p && p.text ? p.text : 'working…');
        },
      });
    }).then(function (eng) {
      engine = eng;
      window.__htHelperLLM = { ready: true, model: MODEL_ID };
      aiProg.textContent = 'Open source AI is on (Llama 3.2 1B, in your browser). Answers still come from the site index.';
      aiBtn.textContent = 'AI on';
      try { localStorage.setItem('htHelperLLM', '1'); } catch (e) { /* private mode */ }
    }).catch(function (err) {
      window.__htHelperLLM = { ready: false, error: String(err && err.message || err) };
      aiProg.textContent = 'The model could not load here (' + String(err && err.message || err).slice(0, 120) + '). The helper keeps working from the site index.';
      aiBtn.disabled = false;
    });
  });
  try {
    if (localStorage.getItem('htHelperLLM') === '1') {
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
