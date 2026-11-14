import test from 'node:test';
import assert from 'node:assert/strict';
import { JSDOM } from '../dependencies.mjs';
import { renderScadaDialog, renderScadaToolbar, ScadaWorkspace } from '../../../../software/cadagent/webkit/scada/ui/src/workspace/workspace.mjs';

function fixture({ native = false, second = false } = {}) {
  const dom = new JSDOM(`<main id="main"><section class="scada-workspace" id="workspace">
    ${renderScadaToolbar({ content: '<button id="equipment-open" data-scada-open="equipment">Equipment</button><button id="events-open" data-scada-open="events">Events</button>' })}
    ${renderScadaDialog({ id: 'equipment', title: 'Feed pump', kind: 'equipment', body: '<label>Speed<input id="speed" value="100"></label><button data-scada-open="events" id="inside-events">Events</button><button id="last-action">Apply</button><details><summary>Advanced</summary><input id="collapsed-input"></details><button hidden id="hidden-action">Hidden</button>' })}
    ${renderScadaDialog({ id: 'events', title: 'Events', body: '<p>Stable event content</p><button id="clear-events">Clear</button>' })}
  </section>${second ? `<section class="scada-workspace" id="second"><button id="second-open" data-scada-open="equipment">Second equipment</button>${renderScadaDialog({ scope: 'second', id: 'equipment', title: 'Second pump', body: '<input value="42">' })}</section>` : ''}</main>`, { url: 'https://digester.test' });
  const { window } = dom, root = window.document.querySelector('#workspace'), opened = [], closed = [], queued = [];
  if (native) for (const dialog of window.document.querySelectorAll('dialog')) {
    dialog.showModal = function () { this.setAttribute('open', ''); };
    dialog.close = function () { this.removeAttribute('open'); queued.push(() => this.dispatchEvent(new window.Event('close'))); };
  }
  const workspace = new ScadaWorkspace(root, { onOpen: event => opened.push(event.id), onClose: event => closed.push([event.id, event.reason]) });
  return { dom, window, document: window.document, root, workspace, opened, closed, queued, $: selector => window.document.querySelector(selector), cleanup() { workspace.destroy(); dom.window.close(); } };
}

test('dialog headings are escaped, caller HTML stays scoped, and IDs can be namespaced', () => {
  const markup = renderScadaDialog({ id: 'pump', scope: 'plant', title: 'Pump <script>bad</script>', subtitle: 'A "quoted" note', body: '<button data-scada-close>Done</button>', footer: '<span>Footer</span>' });
  const dom = new JSDOM(markup);
  const dialog = dom.window.document.querySelector('dialog');
  assert.equal(dialog.id, 'plant-pump-dialog');
  assert.equal(dialog.dataset.scadaDialog, 'pump');
  assert.equal(dialog.getAttribute('aria-labelledby'), 'plant-pump-dialog-title');
  assert.equal(dialog.getAttribute('aria-describedby'), 'plant-pump-dialog-description');
  assert.equal(dialog.querySelector('script'), null);
  assert.equal(dialog.querySelector('[data-scada-dialog-title]').textContent, 'Pump <script>bad</script>');
  assert.equal(dialog.querySelector('[data-scada-dialog-body] button').textContent, 'Done');
  assert.equal(dialog.querySelector('.scada-dialog-footer').textContent, 'Footer');
  assert.throws(() => renderScadaDialog({ id: 'bad"id', title: 'Bad' }), /Invalid SCADA/);
  assert.throws(() => new ScadaWorkspace(null), /workspace root/);
  dom.window.close();
});

