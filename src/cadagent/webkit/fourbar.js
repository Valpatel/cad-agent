/** <cad-fourbar>: an interactive four-bar linkage. Sliders set the four links; the crank turns (or rocks between the
 * angles where the linkage locks) and the coupler and rocker follow on the assembly you pick, with the other assembly
 * as a ghost, the path of a point on the coupler, the Grashof class, and the transmission angle over the input's
 * travel against the 40 degree guideline.
 *
 *   <link rel="stylesheet" href="/kit/fourbar.css">              (in <head>: it keeps the space before the script runs)
 *   <script type="module" src="/kit/fourbar.js"></script>
 *   <cad-fourbar crank="40" coupler="120" rocker="80" ground="100" branch="open" angle="40">
 *     <img src="still.svg" alt="…" width="640" height="320"></cad-fourbar>
 *
 * Attributes (all optional; lengths in mm, angles in degrees): `crank` (a, the input), `coupler` (b), `rocker` (c, the
 * output), `ground` (d), `branch` (`open` or `crossed`: the two ways the same links assemble), `angle` (the input angle
 * the figure starts at, moved to the nearer end of the input's travel when it cannot get there), `theme` (`light` or
 * `dark`; by default the page's color-scheme, else the reader's preference). Out-of-range values are clamped. The
 * element's children are the still shown before the script loads; the live figure replaces them at the same size.
 *
 * Every number comes from formulas.js, the tested port of cadagent.formulas.linkages: grashof, fourbarInputLimits,
 * fourbarAngles and transmissionAngle (Norton's Design of Machinery, after Freudenstein). Rigid links on ideal pins,
 * position only: no speeds, forces, dynamics or joint play. `drawFourbar()` is pure, so tools/fourbar-still.mjs draws
 * the still from the same code. No dependencies, no shadow DOM, no inline script. The animation pauses off screen,
 * starts paused under prefers-reduced-motion, and has a pause button. Each change fires `cad-fourbar-change` with
 * `{ state, result }`.
 */
import { grashof, fourbarAngles, transmissionAngle, fourbarInputLimits } from './formulas.js';

export const VIEW = Object.freeze({ width: 640, height: 320 });
export const CHART = Object.freeze({ width: 320, height: 150 });
export const CONTROLS = Object.freeze({
  crank: { label: 'Crank a (input)', min: 10, max: 150, step: 1, unit: 'mm' },
  coupler: { label: 'Coupler b', min: 10, max: 150, step: 1, unit: 'mm' },
  rocker: { label: 'Rocker c (output)', min: 10, max: 150, step: 1, unit: 'mm' },
  ground: { label: 'Ground d', min: 10, max: 150, step: 1, unit: 'mm' },
});
// Norton's Example 4-1: a crank-rocker whose transmission angle dips below the guideline
export const DEFAULTS = Object.freeze({ crank: 40, coupler: 120, rocker: 80, ground: 100, branch: 'open', angle: 40 });
/** Degrees: a transmission angle below this binds (Norton, Chapter 4: the usual minimum for a four-bar). */
export const MU_POOR = 40;
export const BRANCHES = Object.freeze({ open: 'Open', crossed: 'Crossed' });
const CLASSES = {
  'crank-rocker': ['Crank-rocker', 'Grashof: the crank turns fully'],
  'double-crank': ['Double crank', 'Grashof: both cranks turn fully'],
  'rocker-crank': ['Rocker-crank', 'Grashof: only the output turns fully'],
  'double-rocker': ['Double rocker', 'Grashof: only the coupler turns fully'],
  'triple-rocker': ['Triple rocker', 'Non-Grashof: no link turns fully'],
  'change-point': ['Change point', 'S + L = P + Q'],
};
export const PALETTES = Object.freeze({
  light: Object.freeze({ ink: '#173d3c', muted: '#526863', sage: '#6f8a80', mist: '#eef1e4', back: '#fffdf5', peach: '#ffe1cc',
    rust: '#bd3a12', teal: '#1f6b64', line: '#c9d8ca' }),
  dark: Object.freeze({ ink: '#e6efe9', muted: '#a8bcb5', sage: '#86a499', mist: '#21393a', back: '#11201f', peach: '#4b2b1d',
    rust: '#ff9466', teal: '#6fd0c4', line: '#355450' }),
});
const RAD = Math.PI / 180, TAU = 2 * Math.PI;
const STAGE = { x0: 24, x1: 616, y0: 44, y1: 262 };            // where the linkage is fitted, in SVG units
const deg = x => x / RAD;
const fmt = x => `${Number(x.toFixed(1))}°`;                    // an angle in degrees, to 0.1
const wrap = t => t - TAU * Math.floor((t + Math.PI) / TAU);   // to [-pi, pi)
const esc = t => String(t).replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
const f = n => Number(n.toFixed(2));
// A label drawn over the links keeps a rim of the background around its letters, so it stays readable.
const halo = (P, colour = P.back, width = 4) => ` stroke="${colour}" stroke-width="${width}" stroke-linejoin="round" paint-order="stroke"`;
// Text sizes in SVG units: the figure is 640 wide, so on a phone (compact) it is drawn at about half size and its
// labels need to be larger to stay readable; the legend gives way there (the assembly buttons below say the same).
const SIZES = { normal: { text: 15, small: 13, pill: 15, ch: 9 }, compact: { text: 26, small: 22, pill: 24, ch: 14.2 } };

