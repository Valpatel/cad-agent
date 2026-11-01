/** <cad-fan-curve>: a fan curve against a system curve. Pick the supply voltage of a real fan (its datasheet curve),
 * set how much pressure the enclosure needs, and use one to four fans in parallel or in series; the chart marks where
 * the curves cross (the operating point), the airflow and pressure there, and the fan's stall region.
 *
 *   <link rel="stylesheet" href="/kit/fan-curve.css">            (in <head>: it keeps the space before the script runs)
 *   <script type="module" src="/kit/fan-curve.js"></script>
 *   <cad-fan-curve fan="12" system="12" count="1" arrangement="parallel">
 *     <img src="still.svg" alt="…" width="640" height="340"></cad-fan-curve>
 *
 * Attributes (all optional): `fan` (the supply voltage, `8`, `12` or `16`, each a curve from the datasheet in
 * formulas-data.js), `system` (the pressure drop in Pa the enclosure needs at 100 m³/h, which fixes k in
 * dp = k Q²), `count` (1 to 4 identical fans), `arrangement` (`parallel` or `series`), `theme` (`light` or `dark`; by
 * default the page's color-scheme, else the reader's preference). Out-of-range values are clamped. The element's
 * children are the still shown before the script loads; the live figure replaces them at the same size.
 *
 * Every number comes from formulas.js, the tested port of cadagent.formulas.thermal: fansInParallel, fansInSeries,
 * systemCoefficient, fanOperatingPoint and fanStallFlow (White's Fluid Mechanics, Section 11.5). Steady flow, one air
 * density, identical fans with no interaction losses, the maker's test rig. `drawFanCurve()` is pure, so
 * tools/fan-curve-still.mjs draws the still from the same code. Nothing moves on its own, so there is no motion to
 * reduce. No dependencies, no shadow DOM, no inline script. Each change fires `cad-fan-curve-change` with
 * `{ state, result }`.
 */
import { fansInParallel, fansInSeries, systemCoefficient, fanOperatingPoint, fanStallFlow } from './formulas.js';
import { FANS } from './formulas-data.js';

export const VIEW = Object.freeze({ width: 640, height: 340 });
/** The system slider sets the pressure drop at this flow: 100 m³/h, in m³/s. */
export const REFERENCE_FLOW = 100 / 3600;
export const CONTROLS = Object.freeze({
  system: { label: 'System: pressure drop at 100 m³/h', min: 2, max: 60, step: 1 },
  count: { label: 'Fans', min: 1, max: 4, step: 1 },
});
export const VOLTAGES = Object.freeze(FANS.map(f => String(f.voltage)));
export const ARRANGEMENTS = Object.freeze({ parallel: 'Parallel', series: 'Series' });
// The datasheet's nominal 12 V, against an enclosure that needs 12 Pa at 100 m³/h: clear of the stall region.
export const DEFAULTS = Object.freeze({ fan: '12', system: 12, count: 1, arrangement: 'parallel' });
export const PALETTES = Object.freeze({
  light: Object.freeze({ ink: '#173d3c', muted: '#526863', sage: '#6f8a80', mist: '#eef1e4', back: '#fffdf5', peach: '#ffe1cc',
    rust: '#bd3a12', teal: '#1f6b64', line: '#dfe7dc' }),
  dark: Object.freeze({ ink: '#e6efe9', muted: '#a8bcb5', sage: '#86a499', mist: '#21393a', back: '#11201f', peach: '#4b2b1d',
    rust: '#ff9466', teal: '#6fd0c4', line: '#2b4542' }),
});
const M3H = 3600, CFM = 1.699010796;                            // m³/h in one m³/s, and in one ft³/min
const f = n => Number(n.toFixed(2));
const esc = t => String(t).replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
const halo = (P, width = 4) => ` stroke="${P.back}" stroke-width="${width}" stroke-linejoin="round" paint-order="stroke"`;
const WORDS = ['', 'one', 'two', 'three', 'four'];
/** Flow in m³/s as whole m³/h, and pressure to 0.1 Pa, as the readouts show them. */
export const m3h = q => `${Math.round(q * M3H)} m³/h`;
export const pa = p => `${p.toFixed(1)} Pa`;
// Text sizes and the plot area in SVG units: on a phone (compact) the 640-wide figure is drawn at about half size, so
// its text is larger and the plot leaves more room for the tick labels.
const SIZES = {
  normal: { text: 14, small: 12.5, plot: { x0: 62, x1: 620, y0: 50, y1: 292 }, ticks: 6 },
  compact: { text: 23, small: 21, plot: { x0: 84, x1: 622, y0: 80, y1: 270 }, ticks: 4 },
};

