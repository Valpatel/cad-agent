/**
 * Power-sector visual contracts. No simulation, timers, ratings or IO.
 * Circuit and power-domain metadata supports explicit model/diagram adapters;
 * it does not implement an engineering model or establish material suitability.
 */

function freeze(value) {
  if (value && typeof value === 'object' && !Object.isFrozen(value)) {
    for (const child of Object.values(value)) freeze(child);
    Object.freeze(value);
  }
  return value;
}

function numeric(key, label, defaultValue = 60, unit = '%', max = 100) {
  return {key, label, type: 'number', default: defaultValue, min: 0, max, step: 1, unit};
}

function boolean(key, label, defaultValue = true) {
  return {key, label, type: 'boolean', default: defaultValue};
}

function select(key, label, values, defaultValue = values[0]) {
  return {
    key, label, type: 'select', default: defaultValue,
    options: values.map(value => ({value, label: value.replaceAll('-', ' ')})),
  };
}

export const POWER_VISUAL_FIELDS = freeze({
  active: boolean('active', 'Equipment enabled'),
  running: boolean('running', 'Animate'),
  fault: boolean('fault', 'Fault', false),
  status: select('status', 'Status', ['normal', 'warning', 'offline']),
  load: numeric('load', 'Illustrative output / load'),
  speed: numeric('speed', 'Illustrative driven speed'),
  flow: numeric('flow', 'Supplied circulation'),
  primaryFlow: {...numeric('primaryFlow', 'Primary-side circulation'), shortLabel: 'PRI'},
  secondaryFlow: {...numeric('secondaryFlow', 'Secondary-side circulation'), shortLabel: 'SEC'},
  heat: {...numeric('heat', 'Illustrative thermal index', 45, 'index'), shortLabel: 'HEAT'},
  level: numeric('level', 'Illustrative inventory', 55),
  rodPosition: {...numeric('rodPosition', 'Rod insertion (100 = fully inserted)', 30), shortLabel: 'RODS'},
  position: numeric('position', 'Illustrative tracker position', 50),
  opening: {...numeric('opening', 'Illustrative opening', 100), shortLabel: 'OPEN'},
  pressure: {...numeric('pressure', 'Illustrative pressure index', 45, 'index'), shortLabel: 'PRESS'},
  integrity: {...numeric('integrity', 'Illustrative structural integrity', 100), shortLabel: 'INT'},
  value: numeric('value', 'Illustrative signal index', 42, 'index'),
  field: numeric('field', 'Illustrative excitation field'),
  irradiance: {...numeric('irradiance', 'Illustrative solar resource'), shortLabel: 'SUN'},
  current: numeric('current', 'Illustrative water-current resource', 60, 'index'),
  wave: numeric('wave', 'Illustrative wave resource', 60, 'index'),
  stress: numeric('stress', 'Illustrative surge stress', 5, 'index'),
  steps: numeric('steps', 'Connected capacitor groups', 2, '', 4),
  open: boolean('open', 'Open', false),
  connected: boolean('connected', 'Signal connected'),
  moving: boolean('moving', 'Actuator moving', false),
  tripped: boolean('tripped', 'Trip indication', false),
  automatic: boolean('automatic', 'Automatic control mode'),
});

const COMMON_FIELDS = ['active', 'running', 'fault', 'status'];
const fields = (...keys) => keys.map(key => POWER_VISUAL_FIELDS[key]);
const override = (key, changes) => ({...POWER_VISUAL_FIELDS[key], ...changes});
const port = (id, label, medium, direction, extra = {}) => ({id, label, medium, direction, ...extra});
const supply = () => port('supply', 'Auxiliary power', 'electricity', 'in');
const control = () => port('control', 'Control command', 'data', 'in');
const monitor = () => port('monitor', 'Observation tap', 'measurement', 'out');

function circuit(id, ports, fluid, extra = {}) {
  return {id, ports, fluid, ...extra};
}

function coolantPorts(medium = 'liquid') {
  return [
    port('coolant-in', 'Coolant inlet', medium, 'in'),
    port('coolant-out', 'Coolant outlet', medium, 'out'),
    control(), monitor(),
  ];
}

function switchingPorts() {
  return [
    port('line', 'Line-side circuit', 'electricity', 'bidirectional'),
    port('load', 'Load-side circuit', 'electricity', 'bidirectional'),
    supply(), control(), monitor(),
  ];
}

function measurementPorts() {
  return [
    port('process', 'Observed quantity', 'measurement', 'in'),
    port('signal', 'Measurement signal', 'data', 'out'),
    port('power', 'Instrument power', 'electricity', 'in'),
  ];
}

const FAMILY = {
  thermal: {category: 'power', drawingFamily: 'energy', industries: ['power'], systems: ['thermal-generation']},
  nuclear: {category: 'nuclear', drawingFamily: 'nuclear', industries: ['power', 'nuclear'], systems: ['nuclear-generation']},
  hydro: {category: 'power', drawingFamily: 'energy', industries: ['power', 'water'], systems: ['hydropower']},
  solar: {category: 'power', drawingFamily: 'energy', industries: ['power'], systems: ['solar-generation']},
  marine: {category: 'power', drawingFamily: 'energy', industries: ['power', 'marine'], systems: ['marine-generation']},
  grid: {category: 'power', drawingFamily: 'electrical', industries: ['power', 'industry', 'agriculture'], systems: ['electrical-distribution']},
};

