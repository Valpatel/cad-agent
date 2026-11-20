import test from 'node:test';
import assert from 'node:assert/strict';
import {createModelDefinition,PlaceholderSystemModel} from '../../../../software/cadagent/webkit/scada/sim/src/index.mjs';

const objectSchema=properties=>({type:'object',additionalProperties:false,properties,required:Object.keys(properties)});
const number={type:'number',minimum:0,maximum:1e9};
const bindings=(id='test.flow',parameters={})=>({version:1,components:{pump:{id,version:'1.0.0',parameters}}});
const command=(model,action,value,key)=>model.dispatch({action,component:'pump',arguments:{...(value===undefined?{}:{value}),...(key?{key}:{})}});

function fixture(){
  const system={format:'scada-system',version:1,system:{id:'equation-v1',label:'Equation fixture'},
    components:[['supply','tank'],['pump','pump'],['receiver','tank'],['generator','generator']].map(([id,type])=>({id,type,label:id})),
    connections:[
      {id:'feed',from:{component:'supply',port:'outlet'},to:{component:'pump',port:'inlet'},medium:'liquid'},
      {id:'delivery',from:{component:'pump',port:'outlet'},to:{component:'receiver',port:'inlet'},medium:'liquid'},
      {id:'drive',from:{component:'generator',port:'output'},to:{component:'pump',port:'drive'},medium:'electricity'},
    ]};
  const definition=createModelDefinition(system,{seed:712});
  for(const config of Object.values(definition.components)){
    config.parameters.loss=0;config.parameters.damageRate=0;config.parameters.capacity=100;
    config.initial.load=100;
  }
  definition.components.receiver.initial.level=definition.components.receiver.initial.inventory=0;
  return {system,definition};
}
function provider(overrides={}){
  return {id:'test.flow',version:'1.0.0',stateVersion:1,engines:[1],phases:['resource'],units:'scada-index-v1',
    parameterSchema:objectSchema({rate:number}),defaultParameters:{rate:7},
    stateSchema:objectSchema({}),initialize:()=>({}),evaluate:(_phase,ctx)=>({capacity:ctx.parameters.rate}),...overrides};
}
function session(providers=[provider()],equations=bindings(),options={}){
  const {system,definition}=fixture();if(equations)definition.equations=equations;
  return new PlaceholderSystemModel(system,definition,{equationProviders:providers,...options});
}
function unchanged(model,operation,pattern){
  const saved=model.exportSnapshot(),visible=model.getSnapshot();
  assert.throws(operation,pattern);
  assert.deepEqual(model.exportSnapshot(),saved,'all persisted model/core/provider state rolls back');
  assert.equal(model.getSnapshot(),visible,'the accepted visible snapshot is retained');
}

test('v1 replacement equations change allocated flow and energy, not only readouts',()=>{
  const flow=provider({phases:['resource','energy'],evaluate:(phase,ctx)=>phase==='resource'?{capacity:ctx.parameters.rate}:{demand:5}});
  const model=session([flow]);
  assert.equal(model.getSnapshot().flowRates.delivery,7);
  assert.equal(model.getSnapshot().flowRates.drive,5);
  assert.equal(model.getSnapshot().readings.pump.powerRequested,5);
  const before=model.exportSnapshot();model.step(1);const after=model.exportSnapshot();
  assert.ok(Math.abs(after.state.components.receiver.inventory-before.state.components.receiver.inventory-.7)<1e-10);
  model.setEquationBindings(bindings('test.flow',{rate:12}));
  assert.equal(model.getSnapshot().flowRates.delivery,12);
  assert.equal(model.exportSnapshot().state.components.receiver.inventory,after.state.components.receiver.inventory,'selection preserves inventory');
  command(model,'setEnabled',false);
  assert.equal(model.getSnapshot().flowRates.delivery,0);
  assert.equal(model.getSnapshot().flowRates.drive,0);
  model.destroy();
});

