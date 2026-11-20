// Builds of scratch git worktrees of HEAD with planted edits: what a dirty checkout publishes, what a --worktree draft
// shows, and which missing sources it refuses. Each test makes its own worktree and builds it; none reads the shared
// build. They are a file of their own so that node --test runs them beside website-build.test.mjs, not after it (#814).
import test from 'node:test';
import { YAML } from './npm-context.mjs';
import assert from 'node:assert/strict';
import { execFileSync } from 'node:child_process';
import { mkdir, mkdtemp, readFile, rm, writeFile } from 'node:fs/promises';
import { existsSync } from 'node:fs';
import os from 'node:os';
import path from 'node:path';

const root = path.resolve(import.meta.dirname, '../..');
const tmp = await mkdtemp(path.join(os.tmpdir(), 'cad-agent-website-drafts-'));
test.after(() => rm(tmp, { recursive: true, force: true }));
const git = (...a) => execFileSync('git', a, { cwd: root }).toString();

// Plant a page over a real one in a scratch worktree. The real page's figures (docs/pages.yaml) would look for its
// headings in the planted text, so its entry there goes too.
const plant = async (wt, page, text) => {
  await writeFile(path.join(wt, page), text);
  const spec = path.join(wt, 'docs/pages.yaml');
  const doc = YAML.parseDocument(await readFile(spec, 'utf8'));
  doc.delete(page);
  await writeFile(spec, doc.toString());
};

test('a dirty checkout publishes HEAD, and a draft says it has local changes', async () => {
  // A scratch worktree of HEAD with an edited stylesheet, an edited doc and an untracked page planted in it.
  const wt = path.join(tmp, 'wt');
  execFileSync('git', ['worktree', 'add', '--detach', '--quiet', wt, 'HEAD'], { cwd: root });
  try {
    await writeFile(path.join(wt, 'tools/site/assets/site.css'), 'body{display:none}\n');
    await writeFile(path.join(wt, 'docs/planted.md'), '# Planted\n\nnot committed\n');
    await writeFile(path.join(wt, 'tools/site/assets/planted-module.js'), 'export const draftOnly = true;\n');
    execFileSync('git',['add','tools/site/assets/planted-module.js'],{cwd:wt});
    await plant(wt, 'docs/toolkit.md', '# Toolkit\n\nlocal edit <scr<script>x</script>ipt>window.__x=1</script>\n');
    const run = (...a) => execFileSync(process.execPath, ['tools/site/build-site.mjs', '--root', wt, ...a], { cwd: root }).toString();
    const clean = path.join(tmp, 'clean'), draft = path.join(tmp, 'draft');
    run('--out', clean);
    assert.equal(await readFile(path.join(clean, 'web/site.css'), 'utf8'), git('show', 'HEAD:tools/site/assets/site.css'));
    assert.ok(!existsSync(path.join(clean, 'docs/planted.html')), 'an untracked page was published');
    assert.ok(!existsSync(path.join(clean, 'web/planted-module.js')), 'a staged-only module was published as committed output');
    assert.doesNotMatch(await readFile(path.join(clean, 'docs/toolkit.html'), 'utf8'), /local edit/);
    // Drawn by the reader's browser: this stylesheet would redraw every diagram (it is in their cache key) to no purpose.
    run('--worktree', '--client-diagrams', '--out', draft);
    const toolkit = await readFile(path.join(draft, 'docs/toolkit.html'), 'utf8');
    assert.match(toolkit, /local edit/);
    assert.match(toolkit, /\+ local changes/);
    assert.match(toolkit, /This page has uncommitted changes/);
    assert.equal(await readFile(path.join(draft, 'web/site.css'), 'utf8'), 'body{display:none}\n');
    assert.equal(await readFile(path.join(draft,'web/planted-module.js'),'utf8'),'export const draftOnly = true;\n','draft includes staged new assets');
    assert.ok(!existsSync(path.join(draft,'docs/planted.html')),'draft still excludes untracked files');
    assert.doesNotMatch(toolkit, /<script>|window\.__x=1<\/script>/, 'a nested script survived the sanitizer');
    assert.throws(() => run('--release', '--out', path.join(tmp, 'rel')), /clean working tree/);
    await mkdir(path.join(wt, 'web'), { recursive: true });
    await writeFile(path.join(wt, 'web/site.css'), 'STALE_ROOT_ASSET');
    await rm(path.join(wt, 'tools/site/assets/site.css'));
    assert.throws(() => run('--worktree', '--client-diagrams', '--out', draft), error =>
      String(error.stderr).includes('ENOENT') && String(error.stderr).includes('tools/site/assets/site.css'),
    'a stale web/site.css must not hide a missing current stylesheet');
  } finally {
    execFileSync('git', ['worktree', 'remove', '--force', wt], { cwd: root });
  }
});

