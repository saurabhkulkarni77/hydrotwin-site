/**
 * HydroTwin Data-view host for the 3D river chart. Adapted from the
 * standalone app.mjs for embedding in the
 * classic statistics pages: one station per page (the dataset comes from
 * the page's own chart3d/<site>.json sidecar), all element lookups are
 * scoped to the section root, and initialisation is deferred until the
 * section is scrolled into view so the Three.js bundle is only fetched
 * on demand. The chart code itself (graph.mjs, graph-data.mjs, data.mjs,
 * labels.mjs) is unmodified.
 */
import * as THREE from 'three';
import { OrbitControls } from './OrbitControls.js';
import { createGraph } from './graph.mjs';
import { graphVariables } from './graph-data.mjs';
import { dateAt, indexAt, getComparison } from './data.mjs';

// Model full forms for the model selector labels (ht-fullforms v1):
// display text only -- option values stay the model indexes.
const MODEL_FULL = {
  'ARIMA': 'Autoregressive Integrated Moving Average',
  'SARIMA': 'Seasonal Autoregressive Integrated Moving Average',
  'GP Matérn': 'Gaussian Process (Matérn kernel)',
  'GP RBF': 'Gaussian Process (Radial Basis Function kernel)',
  'LSTM': 'Long Short-Term Memory network',
  'Transformer': 'Transformer (self-attention neural network)',
  'TFT': 'Temporal Fusion Transformer',
  'PatchTST': 'Patch Time-Series Transformer',
  'GCN': 'Graph Convolutional Network',
  'PILSTMv1': 'Physics-Informed LSTM, version 1',
};