const TECHNOLOGIES = {
  'gas-turbine': ['gas-turbine', 'combustion'],
  'heat-recovery-steam-generator': ['combined-cycle', 'heat-recovery'],
  'surface-condenser': ['steam-cycle', 'heat-exchange'],
  deaerator: ['steam-cycle', 'feedwater-treatment'],
  'cooling-radiator': ['air-cooling'],
  'fuel-pressure-regulator': ['fuel-conditioning'],
  'pwr-reactor-vessel': ['pressurized-water-reactor'],
  'bwr-reactor-vessel': ['boiling-water-reactor'],
  'phwr-calandria': ['pressurized-heavy-water-reactor'],
  'gas-cooled-reactor': ['high-temperature-gas-cooled-reactor'],
  'sodium-reactor-vessel': ['sodium-cooled-fast-reactor'],
  'molten-salt-reactor': ['solid-fuel-salt-cooled-reactor'],
  'nuclear-steam-generator': ['nuclear-heat-exchange', 'steam-cycle'],
  pressurizer: ['pressurized-water-reactor'],
  'containment-structure': ['nuclear-support'],
  'used-fuel-pool': ['spent-fuel-cooling'],
  'control-rod-drive': ['reactor-actuation'],
  'neutron-monitor': ['nuclear-instrumentation'],
  'radiation-monitor': ['radiological-instrumentation'],
  reservoir: ['hydropower', 'water-storage'],
  'intake-gate': ['hydropower'],
  'hydro-turbine': ['hydropower'],
  'reversible-pump-turbine': ['pumped-storage'],
  'power-inverter': ['power-conversion', 'photovoltaic', 'battery-storage'],
  heliostat: ['concentrating-solar-tower'],
  'solar-receiver': ['concentrating-solar-tower'],
  'parabolic-trough': ['concentrating-solar-trough'],
  'tidal-turbine': ['tidal-current'],
  'wave-energy-converter': ['wave-point-absorber'],
  alternator: ['synchronous-machine'],
  'hv-circuit-breaker': ['high-voltage-switching'],
  'disconnect-switch': ['electrical-isolation'],
  'earthing-switch': ['earthing'],
  'current-transformer': ['instrument-transformer'],
  'voltage-transformer': ['instrument-transformer'],
  'surge-arrester': ['surge-protection'],
  'capacitor-bank': ['reactive-support'],
  'shunt-reactor': ['reactive-support'],
  'protection-relay': ['electrical-protection'],
  'switchgear-panel': ['air-insulated-switchgear'],
  'gis-bay': ['gas-insulated-switchgear'],
  'automatic-transfer-switch': ['source-transfer'],
  'excitation-system': ['generator-excitation'],
  'power-rectifier': ['power-conversion', 'hvdc'],
};

function define(spec) {
  const family = FAMILY[spec.family];
  const stateFields = [
    ...fields(...COMMON_FIELDS),
    ...spec.fields,
    select('damage', 'Illustrative physical condition', ['none', ...spec.damage]),
  ];
  return {
    type: spec.type,
    id: spec.type,
    label: spec.label,
    name: spec.label,
    category: family.category,
    drawingFamily: family.drawingFamily,
    description: spec.description,
    ports: spec.ports,
    stateFields,
    defaultState: Object.fromEntries(stateFields.map(field => [field.key, field.default])),
    circuits: spec.circuits ?? [],
    powerDomains: spec.powerDomains ?? {},
    modelFamily: spec.modelFamily,
    variants: spec.variants ?? [],
    defaultVariant: spec.defaultVariant ?? spec.variants?.[0]?.id ?? null,
    taxonomy: {
      family: spec.family,
      industries: family.industries,
      systems: spec.systems ?? family.systems,
      functions: spec.functions ?? [],
      technologies: TECHNOLOGIES[spec.type] ?? [spec.family],
      media: [...new Set(spec.ports.map(item => item.medium))],
      keywords: spec.keywords ?? [],
    },
    evidence: spec.evidence,
    modelSupport: {
      kind: 'visual-only',
      description: 'Presentation only, with no physics or process simulation. A separate explicit placeholder or external model supplies all state.',
    },
    provenance: 'Original illustrative artwork planned from named structural references; not a vendor or verified plant drawing.',
  };
}

const reactorFields = fields('load', 'heat', 'flow', 'level', 'rodPosition');
const reactorDamage = ['leaking', 'cooling-loss', 'overheated'];
const instrumentDamage = ['drift', 'broken', 'disconnected'];

