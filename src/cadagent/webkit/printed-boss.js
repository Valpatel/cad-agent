/** <cad-printed-boss>: a thread-forming screw tightened into a printed boss. Pick the screw, the boss's outside
 * diameter and thread engagement, the tightening torque, the filament and which way the boss was printed; the figure
 * shows the boss in section with its hoop stress, and the torque window: the drive torque the screw may take to form
 * its thread, the most you should tighten to, and where the boss's thread strips.
 *
 *   <link rel="stylesheet" href="/kit/printed-boss.css">          (in <head>: it keeps the space before the script runs)
 *   <script type="module" src="/kit/printed-boss.js"></script>
 *   <cad-printed-boss material="pla-bambu-basic" size="30" outside="6" engagement="6" torque="0.3" axis="upright">
 *     <img src="still.svg" alt="…" width="640" height="300"></cad-printed-boss>
 *
 * Attributes (all optional): `material` (a key of formulas-data.js), `size` (a DELTA PT size: 20, 25, 30, 35, 40 or 50,
 * the nominal diameter in tenths of a mm), `outside` (the boss's outside diameter, mm), `engagement` (the length of
 * thread in the boss, mm), `torque` (the tightening torque, N m), `axis` (`upright`: the boss built along Z, its hoop
 * stress in the layers; `lying`: its axis in the bed plane, the hoop stress across them), `theme` (`light` or `dark`; by
 * default the page's color-scheme, else the reader's preference). Out-of-range values are clamped. The element's
 * children are the still shown before the script loads; the live figure replaces them at the same size.
 *
 * Every number comes from formulas.js, the tested port of cadagent.formulas.screw_boss, with the strengths and friction
 * band cadagent.mechanical.bosses.printed_boss uses: Shigley's torque-preload relation through a nut factor for steel
 * on plastic (0.20 to 0.65), the ISO 68-1 stripping area with half the lowest tensile strength across the layers, a
 * Lame cylinder for the wall, Covestro's window (tighten to at least 1.2 times the drive torque and at most half the
 * stripping torque) and the DELTA PT maker's proportions (outside 2 d, engagement 2 d). The drive torque is not
 * computed: it must be measured. No published pull-out data for printed bosses was found, so the result is a starting
 * point for a test boss, not a rating. `drawPrintedBoss()` is pure, so tools/printed-boss-still.mjs draws the still from
 * the same code. Nothing moves on its own. No dependencies, no shadow DOM, no inline script. Each change fires
 * `cad-printed-boss-change` with `{ state, result }`.
 */
import { screwBoss, BOSS } from './formulas.js';
import { MATERIALS, SCREWS } from './formulas-data.js';

export const VIEW = Object.freeze({ width: 640, height: 300 });
export const CONTROLS = Object.freeze({
  outside: { label: 'Outside diameter', min: 2.4, max: 20, step: 0.1, unit: 'mm' },     // min: the smallest screw's minOutside
  engagement: { label: 'Thread engagement', min: 1, max: 25, step: 0.5, unit: 'mm' },
  torque: { label: 'Tightening torque', min: 0.02, max: 3, step: 0.01, unit: 'N·m' },
});
export const AXES = Object.freeze({ upright: 'Upright (along Z)', lying: 'Lying on its side' });
// PLA, a DELTA PT 30 in the maker's 2 d boss, tightened to 0.30 N m: just inside the window.
export const DEFAULTS = Object.freeze({ material: 'pla-bambu-basic', size: '30', outside: 6, engagement: 6, torque: 0.3, axis: 'upright' });
export const PALETTES = Object.freeze({
  light: Object.freeze({ ink: '#173d3c', muted: '#526863', sage: '#6f8a80', mist: '#eef1e4', back: '#fffdf5', peach: '#ffe1cc',
    rust: '#bd3a12', steel: '#aab6b2', drive: '#d9e6dc' }),
  dark: Object.freeze({ ink: '#e6efe9', muted: '#a8bcb5', sage: '#86a499', mist: '#21393a', back: '#11201f', peach: '#4b2b1d',
    rust: '#ff9466', steel: '#64746f', drive: '#2c4a45' }),
});
const SIZES = { normal: { text: 15, small: 13 }, compact: { text: 24, small: 21 } };
const f = n => Number(n.toFixed(2));
const esc = t => String(t).replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
const halo = P => ` stroke="${P.back}" stroke-width="4" stroke-linejoin="round" paint-order="stroke"`;
export const nm = x => `${x >= 10 ? x.toFixed(1) : x.toFixed(2)} N·m`;
export const newtons = x => `${x >= 100 ? x.toFixed(0) : x >= 10 ? x.toFixed(1) : x.toFixed(2)} N`;
const mpa = x => `${(x / 1e6).toFixed(x >= 1e7 ? 1 : 2)} MPa`;
const mm = x => `${Number(x.toFixed(2))} mm`;
const snap = (v, c, min = c.min) => Number(Math.min(c.max, Math.max(min, Math.round(v / c.step) * c.step)).toFixed(3));

