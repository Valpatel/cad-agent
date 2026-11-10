import assert from 'node:assert/strict';
import test from 'node:test';
import { createGuideController, createGuidePlayback } from '../../../software/cadagent/webkit/assembly/guide.js';

function fixture() {
  const names = ['foundation', 'pin-A', 'pin-B'];
  const viewer = { parts: names.map(name => ({ name, file: name + '.stl', sha256: '1'.repeat(64), bounds_mm: [0, 0, 0, 10, 20, 30] })),
    states: [], applyState(state) { this.states.push(structuredClone(state)); }, frameParts() {}, reset() {}, dispose() { this.disposed = true; } };
  const guide = { schema: 'cad-agent.assembly-guide/1', snapshot: { id: 'frozen', revision: '1', status: 'released', source_commit: 'a'.repeat(40) },
    model: { file: 'view.json', sha256: '1'.repeat(64) }, subassemblies: [{ id: 'frame', title: 'Frame', parts: names }], steps: [
      { id: 'overview', title: 'Reference', text: 'Reference only.', subassembly: 'frame', parts: names, highlight: [], offsets_mm: {} },
      { id: 'base', title: 'Foundation', text: 'Place foundation.', subassembly: 'frame', parts: ['foundation'], highlight: ['foundation'], offsets_mm: {} },
      { id: 'pins', title: 'Pins', text: 'Fit B then A.', subassembly: 'frame', parts: names, highlight: ['pin-A', 'pin-B'], offsets_mm: { 'pin-A': [10, 0, 0], 'pin-B': [0, 0, 40] } },
    ] };
  return { guide, viewer, controller: createGuideController(viewer, guide),
    options: { referenceStepIDs: ['overview'], installOrderByStep: { base: ['foundation'], pins: ['pin-B', 'pin-A'] }, durationMs: 400 } };
}
const last = viewer => viewer.states.at(-1);
test('explicit B-before-A order moves one authored instance absolutely; foundation stays static', () => {
  const f = fixture(), events = [], player = createGuidePlayback(f.controller, { ...f.options, onStep: (id, operation) => events.push([id, operation.partId]) });
  player.play();
  assert.deepEqual(last(f.viewer).visible, ['foundation']); assert.deepEqual(last(f.viewer).offsets_mm.foundation, [0, 0, 0]);
  for (let i = 0; i < 4; i++) player.tick(0.1);
  assert.deepEqual(last(f.viewer).visible, ['foundation', 'pin-B']);
  assert.deepEqual(last(f.viewer).offsets_mm['pin-B'], [0, 0, 40]);
  assert.deepEqual(last(f.viewer).offsets_mm['pin-A'], [10, 0, 0], 'hidden future part retains authored framing pose');
  player.tick(0.1); assert.deepEqual(last(f.viewer).offsets_mm['pin-B'], [0, 0, 30]);
  player.setSpeed(2); player.tick(0.1); assert.deepEqual(last(f.viewer).offsets_mm['pin-B'], [0, 0, 10]);
  player.pause(); const pose = structuredClone(last(f.viewer)); player.tick(1000); assert.deepEqual(last(f.viewer), pose);
  player.play(); player.tick(0.05); assert.deepEqual(last(f.viewer).visible, ['foundation', 'pin-B', 'pin-A']);
  assert.deepEqual(last(f.viewer).offsets_mm['pin-B'], [0, 0, 0]);
  assert.deepEqual(last(f.viewer).offsets_mm['pin-A'], [10, 0, 0]);
  player.tick(0.1); assert.deepEqual(last(f.viewer).offsets_mm['pin-A'], [5, 0, 0]);
  player.tick(0.1); assert.equal(player.getState().status, 'ended');
  assert.deepEqual(last(f.viewer).offsets_mm, { 'pin-A': [0, 0, 0], 'pin-B': [0, 0, 0] });
  assert.deepEqual(events, [['base', 'foundation'], ['pins', 'pin-B'], ['pins', 'pin-A']]);
  assert.equal(f.controller.current, 'pins');
  player.play(); assert.equal(player.getState().stepId, 'base', 'terminal Play restarts first installation');
});
test('manual navigation pauses/restarts selected step; loop preserves exact assembled terminal frame', () => {
  const f = fixture(), player = createGuidePlayback(f.controller, f.options);
  f.controller.applyStep('pins'); assert.equal(player.getState().status, 'paused');
  player.play(); assert.equal(player.getState().partId, 'pin-B');
  assert.deepEqual(last(f.viewer).visible, ['foundation', 'pin-B']);
  f.controller.applyStep('overview'); player.play(); assert.equal(player.getState().stepId, 'base');
  player.setLoop(true); player.setSpeed(4);
  for (let i = 0; i < 3; i++) player.tick(0.1);
  assert.equal(player.getState().status, 'playing'); assert.equal(player.getState().progress, 1);
  assert.deepEqual(last(f.viewer).offsets_mm, { 'pin-A': [0, 0, 0], 'pin-B': [0, 0, 0] });
  player.setLoop(false); assert.equal(player.getState().status, 'ended');
  player.setLoop(true); player.play(); for (let i = 0; i < 3; i++) player.tick(0.1);
  player.tick(0); assert.equal(player.getState().stepId, 'base');
  f.controller.reset(); assert.equal(player.getState().status, 'paused'); assert.equal(f.controller.current, null);
});
test('large frame delta is clamped; invalid settings and copied state cannot mutate playback', () => {
  const f = fixture(), player = createGuidePlayback(f.controller, { ...f.options, durationMs: 1000 });
  player.play(); player.tick(100); assert.equal(player.getState().elapsedMs, 100);
  const saved = player.getState(); saved.status = 'ended'; assert.equal(player.getState().status, 'playing');
  for (const value of [0, -1, Infinity, NaN, 5]) assert.throws(() => player.setSpeed(value));
  for (const value of [0, 'true', null]) assert.throws(() => player.setLoop(value));
  for (const value of [-1, Infinity, NaN]) assert.throws(() => player.tick(value));
  assert.equal(player.getState().elapsedMs, 100);
});
test('order is complete and explicit, not manifest order or guessed compound internals', () => {
  for (const change of [
    x => delete x.installOrderByStep.pins,
    x => x.installOrderByStep.pins = ['pin-A'],
    x => x.installOrderByStep.pins = ['pin-A', 'pin-A'],
    x => x.installOrderByStep.pins = ['pin-A', 'unknown'],
    x => x.installOrderByStep.pins = ['foundation', 'pin-A', 'pin-B'],
    x => x.installOrderByStep.overview = ['foundation'],
    x => x.referenceStepIDs = ['overview', 'unknown'],
    x => x.referenceStepIDs = ['overview', 'overview'],
    x => x.durationMs = 0,
  ]) {
    const f = fixture(), options = structuredClone(f.options); change(options);
    assert.throws(() => createGuidePlayback(f.controller, options)); assert.equal(f.viewer.states.length, 0);
  }
  const f = fixture(); f.guide.steps[2].parts = ['pin-A', 'pin-B'];
  const changed = createGuideController(f.viewer, f.guide);
  assert.throws(() => createGuidePlayback(changed, f.options), /monotone/);
});
test('controller has one player owner; disposal unsubscribes without owning viewer lifetime', () => {
  const f = fixture(), states = [], player = createGuidePlayback(f.controller, { ...f.options, onState: s => states.push(s.status) });
  assert.throws(() => createGuidePlayback(f.controller, f.options), /owner/);
  player.play(); player.dispose(); const count = states.length;
  player.dispose(); player.tick(1); f.controller.applyStep('pins');
  assert.equal(states.length, count); assert.equal(f.viewer.disposed, undefined);
  assert.throws(() => player.play(), /disposed/);
  const replacement = createGuidePlayback(f.controller, f.options); replacement.play(); f.controller.dispose();
  assert.equal(replacement.getState().status, 'disposed'); assert.equal(f.viewer.disposed, true);
  assert.throws(() => f.controller.applyStep('pins'), /disposed/);
});
test('prototype-shaped exact instance names keep their own authored offsets', () => {
  for (const special of ['constructor', '__proto__']) {
    const f = fixture();
    for (const p of f.viewer.parts) if (p.name === 'pin-B') p.name = special;
    f.guide.subassemblies[0].parts = ['foundation', 'pin-A', special];
    for (const step of f.guide.steps) {
      step.parts = step.parts.map(name => name === 'pin-B' ? special : name);
      step.highlight = step.highlight.map(name => name === 'pin-B' ? special : name);
      step.offsets_mm = Object.fromEntries(Object.entries(step.offsets_mm).map(([name, offset]) => [name === 'pin-B' ? special : name, offset]));
    }
    const controller = createGuideController(f.viewer, f.guide);
    const player = createGuidePlayback(controller, { ...f.options, installOrderByStep: { base: ['foundation'], pins: [special, 'pin-A'] } });
    player.play(); for (let i = 0; i < 5; i++) player.tick(0.1);
    assert.ok(Object.hasOwn(last(f.viewer).offsets_mm, special));
    assert.deepEqual(last(f.viewer).offsets_mm[special], [0, 0, 30]);
    assert.equal(Object.getPrototypeOf(last(f.viewer).offsets_mm), Object.prototype);
  }
});
test('controller disposal still releases the viewer if a player observer throws', () => {
  const f = fixture(); createGuidePlayback(f.controller, { ...f.options, onState: state => { if (state.status === 'disposed') throw new Error('observer failure'); } });
  assert.throws(() => f.controller.dispose(), /observer failure/); assert.equal(f.viewer.disposed, true);
  f.controller.dispose();
});
