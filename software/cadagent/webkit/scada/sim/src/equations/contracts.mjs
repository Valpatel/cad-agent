/** Numeric proposals use the existing kernel's explicit normalized unit bases.
 * Physical providers must declare their own unit conversions in parameters. */
export const EQUATION_UNITS = 'scada-index-v1';
export const EQUATION_CONTRACT_VERSION = 1;
/** Error-path formatting must not invoke a thrown object's getters/toString. */
export function formatEquationError(error,maxLength = 500) {
  const limit = Number.isInteger(maxLength) && maxLength > 0 ? Math.min(maxLength,1000) : 500;
  let message;
  if (typeof error === 'string') message = error;
  else if (error !== null && (typeof error === 'object' || typeof error === 'function')) {
    try {
      const property = Object.getOwnPropertyDescriptor(error,'message');
      if (property && Object.hasOwn(property,'value') && typeof property.value === 'string') message = property.value;
    } catch { /* Proxies may reject reflection; retain the safe fallback. */ }
  }
  const bounded = typeof message === 'string' ? message.slice(0,limit) : '';
  return /\S/.test(bounded) ? bounded : 'Equation provider failed.'.slice(0,limit);
}
export const freezeData = value => {
  if (value && typeof value === 'object') { Object.values(value).forEach(freezeData); Object.freeze(value); }
  return value;
};
const index = {unit:'normalized kernel index (0–100)', minimum:0, maximum:100};
const rate = {unit:'normalized resource-rate basis (see engineUnits)', minimum:0, maximum:1e9};
const power = {unit:'normalized power-rate basis (see engineUnits)', minimum:0, maximum:1e9};
const heat = {unit:'normalized retained-heat amount per accepted substep', minimum:0, maximum:1e9};
export const EQUATION_PHASE_CONTRACTS = freezeData({
  operating:{engines:[1,2], outputs:{operating:index}, description:'Next operating index, evaluated once per substep before allocation.'},
  resource:{engines:[1,2], outputs:{capacity:rate}, engineUnits:{1:'legacy flow index; inventory-index change = accepted rate × dtMinutes / 10',2:'normalized resource amount per model minute; amount change = accepted rate × dtMinutes, where amount = inventoryIndex × stockScale'}, description:'Effective requested local transfer ceiling. Kernel applies configured rating, absolute disable/isolation/supply gates and finite allocation; fractional derating is the provider law, not multiplied again.'},
  energy:{engines:[1,2], outputs:{capacity:power, demand:power, efficiency:{unit:'fraction', exclusiveMinimum:0, maximum:1}, auxiliaryDemand:power}, engineOutputs:{1:['capacity','demand'],2:['capacity','demand','efficiency','auxiliaryDemand']}, engineUnits:{1:'legacy power index; energy-storage inventory-index change = accepted rate × dtMinutes / 10',2:'normalized energy amount per model minute; stored-energy change = accepted rate × dtMinutes before declared efficiency/loss accounting'}, description:'Effective requested capacity/demand. V2 auxiliaryDemand is nominal per-port demand; engine applies its existing health gate once. Kernel rating and absolute supply gates remain. Provider owns fractional derating. Repeated pure allocation evaluation.'},
  pressure:{engines:[1,2], outputs:{target:index}, engineSemantics:{1:{stage:'response-target',meaning:'Provider target enters the existing family pressure-response integration.'},2:{stage:'next-state',meaning:'Provider target is the next pressure index; it replaces the already-integrated default proposal.'}}, description:'V1 pressure target before family response; v2 next pressure index after the proposed response. Inspect engineVersion; these stages are not interchangeable.'},
  temperature:{engines:[1], outputs:{target:index}, description:'V1 temperature target before family response.'},
  signal:{engines:[1], outputs:{target:index}, description:'V1 signal target.'},
  condition:{engines:[1,2], outputs:{damage:index}, description:'Next absolute damage index; kernel owns declared fault latching.'},
  'thermal-source':{engines:[2], outputs:{heat}, description:'Requested heat this step; kernel caps accepted supply and receiver room and records the ledger.'},
  'thermal-transfer':{engines:[2], outputs:{heat,lossFraction:{unit:'fraction',minimum:0,maximum:1}}, description:'Requested transfer and declared loss fraction; kernel owns paired debit/credit and loss accounting.'},
  'thermal-loss':{engines:[2], outputs:{heat}, description:'Requested heat loss this step, capped by retained heat and recorded by the kernel.'},
});

