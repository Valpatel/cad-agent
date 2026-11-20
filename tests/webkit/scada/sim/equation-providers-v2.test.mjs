import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {CircuitSystemModel} from '../../../../software/cadagent/webkit/scada/sim/src/v2/circuit-system.mjs';
import {createV2ModelDefinition} from '../../../../software/cadagent/webkit/scada/sim/src/v2/contract.mjs';

const object = properties => ({type:'object',properties,required:Object.keys(properties),additionalProperties:false});
const number = {type:'number',minimum:0,maximum:1e9};
function provider(id, phases, evaluate, extra={}) {
  return {id,version:'1.0.0',stateVersion:1,engines:[2],phases,units:'scada-index-v1',
    parameterSchema:object({}),stateSchema:object({}),defaultParameters:{},initialize:()=>({}),evaluate,...extra};
}
const binding = (p, parameters={}) => ({id:p.id,version:p.version,parameters});
const equations = components => ({version:1,components});
const cmd = (m, action, equipment, value) => m.dispatch({action,arguments:{equipment,value}});
const edge=(id,from,fromPort,to,toPort,medium='liquid')=>({id,from:{component:from,port:fromPort},to:{component:to,port:toPort},medium});
function pumping() {
  const system={system:{id:'equation-pump'},components:[{id:'source',type:'tank'},{id:'pump',type:'pump'},{id:'sink',type:'tank'},{id:'supply',type:'transformer'}],connections:[
    edge('in','source','outlet','pump','inlet'),edge('out','pump','outlet','sink','inlet'),edge('power','supply','secondary','pump','drive','electricity'),
  ]};
  const definition=createV2ModelDefinition(system);
  for(const c of Object.values(definition.components)) {
    c.initial.load=100;c.parameters.response=0;c.parameters.damageRate=0;c.parameters.warningAt=100;
    c.parameters.capacity=100;
    for(const circ of Object.values(c.circuits)){circ.parameters.capacity=100;circ.parameters.pressureGain=0;circ.initial.pressure=0;}
  }
  definition.components.source.circuits.water.role='source';
  definition.components.sink.circuits.water.role='sink';
  definition.components.pump.energy.demand=100;
  definition.components.supply.energy={role:'source',inputs:[],outputs:['secondary'],capacity:8,demand:0,efficiency:1,supply:{kind:'boundary'}};
  return {system,definition};
}
function scenario(id) {
  return {system:JSON.parse(readFileSync(new URL(`../../../../software/cadagent/webkit/scada/sim/scenarios/${id}/system.json`,import.meta.url))),definition:JSON.parse(readFileSync(new URL(`../../../../software/cadagent/webkit/scada/sim/scenarios/${id}/model.json`,import.meta.url)))};
}
function create(f, providers=[], selections) {
  const definition=structuredClone(f.definition);
  if(selections)definition.equations=selections;
  return new CircuitSystemModel(f.system,definition,{equationProviders:providers});
}
const near=(a,b)=>assert.ok(Math.abs(a-b)<1e-8,`${a} != ${b}`);
function unchanged(m, operation) {
  const saved=m.exportSnapshot(),visible=m.getSnapshot();
  assert.throws(operation);
  assert.deepEqual(m.exportSnapshot(),saved);
  assert.equal(m.getSnapshot(),visible);
}

// The default flow is linear in the available power fraction. A selected custom
// cube-root law can exceed that default while respecting rating/stock and zero gates.
test('v2 resource equations change allocation before transport, without double derating or bypassing supply/off gates', () => {
  const f=pumping(), normal=create(f);
  const nonlinear=provider('test/nonlinear',['resource'],(phase,ctx)=>({capacity:100*Math.cbrt(ctx.gates.powerFactor)}));
  const model=create(f,[nonlinear],equations({pump:binding(nonlinear)}));
  try {
    near(normal.getSnapshot().flowRates.out,8);
    near(model.getSnapshot().flowRates.out,100*Math.cbrt(.08));
    assert.ok(model.getSnapshot().flowRates.out>normal.getSnapshot().flowRates.out);
    const old=model.exportSnapshot().state.circuits.source.water.amount;
    model.step(.25);
    near(model.exportSnapshot().state.circuits.source.water.amount,old,'external boundary stock stays fixed');
    cmd(model,'setEnabled','supply',false);
    near(model.getSnapshot().flowRates.out,0);
    cmd(model,'setEnabled','supply',true);
    cmd(model,'setEnabled','pump',false);
    near(model.getSnapshot().flowRates.out,0);
  } finally { normal.destroy();model.destroy(); }
});

