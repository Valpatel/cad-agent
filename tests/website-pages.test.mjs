/** tools/site-pages.mjs: real outputs placed on doc pages from docs/pages.yaml, and long reference parts folded (#179). */
import assert from 'node:assert/strict';
import test from 'node:test';
import { FOLD_LINES, FOLD_ROWS, fold, pagePlacer } from '../tools/site-pages.mjs';

const PNG = Buffer.from('89504e470d0a1a0a0000000d49484452000002800000019008060000', 'hex');   // 640 x 400
const base = {
  pageFiles: new Set(['docs/a.md', 'docs/b.md']), tracked: ['docs/img/out.png', 'src/cadagent/gates/motion.py', 'src/cadagent/fea.py'],
  commandNames: new Set(['gates']), readBuf: async () => PNG, pageURL: f => '/' + f.replace(/\.md$/, ''),
};
const tile = (o = {}) => ({ img: 'docs/img/out.png', tool: 'cad-agent gates', caption: 'Contact at 44.9 degrees.', alt: 'An arm', ...o });
const PAGE = '<h1 id="a">A</h1><p>Lead.</p><p>More.</p><h2 id="one">One</h2><p>First.</p><p>Second.</p><h2 id="two">Two</h2><pre>x</pre>';

test('a band goes under the title and its first paragraph; a figure after its section\'s first paragraph', async () => {
  const place = pagePlacer({ ...base, spec: { 'docs/a.md': {
    band: [tile({ href: '#one' }), tile({ tool: 'cadagent.gates.motion', href: 'docs/b.md', input: 'a joint & its range' })],
    figures: [{ after: 'one', img: 'docs/img/out.png', tool: 'cadagent.fea', caption: 'Stress.', alt: 'A part' }, { after: 'two', img: 'docs/img/out.png', caption: 'C', alt: 'D' }] } } });
  const html = await place('docs/a.md', PAGE);
  assert.match(html, /^<h1 id="a">A<\/h1><p>Lead\.<\/p><section class="page-band"[^>]*><ul><li><a href="#one"><img src="\/docs\/img\/out\.png" width="640" height="400" alt="An arm"/);
  assert.match(html, /<a href="\/docs\/b">[^]*?<span class="band-tool"><span class="band-input">a joint &amp; its range<\/span><span class="band-arrow" aria-hidden="true">→<\/span><code>cadagent\.gates\.motion<\/code><\/span>/);
  assert.match(html, /<h2 id="one">One<\/h2><p>First\.<\/p><figure class="page-figure"><img [^>]*alt="A part"[^>]*><figcaption><code>cadagent\.fea<\/code> Stress\.<\/figcaption><\/figure><p>Second\.<\/p>/);
  assert.match(html, /<h2 id="two">Two<\/h2><figure class="page-figure">[\s\S]*?<\/figure><pre>x<\/pre>$/, 'a section that opens with code: right under the heading');
  assert.equal(await place('docs/b.md', PAGE), PAGE, 'a page without an entry is untouched');
});

test('the build stops on anything a reader could not trust', async () => {
  const fails = async (spec, why) => {
    const place = (() => { try { return pagePlacer({ ...base, spec }); } catch (e) { return e; } })();
    const err = place instanceof Error ? place : await place('docs/a.md', PAGE).then(() => null, e => e);
    assert.ok(err, `no error for ${why}`);
    assert.match(err.message, why);
  };
  await fails({ 'docs/c.md': { band: [tile(), tile()] } }, /docs\/c\.md is not a published page/);
  await fails({ 'docs/a.md': { band: [tile({ img: 'docs/img/missing.png' }), tile()] } }, /not a committed picture/);
  await fails({ 'docs/a.md': { band: [tile({ img: 'https://example.com/x.png' }), tile()] } }, /not a committed picture/);
  await fails({ 'docs/a.md': { band: [tile({ tool: 'cad-agent nonsense' }), tile()] } }, /not a cad-agent command or a cadagent module/);
  await fails({ 'docs/a.md': { band: [tile({ tool: 'cadagent.nothing' }), tile()] } }, /not a cad-agent command or a cadagent module/);
  await fails({ 'docs/a.md': { band: [tile({ alt: '' }), tile()] } }, /no alt/);
  await fails({ 'docs/a.md': { band: [tile({ href: 'docs/z.md' }), tile()] } }, /not a published page or an anchor/);
  await fails({ 'docs/a.md': { band: [tile()] } }, /two to four tiles/);
  await fails({ 'docs/a.md': { figures: [{ after: 'nope', img: 'docs/img/out.png', caption: 'C', alt: 'D' }] } }, /no heading with id nope/);
  await fails({ 'docs/a.md': { figures: [{ after: 'one', img: 'docs/img/out.png', alt: 'D' }] } }, /no caption/);
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
