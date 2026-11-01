// Build cad-agent.valpatel.com into a temporary folder from HEAD and check what would be published.
import test from 'node:test';
import assert from 'node:assert/strict';
import { execFileSync, spawn } from 'node:child_process';
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
// Anchor targets from real tags only: `<h2 id="x">` shown in a code sample is text, not a target.
const idsIn = text => new Set([...text.matchAll(/<[a-z][^>]*>/gi)].flatMap(([tag]) => [...tag.matchAll(/\sid="([^"]+)"/gi)].map(m => m[1])));
const ids = async f => idsIn(await readFile(path.join(out, f), 'utf8'));

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
  const lessonDay = git('log', '-1', '--format=%cs', 'HEAD', '--', 'lessons/process/verify-from-source.md').trim();
  assert.match(await readFile(path.join(out, 'index.html'), 'utf8'), new RegExp(`Last updated <time datetime="${commitDay}">`));
  const lesson = await readFile(path.join(out, 'lessons/process/verify-from-source.html'), 'utf8');
  assert.match(lesson, new RegExp(`Last updated <time datetime="${lessonDay}">`), 'a page shows its own last change');
  const fb = lesson.match(/<aside class="feedback"[\s\S]*?<\/aside>/)?.[0];
  assert.ok(fb, 'doc pages end with the feedback box');
  const href = fb.match(/href="([^"]+)"/)[1].replace(/&amp;/g, '&');
  const u = new URL(href);
  assert.equal(u.origin + u.pathname, 'https://github.com/Valpatel/cad-agent/issues/new');
  assert.equal(u.searchParams.get('template'), 'feedback.yml');
  assert.equal(u.searchParams.get('page'), 'https://cad-agent.valpatel.com/lessons/process/verify-from-source');
  assert.match(fb, /edit\/dev\/lessons\/process\/verify-from-source\.md/);
  const form = await readFile(path.join(root, '.github/ISSUE_TEMPLATE/feedback.yml'), 'utf8');
  assert.match(form, /id: page\b/, 'the issue form has the field the link fills in');
});

test('builds are reproducible: two builds of the same commit are identical', async () => {
  const again = path.join(tmp, 'b');
  build(again);
  for (const f of files) assert.ok((await readFile(path.join(out, f))).equals(await readFile(path.join(again, f))), f);
});

