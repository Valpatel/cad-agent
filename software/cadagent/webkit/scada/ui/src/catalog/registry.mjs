/** Pure equipment descriptors and visual-state normalization; no SVG, DOM, clock or IO. */
import {SCADA_EXTENSION_DEFINITIONS,EXISTING_DAMAGE_PROFILES,damageField} from './definitions/industrial.mjs';
import {SCADA_POWER_DEFINITIONS,EXISTING_POWER_PORT_ADDITIONS,GENERATOR_VARIANTS} from './definitions/power.mjs';
import {SCADA_AGRICULTURE_DEFINITIONS} from './definitions/agriculture.mjs';
import {addScadaTaxonomy,ownDataObject,resolveScadaVariant} from './selection.mjs';
import {addUtilityVariants} from './utility-variants.mjs';

const freeze=value=>{if(value&&typeof value==='object'&&!Object.isFrozen(value)){Object.values(value).forEach(freeze);Object.freeze(value);}return value;};
const bool=(key,label,value=true)=>({key,label,type:'boolean',default:value});
const number=(key,label,value,min=0,max=100,unit='%')=>({key,label,type:'number',default:value,min,max,step:1,unit});
const COMMON=[bool('active','Active'),bool('running','Animate'),bool('fault','Fault',false),{key:'status',label:'Status',type:'select',default:'normal',options:[{value:'normal',label:'Normal'},{value:'warning',label:'Warning'},{value:'offline',label:'Offline'}]}];
const LEVEL=number('level','Illustrative fill',55),LOAD=number('load','Illustrative load',60),OPEN=bool('open','Open'),OPENING=number('opening','Illustrative valve opening',100),CONNECTED=bool('connected','Connected'),VALUE=number('value','Illustrative reading',42,-9999,9999,'');
const port=(id,label,medium,direction)=>({id,label,medium,direction});
const LIQUID=[port('inlet','Inlet','liquid','in'),port('outlet','Outlet','liquid','out')];
const GAS=[port('inlet','Gas inlet','gas','in'),port('outlet','Gas outlet','gas','out')];
const POWER=[port('supply','Electrical supply','electricity','in'),port('load','Electrical output','electricity','out')];
const CONTROL=[port('network','Control network','data','bidirectional'),port('power','Control power','electricity','in')];
const SENSOR=[port('process','Process measurement','measurement','in'),port('signal','Measurement signal','data','out'),port('power','Control power','electricity','in')];

export const SCADA_CATEGORIES=freeze([
 {id:'process',label:'Process vessels'},{id:'rotating',label:'Pumps & machinery'},
 {id:'power',label:'Power & energy'},{id:'valves',label:'Valves'},
 {id:'instruments',label:'Instruments'},{id:'automation',label:'PLC & networks'},
 {id:'connections',label:'Connections'},{id:'manufacturing',label:'Manufacturing & solids'},
 {id:'nuclear',label:'Nuclear systems'},{id:'agriculture',label:'Growing & aquaculture'},
 {id:'climate',label:'Climate control'}
]);

function component(type,label,category,description,ports,fields=[],sharedKind=null){
 const extra=[];
 if(['pump','submersible-pump','dosing-pump','blower','compressor','motor','generator'].includes(type)){
  if(!fields.some(field=>field.key==='load'))extra.push(LOAD);
  extra.push(number('speed','Illustrative operating speed',60));
 }
 if(['boiler','flare','heat-exchanger','gas-treatment','filter'].includes(type)&&!fields.some(field=>field.key==='load'))extra.push(LOAD);
 if(['boiler','heat-exchanger'].includes(type))extra.push(number('temperature','Illustrative temperature',type==='boiler'?180:60,-20,type==='boiler'?600:300,'°C'));
 const damageProfile=EXISTING_DAMAGE_PROFILES[type];
 const stateFields=[...COMMON,...fields,...extra,...(damageProfile?[damageField(damageProfile)]:[])];
 return {id:type,type,label,name:label,category,description,ports,stateFields,
  defaultState:Object.fromEntries(stateFields.map(field=>[field.key,field.default])),
  modelSupport:{kind:sharedKind?'shared-model':'visual-only',description:sharedKind?'Reuses the plant twin artwork. The host may connect the documented approximate plant model; this renderer itself performs no physics.':'Visual component only. No process, electrical, PLC, network or safety behavior is simulated.'},
  provenance:'Original project SVG artwork; illustrative geometry, not a vendor drawing or verified plant asset.',sharedKind,damageProfile:damageProfile??null};
}