test('v2 unselected laws preserve the legacy sub-epsilon rate instead of applying the new provider gate', () => {
  const f=pumping();f.definition.components.supply.energy.capacity=1e-10;
  const model=create(f);
  try {assert.equal(model.getSnapshot().flowRates.out,1e-10);} finally {model.destroy();}
});

test('v2 effective energy demand governs both accepted power and observed power factor', () => {
  const f=pumping();
  const law=provider('test/energy',['energy'],(phase,ctx)=>ctx.equipment.id==='pump'?{demand:4}:{capacity:2});
  const model=create(f,[law],equations({pump:binding(law)}));
  try {
    near(model.getSnapshot().readings.pump.powerIn,4);
    near(model.getSnapshot().readings.pump.powerFactor,1);
    model.setEquationBindings(equations({pump:binding(law),supply:binding(law)}));
    near(model.getSnapshot().readings.pump.powerIn,2);
    near(model.getSnapshot().readings.pump.powerFactor,.5);
  } finally { model.destroy(); }
});

test('v2 operating, pressure and condition hooks change actual state with frozen stage contexts', () => {
  const law=provider('test/stages',['operating','pressure','condition'],(phase,ctx)=>{
    assert.ok(Object.isFrozen(ctx)&&Object.isFrozen(ctx.core)&&Object.isFrozen(ctx.configuration));
    if(phase==='operating')return {operating:25};
    if(phase==='pressure'){assert.ok(ctx.readings.resourceOut>=0);return {target:73};}
    assert.equal(ctx.previous.damage,ctx.core.damage);
    return {damage:ctx.previous.damage+2};
  });
  const model=create(pumping(),[law],equations({pump:binding(law)}));
  try {
    model.step(.5);
    const saved=model.exportSnapshot();
    near(saved.state.components.pump.operating,25);
    near(saved.state.circuits.pump.process.pressure,73);
    near(saved.state.components.pump.damage,2);
  } finally { model.destroy(); }
});

test('v2 stateful advance runs once per substep with actual accepted rates and survives exact replay', () => {
  const law=provider('test/counter',['resource'],()=>({capacity:20}),{
    stateSchema:object({ticks:{type:'integer',minimum:0,maximum:1e6},elapsed:number,volume:number}),
    initialize:()=>({ticks:0,elapsed:0,volume:0}),
    advance:ctx=>({ticks:ctx.providerState.ticks+1,elapsed:ctx.providerState.elapsed+ctx.dtMinutes,volume:ctx.providerState.volume+ctx.accepted.resourceOut*ctx.dtMinutes}),
  });
  const f=pumping(),model=create(f,[law],equations({pump:binding(law)})),restored=create(f,[law]);
  try {
    model.getSnapshot();cmd(model,'setLoad','pump',90);model.getSnapshot();
    assert.equal(model.exportSnapshot().equationState.components.pump.state.ticks,0);
    model.step(2.5);
    const saved=model.exportSnapshot(),state=saved.equationState.components.pump.state;
    assert.equal(state.ticks,3);near(state.elapsed,2.5);assert.ok(state.volume>0);
    restored.importSnapshot(saved);
    assert.deepEqual(restored.exportSnapshot(),saved);
    assert.deepEqual(restored.getSnapshot(),model.getSnapshot());
    for(const dt of [.25,1.5]){model.step(dt);restored.step(dt);assert.deepEqual(restored.exportSnapshot(),model.exportSnapshot());assert.deepEqual(restored.getSnapshot(),model.getSnapshot());}
    const stocks=structuredClone(model.exportSnapshot().state);
    model.setEquationBindings(equations({pump:binding(law)}));
    assert.deepEqual(model.exportSnapshot().state,stocks);
    assert.equal(model.exportSnapshot().equationState.components.pump.state.ticks,0);
    model.setEquationBindings(null);
    assert.equal(Object.hasOwn(model.exportSnapshot(),'equationState'),false);
    assert.equal(Object.hasOwn(model.exportModelDefinition(),'equations'),false);
  } finally {model.destroy();restored.destroy();}
});

