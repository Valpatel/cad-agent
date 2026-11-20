import test from 'node:test';
import assert from 'node:assert/strict';
import {spawnSync} from 'node:child_process';
import {
  MODEL_DESCRIPTORS, MODEL_FAMILIES, getModelDescriptor, createModelDefinition,
  validatePlaceholderModelDefinition, PlaceholderSystemModel, createPlaceholderAdapter,
} from '../../../../software/cadagent/webkit/scada/sim/src/index.mjs';

const connection = (id, from, fromPort, to, toPort, medium = 'liquid') => ({id, from:{component:from, port:fromPort}, to:{component:to, port:toPort}, medium});
function configuration(id, components, connections = [], edits = {}, seed = 12345) {
  const system = {format:'scada-system', version:1, system:{id, label:id}, components:components.map(([id,type]) => ({id,type,label:id})), connections};
  const definition = createModelDefinition(system, {seed});
  for (const component of components) definition.components[component[0]].parameters.damageRate = 0;
  for (const [component, edit] of Object.entries(edits)) {
    const previous = definition.components[component];
    definition.components[component] = {...previous, ...edit, parameters:{...previous.parameters, ...edit.parameters}, initial:{...previous.initial, ...edit.initial}};
    if (edit.initial?.inventory != null && edit.initial.level == null) definition.components[component].initial.level = edit.initial.inventory;
    if (edit.initial?.level != null && edit.initial.inventory == null) definition.components[component].initial.inventory = edit.initial.level;
  }
  return {system, definition};
}
function modelFor(id, components, connections = [], edits = {}, seed = 12345, options) {
  const {system, definition} = configuration(id, components, connections, edits, seed);
  return new PlaceholderSystemModel(system, definition, options);
}
const command = (model, action, equipment, value, extra = {}) => model.dispatch({action, arguments:{...(equipment == null ? {} : {equipment}), ...(value === undefined ? {} : {value}), ...extra}});
function visualContract(type, state) {
  const fields = getModelDescriptor(type).visualFields;
  assert.deepEqual(Object.keys(state).sort(), Object.keys(fields).sort(), `${type} exposes only declared visual fields`);
  for (const [key, field] of Object.entries(fields)) {
    const value = state[key];
    if (field.type === 'boolean') assert.equal(typeof value, 'boolean', `${type}.${key}`);
    else if (field.type === 'number') assert.ok(typeof value === 'number' && Number.isFinite(value) && value >= field.min && value <= field.max, `${type}.${key}: ${value}`);
    else assert.ok(field.options.includes(value), `${type}.${key}: ${value}`);
  }
}
function finiteReadings(readings) {
  for (const [key, value] of Object.entries(readings)) if (typeof value === 'number') assert.ok(Number.isFinite(value), `${key} is finite`);
  for (const key of ['stock','pressure','temperature','load','damage','signal']) assert.ok(readings[key] >= 0 && readings[key] <= 100, `${key}: ${readings[key]}`);
}

test('variable valves expose effective partial opening and isolation overrides their operating setpoint', () => {
  for (const type of ['control-valve','gate-valve','butterfly-valve']) {
    const values = [];
    for (const load of [0,50,100]) {
      const model = modelFor('valve-opening', [['valve',type]], [], {valve:{initial:{load},parameters:{warningAt:100}}});
      const state = model.getSnapshot();
      values.push(state.components.valve.opening);
      assert.equal(state.components.valve.opening, load);
      command(model,'setOpen','valve',false);
      assert.equal(model.getSnapshot().components.valve.opening, 0);
      assert.equal(model.getSnapshot().readings.valve.flow, 0);
      model.destroy();
    }
    assert.deepEqual(values,[0,50,100]);
  }
});