test('an image keeps the size its author gave, and its tag survives any alt text', async () => {
  const wt = path.join(tmp, 'wt-img');
  execFileSync('git', ['worktree', 'add', '--detach', '--quiet', wt, 'HEAD'], { cwd: root });
  try {
    const fig = 'img/research/fdm-anisotropy.svg';
    const [W, H] = (await readFile(path.join(root, 'docs', fig), 'utf8')).match(/width="(\d+)" height="(\d+)"/).slice(1).map(Number);
    await plant(wt, 'docs/toolkit.md', `# Toolkit\n\n<img src="${fig}" alt="costs US$'s and $& and $$" width="300">\n\n` +
      `<img src="${fig}" alt="half" width="50%">\n\n<img src="${fig}" alt="short" height="100">\n\nAfter the images.\n`);
    const draft = path.join(tmp, 'draft-img');
    execFileSync(process.execPath, ['tools/site/build-site.mjs', '--root', wt, '--worktree', '--out', draft], { cwd: root });
    const page = await readFile(path.join(draft, 'docs/toolkit.html'), 'utf8');
    const tag = alt => page.match(new RegExp(`<img\\b[^>]*alt="${alt}"[^>]*>`))?.[0] || '';
    assert.match(tag("costs US\\$'s and \\$&amp;? and \\$\\$"), new RegExp(`width="300" height="${Math.round(300 * H / W)}"`), 'a pixel width stays; the height follows');
    assert.equal((page.match(/After the images\./g) || []).length, 1, '"$\'" in an alt text must not copy the rest of the page');
    assert.equal((page.match(/<\/html>/g) || []).length, 1);
    assert.match(tag('half'), new RegExp(`width="${W}" height="${H}" style="width:50%"`), 'a percentage is honoured, with the proportions kept');
    assert.match(tag('short'), new RegExp(`width="${Math.round(100 * W / H)}" height="100"`), 'a pixel height stays; the width follows');
  } finally {
    execFileSync('git', ['worktree', 'remove', '--force', wt], { cwd: root });
  }
});

