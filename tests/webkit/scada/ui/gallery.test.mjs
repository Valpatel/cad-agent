import {UI, TOOLS, TESTS} from '../../../../tools/webkit/scada/paths.mjs';
import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
import {spawnSync} from 'node:child_process';
import {sourceTree, bundleCss} from '../../../../tools/webkit/scada/ui/gallery/css-source-tree.mjs';

const root=UI;

function python(source) {
  const result = spawnSync('python3', ['-c', source], {cwd: TOOLS, encoding: 'utf8'});
  assert.ifError(result.error);
  assert.equal(result.status, 0, result.stderr || result.stdout);
}

test('folder maps stay compact, portable and escaped, and every generated index shares its owner map', () => python(`
import sys,json,xml.etree.ElementTree as ET
from pathlib import Path
sys.path.insert(0,str(Path('ui/gallery').resolve()))
from gallery_maps import folder_map_svg
from asset_maps import gallery_outputs
from scada_paths import UI
svg=folder_map_svg('owner<&>', [('folder<&>', 'Meaning <with> & text')], 'Safe <description>')
doc=ET.fromstring(svg)
assert doc.get('width')=='360'
assert doc.find('{*}title').text=='owner<&> folder map'
assert len(doc.findall('.//{*}text'))==3
assert not doc.findall('.//{*}script')
assert all(not key.endswith(('href','src')) for element in doc.iter() for key in element.attrib)
manifest=json.loads((UI/'metadata/gallery.json').read_text())
categories=json.loads((UI/'metadata/components.json').read_text())['categories']
outputs=gallery_outputs(manifest,categories)
maps=[name for name in outputs if name.endswith('.svg')]
assert len(maps)==3, maps
for name,data in outputs.items():
 assert (UI/name).read_bytes()==data,name
 if name.endswith('README.md'):
  assert b'gallery-map.svg)' in data,name
  assert bytes([96])*3+b'mermaid' not in data,name
`));

test('SVG capture provenance follows the complete renderer and runtime closure independently of map prose', () => python(`
import importlib.util,tempfile
from pathlib import Path
spec=importlib.util.spec_from_file_location('gallery',Path('ui/generate-gallery.py').resolve())
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
actual=module.source_hashes()
assert 'tools/webkit/scada/ui/gallery/renderer.py' in actual
assert 'tools/webkit/scada/ui/gallery/exporter.mjs' in actual
assert 'tools/webkit/scada/ui/gallery/asset_maps.py' not in actual
with tempfile.TemporaryDirectory() as directory:
 module.REPO=Path(directory);module.PACKAGE=module.REPO/'package';module.TOOLS=module.REPO/'gallery'
 files=[module.PACKAGE/'src/symbol.mjs',module.TOOLS/'renderer.py',module.TOOLS/'asset_maps.py',module.REPO/'tools/webkit/scada/scada_paths.py',module.REPO/'tools/webkit/scada/paths.mjs']
 for file in files:
  file.parent.mkdir(parents=True,exist_ok=True);file.write_text('original')
 baseline=module.source_hashes()
 (module.TOOLS/'asset_maps.py').write_text('new documentation')
 assert module.source_hashes()==baseline
 (module.TOOLS/'renderer.py').write_text('changed browser export')
 assert module.source_hashes()!=baseline
 (module.TOOLS/'renderer.py').write_text('original')
 (module.PACKAGE/'src/symbol.mjs').write_text('changed equipment art')
 assert module.source_hashes()!=baseline
`));

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