test('v1 nonlinear effective rates may exceed the old response while rating and absolute gates remain enforced',()=>{
  const {system,definition}=fixture();definition.equations=bindings();
  definition.components.pump.initial.load=25;
  definition.components.pump.parameters.demand=20;
  definition.components.generator.parameters.capacity=10;
  let sawPartialPower=false,requested=40;
  const nonlinear=provider({phases:['resource','energy'],evaluate:(phase,ctx)=>{
    if(phase==='energy')return {demand:20};
    if(ctx.gates.powerFactor===.5&&ctx.defaults.capacity<40){
      sawPartialPower=true;assert.equal(ctx.availablePower,10);assert.equal(ctx.powerBasis,'allocated');
    }
    return {capacity:requested};
  }});
  const model=new PlaceholderSystemModel(system,definition,{equationProviders:[nonlinear]});
  assert.equal(sawPartialPower,true);assert.equal(model.getSnapshot().flowRates.delivery,40);
  assert.equal(model.getSnapshot().readings.pump.powerIn,10);
  requested=500;command(model,'setLoad',25);
  assert.equal(model.getSnapshot().flowRates.delivery,100,'configured rating caps oversized custom request');
  model.dispatch({action:'setEnabled',component:'generator',arguments:{value:false}});
  assert.equal(model.getSnapshot().flowRates.delivery,0,'an unpowered drive cannot transfer resources');
  model.destroy();

  const valveSystem={...system,components:system.components.map(item=>item.id==='pump'?{...item,type:'gate-valve'}:item),connections:system.connections.filter(edge=>edge.id!=='drive')};
  const valveDefinition=createModelDefinition(valveSystem);valveDefinition.equations=bindings();
  const valve=new PlaceholderSystemModel(valveSystem,valveDefinition,{equationProviders:[provider()]});
  assert.ok(valve.getSnapshot().flowRates.delivery>0);
  command(valve,'setOpen',false);assert.equal(valve.getSnapshot().flowRates.delivery,0);
  valve.destroy();
});

test('v1 a selected zero-demand model cannot invent connected drive power from a ratio of one',()=>{
  for(const phases of [['energy'],['resource','energy']]){
    const implementation=provider({phases,evaluate:phase=>phase==='energy'?{demand:0}:{capacity:7}});
    const model=session([implementation]);
    assert.equal(model.getSnapshot().readings.pump.powerFactor,1,'zero request uses the established ratio convention');
    assert.equal(model.getSnapshot().readings.pump.powerIn,0);
    assert.equal(model.getSnapshot().flowRates.delivery,0,'actual connected zero supply still prevents drive output');
    model.dispatch({action:'setEnabled',component:'generator',arguments:{value:false}});
    assert.equal(model.getSnapshot().flowRates.delivery,0);
    model.destroy();
  }
});

test('v1 operating, pressure, temperature, signal and condition replace numerical transitions',()=>{
  const phases=['operating','pressure','temperature','signal','condition'];
  const model=session([provider({phases,evaluate:(phase,ctx)=>{
    assert.ok(Object.isFrozen(ctx)&&Object.isFrozen(ctx.core)&&Object.isFrozen(ctx.configuration));
    if(phase==='operating')return {operating:25};
    if(phase==='condition'){
      assert.equal(ctx.previous.damage,0);assert.equal(typeof ctx.randomSample,'number');
      return {damage:100};
    }
    return {target:phase==='pressure'?90:phase==='temperature'?80:70};
  }})]);
  const original=model.exportSnapshot().state.components.pump;
  model.step(1);const state=model.exportSnapshot().state.components.pump;
  assert.equal(state.operating,25);
  assert.ok(state.pressure>original.pressure);assert.ok(state.temperature>original.temperature);
  assert.ok(state.signal>0);assert.equal(state.damage,100);assert.equal(state.failed,true);
  assert.notEqual(state.mode,'none');assert.equal(model.getSnapshot().flowRates.delivery,0);
  command(model,'repair',undefined);assert.equal(model.exportSnapshot().state.components.pump.damage,0);
  model.destroy();
});

