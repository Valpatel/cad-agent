/** <cad-cantilever>: an interactive snap-fit arm. Sliders set the arm, and the beam bends along its computed curve,
 * coloured by strain, with the root strain, force and pass or fail against the filament's allowable strain.
 *
 *   <link rel="stylesheet" href="/kit/cantilever.css">           (in <head>: it keeps the space before the script runs)
 *   <script type="module" src="/kit/cantilever.js"></script>
 *   <cad-cantilever material="copa-polymaker-dry" direction="along" design="1" length="20" thickness="1.6"
 *                   width="6" deflection="1.5"><img src="still.svg" alt="…" width="640" height="250"></cad-cantilever>
 *
 * Attributes (all optional; mm for lengths): `material` (a key of formulas-data.js), `direction` (`along` or
 * `across` the layers), `design` (1 constant, 2 thickness tapered to h/2, 3 width tapered to b/4), `repeated`
 * (present: opened often, 60 % of the allowable), `length`, `thickness` (at the root), `width`, `deflection` (at the
 * hook). Out-of-range values are clamped. The element's children are the still shown before the script loads; the
 * live figure replaces them at the same size, so nothing moves.
 *
 * The numbers come from formulas.js, the tested port of cadagent.formulas (the Covestro method as `cad-agent
 * snapfit` applies it); the curve is the exact Euler-Bernoulli shape for the section. `drawCantilever()` is pure,
 * so tools/cantilever-still.mjs draws the still from the same code. No dependencies, no shadow DOM, no inline script.
 * The animation pauses off screen, starts paused under prefers-reduced-motion, and has a pause button. Each change
 * fires `cad-cantilever-change` with `{ state, result }`.
 */
import { snapArm, cantileverShape, cantileverStrainProfile, cantileverThicknessProfile } from './formulas.js';
import { MATERIALS } from './formulas-data.js';

export const VIEW = Object.freeze({ width: 640, height: 250 });
export const CONTROLS = Object.freeze({
  length: { label: 'Length', min: 5, max: 40, step: 0.5, unit: 'mm' },
  thickness: { label: 'Root thickness', min: 0.6, max: 4, step: 0.1, unit: 'mm' },
  width: { label: 'Width', min: 2, max: 20, step: 0.5, unit: 'mm' },
  deflection: { label: 'Deflection at the hook', min: 0.1, max: 5, step: 0.05, unit: 'mm' },
});
export const DEFAULTS = Object.freeze({ material: 'copa-polymaker-dry', direction: 'along', design: 1, repeated: false,
  length: 20, thickness: 1.6, width: 6, deflection: 1.5 });
const SECTIONS = { 1: 'Constant', 2: 'Thinner tip (h/2)', 3: 'Narrower tip (b/4)' };
const DIRECTIONS = { along: 'Flat on the bed (along the layers)', across: 'Upright (across the layers)' };
const X0 = 64, Y0 = 136, SCALE = 11;        // root, rest centre line (SVG units), SVG units per mm
// The root-strain label sits just above the root, or under the length dimension when the arm is too short for it.
const strainLabelY = s => s.length * SCALE < 150 ? 58 : Y0 - s.thickness * SCALE / 2 - 12;
const INK = '#173d3c', SAGE = '#6f8a80', MIST = '#eef1e4', CREAM = '#fffdf5', PEACH = '#ffe1cc', RUST = '#bd3a12';

/** The state from attribute values (`get(name)` returns a string or null): unknown values fall back, numbers clamp. */
export function readState(get) {
  const s = { ...DEFAULTS };
  const material = get('material');
  if (MATERIALS.some(m => m.key === material)) s.material = material;
  if (Object.hasOwn(DIRECTIONS, get('direction') ?? '')) s.direction = get('direction');   // not inherited keys
  if (Number(get('design')) in SECTIONS) s.design = Number(get('design'));
  const repeated = get('repeated');
  if (repeated !== null && repeated !== undefined) s.repeated = repeated !== 'false';
  for (const [k, c] of Object.entries(CONTROLS)) {
    const v = parseFloat(get(k));
    if (Number.isFinite(v)) s[k] = Math.min(c.max, Math.max(c.min, v));
  }
  return s;
}

