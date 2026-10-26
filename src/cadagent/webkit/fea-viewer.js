// FEA results viewer: the solved part from cadagent.fea Study.export_viewer(), deformed and coloured by a chosen field,
// with the load ramped live from zero, past the design load, to where the part first reaches its strength and beyond
// (regions past the strength turn black). Hot spots (click to fly there), held faces, load arrows, a section cut,
// and a readout of the value under the pointer. Linear elastic results, so every field scales with the load factor.
//
//   import { mountFeaViewer } from './kit/fea-viewer.js';
//   const v = await mountFeaViewer(document.getElementById('fea'), '../exports/fea/thigh-T1.json', { back: '../site/' });
//   v.setLoad(1.5); v.setField('sf'); v.flyTo(0); v.setClip('x', 0.4);
//
// The element gets the kit's page layout (#app stage, #hud with a top bar, overlays and a side panel; hud.css), so it
// is meant to own the page: kit/fea.html?case=<url> is a ready page.
import * as THREE from 'three';
import { createStage } from './stage.js';
import { section, slider, toggle, readouts, collapsiblePanel, overlayInsets } from './panel.js';

const esc = (s) => String(s ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
const clamp01 = (x) => (x < 0 ? 0 : x > 1 ? 1 : x);
const TYPES = { float32: Float32Array, uint32: Uint32Array, uint8: Uint8Array, int32: Int32Array, uint16: Uint16Array };

function decode(a) {
  const bin = atob(a.b64);
  const u8 = new Uint8Array(bin.length);
  for (let i = 0; i < bin.length; i++) u8[i] = bin.charCodeAt(i);
  return new TYPES[a.dtype](u8.buffer);
}

// Google's Turbo colour map (polynomial fit, sRGB), the same map the static renders and videos use.
function turbo(x) {
  x = clamp01(x);
  const r = 0.13572138 + x * (4.6153926 + x * (-42.66032258 + x * (132.13108234 + x * (-152.94239396 + x * 59.28637943))));
  const g = 0.09140261 + x * (2.19418839 + x * (4.84296658 + x * (-14.18503333 + x * (4.27729857 + x * 2.82956604))));
  const b = 0.1066733 + x * (12.64194608 + x * (-60.58204836 + x * (110.36276771 + x * (-89.90310912 + x * 27.34824973))));
  return [clamp01(r), clamp01(g), clamp01(b)];
}
// Turbo's ends are nearly black; the scale uses its middle so that black always means "past the strength".
const span = (x) => 0.07 + 0.86 * x;
const LUT_N = 256;
const LUT = (() => {
  const out = new Float32Array(LUT_N * 3), c = new THREE.Color();
  for (let i = 0; i < LUT_N; i++) {
    c.setRGB(...turbo(span(i / (LUT_N - 1))), THREE.SRGBColorSpace);   // vertex colours are linear
    out[i * 3] = c.r; out[i * 3 + 1] = c.g; out[i * 3 + 2] = c.b;
  }
  return out;
})();
const gradient = (reverse = false) => `linear-gradient(90deg, ${Array.from({ length: 11 }, (_, i) => {
  const [r, g, b] = turbo(span(reverse ? 1 - i / 10 : i / 10));
  return `rgb(${Math.round(r * 255)}, ${Math.round(g * 255)}, ${Math.round(b * 255)}) ${i * 10}%`;
}).join(', ')})`;
const linear = (hex) => new THREE.Color(hex);           // THREE.Color(hex) converts sRGB hex to linear
const HELD = linear(0x9ea3ad), FAILED = linear(0x0d0d0d);

const SF_RANGE = 4;                                    // the local safety factor colour scale runs 0 .. 4+
const FIELDS = {
  ratio: { label: 'Stress / strength', short: 'σ/σ', note: 'von Mises over the material strength; 1 = it fails there' },
  stress: { label: 'Stress (MPa)', short: 'MPa', note: 'von Mises stress' },
  sf: { label: 'Local safety factor', short: 'SF', note: 'strength over the local stress at this load' },
  disp: { label: 'Displacement (mm)', short: 'mm', note: 'how far each point moves' },
};

const fmtN = (n) => (Math.abs(n) >= 1000 ? `${(n / 1000).toFixed(2)} kN` : `${n.toFixed(0)} N`);
const fmt = (v, d = 2) => (v == null || !isFinite(v) ? '—' : Number(v).toFixed(d));

const CSS = `
.fea-status{left:16px;top:16px;font:11px/1.55 var(--font-mono);color:var(--text-dim);max-width:min(440px,calc(100% - 32px))}
.fea-status .l1{font-weight:700;letter-spacing:.06em;color:var(--cyan)}
.fea-status.over .l1{color:var(--magenta)} .fea-status .bad{color:var(--magenta)}
.fea-legend{top:auto;bottom:34px;left:16px;width:min(320px,calc(100% - 32px));font:10px/1.4 var(--font-mono);color:var(--text-dim)}
.fea-legend .bar{height:10px;border-radius:2px;margin:5px 0 3px;border:1px solid rgba(255,255,255,.08)}
.fea-legend .ticks{display:flex;justify-content:space-between;color:var(--muted)}
.fea-legend .keys{display:flex;flex-wrap:wrap;gap:3px 12px;margin-top:6px;color:var(--muted)}
.fea-legend .sw{display:inline-block;width:9px;height:9px;border-radius:2px;margin-right:5px;vertical-align:-1px}
.fea-labels{position:fixed;inset:0;z-index:3;pointer-events:none;overflow:hidden}
.fea-label{position:absolute;left:0;top:0;width:20px;height:20px;margin:-10px 0 0 -10px;border-radius:50%;border:0;padding:0;
font:700 10px/20px var(--font-mono);text-align:center;color:#060609;background:var(--amber);cursor:pointer;pointer-events:auto;
box-shadow:0 0 0 2px rgba(6,6,9,.75),0 0 12px rgba(252,238,10,.45)}
.fea-label.fail{background:var(--magenta);box-shadow:0 0 0 2px rgba(6,6,9,.75),0 0 12px rgba(255,42,109,.55)}
.fea-label.dim{opacity:.38}
.fea-label.on{outline:2px solid var(--cyan);outline-offset:2px}
.fea-load{position:absolute;left:0;top:0;padding:1px 6px;border-radius:4px;background:rgba(6,6,9,.78);color:#ff5c8d;font:600 10px var(--font-mono);
border:1px solid rgba(255,42,109,.5);white-space:nowrap;transform:translate(-50%,-140%)}
.fea-tip{position:fixed;z-index:6;pointer-events:none;background:rgba(14,14,20,.95);border:1px solid var(--hairline);border-radius:6px;
padding:6px 9px;font:11px/1.5 var(--font-mono);color:var(--text-dim);max-width:270px;box-shadow:0 4px 18px rgba(0,0,0,.5)}
.fea-tip b{color:var(--text);font-weight:600} .fea-tip .bad{color:var(--magenta)} .fea-tip .dim{color:var(--muted)}
.fea-spots{display:grid;gap:6px}
.fea-spot{display:grid;grid-template-columns:22px 1fr auto;gap:1px 8px;align-items:baseline;text-align:left;width:100%;padding:7px 8px;
border:1px solid var(--hairline);border-radius:6px;background:var(--surface-2);color:var(--text-dim);font:11px/1.4 var(--font-mono);cursor:pointer}
.fea-spot:hover,.fea-spot.on{border-color:var(--cyan);box-shadow:0 0 10px var(--glow-12)}
.fea-spot .n{grid-row:span 2;width:20px;height:20px;border-radius:50%;background:var(--amber);color:#060609;font-weight:700;text-align:center;line-height:20px;align-self:center}
.fea-spot.fail .n{background:var(--magenta)}
.fea-spot .f{color:var(--amber);font-weight:600;white-space:nowrap} .fea-spot.fail .f{color:var(--magenta)}
.fea-spot .h{grid-column:2/-1;color:var(--muted)}
.fea-spot .m{grid-column:2/-1;color:var(--amber);font-size:10px}
.fea-marks{position:relative;height:16px;margin:-2px 6px 0;font:9px var(--font-mono);color:var(--muted)}
.fea-marks span{position:absolute;top:3px;transform:translateX(-50%);white-space:nowrap}
.fea-marks span::before{content:"";position:absolute;left:50%;top:-4px;width:1px;height:4px;background:currentColor}
.fea-marks span.fail{color:var(--magenta)}
.fea-row{display:flex;flex-wrap:wrap;gap:6px}
.fea-row .hud-btn{padding:7px 10px}
.fea-row .hud-btn.on{border-color:var(--cyan);color:var(--cyan);background:var(--glow-06)}
.fea-note{font-size:12px;color:var(--muted);margin:0;line-height:1.5}
@media (max-width:820px){.fea-status{font-size:10px;line-height:1.4;padding:6px 8px;top:8px;left:8px}.fea-legend{bottom:8px;left:8px;padding:6px 8px}
.fea-legend .keys{gap:2px 8px;margin-top:4px} #stage-overlay .hud-hint{display:none}
#hud{grid-template-rows:auto minmax(0,1fr) 38vh}}
`;

/**
 * mountFeaViewer(element, url, { title, back, backLabel, panel }) -> Promise<{ stage, data, setLoad, setField,
 *   setExaggeration, setClip(axis 'off'|'x'|'y'|'z', 0..1, flip), flyTo(i, { instant }), play(on),
 *   fit(view 'iso'|'front'|'side'|'top'|'under'), collapse, dispose() }>
 * Fields: 'ratio' (stress / strength), 'stress' (MPa), 'sf' (local safety factor), 'disp' (mm). Stresses are element
 * corner peaks, the values the safety factor uses (the averaged value is shown as "smoothed" in the readouts).
 * `back` is used only when it resolves to this page's origin. `panel: false` starts with the side panel hidden without
 * remembering it. Call dispose() before mounting another viewer in the same page. Bad arguments to the setters are
 * ignored.
 */
export async function mountFeaViewer(element, url, opts = {}) {
  const resp = await fetch(url, { cache: 'no-store' });
  if (!resp.ok) throw new Error(`${resp.status} ${resp.statusText}`);
  const data = await resp.json();
  if (data.format !== 'cadagent-fea-viewer') throw new Error('not a cad-agent FEA viewer file (Study.export_viewer)');

  if (!document.getElementById('fea-viewer-css')) {
    const st = document.createElement('style');
    st.id = 'fea-viewer-css';
    st.textContent = CSS;
    document.head.appendChild(st);
  }
  // everything from the file is data: numbers are coerced, strings are escaped or set as text
  const num = (v, d = 0) => (v !== null && v !== '' && Number.isFinite(+v) ? +v : d);
  const vec = (v, d = [0, 0, 0]) => (Array.isArray(v) && v.length === 3 ? v.map((x, i) => num(x, d[i])) : d.slice());
  const mat = data.material || {}, res = data.result || {}, F = data.failure || {};
  const S = Math.max(num(mat.strength_mpa, 1), 1e-9);
  const lamFail = F.first_failure_factor == null ? Infinity : num(F.first_failure_factor, Infinity);
  const lamMax = Math.max(num(F.max_load_factor, 1.2), 0.01);
  const title = String(opts.title ?? data.name ?? 'FEA');
  const sameOrigin = (h) => { try { const u = new URL(h, location.href); return u.origin === location.origin ? u.href : null; } catch { return null; } };
  const backHref = opts.back ? sameOrigin(opts.back) : null;
  const loadsData = (Array.isArray(data.loads) ? data.loads : []).map((ld) => ({
    kind: ld?.kind === 'torque' ? 'torque' : 'force', origin: vec(ld?.origin), dir: vec(ld?.dir, [0, 0, 1]), n: num(ld?.n),
    axis: vec(ld?.axis, [0, 0, 1]), center: vec(ld?.center), radius: num(ld?.radius), nm: num(ld?.nm), disp: vec(ld?.disp) }));
  const spotsData = (Array.isArray(data.hot_spots) ? data.hot_spots : []).map((h) => ({
    position: vec(h?.position), normal: vec(h?.normal, [0, 0, 1]), vertex: Math.trunc(num(h?.vertex, -1)),
    stress_mpa: num(h?.stress_mpa), of_strength: num(h?.of_strength), fails_at: num(h?.fails_at, Infinity),
    smoothed_mpa: h?.smoothed_mpa == null ? null : num(h.smoothed_mpa), hint: String(h?.hint ?? ''), mesh_note: String(h?.mesh_note ?? '') }));

  element.innerHTML = `<div id="app"></div><div id="hud">
    <header id="topbar"><span class="glyph"></span><h1>${esc(title)}</h1>
      <span class="hud-tag">${esc(mat.name)}</span><span class="hud-tag">SF ${fmt(res.safety_factor)}</span><span class="spacer"></span>
      ${backHref ? `<a class="hud-tag" href="${esc(backHref)}">${esc(opts.backLabel ?? 'Back')}</a>` : ''}</header>
    <main id="stage-overlay">
      <div class="hud-card fea-status"><div class="l1"></div><div class="l2"></div><div class="l3"></div></div>
      <div class="hud-card fea-legend"><div class="name"></div><div class="bar"></div><div class="ticks"></div><div class="keys">
        <span><i class="sw" style="background:#9ea3ad"></i>held</span><span><i class="sw" style="background:#0d0d0d;border:1px solid #444"></i>past the strength</span>
        <span><i class="sw" style="background:#ff2a6d"></i>loads</span><span><i class="sw" style="background:#fcee0a"></i>hot spots</span>
        <span class="sup" hidden><i class="sw" style="background:#59606b"></i>support patch (not checked)</span></div></div>
      <div class="hud-hint">DRAG · ORBIT // SCROLL · ZOOM // HOVER · VALUE // CLICK · PIN</div>
    </main>
    <aside id="panel"></aside></div><div class="fea-labels"></div><div class="fea-tip" hidden></div>`;
  const app = element.querySelector('#app'), hud = element.querySelector('#hud'), panel = element.querySelector('#panel');
  const statusEl = element.querySelector('.fea-status'), legendEl = element.querySelector('.fea-legend');
  const labelsEl = element.querySelector('.fea-labels'), tipEl = element.querySelector('.fea-tip');

  // --- the surface: one vertex per triangle corner, so a triangle can turn black on its own (element stress)
  const surf = data.surface;
  const nv = Math.trunc(num(surf.vertices)), nt = Math.trunc(num(surf.triangles));
  const P0 = decode(surf.positions), IDX = decode(surf.index), D = decode(surf.displacement);
  const VM = decode(surf.von_mises), VMT = decode(surf.tri_von_mises), FL = decode(surf.flags);
  const SM = surf.von_mises_smoothed ? decode(surf.von_mises_smoothed) : null;         // averaged corners ("smoothed")
  const TFL = surf.tri_flags ? decode(surf.tri_flags) : new Uint8Array(nt);           // 1: support element, not checked
  if (P0.length !== 3 * nv || D.length !== 3 * nv || VM.length !== nv || FL.length !== nv || IDX.length !== 3 * nt
      || VMT.length !== nt || TFL.length !== nt || IDX.some((i) => i >= nv)) throw new Error('inconsistent surface arrays');
  const DM = new Float32Array(nv);
  let dmaxS = 0;
  for (let i = 0; i < nv; i++) { DM[i] = Math.hypot(D[3 * i], D[3 * i + 1], D[3 * i + 2]); if (DM[i] > dmaxS) dmaxS = DM[i]; }
  const dmax = Math.max(num(data.max_displacement_mm), dmaxS);
  const heldTri = new Uint8Array(nt);
  for (let t = 0; t < nt; t++) heldTri[t] = (FL[IDX[3 * t]] & FL[IDX[3 * t + 1]] & FL[IDX[3 * t + 2]] & 1) ? 1 : 0;
  const PX = new Float32Array(nv * 3);                  // deformed positions per surface vertex
  const pos = new Float32Array(nt * 9), col = new Float32Array(nt * 9);
  const geo = new THREE.BufferGeometry();
  geo.setAttribute('position', new THREE.BufferAttribute(pos, 3).setUsage(THREE.DynamicDrawUsage));
  geo.setAttribute('color', new THREE.BufferAttribute(col, 3).setUsage(THREE.DynamicDrawUsage));
  const clip = new THREE.Plane(new THREE.Vector3(0, 1, 0), 1e9);
  const front = new THREE.Mesh(geo, new THREE.MeshStandardMaterial({ vertexColors: true, roughness: 0.72, metalness: 0, flatShading: true,
                                                                     clippingPlanes: [clip], side: THREE.FrontSide }));
  const back = new THREE.Mesh(geo, new THREE.MeshBasicMaterial({ color: 0x1d222c, side: THREE.BackSide, clippingPlanes: [clip] }));
  const wire = new THREE.Mesh(geo, new THREE.MeshBasicMaterial({ color: 0x05060a, wireframe: true, transparent: true, opacity: 0.22, clippingPlanes: [clip] }));
  wire.visible = false;
  front.castShadow = true;

  // CAD is z-up in mm; the stage is y-up in metres. Stand the part a little above the floor so it can sag.
  const lo = vec(data.bounds_mm?.[0]), hi = vec(data.bounds_mm?.[1]);
  const size = Math.max(num(data.size_mm, 100), 1e-6), sizeM = size / 1000, meshMm = Math.max(num(data.mesh_mm, size / 30), 1e-6);
  const model = new THREE.Group();
  model.rotation.x = -Math.PI / 2;
  model.scale.setScalar(0.001);
  model.position.set(-(lo[0] + hi[0]) / 2000, -lo[2] / 1000 + 0.12 * sizeM, (lo[1] + hi[1]) / 2000);
  model.add(back, front, wire);
  const stage = createStage(app, { height: sizeM * 1.1, screenshots: true });
  const floor = stage.scene.children.filter((o) => o.isMesh || o.isLine);   // ground, grid, glow: hidden from below
  stage.renderer.localClippingEnabled = true;
  stage.controls.maxPolarAngle = Math.PI;              // look from underneath too
  stage.controls.minDistance = 0.03 * sizeM;           // close enough to read a fillet
  // a headlight that follows the camera: faces turned away from the stage lights stay readable (only failed is black)
  const headlight = new THREE.DirectionalLight(0xffffff, 1.1);
  headlight.position.set(0.3, 0.4, 1);
  stage.camera.add(headlight);
  stage.scene.add(stage.camera);
  stage.root.add(model);
  model.updateMatrixWorld(true);

  // --- loads: arrows (forces) and curled arrows (torques), riding on the deformed part
  const LOAD = 0xff2a6d;
  const loadMat = new THREE.MeshBasicMaterial({ color: LOAD, depthTest: false, transparent: true, opacity: 0.92 });
  const loads = loadsData.map((ld) => {
    const g = new THREE.Group();
    g.renderOrder = 10;
    const label = document.createElement('div');
    label.className = 'fea-load';
    labelsEl.appendChild(label);
    if (ld.kind === 'force') {
      const L = 0.24 * size, r = 0.012 * size;
      const shaft = new THREE.Mesh(new THREE.CylinderGeometry(r, r, L * 0.72, 12), loadMat);
      shaft.position.y = L * 0.36;
      const head = new THREE.Mesh(new THREE.ConeGeometry(r * 2.6, L * 0.28, 16), loadMat);
      head.position.y = L * 0.86;
      g.add(shaft, head);
      const dir = new THREE.Vector3(...ld.dir);
      g.quaternion.setFromUnitVectors(new THREE.Vector3(0, 1, 0), dir);
      const tail = new THREE.Vector3(...ld.origin).addScaledVector(dir, -L);
      for (const m of g.children) m.renderOrder = 10;
      model.add(g);
      return { ld, g, label, base: tail, at: tail, text: (lam) => `F ${fmtN(ld.n * lam)}` };
    }
    const sgn = Math.sign(ld.nm) || 1;
    // around the loaded faces, but never so big it hides the part (holes far from the axis: a bolt circle, a lever)
    const R = Math.min(Math.max(ld.radius * 1.25, 0.06 * size), 0.22 * size), r = 0.01 * size, sweep = 1.5 * Math.PI;
    class Arc extends THREE.Curve { getPoint(t, out = new THREE.Vector3()) { return out.set(R * Math.cos(t * sweep), R * Math.sin(t * sweep), 0); } }
    const tube = new THREE.Mesh(new THREE.TubeGeometry(new Arc(), 48, r, 8, false), loadMat);
    const head = new THREE.Mesh(new THREE.ConeGeometry(r * 2.8, r * 7, 16), loadMat);
    head.position.set(R * Math.cos(sweep), R * Math.sin(sweep), 0);
    head.quaternion.setFromUnitVectors(new THREE.Vector3(0, 1, 0), new THREE.Vector3(-Math.sin(sweep), Math.cos(sweep), 0));
    g.add(tube, head);
    for (const m of g.children) m.renderOrder = 10;
    g.quaternion.setFromUnitVectors(new THREE.Vector3(0, 0, 1), new THREE.Vector3(...ld.axis).multiplyScalar(sgn));
    model.add(g);
    const c = new THREE.Vector3(...ld.center);
    return { ld, g, label, base: c, at: c, text: (lam) => `T ${(Math.abs(ld.nm) * lam).toFixed(1)} N·m` };
  });

  // --- hot spots: numbered labels on the part, a pulse ring when picked
  const spots = spotsData.map((h, i) => {
    const b = document.createElement('button');
    b.type = 'button';
    b.className = `fea-label${h.fails_at < 1 ? ' fail' : ''}`;
    b.textContent = String(i + 1);
    b.title = `#${i + 1}: fails at ×${fmt(h.fails_at)} of the design load (${h.hint})`;
    labelsEl.appendChild(b);
    const ok = h.vertex >= 0 && h.vertex < nv;                    // follows the deformed surface when it is on it
    return { h: { ...h, vertex: ok ? h.vertex : -1 }, b, p: new THREE.Vector3(...h.position), n: new THREE.Vector3(...h.normal) };
  });
  const ring = new THREE.Mesh(new THREE.RingGeometry(0.8, 1, 48), new THREE.MeshBasicMaterial({ color: 0x00f0ff, transparent: true, depthTest: false, side: THREE.DoubleSide }));
  ring.renderOrder = 11;
  ring.visible = false;
  stage.scene.add(ring);
  const probeDot = new THREE.Mesh(new THREE.SphereGeometry(1, 16, 12), new THREE.MeshBasicMaterial({ color: 0x00f0ff, depthTest: false }));
  probeDot.renderOrder = 11;
  probeDot.visible = false;
  stage.scene.add(probeDot);

  // --- state and the update of the surface
  const exagAuto = dmax > 0 ? Math.max(1, (0.08 * size) / (dmax * lamMax)) : 1;
  const S_ = { lam: 1, exag: exagAuto, field: 'ratio', markFail: true, markSupport: false, dirty: true };
  const TV = new Float32Array(nv);
  const vmDesign = num(F.design_stress_mpa);
  const SUP = linear(0x59606b);

  function fieldT(i) {
    const lam = S_.lam;
    switch (S_.field) {
      case 'stress': case 'ratio': return (VM[i] * lam) / S;
      case 'sf': { const s = VM[i] * lam; const sf = s > 0 ? S / s : Infinity; return 1 - Math.min(sf, SF_RANGE) / SF_RANGE; }
      case 'disp': return dmaxS > 0 ? DM[i] / dmaxS : 0;
      default: return 0;
    }
  }
  function update() {
    const lam = S_.lam, k = S_.exag * lam;
    for (let i = 0; i < nv; i++) {
      PX[3 * i] = P0[3 * i] + k * D[3 * i];
      PX[3 * i + 1] = P0[3 * i + 1] + k * D[3 * i + 1];
      PX[3 * i + 2] = P0[3 * i + 2] + k * D[3 * i + 2];
      TV[i] = fieldT(i);
    }
    for (let t = 0; t < nt; t++) {
      const support = TFL[t] & 1;                    // support elements are left out of the failure test, as in the SF
      const failed = S_.markFail && !support && VMT[t] * lam > S;
      const grey = S_.markSupport && support ? 0.7 : 0;
      for (let j = 0; j < 3; j++) {
        const v = IDX[3 * t + j], o = (3 * t + j) * 3;
        pos[o] = PX[3 * v]; pos[o + 1] = PX[3 * v + 1]; pos[o + 2] = PX[3 * v + 2];
        if (heldTri[t]) { col[o] = HELD.r; col[o + 1] = HELD.g; col[o + 2] = HELD.b; }
        else if (failed) { col[o] = FAILED.r; col[o + 1] = FAILED.g; col[o + 2] = FAILED.b; }
        else {
          const q = Math.round(clamp01(TV[v]) * (LUT_N - 1)) * 3;
          col[o] = LUT[q] + grey * (SUP.r - LUT[q]); col[o + 1] = LUT[q + 1] + grey * (SUP.g - LUT[q + 1]); col[o + 2] = LUT[q + 2] + grey * (SUP.b - LUT[q + 2]);
        }
      }
    }
    geo.attributes.position.needsUpdate = true;
    geo.attributes.color.needsUpdate = true;
    geo.computeBoundingSphere();
    for (const L of loads) {
      L.at = L.base.clone().add(new THREE.Vector3(...L.ld.disp).multiplyScalar(k));
      L.g.position.copy(L.at);
    }
    for (const s of spots) s.at = s.h.vertex >= 0 ? new THREE.Vector3(PX[3 * s.h.vertex], PX[3 * s.h.vertex + 1], PX[3 * s.h.vertex + 2]) : s.p.clone();
    paintStatus();
    paintLegend();
    if (pinned) showProbe(pinned, true);
  }

  // --- overlays: the status card and the legend
  // the overstressed volume: a step function (each element joins at its own failure load), an upper bound
  const XS = (F.curve?.load_factor || []).map((x) => num(x, Infinity)), YS = (F.curve?.share || []).map((y) => num(y));
  function shareAt(lam) {
    let lo_ = 0, hi_ = Math.min(XS.length, YS.length);           // the number of steps strictly below lam
    while (lo_ < hi_) { const mid = (lo_ + hi_) >> 1; if (XS[mid] < lam) lo_ = mid + 1; else hi_ = mid; }
    return lo_ ? YS[lo_ - 1] : 0;
  }
  const fmtShare = (sh) => (sh > 0 && sh < 0.001 ? '<0.1' : (sh * 100).toFixed(1));
  const excluded = F.excluded || {};
  function stateOf(lam) {
    if (lam < 1e-6) return 'unloaded';
    if (Math.abs(lam - 1) < 0.006) return 'design load';
    if (Math.abs(lam - lamFail) < 0.006) return 'first failure: the peak reaches the strength';
    if (lam > lamFail) return 'past first failure';
    return lam < 1 ? 'loading' : 'overload';
  }
  function paintStatus() {
    const lam = S_.lam, over = lam > lamFail + 1e-9;
    const sh = shareAt(lam);
    statusEl.classList.toggle('over', over);
    statusEl.querySelector('.l1').textContent = `LOAD ×${lam.toFixed(2)} OF THE DESIGN LOAD · ${stateOf(lam).toUpperCase()}`;
    statusEl.querySelector('.l2').textContent = `peak ${(vmDesign * lam).toFixed(1)} of ${fmt(S, 1)} MPa · max displacement ${(dmax * lam).toFixed(2)} mm`
      + ` (shown ×${S_.exag < 10 ? S_.exag.toFixed(1) : Math.round(S_.exag)})`;
    statusEl.querySelector('.l3').innerHTML = `first failure at ×${fmt(lamFail)} (the safety factor) · past the strength: `
      + `<span class="${sh > 0 ? 'bad' : ''}">${fmtShare(sh)} % of the volume</span> (whole elements: an upper bound)`;
  }
  function paintLegend() {
    const f = S_.field, lam = S_.lam;
    legendEl.querySelector('.name').textContent = `${FIELDS[f].label}${f === 'disp' ? ` at ×${lam.toFixed(2)}` : ''}`;
    legendEl.querySelector('.bar').style.background = gradient(f === 'sf');
    let ticks;
    if (f === 'ratio') ticks = ['0', '0.25', '0.5', '0.75', '1 strength'];
    else if (f === 'stress') ticks = [0, 0.25, 0.5, 0.75, 1].map((x) => (x === 1 ? `${fmt(S, 1)} MPa` : (x * S).toFixed(0)));
    else if (f === 'sf') ticks = ['0', '1', '2', '3', `${SF_RANGE}+`];
    else ticks = [0, 0.25, 0.5, 0.75, 1].map((x) => (x * dmaxS * lam).toFixed(dmaxS * lam < 1 ? 3 : 2) + (x === 1 ? ' mm' : ''));
    legendEl.querySelector('.ticks').innerHTML = ticks.map((t) => `<span>${esc(t)}</span>`).join('');
  }

  // --- panel
  const info = readouts(section(panel, 'Result', { note: String(data.name ?? '') }));
  const vol = F.overstressed_volume || {};
  const rows = [['material', String(mat.name ?? '')], ['strength', `${fmt(S, 1)} MPa`], ['modulus E', `${fmt(num(mat.E_mpa), 0)} MPa`],
    ['design stress', `${fmt(vmDesign, 1)} MPa`], ['safety factor', fmt(res.safety_factor), res.safety_factor < 1 ? 'fail' : res.safety_factor < 1.5 ? 'warn' : 'ok'],
    ['max displacement', `${fmt(dmax, 3)} mm`]];
  if (res.stiffness_n_per_mm) rows.push(['stiffness', `${fmt(res.stiffness_n_per_mm, 1)} N/mm`]);
  if (res.torsional_stiffness_nm_per_deg) rows.push(['torsional stiffness', `${fmt(res.torsional_stiffness_nm_per_deg, 2)} N·m/°`]);
  rows.push(['past strength at 1.25 × SF', `${fmtShare(num(vol['at_1.25x_first_failure']))} % vol (upper bound)`]);
  if (excluded.surface_share != null) {
    const ex = num(excluded.surface_share);
    rows.push(['support patches (not checked)', `${fmtShare(ex)} % of the surface`, ex > 0.4 ? 'warn' : '']);
  }
  if (res.mesh) rows.push(['mesh', `${fmt(res.mesh.tets, 0)} P2 tets, ${fmt(res.mesh.size_mm, 1)} mm`]);
  info.set(rows);

  const lsec = section(panel, 'Load', { note: 'linear: everything scales' });
  const loadSlider = slider(lsec, { label: 'Load factor', min: 0, max: lamMax, step: 0.01, value: 1, fmt: (v) => `×${v.toFixed(2)}`,
                                    onInput: (v) => { stopPlay(); setLoad(v); } });
  const marks = document.createElement('div');
  marks.className = 'fea-marks';
  const markAt = (x, text, cls = '', row = 0) => `<span class="${cls}" style="left:calc(${(x / lamMax) * 100}% + ${6 - 12 * (x / lamMax)}px);top:${3 + 13 * row}px">${text}</span>`;
  const close = isFinite(lamFail) && Math.abs(lamFail - 1) / lamMax < 0.22;     // two marks side by side would collide
  if (close) marks.style.height = '29px';
  marks.innerHTML = markAt(1, '×1 design') + (isFinite(lamFail) && lamFail <= lamMax ? markAt(lamFail, `×${lamFail.toFixed(2)} fails`, 'fail', close ? 1 : 0) : '');
  lsec.appendChild(marks);
  const lrow = document.createElement('div');
  lrow.className = 'fea-row';
  lrow.innerHTML = `<button class="hud-btn primary" data-a="play">▶ Play</button><button class="hud-btn" data-a="design">Design</button>`
    + `<button class="hud-btn" data-a="fail">First failure</button><button class="hud-btn" data-a="max">Max</button>`;
  lsec.appendChild(lrow);
  const playBtn = lrow.querySelector('[data-a=play]');
  lrow.querySelector('[data-a=design]').onclick = () => { stopPlay(); setLoad(1); };
  lrow.querySelector('[data-a=fail]').onclick = () => { stopPlay(); setLoad(Math.min(lamFail, lamMax)); };
  lrow.querySelector('[data-a=max]').onclick = () => { stopPlay(); setLoad(lamMax); };
  playBtn.onclick = () => (playing ? stopPlay() : startPlay());
  const exMax = Math.log10(Math.max(exagAuto * 5, 2));
  const exSlider = slider(lsec, { label: 'Deformation shown', min: 0, max: exMax, step: 0.01, value: Math.log10(exagAuto),
                                  fmt: (v) => { const x = 10 ** v; return x < 1.05 ? 'true scale' : `×${x < 10 ? x.toFixed(1) : Math.round(x)}`; },
                                  onInput: (v) => { S_.exag = 10 ** v; S_.dirty = true; } });
  toggle(lsec, 'Black where past the strength', true, (on) => { S_.markFail = on; S_.dirty = true; });
  toggle(lsec, 'Grey out the support patches (not checked)', false, (on) => {
    S_.markSupport = on; legendEl.querySelector('.sup').hidden = !on; S_.dirty = true;
  });

  const csec = section(panel, 'Colour by');
  const crow = document.createElement('div');
  crow.className = 'fea-row';
  crow.innerHTML = Object.entries(FIELDS).map(([k, f]) => `<button class="hud-btn" data-f="${k}" title="${esc(f.note)}">${esc(f.label.replace(' (MPa)', '').replace(' (mm)', ''))}</button>`).join('');
  csec.appendChild(crow);
  crow.querySelectorAll('button').forEach((b) => { b.onclick = () => setField(b.dataset.f); });

  const ssec = section(panel, 'Where it fails first', { note: `${spots.length} hot spots` });
  const list = document.createElement('div');
  list.className = 'fea-spots';
  list.innerHTML = spots.length ? spots.map((s, i) => `<button class="fea-spot${s.h.fails_at < 1 ? ' fail' : ''}" data-i="${i}">`
    + `<span class="n">${i + 1}</span><span>${fmt(s.h.stress_mpa, 1)} MPa · ${fmt(s.h.of_strength * 100, 0)} % of strength</span>`
    + `<span class="f">fails ×${fmt(s.h.fails_at)}</span><span class="h">${esc(s.h.hint)}</span>`
    + `${s.h.mesh_note ? `<span class="m">${esc(s.h.mesh_note)}</span>` : ''}</button>`).join('')
    : '<p class="fea-note">No stress concentration away from the supports.</p>';
  ssec.appendChild(list);
  const pnote = document.createElement('p');
  pnote.className = 'fea-note';
  pnote.textContent = 'Element peaks away from the clamp and load patches, at least 4 mesh sizes apart. "fails ×" is the load factor at which that spot reaches the strength.';
  ssec.appendChild(pnote);
  list.querySelectorAll('.fea-spot').forEach((b) => { b.onclick = () => flyTo(+b.dataset.i); });
  spots.forEach((s, i) => { s.b.onclick = () => flyTo(i); });

  const probeSec = section(panel, 'Probe', { note: 'click the part' });
  const probeOut = readouts(probeSec);
  probeOut.set([['', 'click a point to pin its values']]);

  const xsec = section(panel, 'Section cut', { note: 'see inside', open: false });
  const xrow = document.createElement('div');
  xrow.className = 'fea-row';
  xrow.innerHTML = ['off', 'x', 'y', 'z'].map((a) => `<button class="hud-btn${a === 'off' ? ' on' : ''}" data-x="${a}">${a.toUpperCase()}</button>`).join('');
  xsec.appendChild(xrow);
  const cut = { axis: 'off', f: 0.5, flip: false };
  const xSlider = slider(xsec, { label: 'Position', min: 0, max: 1, step: 0.005, value: 0.5, fmt: (v) => `${Math.round(v * 100)} %`,
                                 onInput: (v) => setClip(cut.axis === 'off' ? 'x' : cut.axis, v, cut.flip) });
  toggle(xsec, 'Keep the other side', false, (on) => setClip(cut.axis === 'off' ? 'x' : cut.axis, cut.f, on));
  xrow.querySelectorAll('button').forEach((b) => { b.onclick = () => setClip(b.dataset.x, cut.f, cut.flip); });
  const xnote = document.createElement('p');
  xnote.className = 'fea-note';
  xnote.textContent = 'Cuts the surface skin (dark inside): it shows hidden faces, holes and walls, not the stress inside the material.';
  xsec.appendChild(xnote);

  const vsec = section(panel, 'View', { open: false });
  const vrow = document.createElement('div');
  vrow.className = 'fea-row';
  const VIEWS = { iso: [1, 0.6, 1.4], front: [0, 0.12, 1], side: [1, 0.12, 0], top: [0.001, 1, 0.001], under: [0.001, -1, 0.001] };
  vrow.innerHTML = Object.keys(VIEWS).map((k) => `<button class="hud-btn" data-v="${k}">${k.toUpperCase()}</button>`).join('');
  vsec.appendChild(vrow);
  vrow.querySelectorAll('button').forEach((b) => { b.onclick = () => fit(b.dataset.v); });
  toggle(vsec, 'Mesh edges', false, (on) => { wire.visible = on; });
  toggle(vsec, 'Load arrows', true, (on) => { loads.forEach((L) => { L.g.visible = on; L.label.hidden = !on; }); });
  toggle(vsec, 'Hot-spot markers', true, (on) => { spots.forEach((s) => { s.b.hidden = !on; }); });
  slider(vsec, { label: 'Light', min: 0.2, max: 1, step: 0.01, value: 1, fmt: (v) => v.toFixed(2), onInput: (v) => stage.setSceneLight(v) });

  const asec = section(panel, 'Assumptions', { open: false });
  const lines = loadsData.map((ld) => (ld.kind === 'force' ? `force ${fmtN(ld.n)} along (${ld.dir.map((x) => x.toFixed(2)).join(', ')})`
    : `torque ${Math.abs(ld.nm).toFixed(1)} N·m about (${ld.axis.map((x) => x.toFixed(2)).join(', ')})`));
  asec.innerHTML = `<p class="fea-note">${esc(data.assumptions)}</p>`
    + (mat.note ? `<p class="fea-note">Material: ${esc(mat.note)}.</p>` : '')
    + `<p class="fea-note">Design loads (×1): ${esc(lines.join('; ') || 'none')}. Elements touching the clamp and load patches are not checked`
    + ` (like the safety factor) and are capped at the design stress, ${fmt(F.capped_at_mpa, 1)} MPa. "Past the strength" counts the`
    + ` whole volume of each element whose peak passes it: an upper bound.</p>`;

  // --- actions
  function setLoad(v) {
    v = Number(v);
    if (!Number.isFinite(v)) return;
    S_.lam = Math.max(0, Math.min(lamMax, v)); loadSlider.set(S_.lam); S_.dirty = true;
  }
  function setField(f) {
    if (!Object.hasOwn(FIELDS, f)) return;
    S_.field = f;
    crow.querySelectorAll('button').forEach((b) => b.classList.toggle('on', b.dataset.f === f));
    S_.dirty = true;
  }
  function setExaggeration(x) {
    x = Number(x);
    if (!Number.isFinite(x) || x <= 0) return;
    S_.exag = Math.max(1, x); exSlider.set(Math.log10(S_.exag)); S_.dirty = true;
  }
  function setClip(axis, f = cut.f, flip = cut.flip) {
    if (!['off', 'x', 'y', 'z'].includes(axis)) return;
    f = Number(f);
    f = Number.isFinite(f) ? clamp01(f) : cut.f;
    flip = Boolean(flip);
    Object.assign(cut, { axis, f, flip });
    xSlider.set(f);
    xrow.querySelectorAll('button').forEach((b) => b.classList.toggle('on', b.dataset.x === axis));
    if (axis === 'off') { clip.set(new THREE.Vector3(0, 1, 0), 1e9); return; }
    const a = { x: 0, y: 1, z: 2 }[axis];
    const n = new THREE.Vector3(); n.setComponent(a, flip ? 1 : -1);
    const p = new THREE.Vector3((lo[0] + hi[0]) / 2, (lo[1] + hi[1]) / 2, (lo[2] + hi[2]) / 2);
    p.setComponent(a, lo[a] + (hi[a] - lo[a]) * f);
    model.updateMatrixWorld(true);
    clip.copy(new THREE.Plane().setFromNormalAndCoplanarPoint(n, p).applyMatrix4(model.matrixWorld));
  }

  // camera: fit, and fly to a hot spot
  let fly = null;
  function partBox() {
    const b = new THREE.Box3();
    b.setFromObject(model);                          // the part and its load arrows
    return b.expandByScalar(0.05 * sizeM);
  }
  // the stage area the overlays leave free; on a phone the status card and the legend count too
  function insets() {
    const ins = overlayInsets(hud);
    if (window.innerWidth <= 820) {
      const a = app.getBoundingClientRect(), st = statusEl.getBoundingClientRect(), lg = legendEl.getBoundingClientRect();
      ins.top = Math.max(ins.top, st.bottom - a.top + 4);
      ins.bottom = Math.max(ins.bottom, a.bottom - lg.top + 4);
    }
    return ins;
  }
  let lastView = 'iso', userMoved = false;
  stage.controls.addEventListener('start', () => { userMoved = true; });
  function fit(view = 'iso') {
    fly = null;
    lastView = view;
    userMoved = false;
    stage.setInsets(insets());
    stage.fitView(partBox(), { direction: new THREE.Vector3(...(VIEWS[view] ?? VIEWS.iso)), margin: 1.08 });
  }
  let picked = -1;
  function flyTo(i, { instant = false } = {}) {
    i = Number(i);
    if (!Number.isInteger(i)) return;
    const s = spots[i];
    if (!s) return;
    picked = i;
    list.querySelectorAll('.fea-spot').forEach((b, j) => b.classList.toggle('on', j === i));
    spots.forEach((x, j) => x.b.classList.toggle('on', j === i));
    const target = model.localToWorld((s.at ?? s.p).clone());
    const q = model.getWorldQuaternion(new THREE.Quaternion());
    const nW = s.n.clone().applyQuaternion(q).normalize();
    const cur = stage.camera.position.clone().sub(stage.controls.target).normalize();
    // look along the surface normal (leaning towards the current view), or, when other walls are in the way (inside a
    // clevis, a hole, a pocket), the nearest tilt or distance from which the spot is in plain sight
    const D = Math.max(0.8 * sizeM, 25 * meshMm / 1000);
    const up = Math.abs(nW.y) < 0.9 ? new THREE.Vector3(0, 1, 0) : new THREE.Vector3(1, 0, 0);
    const a1 = new THREE.Vector3().crossVectors(nW, up).normalize(), a2 = new THREE.Vector3().crossVectors(nW, a1);
    const dirs = [nW.clone().multiplyScalar(0.85).addScaledVector(cur, 0.5).normalize(), nW.clone()];
    for (const tilt of [0.5, 0.95, 1.3]) {
      for (let k = 0; k < 8; k++) {
        const ang = (k * Math.PI) / 4;
        dirs.push(nW.clone().multiplyScalar(Math.cos(tilt)).addScaledVector(a1, Math.sin(tilt) * Math.cos(ang)).addScaledVector(a2, Math.sin(tilt) * Math.sin(ang)));
      }
    }
    let p1 = null;
    for (const dist of [D, 0.5 * D, 0.25 * D, 0.12 * D]) {
      const d = dirs.find((c) => !blocked(target.clone().addScaledVector(c, dist), target));
      if (d) { p1 = target.clone().addScaledVector(d, dist); break; }
    }
    p1 ??= target.clone().addScaledVector(dirs[0], D);
    fly = { t: 0, dur: instant ? 0 : 0.9, p0: stage.camera.position.clone(), t0: stage.controls.target.clone(), p1, t1: target };
    if (instant) { stage.camera.position.copy(fly.p1); stage.controls.target.copy(fly.t1); stage.controls.update(); fly = null; }
    ring.userData.t = 0;
    ring.userData.spot = i;
    ring.visible = true;
  }

  // is the line from `from` to the surface point `to` (world) blocked by the part? (what the section cut removed is not)
  const occRay = new THREE.Raycaster();
  const occTol = (1.5 * meshMm) / 1000;
  function blocked(from, to) {
    const d = to.clone().sub(from);
    const len = d.length();
    occRay.set(from, d.divideScalar(len));
    occRay.far = Math.max(0, len - occTol);
    // back faces too: a viewpoint inside the material sees the inside of the skin first
    return occRay.intersectObjects([front, back], false).some((h) => clip.distanceToPoint(h.point) >= 0);
  }

  // the load ramp, held a moment at the design load and at first failure
  let playing = false, playT = 0, timeline = null;
  function buildTimeline() {
    const keys = [...new Set([0, 1, isFinite(lamFail) ? Math.min(lamFail, lamMax) : lamMax, lamMax])].sort((a, b) => a - b);
    const segs = [];
    for (let i = 1; i < keys.length; i++) {
      segs.push({ from: keys[i - 1], to: keys[i], dur: Math.max(0.6, 6 * (keys[i] - keys[i - 1]) / lamMax) });
      const hold = keys[i] === 1 ? 0.8 : Math.abs(keys[i] - lamFail) < 1e-9 ? 1.1 : keys[i] === lamMax ? 1.4 : 0;
      if (hold) segs.push({ from: keys[i], to: keys[i], dur: hold });
    }
    return { segs, total: segs.reduce((a, s) => a + s.dur, 0) };
  }
  function startPlay() {
    timeline = buildTimeline();
    playT = S_.lam >= lamMax - 1e-6 ? 0 : (() => {   // start where the slider is
      let t = 0;
      for (const s of timeline.segs) { if (s.to > s.from && S_.lam >= s.from && S_.lam <= s.to) return t + s.dur * (S_.lam - s.from) / (s.to - s.from); t += s.dur; }
      return 0;
    })();
    playing = true;
    playBtn.textContent = '❚❚ Pause';
  }
  function stopPlay() { playing = false; playBtn.textContent = '▶ Play'; }

  // --- hover readout and the pinned probe
  const ray = new THREE.Raycaster(), ndc = new THREE.Vector2();
  let hover = null, pinned = null, down = null;
  const canvas = stage.renderer.domElement;
  const tri = new THREE.Triangle(), bary = new THREE.Vector3();
  function pick(clientX, clientY) {
    const r = canvas.getBoundingClientRect();
    ndc.set(((clientX - r.left) / r.width) * 2 - 1, -((clientY - r.top) / r.height) * 2 + 1);
    ray.setFromCamera(ndc, stage.camera);
    const hits = ray.intersectObject(front, false).filter((h) => clip.distanceToPoint(h.point) >= 0);
    if (!hits.length) return null;
    const h = hits[0], t = h.faceIndex;
    const local = model.worldToLocal(h.point.clone());
    const V = (j) => new THREE.Vector3(pos[(3 * t + j) * 3], pos[(3 * t + j) * 3 + 1], pos[(3 * t + j) * 3 + 2]);
    tri.set(V(0), V(1), V(2));
    tri.getBarycoord(local, bary);
    return { t, w: [bary.x, bary.y, bary.z] };
  }
  function valuesAt(p) {
    const vs = [IDX[3 * p.t], IDX[3 * p.t + 1], IDX[3 * p.t + 2]];
    const lam = S_.lam;
    let vm = 0, sm = 0, dm = 0, flags = 0;
    const x = new THREE.Vector3(), x0 = new THREE.Vector3();
    vs.forEach((v, j) => {
      vm += p.w[j] * VM[v]; sm += p.w[j] * (SM ? SM[v] : VM[v]); dm += p.w[j] * DM[v]; flags |= FL[v];
      x.x += p.w[j] * PX[3 * v]; x.y += p.w[j] * PX[3 * v + 1]; x.z += p.w[j] * PX[3 * v + 2];
      x0.x += p.w[j] * P0[3 * v]; x0.y += p.w[j] * P0[3 * v + 1]; x0.z += p.w[j] * P0[3 * v + 2];
    });
    // the value at a point: the corner peaks there or this triangle's element peak, whichever is higher (the SF's
    // convention, so a failed spot never reads safe); the averaged value is shown as "smoothed"
    const support = Boolean(TFL[p.t] & 1), elem = VMT[p.t] * lam;
    const s = Math.max(vm * lam, elem);
    return { s, smooth: sm * lam, ratio: s / S, sf: s > 0 ? S / s : Infinity, d: dm * lam, elem, failed: !support && elem > S,
             support, flags, x, x0, held: heldTri[p.t] };
  }
  function tipHtml(v) {
    const notes = [];
    if (v.held) notes.push('held (clamped)');
    else if (v.flags & 2) notes.push('on a load patch');
    if (v.support) {
      return '<b>support patch</b>: not checked (idealised clamp or load spike; like the safety factor)<br>'
        + `capped at the design stress · moves <b>${v.d.toFixed(3)} mm</b><br>`
        + `<span class="dim">at (${v.x0.x.toFixed(1)}, ${v.x0.y.toFixed(1)}, ${v.x0.z.toFixed(1)}) mm${notes.length ? ' · ' + esc(notes.join(', ')) : ''}</span>`;
    }
    return `<b>${v.s.toFixed(1)} MPa</b> · ${(v.ratio * 100).toFixed(0)} % of strength <span class="dim">(smoothed ${v.smooth.toFixed(1)})</span><br>`
      + `local SF <b class="${v.sf < 1 ? 'bad' : ''}">${isFinite(v.sf) ? v.sf.toFixed(2) : '∞'}</b> · moves <b>${v.d.toFixed(3)} mm</b><br>`
      + `${v.failed ? '<span class="bad">past the strength here</span><br>' : ''}`
      + `<span class="dim">at (${v.x0.x.toFixed(1)}, ${v.x0.y.toFixed(1)}, ${v.x0.z.toFixed(1)}) mm${notes.length ? ' · ' + esc(notes.join(', ')) : ''}</span>`;
  }
  function showProbe(p, quiet = false) {
    const v = valuesAt(p);
    probeDot.position.copy(model.localToWorld(v.x.clone()));
    probeDot.scale.setScalar(0.008 * sizeM);
    probeDot.visible = true;
    const at = ['at (mm)', `${v.x0.x.toFixed(1)}, ${v.x0.y.toFixed(1)}, ${v.x0.z.toFixed(1)}`];
    if (v.support) {
      probeOut.set([['support patch', 'not checked', 'warn'], ['why', 'idealised clamp/load spike'], ['displacement', `${v.d.toFixed(3)} mm`], at,
        ...(v.held ? [['', 'held face']] : [])]);
    } else {
      probeOut.set([['stress (peak)', `${v.s.toFixed(1)} MPa`, v.failed ? 'fail' : ''], ['smoothed', `${v.smooth.toFixed(1)} MPa`],
        ['of strength', `${(v.ratio * 100).toFixed(0)} %`],
        ['local SF', isFinite(v.sf) ? v.sf.toFixed(2) : '∞', v.sf < 1 ? 'fail' : v.sf < 1.5 ? 'warn' : 'ok'], ['displacement', `${v.d.toFixed(3)} mm`],
        at, ...(v.held ? [['', 'held face']] : [])]);
    }
    if (!quiet) probeSec.closest('details').open = true;
  }
  canvas.addEventListener('pointermove', (e) => { hover = { x: e.clientX, y: e.clientY, type: e.pointerType }; });
  canvas.addEventListener('pointerleave', () => { hover = null; tipEl.hidden = true; });
  canvas.addEventListener('pointerdown', (e) => { down = { x: e.clientX, y: e.clientY }; });
  canvas.addEventListener('pointerup', (e) => {
    if (!down || Math.hypot(e.clientX - down.x, e.clientY - down.y) > 5) return;
    const p = pick(e.clientX, e.clientY);
    pinned = p;
    if (p) showProbe(p); else { probeDot.visible = false; probeOut.set([['', 'click a point to pin its values']]); }
  });

  // --- per frame: the ramp, the camera flight, the pulse, labels and the hover readout
  const v3 = new THREE.Vector3();
  function placeLabel(el, world, dimIfBack = null, hidden = false) {
    v3.copy(world).project(stage.camera);
    const r = canvas.getBoundingClientRect();
    if (v3.z > 1 || v3.z < -1 || clip.distanceToPoint(world) < 0) { el.style.display = 'none'; return; }
    el.style.display = '';
    el.style.transform = `translate(${r.left + (v3.x + 1) / 2 * r.width}px, ${r.top + (1 - v3.y) / 2 * r.height}px)${el.classList.contains('fea-load') ? ' translate(-50%, -140%)' : ''}`;
    if (dimIfBack) el.classList.toggle('dim', hidden || dimIfBack.dot(v3.copy(stage.camera.position).sub(world)) < 0);
  }
  const q = new THREE.Quaternion();
  let frameN = 0;
  stage.onFrame((t, dt) => {
    const below = stage.camera.position.y < 0;
    for (const o of floor) o.visible = !below;
    if (playing) {
      playT = (playT + dt) % timeline.total;
      let acc = 0;
      for (const s of timeline.segs) {
        if (playT <= acc + s.dur) { setLoad(s.from + (s.to - s.from) * ((playT - acc) / s.dur)); break; }
        acc += s.dur;
      }
    }
    if (S_.dirty) { S_.dirty = false; update(); }
    if (fly) {
      fly.t += dt;
      const u = fly.dur > 0 ? Math.min(1, fly.t / fly.dur) : 1, e = u < 0.5 ? 2 * u * u : 1 - (-2 * u + 2) ** 2 / 2;
      stage.camera.position.lerpVectors(fly.p0, fly.p1, e);
      stage.controls.target.lerpVectors(fly.t0, fly.t1, e);
      if (u >= 1) fly = null;
    }
    if (ring.visible) {
      const s = spots[ring.userData.spot];
      ring.userData.t += dt;
      const ph = (ring.userData.t % 1.2) / 1.2;
      ring.position.copy(model.localToWorld((s.at ?? s.p).clone()));
      ring.quaternion.copy(stage.camera.quaternion);
      ring.scale.setScalar(sizeM * (0.015 + 0.05 * ph));
      ring.material.opacity = 1 - ph;
      if (ring.userData.t > 4.8) ring.visible = false;
    }
    model.getWorldQuaternion(q);
    frameN++;
    if (spots.length && frameN % 4 === 0) {         // one occlusion test every few frames, round robin
      const s = spots[(frameN / 4) % spots.length];
      s.occluded = blocked(stage.camera.position, model.localToWorld((s.at ?? s.p).clone()));
    }
    for (const s of spots) if (!s.b.hidden) placeLabel(s.b, model.localToWorld((s.at ?? s.p).clone()), s.n.clone().applyQuaternion(q), s.occluded);
    for (const L of loads) {
      if (L.label.hidden) continue;
      L.label.textContent = L.text(S_.lam);
      placeLabel(L.label, model.localToWorld(L.at.clone()));
    }
    if (hover && hover.type === 'mouse' && !fly) {
      const p = pick(hover.x, hover.y);
      if (p) {
        tipEl.innerHTML = tipHtml(valuesAt(p));
        tipEl.hidden = false;
        const w = tipEl.offsetWidth, h = tipEl.offsetHeight;
        tipEl.style.left = `${Math.min(hover.x + 14, window.innerWidth - w - 8)}px`;
        tipEl.style.top = `${Math.min(hover.y + 14, window.innerHeight - h - 8)}px`;
      } else tipEl.hidden = true;
      hover = { ...hover, type: 'done' };
    }
  });

  // panel: false (a link that hides the panel) must not change what later visits remember
  const collapse = collapsiblePanel(hud, panel, { key: opts.panel === false ? 'fea-panel-collapsed-by-link' : 'fea-panel-collapsed',
                                                  onChange: () => stage.setInsets(insets()) });
  if (opts.panel === false) collapse.set(true);
  const onResize = () => {                            // a resized or rotated screen: refit unless the user has moved the view
    if (!userMoved && !fly && picked < 0) fit(lastView); else stage.setInsets(insets());
  };
  window.addEventListener('resize', onResize);
  setField('ratio');
  update();
  S_.dirty = false;
  fit('iso');
  stage.start();
  let disposed = false;
  function dispose() {                                // free the GPU and the listeners, empty the element
    if (disposed) return;
    disposed = true;
    stopPlay();
    window.removeEventListener('resize', onResize);
    const seen = new Set();
    for (const root of [model, ring, probeDot]) {
      root.traverse((o) => {
        if (o.geometry && !seen.has(o.geometry)) { seen.add(o.geometry); o.geometry.dispose(); }
        for (const m of [].concat(o.material || [])) if (!seen.has(m)) { seen.add(m); m.dispose(); }
      });
    }
    if (stage.dispose) stage.dispose();
    else { stage.renderer.dispose(); stage.renderer.forceContextLoss(); }
    element.innerHTML = '';
  }
  return { stage, data, setLoad, setField, setExaggeration, setClip, flyTo, fit, collapse, dispose,
           play: (on = true) => (on ? startPlay() : stopPlay()) };
}