export const SCADA_POWER_DEFINITIONS = freeze([
  define({
    type: 'gas-turbine', label: 'Combustion gas turbine', family: 'thermal', modelFamily: 'prime-mover',
    description: 'Compressor, combustion and turbine sections with an explicit shaft output and exhaust path.',
    ports: [port('air', 'Combustion air', 'air', 'in'), port('fuel', 'Fuel gas', 'gas', 'in'),
      port('exhaust', 'Turbine exhaust', 'gas', 'out'), port('shaft', 'Shaft output', 'mechanical', 'out'), supply(), control()],
    fields: fields('load', 'speed', 'flow', 'heat'),
    damage: ['blade-damage', 'bearing-fault', 'overheated', 'fuel-leak'],
    circuits: [circuit('fuel', ['fuel'], 'fuel-gas'), circuit('air-exhaust', ['air', 'exhaust'], 'combustion-gas')],
    powerDomains: {shaft: 'mechanical', supply: 'ac'}, functions: ['produce-shaft-power'], evidence: ['P01'],
  }),
  define({
    type: 'heat-recovery-steam-generator', label: 'Heat recovery steam generator', family: 'thermal', modelFamily: 'heat-exchanger',
    description: 'Exhaust duct and steam-water tube banks, with physically separate primary and secondary flow lanes.',
    ports: [port('exhaust-in', 'Hot exhaust inlet', 'gas', 'in'), port('exhaust-out', 'Exhaust outlet', 'gas', 'out'),
      port('feedwater', 'Feedwater inlet', 'liquid', 'in'), port('steam', 'Steam outlet', 'steam', 'out'), control(), monitor()],
    fields: fields('primaryFlow', 'secondaryFlow', 'level', 'heat'), damage: ['tube-leak', 'fouled', 'overheated'],
    circuits: [circuit('exhaust', ['exhaust-in', 'exhaust-out'], 'combustion-gas'),
      circuit('secondary', ['feedwater', 'steam'], 'secondary-water', {phaseChange: true})],
    functions: ['recover-heat', 'generate-steam'], evidence: ['P01'],
  }),
  define({
    type: 'surface-condenser', label: 'Surface condenser', family: 'thermal', modelFamily: 'heat-exchanger',
    description: 'Condensing steam shell, condensate inventory and a separate cooling-water tube circuit.',
    ports: [port('steam', 'Steam inlet', 'steam', 'in'), port('condensate', 'Condensate outlet', 'liquid', 'out'),
      port('cooling-in', 'Cooling-water inlet', 'liquid', 'in'), port('cooling-out', 'Cooling-water outlet', 'liquid', 'out'), monitor()],
    fields: fields('primaryFlow', 'secondaryFlow', 'level', 'heat'), damage: ['tube-leak', 'fouled', 'air-ingress'],
    circuits: [circuit('condensing', ['steam', 'condensate'], 'secondary-water', {phaseChange: true}),
      circuit('cooling', ['cooling-in', 'cooling-out'], 'cooling-water')],
    functions: ['reject-heat', 'condense-steam'], evidence: ['P11', 'P15'],
  }),
  define({
    type: 'deaerator', label: 'Feedwater deaerator', family: 'thermal', modelFamily: 'thermal-storage',
    description: 'Feedwater storage vessel and spray section with a separate steam supply and vent.',
    ports: [port('feedwater-in', 'Feedwater inlet', 'liquid', 'in'), port('feedwater-out', 'Feedwater outlet', 'liquid', 'out'),
      port('steam', 'Heating steam', 'steam', 'in'), port('vent', 'Vent outlet', 'gas', 'out'), monitor()],
    fields: fields('level', 'flow', 'heat'), damage: ['leaking', 'corroded', 'vent-blocked'],
    circuits: [circuit('feedwater', ['feedwater-in', 'feedwater-out', 'steam', 'vent'], 'secondary-water', {phaseChange: true})],
    functions: ['condition-feedwater'], evidence: ['P03'],
  }),
  define({
    type: 'cooling-radiator', label: 'Cooling radiator', family: 'thermal', modelFamily: 'heat-rejection',
    description: 'Finned liquid-cooling assembly and fan, with separate coolant and ambient-air paths.',
    ports: [port('coolant-in', 'Warm coolant', 'liquid', 'in'), port('coolant-out', 'Cooled coolant', 'liquid', 'out'),
      port('air-in', 'Ambient air', 'air', 'in'), port('air-out', 'Warm air', 'air', 'out'), supply(), control()],
    fields: fields('speed', 'flow', 'heat'), damage: ['leaking', 'fan-fault', 'fouled'],
    circuits: [circuit('coolant', ['coolant-in', 'coolant-out'], 'cooling-water'), circuit('air', ['air-in', 'air-out'], 'air')],
    powerDomains: {supply: 'ac'}, functions: ['reject-heat'], evidence: ['P02'],
  }),
  define({
    type: 'fuel-pressure-regulator', label: 'Fuel pressure regulator', family: 'thermal', modelFamily: 'valve',
    description: 'Gas regulator body, actuator and pressure indication with continuously supplied opening.',
    ports: [port('inlet', 'Fuel-gas supply', 'gas', 'in'), port('outlet', 'Regulated fuel gas', 'gas', 'out'), control(), monitor()],
    fields: [override('open', {default: true}), ...fields('opening', 'pressure', 'flow')], damage: ['stuck', 'leaking', 'blocked'],
    circuits: [circuit('fuel', ['inlet', 'outlet'], 'fuel-gas')], functions: ['regulate-flow'], evidence: ['P02'],
  }),

  define({
    type: 'pwr-reactor-vessel', label: 'Pressurized-water reactor vessel', family: 'nuclear', modelFamily: 'conceptual-heat-source',
    description: 'Conceptual water-cooled vessel with supplied inventory, circulation, rod insertion and residual thermal state.',
    ports: coolantPorts(), fields: reactorFields, damage: reactorDamage,
    circuits: [circuit('primary', ['coolant-in', 'coolant-out'], 'primary-water')],
    functions: ['supply-conceptual-heat'], evidence: ['P11', 'P12'],
  }),
  define({
    type: 'bwr-reactor-vessel', label: 'Boiling-water reactor vessel', family: 'nuclear', modelFamily: 'conceptual-heat-source',
    description: 'Conceptual vessel with internal steam separation and a direct steam outlet rather than a PWR secondary generator.',
    ports: [port('feedwater', 'Feedwater inlet', 'liquid', 'in'), port('steam', 'Main steam outlet', 'steam', 'out'),
      port('recirculation-in', 'Recirculation return', 'liquid', 'in'), port('recirculation-out', 'Recirculation supply', 'liquid', 'out'), control(), monitor()],
    fields: reactorFields, damage: reactorDamage,
    circuits: [circuit('reactor-water', ['feedwater', 'steam', 'recirculation-in', 'recirculation-out'], 'reactor-water', {phaseChange: true})],
    functions: ['supply-conceptual-heat', 'generate-steam'], evidence: ['P11', 'P12'],
  }),
  define({
    type: 'phwr-calandria', label: 'PHWR calandria and pressure channels', family: 'nuclear', modelFamily: 'conceptual-heat-source',
    description: 'Horizontal pressure channels and moderator inventory; heat-transport and moderator circuits remain separate.',
    ports: [...coolantPorts(), port('moderator-in', 'Moderator return', 'liquid', 'in'), port('moderator-out', 'Moderator supply', 'liquid', 'out')],
    fields: [...fields('load', 'heat', 'flow'), override('level', {label: 'Illustrative moderator inventory'}), ...fields('rodPosition')],
    damage: reactorDamage,
    circuits: [circuit('heat-transport', ['coolant-in', 'coolant-out'], 'heavy-water'),
      circuit('moderator', ['moderator-in', 'moderator-out'], 'heavy-water')],
    functions: ['supply-conceptual-heat'], evidence: ['P15'],
  }),
  define({
    type: 'gas-cooled-reactor', label: 'Gas-cooled reactor concept', family: 'nuclear', modelFamily: 'conceptual-heat-source',
    description: 'Graphite-core and helium-circulation presentation with independent residual thermal indication.',
    ports: coolantPorts('gas'), fields: fields('load', 'heat', 'flow', 'rodPosition'),
    damage: ['leaking', 'circulator-fault', 'overheated'],
    circuits: [circuit('primary', ['coolant-in', 'coolant-out'], 'helium')],
    functions: ['supply-conceptual-heat'], evidence: ['P12', 'P14'],
  }),
  define({
    type: 'sodium-reactor-vessel', label: 'Sodium-cooled reactor concept', family: 'nuclear', modelFamily: 'conceptual-heat-source',
    description: 'Liquid-metal inventory and core presentation; an intermediate heat exchanger is a separately authored asset.',
    ports: coolantPorts('thermal-fluid'), fields: reactorFields, damage: reactorDamage,
    circuits: [circuit('primary', ['coolant-in', 'coolant-out'], 'sodium')],
    functions: ['supply-conceptual-heat'], evidence: ['P12', 'P14'],
  }),
  define({
    type: 'molten-salt-reactor', label: 'Molten-salt reactor concept', family: 'nuclear', modelFamily: 'conceptual-heat-source',
    description: 'Selected solid-fuel, salt-cooled loop concept. Liquid-fuel salt arrangements require a separate future contract; no neutronics are implied.',
    ports: coolantPorts('thermal-fluid'), fields: reactorFields, damage: reactorDamage,
    circuits: [circuit('primary', ['coolant-in', 'coolant-out'], 'salt')],
    variants: [{id: 'solid-fuel-salt-cooled', label: 'Solid fuel / salt coolant'}],
    functions: ['supply-conceptual-heat'], evidence: ['P12', 'P14'],
  }),
  define({
    type: 'nuclear-steam-generator', label: 'Nuclear steam generator', family: 'nuclear', modelFamily: 'heat-exchanger',
    description: 'Primary tube loop and isolated secondary water/steam inventory with independently supplied flow indicators.',
    ports: [port('primary-in', 'Primary hot inlet', 'liquid', 'in'), port('primary-out', 'Primary return', 'liquid', 'out'),
      port('feedwater', 'Secondary feedwater', 'liquid', 'in'), port('steam', 'Secondary steam', 'steam', 'out'), monitor()],
    fields: fields('primaryFlow', 'secondaryFlow', 'level', 'heat'), damage: ['tube-leak', 'fouled', 'corroded'],
    circuits: [circuit('primary', ['primary-in', 'primary-out'], 'primary-water'),
      circuit('secondary', ['feedwater', 'steam'], 'secondary-water', {phaseChange: true})],
    variants: [
      {id: 'water-primary', label: 'Water primary', circuitOverrides: {primary: {fluid: 'primary-water'}}},
      {id: 'heavy-water-primary', label: 'Heavy-water primary', circuitOverrides: {primary: {fluid: 'heavy-water'}}},
      {id: 'helium-primary', label: 'Helium primary',
        portOverrides: {'primary-in': {medium: 'gas'}, 'primary-out': {medium: 'gas'}},
        circuitOverrides: {primary: {fluid: 'helium'}}},
      {id: 'sodium-primary', label: 'Sodium intermediate loop',
        portOverrides: {'primary-in': {medium: 'thermal-fluid'}, 'primary-out': {medium: 'thermal-fluid'}},
        circuitOverrides: {primary: {fluid: 'sodium'}}},
      {id: 'salt-primary', label: 'Salt intermediate loop',
        portOverrides: {'primary-in': {medium: 'thermal-fluid'}, 'primary-out': {medium: 'thermal-fluid'}},
        circuitOverrides: {primary: {fluid: 'salt'}}},
    ],
    functions: ['transfer-heat', 'generate-steam'], evidence: ['P11', 'P12', 'P15'],
  }),
  define({
    type: 'pressurizer', label: 'Pressurizer', family: 'nuclear', modelFamily: 'thermal-storage',
    description: 'Conceptual surge vessel, heater and spray with an explicitly fictional pressure index.',
    ports: [port('surge', 'Primary surge connection', 'liquid', 'bidirectional'), port('spray', 'Spray inlet', 'liquid', 'in'),
      port('relief', 'Relief outlet', 'steam', 'out'), supply(), control(), monitor()],
    fields: fields('level', 'heat', 'pressure'), damage: ['leaking', 'heater-fault', 'relief-stuck'],
    circuits: [circuit('primary', ['surge', 'spray', 'relief'], 'primary-water', {phaseChange: true})],
    powerDomains: {supply: 'ac'}, functions: ['buffer-primary-inventory'], evidence: ['P12'],
  }),
  define({
    type: 'containment-structure', label: 'Containment structure', family: 'nuclear', modelFamily: 'enclosure',
    description: 'Conceptual enclosure with independent integrity, atmosphere and residual thermal indications.',
    ports: [port('ventilation-in', 'Ventilation inlet', 'gas', 'in'), port('ventilation-out', 'Ventilation outlet', 'gas', 'out'),
      port('drain', 'Collection drain', 'liquid', 'out'), monitor(), control()],
    fields: [override('pressure', {default: 10}), ...fields('integrity'), override('flow', {default: 20}), override('heat', {default: 10})],
    damage: ['leaking', 'cracked', 'ventilation-fault'],
    circuits: [circuit('atmosphere', ['ventilation-in', 'ventilation-out'], 'air'), circuit('collection', ['drain'], 'collection-water')],
    functions: ['show-enclosure-condition'], evidence: ['P12', 'P15'],
  }),
  define({
    type: 'used-fuel-pool', label: 'Used-fuel cooling pool', family: 'nuclear', modelFamily: 'thermal-storage',
    description: 'Rack inventory under water with supplied cooling flow and retained heat, separate from a reactor vessel.',
    ports: [port('cooling-in', 'Cooled water return', 'liquid', 'in'), port('cooling-out', 'Cooling-loop supply', 'liquid', 'out'),
      port('makeup', 'Makeup water', 'liquid', 'in'), monitor()],
    fields: [override('level', {default: 70}), ...fields('flow'), override('heat', {default: 30})],
    damage: ['leaking', 'fouled', 'cooling-loss'],
    circuits: [circuit('pool', ['cooling-in', 'cooling-out', 'makeup'], 'pool-water')],
    functions: ['store-inventory', 'remove-retained-heat'], evidence: ['P15'],
  }),
  define({
    type: 'control-rod-drive', label: 'Control-rod drive indicator', family: 'nuclear', modelFamily: 'actuator',
    description: 'Supplied insertion position and drive availability; hold state does not continuously cycle the rods.',
    ports: [supply(), control(), port('position-signal', 'Position feedback', 'data', 'out')],
    fields: fields('rodPosition', 'speed', 'moving'), damage: ['jammed', 'worn', 'power-loss'],
    powerDomains: {supply: 'ac'}, functions: ['show-actuator-position'], evidence: ['P11', 'P15'],
  }),
  define({
    type: 'neutron-monitor', label: 'Neutron monitor concept', family: 'nuclear', modelFamily: 'sensor',
    description: 'Detector channel and fictional signal index; unavailable signals render as unavailable rather than a valid number.',
    ports: measurementPorts(), fields: fields('value', 'connected'), damage: instrumentDamage,
    powerDomains: {power: 'dc'}, functions: ['observe-signal'], evidence: ['P15'],
  }),
  define({
    type: 'radiation-monitor', label: 'Radiation monitor concept', family: 'nuclear', modelFamily: 'sensor',
    description: 'Area-monitor enclosure and fictional index with no radiation dose or activity calibration.',
    ports: measurementPorts(), fields: fields('value', 'connected'), damage: instrumentDamage,
    powerDomains: {power: 'dc'}, functions: ['observe-signal'], evidence: ['P15'],
  }),

  define({
    type: 'reservoir', label: 'Water reservoir', family: 'hydro', modelFamily: 'storage',
    description: 'Open water inventory with a shoreline and intake, distinct from a pressure vessel or gas holder.',
    ports: [port('inlet', 'Water inflow', 'liquid', 'in'), port('outlet', 'Water release', 'liquid', 'out'),
      port('spillway', 'Spill outlet', 'liquid', 'out'), port('connection', 'Reversible water connection', 'liquid', 'bidirectional', {optional:true}), monitor()],
    fields: [POWER_VISUAL_FIELDS.level, override('flow', {default: 40})], damage: ['leaking', 'contaminated', 'embankment-damage'],
    circuits: [circuit('water', ['inlet', 'outlet', 'spillway', 'connection'], 'water')], functions: ['store-inventory'], evidence: ['P05', 'P06'],
  }),
  define({
    type: 'intake-gate', label: 'Hydraulic intake gate', family: 'hydro', modelFamily: 'valve',
    description: 'Moving gate plate and visible aperture controlling a water intake.',
    ports: [port('inlet', 'Upstream water', 'liquid', 'in'), port('outlet', 'Downstream water', 'liquid', 'out'), supply(), control()],
    fields: [override('open', {default: true}), POWER_VISUAL_FIELDS.opening], damage: ['stuck', 'corroded', 'obstructed'],
    circuits: [circuit('water', ['inlet', 'outlet'], 'water')], powerDomains: {supply: 'ac'}, functions: ['regulate-flow'], evidence: ['P05', 'P06'],
  }),
  define({
    type: 'hydro-turbine', label: 'Hydraulic turbine', family: 'hydro', modelFamily: 'prime-mover',
    description: 'Water runner and casing with distinct water and mechanical output paths.',
    ports: [port('inlet', 'Water inlet', 'liquid', 'in'), port('outlet', 'Tailwater outlet', 'liquid', 'out'),
      port('shaft', 'Shaft output', 'mechanical', 'out'), control()],
    fields: fields('speed', 'load', 'flow'), damage: ['cavitating', 'bearing-fault', 'leaking'],
    circuits: [circuit('water', ['inlet', 'outlet'], 'water')], powerDomains: {shaft: 'mechanical'}, functions: ['produce-shaft-power'], evidence: ['P05', 'P06'],
  }),
  define({
    type: 'reversible-pump-turbine', label: 'Reversible pump-turbine', family: 'hydro', modelFamily: 'reversible-prime-mover',
    description: 'One physical unit with explicit pumping, generating and stopped modes, not simultaneous free production.',
    ports: [port('upper', 'Upper-reservoir connection', 'liquid', 'bidirectional'), port('lower', 'Lower-reservoir connection', 'liquid', 'bidirectional'),
      port('shaft', 'Reversible shaft connection', 'mechanical', 'bidirectional'), control()],
    fields: [...fields('speed', 'load', 'flow'), select('mode', 'Operating mode', ['generating', 'pumping', 'stopped'])],
    damage: ['cavitating', 'bearing-fault', 'leaking'], circuits: [circuit('water', ['upper', 'lower'], 'water')],
    powerDomains: {shaft: 'mechanical'}, functions: ['produce-shaft-power', 'pump-water'], evidence: ['P05', 'P19'],
  }),
  define({
    type: 'power-inverter', label: 'DC/AC power inverter', family: 'grid', modelFamily: 'power-converter',
    description: 'DC/AC conversion cabinet; reverse flow requires the explicit bidirectional variant.',
    ports: [port('dc', 'DC circuit', 'electricity', 'bidirectional'), port('ac', 'AC circuit', 'electricity', 'bidirectional'), control(), monitor()],
    fields: [...fields('load'), select('direction', 'Conversion direction', ['forward', 'idle'])],
    damage: ['semiconductor-fault', 'overheated', 'cooling-loss'], powerDomains: {dc: 'dc', ac: 'ac'},
    variants: [{id: 'dc-to-ac', label: 'DC to AC', allowedDirections: ['forward', 'idle']},
      {id: 'bidirectional', label: 'Bidirectional converter', allowedDirections: ['forward', 'reverse', 'idle']}],
    functions: ['convert-power'], evidence: ['P18', 'P20'],
  }),
  define({
    type: 'heliostat', label: 'Heliostat mirror', family: 'solar', modelFamily: 'solar-collector',
    description: 'Two-axis mirror with a supplied position and independent sunlight resource, separate from PV generation.',
    ports: [port('optical', 'Reflected optical energy', 'optical', 'out'), supply(), control()],
    fields: fields('position', 'irradiance'), damage: ['misaligned', 'soiled', 'drive-fault'],
    powerDomains: {supply: 'ac'}, functions: ['collect-solar-heat'], evidence: ['P17'],
  }),
  define({
    type: 'solar-receiver', label: 'Solar tower receiver', family: 'solar', modelFamily: 'heat-source',
    description: 'Elevated receiver absorbs a separately supplied optical input and heats a circulating fluid.',
    ports: [port('optical', 'Collected optical energy', 'optical', 'in'), port('fluid-in', 'Cool fluid return', 'thermal-fluid', 'in'),
      port('fluid-out', 'Heated fluid supply', 'thermal-fluid', 'out'), monitor()],
    fields: fields('flow', 'heat'), damage: ['leaking', 'fouled', 'overheated'],
    circuits: [circuit('transfer-fluid', ['fluid-in', 'fluid-out'], 'heat-transfer-fluid')], functions: ['collect-solar-heat'], evidence: ['P17'],
  }),
  define({
    type: 'parabolic-trough', label: 'Parabolic-trough collector', family: 'solar', modelFamily: 'solar-collector',
    description: 'Curved linear mirror and receiver tube with independent tracking, resource and fluid states.',
    ports: [port('fluid-in', 'Cool fluid return', 'thermal-fluid', 'in'), port('fluid-out', 'Heated fluid supply', 'thermal-fluid', 'out'), supply(), control()],
    fields: fields('position', 'irradiance', 'flow', 'heat'), damage: ['soiled', 'leaking', 'drive-fault'],
    circuits: [circuit('transfer-fluid', ['fluid-in', 'fluid-out'], 'heat-transfer-fluid')], powerDomains: {supply: 'ac'},
    functions: ['collect-solar-heat'], evidence: ['P17'],
  }),
  define({
    type: 'tidal-turbine', label: 'Tidal-current turbine', family: 'marine', modelFamily: 'environment-generator',
    description: 'Submerged rotor with environmental current distinct from enabled generation.',
    ports: [port('output', 'Electrical collection', 'electricity', 'out'), control(), monitor()],
    fields: [...fields('speed', 'load', 'current'), select('direction', 'Water-current direction', ['flood', 'ebb', 'stopped'])],
    damage: ['blade-damage', 'fouled', 'bearing-fault'], powerDomains: {output: 'ac'}, functions: ['produce-electricity'], evidence: ['P22'],
  }),
  define({
    type: 'wave-energy-converter', label: 'Wave point absorber', family: 'marine', modelFamily: 'environment-generator',
    description: 'Buoy and power-takeoff mechanism; environmental wave movement is independent of the electrical enable flag.',
    ports: [port('output', 'Electrical collection', 'electricity', 'out'), control(), monitor()],
    fields: fields('load', 'wave'), damage: ['mooring-damage', 'seal-leak', 'pto-fault'],
    powerDomains: {output: 'ac'}, functions: ['produce-electricity'], evidence: ['P22'],
  }),

  define({
    type: 'alternator', label: 'Synchronous alternator', family: 'grid', modelFamily: 'shaft-converter',
    description: 'A shaft-to-electrical machine, distinct from the existing fuelled generator package.',
    ports: [port('shaft', 'Mechanical shaft', 'mechanical', 'bidirectional'), port('field', 'DC excitation', 'electricity', 'in'),
      port('output', 'AC electrical circuit', 'electricity', 'bidirectional'), control(), monitor()],
    fields: fields('load', 'speed', 'heat', 'field'), damage: ['winding-fault', 'bearing-fault', 'overheated'],
    powerDomains: {shaft: 'mechanical', field: 'dc', output: 'ac'},
    variants: [{id: 'generator', label: 'Generator'}, {id: 'motor-generator', label: 'Reversible motor-generator'}],
    functions: ['convert-shaft-power'], evidence: ['P06', 'P07'],
  }),
  define({
    type: 'hv-circuit-breaker', label: 'High-voltage circuit breaker', family: 'grid', modelFamily: 'switch',
    description: 'Outdoor interruption poles with visible contact state and a distinct control mechanism.',
    ports: switchingPorts(), fields: fields('open', 'load'), damage: ['stuck', 'contact-wear', 'insulation-fault'],
    powerDomains: {line: 'ac', load: 'ac', supply: 'dc'}, functions: ['interrupt-circuit'], evidence: ['P08', 'P09'],
  }),
  define({
    type: 'disconnect-switch', label: 'Air-break disconnect switch', family: 'grid', modelFamily: 'switch',
    description: 'Visible isolating blade and insulators, distinct from a circuit breaker interruption chamber.',
    ports: switchingPorts(), fields: fields('open', 'load'), damage: ['stuck', 'corroded', 'contact-wear'],
    powerDomains: {line: 'ac', load: 'ac', supply: 'dc'}, functions: ['isolate-circuit'], evidence: ['P10'],
    variants: [
      {id: 'ac-isolator', label: 'AC isolation', powerDomains: {line: 'ac', load: 'ac'}},
      {id: 'dc-isolator', label: 'DC isolation', powerDomains: {line: 'dc', load: 'dc'}},
    ],
  }),
  define({
    type: 'earthing-switch', label: 'Earthing switch', family: 'grid', modelFamily: 'ground-switch',
    description: 'Grounding blade and earth termination; open means a physically broken ground connection.',
    ports: [port('circuit', 'Circuit connection', 'electricity', 'bidirectional'), port('earth', 'Earth connection', 'ground', 'bidirectional'), control(), supply()],
    fields: [override('open', {default: true})], damage: ['stuck', 'corroded', 'contact-wear'],
    powerDomains: {circuit: 'ac', supply: 'dc'}, functions: ['show-ground-connection'], evidence: ['P10'],
  }),
  define({
    type: 'current-transformer', label: 'Current transformer', family: 'grid', modelFamily: 'sensor',
    description: 'Instrument-transformer measurement tap and signal output, not a power-consuming feeder.',
    ports: measurementPorts(), fields: fields('value', 'connected'), damage: ['drift', 'broken', 'insulation-fault'],
    powerDomains: {power: 'dc'}, functions: ['observe-current'], evidence: ['P10'],
  }),
  define({
    type: 'voltage-transformer', label: 'Voltage transformer', family: 'grid', modelFamily: 'sensor',
    description: 'Voltage-sensing instrument transformer with a separate low-energy observation output.',
    ports: measurementPorts(), fields: fields('value', 'connected'), damage: ['drift', 'broken', 'insulation-fault'],
    powerDomains: {power: 'dc'}, functions: ['observe-voltage'], evidence: ['P10'],
  }),
  define({
    type: 'surge-arrester', label: 'Surge arrester', family: 'grid', modelFamily: 'surge-protection',
    description: 'Insulated arrester column and earth lead with supplied stress and degradation indications.',
    ports: [port('line', 'Protected circuit', 'electricity', 'bidirectional'), port('earth', 'Earth connection', 'ground', 'bidirectional'), monitor()],
    fields: fields('stress'), damage: ['degraded', 'insulation-fault', 'overheated'],
    powerDomains: {line: 'ac'}, functions: ['show-surge-protection'], evidence: ['P09', 'P10'],
  }),
  define({
    type: 'capacitor-bank', label: 'Switched capacitor bank', family: 'grid', modelFamily: 'reactive-support',
    description: 'Four visible capacitor groups and switching state with illustrative reactive-support activity.',
    ports: [port('bus', 'AC bus connection', 'electricity', 'bidirectional'), control(), monitor()],
    fields: fields('open', 'load', 'steps'), damage: ['failed-cell', 'overheated', 'insulation-fault'],
    powerDomains: {bus: 'ac'}, functions: ['show-reactive-support'], evidence: ['P10'],
  }),
  define({
    type: 'shunt-reactor', label: 'Shunt reactor', family: 'grid', modelFamily: 'reactive-support',
    description: 'Reactor winding assembly, bus connection and residual thermal state, not a nuclear reactor.',
    ports: [port('bus', 'AC bus connection', 'electricity', 'bidirectional'), control(), monitor()],
    fields: fields('open', 'load', 'heat'), damage: ['winding-fault', 'overheated', 'insulation-fault'],
    powerDomains: {bus: 'ac'}, functions: ['show-reactive-support'], evidence: ['P09', 'P10'],
  }),
  define({
    type: 'protection-relay', label: 'Protection relay', family: 'grid', modelFamily: 'controller',
    description: 'Measurement input, communications and trip output with no implied certified protection curve.',
    ports: [port('measurement', 'Sampled measurement signal', 'data', 'in'), port('trip', 'Trip command', 'data', 'out'),
      port('network', 'Communications', 'data', 'bidirectional'), supply()],
    fields: fields('value', 'connected', 'tripped'), damage: ['drift', 'comms-loss', 'power-loss'],
    powerDomains: {supply: 'dc'}, functions: ['show-protection-control'], evidence: ['P09', 'P10'],
  }),
  define({
    type: 'switchgear-panel', label: 'Metal-clad switchgear panel', family: 'grid', modelFamily: 'switch',
    description: 'Cabinet, visible circuit status and relay compartment with power and control connections kept distinct.',
    ports: switchingPorts(), fields: fields('open', 'load', 'connected'), damage: ['contact-wear', 'insulation-fault', 'overheated'],
    powerDomains: {line: 'ac', load: 'ac', supply: 'dc'}, functions: ['switch-circuit'], evidence: ['P08', 'P10'],
  }),
  define({
    type: 'gis-bay', label: 'Gas-insulated switchgear bay', family: 'grid', modelFamily: 'switch',
    description: 'Enclosed switchgear modules with a fictional insulating-gas pressure index and contact status.',
    ports: switchingPorts(), fields: [...fields('open', 'load'), override('pressure', {default: 60})],
    damage: ['gas-leak', 'contact-wear', 'insulation-fault'],
    powerDomains: {line: 'ac', load: 'ac', supply: 'dc'}, functions: ['switch-circuit'], evidence: ['P08', 'P10'],
  }),
  define({
    type: 'automatic-transfer-switch', label: 'Automatic transfer switch', family: 'grid', modelFamily: 'transfer-switch',
    description: 'Two mutually selected source paths and a common load output; off disconnects both sources.',
    ports: [port('source-a', 'Source A', 'electricity', 'in'), port('source-b', 'Source B', 'electricity', 'in'),
      port('load', 'Selected-source output', 'electricity', 'out'), supply(), control()],
    fields: [select('source', 'Selected source', ['a', 'b', 'off']), ...fields('load', 'automatic')],
    damage: ['stuck', 'contact-wear', 'control-fault'], powerDomains: {'source-a': 'ac', 'source-b': 'ac', load: 'ac', supply: 'dc'},
    functions: ['select-power-source'], evidence: ['P02', 'P20'],
  }),
  define({
    type: 'excitation-system', label: 'Generator excitation system', family: 'grid', modelFamily: 'power-controller',
    description: 'Power stage and regulator cabinet with a separate DC field output and feedback connection.',
    ports: [supply(), port('field', 'DC excitation output', 'electricity', 'out'),
      port('feedback', 'Generator feedback', 'measurement', 'in'), control()],
    fields: fields('load', 'field', 'connected'), damage: ['field-loss', 'power-loss', 'overheated'],
    powerDomains: {supply: 'ac', field: 'dc'}, functions: ['supply-excitation'], evidence: ['P07'],
  }),
  define({
    type: 'power-rectifier', label: 'AC/DC rectifier', family: 'grid', modelFamily: 'power-converter',
    description: 'AC input and DC output conversion cabinet; this contract does not silently allow reverse power.',
    ports: [port('ac', 'AC supply', 'electricity', 'in'), port('dc', 'DC output', 'electricity', 'out'), control(), monitor()],
    fields: [...fields('load'), select('direction', 'Conversion state', ['forward', 'idle'])],
    damage: ['semiconductor-fault', 'overheated', 'cooling-loss'], powerDomains: {ac: 'ac', dc: 'dc'},
    functions: ['convert-power'], evidence: ['P09', 'P10'],
  }),
]);

