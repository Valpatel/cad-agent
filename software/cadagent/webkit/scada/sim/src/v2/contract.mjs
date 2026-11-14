import {TYPE_CONTRACTS} from './type-contracts.mjs';

export const VERSION = 2;
export const CIRCUIT_MODEL_VERSION = VERSION;
export const freeze = value => { if(value && typeof value === 'object' && !Object.isFrozen(value)){Object.values(value).forEach(freeze);Object.freeze(value);}return value; };
export const clone = value => structuredClone(value);
export const clamp = (value,min=0,max=100) => Math.min(max,Math.max(min,value));
export const PARAMETER_BOUNDS = freeze({
  capacity:[0,100],response:[0,1],demand:[0,100],loss:[0,1],pressureGain:[0,100],heatGain:[0,100],warningAt:[0,100],damageRate:[0,10],
  oxygenTransfer:[0,1],tracerConversion:[0,1],uptake:[0,1],mistDuty:[0,100],ventExchange:[0,1],condensation:[0,1],
  cycleFill:[.1,1000],cycleHold:[.1,1000],cycleDrain:[.1,1000],humidityGain:[0,1],lightGain:[0,1],temperatureResponse:[0,1],
});
export const PARAMETER_DEFAULTS = freeze({capacity:60,response:.4,demand:2,loss:0,pressureGain:20,heatGain:20,warningAt:90,damageRate:.1,oxygenTransfer:.1,tracerConversion:.02,uptake:.01,mistDuty:60,ventExchange:.1,condensation:.1,cycleFill:5,cycleHold:3,cycleDrain:5,humidityGain:.1,lightGain:.8,temperatureResponse:.1});
export const ZONE_FIELDS = freeze(['temperature','humidity','light','oxygen']);
export const TRACERS = freeze(['oxygen','nutrient','solids','ph','ec']);
export const CIRCUIT_PARAMETERS=freeze([
  {key:'capacity',label:'Circuit transfer capacity',unit:'toy units / minute',min:0,max:100,default:60},
  {key:'stockScale',label:'Inventory scale',unit:'toy units / inventory point',min:.01,max:1000,default:10},
  {key:'thermalCapacity',label:'Thermal capacity per resource unit',unit:'toy heat units',min:.01,max:100,default:1},
  {key:'loss',label:'Declared transfer loss',unit:'fraction',min:0,max:1,default:0},
  {key:'pressureGain',label:'Illustrative pressure gain',unit:'index',min:0,max:100,default:20},
]);
export const ENERGY_PARAMETERS=freeze([
  {key:'capacity',label:'Conversion / transfer limit',unit:'toy power units',min:0,max:100,default:60},
  {key:'demand',label:'Nominal load request',unit:'toy power units',min:0,max:100,default:2},
  {key:'efficiency',label:'Conversion efficiency',unit:'fraction',min:.001,max:1,default:.9},
]);
export const TRACER_FIELDS=freeze(TRACERS.map(key=>({key,label:({oxygen:'Dissolved oxygen illustration',nutrient:'Nutrient illustration',solids:'Suspended solids illustration',ph:'pH illustration',ec:'Conductivity illustration'})[key],unit:'index',min:0,max:100})));
export const ZONE_FIELD_DEFINITIONS=freeze(ZONE_FIELDS.map(key=>({key,label:`Zone ${key}`,unit:'index',min:0,max:100})));
export function channel(medium){
  if(medium==='ground')return 'reference';
  if(['electricity','electrical','power','mechanical','light','optical'].includes(medium))return 'energy';
  if(['data','signal','control','network','communication'].includes(medium))return 'data';
  if(['measurement','sensor'].includes(medium))return 'measurement';
  if(['thermal','heat','energy'].includes(medium))return 'thermal';
  return 'resource';
}
export function domain(descriptor,portId){const port=descriptor.ports.find(item=>item.id===portId);return descriptor.powerDomains?.[portId] ?? (port?.medium==='mechanical'?'mechanical':['light','optical'].includes(port?.medium)?'optical':'ac');}
const descriptors=new Map(TYPE_CONTRACTS.map(item=>[item.type,item]));
export function getV2Descriptor(type,variant){const item=descriptors.get(type);if(!item)throw new RangeError(`No version 2 descriptor: ${type}`);if(variant){const selected=item.resolvedVariants?.[variant];if(!selected)throw new RangeError(`Unknown ${type} variant: ${variant}`);return selected;}return item;}
export const V2_TYPE_CONTRACTS=freeze(TYPE_CONTRACTS);
const species=medium=>['liquid','steam','thermal-fluid'].includes(medium)?'water':medium==='air'?'air':medium;

