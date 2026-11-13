/**
 * Version 1 placeholder-model configuration validation. This module performs
 * no IO, starts no clocks, and never evaluates model text.
 *
 * The JSON Schema validates the model file's shape and numeric bounds. Runtime
 * validation additionally checks scenario identity, every system component and
 * connection reference, symbol port IDs and protected channels, complete model coverage, descriptor
 * defaults/families, and the level/inventory alias. System presentation fields
 * are copied safely but are otherwise the separate UI schema's responsibility.
 */
import {getModelDescriptor, MODEL_FAMILIES} from './model-registry.mjs';
import {validateV2Definition} from './v2/validation.mjs';
import {normalizeEquationBindings} from './equations/bindings.mjs';

export const PLACEHOLDER_MODEL_FORMAT = 'scada-placeholder-model';
export const PLACEHOLDER_MODEL_VERSION = 1;

const ID = /^[A-Za-z][A-Za-z0-9_-]{0,99}$/;
const BLOCKED_KEYS = new Set(['__proto__', 'prototype', 'constructor']);
const SECRET_KEYS = new Set(['password', 'secret', 'token', 'accesstoken', 'refreshtoken', 'apikey', 'privatekey', 'credentials', 'authorization']);
const PARAMETER_BOUNDS = Object.freeze({
  capacity:[0,100], response:[0,1], demand:[0,100], loss:[0,1],
  pressureGain:[0,100], heatGain:[0,100], warningAt:[0,100], damageRate:[0,10],
});
const INITIAL_NUMBERS = new Set(['load','level','inventory','temperature','pressure','damage']);
const INITIAL_BOOLEANS = new Set(['enabled','open','failed']);
const INITIAL_KEYS = new Set([...INITIAL_NUMBERS, ...INITIAL_BOOLEANS]);
const INITIAL_DEFAULTS = Object.freeze({enabled:true, open:true, load:60, level:60, inventory:60, temperature:20, pressure:10, failed:false, damage:0});
const own = (value, key) => value != null && Object.hasOwn(value, key);
const channel = medium => ['electricity','electrical','power','mechanical'].includes(medium) ? 'power'
  : ['data','signal','control','network','communication'].includes(medium) ? 'data'
    : ['measurement','sensor'].includes(medium) ? 'measurement'
      : ['thermal','heat','energy'].includes(medium) ? 'thermal' : 'resource';
const plain = value => value !== null && typeof value === 'object' && !Array.isArray(value) && [Object.prototype, null].includes(Object.getPrototypeOf(value));
const pathFor = (path, key) => `${path}/${String(key).replaceAll('~','~0').replaceAll('/','~1')}`;
const freeze = value => {
  if (value && typeof value === 'object' && !Object.isFrozen(value)) {
    Object.values(value).forEach(freeze); Object.freeze(value);
  }
  return value;
};

/** Clone data without invoking accessors, toJSON, iterators or prototype keys.
 * Limits apply to both supplied files, including presentation fields ignored
 * by this validator, so a malformed envelope cannot evade the JSON boundary. */