test('empty energy stores cannot supply phantom power and empty vessels cannot leak phantom stock', () => {
  const battery = modelFor('empty-battery', [['battery','battery']], [], {battery:{initial:{inventory:0}}});
  assert.equal(battery.getSnapshot().readings.battery.powerOut,0);
  assert.equal(battery.getSnapshot().components.battery.active,false);
  battery.step(10);
  assert.equal(battery.getSnapshot().readings.battery.stock,0);
  const tank = modelFor('empty-leak', [['tank','tank']], [], {tank:{initial:{inventory:1}}});
  command(tank,'setFault','tank','leaking');
  tank.step(60);
  assert.equal(tank.getSnapshot().readings.tank.stock,0);
  assert.equal(tank.getSnapshot().readings.tank.leak,0);
  battery.destroy();tank.destroy();
});

test('clock and event sequence limits reject commands without partially changing transport or state', () => {
  const model = modelFor('bounded-commands', [['pump','pump']]);
  const saved = model.exportSnapshot();saved.state.minutes=1e9;model.importSnapshot(saved);
  const before = model.exportSnapshot();
  assert.throws(()=>command(model,'step',null,1),/Elapsed time/);
  assert.deepEqual(model.exportSnapshot(),before);
  const sequence = model.exportSnapshot();sequence.state.minutes=0;sequence.state.nextEventId=1e9;model.importSnapshot(sequence);
  const sequenceBefore=model.exportSnapshot();
  assert.throws(()=>command(model,'setEnabled','pump',false),/Event sequence/);
  assert.deepEqual(model.exportSnapshot(),sequenceBefore);
  model.reset();assert.equal(model.getSnapshot().minutes,0);model.destroy();
});

test('the independent model registry provides complete runnable contracts for all eighty symbol types', () => {
  assert.equal(MODEL_DESCRIPTORS.length, 80);
  assert.equal(new Set(MODEL_DESCRIPTORS.map(item => item.type)).size, 80);
  for (const descriptor of MODEL_DESCRIPTORS) {
    assert.ok(MODEL_FAMILIES.includes(descriptor.family), descriptor.type);
    assert.ok(descriptor.inputs.length && descriptor.outputs.length && descriptor.assumptions.length);
    assert.ok(descriptor.failureModes.length);
    assert.equal(descriptor.defaultModel.kind, descriptor.family);
    assert.ok(descriptor.parameters.every(parameter => parameter.key && parameter.unit && parameter.description && parameter.assumed === true));
    assert.ok(Object.isFrozen(descriptor));
    const {system, definition} = configuration('descriptor-probe', [['asset', descriptor.type]]);
    const result = validatePlaceholderModelDefinition(system, definition);
    assert.equal(result.ok, true, JSON.stringify(result.errors));
  }
});

test('configuration validation protects power, data, measurement and heat channels from material overrides', () => {
  const components = [['generator','generator'],['pump','pump'],['tank','tank'],['plc','plc-cpu'],['hmi','hmi'],['sensor','flow-meter'],['boiler','boiler'],['exchanger','heat-exchanger']];
  for (const edge of [
    connection('power-as-water','generator','output','pump','drive','liquid'),
    connection('data-as-water','plc','network','hmi','network','liquid'),
    connection('measurement-as-water','sensor','process','tank','inlet','liquid'),
    connection('heat-as-water','boiler','heat','tank','inlet','liquid'),
    connection('water-as-data','pump','outlet','tank','inlet','data'),
    connection('wrong-power-port','generator','output','pump','inlet','electricity'),
  ]) {
    const {system,definition} = configuration('invalid-channel',components,[edge]);
    const result = validatePlaceholderModelDefinition(system,definition);
    assert.equal(result.ok,false,edge.id);
    assert.ok(result.errors.some(error => error.code === 'channel_mismatch'),edge.id);
    assert.throws(() => new PlaceholderSystemModel(system,definition),/channel|port/i);
  }
  for (const edge of [
    connection('measurement-tap','pump','outlet','sensor','process','measurement'),
    connection('heat-service','boiler','heat','tank','inlet','thermal'),
    connection('hot-fluid','exchanger','hot-out','tank','inlet','thermal-fluid'),
    connection('ordinary-power','generator','output','pump','drive','electricity'),
    connection('ordinary-data','plc','network','hmi','network','data'),
  ]) {
    const {system,definition} = configuration('valid-channel',components,[edge]);
    const result = validatePlaceholderModelDefinition(system,definition);
    assert.equal(result.ok,true,`${edge.id}: ${JSON.stringify(result.errors)}`);
  }
});