/** The state from attribute values (`get(name)` returns a string or null): unknown values fall back, numbers clamp. */
export function readState(get) {
  const s = { ...DEFAULTS };
  if (VOLTAGES.includes(get('fan') ?? '')) s.fan = get('fan');
  for (const [k, c] of Object.entries(CONTROLS)) {
    const v = parseFloat(get(k));
    if (Number.isFinite(v)) s[k] = Math.min(c.max, Math.max(c.min, Math.round(v / c.step) * c.step));
  }
  if (Object.hasOwn(ARRANGEMENTS, get('arrangement') ?? '')) s.arrangement = get('arrangement');
  return s;
}

/** A tick step near max / count from 1, 2, 2.5 and 5 times a power of ten; and the axis's top, a whole step above. */
function axis(max, count) {
  const raw = max / count, mag = 10 ** Math.floor(Math.log10(raw)), n = raw / mag;
  const step = (n <= 1 ? 1 : n <= 2 ? 2 : n <= 2.5 ? 2.5 : n <= 5 ? 5 : 10) * mag;
  return { step, top: step * Math.ceil((max * 1.04) / step) };
}

/** Everything the demo shows for a state, from the port: the fan, its curve and the combined one, k, the operating
 * point, the stall flows (of the combined curve, and of one fan) and what one fan carries at the point. */
export function compute(s) {
  const fan = FANS.find(x => String(x.voltage) === s.fan);
  const single = fan.curve;
  const curve = s.arrangement === 'series' ? fansInSeries(single, s.count) : fansInParallel(single, s.count);
  const k = systemCoefficient(s.system, REFERENCE_FLOW);
  const op = fanOperatingPoint(curve, k);
  const parallel = s.arrangement === 'parallel';
  const each = { flow: parallel ? op.flow / s.count : op.flow, pressure: parallel ? op.pressure : op.pressure / s.count };
  return { fan, single, curve, k, op, stall: fanStallFlow(curve), stallEach: fanStallFlow(single), each };
}

const fans = s => (s.count === 1 ? 'one fan' : `${WORDS[s.count]} fans in ${s.arrangement}`);
/** Where it runs, as the third tile says it: a verdict, its note, and whether it is a warning. */
export function verdict(s, r) {
  const n = r.op.intersections.length, perFan = s.count > 1 && s.arrangement === 'parallel';
  if (n > 1) return { text: 'Unstable', note: `Crosses the curve ${n} times`, poor: true };
  if (r.op.stall) return { text: 'In stall', note: perFan ? `${m3h(r.each.flow)} each, under ${m3h(r.stallEach)}` : `Below ${m3h(r.stall)}`, poor: true };
  return { text: 'Clear of stall', note: r.stall === null ? 'No stall dip' : `Stall below ${m3h(perFan ? r.stallEach : r.stall)}${perFan ? ' each' : ''}`, poor: false };
}

export function summary(s, r) {
  const n = r.op.intersections.length, perFan = s.count > 1 && s.arrangement === 'parallel';
  let out = `Fan-curve explorer: ${fans(s)} (${r.fan.name}) against a system that needs ${s.system} Pa at 100 m³/h ` +
    `delivers ${m3h(r.op.flow)} at ${pa(r.op.pressure)}`;
  if (n > 1) out += `; the system crosses the fan curve ${n} times, so the fan can settle at any of them, and the highest flow is shown`;
  if (r.stall === null) return `${out}; this curve has no stall dip.`;
  const where = perFan ? `; each fan carries ${m3h(r.each.flow)}` : '';
  return r.op.stall ? `${out}${where}, in the stall region (below ${m3h(perFan ? r.stallEach : r.stall)}${perFan ? ' for one fan' : ''}), which the ` +
    "maker's table leaves out: louder and less efficient, and on a flat or rising stretch the flow swings with small changes in the system."
    : `${out}${where}, clear of the stall region, which is below ${m3h(perFan ? r.stallEach : r.stall)}${perFan ? ' for one fan' : ''}.`;
}

