// Build cad-agent.valpatel.com into a temporary folder from HEAD and check what would be published.
import test from 'node:test';
import assert from 'node:assert/strict';
import { execFileSync } from 'node:child_process';
import { mkdtemp, readFile, readdir, rm } from 'node:fs/promises';
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
  for (const f of webTracked) assert.equal(await readFile(path.join(out, f), 'utf8'), git('show', `HEAD:${f}`), f);
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
    for (const [, url] of text.matchAll(/(?:href|src)="([^"]+)"/g)) {
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
  const { createHash } = await import('node:crypto');
  for (const f of html) for (const m of (await readFile(path.join(out, f), 'utf8')).matchAll(/<script\b(?![^>]*\bsrc=)[^>]*>([\s\S]*?)<\/script>/gi))
    if (m[1].trim()) assert.ok(csp.includes(`'sha256-${createHash('sha256').update(m[1]).digest('base64')}'`), `${f}: inline script not in CSP`);
  assert.ok(files.includes('kit/vendor/fonts/OFL-Inter.txt') && files.includes('kit/vendor/fonts/OFL-JetBrainsMono.txt'), 'font licences ship with the fonts');
  assert.ok(existsSync(path.join(out, '404.html')));
  for (const f of html) assert.doesNotMatch(await readFile(path.join(out, f), 'utf8'), /(?:href|src)="\s*(?:javascript|vbscript|data:text):/i, f);
  assert.ok(files.includes('THIRD_PARTY_NOTICES.html'), 'licence notices are published');
});