test('fallback open, Escape and close preserve input state and restore the initiating control', () => {
  const f = fixture();
  try {
    const trigger = f.$('#equipment-open'), input = f.$('#speed'), dialog = f.$('[data-scada-dialog=equipment]');
    trigger.focus(); trigger.click();
    assert.equal(f.workspace.activeId, 'equipment');
    assert.equal(dialog.open, true);
    assert.equal(dialog.getAttribute('aria-modal'), 'true');
    assert.equal(trigger.getAttribute('aria-expanded'), 'true');
    assert.equal(trigger.getAttribute('aria-controls'), dialog.id);
    assert.equal(f.document.activeElement, dialog.querySelector('[data-scada-close]'));
    assert.equal(f.document.documentElement.style.overflow, 'hidden');
    input.value = '127.5'; input.focus();
    assert.equal(f.workspace.open('equipment'), true);
    assert.equal(f.document.activeElement, input, 'reopening the current panel never steals editing focus');
    input.dispatchEvent(new f.window.KeyboardEvent('keydown', { key: 'Escape', bubbles: true, cancelable: true }));
    assert.equal(f.workspace.activeId, null);
    assert.equal(dialog.open, false);
    assert.equal(f.document.activeElement, trigger);
    assert.equal(f.document.documentElement.style.overflow, '');
    assert.equal(trigger.getAttribute('aria-expanded'), 'false');
    assert.deepEqual(f.closed, [['equipment', 'escape']]);
    trigger.click();
    assert.equal(f.$('#speed'), input, 'dialog content stays mounted');
    assert.equal(input.value, '127.5');
    dialog.querySelector('[data-scada-close]').click();
    assert.equal(f.document.activeElement, trigger);
    assert.equal(f.workspace.close(), false, 'repeated close is a no-op');
    assert.equal(f.closed.length, 2);
  } finally { f.cleanup(); }
});

test('fallback contains focus and skips hidden, disabled and collapsed controls', () => {
  const f = fixture();
  try {
    f.workspace.open('equipment', { opener: f.$('#equipment-open'), focus: '#speed' });
    const dialog = f.workspace.activeDialog, first = dialog.querySelector('[data-scada-close]');
    assert.equal(f.document.activeElement, f.$('#speed'));
    // The closed details summary is available, but its input is not.
    const last = dialog.querySelector('summary');
    last.focus();
    last.dispatchEvent(new f.window.KeyboardEvent('keydown', { key: 'Tab', bubbles: true, cancelable: true }));
    assert.equal(f.document.activeElement, first);
    first.dispatchEvent(new f.window.KeyboardEvent('keydown', { key: 'Tab', shiftKey: true, bubbles: true, cancelable: true }));
    assert.equal(f.document.activeElement, last);
    f.$('#events-open').focus();
    assert.ok(dialog.contains(f.document.activeElement), 'programmatic background focus is contained in fallback mode');
    assert.ok(f.root.querySelector('.scada-fallback-backdrop'), 'fallback includes an actual blocking overlay');
    f.root.querySelector('.scada-fallback-backdrop').click();
    assert.equal(f.workspace.activeId, null);
    assert.equal(f.root.querySelector('.scada-fallback-backdrop'), null);
  } finally { f.cleanup(); }
});

test('switching panels preserves the outside opener and ignores stale native close events', () => {
  const f = fixture({ native: true });
  try {
    const opener = f.$('#equipment-open');
    f.workspace.open('equipment', { opener });
    f.$('#inside-events').click();
    assert.equal(f.workspace.activeId, 'events');
    assert.equal(f.$('[data-scada-dialog=equipment]').open, false);
    assert.equal(f.$('[data-scada-dialog=events]').open, true);
    assert.equal(f.queued.length, 1);
    f.queued.shift()();
    assert.equal(f.workspace.activeId, 'events', 'queued close from the old panel cannot affect the new one');
    f.workspace.activeDialog.dispatchEvent(new f.window.Event('cancel', { cancelable: true }));
    assert.equal(f.workspace.activeId, null);
    assert.equal(f.document.activeElement, opener);
    assert.deepEqual(f.closed, [['equipment', 'switch'], ['events', 'escape']]);
    f.queued.splice(0).forEach(run => run());
    assert.equal(f.closed.length, 2);
  } finally { f.cleanup(); }
});

