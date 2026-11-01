/** Draw the site's Mermaid diagrams at build time (#132), so a page arrives with its diagrams finished: nothing moves
 * while it loads, they show without script, and no page downloads Mermaid to draw them.
 *
 * Each `<pre><code class="language-mermaid">` block the Markdown renderer wrote is drawn once by the web kit's own
 * `drawDiagram` (kit/diagrams.js, the code that draws it in a reader's browser) with the vendored Mermaid, in headless
 * Chromium through Playwright, which the browser tests already use. The figure it returns, `<figure class="cad-diagram"
 * data-state="ready">` with the SVG and the source, replaces the block; kit/diagrams.js leaves such figures alone.
 *
 * - Deterministic, on one machine and browser build: the same source, theme, Mermaid, kit, font and drawing code give
 *   the same bytes. The SVG id comes from a hash of those; each drawing gets a fresh Mermaid (its sequence and class
 *   diagrams number elements with counters that run on from one drawing to the next) and a seeded Math.random; every
 *   diagram is drawn twice and kept only if both drawings match; a gantt chart is drawn without its "today" line, which
 *   Mermaid places from the clock; and the labels are measured in the site's own webfont (Inter, which every reader
 *   downloads), not in whatever Arial the build machine has (FONT_SIZE says why 15px). Inter here is its latin subset:
 *   a label character it lacks (→, ≈, Greek, emoji) is measured in the machine's fallback font, so another machine can draw
 *   that diagram a little differently. The build names those characters (stats.uncovered).
 * - Cached: each figure is kept under .cache/site-diagrams/ by a SHA-256 of all of the above, so a build only draws what
 *   changed and, once the cache is warm, needs no browser at all. The browser build is not in the key, so that a warm
 *   cache needs none: after a browser upgrade, empty the cache to draw everything again.
 * - Safe: Mermaid draws in strict mode (DOMPurify on every label); a drawing with a script, an event handler or a
 *   javascript: link is refused, and the site's CSP (no inline script) still applies to the page around it.
 * - Never fatal: with no browser, or for a diagram Mermaid cannot draw, the block is left as it is, the build says so,
 *   and kit/diagrams.js draws it in the reader's browser as before. `client: true` (build-site's --client-diagrams)
 *   leaves every block so, cache or not.
 *
 * Adopted vs built: the approach (Mermaid in Playwright's Chromium at build time, inline SVG, the block kept when no
 * browser is there) is mermaid-isomorphic's, behind rehype-mermaid (MIT, Remco Haszing). mermaid-cli (MIT) does the same
 * through Puppeteer. Neither is a dependency here: both bring their own Mermaid from npm, not the vendored, hash-checked
 * one; both return a bare SVG, not the kit's figure that kit/diagrams.js knows; and this site's Markdown goes through
 * marked, not rehype. Playwright and Chromium themselves are credited in THIRD_PARTY_NOTICES.md.
 */
import { createHash } from 'node:crypto';
import { mkdir, readFile, rename, writeFile } from 'node:fs/promises';
import path from 'node:path';

export const BLOCK = /<pre><code class="language-mermaid">([\s\S]*?)<\/code><\/pre>/g;
// The site's text face, self-hosted under /kit/vendor/fonts (site.css loads it on every page), at 15px: Inter's x-height
// is about 5 % taller than Arial's, so 15px Inter reads at the size of the 16px Arial a reader's browser draws with,
// and the diagrams come out as wide as they were (within 1 %), so each still fits the article column.
export const FONT = "'Inter', Arial, sans-serif", FONT_SIZE = '15px';
const KIT_FILES = ['diagrams.js', 'diagrams.css', 'vendor/mermaid/mermaid.min.js', 'vendor/fonts/fonts.css', 'vendor/fonts/inter.woff2'];
const TYPES = { '.js': 'text/javascript', '.css': 'text/css', '.woff2': 'font/woff2', '.html': 'text/html' };
const ORIGIN = 'http://cad-agent-diagrams.invalid';      // routed in the page, never fetched
const sha = x => createHash('sha256').update(x).digest('hex');
const ENT = { amp: '&', lt: '<', gt: '>', quot: '"', apos: "'", nbsp: '\u00a0' };
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
 * pages' data-diagram-theme; `css` the stylesheets the pages load, which the drawing page loads too; `timeout` the ms
 * one diagram may take. */