for (const descriptor of MODEL_DESCRIPTORS) {
  test(`${descriptor.type}: off, low/mid/high operation, stress, explicit damage and repair are modeled`, () => {
    const loads = [];
    for (const load of [15, 50, 85]) {
      const model = modelFor(`probe-${descriptor.type}`, [['asset', descriptor.type]]);
      command(model, 'setLoad', 'asset', load);
      model.step(5);
      const snapshot = model.getSnapshot();
      assert.equal(snapshot.controls.asset.load, load);
      visualContract(descriptor.type, snapshot.components.asset);
      finiteReadings(snapshot.readings.asset);
      loads.push(snapshot.readings.asset.load);
      command(model, 'setEnabled', 'asset', false);
      assert.equal(model.getSnapshot().components.asset.active, false, 'off disables the component immediately');
      assert.equal(model.getSnapshot().controls.asset.enabled, false);
      model.destroy();
    }
    assert.ok(loads[0] < loads[1] && loads[1] < loads[2], `operating response must differ across low/mid/high: ${loads.join(', ')}`);
    const stressed = modelFor(`stress-${descriptor.type}`, [['asset', descriptor.type]], [], {asset:{parameters:{warningAt:10, damageRate:10}, initial:{load:95}}});
    stressed.step(2);
    let snapshot = stressed.getSnapshot();
    assert.ok(snapshot.readings.asset.damage > 0, 'excess stress grows actual damage');
    assert.ok(snapshot.components.asset.status === 'warning' || snapshot.components.asset.fault, 'stress is visible');
    const mode = descriptor.failureModes[0];
    const healthy = snapshot;
    command(stressed, 'setFault', 'asset', mode.id);
    snapshot = stressed.getSnapshot();
    assert.equal(snapshot.controls.asset.fault, true);
    const partial = ['degrade','leak'].includes(mode.effect) && !['sensor','controller','network'].includes(descriptor.family);
    assert.equal(snapshot.components.asset.fault, !partial, 'visual trip state distinguishes partial damage from unavailable equipment');
    assert.equal(snapshot.components.asset.active, partial, 'reduced-capacity damaged equipment remains active; trips are inactive');
    if (partial) {
      assert.equal(snapshot.components.asset.status,'warning');
      if (healthy.readings.asset.flow > 0) assert.ok(snapshot.readings.asset.flow < healthy.readings.asset.flow, 'partial damage reduces actual flow');
      if ('load' in snapshot.components.asset) assert.ok(snapshot.components.asset.load < healthy.components.asset.load, 'partial damage reduces the illustrated operating load');
    }
    assert.equal(snapshot.components.asset.damage, mode.id, 'the exact type-specific damage mode reaches the illustration');
    assert.ok(snapshot.readings.asset.damage > 0);
    command(stressed, 'setEnabled', 'asset', false);
    command(stressed, 'repair', 'asset');
    snapshot = stressed.getSnapshot();
    assert.equal(snapshot.components.asset.fault, false);
    assert.equal(snapshot.components.asset.damage, 'none');
    assert.equal(snapshot.readings.asset.damage, 0);
    assert.equal(snapshot.controls.asset.enabled, false, 'repair does not silently change the operator command');
    visualContract(descriptor.type, snapshot.components.asset);
    stressed.destroy();
  });
}

const waterComponents = [['tank','tank'],['pump','pump'],['valve','control-valve'],['sink','filter']];
const waterConnections = [connection('intake','tank','outlet','pump','inlet'),connection('delivery','pump','outlet','valve','inlet'),connection('demand','valve','outlet','sink','inlet')];
const waterEdits = {tank:{initial:{inventory:90}}, sink:{kind:'sink'}};