/** Root strain, force, stiffness and the verdict for a state (lengths in mm), with the material and its allowable. */
export function compute(s) {
  const material = MATERIALS.find(m => m.key === s.material);
  const allowable = material.allowable[s.direction][s.repeated ? 'repeated' : 'single'];
  const modulus = material.modulus[s.direction];
  return { ...snapArm(s.length / 1e3, s.thickness / 1e3, s.width / 1e3, s.deflection / 1e3, modulus, allowable, s.design),
    allowable, modulus, material };
}

const pct = x => `${(x * 100).toFixed(2)} %`;
const num = (x, unit) => `${x >= 100 ? x.toFixed(0) : x >= 10 ? x.toFixed(1) : x.toFixed(2)} ${unit}`;
const mm = x => `${Number(x.toFixed(2))} mm`;
export function summary(s, r) {
  return `${r.material.name}, ${s.direction === 'along' ? 'along' : 'across'} the layers: root strain ${pct(r.strain)}, ` +
    `${Math.round(r.ratio * 100)} % of the ${pct(r.allowable)} allowed, ${r.passes ? 'pass' : 'fail'}` +
    `${r.smallDeflection ? '' : ' (outside small deflection)'}; force ${num(r.force, 'N')}.`;
}

const hex = c => [1, 3, 5].map(i => parseInt(c.slice(i, i + 2), 16));
const mix = (a, b, t) => '#' + hex(a).map((v, i) => Math.round(v + (hex(b)[i] - v) * t).toString(16).padStart(2, '0')).join('');
/** Strain over the allowable to a colour: mist at rest, peach from 70 %, rust at the limit and beyond. */
export const strainColour = t => t <= 0 ? MIST : t < 0.7 ? mix(MIST, PEACH, t / 0.7) : t < 1 ? mix(PEACH, RUST, (t - 0.7) / 0.3) : RUST;

const f = n => Number(n.toFixed(2));
const pts = list => list.map(([x, y]) => `${f(x)},${f(y)}`).join(' ');
function outline(s, phase) {
  const L = s.length * SCALE, h = s.thickness * SCALE, lift = s.deflection * SCALE * phase, top = [], bottom = [];
  for (let i = 0; i <= 40; i++) {
    const xi = i / 40, x = X0 + xi * L, y = Y0 - lift * cantileverShape(xi, s.design);
    const half = h * cantileverThicknessProfile(xi, s.design) / 2;
    top.push([x, y - half]); bottom.push([x, y + half]);
  }
  return [...top, ...bottom.reverse()];
}

/** Everything the figure draws for a state at an animation phase (0 at rest, 1 at the full deflection). */
export function geometry(s, r, phase = 1) {
  const L = s.length * SCALE, xTip = X0 + L, lift = s.deflection * SCALE * phase;
  const halfTip = s.thickness * SCALE * cantileverThicknessProfile(1, s.design) / 2;
  const under = Y0 - lift + halfTip;                              // underside of the tip
  const hookH = Math.max(4, s.deflection * SCALE), hookL = Math.min(hookH * 1.732, 0.45 * L);
  const catchTop = under + hookH;
  return {
    rest: pts(outline(s, 0)), beam: pts(outline(s, phase)), xTip,
    hook: pts([[xTip - hookL, under], [xTip, under + hookH], [xTip, under]]),
    catch: pts([[xTip - hookL - 8, catchTop + 18], [xTip - hookL + 2, catchTop], [xTip + 16, catchTop], [xTip + 16, catchTop + 18]]),
    arrow: { x: xTip + 30, y1: catchTop + 22, y2: catchTop + 3 },
    stops: Array.from({ length: 11 }, (_, k) => ({ offset: k / 10, colour: strainColour(phase * r.ratio * cantileverStrainProfile(k / 10, s.design)) })),
    rootColour: strainColour(phase * r.ratio),
    dimY: { x: xTip + 14, y1: Y0, y2: Y0 - s.deflection * SCALE },
    labels: { length: `L ${mm(s.length)}`, deflection: `y ${mm(s.deflection)}`, force: `P ${num(r.force, 'N')}`,
      strain: `ε ${pct(r.strain)}`, verdict: `${r.passes ? 'PASS' : 'FAIL'} · ${Math.round(r.ratio * 100)} % of allowable` },
    passes: r.passes,
  };
}

