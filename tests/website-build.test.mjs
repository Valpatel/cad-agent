// Build cad-agent.valpatel.com into a temporary folder from HEAD and check what would be published.
import test from 'node:test';
import assert from 'node:assert/strict';
import { execFileSync } from 'node:child_process';
import { mkdtemp, readFile, readdir, rm, writeFile } from 'node:fs/promises';
import { existsSync } from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { parseHeaders } from '../tools/preview-site.mjs';

const root = path.resolve(import.meta.dirname, '..');
const tmp = await mkdtemp(path.join(os.tmpdir(), 'cad-agent-website-'));
const build = dir => execFileSync(process.execPath, ['tools/build-site.mjs', '--out', dir], { cwd: root }).toString();
const out = path.join(tmp, 'a');
build(out);
test.after(() => rm(tmp, { recursive: true, force: true }));

const files = (await readdir(out, { recursive: true, withFileTypes: true })).filter(e => e.isFile())
  .map(e => path.relative(out, path.join(e.parentPath, e.name)).split(path.sep).join('/'));
const html = files.filter(f => f.endsWith('.html'));
const git = (...a) => execFileSync('git', a, { cwd: root }).toString();
// Cloudflare Pages resolution: /x serves x.html, /dir/ serves dir/index.html, files as they are.
const resolve = url => {
  const p = decodeURIComponent(url.split('#')[0].split('?')[0]).replace(/^\//, '');
  return [p, p + '.html', p.replace(/\/?$/, '/index.html').replace(/^\//, '')].find(c => files.includes(c));
};
const ids = async f => new Set([...(await readFile(path.join(out, f), 'utf8')).matchAll(/\bid="([^"]+)"/g)].map(m => m[1]));

test('only committed files are published, byte for byte', async () => {
  const webTracked = git('ls-tree', '-r', '--name-only', 'HEAD', 'web/').split('\n').filter(Boolean);
  const webOut = files.filter(f => f.startsWith('web/') && f !== 'web/snap-demo.css');
  assert.deepEqual(webOut.sort(), webTracked.sort());
  for (const f of webTracked) assert.ok((await readFile(path.join(out, f))).equals(execFileSync('git', ['show', `HEAD:${f}`], { cwd: root })), f);
});

test('a dirty checkout publishes HEAD, and a draft says it has local changes', async () => {
  // A scratch worktree of HEAD with an edited stylesheet, an edited doc and an untracked page planted in it.
  const wt = path.join(tmp, 'wt');
  execFileSync('git', ['worktree', 'add', '--detach', '--quiet', wt, 'HEAD'], { cwd: root });
  try {
    await writeFile(path.join(wt, 'web/site.css'), 'body{display:none}\n');
    await writeFile(path.join(wt, 'docs/planted.md'), '# Planted\n\nnot committed\n');
    await writeFile(path.join(wt, 'docs/toolkit.md'), '# Toolkit\n\nlocal edit <scr<script>x</script>ipt>window.__x=1</script>\n');
    const run = (...a) => execFileSync(process.execPath, ['tools/build-site.mjs', '--root', wt, ...a], { cwd: root }).toString();
    const clean = path.join(tmp, 'clean'), draft = path.join(tmp, 'draft');
    run('--out', clean);
    assert.equal(await readFile(path.join(clean, 'web/site.css'), 'utf8'), git('show', 'HEAD:web/site.css'));
    assert.ok(!existsSync(path.join(clean, 'docs/planted.html')), 'an untracked page was published');
    assert.doesNotMatch(await readFile(path.join(clean, 'docs/toolkit.html'), 'utf8'), /local edit/);
    run('--worktree', '--out', draft);
    const toolkit = await readFile(path.join(draft, 'docs/toolkit.html'), 'utf8');
    assert.match(toolkit, /local edit/);
    assert.match(toolkit, /\+ local changes/);
    assert.match(toolkit, /This page has uncommitted changes/);
    assert.doesNotMatch(toolkit, /<script>|window\.__x=1<\/script>/, 'a nested script survived the sanitizer');
    assert.throws(() => run('--release', '--out', path.join(tmp, 'rel')), /clean working tree/);
  } finally {
    execFileSync('git', ['worktree', 'remove', '--force', wt], { cwd: root });
  }
});

test('code samples keep their text, and every code block has a copy button', async () => {
  const dossier = await readFile(path.join(out, 'docs/dossier.html'), 'utf8');
  assert.match(dossier, /onto=None/, 'the sanitizer ate text inside code');
  const toolkit = await readFile(path.join(out, 'docs/toolkit.html'), 'utf8');
  const pres = (toolkit.match(/<pre>/g) || []).length, wrapped = (toolkit.match(/<cad-copy><pre>/g) || []).length;
  const diagrams = (toolkit.match(/<pre><code class="language-mermaid">/g) || []).length;
  assert.ok(pres > 3 && wrapped === pres - diagrams, `${wrapped} of ${pres} code blocks have a copy button`);
  assert.match(await readFile(path.join(out, 'index.html'), 'utf8'), /<cad-copy class="agent-copy"[^>]*><pre class="agent-box"/);
  assert.ok(files.includes('kit/copy.js'));
});

test('pages say when they were last updated and how to give feedback', async () => {
  const commitDay = git('show', '-s', '--format=%cs', 'HEAD').trim();
  const lessonDay = git('log', '-1', '--format=%cs', 'HEAD', '--', 'lessons/01-verify-from-source.md').trim();
  assert.match(await readFile(path.join(out, 'index.html'), 'utf8'), new RegExp(`Last updated <time datetime="${commitDay}">`));
  const lesson = await readFile(path.join(out, 'lessons/01-verify-from-source.html'), 'utf8');
  assert.match(lesson, new RegExp(`Last updated <time datetime="${lessonDay}">`), 'a page shows its own last change');
  const fb = lesson.match(/<aside class="feedback"[\s\S]*?<\/aside>/)?.[0];
  assert.ok(fb, 'doc pages end with the feedback box');
  const href = fb.match(/href="([^"]+)"/)[1].replace(/&amp;/g, '&');
  const u = new URL(href);
  assert.equal(u.origin + u.pathname, 'https://github.com/Valpatel/cad-agent/issues/new');
  assert.equal(u.searchParams.get('template'), 'feedback.yml');
  assert.equal(u.searchParams.get('page'), 'https://cad-agent.valpatel.com/lessons/01-verify-from-source');
  assert.match(fb, /edit\/dev\/lessons\/01-verify-from-source\.md/);
  const form = await readFile(path.join(root, '.github/ISSUE_TEMPLATE/feedback.yml'), 'utf8');
  assert.match(form, /id: page\b/, 'the issue form has the field the link fills in');
});

test('builds are reproducible: two builds of the same commit are identical', async () => {
  const again = path.join(tmp, 'b');
  build(again);
  for (const f of files) assert.ok((await readFile(path.join(out, f))).equals(await readFile(path.join(again, f))), f);
});

test('every internal link and anchor in the HTML resolves', async () => {
  const missing = [];
  for (const f of html) {
    if (f.startsWith('kit/')) continue;                                // the kit's own pages are tested with the kit
    const text = await readFile(path.join(out, f), 'utf8');
    const urls = [...text.matchAll(/<[a-z][^>]*>/gi)].flatMap(([tag]) =>   // real tags only: code text is not a link
      [...tag.matchAll(/\s(?:href|src)="([^"]+)"/gi)].map(m => m[1].replace(/&amp;/g, '&')));
    for (const url of urls) {
      if (/^(?:[a-z]+:|\/\/)/i.test(url)) continue;
      const abs = url.startsWith('#') ? '/' + f.replace(/\.html$/, '') + url : new URL(url, 'https://x/' + f).pathname + (url.includes('#') ? '#' + url.split('#')[1] : '');
      const target = resolve(abs);
      if (!target) { missing.push(`${f} → ${url}`); continue; }
      const hash = abs.split('#')[1];
      if (hash && target.endsWith('.html') && !(await ids(target)).has(decodeURIComponent(hash))) missing.push(`${f} → ${url} (anchor)`);
    }
  }
  assert.deepEqual(missing, []);
});

test('pages have one h1 and heading ids follow GitHub anchors', async () => {
  for (const f of html.filter(f => !f.startsWith('kit/'))) {
    const n = ((await readFile(path.join(out, f), 'utf8')).match(/<h1[\s>]/g) || []).length;
    assert.equal(n, 1, `${f} has ${n} h1`);
  }
  // GitHub's rule: entities decoded and punctuation dropped (no "39" from an encoded apostrophe), runs of spaces kept.
  for (const f of html.filter(f => !f.startsWith('kit/'))) {
    const text = await readFile(path.join(out, f), 'utf8');
    for (const [, id, inner] of text.matchAll(/<h[1-6] id="([^"]*)">([\s\S]*?)<\/h[1-6]>/g)) {
      assert.doesNotMatch(id, /(?:^|-)(?:39|quot|amp)(?:-|s-|$)/, `${f}: ${id}`);
      if (/[’'&]/.test(inner) || /&#39;|&amp;|&quot;/.test(inner)) assert.doesNotMatch(id, /\d{2}/.test(inner) ? /^$/ : /39/, `${f}: ${id}`);
    }
  }
  assert.ok((await ids('lessons/01-verify-from-source.html')).has('01--verify-from-source'), 'runs of spaces are not merged');
});

test('Markdown twins and llms-full.txt carry working links', async () => {
  const full = await readFile(path.join(out, 'llms-full.txt'), 'utf8');
  const relative = [...full.replace(/```[\s\S]*?```/g, '').matchAll(/\]\(([^)\s]+)/g)].map(m => m[1]).filter(u => !/^(?:[a-z]+:|#)/i.test(u));
  assert.deepEqual(relative, [], 'llms-full.txt is one file: its links must be absolute');
  const broken = [];
  for (const f of files.filter(f => f.endsWith('.md') && f !== 'index.md')) {
    const md = (await readFile(path.join(out, f), 'utf8')).replace(/```[\s\S]*?```/g, '');
    for (const [, url] of md.matchAll(/\]\(([^)\s#]+)(?:#[^)\s]*)?(?:\s+"[^"]*")?\)/g)) {
      if (/^(?:[a-z]+:|\/\/)/i.test(url)) continue;
      if (!files.includes(path.posix.normalize(path.posix.join(path.posix.dirname(f), url)))) broken.push(`${f} → ${url}`);
    }
  }
  assert.deepEqual(broken, []);
});

test('sitemap and catalogue use the URLs Pages serves without a redirect', async () => {
  const sitemap = await readFile(path.join(out, 'sitemap.xml'), 'utf8');
  const urls = [...sitemap.matchAll(/<loc>https:\/\/cad-agent\.valpatel\.com([^<]*)<\/loc>/g)].map(m => m[1]);
  assert.ok(urls.length > 40);
  for (const u of urls) { assert.doesNotMatch(u, /\.html$/); assert.ok(resolve(u), u); }
  const catalog = JSON.parse(await readFile(path.join(out, 'catalog.json'), 'utf8'));
  for (const i of catalog.items.filter(i => i.url.startsWith('https://cad-agent.valpatel.com'))) {
    assert.doesNotMatch(i.url, /\.html$/, i.name);
    assert.ok(resolve(i.url.slice('https://cad-agent.valpatel.com'.length)), i.url);
  }
});

test('catalogue statuses are honest', async () => {
  const catalog = JSON.parse(await readFile(path.join(out, 'catalog.json'), 'utf8'));
  const pyproject = (await readFile(path.join(root, 'pyproject.toml'), 'utf8')).toLowerCase();
  for (const lib of catalog.items.filter(i => i.type === 'library' && i.status === 'used')) {
    const pkg = lib.name.split('/').pop().toLowerCase();
    assert.match(pyproject, new RegExp(`"${pkg}[>=<\\[" ]`), `${lib.name} is marked used but is not a dependency`);
  }
  const cli = await readFile(path.join(root, 'src/cadagent/cli.py'), 'utf8');
  for (const t of catalog.items.filter(i => i.type === 'tool')) assert.ok(cli.includes(`"${t.name.replace('cad-agent ', '')}"`), t.name);
  const index = await readFile(path.join(out, 'index.html'), 'utf8');
  for (const [, cmd] of index.matchAll(/<code>cad-agent ([a-z0-9-]+)<\/code>/g))
    assert.ok(catalog.items.some(i => i.name === `cad-agent ${cmd}`), `landing page names cad-agent ${cmd}, which does not exist`);
  for (const i of catalog.items.filter(i => i.type === 'upstream')) assert.ok(i.summary, `${i.name} has no summary`);
});

test('headers: each header comes from one rule, and every inline script is allowed by hash', async () => {
  const text = await readFile(path.join(out, '_headers'), 'utf8');
  const rules = parseHeaders(text);
  for (const p of ['/', '/docs/toolkit', '/docs/toolkit.md', '/llms.txt', '/kit/vendor/three/three.module.min.js', '/kit/viewer']) {
    const seen = {};
    for (const r of rules) if (r.pattern.test(p)) for (const [k] of r.headers) seen[k.toLowerCase()] = (seen[k.toLowerCase()] || 0) + 1;
    for (const [k, n] of Object.entries(seen)) assert.equal(n, 1, `${p}: ${k} is set by ${n} rules and Pages would join them`);
    assert.ok(seen['content-security-policy'], `${p} has no CSP`);
  }
  const csp = text.match(/Content-Security-Policy: (.*)/)[1];
  assert.doesNotMatch(csp, /'unsafe-inline'[^;]*;.*script-src|script-src[^;]*'unsafe-inline'/);
  // The policy allows exactly the kit pages' inline scripts (copied byte for byte from the kit); site pages have none.
  const { createHash } = await import('node:crypto');
  const allowed = new Set(csp.match(/'sha256-[^']+'/g));
  const kitHashes = new Set();
  for (const f of html) for (const m of (await readFile(path.join(out, f), 'utf8')).matchAll(/<script\b(?![^>]*\bsrc=)[^>]*>([\s\S]*?)<\/script>/gi)) {
    if (!m[1].trim()) continue;
    assert.ok(f.startsWith('kit/'), `${f}: inline script on a site page`);
    assert.equal((await readFile(path.join(out, f), 'utf8')), git('show', `HEAD:src/cadagent/webkit/${f.slice(4)}`), `${f} is not the kit's own file`);
    kitHashes.add(`'sha256-${createHash('sha256').update(m[1]).digest('base64')}'`);
  }
  assert.deepEqual([...allowed].sort(), [...kitHashes].sort());
  assert.match(text, /Strict-Transport-Security: max-age=\d{8,}/);
  assert.ok(files.includes('favicon.ico'), 'browsers probe /favicon.ico on text pages');
  assert.ok(files.includes('kit/vendor/fonts/OFL-Inter.txt') && files.includes('kit/vendor/fonts/OFL-JetBrainsMono.txt'), 'font licences ship with the fonts');
  assert.ok(existsSync(path.join(out, '404.html')));
  for (const f of html) assert.doesNotMatch(await readFile(path.join(out, f), 'utf8'), /(?:href|src)="\s*(?:javascript|vbscript|data:text):/i, f);
  assert.ok(files.includes('THIRD_PARTY_NOTICES.html'), 'licence notices are published');
});

test('code samples keep their links as written (no rewriting inside code)', async () => {
  const viewer = await readFile(path.join(out, 'docs/file-viewer.html'), 'utf8');
  assert.match(viewer, /<code[^>]*>[^<]*href="kit\/file-viewer\.html\?file=/, 'the file-viewer snippet was rewritten');
  for (const f of files.filter(f => f.endsWith('.html') && !f.startsWith('kit/')))
    assert.ok(!(await readFile(path.join(out, f), 'utf8')).includes('&amp;amp;'), `${f}: an entity encoded twice`);
});

test('the snap-arm explorer is on its page with its still, and only that page loads its kit files', async () => {
  const page = await readFile(path.join(out, 'docs/compliant.html'), 'utf8');
  const demo = page.match(/<cad-cantilever\b[^>]*>([\s\S]*?)<\/cad-cantilever>/);
  assert.ok(demo, 'no <cad-cantilever> on /docs/compliant');
  assert.match(demo[1], /<img src="\/docs\/img\/compliant\/cantilever-explorer\.svg" alt="[^"]{40,}" width="640" height="250" ?\/?>/);
  const head = page.slice(0, page.indexOf('</head>'));
  assert.match(head, /<link rel="stylesheet" href="\/kit\/cantilever\.css"><link rel="modulepreload" href="\/kit\/cantilever\.js">/);
  for (const f of ['kit/cantilever.js', 'kit/cantilever.css', 'kit/formulas.js', 'kit/formulas-data.js', 'docs/img/compliant/cantilever-explorer.svg'])
    assert.ok(files.includes(f), `${f} is not published`);
  assert.doesNotMatch(await readFile(path.join(out, 'docs/toolkit.html'), 'utf8'), /cantilever\.(css|js)/);
});
