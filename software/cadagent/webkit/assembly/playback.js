/** Ordered presentation over existing absolute viewer states. No timers, rendering loop or progress storage. */
export function createPlayback(context, { installOrderByStep, referenceStepIDs = [], durationMs = 1000,
    onState = () => {}, onStep = () => {} } = {}) {
  const invalid = message => { throw new Error(message); };
  const record = value => value !== null && typeof value === 'object' && !Array.isArray(value);
  if (!record(installOrderByStep) || !Array.isArray(referenceStepIDs)
      || new Set(referenceStepIDs).size !== referenceStepIDs.length
      || !Number.isFinite(durationMs) || durationMs < 100 || durationMs > 60000
      || typeof onState !== 'function' || typeof onStep !== 'function') invalid('Invalid playback configuration');
  const guide = context.guide, ids = new Set(guide.steps.map(step => step.id));
  if (referenceStepIDs.some(id => !ids.has(id))) invalid('Unknown playback reference step');
  const references = new Set(referenceStepIDs), steps = guide.steps.filter(step => !references.has(step.id));
  if (!steps.length) invalid('Playback needs an installation step');
  if (Object.keys(installOrderByStep).some(id => !ids.has(id) || references.has(id))) invalid('Unknown or reference installation order');
  const operations = []; let prior = [];
  for (const step of steps) {
    if (prior.some(name => !step.parts.includes(name))) invalid('Playback requires monotone installed membership');
    const added = step.parts.filter(name => !prior.includes(name)), order = installOrderByStep[step.id];
    if (!Object.hasOwn(installOrderByStep, step.id) || !Array.isArray(order) || !added.length
        || order.length !== added.length || new Set(order).size !== order.length || order.some(name => !added.includes(name)))
      invalid('Installation order must cover each new instance exactly once');
    const installed = [...prior];
    for (const name of order) {
      operations.push({ step, name, installed: [...installed], offset: [...(step.offsets_mm[name] || [0, 0, 0])] });
      installed.push(name);
    }
    prior = [...step.parts];
  }
  let status = 'idle', speed = 1, loop = false, elapsedMs = 0, cursor = 0, restart = true, wrap = false;
  const locate = id => { const index = operations.findIndex(op => op.step.id === id); return index < 0 ? 0 : index; };
  cursor = locate(context.current());
  const snapshot = () => ({ status, stepId: operations[cursor]?.step.id ?? null, partId: operations[cursor]?.name ?? null,
    operationIndex: cursor, elapsedMs, progress: elapsedMs / durationMs, speed, loop });
  const notify = () => onState(snapshot());
  const live = () => { if (status === 'disposed') invalid('Playback is disposed'); };
  function present() {
    const op = operations[cursor], progress = Math.min(1, elapsedMs / durationMs);
    // Future instances keep their authored transforms for includeHidden framing, but are never drawn early.
    const offsets_mm = Object.fromEntries(Object.entries(op.step.offsets_mm).map(([name, offset]) => [name, [...offset]]));
    for (const name of op.installed) offsets_mm[name] = [0, 0, 0];
    offsets_mm[op.name] = op.offset.map(value => value * (1 - progress));
    context.setCurrent(op.step.id);
    context.viewer.applyState({ visible: [...op.installed, op.name], highlight: [op.name], mode: 'solid',
      offsets_mm, selected: null, isolate: null, partModes: {} });
  }
  function begin(index) {
    cursor = index; elapsedMs = 0; restart = false; wrap = false; present();
    const op = operations[cursor];
    onStep(op.step.id, { partId: op.name, operationIndex: cursor });
  }
  const unsubscribe = context.subscribeNavigation(event => {
    if (event.type === 'dispose') { dispose(); return; }
    status = 'paused'; cursor = event.type === 'step' ? locate(event.id) : 0;
    elapsedMs = 0; restart = true; wrap = false; notify();
  });
  function dispose() {
    if (status === 'disposed') return;
    status = 'disposed'; unsubscribe(); notify();
  }
  return {
    play() {
      live();
      if (status === 'playing') return snapshot();
      if (status === 'ended') { cursor = 0; restart = true; }
      status = 'playing'; if (restart || wrap) begin(wrap ? 0 : cursor); notify(); return snapshot();
    },
    pause() { if (status === 'playing') { status = 'paused'; notify(); } return snapshot(); },
    setSpeed(value) { live(); if (!Number.isFinite(value) || value < 0.25 || value > 4) invalid('Invalid playback speed'); speed = value; notify(); return snapshot(); },
    setLoop(value) {
      live(); if (typeof value !== 'boolean') invalid('Invalid playback loop');
      loop = value; if (!loop && wrap) { wrap = false; status = 'ended'; }
      notify(); return snapshot();
    },
    tick(dtSeconds) {
      if (status === 'disposed') return snapshot();
      if (!Number.isFinite(dtSeconds) || dtSeconds < 0) invalid('Invalid playback frame delta');
      if (status !== 'playing') return snapshot();
      if (wrap) begin(0);
      let remaining = Math.min(dtSeconds, 0.1) * 1000 * speed;
      while (remaining > 0 && status === 'playing') {
        const consumed = Math.min(remaining, durationMs - elapsedMs); elapsedMs += consumed; remaining -= consumed; present();
        if (elapsedMs < durationMs) break;
        const finished = operations[cursor], next = operations[cursor + 1];
        if (!next || next.step.id !== finished.step.id) context.commitStep(finished.step.id);
        if (next) begin(cursor + 1);
        else {
          if (loop) wrap = true; else status = 'ended';
          // Keep the exact assembled terminal state visible for this frame; no same-frame catch-up into a loop.
          break;
        }
      }
      notify(); return snapshot();
    },
    getState: snapshot, dispose,
  };
}
