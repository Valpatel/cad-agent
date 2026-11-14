import {SIM, TOOLS, TESTS} from '../../../../tools/webkit/scada/paths.mjs';
import assert from 'node:assert/strict';
import {mkdtemp, mkdir, readFile, writeFile, cp, readdir, lstat, readlink, symlink, rm, chmod} from 'node:fs/promises';
import {tmpdir} from 'node:os';
import {resolve, dirname, join} from 'node:path';
import {fileURLToPath} from 'node:url';
import {spawnSync} from 'node:child_process';
import test from 'node:test';

const packageRoot=SIM;
const generator = join(TOOLS, 'sim/generate-scenario-docs.py');

async function fixture(t) {
  const root = await mkdtemp(join(tmpdir(), 'scada-scenario-docs-'));
  t.after(() => rm(root, {recursive:true, force:true}));
  const catalog = JSON.parse(await readFile(join(packageRoot, 'scenarios/index.json'), 'utf8'));
  catalog.scenarios = catalog.scenarios.filter(item => ['winery', 'electric-batch-oven'].includes(item.id));
  for (const entry of catalog.scenarios) {
    const folder = join(root, 'scenarios', entry.id);
    await mkdir(folder, {recursive:true});
    for (const name of ['system.json', 'model.json']) {
      await cp(join(packageRoot, 'scenarios', entry.id, name), join(folder, name));
    }
  }
  await writeFile(join(root, 'scenarios/index.json'), JSON.stringify(catalog));
  await mkdir(join(root, 'scenarios/unregistered-draft'));
  await writeFile(join(root, 'scenarios/unregistered-draft/README.md'), 'Private draft: preserve this.\n');
  return root;
}

function run(root, check = false) {
  const result = spawnSync('python3', [generator, '--package-root', root, ...(check ? ['--check'] : [])], {
    cwd:tmpdir(), encoding:'utf8', env:{...process.env, PYTHONDONTWRITEBYTECODE:'1'},
  });
  assert.ifError(result.error);
  return result;
}

async function snapshot(root, prefix = '') {
  const entries = [];
  for (const name of (await readdir(join(root, prefix))).sort()) {
    const relative = join(prefix, name), path = join(root, relative), stat = await lstat(path, {bigint:true});
    if (stat.isSymbolicLink()) entries.push([relative, 'symlink', await readlink(path)]);
    else if (stat.isDirectory()) entries.push(...await snapshot(root, relative));
    else entries.push([relative, stat.mode.toString(), stat.mtimeNs.toString(), (await readFile(path)).toString('base64')]);
  }
  return entries;
}

async function editJson(path, edit) {
  const value = JSON.parse(await readFile(path, 'utf8'));
  edit(value);
  await writeFile(path, JSON.stringify(value));
}

