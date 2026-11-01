/** <cad-model>: a CAD assembly in 3D on any page, from a model packed by `cadagent.view.pack_view` (a `cad-agent view`
 * export, welded, quantised and gzip-compressed: a 58-part robot is about 300 KB).
 *
 *   <link rel="stylesheet" href="/kit/model.css">
 *   <script type="module" src="/kit/model.js"></script>
 *   <cad-model src="/models/robot.json" label="Robot">
 *     <img class="cad-model-poster" src="/models/robot.webp" width="1200" height="1000" alt="The robot, assembled">
 *   </cad-model>
 *
 * The poster shows first and keeps the box's size (give the element an aspect-ratio, or let the poster set it), so
 * nothing moves when the 3D view arrives. three.js and the model load only after the page has loaded, when the
 * element is near the screen and the browser is idle; with Save-Data on, a button loads them instead. The model
 * turns slowly (not with reduced motion; a button pauses it), turns under a drag (vertical swipes still scroll the
 * page on touch screens), names the part under the pointer or a tap, and comes apart with "Explode". No wheel zoom,
 * so the page scrolls normally. Rendering stops while the element is off screen or the tab is hidden. Without WebGL
 * or DecompressionStream the poster stays (data-state="error").
 *
 * Attributes: src (required), label, azimuth and elevation (the opening view in degrees; default the model's own
 * `view`, else 35 and 18; azimuth 0 looks from the CAD -y side, 90 from +x), turn
 * (degrees per second, default 10; 0 for none), loading="eager" (start without waiting for the page to load).
 * Properties: ready (a promise), snapshot(width, height, type, quality) (a data: URL of one frame at that size;
 * tools/site-model-poster.mjs makes the poster with it), setExplode(0..1), view(azimuth, elevation).
 * three.js is imported from ./vendor/three/ next to this file, without an import map, so pages with a strict
 * Content-Security-Policy (no inline script) can use it.
 */

const KIT = new URL('.', import.meta.url);
const reduced = () => typeof matchMedia === 'function' && matchMedia('(prefers-reduced-motion: reduce)').matches;
const NAMES = { l: 'left', r: 'right' };
/** "hip_motor_plate_l" → "hip motor plate (left)". */
export const partLabel = name => String(name).replace(/_(l|r)$/, (m, s) => ` (${NAMES[s]})`).replace(/_/g, ' ');

/** The inflated binary: gzip (checked by its magic number, so a server that already decoded it is fine) or raw. */
export async function inflate(buffer) {
  const bytes = new Uint8Array(buffer);
  if (bytes[0] !== 0x1f || bytes[1] !== 0x8b) return bytes;
  const stream = new Blob([bytes]).stream().pipeThrough(new DecompressionStream('gzip'));
  return new Uint8Array(await new Response(stream).arrayBuffer());
}

/** [{ positions: Float32Array (mm, x y z per vertex), index: Uint16Array | Uint32Array }] per part, the inverse of
 * pack_view (cadagent/view.py documents the layout; unpack_model there is the reference the tests compare with). */
export function decodeModel(model, raw) {
  const [x0, y0, z0, x1, y1, z1] = model.box_mm, lo = [x0, y0, z0];
  const step = [x1 - x0, y1 - y0, z1 - z0].map(s => (s > 0 ? s : 1) / model.quant);
  return model.parts.map(part => {
    const n = part.vertices, m = 3 * part.triangles, width = part.index_bits / 8;
    let at = part.offset;
    if (at + 6 * n + width * m > raw.length) throw new Error(`${part.name}: the binary is shorter than the model says`);
    const positions = new Float32Array(3 * n);
    for (let axis = 0; axis < 3; axis++) {
      const low = at + 2 * n * axis, high = low + n;
      let q = 0;
      for (let i = 0; i < n; i++) {
        q = (q + (raw[low + i] | (raw[high + i] << 8))) & 0xffff;
        positions[3 * i + axis] = lo[axis] + q * step[axis];
      }
    }
    at += 6 * n;
    const index = width === 2 ? new Uint16Array(m) : new Uint32Array(m);
    let fresh = 0;
    for (let i = 0; i < m; i++) {
      let code = 0;
      for (let b = 0; b < width; b++) code += raw[at + b * m + i] * 2 ** (8 * b);
      const v = fresh - code;
      if (v < 0) throw new Error(`${part.name}: corner ${i} names a vertex that does not exist yet`);
      index[i] = v;
      if (v === fresh) fresh++;
    }
    if (fresh > n) throw new Error(`${part.name}: more vertices used than stored`);
    return { positions, index };
  });
}