/** The figure as SVG markup. `id` makes the gradient's id unique on a page; `still` adds what a standalone file
 * needs (namespace, size, title, a background, a font). */
export function drawCantilever(s, r, { phase = 1, id = 'cc', still = false, label = summary(s, r) } = {}) {
  const g = geometry(s, r, phase);
  const { width: W, height: H } = VIEW;
  const esc = t => String(t).replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
  const hatch = Array.from({ length: 9 }, (_, i) => `<line x1="20" y1="${52 + i * 20}" x2="64" y2="${36 + i * 20}"/>`).join('');
  return `<svg${still ? ' xmlns="http://www.w3.org/2000/svg"' : ''} viewBox="0 0 ${W} ${H}"${still ? ` width="${W}" height="${H}"` : ''} role="img" aria-label="${esc(label)}">` +
    (still ? `<title>${esc(label)}</title><rect width="${W}" height="${H}" fill="${CREAM}"/>` : '') +
    `<g font-family="${still ? 'Inter,system-ui,-apple-system,Segoe UI,sans-serif' : 'inherit'}" font-size="15" fill="${INK}">` +
    `<defs><linearGradient id="${id}-strain" gradientUnits="userSpaceOnUse" x1="${X0}" y1="0" x2="${f(g.xTip)}" y2="0">` +
    g.stops.map((st, i) => `<stop data-i="${i}" offset="${st.offset}" stop-color="${st.colour}"/>`).join('') + '</linearGradient></defs>' +
    `<rect x="20" y="36" width="44" height="180" rx="4" fill="${MIST}" stroke="${SAGE}"/><g stroke="${SAGE}" stroke-width="1.2">${hatch}</g>` +
    `<line data-part="dim-l" x1="${X0}" y1="26" x2="${f(g.xTip)}" y2="26" stroke="${SAGE}" stroke-width="1.5"/>` +
    `<line data-part="dim-l0" x1="${X0}" y1="20" x2="${X0}" y2="32" stroke="${SAGE}" stroke-width="1.5"/>` +
    `<line data-part="dim-l1" x1="${f(g.xTip)}" y1="20" x2="${f(g.xTip)}" y2="32" stroke="${SAGE}" stroke-width="1.5"/>` +
    `<text data-part="label-length" x="${f((X0 + g.xTip) / 2)}" y="18" text-anchor="middle">${esc(g.labels.length)}</text>` +
    `<polygon data-part="rest" points="${g.rest}" fill="none" stroke="${SAGE}" stroke-width="1.5" stroke-dasharray="5 4"/>` +
    `<polygon data-part="catch" points="${g.catch}" fill="${INK}" opacity=".85"/>` +
    `<polygon data-part="hook" points="${g.hook}" fill="url(#${id}-strain)" stroke="${INK}" stroke-width="2" stroke-linejoin="round"/>` +
    `<polygon data-part="beam" points="${g.beam}" fill="url(#${id}-strain)" stroke="${INK}" stroke-width="2" stroke-linejoin="round"/>` +
    `<circle data-part="root" cx="${X0 + 2}" cy="${Y0}" r="5" fill="${g.rootColour}" stroke="${INK}" stroke-width="1.5"/>` +
    `<text data-part="label-strain" x="${X0 + 10}" y="${f(strainLabelY(s))}" font-weight="700">${esc(g.labels.strain)}</text>` +
    `<line data-part="dim-y" x1="${f(g.dimY.x)}" y1="${f(g.dimY.y1)}" x2="${f(g.dimY.x)}" y2="${f(g.dimY.y2)}" stroke="${SAGE}" stroke-width="1.5"/>` +
    `<text data-part="label-deflection" x="${f(g.dimY.x + 8)}" y="${f((g.dimY.y1 + g.dimY.y2) / 2 + 5)}">${esc(g.labels.deflection)}</text>` +
    `<path data-part="arrow" d="M${f(g.arrow.x)} ${f(g.arrow.y1)}V${f(g.arrow.y2)}m-5 7l5-7 5 7" fill="none" stroke="${RUST}" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"/>` +
    `<text data-part="label-force" x="${f(g.arrow.x + 9)}" y="${f(g.arrow.y1 - 2)}" fill="${RUST}">${esc(g.labels.force)}</text>` +
    `<rect data-part="verdict-box" x="72" y="202" width="264" height="32" rx="16" fill="${g.passes ? MIST : PEACH}" stroke="${g.passes ? SAGE : RUST}"/>` +
    `<text data-part="label-verdict" x="204" y="223" text-anchor="middle" font-weight="700" fill="${g.passes ? INK : RUST}">${esc(g.labels.verdict)}</text>` +
    '</g></svg>';
}