/** The state from attribute values (`get(name)` returns a string or null): unknown values fall back, numbers clamp. */
export function readState(get) {
  const s = { ...DEFAULTS };
  for (const [k, c] of Object.entries(CONTROLS)) {
    const v = parseFloat(get(k));
    if (Number.isFinite(v)) s[k] = Math.min(c.max, Math.max(c.min, v));
  }
  if (Object.hasOwn(BRANCHES, get('branch') ?? '')) s.branch = get('branch');      // not inherited keys
  const angle = parseFloat(get('angle'));
  if (Number.isFinite(angle)) s.angle = -deg(wrap(-angle * RAD));                   // to (-180, 180]
  return s;
}

/** The input's travel: a full turn, the one range it rocks over, or (with limits on both sides) the range that holds
 * the start angle; its mirror image below the ground link is out of reach without taking the linkage apart. lo and
 * hi in rad, lo < hi; a range through 180 degrees runs past pi. */
function travelOf(limits, angle) {
  if (!limits.closes) return null;
  if (limits.fullTurn) return { kind: 'turn', lo: -Math.PI, hi: Math.PI };
  if (limits.folded === null) return { kind: 'rock', lo: -limits.stretched, hi: limits.stretched };
  if (limits.stretched === null) return { kind: 'rock', lo: limits.folded, hi: TAU - limits.folded };
  return angle >= 0 ? { kind: 'rock', lo: limits.folded, hi: limits.stretched, mirror: true }
    : { kind: 'rock', lo: -limits.stretched, hi: -limits.folded, mirror: true };
}

/** Where the moving parts are at input angle t2 (rad), in link units with y up, on both branches. */
function pose(s, t2) {
  const { crank: a, coupler: b, rocker: c, ground: d } = s;
  const A = [a * Math.cos(t2), a * Math.sin(t2)];
  const at = crossed => {
    const got = fourbarAngles(a, b, c, d, t2, crossed);
    if (!got) return null;
    const B = [d + c * Math.cos(got[1]), c * Math.sin(got[1])];
    // a point on the coupler plate: half way along it and 0.4 of its length to its left
    const u = [B[0] - A[0], B[1] - A[1]];
    return { B, P: [A[0] + 0.5 * u[0] - 0.4 * u[1], A[1] + 0.5 * u[1] + 0.4 * u[0]] };
  };
  return { A, open: at(false), crossed: at(true), mu: transmissionAngle(a, b, c, d, t2) };
}

/** Everything the demo shows for a state, from the port: the class, the input's limits and travel, the start angle,
 * the transmission angle at every degree of the input and at each limit, its lowest value, and the figure's fit. */
export function compute(s) {
  const { crank: a, coupler: b, rocker: c, ground: d } = s;
  const g = grashof(a, b, c, d), limits = fourbarInputLimits(a, b, c, d);
  const travel = travelOf(limits, s.angle);
  // the start: the page's angle, moved to the nearer end of the travel when the input cannot get there
  let start = s.angle * RAD;
  if (travel?.kind === 'rock') {
    if (travel.hi > Math.PI && start < 0) start += TAU;
    if (start < travel.lo || start > travel.hi) {
      const gap = t => Math.abs(wrap(start - t));
      start = gap(travel.lo) <= gap(travel.hi) ? travel.lo : travel.hi;
    }
  }
  // the chart's axis: -180..180 degrees, or 0..360 when the travel runs through 180
  const axis = travel?.hi > Math.PI ? 0 : -Math.PI;
  const into = t => (t < axis ? t + TAU : t >= axis + TAU ? t - TAU : t);
  const edges = [limits.folded, limits.stretched].filter(e => e !== null).flatMap(e => [e, -e]).map(into);
  const angles = [...Array.from({ length: 361 }, (_, k) => axis + k * RAD), ...edges].sort((x, y) => x - y);
  const samples = angles.map(t => ({ t, ...pose(s, t) }));
  let low = null;
  for (const p of samples) if (p.mu !== null && (low === null || p.mu < low.mu)) low = { mu: p.mu, t: p.t };
  // where the branches meet in a change-point linkage: the links in one line at 0 or 180 degrees (mu = 0 there)
  const meets = g.kind !== 'change-point' ? [] : [0, Math.PI].filter(t => (transmissionAngle(a, b, c, d, t) ?? 1) < 1e-6).map(into);
  // one scale for the whole cycle and both branches, so the figure never zooms while it moves
  const xs = [0, d, -a, a], ys = [-a, a];
  for (const p of samples) for (const q of [p.open, p.crossed]) if (q) { xs.push(q.B[0], q.P[0]); ys.push(q.B[1], q.P[1]); }
  const [x0, x1, y0, y1] = [Math.min(...xs), Math.max(...xs), Math.min(...ys), Math.max(...ys)];
  const scale = Math.min((STAGE.x1 - STAGE.x0) / (x1 - x0), (STAGE.y1 - STAGE.y0) / (y1 - y0));
  const fit = { scale, cx: (STAGE.x0 + STAGE.x1) / 2 - scale * (x0 + x1) / 2, cy: (STAGE.y0 + STAGE.y1) / 2 + scale * (y0 + y1) / 2 };
  return { grashof: g, limits, travel, start, axis, edges, samples, low, meets, fit };
}

