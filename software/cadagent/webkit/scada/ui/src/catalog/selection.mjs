/** Registry-only selection helpers. No rendering, model, DOM or IO. */

export function freezeScadaMetadata(value) {
  if (value && typeof value === 'object' && !Object.isFrozen(value)) {
    for (const child of Object.values(value)) freezeScadaMetadata(child);
    Object.freeze(value);
  }
  return value;
}

export function ownDataObject(value, allowed, label) {
  if (!value || typeof value !== 'object' || Array.isArray(value)
      || ![Object.prototype, null].includes(Object.getPrototypeOf(value))) {
    throw new TypeError(`${label} must be a plain own-property object.`);
  }
  for (const key of Reflect.ownKeys(value)) {
    if (typeof key !== 'string' || !allowed.includes(key)) {
      throw new TypeError(`Unknown ${label} field: ${String(key)}`);
    }
    if (!Object.hasOwn(Object.getOwnPropertyDescriptor(value, key), 'value')) {
      throw new TypeError(`${label} cannot contain accessors.`);
    }
  }
}

/** A selected variant changes only explicitly declared metadata. */
export function resolveScadaVariant(descriptor, variant) {
  const variants = descriptor.variants ?? [];
  const selected = variant;
  if (selected === undefined || selected === null) return descriptor;
  if (typeof selected !== 'string') throw new TypeError('Variant must be a registered string.');
  const choice = variants.find(item => item.id === selected);
  if (!choice) throw new RangeError(`Unknown ${descriptor.type} variant: ${selected}`);

  const allPorts = [...descriptor.ports, ...(choice.additionalPorts ?? [])];
  const disabled = new Set(choice.disabledPorts ?? []);
  const ports = allPorts
    .filter(port => !disabled.has(port.id))
    .map(port => ({...port, ...(choice.portOverrides?.[port.id] ?? {})}));
  if (new Set(ports.map(port => port.id)).size !== ports.length) {
    throw new TypeError(`Duplicate ports in ${descriptor.type} variant ${selected}.`);
  }
  const circuits = (choice.circuits ?? descriptor.circuits ?? []).map(circuit => ({
    ...circuit,
    ...(choice.circuitOverrides?.[circuit.id] ?? {}),
  }));
  const stateFields = descriptor.stateFields.map(field => {
    const allowed = field.key === 'direction' ? choice.allowedDirections
      : field.key === 'mode' ? choice.allowedModes : undefined;
    if (!allowed) return field;
    return {
      ...field,
      options: allowed.map(value=>field.options.find(option=>option.value===value)??{value,label:value.replaceAll('-',' ')}),
      default: allowed.includes(field.default) ? field.default : allowed[0],
    };
  });
  return freezeScadaMetadata({
    ...descriptor,
    ...(choice.componentLabel?{label:choice.componentLabel,name:choice.componentLabel}:{}),
    ...(choice.description?{description:choice.description}:{}),
    ...(choice.modelSupport?{modelSupport:choice.modelSupport}:{}),
    selectedVariant: choice,
    ports,
    circuits,
    powerDomains: {...(descriptor.powerDomains ?? {}), ...(choice.powerDomains ?? {})},
    taxonomy:{...descriptor.taxonomy,media:[...new Set(ports.map(port=>port.medium))]},
    stateFields,
    defaultState: Object.fromEntries(stateFields.map(field => [field.key, field.default])),
  });
}

const CATEGORY_TAXONOMY = {
  process: {industries: ['process-industry'], systems: ['process-utilities'], functions: ['contain-or-process-material']},
  rotating: {industries: ['industry', 'power', 'water', 'agriculture'], systems: ['mechanical-utilities'], functions: ['move-material-or-shaft']},
  power: {industries: ['industry', 'power', 'agriculture'], systems: ['electrical-distribution'], functions: ['transfer-or-condition-power']},
  valves: {industries: ['industry', 'power', 'water', 'agriculture'], systems: ['fluid-distribution'], functions: ['control-flow']},
  instruments: {industries: ['industry', 'power', 'water', 'agriculture'], systems: ['instrumentation'], functions: ['measure']},
  automation: {industries: ['industry', 'power', 'water', 'agriculture'], systems: ['automation'], functions: ['control-or-communicate']},
  connections: {industries: ['industry', 'power', 'water', 'agriculture'], systems: ['distribution'], functions: ['connect']},
  manufacturing: {industries: ['manufacturing'], systems: ['production-line'], functions: ['process-material']},
  agriculture: {industries: ['agriculture'], systems: ['controlled-environment-agriculture'], functions: ['support-crop-or-fish']},
  climate: {industries: ['agriculture', 'buildings'], systems: ['environmental-control'], functions: ['condition-environment']},
  nuclear: {industries: ['power', 'nuclear'], systems: ['nuclear-generation'], functions: ['support-conceptual-heat-cycle']},
};