export function mount(root) {
  const el = (cls) => root.querySelector('.' + cls);
  const canvas = el('ht3dc-canvas');
  const loading = el('ht3dc-loading');
  const scene = new THREE.Scene();
  scene.background = new THREE.Color('#dbe7e9');
  const camera = new THREE.PerspectiveCamera(48, 1, 0.01, 80);
  const renderer = new THREE.WebGLRenderer({ canvas, antialias: true });
  renderer.setPixelRatio(Math.min(devicePixelRatio, 2));
  renderer.outputColorSpace = THREE.SRGBColorSpace;
  renderer.toneMapping = THREE.ACESFilmicToneMapping;
  renderer.toneMappingExposure = 1.25;
  const orbit = new OrbitControls(camera, canvas);
  orbit.enableDamping = true;
  orbit.minDistance = 2.2;
  orbit.maxDistance = 14;
  orbit.maxPolarAngle = Math.PI * 0.49;

  let dataset;
  let graph;
  const selection = { issueIndex: 0, modelIndex: 0, lead: 4 };
  const format = (value, digits = 2) => value == null
    ? 'Unavailable'
    : value.toLocaleString('en-US', { maximumFractionDigits: digits });

  function resetCamera() {
    camera.position.set(3.1, 2.7, 3.5);
    orbit.target.set(0.05, 1.48, -0.2);
    orbit.update();
  }

  function refresh() {
    if (!dataset || !graph) return;
    selection.issueIndex = Math.max(0, Math.min(
      dataset.n - 1 - selection.lead, selection.issueIndex,
    ));
    const dateInput = el('ht3dc-date');
    dateInput.min = dataset.start;
    dateInput.max = dateAt(dataset, dataset.n - 1 - selection.lead);
    dateInput.value = dateAt(dataset, selection.issueIndex);
    const result = graph.update(selection);
    const comparison = getComparison(dataset, selection);
    el('ht3dc-target').textContent = comparison.targetDate;
    el('ht3dc-pred-flow').textContent = format(comparison.predictedCfs, 0) + ' cfs';
    el('ht3dc-obs-flow').textContent = format(comparison.observedCfs, 0) + ' cfs';
    el('ht3dc-pred-h').textContent = format(comparison.predictedStageFt) + ' ft';
    el('ht3dc-obs-h').textContent = format(comparison.observedEstimatedStageFt) + ' ft';
    el('ht3dc-input-name').textContent = result.variable.title + ' at issue date';
    el('ht3dc-input-value').textContent = format(result.sample?.input) + ' ' + result.variable.unit;
    el('ht3dc-window').textContent = result.count + ' forecast points in ' +
      (result.end - result.start + 1) + ' issue days. Both curves use the selected lead.';
  }

  function populateVariables() {
    const previous = graph?.getVariable() ?? 'rain7';
    const selector = el('ht3dc-variable');
    selector.replaceChildren();
    for (const [key, definition] of Object.entries(graphVariables)) {
      let title = definition.title;
      if (key.startsWith('snow')) {
        const sensorIndex = key === 'snow' ? 0 : Number(key.slice(4)) - 1;
        const sensor = dataset.nrcs.snowStations[sensorIndex];
        if (!sensor && sensorIndex > 0) continue;
        title = sensor ? 'Snow SWE · ' + sensor : 'Snow SWE · unavailable here';
      }
      // The 25-year NRCS fetch carries no SMS:-20 series; an option that
      // can never draw anything is omitted for stations without the data.
      if (key === 'soil20' && dataset.nrcs.soil20.every((v) => v == null)) continue;
      selector.add(new Option(title + ' (' + definition.unit + ')', key));
    }
    selector.value = [...selector.options].some((option) => option.value === previous)
      ? previous : 'rain7';
  }

  async function load() {
    loading.hidden = false;
    loading.textContent = 'Loading the chart data…';
    try {
      const site = root.dataset.site;
      const response = await fetch('../chart3d/' + site + '.json');
      if (!response.ok) throw new Error('Data file unavailable: ' + site);
      dataset = await response.json();
      el('ht3dc-station-name').textContent = dataset.station.name;
      el('ht3dc-model').replaceChildren(...dataset.models.map((name, index) =>
        new Option(MODEL_FULL[name] ? name + ' — ' + MODEL_FULL[name] : name, index),
      ));
      el('ht3dc-model').value = String(selection.modelIndex);
      // Default view: the most recent 90 issue days of the record.
      selection.issueIndex = dataset.n - 1 - selection.lead - 44;
      populateVariables();
      graph = createGraph(dataset, (issueIndex) => {
        selection.issueIndex = issueIndex;
        refresh();
      });
      graph.setVariable(el('ht3dc-variable').value);
      scene.add(graph.group);
      refresh();
      resetCamera();
      loading.hidden = true;
      window.HT3DC = { ready: true, dataset, graph, selection };
    } catch (error) {
      loading.textContent = '3D chart unavailable: ' + error.message;
      console.error(error);
    }
  }

  for (let lead = 1; lead <= 7; lead++) el('ht3dc-lead').add(new Option('+' + lead, lead));
  el('ht3dc-lead').value = String(selection.lead);
  el('ht3dc-form').addEventListener('submit', (event) => event.preventDefault());
  el('ht3dc-model').addEventListener('change', (event) => {
    selection.modelIndex = Number(event.target.value);
    refresh();
  });
  el('ht3dc-lead').addEventListener('change', (event) => {
    selection.lead = Number(event.target.value);
    refresh();
  });
  el('ht3dc-date').addEventListener('change', (event) => {
    const index = indexAt(dataset, event.target.value);
    if (Number.isFinite(index)) selection.issueIndex = index;
    refresh();
  });
  el('ht3dc-variable').addEventListener('change', (event) => {
    graph.setVariable(event.target.value);
    refresh();
  });
  el('ht3dc-reset').addEventListener('click', resetCamera);

  // Raycast only forecast dots. Ignore a drag so orbiting never selects a point.
  const raycaster = new THREE.Raycaster();
  const pointer = new THREE.Vector2();
  let pointerDown;
  canvas.addEventListener('pointerdown', (event) => {
    pointerDown = { x: event.clientX, y: event.clientY };
  });
  canvas.addEventListener('pointerup', (event) => {
    if (!graph || !pointerDown) return;
    const moved = Math.hypot(event.clientX - pointerDown.x, event.clientY - pointerDown.y);
    pointerDown = null;
    if (moved > 5) return;
    const bounds = canvas.getBoundingClientRect();
    pointer.set(
      (event.clientX - bounds.left) / bounds.width * 2 - 1,
      -(event.clientY - bounds.top) / bounds.height * 2 + 1,
    );
    raycaster.setFromCamera(pointer, camera);
    const hit = raycaster.intersectObjects(graph.getTargets())[0];
    if (hit) graph.select(hit.object);
  });
  canvas.addEventListener('pointercancel', () => { pointerDown = null; });

  new ResizeObserver(() => {
    const { width, height } = el('ht3dc-viewport').getBoundingClientRect();
    if (!width || !height) return;
    renderer.setSize(width, height, false);
    camera.aspect = width / height;
    camera.updateProjectionMatrix();
  }).observe(el('ht3dc-viewport'));

  renderer.setAnimationLoop(() => {
    orbit.update();
    graph?.faceLabels(camera);
    renderer.render(scene, camera);
  });

  return load();
}
