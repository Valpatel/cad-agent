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

// Native GL_LINES crossing the camera's near plane can become filled polygons in WebKit (#536).
// Draw the same finite 52-division grid on two triangles instead. Derivatives keep lines about a pixel
// wide while the camera moves; fade only subpixel spacing at the horizon, not the near-camera floor.
function floorGrid(accent, color) {
  const material = new THREE.ShaderMaterial({
    // WebGL 1 needs the GLSL extension directive for fwidth; it is core in WebGL 2.
    extensions: { derivatives: true },
    uniforms: { axisColor: { value: new THREE.Color(accent) }, gridColor: { value: new THREE.Color(color) },
      opacity: { value: 1 } },
    vertexShader: `varying vec2 vGrid;
      void main() {
        vGrid = position.xy * 52.0;
        gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0);
      }`,
    fragmentShader: `uniform vec3 axisColor;
      uniform vec3 gridColor;
      uniform float opacity;
      varying vec2 vGrid;
      void main() {
        vec2 width = max(fwidth(vGrid), vec2(0.000001));
        vec2 distance = abs(fract(vGrid - 0.5) - 0.5);
        vec2 fade = 1.0 - smoothstep(vec2(0.5), vec2(1.0), width);
        vec2 lines = (1.0 - smoothstep(0.25 * width, 0.75 * width, distance)) * fade;
        vec2 axes = 1.0 - smoothstep(0.25 * width, 0.75 * width, abs(vGrid));
        float coverage = max(lines.x, lines.y);
        if (coverage <= 0.0) discard;
        gl_FragColor = vec4(mix(gridColor, axisColor, max(axes.x, axes.y)), opacity * coverage);
        #include <tonemapping_fragment>
        #include <colorspace_fragment>
      }`,
    transparent: true, depthWrite: false, side: THREE.DoubleSide,
  });
  const grid = new THREE.Mesh(new THREE.PlaneGeometry(1, 1), material);
  grid.name = 'stage-grid';
  grid.rotation.x = -Math.PI / 2;
  return grid;
}

/**
 * createStage(container, { height = 1, accent = 0x00f0ff, zoomSpeed = 0.25, dragZoomSpeed = 1, palette })
 * Returns { renderer, scene, camera, controls, root, setSceneLight(0..1), frame(height), onFrame(cb), start(), stop(), dispose(),
 *           setInsets({ left, right, top, bottom }), fitView(points, { direction, margin }), setPalette({accent, grid, glow}) }.
 * `setInsets` takes the pixels covered by overlay UI (a side panel, a top bar): the view's centre moves into the
 * uncovered area, so the model is not hidden behind the panels. `fitView` places the camera so all the points (THREE
 * Vector3s, or a Box3) fit in that uncovered area, looking along `direction` at `target` (default: their centre).
 * `onFrame(cb)` registers cb(t, dt) called every animation frame before rendering.
 *
 * The stage draws on demand: each frame it compares what the renderer would read (sceneSignature) with what it read
 * at the last draw, and draws only on a difference, so an idle stage costs no GPU or rasteriser time. Code that moves,
 * shows, hides, recolours or replaces three.js objects, materials, textures, lights, the camera or the renderer's
 * size needs to do nothing more. `invalidate()` requests a draw for anything the signature cannot see (for example
 * a texture whose pixels change without `needsUpdate`, or a shader that reads time from outside its uniforms).
 * `draws` counts the frame loop's draws.
 */
/**
 * Test and debugging hook shared by every stage on the page: `live` holds each stage's `{draws, invalidate}`, and
 * `alwaysDraw = true` restores drawing on every frame (to compare pictures, or to rule out a missed draw).
 */
export const stageDiagnostics = { live: new Set(), alwaysDraw: false };