test('directed material topology responds coherently to upstream shutdown and downstream isolation', () => {
  const model = modelFor('water-chain', waterComponents, waterConnections, waterEdits);
  try {
    model.step(2);
    assert.ok(model.getSnapshot().flows.delivery);
    assert.ok(model.getSnapshot().readings.pump.flow > 0);
    const normalPressure = model.getSnapshot().readings.pump.pressure;
    command(model, 'setOpen', 'valve', false);
    assert.ok(waterConnections.every(edge => model.getSnapshot().flows[edge.id] === false), 'a closed downstream valve stops upstream and downstream delivery');
    model.step(8);
    assert.ok(model.getSnapshot().readings.pump.pressure > normalPressure, 'running against an isolated outlet raises the toy pressure index');
    command(model, 'setOpen', 'valve', true);
    assert.ok(model.getSnapshot().flows.delivery);
    command(model, 'setEnabled', 'pump', false);
    assert.ok(waterConnections.every(edge => !model.getSnapshot().flows[edge.id]));
    command(model, 'setEnabled', 'pump', true);
    command(model, 'setEnabled', 'tank', false);
    assert.ok(waterConnections.every(edge => !model.getSnapshot().flows[edge.id]), 'an unavailable connected source is not replaced with an imaginary bench supply');
  } finally { model.destroy(); }
});

test('explicit generator supply gates pump operation and overload produces generator stress', () => {
  const model = modelFor('powered-water', [...waterComponents,['generator','generator']], [...waterConnections,connection('pump-power','generator','output','pump','drive','electricity')], {...waterEdits, generator:{parameters:{capacity:100},initial:{load:100}},pump:{parameters:{demand:30}}});
  try {
    model.step(2);
    assert.equal(model.getSnapshot().flows.delivery, true);
    command(model, 'setEnabled', 'generator', false);
    assert.equal(model.getSnapshot().flows['pump-power'], false);
    assert.equal(model.getSnapshot().flows.delivery, false);
    assert.equal(model.getSnapshot().components.pump.active, false);
    command(model, 'setEnabled', 'generator', true);
    command(model, 'setParameter', 'generator', 15, {key:'capacity'});
    command(model, 'setParameter', 'generator', 20, {key:'warningAt'});
    command(model, 'setParameter', 'generator', 3, {key:'damageRate'});
    command(model, 'setParameter', 'pump', 100, {key:'demand'});
    command(model, 'setLoad', 'pump', 100);
    model.step(3);
    const snapshot = model.getSnapshot();
    assert.ok(snapshot.components.generator.status === 'warning' || snapshot.components.generator.fault);
    assert.ok(snapshot.readings.generator.damage > 0);
    assert.ok(snapshot.readings.pump.power >= 0);
  } finally { model.destroy(); }
});

test('sensor measurements and PLC/network failures propagate without creating material stock', () => {
  const material = [connection('fill','source','outlet','tank','inlet','fluid')];
  const components = [['source','wellhead'],['tank','tank']];
  const edits = {source:{initial:{load:40}},tank:{initial:{inventory:15}}};
  const baseline = modelFor('isolated-material', components, material, edits);
  const monitored = modelFor('isolated-material', [...components,['sensor','level-sensor'],['plc','plc-cpu'],['hmi','hmi']], [...material,connection('measure','tank','outlet','sensor','process','measurement'),connection('reading','sensor','signal','plc','backplane','data'),connection('display','plc','network','hmi','network','data')], edits);
  try {
    baseline.step(10); monitored.step(10);
    assert.equal(monitored.getSnapshot().readings.tank.stock, baseline.getSnapshot().readings.tank.stock, 'data and measurement channels cannot add or remove material');
    assert.ok(monitored.getSnapshot().readings.sensor.signal > 0, 'the level sensor measures the connected storage');
    assert.equal(monitored.getSnapshot().components.plc.connected, true);
    assert.equal(monitored.getSnapshot().components.hmi.connected, true);
    command(monitored, 'setFault', 'sensor', true);
    monitored.step(1);
    assert.equal(monitored.getSnapshot().flows.reading, false);
    assert.equal(monitored.getSnapshot().components.plc.connected, false);
    command(monitored, 'repair', 'sensor');
    monitored.step(1);
    assert.equal(monitored.getSnapshot().components.plc.connected, true);
    command(monitored, 'setFault', 'plc', 'comms-loss');
    assert.equal(monitored.getSnapshot().components.hmi.connected, false);
    assert.equal(monitored.getSnapshot().flows.display, false);
    assert.equal(monitored.getSnapshot().flows.fill, true, 'loss of communications alone is not a material source or valve command');
  } finally { baseline.destroy(); monitored.destroy(); }
});

