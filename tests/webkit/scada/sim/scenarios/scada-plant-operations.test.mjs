import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {PlaceholderSystemModel,validatePlaceholderModelDefinition,createPlaceholderAdapter,getModelDescriptor} from '../../../../../software/cadagent/webkit/scada/sim/src/index.mjs';
import {validateSystemDefinition} from '../../../../../software/cadagent/webkit/scada/ui/src/contracts/system-definition.mjs';
const directory=new URL('../../../../../software/cadagent/webkit/scada/sim/scenarios/',import.meta.url);
const read=path=>JSON.parse(readFileSync(new URL(path,directory)));
const catalog=read('index.json');
const scenarios=['wastewater-digester','winery','brewery'].map(id=>({id,entry:catalog.scenarios.find(e=>e.id===id),system:read(`${id}/system.json`),definition:read(`${id}/model.json`)}));
const command=(model,action,equipment,value)=>model.dispatch({action,arguments:{equipment,...(value===undefined?{}:{value})}});
function anchor(system,view,endpoint){const box=view.placements.find(p=>p.component===endpoint.component),port=system.components.find(c=>c.id===endpoint.component).ports.find(p=>p.id===endpoint.port),offset=port.offset??.5;
 return {left:{x:box.x,y:box.y+box.height*offset},right:{x:box.x+box.width,y:box.y+box.height*offset},top:{x:box.x+box.width*offset,y:box.y},bottom:{x:box.x+box.width*offset,y:box.y+box.height}}[port.side];}
