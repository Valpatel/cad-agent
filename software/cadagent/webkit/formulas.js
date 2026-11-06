/** Browser port of cadagent.formulas: exactly the functions the kit's demos need, nothing more. No dependencies.
 *
 *   import { snapArm, cantileverShape, fourbarAngles } from '/kit/formulas.js';
 *   snapArm(0.020, 0.0016, 0.006, 0.0015, 2.703e9, 0.02, 1);   // SI: m, Pa, strain as a fraction
 *   fourbarAngles(40, 120, 80, 100, 40 * Math.PI / 180);       // [theta3, theta4] in rad, or null
 *   fanOperatingPoint([[0, 83], [0.0548, 0]], 1.5e4);          // flow m^3/s, pressure Pa, stable, stall
 *   torsionSnapBar(0.015, 0.004, 0.0012, 0.14, 2.68e9, 0.0095, 0.010, 2);   // shear strain, torque, lever force
 *   screwBoss(0.003, 0.00112, 0.006, 0.006, 0.3, 15.5e6, 35e6, 0.2, 0.65); // clamp band, strip, window, hoop
 *
 * The Python package is the reference. tests/webkit/webkit-formulas.test.mjs runs every function here on the golden vectors
 * that tools/formula_vectors.py writes from the Python, so the two agree to 1e-12. Change the Python first, then
 * this file, then regenerate the vectors. Units, limits and sources are documented on the Python functions
 * (cadagent/formulas/beams.py, linkages.py, thermal.py, torsion.py and screws.py) and in docs/formulas.md.
 *
 * In short: Euler-Bernoulli small-deflection beam theory. The snap-fit functions use the Covestro (Bayer) guide's
 * Table 1 factors, as `cad-agent snapfit` does. A closed form is not proof of strength: print a coupon and measure.
 * The four-bar functions are position analysis of rigid links on ideal pins (Norton's Design of Machinery, after
 * Freudenstein): no velocity, force, dynamics or joint clearance. The fan functions match a fan curve (the datasheet's
 * points joined by straight lines) to a system curve r Q + k Q^2 at one air density (White's Fluid Mechanics,
 * Section 11.5): steady flow, identical fans, no interaction losses. The torsion functions are Saint-Venant torsion of
 * a rectangle (Roark Table 10.1) with the Covestro guide's allowable shear strain (1 + nu) eps. The screw functions are
 * Shigley's torque-preload relation and thread statics, the ISO 68-1 stripping area and Lame's thick-walled cylinder,
 * with Covestro's tightening window and the DELTA PT maker's boss proportions.
 */

// Covestro Table 1, rectangular section: y = k eps l^2 / h (1 constant, 2 thickness to h/2, 3 width to b/4).
export const DESIGN_K_RECT = Object.freeze({ 1: 0.67, 2: 1.09, 3: 0.86 });
export const DESIGNS = Object.freeze({ 1: 'constant section', 2: 'thickness tapered to h/2 at the tip', 3: 'width tapered to b/4 at the tip' });
export const SMALL_DEFLECTION = 0.1;
/** torsionSnapBar flags a twist as large when the trapeze effect adds more than this share to the torque. */
export const SMALL_TWIST_TRAPEZE = 0.1;
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

// ----------------------------------------------------------------------------- torsion (torsion.py)
// SI: metres, pascals, radians; torque in N m.

// A finite number above 0 (or at least 0), as the Python's checks: booleans, strings and null are refused.
const isNum = x => typeof x === 'number' && Number.isFinite(x);
function positive(name, v, strict = true) {
  if (!isNum(v) || (strict ? !(v > 0) : !(v >= 0))) throw new RangeError(`${name} must be a finite number ${strict ? 'above' : 'of at least'} 0, not ${v}`);
  return v;
}
const POISSON_PLASTICS = 0.35;            // snapfit.POISSON_PLASTICS (Covestro Section C)

