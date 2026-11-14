import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {createV2ModelDefinition,createV2Component,V2_TYPE_CONTRACTS} from '../../../../software/cadagent/webkit/scada/sim/src/v2/contract.mjs';
import {validateV2Definition} from '../../../../software/cadagent/webkit/scada/sim/src/v2/validation.mjs';
import {CircuitSystemModel,createV2Adapter} from '../../../../software/cadagent/webkit/scada/sim/src/v2/circuit-system.mjs';
import {MODEL_DESCRIPTORS,V2_MODEL_DESCRIPTORS,V2_VARIANT_DESCRIPTORS,getModelDescriptor,createModelDefinition} from '../../../../software/cadagent/webkit/scada/sim/src/index.mjs';

const near=(a,b,tolerance=1e-6)=>assert.ok(Math.abs(a-b)<tolerance,`${a} ≠ ${b}`);
const edge=(id,from,fromPort,to,toPort,medium='liquid')=>({id,from:{component:from,port:fromPort},to:{component:to,port:toPort},medium});
const system=(types,connections=[])=>({system:{id:'fixture'},components:Object.entries(types).map(([id,type])=>({id,type})),connections});
const modelFor=(sys,edit=()=>{})=>{const config=createV2ModelDefinition(sys);edit(config);return new CircuitSystemModel(sys,config);};
const external=(config,id,output='output')=>{config.components[id].energy={role:'source',inputs:[],outputs:[output],capacity:100,demand:0,efficiency:1,supply:{kind:'boundary'}};config.components[id].initial.load=100;};
const inventory=saved=>Object.values(saved.state.circuits).flatMap(Object.values).reduce((sum,c)=>sum+c.amount,0);
const heat=saved=>Object.values(saved.state.circuits).flatMap(Object.values).reduce((sum,c)=>sum+c.heat,0)+Object.values(saved.state.thermalStores).reduce((a,b)=>a+b,0);
const energy=saved=>heat(saved)+Object.values(saved.state.energyStores).reduce((a,b)=>a+b,0);
const totalEnergyLedger=snapshot=>snapshot.ledger.energyBoundaryIn+snapshot.ledger.heatBoundaryIn-snapshot.ledger.energyBoundaryOut-snapshot.ledger.heatBoundaryOut-snapshot.ledger.energyLoss;
const loop=()=>{
  const sys=system({grid:'generator',tank:'tank',pump:'pump'},[edge('supply','grid','output','pump','drive','electricity'),edge('out','tank','outlet','pump','inlet'),edge('return','pump','outlet','tank','inlet')]);
  return modelFor(sys,c=>{external(c,'grid');c.components.pump.initial.load=100;c.components.pump.energy.demand=3;});
};

test('all 142 base templates have runnable, validated data-only model records',()=>{
  assert.equal(V2_TYPE_CONTRACTS.length,142);
  for(const descriptor of V2_TYPE_CONTRACTS){const sys=system({asset:descriptor.type}),definition=createV2ModelDefinition(sys),validation=validateV2Definition(sys,definition);assert.equal(validation.ok,true,`${descriptor.type}: ${JSON.stringify(validation.errors)}`);const model=new CircuitSystemModel(sys,definition);model.step(.1);assert.equal(model.getSnapshot().minutes,.1);model.destroy();}
});