for(const {id,entry,system,definition} of scenarios){
 test(`${id}: overview, instrument taps and control wires describe the actual shared model`,()=>{
  assert.equal(validateSystemDefinition(system).ok,true);assert.equal(validatePlaceholderModelDefinition(system,definition).ok,true);
  assert.equal(system.views[0].placements.length,system.components.length,'Overview includes every plant asset');
  assert.deepEqual(new Set(system.views.flatMap(v=>v.routes.map(r=>r.connection))),new Set(system.connections.map(e=>e.id)),'No hidden modeled connection');
  const edges=new Map(system.connections.map(e=>[e.id,e]));
  for(const view of system.views)for(const route of view.routes){const edge=edges.get(route.connection);assert.deepEqual(route.points[0],anchor(system,view,edge.from));assert.deepEqual(route.points.at(-1),anchor(system,view,edge.to));}
  const sensors=system.components.filter(c=>getModelDescriptor(c.type).family==='sensor');assert.ok(sensors.length>=4);
  assert.deepEqual(new Set(entry.measurements.map(m=>m.sensor)),new Set(sensors.map(c=>c.id)));
  for(const sensor of sensors){assert.equal(system.connections.filter(e=>e.medium==='measurement'&&e.to.component===sensor.id).length,1);assert.ok(system.connections.some(e=>e.medium==='data'&&e.from.component===sensor.id&&e.to.component==='controller'));assert.ok(system.connections.some(e=>e.medium==='electricity'&&e.to.component===sensor.id));}
  const valves=system.components.filter(c=>c.type==='control-valve');assert.equal(valves.length,3);
  for(const valve of valves){assert.ok(system.connections.some(e=>e.from.component==='remoteIO'&&e.to.component===valve.id&&e.to.port==='control'));assert.ok(system.controls.some(c=>c.component===valve.id&&c.diagram?.whenTrue==='Close'&&c.diagram.whenFalse==='Open'));}
  assert.ok(definition.assumptions.some(a=>/not a safety PLC/.test(a)));assert.ok(definition.assumptions.some(a=>/not misrepresented as PLC data/.test(a)));
 });
 test(`${id}: healthy plant stays productive and avoids latent damage through 300 model minutes`,()=>{
  const model=new PlaceholderSystemModel(system,definition);
  try{for(const dt of [0,10,50,60,60,60,60]){if(dt)model.step(dt);const s=model.getSnapshot();
   for(const c of system.components){assert.equal(s.components[c.id].status,'normal',`${c.id} at ${s.minutes}`);assert.equal(s.readings[c.id].damage,0,`${c.id} damage at ${s.minutes}`);}
   for(const [equipment,c]of Object.entries(definition.components))if(c.kind==='sink')assert.ok(s.readings[equipment].resourceIn>0,`${equipment} productive at ${s.minutes}`);
  }assert.equal(model.clockStarted,false);}finally{model.destroy();}
 });
 test(`${id}: valves isolate physical branches and PLC loss gates actual field commands`,()=>{
  const model=new PlaceholderSystemModel(system,definition),actuated=system.components.filter(c=>c.type==='control-valve').map(c=>c.id);
  try{model.step(5);for(const valve of actuated){assert.ok(model.getSnapshot().readings[valve].resourceOut>0,valve);command(model,'setOpen',valve,false);assert.equal(model.getSnapshot().readings[valve].resourceOut,0,valve);command(model,'setOpen',valve,true);}
   const local=structuredClone(model.getSnapshot().controls);
   command(model,'setEnabled','controller',false);const unavailable=model.getSnapshot();assert.equal(unavailable.readings.remoteIO.connected,false);
   for(const valve of actuated){assert.equal(unavailable.readings[valve].resourceOut,0,valve);assert.equal(unavailable.controls[valve].open,true,'Communication loss does not fabricate local valve movement');}
   for(const c of system.components.filter(c=>['pump','submersible-pump','generator'].includes(c.type)))assert.equal(unavailable.controls[c.id].enabled,local[c.id].enabled);
   command(model,'setEnabled','controller',true);model.step(8);for(const valve of actuated)assert.ok(model.getSnapshot().readings[valve].resourceOut>0,valve+' resumes');
  }finally{model.destroy();}
 });
 test(`${id}: instruments follow source readings and saved runs continue one deterministic session`,()=>{
  const model=new PlaceholderSystemModel(system,definition),copy=new PlaceholderSystemModel(system,definition);
  try{for(let n=0;n<5;n++)model.step(60);const s=model.getSnapshot(),keys={'flow-meter':'flow','pressure-transmitter':'pressure','temperature-sensor':'temperature','level-sensor':'stock','gas-analyzer':'quality'};
   for(const {sensor,asset}of entry.measurements){const type=system.components.find(c=>c.id===sensor).type;assert.ok(Math.abs(s.readings[sensor].signal-s.readings[asset][keys[type]])<2,`${sensor} tracks ${asset}`);}
   const valve=system.components.find(c=>c.type==='control-valve').id;command(model,'setLoad',valve,35);model.step(2);
   const saved=model.exportSnapshot();copy.importSnapshot(JSON.parse(JSON.stringify(saved)));model.step(5);copy.step(5);assert.deepEqual(copy.exportSnapshot(),model.exportSnapshot());
   const observer=createPlaceholderAdapter(copy,{readOnly:true});assert.equal(observer.dispatch,undefined);assert.equal(observer.getSnapshot(),copy.getSnapshot());assert.equal(copy.clockStarted,false);
  }finally{model.destroy();copy.destroy();}
 });
}
test('inlet valve closure removes measured pump flow and increases its backpressure response',()=>{
 const {system,definition}=scenarios[0],model=new PlaceholderSystemModel(system,definition);
 try{model.step(10);const before=model.getSnapshot();assert.ok(before.readings.inletFlow.signal>0);command(model,'setOpen','inletValve',false);model.step(6);const after=model.getSnapshot();assert.equal(after.readings.liftPump.resourceOut,0);assert.ok(after.readings.inletFlow.signal<before.readings.inletFlow.signal*.1);assert.ok(after.readings.liftPump.pressure>before.readings.liftPump.pressure);}finally{model.destroy();}
});
test('previous winery topology snapshots reject atomically instead of inventing equipment migrations',()=>{
 const fixture=new URL('../../../../fixtures/scada/default-model-inputs/',import.meta.url),originalSystem=JSON.parse(readFileSync(new URL('winery.system.json',fixture))),originalDefinition=JSON.parse(readFileSync(new URL('winery.model.json',fixture))),old=new PlaceholderSystemModel(originalSystem,originalDefinition),current=scenarios.find(s=>s.id==='winery'),model=new PlaceholderSystemModel(current.system,current.definition);
 try{old.step(2);model.step(1);const before=model.exportSnapshot();assert.throws(()=>model.importSnapshot(old.exportSnapshot()),/different scenario or topology/i);assert.deepEqual(model.exportSnapshot(),before);assert.equal(model.clockStarted,false);}finally{old.destroy();model.destroy();}
});