function circuitGroups(d){
  if(d.circuits.length)return d.circuits;
  if(d.type==='heat-exchanger')return [{id:'hot',ports:['hot-in','hot-out'],fluid:'water'},{id:'cold',ports:['cold-in','cold-out'],fluid:'water'}];
  const resource=d.ports.filter(port=>channel(port.medium)==='resource'), groups=new Map();
  for(const port of resource){const fuel=port.id==='fuel'?'fuel':port.id==='liquid-fuel'?'fuel-liquid':port.id==='solid-fuel'?'fuel-solid':null;const id=fuel??(port.id==='exhaust'?'exhaust':species(port.medium));if(!groups.has(id))groups.set(id,{id,ports:[],fluid:fuel?(fuel==='fuel'?'fuel-gas':fuel):species(port.medium)});groups.get(id).ports.push(port.id);}
  return [...groups.values()];
}

export function createV2Component(type,{variant}={}){
  const d=getV2Descriptor(type,variant),groups=circuitGroups(d), circuits={};
  for(const group of groups){
    const ports=group.ports.filter(id=>d.ports.some(port=>port.id===id&&channel(port.medium)==='resource'));
    if(!ports.length)continue;
    circuits[group.id]={ports,medium:d.ports.find(port=>port.id===ports[0]).medium,fluid:group.fluid??'water',role:'passage',parameters:{capacity:60,stockScale:10,thermalCapacity:1,loss:0,pressureGain:20},initial:{inventory:50,temperature:20,pressure:10,tracers:{oxygen:60,nutrient:50,solids:20,ph:50,ec:50}}};
  }
  const model=d.family??'processor', initial={enabled:true,open:!['breaker','hv-circuit-breaker','disconnect-switch','earthing-switch'].includes(type),load:60,damage:0,mode:'forward',rodPosition:30};
  const result={model,parameters:{...PARAMETER_DEFAULTS},initial,circuits,thermalLinks:[],assumptions:['All version 2 quantities and coefficients are editable normalized teaching assumptions. No hidden bench supply.']};
  if(variant)result.variant=variant;
  if(Object.keys(circuits).length)result.presentation={primaryCircuit:Object.keys(circuits)[0]};
  for(const[name,c]of Object.entries(circuits))if(name.startsWith('fuel')&&c.ports.every(id=>d.ports.find(p=>p.id===id).direction==='in')){c.role='sink';c.initial.inventory=0;}
  if(['storage','reservoir'].includes(model)||d.visualFields.level)for(const c of Object.values(circuits))c.role='storage';
  const powerPorts=d.ports.filter(p=>channel(p.medium)==='energy');
  const incoming=powerPorts.filter(p=>p.direction!=='out').map(p=>p.id),outgoing=powerPorts.filter(p=>p.direction!=='in').map(p=>p.id);
  if(powerPorts.length){
    let role='load',inputs=incoming,outputs=outgoing;
    if(['generator','source','solar-collector','marine-generator','thermal-receiver','environment-generator'].includes(model)||['solar-panel','wind-turbine','fuel-cell'].includes(type))role='source';
    if(['prime-mover','hydro-prime-mover','reversible-prime-mover'].includes(model))role='prime-mover';
    if(['power-converter','shaft-converter','excitation'].includes(model)||['motor','excitation-system'].includes(type))role='converter';
    if(['switch','switchgear','electrical-storage','power-relay','power-switch','electrical-bus'].includes(model)||['transformer','busbar','breaker','hv-circuit-breaker','disconnect-switch','earthing-switch','switchgear-panel','gis-bay','automatic-transfer-switch'].includes(type))role='relay';
    if(['battery','ups'].includes(type))role='store';
    if(type==='alternator'){inputs=['shaft'];outputs=['output'];}
    if(role==='relay'&&d.ports.some(p=>p.id==='line')&&d.ports.some(p=>p.id==='load')){inputs=['line'];outputs=['load'];}
    if(type==='automatic-transfer-switch'){inputs=['source-a'];outputs=['load'];initial.mode='source-a';}
    if(type==='earthing-switch'){role='load';inputs=['supply'];outputs=[];}
    if(type==='power-inverter'){inputs=['dc'];outputs=['ac'];}
    if(type==='power-rectifier'){inputs=['ac'];outputs=['dc'];}
    if(type==='reversible-pump-turbine'){inputs=['shaft'];outputs=['shaft'];initial.mode='generating';}
    if(type==='grow-light'){role='converter';inputs=['supply'];outputs=['light'];}
    if(type==='shade-screen'){role='relay';inputs=['light-in'];outputs=['light-out'];}
    result.energy={role,inputs,outputs,capacity:60,demand:2,efficiency:.9};
    if(type==='automatic-transfer-switch')result.energy.modes={'source-a':'forward','source-b':'reverse',off:'idle'};
    if(role==='source'||role==='prime-mover'){
      const fuel=Object.keys(circuits).find(id=>id.startsWith('fuel')), steam=Object.keys(circuits).find(id=>/steam|water/.test(id));
      result.energy.supply=fuel?{kind:'resource',circuit:fuel}:steam&&['steam-turbine','hydro-turbine'].includes(type)?{kind:'thermal',circuit:steam}:['solar-panel','wind-turbine','tidal-turbine','wave-energy-converter','heliostat','parabolic-trough'].includes(type)?{kind:'environment',environment:type.includes('solar')||type==='heliostat'||type==='parabolic-trough'?'light':type.includes('wind')?'wind':type.includes('wave')?'wave':'waterCurrent'}:{kind:'boundary'};
      if(['gas-turbine','fuel-cell'].includes(type))result.energy.requiredCircuits=Object.keys(circuits).filter(name=>name.startsWith('fuel')||/air/.test(name));
    }
    if(role==='store'||type==='reversible-pump-turbine'){result.energy.role='store';result.energy.store={capacity:100,initial:50};result.energy.modes=type==='reversible-pump-turbine'?{generating:'discharge',pumping:'charge',stopped:'idle'}:{discharge:'discharge',charge:'charge',idle:'idle'};initial.mode=type==='reversible-pump-turbine'?'generating':'discharge';}
    if(['power-inverter','power-rectifier','alternator'].includes(type))result.energy.modes={forward:'forward',reverse:'reverse',idle:'idle'};
  }
  if(['nuclear-heat-source','thermal-source','heat-source'].includes(model)||/reactor-vessel|phwr-calandria|gas-cooled-reactor|molten-salt-reactor/.test(type)){
    result.thermalStore={capacity:100,initial:45,loss:.005};result.heatSource={target:'body',capacity:20,control:'rodPosition',inverted:true};
  }
  if(type==='used-fuel-pool'){result.thermalStore={capacity:100,initial:35,loss:.005};result.heatSource={target:'body',capacity:2,control:'load'};}
  if(type==='solar-receiver'){result.thermalStore={capacity:100,initial:20,loss:.01};result.heatSource={target:'body',capacity:40,control:'load',supply:{kind:'energy-input'}};result.energy.demand=40;}
  if(type==='rack-oven'){
    initial.open=false;
    result.thermalStore={capacity:100,initial:20,loss:.02};
    result.heatSource={target:'body',capacity:20,control:'load',supply:{kind:'energy-input'}};
    result.energy.demand=20;
    result.assumptions.push('Electricity accepted at supply is the only heating source; the body store retains heat after disable or supply loss and cools by its editable loss coefficient. Heat readings are 0–100 indices, not degrees or process setpoints.','The door command changes the visible door only. No door interlock, convection, product chemistry, bake recipe, temperature controller or seal-loss equation is modeled. Damage uses the shared editable health rule.');
  }
  if(['media-grow-bed','ebb-flow-table'].includes(type))initial.mode='filling';
  if(d.visualFields.measurement)result.measurement=d.visualFields.measurement.default;
  return result;
}