function enrichComponentMetadata(descriptor) {
 const offered=EXISTING_POWER_PORT_ADDITIONS[descriptor.type]??[];
 const additions=offered.filter(port=>!['solid-fuel','liquid-fuel'].includes(port.id));
 let result={...descriptor,ports:[...descriptor.ports,...additions.map(port=>({...port,optional:true}))]};
 const domains={
  'solar-panel':{dc:'dc'},battery:{dc:'dc'},'fuel-cell':{output:'dc'},
  ups:{supply:'ac',load:'ac',battery:'dc'}
 };
 if(domains[descriptor.type])result.powerDomains=domains[descriptor.type];
 if(descriptor.type==='generator')result={...result,variants:GENERATOR_VARIANTS,defaultVariant:'natural-gas-enclosed',circuits:[
  {id:'fuel',ports:['fuel'],fluid:'fuel-gas'},
  {id:'air-exhaust',ports:['air','exhaust'],fluid:'combustion-gas'}
 ]};
 if(descriptor.type==='boiler')result={...result,defaultVariant:'gas-fired',circuits:[
  {id:'fuel',ports:['fuel'],fluid:'fuel-gas'},
  {id:'air-exhaust',ports:['air','exhaust'],fluid:'combustion-gas'},
  {id:'water',ports:['feedwater','steam'],fluid:'secondary-water',phaseChange:true}
 ],variants:[
  {id:'gas-fired',label:'Gas-fired',fuel:'natural-gas',fuelPort:'fuel',disabledPorts:['solid-fuel','liquid-fuel']},
  {id:'solid-fuel',label:'Solid-fuel boiler',componentLabel:'Solid-fuel boiler',description:'Generic boiler illustration with an explicit solid-fuel supply, separate combustion-air path and isolated feedwater/steam inventory.',fuel:'solid-fuel',fuelPort:'solid-fuel',disabledPorts:['fuel','liquid-fuel'],additionalPorts:offered.filter(port=>port.id==='solid-fuel'),circuitOverrides:{fuel:{ports:['solid-fuel'],fluid:'solid-fuel'}}},
  {id:'liquid-fuel',label:'Liquid-fuel boiler',componentLabel:'Liquid-fuel boiler',description:'Generic boiler illustration with an explicit liquid-fuel supply, separate combustion-air path and isolated feedwater/steam inventory.',fuel:'liquid-fuel',fuelPort:'liquid-fuel',disabledPorts:['fuel','solid-fuel'],additionalPorts:offered.filter(port=>port.id==='liquid-fuel'),circuitOverrides:{fuel:{ports:['liquid-fuel'],fluid:'liquid-fuel'}}}
 ]};
 return addScadaTaxonomy(addUtilityVariants(result));
}