test('v2 thermal source and retained-heat loss proposals obey accepted electricity and ledger budgets', () => {
  const law=provider('test/heat',['thermal-source','thermal-loss'],phase=>phase==='thermal-source'?{heat:1e6}:{heat:0},{
    stateSchema:object({accepted:number}),initialize:()=>({accepted:0}),advance:ctx=>({accepted:ctx.providerState.accepted+ctx.accepted.heatSource}),
  });
  const model=create(scenario('electric-batch-oven'),[law],equations({oven:binding(law)}));
  try {
    const retainedHeat=state=>state.thermalStores.oven+Object.values(state.circuits.oven).reduce((sum,circuit)=>sum+circuit.heat,0);
    const before=model.exportSnapshot(),heat=retainedHeat(before.state);
    const accepted=model.getSnapshot().readings.oven.powerIn;
    model.step(1);
    const after=model.exportSnapshot();
    near(retainedHeat(after.state)-heat,accepted);
    near(after.equationState.components.oven.state.accepted,accepted);
    near(after.state.ledger.energyLoss-before.state.ledger.energyLoss,0);
    cmd(model,'setEnabled','supply',false);
    const retained=retainedHeat(model.exportSnapshot().state);
    model.step(1);near(retainedHeat(model.exportSnapshot().state),retained);
  } finally {model.destroy();}
});

test('v2 thermal transfer and loss hooks account paired heat debit, credit and rejected loss', () => {
  const system={system:{id:'heat-law'},components:[{id:'hx',type:'heat-exchanger'}],connections:[]};
  const definition=createV2ModelDefinition(system);
  const c=definition.components.hx;c.parameters.damageRate=0;c.circuits.hot.initial.temperature=90;c.circuits.cold.initial.temperature=10;
  const law=provider('test/transfer',['thermal-transfer'],()=>({heat:10,lossFraction:.2}));
  const model=create({system,definition},[law],equations({hx:binding(law)}));
  try {
    const before=model.exportSnapshot().state;
    model.step(1);const after=model.exportSnapshot().state;
    near(before.circuits.hx.hot.heat-after.circuits.hx.hot.heat,10);
    near(after.circuits.hx.cold.heat-before.circuits.hx.cold.heat,8);
    near(after.ledger.heatBoundaryOut-before.ledger.heatBoundaryOut,2);
  } finally {model.destroy();}
});

test('v2 provider throws, invalid outputs and attempted context mutation roll back complete steps and commands', () => {
  let failure=null;
  const law=provider('test/atomic',['resource'],(phase,ctx)=>{
    if(failure==='throw')throw Error('equation failed');
    if(failure==='mutate')ctx.core.enabled=false;
    if(failure==='invalid')return {capacity:NaN};
    if(failure==='async')return Promise.resolve({capacity:1});
    return {capacity:10};
  },{stateSchema:object({ticks:number}),initialize:()=>({ticks:0}),advance:ctx=>failure==='advance'?{invalid:1}:{ticks:ctx.providerState.ticks+1}});
  const model=create(pumping(),[law],equations({pump:binding(law)}));
  try {
    model.step(1);
    for(const mode of ['throw','mutate','invalid','async','advance']){
      failure=mode;
      unchanged(model,()=>model.dispatch({action:'step',arguments:{minutes:2}}));
    }
    failure='throw';unchanged(model,()=>cmd(model,'setLoad','pump',30));
    unchanged(model,()=>model.dispatch({action:'setParameter',arguments:{equipment:'pump',key:'capacity',value:10}}));
    failure=null;model.step(.25);
  } finally {model.destroy();}
});