export function createV2ModelDefinition(system,{seed=12345,environment={},zones={},assumptions=[]}={}){
  const components=Object.fromEntries(system.components.map(item=>[item.id,createV2Component(item.type,{variant:item.variant})]));
  for(const[id,c]of Object.entries(components)){
    const circuits=Object.keys(c.circuits);
    if(c.thermalStore&&circuits.length)c.thermalLinks.push({id:'body-transfer',from:{component:id,circuit:'body'},to:{component:id,circuit:circuits[0]},conductance:.2,maximumTransfer:20,lossFraction:0});
    if(circuits.length===2&&['heat-exchanger','nuclear-steam-generator','surface-condenser','heat-recovery-steam-generator'].includes(system.components.find(item=>item.id===id).type))c.thermalLinks.push({id:'exchange',from:{component:id,circuit:circuits[0]},to:{component:id,circuit:circuits[1]},conductance:.2,maximumTransfer:20,lossFraction:.02});
  }
  return {format:'scada-placeholder-model',version:2,scenarioId:system.system.id,seed,components,connections:{},environment:{ambient:20,light:60,wind:60,wave:60,waterCurrent:60,...environment},zones,assumptions:['All sources, sinks, and environmental inputs are explicitly declared. Model values are normalized indices, not plant operating predictions.',...assumptions]};
}

