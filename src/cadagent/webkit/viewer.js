// A 3D viewer for any CAD project's assembly: loads exports/view/view.json (written by `cad-agent view`), shows every
// part in place, and gives a parts list (show/hide, colour), an exploded view, a section cut and standard views.
// Housings, brackets, mechanisms and robots all work the same way.
import * as THREE from 'three';
import { STLLoader } from 'three/addons/loaders/STLLoader.js';
import { createStage } from './stage.js';
import { section, slider, toggle, readouts } from './panel.js';

const esc = (s) => String(s ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));

/** createViewer({ app, panel, title, manifestUrl }) -> Promise<{ stage, parts, setExplode, setSection }> */
export async function createViewer({ app, panel, title, manifestUrl }) {
  const manifest = await (await fetch(manifestUrl)).json();
  const base = new URL('.', new URL(manifestUrl, location.href));
  if (title) title.textContent = manifest.title ?? 'Model';

  // CAD is z-up in mm; the stage is y-up in metres.
  const model = new THREE.Group();
  model.rotation.x = -Math.PI / 2;
  model.scale.setScalar(0.001);
  const loader = new STLLoader();
  const clip = new THREE.Plane(new THREE.Vector3(-1, 0, 0), 1e9);
  const parts = [];
  await Promise.all(manifest.parts.map(async (p) => {
    const geo = loader.parse(await (await fetch(new URL(p.file, base))).arrayBuffer());
    geo.computeVertexNormals();
    const mat = new THREE.MeshPhysicalMaterial({ color: p.color, roughness: 0.55, clearcoat: 0.2, clippingPlanes: [clip], clipShadows: true,
                                                 side: THREE.DoubleSide });
    const mesh = new THREE.Mesh(geo, mat);
    mesh.castShadow = mesh.receiveShadow = true;
    mesh.visible = p.visible !== false;
    model.add(mesh);
    const b = p.bounds_mm;
    parts.push({ ...p, mesh, center: new THREE.Vector3((b[0] + b[3]) / 2, (b[1] + b[4]) / 2, (b[2] + b[5]) / 2) });
  }));
  parts.sort((a, b) => manifest.parts.findIndex((p) => p.name === a.name) - manifest.parts.findIndex((p) => p.name === b.name));

  // Stand the model on the floor, centred.
  const box = new THREE.Box3().setFromObject(model);
  const size = box.getSize(new THREE.Vector3()), mid = box.getCenter(new THREE.Vector3());
  const holder = new THREE.Group();
  holder.add(model);
  model.position.set(-mid.x, -box.min.y, -mid.z);
  const height = Math.max(size.x, size.y, size.z);
  const stage = createStage(app, { height: height * 0.8, screenshots: true });
  stage.renderer.localClippingEnabled = true;
  stage.root.add(holder);

  // Exploded view: each part moves away from the assembly centre (or along its configured direction).
  const centre = new THREE.Vector3();
  parts.forEach((p) => centre.add(p.center));
  centre.divideScalar(Math.max(1, parts.length));
  const span = Math.max(size.x, size.y, size.z) * 1000;
  function setExplode(f) {
    for (const p of parts) {
      const dir = p.explode ? new THREE.Vector3(...p.explode).normalize() : p.center.clone().sub(centre);
      if (!p.explode) dir.lengthSq() > 1e-6 ? dir.normalize() : dir.set(0, 0, 1);
      p.mesh.position.copy(dir.multiplyScalar(f * span * 0.6));
    }
  }
  // Section cut along CAD x: everything beyond the plane is cut away.
  const xmin = box.min.x, xmax = box.max.x;
  function setSection(f) { clip.constant = f >= 1 ? 1e9 : -(xmin + (xmax - xmin) * f - mid.x); }

  // Panel
  const info = readouts(section(panel, 'Model', { note: `${parts.length} parts` }));
  info.set([['size', `${Math.round(size.x * 1000)} × ${Math.round(size.z * 1000)} × ${Math.round(size.y * 1000)} mm`],
            ['parts shown', String(parts.filter((p) => p.mesh.visible).length)],
            ...(manifest.skipped?.length ? [['without STEP', manifest.skipped.join(', '), 'warn']] : [])]);
  const views = section(panel, 'View');
  slider(views, { label: 'Explode', min: 0, max: 1, step: 0.01, value: 0, fmt: (v) => `${Math.round(v * 100)}%`, onInput: setExplode });
  slider(views, { label: 'Section cut', min: 0, max: 1, step: 0.01, value: 1, fmt: (v) => (v >= 1 ? 'off' : `${Math.round(v * 100)}%`), onInput: setSection });
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
  const list = section(panel, 'Parts', { note: 'show · colour' });
  for (const p of parts) {
    const row = document.createElement('div');
    row.className = 'hud-toggle';
    row.innerHTML = `<input type="checkbox" ${p.mesh.visible ? 'checked' : ''}><input type="color" value="${esc(p.color)}" `
      + `style="width:18px;height:18px;border:0;padding:0;background:none"><span>${esc(p.id ? p.id + ' · ' : '')}${esc(p.name.replaceAll('_', ' '))}</span>`;
    const [vis, col] = row.querySelectorAll('input');
    vis.onchange = () => { p.mesh.visible = vis.checked; };
    col.oninput = () => p.mesh.material.color.set(col.value);
    list.appendChild(row);
  }
  stage.start();
  return { stage, parts, setExplode, setSection };
}