test('stocks stay bounded during sustained filling, draining and a leaking failure', () => {
  const filling = modelFor('fill-limit', [['source','wellhead'],['tank','tank']], [connection('fill','source','outlet','tank','inlet','fluid')], {tank:{initial:{inventory:0}},source:{initial:{load:100}}});
  const draining = modelFor('drain-limit', [['tank','tank'],['sink','filter']], [connection('drain','tank','outlet','sink','inlet')], {tank:{initial:{inventory:85}},sink:{kind:'sink'}});
  try {
    for (let index=0; index<4; index++) { filling.step(50); draining.step(50); }
    assert.ok(filling.getSnapshot().readings.tank.stock > 90);
    assert.ok(draining.getSnapshot().readings.tank.stock < 1);
    for (const model of [filling,draining]) {
      const stock = model.getSnapshot().readings.tank.stock;
      assert.ok(stock >= 0 && stock <= 100);
      assert.ok(Object.values(model.getSnapshot().readings).every(row => Object.values(row).filter(value => typeof value === 'number').every(Number.isFinite)));
    }
    command(filling, 'setEnabled', 'source', false);
    const before = filling.getSnapshot().readings.tank.stock;
    command(filling, 'setFault', 'tank', 'leaking');
    filling.step(5);
    assert.ok(filling.getSnapshot().readings.tank.stock < before, 'leak damage removes retained resource');
    command(filling, 'repair', 'tank');
    const repaired = filling.getSnapshot().readings.tank.stock;
    filling.step(5);
    assert.equal(filling.getSnapshot().readings.tank.stock, repaired, 'repair stops the leak without inventing refill');
  } finally { filling.destroy(); draining.destroy(); }
});

test('seeded damage and exported snapshots replay deterministically across fresh models', () => {
  const components = [['pump','pump'],['heater','oven']];
  const edits = {pump:{initial:{load:100},parameters:{warningAt:40,damageRate:3}},heater:{initial:{load:100},parameters:{warningAt:40,damageRate:3}}};
  const original = modelFor('seeded',components,[],edits,45821), restored = modelFor('seeded',components,[],edits,999);
  try {
    original.step(6);
    const exported = original.exportSnapshot();
    restored.importSnapshot(JSON.parse(JSON.stringify(exported)));
    assert.deepEqual(restored.getSnapshot(),original.getSnapshot());
    for (let i = 0; i < 8; i++) {
      original.step(1); restored.step(1);
      assert.deepEqual(restored.getSnapshot(),original.getSnapshot(),`same seeded continuation at step ${i + 1}`);
    }
    command(original,'setRunning',null,false);
    restored.importSnapshot(original.exportSnapshot());
    assert.equal(restored.getSnapshot().running,false);
    assert.equal(restored.getSnapshot().minutes,original.getSnapshot().minutes);
    const detached = original.getSnapshot();
    try { detached.controls.pump.enabled = false; } catch {}
    assert.equal(original.getSnapshot().controls.pump.enabled,true,'returned state cannot mutate the live session');
  } finally { original.destroy(); restored.destroy(); }
});