/** An input angle (rad) as the figure and the chart show it: in the chart's axis, -180..180 or 0..360 degrees. */
const shown = (r, t) => deg(r.axis === 0 ? t - TAU * Math.floor(t / TAU) : wrap(t));
export const className = r => r.limits.closes ? CLASSES[r.grashof.inversion][0] : 'No loop';
export function classNote(r) {
  if (!r.limits.closes) return 'One link is longer than the other three together';
  if (r.grashof.kind !== 'change-point') return CLASSES[r.grashof.inversion][1];
  return `${CLASSES['change-point'][1]}: ${r.grashof.crankRotates ? 'the crank turns fully' : 'the input rocks'}`;
}
/** The input's travel in words: "Full turn", "±137.9°", "51.3° to 125.1°", or "None". */
export function travelText(r) {
  const t = r.travel;
  if (!t) return 'None';
  if (t.kind === 'turn') return 'Full turn';
  if (Math.abs(t.lo + t.hi) < 1e-12) return `±${fmt(deg(t.hi))}`;
  return `${fmt(deg(t.lo))} to ${fmt(deg(t.hi))}`;
}
export function travelNote(r) {
  if (!r.travel) return 'The links cannot make a loop';
  if (r.travel.kind === 'turn') return 'The crank goes all the way round';
  return r.travel.mirror ? 'Locks at both ends; a mirror range below the ground' : 'Locks where coupler and rocker line up';
}
const lowText = r => (r.low === null ? '–' : fmt(deg(r.low.mu)));

export function summary(s, r) {
  const links = `Four-bar with crank ${s.crank}, coupler ${s.coupler}, rocker ${s.rocker} and ground ${s.ground} mm`;
  if (!r.limits.closes) return `${links}: the links cannot close at any input angle (one is longer than the other three together).`;
  const lowest = deg(r.low.mu);
  return `${links}, ${s.branch} branch: ${className(r).toLowerCase()} (${classNote(r).replace(/^[^:]*: /, '')}); ` +
    `input travel ${travelText(r).toLowerCase()}; lowest transmission angle ${lowText(r)} at ${fmt(shown(r, r.low.t))}, ` +
    `${lowest < MU_POOR ? 'below' : 'above'} the ${MU_POOR}° guideline.`;
}

// ----------------------------------------------------------------------------- the figure
const toSvg = (r, [x, y]) => [r.fit.cx + r.fit.scale * x, r.fit.cy - r.fit.scale * y];
const pt = (r, p) => toSvg(r, p).map(f).join(',');
const pair = (p, q) => `${f(p[0])},${f(p[1])} ${f(q[0])},${f(q[1])}`;
/** An arc about the input pivot, counter-clockwise from t0 to t1 (rad, t0 < t1 < t0 + 2 pi). */
function crankArc(r, radius, t0, t1) {
  const [cx, cy] = toSvg(r, [0, 0]), rr = r.fit.scale * radius;
  const p = t => `${f(cx + rr * Math.cos(t))} ${f(cy - rr * Math.sin(t))}`;
  return `M${p(t0)}A${f(rr)} ${f(rr)} 0 ${t1 - t0 > Math.PI ? 1 : 0} 0 ${p(t1)}`;
}

/** Everything that moves, for a state at input angle t2 (rad): the links on the chosen branch, the other branch as a
 * ghost, the transmission angle's arc and label, and whether the input is at a limit (locked). */
export function geometry(s, r, t2, compact = false) {
  const at = pose(s, t2), here = at[s.branch], ghost = at[s.branch === 'open' ? 'crossed' : 'open'];
  const O2 = toSvg(r, [0, 0]), O4 = toSvg(r, [s.ground, 0]), A = toSvg(r, at.A);
  const locked = r.travel?.kind === 'rock' && (Math.abs(t2 - r.travel.lo) < 1e-9 || Math.abs(t2 - r.travel.hi) < 1e-9);
  const out = { O2, O4, A, closes: !!here, mu: at.mu, locked, crank: pair(O2, A), ghost: '', plate: '', coupler: '', rocker: '', muArc: '',
    B: [-99, -99], P: [-99, -99], muLabel: { x: -99, y: -99, anchor: 'start', text: '', poor: false } };
  // the input angle's arc, from the ground link to the crank, the short way
  const t = wrap(t2), rr = Math.min(28, 0.45 * r.fit.scale * s.crank);
  out.inputArc = `M${f(O2[0] + rr)} ${f(O2[1])}A${f(rr)} ${f(rr)} 0 0 ${t >= 0 ? 0 : 1} ${f(O2[0] + rr * Math.cos(t))} ${f(O2[1] - rr * Math.sin(t))}`;
  out.inputLabel = `θ₂ ${fmt(shown(r, t2))}`;
  if (!here) return out;
  const B = toSvg(r, here.B), P = toSvg(r, here.P);
  Object.assign(out, { B, P, plate: `${pt(r, at.A)} ${pt(r, here.B)} ${pt(r, here.P)}`, coupler: pair(A, B), rocker: pair(O4, B) });
  if (ghost) out.ghost = `${f(A[0])},${f(A[1])} ${pt(r, ghost.B)} ${f(O4[0])},${f(O4[1])}`;
  // the transmission angle at B, between the coupler (B to A) and the rocker (B to O4), drawn on its acute side
  const dir = p => Math.atan2(B[1] - p[1], p[0] - B[0]);
  let u = dir(A), span = wrap(dir(O4) - u);
  if (Math.abs(span) > Math.PI / 2) { u = wrap(u + Math.PI); span = wrap(dir(O4) - u); }
  const mr = 22, q = w => `${f(B[0] + mr * Math.cos(w))} ${f(B[1] - mr * Math.sin(w))}`;
  out.muArc = `M${q(u)}A${mr} ${mr} 0 0 ${span >= 0 ? 0 : 1} ${q(u + span)}`;
  // the label sits in the wider gap between the two links at B, on its bisector, clear of both
  const gap = dir(O4) - dir(A) - TAU * Math.floor((dir(O4) - dir(A)) / TAU);
  const away = gap > Math.PI ? dir(A) + gap / 2 : dir(O4) + (TAU - gap) / 2, cx = Math.cos(away), poor = deg(at.mu) < MU_POOR;
  const z = SIZES[compact ? 'compact' : 'normal'], reach = 1.7 * z.text;
  out.muLabel = { x: f(Math.min(VIEW.width - 12, Math.max(12, B[0] + reach * cx))),
    y: f(Math.min(272, Math.max(20 + z.text, B[1] - reach * Math.sin(away) + z.text / 3))),
    anchor: cx < -0.35 ? 'end' : cx > 0.35 ? 'start' : 'middle', text: `${locked ? 'locked · ' : ''}μ ${fmt(deg(at.mu))}`, poor };
  return out;
}

