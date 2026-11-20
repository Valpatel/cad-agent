import {EQUATION_UNITS,cloneData,freezeData,knownKeys,plainObject,identity,phaseContract,validatePhaseOutput} from './contracts.mjs';
import {normalizeEquationBindings,resolveEquationBinding} from './bindings.mjs';
import {validateDataSchema,validateSchemaValue} from './schema.mjs';

const providerKey = (id,version) => `${id}\u0000${version}`;
const metadataKeys = ['id','version','stateVersion','engines','phases','units','parameterSchema','stateSchema','defaultParameters','label','description'];
const canonical = value => Array.isArray(value) ? value.map(canonical) : value && typeof value === 'object' ? Object.fromEntries(Object.keys(value).sort().map(key => [key,canonical(value[key])])) : value;
const signature = value => JSON.stringify(canonical(value));
function syncCall(callback,args,label) {
  const result = Reflect.apply(callback,undefined,args);
  if (result && (typeof result === 'object' || typeof result === 'function')) {
    // Attach handlers only to native Promise internal slots, never invoke an
    // arbitrary thenable/accessor. A rejected unsupported Promise must not
    // become an unhandled rejection after the synchronous transaction rejects.
    let nativePromise = false;
    try { Reflect.apply(Promise.prototype.then,result,[() => {},() => {}]); nativePromise = true; } catch {}
    const then = Object.getOwnPropertyDescriptor(result,'then');
    if (nativePromise || (then && (!Object.hasOwn(then,'value') || typeof then.value === 'function'))) throw new TypeError(`${label} must return synchronously, not a Promise or thenable.`);
  }
  return result;
}
function registryFor(providers) {
  if (!Array.isArray(providers)) throw new TypeError('equationProviders must be an array of trusted providers.');
  const registry = new Map();
  for (const supplied of providers) {
    if (!supplied || typeof supplied !== 'object' || Array.isArray(supplied)) throw new TypeError('Expected an equation provider object.');
    const data = {}, callbacks = {};
    for (const key of Reflect.ownKeys(supplied)) {
      const property = Object.getOwnPropertyDescriptor(supplied,key);
      if (typeof key !== 'string' || !property.enumerable || !Object.hasOwn(property,'value')) throw new TypeError('Provider declarations need own enumerable data properties.');
      if (['initialize','evaluate','advance'].includes(key)) callbacks[key] = property.value;
      else if (metadataKeys.includes(key)) data[key] = property.value;
      else throw new TypeError(`Unknown equation provider field: ${key}.`);
    }
    const meta = cloneData(data);
    identity(meta.id,'Provider id'); identity(meta.version,'Provider version');
    if (!Number.isInteger(meta.stateVersion) || meta.stateVersion < 1 || meta.stateVersion > 1e6) throw new TypeError('Provider stateVersion must be a positive bounded integer.');
    if (meta.units !== EQUATION_UNITS) throw new TypeError(`Provider units must be ${EQUATION_UNITS}; explicitly bridge physical units.`);
    if (!Array.isArray(meta.engines) || !meta.engines.length || new Set(meta.engines).size !== meta.engines.length || meta.engines.some(version => ![1,2].includes(version))) throw new TypeError('Provider engines must select version 1 and/or 2.');
    if (!Array.isArray(meta.phases) || !meta.phases.length || new Set(meta.phases).size !== meta.phases.length) throw new TypeError('Provider phases must be a nonempty unique array.');
    for (const engine of meta.engines) for (const phase of meta.phases) phaseContract(phase,engine);
    for (const key of ['initialize','evaluate']) if (typeof callbacks[key] !== 'function') throw new TypeError(`Provider ${key} must be a trusted synchronous function.`);
    if (callbacks.advance !== undefined && typeof callbacks.advance !== 'function') throw new TypeError('Provider advance must be a function.');
    for (const callback of Object.values(callbacks)) if (callback?.constructor?.name === 'AsyncFunction') throw new TypeError('Async equation providers are unsupported.');
    const parameterSchema = validateDataSchema(meta.parameterSchema), stateSchema = validateDataSchema(meta.stateSchema);
    if (parameterSchema.type !== 'object' || stateSchema.type !== 'object') throw new TypeError('Provider parameters and state must use closed object schemas.');
    const defaultParameters = cloneData(meta.defaultParameters ?? {});
    plainObject(defaultParameters,'Provider defaultParameters');
    const schemaSignature = signature({parameterSchema,stateSchema});
    if (schemaSignature.length > 16384) throw new TypeError('Provider schema signature exceeds the saved-state text budget.');
    const key = providerKey(meta.id,meta.version);
    if (registry.has(key)) throw new TypeError(`Duplicate equation provider ${meta.id}@${meta.version}.`);
    registry.set(key,Object.freeze({...meta,parameterSchema,stateSchema,schemaSignature,defaultParameters:freezeData(defaultParameters),...callbacks}));
  }
  return registry;
}

