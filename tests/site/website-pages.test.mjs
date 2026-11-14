/** tools/site/compiler/site-pages.mjs: real outputs placed on doc pages from docs/pages.yaml, section cards, and long reference parts
 * folded (#179). */
import assert from 'node:assert/strict';
import test from 'node:test';
import { createPublication, pageSection, publicPath, requiredSources, selectPages, sourceSpec, validateRedirects } from '../../tools/site/publication.mjs';
import { CARDS_MIN, FOLD_LINES, FOLD_ROWS, fold, pagePlacer, sectionCards } from '../../tools/site/compiler/site-pages.mjs';

const PNG = Buffer.from('89504e470d0a1a0a0000000d49484452000002800000019008060000', 'hex');   // 640 x 400
const base = {
  pageFiles: new Set(['docs/a.md', 'docs/b.md']),
  tracked: ['docs/img/out.png', 'docs/img/two.png', 'software/cadagent/review/gates/motion.py', 'software/cadagent/simulation/fea/__init__.py', 'tools/draw.py', 'software/cadagent/webkit/assembly/part-table.js'],
  commandNames: new Set(['gates', 'site']), readBuf: async () => PNG, pageURL: f => '/' + f.replace(/\.md$/, ''),
};
const out = (o = {}) => ({ img: 'docs/img/out.png', shows: 'output', tool: 'cad-agent site', on: 'fixture', caption: 'Six gates pass.', alt: 'A table', ...o });
const drawn = (o = {}) => ({ img: 'docs/img/out.png', shows: 'diagram', drawn_by: 'tools/draw.py', tool: 'cadagent.review.gates.motion', on: 'fixture-2d', caption: 'Contact at 44.9 degrees.', alt: 'An arm', ...o });
const tile = (o = {}) => ({ ...out(), input: 'a STEP & its joints', output: 'a verdict', href: '#one', ...o });
const PAGE = '<h1 id="a">A</h1><p>Lead.</p><p>More.</p><h2 id="one">One</h2><p>First.</p><p>Second.</p><h2 id="two">Two</h2><pre>x</pre><h2 id="three">Three</h2><p>The file:</p><pre>y</pre>';

test('a band (hero and tiles) goes under the title and its first paragraph, each saying what its picture is', async () => {
  const place = pagePlacer({ ...base, spec: { 'docs/a.md': { hero: out(), band: [tile(), tile({ ...drawn(), input: 'a joint', output: 'the onset', href: 'docs/b.md#x' })] } } });
  const html = await place('docs/a.md', PAGE);
  assert.match(html, /^<h1 id="a">A<\/h1><p>Lead\.<\/p><section class="page-band"[^>]*><figure class="band-hero"><a class="fig-full" href="\/docs\/img\/out\.png"[^>]*><img src="\/docs\/img\/out\.png" width="640" height="400" alt="A table" decoding="async"><\/a>/);
  assert.match(html, /<figcaption><span class="fig-what"><b class="shows-output">Real output<\/b> of <code>cad-agent site<\/code>, on a test fixture in this repo\.<\/span> Six gates pass\.<\/figcaption>/);
  assert.match(html, /<a href="#one"><img [^>]*loading="lazy"[^>]*><span class="band-flow"><span class="band-input">a STEP &amp; its joints<\/span><span class="band-arrow" aria-hidden="true">→<\/span><code>cad-agent site<\/code><span class="band-arrow" aria-hidden="true">→<\/span><span class="band-output">a verdict<\/span><\/span>/);
  assert.match(html, /<a href="\/docs\/b#x">[^]*?<b class="shows-diagram">Diagram<\/b> of <code>cadagent\.review\.gates\.motion<\/code>, drawn by <code>tools\/draw\.py<\/code>, on a test fixture, drawn in 2D; tests hold its numbers to the real check\.<\/span> Contact at 44\.9 degrees\./);
  assert.match(html, /<\/section><p>More\.<\/p>/);
  // A lead that ends with ":" keeps the list it introduces: the band goes right under the title (#217 review).
  const colon = await place('docs/a.md', '<h1 id="a">A</h1><p>Every review walks this list:</p><ol><li>x</li></ol>' + PAGE.slice(PAGE.indexOf('<h2')));
  assert.match(colon, /^<h1 id="a">A<\/h1><section class="page-band"[^]*?<\/section><p>Every review walks this list:<\/p><ol>/);
  assert.equal(await place('docs/b.md', PAGE), PAGE, 'a page without an entry or pictures is untouched');
  const kit = await pagePlacer({ ...base, spec: { 'docs/b.md': { hero: out({ tool: 'kit/assembly/part-table.js' }) } } })('docs/b.md', PAGE);
  assert.match(kit, /<b class="shows-output">Real output<\/b> of <code>kit\/assembly\/part-table\.js<\/code>/, 'a web kit file is a tool, as the site publishes it');
  // A tile is one link: the Gyropup credit's own link would nest in it and split the tile (#217 review). The hero keeps it.
  const gyropup = await pagePlacer({ ...base, spec: { 'docs/a.md': { hero: out({ on: 'gyropup' }), band: [tile({ on: 'gyropup' }), tile()] } } })('docs/a.md', PAGE);
  for (const li of gyropup.match(/<li>[^]*?<\/li>/g)) assert.equal(li.match(/<a\b/g).length, 1, li);
  assert.match(gyropup, /<span class="band-caption">[^]*?, on Gyropup · MIT\.<\/span>/);
  assert.match(gyropup, /<figcaption>[^]*?, on <a href="https:\/\/gyropup\.com">Gyropup<\/a> · MIT\.<\/span>/);
});

