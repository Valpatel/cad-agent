/** <cad-torsion-snap>: a torsion-bar snap. A lever twists one rectangular bar, or a rocker twists two; sliders set the
 * bar, the twist and the lever, and the figure shows the bar twisted along its length and the lever's end view, with
 * the peak shear strain against the filament's allowable, the torque and the force at the lever.
 *
 *   <link rel="stylesheet" href="/kit/torsion-snap.css">          (in <head>: it keeps the space before the script runs)
 *   <script type="module" src="/kit/torsion-snap.js"></script>
 *   <cad-torsion-snap material="pla-bambu-basic" bars="2" length="15" width="4" thickness="1.2" twist="8" lever="10">
 *     <img src="still.svg" alt="…" width="640" height="280"></cad-torsion-snap>
 *
 * Attributes (all optional; mm for lengths, degrees for the twist): `material` (a key of formulas-data.js), `bars`
 * (1: the lever at the free end of one bar; 2: a rocker between two, the Covestro guide's Fig. 21), `repeated` (present:
 * opened often, 60 % of the allowable), `length` (of each bar), `width`, `thickness`, `twist` (at the lever), `lever`
 * (from the bar's axis to where it is pressed), `theme` (`light` or `dark`; by default the page's color-scheme, else the
 * reader's preference). Out-of-range values are clamped. The element's children are the still shown before the script
 * loads; the live figure replaces them at the same size.
 *
 * Every number comes from formulas.js, the tested port of cadagent.formulas.torsion_snap_bar: Saint-Venant torsion of
 * a rectangle (Roark, Table 10.1) and the Covestro guide's allowable shear strain (1 + nu) eps (Section C). The
 * allowable is the filament's across the layers whichever way the bar lies: lying flat, its short sides still shear
 * the layer interfaces at 74 to 100 % of the peak. The force uses G from the highest datasheet modulus, so it is an
 * upper bound at small twist; past it (the trapeze effect adds more than a tenth to the torque) the note says so.
 * `drawTorsionSnap()` is pure, so tools/torsion-snap-still.mjs draws the still from the same code. Nothing
 * moves on its own. No dependencies, no shadow DOM, no inline script. Each change fires `cad-torsion-snap-change` with
 * `{ state, result }`.
 */
import { torsionSnapBar } from './formulas.js';
import { MATERIALS } from './formulas-data.js';

export const VIEW = Object.freeze({ width: 640, height: 280 });
export const CONTROLS = Object.freeze({
  length: { label: 'Length of each bar', min: 4, max: 30, step: 0.5, unit: 'mm' },
  width: { label: 'Width', min: 1, max: 12, step: 0.1, unit: 'mm' },
  thickness: { label: 'Thickness', min: 0.6, max: 4, step: 0.1, unit: 'mm' },
  twist: { label: 'Twist at the lever', min: 0, max: 30, step: 0.5, unit: '°' },
  lever: { label: 'Lever arm', min: 3, max: 30, step: 0.5, unit: 'mm' },
});
export const BARS = Object.freeze({ 1: 'One bar', 2: 'Two bars (a rocker)' });
// A PLA rocker on two bars, pressed 8 degrees: 86 % of the allowable, a pass.
export const DEFAULTS = Object.freeze({ material: 'pla-bambu-basic', bars: 2, repeated: false, length: 15, width: 4,
  thickness: 1.2, twist: 8, lever: 10 });
export const PALETTES = Object.freeze({
  light: Object.freeze({ ink: '#173d3c', muted: '#526863', sage: '#6f8a80', mist: '#eef1e4', back: '#fffdf5', peach: '#ffe1cc',
    rust: '#bd3a12', line: '#dfe7dc' }),
  dark: Object.freeze({ ink: '#e6efe9', muted: '#a8bcb5', sage: '#86a499', mist: '#21393a', back: '#11201f', peach: '#4b2b1d',
    rust: '#ff9466', line: '#2b4542' }),
});
const DEG = Math.PI / 180;
const SIZES = { normal: { text: 15, small: 13 }, compact: { text: 24, small: 21 } };
const f = n => Number(n.toFixed(2));
const esc = t => String(t).replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
const halo = P => ` stroke="${P.back}" stroke-width="4" stroke-linejoin="round" paint-order="stroke"`;
export const pct = x => `${(x * 100).toFixed(2)} %`;
const num = (x, unit) => `${x >= 100 ? x.toFixed(0) : x >= 10 ? x.toFixed(1) : x.toFixed(2)} ${unit}`;
const mm = x => `${Number(x.toFixed(2))} mm`;
const deg = x => `${Number(x.toFixed(1))}°`;
const snap = (v, c) => Number(Math.min(c.max, Math.max(c.min, Math.round(v / c.step) * c.step)).toFixed(3));

