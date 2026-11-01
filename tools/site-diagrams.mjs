/** Draw the site's Mermaid diagrams at build time (#132), so a page arrives with its diagrams finished: nothing moves
 * while it loads, they show without script, and no page downloads Mermaid to draw them.
 *
 * Each `<pre><code class="language-mermaid">` block the Markdown renderer wrote is drawn once by the web kit's own
 * `drawDiagram` (kit/diagrams.js, the code that draws it in a reader's browser) with the vendored Mermaid, in headless
 * Chromium through Playwright, which the browser tests already use. The figure it returns, `<figure class="cad-diagram"
 * data-state="ready">` with the SVG and the source, replaces the block; kit/diagrams.js leaves such figures alone.
 *
 * - Deterministic: the same source, theme, Mermaid, kit and font give the same bytes. The SVG id comes from a hash of
 *   those; each drawing gets a fresh Mermaid (its sequence and class diagrams number elements with counters that run
 *   on from one drawing to the next) and a seeded Math.random; every diagram is drawn twice and kept only if both
 *   drawings match; and the labels are measured in the site's own webfont (Inter, which every reader downloads), not in
 *   whatever Arial the build machine has.
 * - Cached: each figure is kept under .cache/site-diagrams/ by a SHA-256 of all of the above, so a build only draws what
 *   changed and, once the cache is warm, needs no browser at all.
 * - Safe: Mermaid draws in strict mode (DOMPurify on every label); a drawing with a script, an event handler or a
 *   javascript: link is refused, and the site's CSP (no inline script) still applies to the page around it.
 * - Never fatal: with no browser, or for a diagram Mermaid cannot draw, the block is left as it is, the build says so,
 *   and kit/diagrams.js draws it in the reader's browser as before. `client: true` (build-site's --client-diagrams)
 *   leaves every block so, cache or not.
 */
import { createHash } from 'node:crypto';
import { mkdir, readFile, rename, writeFile } from 'node:fs/promises';
import path from 'node:path';