/** Planned optional additions; never mutate the original descriptor in place. */
export const EXISTING_POWER_PORT_ADDITIONS = freeze({
  generator: [port('liquid-fuel', 'Liquid fuel supply', 'liquid', 'in'), port('heat', 'Recovered heat', 'thermal', 'out'),port('air','Combustion air','air','in')],
  boiler: [port('feedwater', 'Feedwater inlet', 'liquid', 'in'), port('solid-fuel', 'Solid fuel feed', 'solids', 'in'),
    port('liquid-fuel', 'Liquid fuel supply', 'liquid', 'in'),port('air','Combustion air','air','in')],
  'fuel-cell': [port('air', 'Oxidant air', 'air', 'in')],
});

export const GENERATOR_VARIANTS = freeze([
  {id: 'natural-gas-enclosed', label: 'Natural gas / enclosed', fuel: 'natural-gas', enclosure: 'cabinet', fuelPort: 'fuel', disabledPorts: ['liquid-fuel']},
  {id: 'natural-gas-industrial', label: 'Natural gas / industrial skid', fuel: 'natural-gas', enclosure: 'skid', fuelPort: 'fuel', disabledPorts: ['liquid-fuel']},
  {id: 'diesel-skid', label: 'Diesel / skid', fuel: 'diesel', enclosure: 'skid', fuelPort: 'liquid-fuel', disabledPorts: ['fuel']},
  {id: 'diesel-enclosed', label: 'Diesel / enclosed', fuel: 'diesel', enclosure: 'cabinet', fuelPort: 'liquid-fuel', disabledPorts: ['fuel']},
  {id: 'gasoline-portable', label: 'Gasoline / portable', fuel: 'gasoline', enclosure: 'portable-frame', fuelPort: 'liquid-fuel', disabledPorts: ['fuel']},
].map(variant=>({
  ...variant,
  componentLabel:`${variant.fuel==='natural-gas'?'Natural-gas':variant.fuel==='diesel'?'Diesel':'Gasoline'} generator ${variant.enclosure==='portable-frame'?'portable frame':variant.enclosure}`,
  description:`Original ${variant.enclosure.replaceAll('-',' ')} packaged-generator illustration with an explicit ${variant.fuel.replaceAll('-',' ')} inlet. Capacity and dynamics come from the external model.`,
  modelSupport:{kind:'visual-only',description:'Original variant artwork with no physics or process simulation. The external model supplies state.'},
  additionalPorts:variant.fuelPort==='liquid-fuel'?[port('liquid-fuel','Liquid fuel supply','liquid','in')]:[],
  circuitOverrides:{fuel:{ports:[variant.fuelPort],fluid:variant.fuel==='natural-gas'?'fuel-gas':variant.fuel}},
})));

