import {getV2Descriptor,createV2Component,PARAMETER_BOUNDS,TRACERS,ZONE_FIELDS,channel,domain,freeze} from './contract.mjs';
import {normalizeEquationBindings} from '../equations/bindings.mjs';

export function safeClone(input){
  const seen=new Set();let count=0,size=0;
  const visit=(value,depth=0,path=[])=>{
    if(++count>100000||depth>32)throw new TypeError('Data exceeds size or nesting limits.');
    if(value===null||typeof value==='boolean')return value;
    if(typeof value==='number'){if(!Number.isFinite(value))throw new TypeError('Numbers must be finite.');return value;}
    if(typeof value==='string'){
      size+=value.length;
      // Exact topology records scale with the entire graph. Keep their total
      // text budget bounded without applying an individual label's 16 KiB cap.
      const signature=path.at(-2)==='system'&&path.at(-1)==='signature';
      if(size>2097152||(!signature&&value.length>16384))throw new TypeError('Text exceeds size limits.');
      return value;
    }
    if(!value||typeof value!=='object'||seen.has(value)||(!Array.isArray(value)&&![Object.prototype,null].includes(Object.getPrototypeOf(value))))throw new TypeError('Expected acyclic plain JSON data.');
    seen.add(value);const result=Array.isArray(value)?[]:{};
    for(const key of Reflect.ownKeys(value)){
      if(Array.isArray(value)&&key==='length')continue;
      if(typeof key!=='string'||['__proto__','prototype','constructor'].includes(key))throw new TypeError('Unsafe data key.');
      const property=Object.getOwnPropertyDescriptor(value,key);if(!Object.hasOwn(property,'value')||!property.enumerable)throw new TypeError('Accessors and hidden properties are forbidden.');
      if(/^(password|secret|token|apikey|credentials|authorization|privatekey)$/i.test(key))throw new TypeError('Credentials do not belong in model data.');
      result[key]=visit(property.value,depth+1,[...path,key]);
    }
    if(Array.isArray(value)&&(Object.keys(result).length!==value.length||Object.keys(result).some(key=>!/^\d+$/.test(key))))throw new TypeError('Sparse or decorated arrays are forbidden.');
    seen.delete(value);return result;
  };return visit(input);
}