// Everything three.js reads when it draws, flattened to numbers: renderer size and output settings, the camera, and
// for each visible object its world matrix, flags, geometry versions, material values and textures. Strings,
// functions and userData are skipped; three.js only re-reads changed shader text after `needsUpdate`, which bumps
// `material.version`, so the version stands for them.
const SKIPPED = new Set(['userData', 'uuid', 'name', 'type', '_listeners']);
const strings = new Map();
const intern = (text) => { let id = strings.get(text); if (id === undefined) strings.set(text, (id = strings.size + 1)); return id; };
const viewport = new THREE.Vector4(), clearColor = new THREE.Color();
function pushValue(out, value, depth) {
  if (typeof value === 'number') out.push(value);
  else if (typeof value === 'boolean') out.push(value ? 1 : 0);
  else if (value === null || value === undefined) out.push(NaN);
  else if (typeof value === 'string') out.push(intern(value));
  else if (typeof value !== 'object' || depth > 3) return;
  else if (value.isTexture) {
    out.push(value.id, value.version, value.offset.x, value.offset.y, value.repeat.x, value.repeat.y, value.rotation, value.center.x, value.center.y, value.flipY ? 1 : 0);
  } else if (value.isColor) out.push(value.r, value.g, value.b);
  else if (value.isVector2) out.push(value.x, value.y);
  else if (value.isVector3 || value.isEuler) out.push(value.x, value.y, value.z);
  else if (value.isVector4 || value.isQuaternion) out.push(value.x, value.y, value.z, value.w);
  else if (value.isMatrix3 || value.isMatrix4) for (const n of value.elements) out.push(n);
  else if (value.isPlane) out.push(value.normal.x, value.normal.y, value.normal.z, value.constant);
  else if (Array.isArray(value) || ArrayBuffer.isView(value)) {
    out.push(value.length);
    for (let i = 0; i < value.length; i++) pushValue(out, value[i], depth + 1);
  } else if (depth === 0 && value.constructor === Object) {    // plain records: defines, extensions
    for (const key in value) pushValue(out, value[key], depth + 1);
  }
}
function pushMaterial(out, material, seen) {
  out.push(material.id, material.version);
  if (seen.has(material)) return;
  seen.add(material);
  for (const key in material) {
    if (SKIPPED.has(key)) continue;
    const value = material[key];
    if (key === 'uniforms') { for (const name in value) pushValue(out, value[name]?.value, 1); } else pushValue(out, value, 0);
  }
}
function pushGeometry(out, geometry) {
  out.push(geometry.id, geometry.index ? geometry.index.version : -1, geometry.drawRange.start, geometry.drawRange.count, geometry.groups.length);
  for (const name in geometry.attributes) {
    const attribute = geometry.attributes[name];
    out.push(attribute.isInterleavedBufferAttribute ? attribute.data.version : attribute.version, attribute.count);
  }
}
function pushObject(out, object, seen) {
  out.push(object.id, object.visible ? 1 : 0);
  if (!object.visible) return;
  for (const n of object.matrixWorld.elements) out.push(n);
  out.push(object.renderOrder, object.layers.mask, object.castShadow ? 1 : 0, object.receiveShadow ? 1 : 0, object.frustumCulled ? 1 : 0);
  if (object.isLight) {
    out.push(object.intensity, object.distance ?? 0, object.decay ?? 0, object.angle ?? 0, object.penumbra ?? 0);
    pushValue(out, object.color, 1);
    if (object.groundColor) pushValue(out, object.groundColor, 1);
    if (object.target) pushValue(out, object.target.matrixWorld, 1);
    const shadow = object.shadow;
    if (shadow) {
      out.push(shadow.bias, shadow.normalBias, shadow.radius, shadow.mapSize.x, shadow.mapSize.y);
      pushValue(out, shadow.camera.projectionMatrix, 1);
    }
  }
  if (object.geometry) pushGeometry(out, object.geometry);
  if (Array.isArray(object.material)) for (const material of object.material) pushMaterial(out, material, seen);
  else if (object.material) pushMaterial(out, object.material, seen);
  if (object.morphTargetInfluences) pushValue(out, object.morphTargetInfluences, 1);
  if (object.isInstancedMesh) out.push(object.count, object.instanceMatrix.version, object.instanceColor ? object.instanceColor.version : -1);
  if (object.isSkinnedMesh) for (const bone of object.skeleton.bones) pushValue(out, bone.matrixWorld, 1);
  out.push(object.children.length);
  for (const child of object.children) pushObject(out, child, seen);
}
/** Fill `out` with the numbers that decide the next picture (see above). */
export function sceneSignature(renderer, scene, camera, out = []) {
  out.length = 0;
  if (scene.matrixWorldAutoUpdate) scene.updateMatrixWorld();
  if (camera.parent === null && camera.matrixWorldAutoUpdate) camera.updateMatrixWorld();
  const canvas = renderer.domElement;
  renderer.getViewport(viewport);
  renderer.getClearColor(clearColor);
  out.push(canvas.width, canvas.height, renderer.getPixelRatio(), viewport.x, viewport.y, viewport.z, viewport.w,
    clearColor.r, clearColor.g, clearColor.b, renderer.getClearAlpha(), renderer.toneMapping, renderer.toneMappingExposure,
    intern(renderer.outputColorSpace), renderer.localClippingEnabled ? 1 : 0, renderer.shadowMap.enabled ? 1 : 0,
    renderer.shadowMap.type, renderer.sortObjects ? 1 : 0, camera.layers.mask);
  pushValue(out, renderer.clippingPlanes, 1);
  pushValue(out, camera.matrixWorld, 1);
  pushValue(out, camera.projectionMatrix, 1);
  pushValue(out, scene.background, 1);
  pushValue(out, scene.environment, 1);
  out.push(scene.backgroundBlurriness ?? 0, scene.backgroundIntensity ?? 1, scene.overrideMaterial ? scene.overrideMaterial.id : -1);
  if (scene.fog) { pushValue(out, scene.fog.color, 1); out.push(scene.fog.near ?? 0, scene.fog.far ?? 0, scene.fog.density ?? 0); }
  const seen = new Set();
  if (scene.overrideMaterial) pushMaterial(out, scene.overrideMaterial, seen);
  pushObject(out, scene, seen);
  return out;
}
/**
 * Equal within a relative 1e-9: far below a pixel at any canvas size, and enough to let a damping tail end instead of
 * redrawing for float rounding. Compared against the last *drawn* signature, so slow drift still adds up to a draw.
 */
