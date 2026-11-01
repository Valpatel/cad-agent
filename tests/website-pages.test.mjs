/** tools/site-pages.mjs: real outputs placed on doc pages from docs/pages.yaml, section cards, and long reference parts
 * folded (#179). */
import assert from 'node:assert/strict';
import test from 'node:test';
import { CARDS_MIN, FOLD_LINES, FOLD_ROWS, fold, pagePlacer, sectionCards } from '../tools/site-pages.mjs';

const PNG = Buffer.from('89504e470d0a1a0a0000000d49484452000002800000019008060000', 'hex');   // 640 x 400
const base = {
  pageFiles: new Set(['docs/a.md', 'docs/b.md']),
  tracked: ['docs/img/out.png', 'docs/img/two.png', 'src/cadagent/review/gates/motion.py', 'src/cadagent/simulation/fea/__init__.py', 'tools/draw.py', 'src/cadagent/webkit/part-table.js'],
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
  assert.equal(await place('docs/b.md', PAGE), PAGE, 'a page without an entry or pictures is untouched');
  const kit = await pagePlacer({ ...base, spec: { 'docs/b.md': { hero: out({ tool: 'kit/part-table.js' }) } } })('docs/b.md', PAGE);
  assert.match(kit, /<b class="shows-output">Real output<\/b> of <code>kit\/part-table\.js<\/code>/, 'a web kit file is a tool, as the site publishes it');
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

test('section cards: one per section with a picture, linking to it, once a page has CARDS_MIN of them; band pictures are not repeated', async () => {
  const img = (src, w = 640) => `<img src="/docs/img/${src}" width="${w}" height="400" alt="x">`;
  const page = `<h1 id="t">T</h1><p>Lead.</p><h2 id="a-b">A &amp; <code>b</code></h2><p>${img('out.png')}</p><h2 id="c">C</h2><p>Text.</p><h2 id="d">D</h2><p><img src="https://example.com/x.png" alt="badge">${img('two.png')}</p>`;
  const cards = sectionCards(page);
  assert.match(cards, /^<nav class="section-cards" aria-label="Sections with pictures"><ul><li><a href="#a-b"><img src="\/docs\/img\/out\.png" width="640" height="400" alt="" loading="lazy" decoding="async"><span>A &amp; b<\/span><\/a><\/li><li><a href="#d"><img src="\/docs\/img\/two\.png"/);
  assert.equal(cards.match(/<li>/g).length, 2, 'C has no picture; the remote badge is not one');
  assert.equal(sectionCards(page, { skip: new Set(['/docs/img/two.png']) }), '', `fewer than ${CARDS_MIN} left: no cards`);
  const placed = await pagePlacer({ ...base, spec: {} })('docs/b.md', page);
  assert.match(placed, /^<h1 id="t">T<\/h1><p>Lead\.<\/p><nav class="section-cards"/, 'cards come on every page, entry or not');
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
  await fails({ 'docs/a.md': { figure: [out({ after: 'one' })] } }, /unknown key figure \(one of hero, band, figures\)/);
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
  await fails({ 'docs/a.md': { hero: drawn({ drawn_by: undefined }) } }, /a diagram says which script drew it/);
  await fails({ 'docs/a.md': { hero: out({ drawn_by: 'tools/draw.py' }) } }, /a real output is drawn by its tool/);
  await fails({ 'docs/a.md': { band: [tile({ href: 'docs/z.md' }), tile()] } }, /not a published page or an anchor/);
  await fails({ 'docs/a.md': { band: [tile({ href: '#nowhere' }), tile()] } }, /no heading with id nowhere on the page/);
  await fails({ 'docs/a.md': { band: [tile({ output: '' }), tile()] } }, /no output/);
  await fails({ 'docs/a.md': { band: [tile()] } }, /two to four tiles/);
  await fails({ 'docs/a.md': { figures: [out({ after: 'nope' })] } }, /no heading with id nope/);
  await fails({ 'docs/a.md': { figures: [out({ after: 'one', caption: '' })] } }, /no caption/);
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