test('v2 failed initialization, hot swap, reset and incompatible restore are atomic', () => {
  let badInitialize=false,badEvaluate=false;
  const good=provider('test/lifecycle',['resource'],()=>{if(badEvaluate)throw Error('bad evaluation');return {capacity:10};},{stateSchema:object({ticks:number}),initialize:()=>{if(badInitialize)throw Error('bad initialization');return {ticks:0};},advance:ctx=>({ticks:ctx.providerState.ticks+1})});
  const other=provider('test/other',['resource'],()=>({capacity:2}));
  const f=pumping(),model=create(f,[good,other],equations({pump:binding(good)})),missing=create(f);
  try {
    model.step(1);const saved=model.exportSnapshot();
    badInitialize=true;unchanged(model,()=>model.reset());unchanged(model,()=>model.setEquationBindings(equations({pump:binding(good)})));badInitialize=false;
    badEvaluate=true;unchanged(model,()=>model.setEquationBindings(equations({pump:binding(good)})));unchanged(model,()=>model.importSnapshot(saved));badEvaluate=false;
    unchanged(model,()=>model.setEquationBindings(equations({pump:{id:'not-registered',version:'1.0.0',parameters:{}}})));
    unchanged(missing,()=>missing.importSnapshot(saved));
    for(const mutate of [s=>s.equationState.components.pump.stateVersion++,s=>s.equationState.components.pump.id='test/other',s=>s.equationState.components.pump.version='2.0.0',s=>s.equationState.components.pump.state.ticks=-1]){
      const bad=structuredClone(saved);mutate(bad);unchanged(model,()=>model.importSnapshot(bad));
    }
    model.setEquationBindings(equations({pump:binding(other)}));
    model.importSnapshot(saved);
    assert.deepEqual(model.exportSnapshot(),saved,'saved registered bindings and state are restored, not the current selection');
  } finally {model.destroy();missing.destroy();}
});

test('v2 clipped demand exposes delivered power rather than an apparent full-power ratio', () => {
  const seen=[];
  const law=provider('test/delivered',['energy','resource','pressure'],(phase,ctx)=>{
    if(phase==='energy')return {demand:1000};
    seen.push({phase,power:ctx.availablePower,rating:ctx.ratedDemand,basis:ctx.powerBasis,gates:ctx.gates});
    return phase==='resource'?{capacity:ctx.availablePower}:{target:ctx.availablePower};
  });
  const f=pumping();f.definition.components.pump.energy.demand=4;
  const model=create(f,[law],equations({pump:binding(law)}));
  try {
    near(model.getSnapshot().readings.pump.powerIn,4);
    near(model.getSnapshot().readings.pump.powerFactor,1);
    near(model.getSnapshot().flowRates.out,4);
    model.step(.5);
    const pressure=seen.find(item=>item.phase==='pressure');
    assert.equal(pressure.power,4);assert.equal(pressure.rating,4);assert.equal(pressure.basis,'allocated');
    assert.equal(pressure.gates.powerFactor,1);assert.equal(pressure.gates.controlFactor,1);
    cmd(model,'setEnabled','pump',false);
    assert.equal(seen.at(-1).gates.healthFactor,1,'healthy and disabled are distinct');
    assert.equal(seen.at(-1).gates.enabled,false);near(model.getSnapshot().flowRates.out,0);
  } finally {model.destroy();}
  const zero=pumping();zero.definition.components.pump.energy.demand=0;
  const aggressive=provider('test/no-free-drive',['energy','resource'],phase=>phase==='energy'?{demand:1000}:{capacity:100});
  const unpowered=create(zero,[aggressive],equations({pump:binding(aggressive)}));
  try {near(unpowered.getSnapshot().readings.pump.powerIn,0);near(unpowered.getSnapshot().flowRates.out,0);} finally {unpowered.destroy();}
});

test('v2 custom auxiliary demand stays within its per-port rating', () => {
  const system={system:{id:'aux-rating'},components:[{id:'supply',type:'battery'},{id:'generator',type:'alternator'}],connections:[edge('field','supply','dc','generator','field','electricity')]};
  const definition=createV2ModelDefinition(system);
  definition.components.supply.initial.load=100;
  definition.components.supply.energy={role:'source',inputs:[],outputs:['dc'],capacity:60,demand:0,efficiency:1,supply:{kind:'boundary'}};
  definition.components.generator.parameters.demand=2;
  const law=provider('test/auxiliary',['energy'],()=>({auxiliaryDemand:1000}));
  const model=create({system,definition},[law],equations({generator:binding(law)}));
  try {near(model.getSnapshot().flowRates.field,2);} finally {model.destroy();}
});