// Bump when the drawing code here changes what it writes, so old cache entries are not reused.
const RENDERER = 'site-diagrams/1';
export const BLOCK = /<pre><code class="language-mermaid">([\s\S]*?)<\/code><\/pre>/g;
// The site's text face, self-hosted under /kit/vendor/fonts (site.css loads it on every page).
export const FONT = "'Inter', Arial, sans-serif";
const KIT_FILES = ['diagrams.js', 'diagrams.css', 'vendor/mermaid/mermaid.min.js', 'vendor/fonts/fonts.css', 'vendor/fonts/inter.woff2'];
const TYPES = { '.js': 'text/javascript', '.css': 'text/css', '.woff2': 'font/woff2', '.html': 'text/html' };
const ORIGIN = 'http://cad-agent-diagrams.invalid';      // routed in the page, never fetched
const sha = x => createHash('sha256').update(x).digest('hex');
const ENT = { amp: '&', lt: '<', gt: '>', quot: '"', apos: "'", nbsp: ' ' };
/** HTML text back to the characters a browser's parser gives (what kit/diagrams.js reads as textContent). */
export const unescapeHtml = s => s.replace(/&(#x[\da-f]+|#\d+|[a-z]+);/gi, (m, e) => e[0] === '#'
  ? String.fromCodePoint(e[1].toLowerCase() === 'x' ? parseInt(e.slice(2), 16) : parseInt(e.slice(1), 10)) : (ENT[e] ?? m));

/** The browser that draws: Playwright's own Chromium, else an installed Google Chrome; null (and why) when neither starts. */
export async function launchChromium() {
  let chromium;
  try { ({ chromium } = await import('@playwright/test')); } catch (e) { return { browser: null, why: `Playwright is not installed (${e.code || e.message})` }; }
  const why = [];
  for (const [name, options] of [['Playwright Chromium', {}], ['Google Chrome', { channel: 'chrome' }]]) {
    try { return { browser: await chromium.launch({ headless: true, ...options }), why: name }; }
    catch (e) { why.push(`${name}: ${e.message.split('\n')[0]}`); }
  }
  return { browser: null, why: why.join('; ') };
}

/** Draw every block in `htmls` (strings of page HTML) and return { draw(html) → html with each block replaced, stats }.
 * `kit(rel)` and `site(rel)` read a committed file of the web kit and of web/ (the build's readBuf). `theme` is the
 * pages' data-diagram-theme; `css` the stylesheets the pages load, which the drawing page loads too. */
export async function drawDiagrams(htmls, { kit, site, theme = 'light', css = ['/web/site.css', '/kit/diagrams.css'], cacheDir,
  client = false, launch = launchChromium, log = console } = {}) {
  const files = new Map();
  for (const f of KIT_FILES) files.set(`/kit/${f}`, await kit(f));
  for (const c of css) if (c.startsWith('/web/')) files.set(c, await site(c.slice('/web/'.length)));
  // What a drawing depends on, besides its source.
  const basis = sha(JSON.stringify([RENDERER, theme, FONT, css, ...[...files].map(([f, b]) => [f, sha(b)])]));
  const mermaidVersion = JSON.parse(await kit('vendor/mermaid/SOURCE.json')).version;
  const keyOf = source => sha(`${basis}\n${source}`);
  const sources = new Map();                                       // key → source
  for (const html of htmls) for (const [, text] of html.matchAll(BLOCK)) { const s = unescapeHtml(text); sources.set(keyOf(s), s); }
  const drawn = new Map(), stats = { diagrams: sources.size, cached: 0, drawn: 0, left: 0, browser: null, mermaid: mermaidVersion };
  const cachePath = key => path.join(cacheDir, `${key}.html`);
  if (!client) for (const key of sources.keys()) {
    try { drawn.set(key, await readFile(cachePath(key), 'utf8')); stats.cached++; } catch { /* not drawn yet */ }
  }
  const todo = [...sources].filter(([key]) => !drawn.has(key));
  const warn = msg => log.warn(`${process.env.GITHUB_ACTIONS ? '::warning::' : ''}diagrams: ${msg}`);
  if (todo.length && client) {
    log.log(`diagrams: ${todo.length} diagrams left to the reader's browser, as asked (--client-diagrams)`);
    stats.left = todo.length;
  } else if (todo.length) {
    const { browser, why } = await launch();
    if (!browser) {
      warn(`${todo.length} of ${sources.size} diagrams will be drawn in the reader's browser, not at build time (${why}). ` +
        'Install a browser with `npx playwright install chromium` to draw them here.');
      stats.left = todo.length;
    } else {
      stats.browser = `${why} ${browser.version()}`;
      try {
        let out;
        try { out = await drawInBrowser(browser, todo, { files, theme, css }); }
        catch (e) { warn(`${todo.length} diagrams will be drawn in the reader's browser: the drawing page failed (${e.message.split('\n')[0]})`); out = []; stats.left = todo.length; }
        await mkdir(cacheDir, { recursive: true });
        for (const [key, result] of out) {
          if (result.error) { warn(`a diagram is left to the reader's browser: ${result.error} (it starts "${sources.get(key).split('\n')[0].slice(0, 60)}")`); stats.left++; continue; }
          drawn.set(key, result.html); stats.drawn++;
          const tmp = `${cachePath(key)}.${process.pid}.tmp`;        // other builds may share the cache: write, then rename
          await writeFile(tmp, result.html); await rename(tmp, cachePath(key));
        }
      } finally { await browser.close(); }
    }
  }
  /** One page's HTML with its blocks replaced by their figures. A figure drawn twice on one page gets a numbered id. */
  const draw = html => {
    const seen = new Map();
    return html.replace(BLOCK, (block, text) => {
      const key = keyOf(unescapeHtml(text)), figure = drawn.get(key);
      if (!figure) return block;
      const n = seen.get(key) || 0; seen.set(key, n + 1);
      return n ? figure.replaceAll(idOf(key), `${idOf(key)}-${n}`) : figure;
    });
  };
  return { draw, stats };
}
const idOf = key => `cad-diagram-s${key.slice(0, 12)}`;

/** Draw [key, source] pairs in one page that serves the kit from memory; each result is { html } or { error }. */
async function drawInBrowser(browser, todo, { files, theme, css }) {
  const context = await browser.newContext({ viewport: { width: 1366, height: 800 }, colorScheme: theme === 'dark' ? 'dark' : 'light', serviceWorkers: 'block' });
  try {
    // Nothing leaves the page: the kit and the stylesheets come from the committed files, anything else is refused.
    await context.route('**/*', route => {
      const url = new URL(route.request().url());
      if (url.origin !== ORIGIN) return route.abort();
      if (url.pathname === '/draw.html') return route.fulfill({ contentType: 'text/html', body: '<!doctype html><html lang="en"><head><meta charset="utf-8">' +
        css.map(c => `<link rel="stylesheet" href="${c}">`).join('') + `</head><body class="doc-page" data-diagram-theme="${theme}"><main></main></body></html>` });
      const body = files.get(url.pathname);
      return body ? route.fulfill({ contentType: TYPES[path.extname(url.pathname)] || 'application/octet-stream', body }) : route.abort();
    });
    // Mermaid's few random choices (and any id it makes from them) are the same on every run: Math.random is a seeded
    // generator (mulberry32), reset before each drawing.
    await context.addInitScript(() => {
      let s = 0;
      window.__cadSeed = n => { s = n >>> 0; };
      Math.random = () => { s = (s + 0x6d2b79f5) >>> 0; let t = s; t = Math.imul(t ^ (t >>> 15), t | 1); t ^= t + Math.imul(t ^ (t >>> 7), t | 61); return ((t ^ (t >>> 14)) >>> 0) / 4294967296; };
    });
    const page = await context.newPage();
    const errors = [];
    page.on('pageerror', e => errors.push(e.message));
    await page.goto(`${ORIGIN}/draw.html`);
    const results = await page.evaluate(async ({ items, theme, font }) => {
      await document.fonts.load(`16px ${font.split(',')[0]}`);
      await document.fonts.ready;
      const { drawDiagram } = await import('/kit/diagrams.js');
      // A fresh Mermaid for each drawing: the same script run again (V8 keeps its compiled code, so this is quick).
      const runtime = await (await fetch('/kit/vendor/mermaid/mermaid.min.js')).text();
      const freshMermaid = () => {
        delete globalThis.mermaid;
        const script = document.createElement('script'); script.textContent = runtime; document.head.append(script); script.remove();
        return globalThis.mermaid;
      };
      const unsafe = figure => {
        for (const el of figure.querySelectorAll('*')) {
          if (/^(script|iframe|object|embed)$/i.test(el.localName)) return `a <${el.localName}> element`;
          for (const a of el.attributes) {
            if (/^on/i.test(a.name)) return `an ${a.name} handler`;
            if (/(^|:)href$|^src$/i.test(a.name) && /^\s*(javascript|vbscript|data):/i.test(a.value)) return `a ${a.value.split(':')[0]}: link`;
          }
        }
        return null;
      };
      const out = [];
      for (const { key, source, id } of items) {
        const twice = [];
        for (let run = 0; run < 2; run++) {
          window.__cadSeed(parseInt(key.slice(0, 8), 16));
          const figure = await drawDiagram(source, { theme, id, fontFamily: font, parent: document.querySelector('main'), mermaid: freshMermaid() });
          twice.push(figure && { html: figure.outerHTML, unsafe: unsafe(figure) });
        }
        const [a, b] = twice;
        out.push([key, !a ? { error: 'Mermaid could not draw it' } : a.unsafe ? { error: `the drawing has ${a.unsafe}` }
          : a.html !== b?.html ? { error: 'two drawings of it differ' } : { html: a.html }]);
      }
      return out;
    }, { items: todo.map(([key, source]) => ({ key, source, id: idOf(key) })), theme, font: FONT });
    if (errors.length) throw new Error(`the drawing page failed: ${errors.join('; ')}`);
    return results;
  } finally { await context.close(); }
}