test('invalid configuration and commands fail atomically; reset keeps edited parameters', () => {
  const {system,definition} = configuration('validation',[['pump','pump']]);
  const model = new PlaceholderSystemModel(system,definition);
  try {
    model.step(2);
    const before = model.exportSnapshot();
    for (const action of [
      () => command(model,'setLoad','pump',101),
      () => command(model,'setEnabled','pump','false'),
      () => command(model,'setOpen','missing',true),
      () => command(model,'setParameter','pump',2,{key:'response'}),
      () => command(model,'setParameter','pump',4,{key:'invented'}),
      () => command(model,'setFault','pump','invented-failure'),
      () => command(model,'setDamage','pump',-1),
      () => model.dispatch({action:'eval',arguments:{value:'code'}}),
      () => model.importSnapshot({...before,version:999}),
      () => model.importSnapshot(null),
      () => model.step(-1),
      () => model.step(Infinity),
    ]) {
      assert.throws(action);
      assert.deepEqual(model.exportSnapshot(),before);
    }
    for (const corrupt of [
      value => { value.system.signature = 'different-topology'; },
      value => { value.state.minutes = -1; },
      value => { value.state.running = 'true'; },
      value => { value.state.randomState = 0; },
      value => { value.state.nextEventId = -1; },
      value => { value.state.components.pump.inventory = 101; },
      value => { value.state.components.pump.operating = NaN; },
      value => { value.state.components.pump.mode = 'made-up-mode'; },
      value => { delete value.state.components.pump; },
      value => { value.state.components.extra = {...value.state.components.pump}; },
      value => { value.state.unrecognized = true; },
      value => { value.model.components.pump.parameters.capacity = -1; },
      value => { value.state.events = [{id:1,minutes:value.state.minutes+1,type:'fault',severity:'critical',equipment:'pump',message:'Future event'}]; value.state.nextEventId=2; },
      value => { value.state.events = [{id:1,minutes:0,type:'fault',severity:'critical',equipment:'pump',message:'First'},{id:1,minutes:0,type:'fault',severity:'critical',equipment:'pump',message:'Repeated id'}]; value.state.nextEventId=2; },
    ]) {
      const payload = structuredClone(before); corrupt(payload);
      assert.throws(() => model.importSnapshot(payload));
      assert.deepEqual(model.exportSnapshot(),before);
    }
    let getters = 0;
    const accessor = structuredClone(before);
    Object.defineProperty(accessor.state.components.pump,'operating',{enumerable:true,get(){getters++;return 50;}});
    assert.throws(() => model.importSnapshot(accessor));
    assert.equal(getters,0,'snapshot validation must not invoke accessors');
    assert.deepEqual(model.exportSnapshot(),before);
    const bad = structuredClone(definition);bad.components.pump.parameters.response=2;
    assert.equal(validatePlaceholderModelDefinition(system,bad).ok,false);
    assert.throws(() => new PlaceholderSystemModel(system,bad));
    command(model,'setParameter','pump',42,{key:'capacity'});
    command(model,'setRunning',null,false);
    command(model,'reset');
    assert.equal(model.getSnapshot().minutes,0);
    assert.equal(model.getSnapshot().running,false);
    assert.equal(model.exportModelDefinition().components.pump.parameters.capacity,42);
    assert.equal(model.getSnapshot().controls.pump.enabled,true);
  } finally { model.destroy(); }
});

test('a large elapsed-time snapshot is restored directly without replaying its history', () => {
  const url = new URL('../../../../software/cadagent/webkit/scada/sim/src/index.mjs',import.meta.url).href;
  const source = `const api=await import(${JSON.stringify(url)});const system={system:{id:'restore'},components:[{id:'pump',type:'pump'}]};const model=new api.PlaceholderSystemModel(system,api.createModelDefinition(system));const payload=model.exportSnapshot();payload.state.minutes=1000000;model.importSnapshot(payload);if(model.getSnapshot().minutes!==1000000)throw new Error('time not restored');model.destroy();`;
  const result = spawnSync(process.execPath,['--input-type=module','-e',source],{encoding:'utf8',timeout:4000});
  assert.equal(result.status,0,result.error?.message || result.stderr || result.stdout);
});

test('read-only adapters observe shared state without dispatch and detach without stopping the model', () => {
  const model = modelFor('adapters',[['pump','pump']]);
  const editable = createPlaceholderAdapter(model), monitor = createPlaceholderAdapter(model,{readOnly:true});
  let updates = 0;
  const unsubscribe = monitor.subscribe(() => updates++);
  try {
    assert.equal(typeof editable.dispatch,'function');
    assert.equal(monitor.dispatch,undefined);
    editable.dispatch({action:'setEnabled',arguments:{equipment:'pump',value:false}});
    assert.equal(monitor.getSnapshot().controls.pump.enabled,false);
    assert.equal(updates,1);
    unsubscribe();
    model.step(1);
    assert.equal(model.getSnapshot().minutes,1);
    assert.equal(updates,1);
  } finally { unsubscribe(); model.destroy(); }
});

