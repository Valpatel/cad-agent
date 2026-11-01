// tools/site-diagrams.mjs: the site's Mermaid blocks drawn at build time (#132), in the headless Chromium the browser
// tests use. Needs Playwright's Chromium (`npx playwright install chromium`) or Google Chrome.
import test from 'node:test';
import assert from 'node:assert/strict';
import { mkdtemp, readFile, readdir, rm } from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import { drawDiagrams, unescapeHtml } from '../tools/site-diagrams.mjs';

const root = path.resolve(import.meta.dirname, '..');
const tmp = await mkdtemp(path.join(os.tmpdir(), 'cad-agent-site-diagrams-'));
test.after(() => rm(tmp, { recursive: true, force: true }));
const kit = f => readFile(path.join(root, 'src/cadagent/webkit', f));
const site = f => readFile(path.join(root, 'web', f));
const esc = s => s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
const block = src => `<pre><code class="language-mermaid">${esc(src)}</code></pre>`;
const quiet = () => { const said = []; return { said, log: { log: m => said.push(m), warn: m => said.push(m) } }; };
let n = 0;
const cache = () => path.join(tmp, `cache-${++n}`);
const FLOW = 'flowchart LR\n    A[Design] --> B[Build] --> C[Test]\n';
// Every tag's attributes: no handler, no script element, no javascript: link anywhere in the drawn figure.
const unsafe = html => [...html.matchAll(/<([a-z][\w:-]*)\b([^>]*)>/gi)].filter(([, tag, attrs]) =>
  /^(script|iframe|object|embed)$/i.test(tag) || /\son[a-z]+\s*=/i.test(attrs) || /(?:href|src)\s*=\s*["']?\s*javascript:/i.test(attrs)).map(m => m[0]);

test('a block becomes a finished figure: drawn, sized, with its source, and kept in the cache', async () => {
  const dir = cache(), page = `<article>${block(FLOW)}</article>`, { log } = quiet();
  const { draw, stats } = await drawDiagrams([page], { kit, site, cacheDir: dir, log });
  assert.equal(stats.drawn, 1, JSON.stringify(stats));
  const html = draw(page);
  assert.doesNotMatch(html, /language-mermaid/);
  assert.match(html, /^<article><figure class="cad-diagram" data-theme="light" aria-label="Engineering diagram" data-state="ready" aria-busy="false" style="--cad-diagram-w: [\d.]+px;">/);
  assert.match(html, /<p class="cad-diagram-hint">Scroll sideways/, 'the hint is left to the stylesheet (no hidden attribute)');
  assert.match(html, /<svg id="cad-diagram-s[0-9a-f]{12}" [^>]*style="max-width: [\d.]+px; width: [\d.]+px;"/);
  assert.match(html, /font-family:'Inter',Arial,sans-serif/, 'measured in the site\'s own webfont');
  for (const label of ['Design', 'Build', 'Test']) assert.match(html, new RegExp(`>${label}<`));
  assert.ok(html.includes(`<pre class="cad-diagram-source">${esc(FLOW)}</pre>`), 'the source, as written');
  assert.deepEqual(unsafe(html), []);
  assert.equal((await readdir(dir)).filter(f => f.endsWith('.html')).length, 1);
  // A second build draws nothing and needs no browser.
  const again = await drawDiagrams([page], { kit, site, cacheDir: dir, log, launch: () => { throw new Error('launched'); } });
  assert.deepEqual([again.stats.cached, again.stats.drawn], [1, 0]);
  assert.equal(again.draw(page), html);
});

test('the same source draws the same bytes in another browser session; theme and source change the drawing', async () => {
  const { log } = quiet(), page = block(FLOW);
  const a = (await drawDiagrams([page], { kit, site, cacheDir: cache(), log })).draw(page);
  const b = (await drawDiagrams([page], { kit, site, cacheDir: cache(), log })).draw(page);
  assert.equal(a, b);
  const dark = (await drawDiagrams([page], { kit, site, cacheDir: cache(), log, theme: 'dark' })).draw(page);
  assert.match(dark, /data-theme="dark"/);
  assert.notEqual(dark.match(/<svg id="([^"]+)"/)[1], a.match(/<svg id="([^"]+)"/)[1], 'a theme is part of the key');
  const other = block(FLOW.replace('Test', 'Ship'));
  const c = (await drawDiagrams([other], { kit, site, cacheDir: cache(), log })).draw(other);
  assert.notEqual(c.match(/<svg id="([^"]+)"/)[1], a.match(/<svg id="([^"]+)"/)[1]);
});

test('a sequence and a class diagram draw the same whatever was drawn before them (Mermaid\'s counters)', async () => {
  const seq = 'sequenceDiagram\n    A->>B: Hello\n    B-->>A: Hi\n', cls = 'classDiagram\n    Animal <|-- Duck\n';
  const { log } = quiet();
  const alone = (await drawDiagrams([block(seq) + block(cls)], { kit, site, cacheDir: cache(), log })).draw(block(seq) + block(cls));
  const after = await drawDiagrams([block(FLOW) + block(cls) + block(seq)], { kit, site, cacheDir: cache(), log });
  assert.equal(after.stats.drawn, 3, JSON.stringify(after.stats));
  assert.equal(after.draw(block(seq) + block(cls)), alone);
});

test('one diagram twice on a page gets two ids; a diagram Mermaid cannot draw is left for the reader\'s browser', async () => {
  const { said, log } = quiet(), bad = 'flowchart LR\n    A --> \n    this is not mermaid ]]] {{\n';
  const page = block(FLOW) + block(bad) + block(FLOW);
  const { draw, stats } = await drawDiagrams([page], { kit, site, cacheDir: cache(), log });
  assert.deepEqual([stats.diagrams, stats.drawn, stats.left], [2, 1, 1]);
  const html = draw(page);
  const ids = [...html.matchAll(/<svg id="([^"]+)"/g)].map(m => m[1]);
  assert.equal(ids.length, 2);
  assert.equal(ids[1], `${ids[0]}-1`);
  assert.ok(!html.slice(html.indexOf(ids[1])).includes(`${ids[0]}_`) && !html.slice(html.indexOf(ids[1])).includes(`#${ids[0]} `),
    'the second figure refers to its own id only');
  assert.ok(html.includes(block(bad)), 'the undrawable block is left as it was');
  assert.ok(said.some(m => /left to the reader's browser: Mermaid could not draw it/.test(m)), said.join('\n'));
});

test('no browser: every block is left as it was, the build is told why, and nothing fails', async () => {
  const { said, log } = quiet(), page = block(FLOW);
  const { draw, stats } = await drawDiagrams([page], { kit, site, cacheDir: cache(), log, launch: async () => ({ browser: null, why: 'no Chromium here' }) });
  assert.deepEqual([stats.drawn, stats.left], [0, 1]);
  assert.equal(draw(page), page);
  assert.match(said.join('\n'), /1 of 1 diagrams will be drawn in the reader's browser, not at build time \(no Chromium here\)/);
  const client = await drawDiagrams([page], { kit, site, cacheDir: cache(), log: quiet().log, client: true, launch: () => { throw new Error('launched'); } });
  assert.equal(client.draw(page), page);
});

test('hostile labels stay inert when drawn at build time', async () => {
  // The labels from the advisories fixed in Mermaid 11.10.0 (tests/webkit-diagrams-browser.mjs draws them in the page).
  const hook = '<img src="x" onerror="window.cadXss=1">';
  const sources = [`sequenceDiagram\n    participant A as Alice${hook}$$\\text{Alice}$$\n    A->>John: Hello John\n`,
    `architecture-beta\n    group api(cloud)[API]\n    service db "${hook}" [Database] in api\n`,
    `flowchart LR\n    A["${hook.replace(/"/g, '#quot;')}"] --> B[<a href="javascript:alert(1)">x</a>]\n`];
  const page = sources.map(block).join('');
  const { draw, stats } = await drawDiagrams([page], { kit, site, cacheDir: cache(), log: quiet().log });
  assert.ok(stats.drawn >= 2, `the sequence and architecture diagrams are drawn: ${JSON.stringify(stats)}`);
  const html = draw(page);
  assert.match(html, /Alice/);
  assert.deepEqual(unsafe(html.replace(/<pre class="cad-diagram-source">[\s\S]*?<\/pre>|<pre><code[\s\S]*?<\/code><\/pre>/g, '')), []);
});

test('HTML text comes back as the browser reads it', () => {
  assert.equal(unescapeHtml('A --&gt; B &amp; &quot;C&quot; &#39;d&#39; &#x2192; &lt;br/&gt;'), 'A --> B & "C" \'d\' → <br/>');
});
