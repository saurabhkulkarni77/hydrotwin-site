/* ht-charts3d v1 — the Data view's hydrograph and "Features affecting
 * discharge flow" chart as real 3D charts.
 *
 * Data provenance (no hardcoded values): the hydrograph draws from
 * the page's own window.HT_DATA flow series (the same series the 2D
 * hydrograph uses, last 365 days); the feature bars draw from the
 * same featimp/<site>.json sidecar the 2D feature chart fetches.
 * Hovering a point or a bar shows its exact values in the tooltip.
 */
import * as THREE from '../3dchart/three.module.js';

const SRC_COLORS = { 'USGS': 0x4EA8E0, 'Open-Meteo': 0xE8A33D, 'Soil': 0x7FB069, 'Snow': 0xA8D8EA };

function textSprite(text, opts) {
  const fs = (opts && opts.size) || 44;
  const c = document.createElement('canvas');
  const g0 = c.getContext('2d');
  g0.font = '600 ' + fs + 'px Arial';
  const w = Math.ceil(g0.measureText(text).width) + 24;
  c.width = w; c.height = fs + 26;
  const g = c.getContext('2d');
  g.font = '600 ' + fs + 'px Arial';
  g.fillStyle = (opts && opts.color) || '#DCE8F5';
  g.textBaseline = 'middle';
  g.fillText(text, 12, c.height / 2);
  const tex = new THREE.CanvasTexture(c);
  tex.colorSpace = THREE.SRGBColorSpace;
  const sp = new THREE.Sprite(new THREE.SpriteMaterial({ map: tex, transparent: true, depthTest: false }));
  const scale = (opts && opts.scale) || 0.0035;
  sp.scale.set(c.width * scale, c.height * scale, 1);
  return sp;
}