/** The screw of a size key. */
export const screwOf = size => SCREWS.sizes.find(x => x.key === size);
/** The thinnest boss the slider allows for a screw: its crest diameter plus 0.4 mm, to the slider's step. */
export const minOutside = size => Number((Math.ceil((screwOf(size).diameter * 1e3 + 0.4) * 10 - 1e-9) / 10).toFixed(1));

/** The state from attribute values (`get(name)` returns a string or null): unknown values fall back, numbers clamp to
 * the controls' steps, and the outside diameter to the screw. */
export function readState(get) {
  const s = { ...DEFAULTS };
  if (MATERIALS.some(m => m.key === get('material'))) s.material = get('material');
  if (SCREWS.sizes.some(x => x.key === get('size'))) s.size = get('size');
  if (Object.hasOwn(AXES, get('axis') ?? '')) s.axis = get('axis');
  for (const [k, c] of Object.entries(CONTROLS)) {
    const v = parseFloat(get(k));
    if (Number.isFinite(v)) s[k] = snap(v, c);
  }
  s.outside = snap(s.outside, CONTROLS.outside, minOutside(s.size));
  return s;
}

/** Everything the demo shows for a state, from the port: screwBoss with the filament's strengths (shear: half the
 * lowest tensile strength across the layers; hoop: in the layers for an upright boss, across them lying) and the
 * friction band, and which of the four checks fail. */
export function compute(s) {
  const material = MATERIALS.find(m => m.key === s.material), screw = screwOf(s.size);
  const shearStrength = SCREWS.shearFromTensile * material.strength.across;
  const hoopStrength = material.strength[s.axis === 'upright' ? 'along' : 'across'];
  const r = screwBoss(screw.diameter, screw.pitch, s.engagement / 1e3, s.outside / 1e3, s.torque, shearStrength, hoopStrength, ...SCREWS.friction);
  const failing = [!r.torqueOk && 'torque', !r.outsideOk && 'outside', !r.engagementOk && 'engagement', !r.hoopOk && 'hoop'].filter(Boolean);
  return { ...r, material, screw, shearStrength, hoopStrength, failing };
}

const REASONS = {
  torque: ['over-tightened', 'tightened past half the strip torque'],
  outside: ['wall too thin', 'outside diameter under 2 d'],
  engagement: ['short thread', 'engagement under 2 d'],
  hoop: ['hoop stress', 'hoop stress over the strength'],
};
/** The verdict's words: short (a phone's pill) or long. */
export function verdict(r, long = true) {
  if (!r.failing.length) return long ? 'inside the guide and the torque window' : 'in the window';
  const first = REASONS[r.failing[0]][long ? 1 : 0];
  return r.failing.length > 1 ? `${first} +${r.failing.length - 1}${long ? ' more' : ''}` : first;
}