test('figures go after their section\'s first paragraph, in YAML order, or under the heading when that paragraph introduces a block', async () => {
  const fig = (after, caption, o = {}) => ({ ...out({ caption, alt: caption }), after, ...o });
  const place = pagePlacer({ ...base, spec: { 'docs/a.md': { figures: [fig('one', 'F1'), fig('two', 'F2'), fig('one', 'F3'), fig('three', 'F4')] } } });
  const html = await place('docs/a.md', PAGE);
  assert.match(html, /<h2 id="one">One<\/h2><p>First\.<\/p><figure class="page-figure">[^]*?F1<\/figcaption><\/figure><figure class="page-figure">[^]*?F3<\/figcaption><\/figure><p>Second\.<\/p>/);
  assert.match(html, /<h2 id="two">Two<\/h2><figure class="page-figure">[^]*?F2<\/figcaption><\/figure><pre>x<\/pre>/, 'a section that opens with code: right under the heading');
  assert.match(html, /<h2 id="three">Three<\/h2><figure class="page-figure">[^]*?F4<\/figcaption><\/figure><p>The file:<\/p><pre>y<\/pre>/, '"The file:" stays with its block');
  assert.match(html, /<a class="fig-full" href="\/docs\/img\/out\.png" title="Open the full-size picture"><img /, 'each figure opens its full-size picture');
});

test('below: places a figure after the first block of its section that has the words, lists and code included', async () => {
  const page = '<h1 id="t">T</h1><h3 id="l">L</h3><ul><li><strong>Rule:</strong> cut &amp; check</li><li><ul><li>nested</li></ul></li></ul><p>Then <img src="/x.png" alt=""> more.</p>' +
    '<cad-copy><pre><code>a &lt; b\n</code></pre></cad-copy><h3 id="m">M</h3><p>Rule: cut &amp; check</p>';
  const fig = (below, caption) => ({ ...out({ caption, alt: caption }), after: 'l', below });
  const html = await pagePlacer({ ...base, spec: { 'docs/a.md': { figures: [fig('Rule: cut & check', 'B1'), fig('a < b', 'B2'), fig('more.', 'B3')] } } })('docs/a.md', page);
  assert.match(html, /<\/ul><\/li><\/ul><figure class="page-figure">[^]*?B1<\/figcaption><\/figure><p>Then/, 'after the whole list, nested lists and all');
  assert.match(html, /more\.<\/p><figure class="page-figure">[^]*?B3<\/figcaption><\/figure><cad-copy>/, 'an image in the paragraph does not end it');
  assert.match(html, /<\/cad-copy><figure class="page-figure">[^]*?B2<\/figcaption><\/figure><h3 id="m">/, 'code is a block too');
  await assert.rejects(pagePlacer({ ...base, spec: { 'docs/a.md': { figures: [fig('nested', 'X'), { ...fig('no such words', 'Y'), after: 'm' }] } } })('docs/a.md', page),
    /figures\[1\]: no paragraph, list, table or code block in its section has the words "no such words"/, 'only its own section is searched');
});