test('versioned public registries preserve eighty legacy types and expose every explicit v2 variant',()=>{
  assert.equal(MODEL_DESCRIPTORS.length,80);
  assert.equal(V2_MODEL_DESCRIPTORS.length,142);
  assert.equal(V2_VARIANT_DESCRIPTORS.length,97);
  for(const descriptor of V2_VARIANT_DESCRIPTORS){
    const sys=system({asset:descriptor.type});sys.components[0].variant=descriptor.variant;
    const definition=createModelDefinition(sys,{version:2});
    assert.deepEqual(descriptor,getModelDescriptor(descriptor.type,{version:2,variant:descriptor.variant}));
    assert.deepEqual(descriptor.defaultModel,createV2Component(descriptor.type,{variant:descriptor.variant}));
    const validation=validateV2Definition(sys,definition);
    assert.equal(validation.ok,true,`${descriptor.type}/${descriptor.variant}: ${JSON.stringify(validation.errors)}`);
    const model=new CircuitSystemModel(sys,definition);model.step(.1);model.importSnapshot(model.exportSnapshot());model.destroy();
  }
  assert.throws(()=>getModelDescriptor('tank',{version:3}),/versions/);
  assert.throws(()=>createModelDefinition(system({tank:'tank'}),{version:3}),/versions/);
  const metadata=JSON.parse(readFileSync(new URL('../../../../software/cadagent/webkit/scada/sim/metadata/model-registry-v2.json',import.meta.url),'utf8'));
  assert.equal(metadata.version,2);assert.deepEqual(metadata.models,V2_MODEL_DESCRIPTORS);assert.deepEqual(metadata.variants,V2_VARIANT_DESCRIPTORS);
});

test('a complete catalog session restores its exact topology signature through direct and command imports',()=>{
  const sys=system(Object.fromEntries(V2_MODEL_DESCRIPTORS.map((item,index)=>[`asset${index}`,item.type])));
  const model=modelFor(sys),saved=model.exportSnapshot();
  assert.ok(saved.system.signature.length>16384);
  model.importSnapshot(saved);assert.deepEqual(model.exportSnapshot(),saved);
  model.dispatch({action:'import',arguments:{payload:saved}});assert.deepEqual(model.exportSnapshot(),saved);
  const invalid=structuredClone(saved);invalid.model.assumptions=['x'.repeat(16385)];
  assert.throws(()=>model.importSnapshot(invalid),/Text exceeds/);assert.deepEqual(model.exportSnapshot(),saved);
});

test('isolated exchanger circuits transfer heat while preserving each stock',()=>{
  const model=modelFor(system({exchanger:'nuclear-steam-generator'}),c=>{
    c.components.exchanger.circuits.primary.initial.inventory=80;c.components.exchanger.circuits.primary.initial.temperature=90;
    c.components.exchanger.circuits.secondary.initial.inventory=20;c.components.exchanger.circuits.secondary.initial.temperature=10;
  });
  const before=model.exportSnapshot(),a=model.getSnapshot().circuits.exchanger;model.step(10);const b=model.getSnapshot().circuits.exchanger;
  near(a.primary.amount,b.primary.amount);near(a.secondary.amount,b.secondary.amount);assert.ok(b.primary.temperature<a.primary.temperature);assert.ok(b.secondary.temperature>a.secondary.temperature);
  near(heat(model.exportSnapshot())-heat(before),totalEnergyLedger(model.getSnapshot()));
});

test('a filled closed loop needs a powered circulation driver and conserves inventory',()=>{
  const model=loop(),before=inventory(model.exportSnapshot());assert.ok(model.getSnapshot().flowRates.out>0);model.step(30);near(inventory(model.exportSnapshot()),before);
  model.dispatch({action:'setEnabled',arguments:{equipment:'pump',value:false}});near(model.getSnapshot().flowRates.out,0);near(model.getSnapshot().flowRates.return,0);
  model.dispatch({action:'setEnabled',arguments:{equipment:'pump',value:true}});model.dispatch({action:'setEnabled',arguments:{equipment:'grid',value:false}});near(model.getSnapshot().flowRates.out,0);
});

test('an empty closed loop and an unconnected pump never invent a bench supply',()=>{
  const model=loop();for(const id of ['tank','pump'])model.dispatch({action:'setLevel',arguments:{equipment:id,value:0}});model.step(1);near(model.getSnapshot().flowRates.out,0);near(Object.values(model.getSnapshot().circuits.tank)[0].amount+Object.values(model.getSnapshot().circuits.pump)[0].amount,0);
  const standalone=modelFor(system({pump:'pump'}));assert.equal(standalone.getSnapshot().readings.pump.powerFactor,0);near(standalone.getSnapshot().readings.pump.flow,0);
});