/** What stays put while the crank moves: the ground, the crank's circle with the arcs where the links cannot close and
 * the limits, and the coupler point's path on the chosen branch. */
function staticLayer(s, r, P, z) {
  const O2 = toSvg(r, [0, 0]), O4 = toSvg(r, [s.ground, 0]);
  const pivot = ([x, y]) => `<path d="M${f(x - 13)} ${f(y + 12)}h26M${f(x - 7)} ${f(y + 12)}l-5 7M${f(x + 1)} ${f(y + 12)}l-5 7M${f(x + 9)} ${f(y + 12)}l-5 7" stroke="${P.sage}" stroke-width="1.5" fill="none"/>` +
    `<path d="M${f(x)} ${f(y)}l-8 12h16z" fill="${P.mist}" stroke="${P.sage}" stroke-width="1.5"/>`;
  let out = `<line x1="${f(O2[0])}" y1="${f(O2[1])}" x2="${f(O4[0])}" y2="${f(O4[1])}" stroke="${P.sage}" stroke-width="2" stroke-dasharray="7 5"/>` +
    pivot(O2) + pivot(O4) + `<text x="${f((O2[0] + O4[0]) / 2)}" y="${f(O2[1] + 6 + z.small)}" text-anchor="middle" font-size="${z.small}" fill="${P.muted}">d</text>` +
    `<circle cx="${f(O2[0])}" cy="${f(O2[1])}" r="${f(r.fit.scale * s.crank)}" fill="none" stroke="${P.sage}" stroke-width="1.2" stroke-dasharray="3 4"/>`;
  const { folded: F, stretched: S } = r.limits;
  // the crank's circle where the links cannot close, in rust: through 180 degrees past the stretched limit, through 0
  // inside the folded one
  const gaps = [...(S !== null ? [[S, TAU - S]] : []), ...(F !== null ? [[-F, F]] : [])];
  for (const [g0, g1] of gaps) out += `<path data-part="no-close" d="${crankArc(r, s.crank, g0, g1)}" fill="none" stroke="${P.rust}" stroke-width="3" stroke-dasharray="2 5" stroke-linecap="round"/>`;
  for (const e of [F, S].filter(v => v !== null).flatMap(v => [v, -v])) {
    const [x, y] = toSvg(r, [s.crank * Math.cos(e), s.crank * Math.sin(e)]), dx = Math.cos(e), dy = -Math.sin(e);
    // outward along the radius, far enough that the label's box clears the crank pin whichever way it points
    const text = fmt(shown(r, e)), reach = 14 + Math.abs(dx) * 0.28 * z.small * text.length + Math.abs(dy) * 0.5 * z.small;
    const lx = Math.min(VIEW.width - 2.8 * z.small, Math.max(2.8 * z.small, x + dx * reach));
    const ly = Math.min(VIEW.height - 54, Math.max(z.small + 4, y + dy * reach + z.small / 3));
    out += `<line data-part="limit" x1="${f(x - dx * 8)}" y1="${f(y - dy * 8)}" x2="${f(x + dx * 10)}" y2="${f(y + dy * 10)}" stroke="${P.rust}" stroke-width="2.5" stroke-linecap="round"/>` +
      `<text x="${f(lx)}" y="${f(ly)}" text-anchor="middle" font-size="${z.small}" fill="${P.rust}"${halo(P)}>${esc(text)}</text>`;
  }
  // the coupler point's path: one polyline per run of positions that close
  const runs = [[]];
  for (const p of r.samples) {
    const q = p[s.branch];
    if (q) runs.at(-1).push(pt(r, q.P)); else if (runs.at(-1).length) runs.push([]);
  }
  for (const run of runs) if (run.length > 1) out += `<polyline data-part="trace" points="${run.join(' ')}" fill="none" stroke="${P.teal}" stroke-width="1.4" stroke-dasharray="1 3" stroke-linecap="round"/>`;
  return out;
}