// ----------------------------------------------------------------------------- the chart
/** The chart's scales for a state: flow (m³/h) and pressure (Pa) axes, and the mapping to SVG units. */
export function scales(r, compact = false) {
  const z = SIZES[compact ? 'compact' : 'normal'], P = z.plot;
  const qx = axis(r.curve.at(-1)[0] * M3H, z.ticks), py = axis(Math.max(...r.curve.map(p => p[1])), z.ticks - 1);
  return { ...P, qx, py, x: q => P.x0 + (P.x1 - P.x0) * (q * M3H) / qx.top, y: p => P.y1 - (P.y1 - P.y0) * p / py.top };
}
const line = (sc, pts) => pts.map(([q, p]) => `${f(sc.x(q))},${f(sc.y(p))}`).join(' ');
/** The system curve k Q² from 0 to where it leaves the plot (its top or its right edge). */
function systemPoints(sc, k) {
  const qTop = Math.min(sc.qx.top / M3H, Math.sqrt(sc.py.top / k)), pts = [];
  for (let i = 0; i <= 48; i++) { const q = qTop * i / 48; pts.push([q, k * q * q]); }
  return pts;
}

/** The figure as SVG markup. `still` adds what a standalone file needs (namespace, size, title, background, a font);
 * `palette` is one of PALETTES; `compact` sizes the text for a phone. */
