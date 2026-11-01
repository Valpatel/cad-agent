/** Browser port of cadagent.formulas: exactly the functions the kit's demos need, nothing more. No dependencies.
 *
 *   import { snapArm, cantileverShape, fourbarAngles } from '/kit/formulas.js';
 *   snapArm(0.020, 0.0016, 0.006, 0.0015, 2.703e9, 0.02, 1);   // SI: m, Pa, strain as a fraction
 *   fourbarAngles(40, 120, 80, 100, 40 * Math.PI / 180);       // [theta3, theta4] in rad, or null
 *   fanOperatingPoint([[0, 83], [0.0548, 0]], 1.5e4);          // flow m^3/s, pressure Pa, stable, stall
 *
 * The Python package is the reference. tests/webkit-formulas.test.mjs runs every function here on the golden vectors
 * that tools/formula_vectors.py writes from the Python, so the two agree to 1e-12. Change the Python first, then
 * this file, then regenerate the vectors. Units, limits and sources are documented on the Python functions
 * (cadagent/formulas/beams.py, linkages.py and thermal.py) and in docs/formulas.md.
 *
 * In short: Euler-Bernoulli small-deflection beam theory. The snap-fit functions use the Covestro (Bayer) guide's
 * Table 1 factors, as `cad-agent snapfit` does. A closed form is not proof of strength: print a coupon and measure.
 * The four-bar functions are position analysis of rigid links on ideal pins (Norton's Design of Machinery, after
 * Freudenstein): no velocity, force, dynamics or joint clearance. The fan functions match a fan curve (the datasheet's
 * points joined by straight lines) to a system curve r Q + k Q^2 at one air density (White's Fluid Mechanics,
 * Section 11.5): steady flow, identical fans, no interaction losses.
 */

// Covestro Table 1, rectangular section: y = k eps l^2 / h (1 constant, 2 thickness to h/2, 3 width to b/4).
export const DESIGN_K_RECT = Object.freeze({ 1: 0.67, 2: 1.09, 3: 0.86 });
export const DESIGNS = Object.freeze({ 1: 'constant section', 2: 'thickness tapered to h/2 at the tip', 3: 'width tapered to b/4 at the tip' });
export const SMALL_DEFLECTION = 0.1;
const THICKNESS_TIP_RATIO = 0.5, WIDTH_TIP_RATIO = 0.25;

// A whole number that names a design, as the Python's `design in DESIGNS` (so "2", 2.5 and inherited keys such as
// "toString" are refused).
const design = d => {
  if (!Number.isInteger(d) || !Object.hasOwn(DESIGN_K_RECT, d)) throw new RangeError(`design must be 1, 2 or 3, not ${d}`);
  return d;
};
const unit = xi => {
  if (!(xi >= 0 && xi <= 1)) throw new RangeError('xi must be between 0 (root) and 1 (tip)');
  return xi;
};

/** Root strain of a rectangular snap arm deflected at the hook: eps = y h / (k L^2). */
export function snapRootStrain(length, thickness, deflection, d = 1) {
  return deflection / (DESIGN_K_RECT[design(d)] * length ** 2 / thickness);
}

/** Force that deflects a rectangular arm to a root strain: P = (b h^2 / 6) Es eps / L. */
export function snapDeflectionForce(length, width, thickness, strain, modulus) {
  return width * thickness ** 3 / 12 / (thickness / 2) * modulus * strain / length;
}

/** One rectangular snap arm: strain, force (N), stiffness (N/m, the same at any deflection), ratio to the allowable,
 * pass, small deflection, and the permissible deflection at the allowable strain (m). */
export function snapArm(length, thickness, width, deflection, modulus, allowableStrain, d = 1) {
  const strain = snapRootStrain(length, thickness, deflection, d);
  const force = snapDeflectionForce(length, width, thickness, strain, modulus);
  // P / y = b h^3 Es / (6 k L^3) whatever the deflection: the force at a unit deflection, so an arm at rest has one
  const stiffness = snapDeflectionForce(length, width, thickness, snapRootStrain(length, thickness, 1, d), modulus);
  return {
    strain, force, stiffness, ratio: strain / allowableStrain,
    passes: strain <= allowableStrain, smallDeflection: deflection <= SMALL_DEFLECTION * length,
    permissibleDeflection: DESIGN_K_RECT[design(d)] * allowableStrain * length ** 2 / (2 * (thickness / 2)),
  };
}