/** Torsion constant of a solid rectangle: K = a b^3 [16/3 - 3.36 (b/a)(1 - b^4 / 12 a^4)], a and b half the sides. */
export function torsionConstantRect(width, thickness) {
  const a = Math.max(width, thickness) / 2, b = Math.min(width, thickness) / 2;
  // products, not powers: Math.pow differs in the last bit between engines (WebKit's from V8's and CPython's)
  const b3 = b * b * b, a4 = a * a * a * a;
  return a * b3 * (16 / 3 - 3.36 * b / a * (1 - b3 * b / (12 * a4)));
}

/** Peak shear stress in a twisted solid rectangle (at the middle of the long sides): 3T / (8 a b^2) times Roark's
 * polynomial in b/a. */
export function torsionShearStressRect(torque, width, thickness) {
  const a = Math.max(width, thickness) / 2, b = Math.min(width, thickness) / 2, q = b / a;
  const q2 = q * q;
  return 3 * torque / (8 * a * b * b) * (1 + 0.6095 * q + 0.8865 * q2 - 1.8023 * q2 * q + 0.9100 * q2 * q2);
}

/** Peak shear strain of a rectangular bar twisted through `twist` over `length`: theta K (tau / T) / L. */
export function torsionShearStrainRect(twist, length, width, thickness) {
  return twist * torsionConstantRect(width, thickness) * torsionShearStressRect(1, width, thickness) / length;
}

/** Torsional stiffness of a uniform bar, T / theta = K G / L (N m / rad). */
export function torsionBarStiffness(length, shearModulus, constant) {
  return constant * shearModulus / length;
}

/** A rectangular torsion bar twisted by a lever (torsion.py, torsion_snap_bar): { shearStrain, allowableShearStrain
 * ((1 + nu) eps, the Covestro guide's), ratio, passes, shearModulus, stiffness (all bars), torque, force (at the
 * lever), travel (lever sin theta), permissibleTwist, and for large twist trapezeRatio (the trapeze effect's torque
 * over the Saint-Venant torque, E t b^5 theta'^3 / 360 over K G theta'), edgeAxialStrain (theta'^2 b^2 / 12) and
 * smallTwist }. Two bars take the same twist and double the torque. */
export function torsionSnapBar(length, width, thickness, twist, modulus, allowableStrain, lever, bars = 1, poisson = POISSON_PLASTICS) {
  for (const [name, v] of [['length', length], ['width', width], ['thickness', thickness], ['modulus', modulus],
    ['allowable_strain', allowableStrain], ['lever', lever]]) positive(name, v);
  positive('twist', twist, false);
  if (bars !== 1 && bars !== 2) throw new RangeError(`bars must be 1 or 2, not ${bars}`);
  if (!isNum(poisson) || !(poisson > -1 && poisson < 0.5)) throw new RangeError(`poisson must be between -1 and 0.5, not ${poisson}`);
  const perRadian = torsionShearStrainRect(1, length, width, thickness);
  const shearStrain = perRadian * twist;
  const allowableShearStrain = (1 + poisson) * allowableStrain;
  const shearModulus = modulus / (2 * (1 + poisson));
  const stiffness = bars * torsionBarStiffness(length, shearModulus, torsionConstantRect(width, thickness));
  const torque = stiffness * twist;
  const longSide = Math.max(width, thickness), shortSide = Math.min(width, thickness), rate = twist / length;
  const b2 = longSide * longSide;
  const trapezeRatio = modulus * shortSide * b2 * b2 * longSide * rate * rate / (360 * torsionConstantRect(width, thickness) * shearModulus);
  return { shearStrain, allowableShearStrain, ratio: shearStrain / allowableShearStrain, passes: shearStrain <= allowableShearStrain,
    shearModulus, stiffness, torque, force: torque / lever, travel: lever * Math.sin(twist), permissibleTwist: allowableShearStrain / perRadian,
    trapezeRatio, edgeAxialStrain: rate * rate * longSide * longSide / 12, smallTwist: trapezeRatio <= SMALL_TWIST_TRAPEZE };
}