function validateDefinition(systemInput,definitionInput){
  const errors=[];let system,definition;
  const add=(path,message)=>{if(errors.length<100)errors.push({path,code:'invalid_model',message});};
  try{system=safeClone(systemInput);definition=safeClone(definitionInput);}catch(error){return{ok:false,errors:[{path:'/',code:'invalid_json',message:error.message}]};}
  const object=(value,path,allowed)=>{if(!value||typeof value!=='object'||Array.isArray(value)){add(path,'Expected object.');return false;}for(const key of Object.keys(value))if(allowed&&!allowed.includes(key))add(`${path}/${key}`,'Unknown field.');return true;};
  const number=(value,path,min=0,max=100)=>{if(typeof value!=='number'||!Number.isFinite(value)||value<min||value>max)add(path,`Expected number from ${min} to ${max}.`);};
  const text=(value,path)=>{if(typeof value!=='string'||!value.length||value.length>128)add(path,'Expected bounded nonempty text.');};
  const enumeration=(value,values,path)=>{if(!values.includes(value))add(path,`Expected ${values.join(', ')}.`);};
  if(!object(definition,'/',['format','version','scenarioId','seed','components','connections','environment','zones','assumptions','equations']))return{ok:false,errors};
  if(definition.equations!==undefined){try{definition.equations=normalizeEquationBindings(definition.equations,{system});}catch(error){add('/equations',error.message);}}
  if(definition.format!=='scada-placeholder-model'||definition.version!==2)add('/version','Expected scada-placeholder-model version 2.');
  if(definition.scenarioId!==system?.system?.id)add('/scenarioId','Must match system identity.');
  number(definition.seed,'/seed',1,4294967295);if(!Number.isInteger(definition.seed))add('/seed','Expected integer seed.');
  if(!Array.isArray(system?.components)||!Array.isArray(system?.connections)){add('/system','Expected components and connections.');return{ok:false,errors};}
  if(!object(definition.components,'/components'))return{ok:false,errors};
  const instances=new Map(),descriptors=new Map(),owners=new Map();
  for(const instance of system.components){if(instances.has(instance.id))add('/system/components','Duplicate equipment identity.');instances.set(instance.id,instance);try{descriptors.set(instance.id,getV2Descriptor(instance.type,definition.components[instance.id]?.variant??instance.variant));}catch(error){add(`/components/${instance.id}`,error.message);}}
  const componentKeys=['model','variant','parameters','initial','circuits','thermalLinks','thermalStore','heatSource','energy','observation','zone','measurement','presentation','assumptions'];
  for(const id of Object.keys(definition.components))if(!instances.has(id))add(`/components/${id}`,'Unknown equipment.');
  for(const[id,instance]of instances){
    const c=definition.components[id],path=`/components/${id}`,d=descriptors.get(id);if(!d||!object(c,path,componentKeys))continue;
    const defaults=createV2Component(instance.type,{variant:c.variant??instance.variant});if(c.model!==defaults.model)add(`${path}/model`,'Template must match registered type.');
    if(c.variant!==undefined&&!d.variants.some(v=>v.id===c.variant))add(`${path}/variant`,'Unknown variant.');
    if(c.parameters!==undefined&&!object(c.parameters,`${path}/parameters`))continue;
    c.parameters={...defaults.parameters,...c.parameters};
    if(object(c.parameters,`${path}/parameters`,Object.keys(PARAMETER_BOUNDS)))for(const[key,bounds]of Object.entries(PARAMETER_BOUNDS))number(c.parameters[key],`${path}/parameters/${key}`,...bounds);
    if(c.initial!==undefined&&!object(c.initial,`${path}/initial`))continue;
    c.initial={...defaults.initial,...c.initial};
    if(object(c.initial,`${path}/initial`,['enabled','open','load','damage','mode','rodPosition'])){
      for(const key of ['enabled','open'])if(typeof c.initial[key]!=='boolean')add(`${path}/initial/${key}`,'Expected boolean.');
      for(const key of ['load','damage','rodPosition'])number(c.initial[key],`${path}/initial/${key}`);text(c.initial.mode,`${path}/initial/mode`);
    }
    if(!object(c.circuits,`${path}/circuits`))continue;
    const own=new Map();owners.set(id,own);
    for(const[circuitId,circuit]of Object.entries(c.circuits)){
      const cp=`${path}/circuits/${circuitId}`;text(circuitId,cp);if(circuitId==='body')add(cp,'body is reserved for the thermal store.');
      if(!object(circuit,cp,['ports','medium','fluid','role','parameters','initial']))continue;
      if(!Array.isArray(circuit.ports)||!circuit.ports.length){add(`${cp}/ports`,'Expected nonempty port array.');continue;}
      for(const port of circuit.ports){const p=d.ports.find(item=>item.id===port);if(!p||channel(p.medium)!=='resource')add(`${cp}/ports`,'Circuit ports must be registered resource ports.');if(own.has(port))add(`${cp}/ports`,'Port belongs to multiple circuits.');own.set(port,circuitId);}
      text(circuit.medium,`${cp}/medium`);text(circuit.fluid,`${cp}/fluid`);enumeration(circuit.role,['passage','storage','source','sink'],`${cp}/role`);
      if(object(circuit.parameters,`${cp}/parameters`,['capacity','stockScale','thermalCapacity','loss','pressureGain']))for(const[key,value]of Object.entries(circuit.parameters))number(value,`${cp}/parameters/${key}`,['stockScale','thermalCapacity'].includes(key)?.01:0,key==='loss'?1:key==='stockScale'?1000:100);
      for(const key of ['capacity','stockScale','thermalCapacity','loss','pressureGain'])if(circuit.parameters?.[key]===undefined)add(`${cp}/parameters/${key}`,'Required parameter.');
      if(object(circuit.initial,`${cp}/initial`,['inventory','temperature','pressure','tracers'])){
        for(const key of ['inventory','temperature','pressure'])number(circuit.initial[key],`${cp}/initial/${key}`);
        if(circuit.initial.tracers!==undefined&&!object(circuit.initial.tracers,`${cp}/initial/tracers`))continue;
        circuit.initial.tracers={oxygen:60,nutrient:50,solids:20,ph:50,ec:50,...circuit.initial.tracers};
        if(object(circuit.initial.tracers,`${cp}/initial/tracers`,TRACERS))for(const[key,value]of Object.entries(circuit.initial.tracers))number(value,`${cp}/initial/tracers/${key}`);
      }
    }
    for(const p of d.ports.filter(p=>channel(p.medium)==='resource'))if(!own.has(p.id))add(`${path}/circuits`,`Resource port ${p.id} has no circuit owner.`);
    for(const group of defaults.circuits?Object.values(defaults.circuits):[]){const assigned=new Set(group.ports.map(port=>own.get(port)));if(assigned.size!==1)add(`${path}/circuits`,'A registered circuit group cannot be split.');}
    for(const[name,circuit]of Object.entries(c.circuits)){const groups=Object.values(defaults.circuits).filter(group=>group.ports.some(port=>circuit.ports.includes(port)));if(groups.length>1)add(`${path}/circuits/${name}`,'Isolated registered circuits cannot be merged.');const registered=d.circuits.find(group=>group.ports.some(port=>circuit.ports.includes(port)));const supported=registered?.supportedFluids??d.selectedVariant?.supportedFluids;if(supported&&!supported.includes(circuit.fluid))add(`${path}/circuits/${name}/fluid`,'Fluid is not supported by the selected placeholder variant.');}
    if(c.presentation){object(c.presentation,`${path}/presentation`,['primaryCircuit']);if(!c.circuits[c.presentation.primaryCircuit])add(`${path}/presentation/primaryCircuit`,'Unknown presentation circuit.');}
    if(c.thermalStore){const p=`${path}/thermalStore`;if(object(c.thermalStore,p,['capacity','initial','loss'])){number(c.thermalStore.capacity,`${p}/capacity`,.01,1000);number(c.thermalStore.initial,`${p}/initial`);number(c.thermalStore.loss,`${p}/loss`,0,1);}}
    if(c.heatSource){const h=c.heatSource,p=`${path}/heatSource`;if(object(h,p,['target','capacity','control','inverted','environment','supply'])){if(!c.circuits[h.target]&&!(h.target==='body'&&c.thermalStore))add(`${p}/target`,'Unknown thermal target.');number(h.capacity,`${p}/capacity`);enumeration(h.control,['load','rodPosition'],`${p}/control`);if(h.inverted!==undefined&&typeof h.inverted!=='boolean')add(`${p}/inverted`,'Expected boolean.');if(h.environment&&!Object.hasOwn(definition.environment??{},h.environment))add(`${p}/environment`,'Unknown environmental boundary.');if(h.supply){object(h.supply,`${p}/supply`,['kind','circuit']);enumeration(h.supply.kind,['energy-input','resource'],`${p}/supply/kind`);if(h.supply.kind==='resource'&&!c.circuits[h.supply.circuit])add(`${p}/supply/circuit`,'Unknown fuel circuit.');}}}
    if(c.energy){const e=c.energy,p=`${path}/energy`;if(object(e,p,['role','inputs','outputs','capacity','demand','efficiency','supply','store','modes','requiredCircuits'])){
      enumeration(e.role,['boundary','source','load','relay','converter','store','prime-mover'],`${p}/role`);for(const key of ['capacity','demand'])number(e[key],`${p}/${key}`);number(e.efficiency,`${p}/efficiency`,.001,1);
      for(const key of ['inputs','outputs']){if(!Array.isArray(e[key])){add(`${p}/${key}`,'Expected array.');continue;}if(new Set(e[key]).size!==e[key].length)add(`${p}/${key}`,'Duplicate energy port.');for(const portId of e[key])if(!d.ports.some(port=>port.id===portId&&channel(port.medium)==='energy'))add(`${p}/${key}`,'Expected registered energy port.');}
      if(e.supply){const s=e.supply;object(s,`${p}/supply`,['kind','circuit','environment']);enumeration(s.kind,['boundary','environment','resource','thermal'],`${p}/supply/kind`);if(['resource','thermal'].includes(s.kind)&&!c.circuits[s.circuit])add(`${p}/supply/circuit`,'Unknown source circuit.');if(s.kind==='environment'&&!Object.hasOwn(definition.environment??{},s.environment))add(`${p}/supply/environment`,'Unknown environmental boundary.');}
      if(['source','prime-mover'].includes(e.role)&&!e.supply)add(`${p}/supply`,'Sources require explicit supply.');
      if(e.store){object(e.store,`${p}/store`,['capacity','initial']);number(e.store.capacity,`${p}/store/capacity`,.01,1000);number(e.store.initial,`${p}/store/initial`);}
      if(e.role==='store'&&!e.store)add(`${p}/store`,'A storage role needs finite energy capacity.');
      if(e.requiredCircuits!==undefined&&(!Array.isArray(e.requiredCircuits)||e.requiredCircuits.some(id=>!c.circuits[id])))add(`${p}/requiredCircuits`,'Expected existing resource circuit IDs.');
      if(e.modes){if(object(e.modes,`${p}/modes`))for(const[key,value]of Object.entries(e.modes)){text(key,`${p}/modes`);enumeration(value,['forward','reverse','charge','discharge','idle'],`${p}/modes/${key}`);}if(!Object.hasOwn(e.modes,c.initial.mode))add(`${path}/initial/mode`,'Initial mode is not declared.');}
      const inDomains=new Set((e.inputs??[]).map(port=>domain(d,port))),outDomains=new Set((e.outputs??[]).map(port=>domain(d,port)));
      if(e.role==='relay'&&[...inDomains].some(value=>[...outDomains].some(other=>value!==other)))add(p,'A relay cannot bridge energy domains; declare a converter.');
    }}
    if(c.zone&&!Object.hasOwn(definition.zones??{},c.zone))add(`${path}/zone`,'Unknown zone.');
    if(c.assumptions!==undefined&&(!Array.isArray(c.assumptions)||c.assumptions.some(value=>typeof value!=='string')))add(`${path}/assumptions`,'Expected assumption strings.');
    if(c.measurement!==undefined&&!d.visualFields.measurement?.options?.includes(c.measurement))add(`${path}/measurement`,'Unknown measurement identity.');
  }
  const reference=(ref,path)=>{if(!object(ref,path,['component','circuit']))return;const c=definition.components[ref.component];if(!c||(!c.circuits?.[ref.circuit]&&!(ref.circuit==='body'&&c.thermalStore)))add(path,'Unknown thermal reference.');};
  for(const[id,c]of Object.entries(definition.components)){
    if(c.thermalLinks!==undefined&&!Array.isArray(c.thermalLinks))add(`/components/${id}/thermalLinks`,'Expected array.');
    const seen=new Set();for(const link of Array.isArray(c.thermalLinks)?c.thermalLinks:[]){const p=`/components/${id}/thermalLinks`;if(!object(link,p,['id','from','to','conductance','maximumTransfer','lossFraction']))continue;reference(link.from,p+'/from');reference(link.to,p+'/to');text(link.id,p+'/id');if(seen.has(link.id))add(p,'Duplicate thermal link ID.');seen.add(link.id);number(link.conductance,p+'/conductance',0,1);number(link.maximumTransfer,p+'/maximumTransfer');number(link.lossFraction,p+'/lossFraction',0,1);}
    if(c.observation){const o=c.observation,p=`/components/${id}/observation`;object(o,p,['component','circuit','zone','quantity']);if(Boolean(o.component)===Boolean(o.zone))add(p,'Select exactly one component or zone.');if(o.component&&!definition.components[o.component])add(p,'Unknown observed component.');if(o.circuit&&!definition.components[o.component]?.circuits?.[o.circuit])add(p,'Unknown observed circuit.');if(o.zone&&!definition.zones?.[o.zone])add(p,'Unknown observed zone.');text(o.quantity,p+'/quantity');}
  }
  if(object(definition.environment,'/environment'))for(const[key,value]of Object.entries(definition.environment))number(value,`/environment/${key}`);
  if(object(definition.zones,'/zones'))for(const[id,zone]of Object.entries(definition.zones)){const p=`/zones/${id}`;object(zone,p,['initial','parameters']);if(object(zone.initial,p+'/initial',ZONE_FIELDS))for(const key of ZONE_FIELDS)number(zone.initial[key],`${p}/initial/${key}`);if(object(zone.parameters,p+'/parameters',['response']))number(zone.parameters.response,p+'/parameters/response',0,1);}
  if(!object(definition.connections,'/connections'))definition.connections={};
  const edgeIds=new Set();
  for(const edge of system.connections){
    if(edgeIds.has(edge.id))add('/system/connections','Duplicate connection ID.');edgeIds.add(edge.id);
    const from=descriptors.get(edge.from?.component),to=descriptors.get(edge.to?.component),source=from?.ports.find(p=>p.id===edge.from.port),target=to?.ports.find(p=>p.id===edge.to.port);
    if(!source||!target){add(`/connections/${edge.id}`,'Unknown endpoint port.');continue;}
    const kind=channel(edge.medium??source.medium),a=channel(source.medium),b=channel(target.medium);
    if(kind==='measurement'){if(b!=='measurement')add(`/connections/${edge.id}`,'Measurement must end on an observation port.');}
    else if(kind==='thermal'){if(a!=='thermal'||b!=='thermal')add(`/connections/${edge.id}`,'Heat-only connections require thermal ports; use explicit thermalLinks for store coupling.');}
    else if(kind!==a||kind!==b)add(`/connections/${edge.id}`,'Connection cannot override protected port channels.');
    if(kind==='energy'&&domain(from,source.id)!==domain(to,target.id))add(`/connections/${edge.id}`,'Energy domain mismatch; use a conversion component.');
    if(kind==='resource'){const a=definition.components[edge.from.component]?.circuits?.[owners.get(edge.from.component)?.get(edge.from.port)],b=definition.components[edge.to.component]?.circuits?.[owners.get(edge.to.component)?.get(edge.to.port)];if(a&&b&&a.fluid!==b.fluid)add(`/connections/${edge.id}`,'Connected resource circuits need one explicit compatible fluid identity.');}
    const config=definition.connections[edge.id];if(config){const p=`/connections/${edge.id}`;object(config,p,['mode']);if(config.mode){object(config.mode,p+'/mode',['equipment','values']);const controller=definition.components[config.mode.equipment];if(!controller)add(p,'Unknown mode controller.');if(object(config.mode.values,p+'/mode/values'))for(const[mode,value]of Object.entries(config.mode.values)){if(controller?.energy?.modes&&!Object.hasOwn(controller.energy.modes,mode))add(p,'Unknown controller mode.');enumeration(value,[-1,0,1],p+'/mode/values');}}}
  }
  for(const id of Object.keys(definition.connections))if(!edgeIds.has(id))add(`/connections/${id}`,'Unknown connection.');
  if(!Array.isArray(definition.assumptions)||definition.assumptions.some(value=>typeof value!=='string'))add('/assumptions','Expected assumption strings.');
  return errors.length?{ok:false,errors}:{ok:true,definition:freeze(definition)};
}

export function validateV2Definition(system,definition){try{return validateDefinition(system,definition);}catch(error){return{ok:false,errors:[{path:'/',code:'invalid_model',message:`Malformed model data: ${error.message}`}]};}}
export const validateV2ModelDefinition=validateV2Definition;