// Closed-form integrals of y'' = M / E I(x) for an end load (see beams.py): zero deflection and slope at the root.
function shape2(xi) {
  const r = THICKNESS_TIP_RATIO, s = 1 - (1 - r) * xi;
  return ((r - 1) - (r / 2 - 1) * s - Math.log(s) - r / (2 * s)) / (1 - r) ** 3;
}
function shape3(xi) {
  const beta = 1 - WIDTH_TIP_RATIO, u = 1 - beta * xi;
  const integralLog = -(u / beta) * (Math.log(u) - 1) - 1 / beta;
  return xi * xi / (2 * beta) - (beta - 1) / beta ** 2 * integralLog;
}
const rawShape = (xi, d) => d === 1 ? xi * xi * (3 - xi) / 6 : d === 2 ? shape2(xi) : shape3(xi);

/** Deflected shape of an end-loaded cantilever over its tip deflection, xi = x / L from the root. */
export function cantileverShape(xi, d = 1) {
  d = design(d);
  return rawShape(unit(xi), d) / rawShape(1, d);
}

/** Outer-fibre strain along the arm over the root strain. */
export function cantileverStrainProfile(xi, d = 1) {
  d = design(d); unit(xi);
  if (d === 1) return 1 - xi;
  if (d === 2) return (1 - xi) / (1 - (1 - THICKNESS_TIP_RATIO) * xi) ** 2;
  return (1 - xi) / (1 - (1 - WIDTH_TIP_RATIO) * xi);
}

/** Thickness along the arm over the root thickness (design 2 tapers to 1/2). */
export function cantileverThicknessProfile(xi, d = 1) {
  return design(d) === 2 ? 1 - (1 - THICKNESS_TIP_RATIO) * xi : 1;
}

// ----------------------------------------------------------------------------- four-bar linkages (linkages.py)
// Norton's naming: a the input crank, b the coupler, c the output rocker, d the ground; any one length unit; angles in
// rad, counter-clockwise from the ground link (the input pivot to the output pivot).

// How near to closing counts as closed, as a fraction of the longest link (linkages.py, _CLOSE).
const CLOSE = 1e-12;

// Whether coupler and rocker can span the diagonal from the crank pin to the output pivot, to CLOSE of the longest
// link (linkages.py, _diagonal_closes): the diagonal's x part as a - d - 2 a sin^2(theta2 / 2), which keeps its digits.
function diagonalCloses(a, b, c, d, theta2) {
  const s = Math.sin(0.5 * theta2);
  const e = Math.hypot(a - d - 2 * a * s * s, a * Math.sin(theta2));
  const tol = CLOSE * Math.max(a, b, c, d);
  return Math.abs(b - c) - tol <= e && e <= b + c + tol;
}

// Python's math.isclose(x, y, rel_tol=1e-12)
const isClose = (x, y) => x === y || Math.abs(x - y) <= 1e-12 * Math.max(Math.abs(x), Math.abs(y));

/** Grashof class: grashof (S + L <= P + Q), kind ('grashof', 'non-grashof', 'change-point'), crankRotates (the input
 * turns fully), and inversion: a Grashof linkage named by its shortest link ('crank-rocker', 'double-crank',
 * 'rocker-crank', 'double-rocker'), else 'triple-rocker' or 'change-point'. */
export function grashof(a, b, c, d) {
  const links = [a, b, c, d].sort((x, y) => x - y);
  const sl = links[0] + links[3], pq = links[1] + links[2];
  const kind = isClose(sl, pq) ? 'change-point' : sl < pq ? 'grashof' : 'non-grashof';
  const inversion = kind === 'grashof'
    ? (links[0] === a ? 'crank-rocker' : links[0] === d ? 'double-crank' : links[0] === c ? 'rocker-crank' : 'double-rocker')
    : kind === 'non-grashof' ? 'triple-rocker' : 'change-point';
  return { grashof: kind !== 'non-grashof', kind, crankRotates: kind !== 'non-grashof' && (links[0] === a || links[0] === d), inversion };
}

