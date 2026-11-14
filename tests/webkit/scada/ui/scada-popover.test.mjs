import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {JSDOM} from '../dependencies.mjs';
import {ScadaPopover, placeScadaPopover} from '../../../../software/cadagent/webkit/scada/ui/src/workspace/popover.mjs';

const rect = (left, top, width, height) => ({left, top, right:left + width, bottom:top + height, width, height});
const css = readFileSync(new URL('../../../../software/cadagent/webkit/scada/ui/src/workspace/popover.css', import.meta.url), 'utf8');
function fixture({native = false} = {}) {
  const dom = new JSDOM(`<style>${css}</style><main id="root"><button id="anchor">P-101</button><button id="other">P-102</button>
    <section id="quick" data-scada-popover popover="manual" hidden tabindex="-1" aria-labelledby="title">
      <header class="scada-popover-header"><h2 id="title">P-101</h2><button data-scada-popover-close>Close</button></header>
      <div class="scada-popover-body"><label>Load<input id="load" value="50"></label><button id="last">Settings</button></div>
    </section></main><button id="outside">Outside</button>`, {pretendToBeVisual:true});
  const {window} = dom, {document} = window, root = document.querySelector('#root'), panel = document.querySelector('#quick');
  const closed = [], queued = [], observers = [];
  Object.defineProperties(window, {innerWidth:{value:1000,writable:true}, innerHeight:{value:800,writable:true}});
  let anchorBounds = rect(440, 400, 120, 80);
  document.querySelector('#anchor').getBoundingClientRect = () => anchorBounds;
  document.querySelector('#other').getBoundingClientRect = () => rect(120, 200, 80, 80);
  panel.getBoundingClientRect = () => rect(Number.parseFloat(panel.style.left) || 0, Number.parseFloat(panel.style.top) || 0, 360, 240);
  window.ResizeObserver = class {
    constructor(callback) { this.callback = callback; this.observed = []; this.disconnected = false; observers.push(this); }
    observe(element) { this.observed.push(element); }
    disconnect() { this.disconnected = true; }
  };
  let shown = false;
  if (native) {
    const matches = panel.matches.bind(panel);
    panel.matches = selector => selector === ':popover-open' ? shown : matches(selector);
    panel.showPopover = () => { shown = true; };
    panel.hidePopover = () => { shown = false; queued.push(() => panel.dispatchEvent(Object.assign(new window.Event('toggle'), {newState:'closed'}))); };
  }
  const controller = new ScadaPopover(root, {onClose:event => closed.push(event.reason)});
  return {dom,window,document,root,panel,controller,closed,queued,observers,
    $:selector => document.querySelector(selector), move:bounds => {anchorBounds = bounds;},
    cleanup() {controller.destroy(); dom.window.close();}};
}

test('placement prefers above, flips when necessary and stays within a narrow or offset viewport', () => {
  assert.deepEqual(placeScadaPopover(rect(450, 400, 100, 80), {width:360,height:240}, rect(0, 0, 1000, 800)),
    {left:320,top:148,width:360,height:240,placement:'top'});
  assert.equal(placeScadaPopover(rect(450, 20, 100, 80), {width:360,height:240}, rect(0, 0, 1000, 800)).placement, 'bottom');
  const mobile = placeScadaPopover(rect(285, 15, 50, 30), {width:360,height:440}, rect(22, 38, 320, 380));
  assert.equal(mobile.width, 296); assert.equal(mobile.height, 356);
  assert.ok(mobile.left >= 34 && mobile.left + mobile.width <= 330);
  assert.ok(mobile.top >= 50 && mobile.top + mobile.height <= 406);
  assert.throws(() => placeScadaPopover(rect(0, 0, 1, 1), {width:360,height:200}, {width:0,height:100}), /viewport/);
});

