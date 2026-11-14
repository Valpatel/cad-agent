import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {JSDOM} from './dependencies.mjs';
import {CircuitSystemModel, createV2Adapter} from '../../../software/cadagent/webkit/scada/sim/src/index.mjs';
import {ScadaViewer} from '../../../software/cadagent/webkit/scada/ui/src/index.mjs';
import {FakePumpEngine} from '../../../software/cadagent/webkit/scada/sim/examples/external-adapter/fake-engine.mjs';
import {createExternalAdapter} from '../../../software/cadagent/webkit/scada/sim/examples/external-adapter/adapter.mjs';
import {resolveComponentState} from '../../../software/cadagent/webkit/scada/ui/src/contracts/system-definition.mjs';
import {renderScadaComponent} from '../../../software/cadagent/webkit/scada/ui/src/symbols/index.mjs';

function render(adapter,id,type) {
  const resolved = resolveComponentState({id,type},adapter.getSnapshot());
  assert.equal(resolved.ok,true,JSON.stringify(resolved.errors));
  return new JSDOM(renderScadaComponent(type,{state:resolved.state}));
}
const sample = overrides => ({timeSeconds:1,valid:true,mechanicalRunning:true,speedRpm:1800,powerKW:2.5,massFlowKgS:0,fault:false,warning:false,...overrides});

test('direct v2 read-only views expose no commands and borrow the same host-owned session', () => {
  const scenario = new URL('../../../software/cadagent/webkit/scada/sim/scenarios/hydroponics-nft/', import.meta.url);
  const definition = JSON.parse(readFileSync(new URL('system.json', scenario), 'utf8'));
  const model = new CircuitSystemModel(definition, JSON.parse(readFileSync(new URL('model.json', scenario), 'utf8')));
  const dom = new JSDOM('<main><div id="primary"></div><div id="observer"></div></main>');
  const dispatch = model.dispatch.bind(model), subscribe = model.subscribe.bind(model);
  let commands = 0, subscriptions = 0;
  model.dispatch = command => { commands++; return dispatch(command); };
  model.subscribe = listener => {
    subscriptions++;
    const unsubscribe = subscribe(listener);
    return () => { subscriptions--; unsubscribe(); };
  };
  model.step(1);
  const initial = model.exportSnapshot(), observerAdapter = createV2Adapter(model, {readOnly:true});
  const primary = new ScadaViewer({definition, adapter:createV2Adapter(model), scope:'primary'});
  const observer = new ScadaViewer({definition, adapter:observerAdapter, scope:'observer'});
  try {
    primary.mount(dom.window.document.querySelector('#primary'));
    observer.mount(dom.window.document.querySelector('#observer'));
    observer.select('supplyPump', {open:true});
    assert.equal(observer.readOnly, true);
    assert.equal(Object.hasOwn(observerAdapter, 'dispatch'), false);
    assert.equal(subscriptions, 2);
    const controls = [...observer.root.querySelectorAll('[data-scada-control]')];
    assert.ok(controls.length >= 4, 'the actual pump inspector exposes its switch, load, fault and repair controls');
    assert.ok(controls.every(control => control.disabled));
    for (const control of controls) {
      control.dispatchEvent(new dom.window.MouseEvent('click', {bubbles:true}));
      control.dispatchEvent(new dom.window.Event('change', {bubbles:true}));
    }
    assert.throws(() => observer.dispatch({action:'reset'}), /read-only/);
    assert.equal(commands, 0);
    assert.deepEqual(model.exportSnapshot(), initial, 'mounting and inspecting views never resets or steps the session');

    primary.dispatch({action:'setEnabled', arguments:{equipment:'supplyPump', value:false}});
    assert.equal(commands, 1);
    assert.equal(observer.snapshot.controls.supplyPump.enabled, false);
    model.step(.25);
    assert.equal(primary.snapshot, model.getSnapshot());
    assert.equal(observer.snapshot, primary.snapshot);
    assert.equal(observer.snapshot.minutes, 1.25, 'two mounted views observe one explicit host step');
    observer.setView(definition.views.at(-1).id);
    assert.equal(observer.snapshot, model.getSnapshot());
    const beforeDestroy = model.exportSnapshot(), finalObserverSnapshot = observer.snapshot;
    observer.destroy();
    assert.equal(subscriptions, 1, 'only the destroyed view unsubscribes');
    assert.deepEqual(model.exportSnapshot(), beforeDestroy);
    model.step(.25);
    assert.equal(primary.snapshot, model.getSnapshot());
    assert.equal(primary.snapshot.minutes, 1.5);
    assert.equal(observer.snapshot, finalObserverSnapshot, 'destroyed view no longer receives updates');
    primary.destroy();
    assert.equal(subscriptions, 0);
    model.step(.25);
    assert.equal(model.getSnapshot().minutes, 1.75, 'the host still owns the live model after both views are removed');
    assert.equal(commands, 1);
  } finally { observer.destroy(); primary.destroy(); model.destroy(); dom.window.close(); }
});

test('external adapter meter uses supported offline rendering; missing/stale differs from measured zero', () => {
  const engine = new FakePumpEngine(), adapter = createExternalAdapter(engine);
  function assertMeter(valid,text) {
    const dom = render(adapter,'meter','flow-meter');
    try {
      const root = dom.window.document.querySelector('.scada-component');
      assert.equal(root.dataset.readingValid,String(valid));
      assert.equal(root.querySelector('[data-scada-reading="value"]').textContent,text);
      if (!valid) assert.match(root.getAttribute('aria-label'),/value unavailable/);
    } finally { dom.window.close(); }
  }
  assertMeter(false,'—');
  engine.publishSample(sample());assertMeter(true,'0');
  engine.publishSample(sample({timeSeconds:2,massFlowKgS:8}));assertMeter(true,'8');
  engine.publishSample({timeSeconds:3,valid:false});assertMeter(false,'—');
  assert.equal(adapter.getSnapshot().telemetry.pump.massFlowKgS,8);
  engine.publishSample(sample({timeSeconds:4,massFlowKgS:12000}));assertMeter(false,'—');
  assert.equal(adapter.getSnapshot().telemetry.pump.valid,true,'raw sample remains available to an appropriately ranged inspector');
  assert.equal(adapter.getSnapshot().telemetry.pump.massFlowKgS,12000);
});

test('external adapter pump offline percentages are visual placeholders; zero flow can coexist with shaft rotation', () => {
  const engine = new FakePumpEngine(), adapter = createExternalAdapter(engine);
  let dom = render(adapter,'pump','pump');
  try {
    const root=dom.window.document.querySelector('.scada-component');
    assert.equal(root.dataset.active,'false');assert.equal(root.dataset.status,'offline');
    assert.equal(root.querySelector('[data-scada-reading="speed"]').textContent,'0%');
    assert.equal(adapter.getSnapshot().telemetry.pump.speedRpm,null);
  } finally { dom.window.close(); }
  engine.publishSample(sample());dom = render(adapter,'pump','pump');
  try {
    assert.equal(dom.window.document.querySelector('.scada-component').dataset.active,'true');
    assert.equal(dom.window.document.querySelector('[data-scada-reading="speed"]').textContent,'50%');
    assert.equal(adapter.getSnapshot().flows.delivery,false);
  } finally { dom.window.close(); }
});
