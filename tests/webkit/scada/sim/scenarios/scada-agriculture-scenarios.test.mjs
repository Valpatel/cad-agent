import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {PlaceholderSystemModel,createPlaceholderAdapter,validatePlaceholderModelDefinition,getModelDescriptor} from '../../../../../software/cadagent/webkit/scada/sim/src/index.mjs';
import {validateSystemDefinition} from '../../../../../software/cadagent/webkit/scada/ui/src/contracts/system-definition.mjs';

const ids=['aquaponics-media-bed','aquaponics-dwc','hydroponics-nft','hydroponics-ebb-flow','greenhouse-drip','indoor-aeroponics'];
const read=path=>JSON.parse(readFileSync(new URL(path,import.meta.url)));
const fixture=id=>{const system=read(`../../../../../software/cadagent/webkit/scada/sim/scenarios/${id}/system.json`),definition=read(`../../../../../software/cadagent/webkit/scada/sim/scenarios/${id}/model.json`);return {system,definition,model:new PlaceholderSystemModel(system,definition)};};
const near=(a,b)=>assert.ok(Math.abs(a-b)<1e-6,`${a} differs from ${b}`);
const amount=snapshot=>Object.values(snapshot.state.circuits).flatMap(Object.values).reduce((sum,circuit)=>sum+circuit.amount,0);
const step=(model,minutes)=>{for(let i=0;i<minutes;i++)model.step(1);};
const command=(model,action,args)=>model.dispatch({action,arguments:args});

for(const id of ids)test(`${id}: canonical public runtime conserves declared stocks and restores all shared state`,()=>{
 const {system,definition,model}=fixture(id);
 assert.equal(validateSystemDefinition(system).ok,true);
 assert.equal(validatePlaceholderModelDefinition(system,definition).ok,true);
 assert.equal(system.views.length,3);
 const initial=model.exportSnapshot();step(model,300);const saved=model.exportSnapshot(),snapshot=model.getSnapshot(),ledger=snapshot.ledger;
 near(amount(saved)-amount(initial),ledger.resourceBoundaryIn-ledger.resourceBoundaryOut-ledger.resourceLeak);
 assert.equal(snapshot.minutes,300);
 assert.ok(Object.values(snapshot.components).every(component=>!component.fault&&component.status==='normal'));
 assert.ok(Object.values(saved.state.components).every(component=>component.damage===0),'Nominal operation must not accumulate hidden damage.');
 const readonly=createPlaceholderAdapter(model,{readOnly:true});assert.equal(readonly.getSnapshot(),snapshot);assert.equal(readonly.dispatch,undefined);
 for(const component of system.components){const descriptor=getModelDescriptor(component.type,{version:2,variant:component.variant});if(!descriptor.parameters.length)continue;const p=descriptor.parameters[0],current=model.getSnapshot().parameters[component.id][p.key],value=current===p.min?p.max:p.min;command(model,'setParameter',{equipment:component.id,key:p.key,value});assert.equal(model.getSnapshot().parameters[component.id][p.key],value);}
 model.importSnapshot(saved);assert.deepEqual(model.exportSnapshot(),saved);step(model,17);const expected=model.exportSnapshot();model.importSnapshot(saved);step(model,17);assert.deepEqual(model.exportSnapshot(),expected);
 model.destroy();
});

test('NFT branch isolation preserves the other branch and separates pH, EC and oxygen identities',()=>{
 const {model}=fixture('hydroponics-nft');step(model,20);
 assert.ok(model.getSnapshot().flowRates['valveA-outlet-to-channelA-inlet']>0);
 command(model,'setOpen',{equipment:'valveA',value:false});step(model,2);
 near(model.getSnapshot().flowRates['valveA-outlet-to-channelA-inlet'],0);
 assert.ok(model.getSnapshot().flowRates['valveB-outlet-to-channelB-inlet']>0);
 for(const [id,quantity] of [['phProbe','ph'],['ecProbe','ec'],['doProbe','oxygen']])assert.equal(model.exportModelDefinition().components[id].observation.quantity,quantity);
 command(model,'setMeasurement',{equipment:'ecProbe',value:'do'});
 assert.equal(model.exportModelDefinition().components.ecProbe.observation.quantity,'oxygen');assert.equal(model.getSnapshot().components.ecProbe.measurement,'do');
 model.destroy();
});

test('aquaponics air interruption does not add or remove fish water inventory',()=>{
 const {model}=fixture('aquaponics-media-bed');step(model,20);const saved=model.exportSnapshot();
 const waterAmount=()=>Object.entries(model.getSnapshot().circuits).flatMap(([,circuits])=>Object.values(circuits)).filter(circuit=>circuit.fluid==='water').reduce((sum,circuit)=>sum+circuit.amount,0);
 const water=waterAmount();command(model,'setEnabled',{equipment:'airSupply',value:false});step(model,20);near(waterAmount(),water);
 const interrupted=model.getSnapshot().circuits.fish.water.oxygen;model.importSnapshot(saved);step(model,20);assert.ok(model.getSnapshot().circuits.fish.water.oxygen>interrupted);
 model.destroy();
});

test('nursery phase, room state, circuit composition and edited assumptions restore exactly',()=>{
 const {model}=fixture('hydroponics-ebb-flow');
 command(model,'setParameter',{equipment:'tableA',key:'cycleHold',value:8});
 command(model,'setCircuitParameter',{equipment:'tableA',circuit:'water',key:'capacity',value:35});
 command(model,'setTracer',{equipment:'tableA',circuit:'water',key:'nutrient',value:23});
 command(model,'setZoneValue',{zone:'growRoom',key:'humidity',value:72});
 command(model,'setEnvironment',{key:'light',value:22});
 step(model,9);const saved=model.exportSnapshot();step(model,20);const expected=model.exportSnapshot();model.importSnapshot(saved);assert.deepEqual(model.exportSnapshot(),saved);step(model,20);assert.deepEqual(model.exportSnapshot(),expected);
 model.destroy();
});

test('an open indoor light breaker leaves its sibling supplied and closing restores it',()=>{
 const {model}=fixture('indoor-aeroponics');step(model,3);
 command(model,'setOpen',{equipment:'breakerA',value:true});
 near(model.getSnapshot().readings.lightA.powerIn,0);assert.ok(model.getSnapshot().readings.lightB.powerIn>0);
 command(model,'setOpen',{equipment:'breakerA',value:false});assert.ok(model.getSnapshot().readings.lightA.powerIn>0);
 model.destroy();
});