// ----------------------------------------------------------------------------- the element (browsers only)
const Base = globalThis.HTMLElement ?? class {};
let instances = 0;
const SLOW = 3200;                         // ms per cycle: bend, hold, release, rest
const HOLD = 0.3;                          // where the hold at full deflection starts, as a fraction of the cycle

function phaseAt(t) {                      // 0 at rest, 1 at full deflection; eased
  const u = (t % SLOW) / SLOW, ease = v => v < 0.5 ? 2 * v * v : 1 - (-2 * v + 2) ** 2 / 2;
  if (u < HOLD) return ease(u / HOLD);
  if (u < 0.72) return 1;
  if (u < 0.92) return 1 - ease((u - 0.72) / 0.2);
  return 0;
}

export class CadCantilever extends Base {
  static get observedAttributes() { return ['material', 'direction', 'design', 'repeated', ...Object.keys(CONTROLS)]; }

  connectedCallback() {
    this.reduced ??= matchMedia('(prefers-reduced-motion: reduce)');
    if (!this.built) {
      this.built = true;
      this.uid = `cc${++instances}`;
      this.state = readState(n => this.getAttribute(n));
      this.playing = !this.reduced.matches;
      // The animation's own clock, in ms into the cycle. It starts in the hold at full deflection, which is the
      // still, so the first live frame is the still however late the script arrives; it stops while the
      // animation does and carries on from the frame on screen.
      this.elapsed = HOLD * SLOW;
      this.visible = true;
      this.build();
      this.update();
    }
    this.onMotion ??= () => this.setPlaying(!this.reduced.matches);
    this.reduced.addEventListener?.('change', this.onMotion);
    if (typeof IntersectionObserver !== 'undefined') {
      this.seen ??= new IntersectionObserver(([e]) => { this.visible = e.isIntersecting; this.loop(); });
      this.seen.observe(this);
    }
    this.loop();
  }

  disconnectedCallback() {
    this.loop();                                 // not connected: stops, keeping the clock
    this.seen?.disconnect();
    this.reduced?.removeEventListener?.('change', this.onMotion);
    clearTimeout(this.announce);
  }

  attributeChangedCallback() {
    if (!this.built) return;
    this.state = readState(n => this.getAttribute(n));
    this.syncControls();
    this.update();
  }

