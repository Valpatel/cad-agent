/** Original, unit-explicit local equipment equations. No engine/UI dependency. */

const finite = (value, name, minimum = -Infinity, maximum = Infinity) => {
  if (typeof value !== 'number' || !Number.isFinite(value) || value < minimum || value > maximum) {
    throw new RangeError(`${name} must be a finite number in [${minimum}, ${maximum}].`);
  }
  return value;
};
const positive = (value, name) => {
  finite(value, name, 0);
  if (value === 0) throw new RangeError(`${name} must be positive.`);
  return value;
};
const efficiency = (value, name) => positive(finite(value, name, 0, 1), name);

function pumpInputs(input, curve) {
  if (!input || typeof input !== 'object' || Array.isArray(input)) throw new TypeError('Pump inputs must be an object.');
  const enabled = input.enabled ?? true;
  if (typeof enabled !== 'boolean') throw new TypeError('enabled must be boolean.');
  // Validate configuration even when disabled or at zero speed.
  const p = {
    enabled,
    speedRatio: finite(input.speedRatio, 'speedRatio', 0),
    shutoffHeadM: positive(input.shutoffHeadM, 'shutoffHeadM'),
    staticHeadM: finite(input.staticHeadM, 'staticHeadM', 0),
    systemResistanceS2M5: finite(input.systemResistanceS2M5, 'systemResistanceS2M5', 0),
    densityKgM3: positive(input.densityKgM3, 'densityKgM3'),
    gravityMS2: positive(input.gravityMS2, 'gravityMS2'),
    pumpEfficiency: efficiency(input.pumpEfficiency, 'pumpEfficiency'),
    motorEfficiency: efficiency(input.motorEfficiency, 'motorEfficiency'),
    driveEfficiency: efficiency(input.driveEfficiency, 'driveEfficiency'),
    idlePowerW: finite(input.idlePowerW, 'idlePowerW', 0),
  };
  if (curve === 'quadratic') p.quadraticResistanceS2M5 = positive(input.quadraticResistanceS2M5, 'quadraticResistanceS2M5');
  else p.linearResistanceSM2 = positive(input.linearResistanceSM2, 'linearResistanceSM2');
  return p;
}

function pumpResult(p, flowM3s, headM, blocked) {
  const pressurePa = finite(p.densityKgM3 * p.gravityMS2 * headM, 'pressurePa', 0);
  const hydraulicPowerW = finite(pressurePa * flowM3s, 'hydraulicPowerW', 0);
  const shaftPowerW = finite(hydraulicPowerW / p.pumpEfficiency, 'shaftPowerW', 0);
  const electricalPowerW = finite(shaftPowerW / (p.motorEfficiency * p.driveEfficiency)
    + (p.enabled && p.speedRatio > 0 ? p.idlePowerW : 0), 'electricalPowerW', 0);
  return Object.freeze({flowM3s, headM, pressurePa, hydraulicPowerW, shaftPowerW,
    electricalPowerW, systemHeadM: finite(p.staticHeadM + p.systemResistanceS2M5 * flowM3s ** 2, 'systemHeadM', 0),
    blocked, speedRatio: p.enabled ? p.speedRatio : 0});
}

/** H(Q,s)=H0*s²-a*Q² intersects Hstatic+R*Q². Q is m³/s; H is m. */
export function solveQuadraticPump(input) {
  const p = pumpInputs(input, 'quadratic');
  const shutoff = finite(p.shutoffHeadM * p.speedRatio ** 2, 'scaled shutoff head', 0);
  const denominator = positive(finite(p.quadraticResistanceS2M5 + p.systemResistanceS2M5, 'combined curve resistance', 0), 'combined curve resistance');
  if (!p.enabled || p.speedRatio === 0) return pumpResult(p, 0, 0, false);
  const available = finite(shutoff - p.staticHeadM, 'available head');
  if (available <= 0) return pumpResult(p, 0, shutoff, true);
  const flow = finite(Math.sqrt(available / denominator), 'flowM3s', 0);
  return pumpResult(p, flow, finite(p.staticHeadM + p.systemResistanceS2M5 * flow ** 2, 'headM', 0), false);
}

/** Nominal H(Q)=H0-bQ scaled by affinity: H(Q,s)=H0*s²-b*s*Q. */
export function solveLinearPump(input) {
  const p = pumpInputs(input, 'linear');
  const shutoff = finite(p.shutoffHeadM * p.speedRatio ** 2, 'scaled shutoff head', 0);
  if (!p.enabled || p.speedRatio === 0) return pumpResult(p, 0, 0, false);
  const available = finite(shutoff - p.staticHeadM, 'available head');
  if (available <= 0) return pumpResult(p, 0, shutoff, true);
  const slope = positive(finite(p.linearResistanceSM2 * p.speedRatio, 'scaled linear resistance', 0), 'scaled linear resistance');
  const root = p.systemResistanceS2M5 === 0 ? available / slope
    : 2 * available / (slope + Math.hypot(slope, 2 * Math.sqrt(p.systemResistanceS2M5) * Math.sqrt(available)));
  const flow = finite(root, 'flowM3s', 0);
  if (available > 0 && flow === 0) throw new RangeError('Operating point is outside the supported numeric range.');
  return pumpResult(p, flow, finite(p.staticHeadM + p.systemResistanceS2M5 * flow ** 2, 'headM', 0), false);
}

/** Develop head and power at an imposed forward flow, e.g. an allocated budget.
 * This is the pump curve at Q, not a second assertion that the system curve balances.
 */