test('branch transfer is capped by summed circuit capacity',()=>{
  const sys=system({source:'tank',left:'tank',right:'tank'},[edge('left','source','outlet','left','inlet'),edge('right','source','outlet','right','inlet')]);
  const model=modelFor(sys,c=>{c.components.source.circuits.water.role='source';c.components.source.circuits.water.parameters.capacity=20;for(const id of ['left','right'])c.components[id].circuits.water.role='sink';});
  const rates=model.getSnapshot().flowRates;near(rates.left+rates.right,20);near(model.getSnapshot().portReadings.source.outlet.outgoing,20);near(model.getSnapshot().portReadings.source.outlet.net,20);model.step(1);near(model.getSnapshot().ledger.resourceBoundaryIn,20);near(model.getSnapshot().ledger.resourceBoundaryOut,20);
});

test('port readings aggregate every incoming branch at a shared port',()=>{
  const sys=system({left:'tank',right:'tank',mix:'tank'},[edge('left','left','outlet','mix','inlet'),edge('right','right','outlet','mix','inlet')]);
  const model=modelFor(sys,c=>{for(const id of ['left','right'])c.components[id].circuits.water.role='source';});
  const snapshot=model.getSnapshot(),port=snapshot.portReadings.mix.inlet;
  near(port.incoming,snapshot.flowRates.left+snapshot.flowRates.right);near(port.incoming,60);near(port.net,-60);assert.equal(port.direction,'in');
});

test('different heat capacities account for rejected heat instead of silently dropping it',()=>{
  const sys=system({hot:'tank',cold:'tank'},[edge('flow','hot','outlet','cold','inlet')]);
  const model=modelFor(sys,c=>{const a=c.components.hot.circuits.water,b=c.components.cold.circuits.water;a.role='source';a.initial.temperature=100;a.parameters.thermalCapacity=10;b.initial.inventory=1;b.initial.temperature=90;b.parameters.thermalCapacity=.1;});
  const before=model.exportSnapshot();model.step(1);near(heat(model.exportSnapshot())-heat(before),totalEnergyLedger(model.getSnapshot()));assert.ok(model.getSnapshot().ledger.heatBoundaryOut>0);
});

test('fuel-derived output plus rejected loss cannot exceed actual fuel input',()=>{
  const sys=system({fuel:'gas-holder',generator:'generator',load:'motor'},[edge('fuel','fuel','outlet','generator','fuel','gas'),edge('electricity','generator','output','load','supply','electricity')]);
  const model=modelFor(sys,c=>{c.components.fuel.circuits.gas.role='source';c.components.fuel.circuits.gas.fluid='fuel-gas';c.components.fuel.circuits.gas.parameters.capacity=10;c.components.generator.energy.efficiency=.5;c.components.generator.initial.load=100;c.components.load.energy.role='load';c.components.load.energy.outputs=[];c.components.load.energy.demand=100;c.components.load.initial.load=100;});
  assert.ok(model.getSnapshot().flowRates.electricity<=5+1e-8);model.step(1);assert.ok(model.getSnapshot().ledger.energyBoundaryIn<=10+1e-8);near(totalEnergyLedger(model.getSnapshot()),0);
});

test('generation debits heat before the same fluid can carry it downstream',()=>{
  const sys=system({source:'tank',turbine:'steam-turbine',sink:'tank',load:'motor'},[edge('feed','source','outlet','turbine','inlet','liquid'),edge('return','turbine','outlet','sink','inlet','liquid'),edge('electricity','turbine','output','load','supply','electricity')]);
  const model=modelFor(sys,c=>{c.components.source.circuits.water.role='source';c.components.source.circuits.water.initial.temperature=0;c.components.turbine.circuits.water.initial.inventory=1;c.components.turbine.circuits.water.parameters.stockScale=1;c.components.turbine.circuits.water.initial.temperature=100;c.components.turbine.initial.load=100;c.components.turbine.energy.efficiency=1;c.components.sink.circuits.water.role='sink';c.components.load.energy.role='load';c.components.load.energy.outputs=[];c.components.load.energy.demand=100;c.components.load.initial.load=100;});
  const before=model.exportSnapshot();model.step(1);near(energy(model.exportSnapshot())-energy(before),totalEnergyLedger(model.getSnapshot()));
});

