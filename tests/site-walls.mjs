/** Walls of text (#179): the longest vertical stretch of a page's content with no picture, diagram, demo or render in
 * it, measured in a real browser. The owner (2026-10-31): "CAD is graphical, so our site should be too. Not a wall of
 * text." tests/website-browser.mjs runs it on every page at 1366 x 800 and holds each page under WALL_LIMIT, except
 * the pages in its WALLS list (the backlog, each with its issue), which may only leave the list.
 *
 * What counts as something to look at: an <img>, <svg>, <video>, <canvas>, <picture>, <cad-model>, a rendered Mermaid
 * diagram (.cad-diagram) or anything marked [data-visual], at least 120 x 80 px as laid out (so an icon, a badge or a
 * copy button's glyph does not count, and a picture folded away in a closed <details> has no size). The content is
 * the doc page's article, else the page's <main>. A stretch runs from the content's top to the first picture,
 * between pictures (overlapping ones merge), and from the last picture to the content's end.
 */

export const VIEWPORT = { width: 1366, height: 800 };
export const WALL_LIMIT = 1.5 * VIEWPORT.height;      // 1200 px: about one and a half screens of reading, no picture
// A page on the backlog must leave it once its longest stretch is under 1080 px. The band between the two keeps a page
// from bouncing on and off the list with each small edit, and absorbs the engines' differences: the site's own fonts
// (kit/vendor/fonts) make the text the same everywhere, but Chrome and WebKit still lay a long page out up to about 4
// percent apart (docs/common-issues: 1186 px in Chrome, 1214 px in WebKit, on 2026-10-31).
export const WALL_CLEARED = 0.9 * WALL_LIMIT;
export const VISUAL = 'img, svg, video, canvas, picture, cad-model, .cad-diagram, [data-visual]';

/** Run in the page (page.evaluate(longestStretch, VISUAL)): { worst, from, to, after, visuals, height } in CSS px,
 * `from`/`to` measured from the content's top, `after` the last heading above the stretch (to say where to look). */
export function longestStretch(selector) {
  const content = document.querySelector('article.prose') || document.querySelector('main');
  const box = content.getBoundingClientRect(), top = box.top + scrollY, bottom = box.bottom + scrollY;
  // Folded away: inside a closed <details> and not in its summary. Chrome lays such content out when asked (it is
  // only hidden by content-visibility), so its size alone does not say the reader cannot see it.
  const folded = el => {
    for (let d = el.closest('details:not([open])'); d; d = d.parentElement?.closest('details:not([open])'))
      if (!d.querySelector(':scope > summary')?.contains(el)) return true;
    return false;
  };
  const spans = [...content.querySelectorAll(selector)]
    .filter(el => (!el.parentElement.closest(selector) || el.matches('.cad-diagram')) && !folded(el))
    .map(el => el.getBoundingClientRect()).filter(r => r.width >= 120 && r.height >= 80)
    .map(r => [r.top + scrollY, r.bottom + scrollY]).sort((a, b) => a[0] - b[0]);
  let at = top, worst = 0, from = top;
  for (const [start, end] of spans) {
    if (start - at > worst) { worst = start - at; from = at; }
    at = Math.max(at, end);
  }
  if (bottom - at > worst) { worst = bottom - at; from = at; }
  const heads = [...content.querySelectorAll('h1, h2, h3')].filter(h => h.getBoundingClientRect().top + scrollY <= from + 1);
  return { worst: Math.round(worst), from: Math.round(from - top), to: Math.round(from - top + worst), visuals: spans.length,
    height: Math.round(bottom - top), after: heads.at(-1)?.textContent.trim().slice(0, 60) || '(top)' };
}

/** Run in the page: planted articles with known geometry, so the measure itself is tested on every run. The measure
 * comes in as an argument (page.evaluate sends one function's source, not what it calls): use `plantedScript()`. */
export function plantedStretches(selector, longestStretch) {
  const make = html => {
    const host = Object.assign(document.createElement('div'), { style: 'position:absolute;left:0;top:0;width:800px' });
    host.innerHTML = `<article class="prose" style="margin:0;padding:0">${html}</article>`;
    document.body.prepend(host);
    return host;
  };
  const text = px => `<p style="height:${px}px;margin:0">words</p>`;
  const pic = (w, h) => `<img alt="" width="${w}" height="${h}" style="display:block;width:${w}px;height:${h}px">`;
  const cases = {
    // 300 text, a picture, 1500 text, a picture, 200 text: the middle stretch decides
    between: [text(300) + pic(400, 200) + text(1500) + pic(400, 200) + text(200), 1500],
    // a 24 px icon and a 100 x 60 badge are not pictures, so the whole 2000 px (with their 84) is one stretch
    small: [text(900) + pic(24, 24) + pic(100, 60) + text(1016), 2000],
    // a picture folded away in a closed <details> is not seen; one in its summary is (the 120 x 90 thumbnail)
    open: [text(700) + `<details open><summary style="height:20px;display:block">more</summary>${pic(400, 300)}</details>` + text(1000), 1000],
    folded: [text(700) + `<details><summary style="height:20px;display:block">more</summary>${pic(400, 300)}</details>` + text(700), 1420],
    summary: [text(700) + `<details><summary style="display:block">${pic(120, 90)}</summary>${pic(400, 300)}</details>` + text(600), 700],
    // a diagram counts once, however many <svg> it holds
    diagram: [text(500) + `<div class="cad-diagram" style="width:400px;height:300px;margin:0;padding:0;box-sizing:border-box"><svg width="400" height="300"></svg><svg width="10" height="10"></svg></div>` + text(800), 800],
  };
  const out = {};
  for (const [name, [html, want]] of Object.entries(cases)) {
    const host = make(html);                                      // first in the document, so it is the one measured
    out[name] = { got: longestStretch(selector).worst, want };
    host.remove();
  }
  return out;
}

/** The expression page.evaluate runs for plantedStretches, with longestStretch passed in. */
export const plantedScript = () => `(${plantedStretches})(${JSON.stringify(VISUAL)}, ${longestStretch})`;
