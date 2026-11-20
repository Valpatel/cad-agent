import test from 'node:test';
import assert from 'node:assert/strict';
import {CircuitSystemModel,createV2ModelDefinition,getV2Descriptor,validateV2Definition} from '../../../../software/cadagent/webkit/scada/sim/src/index.mjs';

const near=(actual,expected,tolerance=1e-7)=>assert.ok(Math.abs(actual-expected)<=tolerance,`${actual} differs from ${expected}`);
const edge=(id,from,fromPort,to,toPort,medium='liquid')=>({id,from:{component:from,port:fromPort},to:{component:to,port:toPort},medium});
function fixture(types,connections=[]){
 const system={system:{id:'independent-regression'},components:Object.entries(types).map(([id,type])=>({id,type})),connections};
 const definition=createV2ModelDefinition(system);
 for(const c of Object.values(definition.components)){c.initial.load=100;c.parameters.damageRate=0;c.parameters.warningAt=100;c.parameters.response=0;c.thermalLinks=[];delete c.heatSource;delete c.thermalStore;for(const circ of Object.values(c.circuits)){circ.parameters.pressureGain=0;circ.initial.pressure=0;}}
 return {system,definition};
}
function instantiate(f){const validation=validateV2Definition(f.system,f.definition);assert.equal(validation.ok,true,JSON.stringify(validation.errors));return new CircuitSystemModel(f.system,f.definition);}
function totals(model){
 const saved=model.exportSnapshot(),definition=saved.model,state=saved.state;let amount=0,energy=0;
 for(const[id,circuits]of Object.entries(state.circuits))for(const[cid,c]of Object.entries(circuits))if(!['source','sink'].includes(definition.components[id].circuits[cid].role)){amount+=c.amount;energy+=c.heat;}
 energy+=Object.values(state.energyStores).reduce((a,b)=>a+b,0)+Object.values(state.thermalStores).reduce((a,b)=>a+b,0);
 const l=state.ledger;return {amount,energy,netEnergy:l.energyBoundaryIn+l.heatBoundaryIn-l.energyBoundaryOut-l.heatBoundaryOut-l.energyLoss,netAmount:l.resourceBoundaryIn-l.resourceBoundaryOut-l.resourceLeak};
}
function assertBalance(before,after){near(after.energy-before.energy,after.netEnergy-before.netEnergy);near(after.amount-before.amount,after.netAmount-before.netAmount);}
function assertBounds(model){
 const {model:definition,state}=model.exportSnapshot();
 for(const[id,circuits]of Object.entries(state.circuits))for(const[cid,c]of Object.entries(circuits)){
  const p=definition.components[id].circuits[cid].parameters;
  for(const[value,max,label]of [[c.amount,100*p.stockScale,'stock'],[c.heat,c.amount*p.thermalCapacity,'heat'],[c.pressure,100,'pressure'],...Object.entries(c.tracers).map(([k,v])=>[v,c.amount,k])])assert.ok(Number.isFinite(value)&&value>=-1e-8&&value<=max+1e-8,`${id}/${cid}/${label}=${value}, max=${max}`);
 }
 for(const[id,charge]of Object.entries(state.energyStores))assert.ok(Number.isFinite(charge)&&charge>=0&&charge<=definition.components[id].energy.store.capacity+1e-8);
 for(const[id,heat]of Object.entries(state.thermalStores))assert.ok(Number.isFinite(heat)&&heat>=0&&heat<=definition.components[id].thermalStore.capacity+1e-8);
}
function advance(model,minutes){for(let elapsed=0;elapsed<minutes;elapsed+=50){model.step(Math.min(50,minutes-elapsed));assertBounds(model);}}
function external(definition,id,port='secondary'){definition.components[id].energy={role:'source',inputs:[],outputs:[port],capacity:100,demand:0,efficiency:1,supply:{kind:'boundary'}};}

function reversibleFixture(){
 const f=fixture({upper:'reservoir',pump:'reversible-pump-turbine',lower:'reservoir'},[
  edge('down-in','upper','outlet','pump','upper'),edge('down-out','pump','lower','lower','inlet'),
  edge('up-in','lower','outlet','pump','lower'),edge('up-out','pump','upper','upper','inlet')]);
 f.definition.components.pump.initial.mode='pumping';
 for(const id of ['down-in','down-out'])f.definition.connections[id]={mode:{equipment:'pump',values:{generating:1,pumping:0,stopped:0}}};
 for(const id of ['up-in','up-out'])f.definition.connections[id]={mode:{equipment:'pump',values:{generating:0,pumping:1,stopped:0}}};
 return f;
}
function storageFixture(){
 const f=fixture({battery:'battery',inverter:'power-inverter',grid:'power-inverter'},[edge('dc','battery','dc','inverter','dc','electricity'),edge('ac','inverter','ac','grid','ac','electricity')]);
 Object.assign(f.definition.components.battery.energy,{capacity:10,efficiency:.9,store:{capacity:100,initial:50}});Object.assign(f.definition.components.inverter.energy,{capacity:10,efficiency:.9});
 f.definition.components.grid.energy={role:'boundary',inputs:['ac'],outputs:['ac'],capacity:10,demand:10,efficiency:1};
 for(const id of ['dc','ac'])f.definition.connections[id]={mode:{equipment:'inverter',values:{forward:1,reverse:-1,idle:0}}};return f;
}