export function summary(s, r) {
  const d = r.screw.diameter * 1e3;
  return `Screw-boss explorer: a DELTA PT ${s.size} screw (${mm(d)}) in a ${mm(s.outside)} boss of ${r.material.name}, ` +
    `${s.axis === 'upright' ? 'printed upright' : 'printed lying on its side'}, ${mm(s.engagement)} of thread, tightened to ${nm(s.torque)}: ` +
    `clamp ${r.preload.low.toFixed(0)} to ${newtons(r.preload.high)} (the low end if the drive torque, which makes no clamp, is the ` +
    `most the window allows); the thread strips at ${newtons(r.stripForce)}, at ${nm(r.stripTorque.low)} to ${nm(r.stripTorque.high)} ` +
    `over the drive torque, so tighten to at most ${nm(r.torqueCeiling)} and only if the ` +
    `measured drive torque is below ${nm(r.driveTorqueLimit)}; hoop stress ${mpa(r.hoopStress)}, ${Math.round(r.hoopRatio * 100)} % ` +
    `of the strength. ${r.passes ? 'A pass' : 'A fail'}: ${verdict(r)}. A starting point to test, not a rating.`;
}

const hex = c => [1, 3, 5].map(i => parseInt(c.slice(i, i + 2), 16));
const mix = (a, b, t) => '#' + hex(a).map((v, i) => Math.round(v + (hex(b)[i] - v) * t).toString(16).padStart(2, '0')).join('');
/** Stress over strength to a colour: mist at rest, peach from 70 %, rust at the limit and beyond. */
export const stressColour = (t, P = PALETTES.light) => t <= 0 ? P.mist : t < 0.7 ? mix(P.mist, P.peach, t / 0.7) : t < 1 ? mix(P.peach, P.rust, (t - 0.7) / 0.3) : P.rust;

// ----------------------------------------------------------------------------- the figure
const LEFT = { x0: 20, x1: 300, y0: 30, y1: 226 };          // the boss in section
const LADDER = { x: 372, y0: 40, y1: 238, w: 16 };          // the torque window, 0 at the bottom

/** Lay out labels at wanted heights in [top, bottom], at least `gap` apart, keeping their order. */
export function spread(wanted, gap, top, bottom) {
  const order = wanted.map((y, i) => [y, i]).sort((a, b) => a[0] - b[0]), out = new Array(wanted.length);
  let y = top - gap;
  for (const [w, i] of order) { y = Math.max(w, y + gap); out[i] = y; }
  for (let j = order.length - 1, next = bottom + gap; j >= 0; j--) {
    const i = order[j][1];
    out[i] = Math.min(out[i], next - gap);
    next = out[i];
  }
  return out;
}

/** The figure as SVG markup. `still` adds what a standalone file needs (namespace, size, title, background, a font);
 * `palette` is one of PALETTES; `compact` sizes the text for a phone; `id` keeps the gradient's id unique on a page. */