/** Flat-and-smooth shading for CAD: each corner's normal averages the faces around its vertex that meet its own face
 * at less than `crease` radians (area-weighted), so cylinders read round and box edges stay sharp. Returns
 * non-indexed { positions, normals }. */
export function creasedNormals(positions, index, crease = 0.6) {
  const faces = index.length / 3, nVert = positions.length / 3, cos = Math.cos(crease);
  const fn = new Float32Array(3 * faces), unit = new Float32Array(3 * faces);
  for (let f = 0; f < faces; f++) {
    const a = 3 * index[3 * f], b = 3 * index[3 * f + 1], c = 3 * index[3 * f + 2];
    const ux = positions[b] - positions[a], uy = positions[b + 1] - positions[a + 1], uz = positions[b + 2] - positions[a + 2];
    const vx = positions[c] - positions[a], vy = positions[c + 1] - positions[a + 1], vz = positions[c + 2] - positions[a + 2];
    const nx = uy * vz - uz * vy, ny = uz * vx - ux * vz, nz = ux * vy - uy * vx, len = Math.hypot(nx, ny, nz) || 1;
    fn[3 * f] = nx; fn[3 * f + 1] = ny; fn[3 * f + 2] = nz;             // length = twice the area: the weight
    unit[3 * f] = nx / len; unit[3 * f + 1] = ny / len; unit[3 * f + 2] = nz / len;
  }
  const start = new Uint32Array(nVert + 1);                              // faces around each vertex (CSR)
  for (let i = 0; i < index.length; i++) start[index[i] + 1]++;
  for (let v = 0; v < nVert; v++) start[v + 1] += start[v];
  const fill = start.slice(0, nVert), around = new Uint32Array(index.length);
  for (let i = 0; i < index.length; i++) around[fill[index[i]]++] = (i / 3) | 0;
  const outP = new Float32Array(3 * index.length), outN = new Float32Array(3 * index.length);
  for (let i = 0; i < index.length; i++) {
    const v = index[i], f = (i / 3) | 0;
    outP[3 * i] = positions[3 * v]; outP[3 * i + 1] = positions[3 * v + 1]; outP[3 * i + 2] = positions[3 * v + 2];
    let x = 0, y = 0, z = 0;
    for (let k = start[v]; k < start[v + 1]; k++) {
      const g = around[k];
      if (unit[3 * f] * unit[3 * g] + unit[3 * f + 1] * unit[3 * g + 1] + unit[3 * f + 2] * unit[3 * g + 2] < cos) continue;
      x += fn[3 * g]; y += fn[3 * g + 1]; z += fn[3 * g + 2];
    }
    const len = Math.hypot(x, y, z);
    if (len > 0) { outN[3 * i] = x / len; outN[3 * i + 1] = y / len; outN[3 * i + 2] = z / len; }
    else { outN[3 * i] = unit[3 * f]; outN[3 * i + 1] = unit[3 * f + 1]; outN[3 * i + 2] = unit[3 * f + 2]; }
  }
  return { positions: outP, normals: outN };
}

const BUTTON = (label, pressed) => {
  const b = document.createElement('button');
  b.type = 'button';
  b.className = 'cad-model-btn';
  b.textContent = label;
  if (pressed !== undefined) b.setAttribute('aria-pressed', String(pressed));
  return b;
};

