/** Runnable placeholder-model contracts. All quantities are teaching indices,
 * never sizing, protection, process-design or calibrated engineering values. */
import {TYPE_CONTRACTS} from './type-contracts.mjs';
import {getV2ModelDescriptor,createV2ModelDefinition} from './v2/contract.mjs';
export {V2_MODEL_DESCRIPTORS,V2_VARIANT_DESCRIPTORS,V2_MODEL_FAMILIES} from './v2/contract.mjs';

const freeze = value => { if (value && typeof value === 'object' && !Object.isFrozen(value)) { Object.values(value).forEach(freeze); Object.freeze(value); } return value; };
export const MODEL_FAMILIES = freeze(['source','storage','pump','valve','processor','heater','generator','load','controller','sensor','pipe','network','energy-storage','sink']);
const families = {
  storage:['tank','gas-holder','silo'],
  processor:['digester','mixing-tank','reactor','clarifier','filter','gas-treatment','transformer','busbar'],
  heater:['heat-exchanger','boiler','flare'],
  pump:['pump','submersible-pump','dosing-pump','blower','compressor'],
  load:['motor'], generator:['generator','solar-panel'],
  'energy-storage':['battery','ups'],
  valve:['breaker','gate-valve','control-valve','check-valve','relief-valve','butterfly-valve'],
  sensor:['electrical-meter','pressure-transmitter','flow-meter','temperature-sensor','level-sensor','gas-analyzer'],
  controller:['plc-rack','plc-cpu','remote-io'],
  network:['hmi','scada-server','network-switch','radio'], pipe:['pipe','junction'],
};
const familyByType = Object.fromEntries(Object.entries(families).flatMap(([family, types]) => types.map(type => [type, family])));
const parameterInfo = [
  ['capacity','Nominal transfer capacity','toy units / minute',0,100,'Upper normalized throughput or supply capacity. Equal branch sharing is assumed.'],
  ['response','Response rate','1 / toy minute',0,1,'First-order approach to the requested operating level; zero freezes the operating level.'],
  ['demand','Nominal electrical demand','toy power units',0,100,'Requested power when an explicit electrical input exists. No connected input assumes a bench supply.'],
  ['loss','Illustrative conversion loss','fraction',0,1,'A declared discarded-resource or transfer-loss fraction; media are not chemically balanced.'],
  ['pressureGain','Pressure response','normalized index',0,100,'Pressure-index gain at the requested operating level; a blocked outlet adds backpressure.'],
  ['heatGain','Thermal response','normalized index',0,100,'Heating or cooling-index change at operating load; no heat capacity or fluid property is implied.'],
  ['warningAt','Stress warning threshold','normalized index',0,100,'Threshold for the greatest of load, pressure, temperature and supply stress.'],
  ['damageRate','Stress damage growth','damage points / toy minute',0,10,'Seeded damage growth above the warning threshold. Damage 100 latches a fictional failure.'],
];
const defaults = {
  source:[80,.8,10,0,65,10,85,1], storage:[70,.4,5,0,10,0,85,1],
  pump:[80,.8,35,.02,55,12,85,1], valve:[90,1,2,0,0,0,85,1],
  processor:[70,.5,40,.05,10,18,85,1], heater:[70,.4,50,.03,8,55,85,1],
  generator:[90,.65,30,.03,0,35,85,1], load:[75,.8,55,.03,10,15,85,1],
  controller:[100,.8,8,0,0,8,85,1], sensor:[100,.9,3,0,0,2,85,1],
  pipe:[95,1,0,.01,0,0,85,1], network:[100,.9,5,0,0,5,85,1],
  'energy-storage':[85,.5,30,.03,0,15,85,1], sink:[80,.6,55,0,0,5,85,1],
};
const commonAssumptions = [
  'This is a bounded, editable teaching model, not an equipment curve, plant calibration or protection model.',
  'Rates, stocks, pressure, temperature, traffic and power use normalized illustrative units; different media are not stoichiometrically or thermodynamically equivalent.',
  'Directed links describe intended flow. Unconnected process inlets and absent electrical inputs use explicitly assumed bench supplies.',
  'Outgoing capacity is shared in proportion to downstream normalized acceptance; no geometry, friction correlations or engineering sizing is inferred.',
  'Pressure and temperature visual units are mapped from a 0–100 index into the symbol display range, not predicted physical measurements.',
];
function effectFor(mode) {
  if (/leak|ruptur/.test(mode)) return 'leak';
  if (/overheat|burnt|refractory/.test(mode)) return 'overheat';
  if (/comms|io-fault|power-loss|short-circuit|broken/.test(mode)) return 'disconnect';
  if (/drift|fouled|worn|corroded|blade-damage|membrane-damage|stack-damage/.test(mode)) return 'degrade';
  if (/fuel-starved/.test(mode)) return 'starve';
  return 'block';
}
function descriptor(contract) {
  const family = contract.family ?? familyByType[contract.type];
  if (!MODEL_FAMILIES.includes(family)) throw new Error(`A runnable model family is required for ${contract.type}.`);
  const parameters = parameterInfo.map(([key,label,unit,min,max,description], index) => ({key,label,unit,min,max,default:defaults[family][index],description,assumed:true}));
  const damageModes = contract.visualFields.damage?.options?.filter(mode => mode !== 'none') ?? ['failed'];
  const failureModes = damageModes.map(id => ({id,label:id.replaceAll('-', ' '),effect:effectFor(id),initialDamage:/ruptur|burnt/.test(id) ? 95 : 60,description:`Fictional ${id} condition. The model latches this fault, reduces availability and retains damage until repair.`}));
  const inventory = Boolean(contract.visualFields.level) && family !== 'sensor';
  const powerRelay = ['transformer','busbar','breaker','motor'].includes(contract.type);
  const cooling = ['chiller','cooling-tower','fan','heat-exchanger'].includes(contract.type);
  const initial = {enabled:true,open:contract.type !== 'breaker',load:60,level:60,inventory:60,temperature:contract.visualFields.temperature ? 50 : 20,pressure:15,failed:false,damage:0};
  return {...contract, family, inventory, powerRelay, cooling,
    inputs:[
      {key:'resourceIn',unit:'toy units / minute',description:'Material-like inputs; excludes electrical, data, measurement and heat-only links.'},
      {key:'powerIn',unit:'toy power units',description:'Explicit electrical or mechanical supply, if connected.'},
      {key:'signalIn',unit:'0–100 signal index',description:'Sensor readings and controller commands, if connected.'},
      {key:'heatIn',unit:'thermal index',description:'Illustrative heat-only coupling; never adds material stock.'},
    ],
    outputs:[
      {key:'flow',unit:'toy units / minute',description:'Actual outgoing material-like throughput after topology and availability gates.'},
      {key:'stock',unit:'0–100 inventory index',description:inventory || family === 'energy-storage' ? 'Bounded stored resource, updated from inflow, outflow and leakage.' : 'No retained resource; reports zero.'},
      {key:'pressure',unit:'0–100 pressure index',description:'Illustrative inherited pressure and blocked-outlet response.'},
      {key:'temperature',unit:'0–100 thermal index',description:'Illustrative thermal lag toward load and connected heat sources.'},
      {key:'power',unit:'toy power units',description:'Supplied or consumed electrical/mechanical throughput.'},
      {key:'signal',unit:'0–100 signal index',description:'Measured or controlled output; communication faults can make it unavailable.'},
      {key:'damage',unit:'0–100 damage index',description:'Seeded cumulative stress damage, separate from the symbol damage enum.'},
    ],
    parameters, failureModes,
    assumptions:[...commonAssumptions, inventory ? 'Stock changes by one tenth of normalized net flow per toy minute; this arbitrary scale keeps demo inventories readable.' : 'This component has no physical hold-up unless its model explicitly declares stock.', ['sensor','controller','network'].includes(family) ? 'Telemetry and controls use a toy fail-safe rule: missing upstream communication makes dependent control output unavailable.' : 'A supplied operating level controls normalized capacity; on/off commands and latched faults take effect immediately.'],
    defaultModel:{kind:family,parameters:Object.fromEntries(parameters.map(parameter => [parameter.key,parameter.default])),initial,assumptions:['All default values are editable normalized demonstration guesses.']},
  };
}
export const MODEL_DESCRIPTORS = freeze(TYPE_CONTRACTS.map(descriptor));
const byType = new Map(MODEL_DESCRIPTORS.map(item => [item.type,item]));
export function getModelDescriptor(type, {version=1,variant}={}) { if(version===2)return getV2ModelDescriptor(type,{variant});if(version!==1)throw new RangeError('Supported model versions are 1 and 2.');const result=byType.get(type); if(!result)throw new RangeError(`No version 1 placeholder model is registered for ${type}; select version 2 for expanded types.`); return result; }
export function createModelDefinition(systemDefinition, {seed = 12345, assumptions = [], version=1,...options} = {}) {
  if(version===2)return createV2ModelDefinition(systemDefinition,{seed,assumptions,...options});
  if(version!==1)throw new RangeError('Supported model versions are 1 and 2.');
  return {format:'scada-placeholder-model',version:1,scenarioId:systemDefinition.system.id,seed,components:Object.fromEntries(systemDefinition.components.map(component => [component.id,structuredClone(getModelDescriptor(component.type).defaultModel)])),assumptions:[...assumptions]};
}
