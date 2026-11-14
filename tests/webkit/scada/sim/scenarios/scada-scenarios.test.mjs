import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {SCADA_COMPONENTS,getScadaComponent} from '../../../../../software/cadagent/webkit/scada/ui/src/symbols/index.mjs';
import {validateSystemDefinition,resolveComponentState} from '../../../../../software/cadagent/webkit/scada/ui/src/contracts/system-definition.mjs';
import {MODEL_DESCRIPTORS,getModelDescriptor} from '../../../../../software/cadagent/webkit/scada/sim/src/model-registry.mjs';
import {validatePlaceholderModelDefinition} from '../../../../../software/cadagent/webkit/scada/sim/src/validation.mjs';
import {PlaceholderSystemModel} from '../../../../../software/cadagent/webkit/scada/sim/src/placeholder-system.mjs';

const directory=new URL('../../../../../software/cadagent/webkit/scada/sim/scenarios/',import.meta.url);
const read=path=>JSON.parse(readFileSync(new URL(path,directory)));
const catalog=read('index.json');
const scenarios=catalog.scenarios.map(entry=>({entry,system:read(entry.system),model:read(entry.model)}));
// The original v1 teaching corpus has specific named views/recipes. Engine version
// does not impose those authoring choices on newly integrated systems.
const transferredScenarioIds=new Set(JSON.parse(readFileSync(new URL('../../../../fixtures/scada/default-baseline.json',import.meta.url))).records.map(record=>record.id));
const legacyScenarios=scenarios.filter(({entry,model})=>model.version===1&&transferredScenarioIds.has(entry.id));
const expandedScenarios=scenarios.filter(({model})=>model.version===2);
const required=['winery','brewery','fortune-cookies','shampoo','carbonated-beverages','dairy','fruit-juice','pharma-oral-liquid','tablets','biopharma-fermentation','sterile-filling','paint-blending','industrial-detergent','polymer-extrusion','concrete-batching','cement','mineral-crushing','mineral-flotation','metal-finishing','pulp-paper'];
const protectedMedia=new Set(['electricity','electrical','power','mechanical','data','signal','control','network','communication','measurement','sensor','thermal','heat','energy']);
const material=edge=>!protectedMedia.has(edge.medium);
const assetMap=system=>new Map(system.components.map(component=>[component.id,component]));
const endpointPort=(system,endpoint)=>getScadaComponent(assetMap(system).get(endpoint.component).type).ports.find(port=>port.id===endpoint.port);
function stepTo(model,minutes){while(model.getSnapshot().minutes<minutes)model.step(Math.min(60,minutes-model.getSnapshot().minutes));}

test('industry catalog preserves all requested sectors and indexes real runnable definitions',()=>{
  assert.equal(catalog.format,'scada-scenario-catalog');assert.equal(catalog.version,1);
  assert.equal(new Set(catalog.scenarios.map(entry=>entry.id)).size,catalog.scenarios.length);
  for(const id of required)assert.ok(scenarios.some(item=>item.entry.id===id),id);
  assert.ok(new Set(catalog.scenarios.map(entry=>entry.sector)).size>=9);
  for(const {entry,system,model} of scenarios){
    assert.equal(system.system.id,entry.id);assert.equal(model.scenarioId,entry.id);
    const structure=validateSystemDefinition(system);assert.equal(structure.ok,true,entry.id+JSON.stringify(structure.errors));
    const configuration=validatePlaceholderModelDefinition(system,model);assert.equal(configuration.ok,true,entry.id+JSON.stringify(configuration.errors));
    assert.deepEqual(entry.componentTypes,[...new Set(system.components.map(item=>item.type))].sort());
    assert.equal(new Set(entry.previewTypes).size,3);for(const type of entry.previewTypes)assert.ok(entry.componentTypes.includes(type));
    const originalV1=model.version===1&&transferredScenarioIds.has(entry.id);
    assert.ok(entry.processSteps.length>=(originalV1?8:3)&&entry.processSteps.length<=14);
    if(model.version===1){if(originalV1)assert.equal(entry.processAssetCount,entry.processSteps.length);assert.equal(entry.processAssetCount+entry.utilityAssetCount,system.components.length);}
    assert.deepEqual(entry.componentVariants,[...new Map(system.components.filter(c=>c.variant).map(c=>[c.type+'/'+c.variant,{type:c.type,variant:c.variant}])).values()].sort((a,b)=>a.type.localeCompare(b.type)||a.variant.localeCompare(b.variant)));
    assert.ok(model.assumptions.length>=(model.version===1?4:3));assert.ok(system.provenance.every(source=>(model.version===1?['assumed','illustrative']:['assumed','illustrative','external']).includes(source.kind)));
    if(model.version===2){assert.equal(typeof entry.facility,'string');assert.ok(entry.references.length);for(const ref of entry.references)assert.ok(system.provenance.some(source=>source.id===ref&&source.kind==='external'&&source.source));}
    for(const config of Object.values(model.components))assert.ok(config.assumptions.length);
  }
});

