/** Browser port of cadagent.formulas: exactly the functions the kit's demos need, nothing more. No dependencies.
 *
 *   import { snapArm, cantileverShape } from '/kit/formulas.js';
 *   snapArm(0.020, 0.0016, 0.006, 0.0015, 2.703e9, 0.02, 1);   // SI: m, Pa, strain as a fraction
 *
 * The Python package is the reference. tests/webkit-formulas.test.mjs runs every function here on the golden vectors
 * that tools/formula_vectors.py writes from the Python, so the two agree to 1e-12. Change the Python first, then
 * this file, then regenerate the vectors. Units, limits and sources are documented on the Python functions
 * (cadagent/formulas/beams.py) and in docs/formulas.md.
 *
 * In short: Euler-Bernoulli small-deflection beam theory. The snap-fit functions use the Covestro (Bayer) guide's
 * Table 1 factors, as `cad-agent snapfit` does. A closed form is not proof of strength: print a coupon and measure.
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
