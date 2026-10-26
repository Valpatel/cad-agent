// HUD panel helpers: collapsible sections, labelled sliders with mono readouts, chip rows, toggles and readout
// tables, styled by hud.css. Plain DOM, no framework.

const esc = (s) => String(s ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));

/** section(parent, title, { note, open = true }) -> the section's body element */
export function section(parent, title, { note = '', open = true } = {}) {
  const d = document.createElement('details');
  d.className = 'hud-section';
  d.open = open;
  d.innerHTML = `<summary><span class="tick"></span>${esc(title)}<span class="note">${esc(note)}</span></summary><div class="body"></div>`;
  parent.appendChild(d);
  return d.querySelector('.body');
}

/**
 * slider(parent, { label, min, max, step = 1, value, unit = '', fmt }) -> { input, set(v), get() }
 * Calls `onInput(value)` while dragging.
 */
export function slider(parent, { label, min, max, step = 1, value, unit = '', fmt, onInput }) {
  const wrap = document.createElement('label');
  wrap.className = 'hud-slider';
  const show = fmt ?? ((v) => `${Number(v).toFixed(step < 1 ? 1 : 0)}${unit}`);
  wrap.innerHTML = `<span class="row"><span>${esc(label)}</span><span class="val"></span></span>`
    + `<input type="range" min="${min}" max="${max}" step="${step}" value="${value}">`;
  const input = wrap.querySelector('input'), val = wrap.querySelector('.val');
  const paint = () => { val.textContent = show(+input.value); };
  input.addEventListener('input', () => { paint(); onInput?.(+input.value); });
  paint();
  parent.appendChild(wrap);
  return { input, set(v) { input.value = String(v); paint(); }, get: () => +input.value };
}

/** jointSliders(parent, joints, onInput) for [{ name, label, min, max, value, unit }] -> { set(name, v) } */
export function jointSliders(parent, joints, onInput) {
  const by = {};
  for (const j of joints) {
    by[j.name] = slider(parent, { ...j, step: j.step ?? (j.unit === '°' ? 1 : 0.01), onInput: (v) => onInput(j.name, v) });
  }
  return { set(name, v) { by[name]?.set(v); }, sliders: by };
}

/** chips(parent, items: [{ id, html, title }], onPick) -> { mark(id) } */
export function chips(parent, items, onPick) {
  const row = document.createElement('div');
  row.className = 'hud-chips';
  for (const it of items) {
    const b = document.createElement('button');
    b.type = 'button';
    b.className = 'hud-chip';
    b.dataset.id = it.id;
    b.title = it.title ?? it.id;
    b.setAttribute('aria-label', it.title ?? it.id);
    b.innerHTML = it.html ?? esc(it.id);
    b.addEventListener('click', () => { mark(it.id); onPick(it.id); });
    row.appendChild(b);
  }
  parent.appendChild(row);
  function mark(id) { row.querySelectorAll('.hud-chip').forEach((b) => b.classList.toggle('active', b.dataset.id === id)); }
  return { mark };
}

/** toggle(parent, label, checked, onChange) -> input */
export function toggle(parent, label, checked, onChange) {
  const l = document.createElement('label');
  l.className = 'hud-toggle';
  l.innerHTML = `<input type="checkbox" ${checked ? 'checked' : ''}><span>${esc(label)}</span>`;
  const input = l.querySelector('input');
  input.addEventListener('change', () => onChange(input.checked));
  parent.appendChild(l);
  return input;
}

/** readouts(parent) -> { set(rows: [[label, value, level?]]) } — a mono telemetry table. */
export function readouts(parent) {
  const t = document.createElement('div');
  t.className = 'hud-readouts';
  parent.appendChild(t);
  return {
    set(rows) {
      t.innerHTML = rows.map(([k, v, lvl]) => `<div class="r ${lvl ?? ''}"><span>${esc(k)}</span><b>${esc(v)}</b></div>`).join('');
    },
  };
}
