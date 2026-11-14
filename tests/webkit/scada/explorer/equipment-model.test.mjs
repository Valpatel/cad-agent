import test from 'node:test';
import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import {equipmentModelReport,renderEquipmentModel} from '../../../../software/cadagent/webkit/scada/explorer/equipment-model.mjs';
import {createPumpBench} from '../../../../software/cadagent/webkit/scada/sim/examples/equation-models/pump-bench.mjs';
import {pumpEquationProviders,solveQuadraticPump,solveLinearPump} from '../../../../software/cadagent/webkit/scada/sim/src/equation-examples/index.mjs';
import {PlaceholderSystemModel,COMPONENT_MODEL_CLASSES,CircuitSystemModel} from '../../../../software/cadagent/webkit/scada/sim/src/index.mjs';

const report = ({system,model},id='pump') => equipmentModelReport({system,id,definition:model.exportModelDefinition(),equationState:model.exportSnapshot().equationState,providers:pumpEquationProviders});

for (const version of [1,2]) test(`engine ${version}: displayed law follows actual provider replacement and current accepted parameters`,()=>{
  const fixture=createPumpBench({version,parameters:{shutoffHeadM:37}}),before=fixture.model.exportSnapshot();
  const quadratic=report(fixture);
  assert.equal(quadratic.provider.id,'engineering.pump.quadratic');
  assert.equal(quadratic.provider.version,'1.0.0');
  assert.equal(quadratic.provider.units,'scada-index-v1');
  assert.equal(quadratic.parameters.shutoffHeadM,37);
  assert.equal(quadratic.parameterUnits.shutoffHeadM,'m');
  assert.equal(quadratic.sources[0].source,solveQuadraticPump.toString());
  assert.equal(quadratic.sources.find(item=>item.label==='Active provider evaluation').source,pumpEquationProviders[0].evaluate.toString());
  assert.deepEqual(fixture.model.exportSnapshot(),before,'inspection must not change the model');
  fixture.model.setEquationBindings({version:1,components:{pump:{id:'engineering.pump.linear',version:'1.0.0',parameters:{shutoffHeadM:29}}}});
  const linear=report(fixture);
  assert.equal(linear.provider.id,'engineering.pump.linear');
  assert.equal(linear.parameters.shutoffHeadM,29);
  assert.equal(linear.sources[0].source,solveLinearPump.toString());
  assert.ok(linear.phaseContracts.some(item=>item.phase==='pressure'&&item.engineSemantics[version]));
  assert.match(renderEquipmentModel(linear),/engineering\.pump\.linear@1\.0\.0/);
  fixture.model.destroy();
});

test('component null override reports builtin behavior instead of a type/family provider',()=>{
  const fixture=createPumpBench({version:1});
  fixture.model.setEquationBindings({version:1,types:{pump:{id:'engineering.pump.quadratic',version:'1.0.0'}},components:{pump:null}});
  const actual=report(fixture);
  assert.equal(actual.provider,null);
  assert.equal(actual.sources.find(item=>item.label==='pressureTarget').source,COMPONENT_MODEL_CLASSES.pump.prototype.pressureTarget.toString());
  assert.match(renderEquipmentModel(actual),/Built-in pump/);
  assert.doesNotMatch(renderEquipmentModel(actual),/engineering\.pump\.quadratic@/);
  fixture.model.destroy();
});

test('builtin math is extracted from the loaded implementation and configuration reflects accepted edits',async()=>{
  const base=new URL('../../../../software/cadagent/webkit/scada/sim/scenarios/wastewater-digester/',import.meta.url);
  const system=JSON.parse(await readFile(new URL('system.json',base),'utf8'));
  const definition=JSON.parse(await readFile(new URL('model.json',base),'utf8'));
  const model=new PlaceholderSystemModel(system,definition),fixture={system,model};
  const id='liftPump',initial=report(fixture,id);
  assert.equal(initial.id,id);
  assert.equal(initial.provider,null);
  // The release wastewater example uses v1; use the real v2 pump fixture as well.
  assert.equal(initial.sources.find(item=>item.label==='capacity').source,COMPONENT_MODEL_CLASSES.pump.prototype.capacity.toString());
  model.dispatch({action:'setParameter',arguments:{equipment:id,key:'capacity',value:43}});
  assert.equal(report(fixture,id).configuration.parameters.capacity,43);
  assert.equal(initial.configuration.parameters.capacity,definition.components[id].parameters.capacity);
  model.destroy();
  const v2=createPumpBench({version:2});v2.model.setEquationBindings(null);
  const actual=report(v2),classSource=CircuitSystemModel.toString();
  assert.equal(actual.version,2);
  for(const item of actual.sources)assert.ok(classSource.includes(item.source),item.label+' must be real loaded source');
  assert.ok(actual.sources.some(item=>item.label==='Connected material allocation'));
  assert.ok(actual.sources.some(item=>item.label==='Time integration and condition'));
  assert.equal(actual.sourcePath,'../sim/src/v2/circuit-system.mjs');
  v2.model.destroy();
});

test('unknown providers and stale saved identities never silently display a different law',()=>{
  const fixture=createPumpBench({version:1}),definition=fixture.model.exportModelDefinition(),saved=fixture.model.exportSnapshot().equationState;
  assert.throws(()=>equipmentModelReport({system:fixture.system,definition,id:'pump',providers:[]}),/Missing registered/);
  saved.components.pump.id='wrong.provider';
  assert.throws(()=>equipmentModelReport({system:fixture.system,definition,id:'pump',providers:pumpEquationProviders,equationState:saved}),/does not match/);
  assert.throws(()=>report(fixture,'missing-id'),/Unknown equipment/);
  fixture.model.destroy();
});

test('a host implementation with the same provider name is never presented as bundled physics',()=>{
  const fixture=createPumpBench({version:1}),definition=fixture.model.exportModelDefinition();
  const custom={...pumpEquationProviders[0],evaluate(){return {capacity:12};}};
  const actual=equipmentModelReport({system:fixture.system,definition,id:'pump',providers:[custom]});
  assert.equal(actual.bundledProvider,false);
  assert.equal(actual.sourcePath,null);
  assert.equal(actual.sources[0].source,custom.evaluate.toString());
  assert.doesNotMatch(renderEquipmentModel(actual),/Complete physical helpers|Open implementation source/);
  fixture.model.destroy();
});

test('equipment identity, descriptions, JSON and executable source are escaped as text',()=>{
  const fixture=createPumpBench({version:1});
  fixture.system.components.find(item=>item.id==='pump').label='<img src=x onerror=alert(1)>';
  const actual=report(fixture);actual.provider.description='</p><script>alert(1)</script>';
  actual.configuration.note='<svg onload=alert(1)>';
  actual.sources.push({label:'<unsafe>',source:'"</code><script>alert(1)</script>"'});
  const html=renderEquipmentModel(actual);
  assert.doesNotMatch(html,/<script>|<svg onload|<unsafe>/);
  assert.match(html,/&lt;script&gt;/);
  assert.match(html,/data-equipment-id="pump"/);
  fixture.model.destroy();
});