// ----------------------------------------------------------------------------- screws (screws.py)
// SI: metres, newtons, pascals; torque in N m; flank angles in rad (the included angle: 60 degrees ISO).

const PITCH_DIAMETER = 0.649519, MINOR_DIAMETER = 1.082532;      // ISO 68-1 basic profile
const DEG = Math.PI / 180;                                        // Python's math.radians multiplies by pi / 180
const ISO_FLANK = 60 * DEG;
/** Boss proportions over the nominal diameter (Bulten, DELTA PT, p. 7) and Covestro's tightening window. */
export const BOSS = Object.freeze({ hole: 0.8, outside: 2.0, engagement: 2.0, tightenOverDrive: 1.2, tightenOverStrip: 0.5 });
const FORMING_FLANK = 30 * DEG, RATIO_SLACK = 1e-9;

/** Nut factor from friction: K = (dm / 2d)(tan lambda + f sec alpha) / (1 - f tan lambda sec alpha) + 0.625 fc. */
export function nutFactor(diameter, pitch, threadFriction, collarFriction, flankAngle = ISO_FLANK) {
  if (!isNum(flankAngle) || !(flankAngle > 0 && flankAngle < Math.PI / 2)) throw new RangeError(`flank_angle is the included angle in radians, between 0 and pi/2, not ${flankAngle}`);
  const dm = diameter - PITCH_DIAMETER * pitch;
  const tanLead = pitch / (Math.PI * dm);
  const sec = 1 / Math.cos(flankAngle / 2);
  const thread = dm / (2 * diameter) * (tanLead + threadFriction * sec) / (1 - threadFriction * tanLead * sec);
  return thread + 0.625 * collarFriction;
}

/** Clamp force from tightening torque, Fi = T / (K d). */
export function preloadFromTorque(torque, diameter, k = 0.2) { return torque / (k * diameter); }

/** Tightening torque for a clamp force, T = K Fi d. */
export function torqueForPreload(preload, diameter, k = 0.2) { return k * preload * diameter; }

/** Shear areas that strip a thread: { external: 0.75 pi D1 Le, internal: 0.875 pi d Le }. */
export function threadShearAreas(diameter, pitch, engagement) {
  const d1 = diameter - MINOR_DIAMETER * pitch;
  return { external: 0.75 * Math.PI * d1 * engagement, internal: 0.875 * Math.PI * diameter * engagement };
}

/** The force that strips one side of a thread: its shear area times the shear strength. */
export function threadStripForce(diameter, pitch, engagement, shearStrength, side = 'internal') {
  const areas = threadShearAreas(diameter, pitch, engagement);
  if (side !== 'internal' && side !== 'external') throw new RangeError("side must be 'internal' or 'external'");
  return areas[side] * shearStrength;
}

/** The radial pressure an axially loaded thread puts on the boss: p = F tan(alpha) / (pi d Le). */
export function threadRadialPressure(load, diameter, engagement, flankAngle = ISO_FLANK) {
  positive('load', load, false); positive('diameter', diameter); positive('engagement', engagement);
  if (!isNum(flankAngle) || !(flankAngle > 0 && flankAngle < Math.PI)) throw new RangeError(`flank_angle must be between 0 and pi radians, not ${flankAngle}`);
  return load * Math.tan(flankAngle / 2) / (Math.PI * diameter * engagement);
}

/** Hoop stress at the bore of a thick-walled cylinder under internal pressure: p (D^2 + d^2) / (D^2 - d^2). */
export function bossHoopStress(pressure, innerDiameter, outerDiameter) {
  positive('pressure', pressure, false); positive('inner_diameter', innerDiameter);
  if (!isNum(outerDiameter) || !(outerDiameter > innerDiameter)) throw new RangeError(`outer_diameter must be finite and above the inner diameter, not ${outerDiameter}`);
  const d2 = innerDiameter * innerDiameter, o2 = outerDiameter * outerDiameter;
  return pressure * (o2 + d2) / (o2 - d2);
}

