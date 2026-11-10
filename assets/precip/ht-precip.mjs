/* ht-precip v1 — rain / snow animation driven by the selected date.
 *
 * On a 3D station page, the day chosen in the page's Date field is
 * looked up in the Open-Meteo archive for the station's coordinates:
 * if the day recorded snowfall, animated snow falls in the scene; if
 * it recorded rain, animated rain; intensity (particle count, fall
 * speed, opacity) scales with the recorded amount. Dry days show no
 * particles. Any fetch failure degrades quietly (no particles, no
 * visible error). State is exposed on window.__htPrecip for checks.
 */
import * as THREE from 'three';

const MAX = 2600;
const state = { status: 'init', date: null, kind: null, amount: null, unit: null, count: 0 };
window.__htPrecip = state;

function isoOfDay(dayIdx) {
  const D = window.HT3D;
  const t0 = Date.parse((D.start || '2001-10-01') + 'T00:00:00Z');
  return new Date(t0 + dayIdx * 864e5).toISOString().slice(0, 10);
}

async function waitForHT3() {
  for (let i = 0; i < 240; i++) {
    if (window.HT3_READY && window.HT3 && window.HT3.scene && window.HT3D) return window.HT3;
    await new Promise((r) => setTimeout(r, 250));
  }
  return null;
}

const HT3 = await waitForHT3();
if (!HT3) { state.status = 'no-scene'; throw new Error('ht-precip: scene unavailable'); }

const scene = HT3.scene;
const geo = new THREE.BufferGeometry();
const pos = new Float32Array(MAX * 3);
geo.setAttribute('position', new THREE.BufferAttribute(pos, 3));
geo.setDrawRange(0, 0);
const mat = new THREE.PointsMaterial({
  color: 0x9fc8ee, size: 2, sizeAttenuation: false,
  transparent: true, opacity: 0, depthWrite: false,
});
const points = new THREE.Points(geo, mat);
points.frustumCulled = false;
points.renderOrder = 5;
points.visible = false;
points.name = 'htPrecip';
scene.add(points);

const badge = document.createElement('div');
badge.id = 'ht-precip-badge';
badge.style.cssText = 'position:fixed;left:14px;top:148px;z-index:29;display:none;'
  + 'padding:6px 11px;border-radius:999px;background:rgba(12,18,28,.88);color:#CFE6FF;'
  + 'font:600 12.5px Arial;box-shadow:0 2px 10px rgba(0,0,0,.4)';
document.body.appendChild(badge);

const seeds = new Float32Array(MAX * 2);
for (let i = 0; i < MAX; i++) { seeds[2 * i] = Math.random(); seeds[2 * i + 1] = Math.random(); }

let active = null; // {kind, count, speed, top, cx, cz, cy}
function layout(kind, count) {
  const t = (HT3.orbit && HT3.orbit.target) || { x: 0, y: 0, z: 0 };
  const W = 1300, H = 520;
  for (let i = 0; i < count; i++) {
    pos[3 * i] = t.x + (seeds[2 * i] - 0.5) * W;
    pos[3 * i + 1] = t.y + seeds[2 * i + 1] * H;
    pos[3 * i + 2] = t.z + (seeds[2 * i + 1] - 0.5) * W;
  }
  geo.attributes.position.needsUpdate = true;
  geo.setDrawRange(0, count);
  active = {
    kind, count, cx: t.x, cz: t.z, cy: t.y, H,
    speed: kind === 'snow' ? 26 : 250,
  };
  mat.color.set(kind === 'snow' ? 0xffffff : 0x9fc8ee);
  mat.size = kind === 'snow' ? 3.4 : 2;
  mat.opacity = kind === 'snow' ? 0.95 : 0.75;
  points.visible = true;
}

function stop() {
  active = null;
  points.visible = false;
  geo.setDrawRange(0, 0);
  badge.style.display = 'none';
}

