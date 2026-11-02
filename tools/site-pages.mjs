/** Visual-first doc pages (#179): real outputs placed on a page from docs/pages.yaml, section cards, and long
 * reference parts folded.
 *
 * The owner, 2026-10-31: "CAD is graphical, so our site should be too. Not a wall of text." Pictures are placed by the
 * site build, never written into the Markdown, so the .md twins and llms.txt stay exactly as written and GitHub shows
 * the page as before. Every placed picture says what it is: a real output of a tool, or a diagram (a drawing of
 * something real), which tool made it and what it was computed on. Used by tools/build-site.mjs; tested in
 * tests/site/website-pages.test.mjs.
 *
 * The template, top to bottom:
 * - a band under the title and its first paragraph: a hero figure and/or two to four input → tool → output tiles;
 * - section cards: one card per section that has a picture, the picture as its face, linking to the section;
 * - figures placed inside sections, after a section's first paragraph;
 * - long tables and code blocks folded into <details>.
 */
import { imageSize } from './site-html.mjs';

const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));

// What a picture was computed on, said beside it (the home page's tiles use the same words; #182 review: not every
// picture is a real part).
export const ON = {
  gyropup: '<a href="https://gyropup.com">Gyropup</a> · MIT', enclosure: 'a printed enclosure', fixture: 'a test fixture in this repo',
  'fixture-2d': 'a test fixture, drawn in 2D; tests hold its numbers to the real check', example: 'a worked example',
  sources: 'published sources',
};
// What a picture is: the tool's own output (a render, a page the tool built, a file it wrote), or a diagram drawn for
// the docs of something real (a 2D model of a fixture, a chart of computed numbers).
export const SHOWS = { output: 'Real output', diagram: 'Diagram' };

// A table of more than FOLD_ROWS body rows, or a code block of more than FOLD_LINES lines, folds into a <details>
// whose summary says what is inside. Chrome's find-in-page opens a fold with a match (other browsers may not search a
// closed one); the Markdown twin has it all.
export const FOLD_ROWS = 12, FOLD_LINES = 24;
// Section cards appear on a page with at least this many sections (h2) that have a picture.
export const CARDS_MIN = 2;

/** Fold long tables (as the build wraps them: <div class="table-scroll">) and long code blocks (<cad-copy><pre>). */
export function fold(html, { rows = FOLD_ROWS, lines = FOLD_LINES } = {}) {
  return html
    .replace(/<div class="table-scroll"><table>([\s\S]*?)<\/table><\/div>/g, (all, inner) => {
      const n = (inner.split('<tbody>')[1] || '').match(/<tr>/g)?.length || 0;
      if (n <= rows) return all;
      const head = [...(inner.match(/<thead>[\s\S]*?<\/thead>/)?.[0] || '').matchAll(/<th[^>]*>([\s\S]*?)<\/th>/g)]
        .map(m => m[1].replace(/<[^>]+>/g, '').trim()).filter(Boolean);
      const what = head.length ? `: ${head.slice(0, 4).join(', ')}${head.length > 4 ? ', …' : ''}` : '';
      return `<details class="fold"><summary><span class="fold-kind">Table</span> ${n} rows${what}</summary>${all}</details>`;
    })
    .replace(/<cad-copy><pre><code(?: class="language-([\w+-]+)")?>([\s\S]*?)<\/code><\/pre><\/cad-copy>/g, (all, lang, code) => {
      const n = code.replace(/\n$/, '').split('\n').length;
      if (n <= lines) return all;
      return `<details class="fold"><summary><span class="fold-kind">Code</span> ${n} lines${lang ? ` of ${esc(lang)}` : ''}</summary>${all}</details>`;
    });
}

/** Section cards: one per h2 section that shows a picture (its first local one, from docs/img/), linking to the
 * section, placed at `at`. A picture in `skip` (already in the band) is not repeated. */