export async function drawDiagrams(htmls, { kit, site, theme = 'light', css = ['/web/site.css', '/kit/diagrams.css'], cacheDir,
  client = false, launch = launchChromium, log = console, timeout = 20000 } = {}) {
  const files = new Map();
  for (const f of KIT_FILES) files.set(`/kit/${f}`, await kit(f));
  for (const c of css) if (c.startsWith('/web/')) files.set(c, await site(c.slice('/web/'.length)));
  // What a drawing depends on, besides its source: this module's own code too, so a change to how it draws never
  // reuses an old drawing.
  const self = sha(await readFile(new URL(import.meta.url)));
  const basis = sha(JSON.stringify([self, theme, FONT, FONT_SIZE, css, ...[...files].map(([f, b]) => [f, sha(b)])]));
  const mermaidVersion = JSON.parse(await kit('vendor/mermaid/SOURCE.json')).version;
  const keyOf = source => sha(`${basis}\n${source}`);
  const sources = new Map();                                       // key → source
  for (const html of htmls) for (const [, text] of html.matchAll(BLOCK)) { const s = unescapeHtml(text); sources.set(keyOf(s), s); }
  const drawn = new Map(), stats = { diagrams: sources.size, cached: 0, drawn: 0, left: 0, browser: null, mermaid: mermaidVersion,
    uncovered: '' };
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
        let out = [];
        try {
          const run = await drawInBrowser(browser, todo, { files, theme, css, timeout });
          out = run.out;
          if (run.errors.length) warn(`the drawing page reported: ${[...new Set(run.errors)].join('; ')}`);
        } catch (e) {
          warn(`${todo.length} diagrams will be drawn in the reader's browser: the drawing page failed (${e.message.split('\n')[0]})`);
          stats.left = todo.length;
        }
        await mkdir(cacheDir, { recursive: true });
        const uncovered = new Set();
        let unsure = 0;
        for (const [key, result] of out) {
          if (result.error) { warn(`a diagram is left to the reader's browser: ${result.error} (it starts "${sources.get(key).split('\n')[0].slice(0, 60)}")`); stats.left++; continue; }
          drawn.set(key, result.html); stats.drawn++;
          if (result.uncovered) { unsure++; for (const c of result.uncovered) uncovered.add(c); }
          const tmp = `${cachePath(key)}.${process.pid}.tmp`;        // other builds may share the cache: write, then rename
          await writeFile(tmp, result.html); await rename(tmp, cachePath(key));
        }
        stats.uncovered = [...uncovered].sort().join('');
        if (unsure) log.log(`diagrams: ${unsure} of the ${stats.drawn} drawn have label characters the site's font does not have ` +
          `(${[...stats.uncovered].join(' ')}). They are measured in this machine's fallback font, so another machine can ` +
          'draw those diagrams a little differently.');
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

/** The source as it is drawn ahead of time. A page drawn once cannot know the reader's day, so a gantt chart gets
 * `todayMarker off` (Mermaid otherwise draws a "today" line from the build machine's clock, and the cache would keep
 * the first build's day). The reader still sees the source as written. */
export function forDrawing(source) {
  const [, front = '', body] = source.match(/^(\s*---\n[\s\S]*?\n---[ \t]*\n)?([\s\S]*)$/);
  const type = body.split('\n').map(l => l.trim()).find(l => l && !l.startsWith('%%'))?.split(/\s/)[0];
  if (type !== 'gantt') return source;
  return front + body.replace(/^[ \t]*todayMarker\b.*\n?/gm, '').replace(/^([ \t]*gantt\b.*)$/m, '$1\n    todayMarker off');
}

/** Draw [key, source] pairs in a page that serves the kit from memory. Returns [key, { html } or { error }] pairs and
 * the page's own errors. A drawing that takes longer than `timeout` ms (Mermaid has had infinite loops) is given up
 * and the page started again for the rest. */
async function drawInBrowser(browser, todo, { files, theme, css, timeout = 20000 }) {
  let context, page;
  const errors = [];
  const start = async () => {
    context = await browser.newContext({ viewport: { width: 1366, height: 800 }, colorScheme: theme === 'dark' ? 'dark' : 'light', serviceWorkers: 'block' });
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
    page = await context.newPage();
    page.on('pageerror', e => errors.push(e.message.split('\n')[0]));
    await page.goto(`${ORIGIN}/draw.html`);
    await page.evaluate(async ({ theme, font, fontSize }) => {
      await document.fonts.load(`${fontSize} ${font.split(',')[0]}`);
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
      // Label characters the font lacks: drawn in the same pixels as in no font at all (the browser's default).
      const canvas = Object.assign(document.createElement('canvas'), { width: 48, height: 32 });
      const ctx = canvas.getContext('2d', { willReadFrequently: true }), lacks = new Map();
      const pixels = (c, family) => { ctx.clearRect(0, 0, 48, 32); ctx.font = `${fontSize} ${family}`; ctx.fillText(c, 4, 24); return ctx.getImageData(0, 0, 48, 32).data.join(); };
      const missing = c => { if (!lacks.has(c)) lacks.set(c, pixels(c, font.split(',')[0]) === pixels(c, 'cad-no-such-font')); return lacks.get(c); };
      const labels = svg => { let text = ''; const walk = document.createTreeWalker(svg, NodeFilter.SHOW_TEXT);
        for (let n; (n = walk.nextNode());) if (!n.parentElement.closest('style')) text += n.data; return text; };
      // Drawn twice, each time with a fresh Mermaid and the same seed: kept only if both drawings are the same bytes.
      window.__cadDraw = async ({ key, source, shown, id }) => {
        const twice = [];
        for (let run = 0; run < 2; run++) {
          window.__cadSeed(parseInt(key.slice(0, 8), 16));
          const figure = await drawDiagram(source, { theme, id, fontFamily: font, fontSize, parent: document.querySelector('main'), mermaid: freshMermaid() });
          if (figure) figure.querySelector(':scope > details > pre.cad-diagram-source').textContent = shown;
          twice.push(figure && { html: figure.outerHTML, unsafe: unsafe(figure),
            uncovered: [...new Set(labels(figure.querySelector('svg')))].filter(c => c > '~' && !/[\s\p{M}\p{Cf}]/u.test(c) && missing(c)).join('') });
        }
        const [a, b] = twice;
        return !a ? { error: 'Mermaid could not draw it' } : a.unsafe ? { error: `the drawing has ${a.unsafe}` }
          : a.html !== b?.html ? { error: 'two drawings of it differ' } : { html: a.html, uncovered: a.uncovered };
      };
    }, { theme, font: FONT, fontSize: FONT_SIZE });
  };
  const out = [];
  try {
    await start();
    for (const [key, source] of todo) {
      let timer;
      const late = new Promise(ok => { timer = setTimeout(() => ok({ error: `it took more than ${timeout / 1000} s` }), timeout); });
      const drawing = page.evaluate(item => window.__cadDraw(item), { key, source: forDrawing(source), shown: source, id: idOf(key) })
        .catch(e => ({ error: `the drawing page failed (${e.message.split('\n')[0]})` }));
      const result = await Promise.race([drawing, late]);
      clearTimeout(timer);
      out.push([key, result]);
      if (result.error && !/^(Mermaid could not|the drawing has|two drawings)/.test(result.error)) { await context.close(); await start(); }
    }
  } finally { await context?.close(); }
  return { out, errors };
}