export function drawFanCurve(s, r, { still = false, label = summary(s, r), palette = PALETTES.light, compact = false } = {}) {
  const P = palette, z = SIZES[compact ? 'compact' : 'normal'], sc = scales(r, compact), { width: W, height: H } = VIEW;
  const v = verdict(s, r);
  let grid = '', ticks = '';
  for (let q = 0; q <= sc.qx.top + 1e-9; q += sc.qx.step) {
    const x = f(sc.x(q / M3H));
    grid += `<line x1="${x}" y1="${sc.y0}" x2="${x}" y2="${sc.y1}" stroke="${P.line}"/>`;
    ticks += `<text x="${x}" y="${f(sc.y1 + 6 + z.small)}" text-anchor="middle">${Number(q.toFixed(1))}</text>`;
  }
  for (let p = 0; p <= sc.py.top + 1e-9; p += sc.py.step) {
    const y = f(sc.y(p));
    grid += `<line x1="${sc.x0}" y1="${y}" x2="${sc.x1}" y2="${y}" stroke="${P.line}"/>`;
    ticks += `<text x="${sc.x0 - 8}" y="${f(y + z.small / 3)}" text-anchor="end">${Number(p.toFixed(1))}</text>`;
  }
  // the stall region: every flow below the stall peak of the curve shown (for fans in parallel, n times one fan's)
  const stallX = r.stall === null ? sc.x0 : Math.min(sc.x1, sc.x(r.stall));
  const band = `<rect data-part="stall" x="${sc.x0}" y="${sc.y0}" width="${f(stallX - sc.x0)}" height="${f(sc.y1 - sc.y0)}" fill="${P.peach}"/>`;
  const [ox, oy] = [f(sc.x(r.op.flow)), f(sc.y(r.op.pressure))];
  // the point's label sits above it, to its right unless that runs off the plot
  const text = `${m3h(r.op.flow)} · ${pa(r.op.pressure)}`, wide = 0.56 * z.text * text.length;
  const right = ox + 12 + wide <= sc.x1, lx = right ? ox + 12 : ox - 12, ly = Math.max(sc.y0 + z.text, oy - 12);
  const others = r.op.intersections.slice(0, -1).map(([q, p]) =>
    `<circle cx="${f(sc.x(q))}" cy="${f(sc.y(p))}" r="5" fill="${P.back}" stroke="${P.ink}" stroke-width="2"/>`).join('');
  // the legend: one line above the plot, a key and a word for each mark (shorter words on a phone)
  const fanWord = s.count === 1 ? 'fan curve' : compact ? `${s.count} fans` : `${WORDS[s.count]} in ${s.arrangement}`;
  const items = [[`<line x2="22" stroke="${P.teal}" stroke-width="3"/>`, fanWord],
    ...(s.count > 1 ? [[`<line x2="22" stroke="${P.sage}" stroke-width="2" stroke-dasharray="5 4"/>`, 'one fan']] : []),
    [`<line x2="22" stroke="${P.rust}" stroke-width="2.5"/>`, 'system'],
    [`<rect y="-6" width="22" height="12" fill="${P.peach}" stroke="${P.rust}" stroke-width="0.8"/>`, compact ? 'stall' : 'stall region']];
  let lx0 = compact ? 8 : sc.x0, legend = '';
  for (const [key, word] of items) {
    legend += `<g transform="translate(${f(lx0)} ${f(z.small + 6)})">${key}<text x="28" y="${f(z.small / 3)}">${esc(word)}</text></g>`;
    lx0 += 28 + 0.52 * z.small * word.length + (compact ? 14 : 22);
  }
  return `<svg${still ? ' xmlns="http://www.w3.org/2000/svg"' : ''} viewBox="0 0 ${W} ${H}"${still ? ` width="${W}" height="${H}"` : ''} role="img" aria-label="${esc(label)}">` +
    (still ? `<title>${esc(label)}</title><rect width="${W}" height="${H}" fill="${P.back}"/>` : '') +
    `<g font-family="${still ? 'Inter,system-ui,-apple-system,Segoe UI,sans-serif' : 'inherit'}" font-size="${z.small}" fill="${P.muted}">` +
    band + `<g data-part="grid">${grid}</g>` +
    `<line x1="${sc.x0}" y1="${sc.y1}" x2="${sc.x1}" y2="${sc.y1}" stroke="${P.sage}" stroke-width="1.5"/>` +
    `<line x1="${sc.x0}" y1="${sc.y0}" x2="${sc.x0}" y2="${sc.y1}" stroke="${P.sage}" stroke-width="1.5"/>` +
    `<g data-part="ticks">${ticks}</g>` +
    `<text x="${sc.x1}" y="${H - 6}" text-anchor="end" fill="${P.ink}">airflow, m³/h</text>` +
    `<text x="8" y="${f(sc.y0 - 12)}" fill="${P.ink}">pressure, Pa</text>` +
    `<g data-part="legend" fill="${P.ink}">${legend}</g>` +
    (s.count > 1 ? `<polyline data-part="single" points="${line(sc, r.single)}" fill="none" stroke="${P.sage}" stroke-width="2" stroke-dasharray="6 5" stroke-linejoin="round"/>` : '') +
    `<polyline data-part="system" points="${line(sc, systemPoints(sc, r.k))}" fill="none" stroke="${P.rust}" stroke-width="2.5" stroke-linejoin="round"/>` +
    `<polyline data-part="fan" points="${line(sc, r.curve)}" fill="none" stroke="${P.teal}" stroke-width="3" stroke-linejoin="round"/>` +
    `<g data-part="fan-points" fill="${P.teal}">${r.curve.map(([q, p]) => `<circle cx="${f(sc.x(q))}" cy="${f(sc.y(p))}" r="2.6"/>`).join('')}</g>` +
    `<path data-part="guides" d="M${ox} ${oy}V${sc.y1}M${ox} ${oy}H${sc.x0}" fill="none" stroke="${P.ink}" stroke-width="1" stroke-dasharray="3 4"/>` +
    others +
    `<circle data-part="point" cx="${ox}" cy="${oy}" r="7" fill="${v.poor ? P.rust : P.ink}" stroke="${P.back}" stroke-width="2.5"/>` +
    `<text data-part="point-label" x="${f(lx)}" y="${f(ly)}" text-anchor="${right ? 'start' : 'end'}" font-size="${z.text}" font-weight="700" fill="${P.ink}"${halo(P)}>${esc(text)}</text>` +
    `<g data-part="hover" visibility="hidden"><line y1="${sc.y0}" y2="${sc.y1}" stroke="${P.muted}"/>` +
    `<text y="${f(sc.y0 + z.small + 4)}" font-size="${z.small}" fill="${P.ink}"${halo(P)}></text></g>` +
    '</g></svg>';
}

/** What the hover line reads at a flow (m³/s): the curve shown (straight between its points; null past free air) and
 * the system. */
export function readAt(r, q) {
  const c = r.curve;
  let fan = null;
  for (let i = 0; i + 1 < c.length; i++) {
    const [q1, p1] = c[i], [q2, p2] = c[i + 1];
    if (q >= q1 && q <= q2) { fan = p1 + (p2 - p1) * (q - q1) / (q2 - q1); break; }
  }
  return { fan, system: r.k * q * q };
}

// ----------------------------------------------------------------------------- the element (browsers only)
const Base = globalThis.HTMLElement ?? class {};
let instances = 0;

export class CadFanCurve extends Base {
  static get observedAttributes() { return ['fan', 'arrangement', 'theme', ...Object.keys(CONTROLS)]; }

