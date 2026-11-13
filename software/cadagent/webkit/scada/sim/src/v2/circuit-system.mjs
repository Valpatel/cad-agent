import {validateV2Definition,safeClone} from './validation.mjs';
import {createEquationRuntime} from '../equations/runtime.mjs';
import {formatEquationError} from '../equations/contracts.mjs';
import {getV2Descriptor,channel,domain,clamp,freeze,clone,TRACERS,ZONE_FIELDS} from './contract.mjs';

const EPS=1e-9, sum=items=>items.reduce((a,b)=>a+b,0), sorted=object=>Object.entries(object).sort(([a],[b])=>a.localeCompare(b));
const mapsClose=(a,b)=>a.size===b.size&&[...a].every(([key,value])=>Math.abs(value-(b.get(key)??0))<1e-9);
const key=(component,circuit)=>JSON.stringify([component,circuit]);
const bounded=(value,min,max,label)=>{if(typeof value!=='number'||!Number.isFinite(value)||value<min||value>max)throw new RangeError(`${label} must be ${min}–${max}.`);return value;};
const bool=(value,label)=>{if(typeof value!=='boolean')throw new TypeError(`${label} must be boolean.`);return value;};
const MODELS_WITH_CYCLES=new Set(['media-grow-bed','ebb-flow-table']);
function topologySignature(system,definition){
  const canonical=value=>Array.isArray(value)?value.map(canonical):value&&typeof value==='object'?Object.fromEntries(Object.keys(value).sort().map(k=>[k,canonical(value[k])])):value;
  return JSON.stringify(canonical({id:system.system.id,components:system.components.map(c=>[c.id,c.type]).sort(),edges:system.connections.map(e=>[e.id,e.from,e.to,e.medium]).sort(),models:sorted(definition.components).map(([id,c])=>[id,{model:c.model,variant:c.variant,circuits:sorted(c.circuits).map(([name,v])=>[name,v.ports.slice().sort(),v.medium,v.fluid,v.role]),thermalStore:Boolean(c.thermalStore),thermalLinks:c.thermalLinks?.map(v=>[v.id,v.from,v.to]).sort(),heatSource:c.heatSource?{target:c.heatSource.target,supply:c.heatSource.supply}:null,energy:c.energy?{role:c.energy.role,inputs:c.energy.inputs,outputs:c.energy.outputs,supply:c.energy.supply,store:Boolean(c.energy.store),requiredCircuits:c.energy.requiredCircuits,modes:c.energy.modes}:null,zone:c.zone}]),directions:definition.connections,zones:Object.keys(definition.zones).sort()}));
}