export function drawPrintedBoss(s, r, { still = false, label = summary(s, r), palette = PALETTES.light, compact = false, id = 'pb' } = {}) {
  const P = palette, z = SIZES[compact ? 'compact' : 'normal'], { width: W, height: H } = VIEW;
  // ---- the boss in section (mm, y down from the boss's top): head, lid, boss with its hole, the floor it stands on
  const d = r.screw.diameter * 1e3, pitch = r.screw.pitch * 1e3, D = s.outside, Le = s.engagement;
  const head = 0.6 * d, lid = Math.max(1.2, 0.6 * d), hole = BOSS.hole * d, depth = Le + 0.5 * d, base = 0.6 * d;
  const spanW = Math.max(D + 2 * d, 2 * d), spanH = head + lid + depth + base;
  const k = Math.min((LEFT.x1 - LEFT.x0) / spanW, (LEFT.y1 - LEFT.y0) / spanH, 40);
  const cx = (LEFT.x0 + LEFT.x1) / 2, top = LEFT.y0 + ((LEFT.y1 - LEFT.y0) - spanH * k) / 2 + (head + lid) * k;
  const X = u => cx + u * k, Y = v => top + v * k;
  // the hoop stress across the wall, Lame: sigma(r) = p a^2 / (b^2 - a^2) (1 + b^2 / r^2), bore a = d / 2
  const a = d / 2, b = D / 2, sigma = rr => r.radialPressure * a * a / (b * b - a * a) * (1 + b * b / (rr * rr));
  const stops = [];
  for (let i = 0; i <= 8; i++) {
    const rr = b - (b - a) * i / 8, c = stressColour(sigma(rr) / r.hoopStrength, P);
    stops.push([0.5 - rr / (2 * b), c]);
  }
  for (let i = 7; i >= 0; i--) stops.push([1 - stops[i][0], stops[i][1]]);
  const grad = `<linearGradient id="${id}-hoop" x1="0" x2="1" y1="0" y2="0">${stops.map(([o, c]) => `<stop offset="${f(o)}" stop-color="${c}"/>`).join('')}</linearGradient>`;
  const cb = Math.min((d + 0.2) / 2, b - 0.05), cbDepth = 0.35 * d;      // the maker's counterbore: d + 0.2 mm, 0.3 to 0.4 d deep
  const holePath = `M${f(X(-cb))} ${f(Y(0))}V${f(Y(cbDepth))}H${f(X(-hole / 2))}V${f(Y(depth))}H${f(X(hole / 2))}V${f(Y(cbDepth))}H${f(X(cb))}V${f(Y(0))}Z`;
  // layer lines: across the boss (horizontal) printed upright, along it (vertical) lying
  const gap = 6, lines = [];
  if (s.axis === 'upright') for (let y = Y(0) + gap; y < Y(depth + base); y += gap) lines.push(`M${f(X(-b))} ${f(y)}H${f(X(b))}`);
  else for (let x = X(-b) + gap; x < X(b); x += gap) lines.push(`M${f(x)} ${f(Y(0))}V${f(Y(depth + base))}`);
  // the screw: head, shank with its thread (crest d, root 0.68 d), and a pointed end at the engagement's depth
  const tipY = Le, root = 0.34 * d, crest = d / 2, teeth = [];
  for (let y = -lid; y < tipY - pitch * 0.5; y += pitch) teeth.push([y, y + pitch / 2]);
  const side = sgn => teeth.map(([y0, y1]) => `L${f(X(sgn * crest))} ${f(Y(y0 + (y1 - y0) / 2))}L${f(X(sgn * root))} ${f(Y(y1 + pitch / 4))}`).join('');
  const screw = `M${f(X(-root))} ${f(Y(-lid))}${side(-1)}L${f(X(-root))} ${f(Y(tipY - 0.3 * d))}L${f(X(0))} ${f(Y(tipY + 0.15 * d))}` +
    `L${f(X(root))} ${f(Y(tipY - 0.3 * d))}${teeth.slice().reverse().map(([y0, y1]) => `L${f(X(root))} ${f(Y(y1 + pitch / 4))}L${f(X(crest))} ${f(Y(y0 + (y1 - y0) / 2))}`).join('')}L${f(X(root))} ${f(Y(-lid))}Z`;
  const headPath = `M${f(X(-d))} ${f(Y(-lid))}V${f(Y(-lid - head * 0.55))}Q${f(X(-d))} ${f(Y(-lid - head))} ${f(X(-d * 0.6))} ${f(Y(-lid - head))}` +
    `H${f(X(d * 0.6))}Q${f(X(d))} ${f(Y(-lid - head))} ${f(X(d))} ${f(Y(-lid - head * 0.55))}V${f(Y(-lid))}Z`;
  const lidW = spanW / 2;
  const dimD = Y(depth + base) + 12;
  const leX = X(b) + 10;
  // ---- the torque window: a ladder from 0 N m up, with its marks labelled on the right
  const tMax = Math.max(r.stripTorque.high, s.torque) * 1.06, T = t => LADDER.y1 - (LADDER.y1 - LADDER.y0) * t / tMax;
  const marks = [
    { key: 'strip', y: (T(r.stripTorque.low) + T(r.stripTorque.high)) / 2, text: compact ? `strips ≥ ${nm(r.stripTorque.low)}` : `strips: drive + ${r.stripTorque.low.toFixed(2)} to ${nm(r.stripTorque.high)}`, colour: P.rust, weight: 600 },
    { key: 'ceiling', y: T(r.torqueCeiling), text: compact ? `max ${nm(r.torqueCeiling)}` : `tighten at most ${nm(r.torqueCeiling)}`, colour: P.ink, weight: 600 },
    { key: 'torque', y: T(s.torque), text: compact ? `you ${nm(s.torque)}` : `your torque ${nm(s.torque)}`, colour: r.torqueOk ? P.ink : P.rust, weight: 700 },
    { key: 'drive', y: T(r.driveTorqueLimit / 2), text: compact ? `drive < ${nm(r.driveTorqueLimit)}` : `drive must measure < ${nm(r.driveTorqueLimit)}`, colour: P.muted, weight: 500 },
  ];
  const ys = spread(marks.map(m => m.y), z.small + 4, LADDER.y0 + z.small * 0.35, LADDER.y1 + z.small * 0.35);
  const lx = LADDER.x + LADDER.w + 12;
  const ladder = `<rect x="${LADDER.x}" y="${LADDER.y0}" width="${LADDER.w}" height="${LADDER.y1 - LADDER.y0}" fill="${P.mist}" stroke="${P.sage}"/>` +
    `<rect data-part="drive" x="${LADDER.x}" y="${f(T(r.driveTorqueLimit))}" width="${LADDER.w}" height="${f(LADDER.y1 - T(r.driveTorqueLimit))}" fill="${P.drive}" stroke="${P.sage}"/>` +
    `<rect data-part="strip" x="${LADDER.x}" y="${f(T(r.stripTorque.high))}" width="${LADDER.w}" height="${f(T(r.stripTorque.low) - T(r.stripTorque.high))}" fill="${P.peach}" stroke="${P.rust}"/>` +
    `<path data-part="ceiling" d="M${LADDER.x - 8} ${f(T(r.torqueCeiling))}H${LADDER.x + LADDER.w + 8}" stroke="${P.ink}" stroke-width="2" stroke-dasharray="4 3"/>` +
    `<path data-part="torque" d="M${LADDER.x - 16} ${f(T(s.torque) - 7)}L${LADDER.x - 3} ${f(T(s.torque))}L${LADDER.x - 16} ${f(T(s.torque) + 7)}ZM${LADDER.x - 3} ${f(T(s.torque))}H${LADDER.x + LADDER.w + 3}" fill="${r.torqueOk ? P.ink : P.rust}" stroke="${r.torqueOk ? P.ink : P.rust}" stroke-width="3" stroke-linejoin="round"/>` +
    `<text x="${LADDER.x - 8}" y="${LADDER.y1 + 5}" text-anchor="end" font-size="${z.small}" fill="${P.muted}">0</text>` +
    `<text x="${LADDER.x + LADDER.w / 2}" y="${LADDER.y0 - 12}" text-anchor="middle" font-size="${z.small}" fill="${P.muted}">${compact ? 'torque' : 'torque, N·m'}</text>` +
    marks.map((m, i) => `<path d="M${LADDER.x + LADDER.w + 3} ${f(m.y)}L${lx - 4} ${f(ys[i] - z.small * 0.35)}" stroke="${P.sage}" stroke-width="1"/>` +
      `<text data-part="label-${m.key}" x="${lx}" y="${f(ys[i])}" font-size="${z.small}" font-weight="${m.weight}" fill="${m.colour}">${esc(m.text)}</text>`).join('');
  const passes = r.passes, pill = `${passes ? 'PASS' : 'FAIL'} · ${verdict(r, !compact)}`, pillW = compact ? 330 : 400;
  return `<svg${still ? ' xmlns="http://www.w3.org/2000/svg"' : ''} viewBox="0 0 ${W} ${H}"${still ? ` width="${W}" height="${H}"` : ''} role="img" aria-label="${esc(label)}">` +
    (still ? `<title>${esc(label)}</title><rect width="${W}" height="${H}" fill="${P.back}"/>` : '') +
    `<defs>${grad}</defs><g font-family="${still ? 'Inter,system-ui,-apple-system,Segoe UI,sans-serif' : 'inherit'}" font-size="${z.text}" fill="${P.ink}">` +
    `<rect data-part="floor" x="${f(X(-lidW))}" y="${f(Y(depth))}" width="${f(2 * lidW * k)}" height="${f(base * k)}" fill="${P.mist}" stroke="${P.sage}" stroke-width="1.4"/>` +
    `<rect data-part="boss" x="${f(X(-b))}" y="${f(Y(0))}" width="${f(D * k)}" height="${f((depth + base) * k)}" fill="url(#${id}-hoop)" stroke="${P.ink}" stroke-width="1.6"/>` +
    `<path data-part="layers" d="${lines.join('')}" stroke="${P.ink}" stroke-width="0.8" opacity=".28"/>` +
    `<path data-part="hole" d="${holePath}" fill="${P.back}" stroke="${P.ink}" stroke-width="1.2"/>` +
    `<rect data-part="lid" x="${f(X(-lidW))}" y="${f(Y(-lid))}" width="${f(2 * lidW * k)}" height="${f(lid * k)}" fill="${P.mist}" stroke="${P.sage}" stroke-width="1.4"/>` +
    `<rect x="${f(X(-(d + 0.4) / 2))}" y="${f(Y(-lid))}" width="${f((d + 0.4) * k)}" height="${f(lid * k)}" fill="${P.back}"/>` +
    `<path data-part="screw" d="${screw}" fill="${P.steel}" stroke="${P.ink}" stroke-width="1.2" stroke-linejoin="round"/>` +
    `<path data-part="head" d="${headPath}" fill="${P.steel}" stroke="${P.ink}" stroke-width="1.4"/>` +
    `<text data-part="label-screw" x="${f(X(d) + 8)}" y="${f(Y(-lid - head / 2) + z.small * 0.35)}" font-size="${z.small}"${halo(P)}>${compact ? `PT ${s.size}` : `DELTA PT ${s.size}, d ${mm(d)}`}</text>` +
    `<path data-part="dim-d" d="M${f(X(-b))} ${f(dimD)}H${f(X(b))}M${f(X(-b))} ${f(dimD - 5)}v10M${f(X(b))} ${f(dimD - 5)}v10" stroke="${P.sage}" stroke-width="1.5"/>` +
    `<path data-part="dim-le" d="M${f(leX)} ${f(Y(0))}V${f(Y(Le))}M${f(leX - 5)} ${f(Y(0))}h10M${f(leX - 5)} ${f(Y(Le))}h10" stroke="${P.sage}" stroke-width="1.5"/>` +
    `<text data-part="label-le" x="${f(leX + 6)}" y="${f(Y(Le / 2) + z.small * 0.35)}" font-size="${z.small}"${halo(P)}>${compact ? 'Le' : `Le ${esc(mm(Le))}`}</text>` +
    `<text data-part="label-hoop" x="${LEFT.x0}" y="${H - 19}" font-weight="700" fill="${r.hoopOk ? P.ink : P.rust}">${compact ? '' : 'wall '}${esc(mpa(r.hoopStress))} · ${Math.round(r.hoopRatio * 100)} %</text>` +
    `<text data-part="label-outside" x="${f(X(b) + 10)}" y="${f(dimD + z.small * 0.35)}" font-size="${z.small}"${halo(P)}>${esc(compact ? `D ${mm(D)}` : `D ${mm(D)} (${(D / d).toFixed(1)} d)`)}</text>` +
    ladder +
    `<rect data-part="verdict-box" x="${W - pillW - 12}" y="${H - 40}" width="${pillW}" height="30" rx="15" fill="${passes ? P.mist : P.peach}" stroke="${passes ? P.sage : P.rust}"/>` +
    `<text data-part="label-verdict" x="${W - 12 - pillW / 2}" y="${H - 19}" text-anchor="middle" font-size="${z.small}" font-weight="700" fill="${passes ? P.ink : P.rust}">${esc(pill)}</text>` +
    '</g></svg>';
}