test('v2 a generating reversible pump is resource powered and does not require incoming shaft power', () => {
  const system={system:{id:'pumped-storage-law'},components:[{id:'upper',type:'tank'},{id:'pump',type:'reversible-pump-turbine'},{id:'lower',type:'tank'},{id:'load',type:'alternator'}],connections:[
    edge('water-in','upper','outlet','pump','upper'),edge('water-out','pump','lower','lower','inlet'),edge('shaft','pump','shaft','load','shaft','mechanical'),
  ]};
  const definition=createV2ModelDefinition(system);
  definition.components.upper.circuits.water.role='source';definition.components.lower.circuits.water.role='sink';
  definition.components.pump.initial.mode='generating';definition.components.pump.initial.load=100;
  definition.components.load.initial.load=100;
  definition.components.load.energy={role:'load',inputs:['shaft','field'],outputs:[],capacity:60,demand:10,efficiency:1};
  const law=provider('test/generating-resource',['resource'],()=>({capacity:20}));
  const model=create({system,definition},[law],equations({pump:binding(law)}));
  try {
    near(model.getSnapshot().readings.pump.powerIn,0);
    assert.ok(model.getSnapshot().readings.pump.powerOut>0);
    assert.ok(model.getSnapshot().flowRates['water-out']>0);
    model.step(.5);
    assert.ok(model.getSnapshot().readings.pump.powerOut>0);
  } finally {model.destroy();}
});

test('v2 thermal source proposals obey source ratings and finite receiver room', () => {
  const f=scenario('electric-batch-oven');
  f.definition.components.oven.heatSource.capacity=2;
  f.definition.components.oven.thermalLinks=[];
  const law=provider('test/rated-heat',['thermal-source','thermal-loss'],phase=>phase==='thermal-source'?{heat:1e9}:{heat:0});
  const model=create(f,[law],equations({oven:binding(law)}));
  try {
    const before=model.exportSnapshot();model.step(.5);
    near(model.exportSnapshot().state.thermalStores.oven-before.state.thermalStores.oven,1);
    const filled=model.exportSnapshot();filled.state.thermalStores.oven=99.75;model.importSnapshot(filled);
    const loss=model.exportSnapshot().state.ledger.energyLoss;model.step(1);
    near(model.exportSnapshot().state.thermalStores.oven,100);
    assert.ok(model.exportSnapshot().state.ledger.energyLoss>loss,'unused accepted electricity is recorded as loss');
  } finally {model.destroy();}
});

test('v2 advance distinguishes accepted interval gates from a newly latched failure', () => {
  const law=provider('test/interval',['resource','condition'],phase=>phase==='condition'?{damage:100}:{capacity:10},{
    stateSchema:object({acceptedPower:number,acceptedFlow:number,intervalHealth:number,currentHealth:number}),
    initialize:()=>({acceptedPower:0,acceptedFlow:0,intervalHealth:0,currentHealth:0}),
    advance:ctx=>({acceptedPower:ctx.accepted.gates.availablePower,acceptedFlow:ctx.accepted.resourceOut,intervalHealth:ctx.accepted.gates.healthFactor,currentHealth:ctx.gates.healthFactor}),
  });
  const model=create(pumping(),[law],equations({pump:binding(law)}));
  try {
    model.step(.5);
    const state=model.exportSnapshot().equationState.components.pump.state;
    near(state.acceptedPower,8);near(state.acceptedFlow,10);
    near(state.intervalHealth,1);near(state.currentHealth,0);
    near(model.getSnapshot().flowRates.out,0);
  } finally {model.destroy();}
});