export class CircuitSystemModel {
  #system;#definition;#descriptors=new Map();#owners=new Map();#state;#snapshot;#listeners=new Set();#timer=null;#clock;#signature;#equations;
  constructor(system,definition,{equationProviders=[],clock={setInterval:(fn,ms)=>globalThis.setInterval(fn,ms),clearInterval:id=>globalThis.clearInterval(id)}}={}){
    const validation=validateV2Definition(system,definition);if(!validation.ok)throw new TypeError(validation.errors.map(e=>`${e.path}: ${e.message}`).join('; '));
    this.#system=freeze(safeClone(system));this.#definition=validation.definition;this.#clock=clock;
    this.#signature=topologySignature(this.#system,this.#definition);
    for(const item of this.#system.components){const descriptor=getV2Descriptor(item.type,this.#definition.components[item.id].variant??item.variant);this.#descriptors.set(item.id,descriptor);this.#owners.set(item.id,new Map(Object.entries(this.#definition.components[item.id].circuits).flatMap(([id,c])=>c.ports.map(port=>[port,id]))));}
    this.#resetState(true);
    this.#equations=createEquationRuntime({system:this.#system,definition:this.#definition,engineVersion:2,providers:equationProviders,initialize:false});
    this.#equations.reset(id=>this.#context(id));
    this.#refresh();
  }
  #resetState(running){
    const components={},circuits={},thermalStores={},energyStores={};
    for(const[id,c]of sorted(this.#definition.components)){
      const descriptor=this.#descriptors.get(id);
      const faultMode=c.initial.damage>=100?descriptor.visualFields.damage?.options?.find(mode=>mode!=='none')??'failed':'none';
      components[id]={...c.initial,operating:c.initial.load,faultMode,signal:0,valid:true,phase:MODELS_WITH_CYCLES.has(descriptor.type)?'filling':'idle',phaseElapsed:0,moisture:50};
      circuits[id]={};for(const[cid,config]of sorted(c.circuits)){
        const amount=config.role==='sink'?0:config.initial.inventory*config.parameters.stockScale;
        circuits[id][cid]={amount,heat:amount*config.parameters.thermalCapacity*config.initial.temperature/100,pressure:config.initial.pressure,tracers:Object.fromEntries(TRACERS.map(name=>[name,amount*(config.initial.tracers[name]??0)/100]))};
      }
      if(c.thermalStore)thermalStores[id]=c.thermalStore.capacity*c.thermalStore.initial/100;
      if(c.energy?.store)energyStores[id]=c.energy.store.capacity*c.energy.store.initial/100;
    }
    this.#state={minutes:0,running,randomState:this.#definition.seed,nextEventId:1,components,circuits,thermalStores,energyStores,zones:Object.fromEntries(sorted(this.#definition.zones).map(([id,z])=>[id,clone(z.initial)])),events:[],ledger:{resourceBoundaryIn:0,resourceBoundaryOut:0,resourceLeak:0,energyBoundaryIn:0,energyBoundaryOut:0,energyLoss:0,heatBoundaryIn:0,heatBoundaryOut:0}};
  }
  get clockStarted(){return this.#timer!==null;}
  getSnapshot(){return this.#snapshot;}
  subscribe(listener){if(typeof listener!=='function')throw new TypeError('Listener must be a function.');this.#listeners.add(listener);return()=>this.#listeners.delete(listener);}
  #emit(event){for(const listener of [...this.#listeners]){try{listener(this.#snapshot,freeze(event));}catch(error){globalThis.reportError?.(error);}}}
  #record(message,type='operator',equipment='system',severity='info'){
    if(this.#state.nextEventId>=1e9)throw new RangeError('Event sequence limit reached.');this.#state.events.push({id:this.#state.nextEventId++,minutes:this.#state.minutes,type,equipment,severity,message});if(this.#state.events.length>100)this.#state.events.shift();
  }
  #context(id,extra={}){
    return{core:{...this.#state.components[id],circuits:this.#state.circuits[id],thermalStore:this.#state.thermalStores[id]??null,energyStore:this.#state.energyStores[id]??null},configuration:this.#definition.components[id],timeMinutes:this.#state.minutes,dtMinutes:extra.dtMinutes??0,...extra};
  }
  #equation(id,phase,context,defaults){
    // Default arithmetic takes the original path; trusted callbacks receive only
    // defensive frozen plain-data contexts through the shared runtime.
    return this.#equations.hasPhase(id,phase)?this.#equations.evaluate(id,phase,this.#context(id,context),defaults):defaults;
  }
  #accepted(id,solution,heat={}){
    const circuits=Object.fromEntries(Object.keys(this.#definition.components[id].circuits).map(cid=>[cid,{input:solution.resource.input.get(key(id,cid))??0,output:solution.resource.output.get(key(id,cid))??0}]));
    return{circuits,...(solution.acceptedGates?{core:solution.acceptedCore[id],gates:solution.acceptedGates[id]}:{}),resourceIn:sum(Object.values(circuits).map(c=>c.input)),resourceOut:sum(Object.values(circuits).map(c=>c.output)),energyIn:solution.energy.input[id]??0,energyOut:solution.energy.output[id]??0,auxiliaryEnergy:solution.energy.auxiliary[id]??0,powerFactor:solution.energy.powerFactors[id]??1,heatSource:heat.heatSource??0,thermalLoss:heat.thermalLoss??0};
  }
  #powerContext(id,energy){
    return{availablePower:energy?.input[id]??0,ratedDemand:this.#definition.components[id].energy?.demand??0,powerBasis:this.#definition.components[id].energy?'allocated':'unavailable'};
  }
  #healthFactor(id){const mode=this.#state.components[id].faultMode;if(mode==='none')return 1;if(/leak|fouled|worn|drift|corrod|cooling-loss|air-loss|torn/.test(mode))return .35;return 0;}
  #health(id){return this.#state.components[id].enabled?this.#healthFactor(id):0;}
  #observationSource(id){
    return Boolean(this.#definition.components[id].observation)||this.#descriptors.get(id).ports.some(port=>channel(port.medium)==='measurement'&&port.direction!=='out');
  }
  #operating(id){return this.#state.components[id].operating/100*this.#health(id);}
  #mode(id){const c=this.#definition.components[id],s=this.#state.components[id];return c.energy?.modes?.[s.mode]??'forward';}
  #edges(){return this.#system.connections.map(edge=>{
    const control=this.#definition.connections[edge.id]?.mode,direction=control?(control.values[this.#state.components[control.equipment].mode]??0):1;
    const from=direction<0?edge.to:edge.from,to=direction<0?edge.from:edge.to,d=this.#descriptors.get(from.component),port=d.ports.find(p=>p.id===from.port);
    return{...edge,from,to,direction,channel:channel(edge.medium??port.medium),domain:domain(d,port.id)};
  }).sort((a,b)=>a.id.localeCompare(b.id));}
  #energyPlan(id,dt,resource){
    const c=this.#definition.components[id],e=c.energy;if(!e)return null;const mode=this.#mode(id),reverse=mode==='reverse',type=this.#descriptors.get(id).type;let inputs=reverse?e.outputs:e.inputs,outputs=reverse?e.inputs:e.outputs;
    if(type==='automatic-transfer-switch'){inputs=[this.#state.components[id].mode==='source-b'?'source-b':'source-a'];outputs=['load'];}
    const aux=this.#descriptors.get(id).ports.filter(p=>['supply','field','auxiliary'].includes(p.id)&&channel(p.medium)==='energy'&&p.direction!=='out'&&!inputs.includes(p.id)&&!outputs.includes(p.id)).map(p=>p.id);
    const isolated=['breaker','hv-circuit-breaker','disconnect-switch','switchgear-panel','gis-bay'].includes(type)&&this.#state.components[id].open;
    const capacity=isolated?0:Math.min(e.capacity,c.parameters.capacity)*this.#operating(id),health=this.#health(id);
    const accepted={circuits:Object.fromEntries(Object.keys(c.circuits).map(cid=>[cid,{input:resource?.input.get(key(id,cid))??0,output:resource?.output.get(key(id,cid))??0}]))};
    accepted.resourceIn=sum(Object.values(accepted.circuits).map(value=>value.input));accepted.resourceOut=sum(Object.values(accepted.circuits).map(value=>value.output));
    const values=this.#equation(id,'energy',{dtMinutes:dt,accepted,gates:{health,healthFactor:this.#healthFactor(id),availability:health,operatingFraction:this.#state.components[id].operating/100,controlFactor:1,conducting:!isolated&&mode!=='idle',mode,enabled:this.#state.components[id].enabled}},{capacity,demand:e.demand*this.#operating(id),efficiency:e.efficiency,auxiliaryDemand:c.parameters.demand});
    return{...e,inputs,outputs,aux,mode,...values,capacity:isolated||health<=EPS?0:Math.min(values.capacity,e.capacity,c.parameters.capacity),demand:health<=EPS?0:Math.min(values.demand,e.demand),auxiliaryDemand:Math.min(values.auxiliaryDemand,c.parameters.demand)};
  }
  #resource(dt,energy){
    const edges=this.#edges().filter(e=>e.channel==='resource'&&e.direction),nodes=new Map(),adj=new Map();
    const communication=new Map([...this.#descriptors].map(([id,d])=>[id,this.#health(id)>0&&(energy?.powerFactors[id]??1)>EPS&&(!/sensor|probe|monitor|plc|remote-io|network|radio|server|hmi/.test(d.type)||this.#state.components[id].faultMode==='none')]));
    const dataEdges=this.#edges().filter(e=>e.channel==='data'&&e.direction);
    // Missing sensor telemetry does not invent a protective interlock through
    // otherwise healthy controller IO. Control/network outages still propagate.
    for(let pass=0;pass<this.#descriptors.size;pass++)for(const edge of dataEdges)if(!this.#observationSource(edge.from.component)&&!communication.get(edge.from.component))communication.set(edge.to.component,false);
    for(const[id,c]of sorted(this.#definition.components))for(const[cid,config]of sorted(c.circuits)){
      const s=this.#state.circuits[id][cid],own=this.#state.components[id],type=this.#descriptors.get(id).type;
      let availability=this.#health(id),driven=['pump','blower','compressor','motor'].some(word=>type.includes(word));
      if(driven)availability*=energy?.powerFactors[id]??0;
      // A selected law cannot turn a zero-demand power ratio into free drive power.
      // The unselected legacy path retains its existing teaching-model behavior.
      const plan=energy?.plans.get(id),mainDriveRequired=plan&&(plan.role==='load'||plan.role==='converter'||plan.role==='store'&&plan.mode==='charge');
      if(driven&&mainDriveRequired&&this.#equations.has(id)&&(energy?.input[id]??0)<=EPS)availability=0;
      const controlFactor=dataEdges.some(edge=>edge.to.component===id&&/control|command/.test(edge.to.port)&&!communication.get(edge.from.component))?0:1;
      if(!controlFactor)availability=0;
      if(/valve|intake-gate/.test(type)&&!own.open)availability=0;
      if(MODELS_WITH_CYCLES.has(type)&&own.phase==='holding')availability=0;
      if(type==='reversible-pump-turbine'&&this.#mode(id)==='idle')availability=0;
      if(type==='aeroponic-chamber')availability*=c.parameters.mistDuty/100;
      const operatingFraction=own.operating/100,operationFactor=/valve|pump|gate|blower|compressor/.test(type)?operatingFraction:1;
      const capacity=this.#equation(id,'resource',{dtMinutes:dt,...this.#powerContext(id,energy),circuit:{id:cid,configuration:config,state:s},gates:{health:this.#health(id),healthFactor:this.#healthFactor(id),availability,powerFactor:energy?.powerFactors[id]??(driven?0:1),operatingFraction,controlFactor,conducting:availability>EPS,mode:this.#mode(id),enabled:own.enabled}},{capacity:Math.min(config.parameters.capacity,c.parameters.capacity)*availability*operationFactor}).capacity;
      const record={id,cid,config,state:s,controlFactor,availability,capacity:this.#equations.has(id)?(availability<=EPS?0:Math.min(capacity,config.parameters.capacity,c.parameters.capacity)):capacity,driven:driven&&availability>EPS,boundary:config.role==='source',max:100*config.parameters.stockScale};
      nodes.set(key(id,cid),record);adj.set(key(id,cid),[]);
    }
    const links=edges.map(edge=>({...edge,a:key(edge.from.component,this.#owners.get(edge.from.component).get(edge.from.port)),b:key(edge.to.component,this.#owners.get(edge.to.component).get(edge.to.port))}));
    for(const edge of links){adj.get(edge.a).push(edge.b);adj.get(edge.b).push(edge.a);}
    const allowed=new Set(),visited=new Set();
    for(const start of nodes.keys())if(!visited.has(start)){
      const group=[],pending=[start];let driver=false,stock=false;
      while(pending.length){const id=pending.pop();if(visited.has(id))continue;visited.add(id);group.push(id);const n=nodes.get(id);driver||=n.boundary||n.driven||['hydro-turbine','reversible-pump-turbine'].includes(this.#descriptors.get(n.id).type)&&this.#mode(n.id)!=='idle';stock||=n.boundary||n.state.amount>EPS;for(const next of adj.get(id))if(!visited.has(next))pending.push(next);}
      if(driver&&stock)group.forEach(id=>allowed.add(id));
    }
    let rates=new Map(links.map(edge=>{
      const source=nodes.get(edge.a),target=nodes.get(edge.b),sourceState=this.#state.components[source.id],targetState=this.#state.components[target.id];
      const sourceCycle=MODELS_WITH_CYCLES.has(this.#descriptors.get(source.id).type),targetCycle=MODELS_WITH_CYCLES.has(this.#descriptors.get(target.id).type);
      const phaseAllows=(!sourceCycle||sourceState.phase==='draining')&&(!targetCycle||targetState.phase==='filling');
      return[edge.id,phaseAllows&&allowed.has(edge.a)&&allowed.has(edge.b)?Math.min(source.capacity,target.capacity):0];
    }));
    const outgoing=new Map([...nodes.keys()].map(id=>[id,links.filter(e=>e.a===id)])),incoming=new Map([...nodes.keys()].map(id=>[id,links.filter(e=>e.b===id)]));
    for(let pass=0;pass<nodes.size+2;pass++){
      let changed=false;
      for(const[id,n]of nodes){
        const outs=outgoing.get(id),ins=incoming.get(id),out=sum(outs.map(e=>rates.get(e.id))),input=sum(ins.map(e=>rates.get(e.id)));
        const available=Math.min(n.capacity,n.config.role==='source'?Infinity:n.state.amount/dt);
        if(out>available+EPS){const factor=available/out;for(const e of outs)rates.set(e.id,rates.get(e.id)*factor);changed=true;}
        const updatedOut=sum(outs.map(e=>rates.get(e.id))),space=Math.min(n.capacity,n.config.role==='sink'?Infinity:(n.max-n.state.amount)/dt+updatedOut);
        if(input>space+EPS){const factor=Math.max(0,space/input);for(const e of ins)rates.set(e.id,rates.get(e.id)*factor);changed=true;}
      }
      if(!changed)break;
    }
    const deliveredRates=new Map(links.map(edge=>[edge.id,rates.get(edge.id)*(1-nodes.get(edge.a).config.parameters.loss)]));
    const input=new Map([...nodes.keys()].map(id=>[id,sum(incoming.get(id).map(e=>deliveredRates.get(e.id)))])),output=new Map([...nodes.keys()].map(id=>[id,sum(outgoing.get(id).map(e=>rates.get(e.id)))]));
    return{nodes,links,rates,deliveredRates,input,output,incoming,outgoing};
  }
  #energy(dt,resource){
    const plans=new Map([...this.#descriptors.keys()].map(id=>[id,this.#energyPlan(id,dt,resource)])),edges=this.#edges().filter(e=>e.channel==='energy'&&e.direction),incoming=(id,ports)=>edges.filter(e=>e.to.component===id&&ports.includes(e.to.port)),outgoing=(id,ports)=>edges.filter(e=>e.from.component===id&&ports.includes(e.from.port));
    const receiverCounts=new Map();for(const edge of edges){const id=`${edge.to.component}/${edge.to.port}`;receiverCounts.set(id,(receiverCounts.get(id)??0)+1);}
    const passLimit=Math.min(4096,Math.max(128,plans.size*16));
    const demands=new Map(),supplies=new Map(),inputEdges=new Map(),outputEdges=new Map(),auxEdges=new Map();
    for(const[id,p]of plans){if(!p)continue;inputEdges.set(id,incoming(id,p.inputs));outputEdges.set(id,outgoing(id,p.outputs));auxEdges.set(id,incoming(id,p.aux));
      let supply=0;
      if(p.role==='boundary')supply=p.capacity;
      if(['source','prime-mover'].includes(p.role)){
        supply=p.capacity;const s=p.supply;
        if(s.kind==='environment')supply*=this.#definition.environment[s.environment]/100;
        if(s.kind==='resource')supply=Math.min(supply,(resource?.input.get(key(id,s.circuit))??0)*p.efficiency);
        if(s.kind==='thermal')supply=Math.min(supply,(this.#state.circuits[id][s.circuit].heat/dt)*p.efficiency,resource?.output.get(key(id,s.circuit))??0);
        for(const circuit of p.requiredCircuits??[])supply=Math.min(supply,resource?.input.get(key(id,circuit))??0);
      }
      if(p.role==='store'&&p.mode==='discharge'){
        supply=Math.min(p.capacity,this.#state.energyStores[id]/dt*p.efficiency);
        if(this.#descriptors.get(id).type==='reversible-pump-turbine'&&resource){const cid=Object.keys(this.#definition.components[id].circuits)[0];supply=Math.min(supply,resource.output.get(key(id,cid))??0);}
      }
      if(p.mode==='idle')supply=0;
      supplies.set(id,supply);demands.set(id,p.role==='boundary'?p.capacity:p.role==='load'?p.demand:p.role==='store'&&p.mode==='charge'?Math.min(p.capacity,(p.store.capacity-this.#state.energyStores[id])/dt/p.efficiency):0);
    }
    let portDemand=new Map();
    let demandConverged=false;
    for(let pass=0;pass<passLimit;pass++){
      const next=new Map();
      for(const[id,p]of plans){if(!p)continue;
        const downstream=sum(outputEdges.get(id).map(edge=>(portDemand.get(`${edge.to.component}/${edge.to.port}`)??0)/receiverCounts.get(`${edge.to.component}/${edge.to.port}`)));
        const missingAux=p.aux.some(port=>!auxEdges.get(id).some(edge=>edge.to.port===port));
        const request=missingAux?0:['relay','converter'].includes(p.role)&&p.mode!=='idle'?Math.min(p.capacity,downstream/p.efficiency):demands.get(id);
        const connectedInputs=p.inputs.filter(port=>inputEdges.get(id).some(edge=>edge.to.port===port));
        for(const port of p.inputs)next.set(`${id}/${port}`,p.mode==='idle'||!connectedInputs.includes(port)?0:request/Math.max(1,connectedInputs.length));
        for(const port of p.aux)next.set(`${id}/${port}`,p.auxiliaryDemand*this.#health(id));
      }demandConverged=mapsClose(portDemand,next);portDemand=next;if(demandConverged)break;
    }
    if(!demandConverged)throw new Error('Energy demand did not converge. Simplify instantaneous cyclic connections or use an explicit storage boundary.');
    let rates=new Map(edges.map(e=>[e.id,0]));
    let flowConverged=false;
    for(let pass=0;pass<passLimit;pass++){
      const next=new Map(edges.map(e=>[e.id,0]));
      for(const[id,p]of plans){if(!p)continue;
        let available=supplies.get(id)??0;
        if(['relay','converter'].includes(p.role)&&p.mode!=='idle')available=Math.min(p.capacity,sum(inputEdges.get(id).map(e=>rates.get(e.id)))*p.efficiency);
        const auxRequest=p.aux.length*p.auxiliaryDemand,auxInput=sum(auxEdges.get(id).map(e=>rates.get(e.id)));
        if(auxRequest>EPS)available*=clamp(auxInput/auxRequest,0,1);
        const outs=outputEdges.get(id),limits=outs.map(edge=>(portDemand.get(`${edge.to.component}/${edge.to.port}`)??0)/receiverCounts.get(`${edge.to.component}/${edge.to.port}`)),total=sum(limits);
        outs.forEach((edge,index)=>next.set(edge.id,total>EPS?Math.min(available,total)*limits[index]/total:0));
      }flowConverged=mapsClose(rates,next);rates=next;if(flowConverged)break;
    }
    if(!flowConverged)throw new Error('Energy flow did not converge. Simplify instantaneous cyclic connections or use an explicit storage boundary.');
    const input={},output={},auxiliary={},powerFactors={};
    for(const[id,p]of plans){if(!p){input[id]=output[id]=auxiliary[id]=0;powerFactors[id]=1;continue;}
      input[id]=sum(inputEdges.get(id).map(e=>rates.get(e.id)));output[id]=sum(outputEdges.get(id).map(e=>rates.get(e.id)));auxiliary[id]=sum(auxEdges.get(id).map(e=>rates.get(e.id)));
      const opticalOnly=p.inputs.length>0&&p.inputs.every(port=>domain(this.#descriptors.get(id),port)==='optical');
      const request=p.role==='load'?p.demand:p.role==='store'?p.capacity:p.aux.length*p.auxiliaryDemand;
      const provided=p.role==='load'||p.role==='store'&&p.mode==='charge'?input[id]:p.role==='store'&&p.mode==='discharge'?output[id]:auxiliary[id];
      powerFactors[id]=opticalOnly?1:request>EPS?clamp(provided/request,0,1):p.role==='store'?0:1;
      if(['converter','relay'].includes(p.role)&&!opticalOnly){const mainRequest=sum(p.inputs.map(port=>portDemand.get(`${id}/${port}`)??0));powerFactors[id]*=mainRequest>EPS?clamp(input[id]/mainRequest,0,1):0;}
    }
    return{plans,edges,rates,input,output,auxiliary,powerFactors,supplies};
  }
  #solve(dt=1){let energy=this.#energy(dt,null),resource;for(let i=0;i<3;i++){resource=this.#resource(dt,energy);energy=this.#energy(dt,resource);}
    const acceptedGates=this.#equations.hasBindings?Object.fromEntries([...this.#descriptors.keys()].map(id=>[id,{healthFactor:this.#healthFactor(id),availability:this.#health(id),operatingFraction:this.#state.components[id].operating/100,enabled:this.#state.components[id].enabled,conducting:this.#state.components[id].enabled&&this.#mode(id)!=='idle'&&Object.keys(this.#definition.components[id].circuits).every(cid=>resource.nodes.get(key(id,cid)).availability>EPS),powerFactor:energy.powerFactors[id]??1,controlFactor:Math.min(1,...Object.keys(this.#definition.components[id].circuits).map(cid=>resource.nodes.get(key(id,cid)).controlFactor)),...this.#powerContext(id,energy)}])):undefined;
    const acceptedCore=this.#equations.hasBindings?Object.fromEntries([...this.#descriptors.keys()].map(id=>[id,{...this.#state.components[id]}])):undefined;
    return{resource,energy,acceptedGates,acceptedCore};
  }
  #heat(ref){if(ref.circuit==='body')return this.#state.thermalStores[ref.component];return this.#state.circuits[ref.component][ref.circuit].heat;}
  #heatMax(ref){const c=this.#definition.components[ref.component];return ref.circuit==='body'?c.thermalStore.capacity:this.#state.circuits[ref.component][ref.circuit].amount*c.circuits[ref.circuit].parameters.thermalCapacity;}
  #temperature(ref){const maximum=this.#heatMax(ref);return maximum>EPS?100*this.#heat(ref)/maximum:0;}
  #setHeat(ref,value){if(ref.circuit==='body')this.#state.thermalStores[ref.component]=value;else this.#state.circuits[ref.component][ref.circuit].heat=value;}
  #advanceResources(solution,dt){
    const r=solution.resource,delta=new Map([...r.nodes.keys()].map(id=>[id,{amount:0,heat:0,tracers:Object.fromEntries(TRACERS.map(name=>[name,0]))}]));
    for(const e of r.links){const volume=r.rates.get(e.id)*dt;if(volume<=EPS)continue;const donor=r.nodes.get(e.a),a=delta.get(e.a),b=delta.get(e.b),fraction=donor.state.amount>EPS?volume/donor.state.amount:0;
      const retained=1-donor.config.parameters.loss;
      a.amount-=volume;b.amount+=volume*retained;this.#state.ledger.resourceBoundaryOut+=volume*(1-retained);
      const heat=donor.state.heat*fraction;a.heat-=heat;b.heat+=heat*retained;this.#state.ledger.heatBoundaryOut+=heat*(1-retained);for(const tracer of TRACERS){const value=donor.state.tracers[tracer]*fraction;a.tracers[tracer]-=value;b.tracers[tracer]+=value*retained;}
    }
    for(const[id,n]of r.nodes){const d=delta.get(id),s=n.state;
      if(n.config.role==='source'){
        this.#state.ledger.resourceBoundaryIn+=Math.max(0,-d.amount);
        this.#state.ledger.resourceBoundaryOut+=Math.max(0,d.amount);
        this.#state.ledger.heatBoundaryIn+=Math.max(0,-d.heat);
        this.#state.ledger.heatBoundaryOut+=Math.max(0,d.heat);
      }else if(n.config.role==='sink'){
        this.#state.ledger.resourceBoundaryOut+=d.amount;this.#state.ledger.heatBoundaryOut+=d.heat;
      }else{
        s.amount+=d.amount;s.heat+=d.heat;for(const tracer of TRACERS)s.tracers[tracer]+=d.tracers[tracer];
        if(/leak|crack|ruptur/.test(this.#state.components[n.id].faultMode)){
          const leak=Math.min(s.amount,2*dt),fraction=s.amount>EPS?leak/s.amount:0;this.#state.ledger.resourceLeak+=leak;this.#state.ledger.heatBoundaryOut+=s.heat*fraction;s.heat*=1-fraction;for(const tracer of TRACERS)s.tracers[tracer]*=1-fraction;s.amount-=leak;
        }
        if(s.amount< -1e-6||s.amount>n.max+1e-6)throw new Error('Resource allocation exceeded a declared inventory bound.');
        s.amount=clamp(s.amount,0,n.max);
        const maximumHeat=s.amount*n.config.parameters.thermalCapacity;
        if(s.heat>maximumHeat){this.#state.ledger.heatBoundaryOut+=s.heat-maximumHeat;s.heat=maximumHeat;}
        if(s.heat< -1e-6)throw new Error('Thermal advection exceeded the donor heat budget.');
        s.heat=Math.max(0,s.heat);
      }
      const incoming=r.incoming.get(id),pressure=incoming.length?sum(incoming.map(e=>r.nodes.get(e.a).state.pressure))/incoming.length:0;
      const pressureTarget=n.config.role==='source'?n.config.initial.pressure:.75*pressure+.25*n.config.initial.pressure+n.config.parameters.pressureGain*this.#operating(n.id)*(n.driven?1:.1);
      s.pressure=this.#equation(n.id,'pressure',{dtMinutes:dt,...this.#powerContext(n.id,solution.energy),circuit:{id:n.cid,configuration:n.config,state:s},readings:{upstreamPressure:pressure,rawTarget:pressureTarget,previousPressure:s.pressure,resourceIn:r.input.get(id)??0,resourceOut:r.output.get(id)??0},gates:{healthFactor:this.#healthFactor(n.id),availability:n.availability,operatingFraction:this.#state.components[n.id].operating/100,powerFactor:solution.energy.powerFactors[n.id]??1,controlFactor:n.controlFactor,driven:n.driven,enabled:this.#state.components[n.id].enabled}},{target:clamp(s.pressure+(pressureTarget-s.pressure)*(1-Math.exp(-.2*dt)))}).target;
    }
  }
  #advanceEnergy(solution,dt){const e=solution.energy;
    for(const[id,p]of e.plans){if(!p)continue;const input=e.input[id]*dt,output=e.output[id]*dt,aux=e.auxiliary[id]*dt;
      this.#state.ledger.energyBoundaryOut+=aux;
      if(p.role==='boundary'){this.#state.ledger.energyBoundaryIn+=output;this.#state.ledger.energyBoundaryOut+=input;}
      else if(p.role==='load'&&this.#definition.components[id].heatSource?.supply?.kind!=='energy-input')this.#state.ledger.energyBoundaryOut+=input;
      else if(['relay','converter'].includes(p.role))this.#state.ledger.energyLoss+=Math.max(0,input-output);
      else if(p.role==='store'){
        if(p.mode==='charge'){const stored=input*p.efficiency;this.#state.energyStores[id]+=stored;this.#state.ledger.energyLoss+=input-stored;}
        if(p.mode==='discharge'){const spent=output/p.efficiency;this.#state.energyStores[id]-=spent;this.#state.ledger.energyLoss+=spent-output;}
        this.#state.energyStores[id]=clamp(this.#state.energyStores[id],0,p.store.capacity);
      }else if(['source','prime-mover'].includes(p.role)){
        const consumed=output/p.efficiency;
        if(p.supply.kind==='thermal'){const ref={component:id,circuit:p.supply.circuit};this.#setHeat(ref,Math.max(0,this.#heat(ref)-consumed));}
        else this.#state.ledger.energyBoundaryIn+=consumed;
        this.#state.ledger.energyLoss+=consumed-output;
      }
    }
  }
  #advanceHeat(solution,dt,acceptedHeat){
    for(const[id,c]of sorted(this.#definition.components)){
      if(c.heatSource){const source=c.heatSource,own=this.#state.components[id],controlFraction=(source.inverted?100-own[source.control]:own[source.control])/100,fraction=controlFraction*this.#health(id),ref={component:id,circuit:source.target};
        const environmentFactor=source.environment?this.#definition.environment[source.environment]/100:1;
        let input=this.#equation(id,'thermal-source',{dtMinutes:dt,thermal:{target:source.target,heat:this.#heat(ref),maximum:this.#heatMax(ref)},gates:{healthFactor:this.#healthFactor(id),availability:this.#health(id),controlFraction,environmentFactor,enabled:own.enabled},accepted:this.#accepted(id,solution)},{heat:source.capacity*fraction*dt*environmentFactor}).heat;
        input=Math.min(input,source.capacity*dt);if(this.#health(id)<=EPS)input=0;
        const fuel=source.supply?.kind==='resource'?source.supply.circuit:c.energy?.supply?.kind==='resource'?c.energy.supply.circuit:null;
        if(fuel)input=Math.min(input,Math.max(0,(solution.resource.input.get(key(id,fuel))??0)*dt-(solution.energy.output[id]??0)*dt/(solution.energy.plans.get(id)?.efficiency??1)));
        const accepted=source.supply?.kind==='energy-input'?(solution.energy.input[id]??0)*dt:null;if(accepted!==null)input=Math.min(input,accepted);
        input=Math.min(input,Math.max(0,this.#heatMax(ref)-this.#heat(ref)));this.#setHeat(ref,this.#heat(ref)+input);if(accepted===null)this.#state.ledger.heatBoundaryIn+=input;else this.#state.ledger.energyLoss+=accepted-input;
        if(acceptedHeat)(acceptedHeat[id]??={}).heatSource=input;
      }
      for(const link of c.thermalLinks??[]){
        const difference=this.#temperature(link.from)-this.#temperature(link.to),from=difference>=0?link.from:link.to,to=difference>=0?link.to:link.from;
        const values=this.#equation(id,'thermal-transfer',{dtMinutes:dt,thermal:{link,from,to,temperatureDifference:difference,donorHeat:this.#heat(from),receiverHeat:this.#heat(to),receiverMaximum:this.#heatMax(to)}},{heat:Math.min(link.maximumTransfer,Math.abs(difference)*link.conductance)*dt,lossFraction:link.lossFraction});
        const requested=Math.min(values.heat,link.maximumTransfer*dt),lossFraction=values.lossFraction;
        const transfer=Math.min(requested,this.#heat(from),Math.max(0,this.#heatMax(to)-this.#heat(to))/Math.max(EPS,1-lossFraction));
        this.#setHeat(from,this.#heat(from)-transfer);this.#setHeat(to,this.#heat(to)+transfer*(1-lossFraction));this.#state.ledger.heatBoundaryOut+=transfer*lossFraction;
      }
      if(c.thermalStore){const heat=this.#state.thermalStores[id],loss=Math.min(heat,this.#equation(id,'thermal-loss',{dtMinutes:dt,thermal:{heat,maximum:c.thermalStore.capacity},accepted:this.#accepted(id,solution)},{heat:heat*(1-Math.exp(-c.thermalStore.loss*dt))}).heat);this.#state.thermalStores[id]-=loss;this.#state.ledger.heatBoundaryOut+=loss;if(acceptedHeat)(acceptedHeat[id]??={}).thermalLoss=loss;}
    }
  }
  #advanceBiology(solution,dt){
    for(const[id,c]of sorted(this.#definition.components)){
      const type=this.#descriptors.get(id).type,s=this.#state.components[id],waterEntry=Object.entries(c.circuits).find(([,v])=>['liquid','thermal-fluid'].includes(v.medium)),air=sum(Object.entries(c.circuits).filter(([,v])=>['air','gas'].includes(v.medium)).map(([cid])=>solution.resource.input.get(key(id,cid))??0));
      if(waterEntry){const[cid,config]=waterEntry,w=this.#state.circuits[id][cid],flow=solution.resource.input.get(key(id,cid))??0,oxygen=w.amount>EPS?w.tracers.oxygen/w.amount:0;
        if(['fish-tank','biofilter','dwc-raft-bed'].includes(type)){const oxygenation=Math.min(w.amount-w.tracers.oxygen,air*c.parameters.oxygenTransfer*dt),demand=Math.min(w.tracers.oxygen,c.parameters.uptake*w.amount*dt);w.tracers.oxygen+=oxygenation-demand;}
        if(['biofilter','media-grow-bed'].includes(type)){const converted=Math.min(w.tracers.solids,c.parameters.tracerConversion*oxygen*w.tracers.solids*dt,Math.max(0,w.amount-w.tracers.nutrient));w.tracers.solids-=converted;w.tracers.nutrient+=converted;}
        if(/bed|channel|table|zone|chamber/.test(type)){const moistureTarget=flow>EPS?Math.min(100,flow*2):0;s.moisture=clamp(s.moisture+(moistureTarget-s.moisture)*(1-Math.exp(-.1*dt)));const uptake=Math.min(w.tracers.nutrient,c.parameters.uptake*s.moisture/100*w.tracers.nutrient*dt);w.tracers.nutrient-=uptake;}
      }
      if(c.zone){const zone=this.#state.zones[c.zone],power=solution.energy.powerFactors[id],load=this.#operating(id)*power;
        if(type==='grow-light'){zone.light=clamp(zone.light+c.parameters.lightGain*(solution.energy.output[id]??0)*dt);zone.temperature=clamp(zone.temperature+load*.1*dt);}
        if(type==='shade-screen')zone.light*=Math.max(0,1-(1-s.operating/100)*.1*dt);
        if(type==='greenhouse-vent'){const exchange=c.parameters.ventExchange*s.operating/100*dt;zone.temperature=clamp(zone.temperature+(this.#definition.environment.ambient-zone.temperature)*exchange);zone.humidity=clamp(zone.humidity+(40-zone.humidity)*exchange);}
        if(type==='evaporative-pad'){const water=waterEntry?this.#state.circuits[id][waterEntry[0]]:null,evaporated=Math.min(water?.amount??0,c.parameters.humidityGain*air*dt);if(water&&evaporated>0){const fraction=evaporated/water.amount;this.#state.ledger.resourceBoundaryOut+=evaporated;this.#state.ledger.heatBoundaryOut+=water.heat*fraction;water.amount-=evaporated;water.heat*=1-fraction;for(const t of TRACERS)water.tracers[t]*=1-fraction;zone.humidity=clamp(zone.humidity+evaporated);zone.temperature=clamp(zone.temperature-evaporated*.2);}}
        if(type==='dehumidifier'){const condensed=Math.min(zone.humidity,c.parameters.condensation*load*dt);zone.humidity-=condensed;if(waterEntry){const target=this.#state.circuits[id][waterEntry[0]],maximum=100*waterEntry[1].parameters.stockScale,added=Math.min(condensed,maximum-target.amount);target.amount+=added;this.#state.ledger.resourceBoundaryIn+=added;}}
      }
      if(MODELS_WITH_CYCLES.has(type)&&s.enabled&&!/timer-stall/.test(s.faultMode)){
        s.phaseElapsed+=dt;const phases=['filling','holding','draining'],durations={filling:c.parameters.cycleFill,holding:c.parameters.cycleHold,draining:c.parameters.cycleDrain};let guard=0;
        while(s.phaseElapsed>=durations[s.phase]&&guard++<1000){s.phaseElapsed-=durations[s.phase];s.phase=phases[(phases.indexOf(s.phase)+1)%3];}
      }
    }
    for(const[id,z]of sorted(this.#definition.zones)){const current=this.#state.zones[id],alpha=1-Math.exp(-z.parameters.response*dt);for(const field of ['temperature','humidity','light'])current[field]=clamp(current[field]+(z.initial[field]-current[field])*alpha);}
  }
  #random(){let v=this.#state.randomState>>>0;v^=v<<13;v^=v>>>17;v^=v<<5;this.#state.randomState=v>>>0;return this.#state.randomState/4294967296;}
  step(minutes=1){return this.#advance(minutes);}
  #advance(minutes,pause=false){
    bounded(minutes,Number.MIN_VALUE,60,'Step minutes');
    if(this.#state.minutes+minutes>1e9||this.#state.nextEventId+Math.ceil(minutes)*this.#descriptors.size>=1e9)throw new RangeError('Time or event limit reached.');
    const previous=clone(this.#state),snapshot=this.#snapshot,equations=this.#equations.checkpoint();
    try{
      if(pause)this.#state.running=false;
      let remaining=minutes;
      while(remaining>EPS){
        const dt=Math.min(1,remaining);
        for(const[id,c]of sorted(this.#definition.components)){
          const s=this.#state.components[id];
          s.operating=this.#equation(id,'operating',{dtMinutes:dt},{operating:s.operating+(s.load-s.operating)*(1-Math.exp(-c.parameters.response*dt))}).operating;
        }
        const solution=this.#solve(dt);
        this.#advanceEnergy(solution,dt);
        this.#advanceResources(solution,dt);
        const acceptedHeat=this.#equations.hasBindings?{}:null;
        this.#advanceHeat(solution,dt,acceptedHeat);
        this.#advanceBiology(solution,dt);
        for(const[id,c]of sorted(this.#definition.components)){
          // A retained command is not an operating load when disabled, failed,
          // isolated or without supply. Stored circuit pressure remains a
          // separate stress source even after the drive stops.
          const s=this.#state.components[id],operatingStress=this.#mode(id)==='idle'?0:s.operating*this.#health(id)*(solution.energy.powerFactors[id]??1);
          const stress=Math.max(operatingStress,...Object.values(this.#state.circuits[id]).map(v=>v.pressure));
          let damage=s.damage,randomSample=null;
          if(stress>c.parameters.warningAt){randomSample=this.#random();damage=clamp(s.damage+c.parameters.damageRate*(stress-c.parameters.warningAt)/100*dt*(.9+.2*randomSample));}
          s.damage=this.#equations.hasPhase(id,'condition')?this.#equation(id,'condition',{dtMinutes:dt,previous:{...s},readings:{stress,operatingStress},randomSample,accepted:this.#accepted(id,solution),gates:{healthFactor:this.#healthFactor(id),availability:this.#health(id),operatingFraction:s.operating/100,powerFactor:solution.energy.powerFactors[id]??1,mode:this.#mode(id),enabled:s.enabled}},{damage}).damage:damage;
          if(s.damage>=100&&s.faultMode==='none'){
            s.faultMode=this.#descriptors.get(id).visualFields.damage?.options?.find(v=>v!=='none')??'failed';
            this.#record(`${this.#descriptors.get(id).label}: equipment failed.`,'fault',id,'critical');
          }
        }
        if(this.#equations.hasBindings)for(const[id]of sorted(this.#definition.components))if(this.#equations.has(id))this.#equations.advance(id,this.#context(id,{dtMinutes:dt,...this.#powerContext(id,solution.energy),accepted:this.#accepted(id,solution,acceptedHeat[id]),gates:{health:this.#health(id),healthFactor:this.#healthFactor(id),availability:this.#health(id),powerFactor:solution.energy.powerFactors[id]??1,operatingFraction:this.#state.components[id].operating/100,controlFactor:Math.min(1,...Object.keys(this.#definition.components[id].circuits).map(cid=>solution.resource.nodes.get(key(id,cid)).controlFactor)),enabled:this.#state.components[id].enabled}}));
        this.#state.minutes+=dt;
        remaining-=dt;
      }
      this.#refresh();
      this.#emit({type:'tick'});
      return this.#snapshot;
    }catch(error){this.#state=previous;this.#snapshot=snapshot;this.#equations.restore(equations);throw error;}
  }
  #observations(readings,circuitReadings){
    // Degraded observations (for example drift/fouling) stay available with
    // warning quality. The health/supply gates still reject broken devices,
    // disconnected telemetry, communication loss and power loss.
    const connected={};for(const[id]of this.#descriptors)connected[id]=this.#health(id)>0&&(readings[id].powerFactor>EPS||!this.#definition.components[id].energy);
    for(let pass=0;pass<this.#descriptors.size;pass++)for(const edge of this.#edges().filter(e=>e.channel==='data'&&e.direction))if(!this.#observationSource(edge.from.component)&&!connected[edge.from.component])connected[edge.to.component]=false;
    for(const[id,c]of sorted(this.#definition.components)){
      const observation=c.observation;if(!observation)continue;const s=this.#state.components[id];let source=observation.zone?this.#state.zones[observation.zone]:observation.circuit?circuitReadings[observation.component]?.[observation.circuit]:readings[observation.component];
      const value=source?.[observation.quantity];s.valid=connected[id]&&typeof value==='number';if(s.valid)s.signal=clamp(value);readings[id].signal=s.signal;readings[id].valid=s.valid;
    }return connected;
  }
  #refresh(){
    const {resource:r,energy:e}=this.#solve(),circuits={},readings={},components={},controls={},parameters={},portReadings={};
    for(const[id,c]of sorted(this.#definition.components)){
      circuits[id]={};portReadings[id]={};for(const[cid,config]of sorted(c.circuits)){const s=this.#state.circuits[id][cid],k=key(id,cid);circuits[id][cid]={inventory:s.amount/config.parameters.stockScale,amount:s.amount,temperature:this.#temperature({component:id,circuit:cid}),pressure:s.pressure,input:r.input.get(k),output:r.output.get(k),fluid:config.fluid,...Object.fromEntries(TRACERS.map(name=>[name,s.amount>EPS?100*s.tracers[name]/s.amount:0]))};}
      const primary=c.presentation?.primaryCircuit??Object.keys(circuits[id])[0],p=circuits[id][primary],own=this.#state.components[id];
      readings[id]={flow:p?.output??0,resourceIn:p?.input??0,resourceOut:p?.output??0,stock:p?.inventory??0,pressure:p?.pressure??0,temperature:c.thermalStore?this.#temperature({component:id,circuit:'body'}):p?.temperature??0,powerIn:e.input[id]??0,powerOut:e.output[id]??0,power:e.output[id]||e.input[id]||0,powerFactor:e.powerFactors[id]??1,signal:own.signal,valid:own.valid,damage:own.damage,moisture:own.moisture,phase:own.phase,load:own.operating*this.#health(id)*(e.powerFactors[id]??1)};
      controls[id]={enabled:own.enabled,open:own.open,load:own.load,fault:own.faultMode!=='none',level:p?.inventory??0,mode:own.mode,rodPosition:own.rodPosition,measurement:c.measurement??''};parameters[id]=clone(c.parameters);
    }
    const connected=this.#observations(readings,circuits);
    for(const[id,c]of sorted(this.#definition.components)){
      const d=this.#descriptors.get(id),s=this.#state.components[id],values={},cs=Object.values(circuits[id]),first=circuits[id][c.presentation?.primaryCircuit]??cs[0],record=readings[id],active=this.#health(id)>0&&connected[id]&&record.powerFactor>EPS&&this.#mode(id)!=='idle';
      for(const[field,spec]of Object.entries(d.visualFields)){
        let value=spec.default;
        if(field==='active')value=active;
        else if(field==='running')value=this.#state.running;
        else if(field==='fault')value=s.faultMode!=='none'&&this.#health(id)<=EPS;
        else if(field==='status')value=(!s.enabled||this.#mode(id)==='idle')&&s.faultMode==='none'?'normal':!connected[id]||record.powerFactor<=EPS?'offline':s.faultMode!=='none'||s.damage>=20?'warning':'normal';
        else if(field==='connected')value=connected[id]&&s.valid;
        else if(field==='damage')value=s.faultMode;
        else if(field==='mode')value=s.mode;
        else if(field==='direction')value=this.#mode(id);
        else if(field==='source'&&d.type==='automatic-transfer-switch')value=this.#mode(id)==='idle'?'off':s.mode==='source-b'?'b':'a';
        else if(field==='phase')value=s.phase;
        else if(field==='measurement')value=c.measurement??spec.default;
        else if(field==='open')value=s.open;
        // Position commands are instantaneous in this placeholder. Operating
        // load lag is not evidence of actuator travel.
        else if(field==='moving')value=false;
        // V2 has no protection decision/contact command model. An equipment
        // fault must not fabricate a successful protective trip.
        else if(field==='tripped')value=false;
        else if(field==='level')value=c.energy?.store?100*this.#state.energyStores[id]/c.energy.store.capacity:first?.inventory??0;
        else if(field==='heat'||field==='temperature')value=record.temperature;
        else if(field==='pressure')value=record.pressure;
        else if(field==='rodPosition')value=s.rodPosition;
        else if(field==='flow'||field==='primaryFlow')value=first?.output??0;
        else if(field==='secondaryFlow')value=cs[1]?.output??0;
        else if(field==='load'||field==='speed')value=active?record.load:0;
        else if(field==='opening')value=s.open?s.operating:0;
        else if(field==='integrity')value=100-s.damage;
        else if(field==='value')value=s.signal;
        else if(field==='oxygen')value=first?.oxygen??0;
        else if(field==='moisture')value=s.moisture;
        else if(['humidity','light'].includes(field))value=c.observation?s.signal:c.zone?this.#state.zones[c.zone][field]:field==='light'?e.output[id]??0:0;
        else if(field==='airflow')value=sum(cs.filter(v=>v.fluid==='air').map(v=>v.output));
        else if(field==='field')value=e.auxiliary[id]??0;
        else if(field==='irradiance')value=this.#definition.environment.light??0;
        else if(field==='wave')value=this.#definition.environment.wave??0;
        else if(field==='current')value=this.#definition.environment.waterCurrent??0;
        if(spec.type==='number')value=clamp(Number(value)||0,spec.min??0,spec.max??100);
        if(spec.type==='select'&&spec.options&&!spec.options.includes(value))value=spec.default;
        values[field]=value;
      }components[id]=values;
    }
    const rates=new Map([...r.deliveredRates,...e.rates]),channels={},directions={};
    for(const edge of this.#edges()){
      channels[edge.id]=edge.channel==='energy'?'power':edge.channel;directions[edge.id]=edge.direction;
      if(edge.channel==='data')rates.set(edge.id,edge.direction&&connected[edge.from.component]&&connected[edge.to.component]?1:0);
      if(edge.channel==='measurement')rates.set(edge.id,edge.direction&&connected[edge.to.component]?1:0);
      if(edge.channel==='thermal')rates.set(edge.id,0);
      if(!rates.has(edge.id))rates.set(edge.id,0);
      const amount=rates.get(edge.id)??0;
      for(const[endpoint,direction]of [[edge.from,'outgoing'],[edge.to,'incoming']]){
        const reading=portReadings[endpoint.component][endpoint.port]??={incoming:0,outgoing:0,net:0,rate:0,direction:'idle',domain:edge.channel==='energy'?edge.domain:edge.channel};
        reading[direction]+=amount;reading.net=reading.outgoing-reading.incoming;reading.rate=Math.abs(reading.net);reading.direction=reading.net>EPS?'out':reading.net< -EPS?'in':reading.incoming+reading.outgoing>EPS?'both':'idle';
      }
    }
    this.#snapshot=freeze({format:'scada-placeholder-state',version:2,scenarioId:this.#definition.scenarioId,minutes:this.#state.minutes,running:this.#state.running,components,controls,readings,parameters,circuits,portReadings,environment:clone(this.#definition.environment),zones:clone(this.#state.zones),energyStores:clone(this.#state.energyStores),flows:Object.fromEntries([...rates].map(([id,rate])=>[id,rate>EPS])),flowRates:Object.fromEntries([...rates].map(([id,rate])=>[id,rate*(directions[id]??1)])),directions,channels,ledger:clone(this.#state.ledger),events:clone(this.#state.events),assumptions:clone(this.#definition.assumptions)});
  }
  dispatch(command){
    const input=safeClone(command);
    const isObject=value=>value!==null&&typeof value==='object'&&!Array.isArray(value);
    if(!isObject(input)||Object.keys(input).some(key=>!['action','id','label','component','arguments'].includes(key)))throw new TypeError('Expected a command object with known fields.');
    for(const key of ['action','id','label','component'])if(input[key]!==undefined&&(typeof input[key]!=='string'||!input[key].length||input[key].length>1000))throw new TypeError(`Command ${key} must be bounded nonempty text.`);
    if(input.arguments!==undefined&&!isObject(input.arguments))throw new TypeError('Command arguments must be an object.');
    const args=input.arguments??{},action=input.action,id=args.equipment??input.component;
    if(args.equipment!==undefined&&(typeof args.equipment!=='string'||!args.equipment.length))throw new TypeError('Equipment must be a nonempty identity.');
    const c=id?this.#definition.components[id]:null,s=id?this.#state.components[id]:null;
    const allowed={setEnabled:['equipment','value'],setOpen:['equipment','value'],setLoad:['equipment','value'],setLevel:['equipment','circuit','value'],setRodPosition:['equipment','value'],setMode:['equipment','value'],setMeasurement:['equipment','value'],setFault:['equipment','value'],setDamage:['equipment','value'],setParameter:['equipment','key','value'],setCircuitParameter:['equipment','circuit','key','value'],setEnergyParameter:['equipment','key','value'],setTracer:['equipment','circuit','key','value'],setZoneValue:['zone','key','value'],setEnvironment:['key','value'],repair:['equipment'],setRunning:['value'],step:['minutes','value'],reset:[],import:['payload','value']}[action];
    if(!allowed||Object.keys(args).some(k=>!allowed.includes(k)))throw new TypeError('Unknown command or argument.');
    if(['step','reset','import'].includes(action)){if(action==='step')return this.#advance(args.minutes??args.value??1,true);if(action==='reset')return this.reset();return this.importSnapshot(args.payload??args.value);}
    if(!['setRunning','setEnvironment','setZoneValue','repair'].includes(action)&&!c)throw new RangeError('Unknown equipment.');
    if(action==='repair'&&id&&id!=='all'&&!c)throw new RangeError('Unknown equipment.');
    const previous=clone(this.#state),definition=this.#definition,snapshot=this.#snapshot,equations=this.#equations;
    try{
      if(action==='setEnabled')s.enabled=bool(args.value,'Enabled');
      if(action==='setOpen')s.open=bool(args.value,'Open');
      if(action==='setLoad')s.load=bounded(args.value,0,100,'Load');
      if(action==='setRodPosition')s.rodPosition=bounded(args.value,0,100,'Rod position');
      if(action==='setMode'){const modes=c.energy?.modes??{};if(!Object.hasOwn(modes,args.value))throw new RangeError('Unknown operating mode.');s.mode=args.value;}
      if(action==='setDamage'){s.damage=bounded(args.value,0,100,'Damage');if(s.damage>=100)s.faultMode=this.#descriptors.get(id).visualFields.damage?.options?.find(v=>v!=='none')??'failed';}
      if(action==='setFault'){const options=this.#descriptors.get(id).visualFields.damage?.options??['none','failed'],value=args.value===true?options.find(v=>v!=='none'):args.value===false?'none':args.value;if(!options.includes(value))throw new RangeError('Unknown fault.');s.faultMode=value;s.damage=value==='none'?0:60;}
      if(action==='repair')for(const[other,own]of Object.entries(this.#state.components))if(!id||id==='all'||other===id){own.damage=0;own.faultMode='none';}
      if(action==='setLevel'){const cid=args.circuit??Object.keys(c.circuits)[0],config=c.circuits[cid],own=this.#state.circuits[id][cid];if(!config)throw new RangeError('Unknown circuit.');const amount=bounded(args.value,0,100,'Level')*config.parameters.stockScale,factor=own.amount>EPS?amount/own.amount:0,heatChange=own.heat*(factor-1);this.#state.ledger.resourceBoundaryIn+=Math.max(0,amount-own.amount);this.#state.ledger.resourceBoundaryOut+=Math.max(0,own.amount-amount);this.#state.ledger.heatBoundaryIn+=Math.max(0,heatChange);this.#state.ledger.heatBoundaryOut+=Math.max(0,-heatChange);own.amount=amount;own.heat*=factor;for(const tracer of TRACERS)own.tracers[tracer]*=factor;}
      if(action==='setTracer'){const target=this.#state.circuits[id][args.circuit];if(!target||!TRACERS.includes(args.key))throw new RangeError('Unknown circuit or tracer.');if(target.amount<=EPS)throw new RangeError('An empty circuit has no composition; add resource before editing tracers.');target.tracers[args.key]=target.amount*bounded(args.value,0,100,'Tracer index')/100;}
      if(action==='setZoneValue'){const zone=this.#state.zones[args.zone];if(!zone||!ZONE_FIELDS.includes(args.key))throw new RangeError('Unknown zone or quantity.');zone[args.key]=bounded(args.value,0,100,'Zone index');}
      if(['setParameter','setEnvironment','setCircuitParameter','setEnergyParameter','setMeasurement'].includes(action)){
        const next=clone(this.#definition);
        if(action==='setParameter')next.components[id].parameters[args.key]=args.value;
        if(action==='setCircuitParameter'){if(!next.components[id].circuits[args.circuit])throw new RangeError('Unknown circuit.');next.components[id].circuits[args.circuit].parameters[args.key]=args.value;}
        if(action==='setEnergyParameter'){if(!next.components[id].energy||!['capacity','demand','efficiency'].includes(args.key))throw new RangeError('Unknown energy parameter.');next.components[id].energy[args.key]=args.value;}
        if(action==='setEnvironment'){if(!Object.hasOwn(next.environment,args.key))throw new RangeError('Unknown environment key.');next.environment[args.key]=args.value;}
        if(action==='setMeasurement'){const choices=this.#descriptors.get(id).visualFields.measurement?.options;if(!choices?.includes(args.value))throw new RangeError('Unknown measurement identity.');next.components[id].measurement=args.value;if(next.components[id].observation)next.components[id].observation.quantity=args.value==='do'?'oxygen':args.value;}
        const result=validateV2Definition(this.#system,next);if(!result.ok)throw new TypeError(result.errors.map(e=>e.message).join('; '));this.#assertState(this.#state,result.definition);
        const runtime=this.#equations.withDefinition(result.definition,{initialize:false});runtime.importState(this.#equations.exportState());this.#definition=result.definition;this.#equations=runtime;
      }
      if(action==='setRunning')this.#state.running=bool(args.value,'Running');
      this.#record(`${id?this.#descriptors.get(id)?.label??id:'System'}: ${action.replace(/^set/,'').replace(/([A-Z])/g,' $1').trim().toLowerCase()}${args.value===undefined?'':` → ${args.value}`}.`);this.#refresh();this.#emit({type:'command',action});return this.#snapshot;
    }catch(error){this.#state=previous;this.#definition=definition;this.#snapshot=snapshot;this.#equations=equations;throw error;}
  }
  setEquationBindings(equations){
    const next=clone(this.#definition);
    if(equations===null||equations===undefined)delete next.equations;else next.equations=safeClone(equations);
    const validation=validateV2Definition(this.#system,next);if(!validation.ok)throw new TypeError(validation.errors.map(e=>e.message).join('; '));
    const runtime=this.#equations.withDefinition(validation.definition,{initialize:false});
    runtime.reset(id=>this.#context(id));
    const previous=clone(this.#state),definition=this.#definition,snapshot=this.#snapshot,oldRuntime=this.#equations;
    try{this.#definition=validation.definition;this.#equations=runtime;this.#refresh();}
    catch(error){this.#state=previous;this.#definition=definition;this.#snapshot=snapshot;this.#equations=oldRuntime;throw error;}
    this.#emit({type:'equations'});return this.#snapshot;
  }
  reset(){
    const previous=this.#state,snapshot=this.#snapshot,equations=this.#equations;
    try{this.#resetState(previous.running);this.#equations=equations.fork();this.#equations.reset(id=>this.#context(id));this.#refresh();}
    catch(error){this.#state=previous;this.#snapshot=snapshot;this.#equations=equations;throw error;}
    this.#emit({type:'reset'});return this.#snapshot;
  }
  exportModelDefinition(){return clone(this.#definition);}
  exportSnapshot(){const equationState=this.#equations.exportState();return{format:'scada-placeholder-snapshot',version:2,system:{id:this.#system.system.id,signature:this.#signature},model:clone(this.#definition),state:clone(this.#state),...(equationState===undefined?{}:{equationState})};}
  #assertState(state,definition){
    const template=this.#state;
    const shape=(value,expected,path)=>{
      if(typeof expected==='number'){bounded(value,0,Number.MAX_SAFE_INTEGER,path);return;}
      if(typeof expected==='boolean'){bool(value,path);return;}
      if(typeof expected==='string'){if(typeof value!=='string'||value.length>1000)throw new TypeError(`Invalid ${path}.`);return;}
      if(Array.isArray(expected)){if(!Array.isArray(value)||value.length>100)throw new TypeError(`Invalid ${path}.`);return;}
      if(!value||typeof value!=='object'||Array.isArray(value)||Object.keys(value).sort().join('|')!==Object.keys(expected).sort().join('|'))throw new TypeError(`Invalid ${path}.`);
      for(const name of Object.keys(expected))shape(value[name],expected[name],`${path}/${name}`);
    };
    shape(state,template,'state');bounded(state.minutes,0,1e9,'Minutes');bounded(state.randomState,1,4294967295,'Random state');bounded(state.nextEventId,1,1e9,'Event sequence');
    if(!Number.isInteger(state.randomState)||!Number.isInteger(state.nextEventId))throw new TypeError('Random state and event sequence must be integers.');
    for(const[id,c]of Object.entries(definition.components)){
      const s=state.components[id],d=this.#descriptors.get(id);
      for(const field of ['load','operating','rodPosition','damage','signal','moisture'])bounded(s[field],0,100,field);
      const failureModes=d.visualFields.damage?.options??['none'];if(!failureModes.includes(s.faultMode))throw new TypeError('Invalid fault mode.');
      const modes=c.energy?.modes?Object.keys(c.energy.modes):[c.initial.mode];if(!modes.includes(s.mode))throw new TypeError('Invalid operating mode.');
      if(s.damage>=100&&s.faultMode==='none')throw new TypeError('Complete damage needs a latched fault.');
      if(MODELS_WITH_CYCLES.has(d.type)){const durations={filling:c.parameters.cycleFill,holding:c.parameters.cycleHold,draining:c.parameters.cycleDrain};if(!Object.hasOwn(durations,s.phase)||s.phaseElapsed>=durations[s.phase])throw new TypeError('Invalid irrigation phase or elapsed duration.');}
      else if(s.phase!=='idle'||s.phaseElapsed!==0)throw new TypeError('This model has no irrigation phase.');
      for(const[cid,config]of Object.entries(c.circuits)){
        const own=state.circuits[id][cid];bounded(own.amount,0,100*config.parameters.stockScale,'Circuit stock');bounded(own.pressure,0,100,'Circuit pressure');bounded(own.heat,0,own.amount*config.parameters.thermalCapacity+1e-7,'Circuit heat');for(const amount of Object.values(own.tracers))bounded(amount,0,own.amount+1e-7,'Tracer stock');
      }
      if(c.thermalStore)bounded(state.thermalStores[id],0,c.thermalStore.capacity,'Thermal storage');
      if(c.energy?.store)bounded(state.energyStores[id],0,c.energy.store.capacity,'Energy storage');
    }
    for(const zone of Object.values(state.zones))for(const value of Object.values(zone))bounded(value,0,100,'Zone index');
    let last=0,lastMinutes=0;
    for(const event of state.events){
      if(!event||typeof event!=='object'||Object.keys(event).sort().join('|')!==['id','minutes','type','equipment','severity','message'].sort().join('|'))throw new TypeError('Invalid event record.');
      if(!Number.isInteger(event.id)||event.id<=last||event.id>=state.nextEventId)throw new TypeError('Invalid event sequence.');bounded(event.minutes,lastMinutes,state.minutes,'Event time');lastMinutes=event.minutes;
      if(typeof event.message!=='string'||event.message.length>1000||!['info','warning','critical'].includes(event.severity)||typeof event.type!=='string'||event.type.length>80||!(event.equipment==='system'||definition.components[event.equipment]))throw new TypeError('Invalid event history.');last=event.id;
    }
  }
  importSnapshot(payload){
    const input=safeClone(payload);if(!input||Object.keys(input).filter(key=>key!=='equationState').sort().join('|')!==['format','version','system','model','state'].sort().join('|')||input.format!=='scada-placeholder-snapshot'||input.version!==2||input.system?.signature!==this.#signature||input.system.id!==this.#system.system.id||Object.keys(input.system).sort().join('|')!=='id|signature')throw new TypeError('Snapshot version or topology mismatch.');
    const validation=validateV2Definition(this.#system,input.model);if(!validation.ok)throw new TypeError('Invalid snapshot model.');
    if(topologySignature(this.#system,validation.definition)!==this.#signature)throw new TypeError('Snapshot model topology differs.');this.#assertState(input.state,validation.definition);
    const runtime=this.#equations.withDefinition(validation.definition,{initialize:false});runtime.importState(input.equationState);
    const old=this.#state,definition=this.#definition,snapshot=this.#snapshot,equations=this.#equations;
    try{this.#state=input.state;this.#definition=validation.definition;this.#equations=runtime;this.#refresh();}
    catch(error){this.#state=old;this.#definition=definition;this.#snapshot=snapshot;this.#equations=equations;throw error;}
    this.#emit({type:'import'});return this.#snapshot;
  }
  start({intervalMs=1000,minutesPerTick=1}={}){bounded(intervalMs,50,60000,'Interval');bounded(minutesPerTick,Number.MIN_VALUE,60,'Tick minutes');if(this.#timer!==null)return;this.#timer=this.#clock.setInterval(()=>{if(!this.#state.running)return;try{this.step(minutesPerTick);}catch(error){
      this.#state.running=false;this.stop();const message=formatEquationError(error,1000);
      if(this.#state.nextEventId<1e9)this.#record(message,'error','system','critical');
      else{const terminal={id:this.#state.nextEventId-1,minutes:this.#state.minutes,type:'error',equipment:'system',severity:'critical',message};if(this.#state.events.at(-1)?.id===terminal.id)this.#state.events.pop();this.#state.events.push(terminal);if(this.#state.events.length>100)this.#state.events.shift();}
      // A persistently failing pure provider must not escape the clock callback
      // merely because producing a refreshed reading invokes it again.
      try{this.#refresh();}catch{this.#snapshot=freeze({...this.#snapshot,running:false,components:Object.fromEntries(Object.entries(this.#snapshot.components).map(([id,value])=>[id,{...value,...(Object.hasOwn(value,'running')?{running:false}:{})}])),events:clone(this.#state.events)});}
      this.#emit({type:'error',message});
    }},intervalMs);this.#timer?.unref?.();}
  stop(){if(this.#timer!==null){this.#clock.clearInterval(this.#timer);this.#timer=null;}}
  destroy(){this.stop();this.#listeners.clear();}
}

export function createV2Adapter(model,{readOnly=false}={}){return Object.freeze({readOnly,getSnapshot:()=>model.getSnapshot(),subscribe:listener=>model.subscribe(listener),dispatch:command=>{if(readOnly)throw new Error('This adapter is read-only.');return model.dispatch(command);}});}
