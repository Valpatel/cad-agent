/** Draw the still that <cad-fan-curve> shows before its script loads, from the same code the live chart uses.
 *
 *   node tools/fan-curve-still.mjs            # write docs/img/thermal/fan-curve-explorer.svg
 *   node tools/fan-curve-still.mjs --check    # exit 1 if the committed still or a page's alt text is out of date
 *
 * The state is read from the <cad-fan-curve> attributes on the pages that show the demo (PAGES), which must all agree,
 * so the pages, the still and the live demo start from the same fan and system; each alt text must quote the computed
 * airflow and pressure and say whether the fan runs in its stall region.
 */
import { readFileSync, writeFileSync, existsSync, mkdirSync } from 'node:fs';
import path from 'node:path';
import { readState, compute, drawFanCurve, summary, m3h, pa } from '../src/cadagent/webkit/fan-curve.js';

const root = path.resolve(import.meta.dirname, '..');
export const PAGES = ['docs/fans.md', 'docs/formulas.md'];
export const STILL = 'docs/img/thermal/fan-curve-explorer.svg';

/** The element on a page (a line that starts with it, not a mention in the text): its attributes, as the browser
 * would read them, and its children (the still). */
export function element(md, page) {
  const tag = md.match(/^<cad-fan-curve\b([^>]*)>([\s\S]*?)<\/cad-fan-curve>/m);
  if (!tag) throw new Error(`${page}: no <cad-fan-curve> element`);
  return { attrs: Object.fromEntries([...tag[1].matchAll(/([a-z-]+)(?:="([^"]*)")?/g)].map(m => [m[1], m[2] ?? ''])), inner: tag[2] };
}

export function still(read = page => readFileSync(path.join(root, page), 'utf8')) {
  const problems = [], found = PAGES.map(page => ({ page, ...element(read(page), page) }));
  const first = found[0];
  for (const { page, attrs } of found.slice(1))
    if (JSON.stringify(attrs) !== JSON.stringify(first.attrs)) problems.push(`${page}: <cad-fan-curve> attributes differ from ${first.page}'s`);
  const state = readState(n => (n in first.attrs ? first.attrs[n] : null));
  const result = compute(state);
  const point = `${m3h(result.op.flow)} at ${pa(result.op.pressure)}`;
  const where = result.op.stall ? 'in the stall region' : 'clear of the stall region';
  for (const { page, inner } of found) {
    const alt = inner.match(/\balt="([^"]*)"/)?.[1] || '';
    const rel = path.relative(path.dirname(page), STILL);
    if (!inner.includes(`src="${rel}"`)) problems.push(`${page}: the element does not show ${rel}`);
    if (!alt.includes(point)) problems.push(`${page}: the still's alt text does not quote the operating point, ${point}`);
    if (!alt.includes(where)) problems.push(`${page}: the alt text does not say the fan runs ${where}`);
  }
  return { svg: drawFanCurve(state, result, { still: true, label: summary(state, result) }) + '\n', problems, state, result };
}

if (import.meta.url === `file://${process.argv[1]}`) {
  const { svg, problems } = still();
  const file = path.join(root, STILL);
  if (process.argv.includes('--check')) {
    if (!existsSync(file) || readFileSync(file, 'utf8') !== svg) problems.push(`${STILL} is out of date: run node tools/fan-curve-still.mjs`);
    if (problems.length) { console.error(problems.join('\n')); process.exit(1); }
    console.log(`${STILL} is current`);
  } else {
    mkdirSync(path.dirname(file), { recursive: true });
    writeFileSync(file, svg);
    console.log(`wrote ${STILL}${problems.length ? '\n' + problems.join('\n') : ''}`);
  }
}
