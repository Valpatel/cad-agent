import {SIM, FIXTURES} from '../paths.mjs';
import {readFile, readdir} from 'node:fs/promises';
import {resolve, join, relative} from 'node:path';
import {fileURLToPath, pathToFileURL} from 'node:url';
import {createHash} from 'node:crypto';
import assert from 'node:assert/strict';

// Read-only frozen compatibility oracle. There is intentionally no capture,
// update or write mode: expected hashes came from the original full snapshots.
if(process.argv.length>2){
 if(process.argv.length===3&&process.argv[2]==='--help'){
  process.stdout.write('Check all 60 original scenarios and 1,440 frozen checkpoints. No files are written.\n');
  process.exit(0);
 }
 throw new TypeError('This read-only checker accepts no arguments other than --help.');
}
const pkg=SIM;
const expectedPath=join(FIXTURES,'default-baseline.json');
const {PlaceholderSystemModel}=await import(pathToFileURL(join(pkg,'src/index.mjs')));
const canonical=value=>Array.isArray(value)?value.map(canonical):value&&typeof value==='object'?Object.fromEntries(Object.keys(value).sort().map(key=>[key,canonical(value[key])])):value;
const bytes=value=>Buffer.from(JSON.stringify(canonical(value))+'\n');
const hash=value=>createHash('sha256').update(value).digest('hex');
const readJson=async path=>JSON.parse(await readFile(path,'utf8'));
const sourcePaths=[];
async function walk(folder){for(const entry of await readdir(folder,{withFileTypes:true})){const path=join(folder,entry.name);if(entry.isDirectory())await walk(path);else if(/\.(mjs|json)$/.test(entry.name))sourcePaths.push(path);}}
for(const folder of ['src','schema','scenarios'])await walk(join(pkg,folder));
const sourceHashes=Object.fromEntries(await Promise.all(sourcePaths.sort().map(async p=>[relative(pkg,p),hash(await readFile(p))])));
const catalog=await readJson(join(pkg,'scenarios/index.json'));
const oracle=await readJson(expectedPath);
assert.equal(oracle.format,'scada-default-model-digests');assert.equal(oracle.version,1);
assert.equal(oracle.scenarios,60);assert.equal(oracle.checkpoints,1440);
const expectedRecords=new Map(oracle.records.map(record=>[record.id,record]));
assert.equal(expectedRecords.size,oracle.records.length,'Baseline scenario IDs must be unique');
const originalScenarios=catalog.scenarios.filter(entry=>expectedRecords.has(entry.id));
assert.deepEqual(originalScenarios.map(entry=>entry.id).sort(),[...expectedRecords.keys()].sort(),'An original scenario was removed from the frozen baseline');
const additions=catalog.scenarios.filter(entry=>!expectedRecords.has(entry.id)).map(entry=>entry.id);
assert.ok(additions.every(id=>id==='wastewater-digester'),'Review new scenarios explicitly; separate fixtures cover additions');
const frozenInputs=await readJson(join(FIXTURES,'default-model-inputs/index.json'));
assert.equal(frozenInputs.format,'scada-default-model-inputs');assert.equal(frozenInputs.version,1);
const frozenEntries=new Map(frozenInputs.scenarios.map(entry=>[entry.id,entry]));
assert.deepEqual([...frozenEntries.keys()].sort(),['brewery','winery'],'Only explicitly evolved examples use retained oracle inputs');
const results=[],failures=[];