export function cloneData(input) {
  const ancestors = new Set(); let count = 0, textSize = 0;
  function visit(value, depth) {
    if (++count > 100000 || depth > 32) throw new TypeError('Equation data exceeds size/depth limits.');
    if (value === null || typeof value === 'boolean') return value;
    if (typeof value === 'number') { if (!Number.isFinite(value)) throw new TypeError('Equation numbers must be finite.'); return value; }
    if (typeof value === 'string') { textSize += value.length; if (textSize > 2097152 || value.length > 16384) throw new TypeError('Equation text exceeds limits.'); return value; }
    if (!value || typeof value !== 'object' || ancestors.has(value) || (!Array.isArray(value) && ![Object.prototype,null].includes(Object.getPrototypeOf(value)))) throw new TypeError('Expected acyclic plain equation JSON data.');
    ancestors.add(value); const result = Array.isArray(value) ? [] : {};
    for (const key of Reflect.ownKeys(value)) {
      if (Array.isArray(value) && key === 'length') continue;
      if (typeof key !== 'string' || ['__proto__','prototype','constructor'].includes(key)) throw new TypeError('Unsafe equation data key.');
      const property = Object.getOwnPropertyDescriptor(value,key);
      if (!Object.hasOwn(property,'value') || !property.enumerable) throw new TypeError('Equation data cannot use accessors or hidden properties.');
      result[key] = visit(property.value,depth + 1);
    }
    if (Array.isArray(value) && (Object.keys(result).length !== value.length || Object.keys(result).some(key => !/^(0|[1-9]\d*)$/.test(key)))) throw new TypeError('Equation arrays cannot be sparse or decorated.');
    ancestors.delete(value); return result;
  }
  return visit(input,0);
}

export function plainObject(value, label = 'Value') {
  if (!value || typeof value !== 'object' || Array.isArray(value) || ![Object.prototype,null].includes(Object.getPrototypeOf(value))) throw new TypeError(`${label} must be a plain object.`);
  return value;
}
export function knownKeys(object, allowed, label) {
  plainObject(object,label);
  for (const key of Object.keys(object)) if (!allowed.includes(key)) throw new TypeError(`Unknown ${label} field: ${key}.`);
}
export function identity(value,label) {
  if (typeof value !== 'string' || !/^[A-Za-z0-9][A-Za-z0-9._:/@+-]{0,127}$/.test(value)) throw new TypeError(`${label} must be a bounded stable identity.`);
  return value;
}
export function phaseContract(phase, engineVersion) {
  const contract = EQUATION_PHASE_CONTRACTS[phase];
  if (!contract || !contract.engines.includes(engineVersion)) throw new TypeError(`Unsupported equation phase ${phase} for engine ${engineVersion}.`);
  return contract;
}
export function validatePhaseOutput(phase, engineVersion, output) {
  const contract = phaseContract(phase,engineVersion), value = cloneData(output);
  knownKeys(value,contract.engineOutputs?.[engineVersion] ?? Object.keys(contract.outputs),`${phase} output`);
  for (const [key,number] of Object.entries(value)) {
    const spec = contract.outputs[key];
    if (typeof number !== 'number' || !Number.isFinite(number) || (spec.minimum !== undefined && number < spec.minimum) || (spec.exclusiveMinimum !== undefined && number <= spec.exclusiveMinimum) || (spec.maximum !== undefined && number > spec.maximum)) throw new RangeError(`Equation ${phase}.${key} is outside its ${spec.unit} contract.`);
  }
  return value;
}
