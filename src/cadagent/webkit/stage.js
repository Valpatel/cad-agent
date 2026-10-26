// The stage: renderer, camera and orbit controls, control-room lighting, floor grid and glow pad, and a scene-light
// dimmer. No robot here: a project adds its own model to `stage.scene` (or `stage.root`).
//
// Units are metres; the floor is y = 0, x right, y up, z towards the viewer. Sizes scale with `opts.height`, the
// robot's rough height, so the same stage frames a 0.3 m robot or a 2 m one.
//
// Adapted from the Moxie simulator's moxie/scene.js (mvalancy/moxie-robot-saver, MIT).
import * as THREE from 'three';
import { OrbitControls } from 'three/addons/controls/OrbitControls.js';

function radialGlow(stops) {
  const c = document.createElement('canvas');
  c.width = c.height = 256;
  const g = c.getContext('2d');
  const grad = g.createRadialGradient(128, 128, 0, 128, 128, 128);
  for (const [at, col] of stops) grad.addColorStop(at, col);
  g.fillStyle = grad;
  g.fillRect(0, 0, 256, 256);
  const t = new THREE.CanvasTexture(c);
  t.colorSpace = THREE.SRGBColorSpace;
  return t;
}

/**
 * createStage(container, { height = 1, accent = 0x00f0ff })
 * Returns { renderer, scene, camera, controls, root, setSceneLight(0..1), frame(height), onFrame(cb), start() }.
 * `onFrame(cb)` registers cb(t, dt) called every animation frame before rendering.
 */
export function createStage(container, opts = {}) {
  const h = opts.height ?? 1;
  const accent = opts.accent ?? 0x00f0ff;

  const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true, preserveDrawingBuffer: !!opts.screenshots });
  renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
  renderer.shadowMap.enabled = true;
  renderer.shadowMap.type = THREE.PCFSoftShadowMap;
  renderer.toneMapping = THREE.ACESFilmicToneMapping;
  renderer.toneMappingExposure = 1.05;
  container.appendChild(renderer.domElement);

  const scene = new THREE.Scene();
  const camera = new THREE.PerspectiveCamera(38, 1, 0.05, 50);   // near/far are set from the model size in frame()
  const controls = new OrbitControls(camera, renderer.domElement);
  controls.enableDamping = true;
  controls.dampingFactor = 0.08;
  controls.maxPolarAngle = 1.5;

  // cool control-room lighting: white key, cold fill, accent rim
  const hemi = new THREE.HemisphereLight(0xdcecff, 0x10151d, 0.6);
  const key = new THREE.DirectionalLight(0xffffff, 2.1);
  key.castShadow = true;
  key.shadow.mapSize.set(2048, 2048);
  key.shadow.bias = -0.0005;
  key.shadow.radius = 5;
  const fill = new THREE.DirectionalLight(0xa9d8ff, 0.45);
  const rim = new THREE.DirectionalLight(accent, 1.0);
  scene.add(hemi, key, fill, rim);

  const ground = new THREE.Mesh(new THREE.CircleGeometry(1, 64), new THREE.ShadowMaterial({ opacity: 0.4 }));
  ground.rotation.x = -Math.PI / 2;
  ground.receiveShadow = true;
  const grid = new THREE.GridHelper(1, 52, accent, 0x0e7490);
  grid.material.transparent = true;
  grid.material.depthWrite = false;
  const pad = new THREE.Mesh(new THREE.CircleGeometry(1, 48), new THREE.MeshBasicMaterial({
    map: radialGlow([[0, 'rgba(0, 240, 255, 0.20)'], [0.5, 'rgba(0, 240, 255, 0.05)'], [1, 'rgba(0, 240, 255, 0)']]),
    transparent: true, depthWrite: false, blending: THREE.AdditiveBlending,
  }));
  pad.rotation.x = -Math.PI / 2;
  scene.add(ground, grid, pad);

  const root = new THREE.Group();
  scene.add(root);

  // Size everything to the robot.
  function frame(height) {
    const s = height;
    // A tight near/far range keeps depth precision high, so close surfaces do not flicker (z-fighting).
    camera.near = 0.02 * s;
    camera.far = 30 * s;
    camera.updateProjectionMatrix();
    key.shadow.normalBias = 0.01 * s;     // no shadow acne crawling over moving parts
    camera.position.set(1.5 * s, 1.15 * s, 2.6 * s);
    controls.target.set(0, 0.5 * s, 0);
    controls.minDistance = 0.6 * s;
    controls.maxDistance = 9 * s;
    key.position.set(2.6 * s, 4.4 * s, 3.2 * s);
    Object.assign(key.shadow.camera, { left: -2 * s, right: 2 * s, top: 2.4 * s, bottom: -1.2 * s, near: 0.1 * s, far: 12 * s });
    key.shadow.camera.updateProjectionMatrix();
    fill.position.set(-3.2 * s, 1.8 * s, 1.2 * s);
    rim.position.set(-1 * s, 2.8 * s, -3.4 * s);
    ground.scale.setScalar(6 * s);
    grid.scale.setScalar(20 * s);
    grid.position.y = 0.0005 * s;
    pad.scale.setScalar(2.1 * s);
    pad.position.y = 0.001 * s;
    controls.update();
  }
  frame(h);

  const light = { level: 0.85, current: 0.85, base: { hemi: 0.6, key: 2.1, fill: 0.45, rim: 1.0, grid: 0.09, pad: 1.0 } };
  function applyLight() {
    const s = light.current, lit = 0.04 + 0.96 * s;
    hemi.intensity = light.base.hemi * lit;
    key.intensity = light.base.key * lit;
    fill.intensity = light.base.fill * lit;
    rim.intensity = light.base.rim * (0.12 + 0.88 * s);
    grid.material.opacity = light.base.grid * (0.35 + 0.65 * s);
    pad.material.opacity = light.base.pad * (0.45 + 0.55 * s);
  }
  applyLight();

  function resize() {
    const w = container.clientWidth || window.innerWidth, hh = container.clientHeight || window.innerHeight;
    renderer.setSize(w, hh, false);
    renderer.domElement.style.width = '100%';
    renderer.domElement.style.height = '100%';
    camera.aspect = w / hh;
    camera.updateProjectionMatrix();
  }
  new ResizeObserver(resize).observe(container);
  resize();

  const callbacks = [];
  const clock = new THREE.Clock();
  let running = false;
  function tick() {
    const dt = Math.min(clock.getDelta(), 0.05), t = clock.elapsedTime;
    light.current += (light.level - light.current) * (1 - Math.exp(-dt * 4));
    applyLight();
    for (const cb of callbacks) {
      try { cb(t, dt); } catch (err) {               // one bad callback must not freeze the stage
        if (!cb.failed) { cb.failed = true; console.error(err); document.body.dataset.stageError = String(err?.stack ?? err).slice(0, 500); }
      }
    }
    controls.update();
    renderer.render(scene, camera);
    requestAnimationFrame(tick);
  }

  return {
    renderer, scene, camera, controls, root, frame,
    setSceneLight(v) { light.level = Math.max(0, Math.min(1, v)); },
    onFrame(cb) { callbacks.push(cb); },
    start() { if (!running) { running = true; requestAnimationFrame(tick); } },
  };
}