for(const liveEntry of originalScenarios){
 const entry=frozenEntries.get(liveEntry.id)??liveEntry;
 const inputRoot=frozenEntries.has(entry.id)?join(FIXTURES,'default-model-inputs'):join(pkg,'scenarios');
 const system=await readJson(join(inputRoot,entry.system));
 const definition=await readJson(join(inputRoot,entry.model));
 const record={scenario:entry.id,version:definition.version,seed:definition.seed,system,definition,branches:{}};
 const create=(modelDefinition=definition)=>new PlaceholderSystemModel(system,modelDefinition,{clock:{setInterval(){throw Error('Baseline must not start a clock');},clearInterval(){}}});
 const capture=(model,label,list)=>{
   assert.equal(model.clockStarted,false);
   const saved=model.exportSnapshot(),visible=model.getSnapshot();
   list.push({label,saved,visible});
   return saved;
 };
 const dispatch=(model,action,args)=>model.dispatch({action,arguments:args});
 // Original unmodified scenario configuration, fractional then long horizons.
 let model=create();const nominal=record.branches.nominal=[];
 try{
  capture(model,'initial',nominal);
  for(const [label,steps]of [['quarter',[.25]],['minute-1',[.75]],['minute-10',[9]],['minute-60',[50]],['minute-300',[60,60,60,60]]]){
   for(const dt of steps)model.step(dt);capture(model,label,nominal);
  }
 }finally{model.destroy();}
 // A real catalog fault command, followed by elapsed damage and repair.
 const fault=entry.experiments.flatMap(exp=>exp.commands).find(cmd=>['setFault','setDamage'].includes(cmd.action));
 assert.ok(fault,`${entry.id}: needs an authored fault`);
 model=create();const failure=record.branches.faultRepair=[];record.faultCommand=fault;
 try{
  model.dispatch(fault);capture(model,'injected',failure);
  model.step(1.25);capture(model,'fault-step-1.25',failure);
  dispatch(model,'repair',{equipment:fault.arguments.equipment});capture(model,'repaired',failure);
  model.step(2.75);capture(model,'repaired-step-4',failure);
 }finally{model.destroy();}
 // First authored recipe is a concrete additional command path, not an override.
 const experiment=entry.experiments[0];record.firstExperiment=experiment;
 model=create();const commands=record.branches.authoredCommand=[];
 try{
  for(const command of experiment.commands)model.dispatch(command);
  capture(model,'commands',commands);
  model.step(.5);model.step(1.5);capture(model,'commands-step-2',commands);
 }finally{model.destroy();}
 // Standard public parameter edits force PRNG-sensitive conditions in every
 // scenario. No injected equations, registered model or alternate provider.
 for(const alternate of [false,true]){
  const modelDefinition=structuredClone(definition);
  if(alternate)modelDefinition.seed=((definition.seed^0x9e3779b9)>>>0)||1;
  const branch=record.branches[alternate?'alternateSeed':'seededReplay']=[];
  model=create(modelDefinition);let restored;
  try{
   for(const id of Object.keys(modelDefinition.components).sort()){
    dispatch(model,'setParameter',{equipment:id,key:'warningAt',value:0});
    dispatch(model,'setParameter',{equipment:id,key:'damageRate',value:1});
   }
   capture(model,'stress-commands',branch);
   model.step(.25);model.step(.75);model.step(1.5);
   const saved=capture(model,'stress-step-2.5',branch);
   assert.notEqual(saved.state.randomState,modelDefinition.seed,`${entry.id}: stress must exercise seeded randomness`);
   restored=create(modelDefinition);restored.importSnapshot(structuredClone(saved));
   assert.deepEqual(restored.exportSnapshot(),saved,`${entry.id}: exact saved-state round trip`);
   assert.deepEqual(restored.getSnapshot(),model.getSnapshot(),`${entry.id}: restored visible state`);
   capture(restored,'imported',branch);
   for(const dt of [.5,2]){model.step(dt);restored.step(dt);assert.deepEqual(restored.exportSnapshot(),model.exportSnapshot(),`${entry.id}: deterministic continuation`);assert.deepEqual(restored.getSnapshot(),model.getSnapshot());}
   capture(model,'continued-step-5',branch);
   dispatch(model,'setRunning',{value:false});capture(model,'paused',branch);
   dispatch(model,'step',{minutes:.5});capture(model,'explicit-step-5.5',branch);
  }finally{model.destroy();restored?.destroy();}
 }
 assert.notEqual(hash(bytes(record.branches.seededReplay)),hash(bytes(record.branches.alternateSeed)));
 const data=bytes(record),sha256=hash(data),expected=expectedRecords.get(entry.id);
 const checkpointHashes=Object.fromEntries(Object.entries(record.branches).flatMap(([branch,list])=>list.map(item=>[`${branch}/${item.label}`,hash(bytes(item))])));
 const changes=[...new Set([...Object.keys(expected.checkpointHashes),...Object.keys(checkpointHashes)])].filter(label=>expected.checkpointHashes[label]!==checkpointHashes[label]);
 if(sha256!==expected.sha256||changes.length){
  failures.push({scenario:entry.id,checkpoints:changes,recordMetadataOnly:changes.length===0});
  process.stderr.write(`${entry.id}: ${changes.length?changes.join(', '):'scenario definition or authored recipe metadata changed'}\n`);
 }
 results.push({id:entry.id,checkpointHashes});
 process.stdout.write(`Compared ${entry.id}: ${Object.keys(checkpointHashes).length} checkpoints\n`);
}
const finalSourceHashes=Object.fromEntries(await Promise.all(sourcePaths.sort().map(async p=>[relative(pkg,p),hash(await readFile(p))])));
assert.deepEqual(finalSourceHashes,sourceHashes,'Source changed during baseline capture');
const checkpoints=results.reduce((n,r)=>n+Object.keys(r.checkpointHashes).length,0);
assert.equal(checkpoints,oracle.checkpoints,'Frozen checkpoint coverage changed');
process.stdout.write(JSON.stringify({scenarios:results.length,checkpoints,failures:failures.length,baselineManifestSha256:oracle.provenance.captureManifestSha256})+'\n');
if(failures.length)process.exitCode=1;