test('the palette goes into real diagrams only: not into a quoted example, and :::here counts', async () => {
  const wt = path.join(tmp, 'wt-palette');
  execFileSync('git', ['worktree', 'add', '--detach', '--quiet', wt, 'HEAD'], { cwd: root });
  try {
    await plant(wt, 'docs/toolkit.md', '# Toolkit\n\n' +
      '```mermaid\nflowchart TD\n    A[a]:::here --> B[b]\n```\n\n' +
      '````markdown\n```mermaid\nflowchart TD\n    Q[quoted]\n    class Q out\n```\n````\n');
    const draft = path.join(tmp, 'draft-palette');
    execFileSync(process.execPath, ['tools/site/build-site.mjs', '--root', wt, '--worktree', '--out', draft], { cwd: root });
    const page = await readFile(path.join(draft, 'docs/toolkit.html'), 'utf8');
    const diagram = page.match(/<pre class="cad-diagram-source">([\s\S]*?)<\/pre>|<code class="language-mermaid">([\s\S]*?)<\/code>/)?.slice(1).join('') || '';
    assert.match(diagram, /classDef here fill:#fffdf5/, ':::here shorthand gets the palette');
    assert.doesNotMatch(diagram, /classDef (?:near|out)/, 'only the classes the diagram uses');
    const quoted = page.match(/<code class="language-markdown">([\s\S]*?)<\/code>/)?.[1] || '';
    assert.match(quoted, /class Q out/);
    assert.doesNotMatch(quoted, /classDef/, 'a Mermaid example inside another fence stays as written');
  } finally {
    execFileSync('git', ['worktree', 'remove', '--force', wt], { cwd: root });
  }
});

test('a real draft consumes moved sources and cannot substitute stale root files when they are missing', async () => {
  const wt = path.join(tmp, 'wt-policy');
  execFileSync('git', ['worktree', 'add', '--detach', '--quiet', wt, 'HEAD'], { cwd: root });
  try {
    await writeFile(path.join(wt, '.github/CONTRIBUTING.md'), '# Current policy\n\nMOVED_SOURCE_SENTINEL.\n\n[Commands](../docs/toolkit.md#commands)\n');
    await writeFile(path.join(wt, 'CONTRIBUTING.md'), '# Stale root policy\n\nSTALE_ROOT_SENTINEL.\n');
    await writeFile(path.join(wt, 'software/vendor/THIRD_PARTY_NOTICES.md'), '# Third-party notices\n\nMOVED_NOTICE_SENTINEL.\n\n[Commands](../../docs/toolkit.md#commands)\n');
    await writeFile(path.join(wt, 'THIRD_PARTY_NOTICES.md'), '# Stale root notices\n\nSTALE_NOTICE_SENTINEL.\n');
    const registry = path.join(wt, 'software/vendor/upstreams/registry.yaml');
    const upstreams = YAML.parse(await readFile(registry, 'utf8'));
    upstreams[0].what = 'REGISTRY_SOURCE_SENTINEL';
    await writeFile(registry, YAML.stringify(upstreams));
    await mkdir(path.join(wt, 'upstreams'), { recursive: true });
    await writeFile(path.join(wt, 'upstreams', 'registry.yaml'), '[]\n');
    const guide = 'docs/practice/weekly-upstream-update.md';
    await plant(wt, guide, '# Weekly upstream update\n\nMOVED_GUIDE_SENTINEL.\n\n[Commands](../toolkit.md#commands)\n');
    await writeFile(path.join(wt, 'docs/weekly-upstream-update.md'), '# Stale guide\n\nSTALE_GUIDE_SENTINEL.\n');
    const landscapeSource = 'docs/research/landscape.json';
    const landscape = JSON.parse(await readFile(path.join(wt, landscapeSource), 'utf8'));
    landscape.libraries[0].what = 'RESEARCH_SOURCE_SENTINEL';
    await writeFile(path.join(wt, landscapeSource), JSON.stringify(landscape));
    await mkdir(path.join(wt, 'research'), { recursive: true });
    await writeFile(path.join(wt, 'research/landscape.json'), '{"projects":[],"libraries":[],"benchmarks":[]}\n');
    const draft = path.join(tmp, 'draft-policy');
    const run = () => execFileSync(process.execPath, ['tools/site/build-site.mjs', '--root', wt, '--worktree', '--client-diagrams', '--out', draft], { cwd: root, encoding: 'utf8', stdio: ['ignore', 'pipe', 'pipe'] });
    run();
    const page = await readFile(path.join(draft, 'CONTRIBUTING.html'), 'utf8');
    assert.match(page, /MOVED_SOURCE_SENTINEL/);
    assert.doesNotMatch(page, /STALE_ROOT_SENTINEL/);
    assert.match(page, /href="\/docs\/toolkit#commands"/);
    assert.match(await readFile(path.join(draft, 'CONTRIBUTING.md'), 'utf8'), /\]\(docs\/toolkit\.md#commands\)/);
    const notice = await readFile(path.join(draft, 'THIRD_PARTY_NOTICES.html'), 'utf8');
    assert.match(notice, /MOVED_NOTICE_SENTINEL/);
    assert.doesNotMatch(notice, /STALE_NOTICE_SENTINEL/);
    assert.match(notice, /href="\/docs\/toolkit#commands"/);
    assert.match(await readFile(path.join(draft, 'THIRD_PARTY_NOTICES.md'), 'utf8'), /\]\(docs\/toolkit\.md#commands\)/);
    const catalog = JSON.parse(await readFile(path.join(draft, 'catalog.json'), 'utf8'));
    assert.equal(catalog.items.find(i => i.name === upstreams[0].name).what, 'REGISTRY_SOURCE_SENTINEL');
    assert.equal(catalog.items.find(i => i.kind === 'library' && i.name === landscape.libraries[0].name).what, 'RESEARCH_SOURCE_SENTINEL');
    const movedGuide = await readFile(path.join(draft, 'docs/weekly-upstream-update.html'), 'utf8');
    assert.match(movedGuide, /MOVED_GUIDE_SENTINEL/);
    assert.doesNotMatch(movedGuide, /STALE_GUIDE_SENTINEL/);
    assert.match(movedGuide, /href="\/docs\/toolkit#commands"/);
    assert.match(await readFile(path.join(draft, 'docs/weekly-upstream-update.md'), 'utf8'), /\]\(toolkit\.md#commands\)/);
    for (const source of ['.github/CONTRIBUTING.md', 'software/vendor/THIRD_PARTY_NOTICES.md', 'software/vendor/upstreams/registry.yaml', guide, landscapeSource]) {
      const current = await readFile(path.join(wt, source));
      await rm(path.join(wt, source));
      assert.throws(run, error => String(error.stderr).includes('ENOENT') && String(error.stderr).includes(source),
        `${source}: missing real source must fail even while the stale root file still exists`);
      await writeFile(path.join(wt, source), current);
    }
  } finally {
    execFileSync('git', ['worktree', 'remove', '--force', wt], { cwd: root });
  }
});