/** The state from attribute values (`get(name)` returns a string or null): unknown values fall back, numbers clamp to
 * the controls' steps. */
export function readState(get) {
  const s = { ...DEFAULTS };
  if (MATERIALS.some(m => m.key === get('material'))) s.material = get('material');
  if (get('bars') === '1' || get('bars') === '2') s.bars = Number(get('bars'));
  const repeated = get('repeated');
  if (repeated !== null && repeated !== undefined) s.repeated = repeated !== 'false';
  for (const [k, c] of Object.entries(CONTROLS)) {
    const v = parseFloat(get(k));
    if (Number.isFinite(v)) s[k] = snap(v, c);
  }
  return s;
}

/** Everything the demo shows for a state (lengths in mm), from the port: the bar's strain, torque and force, with the
 * material, its modulus (the highest edition's, in the layer plane) and its allowable across the layers. */
export function compute(s) {
  const material = MATERIALS.find(m => m.key === s.material);
  const allowable = material.allowable.across[s.repeated ? 'repeated' : 'single'];
  const modulus = material.modulus.along;
  return { ...torsionSnapBar(s.length / 1e3, s.width / 1e3, s.thickness / 1e3, s.twist * DEG, modulus, allowable,
    s.lever / 1e3, s.bars), material, modulus, allowable };
}

export function summary(s, r) {
  return `Torsion-snap explorer: ${s.bars === 2 ? `two bars of ${r.material.name}, each` : `one bar of ${r.material.name},`} ${mm(s.length)} long, ` +
    `${Number(s.width.toFixed(2))} × ${mm(s.thickness)}, twisted ${deg(s.twist)} by a ${mm(s.lever)} lever: peak shear strain ` +
    `${pct(r.shearStrain)}, ${Math.round(r.ratio * 100)} % of the ${pct(r.allowableShearStrain)} allowed across the layers, ` +
    `${r.passes ? 'a pass' : 'a fail'}; ${num(r.force, 'N')} at the lever. The allowable is reached at ${deg(r.permissibleTwist / DEG)}.` +
    (r.smallTwist ? '' : ` ${largeTwist(r)}`);
}

/** The warning for a twist past the closed form's reach (the trapeze effect adds more than a tenth to the torque). */
export const largeTwist = r => `Twisted far: the edges stretch (the trapeze effect), adding ${Math.round(r.trapezeRatio * 100)} % to the ` +
  `torque and ${pct(r.edgeAxialStrain)} strain along them. The check leaves that out.`;
const NOTE = 'Saint-Venant torsion with the Covestro allowable (1 + ν) ε across the layers. A closed form, not proof: print a test bar and measure.';

const hex = c => [1, 3, 5].map(i => parseInt(c.slice(i, i + 2), 16));
const mix = (a, b, t) => '#' + hex(a).map((v, i) => Math.round(v + (hex(b)[i] - v) * t).toString(16).padStart(2, '0')).join('');
/** Strain over the allowable to a colour: mist at rest, peach from 70 %, rust at the limit and beyond. */
export const strainColour = (t, P = PALETTES.light) => t <= 0 ? P.mist : t < 0.7 ? mix(P.mist, P.peach, t / 0.7) : t < 1 ? mix(P.peach, P.rust, (t - 0.7) / 0.3) : P.rust;