/** The pill under the linkage: the class, and where a rocking input locks or a turning one's lowest transmission angle
 * against the guideline. */
export function pill(r) {
  if (!r.limits.closes) return { text: 'No loop: one link outreaches the rest', poor: true };
  if (r.travel.kind === 'rock') return { text: `${className(r)} · locks at ${lockText(r)}`, poor: true };
  const poor = deg(r.low.mu) < MU_POOR;
  return { text: `${className(r)} · lowest μ ${lowText(r)}${poor ? ` < ${MU_POOR}°` : ''}`, poor };
}
/** Where a rocking input locks: "±137.9°", or "51.3°, 125.1°". */
const lockText = r => travelText(r).replace(' to ', ', ');

/** The figure as SVG markup at input angle t2 (rad; the start angle by default). `still` adds what a standalone file
 * needs (namespace, size, title, background, a font); `palette` is one of PALETTES; `compact` sizes the text for a
 * phone. */
export function drawFourbar(s, r, { t2 = r.start, still = false, label = summary(s, r), palette = PALETTES.light, compact = false } = {}) {
  const P = palette, g = geometry(s, r, t2, compact), { width: W, height: H } = VIEW, z = SIZES[compact ? 'compact' : 'normal'];
  const pl = pill(r), pillW = Math.min(W - 8, z.ch * pl.text.length + 2.4 * z.pill), pillH = 2.1 * z.pill;
  const other = s.branch === 'open' ? 'crossed' : 'open';
  return `<svg${still ? ' xmlns="http://www.w3.org/2000/svg"' : ''} viewBox="0 0 ${W} ${H}"${still ? ` width="${W}" height="${H}"` : ''} role="img" aria-label="${esc(label)}">` +
    (still ? `<title>${esc(label)}</title><rect width="${W}" height="${H}" fill="${P.back}"/>` : '') +
    `<g font-family="${still ? 'Inter,system-ui,-apple-system,Segoe UI,sans-serif' : 'inherit'}" font-size="${z.text}" fill="${P.ink}">` +
    `<g data-part="static">${staticLayer(s, r, P, z)}</g>` +
    `<text data-part="label-input" x="16" y="${10 + z.text}" font-weight="700" fill="${P.rust}"${halo(P)}>${esc(g.inputLabel)}</text>` +
    (compact ? '' : `<text x="${W - 20}" y="26" font-size="13" fill="${P.muted}" text-anchor="end">${esc(s.branch)} branch, solid · ${other}, dashed</text>`) +
    `<path data-part="input-arc" d="${g.inputArc}" fill="none" stroke="${P.rust}" stroke-width="1.5"/>` +
    `<polyline data-part="ghost" points="${g.ghost}" fill="none" stroke="${P.sage}" stroke-width="2.5" stroke-dasharray="6 5" stroke-linejoin="round"/>` +
    `<polygon data-part="plate" points="${g.plate}" fill="${P.mist}" stroke="${P.ink}" stroke-width="1.5" stroke-linejoin="round"/>` +
    `<polyline data-part="rocker" points="${g.rocker}" fill="none" stroke="${P.teal}" stroke-width="6" stroke-linecap="round"/>` +
    `<polyline data-part="coupler" points="${g.coupler}" fill="none" stroke="${P.ink}" stroke-width="6" stroke-linecap="round"/>` +
    `<polyline data-part="crank" points="${g.crank}" fill="none" stroke="${P.rust}" stroke-width="6" stroke-linecap="round"/>` +
    `<path data-part="mu-arc" d="${g.muArc}" fill="none" stroke="${g.muLabel.poor ? P.rust : P.ink}" stroke-width="1.8"/>` +
    ['o2', 'o4', 'a', 'b'].map(k => {
      const [x, y] = { o2: g.O2, o4: g.O4, a: g.A, b: g.B }[k];
      return `<circle data-part="pin-${k}" cx="${f(x)}" cy="${f(y)}" r="5" fill="${P.back}" stroke="${P.ink}" stroke-width="2"/>`;
    }).join('') +
    `<circle data-part="point-p" cx="${f(g.P[0])}" cy="${f(g.P[1])}" r="4" fill="${P.teal}"/>` +
    `<text data-part="label-mu" x="${g.muLabel.x}" y="${g.muLabel.y}" text-anchor="${g.muLabel.anchor}" font-weight="700" fill="${g.muLabel.poor ? P.rust : P.ink}"${halo(P)}>${esc(g.muLabel.text)}</text>` +
    `<rect x="${f((W - pillW) / 2)}" y="${f(H - 10 - pillH)}" width="${f(pillW)}" height="${f(pillH)}" rx="${f(pillH / 2)}" fill="${pl.poor ? P.peach : P.mist}" stroke="${pl.poor ? P.rust : P.sage}"/>` +
    `<text data-part="pill" x="${W / 2}" y="${f(H - 10 - pillH / 2 + 0.36 * z.pill)}" text-anchor="middle" font-size="${z.pill}" font-weight="700" fill="${pl.poor ? P.rust : P.ink}">${esc(pl.text)}</text>` +
    '</g></svg>';
}

