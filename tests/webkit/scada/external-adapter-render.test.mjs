import test from 'node:test';
import assert from 'node:assert/strict';
import {JSDOM} from './dependencies.mjs';
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