// ----------------------------------------------------------------------------- the figure
// The bar runs along x (mm); its section is w along y by t along z, turned through phi(x) about the axis: 0 at a fixed
// end, the twist at the lever. The lever lies on the bar's top face and points to -y, at the viewer; pressed, its end
// goes down. An oblique projection draws y at 0.7 of its size, 40 degrees up: (x, y, z) lands at (x + OX y, z + OY y),
// so the viewer looks along (-OX, 1, -OY), from the front, the right and above.
const OX = 0.7 * Math.cos(40 * DEG), OY = 0.7 * Math.sin(40 * DEG);
const turn = (y, z, phi) => [y * Math.cos(phi) - z * Math.sin(phi), y * Math.sin(phi) + z * Math.cos(phi)];
const depth = (x, y, z) => -OX * x + y - OY * z;              // larger is farther from the viewer
const BOX = { x0: 34, x1: 424, y0: 44, y1: 222 };           // the bar view
const END = { x0: 448, x1: 628, y0: 44, y1: 222 };          // the end view at the lever

/** The twist at x along the bar(s): 0 at each fixed end, the full twist at the lever. */
const twistAt = (s, x, phi) => s.bars === 2 ? phi * (1 - Math.abs(x - s.length) / s.length) : phi * x / s.length;

/** The bar view's projection: a function from (x, y, z) in mm to the SVG, fitted to hold the bar, its walls and the
 * lever both at rest and pressed. */
function barView(s, wall) {
  const total = s.bars * s.length, phi = s.twist * DEG, R = Math.hypot(s.width, s.thickness) / 2;
  const raw = (x, y, z) => [x + OX * y, -(z + OY * y)];
  const pts = [];
  for (const x of s.bars === 2 ? [0, total] : [0]) for (const y of [-wall, wall]) for (const z of [-wall, wall]) pts.push(raw(x, y, z));
  for (const x of [0, s.length, total]) for (const y of [-R, R]) for (const z of [-R, R]) pts.push(raw(x, y, z));
  for (const p of [0, phi]) pts.push(raw(s.length, ...turn(-s.lever, s.thickness / 2, p)));
  const xs = pts.map(p => p[0]), ys = pts.map(p => p[1]);
  const bw = Math.max(...xs) - Math.min(...xs), bh = Math.max(...ys) - Math.min(...ys);
  const k = Math.min((BOX.x1 - BOX.x0) / bw, (BOX.y1 - BOX.y0) / bh, 16);
  const dx = BOX.x0 + ((BOX.x1 - BOX.x0) - bw * k) / 2 - Math.min(...xs) * k;
  const dy = BOX.y0 + ((BOX.y1 - BOX.y0) - bh * k) / 2 - Math.min(...ys) * k;
  return { k, total, phi, P: (x, y, z) => { const [u, v] = raw(x, y, z); return [dx + u * k, dy + v * k]; } };
}

const pt = p => p.map(f).join(',');
const seg = (a, b) => `M${f(a[0])} ${f(a[1])}L${f(b[0])} ${f(b[1])}`;
const arrowHead = (tip, ux, uy, size = 7) => `M${f(tip[0] - ux * size * 1.3 + uy * size * 0.75)} ${f(tip[1] - uy * size * 1.3 - ux * size * 0.75)}` +
  `L${f(tip[0])} ${f(tip[1])}L${f(tip[0] - ux * size * 1.3 - uy * size * 0.75)} ${f(tip[1] - uy * size * 1.3 + ux * size * 0.75)}`;

/** The figure as SVG markup. `still` adds what a standalone file needs (namespace, size, title, background, a font);
 * `palette` is one of PALETTES; `compact` sizes the text for a phone. */