/** Coupler and output angles [theta3, theta4] from the input angle, on the open branch or the crossed one, or null
 * where the links cannot close: Freudenstein's equation, solved as in linkages.py (see its comments). */
export function fourbarAngles(a, b, c, d, theta2, crossed = false) {
  const k1 = d / a, k2 = d / c, k3 = (a * a - b * b + c * c + d * d) / (2 * a * c);
  const cos2 = Math.cos(theta2), sin2 = Math.sin(theta2);
  const A = (c - d) / c * cos2 + ((a - b) * (a + b) + (c - d) ** 2) / (2 * a * c);
  const B = -2 * sin2;
  const C = k1 - (k2 + 1) * cos2 + k3;
  let disc = B * B - 4 * A * C;
  if (disc < 0) {
    if (!diagonalCloses(a, b, c, d, theta2)) return null;
    disc = 0;
  }
  const root = Math.sqrt(disc);
  const num = crossed ? -B + root : -B - root;
  const conj = crossed ? -B - root : -B + root;
  let theta4 = Math.abs(num) > Math.abs(conj) || (Math.abs(num) === Math.abs(conj) && Math.abs(A) >= Math.abs(C))
    ? 2 * Math.atan2(num, 2 * A) : 2 * Math.atan2(2 * C, conj);
  theta4 = Math.atan2(Math.sin(theta4), Math.cos(theta4));
  const theta3 = Math.atan2(c * Math.sin(theta4) - a * sin2, d + c * Math.cos(theta4) - a * cos2);
  return [theta3, theta4];
}

/** Transmission angle between coupler and rocker, rad, folded to 0..pi/2 (below about 40 degrees the linkage binds),
 * the same on both branches; null where the links cannot close. */
export function transmissionAngle(a, b, c, d, theta2) {
  let cosMu = (b * b + c * c - a * a - d * d + 2 * a * d * Math.cos(theta2)) / (2 * b * c);
  if (Math.abs(cosMu) > 1) {
    if (!diagonalCloses(a, b, c, d, theta2)) return null;
    cosMu = Math.sign(cosMu);
  }
  const mu = Math.acos(cosMu);
  return Math.min(mu, Math.PI - mu);
}

/** Where the input locks: { closes, fullTurn, folded, stretched }, the last two |theta2| in rad (0..pi) where
 * coupler and rocker fold or stretch into one line, or null where the input passes that side. The input closes for
 * folded <= |theta2| <= stretched (Norton's toggle positions, in half angles as linkages.py has them). */
export function fourbarInputLimits(a, b, c, d) {
  const tol = CLOSE * Math.max(a, b, c, d);
  const near = Math.abs(a - d), far = a + d, fold = Math.abs(b - c), stretch = b + c;
  const closes = near <= stretch + tol && fold - tol <= far;
  const toggle = span => 2 * Math.atan2(Math.sqrt(Math.max((span - near) * (span + near), 0)),
    Math.sqrt(Math.max((far - span) * (far + span), 0)));
  const folded = closes && near < fold - tol ? toggle(fold) : null;
  const stretched = closes && far > stretch + tol ? toggle(stretch) : null;
  return { closes, fullTurn: closes && folded === null && stretched === null, folded, stretched };
}

// ----------------------------------------------------------------------------- fans (thermal.py)
// SI: flow in m^3/s, pressure in Pa; a fan curve is [[Q, dp], ...] with Q increasing, joined by straight lines.

function fanPoints(curve) {
  const ok = Array.isArray(curve) && curve.length >= 2 && curve.every(pt => Array.isArray(pt) && pt.length === 2 &&
    typeof pt[0] === 'number' && typeof pt[1] === 'number' && Number.isFinite(pt[0]) && Number.isFinite(pt[1]));
  if (!ok || curve.some((pt, i) => i && !(pt[0] > curve[i - 1][0])))
    throw new RangeError('the fan curve needs at least two finite points with increasing flow');
  return curve.map(([q, p]) => [q, p]);
}
// A whole number of fans, 1 or more (thermal.py, _fan_count): true, "2" and 2.5 are refused.
function fanCount(n) {
  if (!Number.isInteger(n) || n < 1) throw new RangeError(`the number of fans must be a whole number, 1 or more, not ${n}`);
  return n;
}
const isFinitePos = x => typeof x === 'number' && Number.isFinite(x) && x > 0;
const isFiniteNonNeg = x => typeof x === 'number' && Number.isFinite(x) && x >= 0;
// Python's math.copysign(x, y), with the sign of -0
const copysign = (x, y) => (y < 0 || Object.is(y, -0) ? -Math.abs(x) : Math.abs(x));
// Python's math.isclose(x, y, rel_tol=1e-9, abs_tol=1e-15)
const sameRoot = (x, y) => x === y || Math.abs(x - y) <= Math.max(1e-9 * Math.max(Math.abs(x), Math.abs(y)), 1e-15);