for (const native of [false, true]) test(`${native ? 'native' : 'fallback'} popover keeps the diagram interactive and restores focus only on explicit dismissal`, () => {
  const f = fixture({native});
  try {
    f.document.documentElement.style.overflow = 'auto';
    f.$('#anchor').focus();
    assert.equal(f.controller.open(f.panel, {anchor:() => f.$('#anchor'), opener:f.$('#anchor')}), true);
    assert.equal(f.controller.activePanel, f.panel);
    assert.equal(f.panel.hidden, false); assert.equal(f.panel.getAttribute('aria-modal'), 'false');
    assert.equal(f.panel.getAttribute('popover'), native ? 'manual' : null);
    assert.equal(f.document.documentElement.style.overflow, 'auto');
    assert.equal(f.document.querySelector('[inert]'), null);
    assert.equal(f.document.activeElement, f.$('[data-scada-popover-close]'));
    f.$('#load').value = '72'; f.$('#load').focus();
    f.controller.open(f.panel, {anchor:() => f.$('#anchor')});
    assert.equal(f.document.activeElement, f.$('#load'), 'same-panel refresh preserves editing focus');
    const tab = new f.window.KeyboardEvent('keydown', {key:'Tab',bubbles:true,cancelable:true});
    f.$('#last').dispatchEvent(tab); assert.equal(tab.defaultPrevented, false, 'popover does not trap Tab');
    f.$('#outside').focus(); f.$('#outside').click();
    assert.equal(f.controller.activePanel, null); assert.equal(f.document.activeElement, f.$('#outside'));
    assert.equal(f.panel.hidden, true); assert.equal(f.$('#load').value, '72');
    assert.equal(f.panel.getAttribute('popover'), 'manual');
    f.controller.open(f.panel, {anchor:f.$('#anchor'),opener:f.$('#anchor')});
    const escape = new f.window.KeyboardEvent('keydown', {key:'Escape',bubbles:true,cancelable:true});
    f.$('#load').dispatchEvent(escape);
    assert.equal(escape.defaultPrevented, true); assert.equal(f.document.activeElement, f.$('#anchor'));
    assert.deepEqual(f.closed, ['outside','escape']);
    assert.equal(f.controller.close(), false);
  } finally {f.cleanup();}
});

test('fallback fields stay focusable without CSS when the DOM implements only popover visibility semantics', () => {
  const f = fixture();
  try {
    f.document.querySelector('style').remove();
    assert.equal(typeof f.panel.showPopover, 'undefined');
    assert.equal(f.panel.getAttribute('popover'), 'manual');
    f.controller.open(f.panel, {anchor:f.$('#anchor'),opener:f.$('#anchor')});
    assert.equal(f.document.activeElement, f.$('[data-scada-popover-close]'));
    f.$('#load').focus(); assert.equal(f.document.activeElement, f.$('#load'));
    f.$('#load').value = '84'; f.controller.reposition();
    assert.equal(f.document.activeElement, f.$('#load')); assert.equal(f.$('#load').value, '84');
    f.controller.destroy();
    assert.equal(f.panel.getAttribute('popover'), 'manual'); assert.equal(f.panel.hidden, true);
  } finally {f.cleanup();}
});

test('reposition follows an anchor resolver, viewport changes and resize notifications without changing a draft', () => {
  const f = fixture();
  try {
    let anchor = f.$('#anchor');
    f.controller.open(f.panel, {anchor:() => anchor,opener:f.$('#anchor')});
    assert.equal(f.panel.style.left, '320px'); assert.equal(f.panel.style.top, '148px');
    f.$('#load').value = '91'; f.$('#load').focus();
    f.move(rect(600, 600, 120, 80)); f.controller.reposition();
    assert.equal(f.panel.style.left, '480px'); assert.equal(f.panel.style.top, '348px');
    anchor = f.$('#other'); f.controller.reposition();
    assert.equal(f.panel.style.left, '212px'); assert.equal(f.panel.style.top, '120px');
    f.window.innerWidth = 400; f.window.innerHeight = 300;
    f.window.dispatchEvent(new f.window.Event('resize'));
    assert.equal(f.panel.style.maxWidth, '376px'); assert.equal(f.panel.style.maxHeight, '276px');
    assert.ok(Number.parseFloat(f.panel.style.left) >= 12);
    assert.ok(Number.parseFloat(f.panel.style.left) + 360 <= 388);
    assert.equal(f.document.activeElement, f.$('#load')); assert.equal(f.$('#load').value, '91');
    f.observers[0].callback(); assert.equal(f.controller.activePanel, f.panel);
    f.controller.close(); assert.equal(f.observers[0].disconnected, true);
  } finally {f.cleanup();}
});

test('a suppressed diagram-drag click does not dismiss the quick controls', () => {
  const f = fixture();
  try {
    f.controller.open(f.panel, {anchor:f.$('#anchor'),opener:f.$('#anchor')});
    f.$('#other').addEventListener('click', event => event.preventDefault());
    f.$('#other').click(); assert.equal(f.controller.activePanel, f.panel);
    f.$('[data-scada-popover-close]').click();
    assert.equal(f.controller.activePanel, null); assert.equal(f.document.activeElement, f.$('#anchor'));
  } finally {f.cleanup();}
});