export function sectionCards(html, { skip = new Set(), min = CARDS_MIN } = {}) {
  const heads = [...html.matchAll(/<h2 id="([^"]+)">([\s\S]*?)<\/h2>/g)];
  const cards = [];
  for (const [i, h] of heads.entries()) {
    const body = html.slice(h.index + h[0].length, heads[i + 1]?.index ?? html.length);
    const img = [...body.matchAll(/<img\b[^>]*>/g)].map(m => m[0])
      .find(t => /\ssrc="\/docs\/img\/[^"]+"/.test(t) && /\swidth="\d+"/.test(t) && !skip.has(t.match(/\ssrc="([^"]+)"/)[1]));
    if (!img) continue;
    const [src, width, height] = ['src', 'width', 'height'].map(a => img.match(new RegExp(`\\s${a}="([^"]+)"`))[1]);
    const title = h[2].replace(/<[^>]+>/g, '').trim();
    cards.push(`<li><a href="#${esc(encodeURIComponent(h[1]))}"><img src="${src}" width="${width}" height="${height}" alt="" loading="lazy" decoding="async"><span>${esc(title.replace(/&amp;/g, '&'))}</span></a></li>`);
  }
  return cards.length < min ? '' : `<nav class="section-cards" aria-label="Sections with pictures"><ul>${cards.join('')}</ul></nav>`;
}

// The keys an entry may have: anything else (a typo such as `figure:` or `herf:`) stops the build.
const KEYS = {
  page: ['hero', 'band', 'figures'],
  hero: ['img', 'shows', 'drawn_by', 'on', 'tool', 'caption', 'alt'],
  tile: ['img', 'shows', 'drawn_by', 'on', 'input', 'tool', 'output', 'caption', 'alt', 'href'],
  figure: ['after', 'below', 'img', 'shows', 'drawn_by', 'on', 'tool', 'caption', 'alt'],
};

/** place(file, html) puts a page's band, section cards and figures (`spec`: docs/pages.yaml, parsed) into its
 * rendered HTML. It throws on a page that is not published, an empty entry or an unknown key, a picture that is not
 * committed under docs/img/, a heading the page does not have, missing alt text, caption or `on`, a `shows` that is
 * not output or diagram, or a tool that is not a cad-agent command, a cadagent module, a web kit file (kit/…, as the
 * site publishes src/cadagent/webkit/) or a script under tools/. */