export function sameSignature(a, b) {
  if (!b || a.length !== b.length) return false;
  for (let i = 0; i < a.length; i++) {
    const x = a[i], y = b[i];
    if (x === y || (x !== x && y !== y)) continue;
    if (!(Math.abs(x - y) <= 1e-9 * Math.max(1, Math.abs(x), Math.abs(y)))) return false;
  }
  return true;
}

export function createStage(container, opts = {}) {
  const h = opts.height ?? 1;
  const accent = opts.accent ?? 0x00f0ff;

  const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true, preserveDrawingBuffer: !!opts.screenshots });
  renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
  renderer.shadowMap.enabled = true;
  renderer.shadowMap.type = THREE.PCFSoftShadowMap;
  renderer.toneMapping = THREE.ACESFilmicToneMapping;
  renderer.toneMappingExposure = 1.35;
  container.appendChild(renderer.domElement);

  const scene = new THREE.Scene();
  const camera = new THREE.PerspectiveCamera(38, 1, 0.05, 50);   // near/far are set from the model size in frame()
  const controls = new OrbitControls(camera, renderer.domElement);
  controls.enableDamping = true;
  controls.dampingFactor = 0.08;
  // Wheel zoom at a quarter speed (four wheel increments cover the former single-increment distance; small trackpad
  // deltas and trackpad pinch, which arrives as ctrl+wheel, stay continuous), but middle-button drag and touch pinch at full speed: OrbitControls has one zoomSpeed for all
  // three, so it is set per gesture, in the capture phase on the container, before OrbitControls sees the event.
  const wheelZoom = opts.zoomSpeed ?? 0.25, dragZoom = opts.dragZoomSpeed ?? 1;
  controls.zoomSpeed = wheelZoom;
  const gestures = new AbortController();           // removed in dispose(), so re-mounting does not pile listeners up
  container.addEventListener('wheel', () => { controls.zoomSpeed = wheelZoom; }, { capture: true, passive: true, signal: gestures.signal });
  container.addEventListener('pointerdown', () => { controls.zoomSpeed = dragZoom; }, { capture: true, passive: true, signal: gestures.signal });
  controls.maxPolarAngle = 1.5;

  // cool control-room lighting: white key, cold fill, accent rim
  const hemi = new THREE.HemisphereLight(0xeef6ff, 0x2a3240, 1.1);
  const key = new THREE.DirectionalLight(0xffffff, 2.8);
  key.castShadow = true;
  key.shadow.mapSize.set(2048, 2048);
  key.shadow.bias = -0.0005;
  key.shadow.radius = 5;
  const fill = new THREE.DirectionalLight(0xcfe6ff, 1.0);
  const ambient = new THREE.AmbientLight(0xffffff, 0.35);
  const rim = new THREE.DirectionalLight(accent, 1.0);
  scene.add(hemi, key, fill, rim, ambient);

  const ground = new THREE.Mesh(new THREE.CircleGeometry(1, 64), new THREE.ShadowMaterial({ opacity: 0.4 }));
  ground.rotation.x = -Math.PI / 2;
  ground.receiveShadow = true;
  const grid = floorGrid(accent, 0x0e7490);
  const pad = new THREE.Mesh(new THREE.CircleGeometry(1, 48), new THREE.MeshBasicMaterial({
    map: radialGlow([[0, 'rgba(120, 220, 255, 0.32)'], [0.5, 'rgba(0, 240, 255, 0.09)'], [1, 'rgba(0, 240, 255, 0)']]),
    transparent: true, depthWrite: false, blending: THREE.AdditiveBlending,
  }));
  pad.rotation.x = -Math.PI / 2;
  scene.add(ground, grid, pad);

  /** Recolor stage accents without changing the model's authored materials or camera. */
  function setPalette({accent:nextAccent=accent,grid:nextGrid=0x0e7490,glow:nextGlow=0x00f0ff,background}={}) {
    if(background!==undefined)scene.background=new THREE.Color(background);
    rim.color.set(nextAccent);
    grid.material.uniforms.axisColor.value.set(nextAccent);
    grid.material.uniforms.gridColor.value.set(nextGrid);
    const rgb=new THREE.Color(nextGlow).getStyle();
    const components=rgb.match(/[\d.]+/g);
    const rgba=alpha=>`rgba(${components.join(',')},${alpha})`;
    pad.material.map.dispose();
    pad.material.map=radialGlow([[0,rgba(.22)],[.5,rgba(.07)],[1,rgba(0)]]);
    pad.material.needsUpdate=true;
  }
  if(opts.palette)setPalette(opts.palette);

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

  const light = { level: 1, current: 1, base: { hemi: 1.1, key: 2.8, fill: 1.0, rim: 1.0, grid: 0.12, pad: 1.0, ambient: 0.35 } };
  function applyLight() {
    const s = light.current, lit = 0.04 + 0.96 * s;
    hemi.intensity = light.base.hemi * lit;
    key.intensity = light.base.key * lit;
    fill.intensity = light.base.fill * lit;
    ambient.intensity = light.base.ambient * lit;
    rim.intensity = light.base.rim * (0.12 + 0.88 * s);
    grid.material.opacity = light.base.grid * (0.35 + 0.65 * s);
    grid.material.uniforms.opacity.value = grid.material.opacity;
    pad.material.opacity = light.base.pad * (0.45 + 0.55 * s);
  }
  applyLight();

  const insets = { left: 0, right: 0, top: 0, bottom: 0 };
  const size = () => [container.clientWidth || window.innerWidth, container.clientHeight || window.innerHeight];
  function resize() {
    const [w, hh] = size();
    renderer.setSize(w, hh, false);
    renderer.domElement.style.width = '100%';
    renderer.domElement.style.height = '100%';
    camera.aspect = w / hh;
    // shift the projection so the camera looks at the centre of the area the overlays leave free
    const dx = (insets.right - insets.left) / 2, dy = (insets.bottom - insets.top) / 2;
    if (dx || dy) camera.setViewOffset(w, hh, dx, dy, w, hh); else camera.clearViewOffset();
    camera.updateProjectionMatrix();
  }
  function setInsets(next = {}) {
    for (const k of Object.keys(insets)) insets[k] = Math.max(0, next[k] ?? 0);
    resize();
  }
  function fitView(points, { direction = new THREE.Vector3(1, 0.6, 1.4), margin = 1.06, target = null, apply = true } = {}) {
    const box = points.isBox3 ? points : new THREE.Box3().setFromPoints(points);
    const pts = points.isBox3 ? [0, 1, 2, 3, 4, 5, 6, 7].map((i) => new THREE.Vector3(i & 1 ? box.max.x : box.min.x, i & 2 ? box.max.y : box.min.y, i & 4 ? box.max.z : box.min.z)) : points;
    const sphere = box.getBoundingSphere(new THREE.Sphere());
    const center = target ?? sphere.center;
    const dir = direction.clone().normalize();
    const [w, hh] = size();
    resize();
    // the free area in normalised device coordinates (the projection already includes the view offset)
    const x0 = -1 + (2 * insets.left) / w, x1 = 1 - (2 * insets.right) / w, y0 = -1 + (2 * insets.bottom) / hh, y1 = 1 - (2 * insets.top) / hh;
    const shrink = 1 / margin;
    const v = new THREE.Vector3();
    const saved = { p: camera.position.clone(), q: camera.quaternion.clone() };
    const cx = (x0 + x1) / 2, cy = (y0 + y1) / 2;
    const fits = (dist) => {
      camera.position.copy(center).addScaledVector(dir, dist);
      camera.lookAt(center);
      camera.updateMatrixWorld();
      return pts.every((p) => {
        if (v.copy(p).applyMatrix4(camera.matrixWorldInverse).z > -camera.near) return false;    // behind the camera
        v.copy(p).project(camera);
        return Math.abs(v.x - cx) <= shrink * (x1 - x0) / 2 && Math.abs(v.y - cy) <= shrink * (y1 - y0) / 2;
      });
    };
    // perspective: near things look bigger, so search the distance that just fits every point
    let hi = Math.max(sphere.radius, center.distanceTo(sphere.center) + sphere.radius) * 6, lo = 0.05 * sphere.radius;
    if (fits(hi)) {
      for (let k = 0; k < 32; k++) { const mid = (lo + hi) / 2; if (fits(mid)) hi = mid; else lo = mid; }
    }
    const dist = hi;
    const position = center.clone().addScaledVector(dir, dist);
    camera.position.copy(saved.p);
    camera.quaternion.copy(saved.q);
    camera.updateMatrixWorld();
    if (!apply) return { center, distance: dist, position };
    camera.position.copy(position);
    controls.target.copy(center);
    camera.far = Math.max(camera.far, dist + 4 * sphere.radius);
    controls.maxDistance = Math.max(controls.maxDistance, 2 * dist);
    camera.updateProjectionMatrix();
    controls.update();
    return { center, distance: dist, position };
  }
  const observer = new ResizeObserver(resize);
  observer.observe(container);
  resize();

  const callbacks = [];
  const clock = new THREE.Clock();
  let running = false, frameId = 0;
  // Draw on demand (#822). Every frame still advances the clock, the light dimmer, the onFrame callbacks and the
  // controls, but the picture is drawn only when what the renderer would read has changed since the last draw
  // (sceneSignature), when invalidate() asked for it, or while stageDiagnostics.alwaysDraw is set. A stage that is
  // off screen or hidden draws nothing and draws once when it comes back.
  let needsDraw = true, onScreen = null, drawn = null, pending = [];
  const diagnostics = { draws: 0, frames: 0, invalidate: () => { needsDraw = true; } };
  const invalidate = () => { needsDraw = true; };
  const visibility = typeof IntersectionObserver === 'function'
    ? new IntersectionObserver((entries) => {
      const next = entries[entries.length - 1].isIntersecting;
      if (next && !onScreen) needsDraw = true;          // coming back on screen draws once
      onScreen = next;
    })
    : null;
  if (visibility) visibility.observe(renderer.domElement); else onScreen = true;
  renderer.domElement.addEventListener('webglcontextrestored', invalidate, { signal: gestures.signal });
  document.addEventListener('visibilitychange', () => { if (!document.hidden) needsDraw = true; }, { signal: gestures.signal });
  function tick() {
    if (!running) return;
    const dt = Math.min(clock.getDelta(), 0.05), t = clock.elapsedTime;
    light.current += (light.level - light.current) * (1 - Math.exp(-dt * 4));
    applyLight();
    for (const cb of [...callbacks]) {
      try { cb(t, dt); } catch (err) {               // one bad callback must not freeze the stage
        if (!cb.failed) { cb.failed = true; if (opts.onError) opts.onError(err); else { console.error(err); document.body.dataset.stageError = String(err?.stack ?? err).slice(0, 500); } }
      }
    }
    controls.update();
    diagnostics.frames++;
    if (onScreen && !document.hidden) {
      pending = sceneSignature(renderer, scene, camera, pending);
      if (needsDraw || stageDiagnostics.alwaysDraw || !sameSignature(pending, drawn)) {
        needsDraw = false;
        renderer.render(scene, camera);
        diagnostics.draws++;
        [drawn, pending] = [pending, drawn ?? []];
      }
    }
    frameId = requestAnimationFrame(tick);
  }
  stageDiagnostics.live.add(diagnostics);

  return {
    renderer, scene, camera, controls, root, frame, setInsets, fitView, setPalette,
    /** Ask for a draw on the next frame. Only needed for a change the stage cannot see (see sceneSignature). */
    invalidate,
    /** Draws made by this stage's frame loop (a test hook; see stageDiagnostics). */
    get draws() { return diagnostics.draws; },
    /** Frames the loop has run (callbacks, controls and the draw decision), drawn or not: wait on this, not on draws. */
    get frames() { return diagnostics.frames; },
    setSceneLight(v, immediate = false) { light.level = Math.max(0, Math.min(1, v)); if (immediate) { light.current = light.level; applyLight(); } },
    onFrame(cb) {
      callbacks.push(cb);
      let subscribed = true;
      return () => { if (!subscribed) return; subscribed = false; const index = callbacks.indexOf(cb); if (index !== -1) callbacks.splice(index, 1); };
    },
    start() { if (!running) { running = true; frameId = requestAnimationFrame(tick); } },
    stop() { running = false; cancelAnimationFrame(frameId); },
    /** Stop, and free the WebGL context, the controls and the canvas (before mounting another stage on the page). */
    dispose() {
      running = false;
      callbacks.length = 0;
      cancelAnimationFrame(frameId);
      observer.disconnect();
      visibility?.disconnect();
      stageDiagnostics.live.delete(diagnostics);
      gestures.abort();
      controls.dispose();
      for(const object of [ground,grid,pad]){object.geometry.dispose();object.material.map?.dispose();object.material.dispose();}
      renderer.dispose();
      renderer.forceContextLoss();
      renderer.domElement.remove();
    },
  };
}
