/** Browser port of cadagent.formulas: exactly the functions the kit's demos need, nothing more. No dependencies.
 *
 *   import { snapArm, cantileverShape, fourbarAngles } from '/kit/formulas.js';
 *   snapArm(0.020, 0.0016, 0.006, 0.0015, 2.703e9, 0.02, 1);   // SI: m, Pa, strain as a fraction
 *   fourbarAngles(40, 120, 80, 100, 40 * Math.PI / 180);       // [theta3, theta4] in rad, or null
 *
 * The Python package is the reference. tests/webkit-formulas.test.mjs runs every function here on the golden vectors
 * that tools/formula_vectors.py writes from the Python, so the two agree to 1e-12. Change the Python first, then
 * this file, then regenerate the vectors. Units, limits and sources are documented on the Python functions
 * (cadagent/formulas/beams.py and linkages.py) and in docs/formulas.md.
 *
 * In short: Euler-Bernoulli small-deflection beam theory. The snap-fit functions use the Covestro (Bayer) guide's
 * Table 1 factors, as `cad-agent snapfit` does. A closed form is not proof of strength: print a coupon and measure.
 * The four-bar functions are position analysis of rigid links on ideal pins (Norton's Design of Machinery, after
 * Freudenstein): no velocity, force, dynamics or joint clearance.
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