export function pagePlacer({ spec, pageFiles, tracked, commandNames, readBuf, pageURL }) {
  const fail = (at, why) => { throw new Error(`docs/pages.yaml ${at}: ${why}`); };
  const only = (o, keys, at) => {
    if (!o || typeof o !== 'object' || Array.isArray(o)) fail(at, 'is not a mapping');
    for (const k of Object.keys(o)) if (!keys.includes(k)) fail(at, `unknown key ${k} (one of ${keys.join(', ')})`);
  };
  for (const [file, page] of Object.entries(spec || {})) {
    if (!pageFiles.has(file)) fail(file, 'is not a published page');
    only(page, KEYS.page, file);
    if (!page.hero && !page.band?.length && !page.figures?.length) fail(file, 'places nothing (give it a hero, a band or figures)');
    // A key that is there is used: an empty hero, band or figures list is a mistake, not nothing.
    if ('hero' in page && (!page.hero || typeof page.hero !== 'object' || Array.isArray(page.hero))) fail(`${file} hero`, 'is not a mapping');
    if ('figures' in page && (!Array.isArray(page.figures) || !page.figures.length)) fail(`${file} figures`, 'is a list of figures');
  }
  const picture = async (src, alt, at, attrs = ' loading="lazy" decoding="async"') => {
    if (!tracked.includes(src) || !/^docs\/img\/.*\.(svg|png|jpe?g|webp)$/.test(src)) fail(at, `${src} is not a committed picture under docs/img/`);
    const size = imageSize(await readBuf(src), src);
    if (!size) fail(at, `cannot read the size of ${src}`);
    return `<img src="/${esc(src)}" width="${size.width}" height="${size.height}" alt="${esc(alt)}"${attrs}>`;
  };
  const tool = (name, at) => {
    const cmd = name.match(/^cad-agent ([a-z0-9-]+)$/)?.[1], mod = name.match(/^cadagent(?:\.[a-z_]+)+$/)?.[0];
    const ok = cmd ? commandNames.has(cmd)
      : mod ? [`src/${mod.replace(/\./g, '/')}.py`, `src/${mod.replace(/\./g, '/')}/__init__.py`].some(f => tracked.includes(f))
        : /^kit\/[\w./-]+$/.test(name) ? tracked.includes(`src/cadagent/webkit/${name.slice(4)}`)
          : /^tools\/[\w./-]+$/.test(name) && tracked.includes(name);
    if (!ok) fail(at, `${name} is not a cad-agent command, a cadagent module, a web kit file (kit/…) or a script under tools/`);
    return `<code>${esc(name)}</code>`;
  };
  const need = (o, keys, at) => { for (const k of keys) if (!o?.[k]) fail(at, `no ${k}`); };
  // What the picture is, said first in its caption: "Real output of `cad-agent site`, on a test fixture in this repo."
  // or "Diagram of `cadagent.review.gates.motion`, drawn by `tools/motion_figures.py`, on a test fixture, drawn in 2D…".
  // A real output is the tool's own (it wrote or drew the picture); a diagram names the script that drew it. Inside a
  // link (a band tile is one), the "on" credit drops its own link: a link in a link would split the tile.
  const what = (v, at, inLink = false) => {
    if (!SHOWS[v.shows]) fail(at, `shows is one of ${Object.keys(SHOWS).join(', ')} (a real output of the tool, or a diagram of something real)`);
    if (!ON[v.on]) fail(at, `on is one of ${Object.keys(ON).join(', ')}`);
    if (v.on === 'fixture-2d' && v.shows !== 'diagram') fail(at, 'a 2D drawing of a fixture is a diagram, not a real output');
    if (v.shows === 'diagram' && !/^tools\//.test(v.drawn_by || '')) fail(at, 'a diagram says which script under tools/ drew it (drawn_by)');
    if (v.shows === 'output' && v.drawn_by) fail(at, 'a real output is drawn by its tool: drop drawn_by, or make it a diagram');
    const by = v.shows === 'diagram' ? `, drawn by ${tool(v.drawn_by, at)}` : '';
    const on = inLink ? ON[v.on].replace(/<[^>]+>/g, '') : ON[v.on];
    return `<span class="fig-what"><b class="shows-${v.shows}">${SHOWS[v.shows]}</b> of ${tool(v.tool, at)}${by}, on ${on}.</span>`;
  };
  // A tile links to a heading on its page (#id, which must exist) or to another published page (docs/x.md#id).
  const heading = (html, id) => html.includes(` id="${id}"`) && new RegExp(`<h[1-6] id="${id.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')}"`).test(html);
  const elsewhere = [];                       // [at, page, heading id]: checked by place.checkLinks once all pages exist
  const link = (href, at, html) => {
    const [target, hash] = href.split('#');
    if (!target) return heading(html, hash) ? href : fail(at, `no heading with id ${hash} on the page`);
    if (!pageFiles.has(target)) fail(at, `${href} is not a published page or an anchor`);
    if (hash) elsewhere.push([at, target, hash]);
    return pageURL(target) + (hash ? '#' + hash : '');
  };
  const full = (src, img) => `<a class="fig-full" href="/${esc(src)}" title="Open the full-size picture">${img}</a>`;
  // Where a figure goes in a section: after its first paragraph, unless that paragraph introduces the block after it
  // (it ends with a colon) or there is none; then right under the heading.
  const inSection = (html, end) => {
    const p = html.slice(end).match(/^\s*<p>([\s\S]*?)<\/p>/);
    return !p || /:\s*$/.test(p[1].replace(/<[^>]+>/g, '')) ? end : end + p[0].length;
  };
  // `below: some words`: after the section's first block (paragraph, list, table, code, fold) whose text has them, so a
  // figure can sit beside the part it shows. Blocks are the section's top-level elements, found by tag depth.
  const VOID = /^(?:img|br|hr|input|source|wbr|col|area|meta|link)$/i;
  const below = (html, start, words, at) => {
    const next = html.slice(start).search(/<h[1-4][ >]/), end = next < 0 ? html.length : start + next;
    const text = s => s.replace(/<[^>]+>/g, '').replace(/&(amp|lt|gt|quot|#39);/g, (m, e) => ({ amp: '&', lt: '<', gt: '>', quot: '"', '#39': "'" }[e])).replace(/\s+/g, ' ');
    let depth = 0, open = -1;
    for (const m of html.slice(start, end).matchAll(/<(\/?)([a-z][\w-]*)\b[^>]*?(\/?)>/gi)) {
      if (VOID.test(m[2]) || m[3]) continue;
      if (!m[1]) { if (depth++ === 0) open = start + m.index; continue; }
      if (--depth === 0) {
        const close = start + m.index + m[0].length;
        if (text(html.slice(open, close)).includes(words)) return close;
      }
    }
    return fail(at, `no paragraph, list, table or code block in its section has the words "${words}"`);
  };
  // The band and the cards: after the title and its first paragraph, as a figure in a section (so not between a lead
  // that ends with ":" and the list it introduces).
  const underTitle = html => {
    const h1 = html.match(/<h1\b[^>]*>[\s\S]*?<\/h1>/);
    return inSection(html, h1 ? h1.index + h1[0].length : 0);
  };
  const place = async (file, html) => {
    const page = spec?.[file] || {};
    // Figures first, all at once from the original positions (last first, so the earlier positions hold), each
    // heading's figures in their YAML order.
    const inserts = [];
    for (const [i, f] of (page.figures || []).entries()) {
      const at = `${file} figures[${i}]`;
      only(f, KEYS.figure, at);
      need(f, ['after', 'img', 'shows', 'on', 'tool', 'caption', 'alt'], at);
      const head = [...html.matchAll(/<h([2-4]) id="([^"]+)">[\s\S]*?<\/h\1>/g)].find(m => m[2] === f.after);
      if (!head) fail(at, `no heading with id ${f.after} on the page`);
      const end = head.index + head[0].length;
      if ('below' in f && (typeof f.below !== 'string' || !f.below.trim())) fail(at, 'below is the words of the block to place it after');
      inserts.push([f.below ? below(html, end, String(f.below).replace(/\s+/g, ' '), at) : inSection(html, end), i,
        `<figure class="page-figure">${full(f.img, await picture(f.img, f.alt, at))}<figcaption>${what(f, at)} ${esc(f.caption)}</figcaption></figure>`]);
    }
    for (const [where, , figure] of inserts.sort((a, b) => b[0] - a[0] || b[1] - a[1])) html = html.slice(0, where) + figure + html.slice(where);
    // The band: a hero figure and/or input → tool → output tiles.
    const banded = new Set();
    let band = '';
    if (page.hero) {
      const at = `${file} hero`;
      only(page.hero, KEYS.hero, at);
      need(page.hero, ['img', 'shows', 'on', 'tool', 'caption', 'alt'], at);
      banded.add('/' + page.hero.img);
      band += `<figure class="band-hero">${full(page.hero.img, await picture(page.hero.img, page.hero.alt, at, ' decoding="async"'))}<figcaption>${what(page.hero, at)} ${esc(page.hero.caption)}</figcaption></figure>`;
    }
    if ('band' in page) {
      if (!Array.isArray(page.band) || page.band.length < 2 || page.band.length > 4) fail(file, 'a band has two to four tiles');
      const tiles = [];
      for (const [i, t] of page.band.entries()) {
        const at = `${file} band[${i}]`;
        only(t, KEYS.tile, at);
        need(t, ['img', 'shows', 'on', 'input', 'tool', 'output', 'caption', 'alt', 'href'], at);
        banded.add('/' + t.img);
        // input → tool → output: what goes in and what comes out, in words (the reader's), the tool, and the picture
        const flow = `<span class="band-flow"><span class="band-input">${esc(t.input)}</span><span class="band-arrow" aria-hidden="true">→</span>${tool(t.tool, at)}<span class="band-arrow" aria-hidden="true">→</span><span class="band-output">${esc(t.output)}</span></span>`;
        tiles.push(`<li><a href="${esc(link(t.href, at, html))}">${await picture(t.img, t.alt, at)}${flow}<span class="band-caption">${what(t, at, true)} ${esc(t.caption)}</span></a></li>`);
      }
      band += `<ul class="band-tiles">${tiles.join('')}</ul>`;
    }
    const top = (band ? `<section class="page-band" aria-label="What this page's tools make">${band}</section>` : '') + sectionCards(html, { skip: banded });
    if (!top) return html;
    const where = underTitle(html);
    return html.slice(0, where) + top + html.slice(where);
  };
  /** After every page is placed: a tile's link to a heading on another page finds it (htmlOf(file): its final HTML). */
  place.checkLinks = htmlOf => {
    for (const [at, target, hash] of elsewhere) if (!heading(htmlOf(target) || '', hash)) fail(at, `no heading with id ${hash} on ${target}`);
  };
  return place;
}