test('scenario docs derive facts, remain deterministic and detect changed JSON without writing', async t => {
  const root = await fixture(t);
  const missingBefore = await snapshot(root);
  assert.equal(run(root, true).status, 1);
  assert.deepEqual(await snapshot(root), missingBefore, 'check must not create missing output');
  assert.equal(run(root).status, 0);
  assert.equal(JSON.parse(run(root).stdout).changed, 0);
  assert.equal(run(root, true).status, 0);
  const winery = join(root, 'scenarios/winery/README.md');
  const initial = await readFile(winery, 'utf8');
  assert.match(initial, /Generated scenario map/);
  assert.match(initial, /img\/topologies\/food-beverage\/winery\/topology\.svg/);
  assert.match(initial, /img\/thumbnails\/food-beverage\/winery\/preview\.jpg/);
  assert.doesNotMatch(initial, /```mermaid/);
  const index = await readFile(join(root, 'scenarios/README.md'), 'utf8');
  assert.match(index, /The 2 scenario folders/);
  assert.match(index, /v1: 1; v2: 1/);
  assert.match(index, /\[Open the complete contact sheet\]/);

  await editJson(join(root, 'scenarios/winery/model.json'), model => {
    model.components.grapeIntake.kind = 'storage';
  });
  await editJson(join(root, 'scenarios/index.json'), catalog => {
    catalog.scenarios[0].title = 'Edited winery title';
    catalog.scenarios[0].experiments[0].title = 'Edited command recipe';
  });
  const before = await snapshot(root);
  const stale = run(root, true);
  assert.equal(stale.status, 1);
  assert.match(stale.stderr, /Stale scenario documentation.*winery\/README\.md/);
  assert.deepEqual(await snapshot(root), before, 'check must not change bytes, mtimes, or file set');
  assert.equal(run(root).status, 0);
  const updated = await readFile(winery, 'utf8');
  assert.match(updated, /^# Edited winery title/);
  assert.match(updated, /Edited command recipe/);
  assert.match(updated, /`grapeIntake`.*`storage`/);
  assert.equal(await readFile(join(root, 'scenarios/unregistered-draft/README.md'), 'utf8'), 'Private draft: preserve this.\n');
  assert.equal(run(root, true).status, 0);
});

test('scenario docs normalize archive member permissions while check remains read-only', async t => {
  const root=await fixture(t);
  assert.equal(run(root).status,0);
  const target=join(root,'scenarios/winery/README.md');
  const contents=await readFile(target);
  assert.equal((await lstat(target)).mode&0o7777,0o644,'new generated maps have reproducible readable modes');
  await chmod(target,0o600);
  const before=await snapshot(root);
  const checked=run(root,true);
  assert.equal(checked.status,1);
  assert.match(checked.stderr,/Stale scenario documentation.*winery\/README\.md/);
  assert.deepEqual(await snapshot(root),before,'check changes neither file data nor permissions');
  assert.equal(JSON.parse(run(root).stdout).changed,1);
  assert.equal((await lstat(target)).mode&0o7777,0o644);
  assert.deepEqual(await readFile(target),contents,'permission repair preserves generated prose');
  assert.equal(run(root,true).status,0);
  assert.equal(await readFile(join(root,'scenarios/unregistered-draft/README.md'),'utf8'),'Private draft: preserve this.\n');
});

test('scenario docs reject invalid catalog claims before any output mutation', async t => {
  const cases = [
    ['duplicate ID', catalog => catalog.scenarios.push({...catalog.scenarios[0]}), /Duplicate scenario ID/],
    ['unsafe ID', catalog => { catalog.scenarios[1].id = '../escape'; }, /Unsafe scenario ID/],
    ['unexpected input path', catalog => { catalog.scenarios[1].model = '../../elsewhere/model.json'; }, /Unexpected model path/],
  ];
  for (const [label, edit, message] of cases) await t.test(label, async t => {
    const root = await fixture(t);
    assert.equal(run(root).status, 0);
    await writeFile(join(root, 'scenarios/winery/README.md'), 'Deliberately stale but must survive invalid input.\n');
    await editJson(join(root, 'scenarios/index.json'), edit);
    const before = await snapshot(root);
    for (const check of [false, true]) {
      const result = run(root, check);
      assert.equal(result.status, 1);
      assert.match(result.stderr, message);
      assert.deepEqual(await snapshot(root), before);
    }
  });
});

test('scenario docs reject malformed late definitions and duplicate JSON keys before earlier writes', async t => {
  const root = await fixture(t);
  assert.equal(run(root).status, 0);
  await writeFile(join(root, 'scenarios/winery/README.md'), 'Earlier output sentinel.\n');
  const model = join(root, 'scenarios/electric-batch-oven/model.json');
  const original = await readFile(model, 'utf8');
  for (const invalid of ['{"format":"one","format":"two"}', '{invalid JSON']) {
    await writeFile(model, invalid);
    const before = await snapshot(root);
    const result = run(root);
    assert.equal(result.status, 1);
    assert.match(result.stderr, /Invalid JSON/);
    assert.deepEqual(await snapshot(root), before);
  }
  await writeFile(model, original);
});

test('scenario docs reject symlinked inputs, output files and scenario folders', async t => {
  for (const kind of ['input', 'output', 'folder']) await t.test(kind, async t => {
    const root = await fixture(t);
    assert.equal(run(root).status, 0);
    await writeFile(join(root, 'scenarios/winery/README.md'), 'Earlier output sentinel.\n');
    if (kind === 'folder') {
      const path = join(root, 'scenarios/electric-batch-oven');
      await cp(path, join(root, 'external-target'), {recursive:true});
      await rm(path, {recursive:true});
      await symlink('../external-target', path);
    } else {
      const path = join(root, 'scenarios/electric-batch-oven', kind === 'input' ? 'model.json' : 'README.md');
      await cp(path, join(root, 'external-target'));
      await rm(path);
      await symlink('../../external-target', path);
    }
    const before = await snapshot(root);
    for (const check of [false, true]) {
      const result = run(root, check);
      assert.equal(result.status, 1);
      assert.match(result.stderr, /Symlinks are not allowed/);
      assert.deepEqual(await snapshot(root), before);
    }
  });
});
