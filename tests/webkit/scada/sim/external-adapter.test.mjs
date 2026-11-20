import test from 'node:test';
import assert from 'node:assert/strict';
import {execFileSync} from 'node:child_process';
import {createExternalAdapter} from '../../../../software/cadagent/webkit/scada/sim/examples/external-adapter/adapter.mjs';
import {FakePumpEngine} from '../../../../software/cadagent/webkit/scada/sim/examples/external-adapter/fake-engine.mjs';

const sample = overrides => ({timeSeconds:1, valid:true, mechanicalRunning:true, speedRpm:1800, powerKW:2.5, massFlowKgS:12, fault:false, warning:false, ...overrides});
const command = (action, value) => ({action, component:'pump', arguments:{value}});

test('external example preserves raw units, observed output and distinct command setpoints', () => {
  const engine = new FakePumpEngine(), adapter = createExternalAdapter(engine, {readOnly:false});
  engine.publishSample(sample());
  adapter.dispatch(command('setSpeedPercent', 75));
  const result = adapter.getSnapshot();
  assert.equal(engine.read().request.speedRpm, 2700);
  assert.equal(result.controls.pump.speedPercent, 75);
  assert.equal(result.components.pump.speed, 50);
  assert.equal(result.components.pump.load, 25);
  assert.equal(result.telemetry.pump.massFlowKgS, 12);
  assert.equal(result.telemetry.pump.units.massFlowKgS, 'kg/s');
  assert.equal(result.seconds, 1);
  assert.equal(Object.isFrozen(result.telemetry.pump.units), true);
  engine.publishSample(sample({timeSeconds:2, speedRpm:5400, powerKW:15, massFlowKgS:-3}));
  const high = adapter.getSnapshot();
  assert.equal(high.components.pump.speed, 100);
  assert.equal(high.components.pump.load, 100);
  assert.equal(high.components.pump.status, 'warning');
  assert.equal(high.telemetry.pump.speedRpm, 5400);
  assert.equal(high.telemetry.pump.massFlowKgS, -3);
});

test('missing and stale raw observations stay unavailable while valid zero remains distinct', () => {
  const engine = new FakePumpEngine(), adapter = createExternalAdapter(engine);
  assert.equal(adapter.getSnapshot().telemetry.pump.massFlowKgS, null);
  assert.equal(adapter.getSnapshot().components.pump.status, 'offline');
  assert.equal(adapter.getSnapshot().components.meter.status, 'offline');
  assert.equal(Object.hasOwn(adapter.getSnapshot().flows, 'delivery'), false);
  engine.publishSample(sample({massFlowKgS:0}));
  assert.equal(adapter.getSnapshot().flows.delivery, false);
  assert.equal(adapter.getSnapshot().components.meter.value, 0);
  assert.equal(adapter.getSnapshot().components.meter.active, true);
  assert.equal(adapter.getSnapshot().components.pump.active, true, 'a rotating shaft does not prove material flow');
  engine.publishSample({timeSeconds:4, valid:false});
  const stale = adapter.getSnapshot();
  assert.equal(stale.telemetry.pump.massFlowKgS, 0);
  assert.equal(stale.telemetry.pump.lastValidTimeSeconds, 1);
  assert.equal(stale.telemetry.pump.valid, false);
  assert.equal(stale.components.pump.active, false);
  assert.equal(stale.components.meter.active, false);
  assert.equal(Object.hasOwn(stale.flows, 'delivery'), false);
  engine.publishSample(sample({timeSeconds:5, massFlowKgS:8}));
  assert.equal(adapter.getSnapshot().telemetry.pump.valid, true);
  assert.equal(adapter.getSnapshot().telemetry.pump.massFlowKgS, 8);
});

test('read-only adapters omit dispatch and rejected inputs leave the fake engine untouched', () => {
  const engine = new FakePumpEngine(), adapter = createExternalAdapter(engine, {readOnly:false});
  assert.equal(Object.hasOwn(createExternalAdapter(engine), 'dispatch'), false);
  const before = engine.read();
  for (const invalid of [command('setSpeedPercent', -1), command('setSpeedPercent', NaN), command('setEnabled', 1), command('repair', true), command('setFault', 'seized'), {...command('setEnabled', true), component:'other'}, {...command('setEnabled', false), arguments:{equipment:'other', value:false}}, {...command('setSpeedPercent', 1), extra:1}]) {
    assert.throws(() => adapter.dispatch(invalid)); assert.equal(engine.read(), before);
  }
  assert.throws(() => engine.publishSample(sample({speedRpm:Infinity})));
  assert.equal(engine.read(), before);
  assert.throws(() => createExternalAdapter(engine, {ratedSpeedRpm:0}));
  adapter.dispatch(command('setEnabled', false));
  assert.equal(engine.read().request.enabled, false);
});

test('two views share one source; unsubscribe is idempotent and does not own engine lifetime', () => {
  const engine = new FakePumpEngine(), first = createExternalAdapter(engine), second = createExternalAdapter(engine);
  const seenA = [], seenB = [];
  const removeA = first.subscribe((state, event) => seenA.push([state, event]));
  const removeB = second.subscribe(state => seenB.push(state));
  assert.equal(engine.subscriberCount, 2);
  assert.equal(seenA.length, 0, 'subscribe does not emit or advance time');
  engine.publishSample(sample());
  assert.deepEqual(seenA[0][0], seenB[0]);
  assert.equal(seenA[0][1].type, 'sample');
  removeA(); removeA();
  engine.setRunning(false);
  assert.equal(seenA.length, 1);
  assert.equal(seenB.at(-1).components.pump.running, false);
  assert.equal(seenB.at(-1).telemetry.pump.massFlowKgS, 12);
  removeB();
  assert.equal(engine.subscriberCount, 0);
  engine.publishSample(sample({timeSeconds:2}));
  assert.equal(engine.read().timeSeconds, 2);
});

test('detached example import, subscription and commands require no UI, IO or automatic clock', () => {
  const adapterUrl = new URL('../../../../software/cadagent/webkit/scada/sim/examples/external-adapter/adapter.mjs', import.meta.url).href;
  const engineUrl = new URL('../../../../software/cadagent/webkit/scada/sim/examples/external-adapter/fake-engine.mjs', import.meta.url).href;
  const script = `for(const key of ['setInterval','setTimeout','fetch'])globalThis[key]=()=>{throw Error('unexpected '+key)};for(const key of ['window','document','localStorage'])Object.defineProperty(globalThis,key,{get(){throw Error('browser access')}});const {createExternalAdapter}=await import(${JSON.stringify(adapterUrl)});const {FakePumpEngine}=await import(${JSON.stringify(engineUrl)});const engine=new FakePumpEngine();const adapter=createExternalAdapter(engine,{readOnly:false});const remove=adapter.subscribe(()=>{});adapter.dispatch({action:'setEnabled',component:'pump',arguments:{value:false}});remove();adapter.getSnapshot();`;
  execFileSync(process.execPath, ['--input-type=module', '-e', script]);
});
