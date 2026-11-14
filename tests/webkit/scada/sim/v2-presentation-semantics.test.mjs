import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {CircuitSystemModel} from '../../../../software/cadagent/webkit/scada/sim/src/v2/circuit-system.mjs';
import {createV2ModelDefinition} from '../../../../software/cadagent/webkit/scada/sim/src/v2/contract.mjs';

const scenario = name => new CircuitSystemModel(
  JSON.parse(readFileSync(new URL(`../../../../software/cadagent/webkit/scada/sim/scenarios/${name}/system.json`, import.meta.url))),
  JSON.parse(readFileSync(new URL(`../../../../software/cadagent/webkit/scada/sim/scenarios/${name}/model.json`, import.meta.url))),
);
const command = (model, action, equipment, value) => model.dispatch({action, arguments:{equipment, value}});
const fixture = (type, configure = () => {}) => {
  const system = {system:{id:'presentation-semantics'}, components:[{id:'asset',type}], connections:[]};
  const definition = createV2ModelDefinition(system);
  configure(definition.components.asset);
  return new CircuitSystemModel(system, definition);
};

test('transfer-switch presentation names the same source as its selected energy path, including off and restore', () => {
  const model = scenario('power-diesel-standby');
  try {
    for (const [mode, source] of [['source-a','a'], ['source-b','b'], ['off','off'], ['source-a','a']]) {
      command(model, 'setMode', 'transfer', mode);
      const snapshot = model.getSnapshot();
      assert.equal(snapshot.controls.transfer.mode, mode);
      assert.equal(snapshot.components.transfer.source, source);
      const a = snapshot.flowRates['grid-secondary-to-transfer-source-a'];
      const b = snapshot.flowRates['engine-output-to-transfer-source-b'];
      const output = snapshot.flowRates['transfer-load-to-load-supply'];
      if (source === 'a') { assert.ok(a > 0); assert.equal(b, 0); assert.ok(output > 0); }
      else if (source === 'b') { assert.ok(b > 0); assert.equal(a, 0); assert.ok(output > 0); }
      else { assert.equal(a, 0); assert.equal(b, 0); assert.equal(output, 0); assert.equal(snapshot.components.transfer.active, false); }
    }
    command(model, 'setMode', 'transfer', 'source-b');
    const saved = model.exportSnapshot();
    command(model, 'setMode', 'transfer', 'off');
    model.importSnapshot(saved);
    assert.equal(model.getSnapshot().components.transfer.source, 'b');
  } finally { model.destroy(); }
});

test('relay equipment damage never fabricates a protection decision or an asserted trip output', () => {
  const model = scenario('power-substation-distribution');
  try {
    for (const mode of ['none','drift','comms-loss','power-loss','none']) {
      command(model, 'setFault', 'relay', mode);
      const snapshot = model.getSnapshot();
      assert.equal(snapshot.components.relay.tripped, false, mode);
      assert.equal(snapshot.controls.relay.fault, mode !== 'none');
      assert.equal(snapshot.components.relay.damage, mode);
      if (mode === 'drift') { assert.equal(snapshot.components.relay.connected, true); assert.equal(snapshot.components.relay.status, 'warning'); }
      if (mode === 'comms-loss' || mode === 'power-loss') assert.equal(snapshot.components.relay.connected, false);
    }
    assert.equal(model.getSnapshot().components.relay.connected, true);
  } finally { model.destroy(); }
});

test('instantaneous rod position edits and unrelated load lag do not invent actuator travel', () => {
  const model = scenario('power-nuclear-pwr');
  try {
    const initial = model.getSnapshot().components.rods.rodPosition;
    command(model, 'setRodPosition', 'rods', 80);
    assert.notEqual(initial, 80);
    assert.equal(model.getSnapshot().components.rods.rodPosition, 80);
    assert.equal(model.getSnapshot().components.rods.moving, false);
    command(model, 'setLoad', 'rods', 0);
    assert.equal(model.getSnapshot().components.rods.rodPosition, 80);
    assert.equal(model.getSnapshot().components.rods.moving, false);
    model.step(1);
    assert.equal(model.getSnapshot().components.rods.rodPosition, 80);
    assert.equal(model.getSnapshot().components.rods.moving, false);
  } finally { model.destroy(); }
});