/** The straight-line fan curve between shut-off pressure (Pa) and free-air flow (m^3/s). */
export function fanCurveLine(dpShutoff, qFree) {
  if (!isFinitePos(dpShutoff) || !isFinitePos(qFree)) throw new RangeError('the shut-off pressure and the free-air flow must both be above 0');
  return [[0, dpShutoff], [qFree, 0]];
}

/** Quadratic system curve through one point: k = dp / Q^2 (Pa s^2/m^6). */
export function systemCoefficient(dp, q) {
  if (!isFinitePos(q) || !isFiniteNonNeg(dp)) throw new RangeError('the system point needs a flow above 0 and a pressure drop of 0 or more');
  return dp / (q * q);
}

/** Identical fans in series: the same flow through each, pressures add (dp_n = n dp). */
export function fansInSeries(curve, count) {
  const n = fanCount(count);
  return fanPoints(curve).map(([q, p]) => [q, n * p]);
}

/** Identical fans in parallel: the same pressure across each, flows add (Q_n = n Q). */
export function fansInParallel(curve, count) {
  const n = fanCount(count);
  return fanPoints(curve).map(([q, p]) => [n * q, p]);
}

/** The flow at the stall peak (the end of the curve's last rise, and of a flat top after it): below it an axial fan
 * runs stalled. null when the pressure never rises with flow. */
export function fanStallFlow(curve) {
  const pts = fanPoints(curve);
  let last = -1;
  for (let i = 0; i + 1 < pts.length; i++) if (pts[i + 1][1] > pts[i][1]) last = i;
  if (last < 0) return null;
  let j = last + 1;
  while (j + 1 < pts.length && pts[j + 1][1] === pts[j][1]) j++;
  return pts[j][0];
}

/** Where the fan curve meets the system dp = r Q + k Q^2, solved exactly on each straight segment (thermal.py):
 * { flow, pressure, intersections (every crossing [Q, dp], low flow first), stable (one crossing), stall (below the
 * stall peak) }. The operating point is the highest-flow crossing. */
export function fanOperatingPoint(curve, k, r = 0) {
  const pts = fanPoints(curve);
  if (!isFiniteNonNeg(k) || !isFiniteNonNeg(r) || (k === 0 && r === 0)) throw new RangeError('the system needs a positive loss: k > 0 or r > 0');
  const found = [];
  for (let i = 0; i + 1 < pts.length; i++) {
    const [q1, p1] = pts[i], [q2, p2] = pts[i + 1];
    const s = (p2 - p1) / (q2 - q1);
    const qa = k, qb = r - s, qc = -(p1 - s * q1);
    let roots;
    if (qa === 0) roots = qb ? [-qc / qb] : [];
    else {
      const disc = qb * qb - 4 * qa * qc;
      if (disc < 0) continue;
      const sq = Math.sqrt(disc);
      const t = -0.5 * (qb + copysign(sq, qb));
      roots = t ? [t / qa, qc / t] : [-qb / (2 * qa)];
    }
    for (let q of roots) {
      if (q1 - 1e-12 * q2 <= q && q <= q2 * (1 + 1e-12) && q >= 0) {
        q = Math.min(Math.max(q, q1), q2);
        if (!found.some(([f]) => sameRoot(q, f))) found.push([q, r * q + k * q * q]);
      }
    }
  }
  if (!found.length) throw new RangeError("the fan and system curves do not cross within the fan curve's points");
  found.sort((a, b) => a[0] - b[0] || a[1] - b[1]);
  const [q, p] = found.at(-1), peak = fanStallFlow(pts);
  return { flow: q, pressure: p, intersections: found, stable: found.length === 1, stall: peak !== null && q < peak };
}