// ----------------------------------------------------------------------------- the element (browsers only)
const Base = globalThis.HTMLElement ?? class {};
let instances = 0;

export class CadPrintedBoss extends Base {
  static get observedAttributes() { return ['material', 'size', 'axis', 'theme', ...Object.keys(CONTROLS)]; }

  connectedCallback() {
    this.dark ??= matchMedia('(prefers-color-scheme: dark)');
    this.narrow ??= matchMedia('(max-width: 699.98px)');                    // printed-boss.css's phone layout
    if (!this.built) {
      this.built = true;
      this.uid = `pb${++instances}`;
      this.state = readState(n => this.getAttribute(n));
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
    // (aria-valuetext), and only the debounced .pb-status line announces results.
    const slider = (k, c) => `<div class="pb-field"><label for="${id(k)}">${esc(c.label)} <span class="pb-value" data-out="${k}" aria-hidden="true"></span></label>` +
      `<input id="${id(k)}" type="range" name="${k}" min="${c.min}" max="${c.max}" step="${c.step}"></div>`;
    const select = (name, text, options) => `<div class="pb-field"><label for="${id(name)}">${text}</label><select id="${id(name)}" name="${name}">${options.map(([v, t]) =>
      `<option value="${esc(v)}">${esc(t)}</option>`).join('')}</select></div>`;
    this.replaceChildren();
    this.insertAdjacentHTML('beforeend', `<div class="pb-figure"></div><div class="pb-panel">
<div class="pb-readout">
<p class="pb-tile"><span class="pb-k">Clamp force</span><b data-out="clamp"></b><span data-out="clamp-note"></span></p>
<p class="pb-tile"><span class="pb-k">Thread strips at</span><b data-out="strip"></b><span data-out="strip-note"></span></p>
<p class="pb-tile" data-out="verdict-tile"><span class="pb-k">Verdict</span><b data-out="verdict"></b><span data-out="verdict-note"></span></p></div>
<div class="pb-controls"><div class="pb-col">${select('size', 'Screw (DELTA PT)', SCREWS.sizes.map(x => [x.key, `PT ${x.key}: ${Number((x.diameter * 1e3).toFixed(1))} mm, pitch ${Number((x.pitch * 1e3).toFixed(2))} mm`]))}
${slider('outside', CONTROLS.outside)}${slider('engagement', CONTROLS.engagement)}</div>
<div class="pb-col">${slider('torque', CONTROLS.torque)}${select('material', 'Filament', MATERIALS.map(m => [m.key, m.name]))}
<fieldset><legend>Boss printed</legend>${Object.entries(AXES).map(([v, t]) =>
  `<label><input type="radio" name="${id('axis')}" value="${v}" data-name="axis"> ${esc(t)}</label>`).join('')}</fieldset></div></div>
<p class="pb-note">Datasheet strengths, Shigley's thread statics, Covestro's torque window. No printed-boss test data: a starting point to test, not a rating.</p>
<p class="pb-status" role="status" aria-live="polite"></p></div>`);
    this.figure = this.querySelector('.pb-figure');
    this.out = Object.fromEntries([...this.querySelectorAll('[data-out]')].map(n => [n.dataset.out, n]));
    this.status = this.querySelector('.pb-status');
    this.addEventListener('input', e => this.onInput(e));
    this.addEventListener('change', e => this.onInput(e));
    this.dataset.theme = this.theme();
    this.syncControls();
  }

  syncControls() {
    this.querySelector('input[name="outside"]').min = minOutside(this.state.size);
    for (const k of Object.keys(CONTROLS)) this.querySelector(`input[name="${k}"]`).value = this.state[k];
    this.querySelector('select[name="size"]').value = this.state.size;
    this.querySelector('select[name="material"]').value = this.state.material;
    for (const r of this.querySelectorAll('input[type="radio"]')) r.checked = this.state.axis === r.value;
  }

  onInput(e) {
    const t = e.target;
    if (!t.matches?.('input, select')) return;
    const name = t.dataset.name || t.name;
    if (name in CONTROLS) this.state[name] = Number(t.value);
    else if (name === 'axis' && t.checked) this.state.axis = t.value;
    else if (name === 'material') this.state.material = t.value;
    else if (name === 'size') {
      this.state.size = t.value;
      this.state.outside = snap(this.state.outside, CONTROLS.outside, minOutside(t.value));
      this.syncControls();
    } else return;
    this.update({ announce: true });
  }

  /** Draw the figure afresh (for a new state, theme or layout). */
  paint() {
    this.figure.innerHTML = drawPrintedBoss(this.state, this.result, { palette: PALETTES[this.dataset.theme], compact: this.narrow.matches,
      label: this.said, id: this.uid });
  }

  // Only what the user does is announced, once the slider stops moving: the first draw and attribute changes are not
  // (the figure's aria-label carries the same summary). An announcement still pending speaks the latest result.
  update({ announce = false } = {}) {
    const s = this.state, r = this.result = compute(s);
    for (const [k, c] of Object.entries(CONTROLS)) {
      const value = Number(s[k].toFixed(2));
      this.out[k].textContent = k === 'torque' ? nm(value) : `${value} ${c.unit}`;
      this.querySelector(`input[name="${k}"]`).setAttribute('aria-valuetext', k === 'torque' ? `${value} newton metres` : `${value} millimetres`);
    }
    this.out.clamp.textContent = `${r.preload.low.toFixed(0)}–${newtons(r.preload.high)}`;
    this.out['clamp-note'].textContent = 'less the drive torque';
    this.out.strip.textContent = newtons(r.stripForce);
    this.out['strip-note'].textContent = `drive + ${nm(r.stripTorque.low)}–${nm(r.stripTorque.high)}`;
    this.out.verdict.textContent = r.passes ? 'PASS' : 'FAIL';
    this.out['verdict-note'].textContent = r.passes ? `tighten ≤ ${nm(r.torqueCeiling)}` : verdict(r, false);
    this.out['verdict-tile'].dataset.verdict = r.passes ? 'pass' : 'fail';
    this.said = summary(s, r);
    this.paint();
    if (announce) {
      clearTimeout(this.announce);
      this.announce = setTimeout(() => { this.status.textContent = this.said; }, 700);
    }
    this.dispatchEvent(new CustomEvent('cad-printed-boss-change', { bubbles: true, detail: { state: { ...s }, result: {
      preload: { ...r.preload }, stripForce: r.stripForce, stripTorque: { ...r.stripTorque }, torqueCeiling: r.torqueCeiling,
      driveTorqueLimit: r.driveTorqueLimit, hoopStress: r.hoopStress, hoopRatio: r.hoopRatio, passes: r.passes,
      failing: [...r.failing], material: r.material.key, size: r.screw.key } } }));
  }
}

if (typeof customElements !== 'undefined' && !customElements.get('cad-printed-boss')) customElements.define('cad-printed-boss', CadPrintedBoss);