// Node (the decoder's tests) has no HTMLElement: the element is only defined in a browser.
class CadModel extends (typeof HTMLElement === 'undefined' ? class {} : HTMLElement) {
  #started = false;
  #resolve;
  ready = new Promise(r => { this.#resolve = r; });

  connectedCallback() {
    if (this.#started) return;
    this.dataset.state ||= 'poster';
    const go = () => this.#start();
    if (this.getAttribute('loading') === 'eager') return go();
    if (navigator.connection?.saveData) {
      const b = BUTTON('Load the 3D model');
      b.classList.add('cad-model-load');
      b.addEventListener('click', () => { b.remove(); go(); }, { once: true });
      this.append(b);
      return;
    }
    const whenLoaded = document.readyState === 'complete' ? Promise.resolve() : new Promise(r => addEventListener('load', r, { once: true }));
    whenLoaded.then(() => {
      const io = new IntersectionObserver(entries => {
        if (!entries.some(e => e.isIntersecting)) return;
        io.disconnect();
        (window.requestIdleCallback || (cb => setTimeout(cb, 1)))(go, { timeout: 1500 });
      }, { rootMargin: '300px' });
      io.observe(this);
    });
  }

  async #start() {
    if (this.#started) return;
    this.#started = true;
    this.dataset.state = 'loading';
    try {
      const src = new URL(this.getAttribute('src'), location.href);
      const [THREE, model] = await Promise.all([import(new URL('vendor/three/three.module.min.js', KIT).href),
        fetch(src).then(r => { if (!r.ok) throw new Error(`${src.pathname}: HTTP ${r.status}`); return r.json(); })]);
      if (model.schema !== 'cad-agent-model/1') throw new Error(`unknown model schema ${model.schema}`);
      const bin = await fetch(new URL(model.bin, src)).then(r => { if (!r.ok) throw new Error(`${model.bin}: HTTP ${r.status}`); return r.arrayBuffer(); });
      const parts = decodeModel(model, await inflate(bin));
      this.#build(THREE, model, parts);
      this.dataset.state = 'ready';
      this.#resolve(this);
    } catch (err) {
      this.dataset.state = 'error';
      this.dataset.error = String(err?.message ?? err).slice(0, 300);
      this.#resolve(this);
    }
  }

  #build(THREE, model, decoded) {
    const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true, powerPreference: 'low-power', preserveDrawingBuffer: false });
    renderer.setPixelRatio(Math.min(devicePixelRatio || 1, 2));
    renderer.toneMapping = THREE.ACESFilmicToneMapping;
    renderer.toneMappingExposure = 1.05;
    renderer.shadowMap.enabled = true;
    renderer.shadowMap.type = THREE.PCFShadowMap;           // honours shadow.radius (PCFSoft does not)
    const canvas = renderer.domElement;
    canvas.className = 'cad-model-canvas';
    canvas.setAttribute('role', 'img');
    canvas.setAttribute('aria-label', `${this.getAttribute('label') || model.title}: a 3D model you can turn by dragging`);

    const scene = new THREE.Scene();
    scene.add(new THREE.HemisphereLight(0xffffff, 0xb9c8c0, 1.6));
    const key = new THREE.DirectionalLight(0xffffff, 2.4);
    key.castShadow = true;
    key.shadow.mapSize.set(2048, 2048);
    key.shadow.radius = 3;
    const fill = new THREE.DirectionalLight(0xdbe9ff, 0.8), rim = new THREE.DirectionalLight(0xffe2c4, 0.9);
    scene.add(key, key.target, fill, rim);

    const zUp = new THREE.Group();                      // CAD is z-up; three.js is y-up
    zUp.rotation.x = -Math.PI / 2;
    const meshes = [];
    model.parts.forEach((part, i) => {
      const { positions, normals } = creasedNormals(decoded[i].positions, decoded[i].index);
      const geo = new THREE.BufferGeometry();
      geo.setAttribute('position', new THREE.BufferAttribute(positions, 3));
      geo.setAttribute('normal', new THREE.BufferAttribute(normals, 3));
      geo.computeBoundingSphere();
      const mat = new THREE.MeshStandardMaterial({ color: part.color, roughness: 0.62, metalness: 0.05 });
      const mesh = new THREE.Mesh(geo, mat);
      mesh.castShadow = mesh.receiveShadow = true;
      mesh.visible = part.visible !== false;
      mesh.userData.part = part;
      zUp.add(mesh);
      meshes.push(mesh);
    });
    const holder = new THREE.Group();
    holder.add(zUp);
    scene.add(holder);
    zUp.updateMatrixWorld(true);
    const box = new THREE.Box3().setFromObject(zUp), size = box.getSize(new THREE.Vector3()), mid = box.getCenter(new THREE.Vector3());
    zUp.position.set(-mid.x, -box.min.y, -mid.z);        // stand it on the floor, centred
    const radius = size.length() / 2, centre = new THREE.Vector3(0, size.y / 2, 0);

    // Exploded view: each part slides away from the assembly's centre (or along its own explode direction).
    const middle = new THREE.Vector3();
    const centres = model.parts.map(p => { const b = p.bounds_mm || [0, 0, 0, 0, 0, 0]; return new THREE.Vector3((b[0] + b[3]) / 2, (b[1] + b[4]) / 2, (b[2] + b[5]) / 2); });
    centres.forEach(c => middle.add(c));
    middle.divideScalar(Math.max(1, centres.length));
    const dirs = model.parts.map((p, i) => {
      const d = p.explode ? new THREE.Vector3(...p.explode) : centres[i].clone().sub(middle);
      return d.lengthSq() > 1e-9 ? d.normalize() : new THREE.Vector3(0, 0, 1);
    });
    const reach = Math.max(size.x, size.y, size.z) * 0.2;
    let explode = 0;
    const setExplode = f => { explode = f; meshes.forEach((m, i) => m.position.copy(dirs[i]).multiplyScalar(f * reach)); fit(); place(); };

    const floor = new THREE.Mesh(new THREE.PlaneGeometry(radius * 12, radius * 12), new THREE.ShadowMaterial({ opacity: 0.16 }));
    floor.rotation.x = -Math.PI / 2;
    floor.receiveShadow = true;
    scene.add(floor);
    key.position.set(radius * 1.6, radius * 3.2, radius * 1.4);
    Object.assign(key.shadow.camera, { left: -radius * 1.6, right: radius * 1.6, top: radius * 1.6, bottom: -radius * 1.6, near: radius * 0.5, far: radius * 8 });
    key.shadow.camera.updateProjectionMatrix();
    key.shadow.bias = -0.0004;
    key.shadow.normalBias = radius * 0.004;
    fill.position.set(-radius * 2.5, radius * 1.2, radius * 1.5);
    rim.position.set(-radius * 1.5, radius * 2, -radius * 2.5);

    const camera = new THREE.PerspectiveCamera(28, 1, radius * 0.05, radius * 20);
    const deg = Math.PI / 180;
    const num = (name, fallback) => {             // the attribute, else the model's own opening view, else the default
      const v = parseFloat(this.getAttribute(name)), own = Number(model.view?.[name]);
      return Number.isFinite(v) ? v : Number.isFinite(own) ? own : fallback;
    };
    const view = { az: num('azimuth', 35) * deg, el: num('elevation', 18) * deg };
    let distance = radius * 3;
    // The bounding sphere (grown by the explode) fits both ways; 0.94 of it, since a sphere is looser than the parts.
    const fit = () => {
      const vfov = camera.fov * deg / 2, hfov = Math.atan(Math.tan(vfov) * camera.aspect);
      distance = (radius + explode * reach) * 0.94 / Math.sin(Math.min(vfov, hfov));
    };
    const place = () => {
      camera.position.set(Math.sin(view.az) * Math.cos(view.el), Math.sin(view.el), Math.cos(view.az) * Math.cos(view.el))
        .multiplyScalar(distance).add(centre);
      camera.lookAt(centre);
    };

    // Controls: drag turns (inertia after release), slow turntable when idle, hover or tap names the part.
    const speed = num('turn', 10) * deg;
    let turning = !reduced() && speed !== 0;
    let paused = false, drag = null, spin = 0, lastInput = -1e9, hovered = null, anim = null, frame = 0, visible = true;
    const ui = document.createElement('div');
    ui.className = 'cad-model-ui';
    const label = document.createElement('p');
    label.className = 'cad-model-label';
    label.textContent = 'Drag to turn';
    const pause = BUTTON('Pause', false), apart = BUTTON('Explode', false);
    if (!turning) pause.hidden = true;
    ui.append(label, apart, pause);
    const ray = new THREE.Raycaster(), pointer = new THREE.Vector2();
    const pick = (x, y) => {
      const r = canvas.getBoundingClientRect();
      pointer.set(((x - r.left) / r.width) * 2 - 1, -((y - r.top) / r.height) * 2 + 1);
      ray.setFromCamera(pointer, camera);
      return ray.intersectObjects(meshes, false)[0]?.object ?? null;
    };
    const highlight = mesh => {
      if (hovered === mesh) return;
      if (hovered) hovered.material.emissive.setHex(0x000000);
      hovered = mesh;
      if (mesh) mesh.material.emissive.setHex(0x3a2008);
      label.textContent = mesh ? partLabel(mesh.userData.part.name) : 'Drag to turn';
      request();
    };
    canvas.style.touchAction = 'pan-y';
    canvas.addEventListener('pointerdown', e => {
      drag = { id: e.pointerId, x: e.clientX, y: e.clientY, moved: 0, t: performance.now() };
      spin = 0; lastInput = performance.now();
      canvas.setPointerCapture?.(e.pointerId);
    });
    canvas.addEventListener('pointermove', e => {
      if (drag && e.pointerId === drag.id) {
        const dx = e.clientX - drag.x, dy = e.clientY - drag.y, dt = Math.max(1, performance.now() - drag.t);
        drag.moved += Math.abs(dx) + Math.abs(dy);
        view.az -= dx * 0.0085;
        view.el = Math.min(70 * deg, Math.max(-4 * deg, view.el + dy * 0.006));
        spin = -dx * 0.0085 / dt * 1000;
        Object.assign(drag, { x: e.clientX, y: e.clientY, t: performance.now() });
        lastInput = performance.now();
        request();
      } else if (e.pointerType === 'mouse') highlight(pick(e.clientX, e.clientY));
    });
    const release = e => {
      if (!drag || e.pointerId !== drag.id) return;
      if (drag.moved < 6) highlight(pick(e.clientX, e.clientY));   // a tap or click names the part
      if (performance.now() - drag.t > 80) spin = 0;
      drag = null;
      lastInput = performance.now();
      request();
    };
    canvas.addEventListener('pointerup', release);
    canvas.addEventListener('pointercancel', e => { if (drag && e.pointerId === drag.id) { drag = null; spin = 0; } });
    canvas.addEventListener('pointerleave', e => { if (e.pointerType === 'mouse' && !drag) highlight(null); });
    pause.addEventListener('click', () => {
      paused = !paused;
      pause.setAttribute('aria-pressed', String(paused));
      pause.textContent = paused ? 'Turn' : 'Pause';
      lastInput = -1e9;
      request();
    });
    apart.addEventListener('click', () => {
      const to = explode > 0.5 ? 0 : 1;
      apart.setAttribute('aria-pressed', String(to === 1));
      if (reduced()) { setExplode(to); request(); return; }
      anim = { from: explode, to, t0: performance.now() };
      request();
    });

    const resize = () => {
      const w = this.clientWidth || 1, h = this.clientHeight || 1;
      renderer.setSize(w, h, false);
      camera.aspect = w / h;
      camera.updateProjectionMatrix();
      fit();
      place();
      request();
    };
    let last = performance.now();
    const tick = now => {
      frame = 0;
      const dt = Math.min(0.05, (now - last) / 1000);
      last = now;
      let more = false;
      if (anim) {
        const k = Math.min(1, (now - anim.t0) / 900), ease = k < 0.5 ? 4 * k ** 3 : 1 - (-2 * k + 2) ** 3 / 2;
        setExplode(anim.from + (anim.to - anim.from) * ease);
        if (k >= 1) anim = null; else more = true;
      }
      if (!drag && Math.abs(spin) > 0.01) { view.az += spin * dt; spin *= Math.exp(-dt * 4); more = true; }
      if (turning && !paused && !drag && now - lastInput > 4000) { view.az += speed * dt; more = true; }
      place();
      renderer.render(scene, camera);
      if (more && visible) frame = requestAnimationFrame(tick);
    };
    function request() { if (!frame && visible) { last = performance.now(); frame = requestAnimationFrame(tick); } }
    new ResizeObserver(resize).observe(this);
    new IntersectionObserver(es => {
      visible = es.some(e => e.isIntersecting) && document.visibilityState === 'visible';
      if (visible) request(); else if (frame) { cancelAnimationFrame(frame); frame = 0; }
    }).observe(this);
    document.addEventListener('visibilitychange', () => {
      visible = document.visibilityState === 'visible';
      if (visible) request();
    });
    matchMedia('(prefers-reduced-motion: reduce)').addEventListener?.('change', () => { turning = !reduced() && speed !== 0; pause.hidden = !turning; request(); });

    this.append(canvas, ui);
    resize();
    renderer.render(scene, camera);
    requestAnimationFrame(() => this.classList.add('cad-model-live'));   // the canvas fades in over the poster

    this.setExplode = f => { setExplode(Math.max(0, Math.min(1, f))); request(); };
    this.view = (azimuth, elevation) => { view.az = azimuth * deg; view.el = elevation * deg; lastInput = performance.now(); request(); };
    this.snapshot = (width, height, type = 'image/png', quality = 0.9) => {
      const old = [renderer.getPixelRatio(), this.clientWidth, this.clientHeight];
      renderer.setPixelRatio(1);
      renderer.setSize(width, height, false);
      camera.aspect = width / height;
      camera.updateProjectionMatrix();
      fit();
      place();
      renderer.render(scene, camera);
      const url = canvas.toDataURL(type, quality);
      renderer.setPixelRatio(old[0]);
      resize();
      return url;
    };
    this.stats = { parts: meshes.length, triangles: model.triangles, bytes: model.bytes };
  }
}

if (typeof customElements !== 'undefined' && !customElements.get('cad-model')) customElements.define('cad-model', CadModel);
