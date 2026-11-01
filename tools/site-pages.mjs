/** Visual-first doc pages (#179): real outputs placed on a page from docs/pages.yaml, and long reference parts folded.
 *
 * The owner, 2026-10-31: "CAD is graphical, so our site should be too. Not a wall of text." Pictures are placed by the
 * site build, never written into the Markdown, so the .md twins and llms.txt stay exactly as written and GitHub shows
 * the page as before. Used by tools/build-site.mjs; tested in tests/website-pages.test.mjs.
 */
import { imageSize } from './site-html.mjs';

const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));

// A table of more than FOLD_ROWS body rows, or a code block of more than FOLD_LINES lines, folds into a <details>
// whose summary says what is inside. Find-in-page still finds folded text, and the Markdown twin has it all.
export const FOLD_ROWS = 12, FOLD_LINES = 24;

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

/** place(file, html) puts a page's band and figures from `spec` (docs/pages.yaml, parsed) into its rendered HTML.
 * It throws on a page that is not published, a picture that is not committed under docs/img/, a heading the page does
 * not have, a missing caption or alt text, or a tool that is neither a cad-agent command nor a cadagent module. */
export function pagePlacer({ spec, pageFiles, tracked, commandNames, readBuf, pageURL }) {
  for (const file of Object.keys(spec)) if (!pageFiles.has(file)) throw new Error(`docs/pages.yaml: ${file} is not a published page`);
  const fail = (at, why) => { throw new Error(`docs/pages.yaml ${at}: ${why}`); };
  const picture = async (src, alt, at) => {
    if (!tracked.includes(src) || !/^docs\/img\/.*\.(svg|png|jpe?g|webp)$/.test(src)) fail(at, `${src} is not a committed picture under docs/img/`);
    const size = imageSize(await readBuf(src), src);
    if (!size) fail(at, `cannot read the size of ${src}`);
    return `<img src="/${esc(src)}" width="${size.width}" height="${size.height}" alt="${esc(alt)}" loading="lazy" decoding="async">`;
  };
  const tool = (name, at) => {
    const cmd = name.match(/^cad-agent ([a-z0-9-]+)/)?.[1], mod = name.match(/^cadagent(?:\.[a-z_]+)+$/)?.[0];
    const file = mod && `src/${mod.split('.').join('/')}`;
    if (cmd ? !commandNames.has(cmd) : !(mod && (tracked.includes(`${file}.py`) || tracked.includes(`${file}/__init__.py`))))
      fail(at, `${name} is not a cad-agent command or a cadagent module`);
    return `<code>${esc(name)}</code>`;
  };
  const need = (o, keys, at) => { for (const k of keys) if (!o?.[k]) fail(at, `no ${k}`); };
  const link = (href, at) => href.startsWith('#') ? href : pageFiles.has(href) ? pageURL(href) : fail(at, `${href} is not a published page or an anchor`);
  // After the opening at `end`: past its first paragraph if one follows at once, else right there.
  const afterFirstParagraph = (html, end) => end + (html.slice(end).match(/^\s*<p>[\s\S]*?<\/p>/)?.[0].length || 0);
  return async (file, html) => {
    const page = spec[file];
    if (!page) return html;
    for (const [i, f] of (page.figures || []).entries()) {
      const at = `${file} figures[${i}]`;
      need(f, ['after', 'img', 'caption', 'alt'], at);
      const head = [...html.matchAll(/<h([23]) id="([^"]+)">[\s\S]*?<\/h\1>/g)].find(m => m[2] === f.after);
      if (!head) fail(at, `no heading with id ${f.after} on the page`);
      const where = afterFirstParagraph(html, head.index + head[0].length);
      const figure = `<figure class="page-figure">${await picture(f.img, f.alt, at)}<figcaption>${f.tool ? `${tool(f.tool, at)} ` : ''}${esc(f.caption)}</figcaption></figure>`;
      html = html.slice(0, where) + figure + html.slice(where);
    }
    if (page.band) {
      if (!Array.isArray(page.band) || page.band.length < 2 || page.band.length > 4) fail(file, 'a band has two to four tiles');
      const tiles = [];
      for (const [i, t] of page.band.entries()) {
        const at = `${file} band[${i}]`;
        need(t, ['img', 'tool', 'caption', 'alt'], at);
        // input → tool → output: what goes in (words: the input is the reader's), the tool, and the real output
        const flow = `${t.input ? `<span class="band-input">${esc(t.input)}</span><span class="band-arrow" aria-hidden="true">→</span>` : ''}${tool(t.tool, at)}`;
        const inner = `${await picture(t.img, t.alt, at)}<span class="band-tool">${flow}</span><span class="band-caption">${esc(t.caption)}</span>`;
        tiles.push(`<li>${t.href ? `<a href="${esc(link(t.href, at))}">${inner}</a>` : `<span>${inner}</span>`}</li>`);
      }
      const h1 = html.match(/<h1\b[^>]*>[\s\S]*?<\/h1>/);
      const where = afterFirstParagraph(html, h1 ? h1.index + h1[0].length : 0);
      html = html.slice(0, where) + `<section class="page-band" aria-label="What this page's tools make"><ul>${tiles.join('')}</ul></section>` + html.slice(where);
    }
    return html;
  };
}