test('every registered symbol has an explicit model descriptor and a usable scenario location',()=>{
  const coverage=new Set(scenarios.flatMap(({system})=>system.components.map(component=>component.type)));
  assert.equal(MODEL_DESCRIPTORS.length,80);assert.ok(SCADA_COMPONENTS.length>=141);
  const legacyCoverage=new Set(legacyScenarios.flatMap(({system})=>system.components.map(c=>c.type)));
  for(const descriptor of MODEL_DESCRIPTORS)assert.ok(legacyCoverage.has(descriptor.type),descriptor.type+' original version1 coverage');
  assert.equal(legacyScenarios.length,20);assert.ok(expandedScenarios.length>=40);assert.ok(scenarios.length>=60);
  for(const component of SCADA_COMPONENTS){
    assert.ok(coverage.has(component.type),`${component.type} needs a runnable example`);
    const descriptor=getModelDescriptor(component.type,{version:2});
    assert.ok(descriptor.family);assert.ok(descriptor.parameters.length);assert.ok(descriptor.failureModes.length);
    assert.deepEqual(descriptor.ports.map(port=>port.id).sort(),component.ports.map(port=>port.id).sort());
  }
  const schema=JSON.parse(readFileSync(new URL('../../../../../software/cadagent/webkit/scada/ui/schema/scada-system.schema.json',import.meta.url)));
  assert.deepEqual([...schema.$defs.component.properties.type.enum].sort(),SCADA_COMPONENTS.map(component=>component.type).sort());
  for(const component of SCADA_COMPONENTS)for(const field of component.stateFields){
    assert.ok(schema.$defs.state.properties[field.key],field.key);assert.ok(schema.$defs.bindings.properties[field.key],field.key);
  }
});

test('focused layouts share canonical assets and every primary stage reaches a product boundary',()=>{
  for(const {entry,system,model} of legacyScenarios){
    const canonical=new Set(system.components.map(component=>component.id)),visible=new Set();
    assert.ok(system.views.length>=2);assert.deepEqual(entry.views,system.views.map(({id,label})=>({id,label})));
    for(const view of system.views){assert.ok(view.placements.length<=14,`${entry.id}/${view.id} is too crowded`);for(const node of view.placements){assert.ok(canonical.has(node.component));visible.add(node.component);}}
    assert.deepEqual(visible,canonical);
    assert.ok(system.views[0].placements.some(node=>system.views.slice(1).some(view=>view.placements.some(other=>other.component===node.component))),'Views need overlapping canonical equipment');
    const main=system.views.find(view=>view.id==='process');assert.ok(main);assert.equal(main.placements.length,entry.processAssetCount);
    const sinks=new Set(Object.entries(model.components).filter(([,config])=>config.kind==='sink').map(([id])=>id));assert.ok(sinks.size);
    const next=new Map([...canonical].map(id=>[id,system.connections.filter(edge=>material(edge)&&edge.from.component===id).map(edge=>edge.to.component)]));
    for(const node of main.placements){const todo=[node.component],seen=new Set();while(todo.length){const id=todo.pop();if(seen.has(id))continue;seen.add(id);todo.push(...next.get(id));}assert.ok([...sinks].some(id=>seen.has(id)),`${entry.id}/${node.component} does not reach a product sink`);}
    const connected=new Set(system.connections.flatMap(edge=>[edge.from.component,edge.to.component]));assert.deepEqual(connected,canonical);
  }
});

