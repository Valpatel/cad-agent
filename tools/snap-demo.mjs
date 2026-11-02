/** The landing page's cantilever snap-fit animation, computed from its geometry instead of keyframed by eye.
 *
 * The arm (with its hook) is fixed to the wall and pivots about its root; the mating part (a plate with a catch rib)
 * slides in from the right. For every sampled position of the mating part the arm's lift is the smallest rotation
 * at which the two outlines do not overlap, so the hook rides the catch's lead-in, slides over its top, drops in behind
 * its retaining face and holds when the part is pulled back. Rigid rotation about the root stands in for bending:
 * it is a picture of the motion, not a deflection result (`cad-agent snapfit` does the sizing).
 * Coordinates are SVG user units, y down. tests/site/website-snap-demo.test.mjs checks contact, engagement and the lock.
 *
 * Why the retaining faces lean: the hook hangs below the arm's pivot, so a square (vertical) face pushed by a
 * pull-back has a lever arm about the root and turns the arm upward: the joint would hold only by friction.
 * Both faces are undercut past the hook's arc of motion (UNDERCUT_DEG > ARC_DEG), so the contact force's line of
 * action passes above the root (y ≈ 98 to 113 at the root's x, against the root's 121) and drives the hook deeper
 * instead (`lockMoment` > 0 over the whole contact). The margin over the arc is 4° at mid-contact, about 2° at the
 * hook tip and 6° at the top of the rib.
 */
export const ROOT = [64, 121];
const TIP_Y = 154, RIB_TOP = 140, FACE_X = 282, PLAY = 2;
// Direction of the hook's arc at the middle of the contact, measured from vertical; the faces lean 4° past it.
export const ARC_DEG = Math.atan2((TIP_Y + RIB_TOP) / 2 - ROOT[1], FACE_X - ROOT[0]) * 180 / Math.PI;
export const UNDERCUT_DEG = ARC_DEG + 4;
const lean = Math.tan(UNDERCUT_DEG * Math.PI / 180);
const hookFaceX = y => FACE_X + (TIP_Y - y) * lean, ribFaceX = y => FACE_X - PLAY + (TIP_Y - y) * lean;
// Arm outline at rest: top edge, end face, hook lead-in ramp (faces the incoming catch), hook tip, retaining face
// (faces the wall, undercut), underside back to the root.
export const ARM = [[64, 100], [318, 110], [318, 132], [290, TIP_Y], [FACE_X, TIP_Y], [hookFaceX(132), 132], [64, 142]];
// Catch rib on the mating plate, engaged position: lead-in chamfer on the leading (left) side, undercut retaining
// face on the right, PLAY units from the hook's.
export const RIB = [[246, 176], [246, 160], [266, RIB_TOP], [ribFaceX(RIB_TOP), RIB_TOP], [ribFaceX(176), 176]];
export const PLATE = [[206, 176], [620, 176], [620, 190], [206, 190]];
export const PARTS = { arm: ARM, rib: RIB, plate: PLATE };
export const START = 120;              // mating part offset (+x) before insertion
const MAX_LIFT = 12;                   // degrees; the search bracket
const GAP = 0.02;                      // degrees the animated hook rides above contact (≈0.08 units): drawn touching

const rotate = ([x, y], liftDeg) => {   // lift > 0 raises the free end (counter-clockwise on screen)
  const a = -liftDeg * Math.PI / 180, [cx, cy] = ROOT;
  return [cx + (x - cx) * Math.cos(a) - (y - cy) * Math.sin(a), cy + (x - cx) * Math.sin(a) + (y - cy) * Math.cos(a)];
};
export const armAt = (lift, arm = ARM) => arm.map(p => rotate(p, lift));
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
export const clear = (lift, offset, parts = PARTS) => {
  const arm = armAt(lift, parts.arm);
  return !overlap(arm, shift(parts.rib, offset)) && !overlap(arm, shift(parts.plate, offset));
};
/** How low (degrees) the arm can come down onto the mating part at this offset, swinging from above: the lowest
 * lift whose whole path up to MAX_LIFT is clear. (The lowest clear lift is not enough: just after the hook passes
 * the catch's corner, rest is clear but the swing down to it is not, so the hook still rides the corner.) */