export class EquationRuntime {
  #system; #definition; #engineVersion; #registry; #bindings = new Map(); #states = new Map(); #checkpoints = new WeakMap();
  constructor({system,definition,engineVersion,providers = [],initialize = true},internalRegistry) {
    if (![1,2].includes(engineVersion) || typeof initialize !== 'boolean') throw new TypeError('Expected engine version 1/2 and boolean initialize.');
    this.#system = freezeData(cloneData(system)); this.#definition = freezeData(cloneData(definition)); this.#engineVersion = engineVersion;
    this.#registry = internalRegistry ?? registryFor(providers);
    const equations = definition.equations === undefined ? null : normalizeEquationBindings(definition.equations,{system});
    for (const instance of [...system.components].sort((a,b) => a.id.localeCompare(b.id))) {
      const config = definition.components[instance.id];
      const equipment = freezeData({id:instance.id,type:instance.type,variant:config.variant ?? instance.variant ?? null,family:engineVersion === 1 ? config.kind : config.model});
      const binding = resolveEquationBinding(equations,equipment,engineVersion);
      if (!binding) continue;
      const provider = this.#registry.get(providerKey(binding.id,binding.version));
      if (!provider) throw new TypeError(`Missing equation provider ${binding.id}@${binding.version} for ${instance.id}.`);
      if (!provider.engines.includes(engineVersion)) throw new TypeError(`Provider ${binding.id} does not support engine ${engineVersion}.`);
      const parameters = validateSchemaValue(provider.parameterSchema,{...provider.defaultParameters,...binding.parameters},`Parameters for ${instance.id}`);
      this.#bindings.set(instance.id,{equipment,binding,provider,parameters});
    }
    if (initialize) this.reset();
  }
  get hasBindings() { return this.#bindings.size > 0; }
  has(id) { return this.#bindings.has(id); }
  hasPhase(id,phase) { return this.#bindings.get(id)?.provider.phases.includes(phase) ?? false; }
  #context(id,context = {},defaults = {},initializing = false) {
    const record = this.#bindings.get(id);
    if (!record) throw new RangeError(`No equation binding for ${id}.`);
    if (!initializing && !this.#states.has(id)) throw new TypeError(`Equation state for ${id} has not been initialized or restored.`);
    return freezeData({...cloneData(context),engineVersion:this.#engineVersion,equipment:record.equipment,parameters:record.parameters,providerState:initializing ? null : cloneData(this.#states.get(id)),defaults:cloneData(defaults)});
  }
  evaluate(id,phase,context,defaults) {
    if (!this.hasPhase(id,phase)) return defaults;
    const record = this.#bindings.get(id), baseline = validatePhaseOutput(phase,this.#engineVersion,defaults);
    const output = syncCall(record.provider.evaluate,[phase,this.#context(id,context,baseline)],`${record.provider.id} evaluate`);
    return freezeData({...baseline,...validatePhaseOutput(phase,this.#engineVersion,output)});
  }
  advance(id,context) {
    const record = this.#bindings.get(id);
    if (!record?.provider.advance) return;
    const result = syncCall(record.provider.advance,[this.#context(id,context)],`${record.provider.id} advance`);
    this.#states.set(id,validateSchemaValue(record.provider.stateSchema,result,`State for ${id}`));
  }
  reset(contextForId = () => ({})) {
    if (typeof contextForId !== 'function') throw new TypeError('reset context must be a function.');
    const next = new Map();
    for (const [id,record] of this.#bindings) {
      const result = syncCall(record.provider.initialize,[this.#context(id,contextForId(id),{},true)],`${record.provider.id} initialize`);
      next.set(id,validateSchemaValue(record.provider.stateSchema,result,`Initial state for ${id}`));
    }
    this.#states = next;
  }
  exportState() {
    if (!this.hasBindings) return undefined;
    const components = {};
    for (const [id,record] of this.#bindings) {
      if (!this.#states.has(id)) throw new TypeError(`Equation state for ${id} is not initialized.`);
      components[id] = {id:record.provider.id,version:record.provider.version,stateVersion:record.provider.stateVersion,units:EQUATION_UNITS,parameters:cloneData(record.parameters),schemaSignature:record.provider.schemaSignature,state:cloneData(this.#states.get(id))};
    }
    return {version:1,components};
  }
  importState(payload) {
    if (!this.hasBindings) { if (payload !== undefined) throw new TypeError('Unexpected equation state without active bindings.'); this.#states = new Map(); return; }
    const saved = cloneData(payload); knownKeys(saved,['version','components'],'equation state');
    if (saved.version !== 1) throw new TypeError('Expected equation state version 1.');
    knownKeys(saved.components,[...this.#bindings.keys()],'equation component state');
    if (Object.keys(saved.components).length !== this.#bindings.size) throw new TypeError('Equation state must cover every bound component.');
    const next = new Map();
    for (const [id,record] of this.#bindings) {
      const entry = saved.components[id]; knownKeys(entry,['id','version','stateVersion','units','parameters','schemaSignature','state'],'saved provider state');
      if (entry.id !== record.provider.id || entry.version !== record.provider.version || entry.stateVersion !== record.provider.stateVersion) throw new TypeError(`Equation provider identity/state version mismatch for ${id}.`);
      if (entry.units !== EQUATION_UNITS || entry.schemaSignature !== record.provider.schemaSignature || signature(entry.parameters) !== signature(record.parameters)) throw new TypeError(`Equation units, schema or parameters mismatch for ${id}.`);
      next.set(id,validateSchemaValue(record.provider.stateSchema,entry.state,`Saved state for ${id}`));
    }
    this.#states = next;
  }
  checkpoint() {
    const token = Object.freeze({});
    this.#checkpoints.set(token,new Map([...this.#states].map(([id,state]) => [id,freezeData(cloneData(state))])));
    return token;
  }
  restore(token) {
    const states = this.#checkpoints.get(token);
    if (!states) throw new TypeError('Checkpoint does not belong to this equation runtime.');
    this.#states = new Map(states);
  }
  withDefinition(definition,{initialize = true} = {}) {
    return new EquationRuntime({system:this.#system,definition,engineVersion:this.#engineVersion,initialize},this.#registry);
  }
  fork() {
    const result = this.withDefinition(this.#definition,{initialize:false});
    result.#states = new Map([...this.#states].map(([id,state]) => [id,freezeData(cloneData(state))]));
    return result;
  }
}

export function createEquationRuntime(options) { return new EquationRuntime(options); }