/** A thread-forming screw tightened in a plastic boss (screws.py, screw_boss): { nutFactor, preload, stripTorque as
 * {low, high}; stripForce, margin {low, high}, torqueCeiling, driveTorqueLimit, driveTorque, radialPressure,
 * hoopStress, hoopRatio, outsideRatio, engagementRatio, torqueOk, outsideOk, engagementOk, hoopOk, passes }. The drive
 * torque forms the thread and makes no clamp: measured, it comes off the torque and adds to the stripping torque; not
 * measured (null), the clamp band runs from the most drive torque the window allows (T / 1.2) to none, and the
 * stripping torque is the clamp's share alone. */
export function screwBoss(diameter, pitch, engagement, outsideDiameter, torque, shearStrength, hoopStrength,
  frictionLow = 0.2, frictionHigh = 0.5, flankAngle = FORMING_FLANK, driveTorque = null) {
  for (const [name, v] of [['diameter', diameter], ['pitch', pitch], ['engagement', engagement], ['torque', torque],
    ['shear_strength', shearStrength], ['hoop_strength', hoopStrength]]) positive(name, v);
  positive('friction_low', frictionLow, false);
  if (!isNum(frictionHigh) || !(frictionHigh >= frictionLow)) throw new RangeError(`friction_high must be finite and at least friction_low, not ${frictionHigh}`);
  if (!isNum(outsideDiameter) || !(outsideDiameter > diameter)) throw new RangeError(`outside_diameter must be finite and above the screw's diameter, not ${outsideDiameter}`);
  if (driveTorque !== null) positive('drive_torque', driveTorque, false);
  const kLow = nutFactor(diameter, pitch, frictionLow, frictionLow, flankAngle);
  const kHigh = nutFactor(diameter, pitch, frictionHigh, frictionHigh, flankAngle);
  const strip = threadStripForce(diameter, pitch, engagement, shearStrength, 'internal');
  const drive = driveTorque === null ? 0 : driveTorque;
  const driveMost = driveTorque === null ? torque / BOSS.tightenOverDrive : driveTorque;
  const stripLow = drive + torqueForPreload(strip, diameter, kLow), stripHigh = drive + torqueForPreload(strip, diameter, kHigh);
  const preloadHigh = preloadFromTorque(Math.max(torque - drive, 0), diameter, kLow);
  const pressure = threadRadialPressure(preloadHigh, diameter, engagement, flankAngle);
  const hoop = bossHoopStress(pressure, diameter, outsideDiameter);
  const ceiling = BOSS.tightenOverStrip * stripLow;
  const out = { nutFactor: { low: kLow, high: kHigh },
    preload: { low: preloadFromTorque(Math.max(torque - driveMost, 0), diameter, kHigh), high: preloadHigh },
    stripForce: strip, stripTorque: { low: stripLow, high: stripHigh },
    margin: { low: stripLow / torque, high: stripHigh / torque },
    torqueCeiling: ceiling, driveTorqueLimit: torque / BOSS.tightenOverDrive, driveTorque,
    radialPressure: pressure, hoopStress: hoop, hoopRatio: hoop / hoopStrength,
    outsideRatio: outsideDiameter / diameter, engagementRatio: engagement / diameter };
  out.torqueOk = torque <= ceiling && (driveTorque === null || torque >= BOSS.tightenOverDrive * driveTorque);
  out.outsideOk = out.outsideRatio >= BOSS.outside * (1 - RATIO_SLACK);
  out.engagementOk = out.engagementRatio >= BOSS.engagement * (1 - RATIO_SLACK);
  out.hoopOk = out.hoopRatio < 1;
  out.passes = out.torqueOk && out.outsideOk && out.engagementOk && out.hoopOk;
  return out;
}