test('a converter cycle with no source produces no energy',()=>{
  const sys=system({rectifier:'power-rectifier',inverter:'power-inverter'},[edge('dc','rectifier','dc','inverter','dc','electricity'),edge('ac','inverter','ac','rectifier','ac','electricity')]);
  const model=modelFor(sys);model.step(30);near(model.getSnapshot().flowRates.dc,0);near(model.getSnapshot().flowRates.ac,0);near(totalEnergyLedger(model.getSnapshot()),0);
});

test('battery charge and discharge modes preserve signed direction and efficiency',()=>{
  const sys=system({grid:'battery',battery:'battery'},[edge('link','grid','dc','battery','dc','electricity')]);
  const model=modelFor(sys,c=>{c.components.grid.energy={role:'boundary',inputs:['dc'],outputs:['dc'],capacity:100,demand:100,efficiency:1};c.components.grid.initial.load=100;c.components.battery.energy.capacity=10;c.components.battery.energy.efficiency=.8;c.components.battery.initial.load=100;c.components.battery.initial.mode='charge';c.connections.link={mode:{equipment:'battery',values:{charge:1,discharge:-1,idle:0}}};});
  const before=model.exportSnapshot();assert.ok(model.getSnapshot().flowRates.link>0);model.step(1);near(model.getSnapshot().energyStores.battery,58);near(energy(model.exportSnapshot())-energy(before),totalEnergyLedger(model.getSnapshot()));
  model.dispatch({action:'setMode',arguments:{equipment:'battery',value:'discharge'}});assert.ok(model.getSnapshot().flowRates.link<0);model.step(1);near(model.getSnapshot().energyStores.battery,45.5);near(energy(model.exportSnapshot())-energy(before),totalEnergyLedger(model.getSnapshot()));
});

test('ground references and CT observation ports never own fictitious material inventory',()=>{
  for(const type of ['earthing-switch','surge-arrester','current-transformer','voltage-transformer']){const model=modelFor(system({asset:type}));assert.deepEqual(model.getSnapshot().circuits.asset,{});}
});

test('source off retains stored heat and does not drain nuclear coolant',()=>{
  const model=modelFor(system({core:'pwr-reactor-vessel'})),before=model.getSnapshot();model.dispatch({action:'setEnabled',arguments:{equipment:'core',value:false}});model.step(1);assert.ok(model.getSnapshot().components.core.heat>0);near(Object.values(model.getSnapshot().circuits.core)[0].amount,Object.values(before.circuits.core)[0].amount);
});

test('saved circuit state resumes deterministically and readonly adapters share state',()=>{
  const model=loop(),saved=model.exportSnapshot(),readOnly=createV2Adapter(model,{readOnly:true});let updates=0;const unsubscribe=readOnly.subscribe(()=>updates++);assert.throws(()=>readOnly.dispatch({action:'reset'}),/read-only/);model.step(5);assert.equal(updates,1);unsubscribe();const first=model.exportSnapshot();model.importSnapshot(saved);model.step(5);assert.deepEqual(model.exportSnapshot(),first);assert.equal(readOnly.getSnapshot(),model.getSnapshot());
});

test('invalid model edits and negative imported heat leave canonical state unchanged',()=>{
  const model=loop(),before=model.exportSnapshot();assert.throws(()=>model.dispatch({action:'setParameter',arguments:{equipment:'pump',key:'response',value:Infinity}}));assert.deepEqual(model.exportSnapshot(),before);const bad=structuredClone(before);Object.values(bad.state.circuits.pump)[0].heat=-1;assert.throws(()=>model.importSnapshot(bad));assert.deepEqual(model.exportSnapshot(),before);
});