function safeClone(input, path, errors) {
  let count = 0, characters = 0;
  const seen = new WeakSet();
  const add = (where, code, message) => {
    if (errors.length < 100) errors.push({path:where, code, message});
  };
  const visit = (value, where, depth) => {
    if (++count > 60000 || depth > 32) {
      add(where, 'size_limit', 'JSON data exceeds the supported size or nesting limit.');
      return undefined;
    }
    if (value === null || typeof value === 'boolean') return value;
    if (typeof value === 'number') {
      if (!Number.isFinite(value)) { add(where, 'invalid_number', 'JSON numbers must be finite.'); return undefined; }
      return value;
    }
    if (typeof value === 'string') {
      characters += value.length;
      if (value.length > 16384 || characters > 2097152) { add(where, 'size_limit', 'JSON strings exceed the supported size limit.'); return undefined; }
      return value;
    }
    if (typeof value !== 'object') { add(where, 'non_json', 'Only JSON data is accepted.'); return undefined; }
    if (seen.has(value)) { add(where, 'cycle', 'Cyclic objects are not JSON data.'); return undefined; }
    const array = Array.isArray(value);
    if ((!array && !plain(value)) || (array && Object.getPrototypeOf(value) !== Array.prototype)) {
      add(where, 'prototype', 'Only plain JSON objects and arrays are accepted.'); return undefined;
    }
    seen.add(value);
    const keys = Reflect.ownKeys(value);
    if (keys.length > 60000 || (array && value.length > 60000)) {
      add(where, 'size_limit', 'JSON data exceeds the supported size limit.'); seen.delete(value); return undefined;
    }
    const output = array ? [] : {};
    if (array) {
      for (let index = 0; index < value.length; index++) {
        const descriptor = Object.getOwnPropertyDescriptor(value, String(index));
        if (!descriptor || !own(descriptor, 'value')) { add(pathFor(where,index), 'non_json', 'Sparse arrays and accessors are not JSON data.'); continue; }
        output.push(visit(descriptor.value, pathFor(where,index), depth + 1));
      }
      for (const key of keys) if (key !== 'length' && (typeof key !== 'string' || !/^(0|[1-9]\d*)$/.test(key) || Number(key) >= value.length)) add(where, 'non_json', 'Arrays cannot have custom properties.');
    } else {
      for (const key of keys) {
        if (typeof key !== 'string' || key.length > 128) { add(where, 'non_json', 'Object keys must be bounded strings.'); continue; }
        const nextPath = pathFor(where,key);
        if (BLOCKED_KEYS.has(key)) { add(nextPath, 'blocked_key', 'Prototype keys are forbidden.'); continue; }
        if (SECRET_KEYS.has(key.toLowerCase().replaceAll(/[-_]/g,''))) { add(nextPath, 'secret_field', 'Model definitions must not contain credentials or secret fields.'); continue; }
        const descriptor = Object.getOwnPropertyDescriptor(value,key);
        if (!descriptor?.enumerable || !own(descriptor,'value')) { add(nextPath, 'non_json', 'Accessors and hidden object properties are not JSON data.'); continue; }
        output[key] = visit(descriptor.value, nextPath, depth + 1);
      }
    }
    seen.delete(value);
    return output;
  };
  try { return visit(input, path, 0); }
  catch { add(path, 'non_json', 'The value could not be read as plain JSON data.'); return undefined; }
}

/** Validate a presentation system together with its independent model file.
 * Success contains a new recursively frozen, default-filled model definition;
 * the input objects are never mutated. No model equations run during validation. */
