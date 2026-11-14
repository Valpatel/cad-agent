/** Deliberately bounded JSON Schema subset for provider parameters and state.
 * No refs, code, remote schema fetch, coercion or implicit defaults. */
import {cloneData,freezeData,knownKeys,plainObject} from './contracts.mjs';

const TYPES = ['object','array','string','number','integer','boolean','null'];
const KEYS = ['type','properties','required','additionalProperties','items','minimum','maximum','exclusiveMinimum','exclusiveMaximum','minItems','maxItems','minLength','maxLength','enum','const','description','title'];
const equal = (left,right) => JSON.stringify(left) === JSON.stringify(right);

export function validateDataSchema(input) {
  const schema = cloneData(input);
  function inspect(node,depth = 0) {
    if (depth > 24) throw new TypeError('Provider schema is too deep.');
    knownKeys(node,KEYS,'provider schema');
    if (!TYPES.includes(node.type)) throw new TypeError('Provider schemas need one supported type.');
    for (const key of ['title','description']) if (node[key] !== undefined && typeof node[key] !== 'string') throw new TypeError(`Schema ${key} must be text.`);
    if (node.type === 'object') {
      if (node.additionalProperties !== false) throw new TypeError('Provider object schemas must declare additionalProperties:false.');
      plainObject(node.properties ?? {},'schema properties');
      for (const child of Object.values(node.properties ?? {})) inspect(child,depth + 1);
      if (node.required !== undefined && (!Array.isArray(node.required) || new Set(node.required).size !== node.required.length || node.required.some(key => typeof key !== 'string' || !Object.hasOwn(node.properties ?? {},key)))) throw new TypeError('Required schema keys must name declared properties.');
    } else if (['properties','required','additionalProperties'].some(key => Object.hasOwn(node,key))) throw new TypeError('Object schema keywords require object type.');
    if (node.type === 'array') { if (!node.items) throw new TypeError('Array schemas need items.'); inspect(node.items,depth + 1); }
    else if (['items','minItems','maxItems'].some(key => Object.hasOwn(node,key))) throw new TypeError('Array schema keywords require array type.');
    for (const key of ['minimum','maximum','exclusiveMinimum','exclusiveMaximum']) if (node[key] !== undefined && (!['number','integer'].includes(node.type) || typeof node[key] !== 'number' || !Number.isFinite(node[key]))) throw new TypeError('Numeric bounds require a numeric schema.');
    for (const key of ['minItems','maxItems','minLength','maxLength']) if (node[key] !== undefined && (!Number.isInteger(node[key]) || node[key] < 0 || node[key] > 100000)) throw new TypeError('Schema lengths must be bounded nonnegative integers.');
    if (node.type !== 'string' && ['minLength','maxLength'].some(key => Object.hasOwn(node,key))) throw new TypeError('String lengths require string type.');
    for (const [low,high] of [['minimum','maximum'],['minItems','maxItems'],['minLength','maxLength']]) if (node[low] !== undefined && node[high] !== undefined && node[low] > node[high]) throw new TypeError('Schema minimum exceeds maximum.');
    if (node.enum !== undefined && (!Array.isArray(node.enum) || !node.enum.length || node.enum.some(value => value !== null && typeof value === 'object'))) throw new TypeError('Schema enum must be a nonempty array of primitive values.');
    if (Object.hasOwn(node,'const') && node.const !== null && typeof node.const === 'object') throw new TypeError('Schema const must be primitive.');
  }
  inspect(schema); return freezeData(schema);
}

export function validateSchemaValue(schema,input,label = 'Provider data') {
  const value = cloneData(input);
  function visit(spec,current,path) {
    const type = spec.type;
    const matches = type === 'null' ? current === null : type === 'array' ? Array.isArray(current) : type === 'object' ? current !== null && typeof current === 'object' && !Array.isArray(current) : type === 'integer' ? Number.isInteger(current) : typeof current === type;
    if (!matches) throw new TypeError(`${label}${path} must be ${type}.`);
    if (spec.enum && !spec.enum.some(item => equal(item,current))) throw new TypeError(`${label}${path} is not an allowed value.`);
    if (Object.hasOwn(spec,'const') && !equal(spec.const,current)) throw new TypeError(`${label}${path} does not match its constant.`);
    if (type === 'object') {
      for (const key of Object.keys(current)) if (!Object.hasOwn(spec.properties ?? {},key)) throw new TypeError(`Unknown ${label}${path}/${key}.`);
      for (const key of spec.required ?? []) if (!Object.hasOwn(current,key)) throw new TypeError(`Missing ${label}${path}/${key}.`);
      for (const [key,child] of Object.entries(current)) visit(spec.properties[key],child,`${path}/${key}`);
    }
    if (type === 'array') {
      if (current.length < (spec.minItems ?? 0) || current.length > (spec.maxItems ?? 10000)) throw new RangeError(`${label}${path} array length is out of bounds.`);
      current.forEach((item,index) => visit(spec.items,item,`${path}/${index}`));
    }
    if (type === 'string' && (current.length < (spec.minLength ?? 0) || current.length > (spec.maxLength ?? 16384))) throw new RangeError(`${label}${path} string length is out of bounds.`);
    if (['number','integer'].includes(type) && ((spec.minimum !== undefined && current < spec.minimum) || (spec.maximum !== undefined && current > spec.maximum) || (spec.exclusiveMinimum !== undefined && current <= spec.exclusiveMinimum) || (spec.exclusiveMaximum !== undefined && current >= spec.exclusiveMaximum))) throw new RangeError(`${label}${path} is outside schema bounds.`);
  }
  visit(schema,value,''); return freezeData(value);
}
