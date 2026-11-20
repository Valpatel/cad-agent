/** What a shared link and an agent's first fetch need from the built site (#804), as pure functions the build runs over
 * its own output and the tests run over planted controls (tests/site/website-checks.test.mjs).
 *
 * - socialMeta: the Open Graph and Twitter card tags for one page, from that page's own title, description and address,
 *   with the one owned card picture (tools/site/figures/social-card.mjs).
 * - socialProblems: a built page whose card tags are missing, empty or not its own.
 * - llmsLinks / llmsProblems: every address on this site that llms.txt names, read the way a plain link finder reads
 *   text (an address runs to the next space, quote or angle bracket; only a sentence's closing `.`, `,` or `:` is left
 *   off), and the ones the built site does not serve. A `;` or `)` straight after an address is part of it to such a
 *   reader, so it fails here as the dead link it is to them. `<area>` placeholders are templates, not links. */

const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
const unesc = s => s.replace(/&(amp|lt|gt|quot|#39);/g, (m, e) => ({ amp: '&', lt: '<', gt: '>', quot: '"', '#39': "'" }[e]));

/** The card picture's size (the figure script draws it at this size; the build checks the file). */
export const CARD = { file: 'web/social-card.png', width: 1200, height: 630, alt: 'cad-agent: open-source CAD libraries, simulators, checks and tools for agents' };

export function socialMeta({ title, description, url, origin, siteName = 'cad-agent' }) {
  const image = `${origin}/${CARD.file}`;
  return [
    ['property', 'og:type', 'website'], ['property', 'og:site_name', siteName], ['property', 'og:title', title],
    ['property', 'og:description', description], ...(url == null ? [] : [['property', 'og:url', origin + url]]), ['property', 'og:image', image],
    ['property', 'og:image:width', String(CARD.width)], ['property', 'og:image:height', String(CARD.height)],
    ['property', 'og:image:alt', CARD.alt], ['name', 'twitter:card', 'summary_large_image'],
  ].map(([k, n, v]) => `<meta ${k}="${n}" content="${esc(v)}">`).join('');
}

const metaValue = (html, key, name) => {
  const m = html.match(new RegExp(`<meta ${key}="${name.replace(/[.:]/g, '\\$&')}" content="([^"]*)">`));
  return m ? unesc(m[1]) : null;
};

/** Problems with one built page's card tags: each present once, not empty, and the page's own title, description and
 * address (its canonical link, when it has one: the 404 page has none). */
export function socialProblems(html, { origin }) {
  const problems = [];
  const title = html.match(/<title>([^<]*)<\/title>/)?.[1];
  const description = html.match(/<meta name="description" content="([^"]*)">/)?.[1];
  const canonical = html.match(/<link rel="canonical" href="([^"]*)">/)?.[1];
  const want = { 'og:title': title && unesc(title), 'og:description': description && unesc(description), 'og:url': canonical && unesc(canonical),
    'og:image': `${origin}/${CARD.file}`, 'twitter:card': 'summary_large_image' };
  // A page without an address of its own (the 404 page) names none: a shared link to it is not the home page.
  if (!canonical) {
    delete want['og:url'];
    if (html.includes('<meta property="og:url" ')) problems.push('og:url on a page without a canonical address');
  }
  for (const [name, expected] of Object.entries(want)) {
    const key = name.startsWith('twitter:') ? 'name' : 'property';
    const count = html.split(`<meta ${key}="${name}" `).length - 1;
    const got = metaValue(html, key, name);
    if (count !== 1) problems.push(`${name}: ${count} tags, not one`);
    else if (!got && expected !== '') problems.push(`${name} is empty`);   // a page whose own description is empty passes it on
    else if (expected && got !== expected) problems.push(`${name} is "${got}", not the page's own "${expected}"`);
  }
  if (!/<link rel="apple-touch-icon" href="\/apple-touch-icon\.png">/.test(html)) problems.push('no apple-touch-icon link');
  return problems;
}

/** Every address on `origin` that `text` names, as a plain link finder reads it. */
export function llmsLinks(text, origin) {
  const links = [];
  // Markdown links: the target is what is between the parentheses.
  const rest = text.replace(/\]\(([^)\s]+)\)/g, (all, target) => { if (target.startsWith(origin)) links.push(target); return ']'; });
  const bare = new RegExp(`${origin.replace(/[.]/g, '\\.')}(?:/[^\\s<>"'\`]*)?`, 'g');
  for (const m of rest.matchAll(bare)) {
    if (rest[m.index + m[0].length] === '<') continue;           // catalog/<area>.json: a template, not a link
    links.push(m[0].replace(/[.,:]+$/, ''));
  }
  return links;
}

/** The addresses in `text` the built site does not serve. `serves(pathname)` answers for one decoded path. */
export function llmsProblems(text, origin, serves) {
  const problems = [];
  for (const link of new Set(llmsLinks(text, origin))) {
    let pathname;
    try { pathname = decodeURIComponent(new URL(link).pathname); } catch { problems.push(`${link}: not an address`); continue; }
    if (!serves(pathname)) problems.push(`${link}: not on the built site`);
  }
  return problems;
}

/** The files Cloudflare Pages could answer `pathname` with (pretty URLs: /a serves a.html or a/index.html). */
export const servedFiles = pathname => pathname.endsWith('/') ? [pathname + 'index.html']
  : [pathname, pathname + '.html', pathname + '/index.html'];