test('every internal link and anchor in the HTML resolves', async () => {
  assert.deepEqual([...idsIn('<h2 id="real">x</h2><pre><code>&lt;h2 id="in-code"&gt;</code></pre>')], ['real']);
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
  assert.ok((await ids('lessons/process/README.html')).has('lessons--process'), 'runs of spaces are not merged');
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

test('an image keeps the size its author gave, and its tag survives any alt text', async () => {
  const wt = path.join(tmp, 'wt-img');
  execFileSync('git', ['worktree', 'add', '--detach', '--quiet', wt, 'HEAD'], { cwd: root });
  try {
    const fig = 'img/research/fdm-anisotropy.svg';
    const [W, H] = (await readFile(path.join(root, 'docs', fig), 'utf8')).match(/width="(\d+)" height="(\d+)"/).slice(1).map(Number);
    await writeFile(path.join(wt, 'docs/toolkit.md'), `# Toolkit\n\n<img src="${fig}" alt="costs US$'s and $& and $$" width="300">\n\n` +
      `<img src="${fig}" alt="half" width="50%">\n\n<img src="${fig}" alt="short" height="100">\n\nAfter the images.\n`);
    const draft = path.join(tmp, 'draft-img');
    execFileSync(process.execPath, ['tools/build-site.mjs', '--root', wt, '--worktree', '--out', draft], { cwd: root });
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

test('doc pages carry the page tree, with this page marked', async () => {
  const toolkit = await readFile(path.join(out, 'docs/toolkit.html'), 'utf8');
  const nav = toolkit.match(/<cad-nav [^>]*>([\s\S]*?)<\/cad-nav>/)?.[1];
  assert.ok(nav, 'no <cad-nav> on a doc page');
  assert.equal((nav.match(/aria-current="page"/g) || []).length, 1);
  assert.match(nav, /<a href="\/docs\/toolkit" aria-current="page">/);
  const catalog = JSON.parse(await readFile(path.join(out, 'catalog.json'), 'utf8'));
  for (const doc of catalog.items.filter(i => i.markdown && i.status === 'ours' && ['doc', 'lesson', 'skill', 'agent', 'research'].includes(i.type)))
    assert.ok(nav.includes(`href="${doc.url.replace('https://cad-agent.valpatel.com', '')}"`), `${doc.name} is missing from the page tree`);
  assert.ok(files.includes('kit/nav.js') && files.includes('kit/nav.css'));
  // Written out in full, so the first paint is final and it works without script: a landmark, the toggle, the
  // filter, and this page's outline (every h2/h3 with an id) under it, again in the right-hand column.
  assert.match(toolkit, /<cad-nav [^>]*role="navigation" aria-label="Pages and contents"/);
  assert.match(toolkit, /<link rel="stylesheet" href="\/kit\/nav\.css">/);
  assert.match(nav, /^<button type="button" class="cad-nav-toggle" aria-expanded="false">/);
  assert.match(nav, /<div class="cad-nav-panel"><input type="search" class="cad-nav-filter"/);
  const article = toolkit.match(/<article class="prose">([\s\S]*?)<\/article>/)[1];
  const heads = [...article.matchAll(/<h[23] id="([^"]+)">/g)].map(m => m[1]);
  const listed = list => [...list.matchAll(/<a href="#([^"]+)">/g)].map(m => decodeURIComponent(m[1]));
  const inTree = nav.match(/aria-current="page">[^<]*<\/a><ol class="cad-nav-outline"[^>]*>([\s\S]*?)<\/ol>/)?.[1];
  assert.deepEqual(listed(inTree ?? ''), heads, 'the outline under the current page lists every h2/h3');
  const rail = toolkit.match(/<nav class="doc-rail" aria-labelledby="rail-title">([\s\S]*?)<\/nav>/)?.[1];
  assert.deepEqual(listed(rail ?? ''), heads, 'the right-hand outline lists every h2/h3');
  assert.match(toolkit, /<body[^>]*><a class="skip-link" href="#main:content">Skip to content<\/a>/);
  assert.match(toolkit, /<div class="doc-main" id="main:content" tabindex="-1">/);
  // The rail is named once, by its visible title; the outline in the tree keeps its own name inside "Pages and contents".
  assert.match(toolkit, /<nav class="doc-rail" aria-labelledby="rail-title"><p class="doc-rail-title" id="rail-title">On this page<\/p><ol class="cad-nav-outline cad-nav-rail">/);
  assert.match(toolkit, /aria-current="page">[^<]*<\/a><ol class="cad-nav-outline" aria-label="On this page">/);
});

// Owner (2026-10-31): "make sure every page has some interesting diagrams, animations, renders etc, don't make them
// boring." The pages that still have no picture, render, diagram or demo, exactly (the backlog in #122, now empty). A
// new page without one fails; if one must ship without, list it here with the issue that adds its visual.
const PAGES_WITHOUT_VISUALS = [];   // #124 gave every page one; keep it empty
test('the pages without a picture, diagram or demo are exactly the known backlog', async () => {
  const { without } = JSON.parse(await readFile(path.join(out, 'visuals.json'), 'utf8'));
  const gained = PAGES_WITHOUT_VISUALS.filter(p => !without.includes(p)), lacking = without.filter(p => !PAGES_WITHOUT_VISUALS.includes(p));
  assert.deepEqual(lacking, [], `add a diagram, render or demo to: ${lacking.join(', ')}`);
  assert.deepEqual(gained, [], `these now have something to look at; remove them from PAGES_WITHOUT_VISUALS: ${gained.join(', ')}`);
});

test('a moved page leaves a stub on GitHub and a 301 on the site', async () => {
  const stubs = git('grep', '-l', '-e', '^<!-- moved-to:', 'HEAD', '--', '*.md').split('\n').filter(Boolean).map(l => l.replace(/^HEAD:/, ''));
  assert.ok(stubs.length >= 12, 'the twelve numbered lessons are stubs');
  const redirects = new Map((await readFile(path.join(out, '_redirects'), 'utf8')).trim().split('\n').map(l => l.split(' ')).map(([f, ...r]) => [f, r]));
  const catalog = await readFile(path.join(out, 'catalog.json'), 'utf8');
  for (const stub of stubs) {
    const from = '/' + stub.replace(/\.md$/, '');
    assert.ok(!files.includes(stub.replace(/\.md$/, '.html')) && !files.includes(stub), `${stub} is not published`);
    assert.ok(!catalog.includes(`"${stub.replace(/\.md$/, '')}"`) && !catalog.includes(from + '"'), `${stub} is not catalogued`);
    const [to, code] = redirects.get(from) || [];
    assert.equal(code, '301', from);
    assert.ok(resolve(to)?.endsWith('.html'), `${from} → ${to}, a page`);
    assert.deepEqual(redirects.get('/' + stub), [to + '.md', '301'], 'its Markdown twin moves too');
    assert.ok(files.includes(to.slice(1) + '.md'));
  }
  // The preview server answers the way Pages does, keeping the query.
  const server = spawn(process.execPath, ['tools/preview-site.mjs', '--dir', out, '--port', '0'], { cwd: root });
  try {
    const base = await new Promise((ok, fail) => {
      server.stdout.on('data', d => { const m = String(d).match(/http:\/\/[\d.]+:\d+/); if (m) ok(m[0]); });
      server.on('exit', c => fail(new Error(`preview server exited ${c}`)));
    });
    const res = await fetch(`${base}/lessons/03-mechanical-design-rules?x=1`, { redirect: 'manual' });
    assert.equal(res.status, 301);
    assert.equal(res.headers.get('location'), '/lessons/mechanical/design-rules?x=1');
    assert.equal((await fetch(`${base}/lessons/mechanical/design-rules`)).status, 200);
  } finally { server.kill(); }
});

test('a link to a folder opens its README page', async () => {
  const index = await readFile(path.join(out, 'lessons/README.html'), 'utf8');
  for (const area of ['process', 'mechanical', 'wiring', 'electronics', 'simulation', 'review']) {
    assert.match(index, new RegExp(`href="/lessons/${area}/README"`), area);
    assert.doesNotMatch(index, new RegExp(`href="https://github.com/[^"]*/tree/dev/lessons/${area}/?"`), area);
  }
  assert.match(await readFile(path.join(out, 'lessons/README.md'), 'utf8'), /\]\(process\/README\.md\)/, 'the Markdown twin too');
});

test('every lesson page has a diagram, and the home page counts lessons, not pages', async () => {
  const lessons = files.filter(f => /^lessons\/.+\.html$/.test(f));
  assert.ok(lessons.length >= 19, 'the index, six area READMEs and twelve lesson files');
  for (const f of lessons) assert.match(await readFile(path.join(out, f), 'utf8'), /class="language-mermaid"|<img\b/, `${f} has no diagram or picture`);
  const rules = git('grep', '-h', '-e', '^### ', 'HEAD', '--', 'lessons/*/*.md', ':!lessons/*/README.md').split('\n').filter(Boolean).length;
  assert.ok(rules > 50);
  assert.match(await readFile(path.join(out, 'index.html'), 'utf8'), new RegExp(`Fill the gaps</span><span class="mission-num">${rules}<`));
});

test('redirects outlive the stubs, and a stub must point at a published page that is listed', async () => {
  const wt = path.join(tmp, 'wt-redirects');
  execFileSync('git', ['worktree', 'add', '--detach', '--quiet', wt, 'HEAD'], { cwd: root });
  const commit = msg => execFileSync('git', ['-c', 'user.name=test', '-c', 'user.email=test@example.invalid', 'commit', '-qam', msg], { cwd: wt });
  const buildWt = dir => execFileSync(process.execPath, ['tools/build-site.mjs', '--root', wt, '--out', dir], { cwd: root, stdio: 'pipe' });
  const stub = 'lessons/03-mechanical-design-rules.md';
  try {
    // v0.6.0 deletes the stubs: the site keeps every 301.
    execFileSync('git', ['rm', '-q', ...git('grep', '-l', '-e', '^<!-- moved-to:', 'HEAD', '--', '*.md').split('\n').filter(Boolean)
      .map(l => l.replace(/^HEAD:/, ''))], { cwd: wt });
    commit('drop the stubs');
    const after = path.join(tmp, 'no-stubs');
    buildWt(after);
    assert.equal(await readFile(path.join(after, '_redirects'), 'utf8'), await readFile(path.join(out, '_redirects'), 'utf8'));
    execFileSync('git', ['checkout', '-q', 'HEAD~1'], { cwd: wt });
    // A stub that points at a file the site does not publish, or at another stub, fails the build.
    for (const [target, why] of [['../CLAUDE.md', 'not a published page'], ['04-fasteners-and-assembly-access.md', 'not a published page']]) {
      await writeFile(path.join(wt, stub), `<!-- moved-to: ${target} -->\n# Moved\n`);
      commit(`stub to ${target}`);
      assert.throws(() => buildWt(path.join(tmp, 'bad')), e => String(e.stderr).includes(why), target);
      execFileSync('git', ['checkout', '-q', 'HEAD~1'], { cwd: wt });
    }
    // Bad lines in the list fail the build: a source listed twice (Pages keeps the first, the preview server the last),
    // a leading slash, a source that is not a .md path or not a plain path (a splat, a placeholder, `..`, `//`, `./`),
    // a file that is still in the repo, and a stub listed elsewhere.
    const list = path.join(wt, 'tools/site-redirects.txt');
    const original = await readFile(list, 'utf8');
    for (const [line, why] of [
      [`${stub} lessons/README.md`, 'is listed twice'],
      ['/lessons/gone.md lessons/README.md', 'without a leading slash'],
      ['lessons/gone lessons/README.md', 'without a leading slash'],
      ['web/site.css lessons/README.md', 'without a leading slash'],
      ['lessons/*.md lessons/README.md', 'without a leading slash'],          // a Pages splat: every lesson would loop
      ['lessons/:name.md lessons/README.md', 'without a leading slash'],      // a Pages placeholder
      ['lessons/../gone.md lessons/README.md', 'without a leading slash'],
      ['lessons//gone.md lessons/README.md', 'without a leading slash'],
      ['lessons/./gone.md lessons/README.md', 'without a leading slash'],
      ['docs/toolkit.md lessons/README.md', 'is still a file in the repo'],
    ]) {
      await writeFile(list, original + line + '\n');
      commit(`bad line ${line}`);
      assert.throws(() => buildWt(path.join(tmp, 'bad-line')), e => String(e.stderr).includes(why), line);
      execFileSync('git', ['checkout', '-q', 'HEAD~1'], { cwd: wt });
    }
    await writeFile(list, original.replace(`${stub} lessons/mechanical/design-rules.md`, `${stub} lessons/README.md`));
    commit('stub listed elsewhere');
    assert.throws(() => buildWt(path.join(tmp, 'bad3')), e => String(e.stderr).includes('change its line'));
    execFileSync('git', ['checkout', '-q', 'HEAD~1'], { cwd: wt });
    // A stub missing from tools/site-redirects.txt fails the build too.
    await writeFile(list, original.split('\n').filter(l => !l.startsWith(stub)).join('\n'));
    commit('unlisted stub');
    assert.throws(() => buildWt(path.join(tmp, 'bad2')), e => String(e.stderr).includes('add "' + stub));
  } finally {
    execFileSync('git', ['worktree', 'remove', '--force', wt], { cwd: root });
  }
});

test('every local image has its width and height, so nothing jumps while it loads', async () => {
  const bare = [];
  for (const f of html.filter(f => !f.startsWith('kit/'))) {
    for (const [tag] of (await readFile(path.join(out, f), 'utf8')).matchAll(/<img\b[^>]*\ssrc="\/[^"]*"[^>]*>/gi))
      if (!/\swidth="\d+"/.test(tag) || !/\sheight="\d+"/.test(tag)) bare.push(`${f}: ${tag.slice(0, 100)}`);
  }
  assert.deepEqual(bare, []);
});

test('diagrams in files agents load leave the palette to the site', async () => {
  const sources = git('ls-tree', '-r', '--name-only', 'HEAD', 'skills', 'agents').split('\n').filter(f => /^(skills\/[^/]+\/SKILL|agents\/[^/]+)\.md$/.test(f));
  let drawn = 0;
  for (const f of sources) {
    const md = git('show', `HEAD:${f}`);
    if (!/```mermaid/.test(md)) continue;
    drawn++;
    assert.doesNotMatch(md, /^\s*classDef (?:here|near|out)\b/m, `${f}: the site adds the palette; keep agent context short`);
    const page = await readFile(path.join(out, f.replace(/\.md$/, '.html')), 'utf8');
    const used = [...md.matchAll(/^\s*class\s+\S+\s+(here|near|out)\s*$/gm)].map(m => m[1]);
    for (const c of new Set(used)) assert.match(page, new RegExp(`classDef ${c} fill:#`), `${f}: ${c} is drawn in the palette`);
    assert.doesNotMatch(await readFile(path.join(out, f), 'utf8'), /classDef/, `${f}: the Markdown twin stays as written`);
  }
  assert.ok(drawn >= 8, `${drawn} skill and subagent diagrams`);
});

test('the palette goes into real diagrams only: not into a quoted example, and :::here counts', async () => {
  const wt = path.join(tmp, 'wt-palette');
  execFileSync('git', ['worktree', 'add', '--detach', '--quiet', wt, 'HEAD'], { cwd: root });
  try {
    await writeFile(path.join(wt, 'docs/toolkit.md'), '# Toolkit\n\n' +
      '```mermaid\nflowchart TD\n    A[a]:::here --> B[b]\n```\n\n' +
      '````markdown\n```mermaid\nflowchart TD\n    Q[quoted]\n    class Q out\n```\n````\n');
    const draft = path.join(tmp, 'draft-palette');
    execFileSync(process.execPath, ['tools/build-site.mjs', '--root', wt, '--worktree', '--out', draft], { cwd: root });
    const page = await readFile(path.join(draft, 'docs/toolkit.html'), 'utf8');
    const diagram = page.match(/<code class="language-mermaid">([\s\S]*?)<\/code>/)?.[1] || '';
    assert.match(diagram, /classDef here fill:#fffdf5/, ':::here shorthand gets the palette');
    assert.doesNotMatch(diagram, /classDef (?:near|out)/, 'only the classes the diagram uses');
    const quoted = page.match(/<code class="language-markdown">([\s\S]*?)<\/code>/)?.[1] || '';
    assert.match(quoted, /class Q out/);
    assert.doesNotMatch(quoted, /classDef/, 'a Mermaid example inside another fence stays as written');
  } finally {
    execFileSync('git', ['worktree', 'remove', '--force', wt], { cwd: root });
  }
});

test('no page refers to a lesson by its old number', () => {
  // The numbered lessons moved into area folders (#133): "see 04" or "lesson 07" now leads nowhere. Link the page.
  let hits = '';
  try {
    hits = git('grep', '-n', '-E', '-e', String.raw`\b[Ll]essons? (0[1-9]|1[0-2])\b|\b[Ss]ee (0[1-9]|1[0-2])\b`, 'HEAD', '--',
      '*.md', '*.json', ':!CHANGELOG.md');
  } catch (e) { if (e.status !== 1) throw e; }                // git grep exits 1 when nothing matches
  hits = hits.split('\n').filter(Boolean);
  assert.deepEqual(hits, []);
});
