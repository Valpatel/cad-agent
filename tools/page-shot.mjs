// Photograph one local page for a catalogue cover: node tools/page-shot.mjs <page.html> <out.png> [width] [height]
// (tools/tool_figures.py --shots calls it). Chrome, or Playwright's Chromium with PLAYWRIGHT_CHANNEL=chromium.
import { chromium } from 'playwright';
import path from 'node:path';
import { pathToFileURL } from 'node:url';

const [page, out, width = '1200', height = '900'] = process.argv.slice(2);
if (!page || !out) { console.error('usage: node tools/page-shot.mjs <page.html> <out.png> [width] [height]'); process.exit(2); }
const browser = await chromium.launch({ channel: process.env.PLAYWRIGHT_CHANNEL === 'chromium' ? undefined : 'chrome', headless: true });
try {
  const tab = await browser.newPage({ viewport: { width: Number(width), height: Number(height) }, deviceScaleFactor: 1 });
  await tab.goto(pathToFileURL(path.resolve(page)).href, { waitUntil: 'load' });
  await tab.evaluate(() => document.fonts.ready);
  await tab.screenshot({ path: out });
} finally {
  await browser.close();
}