test('routing stays orthogonal and never crosses an unrelated equipment card',()=>{
  for(const {entry,system} of scenarios){const edges=new Map(system.connections.map(edge=>[edge.id,edge]));
    for(const view of system.views)for(const route of view.routes){const edge=edges.get(route.connection);
      for(let index=1;index<route.points.length;index++){
        const a=route.points[index-1],b=route.points[index];assert.ok(a.x===b.x||a.y===b.y);
        for(const box of view.placements){if([edge.from.component,edge.to.component].includes(box.component))continue;
          const intersects=a.x===b.x?a.x>box.x&&a.x<box.x+box.width&&Math.max(Math.min(a.y,b.y),box.y)<Math.min(Math.max(a.y,b.y),box.y+box.height):a.y>box.y&&a.y<box.y+box.height&&Math.max(Math.min(a.x,b.x),box.x)<Math.min(Math.max(a.x,b.x),box.x+box.width);
          assert.equal(intersects,false,`${entry.id}/${view.id}/${route.connection} crosses ${box.component}`);
        }
      }
    }
  }
});

test('legacy material streams cannot enter electrical or signal ports and probes tap their declared equipment',()=>{
  for(const {entry,system} of legacyScenarios){
    for(const edge of system.connections){const from=endpointPort(system,edge.from),to=endpointPort(system,edge.to);
      assert.notEqual(from.direction,'in');assert.notEqual(to.direction,'out');
      if(material(edge)){assert.ok(!protectedMedia.has(from.medium)&&!protectedMedia.has(to.medium),`${entry.id}/${edge.id} has a material/protected-port mismatch`);}
      if(edge.medium==='electricity')assert.ok(['electricity','mechanical'].includes(from.medium)&&['electricity','mechanical'].includes(to.medium));
      if(edge.medium==='data')assert.equal(from.medium+'|'+to.medium,'data|data');
      if(edge.medium==='measurement')assert.equal(to.medium,'measurement');
    }
    const sensors=system.components.filter(component=>getModelDescriptor(component.type).family==='sensor');
    assert.deepEqual(entry.measurements.map(item=>item.sensor).sort(),sensors.map(item=>item.id).sort());
    for(const measurement of entry.measurements){const taps=system.connections.filter(edge=>edge.medium==='measurement'&&edge.to.component===measurement.sensor);assert.equal(taps.length,1);assert.equal(taps[0].from.component,measurement.asset);}
  }
  const byId=new Map(scenarios.map(item=>[item.entry.id,item.entry]));
  for(const [scenario,sensor,asset] of [['fortune-cookies','temperature','oven'],['cement','temperature','kiln'],['tablets','temperature','dryer'],['pulp-paper','temperature','dryer'],['polymer-extrusion','temperature','extruder'],['brewery','temperature','cooler'],['shampoo','level','bulk'],['industrial-detergent','level','hold']]){
    assert.equal(byId.get(scenario).measurements.find(item=>item.sensor===sensor).asset,asset);
  }
  for(const id of ['fortune-cookies','shampoo','carbonated-beverages','pharma-oral-liquid','industrial-detergent']){
    const {system}=scenarios.find(item=>item.entry.id===id);const dosing=new Set(system.components.filter(component=>component.type==='dosing-pump').map(component=>component.id));
    for(const edge of system.connections.filter(edge=>material(edge)&&dosing.has(edge.to.component)))assert.equal(edge.to.port,'suction');
  }
});

