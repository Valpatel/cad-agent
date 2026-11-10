/** Optional instructions for the existing viewer. Geometry is already assembled, mm / z-up. */
export const GUIDE_SCHEMA = 'cad-agent.assembly-guide/1';
const hashPattern = /^[0-9a-f]{64}$/;
const idPattern = /^[a-zA-Z0-9][a-zA-Z0-9_.-]{0,127}$/;
const record = value => value !== null && typeof value === 'object' && !Array.isArray(value);
const fail = text => { throw new Error(text); };
const keys = (value, allowed, where) => {
  if (!record(value)) fail(`${where} must be an object`);
  for (const key of Object.keys(value)) if (!allowed.includes(key)) fail(`${where}: unknown field ${key}`);
};
const text = (value, where, max = 4000) => {
  if (typeof value !== 'string' || !value.trim() || value.length > max) fail(`${where} must be nonempty text`);
};
const id = (value, where) => { if (typeof value !== 'string' || !idPattern.test(value)) fail(`${where}: invalid ID`); };
const vec = (value, where, nonzero = false) => {
  if (!Array.isArray(value) || value.length !== 3 || !value.every(Number.isFinite)
      || value.some(n => Math.abs(n) > 1e9) || (nonzero && !value.some(n => n !== 0))) fail(`${where}: invalid vector`);
};
function refs(value, allowed, where, nonempty = false) {
  if (!Array.isArray(value) || (nonempty && !value.length) || value.length > 2000
      || value.some(n => typeof n !== 'string' || !allowed.has(n)) || new Set(value).size !== value.length)
    fail(`${where}: unknown, duplicate or missing members`);
}
/** Data URLs are local relative references. ../ is allowed; release packaging enforces its project boundary. */
export function assetURL(file, base, root) {
  if (typeof file !== 'string' || !file || file.length > 2000 || /[\\\x00-\x20?#]/.test(file)
      || /^(?:[a-z][a-z0-9+.-]*:|\/)/i.test(file)) fail('Asset must be a relative local path');
  // Reject encoded separators/dots, so containment checks cannot differ from a static server's decoding.
  if (/%(?:2e|2f|5c|00)/i.test(file)) fail('Encoded asset path traversal is unsupported');
  const baseURL = new URL(base), url = new URL(file, baseURL);
  if (url.origin !== baseURL.origin || url.username || url.password) fail('Asset changes origin');
  if (root) {
    const boundary = new URL(root, baseURL);
    if (url.origin !== boundary.origin || !url.pathname.startsWith(boundary.pathname.endsWith('/') ? boundary.pathname : boundary.pathname + '/'))
      fail('Asset escapes the bundle');
  }
  return url;
}
/** Ordinary viewers keep URL()/fetch semantics, including root/absolute and external CORS URLs.
 * Guide data remains relative-only. An explicit assetRoot narrows either mode to the caller's bundle. */
export function viewAssetURL(file, base, { guide = false, assetRoot } = {}) {
  if (guide) return assetURL(file, base, assetRoot);
  if (typeof file !== 'string' || !file.trim() || file.length > 2000 || /[\\\x00-\x1f\x7f]/.test(file)) fail('Invalid model asset URL');
  const url = new URL(file, base);
  if (!['http:', 'https:'].includes(url.protocol) || url.username || url.password) fail('Invalid model asset URL');
  if (assetRoot) {
    const root = new URL(assetRoot, base);
    if (/%(?:2e|2f|5c|00)/i.test(url.pathname) || url.origin !== root.origin
        || !url.pathname.startsWith(root.pathname.endsWith('/') ? root.pathname : root.pathname + '/')) fail('Asset escapes the bundle');
  }
  return url;
}
function binding(value, where) {
  keys(value, ['file', 'sha256'], where);
  assetURL(value.file, 'https://guide.invalid/bundle/guide.json');
  if (!hashPattern.test(value.sha256)) fail(`${where}: invalid SHA-256`);
}
/** Validate legacy manifests too; guide-bound manifests additionally require explicit frame and mesh hashes. */
export function validateView(manifest, { guide = false } = {}) {
  if (!record(manifest) || !Array.isArray(manifest.parts) || !manifest.parts.length || manifest.parts.length > 2000)
    fail('Model manifest needs 1..2000 parts');
  if ((guide || manifest.units !== undefined) && manifest.units !== 'mm') fail('Model units must be mm');
  if ((guide || manifest.up !== undefined) && manifest.up !== 'z') fail('Model frame must be z-up');
  const names = new Set();
  for (const p of manifest.parts) {
    if (!record(p)) fail('Invalid model part');
    text(p.name, 'Part name', 200);
    if (names.has(p.name)) fail(`Duplicate model part ${p.name}`);
    names.add(p.name);
    viewAssetURL(p.file, 'https://guide.invalid/view.json', { guide });
    if (!Array.isArray(p.bounds_mm) || p.bounds_mm.length !== 6 || !p.bounds_mm.every(Number.isFinite)
        || p.bounds_mm.some(n => Math.abs(n) > 1e9) || [0, 1, 2].some(i => p.bounds_mm[i] > p.bounds_mm[i + 3])) fail(`Invalid bounds for ${p.name}`);
    if (p.color !== undefined && !(typeof p.color === 'string' && (guide ? /^#[0-9a-f]{6}$/i.test(p.color) : p.color.trim().length > 0 && p.color.length <= 128))
        && !(Number.isInteger(p.color) && p.color >= 0 && p.color <= 0xffffff)) fail(`Invalid color for ${p.name}`);
    if (p.visible !== undefined && typeof p.visible !== 'boolean') fail(`Invalid visibility for ${p.name}`);
    if (p.explode !== undefined && p.explode !== null) vec(p.explode, 'Explode direction', true);
    if ((guide || p.sha256 !== undefined) && !hashPattern.test(p.sha256)) fail(`Missing or invalid mesh SHA-256 for ${p.name}`);
  }
  return manifest;
}
export function validateGuide(guide, manifest) {
  keys(guide, ['schema', 'snapshot', 'model', 'subassemblies', 'steps', 'source'], 'Guide');
  if (guide.schema !== GUIDE_SCHEMA) fail('Unsupported assembly guide schema');
  keys(guide.snapshot, ['id', 'revision', 'status', 'source_commit'], 'Snapshot');
  id(guide.snapshot.id, 'Snapshot'); text(guide.snapshot.revision, 'Revision', 200);
  if (!['released', 'wip'].includes(guide.snapshot.status) || !/^[0-9a-f]{40}$/.test(guide.snapshot.source_commit)) fail('Invalid snapshot status/source commit');
  if (guide.source !== undefined && !record(guide.source)) fail('Guide source metadata must be an object');
  binding(guide.model, 'Model');
  validateView(manifest, { guide: true });
  const names = new Set(manifest.parts.map(p => p.name)), groups = new Map();
  if (!Array.isArray(guide.subassemblies) || !guide.subassemblies.length || guide.subassemblies.length > 2000) fail('Guide needs subassemblies');
  for (const group of guide.subassemblies) {
    keys(group, ['id', 'title', 'parts'], 'Subassembly'); id(group.id, 'Subassembly'); text(group.title, 'Subassembly title');
    if (groups.has(group.id)) fail('Duplicate subassembly');
    refs(group.parts, names, 'Subassembly parts', true); groups.set(group.id, new Set(group.parts));
  }
  if (!Array.isArray(guide.steps) || !guide.steps.length || guide.steps.length > 2000) fail('Guide needs 1..2000 steps');
  const seen = new Set();
  for (const step of guide.steps) {
    keys(step, ['id', 'title', 'subassembly', 'parts', 'highlight', 'offsets_mm', 'text', 'poster', 'camera', 'requires'], 'Step');
    id(step.id, 'Step'); text(step.title, 'Step title'); text(step.text, 'Step instruction', 20000);
    if (seen.has(step.id)) fail('Duplicate step');
    const members = groups.get(step.subassembly);
    if (!members) fail('Unknown step subassembly');
    refs(step.parts, names, 'Step parts', true); refs(step.highlight, new Set(step.parts), 'Step highlight');
    refs(step.highlight, members, 'Highlighted subassembly members');
    keys(step.offsets_mm, step.parts, 'Step offsets');
    for (const offset of Object.values(step.offsets_mm)) vec(offset, 'CAD offset');
    if (step.camera !== undefined) { keys(step.camera, ['direction'], 'Camera'); vec(step.camera.direction, 'Camera direction', true); }
    if (step.poster !== undefined) binding(step.poster, 'Poster');
    if (step.requires !== undefined) refs(step.requires, seen, 'Step prerequisites');
    seen.add(step.id);
  }
  return guide;
}
export async function sha256(bytes) {
  return [...new Uint8Array(await crypto.subtle.digest('SHA-256', bytes))].map(b => b.toString(16).padStart(2, '0')).join('');
}
/** Deadline includes headers and streamed body. Abort never publishes a late completion. */
export async function readAsset(url, { signal, fetcher = fetch, timeoutMs = 15000, maxBytes = 128 * 1024 * 1024, expectedHash, redirect = 'error' } = {}) {
  if (!['error', 'follow'].includes(redirect)) fail('Invalid redirect policy');
  if (!Number.isFinite(timeoutMs) || timeoutMs <= 0 || !Number.isSafeInteger(maxBytes) || maxBytes <= 0) fail('Invalid asset limits');
  const controller = new AbortController();
  const abort = () => controller.abort(signal?.reason);
  signal?.addEventListener('abort', abort, { once: true });
  if (signal?.aborted) abort();
  const timer = setTimeout(() => controller.abort(new Error('Asset download timed out')), timeoutMs);
  let reader;
  const operation = async () => {
    controller.signal.throwIfAborted();
    const response = await fetcher(url, { signal: controller.signal, redirect });
    controller.signal.throwIfAborted();
    if (!response.ok) fail(`Asset HTTP ${response.status}`);
    if (Number(response.headers.get('content-length')) > maxBytes) fail('Asset exceeds byte limit');
    reader = response.body?.getReader();
    if (!reader) fail('Asset has no readable body');
    const chunks = []; let size = 0;
    for (;;) {
      const { value, done } = await reader.read(); controller.signal.throwIfAborted();
      if (done) break;
      size += value.byteLength; if (size > maxBytes) fail('Asset exceeds byte limit'); chunks.push(value);
    }
    const bytes = new Uint8Array(size); let offset = 0;
    for (const chunk of chunks) { bytes.set(chunk, offset); offset += chunk.byteLength; }
    if (expectedHash && await sha256(bytes) !== expectedHash) fail('Asset SHA-256 mismatch');
    controller.signal.throwIfAborted();
    return bytes.buffer;
  };
  let onAbort;
  try {
    const cancelled = new Promise((_, reject) => { onAbort = () => reject(controller.signal.reason || new DOMException('Aborted', 'AbortError')); controller.signal.addEventListener('abort', onAbort, { once: true }); });
    return await Promise.race([operation(), cancelled]);
  } finally {
    clearTimeout(timer); signal?.removeEventListener('abort', abort); controller.signal.removeEventListener('abort', onAbort);
    controller.abort();
    if (reader) { try { reader.cancel().catch(() => {}); } catch {} }
  }
}
export function parseJSON(bytes) {
  try { return JSON.parse(new TextDecoder('utf-8', { fatal: true }).decode(bytes)); }
  catch { fail('Asset is not valid JSON'); }
}
export async function loadGuide(url, options = {}) {
  const guideURL = new URL(url, globalThis.location?.href || 'https://guide.invalid/');
  const guide = parseJSON(await readAsset(guideURL, { ...options, redirect: 'error', maxBytes: 2 * 1024 * 1024 }));
  if (!record(guide)) fail('Guide must be an object');
  binding(guide.model, 'Model');
  const manifestUrl = assetURL(guide.model.file, guideURL, options.assetRoot);
  const manifest = parseJSON(await readAsset(manifestUrl, { ...options, redirect: 'error', expectedHash: guide.model.sha256, maxBytes: 2 * 1024 * 1024 }));
  validateGuide(guide, manifest);
  // Validate every referenced URL before the renderer starts fetching mesh data.
  for (const part of manifest.parts) assetURL(part.file, manifestUrl, options.assetRoot);
  for (const step of guide.steps) if (step.poster) assetURL(step.poster.file, guideURL, options.assetRoot);
  return { guide, manifest, manifestUrl: manifestUrl.href, guideUrl: guideURL.href };
}
/** Absolute state, so backward/direct navigation cannot accumulate a translation or material change. */
export function stepState(guide, id, { explode = 1, mode = 'ghost' } = {}) {
  if (!Number.isFinite(explode) || explode < 0 || explode > 1 || !['solid', 'ghost', 'wireframe'].includes(mode)) fail('Invalid instruction presentation');
  const step = guide.steps.find(s => s.id === id);
  if (!step) fail(`Unknown instruction step ${id}`);
  return { visible: [...step.parts], highlight: [...step.highlight], mode,
    offsets_mm: Object.fromEntries(Object.entries(step.offsets_mm).map(([name, v]) => [name, v.map(n => n * explode)])), selected: null, isolate: null, partModes: {} };
}
export function createGuideController(viewer, guide) {
  validateGuide(guide, { units: 'mm', up: 'z', parts: viewer.parts.map(({ mesh, center, ...part }) => part) });
  let current = null;
  return {
    get current() { return current; },
    applyStep(id, { frame = true, ...options } = {}) {
      const state = stepState(guide, id, options), step = guide.steps.find(s => s.id === id);
      viewer.applyState(state);
      if (frame) viewer.frameParts(step.parts, step.camera?.direction);
      current = id; return state;
    },
    reset() { viewer.reset(); current = null; },
    dispose() { current = null; viewer.dispose(); },
  };
}
/** One complete presentation state. Validation precedes all scene mutation. */
export function validateState(state, partNames) {
  keys(state, ['visible', 'highlight', 'mode', 'offsets_mm', 'selected', 'isolate', 'partModes'], 'Viewer state');
  const names = new Set(partNames);
  refs(state.visible, names, 'Visible parts'); refs(state.highlight, new Set(state.visible), 'Highlight');
  if (!['solid', 'ghost', 'wireframe'].includes(state.mode)) fail('Invalid display mode');
  keys(state.offsets_mm, [...names], 'Viewer offsets');
  for (const value of Object.values(state.offsets_mm)) vec(value, 'CAD offset');
  if (state.selected !== null && (!state.visible.includes(state.selected) || !names.has(state.selected))) fail('Unknown or hidden selection');
  if (state.isolate !== null) refs(state.isolate, new Set(state.visible), 'Isolated parts');
  if (state.partModes !== undefined) {
    keys(state.partModes, state.visible, 'Part appearances');
    if (!Object.values(state.partModes).every(mode => ['solid', 'transparent', 'wireframe'].includes(mode))) fail('Invalid part appearance');
  }
  if (state.selected !== null && state.isolate !== null && !state.isolate.includes(state.selected)) fail('Selection is outside isolation');
  return state;
}
/** Small optional controls used by viewer.html; products can keep their own page composition. */
export async function mountGuide({ app, panel, title, guideUrl, expectedHash, signal, onProgress = () => {}, assetRoot }) {
  if (expectedHash !== undefined && !hashPattern.test(expectedHash)) fail('Invalid guide SHA-256');
  const loaded = await loadGuide(guideUrl, { expectedHash, signal, assetRoot });
  const { createViewer } = await import('../viewer.js');
  let controls, syncAppearance;
  const viewer = await createViewer({ app, panel, title, manifestUrl: loaded.manifestUrl, manifest: loaded.manifest, guideBound: true, signal, onProgress, assetRoot, onStateChange: () => syncAppearance?.() });
  try {
    const controller = createGuideController(viewer, loaded.guide), guide = loaded.guide;
    controls = document.createElement('section'); controls.className = 'hud-section guide-controls';
    controls.innerHTML = '<h2>Assembly instructions</h2><p class="guide-version"></p><label>Instruction <select aria-label="Instruction step"></select></label><p class="guide-text"></p><div class="hud-chips"><button type="button" class="hud-btn" data-action="previous">Previous</button><button type="button" class="hud-btn" data-action="next">Next</button><button type="button" class="hud-btn" data-action="reset">Assembled</button></div><label>Display <select aria-label="Instruction display"><option value="ghost">Ghost previous parts</option><option value="solid">Solid</option><option value="wireframe">Wireframe</option></select></label><label><input type="checkbox" checked class="guide-explode"> Show authored explosion</label><p>Selected: <output class="guide-selection">None</output></p><label>Selected part appearance <select aria-label="Selected part appearance" disabled><option value="">Use scene mode</option><option value="solid">Solid</option><option value="transparent">Transparent</option><option value="wireframe">Wireframe</option></select></label>';
    controls.querySelector('.guide-version').textContent = `${guide.snapshot.revision} · ${guide.snapshot.status} · ${guide.snapshot.source_commit.slice(0, 10)}`;
    const select = controls.querySelector('select'), mode = controls.querySelector('[aria-label="Instruction display"]'), explode = controls.querySelector('.guide-explode');
    const overview = document.createElement('option'); overview.value = ''; overview.textContent = 'Assembled overview'; select.append(overview);
    for (const step of guide.steps) { const option = document.createElement('option'); option.value = step.id; option.textContent = step.title; select.append(option); }
    const appearance = controls.querySelector('[aria-label="Selected part appearance"]');
    syncAppearance = () => {
      const state = viewer.getState(); controls.querySelector('.guide-selection').textContent = state.selected || 'None';
      appearance.disabled = state.selected === null;
      appearance.value = state.selected && Object.hasOwn(state.partModes, state.selected) ? state.partModes[state.selected] : '';
    };
    const lifetime = new AbortController();
    const apply = id => {
      mode.disabled = false; explode.disabled = false;
      controller.applyStep(id, { mode: mode.value, explode: explode.checked ? 1 : 0 });
      select.value = id; const index = guide.steps.findIndex(step => step.id === id);
      controls.querySelector('.guide-text').textContent = guide.steps[index].text;
      controls.querySelector('[data-action="previous"]').disabled = index === 0;
      controls.querySelector('[data-action="next"]').disabled = index === guide.steps.length - 1;
      syncAppearance();
    };
    const on = (element, event, fn) => element.addEventListener(event, fn, { signal: lifetime.signal });
    on(appearance, 'change', () => { const selected = viewer.getState().selected; if (selected) viewer.setPartMode(selected, appearance.value || null); });
    on(select, 'change', () => select.value ? apply(select.value) : resetOverview()); on(mode, 'change', () => apply(select.value)); on(explode, 'change', () => apply(select.value));
    for (const [action, delta] of [['previous', -1], ['next', 1]]) on(controls.querySelector(`[data-action="${action}"]`), 'click', () => {
      const index = guide.steps.findIndex(step => step.id === select.value); if (guide.steps[index + delta]) apply(guide.steps[index + delta].id);
    });
    function resetOverview() {
      controller.reset(); syncAppearance(); select.value = ''; mode.value = 'solid'; explode.checked = false;
      mode.disabled = true; explode.disabled = true;
      controls.querySelector('.guide-text').textContent = 'Assembled view. Choose an instruction to resume.';
      controls.querySelector('[data-action="previous"]').disabled = true;
      controls.querySelector('[data-action="next"]').disabled = false;
    }
    on(controls.querySelector('[data-action="reset"]'), 'click', resetOverview);
    panel.prepend(controls); apply(guide.steps[0].id);
    const dispose = () => { lifetime.abort(); controls.remove(); controller.dispose(); signal?.removeEventListener('abort', dispose); };
    signal?.addEventListener('abort', dispose, { once: true });
    if (signal?.aborted) { dispose(); signal.throwIfAborted(); }
    return { ...loaded, viewer, controller, selectStep: apply, dispose };
  } catch (error) { controls?.remove(); viewer.dispose(); throw error; }
}
