import * as THREE from 'three';

/**
 * Render a text label onto a plane without HTML inside the 3D scene.
 * Dimensions are scene units; fontSize controls the canvas text resolution.
 * The caller owns/disposes the geometry, material, and canvas texture.
 */
export function label(text, {
  width = 1.2,
  height = 0.15,
  color = '#244956',
  background = '#f5faf9',
  fontSize = 40,
} = {}) {
  const canvas = document.createElement('canvas');
  canvas.width = Math.max(192, Math.min(4096, Math.round(128 * width / height)));
  canvas.height = 128;
  const context = canvas.getContext('2d');
  context.fillStyle = background;
  context.fillRect(0, 0, canvas.width, canvas.height);
  context.fillStyle = color;
  context.font = `600 ${fontSize}px system-ui`;
  context.textAlign = 'center';
  context.textBaseline = 'middle';
  context.fillText(text, canvas.width / 2, canvas.height / 2, canvas.width - 32);

  const texture = new THREE.CanvasTexture(canvas);
  texture.colorSpace = THREE.SRGBColorSpace;
  const material = new THREE.MeshBasicMaterial({
    map: texture,
    transparent: true,
    side: THREE.DoubleSide,
    // Keep text legible over geometry and independent of lighting/fog.
    toneMapped: false,
    fog: false,
    depthTest: false,
    depthWrite: false,
  });
  const mesh = new THREE.Mesh(new THREE.PlaneGeometry(width, height), material);
  mesh.renderOrder = 20;
  return mesh;
}