  connectedCallback() {
    this.dark ??= matchMedia('(prefers-color-scheme: dark)');
    this.narrow ??= matchMedia('(max-width: 699.98px)');                   // fan-curve.css's phone layout
    if (!this.built) {
      this.built = true;
      this.uid = `fc${++instances}`;
      this.state = readState(n => this.getAttribute(n));
      this.result = compute(this.state);
      this.build();
      this.update();
    }
    this.onScheme ??= () => this.applyTheme();
    this.onNarrow ??= () => this.paint();
    this.dark.addEventListener?.('change', this.onScheme);
    this.narrow.addEventListener?.('change', this.onNarrow);
  }

  disconnectedCallback() {
    this.dark?.removeEventListener?.('change', this.onScheme);
    this.narrow?.removeEventListener?.('change', this.onNarrow);
    clearTimeout(this.announce);
  }

  attributeChangedCallback(name) {
    if (!this.built) return;
    if (name === 'theme') { this.applyTheme(); return; }
    this.state = readState(n => this.getAttribute(n));
    this.syncControls();
    this.result = compute(this.state);
    this.update();
  }

  /** light or dark: the theme attribute, else the page's color-scheme, else the reader's preference. */
  theme() {
    const asked = this.getAttribute('theme');
    if (asked === 'light' || asked === 'dark') return asked;
    const scheme = getComputedStyle(this).colorScheme || '';
    if (/\blight\b/.test(scheme) !== /\bdark\b/.test(scheme)) return /\bdark\b/.test(scheme) ? 'dark' : 'light';
    return this.dark.matches ? 'dark' : 'light';
  }

  applyTheme() {
    const theme = this.theme();
    if (theme === this.dataset.theme) return;
    this.dataset.theme = theme;
    if (this.figure) this.paint();
  }

  build() {
    const id = n => `${this.uid}-${n}`;
    // The visible value is a plain span, not an <output> (an implicit live region): the slider speaks its own value
    // (aria-valuetext), and only the debounced .fc-status line announces results.
    const slider = (k, c) => `<div class="fc-field"><label for="${id(k)}">${esc(c.label)} <span class="fc-value" data-out="${k}" aria-hidden="true"></span></label>` +
      `<input id="${id(k)}" type="range" name="${k}" min="${c.min}" max="${c.max}" step="${c.step}"></div>`;
    const radios = (name, legend, options) => `<fieldset><legend>${legend}</legend>${options.map(([v, t]) =>
      `<label><input type="radio" name="${id(name)}" value="${v}" data-name="${name}"> ${t}</label>`).join('')}</fieldset>`;
    this.replaceChildren();
    this.insertAdjacentHTML('beforeend', `<div class="fc-figure"></div><div class="fc-panel">
<div class="fc-readout">
<p class="fc-tile"><span class="fc-k">Airflow</span><b data-out="flow"></b><span data-out="flow-note"></span></p>
<p class="fc-tile"><span class="fc-k">Pressure</span><b data-out="pressure"></b><span data-out="pressure-note"></span></p>
<p class="fc-tile" data-out="verdict-tile"><span class="fc-k">Where it runs</span><b data-out="verdict"></b><span data-out="verdict-note"></span></p></div>
<div class="fc-controls"><div class="fc-col">${radios('fan', 'Supply', VOLTAGES.map(v => [v, `${v} V`]))}${slider('system', CONTROLS.system)}</div>
<div class="fc-col">${slider('count', CONTROLS.count)}${radios('arrangement', 'Fans are', Object.entries(ARRANGEMENTS))}</div></div>
<p class="fc-note">Datasheet curve, ebm-papst W2G115-AD15-13, on the maker's rig; steady flow, identical fans. Your enclosure's system curve comes from a test or CFD.</p>
<p class="fc-status" role="status" aria-live="polite"></p></div>`);
    this.figure = this.querySelector('.fc-figure');
    this.out = Object.fromEntries([...this.querySelectorAll('[data-out]')].map(n => [n.dataset.out, n]));
    this.status = this.querySelector('.fc-status');
    this.addEventListener('input', e => this.onInput(e));
    this.addEventListener('change', e => this.onInput(e));
    this.figure.addEventListener('pointermove', e => this.hover(e));
    this.figure.addEventListener('pointerleave', () => this.hover(null));
    this.dataset.theme = this.theme();
    this.syncControls();
  }