test('reversible pumping cannot move material without shaft energy, including zero-rated and full stores',()=>{
 for(const patch of [{},{capacity:0},{store:{capacity:100,initial:100}}]){const f=reversibleFixture();Object.assign(f.definition.components.pump.energy,patch);const m=instantiate(f),before=totals(m),upper=m.getSnapshot().circuits.upper.water.amount;
  near(m.getSnapshot().readings.pump.powerIn,0);near(m.getSnapshot().flowRates['up-in'],0);near(m.getSnapshot().flowRates['up-out'],0);m.step(10);near(m.getSnapshot().circuits.upper.water.amount,upper);assertBalance(before,totals(m));}
});

test('operator stock additions and removals account for transported heat',()=>{
 const f=fixture({tank:'tank'});f.definition.components.tank.circuits.water.initial.temperature=80;const m=instantiate(f),before=totals(m);
 for(const level of [90,20,0,50]){m.dispatch({action:'setLevel',arguments:{equipment:'tank',circuit:'water',value:level}});assertBalance(before,totals(m));assertBounds(m);}
});

test('invalid finite step commands reject atomically without pausing the model',()=>{
 const m=instantiate(storageFixture()),before=m.exportSnapshot(),snapshot=m.getSnapshot();
 for(const minutes of [0,-1,61,NaN,Infinity]){assert.throws(()=>m.dispatch({action:'step',arguments:{minutes}}));assert.deepEqual(m.exportSnapshot(),before);assert.equal(m.getSnapshot(),snapshot);}
});

test('snapshot rejection checks candidate energy limits, state enums and complete event records atomically',()=>{
 const m=instantiate(storageFixture());m.step(1);const before=m.exportSnapshot(),snapshot=m.getSnapshot();
 const mutations=[s=>s.state.energyStores.battery=101,s=>s.model.components.battery.energy.store.capacity=.01,s=>s.state.components.inverter.mode='surprise',s=>s.state.components.inverter.phase='invented',s=>{s.state.nextEventId=2;s.state.events=[{id:1,minutes:0,type:{},equipment:'battery',severity:'bogus',message:null}]}];
 for(const mutate of mutations){const candidate=structuredClone(before);mutate(candidate);assert.throws(()=>m.importSnapshot(candidate));assert.deepEqual(m.exportSnapshot(),before);assert.equal(m.getSnapshot(),snapshot);}
});

test('reusing a snapshot signature does not authorize changed energy ports or circuit ownership',()=>{
 const m=instantiate(storageFixture()),before=m.exportSnapshot(),candidate=structuredClone(before);candidate.model.components.inverter.energy.inputs=['ac'];candidate.model.components.inverter.energy.outputs=['dc'];assert.throws(()=>m.importSnapshot(candidate));assert.deepEqual(m.exportSnapshot(),before);
 const exchanger=instantiate(fixture({hx:'heat-exchanger'})),saved=exchanger.exportSnapshot(),swapped=structuredClone(saved),c=swapped.model.components.hx.circuits;[c.hot.ports,c.cold.ports]=[c.cold.ports,c.hot.ports];assert.throws(()=>exchanger.importSnapshot(swapped));assert.deepEqual(exchanger.exportSnapshot(),saved);
});

test('depleted storage cannot black-start; reversing a real boundary charges only to its finite capacity',()=>{
 const m=instantiate(storageFixture()),before=totals(m);advance(m,2000);near(m.getSnapshot().energyStores.battery,0);Object.values(m.getSnapshot().flowRates).forEach(v=>near(v,0));
 m.dispatch({action:'setEnabled',arguments:{equipment:'grid',value:false}});m.dispatch({action:'setMode',arguments:{equipment:'battery',value:'charge'}});m.dispatch({action:'setMode',arguments:{equipment:'inverter',value:'reverse'}});m.step(10);near(m.getSnapshot().energyStores.battery,0);
 m.dispatch({action:'setEnabled',arguments:{equipment:'grid',value:true}});assert.ok(m.getSnapshot().flowRates.dc<0);assert.ok(m.getSnapshot().flowRates.ac<0);advance(m,2000);near(m.getSnapshot().energyStores.battery,100);Object.values(m.getSnapshot().flowRates).forEach(v=>near(v,0));assertBalance(before,totals(m));
});