export const CAPACITY_PRESETS = freeze([
  {id: 'portable-demo', label: 'Portable demonstration', ratedPowerKW: 5, basis: 'editable illustrative assumption'},
  {id: 'building-demo', label: 'Building demonstration', ratedPowerKW: 100, basis: 'editable illustrative assumption'},
  {id: 'industrial-demo', label: 'Industrial demonstration', ratedPowerKW: 2000, basis: 'editable illustrative assumption'},
]);

export const DRAFT_CONTRACT_NOTES = freeze({
  version: 'power-contract-draft-2',
  stateUnits: 'All new thermal, pressure and nuclear measurement values are fictional normalized indices. No calibrated nuclear units.',
  circuitRule: 'Every resource port belongs to one circuit. Different circuits never exchange mass without an explicit permitted relationship.',
  fluidRule: 'Broad carrier media do not prove material compatibility. Exact fluid identity and supported variants are authored in model v2.',
  modeRule: 'Reversible pump-turbine upper/lower/shaft are bidirectional ports; an explicit model mode chooses one direction at a time.',
  validityRule: 'Broken, offline or disconnected instruments display unavailable, including their generic numeric gauge; drift remains indicated.',
  animationRule: 'Supplied circulation, environmental motion and retained heat are independent of production enable; pause and reduced motion still govern all animation.',
});