export const SCADA_COMPONENTS=freeze([
 component('digester','Anaerobic digester','process','Domed vessel with mixing shaft, liquid motion and rising gas bubbles.',[...LIQUID,port('biogas','Biogas','gas','out'),port('drive','Mixer power','electricity','in')],[LEVEL],'digester'),
 component('tank','Storage tank','process','Glass-sided cylindrical tank with level scale, inlet and outlet.',LIQUID,[LEVEL]),
 component('gas-holder','Gas holder','process','Assumed low-pressure gas buffer with an adjustable inventory illustration.',GAS,[LEVEL],'storage'),
 component('mixing-tank','Mixing tank','process','Open vessel, overhead gearbox and an animated agitator.',[...LIQUID,port('drive','Mixer power','electricity','in')],[LEVEL]),
 component('reactor','Pressure reactor','process','Sealed horizontal vessel with inspection flanges and a pressure indicator.',[...LIQUID,port('vent','Vent','gas','out'),port('gas-inlet','Process gas addition','gas','in')],[LEVEL]),
 component('clarifier','Circular clarifier','process','Settling basin with a moving scraper bridge and central feed well.',[port('feed','Mixed liquor','liquid','in'),port('effluent','Clarified liquid','liquid','out'),port('sludge','Settled solids','sludge','out')],[LEVEL]),
 component('silo','Bulk solids silo','process','Tall storage bin with a conical hopper and discharge throat.',[port('fill','Solids fill','solids','in'),port('discharge','Solids discharge','solids','out')],[LEVEL]),
 component('heat-exchanger','Heat exchanger','process','Tube bundle with visually separate hot and cold flow paths.',[port('hot-in','Hot inlet','thermal-fluid','in'),port('hot-out','Hot outlet','thermal-fluid','out'),port('cold-in','Cold inlet','thermal-fluid','in'),port('cold-out','Cold outlet','thermal-fluid','out')]),
 component('filter','Media filter','process','Single pressure filter with a porous media bed and differential gauge.',[...LIQUID,port('backwash','Backwash','liquid','in')]),
 component('gas-treatment','Gas treatment train','process','Shared twin illustration for grouped gas conditioning vessels.',[...GAS,port('drive','Conditioning power','electricity','in')],[],'conditioning'),
 component('boiler','Gas-fired boiler','process','Burner window, flame and stack, reused from the twin useful-gas branch.',[port('fuel','Fuel gas','gas','in'),port('heat','Useful heat','thermal','out'),port('exhaust','Exhaust','gas','out'),port('steam','Steam service','steam','out')],[],'othergas'),
 component('flare','Flare stack','process','Shared controlled-flare illustration with layered flame and embers.',[port('fuel','Relief gas','gas','in'),port('exhaust','Combustion products','gas','out')],[],'flare'),
 component('pump','Centrifugal pump','rotating','Distinct pump volute, motor, flange connections and spinning impeller.',[...LIQUID,port('drive','Motor power','electricity','in')],[],'pump'),
 component('submersible-pump','Submersible pump','rotating','Vertical sealed pump housing, suction strainer and rising discharge.',[...LIQUID,port('drive','Motor cable','electricity','in')]),
 component('dosing-pump','Metering pump','rotating','Compact drive and reciprocating diaphragm head for controlled chemical feed.',[port('suction','Chemical suction','chemical','in'),port('dose','Dosing outlet','chemical','out'),port('drive','Motor power','electricity','in')]),
 component('blower','Centrifugal blower','rotating','Scroll housing, guarded radial fan and tangential air outlet.',[port('intake','Air intake','air','in'),port('discharge','Air discharge','air','out'),port('drive','Motor power','electricity','in')]),
 component('compressor','Reciprocating compressor','rotating','Twin cylinders over a receiver with a cycling piston linkage.',[...GAS,port('drive','Motor power','electricity','in')]),
 component('motor','Electric motor','rotating','Ribbed motor casing, fan guard and rotating output shaft.',[port('supply','Motor supply','electricity','in'),port('shaft','Mechanical shaft','mechanical','out')],[LOAD]),
 component('generator','Microturbine generator','power','Shared louvered generator cabinet with exhaust and electrical output lead.',[port('fuel','Fuel gas','gas','in'),port('output','Electrical generation','electricity','out'),port('exhaust','Exhaust','gas','out')],[LOAD],'turbine'),
 component('transformer','Power transformer','power','Finned transformer tank with primary and secondary bushings.',[port('primary','Primary winding','electricity','in'),port('secondary','Secondary winding','electricity','out')],[LOAD]),
 component('breaker','Circuit breaker','power','Contact enclosure with an explicit open or closed electrical path.',POWER,[OPEN]),
 component('busbar','Distribution bus','power','Three insulated copper rails and visible branch takeoffs.',[port('supply','Incoming supply','electricity','in'),port('branch-a','Branch A','electricity','out'),port('branch-b','Branch B','electricity','out'),port('branch-c','Branch C','electricity','out')],[LOAD]),
 component('battery','Battery bank','power','Three cells with adjustable charge bars and linked terminals.',[port('dc','DC connection','electricity','bidirectional')],[LEVEL]),
 component('ups','Uninterruptible supply','power','UPS cabinet with inverter display, battery drawer and output cable.',[...POWER,port('battery','External battery','electricity','bidirectional')],[LEVEL,LOAD]),
 component('solar-panel','Solar array','power','Tilted photovoltaic panel with individual cells and a DC lead.',[port('dc','DC output','electricity','out')],[LOAD]),
 component('electrical-meter','Net power indicator','power','Shared animated electrical contribution symbol from the plant twin.',[port('measurement','Electrical measurement','measurement','in'),port('signal','Power reading','data','out')],[LOAD],'net'),
 component('gate-valve','Gate valve','valves','Flanged valve body with a lifting stem and handwheel.',LIQUID,[OPEN,OPENING]),
 component('control-valve','Control valve','valves','Process valve with a pneumatic diaphragm actuator and control signal.',[...LIQUID,port('control','Actuator command','data','in')],[OPEN,OPENING]),
 component('check-valve','Check valve','valves','Direction arrow and a hinged internal flap showing the permitted flow path.',LIQUID,[OPEN]),
 component('relief-valve','Pressure relief valve','valves','Spring-loaded relief body with a distinct upward vent connection.',[port('inlet','Protected line','fluid','in'),port('relief','Relief outlet','fluid','out')],[OPEN]),
 component('butterfly-valve','Butterfly valve','valves','Circular wafer body with a quarter-turn disc and lever.',LIQUID,[OPEN,OPENING]),
 component('pressure-transmitter','Pressure transmitter','instruments','Round pressure dial with a sensing stem, needle and signal halo.',SENSOR,[VALUE]),
 component('flow-meter','Inline flow meter','instruments','Flanged spool, digital display and animated direction markers.',SENSOR,[VALUE]),
 component('temperature-sensor','Temperature probe','instruments','Thermowell probe with a temperature bulb and local transmitter head.',SENSOR,[VALUE]),
 component('level-sensor','Level transmitter','instruments','Radar head with a downward sensing cone and vertical fill ruler.',SENSOR,[LEVEL,VALUE]),
 component('gas-analyzer','Gas analyzer','instruments','Sampling cabinet with gas tubing, spectrum trace and local display.',SENSOR,[VALUE]),
 component('plc-rack','PLC rack','automation','Power supply, CPU and modular IO on a common backplane.',[...CONTROL,port('io','Field IO','data','bidirectional')],[CONNECTED,LOAD]),
 component('plc-cpu','PLC CPU','automation','Controller module with mode indicators, scan status and service port.',[...CONTROL,port('backplane','IO backplane','data','bidirectional')],[CONNECTED,LOAD]),
 component('remote-io','Remote IO station','automation','Distributed input and output modules with field terminal blocks.',[...CONTROL,port('inputs','Field inputs','data','in'),port('outputs','Field outputs','data','out')],[CONNECTED,LOAD]),
 component('hmi','Operator HMI','automation','Panel-mounted touch display with a miniature process diagram.',CONTROL,[CONNECTED]),
 component('scada-server','SCADA server','automation','Server enclosure with drive bays, trend display and network activity.',CONTROL,[CONNECTED,LOAD]),
 component('network-switch','Industrial network switch','automation','Rugged Ethernet switch with individual RJ45 ports and link activity.',[port('uplink','Network uplink','data','bidirectional'),port('ports','Field Ethernet ports','data','bidirectional'),port('power','Control power','electricity','in')],[CONNECTED,LOAD]),
 component('radio','Telemetry radio','automation','Antenna, radio enclosure and pulsing bidirectional signal arcs.',[...CONTROL,port('wireless','Wireless telemetry','data','bidirectional')],[CONNECTED]),
 component('pipe','Process pipe','connections','Elbow pipe segment with animated flow and flange details.',LIQUID,[OPEN]),
 component('junction','Four-way junction','connections','Four process branches meeting at an explicitly marked common junction.',[port('west','West','fluid','bidirectional'),port('east','East','fluid','bidirectional'),port('north','North','fluid','bidirectional'),port('south','South','fluid','bidirectional')],[OPEN]),
 ...SCADA_EXTENSION_DEFINITIONS.map(item=>({...component(item.type,item.label,item.category,item.description,item.ports,item.fields),drawingFamily:item.drawingFamily,modelFamily:item.modelFamily,damageProfile:item.damageProfile})),
 ...SCADA_POWER_DEFINITIONS,
 ...SCADA_AGRICULTURE_DEFINITIONS.map(item=>({...component(item.type,item.label,item.category,item.description,item.ports,item.fields),drawingFamily:item.drawingFamily,modelFamily:item.modelFamily,provenance:item.provenance,taxonomy:item.taxonomy}))
].map(enrichComponentMetadata));

