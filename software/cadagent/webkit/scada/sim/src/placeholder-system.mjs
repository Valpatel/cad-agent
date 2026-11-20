import {getModelDescriptor} from './model-registry.mjs';
import {validatePlaceholderModelDefinition} from './validation.mjs';
import {COMPONENT_MODEL_CLASSES,clamp} from './components.mjs';
import {CircuitSystemModel} from './v2/circuit-system.mjs';
import {createEquationRuntime} from './equations/index.mjs';
import {formatEquationError} from './equations/contracts.mjs';

const freeze=value=>{if(value&&typeof value==='object'&&!Object.isFrozen(value)){Object.values(value).forEach(freeze);Object.freeze(value);}return value;};
const sum=values=>values.reduce((total,value)=>total+value,0);
const EPS=1e-8, MAX_MINUTES=1e9;
const BOOLEAN_STATE=['enabled','open','failed','warning','connected'];
const NUMBER_STATE=['load','operating','inventory','pressure','temperature','damage','signal'];
function bounded(value,min,max,label){if(typeof value!=='number'||!Number.isFinite(value)||value<min||value>max)throw new RangeError(`${label} must be from ${min} to ${max}.`);return value;}
function boolean(value,label){if(typeof value!=='boolean')throw new TypeError(`${label} must be boolean.`);return value;}
function keys(object,allowed,label){if(!object||typeof object!=='object'||Array.isArray(object))throw new TypeError(`${label} must be an object.`);for(const key of Object.keys(object))if(!allowed.includes(key))throw new TypeError(`Unknown ${label} field: ${key}`);}
function safeData(input){
  let count=0;const seen=new Set();
  function copy(value,depth=0){
    if(++count>100000||depth>30)throw new RangeError('Data is too large or deeply nested.');
    if(value===null||typeof value==='boolean')return value;
    if(typeof value==='number'){if(!Number.isFinite(value))throw new TypeError('Data numbers must be finite.');return value;}
    if(typeof value==='string'){if(value.length>1000000)throw new RangeError('Data text is too long.');return value;}
    if(!value||typeof value!=='object'||(!Array.isArray(value)&&![Object.prototype,null].includes(Object.getPrototypeOf(value)))||seen.has(value))throw new TypeError('Expected acyclic plain JSON data.');
    seen.add(value);const output=Array.isArray(value)?[]:{};
    if(Array.isArray(value)&&value.length>10000)throw new RangeError('Data arrays are too long.');
    for(const key of Reflect.ownKeys(value)){
      if(Array.isArray(value)&&key==='length')continue;
      if(typeof key!=='string'||['__proto__','constructor','prototype'].includes(key))throw new TypeError('Unsafe data property.');
      const property=Object.getOwnPropertyDescriptor(value,key);if(!Object.hasOwn(property,'value'))throw new TypeError('Accessor data is not supported.');
      output[key]=copy(property.value,depth+1);
    }
    if(Array.isArray(value)&&Object.keys(output).length!==value.length)throw new TypeError('Sparse arrays are not supported.');
    seen.delete(value);return output;
  }
  return copy(input);
}
function classify(medium){
  if(['electricity','electrical','power','mechanical'].includes(medium))return 'power';
  if(['data','signal','control','network','communication'].includes(medium))return 'data';
  if(['measurement','sensor'].includes(medium))return 'measurement';
  if(['thermal','heat','energy'].includes(medium))return 'thermal';
  return 'resource';
}
function signature(system){return JSON.stringify({id:system.system.id,components:system.components.map(item=>[item.id,item.type]).sort((a,b)=>a[0].localeCompare(b[0])),connections:(system.connections??[]).map(edge=>[edge.id,edge.from.component,edge.from.port,edge.to.component,edge.to.port,edge.medium??'']).sort((a,b)=>a[0].localeCompare(b[0]))});}
function displayValue(index,field){
  const normalized=clamp(index)/100, middle=typeof field.default==='number'?field.default:(field.min+field.max)/2;
  return clamp(normalized<=.5?field.min+(middle-field.min)*normalized*2:middle+(field.max-middle)*(normalized-.5)*2,field.min,field.max);
}

/** One external model for any number of viewers. No DOM, network, storage or UI
 * dependency. start() is explicit; imports never install timers or replay time. */