test('extended inspector commands edit circuits, tracers, zones, energy, modes and probe identity',()=>{
  const sys=system({water:'tank',probe:'water-quality-probe',battery:'battery',core:'pwr-reactor-vessel'});
  const model=modelFor(sys,c=>{
    c.zones.room={initial:{temperature:20,humidity:50,light:60,oxygen:70},parameters:{response:.1}};
    c.components.probe.observation={component:'water',circuit:'water',quantity:'oxygen'};
    delete c.components.probe.energy;
  });
  for(const [action,args] of [
    ['setCircuitParameter',{equipment:'water',circuit:'water',key:'capacity',value:25}],
    ['setTracer',{equipment:'water',circuit:'water',key:'ph',value:75}],
    ['setZoneValue',{zone:'room',key:'humidity',value:65}],
    ['setEnvironment',{key:'ambient',value:30}],
    ['setEnergyParameter',{equipment:'battery',key:'capacity',value:20}],
    ['setMode',{equipment:'battery',value:'idle'}],
    ['setMeasurement',{equipment:'probe',value:'ph'}],
    ['setRodPosition',{equipment:'core',value:80}],
  ])model.dispatch({action,arguments:args});
  const config=model.exportModelDefinition(),snapshot=model.getSnapshot();
  assert.equal(config.components.water.circuits.water.parameters.capacity,25);
  assert.equal(config.components.battery.energy.capacity,20);
  assert.equal(config.components.probe.measurement,'ph');
  assert.equal(config.components.probe.observation.quantity,'ph');
  near(snapshot.readings.probe.signal,75);
  assert.equal(snapshot.zones.room.humidity,65);
  assert.equal(snapshot.environment.ambient,30);
  assert.equal(snapshot.controls.core.rodPosition,80);
  assert.equal(snapshot.components.battery.status,'normal');
  assert.equal(snapshot.components.battery.active,false);
  model.importSnapshot(model.exportSnapshot());
});

test('malformed commands and rejected extended edits preserve state and snapshot identity',()=>{
  const model=loop(),saved=model.exportSnapshot(),snapshot=model.getSnapshot();
  const invalid=[null,[],{action:'reset',arguments:[]},{action:'reset',arguments:null},{action:'reset',label:{}},
    {action:'repair',arguments:{equipment:'missing'}},{action:'repair',arguments:{equipment:2}},
    {action:'setCircuitParameter',arguments:{equipment:'pump',circuit:'process',key:'stockScale',value:.01}},
    {action:'setEnergyParameter',arguments:{equipment:'pump',key:'efficiency',value:0}},
    {action:'setTracer',arguments:{equipment:'pump',circuit:'water',key:'ph',value:101}},
    {action:'setZoneValue',arguments:{zone:'missing',key:'light',value:10}},
    {action:'setEnvironment',arguments:{key:'missing',value:10}},
    {action:'setMeasurement',arguments:{equipment:'pump',value:'ph'}},
    {action:'setMode',arguments:{equipment:'pump',value:'idle'}},
    {action:'setRodPosition',arguments:{equipment:'pump',value:-1}},
  ];
  for(const command of invalid){assert.throws(()=>model.dispatch(command));assert.deepEqual(model.exportSnapshot(),saved);assert.equal(model.getSnapshot(),snapshot);}
});

test('a nonconvergent instantaneous energy cycle rejects steps without partial advancement',()=>{
  const sys=system({a:'transformer',b:'transformer',load:'transformer'},[
    edge('ab','a','secondary','b','primary','electricity'),edge('ba','b','secondary','a','primary','electricity'),edge('load','b','secondary','load','primary','electricity')]);
  const model=modelFor(sys,c=>{
    for(const id of ['a','b']){c.components[id].energy.efficiency=1;c.components[id].initial.load=100;}
    Object.assign(c.components.load.energy,{role:'load',inputs:['primary'],outputs:[],demand:.001});
    c.components.load.initial.load=0;c.components.load.parameters.response=1;
  });
  model.dispatch({action:'setLoad',arguments:{equipment:'load',value:1}});
  const saved=model.exportSnapshot(),snapshot=model.getSnapshot();
  for(const advance of [()=>model.step(1),()=>model.dispatch({action:'step',arguments:{minutes:1}})]){
    assert.throws(advance,/did not converge/);assert.deepEqual(model.exportSnapshot(),saved);assert.equal(model.getSnapshot(),snapshot);
  }
});