// ----------------------------------------------------------------------------- the chart
const CX = { x0: 40, x1: 308, y0: 14, y1: 116 };                 // the plot area, in the chart's units
const chartX = (r, t) => CX.x0 + (CX.x1 - CX.x0) * (t - r.axis) / TAU;
const chartY = mu => CX.y1 - (CX.y1 - CX.y0) * deg(mu) / 90;

/** The chart's marker at input angle t2 (rad): its x, and its y on the curve where the links close there. */
export function chartMarker(s, r, t2) {
  const t = r.axis + (t2 - r.axis) - TAU * Math.floor((t2 - r.axis) / TAU);
  const mu = transmissionAngle(s.crank, s.coupler, s.rocker, s.ground, t2);
  return { x: f(chartX(r, t)), y: f(chartY(mu ?? 0)), closes: mu !== null };
}

/** The transmission angle over the input's travel as SVG markup: the band below MU_POOR, the stretches where the links
 * cannot close, the limits (rust) and the change points (dashed), and a marker at input angle t2. */
export function drawChart(s, r, { t2 = r.start, palette = PALETTES.light } = {}) {
  const P = palette, { width: W, height: H } = CHART, yPoor = f(chartY(MU_POOR * RAD));
  const label = r.low === null ? 'Transmission angle: the links cannot close at any input angle.' :
    `Transmission angle over the input angle from ${fmt(deg(r.axis))} to ${fmt(deg(r.axis + TAU))}: lowest ${lowText(r)} at ` +
    `${fmt(shown(r, r.low.t))}; below ${MU_POOR}° the linkage binds.`;
  let body = `<rect x="${CX.x0}" y="${yPoor}" width="${CX.x1 - CX.x0}" height="${f(CX.y1 - yPoor)}" fill="${P.peach}"/>`;
  // where the links cannot close: the runs of samples without a transmission angle, between their neighbours
  const shade = (t0, t1) => { body += `<rect data-part="chart-no-close" x="${f(chartX(r, t0))}" y="${CX.y0}" width="${f(chartX(r, t1) - chartX(r, t0))}" height="${CX.y1 - CX.y0}" fill="${P.mist}"/>`; };
  let from = null;
  r.samples.forEach((p, i) => {
    if (p.mu === null && from === null) from = i ? r.samples[i - 1].t : p.t;
    else if (p.mu !== null && from !== null) { shade(from, p.t); from = null; }
  });
  if (from !== null) shade(from, r.samples.at(-1).t);
  for (const v of [0, MU_POOR, 90]) body += `<line x1="${CX.x0 - 4}" y1="${f(chartY(v * RAD))}" x2="${CX.x1}" y2="${f(chartY(v * RAD))}" stroke="${P.line}"/>` +
    `<text x="${CX.x0 - 7}" y="${f(chartY(v * RAD) + 4)}" text-anchor="end">${v}°</text>`;
  for (let k = 0; k <= 4; k++) body += `<text x="${f(chartX(r, r.axis + k * Math.PI / 2))}" y="${CX.y1 + 15}" text-anchor="middle">${Math.round(deg(r.axis) + 90 * k)}°</text>`;
  body += `<text x="${(CX.x0 + CX.x1) / 2}" y="${H - 3}" text-anchor="middle">input angle θ₂</text>` +
    `<text x="${CX.x1 - 4}" y="${f(CX.y1 - 6)}" text-anchor="end" fill="${P.rust}"${halo(P, P.peach, 3)}>below ${MU_POOR}°: binds</text>` +
    `<text x="${CX.x0 + 4}" y="${CX.y0 + 12}" fill="${P.ink}" font-weight="700">μ</text>`;
  const runs = [[]];
  for (const p of r.samples) if (p.mu !== null) runs.at(-1).push(`${f(chartX(r, p.t))},${f(chartY(p.mu))}`); else if (runs.at(-1).length) runs.push([]);
  for (const run of runs) if (run.length > 1) body += `<polyline data-part="chart-mu" points="${run.join(' ')}" fill="none" stroke="${P.teal}" stroke-width="2.2" stroke-linejoin="round"/>`;
  const line = (t, part, stroke, dash = '') => `<line data-part="${part}" x1="${f(chartX(r, t))}" y1="${CX.y0}" x2="${f(chartX(r, t))}" y2="${CX.y1}" stroke="${stroke}" stroke-width="1.5"${dash}/>`;
  for (const t of r.edges) body += line(t, 'chart-limit', P.rust);
  for (const t of r.meets) body += line(t, 'chart-meet', P.sage, ' stroke-dasharray="3 3"');
  const m = chartMarker(s, r, t2);
  body += `<line data-part="chart-cursor" x1="${m.x}" y1="${CX.y0}" x2="${m.x}" y2="${CX.y1}" stroke="${P.sage}"/>` +
    `<circle data-part="chart-dot" cx="${m.x}" cy="${m.y}" r="${m.closes ? 4.5 : 0}" fill="${P.rust}" stroke="${P.back}" stroke-width="1.5"/>`;
  return `<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="${esc(label)}"><g font-family="inherit" font-size="11" fill="${P.muted}">${body}</g></svg>`;
}

// ----------------------------------------------------------------------------- the motion
const TURN = 6000;                   // ms for one turn of the crank
const DWELL = 700;                   // ms held, locked, at each limit of a rocking input
const ease = v => (1 - Math.cos(Math.PI * v)) / 2;