test('degraded CT and water-quality observations remain available; unavailable faults retain values until repair', () => {
  const station = scenario('power-substation-distribution');
  const farm = scenario('aquaponics-dwc');
  try {
    const reading = station.getSnapshot().components.ct.value;
    command(station, 'setFault', 'ct', 'drift');
    assert.equal(station.getSnapshot().components.ct.connected, true);
    assert.equal(station.getSnapshot().readings.ct.valid, true);
    assert.equal(station.getSnapshot().components.ct.value, reading);
    assert.equal(station.getSnapshot().components.ct.status, 'warning');
    for (const mode of ['broken','insulation-fault']) {
      command(station, 'setFault', 'ct', mode);
      assert.equal(station.getSnapshot().components.ct.connected, false);
      assert.equal(station.getSnapshot().readings.ct.valid, false);
      assert.equal(station.getSnapshot().components.ct.value, reading);
    }
    station.dispatch({action:'repair', arguments:{equipment:'ct'}});
    assert.equal(station.getSnapshot().components.ct.connected, true);
    assert.equal(station.getSnapshot().readings.ct.valid, true);
    for (const mode of ['drift','fouled']) {
      command(farm, 'setFault', 'fishProbe', mode);
      farm.dispatch({action:'setTracer',arguments:{equipment:'fish',circuit:'water',key:'oxygen',value:37}});
      const snapshot = farm.getSnapshot();
      assert.equal(snapshot.components.fishProbe.connected, true);
      assert.equal(snapshot.readings.fishProbe.valid, true);
      assert.equal(snapshot.components.fishProbe.status, 'warning');
      assert.equal(snapshot.components.fishProbe.value, 37);
    }
    command(farm, 'setFault', 'fishProbe', 'disconnected');
    farm.dispatch({action:'setTracer',arguments:{equipment:'fish',circuit:'water',key:'oxygen',value:22}});
    assert.equal(farm.getSnapshot().readings.fishProbe.valid, false);
    assert.equal(farm.getSnapshot().components.fishProbe.value, 37, 'unavailable telemetry holds its last observation');
    farm.dispatch({action:'repair',arguments:{equipment:'fishProbe'}});
    assert.equal(farm.getSnapshot().components.fishProbe.value, 22);
    assert.equal(farm.getSnapshot().readings.fishProbe.valid, true);
  } finally { station.destroy(); farm.destroy(); }
});

test('a disabled high command cannot cause operating damage or re-fail repaired equipment; stored heat is retained', () => {
  const model = fixture('tank', config => {
    config.initial.enabled = false; config.initial.load = 100;
    config.parameters.warningAt = 10; config.parameters.damageRate = 10;
    for (const circuit of Object.values(config.circuits)) { circuit.initial.pressure = 0; circuit.initial.temperature = 90; }
  });
  try {
    model.step(15);
    assert.equal(model.getSnapshot().readings.asset.damage, 0);
    assert.equal(model.getSnapshot().readings.asset.temperature, 90);
    command(model, 'setFault', 'asset', 'leaking');
    model.dispatch({action:'repair',arguments:{equipment:'asset'}});
    model.step(15);
    assert.equal(model.getSnapshot().readings.asset.damage, 0);
    assert.equal(model.getSnapshot().controls.asset.enabled, false);
    assert.equal(model.getSnapshot().controls.asset.load, 100);
    assert.equal(model.getSnapshot().components.asset.damage, 'none');
  } finally { model.destroy(); }
});

test('retained circuit pressure can still cause damage after disable, while missing supply and idle do not count as load', () => {
  const pressurized = fixture('tank', config => {
    config.initial.enabled = false; config.initial.load = 0;
    config.parameters.warningAt = 10; config.parameters.damageRate = 10;
    for (const circuit of Object.values(config.circuits)) circuit.initial.pressure = 100;
  });
  const unpowered = fixture('motor', config => {
    config.initial.load = 100; config.parameters.warningAt = 10; config.parameters.damageRate = 10;
  });
  const idle = fixture('battery', config => {
    config.initial.mode = 'idle'; config.initial.load = 100;
    config.parameters.warningAt = 10; config.parameters.damageRate = 10;
  });
  try {
    pressurized.step(1);
    assert.ok(pressurized.getSnapshot().readings.asset.pressure > 10);
    assert.ok(pressurized.getSnapshot().readings.asset.damage > 0);
    unpowered.step(15);
    assert.equal(unpowered.getSnapshot().readings.asset.powerFactor, 0);
    assert.equal(unpowered.getSnapshot().readings.asset.damage, 0);
    idle.step(15);
    assert.equal(idle.getSnapshot().components.asset.active, false);
    assert.equal(idle.getSnapshot().readings.asset.damage, 0);
  } finally { pressurized.destroy(); unpowered.destroy(); idle.destroy(); }
});