test('section cards: one per section with a picture, linking to it, once a page has CARDS_MIN of them; band pictures are not repeated', async () => {
  const img = (src, w = 640) => `<img src="/docs/img/${src}" width="${w}" height="400" alt="x">`;
  const page = `<h1 id="t">T</h1><p>Lead.</p><h2 id="a-b">A &amp; <code>b</code></h2><p>${img('out.png')}</p><h2 id="c">C</h2><p>Text.</p><h2 id="d">D</h2><p><img src="https://example.com/x.png" alt="badge">${img('two.png')}</p>`;
  const cards = sectionCards(page);
  assert.match(cards, /^<nav class="section-cards" aria-label="Sections with pictures"><ul><li><a href="#a-b"><img src="\/docs\/img\/out\.png" width="640" height="400" alt="" loading="lazy" decoding="async"><span>A &amp; b<\/span><\/a><\/li><li><a href="#d"><img src="\/docs\/img\/two\.png"/);
  assert.equal(cards.match(/<li>/g).length, 2, 'C has no picture; the remote badge is not one');
  assert.equal(sectionCards(page, { skip: new Set(['/docs/img/two.png']) }), '', `fewer than ${CARDS_MIN} left: no cards`);
  const placed = await pagePlacer({ ...base, spec: {} })('docs/b.md', page);
  assert.match(placed, /^<h1 id="t">T<\/h1><p>Lead\.<\/p><nav class="section-cards"/, 'cards come on every page, entry or not');
  const compact = pagePlacer({ ...base, spec: { 'docs/a.md': { cards: false } } });
  assert.equal(await compact('docs/a.md', page), page, 'a compact page keeps every authored image and section without duplicate cards');
  assert.equal(await compact('docs/b.md', page), placed, 'the setting does not suppress cards on another page');
  assert.equal(await pagePlacer({ ...base, spec: { 'docs/b.md': { cards: true } } })('docs/b.md', page), placed, 'explicit true retains normal cards');
  const compactWithHero = await pagePlacer({ ...base, spec: { 'docs/a.md': { cards: false, hero: out() } } })('docs/a.md', page);
  assert.match(compactWithHero, /class="page-band"/, 'suppressing cards still places configured figures');
  assert.doesNotMatch(compactWithHero, /section-cards/);
  const banded = await pagePlacer({ ...base, spec: { 'docs/a.md': { hero: out({ img: 'docs/img/two.png' }) } } })('docs/a.md', page);
  assert.doesNotMatch(banded, /section-cards/, 'the hero\'s picture is not a card again, and one card is too few');
});