/** The input angle (rad) t ms after the start: a steady turn, or a rock between the limits with a dwell at each.
 * At t = 0 it is the start angle exactly, so the first live frame is the still. */
export function angleAt(r, t) {
  const tr = r.travel;
  if (!tr || t <= 0) return r.start;
  if (tr.kind === 'turn') return r.start + TAU * (t % TURN) / TURN;
  const span = tr.hi - tr.lo, leg = Math.max(900, TURN * span / TAU), period = 2 * (leg + DWELL);
  // where the start sits on the way up: ease(v) = (start - lo) / span
  const v0 = Math.acos(Math.min(1, Math.max(-1, 1 - 2 * (r.start - tr.lo) / span))) / Math.PI;
  const u = (v0 * leg + t) % period;
  if (u < leg) return tr.lo + span * ease(u / leg);
  if (u < leg + DWELL) return tr.hi;
  if (u < 2 * leg + DWELL) return tr.hi - span * ease((u - leg - DWELL) / leg);
  return tr.lo;
}

// ----------------------------------------------------------------------------- the element (browsers only)
const Base = globalThis.HTMLElement ?? class {};
let instances = 0;

export class CadFourbar extends Base {
  static get observedAttributes() { return ['branch', 'angle', 'theme', ...Object.keys(CONTROLS)]; }

  connectedCallback() {
    this.reduced ??= matchMedia('(prefers-reduced-motion: reduce)');
    this.dark ??= matchMedia('(prefers-color-scheme: dark)');
    this.narrow ??= matchMedia('(max-width: 699.98px)');                   // fourbar.css's phone layout
    if (!this.built) {
      this.built = true;
      this.uid = `fb${++instances}`;
      this.state = readState(n => this.getAttribute(n));
      this.result = compute(this.state);
      this.playing = !this.reduced.matches;
      this.elapsed = 0;               // the animation's own clock, ms from the start angle; it stops while the motion does
      this.visible = true;
      this.build();
      this.update();
    }
    this.onMotion ??= () => this.setPlaying(!this.reduced.matches);
    this.onScheme ??= () => this.applyTheme();
    this.onNarrow ??= () => { this.paint(); this.render(); };
    this.reduced.addEventListener?.('change', this.onMotion);
    this.dark.addEventListener?.('change', this.onScheme);
    this.narrow.addEventListener?.('change', this.onNarrow);
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
    this.dark?.removeEventListener?.('change', this.onScheme);
    this.narrow?.removeEventListener?.('change', this.onNarrow);
    clearTimeout(this.announce);
  }

  attributeChangedCallback(name) {
    if (!this.built) return;
    if (name === 'theme') { this.applyTheme(); return; }
    this.state = readState(n => this.getAttribute(n));
    this.syncControls();
    this.restart();
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
    if (this.figure) { this.paint(); this.render(); }
  }

  build() {
    const id = n => `${this.uid}-${n}`;
    // The visible value is a plain span, not an <output> (an implicit live region): the slider speaks its own value
    // (aria-valuetext), and only the debounced .fb-status line announces results.
    const slider = (k, c) => `<div class="fb-field"><label for="${id(k)}">${esc(c.label)} <span class="fb-value" data-out="${k}" aria-hidden="true"></span></label>` +
      `<input id="${id(k)}" type="range" name="${k}" min="${c.min}" max="${c.max}" step="${c.step}"></div>`;
    this.replaceChildren();
    this.insertAdjacentHTML('beforeend', `<div class="fb-figure"></div><div class="fb-panel">
<div class="fb-readout">
<p class="fb-tile"><span class="fb-k">Grashof class</span><b data-out="class"></b><span data-out="class-note"></span></p>
<p class="fb-tile" data-out="mu-tile"><span class="fb-k">Transmission angle</span><b data-out="mu"></b><span data-out="mu-note"></span></p>
<p class="fb-tile"><span class="fb-k">Input travel</span><b data-out="travel"></b><span data-out="travel-note"></span></p></div>
<div class="fb-body"><div class="fb-chart"></div><div class="fb-controls">${Object.entries(CONTROLS).map(([k, c]) => slider(k, c)).join('')}
<fieldset><legend>Assembly</legend>${Object.entries(BRANCHES).map(([v, t]) =>
  `<label><input type="radio" name="${id('branch')}" value="${v}" data-name="branch"> ${t}</label>`).join('')}</fieldset></div></div>
<div class="fb-foot"><p class="fb-note">Rigid links on ideal pins, position only: no speeds, forces or joint play (Norton; Freudenstein).</p>
<button type="button" class="fb-play"></button></div>
<p class="fb-status" role="status" aria-live="polite"></p></div>`);
    this.figure = this.querySelector('.fb-figure');
    this.chart = this.querySelector('.fb-chart');
    this.out = Object.fromEntries([...this.querySelectorAll('[data-out]')].map(n => [n.dataset.out, n]));
    this.play = this.querySelector('.fb-play');
    this.status = this.querySelector('.fb-status');
    this.play.addEventListener('click', () => this.setPlaying(!this.playing));
    this.addEventListener('input', e => this.onInput(e));
    this.addEventListener('change', e => this.onInput(e));
    this.dataset.theme = this.theme();
    this.syncControls();
  }

