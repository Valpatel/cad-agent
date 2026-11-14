import {TYPE_CONTRACTS} from '../v2/type-contracts.mjs';
import {cloneData,freezeData,knownKeys,plainObject,identity} from './contracts.mjs';

const FAMILIES = {
  v1:new Set(['source','storage','pump','valve','processor','heater','generator','load','controller','sensor','pipe','network','energy-storage','sink']),
  v2:new Set(TYPE_CONTRACTS.flatMap(item => [item.family ?? 'processor', ...Object.values(item.resolvedVariants ?? {}).map(variant => variant.family ?? item.family ?? 'processor')])),
};
const TYPES = new Set(TYPE_CONTRACTS.map(item => item.type));

/** Data-only validation; provider availability is checked by EquationRuntime. */
export function normalizeEquationBindings(input,{system} = {}) {
  const value = cloneData(input);
  knownKeys(value,['version','families','types','components'],'equations');
  if (value.version !== 1) throw new TypeError('Expected equations version 1.');
  const ids = new Set((system?.components ?? []).map(item => item.id));
  const binding = record => {
    if (record === null) return null;
    knownKeys(record,['id','version','parameters'],'equation binding');
    identity(record.id,'Provider id'); identity(record.version,'Provider version');
    plainObject(record.parameters ?? {},'Equation parameters');
    return {id:record.id,version:record.version,parameters:cloneData(record.parameters ?? {})};
  };
  const normalizeMap = (map, allowed, label) => {
    plainObject(map ?? {},label);
    const result = {};
    for (const [key,record] of Object.entries(map ?? {})) {
      if (!allowed.has(key)) throw new TypeError(`Unknown equation ${label} selector: ${key}.`);
      result[key] = binding(record);
    }
    return result;
  };
  knownKeys(value.families ?? {},['v1','v2'],'equation families');
  return freezeData({version:1,
    families:{v1:normalizeMap(value.families?.v1,FAMILIES.v1,'v1 family'),v2:normalizeMap(value.families?.v2,FAMILIES.v2,'v2 family')},
    types:normalizeMap(value.types,TYPES,'type'),components:normalizeMap(value.components,ids,'component'),
  });
}

export function resolveEquationBinding(equations,equipment,engineVersion) {
  if (!equations) return null;
  if (Object.hasOwn(equations.components,equipment.id)) return equations.components[equipment.id];
  if (Object.hasOwn(equations.types,equipment.type)) return equations.types[equipment.type];
  return equations.families[`v${engineVersion}`][equipment.family] ?? null;
}