test('the build stops on anything a reader could not trust', async () => {
  const fails = async (spec, why) => {
    const place = (() => { try { return pagePlacer({ ...base, spec }); } catch (e) { return e; } })();
    const err = place instanceof Error ? place : await place('docs/a.md', PAGE).then(() => null, e => e);
    assert.ok(err, `no error for ${why}`);
    assert.match(err.message, why);
  };
  await fails({ 'docs/c.md': { hero: out() } }, /docs\/c\.md: is not a published page/);
  await fails({ 'docs/a.md': null }, /docs\/a\.md: is not a mapping/);
  await fails({ 'docs/a.md': {} }, /places nothing/);
  await fails({ 'docs/a.md': { figures: [] } }, /places nothing/);
  await fails({ 'docs/a.md': { figure: [out({ after: 'one' })] } }, /unknown key figure \(one of hero, band, figures, cards\)/);
  for (const cards of ['false', 0, null, [], {}]) await fails({ 'docs/a.md': { cards } }, /cards: must be a boolean/);
  await fails({ 'docs/a.md': { band: [tile({ herf: '#one' }), tile()] } }, /band\[0\]: unknown key herf/);
  await fails({ 'docs/a.md': { hero: out({ img: 'docs/img/missing.png' }) } }, /not a committed picture/);
  await fails({ 'docs/a.md': { hero: out({ img: 'https://example.com/x.png' }) } }, /not a committed picture/);
  await fails({ 'docs/a.md': { hero: out({ tool: 'cad-agent nonsense' }) } }, /not a cad-agent command, a cadagent module, a web kit file \(kit\/…\) or a script under tools\//);
  await fails({ 'docs/a.md': { hero: out({ tool: 'cadagent.gates.motion' }) } }, /not a cad-agent command, a cadagent module, a web kit file \(kit\/…\) or a script under tools\//);
  await fails({ 'docs/a.md': { hero: out({ tool: 'kit/missing.js' }) } }, /not a cad-agent command, a cadagent module, a web kit file \(kit\/…\) or a script under tools\//);
  await fails({ 'docs/a.md': { hero: out({ tool: 'tools/missing.py' }) } }, /not a cad-agent command, a cadagent module, a web kit file \(kit\/…\) or a script under tools\//);
  await fails({ 'docs/a.md': { hero: out({ alt: '' }) } }, /hero: no alt/);
  await fails({ 'docs/a.md': { hero: out({ shows: 'render' }) } }, /shows is one of output, diagram/);
  await fails({ 'docs/a.md': { hero: out({ on: 'somewhere' }) } }, /on is one of gyropup/);
  await fails({ 'docs/a.md': { hero: out({ on: 'fixture-2d' }) } }, /a 2D drawing of a fixture is a diagram, not a real output/);
  await fails({ 'docs/a.md': { hero: drawn({ drawn_by: undefined }) } }, /a diagram says which script under tools\/ drew it/);
  await fails({ 'docs/a.md': { hero: drawn({ drawn_by: 'cad-agent site' }) } }, /a diagram says which script under tools\/ drew it/);
  await fails({ 'docs/a.md': { hero: out({ drawn_by: 'tools/draw.py' }) } }, /a real output is drawn by its tool/);
  await fails({ 'docs/a.md': { band: [tile({ href: 'docs/z.md' }), tile()] } }, /not a published page or an anchor/);
  await fails({ 'docs/a.md': { band: [tile({ href: '#nowhere' }), tile()] } }, /no heading with id nowhere on the page/);
  await fails({ 'docs/a.md': { band: [tile({ output: '' }), tile()] } }, /no output/);
  await fails({ 'docs/a.md': { band: [tile()] } }, /two to four tiles/);
  await fails({ 'docs/a.md': { figures: [out({ after: 'nope' })] } }, /no heading with id nope/);
  await fails({ 'docs/a.md': { figures: [out({ after: 'one', caption: '' })] } }, /no caption/);
  // #217 review: a key that is there is used, and a link names a heading.
  await fails({ 'docs/a.md': { hero: out(), figures: { after: 'one' } } }, /docs\/a\.md figures: is a list of figures/);
  await fails({ 'docs/a.md': { hero: out(), figures: 'one' } }, /docs\/a\.md figures: is a list of figures/);
  await fails({ 'docs/a.md': { hero: null, figures: [out({ after: 'one' })] } }, /docs\/a\.md hero: is not a mapping/);
  await fails({ 'docs/a.md': { hero: out(), band: null } }, /two to four tiles/);
  await fails({ 'docs/a.md': { figures: [out({ after: 'one', below: '' })] } }, /figures\[0\]: below is the words of the block/);
  await fails({ 'docs/a.md': { band: [tile({ href: '#fig' }), tile()] } }, /no heading with id fig on the page/);
});

test('a tile linking a heading on another page is checked once every page is placed', async () => {
  const place = pagePlacer({ ...base, spec: { 'docs/a.md': { band: [tile({ href: 'docs/b.md#x' }), tile({ href: 'docs/b.md#nope' })] } } });
  await place('docs/a.md', PAGE + '<p id="fig">A figure</p>');
  const pages = { 'docs/b.md': '<h1 id="b">B</h1><h2 id="x">X</h2><p id="nope">not a heading</p>' };
  assert.throws(() => place.checkLinks(f => pages[f]), /docs\/a\.md band\[1\]: no heading with id nope on docs\/b\.md/);
  pages['docs/b.md'] += '<h3 id="nope">Nope</h3>';
  place.checkLinks(f => pages[f]);
});

test('long tables and code blocks fold, with a summary of what is inside; short ones stay open', () => {
  const table = n => `<div class="table-scroll"><table><thead><tr><th>Part</th><th>Mass <code>g</code></th></tr></thead><tbody>${'<tr><td>a</td><td>1</td></tr>'.repeat(n)}</tbody></table></div>`;
  const code = (n, lang) => `<cad-copy><pre><code${lang ? ` class="language-${lang}"` : ''}>${'line\n'.repeat(n)}</code></pre></cad-copy>`;
  assert.equal(fold(table(FOLD_ROWS)), table(FOLD_ROWS));
  assert.equal(fold(table(FOLD_ROWS + 1)), `<details class="fold"><summary><span class="fold-kind">Table</span> ${FOLD_ROWS + 1} rows: Part, Mass g</summary>${table(FOLD_ROWS + 1)}</details>`);
  assert.equal(fold(code(FOLD_LINES, 'python')), code(FOLD_LINES, 'python'));
  assert.equal(fold(code(FOLD_LINES + 1, 'python')), `<details class="fold"><summary><span class="fold-kind">Code</span> ${FOLD_LINES + 1} lines of python</summary>${code(FOLD_LINES + 1, 'python')}</details>`);
  assert.match(fold(code(40)), /<summary><span class="fold-kind">Code<\/span> 40 lines<\/summary>/);
  const diagram = '<pre><code class="language-mermaid">' + 'a\n'.repeat(40) + '</code></pre>';
  assert.equal(fold(diagram), diagram, 'a diagram source is a picture, not reference text');
});


test('the real source selector keeps moved identities and rejects missing current sources', () => {
  const extras = ['THIRD_PARTY_NOTICES.md', 'CONTRIBUTING.md', '.github/SECURITY.md', 'SECURITY.md', 'docs/a b.md', 'docs/a\tb.md', 'docs/AGENTS.md'];
  const files = [...requiredSources, ...extras];
  assert.deepEqual(selectPages(files).map(p => p.file), [...requiredSources, 'docs/a b.md', 'docs/a\tb.md']);
  const cases = [
    ['.github/CONTRIBUTING.md', 'CONTRIBUTING.md', 'docs'],
    ['software/vendor/THIRD_PARTY_NOTICES.md', 'THIRD_PARTY_NOTICES.md', 'docs'],
    ['docs/mechanical/compliant.md', 'docs/compliant.md', 'docs'],
    ['docs/research/manufacturing/process-profiles.md', 'research/process-profiles.md', 'research'],
    ['docs/lessons/process/verify-from-source.md', 'lessons/process/verify-from-source.md', 'lessons'],
  ];
  for (const [source, identity, section] of cases) {
    assert.equal(publicPath(source), identity);
    assert.equal(pageSection(source).id, section);
    assert.throws(() => selectPages(files.filter(f => f !== source)), error => error.message.includes(`required published source ${source} is missing`));
  }
  assert.equal(pageSection('research/process-profiles.md'), null, 'a stale old root is not a source');
  assert.equal(pageSection('docs/research/references/README.md'), null, 'reference maintenance procedures remain source-only');
});

test('source aliases fail on duplicate public pages and ambiguous or incomplete metadata', () => {
  assert.throws(() => selectPages([...requiredSources, 'docs/compliant.md']), /duplicate public page docs\/compliant\.md/);
  const bad = mutate => { const spec = structuredClone(sourceSpec); mutate(spec); return () => createPublication(spec); };
  assert.throws(bad(spec => spec.files.push({ source: 'docs/other.md', public: 'docs/compliant.md' })), /duplicate page source or public identity/);
  assert.throws(bad(spec => spec.roots.push({ source: 'docs/research/nested', public: 'other' })), /ambiguous page source roots/);
  assert.throws(bad(spec => spec.roots = []), /needs schema 1, roots and files/);
  assert.throws(bad(spec => spec.unpublished = 'docs/private.md'), /must be an array/);
  assert.throws(bad(spec => spec.unpublished.push('docs/mechanical/compliant.md')), /contradictory unpublished source/);
  const spec = structuredClone(sourceSpec);
  spec.roots.push({ source: 'docs/absent', public: 'absent' });
  assert.throws(() => createPublication(spec).selectPages(requiredSources), /required published root docs\/absent is missing/);
});


test('redirect validation rejects malformed routes and live public aliases using real source identity', () => {
  const context = { tracked: requiredSources, pageFiles: new Set(requiredSources), moved: [], publicPath };
  const target = 'docs/lessons/README.md';
  for (const from of ['/lessons/gone.md', 'lessons/gone', 'web/site.css', 'lessons/*.md', 'lessons/:name.md',
    'lessons/../gone.md', 'lessons//gone.md', 'lessons/./gone.md'])
    assert.throws(() => validateRedirects([[from, target]], context), /without a leading slash/, from);
  for (const from of ['docs/compliant.md', 'CONTRIBUTING.md'])
    assert.throws(() => validateRedirects([[from, target]], context), /still a file in the repo/, from);
  assert.throws(() => validateRedirects([['lessons/old.md', target], ['lessons/old.md', target]], context), /listed twice/);
  assert.throws(() => validateRedirects([['lessons/old.md', 'docs/absent.md']], context), /not a published page/);
});

test('a physical source stub keeps its public redirect identity, and missing or mismatched rules fail', () => {
  const source = 'docs/lessons/03-mechanical-design-rules.md', identity = 'lessons/03-mechanical-design-rules.md';
  const target = 'docs/lessons/mechanical/design-rules.md';
  const context = { tracked: [...requiredSources, source], pageFiles: new Set(requiredSources), moved: [[source, target]], publicPath };
  assert.doesNotThrow(() => validateRedirects([[identity, target]], context));
  assert.throws(() => validateRedirects([], context), /add "lessons\/03-mechanical-design-rules\.md/);
  assert.throws(() => validateRedirects([[identity, 'docs/lessons/README.md']], context), /change its line/);
});

// Inert page-probe controls: no browser/site build/model is started by these tests.
import { EventEmitter } from 'node:events';
import { mkdtemp, readFile, readdir, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import path from 'node:path';
import { readerBoundaryGoto, readerBoundaryProblems } from './site-outline.mjs';

class ReaderProbePage extends EventEmitter {
  calls = [];
  url() { return 'http://user:password@localhost:1234/docs/toolkit?secret=value#private'; }
  async goto(target, options) { this.calls.push({ target, options }); return this.navigate(); }
  async evaluate() { this.domCalls = (this.domCalls || 0) + 1; return { readyState: 'interactive', navReady: false,
    styles: [{ href: this.url(), disabled: false }], fonts: 'loading' }; }
  async screenshot(options) { this.imageOptions = options; return Buffer.from('inert screenshot control'); }
}
const probeRequest = i => ({ url: () => 'http://user:password@localhost:1234/request-' + i + '?secret=value#private',
  method: () => 'GET', resourceType: () => 'script', failure: () => ({ errorText: 'request failed' }) });
const probeContext = async t => {
  const evidence = await mkdtemp(path.join(tmpdir(), 'cad-agent-reader-inert-'));
  t.after(() => rm(evidence, { recursive: true, force: true }));
  return { evidence, viewport: { width: 1440, height: 900 }, states: [{ earlier: 'preserved' }], problems: ['earlier problem'] };
};
const noProbeListeners = page => assert.equal(page.eventNames().length, 0, 'every probe listener is detached');

test('reader navigation success preserves exact goto contract without capture or receipt work', async t => {
  const context = await probeContext(t), page = new ReaderProbePage(), response = {};
  page.navigate = () => response;
  assert.equal(await readerBoundaryGoto(page, 'http://localhost/docs/toolkit', context), response);
  assert.deepEqual(page.calls, [{ target: 'http://localhost/docs/toolkit', options: { waitUntil: 'networkidle' } }]);
  assert.equal(page.domCalls, undefined); assert.equal(page.imageOptions, undefined);
  assert.deepEqual(await readdir(context.evidence), []); noProbeListeners(page);
});

test('failed reader navigation writes bounded redacted partial evidence before caller close and rethrows original', async t => {
  const context = await probeContext(t), page = new ReaderProbePage(), original = new Error('Timeout 30000ms at ' + page.url());
  original.name = 'TimeoutError';
  page.navigate = () => {
    const requests = Array.from({ length: 100 }, (_, i) => probeRequest(i));
    for (const request of requests) {
      page.emit('request', request);
      page.emit('response', { url: request.url, status: () => 200, request: () => ({ isNavigationRequest: () => true }) });
      page.emit('console', { type: () => 'error', text: () => 'pending ' + request.url() + 'x'.repeat(1000) });
      page.emit('pageerror', new Error('failed ' + request.url()));
    }
    page.emit('requestfinished', requests[0]); page.emit('requestfailed', requests[1]);
    page.emit('domcontentloaded'); throw original;
  };
  let closed = false;
  try { await readerBoundaryGoto(page, page.url(), context); assert.fail('a navigation error became success'); }
  catch (error) {
    assert.equal(error, original);
    const text = await readFile(path.join(context.evidence, 'receipt.json'), 'utf8'), receipt = JSON.parse(text);
    assert.equal(closed, false, 'partial receipt already exists before caller closes page');
    assert.deepEqual(receipt.states[0], { earlier: 'preserved' }); assert.deepEqual(receipt.problems, ['earlier problem']);
    const failure = receipt.states[1].navigationFailure;
    assert.deepEqual(failure.viewport, context.viewport); assert.equal(failure.javaScriptEnabled, true);
    assert.equal(failure.pendingCount, 98); assert.equal(failure.pending.length, 22);
    for (const kind of ['responses', 'console', 'pageerror']) {
      assert.equal(failure.counts[kind], 100); assert.equal(failure.events[kind].length, 24);
    }
    assert.equal(failure.events.failed.length, 1); assert.equal(failure.events.lifecycle[0].name, 'domcontentloaded');
    assert.equal(failure.dom.readyState, 'interactive'); assert.equal(failure.dom.navReady, false);
    assert.equal(failure.screenshot, 'navigation-failure.png'); assert.ok(text.length < 40000);
    assert.doesNotMatch(text, /password|secret|private|user:/);
    assert.deepEqual(page.imageOptions, { type: 'png', fullPage: false, timeout: 1000 });
  } finally { closed = true; }
  noProbeListeners(page);
});

test('reader capture errors and oversized screenshot do not replace the navigation failure', async t => {
  const context = await probeContext(t), page = new ReaderProbePage(), original = new Error('original navigation');
  page.navigate = () => { throw original; };
  page.evaluate = () => { throw new Error('execution context destroyed'); };
  page.screenshot = async () => Buffer.alloc(2 * 1024 * 1024 + 1);
  await assert.rejects(readerBoundaryGoto(page, page.url(), context), error => error === original);
  const receipt = JSON.parse(await readFile(path.join(context.evidence, 'receipt.json'), 'utf8'));
  assert.match(receipt.states.at(-1).navigationFailure.captureErrors.join(' '), /DOM: execution context destroyed.*exceeded 2 MiB/);
  assert.equal(receipt.states.at(-1).navigationFailure.screenshot, undefined);
  assert.deepEqual(await readdir(context.evidence), ['receipt.json']); noProbeListeners(page);
});

test('a stalled diagnostic DOM read is bounded while the original navigation error remains authoritative', { timeout: 5000 }, async t => {
  const context = await probeContext(t), page = new ReaderProbePage(), original = new Error('original timeout');
  page.navigate = () => { throw original; }; page.evaluate = () => new Promise(() => {});
  await assert.rejects(readerBoundaryGoto(page, page.url(), context), error => error === original);
  const receipt = JSON.parse(await readFile(path.join(context.evidence, 'receipt.json'), 'utf8'));
  assert.match(receipt.states.at(-1).navigationFailure.captureErrors[0], /exceeded 1000 ms/); noProbeListeners(page);
});

test('the real reader probe retains partial state before close when post-navigation readiness throws', async t => {
  const page = new ReaderProbePage(), original = new Error('reader readiness timeout');
  let evidence, closed = false;
  t.mock.method(console, 'log', text => { if (text.startsWith('Reader boundary partial evidence: ')) evidence = text.slice('Reader boundary partial evidence: '.length); });
  t.after(async () => { if (evidence) await rm(evidence, { recursive: true, force: true }); });
  page.navigate = () => ({}); page.waitForSelector = async () => { throw original; };
  page.close = async () => {
    const receipt = JSON.parse(await readFile(path.join(evidence, 'receipt.json'), 'utf8'));
    assert.equal(receipt.states[0].probeFailure.error.message, original.message);
    assert.deepEqual(receipt.states[0].probeFailure.viewport, { width: 1440, height: 900 });
    noProbeListeners(page); closed = true;
  };
  await assert.rejects(readerBoundaryProblems({ newPage: async () => page }, 'http://localhost'), error => error === original);
  assert.equal(closed, true);
});

test('a disconnected page and unavailable receipt directory never mask the original reader navigation error', async t => {
  const context = await probeContext(t), page = new ReaderProbePage(), original = new Error('original navigation failure');
  context.evidence = path.join(context.evidence, 'missing');
  page.navigate = () => { throw original; }; page.url = () => { throw new Error('disconnected'); };
  const errors = []; t.mock.method(console, 'error', text => errors.push(text));
  await assert.rejects(readerBoundaryGoto(page, 'http://localhost/docs/toolkit', context), error => error === original);
  assert.equal(context.states.at(-1).navigationFailure.currentURL, '[unavailable URL]');
  assert.equal(errors.length, 1); assert.match(errors[0], /partial receipt unavailable/); noProbeListeners(page);
});

// #663: the prior filtered sample was internally consistent before the resized layout arrived.
import { readerOverflowSnapshot } from './site-outline.mjs';
test('reader overflow readiness rejects stale viewport/layout/containment and captures the passing sample', t => {
  const mockGlobal=(name,value)=>{const old=Object.getOwnPropertyDescriptor(globalThis,name);Object.defineProperty(globalThis,name,{value,configurable:true});t.after(()=>old?Object.defineProperty(globalThis,name,old):delete globalThis[name]);};
  const panel = { clientHeight:345, scrollHeight:345, hasAttribute:()=>false };
  const style = {position:'sticky',overscrollBehaviorY:'auto'};
  mockGlobal('document',{querySelector:()=>panel});
  mockGlobal('getComputedStyle',()=>style);
  mockGlobal('scrollY',300);
  mockGlobal('innerWidth',1440);
  mockGlobal('innerHeight',600);
  const expected={width:1440,height:600,overflow:true,position:'sticky'};
  assert.equal(readerOverflowSnapshot(expected),false,'preceding fitting layout must not settle resize');
  panel.clientHeight=968;panel.scrollHeight=1429;
  assert.equal(readerOverflowSnapshot(expected),false,'actual hosted transitional sample is rejected');
  style.overscrollBehaviorY='contain';panel.hasAttribute=()=>true;
  assert.equal(readerOverflowSnapshot(expected),false,'old tall max-height still exceeds requested viewport');
  panel.clientHeight=488;
  const sample=readerOverflowSnapshot(expected);
  assert.equal(sample.content,1429);assert.equal(sample.contain,'contain');assert.equal(sample.fits,false);
  panel.clientHeight=345;panel.scrollHeight=345;
  assert.equal(sample.height,488,'returned value is the captured sample, not a second layout read');
});
