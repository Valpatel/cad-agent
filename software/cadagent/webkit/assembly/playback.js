/** Ordered presentation over existing absolute viewer states. No timers, rendering loop or progress storage. */
export function createPlayback(context, { installOrderByStep, referenceStepIDs = [], durationMs = 1000,
    onState = () => {}, onStep = () => {} } = {}) {
  if (context.plan) return createPlanPlayback(context, { durationMs, onState, onStep });
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
      operations.push({ step, name, installed: [...installed], offset: [...(Object.hasOwn(step.offsets_mm, name) ? step.offsets_mm[name] : [0, 0, 0])] });
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
    const offsets = new Map(Object.entries(op.step.offsets_mm).map(([name, offset]) => [name, [...offset]]));
    for (const name of op.installed) offsets.set(name, [0, 0, 0]);
    offsets.set(op.name, op.offset.map(value => value * (1 - progress)));
    context.setCurrent(op.step.id);
    context.viewer.applyState({ visible: [...op.installed, op.name], highlight: [op.name], mode: 'solid',
      offsets_mm: Object.fromEntries(offsets), selected: null, isolate: null, partModes: {} });
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

/** Canonical bounded serial intent. Kept beside the existing playback owner; no scheduler or renderer. */
export function normalizePlan(value, { meshHashes } = {}) {
  const bad = message => { throw new Error(`assembly plan: ${message}`); };
  const obj = v => v !== null && typeof v === 'object' && !Array.isArray(v);
  const fields = (v, allowed) => { if (!obj(v) || Object.keys(v).some(k => !allowed.includes(k)) || allowed.some(k => !Object.hasOwn(v, k))) bad('missing or unsupported fields'); };
  const text = v => typeof v === 'string' && v.trim() && v.length <= 2000;
  const finite = v => Number.isFinite(v) && Math.abs(v) <= 1e9;
  const vector = v => Array.isArray(v) && v.length === 3 && v.every(finite);
  const hash = v => typeof v === 'string' && /^[0-9a-f]{64}$/.test(v);
  const refs = (v, allowed, nonempty = false) => {
    if (!Array.isArray(v) || (nonempty && !v.length) || v.length > 2000 || v.some(n => typeof n !== 'string' || !allowed.has(n)) || new Set(v).size !== v.length) bad('unknown, duplicate or missing members');
  };
  fields(value, ['schema', 'units', 'frame', 'source', 'fixed', 'operations', 'clearance_mm']);
  if (value.schema !== 'cad-agent.assembly-plan/1' || value.units !== 'mm' || value.frame !== 'assembly-home/z-up') bad('unsupported schema/units/frame');
  if (!finite(value.clearance_mm) || value.clearance_mm < 0) bad('finite nonnegative clearance allowance required');
  const source = value.source;
  fields(source, ['revision', 'closure_sha256', 'producer', 'instances', 'tooling_sha256']);
  if (typeof source.revision !== 'string' || !/^[0-9a-f]{40}$/.test(source.revision) || !hash(source.tooling_sha256) || !hash(source.closure_sha256) || !text(source.producer) || !obj(source.instances) || !Object.keys(source.instances).length || Object.keys(source.instances).length > 2000) bad('exact source closure/producer required');
  const names = new Set(Object.keys(source.instances));
  for (const [name, entry] of Object.entries(source.instances)) {
    fields(entry, ['mesh_sha256', 'brep_sha256', 'matrix']);
    if (!text(name) || name.length > 200 || !hash(entry.mesh_sha256) || !hash(entry.brep_sha256)) bad('invalid source instance');
    const m = entry.matrix;
    if (!Array.isArray(m) || m.length !== 12 || !m.every(finite)) bad('invalid placement');
    const rows = [m.slice(0, 3), m.slice(4, 7), m.slice(8, 11)];
    for (let i = 0; i < 3; i++) for (let j = 0; j < 3; j++) if (Math.abs(rows[i].reduce((n, a, k) => n + a * rows[j][k], 0) - Number(i === j)) > 1e-7) bad('nonrigid placement');
    const [a, b, c] = rows;
    if (Math.abs(a[0]*(b[1]*c[2]-b[2]*c[1])-a[1]*(b[0]*c[2]-b[2]*c[0])+a[2]*(b[0]*c[1]-b[1]*c[0])-1) > 1e-7) bad('reflected placement');
  }
  if (meshHashes && (Object.keys(meshHashes).length !== names.size || Object.entries(meshHashes).some(([n, h]) => !names.has(n) || source.instances[n].mesh_sha256 !== h))) bad('stale or ambiguous mesh/source membership');
  refs(value.fixed, names, true);
  const owned = new Set(value.fixed), seen = new Set(); let previous;
  if (!Array.isArray(value.operations) || !value.operations.length || value.operations.length > 2000) bad('needs serial operations');
  for (const op of value.operations) {
    fields(op, ['id', 'type', 'members', 'requires', 'path_mm', 'intent', 'tools']);
    if (typeof op.id !== 'string' || !/^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$/.test(op.id) || seen.has(op.id) || op.type !== 'translate') bad('duplicate identity or unsupported operation');
    refs(op.requires, seen);
    if (previous !== undefined && !op.requires.includes(previous)) bad('serial predecessor dependency required');
    refs(op.members, names, true);
    if (op.members.some(n => owned.has(n))) bad('overlapping rigid ownership');
    op.members.forEach(n => owned.add(n));
    const path = op.path_mm;
    if (!Array.isArray(path) || path.length < 2 || path.length > 256 || !path.every(vector) || path.at(-1).some(n => n !== 0) || !path[0].some(n => n !== 0) || path.slice(1).some((v, i) => v.every((n, k) => n === path[i][k]))) bad('finite nonzero piecewise path to home required');
    if (!text(op.intent)) bad('independent intent reference required');
    if (!Array.isArray(op.tools) || op.tools.length > 32) bad('invalid tool references');
    const tools = new Set();
    for (const tool of op.tools) {
      fields(tool, ['fastener', 'tool', 'approach_mm']);
      if (!op.members.includes(tool.fastener) || !text(tool.tool) || tools.has(tool.fastener) || !finite(tool.approach_mm) || tool.approach_mm <= 0) bad('tool needs moving fastener and finite axial approach');
      tools.add(tool.fastener);
    }
    seen.add(op.id); previous = op.id;
  }
  if (owned.size !== names.size) bad('exact checked/fixed instance closure required');
  const freeze = v => { if (v && typeof v === 'object') { Object.values(v).forEach(freeze); Object.freeze(v); } return v; };
  return freeze(structuredClone(value));
}

/** Installation position [0,n]. Disassembly is evaluated at n-position, including operation order. */
export function planState(plan, position) {
  if (!Number.isFinite(position) || position < 0 || position > plan.operations.length) throw new Error('assembly plan: invalid seek');
  const offsets = new Map(plan.fixed.map(n => [n, [0, 0, 0]]));
  plan.operations.forEach((op, index) => {
    const path = op.path_mm, lengths = path.slice(1).map((b, i) => Math.hypot(...b.map((n, k) => n - path[i][k])));
    let distance = Math.max(0, Math.min(1, position - index)) * lengths.reduce((a, b) => a + b, 0), offset = [...path.at(-1)];
    for (let i = 0; i < lengths.length; i++) {
      if (distance <= lengths[i]) { offset = path[i].map((n, k) => n + (path[i + 1][k] - n) * distance / lengths[i]); break; }
      distance -= lengths[i];
    }
    op.members.forEach(n => offsets.set(n, [...offset]));
  });
  return Object.fromEntries(offsets);
}

/** Desired CAD-root poses from immutable rest; parent changes are inverted exactly once. */
export function createPlanPoseAdapter(THREE, root, parts) {
  root.updateWorldMatrix(true, true);
  const inverse = root.matrixWorld.clone().invert();
  const rest = new Map(parts.map(({ name, mesh }) => [name, inverse.clone().multiply(mesh.matrixWorld)]));
  return offsets => {
    root.updateWorldMatrix(true, true);
    for (const { name, mesh } of parts) {
      if (!Object.hasOwn(offsets, name)) throw new Error(`assembly plan: missing pose ${name}`);
      const desired = root.matrixWorld.clone().multiply(new THREE.Matrix4().makeTranslation(...offsets[name])).multiply(rest.get(name));
      mesh.parent.updateWorldMatrix(true, false);
      mesh.matrix.copy(mesh.parent.matrixWorld).invert().multiply(desired);
      mesh.matrix.decompose(mesh.position, mesh.quaternion, mesh.scale);
      mesh.updateMatrixWorld(true);
    }
  };
}

/** Uses the existing caller's ticks. Absolute seeking/reversal never resamples exploded rest poses. */
export function createPlanPlayback(context, { durationMs = 1000, onState = () => {}, onStep = () => {} } = {}) {
  if (!Number.isFinite(durationMs) || durationMs < 100 || durationMs > 60000 || typeof onState !== 'function' || typeof onStep !== 'function') throw new Error('Invalid plan playback configuration');
  const plan = context.plan, n = plan.operations.length;
  let position = 0, direction = 1, status = 'idle', speed = 1, loop = false;
  const live = () => { if (status === 'disposed') throw new Error('Playback is disposed'); };
  const index = () => Math.min(n - 1, Math.max(0, direction > 0 ? Math.floor(position) : Math.ceil(position) - 1));
  const snapshot = () => ({ status, position, direction, speed, loop, operationIndex: index(), stepId: plan.operations[index()].id, progress: position / n });
  const notify = () => onState(snapshot());
  function present() {
    const op = plan.operations[index()]; context.setCurrent(op.id);
    context.viewer.applyState({ visible: Object.keys(plan.source.instances), highlight: [...op.members], mode: 'solid', offsets_mm: planState(plan, position), selected: null, isolate: null, partModes: {} });
  }
  const unsubscribe = context.subscribeNavigation(event => {
    if (event.type === 'dispose') return dispose();
    status = 'paused'; position = event.type === 'step' ? plan.operations.findIndex(op => op.id === event.id) : n;
    if (position < 0) position = 0;
    notify();
  });
  function dispose() { if (status === 'disposed') return; status = 'disposed'; unsubscribe(); notify(); }
  return {
    play() { live(); if (status === 'ended' || (status === 'idle' && position === n && direction > 0)) position = direction > 0 ? 0 : n; status = 'playing'; present(); notify(); return snapshot(); },
    pause() { live(); if (status === 'playing') status = 'paused'; notify(); return snapshot(); },
    reverse() { live(); direction *= -1; if (status === 'ended') status = 'paused'; present(); notify(); return snapshot(); },
    seek(value) { live(); planState(plan, value); position = value; if (status === 'ended') status = 'paused'; present(); notify(); return snapshot(); },
    reset() { live(); status = 'idle'; position = n; present(); notify(); return snapshot(); },
    setSpeed(value) { live(); if (!Number.isFinite(value) || value < 0.25 || value > 4) throw new Error('Invalid playback speed'); speed = value; notify(); return snapshot(); },
    setLoop(value) { live(); if (typeof value !== 'boolean') throw new Error('Invalid playback loop'); loop = value; notify(); return snapshot(); },
    tick(dt) {
      if (status === 'disposed') return snapshot();
      if (!Number.isFinite(dt) || dt < 0) throw new Error('Invalid playback frame delta');
      if (status !== 'playing') return snapshot();
      const before = index(); position = Math.max(0, Math.min(n, position + direction * Math.min(dt, 0.1) * 1000 * speed / durationMs));
      present(); if (before !== index()) onStep(plan.operations[index()].id, { operationIndex: index() });
      if (position === (direction > 0 ? n : 0)) { status = loop ? 'playing' : 'ended'; if (loop) direction *= -1; }
      notify(); return snapshot();
    }, getState: snapshot, dispose,
  };
}
