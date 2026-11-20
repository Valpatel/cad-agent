import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {CircuitSystemModel} from '../../../../software/cadagent/webkit/scada/sim/src/v2/circuit-system.mjs';
import {createV2Component} from '../../../../software/cadagent/webkit/scada/sim/src/v2/contract.mjs';
import {getModelDescriptor, MODEL_DESCRIPTORS} from '../../../../software/cadagent/webkit/scada/sim/src/index.mjs';

const system=JSON.parse(readFileSync(new URL('../../../../software/cadagent/webkit/scada/sim/scenarios/electric-batch-oven/system.json',import.meta.url)));
const definition=JSON.parse(readFileSync(new URL('../../../../software/cadagent/webkit/scada/sim/scenarios/electric-batch-oven/model.json',import.meta.url)));
const command=(model,action,equipment,value)=>model.dispatch({action,arguments:{equipment,...(value===undefined?{}:{value})}});
const heat=snapshot=>Object.values(snapshot.state.thermalStores).reduce((sum,value)=>sum+value,0)+Object.values(snapshot.state.circuits).flatMap(Object.values).reduce((sum,circuit)=>sum+circuit.heat,0);
const netEnergy=snapshot=>{const l=snapshot.ledger;return l.energyBoundaryIn+l.heatBoundaryIn-l.energyBoundaryOut-l.heatBoundaryOut-l.energyLoss;};
const near=(a,b)=>assert.ok(Math.abs(a-b)<1e-7,`${a} != ${b}`);

test('rack oven is an explicit v2 electric heater without changing the eighty-type v1 registry',()=>{
  assert.equal(MODEL_DESCRIPTORS.length,80);
  assert.throws(()=>getModelDescriptor('rack-oven'),/No.*model|Unknown|Unsupported/i);
  const descriptor=getModelDescriptor('rack-oven',{version:2});
  const component=createV2Component('rack-oven');
  assert.deepEqual(component.heatSource.supply,{kind:'energy-input'});
  assert.equal(component.initial.open,false);
  assert.equal(descriptor.visualFields.temperature.unit,'index');
  assert.ok(descriptor.assumptions.some(text=>/No door interlock/.test(text)));
  const isolated=new CircuitSystemModel({system:{id:'isolated'},components:[{id:'oven',type:'rack-oven'}],connections:[]},{...definition,scenarioId:'isolated',components:{oven:component}});
  try{const before=isolated.getSnapshot().readings.oven.temperature;isolated.step(10);assert.equal(isolated.getSnapshot().readings.oven.powerIn,0);assert.ok(isolated.getSnapshot().readings.oven.temperature<before);}finally{isolated.destroy();}
});

test('electric input becomes retained heat, isolation stops heating, and every step accounts for energy',()=>{
  const model=new CircuitSystemModel(system,definition),initial=heat(model.exportSnapshot());
  try{
    const first=model.getSnapshot().readings.oven.temperature;
    model.step(5);
    const warmed=model.getSnapshot().readings.oven.temperature;
    assert.ok(warmed>first);assert.ok(model.getSnapshot().readings.oven.powerIn>0);
    near(heat(model.exportSnapshot())-initial,netEnergy(model.getSnapshot()));
    command(model,'setOpen','breaker',true);
    assert.equal(model.getSnapshot().readings.oven.powerIn,0);
    assert.equal(model.getSnapshot().readings.oven.temperature,warmed);
    model.step(5);assert.ok(model.getSnapshot().readings.oven.temperature<warmed);assert.ok(model.getSnapshot().readings.oven.temperature>0);
    near(heat(model.exportSnapshot())-initial,netEnergy(model.getSnapshot()));
    command(model,'setOpen','breaker',false);command(model,'setEnabled','oven',false);
    assert.equal(model.getSnapshot().readings.oven.powerIn,0);
    command(model,'setEnabled','oven',true);assert.ok(model.getSnapshot().readings.oven.powerIn>0);
  }finally{model.destroy();}
});

test('rack door, localized damage, repair, reset and snapshot restore share one state',()=>{
  const model=new CircuitSystemModel(system,definition);
  try{
    model.step(3);const heatBeforeDoor=model.getSnapshot().readings.oven.temperature;
    command(model,'setOpen','oven',true);assert.equal(model.getSnapshot().components.oven.open,true);
    assert.equal(model.getSnapshot().readings.oven.temperature,heatBeforeDoor,'door changes presentation without inventing a heat impulse');
    for(const condition of ['overheated','element-fault','door-seal-leak']){
      command(model,'setFault','oven',condition);assert.equal(model.getSnapshot().components.oven.damage,condition);
      command(model,'repair','oven');assert.equal(model.getSnapshot().components.oven.damage,'none');
    }
    command(model,'setDamage','oven',100);assert.equal(model.getSnapshot().components.oven.active,false);assert.equal(model.getSnapshot().readings.oven.powerIn,0);
    assert.equal(model.getSnapshot().readings.oven.temperature,heatBeforeDoor);
    command(model,'repair','oven');assert.ok(model.getSnapshot().readings.oven.powerIn>0);
    const saved=model.exportSnapshot(),restored=new CircuitSystemModel(system,definition);
    try{restored.importSnapshot(saved);model.step(2);restored.step(2);assert.deepEqual(restored.getSnapshot(),model.getSnapshot());}finally{restored.destroy();}
    model.dispatch({action:'setParameter',arguments:{equipment:'oven',key:'damageRate',value:.2}});
    model.reset();assert.equal(model.getSnapshot().parameters.oven.damageRate,.2);assert.equal(model.getSnapshot().components.oven.open,false);assert.equal(model.getSnapshot().readings.oven.temperature,definition.components.oven.thermalStore.initial);
  }finally{model.destroy();}
});