  build() {
    const id = n => `${this.uid}-${n}`;
    const esc = t => String(t).replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
    // The visible value is a plain span, not an <output> (an implicit live region): the slider speaks its own value
    // (aria-valuetext), and only the debounced .cc-status line announces results.
    const slider = (k, c) => `<div class="cc-field"><label for="${id(k)}">${c.label} <span class="cc-value" data-out="${k}" aria-hidden="true"></span></label>` +
      `<input id="${id(k)}" type="range" name="${k}" min="${c.min}" max="${c.max}" step="${c.step}"></div>`;
    const radios = (name, options) => Object.entries(options).map(([v, text]) =>
      `<label><input type="radio" name="${id(name)}" value="${v}" data-name="${name}"> ${esc(text)}</label>`).join('');
    this.replaceChildren();
    this.insertAdjacentHTML('beforeend', `<div class="cc-figure"></div><div class="cc-panel">
<div class="cc-readout">
<p class="cc-tile"><span class="cc-k">Root strain</span><b data-out="strain"></b><span data-out="allowed"></span></p>
<p class="cc-tile" data-out="verdict-tile"><span class="cc-k">Verdict</span><b data-out="verdict"></b><span data-out="ratio"></span></p>
<p class="cc-tile"><span class="cc-k">Force</span><b data-out="force"></b><span data-out="stiffness"></span></p></div>
<div class="cc-controls"><div class="cc-sliders">${Object.entries(CONTROLS).map(([k, c]) => slider(k, c)).join('')}</div>
<div class="cc-choices"><div class="cc-field"><label for="${id('material')}">Material</label><select id="${id('material')}" name="material">${MATERIALS.map(m =>
  `<option value="${esc(m.key)}">${esc(m.name)}</option>`).join('')}</select></div>
<div class="cc-field"><label for="${id('design')}">Section</label><select id="${id('design')}" name="design">${Object.entries(SECTIONS).map(([v, t]) =>
  `<option value="${v}">${esc(t)}</option>`).join('')}</select></div>
<fieldset><legend>Arm printed</legend>${radios('direction', DIRECTIONS)}</fieldset>
<label class="cc-check"><input type="checkbox" name="repeated"> Opened often (60 % of the allowable)</label></div></div>
<div class="cc-foot"><p class="cc-note">A closed form (Covestro method, small deflection), not proof of strength: print a test arm and measure.</p>
<button type="button" class="cc-play"></button></div>
<p class="cc-status" role="status" aria-live="polite"></p></div>`);
    this.figure = this.querySelector('.cc-figure');
    this.figure.innerHTML = drawCantilever(this.state, compute(this.state), { id: this.uid });
    this.svg = this.figure.querySelector('svg');
    this.parts = Object.fromEntries([...this.svg.querySelectorAll('[data-part]')].map(n => [n.dataset.part, n]));
    this.stops = [...this.svg.querySelectorAll('stop')];
    this.out = Object.fromEntries([...this.querySelectorAll('[data-out]')].map(n => [n.dataset.out, n]));
    this.play = this.querySelector('.cc-play');
    this.status = this.querySelector('.cc-status');
    this.play.addEventListener('click', () => this.setPlaying(!this.playing));
    this.addEventListener('input', e => this.onInput(e));
    this.addEventListener('change', e => this.onInput(e));
    this.syncControls();
  }

  syncControls() {
    for (const k of Object.keys(CONTROLS)) this.querySelector(`input[name="${k}"]`).value = this.state[k];
    this.querySelector('select[name="material"]').value = this.state.material;
    this.querySelector('select[name="design"]').value = String(this.state.design);
    for (const r of this.querySelectorAll('input[type="radio"]')) r.checked = String(this.state[r.dataset.name]) === r.value;
    this.querySelector('input[name="repeated"]').checked = this.state.repeated;
  }

  onInput(e) {
    const t = e.target;
    if (!t.matches?.('input, select')) return;
    const name = t.dataset.name || t.name;
    if (name in CONTROLS) this.state[name] = Number(t.value);
    else if (name === 'design') this.state.design = Number(t.value);
    else if (name === 'repeated') this.state.repeated = t.checked;
    else if (name === 'material' || name === 'direction') this.state[name] = t.value;
    else return;
    this.update();
  }

  setPlaying(on) {
    if (on && !this.playing) this.elapsed = HOLD * SLOW;     // paused shows full deflection: carry on from there
    this.playing = on;
    this.loop();
    this.render();
  }

