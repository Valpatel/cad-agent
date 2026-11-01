/** Draw the still that <cad-torsion-snap> shows before its script loads, from the same code the live figure uses.
 *
 *   node tools/torsion-snap-still.mjs            # write docs/img/compliant/torsion-snap-explorer.svg
 *   node tools/torsion-snap-still.mjs --check    # exit 1 if the committed still or a page's alt text is out of date
 *
 * The state is read from the <cad-torsion-snap> attributes on the pages that show the demo (PAGES), which must all
 * agree, so the pages, the still and the live demo start from the same bar; each alt text must quote the computed
 * shear strain and say whether it passes.
 */
import { readFileSync, writeFileSync, existsSync, mkdirSync } from 'node:fs';
import path from 'node:path';
import { readState, compute, drawTorsionSnap, summary, pct } from '../src/cadagent/webkit/torsion-snap.js';

const root = path.resolve(import.meta.dirname, '..');
export const PAGES = ['docs/compliant.md'];
export const STILL = 'docs/img/compliant/torsion-snap-explorer.svg';

/** The element on a page (a line that starts with it, not a mention in the text): its attributes, as the browser
 * would read them, and its children (the still). */
export function element(md, page) {
  const tag = md.match(/^<cad-torsion-snap\b([^>]*)>([\s\S]*?)<\/cad-torsion-snap>/m);
  if (!tag) throw new Error(`${page}: no <cad-torsion-snap> element`);
  return { attrs: Object.fromEntries([...tag[1].matchAll(/([a-z-]+)(?:="([^"]*)")?/g)].map(m => [m[1], m[2] ?? ''])), inner: tag[2] };
}

export function still(read = page => readFileSync(path.join(root, page), 'utf8')) {
  const problems = [], found = PAGES.map(page => ({ page, ...element(read(page), page) }));
  const first = found[0];
  for (const { page, attrs } of found.slice(1))
    if (JSON.stringify(attrs) !== JSON.stringify(first.attrs)) problems.push(`${page}: <cad-torsion-snap> attributes differ from ${first.page}'s`);
  const state = readState(n => (n in first.attrs ? first.attrs[n] : null));
  const result = compute(state);
  for (const { page, inner } of found) {
    const alt = inner.match(/\balt="([^"]*)"/)?.[1] || '';
    const rel = path.relative(path.dirname(page), STILL);
    if (!inner.includes(`src="${rel}"`)) problems.push(`${page}: the element does not show ${rel}`);
    if (!alt.includes(`shear strain ${pct(result.shearStrain)}`)) problems.push(`${page}: the still's alt text does not quote the shear strain, ${pct(result.shearStrain)}`);
    if (!alt.includes(result.passes ? 'a pass' : 'a fail')) problems.push(`${page}: the alt text does not say the bar ${result.passes ? 'passes' : 'fails'}`);
  }
  return { svg: drawTorsionSnap(state, result, { still: true, label: summary(state, result) }) + '\n', problems, state, result };
}

if (import.meta.url === `file://${process.argv[1]}`) {
  const { svg, problems } = still();
  const file = path.join(root, STILL);
  if (process.argv.includes('--check')) {
    if (!existsSync(file) || readFileSync(file, 'utf8') !== svg) problems.push(`${STILL} is out of date: run node tools/torsion-snap-still.mjs`);
    if (problems.length) { console.error(problems.join('\n')); process.exit(1); }
    console.log(`${STILL} is current`);
  } else {
    mkdirSync(path.dirname(file), { recursive: true });
    writeFileSync(file, svg);
    console.log(`wrote ${STILL}${problems.length ? '\n' + problems.join('\n') : ''}`);
  }
}