export function liftAt(offset, parts = PARTS) {
  const STEP = 0.05;
  if (!clear(MAX_LIFT, offset, parts)) throw new Error(`snap demo: no clearance at offset ${offset}`);
  let hi = MAX_LIFT;
  while (hi > 0 && clear(Math.max(0, hi - STEP), offset, parts)) hi = Math.max(0, hi - STEP);
  if (hi === 0) return 0;
  let lo = Math.max(0, hi - STEP);
  for (let i = 0; i < 40; i++) { const mid = (lo + hi) / 2; (clear(mid, offset, parts) ? (hi = mid) : (lo = mid)); }
  return hi;
}
/** Moment about the root of a frictionless pull-back contact force on the hook, per unit force, at the worst point
 * of the retaining-face contact (rib top to hook tip). Positive turns the free end down, into the catch: the joint
 * locks without friction. The rib's retaining face is its edge facing +x. */
export function lockMoment(rib = RIB) {
  const edges = rib.map((p, i) => [p, rib[(i + 1) % rib.length]]);
  const [a, b] = edges.reduce((best, e) => (e[0][0] + e[1][0] > best[0][0] + best[1][0] ? e : best));
  const [dx, dy] = [b[0] - a[0], b[1] - a[1]], len = Math.hypot(dx, dy);
  let n = [dy / len, -dx / len];                       // a normal of the face; point it out of the rib (+x)
  if (n[0] < 0) n = [-n[0], -n[1]];
  const top = Math.min(...rib.map(p => p[1])), tip = Math.max(...ARM.map(p => p[1]));
  let worst = Infinity;
  for (let y = top; y <= tip + 1e-9; y += (tip - top) / 20) {
    const x = a[0] + (y - a[1]) / dy * dx;              // contact point on the face at this height
    worst = Math.min(worst, (x - ROOT[0]) * n[1] - (y - ROOT[1]) * n[0]);   // r × F, y down: > 0 turns clockwise
  }
  return worst;
}
/** Offset at which the hook drops in: below it the arm is at rest, just above it the arm is lifted. */
export function snapOffset() {
  let lo = 0, hi = 30;                  // lift(lo) = 0, lift(hi) > 0
  for (let i = 0; i < 50; i++) { const mid = (lo + hi) / 2; (liftAt(mid) > 0 ? (hi = mid) : (lo = mid)); }
  return hi;
}
/** How far the engaged part can be pulled back before the retaining faces meet. */
export function pullStop(parts = PARTS) {
  let hi = 0;
  while (clear(0, hi, parts)) { hi += 0.25; if (hi > START) throw new Error('snap demo: the catch never meets the hook'); }
  let lo = hi - 0.25;
  for (let i = 0; i < 50; i++) { const mid = (lo + hi) / 2; (clear(0, mid, parts) ? (lo = mid) : (hi = mid)); }
  return lo;
}
/** CSS interpolates each keyframe pair linearly: add computed frames until every in-between pose is clear too. */
export function densify(rows, steps = 16) {
  const out = [rows[0]];
  const lerp = (a, b, t) => a.map((v, i) => v + (b[i] - v) * t);
  const fill = (a, b, depth) => {
    const bad = Array.from({ length: steps - 1 }, (_, i) => lerp(a, b, (i + 1) / steps)).some(r => !clear(r[2], r[1]));
    if (bad && depth < 8) {
      const m = lerp(a, b, 0.5);
      m[2] = Math.max(m[2], liftAt(m[1]) + (liftAt(m[1]) > 0 ? GAP : 0));
      fill(a, m, depth + 1); out.push(m); fill(m, b, depth + 1);
    }
  };
  for (let i = 1; i < rows.length; i++) {           // the reset jump happens while the part is invisible
    if (rows[i - 1][3] || rows[i][3]) fill(rows[i - 1], rows[i], 0);
    out.push(rows[i]);
  }
  return out;
}