const cache = new Map();
async function weatherFor(dateIso) {
  if (cache.has(dateIso)) return cache.get(dateIso);
  const D = window.HT3D;
  const url = 'https://archive-api.open-meteo.com/v1/archive'
    + '?latitude=' + encodeURIComponent(D.lat) + '&longitude=' + encodeURIComponent(D.lon)
    + '&start_date=' + dateIso + '&end_date=' + dateIso
    + '&daily=precipitation_sum,rain_sum,snowfall_sum&timezone=UTC';
  const ac = new AbortController();
  const to = setTimeout(() => ac.abort(), 9000);
  try {
    const r = await fetch(url, { signal: ac.signal });
    if (!r.ok) throw new Error('archive ' + r.status);
    const j = await r.json();
    const d = (j && j.daily) || {};
    const out = {
      precip: d.precipitation_sum ? d.precipitation_sum[0] : null,
      rain: d.rain_sum ? d.rain_sum[0] : null,
      snow: d.snowfall_sum ? d.snowfall_sum[0] : null, // cm
    };
    cache.set(dateIso, out);
    return out;
  } finally { clearTimeout(to); }
}

let seq = 0;
async function applyDate(dateIso) {
  const my = ++seq;
  state.date = dateIso; state.status = 'loading'; state.kind = null; state.count = 0;
  if (!dateIso || dateIso < '2001-10-01' || dateIso > '2026-09-30') { stop(); state.status = 'out-of-range'; return; }
  let w;
  try { w = await weatherFor(dateIso); } catch (e) {
    if (my === seq) { stop(); state.status = 'unavailable'; }
    return;
  }
  if (my !== seq) return; // a newer date superseded this fetch
  const snow = w.snow || 0, rain = (w.rain != null ? w.rain : (w.precip || 0));
  if (snow > 0) {
    const count = Math.max(90, Math.min(MAX, Math.round(snow * 170)));
    layout('snow', count);
    state.kind = 'snow'; state.amount = snow; state.unit = 'cm'; state.count = count; state.status = 'active';
    badge.textContent = '❄ Snow · ' + snow.toFixed(1) + ' cm · ' + dateIso + ' (Open-Meteo)';
    badge.style.display = 'block';
  } else if (rain > 0) {
    const count = Math.max(70, Math.min(MAX, Math.round(rain * 130)));
    layout('rain', count);
    state.kind = 'rain'; state.amount = rain; state.unit = 'mm'; state.count = count; state.status = 'active';
    badge.textContent = '🌧 Rain · ' + rain.toFixed(1) + ' mm · ' + dateIso + ' (Open-Meteo)';
    badge.style.display = 'block';
  } else {
    stop();
    state.kind = null; state.amount = 0; state.count = 0; state.status = 'dry';
  }
}

function currentDateIso() {
  const el = document.getElementById('ht-date');
  if (el && el.value) return el.value;
  const S2 = window.__htS;
  return S2 ? isoOfDay(S2.day) : null;
}

let lastDate = null;
function tick() {
  const d = currentDateIso();
  if (d && d !== lastDate) { lastDate = d; applyDate(d); }
}
const dateEl = document.getElementById('ht-date');
if (dateEl) dateEl.addEventListener('change', tick);
setInterval(tick, 800);
tick();

// animation loop (the scene itself is drawn by the page's own loop)
let prev = performance.now();
function animate(now) {
  requestAnimationFrame(animate);
  const dt = Math.min(0.05, (now - prev) / 1000); prev = now;
  const S2 = window.__htS;
  if (!active || (S2 && S2.mode !== 'ground')) { if (points.visible && S2 && S2.mode !== 'ground') points.visible = false; return; }
  if (!points.visible) points.visible = true;
  const fall = active.speed * dt;
  const sway = active.kind === 'snow' ? Math.sin(now / 700) * 14 * dt : 0;
  for (let i = 0; i < active.count; i++) {
    let y = pos[3 * i + 1] - fall * (0.7 + seeds[2 * i] * 0.6);
    if (y < active.cy - 30) y = active.cy + active.H;
    pos[3 * i + 1] = y;
    if (sway) pos[3 * i] += sway;
  }
  geo.attributes.position.needsUpdate = true;
}
requestAnimationFrame(animate);
state.status = 'ready';