test('native backdrop closes only when both pointer start and click are outside the dialog', () => {
  const f = fixture({ native: true });
  try {
    f.workspace.open('equipment');
    const dialog = f.workspace.activeDialog;
    dialog.getBoundingClientRect = () => ({ left: 100, top: 100, right: 500, bottom: 500 });
    const point = (type, x, y) => dialog.dispatchEvent(new f.window.MouseEvent(type, { bubbles: true, cancelable: true, clientX: x, clientY: y }));
    point('pointerdown', 200, 200); point('click', 200, 200);
    assert.equal(f.workspace.activeId, 'equipment', 'dialog padding is not its backdrop');
    point('pointerdown', 200, 200); point('click', 20, 20);
    assert.equal(f.workspace.activeId, 'equipment', 'dragging from content to backdrop must not dismiss');
    point('pointerdown', 20, 20); point('click', 20, 20);
    assert.equal(f.workspace.activeId, null);
    assert.deepEqual(f.closed, [['equipment', 'backdrop']]);
  } finally { f.cleanup(); }
});

test('immediately reopening an externally closed native dialog survives its queued close event', () => {
  const f = fixture({ native: true });
  try {
    const opener = f.$('#equipment-open');
    f.workspace.open('equipment', { opener });
    const dialog = f.workspace.activeDialog;
    dialog.close();
    assert.equal(dialog.open, false);
    assert.equal(f.workspace.open('equipment', { opener }), true);
    assert.equal(dialog.open, true);
    f.queued.shift()();
    assert.equal(f.workspace.activeId, 'equipment');
    assert.equal(dialog.open, true);
    f.workspace.close();
    assert.equal(f.document.activeElement, opener);
    assert.equal(f.document.documentElement.style.overflow, '');
  } finally { f.cleanup(); }
});

test('external native closure and removed openers clean up once with a usable focus fallback', () => {
  const f = fixture({ native: true });
  try {
    const opener = f.$('#equipment-open');
    f.workspace.open('equipment', { opener }); opener.remove();
    f.workspace.activeDialog.close(); f.queued.shift()();
    assert.equal(f.workspace.activeId, null);
    assert.equal(f.document.activeElement, f.$('#events-open'));
    assert.deepEqual(f.closed, [['equipment', 'native']]);
    assert.equal(f.document.documentElement.style.overflow, '');
  } finally { f.cleanup(); }
});

test('two workspaces share scroll locking; destruction closes and removes delegated listeners', () => {
  const f = fixture({ second: true }), second = new ScadaWorkspace(f.$('#second'));
  try {
    f.document.documentElement.style.overflow = 'clip';
    f.workspace.open('equipment'); second.open('equipment');
    f.workspace.close({ restoreFocus: false });
    assert.equal(f.document.documentElement.style.overflow, 'hidden');
    second.destroy();
    assert.equal(f.document.documentElement.style.overflow, 'clip');
    assert.equal(f.$('#second [data-scada-dialog]').open, false);
    f.$('#second-open').click();
    assert.equal(second.activeId, null);
    assert.equal(second.open('equipment'), false);
    f.workspace.open('equipment'); f.workspace.destroy();
    assert.equal(f.$('[data-scada-dialog=equipment]').open, false);
    assert.equal(f.document.documentElement.style.overflow, 'clip');
    f.$('#equipment-open').click();
    assert.equal(f.workspace.activeId, null);
  } finally { second.destroy(); f.cleanup(); }
});

test('a missing dialog does not close the current panel or alter focus', () => {
  const f = fixture();
  try {
    f.workspace.open('equipment', { focus: '#speed' });
    assert.equal(f.workspace.open('missing'), false);
    assert.equal(f.workspace.activeId, 'equipment');
    assert.equal(f.document.activeElement, f.$('#speed'));
  } finally { f.cleanup(); }
});
