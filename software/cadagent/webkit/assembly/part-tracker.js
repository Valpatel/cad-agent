// Browser-local checklist state. This never places an order or contacts a vendor.
const VERSION = 1;
const forbidden = new Set(['__proto__', 'prototype', 'constructor']);
const validKey = value => typeof value === 'string' && value.length > 0 && value.length <= 300 && !forbidden.has(value);
const record = value => !!value && typeof value === 'object' && !Array.isArray(value);

export function createPartTracker({ project, fields = ['ordered', 'inHand', 'printed'], storage, events = globalThis.window } = {}) {
  if (!validKey(project) || !Array.isArray(fields) || !fields.length || fields.some(field => !validKey(field)) || new Set(fields).size !== fields.length) {
    throw new TypeError('A project and unique status fields are required.');
  }
  const key = `cadagent.parts.v${VERSION}:${project}`, allowed = new Set(fields), listeners = new Set();
  let entries = new Map(), persistent = true, warning = '';
  const failStorage = () => { persistent = false; warning = 'Changes stay in this tab. Browser storage is unavailable; export your progress to keep it.'; };
  if (storage === undefined) { try { storage = globalThis.localStorage; } catch { failStorage(); } }
  if (!storage) failStorage();
  function decode(text) {
    if (typeof text !== 'string' || text.length > 2_000_000) throw new Error('Choose a progress file smaller than 2 MB.');
    let data;
    try { data = JSON.parse(text); } catch { throw new Error('The progress file is not valid JSON.'); }
    if (!record(data) || data.version !== VERSION || data.project !== project || !record(data.parts)) throw new Error('This progress file belongs to another project or an unsupported version.');
    const rows = Object.entries(data.parts);
    if (rows.length > 10000) throw new Error('The progress file contains too many parts.');
    const next = new Map();
    for (const [id, state] of rows) {
      if (!validKey(id) || !record(state)) throw new Error('The progress file contains an invalid part.');
      const clean = Object.create(null);
      for (const [field, value] of Object.entries(state)) {
        if (!allowed.has(field) || typeof value !== 'boolean') throw new Error('The progress file contains an unsupported status.');
        clean[field] = value;
      }
      next.set(id, clean);
    }
    return next;
  }
  const serialise = (parts = entries) => JSON.stringify({ version: VERSION, project, parts: Object.fromEntries(parts) }, null, 2);
  function checkSize(parts) {
    if (parts.size > 10000 || new TextEncoder().encode(serialise(parts)).byteLength > 2_000_000) {
      throw new Error('Progress is too large for one file. Keep at most 10,000 parts and 2 MB per project.');
    }
  }
  const emit = () => { for (const listener of listeners) listener(api); };
  function save() {
    if (storage) {
      try { storage.setItem(key, serialise()); persistent = true; warning = ''; }
      catch { failStorage(); }
    }
    emit();
  }
  try { const saved = storage?.getItem(key); if (saved) entries = decode(saved); }
  catch (error) { persistent = false; warning = `Saved progress could not be read. ${error.message} Export changes before leaving this tab.`; }
  const onStorage = event => {
    if (event.key !== key || event.storageArea && event.storageArea !== storage) return;
    try { entries = event.newValue === null ? new Map() : decode(event.newValue); persistent = true; warning = ''; emit(); }
    catch { warning = 'A progress update from another tab could not be read. Your current checklist is unchanged.'; emit(); }
  };
  events?.addEventListener('storage', onStorage);
  const api = {
    project, key, fields: [...fields],
    get persistent() { return persistent; },
    get warning() { return warning; },
    get(id, field) { return entries.get(id)?.[field] === true; },
    set(id, field, value) {
      if (!validKey(id) || !allowed.has(field) || typeof value !== 'boolean') throw new TypeError('Invalid part status.');
      const next = new Map(entries); next.set(id, { ...entries.get(id), [field]: value }); checkSize(next);
      entries = next; save();
    },
    export() { return serialise(); },
    import(text) {
      const incoming = decode(text); // Validate every row before changing anything.
      const next = new Map(entries);
      for (const [id, state] of incoming) next.set(id, { ...next.get(id), ...state });
      checkSize(next); entries = next; save(); return incoming.size;
    },
    subscribe(listener) { listeners.add(listener); return () => listeners.delete(listener); },
    dispose() { listeners.clear(); events?.removeEventListener('storage', onStorage); },
  };
  return api;
}