function cycleFixture(withSource){
 const types={a:'transformer',b:'transformer',load:'transformer'};if(withSource)types.source='transformer';
 const edges=[edge('a-b','a','secondary','b','primary','electricity'),edge('b-a','b','secondary','a','primary','electricity'),edge('load','b','secondary','load','primary','electricity')];if(withSource)edges.push(edge('supply','source','secondary','a','primary','electricity'));
 const f=fixture(types,edges);for(const id of ['a','b'])Object.assign(f.definition.components[id].energy,{capacity:100,efficiency:1});f.definition.components.load.energy={role:'load',inputs:['primary'],outputs:[],capacity:20,demand:20,efficiency:1};if(withSource)external(f.definition,'source');return f;
}
test('lossless converter cycles never generate energy without a source over 2000 minutes',()=>{const m=instantiate(cycleFixture(false)),before=totals(m);advance(m,2000);Object.values(m.getSnapshot().flowRates).forEach(v=>near(v,0));assertBalance(before,totals(m));near(m.getSnapshot().ledger.energyLoss,0);});

test('a supplied lossless cycle does not classify solver truncation as conversion loss',()=>{const m=instantiate(cycleFixture(true));m.step(1);near(m.getSnapshot().ledger.energyLoss,0,1e-6);near(m.getSnapshot().readings.load.powerIn,20,1e-6);});

test('tiny-stock high-flow closed circuits preserve amounts and tracer/heat bounds over 2000 minutes',()=>{
 const f=fixture({tank:'tank',pump:'pump',source:'transformer'},[edge('forward','tank','outlet','pump','inlet'),edge('return','pump','outlet','tank','inlet'),edge('power','source','secondary','pump','drive','electricity')]);external(f.definition,'source');
 for(const[id,c]of Object.entries(f.definition.components))for(const w of Object.values(c.circuits)){w.parameters.capacity=100;w.parameters.stockScale=.01;w.parameters.thermalCapacity=id==='tank'?100:.01;w.initial.inventory=id==='tank'?99:.01;w.initial.temperature=100;w.initial.tracers={oxygen:id==='tank'?100:0,nutrient:0,solids:100,ph:100,ec:0};}
 const m=instantiate(f),before=totals(m);advance(m,2000);assertBalance(before,totals(m));
});

test('saturated receiving stock cannot overfill from multiple sources or exceed tracer bounds',()=>{
 const f=fixture({hot:'tank',cold:'tank',mix:'tank',sink:'tank'},[edge('hot','hot','outlet','mix','inlet'),edge('cold','cold','outlet','mix','inlet'),edge('out','mix','outlet','sink','inlet')]);
 for(const[id,c]of Object.entries(f.definition.components)){const w=c.circuits.water;w.parameters.capacity=100;w.initial.temperature=id==='hot'?100:0;w.initial.tracers={oxygen:id==='hot'?100:0,nutrient:id==='cold'?100:0,solids:100,ph:0,ec:100};if(['hot','cold'].includes(id))w.role='source';if(id==='sink')w.role='sink';if(id==='mix'){w.parameters.stockScale=.01;w.initial.inventory=99;}}
 const m=instantiate(f),before=totals(m);advance(m,2000);assertBalance(before,totals(m));near(m.getSnapshot().circuits.mix.water.amount,1);
});

test('electrical outages and lamp faults stop optical heating without resetting retained heat',()=>{
 const f=fixture({source:'transformer',lamp:'grow-light',receiver:'solar-receiver'},[edge('electric','source','secondary','lamp','supply','electricity'),edge('optical','lamp','light','receiver','optical','optical')]);external(f.definition,'source');
 const r=f.definition.components.receiver;r.energy.demand=10;r.thermalStore={capacity:100,initial:30,loss:0};r.heatSource={target:'body',capacity:10,control:'load',supply:{kind:'energy-input'}};
 const m=instantiate(f),before=totals(m);m.step(3);const warm=m.exportSnapshot().state.thermalStores.receiver;assert.ok(warm>30);
 m.dispatch({action:'setEnabled',arguments:{equipment:'source',value:false}});m.step(3);near(m.getSnapshot().flowRates.optical,0);near(m.exportSnapshot().state.thermalStores.receiver,warm);
 m.dispatch({action:'setEnabled',arguments:{equipment:'source',value:true}});m.dispatch({action:'setFault',arguments:{equipment:'lamp',value:getV2Descriptor('grow-light').visualFields.damage.options.find(v=>v!=='none')}});m.step(3);near(m.getSnapshot().flowRates.optical,0);near(m.exportSnapshot().state.thermalStores.receiver,warm);assertBalance(before,totals(m));
});

test('returning material to an external boundary produces a self-restorable snapshot',()=>{
 const f=fixture({tank:'tank',boundary:'tank'},[edge('return','tank','outlet','boundary','inlet')]);f.definition.components.boundary.circuits.water.role='source';const m=instantiate(f),before=totals(m);m.step(1);assertBalance(before,totals(m));const saved=m.exportSnapshot();assert.doesNotThrow(()=>m.importSnapshot(saved));assert.deepEqual(m.exportSnapshot(),saved);
});
