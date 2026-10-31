/** The landing page's cantilever snap-fit animation, computed from its geometry instead of keyframed by eye.
 *
 * The arm (with its hook) is fixed to the wall and pivots about its root; the mating part (a plate with a catch rib)
 * slides in from the right. For every sampled position of the mating part the arm's lift is the smallest rotation
 * at which the two outlines do not overlap, so the hook rides the catch's lead-in, slides over its top, drops in behind
 * its retaining face and holds when the part is pulled back. Rigid rotation about the root stands in for bending:
 * it is a picture of the motion, not a deflection result (`cad-agent snapfit` does the sizing).
 * Coordinates are SVG user units, y down. tests/site-snap-demo.test.mjs checks contact and engagement.
 */
export const ROOT = [64, 121];
// Arm outline at rest: top edge, end face, hook lead-in ramp (faces the incoming catch), hook tip, retaining face
// (faces the wall), underside back to the root.
export const ARM = [[64, 100], [318, 110], [318, 132], [290, 154], [282, 154], [282, 132], [64, 142]];
// Catch rib on the mating plate, engaged position: lead-in chamfer on the leading (left) side, square retaining face
// on the right, which the hook's retaining face meets when the part is pulled back.
export const RIB = [[246, 176], [246, 160], [266, 140], [280, 140], [280, 176]];
export const PLATE = [[206, 176], [620, 176], [620, 190], [206, 190]];
export const START = 120;              // mating part offset (+x) before insertion
const MAX_LIFT = 12;                   // degrees; the search bracket

const rotate = ([x, y], liftDeg) => {   // lift > 0 raises the free end (counter-clockwise on screen)
  const a = -liftDeg * Math.PI / 180, [cx, cy] = ROOT;
  return [cx + (x - cx) * Math.cos(a) - (y - cy) * Math.sin(a), cy + (x - cx) * Math.sin(a) + (y - cy) * Math.cos(a)];
};
export const armAt = lift => ARM.map(p => rotate(p, lift));
export const shift = (poly, dx) => poly.map(([x, y]) => [x + dx, y]);

const cross = (o, a, b) => (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0]);
const segmentsCross = (p1, p2, q1, q2) => {
  const d1 = cross(q1, q2, p1), d2 = cross(q1, q2, p2), d3 = cross(p1, p2, q1), d4 = cross(p1, p2, q2);
  return ((d1 > 0 && d2 < 0) || (d1 < 0 && d2 > 0)) && ((d3 > 0 && d4 < 0) || (d3 < 0 && d4 > 0));
};
const inside = ([x, y], poly) => {
  let c = false;
  for (let i = 0, j = poly.length - 1; i < poly.length; j = i++) {
    const [xi, yi] = poly[i], [xj, yj] = poly[j];
    if ((yi > y) !== (yj > y) && x < (xj - xi) * (y - yi) / (yj - yi) + xi) c = !c;
  }
  return c;
};
/** True when the outlines overlap (touching edges do not count). */
export function overlap(a, b) {
  for (let i = 0; i < a.length; i++) for (let j = 0; j < b.length; j++)
    if (segmentsCross(a[i], a[(i + 1) % a.length], b[j], b[(j + 1) % b.length])) return true;
  return a.some(p => inside(p, b)) || b.some(p => inside(p, a));
}
export const clear = (lift, offset) => {
  const arm = armAt(lift);
  return !overlap(arm, shift(RIB, offset)) && !overlap(arm, shift(PLATE, offset));
};
/** Smallest lift (degrees) at which the arm clears the mating part at this offset. */
export function liftAt(offset) {
  if (clear(0, offset)) return 0;
  let lo = 0, hi = MAX_LIFT;
  if (!clear(hi, offset)) throw new Error(`snap demo: no clearance at offset ${offset}`);
  for (let i = 0; i < 50; i++) { const mid = (lo + hi) / 2; (clear(mid, offset) ? (hi = mid) : (lo = mid)); }
  return hi;
}
/** Offset at which the hook drops in: below it the arm is at rest, just above it the arm is lifted. */
export function snapOffset() {
  let lo = 0, hi = 30;                  // lift(lo) = 0, lift(hi) > 0
  for (let i = 0; i < 50; i++) { const mid = (lo + hi) / 2; (liftAt(mid) > 0 ? (hi = mid) : (lo = mid)); }
  return hi;
}
/** How far the engaged part can be pulled back before the retaining faces meet. */
export function pullStop() {
  let hi = 0;
  while (clear(0, hi)) { hi += 0.25; if (hi > START) throw new Error('snap demo: the catch never meets the hook'); }
  let lo = hi - 0.25;
  for (let i = 0; i < 50; i++) { const mid = (lo + hi) / 2; (clear(0, mid) ? (lo = mid) : (hi = mid)); }
  return lo;
}