const registry=new Map(SCADA_COMPONENTS.map(item=>[item.type,item]));
export function getScadaComponent(type,options={}){
 ownDataObject(options,['variant'],'component selection');
 if(options.variant!==undefined&&typeof options.variant!=='string')throw new TypeError('Variant must be a registered string.');
 const descriptor=registry.get(type);
 if(!descriptor)throw new RangeError(`Unknown SCADA component type: ${String(type)}`);
 return resolveScadaVariant(descriptor,options.variant);
}

export function getScadaVariants(type){
 const descriptor=registry.get(type);
 if(!descriptor)throw new RangeError(`Unknown SCADA component type: ${String(type)}`);
 return descriptor.variants??Object.freeze([]);
}

/** Strict keys/types; finite numeric states are constrained to declared ranges. */
export function normalizeScadaState(type,input={},options={}){
 const descriptor=getScadaComponent(type,options);
 if(!input||typeof input!=='object'||Array.isArray(input)||![Object.prototype,null].includes(Object.getPrototypeOf(input)))throw new TypeError('SCADA state must be a plain own-property object.');
 const fields=new Map(descriptor.stateFields.map(field=>[field.key,field]));
 for(const key of Reflect.ownKeys(input)){
  if(typeof key!=='string'||!fields.has(key))throw new TypeError(`Unknown ${type} state field: ${String(key)}`);
  if(!Object.hasOwn(Object.getOwnPropertyDescriptor(input,key),'value'))throw new TypeError('SCADA state must contain data properties, not accessors.');
 }
 const state={...descriptor.defaultState};
 for(const [key,value] of Object.entries(input)){
  const field=fields.get(key);
  if(field.type==='boolean'){if(typeof value!=='boolean')throw new TypeError(`${key} must be boolean.`);state[key]=value;}
  else if(field.type==='number'){if(typeof value!=='number'||!Number.isFinite(value))throw new TypeError(`${key} must be a finite number.`);state[key]=Math.min(field.max,Math.max(field.min,value));}
  else{if(typeof value!=='string'||!field.options.some(option=>option.value===value))throw new TypeError(`${key} is not a supported state.`);state[key]=value;}
 }
 return state;
}