const ease = u => u < .5 ? 4 * u * u * u : 1 - (-2 * u + 2) ** 3 / 2;
const f = (n, d = 2) => Number(n.toFixed(d));
const mix = (a, b, t) => '#' + [0, 2, 4].map(i => Math.round(parseInt(a.slice(1 + i, 3 + i), 16) * (1 - t) + parseInt(b.slice(1 + i, 3 + i), 16) * t)
  .toString(16).padStart(2, '0')).join('');

/** Timeline samples: [percent, offset, lift, catchOpacity]. One loop: wait, insert (contact computed), snap, hold,
 * pull back to contact with the retaining face (computed), hold, fade out, reset, fade in. Drawn, not computed:
 * the timing, and a small overshoot past rest after the drop (checked clear). */
export function timeline() {
  const rows = [[0, START, 0, 1], [8, START, 0, 1]];
  const snap = snapOffset(), pull = Math.floor(pullStop() * 100) / 100 - 0.01;   // stays clear once rounded
  let snapped = false;
  for (let k = 1; k <= 84; k++) {      // insertion: 8 % → 50 %
    const pct = 8 + k * 0.5, offset = START * (1 - ease(k / 84));
    if (!snapped && offset < snap) {   // the hook drops in: a quick fall with a small overshoot, then rest
      snapped = true;
      // In two moves, at offsets that survive rounding to 2 places: slide past the corner at the corner's full lift,
      // then fall where the whole swing is clear. Falling while still moving across the corner would cut into it.
      const above = Math.ceil((snap + 1e-3) * 100) / 100, below = Math.floor((snap - 0.01) * 100) / 100;
      const top = Math.max(liftAt(above), liftAt(snap + 1e-4)) + GAP, at = Math.min(offset, below);
      let overshoot = -0.4;            // as far past rest as the parts allow
      while (overshoot < 0 && !clear(overshoot, at)) overshoot = Math.min(0, overshoot + 0.05);
      rows.push([pct - 0.25, above, top, 1], [pct - 0.1, below, top, 1], [pct + 0.6, at, overshoot, 1], [pct + 1.4, at, 0.15, 1], [pct + 2.2, at, 0, 1]);
      continue;
    }
    if (snapped && rows.at(-1)[0] >= pct) continue;
    const lift = snapped ? 0 : liftAt(offset);
    rows.push([pct, offset, lift > 0 ? lift + GAP : 0, 1]);
  }
  rows.push([60, 0, 0, 1], [63, pull, 0, 1], [80, pull, 0, 1], [86, pull, 0, 0], [86.1, START, 0, 0], [93, START, 0, 0], [98, START, 0, 1], [100, START, 0, 1]);
  // The rows are returned as the CSS will carry them (percent to 3 places, offset to 2, lift rounded up to 3, which
  // only lifts the hook clear of contact), so the tests check exactly what the browser draws.
  const all = densify(rows).map(r => [f(r[0], 3), f(r[1]), Math.ceil(r[2] * 1000 - 1e-9) / 1000, r[3]]);
  return { rows: all, snap, pull, maxLift: Math.max(...all.map(r => r[2])) };
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
  const kf = (name, fn) => `@keyframes ${name}{${rows.map(r => `${r[0]}%{${fn(r)}}`).join('')}}`;
  const css = `/* Generated by tools/snap-demo.mjs from the demo geometry: do not edit by hand. */
${kf('snap-catch', r => `transform:translateX(${r[1]}px);opacity:${r[3]}`)}
${kf('snap-arm', r => `transform:rotate(${-r[2] || 0}deg)`)}
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