  syncControls() {
    for (const k of Object.keys(CONTROLS)) this.querySelector(`input[name="${k}"]`).value = this.state[k];
    for (const r of this.querySelectorAll('input[type="radio"]')) r.checked = this.state[r.dataset.name] === r.value;
  }

  onInput(e) {
    const t = e.target;
    if (!t.matches?.('input')) return;
    const name = t.dataset.name || t.name;
    if (name in CONTROLS) this.state[name] = Number(t.value);
    else if ((name === 'fan' || name === 'arrangement') && t.checked) this.state[name] = t.value;
    else return;
    this.result = compute(this.state);
    this.update({ announce: true });
  }

  /** Draw the chart afresh (for a new state, theme or layout). */
  paint() {
    const s = this.state, r = this.result;
    this.palette = PALETTES[this.dataset.theme];
    this.compact = this.narrow.matches;
    this.figure.innerHTML = drawFanCurve(s, r, { palette: this.palette, compact: this.compact });
    this.hoverPart = this.figure.querySelector('[data-part=hover]');
  }

  /** The hover line: the flow under the pointer, and the fan's and the system's pressure there. */
  hover(e) {
    const g = this.hoverPart;
    if (!g) return;
    const svg = this.figure.firstElementChild, box = svg?.getBoundingClientRect();
    const sc = scales(this.result, this.compact);
    const x = e && box?.width ? (e.clientX - box.left) * VIEW.width / box.width : -1;
    if (x < sc.x0 || x > sc.x1) { g.setAttribute('visibility', 'hidden'); return; }
    const q = (x - sc.x0) / (sc.x1 - sc.x0) * sc.qx.top / M3H, at = readAt(this.result, q);
    const [ln, text] = g.children;
    for (const a of ['x1', 'x2']) ln.setAttribute(a, f(x));
    text.textContent = `${m3h(q)}: fan ${at.fan === null ? '–' : pa(at.fan)} · system ${pa(at.system)}`;
    const right = x < (sc.x0 + sc.x1) / 2;
    text.setAttribute('x', f(right ? x + 8 : x - 8));
    text.setAttribute('text-anchor', right ? 'start' : 'end');
    g.setAttribute('visibility', 'visible');
  }

  // Only what the user does is announced, once the slider stops moving: the first draw and attribute changes are not
  // (the figure's aria-label carries the same summary). An announcement still pending speaks the latest result.
  update({ announce = false } = {}) {
    const s = this.state, r = this.result, v = verdict(s, r);
    this.out.system.textContent = `${s.system} Pa`;
    this.querySelector('input[name="system"]').setAttribute('aria-valuetext', `${s.system} pascals at 100 cubic metres per hour`);
    this.out.count.textContent = `${s.count} ${s.count === 1 ? 'fan' : 'fans'}`;
    this.querySelector('input[name="count"]').setAttribute('aria-valuetext', `${s.count} ${s.count === 1 ? 'fan' : 'fans'}`);
    this.out.flow.textContent = m3h(r.op.flow);
    this.out['flow-note'].textContent = `${Math.round(r.op.flow * M3H / CFM)} CFM${s.count > 1 && s.arrangement === 'parallel' ? ` · ${m3h(r.each.flow)} each` : ''}`;
    this.out.pressure.textContent = pa(r.op.pressure);
    this.out['pressure-note'].textContent = s.count > 1 && s.arrangement === 'series' ? `${pa(r.each.pressure)} from each fan`
      : `System k ${Math.round(r.k).toLocaleString('en-US')} Pa·s²/m⁶`;
    this.out.verdict.textContent = v.text;
    this.out['verdict-note'].textContent = v.note;
    this.out['verdict-tile'].dataset.verdict = v.poor ? 'poor' : 'good';
    this.said = summary(s, r);
    this.paint();
    if (announce) {
      clearTimeout(this.announce);
      this.announce = setTimeout(() => { this.status.textContent = this.said; }, 700);
    }
    this.dispatchEvent(new CustomEvent('cad-fan-curve-change', { bubbles: true, detail: { state: { ...s }, result: {
      flow: r.op.flow, pressure: r.op.pressure, stable: r.op.stable, stall: r.op.stall, intersections: r.op.intersections.map(p => [...p]),
      k: r.k, stallFlow: r.stall, stallFlowEach: r.stallEach } } }));
  }
}

if (typeof customElements !== 'undefined' && !customElements.get('cad-fan-curve')) customElements.define('cad-fan-curve', CadFanCurve);
