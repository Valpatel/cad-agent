/** The checks the site build runs over its own output (#804, tools/site/compiler/site-checks.mjs), each with a planted
 * control: a page's link-card tags, and the addresses llms.txt names as a plain link finder reads them. Also the link
 * card's record (tools/site/figures/social-card.mjs --check), and that the home page's layer cake names the sections
 * its labels promise. */
import assert from 'node:assert/strict';
import { execFileSync } from 'node:child_process';
import { readFileSync } from 'node:fs';
import path from 'node:path';
import { test } from 'node:test';
import { YAML } from './npm-context.mjs';
import { CARD, llmsLinks, llmsProblems, servedFiles, socialMeta, socialProblems } from '../../tools/site/compiler/site-checks.mjs';
import { imageSize } from '../../tools/site/compiler/site-html.mjs';

const root = path.resolve(import.meta.dirname, '../..');
const ORIGIN = 'https://cad-agent.valpatel.com';
const page = ({ title = 'Linkages · cad-agent', description = 'Four-bar & slider-crank "rules"', url = '/docs/linkages', canonical = true, meta } = {}) =>
  `<head><title>${title.replace(/&/g, '&amp;')}</title><meta name="description" content="${description.replace(/&/g, '&amp;').replace(/"/g, '&quot;')}">` +
  `${canonical ? `<link rel="canonical" href="${ORIGIN}${url}">` : ''}${meta ?? socialMeta({ title, description, url, origin: ORIGIN })}` +
  '<link rel="apple-touch-icon" href="/apple-touch-icon.png"></head>';

test("a page's card tags are its own title, description and address", () => {
  assert.deepEqual(socialProblems(page(), { origin: ORIGIN }), []);
  assert.deepEqual(socialProblems(page({ canonical: false, url: '/' }), { origin: ORIGIN }), [], 'a page without a canonical link (404) still has a card');
  assert.match(socialMeta({ title: 'a "b" & c', description: 'd', url: '/', origin: ORIGIN }), /og:title" content="a &quot;b&quot; &amp; c"/);
});

test('planted controls: missing, empty, doubled or borrowed card tags fail', () => {
  const good = socialMeta({ title: 'Linkages · cad-agent', description: 'Four-bar & slider-crank "rules"', url: '/docs/linkages', origin: ORIGIN });
  const without = name => good.replace(new RegExp(`<meta (?:property|name)="${name}" content="[^"]*">`), '');
  assert.deepEqual(socialProblems(page({ meta: without('og:image') }), { origin: ORIGIN }), ['og:image: 0 tags, not one']);
  assert.deepEqual(socialProblems(page({ meta: without('twitter:card') }), { origin: ORIGIN }), ['twitter:card: 0 tags, not one']);
  assert.deepEqual(socialProblems(page({ meta: good + '<meta property="og:title" content="x">' }), { origin: ORIGIN }), ['og:title: 2 tags, not one']);
  assert.deepEqual(socialProblems(page({ meta: good.replace(/og:description" content="[^"]*"/, 'og:description" content=""') }), { origin: ORIGIN }), ['og:description is empty']);
  // The home page's tags copied onto another page.
  const home = socialMeta({ title: 'cad-agent · home', description: 'Home', url: '/', origin: ORIGIN });
  assert.deepEqual(socialProblems(page({ meta: home }), { origin: ORIGIN }), [
    'og:title is "cad-agent · home", not the page\'s own "Linkages · cad-agent"',
    'og:description is "Home", not the page\'s own "Four-bar & slider-crank "rules""',
    `og:url is "${ORIGIN}/", not the page's own "${ORIGIN}/docs/linkages"`]);
  assert.deepEqual(socialProblems(page().replace('<link rel="apple-touch-icon" href="/apple-touch-icon.png">', ''), { origin: ORIGIN }), ['no apple-touch-icon link']);
});

test('llms.txt addresses are read as a plain link finder reads them', () => {
  const text = [
    `Counts per area: ${ORIGIN}/catalog/references/index.json; one area: ${ORIGIN}/catalog/references/<area>.json.`,
    `Full text: ${ORIGIN}/llms-full.txt, and the [guide](${ORIGIN}/docs/agent-workflow.md): see ${ORIGIN}/docs/toolkit.`,
    `In brackets (${ORIGIN}/catalog.json) and at the end: ${ORIGIN}/explore`,
  ].join('\n');
  assert.deepEqual(llmsLinks(text, ORIGIN), [`${ORIGIN}/docs/agent-workflow.md`, `${ORIGIN}/catalog/references/index.json;`,
    `${ORIGIN}/llms-full.txt`, `${ORIGIN}/docs/toolkit`, `${ORIGIN}/catalog.json)`, `${ORIGIN}/explore`]);
  const site = new Set(['/catalog/references/index.json', '/llms-full.txt', '/docs/agent-workflow.md', '/docs/toolkit.html', '/catalog.json', '/explore.html']);
  const serves = p => servedFiles(p).some(f => site.has(f));
  // The planted controls: the live site's dead link (#804) and a closing bracket glued to an address.
  assert.deepEqual(llmsProblems(text, ORIGIN, serves), [`${ORIGIN}/catalog/references/index.json;: not on the built site`, `${ORIGIN}/catalog.json): not on the built site`]);
  assert.deepEqual(llmsProblems(text.replace('index.json;', 'index.json (').replace('catalog.json)', 'catalog.json )'), ORIGIN, serves), []);
  assert.deepEqual(llmsProblems(`${ORIGIN}/gone`, ORIGIN, serves), [`${ORIGIN}/gone: not on the built site`]);
  assert.deepEqual(servedFiles('/a/'), ['/a/index.html']);
});

test('the link card and touch icon are the drawn pictures their record names, at the sizes the tags say', () => {
  execFileSync(process.execPath, ['tools/site/figures/social-card.mjs', '--check'], { cwd: root, stdio: 'pipe' });
  const card = imageSize(readFileSync(path.join(root, 'tools/site/assets/social-card.png')));
  assert.deepEqual(card, { width: CARD.width, height: CARD.height });
  assert.deepEqual(imageSize(readFileSync(path.join(root, 'tools/site/assets/apple-touch-icon.png'))), { width: 180, height: 180 });
});

test('the layer cake opens the section a block names where its page has one', () => {
  const home = YAML.parse(readFileSync(path.join(root, 'docs/home.yaml'), 'utf8'));
  const blocks = Object.fromEntries(home.stack.flatMap(l => l.blocks).map(b => [b.label, b.href]));
  for (const label of ['Commands', 'Build and export', 'Check', 'Design rules', 'Reports and reviews', 'Print', 'Explore designs'])
    assert.equal(blocks[label], 'docs/toolkit.md#commands', label);
  assert.notEqual(blocks['Eval jobs'], blocks['Candidate eval tasks'], 'two blocks, two sections');
});