export function drawTorsionSnap(s, r, { still = false, label = summary(s, r), palette = PALETTES.light, compact = false } = {}) {
  const P = palette, z = SIZES[compact ? 'compact' : 'normal'], { width: W, height: H } = VIEW;
  const w2 = s.width / 2, t2 = s.thickness / 2, big = Math.max(s.width, s.thickness);
  const wall = big / 2 + Math.max(1, 0.35 * big);
  const v = barView(s, wall);
  const corners = [[-w2, -t2], [w2, -t2], [w2, t2], [-w2, t2]];          // round the section: bottom, back, top, front faces
  const fill = strainColour(r.ratio, P), N = 32;
  const at = (x, [cy, cz]) => v.P(x, ...turn(cy, cz, twistAt(s, x, v.phi)));
  // Each face is cut into strips along the bar. A strip faces the viewer when it winds the same way on screen as the
  // top face untwisted; the strips are drawn far to near with their long edges, so the near ones hide the far ones.
  // Lines across the faces every few strips, and the wide faces' centre lines, show the twist.
  const wind = q => q.reduce((a, [x1, y1], i) => { const [x2, y2] = q[(i + 1) % q.length]; return a + x1 * y2 - x2 * y1; }, 0);
  const facing = Math.sign(wind([v.P(0, w2, t2), v.P(0, -w2, t2), v.P(1, -w2, t2), v.P(1, w2, t2)]));
  const strips = [];
  for (let n = 0; n < N; n++) {
    const xa = v.total * n / N, xb = v.total * (n + 1) / N, xm = (xa + xb) / 2;
    for (let i = 0; i < 4; i++) {
      const a = corners[i], b = corners[(i + 1) % 4], q = [at(xa, a), at(xa, b), at(xb, b), at(xb, a)];
      if (Math.sign(wind(q)) !== facing) continue;
      const mid = [(a[0] + b[0]) / 2, (a[1] + b[1]) / 2], [ym, zm] = turn(...mid, twistAt(s, xm, v.phi));
      const nz = turn(...[[0, -1], [1, 0], [0, 1], [-1, 0]][i], twistAt(s, xm, v.phi))[1];
      const shade = nz > 0.5 ? fill : mix(fill, P.ink, nz > -0.5 ? 0.16 : 0.3);
      let g = `<polygon points="${q.map(pt).join(' ')}" fill="${shade}" stroke="${shade}" stroke-width="0.8" stroke-linejoin="round"/>` +
        `<path d="${seg(q[0], q[3])}${seg(q[1], q[2])}${n % 4 === 0 ? seg(q[0], q[1]) : ''}${n === N - 1 ? seg(q[3], q[2]) : ''}" stroke="${P.ink}" stroke-width="${n % 4 === 0 ? '1.4' : '1.4'}" stroke-linecap="round" fill="none"/>`;
      if (i % 2 === 0) g += `<path d="${seg(at(xa, mid), at(xb, mid))}" stroke="${P.ink}" stroke-width="1" opacity=".5"/>`;
      strips.push([depth(xm, ym, zm), g]);
    }
  }
  const bar = strips.sort((p, q) => q[0] - p[0]).map(x => x[1]).join('');
  // the fixed ends: ribbed plates, the far one behind the bar and the near one (a rocker's) in front
  const plate = x => {
    const c = [[-wall, -wall], [wall, -wall], [wall, wall], [-wall, wall]].map(([y, zz]) => v.P(x, y, zz));
    const ribs = [-0.6, -0.2, 0.2, 0.6].map(u => seg(v.P(x, u * wall, -wall), v.P(x, u * wall, wall))).join('');
    return `<polygon points="${c.map(pt).join(' ')}" fill="${P.mist}" stroke="${P.sage}" stroke-width="1.5" stroke-linejoin="round"/>` +
      `<path d="${ribs}" stroke="${P.sage}" stroke-width="1.1"/>`;
  };
  // the lever on the top face at x = L, at rest (dashed) and pressed, with the press at its end
  const leverAt = phi => [v.P(s.length, ...turn(0, t2, phi)), v.P(s.length, ...turn(-s.lever, t2, phi))];
  const [rest0, rest1] = leverAt(0), [lev0, lev1] = leverAt(v.phi);
  const press = (() => {                                      // down the tip's path: d/dphi of turn(-lever, t/2, phi)
    const [dy, dz] = [s.lever * Math.sin(v.phi) - t2 * Math.cos(v.phi), -s.lever * Math.cos(v.phi) - t2 * Math.sin(v.phi)];
    const ux = OX * dy, uy = -(dz + OY * dy), n = Math.hypot(ux, uy);
    return [ux / n, uy / n];
  })();
  const pressLen = compact ? 34 : 28, pTip = [lev1[0] - press[0] * 3, lev1[1] - press[1] * 3];
  const pTail = [pTip[0] - press[0] * pressLen, pTip[1] - press[1] * pressLen];
  const [d0x] = v.P(0, 0, 0), [d1x] = v.P(s.length, 0, 0), dimY = BOX.y0 - 12;
  // the end view at the lever, looking along the bar: the section turned through the twist over its outline at rest
  const R = Math.hypot(s.width, s.thickness) / 2, ke = Math.min((END.x1 - END.x0 - 16) / (s.lever + R), (END.y1 - END.y0 - 40) / (2 * R + 2), 14);
  const cx = END.x0 + 8 + R * ke, cy = (END.y0 + END.y1) / 2 + 4;
  const E = (y, zz) => [cx - y * ke, cy - zz * ke];                       // y to the left, so the lever points right
  const sect = phi => corners.map(c => pt(E(...turn(...c, phi)))).join(' ');
  const tip = E(...turn(-s.lever, 0, v.phi)), ux = Math.cos(v.phi), uy = Math.sin(v.phi);
  const nx = -uy, ny = ux;                                                // square to the lever, pressing down
  const len = compact ? 46 : 36, a1 = [tip[0] - nx * 4, tip[1] - ny * 4], a0 = [a1[0] - nx * len, a1[1] - ny * len];
  const below = tip[1] + z.text + 10 < H - 44;                            // the force's label under the lever's end, if it fits
  const arcR = Math.min(s.lever * ke * 0.6, 64);
  const arc = v.phi > 1e-6 ? `<path data-part="arc" d="M${f(cx + arcR)} ${f(cy)}A${f(arcR)} ${f(arcR)} 0 0 1 ${f(cx + arcR * ux)} ${f(cy + arcR * uy)}" fill="none" stroke="${P.rust}" stroke-width="1.6"/>` : '';
  const passes = r.passes, pct100 = Math.round(r.ratio * 100);
  const pill = compact ? `${passes ? 'PASS' : 'FAIL'} · ${pct100} %` : `${passes ? 'PASS' : 'FAIL'} · ${pct100} % of the allowed shear strain`;
  const pillW = compact ? 230 : 330;
  return `<svg${still ? ' xmlns="http://www.w3.org/2000/svg"' : ''} viewBox="0 0 ${W} ${H}"${still ? ` width="${W}" height="${H}"` : ''} role="img" aria-label="${esc(label)}">` +
    (still ? `<title>${esc(label)}</title><rect width="${W}" height="${H}" fill="${P.back}"/>` : '') +
    `<g font-family="${still ? 'Inter,system-ui,-apple-system,Segoe UI,sans-serif' : 'inherit'}" font-size="${z.text}" fill="${P.ink}">` +
    plate(0) + `<g data-part="bar">${bar}</g>` + (s.bars === 2 ? plate(v.total) : '') +
    `<path data-part="rest-lever" d="${seg(rest0, rest1)}" stroke="${P.sage}" stroke-width="2" stroke-dasharray="5 4"/>` +
    `<path data-part="lever" d="${seg(lev0, lev1)}" stroke="${P.ink}" stroke-width="5" stroke-linecap="round"/>` +
    `<path data-part="press" d="${seg(pTail, pTip)}${arrowHead(pTip, ...press, 6)}" stroke="${P.rust}" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round" fill="none"/>` +
    `<path data-part="dim-l" d="M${f(d0x)} ${dimY}H${f(d1x)}M${f(d0x)} ${dimY - 6}v12M${f(d1x)} ${dimY - 6}v12" stroke="${P.sage}" stroke-width="1.5" fill="none"/>` +
    `<text data-part="label-length" x="${f((d0x + d1x) / 2)}" y="${dimY - 8}" text-anchor="middle" font-size="${z.small}">L ${esc(mm(s.length))}</text>` +
    `<text data-part="label-strain" x="${BOX.x0}" y="${H - 19}" font-weight="700">${compact ? '' : 'peak '}γ ${esc(pct(r.shearStrain))}</text>` +
    `<text x="${END.x1}" y="${BOX.y0 - 20}" text-anchor="end" font-size="${z.small}" fill="${P.muted}">${compact ? 'end view' : 'end view at the lever'}</text>` +
    `<polygon data-part="end-rest" points="${sect(0)}" fill="none" stroke="${P.sage}" stroke-width="1.5" stroke-dasharray="4 3"/>` +
    `<path d="M${f(cx)} ${f(cy)}H${f(cx + s.lever * ke)}" stroke="${P.sage}" stroke-width="2" stroke-dasharray="5 4"/>` +
    `<polygon data-part="end" points="${sect(v.phi)}" fill="${fill}" stroke="${P.ink}" stroke-width="1.6"/>` +
    `<path data-part="end-lever" d="${seg([cx, cy], tip)}" stroke="${P.ink}" stroke-width="5" stroke-linecap="round"/>` +
    `<circle cx="${f(cx)}" cy="${f(cy)}" r="3" fill="${P.back}" stroke="${P.ink}" stroke-width="1.5"/>` + arc +
    `<text data-part="label-twist" x="${f(cx + arcR * 0.45)}" y="${f(cy - 9)}" font-size="${z.small}" fill="${P.rust}"${halo(P)}>θ ${esc(deg(s.twist))}</text>` +
    `<path data-part="arrow" d="${seg(a0, a1)}${arrowHead(a1, nx, ny)}" stroke="${P.rust}" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round" fill="none"/>` +
    `<text data-part="label-force" x="${f(Math.min(below ? tip[0] + 6 : a0[0], W - 8))}" y="${f(below ? tip[1] + z.text + 6 : a0[1] - 8)}" text-anchor="end" font-weight="700" fill="${P.rust}"${halo(P)}>F ${esc(num(r.force, 'N'))}</text>` +
    `<rect data-part="verdict-box" x="${W - pillW - 12}" y="${H - 40}" width="${pillW}" height="30" rx="15" fill="${passes ? P.mist : P.peach}" stroke="${passes ? P.sage : P.rust}"/>` +
    `<text data-part="label-verdict" x="${W - 12 - pillW / 2}" y="${H - 19}" text-anchor="middle" font-size="${z.small}" font-weight="700" fill="${passes ? P.ink : P.rust}">${esc(pill)}</text>` +
    '</g></svg>';
}

