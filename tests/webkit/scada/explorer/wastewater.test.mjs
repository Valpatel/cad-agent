import test from 'node:test';
import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import {PlaceholderSystemModel,createPlaceholderAdapter} from '../../../../software/cadagent/webkit/scada/sim/src/index.mjs';
import {validateSystemDefinition} from '../../../../software/cadagent/webkit/scada/ui/src/contracts/system-definition.mjs';
const source=new URL('../../../../software/cadagent/webkit/scada/sim/scenarios/wastewater-digester/',import.meta.url);
const system=JSON.parse(await readFile(new URL('system.json',source),'utf8'));
const definition=JSON.parse(await readFile(new URL('model.json',source),'utf8'));
const make=()=>new PlaceholderSystemModel(system,definition);
const command=(model,action,equipment,value)=>model.dispatch({action,arguments:{equipment,...(value===undefined?{}:{value})}});

test('wastewater views and controls resolve against one explicitly assumed system',()=>{
 assert.equal(validateSystemDefinition(system).ok,true);
 assert.deepEqual(system.views.map(v=>v.id),['overview','treatment','sludge-energy','power-control']);
 const ids=new Set(system.components.map(c=>c.id));
 for(const id of ids)assert.ok(system.views.some(v=>v.placements.some(p=>p.component===id)),`${id} needs a view`);
 assert.equal(definition.scenarioId,system.system.id);
 assert.ok(definition.assumptions.some(a=>/normalized/.test(a)));
 const power=system.views.find(v=>v.id==='sludge-energy');
 assert.ok(power.placements.find(p=>p.component==='loads').x>power.placements.find(p=>p.component==='chp').x);
});
test('lift-pump stop removes its connected flow and repair preserves deliberate controls',()=>{
 const model=make();model.step(2);assert.equal(model.getSnapshot().flows['liftPump-to-inletValve'],true);
 command(model,'setEnabled','liftPump',false);model.step(1);
 assert.equal(model.getSnapshot().flows['liftPump-to-inletValve'],false);assert.equal(model.getSnapshot().readings.liftPump.resourceOut,0);
 command(model,'setFault','liftPump',true);command(model,'repair','liftPump');
 assert.equal(model.getSnapshot().controls.liftPump.enabled,false);
 command(model,'setEnabled','liftPump',true);model.step(2);assert.equal(model.getSnapshot().flows['liftPump-to-inletValve'],true);model.destroy();
});
test('generator fault removes electrical supply while the separate flare stays available',()=>{
 const model=make();model.step(2);assert.ok(model.getSnapshot().readings.loads.powerIn>0);
 command(model,'setFault','chp',true);model.step(1);const state=model.getSnapshot();
 assert.equal(state.readings.loads.powerIn,0);assert.equal(state.components.chp.fault,true);
 assert.equal(state.components.flare.fault,false);assert.ok(state.readings.flare.resourceIn>0);
 command(model,'repair','chp');model.step(1);assert.ok(model.getSnapshot().readings.loads.powerIn>0);model.destroy();
});
test('a closed sludge valve cuts shared digester feed and a leak is retained until repair',()=>{
 const model=make();model.step(2);command(model,'setOpen','sludgeValve',false);model.step(1);
 assert.equal(model.getSnapshot().flows['sludgeValve-to-digester'],false);assert.equal(model.getSnapshot().readings.sludgeValve.resourceOut,0);
 command(model,'setFault','digester','leaking');model.step(1);
 assert.equal(model.getSnapshot().components.digester.damage,'leaking');
 command(model,'repair','digester');assert.equal(model.getSnapshot().components.digester.damage,'none');
 assert.equal(model.getSnapshot().controls.sludgeValve.open,false);model.destroy();
});
test('read-only observer shares each update without owning a second clock or write method',()=>{
 const model=make(),control=createPlaceholderAdapter(model),observer=createPlaceholderAdapter(model,{readOnly:true});
 assert.equal('dispatch' in observer,false);let seen;
 const unsubscribe=observer.subscribe(snapshot=>{seen=snapshot;});
 control.dispatch({action:'step',arguments:{minutes:1}});
 assert.equal(observer.getSnapshot().minutes,1);assert.equal(seen.minutes,1);
 assert.deepEqual(observer.getSnapshot(),control.getSnapshot());
 unsubscribe();control.dispatch({action:'step',arguments:{minutes:1}});assert.equal(model.getSnapshot().minutes,2);model.destroy();
});
test('overload experiment and compatible snapshot replay remain deterministic',()=>{
 const model=make();model.dispatch({action:'setParameter',arguments:{equipment:'loads',key:'demand',value:95}});command(model,'setLoad','loads',100);model.step(3);
 assert.ok(model.getSnapshot().readings.loads.powerFactor<1);
 const saved=model.exportSnapshot(),copy=make();copy.importSnapshot(saved);
 model.step(4);copy.step(4);assert.deepEqual(copy.exportSnapshot(),model.exportSnapshot());
 model.destroy();copy.destroy();
});
