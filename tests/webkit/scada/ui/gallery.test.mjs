import {UI, TOOLS, TESTS} from '../../../../tools/webkit/scada/paths.mjs';
import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
import {sourceTree, bundleCss} from '../../../../tools/webkit/scada/ui/gallery/css-source-tree.mjs';

const root=UI;

test('gallery preserves var animation shorthand, declaration order and leading pseudo selector', () => {
  const css = ':is(.active,.ready) .rotor{animation:spin var(--speed,2s) infinite;animation-play-state:paused;content:"} /* not syntax */"}@keyframes spin{to{transform:rotate(1turn)}}';
  const [rule, frames] = sourceTree(css);
  assert.equal(rule.source, css.slice(0, css.indexOf('@keyframes')));
  assert.equal(rule.selector, ':is(.active,.ready) .rotor');
  assert.equal(frames.name, 'spin');
  assert.equal(frames.source, '@keyframes spin{to{transform:rotate(1turn)}}');
});

test('gallery retains conditional source declarations and rejects unsupported rule kinds', () => {
  const [group] = sourceTree('@media (prefers-reduced-motion:reduce){:is(.x,.y) *{animation:none!important}}');
  assert.equal(group.before + group.children[0].source + group.after, '@media (prefers-reduced-motion:reduce){:is(.x,.y) *{animation:none!important}}');
  assert.throws(() => sourceTree('@font-face{font-family:external;src:url(font.woff)}'), /Unsupported CSS rule/);
});

test('gallery CSS imports stay within the package and reject circular dependencies', t => {
  const temporary = fs.mkdtempSync(path.join(os.tmpdir(), 'scada-gallery-css-'));
  t.after(() => fs.rmSync(temporary, {recursive: true, force: true}));
  fs.mkdirSync(path.join(temporary, 'package'));
  fs.writeFileSync(path.join(temporary, 'outside.css'), '.x{fill:red}');
  const entry = path.join(temporary, 'package/entry.css');
  fs.writeFileSync(entry, '@import url("../outside.css");');
  assert.throws(() => bundleCss(entry, path.dirname(entry)), /escapes package/);
  fs.writeFileSync(entry, '@import url("entry.css");');
  assert.throws(() => bundleCss(entry, path.dirname(entry)), /Circular/);
  fs.writeFileSync(entry, '@import "entry.css";');
  assert.throws(() => bundleCss(entry, path.dirname(entry)), /Unexpanded/);
});

test('canonical gallery stylesheet has no external or unresolved imports', () => {
  const {css, sourceTree: rules, sources} = bundleCss(path.join(root, 'src/symbols/components.css'), root);
  assert.ok(rules.length > 0);
  assert.ok(Object.keys(sources).length > 1);
  assert.ok(!css.includes('@import'));
  const nested = rules.flatMap(rule => rule.children ?? []);
  assert.ok(nested.some(rule => rule.source.includes('animation:none!important')));
});


test('gallery state examples declare motion expectations and only use existing state fields', async () => {
  const {getScadaComponent} = await import('../../../../software/cadagent/webkit/scada/ui/src/symbols/index.mjs');
  const samples = JSON.parse(fs.readFileSync(path.join(TOOLS, 'ui/gallery/samples.json')));
  const keys = new Set();
  for (const sample of samples) {
    const key = [sample.type, sample.variant ?? '', sample.sample].join('/');
    assert.ok(!keys.has(key), 'Duplicate sample: ' + key); keys.add(key);
    assert.ok(['animated', 'still'].includes(sample.expectedMotion), key);
    const descriptor = getScadaComponent(sample.type, sample.variant ? {variant: sample.variant} : {});
    const fields = new Map(descriptor.stateFields.map(field => [field.key, field]));
    for (const [name, value] of Object.entries(sample.state)) {
      assert.ok(fields.has(name), key + ': unknown field ' + name);
      const field = fields.get(name);
      if (field.type === 'select') assert.ok(field.options.some(option => option.value === value), key);
      if (field.type === 'number') assert.ok(Number.isFinite(value) && value >= field.min && value <= field.max, key);
    }
  }
  assert.equal(samples.find(sample => sample.type === 'pump' && sample.sample === 'paused').expectedMotion, 'still');
  assert.equal(samples.find(sample => sample.type === 'plc-rack' && sample.sample === 'disconnected').expectedMotion, 'still');
});