// ----------------------------------------------------------------------------- the element (browsers only)
const Base = globalThis.HTMLElement ?? class {};
let instances = 0;

export class CadTorsionSnap extends Base {
  static get observedAttributes() { return ['material', 'bars', 'repeated', 'theme', ...Object.keys(CONTROLS)]; }

  connectedCallback() {
    this.dark ??= matchMedia('(prefers-color-scheme: dark)');
    this.narrow ??= matchMedia('(max-width: 699.98px)');                    // torsion-snap.css's phone layout
    if (!this.built) {
      this.built = true;
      this.uid = `ts${++instances}`;
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
    // (aria-valuetext), and only the debounced .ts-status line announces results.
    const slider = (k, c) => `<div class="ts-field"><label for="${id(k)}">${esc(c.label)} <span class="ts-value" data-out="${k}" aria-hidden="true"></span></label>` +
      `<input id="${id(k)}" type="range" name="${k}" min="${c.min}" max="${c.max}" step="${c.step}"></div>`;
    this.replaceChildren();
    this.insertAdjacentHTML('beforeend', `<div class="ts-figure"></div><div class="ts-panel">
<div class="ts-readout">
<p class="ts-tile"><span class="ts-k">Shear strain</span><b data-out="strain"></b><span data-out="allowed"></span></p>
<p class="ts-tile" data-out="verdict-tile"><span class="ts-k">Verdict</span><b data-out="verdict"></b><span data-out="ratio"></span></p>
<p class="ts-tile"><span class="ts-k">Force at the lever</span><b data-out="force"></b><span data-out="torque"></span></p></div>
<div class="ts-controls"><div class="ts-col">${['length', 'width', 'thickness'].map(k => slider(k, CONTROLS[k])).join('')}
<fieldset><legend>Bars</legend>${Object.entries(BARS).map(([v, t]) =>
  `<label><input type="radio" name="${id('bars')}" value="${v}" data-name="bars"> ${esc(t)}</label>`).join('')}</fieldset></div>
<div class="ts-col">${['twist', 'lever'].map(k => slider(k, CONTROLS[k])).join('')}
<div class="ts-field"><label for="${id('material')}">Filament</label><select id="${id('material')}" name="material">${MATERIALS.map(m =>
  `<option value="${esc(m.key)}">${esc(m.name)}</option>`).join('')}</select></div>
<label class="ts-check"><input type="checkbox" name="repeated"> Opened often (60 % of the allowable)</label></div></div>
<p class="ts-note" data-out="note">${esc(NOTE)}</p>
<p class="ts-status" role="status" aria-live="polite"></p></div>`);
    this.figure = this.querySelector('.ts-figure');
    this.out = Object.fromEntries([...this.querySelectorAll('[data-out]')].map(n => [n.dataset.out, n]));
    this.status = this.querySelector('.ts-status');
    this.addEventListener('input', e => this.onInput(e));
    this.addEventListener('change', e => this.onInput(e));
    this.dataset.theme = this.theme();
    this.syncControls();
  }

  syncControls() {
    for (const k of Object.keys(CONTROLS)) this.querySelector(`input[name="${k}"]`).value = this.state[k];
    this.querySelector('select[name="material"]').value = this.state.material;
    for (const r of this.querySelectorAll('input[type="radio"]')) r.checked = String(this.state.bars) === r.value;
    this.querySelector('input[name="repeated"]').checked = this.state.repeated;
  }

  onInput(e) {
    const t = e.target;
    if (!t.matches?.('input, select')) return;
    const name = t.dataset.name || t.name;
    if (name in CONTROLS) this.state[name] = Number(t.value);
    else if (name === 'bars' && t.checked) this.state.bars = Number(t.value);
    else if (name === 'repeated') this.state.repeated = t.checked;
    else if (name === 'material') this.state.material = t.value;
    else return;
    this.update({ announce: true });
  }

  /** Draw the figure afresh (for a new state, theme or layout). */
  paint() {
    this.figure.innerHTML = drawTorsionSnap(this.state, this.result, { palette: PALETTES[this.dataset.theme], compact: this.narrow.matches, label: this.said });
  }

  // Only what the user does is announced, once the slider stops moving: the first draw and attribute changes are not
  // (the figure's aria-label carries the same summary). An announcement still pending speaks the latest result.
  update({ announce = false } = {}) {
    const s = this.state, r = this.result = compute(s);
    for (const [k, c] of Object.entries(CONTROLS)) {
      const value = Number(s[k].toFixed(2));
      this.out[k].textContent = k === 'twist' ? deg(value) : `${value} ${c.unit}`;
      this.querySelector(`input[name="${k}"]`).setAttribute('aria-valuetext', k === 'twist' ? `${value} degrees` : `${value} millimetres`);
    }
    this.out.strain.textContent = pct(r.shearStrain);
    this.out.allowed.textContent = `of ${pct(r.allowableShearStrain)} allowed`;
    this.out.verdict.textContent = r.passes ? 'PASS' : 'FAIL';
    this.out.ratio.textContent = `${Math.round(r.ratio * 100)} % · limit at ${deg(r.permissibleTwist / DEG)}`;
    this.out['verdict-tile'].dataset.verdict = r.passes ? 'pass' : 'fail';
    this.out.force.textContent = num(r.force, 'N');
    this.out.torque.textContent = `torque ${num(r.torque * 1e3, 'N·mm')}`;
    this.out.note.textContent = r.smallTwist ? NOTE : largeTwist(r);
    if (r.smallTwist) delete this.out.note.dataset.warn; else this.out.note.dataset.warn = '';
    this.said = summary(s, r);
    this.paint();
    if (announce) {
      clearTimeout(this.announce);
      this.announce = setTimeout(() => { this.status.textContent = this.said; }, 700);
    }
    this.dispatchEvent(new CustomEvent('cad-torsion-snap-change', { bubbles: true, detail: { state: { ...s }, result: {
      shearStrain: r.shearStrain, allowableShearStrain: r.allowableShearStrain, ratio: r.ratio, passes: r.passes, torque: r.torque,
      force: r.force, stiffness: r.stiffness, permissibleTwist: r.permissibleTwist, trapezeRatio: r.trapezeRatio,
      smallTwist: r.smallTwist, material: r.material.key } } }));
  }
}

if (typeof customElements !== 'undefined' && !customElements.get('cad-torsion-snap')) customElements.define('cad-torsion-snap', CadTorsionSnap);
