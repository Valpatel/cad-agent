// Photograph one local page for a catalogue cover (tools/tool_figures.py --shots calls it):
//   node tools/page-shot.mjs <page.html> <out.png> [width] [height] [selector]
// The window is width x height CSS px at 1.2 device pixels each; with a selector (Playwright's syntax), the page is
// scrolled so that element is at the top. Chrome, or Playwright's Chromium with PLAYWRIGHT_CHANNEL=chromium.
import { chromium } from 'playwright';
import path from 'node:path';
import { pathToFileURL } from 'node:url';

const [page, out, width = '1200', height = '900', selector = ''] = process.argv.slice(2);
if (!page || !out) { console.error('usage: node tools/page-shot.mjs <page.html> <out.png> [width] [height] [selector]'); process.exit(2); }
const browser = await chromium.launch({ channel: process.env.PLAYWRIGHT_CHANNEL === 'chromium' ? undefined : 'chrome', headless: true });
try {
  const tab = await browser.newPage({ viewport: { width: Number(width), height: Number(height) }, deviceScaleFactor: 1.2 });
  await tab.goto(pathToFileURL(path.resolve(page)).href, { waitUntil: 'load' });
  await tab.evaluate(() => document.fonts.ready);
  if (selector) await tab.locator(selector).first().evaluate(el => { el.scrollIntoView({ block: 'start' }); window.scrollBy(0, -12); });
  await tab.screenshot({ path: out });
} finally {
  await browser.close();
}