test('v2 a later provider failure restores already advanced provider state and accepted core stocks', () => {
  let fail=false;
  const law=provider('test/multiple',['resource'],()=>({capacity:10}),{
    stateSchema:object({ticks:number}),initialize:()=>({ticks:0}),advance:ctx=>{
      if(fail&&ctx.equipment.id==='sink')throw Error('later provider failed');
      return {ticks:ctx.providerState.ticks+1};
    },
  });
  const model=create(pumping(),[law],equations({pump:binding(law),sink:binding(law)}));
  try {
    model.step(1);fail=true;unchanged(model,()=>model.step(1));
    fail=false;model.step(1);
    assert.equal(model.exportSnapshot().equationState.components.pump.state.ticks,2);
    assert.equal(model.exportSnapshot().equationState.components.sink.state.ticks,2);
  } finally {model.destroy();}
});

test('v2 a failure after two accepted internal substeps rolls back the entire requested step', () => {
  let fail=true;
  const law=provider('test/late-substep',['resource'],()=>({capacity:10}),{
    stateSchema:object({ticks:number}),initialize:()=>({ticks:0}),advance:ctx=>{
      if(fail&&ctx.timeMinutes>=2)throw Error('third substep failed');
      return {ticks:ctx.providerState.ticks+1};
    },
  });
  const model=create(pumping(),[law],equations({pump:binding(law)}));
  try {
    unchanged(model,()=>model.step(3));
    fail=false;model.step(3);
    assert.equal(model.exportSnapshot().equationState.components.pump.state.ticks,3);
    assert.equal(model.exportSnapshot().state.minutes,3);
  } finally {model.destroy();}
});

test('v2 the optional clock stops cleanly when a provider also fails during error refresh', () => {
  let callback,stops=0,fail=false;
  const law=provider('test/clock',['resource'],()=>{if(fail)throw Error('persistent provider failure');return {capacity:10};});
  const f=pumping();f.definition.equations=equations({pump:binding(law)});
  const model=new CircuitSystemModel(f.system,f.definition,{equationProviders:[law],clock:{setInterval:fn=>{callback=fn;return 23;},clearInterval:id=>{assert.equal(id,23);stops++;}}});
  try {
    const readings=model.getSnapshot().readings,core=model.exportSnapshot().state;
    model.start();fail=true;assert.doesNotThrow(callback);
    assert.equal(stops,1);assert.equal(model.clockStarted,false);assert.equal(model.getSnapshot().running,false);
    assert.deepEqual(model.getSnapshot().readings,readings);
    assert.deepEqual(model.exportSnapshot().state.circuits,core.circuits);
    assert.equal(model.exportSnapshot().state.minutes,core.minutes);
    assert.match(model.getSnapshot().events.at(-1).message,/persistent provider failure/);
    for(const visual of Object.values(model.getSnapshot().components))if(Object.hasOwn(visual,'running'))assert.equal(visual.running,false);
  } finally {model.destroy();}
});

test('v2 clock errors tolerate non-Error throws without invoking hostile message accessors', () => {
  let accessed=0;
  const hostile=Object.create(null);
  Object.defineProperty(hostile,'message',{get(){accessed++;throw Error('message getter must not run');}});
  Object.defineProperty(hostile,'toString',{get(){accessed++;throw Error('toString getter must not run');}});
  for(const thrown of [null,undefined,hostile]){
    let callback,fail=false;
    const law=provider('test/non-error',['resource'],()=>{if(fail)throw thrown;return {capacity:10};});
    const f=pumping();f.definition.equations=equations({pump:binding(law)});
    const model=new CircuitSystemModel(f.system,f.definition,{equationProviders:[law],clock:{setInterval:fn=>{callback=fn;return 1;},clearInterval:()=>{}}});
    try {
      const saved=model.exportSnapshot(),readings=model.getSnapshot().readings;
      model.start();fail=true;assert.doesNotThrow(callback);
      assert.equal(model.clockStarted,false);assert.equal(model.getSnapshot().running,false);
      assert.deepEqual(model.getSnapshot().readings,readings);
      assert.deepEqual(model.exportSnapshot().state.circuits,saved.state.circuits);
      assert.equal(model.getSnapshot().events.at(-1).severity,'critical');
      assert.ok(model.getSnapshot().events.at(-1).message.length>0);
      fail=false;model.importSnapshot(model.exportSnapshot());
    } finally {model.destroy();}
  }
  assert.equal(accessed,0);
});