const ease = u => u < .5 ? 4 * u * u * u : 1 - (-2 * u + 2) ** 3 / 2;
const f = (n, d = 2) => Number(n.toFixed(d));
const mix = (a, b, t) => '#' + [0, 2, 4].map(i => Math.round(parseInt(a.slice(1 + i, 3 + i), 16) * (1 - t) + parseInt(b.slice(1 + i, 3 + i), 16) * t)
  .toString(16).padStart(2, '0')).join('');

/** Timeline samples: [percent, offset, lift, catchOpacity]. One loop: wait, insert (contact computed), snap, hold,
 * pull back against the retaining face, hold, fade out, reset, fade in. */
export function timeline() {
  const rows = [[0, START, 0, 1], [8, START, 0, 1]];
  const snap = snapOffset(), pull = pullStop() * 0.95;
  let snapped = false;
  for (let k = 1; k <= 84; k++) {      // insertion: 8 % → 50 %
    const pct = 8 + k * 0.5, offset = START * (1 - ease(k / 84));
    if (!snapped && offset < snap) {   // the hook drops in: a quick fall with a small overshoot, then rest
      snapped = true;
      let overshoot = -0.4;            // as far past rest as the parts allow
      while (overshoot < 0 && !clear(overshoot, offset)) overshoot = Math.min(0, overshoot + 0.05);
      rows.push([pct - 0.25, snap + 1e-3, liftAt(snap + 1e-3), 1], [pct + 0.6, offset, overshoot, 1], [pct + 1.4, offset, 0.15, 1], [pct + 2.2, offset, 0, 1]);
      continue;
    }
    if (snapped && rows.at(-1)[0] >= pct) continue;
    rows.push([pct, offset, snapped ? 0 : liftAt(offset), 1]);
  }
  rows.push([60, 0, 0, 1], [63, pull, 0, 1], [80, pull, 0, 1], [86, pull, 0, 0], [86.1, START, 0, 0], [93, START, 0, 0], [98, START, 0, 1], [100, START, 0, 1]);
  return { rows, snap, pull, maxLift: Math.max(...rows.map(r => r[2])) };
}

export function snapDemo() {
  const { rows, maxLift } = timeline();
  const snapPct = rows.find((r, i) => i && rows[i - 1][2] > 0 && r[2] <= 0)[0];
  const pts = poly => poly.map(p => p.join(' ')).join(' L');
  const svg = `<svg class="snap-demo" viewBox="0 0 440 240" role="img" aria-label="Animated cantilever snap fit: the mating part slides in, its catch lifts the arm's hook over the lead-in, the hook drops in behind the catch and holds when the part is pulled back">
<rect x="20" y="40" width="46" height="150" rx="6" fill="#254952" opacity=".85"/>
<g class="catch"><path d="M${pts(PLATE)} Z" fill="#254952" opacity=".55"/><path d="M${pts(RIB)} Z" fill="#bd3a12"/></g>
<g class="arm"><path d="M${pts(ARM)} Z" fill="#fffdf5" stroke="#173d3c" stroke-width="2.5" stroke-linejoin="round"/>
<circle class="root" cx="${ROOT[0] + 4}" cy="${ROOT[1]}" r="7" fill="#2e9d5b"/></g>
<g class="click"><text x="296" y="84" text-anchor="middle" font-family="JetBrains Mono, monospace" font-size="15" font-weight="700" fill="#bd3a12">click!</text></g>
</svg>`;
  const kf = (name, fn) => `@keyframes ${name}{${rows.map(r => `${f(r[0], 2)}%{${fn(r)}}`).join('')}}`;
  const css = `/* Generated by tools/snap-demo.mjs from the demo geometry: do not edit by hand. */
${kf('snap-catch', r => `transform:translateX(${f(r[1])}px);opacity:${r[3]}`)}
${kf('snap-arm', r => `transform:rotate(${f(-r[2], 3)}deg)`)}
${kf('snap-strain', r => `fill:${mix('#2e9d5b', '#d39a1c', Math.max(0, r[2]) / maxLift)}`)}
@keyframes snap-click{0%,${f(snapPct - 0.3)}%{opacity:0;transform:scale(.6)}${f(snapPct + 1.5)}%{opacity:1;transform:scale(1.1)}${f(snapPct + 14)}%,100%{opacity:0;transform:scale(1)}}
.snap-demo .catch{animation:snap-catch 5.2s linear infinite}
.snap-demo .arm{transform-origin:${ROOT[0]}px ${ROOT[1]}px;transform-box:view-box;animation:snap-arm 5.2s linear infinite}
.snap-demo .root{animation:snap-strain 5.2s linear infinite}
.snap-demo .click{transform-origin:296px 80px;transform-box:view-box;opacity:0;animation:snap-click 5.2s ease-out infinite}
@media(prefers-reduced-motion:reduce){.snap-demo .catch,.snap-demo .arm,.snap-demo .root,.snap-demo .click{animation:none}}
`;
  return { svg, css };
}