export function mount(root) {
  const canvas = root.querySelector('.htc3-canvas');
  const tip = root.querySelector('.htc3-tip');
  const loading = root.querySelector('.htc3-loading');
  const D = window.HT_DATA;
  const site = root.dataset.site;

  const renderer = new THREE.WebGLRenderer({ canvas, antialias: true });
  renderer.setPixelRatio(Math.min(devicePixelRatio, 2));
  renderer.outputColorSpace = THREE.SRGBColorSpace;
  const scene = new THREE.Scene();
  scene.background = new THREE.Color(0x0e1a24);
  scene.add(new THREE.HemisphereLight(0xdce8f5, 0x33404f, 1.1));
  const sun = new THREE.DirectionalLight(0xfff4e0, 2.2);
  sun.position.set(4, 8, 5);
  scene.add(sun);
  const camera = new THREE.PerspectiveCamera(46, 1, 0.1, 200);

  // simple orbit: drag to rotate, wheel to zoom
  const target = new THREE.Vector3(0, 1.6, 0);
  let theta = 0.65, phi = 1.02, radius = 13;
  function placeCam() {
    camera.position.set(
      target.x + radius * Math.sin(phi) * Math.sin(theta),
      target.y + radius * Math.cos(phi),
      target.z + radius * Math.sin(phi) * Math.cos(theta));
    camera.lookAt(target);
  }
  let drag = null;
  canvas.addEventListener('pointerdown', (e) => { drag = { x: e.clientX, y: e.clientY }; canvas.setPointerCapture(e.pointerId); });
  canvas.addEventListener('pointermove', (e) => {
    if (!drag) return;
    theta -= (e.clientX - drag.x) * 0.008;
    phi = Math.max(0.15, Math.min(1.45, phi - (e.clientY - drag.y) * 0.008));
    drag = { x: e.clientX, y: e.clientY };
    placeCam();
  });
  canvas.addEventListener('pointerup', () => { drag = null; });
  canvas.addEventListener('wheel', (e) => {
    e.preventDefault();
    radius = Math.max(5, Math.min(30, radius * (e.deltaY > 0 ? 1.1 : 0.9)));
    placeCam();
  }, { passive: false });

  const grid = new THREE.GridHelper(10, 10, 0x2a4258, 0x1c3049);
  grid.position.y = 0; scene.add(grid);

  const hydroGroup = new THREE.Group(); scene.add(hydroGroup);
  const featGroup = new THREE.Group(); scene.add(featGroup);
  const pickables = [];

  // ------------------------------------------------ hydrograph (last 365 days of the page's own series)
  const flow = D.flow || [];
  const n = flow.length;
  const DAY = 365;
  const i0 = Math.max(0, n - DAY);
  const pts = [];
  let lo = Infinity, hi = -Infinity;
  for (let i = i0; i < n; i++) {
    const v = flow[i];
    if (v != null && v > 0) { lo = Math.min(lo, Math.log10(v)); hi = Math.max(hi, Math.log10(v)); }
  }
  if (hi <= lo) { hi = lo + 1; }
  const dateOf = (i) => new Date(Date.parse(D.start + 'T00:00:00Z') + i * 864e5).toISOString().slice(0, 10);
  for (let k = 0; k <= n - 1 - i0; k++) {
    const i = i0 + k, v = flow[i];
    if (v == null || !(v > 0)) continue;
    const x = -5 + 10 * (k / Math.max(1, DAY - 1));
    const y = 0.05 + 3.4 * (Math.log10(v) - lo) / (hi - lo);
    pts.push({ x, y, i, v });
  }
  if (pts.length > 1) {
    const lineGeo = new THREE.BufferGeometry().setFromPoints(pts.map((p) => new THREE.Vector3(p.x, p.y, 0)));
    hydroGroup.add(new THREE.Line(lineGeo, new THREE.LineBasicMaterial({ color: 0x4ea8e0 })));
    // translucent ribbon under the line
    const rp = [], ridx = [];
    pts.forEach((p, k) => {
      rp.push(p.x, p.y, 0, p.x, 0, 0);
      if (k) { const a = 2 * (k - 1); ridx.push(a, a + 1, a + 2, a + 1, a + 3, a + 2); }
    });
    const rg = new THREE.BufferGeometry();
    rg.setAttribute('position', new THREE.Float32BufferAttribute(rp, 3));
    rg.setIndex(ridx); rg.computeVertexNormals();
    const ribbon = new THREE.Mesh(rg, new THREE.MeshBasicMaterial({
      color: 0x2f80d1, transparent: true, opacity: 0.28, side: THREE.DoubleSide, depthWrite: false }));
    hydroGroup.add(ribbon);
    // hover targets (one per week)
    const dotGeo = new THREE.SphereGeometry(0.075, 10, 8);
    pts.forEach((p, k) => {
      if (k % 7 && k !== pts.length - 1) return;
      const m = new THREE.Mesh(dotGeo, new THREE.MeshBasicMaterial({ color: 0xffd24d }));
      m.position.set(p.x, p.y, 0);
      m.userData.tip = dateOf(p.i) + ' · flow ' + Math.round(p.v).toLocaleString('en-US') + ' cfs';
      hydroGroup.add(m); pickables.push(m);
    });
    const t1 = textSprite('Hydrograph — last 365 days, log scale', { scale: 0.0042 });
    t1.position.set(0, 4.1, 0); hydroGroup.add(t1);
    const t2 = textSprite(Math.round(Math.pow(10, hi)).toLocaleString('en-US') + ' cfs', { scale: 0.003 });
    t2.position.set(-5.6, 3.5, 0); hydroGroup.add(t2);
    const t3 = textSprite(Math.round(Math.pow(10, lo)).toLocaleString('en-US') + ' cfs', { scale: 0.003 });
    t3.position.set(-5.6, 0.2, 0); hydroGroup.add(t3);
    const t4 = textSprite(dateOf(i0), { scale: 0.003 }); t4.position.set(-4.6, -0.35, 0); hydroGroup.add(t4);
    const t5 = textSprite(dateOf(n - 1), { scale: 0.003 }); t5.position.set(4.6, -0.35, 0); hydroGroup.add(t5);
  }

  // ------------------------------------------------ feature importance bars (same sidecar as the 2D chart)
  async function loadFeatures() {
    const r = await fetch('../featimp/' + site + '.json');
    if (!r.ok) throw new Error('featimp ' + r.status);
    const d = await r.json();
    const feats = (d.features || []).slice(0, 15);
    const max = Math.max.apply(null, feats.map((f) => f.share).concat([0.0001]));
    const bw = 0.52, gap = 0.66;
    const x0 = -((feats.length - 1) * gap) / 2;
    feats.forEach((f, k) => {
      const h = 0.05 + 3.3 * (f.share / max);
      const col = SRC_COLORS[f.source] || 0x9fb3c8;
      const bar = new THREE.Mesh(
        new THREE.BoxGeometry(bw, h, bw),
        new THREE.MeshStandardMaterial({ color: col, roughness: 0.55, metalness: 0.05 }));
      bar.position.set(x0 + k * gap, h / 2, 0);
      bar.userData.tip = f.name + (f.unit ? ' (' + f.unit + ')' : '') + ' · ' + f.source
        + ' · importance ' + (f.share * 100).toFixed(1) + '% of total gain';
      featGroup.add(bar); pickables.push(bar);
      if (k % 2 === 0) {
        const lab = textSprite(f.name.replace(/^Flow, /, 'Flow '), { scale: 0.0016, size: 40 });
        lab.position.set(x0 + k * gap, -0.3, 0.35);
        featGroup.add(lab);
      }
    });
    const t = textSprite('Features affecting discharge flow — XGBoost gain share', { scale: 0.0042 });
    t.position.set(0, 4.1, 0); featGroup.add(t);
    return d;
  }

  // ------------------------------------------------ modes + hover
  let mode = 'hydro';
  function setMode(m) {
    mode = m;
    hydroGroup.visible = m === 'hydro';
    featGroup.visible = m === 'feat';
    root.querySelectorAll('.htc3-mode').forEach((b) => {
      b.classList.toggle('htc3-on', b.dataset.mode === m);
    });
    window.__htCharts3d = { ready: true, mode, site, hydroPoints: pts.length };
  }
  root.querySelectorAll('.htc3-mode').forEach((b) => {
    b.addEventListener('click', () => setMode(b.dataset.mode));
  });

  const ray = new THREE.Raycaster();
  const ptr = new THREE.Vector2();
  canvas.addEventListener('pointermove', (e) => {
    const r = canvas.getBoundingClientRect();
    ptr.set(((e.clientX - r.left) / r.width) * 2 - 1, -((e.clientY - r.top) / r.height) * 2 + 1);
    ray.setFromCamera(ptr, camera);
    const hits = ray.intersectObjects(pickables.filter((o) => {
      let p = o; while (p) { if (p === hydroGroup) return mode === 'hydro'; if (p === featGroup) return mode === 'feat'; p = p.parent; } return false;
    }));
    if (hits.length) {
      tip.textContent = hits[0].object.userData.tip;
      tip.style.display = 'block';
      tip.style.left = (e.clientX - r.left + 12) + 'px';
      tip.style.top = (e.clientY - r.top + 10) + 'px';
      canvas.style.cursor = 'pointer';
    } else {
      tip.style.display = 'none';
      canvas.style.cursor = 'grab';
    }
  });

  new ResizeObserver(() => {
    const w = canvas.clientWidth || canvas.parentElement.clientWidth;
    const h = canvas.clientHeight || 440;
    if (!w) return;
    renderer.setSize(w, h, false);
    camera.aspect = w / h; camera.updateProjectionMatrix();
  }).observe(canvas);

  placeCam();
  renderer.setAnimationLoop(() => renderer.render(scene, camera));
  setMode('hydro');
  loadFeatures().then(() => { loading.hidden = true; })
    .catch((e) => { loading.textContent = '3D feature chart unavailable: ' + e.message; });
  if (pts.length) loading.hidden = true;
}
