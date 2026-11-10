// A 3D viewer for any CAD project's assembly: loads exports/view/view.json (written by `cad-agent view`), shows every
// part in place, and gives a parts list (show/hide, colour), an exploded view, a section cut and standard views.
// Housings, brackets, mechanisms and robots all work the same way.
import * as THREE from 'three';
import { STLLoader } from 'three/addons/loaders/STLLoader.js';
import { createStage } from './stage.js';
import { section, slider, toggle, readouts } from './panel.js';
import { viewAssetURL, readAsset, parseJSON, validateView, validateState } from './assembly/guide.js';
import { validateSTL, normalizeMesh, MAX_TRIANGLES } from './file-geometry.js';

const esc = (s) => String(s ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));

/** Existing viewer, with optional validated guide manifests and abortable loading. */
export async function createViewer({ app, panel, title, manifestUrl, manifest: suppliedManifest,
    signal, onProgress = () => {}, timeoutMs = 30000, assetRoot, guideBound = false, onSelect = () => {}, onStateChange = () => {} }) {
  if (typeof guideBound !== 'boolean') throw new Error('Invalid guide mode');
  if (!Number.isFinite(timeoutMs) || timeoutMs <= 0) throw new Error('Invalid viewer timeout');
  const lifetime = new AbortController(), parts = [], events = new AbortController();
  let stage, timer, controlsHost, disposed = false;
  const cancel = () => { lifetime.abort(signal?.reason); dispose(); };
  signal?.addEventListener('abort', cancel, { once: true });
  if (signal?.aborted) cancel();
  timer = setTimeout(() => lifetime.abort(new Error('Model loading timed out')), timeoutMs);
  function dispose() {
    if (disposed) return;
    disposed = true; lifetime.abort(); events.abort(); signal?.removeEventListener('abort', cancel);
    clearTimeout(timer); stage?.dispose();
    for (const p of parts) { p.mesh.geometry.dispose(); p.mesh.material.dispose(); }
    controlsHost?.remove();
  }
  try {
  lifetime.signal.throwIfAborted();
  onProgress('Downloading the model manifest…');
  const manifest = structuredClone(validateView(suppliedManifest || parseJSON(await readAsset(manifestUrl, { signal: lifetime.signal, redirect: guideBound || assetRoot ? 'error' : 'follow', maxBytes: 2 * 1024 * 1024 })), { guide: guideBound }));
  const base = new URL('.', new URL(manifestUrl, location.href));
  // CAD is z-up in mm; the stage is y-up in metres. Baseline placements are baked into the meshes.
  const model = new THREE.Group();
  model.rotation.x = -Math.PI / 2;
  model.scale.setScalar(0.001);
  const loader = new STLLoader();
  const clip = new THREE.Plane(new THREE.Vector3(-1, 0, 0), 1e9);
  let totalBytes = 0, totalTriangles = 0;
  for (const p of manifest.parts) {
    onProgress(`Loading model part ${parts.length + 1} of ${manifest.parts.length}…`);
    const bytes = await readAsset(viewAssetURL(p.file, base, { guide: guideBound, assetRoot }), { signal: lifetime.signal, expectedHash: p.sha256, redirect: guideBound || assetRoot ? 'error' : 'follow' });
    totalBytes += bytes.byteLength;
    if (totalBytes > 128 * 1024 * 1024) throw new Error('Assembly exceeds the preview byte limit');
    validateSTL(bytes);
    const geo = loader.parse(bytes);
    try {
      normalizeMesh({ positions: geo.attributes.position?.array, indices: geo.index?.array });
      totalTriangles += geo.index ? geo.index.count / 3 : geo.attributes.position.count / 3;
      if (totalTriangles > MAX_TRIANGLES) throw new Error('Assembly exceeds the preview triangle limit');
      geo.computeVertexNormals();
      lifetime.signal.throwIfAborted();
    } catch (error) { geo.dispose(); throw error; }
    const mat = new THREE.MeshPhysicalMaterial({ color: p.color, roughness: 0.55, clearcoat: 0.2, clippingPlanes: [clip], clipShadows: true,
                                                 side: THREE.DoubleSide });
    const mesh = new THREE.Mesh(geo, mat);
    mesh.castShadow = mesh.receiveShadow = true;
    mesh.visible = p.visible !== false;
    model.add(mesh);
    const b = p.bounds_mm;
    parts.push({ ...p, mesh, center: new THREE.Vector3((b[0] + b[3]) / 2, (b[1] + b[4]) / 2, (b[2] + b[5]) / 2) });
  }
  lifetime.signal.throwIfAborted();
  onProgress('Preparing the 3D view…');
  if (title) title.textContent = manifest.title ?? 'Model';
  // Stand the model on the floor, centred.
  const box = new THREE.Box3().setFromObject(model);
  const size = box.getSize(new THREE.Vector3()), mid = box.getCenter(new THREE.Vector3());
  const holder = new THREE.Group();
  holder.add(model);
  model.position.set(-mid.x, -box.min.y, -mid.z);
  const height = Math.max(size.x, size.y, size.z);
  stage = createStage(app, { height: height * 0.8, screenshots: true });
  stage.renderer.localClippingEnabled = true;
  stage.root.add(holder);

  // Exploded view: each part moves away from the assembly centre (or along its configured direction).
  const centre = new THREE.Vector3();
  parts.forEach((p) => centre.add(p.center));
  centre.divideScalar(Math.max(1, parts.length));
  const span = Math.max(size.x, size.y, size.z) * 1000;
  let explodeSlider, sectionSlider;
  function setExplode(f) {
    ensureLive();
    if (!Number.isFinite(f) || f < 0 || f > 1) throw new Error('Invalid explode factor');
    explodeSlider?.set(f);
    const offsets_mm = Object.fromEntries(parts.map(p => {
      const dir = p.explode ? new THREE.Vector3(...p.explode).normalize() : p.center.clone().sub(centre);
      if (!p.explode) dir.lengthSq() > 1e-6 ? dir.normalize() : dir.set(0, 0, 1);
      return [p.name, dir.multiplyScalar(f * span * 0.6).toArray()];
    }));
    applyState({ ...state, offsets_mm });
  }
  // Section cut along CAD x: everything beyond the plane is cut away.
  const xmin = box.min.x, xmax = box.max.x;
  function setSection(f) { if (disposed || !Number.isFinite(f) || f < 0 || f > 1) throw new Error('Invalid section factor'); sectionSlider?.set(f); clip.constant = f >= 1 ? 1e9 : -(xmin + (xmax - xmin) * f - mid.x); }

  // Own only this wrapper; a product may have other controls in its panel.
  controlsHost = document.createElement('div'); panel.append(controlsHost);
  // Panel
  const info = readouts(section(controlsHost, 'Model', { note: `${parts.length} parts` }));
  const shownReadout = () => info.set([['size', `${Math.round(size.x * 1000)} × ${Math.round(size.z * 1000)} × ${Math.round(size.y * 1000)} mm`],
                                       ['parts shown', String(parts.filter((p) => p.mesh.visible).length)],
                                       ...(manifest.skipped?.length ? [['not exported', manifest.skipped.join(', '), 'warn']] : [])]);
  shownReadout();
  const views = section(controlsHost, 'View');
  explodeSlider = slider(views, { label: 'Explode', min: 0, max: 1, step: 0.01, value: 0, fmt: (v) => `${Math.round(v * 100)}%`, onInput: setExplode });
  sectionSlider = slider(views, { label: 'Section cut', min: 0, max: 1, step: 0.01, value: 1, fmt: (v) => (v >= 1 ? 'off' : `${Math.round(v * 100)}%`), onInput: setSection });
  slider(views, { label: 'Light', min: 0, max: 1, step: 0.01, value: 0.85, fmt: (v) => v.toFixed(2), onInput: (v) => stage.setSceneLight(v) });
  const camRow = document.createElement('div');
  camRow.className = 'hud-chips';
  const d = height * 2.6;
  for (const [name, pos] of [['ISO', [0.58, 0.45, 1]], ['FRONT', [0, 0.35, 1]], ['SIDE', [1, 0.35, 0]], ['TOP', [0.001, 1, 0.001]]]) {
    const b = document.createElement('button');
    b.className = 'hud-btn';
    b.textContent = name;
    b.onclick = () => { stage.camera.position.set(pos[0] * d, pos[1] * d, pos[2] * d); stage.controls.target.set(0, size.y / 2, 0); };
    camRow.appendChild(b);
  }
  views.appendChild(camRow);
  // Parts list: one section per category (printed parts, bought parts, the board...), each with a show/hide-all box.
  const syncGroups = [];
  const categories = [...new Set(parts.map((p) => p.category ?? ''))];
  for (const category of categories) {
    const members = parts.filter((p) => (p.category ?? '') === category);
    // a section whose parts all start hidden (a reference board, variants) starts folded
    const list = section(controlsHost, category || 'Parts', { note: categories.length > 1 ? `${members.length} parts` : 'show · colour',
                                                       open: categories.length === 1 || members.some((p) => p.mesh.visible) });
    const rows = [];
    let all = null;
    const syncAll = () => {
      if (!all) return;
      const on = members.filter((p) => p.mesh.visible).length;
      all.checked = on === members.length;
      all.indeterminate = on > 0 && on < members.length;
    };
    if (categories.length > 1) {
      const head = document.createElement('div');
      head.className = 'hud-toggle';
      head.innerHTML = `<input type="checkbox"><span><b>All ${esc((category || 'other parts').toLowerCase())}</b></span>`;
      all = head.querySelector('input');
      all.onchange = () => {
        const groupNames = members.map(p => p.name);
        state.visible = all.checked ? [...new Set([...state.visible, ...groupNames])] : state.visible.filter(n => !groupNames.includes(n));
        visibilityChanged();
        members.forEach((p, i) => { rows[i].checked = p.mesh.visible; });
        syncAll();
        shownReadout();
      };
      list.appendChild(head);
    }
    for (const p of members) {
      const row = document.createElement('div');
      row.className = 'hud-toggle';
      row.innerHTML = `<input type="checkbox" ${p.mesh.visible ? 'checked' : ''}><input type="color" value="${esc(p.color)}" `
        + `style="width:18px;height:18px;border:0;padding:0;background:none"><span>${esc(p.id ? p.id + ' · ' : '')}${esc(p.name.replaceAll('_', ' '))}</span>`;
      const [vis, col] = row.querySelectorAll('input');
      vis.onchange = () => { state.visible = vis.checked ? [...new Set([...state.visible, p.name])] : state.visible.filter(n => n !== p.name); visibilityChanged(); syncAll(); };
      col.oninput = () => { userColors.set(p.name, new THREE.Color(col.value)); p.mesh.material.color.set(col.value); };
      vis.dataset.part = p.name;
      rows.push(vis);
      list.appendChild(row);
    }
    syncAll(); syncGroups.push(syncAll);
  }
  const userColors = new Map();
  const baseline = new Map(parts.map(p => [p.name, { visible: p.mesh.visible, color: p.mesh.material.color.clone() }]));
  const names = parts.map(p => p.name);
  let state = { visible: parts.filter(p => p.mesh.visible).map(p => p.name), highlight: [], mode: 'solid', offsets_mm: {}, selected: null, isolate: null, partModes: {} };
  const opening = { position: stage.camera.position.clone(), target: stage.controls.target.clone() };
  const ensureLive = () => { if (disposed) throw new Error('Viewer is disposed'); };
  function visibilityChanged() {
    state.partModes = Object.fromEntries(Object.entries(state.partModes).filter(([name]) => state.visible.includes(name)));
    state.highlight = state.highlight.filter(n => state.visible.includes(n));
    if (!state.visible.includes(state.selected)) state.selected = null;
    if (state.isolate !== null) state.isolate = state.isolate.filter(n => state.visible.includes(n));
    applyState(state);
  }
  function applyState(next) {
    ensureLive(); validateState(next, names);
    const nextState = structuredClone({ ...next, partModes: next.partModes ?? {} });
    const previousSelection = state.selected;
    for (const p of parts) {
      const m = p.mesh.material, highlighted = next.highlight.includes(p.name);
      p.mesh.visible = next.visible.includes(p.name) && (next.isolate === null || next.isolate.includes(p.name));
      p.mesh.position.fromArray(Object.hasOwn(next.offsets_mm, p.name) ? next.offsets_mm[p.name] : [0, 0, 0]);
      m.color.copy(userColors.get(p.name) || baseline.get(p.name).color);
      m.emissive.setHex(next.selected === p.name ? 0x005588 : highlighted ? 0x5a2700 : 0);
      const partMode = Object.hasOwn(nextState.partModes, p.name) ? nextState.partModes[p.name] : null;
      m.wireframe = partMode ? partMode === 'wireframe' : next.mode === 'wireframe';
      m.opacity = partMode ? (partMode === 'transparent' ? 0.2 : 1) : next.mode === 'ghost' && !highlighted ? 0.2 : 1;
      m.transparent = m.opacity < 1; m.depthWrite = !m.transparent; m.needsUpdate = true;
    }
    state = nextState;
    // Existing visibility controls reflect programmatic step state too.
    for (const input of controlsHost.querySelectorAll('input[data-part]')) input.checked = parts.find(p => p.name === input.dataset.part).mesh.visible;
    syncGroups.forEach(sync => sync());
    shownReadout(); model.updateMatrixWorld(true);
    if (state.selected !== previousSelection) onSelect(state.selected);
    onStateChange(structuredClone(state));
    return structuredClone(state);
  }
  function updateInsets() {
    const a = app.getBoundingClientRect(), p = panel.getBoundingClientRect();
    const header = title?.closest('header')?.getBoundingClientRect();
    const vertical = Math.min(a.bottom, p.bottom) - Math.max(a.top, p.top);
    const horizontal = Math.min(a.right, p.right) - Math.max(a.left, p.left);
    stage.setInsets({ top: header ? Math.max(0, Math.min(a.height - 1, header.bottom - a.top)) : 0,
      right: vertical > 0 && horizontal > 0 && p.left > a.left + a.width / 2 ? a.right - p.left : 0,
      bottom: vertical > 0 && horizontal > 0 && p.top > a.top + a.height / 2 ? a.bottom - p.top : 0 });
  }
  function frameParts(selected = state.visible, direction) {
    ensureLive();
    validateState({ visible: selected, highlight: [], mode: 'solid', offsets_mm: {}, selected: null, isolate: null }, names);
    if (direction) {
      if (!Array.isArray(direction) || direction.length !== 3 || !direction.every(Number.isFinite) || !direction.some(n => n !== 0)) throw new Error('Invalid camera direction');
    }
    model.updateMatrixWorld(true);
    const points = [];
    for (const p of parts.filter(p => selected.includes(p.name) && p.mesh.visible)) {
      const b = new THREE.Box3().setFromObject(p.mesh);
      if (!b.isEmpty()) for (let i = 0; i < 8; i++) points.push(new THREE.Vector3(i & 1 ? b.max.x : b.min.x, i & 2 ? b.max.y : b.min.y, i & 4 ? b.max.z : b.min.z));
    }
    if (points.length) {
      const result = stage.fitView(points, { direction: direction ? new THREE.Vector3(direction[0], direction[2], -direction[1]) : stage.camera.position.clone().sub(stage.controls.target) });
      stage.camera.updateMatrixWorld(true); return result;
    }
  }
  function setSelection(name) {
    applyState({ ...state, selected: name });
  }
  function setPartMode(name, mode) {
    ensureLive();
    if (!state.visible.includes(name)) throw new Error('Part appearance needs a visible instance');
    const entries = Object.entries(state.partModes).filter(([key]) => key !== name);
    if (mode !== null) entries.push([name, mode]);
    return applyState({ ...state, partModes: Object.fromEntries(entries) });
  }
  function reset() {
    ensureLive(); userColors.clear();
    applyState({ visible: parts.filter(p => baseline.get(p.name).visible).map(p => p.name), highlight: [], mode: 'solid', offsets_mm: {}, selected: null, isolate: null, partModes: {} });
    explodeSlider?.set(0); setSection(1); stage.camera.position.copy(opening.position); stage.controls.target.copy(opening.target); stage.controls.update(); stage.camera.updateMatrixWorld(true);
  }
  const ray = new THREE.Raycaster(), pointer = new THREE.Vector2();
  let down;
  const canvas = stage.renderer.domElement;
  canvas.addEventListener('pointerdown', e => { down = [e.clientX, e.clientY]; }, { signal: events.signal });
  canvas.addEventListener('pointerup', e => {
    if (!down || Math.hypot(e.clientX - down[0], e.clientY - down[1]) > 5) return;
    const rect = canvas.getBoundingClientRect();
    pointer.set(2 * (e.clientX - rect.left) / rect.width - 1, 1 - 2 * (e.clientY - rect.top) / rect.height);
    stage.camera.updateMatrixWorld(true); model.updateMatrixWorld(true);
    ray.setFromCamera(pointer, stage.camera);
    const hit = ray.intersectObjects(parts.filter(p => p.mesh.visible).map(p => p.mesh))[0];
    setSelection(parts.find(p => p.mesh === hit?.object)?.name || null);
  }, { signal: events.signal });
  updateInsets(); frameParts(state.visible);
  opening.position.copy(stage.camera.position); opening.target.copy(stage.controls.target);
  window.addEventListener('resize', () => { if (!disposed) { updateInsets(); frameParts(state.visible); } }, { signal: events.signal });
  stage.start(); stage.renderer.render(stage.scene, stage.camera);
  await new Promise((resolve, reject) => {
    let frame;
    const aborted = () => { cancelAnimationFrame(frame); reject(lifetime.signal.reason); };
    frame = requestAnimationFrame(() => { lifetime.signal.removeEventListener('abort', aborted); resolve(); });
    lifetime.signal.addEventListener('abort', aborted, { once: true });
    if (lifetime.signal.aborted) aborted();
  });
  lifetime.signal.throwIfAborted(); clearTimeout(timer);
  onProgress('Model ready');
  return { stage, parts, setExplode, setSection, applyState, getState: () => structuredClone(state), frameParts, setSelection, setPartMode, reset, dispose };
  } catch (error) { dispose(); throw error; }
}