test('every asset exposes supported visual bindings and operational controls with truthful valve semantics',()=>{
  for(const {entry,system} of scenarios)for(const component of system.components){
    const descriptor=getScadaComponent(component.type);assert.deepEqual(Object.keys(component.bindings).sort(),descriptor.stateFields.map(field=>field.key).sort());
    for(const action of ['setEnabled','setLoad','setFault','repair']){
      const command=system.commands.find(command=>command.component===component.id&&command.action===action);assert.ok(command,`${entry.id}/${component.id}/${action}`);
      assert.equal(command.arguments.equipment,component.id);assert.ok(system.controls.some(control=>control.command===command.id));
    }
    if(['control-valve','gate-valve','butterfly-valve'].includes(component.type)){
      const command=system.commands.find(command=>command.component===component.id&&command.action==='setLoad');assert.match(system.controls.find(control=>control.command===command.id).label,/opening/i);
      assert.ok(component.bindings.opening);
    }
    if(component.type==='breaker'){
      const command=system.commands.find(command=>command.component===component.id&&command.action==='setOpen');assert.match(system.controls.find(control=>control.command===command.id).label,/isolated/i);
    }
  }
});

test('all legacy scenario baselines remain productive and free of injected/latent faults through300toy minutes',()=>{
  for(const {entry,system,model:configuration} of legacyScenarios){
    const model=new PlaceholderSystemModel(system,configuration);assert.equal(model.clockStarted,false);
    try{for(const time of [0,10,60,300]){
      stepTo(model,time);const snapshot=model.getSnapshot();
      for(const component of system.components){
        const resolved=resolveComponentState(component,snapshot);assert.equal(resolved.ok,true,`${entry.id}/${component.id}: ${JSON.stringify(resolved.errors)}`);
        assert.equal(resolved.state.status,'normal',`${entry.id}/${component.id} abnormal at ${time}`);assert.equal(resolved.state.fault,false);assert.equal(resolved.state.damage,'none');
        assert.equal(snapshot.readings[component.id].damage,0,`${entry.id}/${component.id} damages itself at baseline`);
        for(const value of Object.values(snapshot.readings[component.id]))if(typeof value==='number')assert.ok(Number.isFinite(value));
      }
      for(const [id,config] of Object.entries(configuration.components))if(config.kind==='sink')assert.ok(snapshot.readings[id].resourceIn>0,`${entry.id}/${id} is not producing at ${time}`);
    }assert.equal(model.clockStarted,false);}finally{model.destroy();}
  }
});

test('legacy scenario experiments execute actual adapter commands and produce the advertised control/fault transitions',()=>{
  for(const {entry,system,model:configuration} of legacyScenarios){assert.ok(entry.experiments.length>=4);
    for(const experiment of entry.experiments){assert.ok(experiment.expected&&experiment.limitation);const model=new PlaceholderSystemModel(system,configuration);
      try{for(const command of experiment.commands)model.dispatch(command);model.step(10);const snapshot=model.getSnapshot();
        if(experiment.id==='starve-feed'){const id=experiment.commands[0].arguments.equipment;assert.equal(snapshot.controls[id].enabled,false);assert.equal(snapshot.readings[id].resourceOut,0);}
        if(experiment.id==='overload-stage'){const id=experiment.commands[0].arguments.equipment;assert.equal(snapshot.parameters[id].capacity,25);assert.equal(snapshot.controls[id].load,95);assert.equal(snapshot.components[id].status,'warning');assert.ok(snapshot.readings[id].damage>0);}
        if(['break-stage','trip-power'].includes(experiment.id)){const id=experiment.commands[0].arguments.equipment;assert.equal(snapshot.controls[id].fault,true);assert.notEqual(snapshot.components[id].damage,'none');model.dispatch({action:'repair',arguments:{equipment:id}});assert.equal(model.getSnapshot().controls[id].fault,false);}
        if(experiment.id==='isolate-transfer'){const id=experiment.commands[0].arguments.equipment;assert.equal(snapshot.controls[id].open,false);assert.equal(snapshot.readings[id].resourceOut,0);}
      }finally{model.destroy();}
    }
  }
});