export function getV2ModelDescriptor(type,{variant}={}){
  const descriptor=getV2Descriptor(type,variant),model=createV2Component(type,{variant});
  const keys=['capacity','response','warningAt','damageRate'];
  if(descriptor.ports.some(p=>['supply','field','auxiliary'].includes(p.id)))keys.push('demand');
  if(['fish-tank','biofilter','dwc-raft-bed'].includes(type))keys.push('oxygenTransfer','uptake');
  if(['biofilter','media-grow-bed'].includes(type))keys.push('tracerConversion');
  if(/bed|channel|table|zone|chamber/.test(type)&&Object.keys(model.circuits).length)keys.push('uptake');
  if(type==='aeroponic-chamber')keys.push('mistDuty');
  if(['media-grow-bed','ebb-flow-table'].includes(type))keys.push('cycleFill','cycleHold','cycleDrain');
  if(type==='greenhouse-vent')keys.push('ventExchange');
  if(type==='grow-light')keys.push('lightGain');
  if(type==='evaporative-pad')keys.push('humidityGain');
  if(type==='dehumidifier')keys.push('condensation');
  const labels={capacity:'Equipment transfer ceiling',response:'Operating response',warningAt:'Stress warning threshold',damageRate:'Seeded stress damage rate',demand:'Auxiliary power request',oxygenTransfer:'Aeration response',tracerConversion:'Solids conversion response',uptake:'Illustrative uptake response',mistDuty:'Mist duty',cycleFill:'Fill phase duration',cycleHold:'Hold phase duration',cycleDrain:'Drain phase duration',ventExchange:'Vent exchange response',lightGain:'Light contribution',humidityGain:'Evaporation response',condensation:'Condensation response'};
  return freeze({...descriptor,version:2,variant:variant??null,
    inputs:[
      {key:'resourceIn',unit:'toy units / minute',description:'Accepted material transfer into the explicitly selected presentation circuit.'},
      {key:'powerIn',unit:'toy power units',description:'Accepted input in the declared AC, DC, mechanical or optical domain.'},
    ],
    outputs:[
      {key:'flow',unit:'toy units / minute',description:'Outgoing material transfer from the selected presentation circuit; inspect circuits for every separate path.'},
      {key:'stock',unit:'index',description:'Presentation-circuit amount divided by its declared stockScale; bounded to 0–100.'},
      {key:'temperature',unit:'index',description:'Stored heat divided by the declared heat capacity, scaled to 0–100.'},
      {key:'powerOut',unit:'toy power units',description:'Delivered output, limited by accepted supply and declared efficiency.'},
      {key:'signal',unit:'index',description:'Last valid explicitly configured observation; valid reports availability.'},
    ],
    parameters:[...new Set(keys)].map(key=>({key,label:labels[key],unit:key.startsWith('cycle')?'toy minutes':['warningAt','mistDuty'].includes(key)?'index':'normalized coefficient',min:PARAMETER_BOUNDS[key][0],max:PARAMETER_BOUNDS[key][1],default:model.parameters[key],assumed:true})),circuitParameters:CIRCUIT_PARAMETERS,energyParameters:ENERGY_PARAMETERS,tracers:TRACER_FIELDS,zoneFields:ZONE_FIELD_DEFINITIONS,failureModes:(descriptor.visualFields.damage?.options??[]).filter(id=>id!=='none').map(id=>({id,label:id.replaceAll('-',' '),description:'Fictional condition; retained until repair.'})),defaultModel:model,assumptions:model.assumptions});
}

/** Separate registries preserve the version 1 contract and make every explicit
 * configuration discoverable without importing the presentation package. */
export const V2_MODEL_DESCRIPTORS=freeze(TYPE_CONTRACTS.map(item=>getV2ModelDescriptor(item.type)));
export const V2_VARIANT_DESCRIPTORS=freeze(TYPE_CONTRACTS.flatMap(item=>item.variants.map(variant=>getV2ModelDescriptor(item.type,{variant:variant.id}))));
export const V2_MODEL_FAMILIES=freeze([...new Set(V2_MODEL_DESCRIPTORS.map(item=>item.defaultModel.model))].sort());