const SPECIFIC_TAXONOMY = {
  generator: {family: 'packaged-generation', systems:['thermal-generation','electrical-distribution','microgrid'], technologies: ['reciprocating-engine', 'microturbine'], functions: ['generate-electricity'], keywords: ['genset', 'standby', 'CHP', 'diesel', 'gasoline', 'natural gas']},
  'steam-turbine': {family: 'integrated-steam-generation', technologies: ['steam-cycle'], functions: ['generate-electricity'], keywords: ['integrated turbine generator']},
  'solar-panel': {family: 'solar', technologies: ['photovoltaic'], functions: ['convert-solar-energy'], keywords: ['PV', 'DC array']},
  'wind-turbine': {family: 'wind', technologies: ['wind'], functions: ['generate-electricity']},
  'fuel-cell': {family: 'electrochemical', technologies: ['fuel-cell'], functions: ['generate-electricity']},
  electrolyzer: {family: 'electrochemical', technologies: ['electrolysis'], functions: ['produce-gas']},
  battery: {family: 'energy-storage', technologies: ['battery'], functions: ['store-electrical-energy']},
  ups: {family: 'energy-storage', technologies: ['battery', 'power-conversion'], functions: ['maintain-electrical-supply']},
  boiler: {family: 'thermal-generation', technologies: ['combustion', 'steam-cycle'], functions: ['supply-heat', 'generate-steam']},
  'heat-exchanger': {family: 'heat-transfer', technologies: ['heat-exchange'], functions: ['transfer-heat']},
};

/** Add orthogonal discovery metadata while retaining the original physical ID. */
export function addScadaTaxonomy(descriptor) {
  const defaults = CATEGORY_TAXONOMY[descriptor.category] ?? {};
  const specific = SPECIFIC_TAXONOMY[descriptor.type] ?? {};
  const source = descriptor.taxonomy ?? {};
  const taxonomy = {
    family: descriptor.category,
    industries: [], systems: [], functions: [], technologies: [], keywords: [],
    ...defaults, ...specific, ...source,
    media: [...new Set([
      ...descriptor.ports.map(port => port.medium),
      ...(descriptor.variants??[]).flatMap(variant=>[
        ...Object.values(variant.portOverrides??{}).map(port=>port.medium),
        ...(variant.additionalPorts??[]).map(port=>port.medium),
      ]).filter(Boolean),
    ])],
  };
  if (!taxonomy.technologies.length) taxonomy.technologies = [taxonomy.family];
  return {...descriptor, taxonomy};
}

export const SCADA_FILTER_KEYS = Object.freeze([
  'query', 'type', 'category', 'industry', 'system', 'function', 'medium',
  'technology', 'fuel', 'variant', 'modelSupport',
]);

function facetValues(descriptor, key) {
  const taxonomy = descriptor.taxonomy ?? {};
  const plural = {
    industry: 'industries', system: 'systems', function: 'functions',
    medium: 'media', technology: 'technologies',
  };
  if (plural[key]) return taxonomy[plural[key]] ?? [];
  if (key === 'fuel') return (descriptor.variants ?? []).map(item => item.fuel).filter(Boolean);
  if (key === 'variant') return (descriptor.variants ?? []).map(item => item.id);
  if (key === 'modelSupport') return [descriptor.modelSupport?.kind,...(descriptor.variants??[]).map(variant=>variant.modelSupport?.kind)].filter(Boolean);
  return [descriptor[key]].filter(Boolean);
}

/** Deterministic, data-only selection. OR within a facet; AND between facets. */
export function queryScadaMetadata(descriptors, filters = {}) {
  ownDataObject(filters, SCADA_FILTER_KEYS, 'catalog filter');
  const exact = [];
  let tokens = [];
  for (const [key, value] of Object.entries(filters)) {
    if (key === 'query') {
      if (typeof value !== 'string' || value.length > 512) throw new TypeError('Search query must be a string of at most 512 characters.');
      tokens = value.toLocaleLowerCase('en-US').trim().split(/\s+/).filter(Boolean);
      continue;
    }
    if(Array.isArray(value)) {
      if(Object.getPrototypeOf(value)!==Array.prototype || Reflect.ownKeys(value).some(key=>key!=='length' && !/^(0|[1-9][0-9]*)$/.test(String(key)))) {
        throw new TypeError(`${key} must be a plain string array.`);
      }
      for(let index=0;index<value.length;index++) {
        const property=Object.getOwnPropertyDescriptor(value,String(index));
        if(!property || !Object.hasOwn(property,'value'))throw new TypeError(`${key} must contain own data values.`);
      }
    }
    const values = Array.isArray(value) ? value : [value];
    if (!values.length || values.some(item => typeof item !== 'string' || !item || item.length > 100)) {
      throw new TypeError(`${key} must be a string or nonempty string array.`);
    }
    exact.push([key, values]);
  }
  return Object.freeze(descriptors.filter(descriptor => {
    if (!exact.every(([key, values]) => values.some(value => facetValues(descriptor, key).includes(value)))) return false;
    const searchable = [descriptor.type, descriptor.label, descriptor.description,
      ...Object.values(descriptor.taxonomy ?? {}).flat(),
      ...(descriptor.variants ?? []).flatMap(variant => [variant.id, variant.label, variant.fuel, variant.enclosure]),
    ].filter(Boolean).join(' ').toLocaleLowerCase('en-US');
    return tokens.every(token => searchable.includes(token));
  }).sort((a, b) => a.type.localeCompare(b.type, 'en')));
}

export function getScadaMetadataFacets(descriptors) {
  return freezeScadaMetadata(Object.fromEntries(SCADA_FILTER_KEYS
    .filter(key => key !== 'query')
    .map(key => [key, [...new Set(descriptors.flatMap(item => facetValues(item, key)))].sort()])));
}