test('concrete breaker starts closed, opening isolates explicit consumers and closing restores supply',()=>{
  const {system,model:configuration}=scenarios.find(item=>item.entry.id==='concrete-batching');assert.equal(configuration.components.breaker.initial.open,false);
  const model=new PlaceholderSystemModel(system,configuration),consumers=system.connections.filter(edge=>edge.from.component==='breaker'&&edge.medium==='electricity').map(edge=>edge.to.component);assert.ok(consumers.length);
  try{
    assert.ok(consumers.every(id=>model.getSnapshot().readings[id].powerFactor>.999));
    model.dispatch({action:'setOpen',arguments:{equipment:'breaker',value:true}});
    assert.ok(consumers.every(id=>model.getSnapshot().readings[id].powerFactor===0));
    model.dispatch({action:'setOpen',arguments:{equipment:'breaker',value:false}});
    assert.ok(consumers.every(id=>model.getSnapshot().readings[id].powerFactor>.999));
  }finally{model.destroy();}
});

test('every legacy scenario preserves seeded damaged-state evolution across JSON export/import and reset keeps edited parameters',()=>{
  for(const {entry,system,model:configuration} of legacyScenarios){
    const original=new PlaceholderSystemModel(system,configuration),restored=new PlaceholderSystemModel(system,configuration);
    try{
      const experiment=entry.experiments.find(item=>item.id==='overload-stage');
      for(const command of experiment.commands)original.dispatch(command);
      original.step(10);restored.importSnapshot(JSON.parse(JSON.stringify(original.exportSnapshot())));
      original.step(5);restored.step(5);assert.deepEqual(restored.getSnapshot(),original.getSnapshot(),entry.id);
      assert.equal(restored.clockStarted,false);
      const id=experiment.commands[0].arguments.equipment;restored.reset();
      assert.equal(restored.getSnapshot().minutes,0);assert.equal(restored.getSnapshot().parameters[id].capacity,25);
      assert.equal(restored.getSnapshot().readings[id].damage,0);assert.equal(restored.getSnapshot().controls[id].load,configuration.components[id].initial.load);
    }finally{original.destroy();restored.destroy();}
  }
});

function retainedTotals(model){const s=model.exportSnapshot().state;return {mass:Object.values(s.circuits).flatMap(Object.values).reduce((sum,c)=>sum+c.amount,0),energy:Object.values(s.circuits).flatMap(Object.values).reduce((sum,c)=>sum+c.heat,0)+Object.values(s.thermalStores).reduce((a,b)=>a+b,0)+Object.values(s.energyStores).reduce((a,b)=>a+b,0)};}
const makeScenario=id=>{const scenario=scenarios.find(({entry})=>entry.id===id);assert.ok(scenario,id);return {...scenario,instance:new PlaceholderSystemModel(scenario.system,scenario.model)};};

test('expanded scenarios preserve focused shared views, explicit provenance and version2 identities',()=>{
  for(const {entry,system,model} of expandedScenarios){
    const canonical=new Set(system.components.map(c=>c.id));assert.ok(system.views.length>=2&&system.views.length<=4);
    assert.deepEqual(new Set(system.views.flatMap(v=>v.placements.map(p=>p.component))),canonical,entry.id);
    assert.deepEqual(entry.views,system.views.map(({id,label})=>({id,label})),entry.id);
    assert.ok(system.views[0].placements.some(p=>system.views.slice(1).some(v=>v.placements.some(q=>p.component===q.component))),entry.id+' shared view equipment');
    assert.equal(model.version,2);for(const c of system.components){assert.equal(model.components[c.id].variant,c.variant);getModelDescriptor(c.type,{version:2,variant:c.variant});}
    assert.ok(system.provenance.some(p=>p.kind==='assumed'));assert.ok(system.provenance.some(p=>p.kind==='external'));
  }
});