test('v1 provider state advances once per substep and restores without initialize or replay',()=>{
  let initializeCount=0,evaluateCount=0;
  const stateful=provider({stateSchema:objectSchema({elapsed:number,steps:{type:'integer',minimum:0},volume:number}),
    initialize:()=>{initializeCount++;return {elapsed:0,steps:0,volume:0};},
    evaluate:(_phase,ctx)=>{evaluateCount++;return {capacity:ctx.parameters.rate};},
    advance:ctx=>({elapsed:ctx.providerState.elapsed+ctx.dtMinutes,steps:ctx.providerState.steps+1,
      volume:ctx.providerState.volume+ctx.accepted.resourceOut*ctx.dtMinutes/10})});
  const model=session([stateful]);assert.equal(initializeCount,1);
  const atStart=model.exportSnapshot();model.getSnapshot();command(model,'setLoad',90);
  assert.deepEqual(model.exportSnapshot().equationState,atStart.equationState,'reads and commands never advance local dynamics');
  model.step(2.5);const saved=model.exportSnapshot(),state=saved.equationState.components.pump.state;
  assert.equal(state.steps,3);assert.equal(state.elapsed,2.5);assert.ok(state.volume>0);assert.ok(evaluateCount>state.steps);
  const restored=session([stateful],null);restored.importSnapshot(saved);
  assert.equal(initializeCount,1,'restoring selected equations does not initialize or replay them');
  assert.deepEqual(restored.exportSnapshot(),saved);
  model.step(.75);restored.step(.75);assert.deepEqual(restored.exportSnapshot(),model.exportSnapshot());
  const core=model.exportSnapshot().state;model.setEquationBindings(bindings());
  assert.equal(initializeCount,2);assert.equal(model.exportSnapshot().equationState.components.pump.state.steps,0);
  assert.deepEqual(model.exportSnapshot().state,core,'hot swap retains all kernel state');
  model.reset();assert.equal(initializeCount,3);assert.equal(model.exportSnapshot().state.minutes,0);
  model.setEquationBindings(null);assert.equal(Object.hasOwn(model.exportSnapshot(),'equationState'),false);
  model.destroy();restored.destroy();
});

test('v1 accepted interval gates retain the pre-failure operating point for stateful bookkeeping',()=>{
  const implementation=provider({phases:['resource','condition'],
    stateSchema:objectSchema({flow:number,health:number}),initialize:()=>({flow:0,health:0}),
    evaluate:(phase,ctx)=>phase==='resource'?{capacity:ctx.parameters.rate}:{damage:100},
    advance:ctx=>{
      assert.equal(ctx.core.failed,true);assert.equal(ctx.gates.healthFactor,0);
      assert.equal(ctx.accepted.core.failed,false);assert.equal(ctx.accepted.gates.healthFactor,1);
      assert.equal(ctx.accepted.gates.operatingFraction,1);assert.equal(ctx.accepted.gates.controlFactor,1);
      assert.equal(ctx.accepted.powerBasis,'allocated');assert.ok(ctx.accepted.availablePower>0);
      return {flow:ctx.accepted.resourceOut,health:ctx.accepted.gates.healthFactor};
    }});
  const model=session([implementation]);model.step(1);
  assert.equal(model.getSnapshot().flowRates.delivery,0,'the next algebraic allocation reflects the failed pump');
  assert.equal(model.exportSnapshot().equationState.components.pump.state.flow,7,'the completed interval still records delivered flow');
  model.destroy();
});

test('v1 provider failures roll back step, command, parameter edit, reset, import and selection',()=>{
  let failure=null;
  const implementation=provider({stateSchema:objectSchema({steps:{type:'integer',minimum:0}}),
    initialize:()=>{if(failure==='initialize')throw new Error('initialize failed');return {steps:0};},
    evaluate:(_phase,ctx)=>{
      if(failure==='evaluate')throw new Error('evaluate failed');
      if(failure==='late'&&ctx.timeMinutes>0)throw new Error('final refresh failed');
      if(failure==='late-multi'&&ctx.timeMinutes>=2)throw new Error('later substep failed');
      return {capacity:ctx.parameters.rate};
    },
    advance:ctx=>{if(failure==='advance')throw new Error('advance failed');return {steps:ctx.providerState.steps+1};}});
  const model=session([implementation]);
  failure='evaluate';
  unchanged(model,()=>model.step(1),/evaluate failed/);
  unchanged(model,()=>command(model,'step',1),/evaluate failed/);
  unchanged(model,()=>command(model,'setLoad',30),/evaluate failed/);
  unchanged(model,()=>command(model,'setParameter',.3,'response'),/evaluate failed/);
  const saved=model.exportSnapshot();saved.state.components.pump.load=42;
  unchanged(model,()=>model.importSnapshot(saved),/evaluate failed/);
  unchanged(model,()=>model.setEquationBindings(bindings('test.flow',{rate:9})),/evaluate failed/);
  failure='advance';unchanged(model,()=>model.step(1),/advance failed/);
  failure='late';unchanged(model,()=>model.step(1),/final refresh failed/);
  failure='late-multi';unchanged(model,()=>model.step(3),/later substep failed/);
  failure='initialize';unchanged(model,()=>model.reset(),/initialize failed/);
  unchanged(model,()=>model.setEquationBindings(bindings()),/initialize failed/);
  failure=null;model.step(1);assert.equal(model.exportSnapshot().equationState.components.pump.state.steps,1);
  model.destroy();
});