  /** Draw the figure and the chart afresh (for a new state or theme) at the frame on screen. */
  paint() {
    const s = this.state, r = this.result, palette = PALETTES[this.dataset.theme], t2 = angleAt(r, this.clock());
    this.palette = palette;
    this.compact = this.narrow.matches;
    this.figure.innerHTML = drawFourbar(s, r, { t2, palette, compact: this.compact, label: summary(s, r) });
    this.chart.innerHTML = drawChart(s, r, { t2, palette });
    this.parts = Object.fromEntries([...this.querySelectorAll('.fb-figure [data-part], .fb-chart [data-part]')].map(n => [n.dataset.part, n]));
  }

  syncControls() {
    for (const k of Object.keys(CONTROLS)) this.querySelector(`input[name="${k}"]`).value = this.state[k];
    for (const r of this.querySelectorAll('input[type="radio"]')) r.checked = this.state.branch === r.value;
  }

  onInput(e) {
    const t = e.target;
    if (!t.matches?.('input')) return;
    const name = t.dataset.name || t.name;
    if (name in CONTROLS) this.state[name] = Number(t.value);
    else if (name === 'branch' && t.checked) this.state.branch = t.value;
    else return;
    // a new linkage starts from where the crank is now, as far as its travel allows
    this.state.angle = shown({ axis: -Math.PI }, angleAt(this.result, this.clock()));
    this.restart({ announce: true });
  }

  restart(opts) {
    this.result = compute(this.state);
    this.elapsed = 0;
    if (this.frame) this.t0 = performance.now();
    this.update(opts);
  }

  setPlaying(on) {
    this.playing = on;
    this.loop();
    this.render();
  }

  // Only what the user does is announced, once the slider stops moving: the first draw and attribute changes are not
  // (the figure's aria-label carries the same summary). An announcement still pending speaks the latest result.
  update({ announce = false } = {}) {
    const s = this.state, r = this.result;
    for (const k of Object.keys(CONTROLS)) {
      this.out[k].textContent = `${s[k]} mm`;
      this.querySelector(`input[name="${k}"]`).setAttribute('aria-valuetext', `${s[k]} millimetres`);
    }
    this.out.class.textContent = className(r);
    this.out['class-note'].textContent = classNote(r);
    this.out['mu-note'].textContent = r.low === null ? 'No position closes' : r.travel.kind === 'rock' ? 'Falls to 0° where the input locks' :
      `Lowest ${lowText(r)} at ${fmt(shown(r, r.low.t))}`;
    this.out['mu-tile'].dataset.verdict = r.low === null || deg(r.low.mu) < MU_POOR ? 'poor' : 'good';
    this.out.travel.textContent = travelText(r);
    this.out['travel-note'].textContent = travelNote(r);
    this.said = summary(s, r);
    this.paint();
    if (announce) {
      clearTimeout(this.announce);
      this.announce = setTimeout(() => { this.status.textContent = this.said; }, 700);
    }
    this.render();
    this.dispatchEvent(new CustomEvent('cad-fourbar-change', { bubbles: true, detail: { state: { ...s }, result: {
      grashof: { ...r.grashof }, limits: { ...r.limits }, travel: r.travel && { ...r.travel }, start: r.start, lowest: r.low && { ...r.low } } } }));
  }

  clock() { return this.frame ? performance.now() - this.t0 : this.elapsed; }

  render(t2 = angleAt(this.result, this.clock())) {
    const s = this.state, r = this.result, P = this.palette, g = geometry(s, r, t2, this.compact), p = this.parts;
    const set = (n, a) => { for (const k in a) n.setAttribute(k, a[k]); };
    set(p.crank, { points: g.crank }); set(p['input-arc'], { d: g.inputArc }); p['label-input'].textContent = g.inputLabel;
    set(p.ghost, { points: g.ghost }); set(p.plate, { points: g.plate }); set(p.coupler, { points: g.coupler }); set(p.rocker, { points: g.rocker });
    set(p['mu-arc'], { d: g.muArc, stroke: g.muLabel.poor ? P.rust : P.ink });
    for (const [k, at] of [['pin-a', g.A], ['pin-b', g.B]]) set(p[k], { cx: f(at[0]), cy: f(at[1]) });
    set(p['point-p'], { cx: f(g.P[0]), cy: f(g.P[1]) });
    set(p['label-mu'], { x: g.muLabel.x, y: g.muLabel.y, 'text-anchor': g.muLabel.anchor, fill: g.muLabel.poor ? P.rust : P.ink });
    p['label-mu'].textContent = g.muLabel.text;
    const m = chartMarker(s, r, t2);
    set(p['chart-cursor'], { x1: m.x, x2: m.x }); set(p['chart-dot'], { cx: m.x, cy: m.y, r: m.closes ? 4.5 : 0 });
    this.out.mu.textContent = g.mu === null ? '–' : `${g.locked ? 'Locked, ' : ''}${fmt(deg(g.mu))}`;
    this.play.textContent = this.playing ? 'Pause' : 'Play';
    this.play.setAttribute('aria-label', `${this.playing ? 'Pause' : 'Play'} the linkage`);
  }

  loop() {
    const run = this.playing && this.visible && this.isConnected && this.result.travel !== null;
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

if (typeof customElements !== 'undefined' && !customElements.get('cad-fourbar')) customElements.define('cad-fourbar', CadFourbar);
