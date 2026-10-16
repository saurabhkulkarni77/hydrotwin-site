/**
 * Reusable Three.js chart. The host owns the camera, renderer, and UI.
 * Add graph.group to a scene, then call update(selection) after state changes.
 */
import * as THREE from 'three';
import { label } from './labels.mjs';
import { graphVariables, graphSamples } from './graph-data.mjs';

const SIZE = { time: 2.8, height: 1.7, depth: 1.65 };
const HISTORY_DAYS = 90;
const DAYS_BEFORE_SELECTION = 44;
const COLORS = {
  axis: '#466a76',
  grid: '#9bb6be',
  observed: '#247e9f',
  predicted: '#d5793d',
  point: '#db7d40',
  selected: '#fff2b0',
};

/** Pad constant series too, so dry periods and flat readings remain visible. */
function paddedExtent(values) {
  const minimum = values.length ? Math.min(...values) : 0;
  const maximum = values.length ? Math.max(...values) : 1;
  const padding = (maximum - minimum || Math.max(1, Math.abs(minimum) * 0.1)) * 0.12;
  return [minimum - padding, maximum + padding];
}

export function createGraph(dataset, onSelect) {
  const group = new THREE.Group();
  const content = new THREE.Group();
  group.add(content);
  // This default places the plot in the Field Lab scene; hosts can move it.
  group.position.set(-1.35, 0.65, 0.55);

  let variable = 'rain7';
  let start = -1;
  let end = -1;
  let cacheKey = '';
  let samples = [];
  let targets = [];
  let labels = [];
  let selectedMarker = null;

  function clearContent() {
    // Points share GPU resources. Dispose each unique resource exactly once.
    const geometries = new Set();
    const materials = new Set();
    const textures = new Set();
    content.traverse((object) => {
      if (object.geometry) geometries.add(object.geometry);
      if (object.material) {
        materials.add(object.material);
        if (object.material.map) textures.add(object.material.map);
      }
    });
    content.clear();
    geometries.forEach((geometry) => geometry.dispose());
    materials.forEach((material) => material.dispose());
    textures.forEach((texture) => texture.dispose());
    labels = [];
    targets = [];
    selectedMarker = null;
  }

  function addText(value, x, y, z, width = 0.9, height = 0.11, color = '#294c58') {
    const mesh = label(value, { width, height, fontSize: 104, color });
    mesh.position.set(x, y, z);
    content.add(mesh);
    labels.push(mesh);
  }

  function addLine(points, color, opacity = 1) {
    if (points.length < 2) return;
    const geometry = new THREE.BufferGeometry().setFromPoints(points);
    const material = new THREE.LineBasicMaterial({
      color,
      transparent: opacity < 1,
      opacity,
    });
    content.add(new THREE.Line(geometry, material));
  }

  function updateWindow(selection) {
    // Keep a stable 90-day window while selecting points within it. Recenter
    // only when selection leaves it; trim the right edge for the chosen lead.
    if (start < 0 || selection.issueIndex < start || selection.issueIndex > end) {
      start = Math.max(0, Math.min(
        dataset.n - selection.lead - HISTORY_DAYS,
        selection.issueIndex - DAYS_BEFORE_SELECTION,
      ));
      end = Math.min(dataset.n - 1 - selection.lead, start + HISTORY_DAYS - 1);
    }
    if (end + selection.lead >= dataset.n) {
      end = dataset.n - 1 - selection.lead;
      start = Math.max(0, end - HISTORY_DAYS + 1);
    }
  }

  function drawAxes(heightRange, inputRange, hasHeights, hasInputs) {
    const { time, height, depth } = SIZE;
    const [heightMin, heightMax] = heightRange;
    const [inputMin, inputMax] = inputRange;

    addLine([
      new THREE.Vector3(0, height, 0),
      new THREE.Vector3(0, 0, 0),
      new THREE.Vector3(time, 0, 0),
    ], COLORS.axis);
    addLine([
      new THREE.Vector3(0, 0, 0),
      new THREE.Vector3(0, 0, -depth),
    ], COLORS.axis);

    for (let tick = 0; tick <= 4; tick++) {
      const fraction = tick / 4;
      const x = fraction * time;
      const y = fraction * height;
      const z = -fraction * depth;
      addLine([
        new THREE.Vector3(0, y, 0), new THREE.Vector3(time, y, 0),
      ], COLORS.grid, 0.4);
      addLine([
        new THREE.Vector3(0, 0, z), new THREE.Vector3(time, 0, z),
      ], COLORS.grid, 0.4);
      addLine([
        new THREE.Vector3(x, 0, 0), new THREE.Vector3(x, 0, -depth),
      ], COLORS.grid, 0.3);
      addText(
        hasHeights ? (heightMin + fraction * (heightMax - heightMin)).toFixed(1) : '—',
        -0.14, y, 0, 0.30, 0.10, COLORS.observed,
      );
      addText(
        hasInputs ? (inputMin + fraction * (inputMax - inputMin)).toFixed(1) : '—',
        -0.17, 0, z, 0.30, 0.10,
      );
    }

    addText('X · TARGET DATE', time / 2, -0.26, 0.1, 1.15, 0.12);
    addText(samples[0].targetDate, 0, -0.12, 0, 0.65, 0.10);
    addText(samples.at(-1).targetDate, time, -0.12, 0, 0.65, 0.10);
    addText(
      'Y · RIVER HEIGHT (ft, estimated)',
      time / 2, height + 0.18, 0, 2.2, 0.13, COLORS.observed,
    );
    const definition = graphVariables[variable];
    addText(
      'Z · ' + definition.title + ' (' + definition.unit + ')',
      time / 2, -0.15, -depth, 2.1, 0.12,
    );
  }

  function drawSeries(field, color, toPosition) {
    let path = [];
    for (const sample of samples) {
      // Break the curve at missing values. Joining across a gap would imply
      // observations or predictions that the supplied data does not contain.
      if (sample.input == null || sample[field] == null) {
        addLine(path, color);
        path = [];
      } else {
        path.push(toPosition(sample, sample[field]));
      }
    }
    addLine(path, color);
  }

  function rebuild(selection) {
    clearContent();
    samples = graphSamples(dataset, selection, variable, start, end);
    const forecastPoints = samples.filter((sample) =>
      sample.input != null && sample.predictedStage != null,
    );
    const inputs = samples.filter((sample) => sample.input != null)
      .map((sample) => sample.input);
    const heights = samples.flatMap((sample) => [
      sample.predictedStage, sample.observedStage,
    ]).filter((value) => value != null);
    const heightRange = paddedExtent(heights);
    const inputRange = paddedExtent(inputs);
    const [heightMin, heightMax] = heightRange;
    const [inputMin, inputMax] = inputRange;

    // Normalize scientific values into scene units. Larger gauge height moves
    // UP (+Y); larger environment readings move INTO the plot (-Z).
    const toPosition = (sample, stage) => new THREE.Vector3(
      (sample.issueIndex - start) / (end - start || 1) * SIZE.time,
      (stage - heightMin) / (heightMax - heightMin) * SIZE.height,
      -(sample.input - inputMin) / (inputMax - inputMin) * SIZE.depth,
    );

    drawAxes(heightRange, inputRange, heights.length > 0, inputs.length > 0);
    drawSeries('observedStage', COLORS.observed, toPosition);
    drawSeries('predictedStage', COLORS.predicted, toPosition);

    // Every forecast dot has the same shape/material. A separate marker shows
    // selection, so no per-dot material copies or colour mutations are needed.
    if (forecastPoints.length) {
      const geometry = new THREE.SphereGeometry(0.018, 8, 6);
      const material = new THREE.MeshBasicMaterial({ color: COLORS.point });
      for (const sample of forecastPoints) {
        const dot = new THREE.Mesh(geometry, material);
        dot.position.copy(toPosition(sample, sample.predictedStage));
        dot.userData.issueIndex = sample.issueIndex;
        dot.userData.sample = sample;
        content.add(dot);
        targets.push(dot);
      }
    }
    selectedMarker = new THREE.Mesh(
      new THREE.SphereGeometry(0.036, 16, 10),
      new THREE.MeshBasicMaterial({ color: COLORS.selected }),
    );
    content.add(selectedMarker);

    const status = variable.startsWith('snow') && !inputs.length
      ? 'Snow observations unavailable in this window'
      : forecastPoints.length + ' / ' + samples.length +
        ' forecast points · gaps mean unavailable data';
    addText(status, SIZE.time / 2, SIZE.height + 0.36, 0, 2.5, 0.11, '#667983');
  }

  /** Rebuild only when model/lead/variable/window changes; otherwise highlight. */
  function update(selection) {
    updateWindow(selection);
    const nextKey = [
      selection.modelIndex, selection.lead, variable, start, end,
    ].join(':');
    if (nextKey !== cacheKey) {
      rebuild(selection);
      cacheKey = nextKey;
    }
    const active = targets.find((dot) =>
      dot.userData.issueIndex === selection.issueIndex,
    );
    selectedMarker.visible = Boolean(active);
    if (active) selectedMarker.position.copy(active.position);

    return {
      sample: samples.find((sample) => sample.issueIndex === selection.issueIndex),
      variable: graphVariables[variable],
      start,
      end,
      count: targets.length,
    };
  }

  return {
    group,
    update,
    // Call during rendering so the plane labels face the viewing camera.
    faceLabels(camera) {
      labels.forEach((mesh) => mesh.quaternion.copy(camera.quaternion));
    },
    setVariable(value) {
      if (!graphVariables[value]) throw new RangeError('Graph variable unavailable');
      variable = value;
      cacheKey = '';
    },
    getVariable: () => variable,
    getTargets: () => targets,
    getSamples: () => samples,
    // The host raycasts getTargets(), then passes the intersected mesh here.
    select: (hit) => onSelect(hit.userData.issueIndex),
    dispose() {
      clearContent();
      samples = [];
      cacheKey = '';
      group.removeFromParent();
    },
  };
}