test('all40 expanded scenarios stay normal at0/10/60/300 minutes, conserve declared inventories and replay exactly',()=>{
  for(const {entry,system,model:definition} of expandedScenarios){
    const model=new PlaceholderSystemModel(system,definition),before=retainedTotals(model);
    try{
      for(const minutes of [0,10,60,300]){
        stepTo(model,minutes);const snapshot=model.getSnapshot();assert.equal(model.clockStarted,false);
        for(const component of system.components){const state=resolveComponentState(component,snapshot);assert.equal(state.ok,true,entry.id+'/'+component.id);assert.equal(state.state.status,'normal',entry.id+'/'+component.id+' at '+minutes);assert.equal(state.state.fault,false);assert.equal(state.state.damage,'none');assert.equal(snapshot.readings[component.id].damage,0,entry.id+'/'+component.id+' damage at '+minutes);for(const value of Object.values(snapshot.readings[component.id]))if(typeof value==='number')assert.ok(Number.isFinite(value));}
        for(const [id,c] of Object.entries(definition.components))if(c.energy?.role==='load'&&c.energy.demand>0)assert.ok(snapshot.readings[id].powerFactor>=.99,entry.id+'/'+id+' supplied demand');
      }
      const after=retainedTotals(model),ledger=model.getSnapshot().ledger;
      assert.ok(Math.abs(after.mass-before.mass-ledger.resourceBoundaryIn+ledger.resourceBoundaryOut+ledger.resourceLeak)<1e-6,entry.id+' resource ledger');
      assert.ok(Math.abs(after.energy-before.energy-ledger.energyBoundaryIn-ledger.heatBoundaryIn+ledger.energyBoundaryOut+ledger.heatBoundaryOut+ledger.energyLoss)<1e-6,entry.id+' energy ledger');
      const restored=new PlaceholderSystemModel(system,definition);try{restored.importSnapshot(JSON.parse(JSON.stringify(model.exportSnapshot())));model.step(7);restored.step(7);assert.deepEqual(restored.exportSnapshot(),model.exportSnapshot(),entry.id+' continuation');}finally{restored.destroy();}
    }finally{model.destroy();}
  }
});

test('all expanded catalog experiments dispatch on the public adapter without invalid or nonfinite state',()=>{
  for(const {entry,system,model:definition} of expandedScenarios)for(const experiment of entry.experiments){
    assert.ok(experiment.expected&&experiment.limitation);const model=new PlaceholderSystemModel(system,definition);
    try{for(const command of experiment.commands)assert.doesNotThrow(()=>model.dispatch(command),entry.id+'/'+experiment.id);model.step(10);const snapshot=model.getSnapshot();for(const component of system.components){assert.equal(resolveComponentState(component,snapshot).ok,true,entry.id+'/'+component.id);for(const value of Object.values(snapshot.readings[component.id]))if(typeof value==='number')assert.ok(Number.isFinite(value));}}finally{model.destroy();}
  }
});

test('battery and pumped storage experiments reverse signed flows and change finite stock in the advertised direction',()=>{
  for(const id of ['power-battery-storage','power-hybrid-microgrid','power-pumped-storage'])for(const mode of id==='power-pumped-storage'?['generate','pump']:['discharge','charge']){
    const {instance:model,entry}=makeScenario(id);try{const before=model.getSnapshot(),store=id==='power-pumped-storage'?'unit':'battery';for(const command of entry.experiments.find(e=>e.id===mode).commands)model.dispatch(command);model.step(.2);const after=model.getSnapshot(),charging=['pump','charge'].includes(mode),edge=id==='power-pumped-storage'?'machine-output-to-acBus-branch-a':id==='power-hybrid-microgrid'?'storageConverter-ac-to-acBus-branch-a':'converter-ac-to-acBus-branch-a';assert.ok(charging?after.energyStores[store]>before.energyStores[store]:after.energyStores[store]<before.energyStores[store],id+'/'+mode+' energy movement');assert.ok(charging?after.flowRates[edge]<0:after.flowRates[edge]>0,id+'/'+mode+' signed electrical path');if(id==='power-pumped-storage'){const oldUpper=before.circuits.upper.water.amount,newUpper=after.circuits.upper.water.amount;assert.ok(charging?newUpper>oldUpper:newUpper<oldUpper);assert.ok(charging?after.flowRates['upper-connection-to-unit-upper']<0:after.flowRates['upper-connection-to-unit-upper']>0);}}finally{model.destroy();}
  }
});