test('Escape closes the quick controls before its enclosing dialog and ignores a different active dialog', () => {
  const f = fixture();
  try {
    const dialog = f.document.createElement('dialog'); dialog.open = true;
    f.root.before(dialog); dialog.append(f.root);
    let escaped = 0; dialog.addEventListener('keydown', event => {if (event.key === 'Escape') escaped++;});
    f.controller.open(f.panel, {anchor:f.$('#anchor'),opener:f.$('#anchor')});
    f.$('#load').dispatchEvent(new f.window.KeyboardEvent('keydown', {key:'Escape',bubbles:true,cancelable:true}));
    assert.equal(f.controller.activePanel, null); assert.equal(dialog.open, true); assert.equal(escaped, 0);
    f.controller.open(f.panel, {anchor:f.$('#anchor'),opener:f.$('#anchor')});
    const other = f.document.createElement('dialog'); other.open = true; other.innerHTML = '<button>Other modal</button>';
    f.document.body.append(other); other.querySelector('button').focus();
    const escape = new f.window.KeyboardEvent('keydown', {key:'Escape',bubbles:true,cancelable:true});
    other.querySelector('button').dispatchEvent(escape);
    assert.equal(escape.defaultPrevented, false); assert.equal(f.controller.activePanel, f.panel);
  } finally {f.cleanup();}
});

test('queued native close cannot close a reopened panel, and an external hide cleans up', () => {
  const f = fixture({native:true});
  try {
    f.controller.open(f.panel, {anchor:f.$('#anchor'),opener:f.$('#anchor')});
    f.controller.close(); f.controller.open(f.panel, {anchor:f.$('#anchor'),opener:f.$('#anchor')});
    f.queued.shift()(); assert.equal(f.controller.activePanel, f.panel);
    f.panel.hidePopover(); f.queued.shift()();
    assert.equal(f.controller.activePanel, null); assert.equal(f.panel.hidden, true);
    assert.deepEqual(f.closed, ['close','native']);
  } finally {f.cleanup();}
});

test('unavailable requested focus falls back to Close and Escape dismisses only the latest popover', () => {
  const f = fixture(); let second;
  try {
    f.$('#load').disabled = true;
    f.controller.open(f.panel, {anchor:f.$('#anchor'),opener:f.$('#anchor'),focus:'#load'});
    assert.equal(f.document.activeElement, f.$('[data-scada-popover-close]'));
    const root = f.document.createElement('section');
    root.innerHTML = '<button id="second-opener">Second</button><section data-scada-popover hidden tabindex="-1"><button data-scada-popover-close>Close second</button></section>';
    f.document.body.append(root); second = new ScadaPopover(root);
    const panel = root.querySelector('[data-scada-popover]');
    second.open(panel, {anchor:root.querySelector('button'),opener:root.querySelector('button')});
    panel.querySelector('button').dispatchEvent(new f.window.KeyboardEvent('keydown', {key:'Escape',bubbles:true,cancelable:true}));
    assert.equal(second.activePanel, null); assert.equal(f.controller.activePanel, f.panel);
    assert.equal(f.document.activeElement.id, 'second-opener');
  } finally {second?.destroy(); f.cleanup();}
});

test('detached panels close without stealing focus and destroy releases every owned observer/listener', () => {
  const f = fixture();
  try {
    f.controller.open(f.panel, {anchor:f.$('#anchor'),opener:f.$('#anchor')});
    f.$('#outside').focus(); f.panel.remove(); f.controller.reposition();
    assert.equal(f.controller.activePanel, null); assert.equal(f.document.activeElement, f.$('#outside'));
    f.root.append(f.panel); f.controller.open(f.panel, {anchor:f.$('#anchor'),opener:f.$('#anchor')});
    f.controller.destroy(); assert.equal(f.panel.hidden, true); assert.ok(f.observers.every(item => item.disconnected));
    const style = f.panel.getAttribute('style');
    f.window.innerWidth = 420; f.window.dispatchEvent(new f.window.Event('resize'));
    assert.equal(f.panel.getAttribute('style'), style);
    assert.equal(f.controller.open(f.panel), false);
    assert.deepEqual(f.closed, ['removed','destroy']);
  } finally {f.cleanup();}
});
