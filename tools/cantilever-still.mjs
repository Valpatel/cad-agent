/** Draw the still that <cad-cantilever> shows before its script loads, from the same code the live figure uses.
 *
 *   node tools/cantilever-still.mjs            # write docs/img/compliant/cantilever-explorer.svg
 *   node tools/cantilever-still.mjs --check    # exit 1 if the committed still or its alt text is out of date
 *
 * The state is read from the <cad-cantilever> attributes in docs/compliant.md, so the page, the still and the live
 * demo always start from the same arm; the alt text must quote the computed root strain.
 */
import { readFileSync, writeFileSync, existsSync } from 'node:fs';
import path from 'node:path';
import { readState, compute, drawCantilever, summary } from '../src/cadagent/webkit/cantilever.js';

const root = path.resolve(import.meta.dirname, '..');
const PAGE = 'docs/compliant.md', STILL = 'docs/img/compliant/cantilever-explorer.svg';

export function still(md = readFileSync(path.join(root, PAGE), 'utf8')) {
  const tag = md.match(/<cad-cantilever\b([^>]*)>([\s\S]*?)<\/cad-cantilever>/);
  if (!tag) throw new Error(`${PAGE}: no <cad-cantilever> element`);
  const attrs = Object.fromEntries([...tag[1].matchAll(/([a-z-]+)(?:="([^"]*)")?/g)].map(m => [m[1], m[2] ?? '']));
  const state = readState(n => (n in attrs ? attrs[n] : null));
  const result = compute(state);
  const alt = tag[2].match(/\balt="([^"]*)"/)?.[1] || '';
  const strain = `${(result.strain * 100).toFixed(2)} %`;
  const problems = [];
  if (!tag[2].includes(`img/compliant/${path.basename(STILL)}`)) problems.push(`the element does not show ${STILL}`);
  if (!alt.includes(strain)) problems.push(`the still's alt text does not quote the computed root strain ${strain}`);
  return { svg: drawCantilever(state, result, { still: true, id: 'still', label: summary(state, result) }) + '\n', problems };
}

if (import.meta.url === `file://${process.argv[1]}`) {
  const { svg, problems } = still();
  const file = path.join(root, STILL);
  if (process.argv.includes('--check')) {
    if (!existsSync(file) || readFileSync(file, 'utf8') !== svg) problems.push(`${STILL} is out of date: run node tools/cantilever-still.mjs`);
    if (problems.length) { console.error(problems.join('\n')); process.exit(1); }
    console.log(`${STILL} is current`);
  } else {
    writeFileSync(file, svg);
    console.log(`wrote ${STILL}${problems.length ? '\n' + problems.join('\n') : ''}`);
  }
}