  update() {
    const s = this.state, r = this.result = compute(s);
    for (const [k, c] of Object.entries(CONTROLS)) {
      this.out[k].textContent = mm(s[k]);
      this.querySelector(`input[name="${k}"]`).setAttribute('aria-valuetext', `${Number(s[k].toFixed(2))} millimetres`);
    }
    this.out.strain.textContent = pct(r.strain);
    this.out.allowed.textContent = `of ${pct(r.allowable)} allowed`;
    this.out.verdict.textContent = r.passes ? 'PASS' : 'FAIL';
    this.out.ratio.textContent = `${Math.round(r.ratio * 100)} % of allowable${r.smallDeflection ? '' : ' · y > L/10'}`;
    this.out['verdict-tile'].dataset.verdict = r.passes ? 'pass' : 'fail';
    this.out.force.textContent = num(r.force, 'N');
    this.out.stiffness.textContent = `at the hook · ${num(r.stiffness / 1e3, 'N/mm')}`;
    const text = summary(s, r);
    this.svg.setAttribute('aria-label', text);
    clearTimeout(this.announce);                 // screen readers hear the result once the slider stops moving
    this.announce = setTimeout(() => { this.status.textContent = text; }, 700);
    this.render();
    this.dispatchEvent(new CustomEvent('cad-cantilever-change', { bubbles: true, detail: { state: { ...s }, result: { ...r, material: r.material.key } } }));
  }

  clock() { return this.frame ? performance.now() - this.t0 : this.elapsed; }

  render(phase = this.playing ? phaseAt(this.clock()) : 1) {
    const s = this.state, r = this.result, g = geometry(s, r, phase), p = this.parts, set = (n, a) => { for (const k in a) n.setAttribute(k, a[k]); };
    set(p.rest, { points: g.rest }); set(p.beam, { points: g.beam }); set(p.hook, { points: g.hook }); set(p.catch, { points: g.catch });
    set(p.root, { fill: g.rootColour });
    g.stops.forEach((st, i) => this.stops[i].setAttribute('stop-color', st.colour));
    this.svg.querySelector('linearGradient').setAttribute('x2', f(g.xTip));
    set(p['dim-l'], { x2: f(g.xTip) }); set(p['dim-l1'], { x1: f(g.xTip), x2: f(g.xTip) });
    set(p['label-length'], { x: f((X0 + g.xTip) / 2) }); p['label-length'].textContent = g.labels.length;
    set(p['label-strain'], { y: f(strainLabelY(s)) }); p['label-strain'].textContent = g.labels.strain;
    set(p['dim-y'], { x1: f(g.dimY.x), x2: f(g.dimY.x), y2: f(g.dimY.y2) });
    set(p['label-deflection'], { x: f(g.dimY.x + 8), y: f((g.dimY.y1 + g.dimY.y2) / 2 + 5) }); p['label-deflection'].textContent = g.labels.deflection;
    set(p.arrow, { d: `M${f(g.arrow.x)} ${f(g.arrow.y1)}V${f(g.arrow.y2)}m-5 7l5-7 5 7` });
    set(p['label-force'], { x: f(g.arrow.x + 9), y: f(g.arrow.y1 - 2) }); p['label-force'].textContent = g.labels.force;
    set(p['verdict-box'], { fill: g.passes ? MIST : PEACH, stroke: g.passes ? SAGE : RUST });
    set(p['label-verdict'], { fill: g.passes ? INK : RUST }); p['label-verdict'].textContent = g.labels.verdict;
    this.play.textContent = this.playing ? 'Pause' : 'Play';
    this.play.setAttribute('aria-label', `${this.playing ? 'Pause' : 'Play'} the bending animation`);
  }

  loop() {
    const run = this.playing && this.visible && this.isConnected;
    if (run && !this.frame) {
      this.t0 = performance.now() - this.elapsed;
      const tick = () => { this.render(); this.frame = requestAnimationFrame(tick); };
      this.frame = requestAnimationFrame(tick);
    } else if (!run && this.frame) {
      this.elapsed = this.clock();
      cancelAnimationFrame(this.frame); this.frame = 0;
    }
  }
}

if (typeof customElements !== 'undefined' && !customElements.get('cad-cantilever')) customElements.define('cad-cantilever', CadCantilever);