test('headless imports and construction do not start clocks or use browser/network capabilities', () => {
  const url = new URL('../../../../software/cadagent/webkit/scada/sim/src/index.mjs',import.meta.url).href;
  const source = `globalThis.setInterval=()=>{throw new Error('implicit clock')};globalThis.fetch=()=>{throw new Error('network dependency')};for(const key of ['window','document','localStorage'])Object.defineProperty(globalThis,key,{get(){throw new Error('browser dependency')}});const api=await import(${JSON.stringify(url)});const system={system:{id:'isolated'},components:[{id:'pump',type:'pump'}]};const model=new api.PlaceholderSystemModel(system,api.createModelDefinition(system));model.importSnapshot(model.exportSnapshot());api.createPlaceholderAdapter(model).getSnapshot();model.destroy();`;
  const result = spawnSync(process.execPath,['--input-type=module','-e',source],{encoding:'utf8',timeout:10000});
  assert.equal(result.status,0,result.stderr || result.stdout);
});

test('explicit clock starts once, pauses, survives imports without duplication and cleans up', () => {
  const callbacks = new Map();let serial=0;
  const clock = {setInterval(callback){const id={id:++serial,unref(){}};callbacks.set(id,callback);return id;},clearInterval(id){callbacks.delete(id);}};
  const model = modelFor('clock',[['pump','pump']],[],{},12345,{clock});
  assert.equal(callbacks.size,0);
  try {
    model.start();model.start();assert.equal(callbacks.size,1);
    [...callbacks.values()][0]();assert.equal(model.getSnapshot().minutes,1);
    command(model,'setRunning',null,false);
    [...callbacks.values()][0]();assert.equal(model.getSnapshot().minutes,1);
    command(model,'step');assert.equal(model.getSnapshot().minutes,2);assert.equal(model.getSnapshot().running,false);
    model.importSnapshot(model.exportSnapshot());assert.equal(callbacks.size,1);
    model.stop();model.stop();assert.equal(callbacks.size,0);
    model.importSnapshot(model.exportSnapshot());assert.equal(callbacks.size,0);
    model.start();assert.equal(callbacks.size,1);
  } finally { model.destroy(); }
  assert.equal(callbacks.size,0);
});

test('an exhausted imported event sequence pauses the optional clock and exposes an importable terminal error', () => {
  for (const fullHistory of [false,true]) {
    const callbacks=new Map();let serial=0;
    const clock={setInterval(callback){const id=++serial;callbacks.set(id,callback);return id;},clearInterval(id){callbacks.delete(id);}};
    const model=modelFor('exhausted-clock',[['pump','pump']],[],{},12345,{clock});
    const payload=model.exportSnapshot();payload.state.nextEventId=1e9;
    if(fullHistory)payload.state.events=Array.from({length:100},(_,index)=>({id:999999900+index,minutes:0,type:'operator',severity:'info',equipment:'pump',message:'Previous event'}));
    model.importSnapshot(payload);const notices=[];model.subscribe((snapshot,event)=>notices.push({snapshot,event}));
    model.start();assert.doesNotThrow(()=>[...callbacks.values()][0]());
    assert.equal(model.clockStarted,false);assert.equal(callbacks.size,0);
    assert.equal(model.getSnapshot().running,false);assert.equal(model.getSnapshot().minutes,0);
    assert.match(model.getSnapshot().events.at(-1).message,/Event sequence limit/);
    assert.equal(model.getSnapshot().events.at(-1).severity,'critical');
    assert.equal(notices.at(-1).event.type,'error');assert.match(notices.at(-1).event.message,/Event sequence limit/);
    assert.ok(model.getSnapshot().events.length<=100);
    assert.doesNotThrow(()=>model.importSnapshot(model.exportSnapshot()));
    model.destroy();
  }
});