function validateLegacyModelDefinition(systemDefinition, modelDefinition) {
  const errors = [];
  const add = (path, code, message) => { if (errors.length < 100) errors.push({path, code, message}); };
  const system = safeClone(systemDefinition, '/systemDefinition', errors);
  const model = safeClone(modelDefinition, '', errors);
  if (errors.length) return {ok:false, errors};

  const object = (value, path, allowed, required = []) => {
    if (!plain(value)) { add(path, 'object', 'Expected a plain object.'); return false; }
    if (allowed) for (const key of Object.keys(value)) if (!allowed.includes(key)) add(pathFor(path,key), 'unknown_field', 'Unknown field.');
    for (const key of required) if (!own(value,key)) add(pathFor(path,key), 'required', 'Required field is missing.');
    return true;
  };
  const identifier = (value, path) => {
    if (typeof value !== 'string' || !ID.test(value) || BLOCKED_KEYS.has(value)) { add(path, 'id', 'Use a letter followed by at most 99 letters, digits, underscores or hyphens.'); return false; }
    return true;
  };
  const numeric = (value, path, min, max) => {
    if (typeof value !== 'number' || !Number.isFinite(value) || value < min || value > max) { add(path, 'range', `Expected a finite number from ${min} to ${max}.`); return false; }
    return true;
  };
  const assumptions = (value, path) => {
    if (value === undefined) return [];
    if (!Array.isArray(value) || value.length > 64) { add(path, 'assumptions', 'Assumptions must contain at most 64 text entries.'); return []; }
    return value.map((item,index) => {
      if (typeof item !== 'string' || item.length < 1 || item.length > 1024) add(pathFor(path,index), 'assumption_text', 'An assumption must be text from 1 to 1024 characters.');
      return item;
    });
  };

  if (!object(system, '/systemDefinition', null, ['system','components'])) return {ok:false,errors};
  if (object(system.system, '/systemDefinition/system', null, ['id'])) identifier(system.system.id, '/systemDefinition/system/id');
  if (!Array.isArray(system.components) || system.components.length < 1 || system.components.length > 256) add('/systemDefinition/components', 'components', 'A system needs from 1 to 256 components.');
  const components = Array.isArray(system.components) ? system.components.slice(0,256) : [];
  const descriptors = new Map(), componentIds = new Set();
  for (const [index,component] of components.entries()) {
    const path = `/systemDefinition/components/${index}`;
    if (!object(component,path,null,['id','type'])) continue;
    if (identifier(component.id,`${path}/id`)) {
      if (componentIds.has(component.id)) add(`${path}/id`, 'duplicate_id', 'Component IDs must be unique.');
      componentIds.add(component.id);
    }
    if (typeof component.type !== 'string') { add(`${path}/type`, 'type', 'A component type is required.'); continue; }
    try { const descriptor = getModelDescriptor(component.type); if (!descriptor) throw new Error(); descriptors.set(component.id,descriptor); }
    catch { add(`${path}/type`, 'unknown_type', `No placeholder model is registered for ${String(component.type).slice(0,100)}.`); }
  }
  const rawConnections = system.connections ?? [];
  if (!Array.isArray(rawConnections) || rawConnections.length > 1024) add('/systemDefinition/connections', 'connections', 'A system may contain at most 1024 connections.');
  const connectionIds = new Set();
  for (const [index,connection] of (Array.isArray(rawConnections) ? rawConnections.slice(0,1024) : []).entries()) {
    const path = `/systemDefinition/connections/${index}`;
    if (!object(connection,path,null,['id','from','to'])) continue;
    if (identifier(connection.id,`${path}/id`)) {
      if (connectionIds.has(connection.id)) add(`${path}/id`, 'duplicate_id', 'Connection IDs must be unique.');
      connectionIds.add(connection.id);
    }
    for (const direction of ['from','to']) {
      const endpoint = connection[direction], endpointPath = `${path}/${direction}`;
      if (!object(endpoint,endpointPath,['component','port'],['component','port'])) continue;
      if (!componentIds.has(endpoint.component)) add(`${endpointPath}/component`, 'unknown_component', 'Connection endpoint must name a declared component.');
      const descriptor = descriptors.get(endpoint.component);
      if (typeof endpoint.port !== 'string' || (descriptor && !descriptor.ports?.some(port => port.id === endpoint.port))) add(`${endpointPath}/port`, 'unknown_port', 'Connection endpoint must name a port declared by its component type.');
    }
    if (own(connection,'medium') && (typeof connection.medium !== 'string' || connection.medium.length < 1 || connection.medium.length > 64)) add(`${path}/medium`, 'medium', 'A connection medium must be text from 1 to 64 characters.');
    const sourcePort = descriptors.get(connection.from?.component)?.ports?.find(port => port.id === connection.from?.port);
    const targetPort = descriptors.get(connection.to?.component)?.ports?.find(port => port.id === connection.to?.port);
    if (sourcePort && targetPort) {
      const declared = channel(connection.medium ?? sourcePort.medium), source = channel(sourcePort.medium), target = channel(targetPort.medium);
      // Measurement links are non-material taps into declared sensor inputs.
      // Heat-only service may transfer a thermal index to a process receiver,
      // without treating that index as material flow or inventory.
      const compatible = declared === 'measurement' ? target === 'measurement'
        : declared === 'thermal' ? source === 'thermal' && ['thermal','resource'].includes(target)
          : declared === source && declared === target;
      if (!compatible) add(`${path}/medium`, 'channel_mismatch', 'A connection cannot override a power, data, measurement or heat-only port into another channel. Measurement taps must end at a measurement port; heat-only service must start at a thermal port.');
    }
  }

  if (!object(model, '', ['format','version','scenarioId','seed','components','assumptions','equations'], ['format','version','scenarioId','seed','components'])) return {ok:false,errors};
  if (model.format !== PLACEHOLDER_MODEL_FORMAT) add('/format', 'format', `Expected ${PLACEHOLDER_MODEL_FORMAT}.`);
  if (model.version !== PLACEHOLDER_MODEL_VERSION) add('/version', 'version', 'Only placeholder model version 1 is supported.');
  identifier(model.scenarioId, '/scenarioId');
  if (model.scenarioId !== system.system?.id) add('/scenarioId', 'scenario_mismatch', 'scenarioId must match system.system.id.');
  if (!Number.isInteger(model.seed) || model.seed < 1 || model.seed > 4294967295) add('/seed', 'seed', 'Seed must be an integer from 1 to 4294967295.');
  const normalized = {format:PLACEHOLDER_MODEL_FORMAT, version:PLACEHOLDER_MODEL_VERSION, scenarioId:model.scenarioId, seed:model.seed, components:{}, assumptions:assumptions(model.assumptions,'/assumptions')};
  if (model.equations !== undefined) {
    try { normalized.equations = normalizeEquationBindings(model.equations,{system}); }
    catch (error) { add('/equations','invalid_equations',error.message); }
  }
  if (!object(model.components, '/components')) return {ok:false,errors};
  if (Object.keys(model.components).length > 256) add('/components', 'components', 'A model may contain at most 256 component records.');
  for (const id of Object.keys(model.components)) {
    identifier(id, pathFor('/components',id));
    if (!componentIds.has(id)) add(pathFor('/components',id), 'unknown_component', 'Model component is not declared by the system.');
  }
  const families = new Set(Array.isArray(MODEL_FAMILIES) ? MODEL_FAMILIES.map(family => typeof family === 'string' ? family : family.id ?? family.family) : Object.keys(MODEL_FAMILIES));
  for (const component of components) {
    if (!component || typeof component.id !== 'string') continue;
    const path = pathFor('/components',component.id), descriptor = descriptors.get(component.id);
    if (!own(model.components,component.id)) { add(path, 'missing_component', 'Every system component needs a model component record.'); continue; }
    const input = model.components[component.id];
    if (!object(input,path,['kind','parameters','initial','assumptions']) || !descriptor) continue;
    const defaults = descriptor.defaultModel ?? {};
    const kind = input.kind ?? defaults.kind ?? descriptor.family;
    if (!families.has(kind)) add(`${path}/kind`, 'family', 'Unknown placeholder model family.');
    const parameterDescriptors = new Map((descriptor.parameters ?? []).map(parameter => [parameter.key,parameter]));
    const parameters = Object.fromEntries([...parameterDescriptors].map(([key,parameter]) => [key,parameter.default]));
    Object.assign(parameters, defaults.parameters ?? {});
    if (own(input,'parameters') && object(input.parameters,`${path}/parameters`,Object.keys(PARAMETER_BOUNDS))) Object.assign(parameters,input.parameters);
    for (const [key,value] of Object.entries(parameters)) {
      const bounds = PARAMETER_BOUNDS[key], parameter = parameterDescriptors.get(key);
      if (!bounds || !parameter) { add(pathFor(`${path}/parameters`,key), 'parameter', 'Parameter is not declared by this component model.'); continue; }
      numeric(value,pathFor(`${path}/parameters`,key),Math.max(bounds[0],parameter.min ?? bounds[0]),Math.min(bounds[1],parameter.max ?? bounds[1]));
    }
    const initial = {...INITIAL_DEFAULTS, ...defaults.initial};
    if (own(input,'initial') && object(input.initial,`${path}/initial`,[...INITIAL_KEYS])) {
      Object.assign(initial,input.initial);
      if (own(input.initial,'level') && !own(input.initial,'inventory')) initial.inventory = input.initial.level;
      if (own(input.initial,'inventory') && !own(input.initial,'level')) initial.level = input.initial.inventory;
      if (own(input.initial,'level') && own(input.initial,'inventory') && input.initial.level !== input.initial.inventory) add(`${path}/initial`, 'inventory_alias', 'level and inventory name the same initial stock and must agree when both are provided.');
    }
    for (const [key,value] of Object.entries(initial)) {
      if (INITIAL_NUMBERS.has(key)) numeric(value,pathFor(`${path}/initial`,key),0,100);
      else if (INITIAL_BOOLEANS.has(key)) { if (typeof value !== 'boolean') add(pathFor(`${path}/initial`,key), 'boolean', 'Expected a boolean.'); }
      else add(pathFor(`${path}/initial`,key), 'initial_field', 'Unknown initial-state field.');
    }
    normalized.components[component.id] = {kind, parameters, initial, assumptions:assumptions(input.assumptions,`${path}/assumptions`)};
  }
  return errors.length ? {ok:false,errors} : {ok:true,definition:freeze(normalized)};
}

/** Validate through the explicitly selected format version. */
export function validatePlaceholderModelDefinition(systemDefinition, modelDefinition) {
  return modelDefinition?.version === 2
    ? validateV2Definition(systemDefinition, modelDefinition)
    : validateLegacyModelDefinition(systemDefinition, modelDefinition);
}