class LegacyPlaceholderSystemModel {
  #system;#definition;#signature;#components=new Map();#edges=[];#minutes=0;#running=true;#randomState;#events=[];#nextEventId=1;
  #listeners=new Set();#snapshot;#solution;#clock;#timer=null;
  #equations;
  constructor(systemDefinition,modelDefinition,{equationProviders=[],clock={setInterval:(callback,ms)=>globalThis.setInterval(callback,ms),clearInterval:id=>globalThis.clearInterval(id)}}={}){
    const result=validatePlaceholderModelDefinition(systemDefinition,modelDefinition);
    if(!result.ok)throw new TypeError(result.errors.map(error=>`${error.path}: ${error.message}`).join('; '));
    this.#system=freeze(safeData(systemDefinition));this.#signature=signature(this.#system);this.#definition=result.definition;
    if(typeof clock?.setInterval!=='function'||typeof clock?.clearInterval!=='function')throw new TypeError('Clock adapter needs setInterval and clearInterval.');
    this.#clock=clock;this.#randomState=this.#definition.seed;
    this.#buildComponents();
    this.#equations=createEquationRuntime({system:this.#system,definition:this.#definition,engineVersion:1,providers:equationProviders,initialize:false});
    this.#equations.reset(id=>this.#equationContext(this.#components.get(id)));
    this.#edges=(this.#system.connections??[]).map(edge=>{
      const source=this.#components.get(edge.from.component),port=source.descriptor.ports.find(item=>item.id===edge.from.port);
      const medium=edge.medium??port?.medium??'material';return {...edge,medium,channel:classify(medium)};
    });
    this.#initializeSignals();this.#refresh();
  }
  #buildComponents(){this.#components=new Map([...this.#system.components].sort((a,b)=>a.id.localeCompare(b.id)).map(item=>{const descriptor=getModelDescriptor(item.type),config=this.#definition.components[item.id],Class=COMPONENT_MODEL_CLASSES[config.kind];return[item.id,new Class(item.id,descriptor,config)];}));}
  #initializeSignals(){const initial=this.#solve();for(const[id,component]of this.#components)if(component.kind==='sensor')component.state.signal=this.#evaluate(component,'signal',{readings:initial.records.get(id)},{target:component.signalTarget(initial.records.get(id))}).target;}
  #equationContext(component,extra={}){
    // Measurement records can reference one another. Providers receive only
    // finite scalar observations plus one explicit, nonrecursive sample list.
    const scalar=record=>Object.fromEntries(Object.entries(record).filter(([,value])=>typeof value==='number'||typeof value==='boolean'));
    const readings=extra.readings?{...scalar(extra.readings),signalInputs:[...(extra.readings.signalInputs??[])],measurements:(extra.readings.measurements??[]).map(scalar)}:undefined;
    return {core:component.state,configuration:this.#definition.components[component.id],timeMinutes:this.#minutes,dtMinutes:0,...extra,
      gates:{healthFactor:component.healthFactor,operatingFraction:component.state.operating/100,enabled:component.state.enabled,conducting:component.conducting,...extra.gates},...(readings?{readings}:{})};
  }
  #evaluate(component,phase,context,defaults){
    if(!this.#equations?.hasPhase(component.id,phase))return defaults;
    return this.#equations.evaluate(component.id,phase,this.#equationContext(component,context),defaults);
  }
  #resourceCapacity(component,power=1,control=1,dtMinutes=1,reliefCapacity,powerSupply={}){
    const capacity=reliefCapacity??component.capacity(power,control),conducting=component.conducting||reliefCapacity!==undefined;
    const requested=this.#evaluate(component,'resource',{dtMinutes,...powerSupply,gates:{powerFactor:power,controlFactor:control,conducting}},{capacity}).capacity;
    if(this.#equations.has(component.id)&&component.materialParticipant&&!component.powerSource&&powerSupply.powerBasis==='allocated'&&powerSupply.availablePower<=EPS)return 0;
    if(!this.#equations.hasPhase(component.id,'resource'))return requested;
    if(component.availability<=0||power<=EPS||control<=EPS||(['valve','pipe'].includes(component.kind)&&!conducting))return 0;
    return Math.min(component.parameters.capacity,requested);
  }
  #energy(component,dtMinutes=1){
    const request=this.#evaluate(component,'energy',{dtMinutes},
      {capacity:component.capacity(),demand:component.powerRequest()});
    if(this.#equations.hasPhase(component.id,'energy'))return {...request,capacity:component.availability<=0?0:Math.min(component.parameters.capacity,request.capacity),demand:component.availability<=0?0:Math.min(component.parameters.demand,request.demand)};
    return request;
  }
  // Roll back directly: replaying import/refresh would invoke the same failed
  // provider again. The cached solution and visible snapshot are part of state.
  #transaction(operation){
    const before={definition:this.#definition,components:this.#components,
      componentState:new Map([...this.#components].map(([id,c])=>[id,{state:structuredClone(c.state),parameters:{...c.parameters}}])),
      minutes:this.#minutes,running:this.#running,randomState:this.#randomState,
      events:structuredClone(this.#events),nextEventId:this.#nextEventId,
      solution:this.#solution,snapshot:this.#snapshot,equations:this.#equations,
      equationState:this.#equations?.checkpoint()};
    try{return operation();}
    catch(error){
      this.#definition=before.definition;this.#components=before.components;
      for(const[id,c]of this.#components){c.state=before.componentState.get(id).state;c.parameters=before.componentState.get(id).parameters;}
      this.#minutes=before.minutes;this.#running=before.running;this.#randomState=before.randomState;
      this.#events=before.events;this.#nextEventId=before.nextEventId;
      this.#solution=before.solution;this.#snapshot=before.snapshot;this.#equations=before.equations;
      if(this.#equations)this.#equations.restore(before.equationState);
      throw error;
    }
  }
  #random(){let value=this.#randomState>>>0;value^=value<<13;value^=value>>>17;value^=value<<5;this.#randomState=value>>>0;return this.#randomState/4294967296;}
  #record(message,type='operator',equipment='system',severity='info'){
    if(this.#nextEventId>=1e9)throw new RangeError('Event sequence limit reached.');
    this.#events.push({id:this.#nextEventId++,minutes:this.#minutes,type,severity,equipment,message});if(this.#events.length>100)this.#events.shift();
  }
  #emit(event){for(const listener of [...this.#listeners]){try{listener(this.#snapshot,freeze(event));}catch(error){globalThis.reportError?.(error);}}}
  subscribe(listener){if(typeof listener!=='function')throw new TypeError('Subscriber must be a function.');this.#listeners.add(listener);return()=>this.#listeners.delete(listener);}
  getSnapshot(){return this.#snapshot;}
  get clockStarted(){return this.#timer!==null;}

  #network(channel,capacities,sources,stores,scale){
    const edges=this.#edges.filter(edge=>edge.channel===channel),incoming=new Map(),outgoing=new Map();
    for(const id of this.#components.keys()){incoming.set(id,[]);outgoing.set(id,[]);}
    for(const edge of edges){incoming.get(edge.to.component).push(edge);outgoing.get(edge.from.component).push(edge);}
    let demand=new Map(capacities);const passes=this.#components.size+2;
    for(let pass=0;pass<passes;pass++){
      const next=new Map();
      for(const [id,component]of this.#components){
        const cap=capacities.get(id)??0,outputs=outgoing.get(id);
        const downstream=sum(outputs.map(edge=>(demand.get(edge.to.component)??0)/Math.max(1,incoming.get(edge.to.component).length)));
        let accepted=outputs.length?Math.min(cap,downstream/Math.max(.01,1-component.parameters.loss)):cap;
        if(stores.has(id)){const canDischarge=Math.min(cap,sources.get(id)??0,downstream);accepted=Math.min(cap,(100-component.state.inventory)/scale+canDischarge);}
        next.set(id,Math.max(0,accepted));
      }
      demand=next;
    }
    let rates=new Map(edges.map(edge=>[edge.id,0]));
    for(let pass=0;pass<passes;pass++){
      const next=new Map();
      for(const [id,component]of this.#components){
        const input=sum(incoming.get(id).map(edge=>rates.get(edge.id)??0));
        let available=sources.has(id)?sources.get(id):input*(1-component.parameters.loss);
        available=Math.min(capacities.get(id)??0,available);
        const outputs=outgoing.get(id),limits=outputs.map(edge=>(demand.get(edge.to.component)??0)/Math.max(1,incoming.get(edge.to.component).length));
        const desired=sum(limits),total=Math.min(available,desired);
        outputs.forEach((edge,index)=>next.set(edge.id,desired>EPS?Math.max(0,total*limits[index]/desired):0));
      }
      rates=next;
    }
    const input=new Map(),output=new Map(),requested=new Map();
    for(const id of this.#components.keys()){
      input.set(id,sum(incoming.get(id).map(edge=>rates.get(edge.id)??0)));
      output.set(id,sum(outgoing.get(id).map(edge=>rates.get(edge.id)??0)));
      requested.set(id,sum(outgoing.get(id).map(edge=>(demand.get(edge.to.component)??0)/Math.max(1,incoming.get(edge.to.component).length))));
    }
    return{rates,input,output,requested,incoming,outgoing,demand};
  }
  #solve(minutes=1){
    const scale=Math.max(.001,minutes)/10,components=this.#components;
    const resourceEdges=this.#edges.filter(edge=>edge.channel==='resource'),powerEdges=this.#edges.filter(edge=>edge.channel==='power'),dataEdges=this.#edges.filter(edge=>edge.channel==='data');
    const powerInputs=new Map([...components.keys()].map(id=>[id,powerEdges.filter(edge=>edge.to.component===id)]));
    const resourceInputs=new Map([...components.keys()].map(id=>[id,resourceEdges.filter(edge=>edge.to.component===id)]));
    let powerFactors=new Map([...components.keys()].map(id=>[id,1])),fuelFactors=new Map([...components.keys()].map(id=>[id,1]));
    const controlFactors=new Map([...components.keys()].map(id=>[id,1])),powerRequests=new Map(),conductingFactors=new Map();
    const communicating=c=>c.availability>0&&!(['sensor','controller','network'].includes(c.kind)&&c.state.failed);
    let connected=new Map([...components].map(([id,c])=>[id,communicating(c)]));let power,resource;
    const powerSupply=id=>({availablePower:powerInputs.get(id).length?(power?.input.get(id)??0):(powerRequests.get(id)??0),powerBasis:powerInputs.get(id).length?'allocated':'unconnected-bench'});
    for(let coupled=0;coupled<4;coupled++){
      const powerCaps=new Map(),powerSources=new Map(),powerStores=new Set();
      for(const [id,c]of components){
        const relaysPower=c.powerRelay&&powerEdges.some(edge=>edge.from.component===id);
        const energy=this.#energy(c,minutes),cap=c.powerSource||relaysPower?energy.capacity:energy.demand*(this.#equations.hasPhase(id,'energy')?1:c.availability);
        powerCaps.set(id,c.descriptor.type==='breaker'&&!c.conducting?0:cap);
        if(c.powerSource){powerSources.set(id,c.storesPower?Math.min(cap,c.state.inventory/scale*(1-c.parameters.loss)):cap*fuelFactors.get(id));if(c.storesPower)powerStores.add(id);}
        else if(c.powerRelay&&!powerInputs.get(id).length)powerSources.set(id,cap);
      }
      power=this.#network('power',powerCaps,powerSources,powerStores,scale);
      for(const [id,c]of components){const request=this.#energy(c,minutes).demand;powerRequests.set(id,request);powerFactors.set(id,powerInputs.get(id).length?(request>EPS?clamp(power.input.get(id)/request,0,1):1):1);}
      connected=new Map([...components].map(([id,c])=>[id,communicating(c)&&(c.powerSource||powerFactors.get(id)>EPS)]));
      for(let pass=0;pass<components.size+1;pass++){
        const next=new Map(connected);
        for(const[id,c]of components){const feeds=dataEdges.filter(edge=>edge.to.component===id);if(feeds.length&&['controller','network'].includes(c.kind))next.set(id,connected.get(id)&&feeds.every(edge=>connected.get(edge.from.component)));}
        connected=next;
      }
      const resourceCaps=new Map(),resourceSources=new Map(),resourceStores=new Set();
      for(const[id,c]of components){
        const commandFeeds=dataEdges.filter(edge=>edge.to.component===id&&/control|command|actuat/.test(edge.to.port));
        const control=commandFeeds.length?Math.min(...commandFeeds.map(edge=>connected.get(edge.from.component)?components.get(edge.from.component).state.signal/100:0)):1;
        controlFactors.set(id,control);
        let reliefCapacity;
        if(c.descriptor.type==='relief-valve'&&!c.state.open){const upstream=Math.max(0,...resourceInputs.get(id).map(edge=>components.get(edge.from.component).state.pressure));if(upstream>c.parameters.warningAt)reliefCapacity=c.parameters.capacity*c.availability;}
        conductingFactors.set(id,c.conducting||reliefCapacity!==undefined);
        const cap=c.materialParticipant?this.#resourceCapacity(c,powerFactors.get(id),control,minutes,reliefCapacity,powerSupply(id)):0;
        resourceCaps.set(id,cap);
        if(c.storesResource){resourceSources.set(id,Math.min(cap,c.state.inventory/scale));resourceStores.add(id);}
        else if(c.kind==='source'||!resourceInputs.get(id).length)resourceSources.set(id,cap);
      }
      resource=this.#network('resource',resourceCaps,resourceSources,resourceStores,scale);
      for(const[id,c]of components)if(c.kind==='generator'&&resourceInputs.get(id).length)fuelFactors.set(id,clamp(resource.input.get(id)/Math.max(EPS,this.#resourceCapacity(c,1,1,minutes,undefined,powerSupply(id))),0,1));
    }
    const records=new Map();
    for(const[id,c]of components){
      const incoming=resource.incoming.get(id),outgoing=resource.outgoing.get(id),input=resource.input.get(id);
      const bench=!incoming.length&&!outgoing.length&&c.materialParticipant&&!c.storesResource&&!c.powerRelay;
      const output=bench?this.#resourceCapacity(c,powerFactors.get(id),1,minutes,undefined,powerSupply(id)):resource.output.get(id);
      const upstream=incoming.map(edge=>components.get(edge.from.component));
      const powerOutput=power.output.get(id)||(!power.outgoing.get(id).length&&c.powerSource?(c.storesPower?Math.min(this.#energy(c,minutes).capacity,c.state.inventory/scale*(1-c.parameters.loss)):this.#energy(c,minutes).capacity*fuelFactors.get(id)):0);
      const operatingPowerFactor=c.powerSource?(powerOutput>EPS||power.input.get(id)>EPS?1:0):powerFactors.get(id);
      records.set(id,{flow:output,resourceIn:input,resourceOut:output,stock:c.storesResource||c.storesPower?c.state.inventory:0,
        pressure:c.state.pressure,temperature:c.state.temperature,load:c.state.operating*c.availability*operatingPowerFactor,
        damage:c.state.damage,power:powerOutput||power.input.get(id),powerIn:power.input.get(id),powerOut:powerOutput,powerRequested:this.#energy(c,minutes).demand,powerFactor:operatingPowerFactor,
        signal:c.state.signal,quality:clamp(100-c.parameters.loss*100-c.state.damage*.25),connected:connected.get(id),
        blocked:this.#resourceCapacity(c,1,1,minutes,undefined,powerSupply(id))>EPS?clamp(1-output/this.#resourceCapacity(c,1,1,minutes,undefined,powerSupply(id)),0,1):0,
        upstreamPressure:upstream.length?sum(upstream.map(source=>source.state.pressure))/upstream.length:0,
        upstreamTemperature:upstream.length?sum(upstream.map(source=>source.state.temperature))/upstream.length:0,
        heatIn:sum(this.#edges.filter(edge=>edge.channel==='thermal'&&edge.to.component===id).map(edge=>components.get(edge.from.component).state.temperature*components.get(edge.from.component).availability)),
        overload:c.powerSource&&power.requested.get(id)>this.#energy(c,minutes).capacity*fuelFactors.get(id)+EPS,
        missingSignal:dataEdges.some(edge=>edge.to.component===id&&!connected.get(edge.from.component)),
        signalInputs:dataEdges.filter(edge=>edge.to.component===id&&connected.get(edge.from.component)).map(edge=>components.get(edge.from.component).state.signal),measurements:[],leak:c.storesResource?Math.min(c.stockLeak(),Math.max(0,c.state.inventory/scale+input-output)):0,overflow:0,
      });
    }
    for(const[id,record]of records)record.measurements=this.#edges.filter(edge=>edge.channel==='measurement'&&edge.to.component===id).map(edge=>records.get(edge.from.component));
    const rates=new Map([...resource.rates,...power.rates]);
    for(const edge of this.#edges){
      const source=components.get(edge.from.component),target=components.get(edge.to.component);
      if(edge.channel==='data')rates.set(edge.id,connected.get(edge.from.component)&&connected.get(edge.to.component)?source.state.signal:0);
      if(edge.channel==='measurement')rates.set(edge.id,target.availability>0&&powerFactors.get(target.id)>EPS?1:0);
      if(edge.channel==='thermal')rates.set(edge.id,source.availability>0&&target.availability>0?source.state.temperature:0);
    }
    const acceptedStates=new Map([...components].map(([id,c])=>[id,{core:{...c.state},gates:{healthFactor:c.healthFactor,operatingFraction:c.state.operating/100,enabled:c.state.enabled,conducting:conductingFactors.get(id),powerFactor:records.get(id).powerFactor,controlFactor:controlFactors.get(id)}}]));
    return{records,rates,resource,power,controlFactors,acceptedStates,powerSupplies:new Map([...components.keys()].map(id=>[id,powerSupply(id)]))};
  }
  #visual(component,record){
    const state=component.state,visual={};
    for(const[key,field]of Object.entries(component.descriptor.visualFields)){
      if(key==='active')visual[key]=component.availability>0&&record.powerFactor>EPS&&(component.kind==='sensor'||component.kind==='network'||component.kind==='controller'?record.connected:record.load>EPS);
      else if(key==='running')visual[key]=this.#running;
      else if(key==='fault')visual[key]=state.failed&&(component.availability<=EPS||['sensor','controller','network'].includes(component.kind));
      else if(key==='status')visual[key]=!record.connected||record.powerFactor<=EPS?'offline':state.failed||state.warning?'warning':'normal';
      else if(key==='open')visual[key]=state.open;
      else if(key==='opening')visual[key]=component.conducting?record.load:0;
      else if(key==='connected')visual[key]=record.connected;
      else if(key==='damage')visual[key]=state.mode!=='none'?state.mode:state.damage>=20?component.descriptor.failureModes[0].id:'none';
      else if(key==='level')visual[key]=component.kind==='sensor'?state.signal:state.inventory;
      else if(key==='load'||key==='speed')visual[key]=component.kind==='sensor'&&component.descriptor.type==='electrical-meter'?state.signal:record.load;
      else if(key==='temperature')visual[key]=displayValue(state.temperature,field);
      else if(key==='value'){
        const measuredEdge=this.#edges.find(edge=>edge.channel==='measurement'&&edge.to.component===component.id);
        const measured=measuredEdge?this.#components.get(measuredEdge.from.component):null;
        const range=component.descriptor.type==='temperature-sensor'?measured?.descriptor.visualFields.temperature:component.descriptor.type==='pressure-transmitter'&&measured?.descriptor.type==='wellhead'?measured.descriptor.visualFields.value:null;
        visual[key]=component.descriptor.type==='wellhead'?displayValue(state.pressure,field):range?clamp(displayValue(state.signal,range),field.min,field.max):clamp(state.signal,field.min,field.max);
      }
      else visual[key]=field.default;
    }
    return visual;
  }
  #refresh(){
    this.#solution=this.#solve();const components={},controls={},readings={},parameters={};
    for(const[id,component]of this.#components){const record=this.#solution.records.get(id);components[id]=this.#visual(component,record);controls[id]={enabled:component.state.enabled,load:component.state.load,open:component.state.open,fault:component.state.failed,level:component.state.inventory};parameters[id]={...component.parameters};
      readings[id]=Object.fromEntries(Object.entries(record).filter(([key,value])=>typeof value==='number'||typeof value==='boolean'));}
    this.#snapshot=freeze({format:'scada-placeholder-state',version:1,scenarioId:this.#definition.scenarioId,minutes:this.#minutes,running:this.#running,
      components,controls,readings,parameters,flows:Object.fromEntries([...this.#solution.rates].map(([id,rate])=>[id,rate>EPS])),flowRates:Object.fromEntries(this.#solution.rates),
      channels:Object.fromEntries(this.#edges.map(edge=>[edge.id,edge.channel])),events:structuredClone(this.#events),assumptions:[...this.#definition.assumptions]});
  }
  #checkStep(minutes){bounded(minutes,Number.MIN_VALUE,60,'Step duration');if(this.#minutes+minutes>MAX_MINUTES)throw new RangeError('Elapsed time limit reached.');if(this.#nextEventId+Math.ceil(minutes)*this.#components.size>=1e9)throw new RangeError('Event sequence limit reached; reset to begin a new history.');return minutes;}
  step(minutes=1){return this.#transaction(()=>this.#step(minutes));}
  #step(minutes=1){
    this.#checkStep(minutes);
    let remaining=minutes;
    while(remaining>EPS){const duration=Math.min(1,remaining);for(const component of this.#components.values())component.operatingStep(duration,this.#equations.has(component.id)?(phase,defaults)=>this.#evaluate(component,phase,{dtMinutes:duration},defaults):undefined);
      const solution=this.#solve(duration),before=new Map([...this.#components].map(([id,c])=>[id,{failed:c.state.failed,warning:c.state.warning}]));
      for(const[id,c]of this.#components){const context=solution.records.get(id);
        if(c.storesResource){const change=(context.resourceIn-context.resourceOut-context.leak)*duration/10;context.overflow=Math.max(0,c.state.inventory+change-100);c.state.inventory=clamp(c.state.inventory+change);}
        if(c.storesPower)c.state.inventory=clamp(c.state.inventory+(context.powerIn*(1-c.parameters.loss)-context.powerOut/Math.max(.01,1-c.parameters.loss))*duration/10);
        const randomSample=this.#random(),previous={...c.state};
        c.conditionStep(duration,context,randomSample,this.#equations.has(id)?(phase,defaults)=>this.#evaluate(c,phase,{dtMinutes:duration,readings:context,previous,...solution.powerSupplies.get(id),gates:{powerFactor:context.powerFactor,controlFactor:solution.controlFactors.get(id)},...(phase==='condition'?{randomSample}:{})},defaults):undefined);
      }
      for(const[id,c]of this.#components)if(this.#equations.has(id)){const readings=solution.records.get(id);this.#equations.advance(id,this.#equationContext(c,{dtMinutes:duration,readings,...solution.powerSupplies.get(id),gates:{powerFactor:readings.powerFactor,controlFactor:solution.controlFactors.get(id)},accepted:{resourceIn:readings.resourceIn,resourceOut:readings.resourceOut,energyIn:readings.powerIn,energyOut:readings.powerOut,...solution.powerSupplies.get(id),...solution.acceptedStates.get(id)}}));}
      this.#minutes+=duration;remaining-=duration;
      for(const[id,c]of this.#components){const previous=before.get(id);if(!previous.failed&&c.state.failed)this.#record(`Stress damage latched ${c.state.mode}.`,'failure',id,'critical');else if(!previous.warning&&c.state.warning)this.#record('Illustrative stress or supply warning.','warning',id,'warning');else if(previous.warning&&!c.state.warning)this.#record('Illustrative warning cleared.','recovery',id);}
    }
    this.#refresh();this.#emit({type:'step'});return this.#snapshot;
  }
  #equipment(id){const component=this.#components.get(id);if(!component)throw new RangeError(`Unknown equipment: ${id}`);return component;}
  dispatch(input){return this.#transaction(()=>this.#dispatch(input));}
  #dispatch(input){
    const command=safeData(input);keys(command,['id','label','component','action','arguments'],'command');
    const args=command.arguments??{};keys(args,['equipment','value','key','minutes','payload'],'command arguments');
    const id=args.equipment??command.component;
    if(command.action==='import')return this.importSnapshot(args.payload??args.value);
    if(command.action==='reset')return this.reset();
    if(command.action==='step'){const duration=this.#checkStep(args.minutes??args.value??1);this.#running=false;return this.step(duration);}
    if(this.#nextEventId+this.#components.size>=1e9)throw new RangeError('Event sequence limit reached; reset to begin a new history.');
    if(command.action==='setRunning'){boolean(args.value,'Running');this.#running=args.value;this.#record(`Simulation ${args.value?'running':'paused'}.`,'transport');}
    else if(command.action==='repair'){
      const targets=id==null||id==='all'?[...this.#components.values()]:[this.#equipment(id)];
      for(const component of targets){component.state.failed=false;component.state.damage=0;component.state.mode='none';component.state.warning=false;const label=this.#system.components.find(item=>item.id===component.id)?.label??component.id;this.#record(`${label}: repaired model damage; switch settings were retained.`,'repair',component.id);}
    }else{
      const component=this.#equipment(id),state=component.state;
      if(command.action==='setEnabled'){boolean(args.value,'Enabled');state.enabled=args.value;}
      else if(command.action==='setOpen'){boolean(args.value,'Open');state.open=args.value;}
      else if(command.action==='setLoad')state.load=bounded(args.value,0,100,'Operating level');
      else if(command.action==='setLevel')state.inventory=bounded(args.value,0,100,'Stock level');
      else if(command.action==='setDamage'){state.damage=bounded(args.value,0,100,'Damage');if(state.damage>=100){state.failed=true;state.mode=component.descriptor.failureModes[0].id;}}
      else if(command.action==='setFault'){
        if(args.value===false||args.value==='none'){state.failed=false;state.damage=0;state.mode='none';}
        else{const mode=component.descriptor.failureModes.find(mode=>mode.id===(args.value===true?component.descriptor.failureModes[0].id:args.value));if(!mode)throw new RangeError('Unknown component failure mode.');state.failed=true;state.mode=mode.id;state.damage=Math.max(state.damage,mode.initialDamage);if(mode.effect==='overheat')state.temperature=Math.max(state.temperature,90);}
      }else if(command.action==='setParameter'){
        const parameter=component.descriptor.parameters.find(item=>item.key===args.key);if(!parameter)throw new RangeError('Unknown model parameter.');bounded(args.value,parameter.min,parameter.max,parameter.label);
        const next=this.exportModelDefinition();next.components[id].parameters[args.key]=args.value;const checked=validatePlaceholderModelDefinition(this.#system,next);if(!checked.ok)throw new TypeError(checked.errors[0].message);this.#definition=checked.definition;component.parameters={...this.#definition.components[id].parameters};
      }else throw new RangeError(`Unknown model command: ${command.action}`);
      const label=this.#system.components.find(item=>item.id===id)?.label??id;
      const parameter=component.descriptor.parameters.find(item=>item.key===args.key);
      const wording={setEnabled:`switched ${args.value?'on':'off'}`,setOpen:args.value?'opened':'closed',setLoad:`${component.descriptor.visualFields.opening?'opening setpoint':'operating level'} set to ${args.value}%`,setLevel:`inventory index set to ${args.value}`,setDamage:`illustrative damage set to ${args.value}%`,setFault:state.failed?`injected ${component.descriptor.failureModes.find(mode=>mode.id===state.mode)?.label??'equipment'} damage`:'repaired faults and damage',setParameter:parameter?`${parameter.label.toLowerCase()} set to ${args.value} ${parameter.unit}`:'model estimate changed'};
      this.#record(`${label}: ${wording[command.action]}.`,'operator',id,command.action==='setFault'&&state.failed?(component.availability>0?'warning':'critical'):'info');
    }
    this.#refresh();this.#emit({type:'command',action:command.action});return this.#snapshot;
  }
  reset(){return this.#transaction(()=>this.#reset());}
  #reset(){this.#minutes=0;this.#randomState=this.#definition.seed;this.#events=[];this.#nextEventId=1;this.#buildComponents();this.#equations.reset(id=>this.#equationContext(this.#components.get(id)));this.#initializeSignals();this.#record('Reset with current model parameters.','reset');this.#refresh();this.#emit({type:'reset',resetPresentation:true});return this.#snapshot;}
  exportModelDefinition(){return structuredClone(this.#definition);}
  exportSnapshot(){return{format:'scada-placeholder-snapshot',version:1,system:{id:this.#definition.scenarioId,signature:this.#signature},model:this.exportModelDefinition(),state:{minutes:this.#minutes,running:this.#running,randomState:this.#randomState,nextEventId:this.#nextEventId,components:Object.fromEntries([...this.#components].map(([id,c])=>[id,structuredClone(c.state)])),events:structuredClone(this.#events)},...(this.#equations.hasBindings?{equationState:this.#equations.exportState()}: {})};}
  importSnapshot(input){return this.#transaction(()=>this.#importSnapshot(input));}
  #importSnapshot(input){
    const payload=safeData(input);keys(payload,['format','version','system','model','state','equationState'],'snapshot');
    if(payload.format!=='scada-placeholder-snapshot'||payload.version!==1)throw new TypeError('Expected a placeholder snapshot version 1.');
    keys(payload.system,['id','signature'],'snapshot system');if(payload.system.id!==this.#definition.scenarioId||payload.system.signature!==this.#signature)throw new TypeError('Snapshot belongs to a different scenario or topology.');
    const checked=validatePlaceholderModelDefinition(this.#system,payload.model);if(!checked.ok)throw new TypeError(checked.errors.map(error=>error.message).join('; '));
    const state=payload.state;keys(state,['minutes','running','randomState','nextEventId','components','events'],'snapshot state');bounded(state.minutes,0,MAX_MINUTES,'Elapsed minutes');boolean(state.running,'Running');
    for(const[key,max]of [['randomState',4294967295],['nextEventId',1e9]])if(!Number.isInteger(state[key])||state[key]<1||state[key]>max)throw new RangeError(`Invalid ${key}.`);
    keys(state.components,[...this.#components.keys()],'snapshot components');if(Object.keys(state.components).length!==this.#components.size)throw new TypeError('Snapshot must include every component.');
    for(const[id,component]of this.#components){const restored=state.components[id];keys(restored,[...BOOLEAN_STATE,...NUMBER_STATE,'mode'],'component state');if(Object.keys(restored).length!==BOOLEAN_STATE.length+NUMBER_STATE.length+1)throw new TypeError('Component snapshot is incomplete.');for(const key of BOOLEAN_STATE)boolean(restored[key],key);for(const key of NUMBER_STATE)bounded(restored[key],0,100,key);if(restored.mode!=='none'&&!component.descriptor.failureModes.some(mode=>mode.id===restored.mode))throw new RangeError('Unknown saved failure mode.');if(restored.failed!==(restored.mode!=='none'))throw new TypeError('A latched failure and its saved mode must agree.');if(restored.damage>=100&&!restored.failed)throw new TypeError('Complete damage must latch a failure.');}
    if(!Array.isArray(state.events)||state.events.length>100)throw new TypeError('Snapshot event history must contain at most 100 entries.');let lastId=0,lastTime=0;
    for(const event of state.events){keys(event,['id','minutes','type','severity','equipment','message'],'event');if(!Number.isInteger(event.id)||event.id<=lastId||event.id>=state.nextEventId)throw new TypeError('Event IDs must increase before the next sequence.');bounded(event.minutes,lastTime,state.minutes,'Event time');for(const key of ['type','severity','equipment','message'])if(typeof event[key]!=='string'||!event[key]||event[key].length>(key==='message'?500:100))throw new TypeError('Invalid event text.');if(!['info','warning','critical'].includes(event.severity)||!(event.equipment==='system'||this.#components.has(event.equipment)))throw new TypeError('Invalid event severity or equipment.');lastId=event.id;lastTime=event.minutes;}
    const equations=this.#equations.withDefinition(checked.definition,{initialize:false});equations.importState(payload.equationState);
    this.#definition=checked.definition;this.#equations=equations;this.#buildComponents();for(const[id,component]of this.#components)component.state={...state.components[id]};
    this.#minutes=state.minutes;this.#running=state.running;this.#randomState=state.randomState;this.#events=state.events;this.#nextEventId=state.nextEventId;this.#refresh();this.#emit({type:'import',resetPresentation:true});return this.#snapshot;
  }
  setEquationBindings(equations){return this.#transaction(()=>{
    const next=this.exportModelDefinition();
    if(equations===undefined||equations===null)delete next.equations;else next.equations=safeData(equations);
    const checked=validatePlaceholderModelDefinition(this.#system,next);
    if(!checked.ok)throw new TypeError(checked.errors.map(error=>error.message).join('; '));
    const candidate=this.#equations.withDefinition(checked.definition,{initialize:false});
    candidate.reset(id=>this.#equationContext(this.#components.get(id)));
    this.#definition=checked.definition;this.#equations=candidate;this.#refresh();
    this.#emit({type:'equations'});return this.#snapshot;
  });}
  start({intervalMs=1000,minutesPerTick=1}={}){bounded(intervalMs,50,60000,'Clock interval');bounded(minutesPerTick,Number.MIN_VALUE,60,'Clock step');if(this.#timer!==null)return this;this.#timer=this.#clock.setInterval(()=>{if(this.#running){try{this.step(minutesPerTick);}catch(error){
    this.#running=false;this.stop();const message=formatEquationError(error,500);
    if(this.#nextEventId<1e9)this.#record(message,'error','system','critical');
    else{
      // An imported exhausted sequence still needs a visible terminal error.
      // Reuse only its final slot, keeping the bounded history importable.
      const terminal={id:this.#nextEventId-1,minutes:this.#minutes,type:'error',severity:'critical',equipment:'system',message};
      if(this.#events.at(-1)?.id===terminal.id)this.#events.pop();
      this.#events.push(terminal);if(this.#events.length>100)this.#events.shift();
    }
    // A provider can also fail during refresh; retain the last accepted readouts
    // while exposing the paused clock and error history without rerunning it.
    try{this.#refresh();}catch{this.#snapshot=freeze({...this.#snapshot,running:false,components:Object.fromEntries(Object.entries(this.#snapshot.components).map(([id,state])=>[id,Object.hasOwn(state,'running')?{...state,running:false}:state])),events:structuredClone(this.#events)});}
    this.#emit({type:'error',message});
  }}},intervalMs);this.#timer?.unref?.();return this;}
  stop(){if(this.#timer!==null)this.#clock.clearInterval(this.#timer);this.#timer=null;return this;}
  destroy(){this.stop();this.#listeners.clear();}
}

/** Stable public session identity. Version 1 keeps its original solver and
 * snapshots; version 2 owns explicit circuits and conversions. */
export class PlaceholderSystemModel {
  #implementation;
  constructor(system,definition,options){
    this.#implementation=definition?.version===2
      ? new CircuitSystemModel(system,definition,options)
      : new LegacyPlaceholderSystemModel(system,definition,options);
  }
  get clockStarted(){return this.#implementation.clockStarted;}
  getSnapshot(){return this.#implementation.getSnapshot();}
  subscribe(listener){return this.#implementation.subscribe(listener);}
  dispatch(command){return this.#implementation.dispatch(command);}
  step(minutes){return this.#implementation.step(minutes);}
  reset(){return this.#implementation.reset();}
  exportModelDefinition(){return this.#implementation.exportModelDefinition();}
  exportSnapshot(){return this.#implementation.exportSnapshot();}
  importSnapshot(payload){return this.#implementation.importSnapshot(payload);}
  setEquationBindings(equations){return this.#implementation.setEquationBindings(equations);}
  start(options){this.#implementation.start(options);return this;}
  stop(){this.#implementation.stop();return this;}
  destroy(){return this.#implementation.destroy();}
}