test('complete initial damage latches a fault and remains restorable after reset',()=>{
  const model=modelFor(system({pump:'pump'}),c=>{c.components.pump.initial.damage=100;});
  assert.equal(model.getSnapshot().controls.pump.fault,true);
  for(const reset of [()=>{},()=>model.reset()]){reset();const saved=model.exportSnapshot();model.importSnapshot(saved);assert.deepEqual(model.exportSnapshot(),saved);}
});

test('empty circuit composition edits reject without recording an applied command',()=>{
  const model=modelFor(system({tank:'tank'}),c=>{c.components.tank.circuits.water.initial.inventory=0;});
  const saved=model.exportSnapshot(),snapshot=model.getSnapshot();
  assert.throws(()=>model.dispatch({action:'setTracer',arguments:{equipment:'tank',circuit:'water',key:'ph',value:80}}),/empty circuit/);
  assert.deepEqual(model.exportSnapshot(),saved);assert.equal(model.getSnapshot(),snapshot);
});

test('a common bus requests its full demand through connected inputs while a reverse branch is idle',()=>{
  const sys=system({grid:'transformer',bus:'busbar',converter:'power-inverter',load:'transformer'},[
    edge('supply','grid','secondary','bus','supply','electricity'),edge('storage','converter','ac','bus','branch-a','electricity'),edge('load','bus','branch-b','load','primary','electricity')]);
  sys.components.find(c=>c.id==='bus').variant='bidirectional';
  const model=modelFor(sys,c=>{
    external(c,'grid','secondary');
    Object.assign(c.components.bus.energy,{inputs:['supply','branch-a'],outputs:['branch-a','branch-b'],capacity:100,efficiency:1});
    c.components.bus.parameters.capacity=100;c.components.bus.initial.load=100;
    Object.assign(c.components.load.energy,{role:'load',inputs:['primary'],outputs:[],demand:20});c.components.load.initial.load=100;
    c.components.converter.initial.mode='idle';
    c.connections.storage={mode:{equipment:'converter',values:{forward:1,reverse:-1,idle:0}}};
  });
  near(model.getSnapshot().readings.load.powerFactor,1);near(model.getSnapshot().flowRates.load,20);near(model.getSnapshot().flowRates.storage,0);
  model.dispatch({action:'setEnabled',arguments:{equipment:'bus',value:false}});
  near(model.getSnapshot().flowRates.load,0);
});

test('failed observation telemetry leaves circulation intact while controller loss gates explicit control',()=>{
  const sys=system({grid:'transformer',dc:'battery',core:'pwr-reactor-vessel',pump:'pump',plc:'plc-rack',probe:'neutron-monitor'},[
    edge('coolant-in','pump','outlet','core','coolant-in'),edge('coolant-out','core','coolant-out','pump','inlet'),
    edge('pump-power','grid','secondary','pump','drive','electricity'),edge('control-power','grid','secondary','plc','power','electricity'),edge('probe-power','dc','dc','probe','power','electricity'),
    edge('telemetry','probe','signal','plc','io','data'),edge('control','plc','io','core','control','data')]);
  sys.components.find(c=>c.id==='pump').variant='water';
  const model=modelFor(sys,c=>{external(c,'grid','secondary');external(c,'dc','dc');c.components.pump.initial.load=100;c.components.pump.circuits.process.fluid='primary-water';c.components.probe.observation={component:'core',circuit:'primary',quantity:'temperature'};});
  const before=model.getSnapshot().readings.pump.resourceOut;assert.ok(before>0);
  model.dispatch({action:'setFault',arguments:{equipment:'probe',value:'broken'}});
  assert.equal(model.getSnapshot().readings.probe.valid,false);near(model.getSnapshot().flowRates.telemetry,0);
  near(model.getSnapshot().readings.pump.resourceOut,before);assert.equal(model.getSnapshot().components.plc.connected,true);
  model.dispatch({action:'setFault',arguments:{equipment:'plc',value:true}});
  near(model.getSnapshot().readings.pump.resourceOut,0);near(model.getSnapshot().flowRates.control,0);
});