test('PWR rod demand, primary-pump isolation and monitor failure affect the correct physical and observation paths',()=>{
  const baseline=makeScenario('power-nuclear-pwr'),rods=makeScenario('power-nuclear-pwr'),cooling=makeScenario('power-nuclear-pwr'),monitor=makeScenario('power-nuclear-pwr');
  try{
    rods.instance.dispatch({action:'setRodPosition',arguments:{equipment:'core',value:100}});
    cooling.instance.dispatch({action:'setEnabled',arguments:{equipment:'primaryPump',value:false}});
    monitor.instance.dispatch({action:'setFault',arguments:{equipment:'neutron',value:'broken'}});
    for(const item of [baseline,rods,cooling,monitor])item.instance.step(10);
    const nominal=baseline.instance.getSnapshot(),reduced=rods.instance.getSnapshot(),stopped=cooling.instance.getSnapshot(),failed=monitor.instance.getSnapshot();
    assert.ok(reduced.ledger.heatBoundaryIn<nominal.ledger.heatBoundaryIn,'Rod insertion reduces new heat input');assert.ok(reduced.readings.core.temperature>0,'Stored heat persists');
    assert.equal(stopped.readings.primaryPump.resourceOut,0);assert.ok(nominal.readings.primaryPump.resourceOut>0);assert.notEqual(stopped.circuits.steamGenerator.primary.temperature,nominal.circuits.steamGenerator.primary.temperature,'Cooling isolation changes the thermal trajectory');
    assert.equal(failed.readings.neutron.valid,false);assert.equal(failed.readings.primaryPump.resourceOut,nominal.readings.primaryPump.resourceOut,'Non-consuming monitor failure does not remove coolant');
    const config=baseline.model;assert.notEqual(config.components.steamGenerator.circuits.primary.fluid,config.components.steamGenerator.circuits.secondary.fluid);assert.notEqual(config.components.condenser.circuits.cooling.fluid,config.components.condenser.circuits.condensing.fluid);
  }finally{for(const item of [baseline,rods,cooling,monitor])item.instance.destroy();}
});

test('fuel, environmental resource and output isolation change delivered electrical power',()=>{
  for(const [id,command] of [
    ['power-ng-engine-chp',{action:'setEnabled',arguments:{equipment:'fuel',value:false}}],
    ['power-gas-simple-cycle',{action:'setEnabled',arguments:{equipment:'air',value:false}}],
    ['power-solar-pv',{action:'setEnvironment',arguments:{key:'light',value:0}}],
    ['power-wind-collection',{action:'setEnvironment',arguments:{key:'wind',value:0}}],
    ['power-substation-distribution',{action:'setOpen',arguments:{equipment:'feederA',value:true}}],
  ]){
    const baseline=makeScenario(id),changed=makeScenario(id);try{changed.instance.dispatch(command);baseline.instance.step(10);changed.instance.step(10);const before=baseline.instance.getSnapshot(),after=changed.instance.getSnapshot();const loads=Object.entries(baseline.model.components).filter(([,c])=>c.energy?.role==='load'&&(c.energy.demand??0)>1).map(([id])=>id);assert.ok(loads.some(id=>after.readings[id].powerIn<before.readings[id].powerIn),id+' downstream delivery');}finally{baseline.instance.destroy();changed.instance.destroy();}
  }
});