test('v1 missing providers, incompatible saved identity and malformed outputs reject atomically',()=>{
  let invalid=null;
  const implementation=provider({evaluate:(_phase,ctx)=>{
    if(invalid==='mutate')ctx.core.load=0;
    if(invalid==='promise')return Promise.resolve({capacity:1});
    return {capacity:invalid==='nan'?NaN:invalid==='negative'?-1:ctx.parameters.rate};
  }});
  const model=session([implementation]);
  unchanged(model,()=>model.setEquationBindings(bindings('test.missing')),/Missing equation provider/);
  const saved=model.exportSnapshot();saved.equationState.components.pump.stateVersion=999;
  unchanged(model,()=>model.importSnapshot(saved),/version mismatch/);
  for(const mode of ['mutate','promise','nan','negative']){
    invalid=mode;unchanged(model,()=>model.step(1),/read only|extensible|synchronously|finite|outside/i);
  }
  invalid=null;model.step(.5);model.destroy();
});

test('v1 optional clock stops after a failed provider and keeps last accepted observations',()=>{
  let callback,starts=0,stops=0,broken=false;
  const model=session([provider({evaluate:(_phase,ctx)=>{if(broken)throw new Error('clock provider failed');return {capacity:ctx.parameters.rate};}})],bindings(),
    {clock:{setInterval:fn=>{starts++;callback=fn;return 7;},clearInterval:id=>{assert.equal(id,7);stops++;}}});
  assert.equal(starts,0);model.start();model.start();assert.equal(starts,1);
  const readings=model.getSnapshot().readings;broken=true;assert.doesNotThrow(()=>callback());
  assert.equal(stops,1);assert.equal(model.clockStarted,false);assert.equal(model.getSnapshot().running,false);
  assert.equal(model.getSnapshot().components.pump.running,false);
  assert.deepEqual(model.getSnapshot().readings,readings);assert.match(model.getSnapshot().events.at(-1).message,/clock provider failed/);
  model.destroy();assert.equal(stops,1);
});

test('v1 clock failure reporting accepts arbitrary thrown values without invoking error accessors',()=>{
  let accessorCalls=0;
  const hostile={toString(){accessorCalls++;throw Error('must not stringify');}};
  Object.defineProperty(hostile,'message',{get(){accessorCalls++;throw Error('must not read');}});
  for(const thrown of [null,undefined,hostile]){
    let callback,broken=false,stops=0;
    const model=session([provider({evaluate:(_phase,ctx)=>{if(broken)throw thrown;return {capacity:ctx.parameters.rate};}})],bindings(),
      {clock:{setInterval:fn=>{callback=fn;return 9;},clearInterval:()=>{stops++;}}});
    model.start();broken=true;assert.doesNotThrow(()=>callback());
    assert.equal(stops,1);assert.equal(model.clockStarted,false);
    assert.equal(model.getSnapshot().running,false);assert.equal(model.getSnapshot().components.pump.running,false);
    assert.equal(model.getSnapshot().events.at(-1).message,'Equation provider failed.');
    const saved=model.exportSnapshot();broken=false;model.importSnapshot(saved);
    assert.deepEqual(model.exportSnapshot(),saved,'the paused error state remains a valid saved session');
    model.destroy();
  }
  assert.equal(accessorCalls,0);
});