export function pumpAtFlow(curve, input, flowM3s) {
  if (!['linear', 'quadratic'].includes(curve)) throw new RangeError('Unknown pump curve.');
  const p = pumpInputs(input, curve);
  finite(flowM3s, 'flowM3s', 0);
  if (!p.enabled || p.speedRatio === 0) {
    if (flowM3s !== 0) throw new RangeError('A stopped pump cannot supply positive forward flow in this check-valve model.');
    return pumpResult(p, 0, 0, false);
  }
  const shutoff = finite(p.shutoffHeadM * p.speedRatio ** 2, 'scaled shutoff head', 0);
  const reduction = curve === 'quadratic' ? p.quadraticResistanceS2M5 * flowM3s ** 2 : p.linearResistanceSM2 * p.speedRatio * flowM3s;
  const head = finite(shutoff - finite(reduction, 'curve head reduction', 0), 'curve head');
  if (head < -Math.max(1, shutoff) * 1e-12) throw new RangeError('Forward flow lies beyond the nonnegative-head pump curve.');
  return pumpResult(p, flowM3s, Math.max(0, head), flowM3s === 0);
}

/** Conservative electrical rating over 0 <= Q <= the local operating point.
 * A throttled centrifugal pump can draw MORE power than at the selected duty.
 * The maximum of Q*(H0*s²-aQ²) or Q*(H0*s²-bsQ) is analytic.
 */
export function pumpPowerEnvelope(curve, input) {
  const point = curve === 'quadratic' ? solveQuadraticPump(input) : curve === 'linear' ? solveLinearPump(input) : null;
  if (!point) throw new RangeError('Unknown pump curve.');
  if (!point.speedRatio) return Object.freeze({...point, maximumElectricalPowerW:0});
  const peak = curve === 'quadratic'
    ? Math.sqrt(input.shutoffHeadM * point.speedRatio ** 2 / (3 * input.quadraticResistanceS2M5))
    : input.shutoffHeadM * point.speedRatio / (2 * input.linearResistanceSM2);
  const maximum = pumpAtFlow(curve, input, Math.min(point.flowM3s, peak)).electricalPowerW;
  return Object.freeze({...point, maximumElectricalPowerW:maximum});
}

/** Speed limited to an electrical budget. This is a quasi-steady VFD idealization,
 * not a torque/inertia solution. Bisection uses the monotone power envelope.
 */
export function limitPumpPower(curve, input, availablePowerW) {
  finite(availablePowerW, 'availablePowerW', 0);
  const full = pumpPowerEnvelope(curve, input);
  if (availablePowerW >= full.maximumElectricalPowerW) return full;
  if (availablePowerW <= input.idlePowerW) return pumpPowerEnvelope(curve, {...input, speedRatio:0});
  let low = 0, high = input.speedRatio;
  for (let i = 0; i < 64; i++) {
    const middle = (low + high) / 2;
    if (pumpPowerEnvelope(curve, {...input, speedRatio:middle}).maximumElectricalPowerW <= availablePowerW) low = middle;
    else high = middle;
  }
  return pumpPowerEnvelope(curve, {...input, speedRatio:low});
}

/** Exact first-order response for a constant target over one supplied time step. */
export function firstOrderResponse(previous, target, timeConstantS, dtS) {
  finite(previous, 'previous'); finite(target, 'target');
  finite(timeConstantS, 'timeConstantS', 0); finite(dtS, 'dtS', 0);
  if (dtS === 0) return previous;
  if (timeConstantS === 0) return target;
  return finite(previous + (target - previous) * -Math.expm1(-dtS / timeConstantS), 'first-order response');
}

/** Constant-R resistor at RMS voltage; duty is a time-average fraction. */
export function resistiveHeaterPower({voltageV, resistanceOhm, duty = 1, efficiency: conversionEfficiency = 1}) {
  finite(voltageV, 'voltageV', 0); positive(resistanceOhm, 'resistanceOhm');
  finite(duty, 'duty', 0, 1); efficiency(conversionEfficiency, 'efficiency');
  const electricalPowerW = finite(voltageV ** 2 / resistanceOhm * duty, 'electricalPowerW', 0);
  return Object.freeze({electricalPowerW, heatPowerW: finite(electricalPowerW * conversionEfficiency, 'heatPowerW', 0)});
}

/** C*dT/dt=P-UA(T-Ta), exact over constant P/Ta/UA. Temperatures are kelvin.
 * Signed heatLossJ is negative when ambient adds heat to a colder body.
 */
export function stepLumpedThermal({temperatureK, ambientK, capacityJK, conductanceWK, heatPowerW, dtS}) {
  finite(temperatureK, 'temperatureK', 0); finite(ambientK, 'ambientK', 0);
  positive(capacityJK, 'capacityJK'); finite(conductanceWK, 'conductanceWK', 0);
  finite(heatPowerW, 'heatPowerW'); finite(dtS, 'dtS', 0);
  const inputEnergyJ = finite(heatPowerW * dtS, 'inputEnergyJ');
  const x = finite(conductanceWK * dtS / capacityJK, 'thermal decay argument', 0);
  const phi = x === 0 ? 1 : -Math.expm1(-x) / x;
  const deltaK = finite((heatPowerW - conductanceWK * (temperatureK - ambientK)) * dtS / capacityJK * phi, 'temperature change');
  const next = finite(temperatureK + deltaK, 'temperatureK', 0);
  const storedEnergyChangeJ = finite(capacityJK * deltaK, 'storedEnergyChangeJ');
  return Object.freeze({temperatureK: next, storedEnergyChangeJ, inputEnergyJ,
    heatLossJ: finite(inputEnergyJ - storedEnergyChangeJ, 'heatLossJ')});
}
