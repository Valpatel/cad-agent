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

/**
 * collapsiblePanel(hud, panel, { key, onChange }) adds a button to the top bar and a tab on the panel's edge that hide
 * and show the side panel, remembers the choice (localStorage `key`), and calls onChange(collapsed) after the layout
 * changes (use it to update the stage's insets). Returns { collapsed(), set(bool) }.
 */
export function collapsiblePanel(hud, panel, { key = 'hud-panel-collapsed', onChange } = {}) {
  const tab = document.createElement('button');
  tab.className = 'hud-panel-tab';
  tab.type = 'button';
  hud.appendChild(tab);
  const btn = document.createElement('button');
  btn.className = 'hud-pill';
  btn.type = 'button';
  hud.querySelector('#topbar')?.appendChild(btn);
  let state = false;
  try { state = localStorage.getItem(key) === '1'; } catch { /* storage blocked */ }
  function set(v) {
    state = Boolean(v);
    hud.classList.toggle('panel-collapsed', state);
    tab.textContent = state ? '\u25C2' : '\u25B8';
    tab.title = state ? 'Show the panel' : 'Hide the panel';
    btn.textContent = state ? 'SHOW PANEL' : 'HIDE PANEL';
    try { localStorage.setItem(key, state ? '1' : '0'); } catch { /* storage blocked */ }
    requestAnimationFrame(() => onChange?.(state));
  }
  tab.onclick = btn.onclick = () => set(!state);
  set(state);
  return { collapsed: () => state, set };
}

/** The pixels of the stage that overlay UI covers: the side panel (unless collapsed) and the top bar. */
export function overlayInsets(hud) {
  const W = window.innerWidth;
  const top = hud.querySelector('#topbar')?.getBoundingClientRect().bottom ?? 0;
  const panel = hud.querySelector('#panel');
  const pr = panel && !hud.classList.contains('panel-collapsed') ? panel.getBoundingClientRect() : null;
  const app = document.getElementById('app')?.getBoundingClientRect().top ?? 0;
  const side = pr && pr.width && pr.left > W / 2 ? W - pr.left : 0;
  const below = pr && pr.width && pr.left <= W / 2 ? window.innerHeight - pr.top : 0;   // narrow screens: panel underneath
  return { right: side, top: Math.max(0, top - app), bottom: below, left: 0 };
}
