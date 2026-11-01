/** Explicit, recoverable Mermaid rendering for static and dynamically inserted Markdown.
 *
 * A figure drawn ahead of time (`drawDiagram`, which the cad-agent site build runs in a headless browser, #132) arrives
 * as `<figure class="cad-diagram" data-state="ready">` with its SVG and source: it is kept as it is, without loading
 * Mermaid, and drawn again only when the page's theme is not the one it was drawn in. */
const SELECTOR = 'pre > code.language-mermaid, pre.mermaid';
const DRAWN = 'figure.cad-diagram[data-state=ready]';
// A generic font avoids asynchronous webfont swaps changing Mermaid's label measurements. A build that draws ahead of
// time, after its webfont has loaded, can pass its own (`drawDiagram`).
const FONT = 'Arial, sans-serif';
const runtimeURL = new URL('./vendor/mermaid/mermaid.min.js', import.meta.url);
let runtimePromise, queue = Promise.resolve(), sequence = 0;
const records = new WeakMap(), figures = new WeakSet();
// The stylesheet keeps the hint's line when the drawing (--cad-diagram-w) is wider than the figure, so a figure drawn
// ahead of time is laid out right before any script runs. `hidden` follows the stylesheet, for screen readers; a figure
// that is not laid out (in a closed <details>) is left to the stylesheet.
function updateOverflowHint(figure) {
  const view = figure.querySelector('.cad-diagram-view'), hint = figure.querySelector('.cad-diagram-hint');
  if (!view || !hint || !figure.getClientRects().length) return;
  hint.hidden = false;
  hint.hidden = figure.dataset.state !== 'ready' || hint.getBoundingClientRect().height < 1;
}
window.addEventListener('resize', () => document.querySelectorAll('.cad-diagram').forEach(updateOverflowHint));
function runtime() {
  if (runtimePromise) return runtimePromise;
  runtimePromise = new Promise((resolve, reject) => {
    const script = document.createElement('script'); script.src = runtimeURL.href; script.async = true;
    const timer = setTimeout(() => finish(new Error('Diagram renderer timed out')), 20000);
    function finish(error) {
      clearTimeout(timer); script.onload = script.onerror = null;
      if (error) { script.remove(); runtimePromise = undefined; reject(error); }
      else resolve(globalThis.mermaid);
    }
    script.onload = () => finish(globalThis.mermaid?.render ? null : new Error('Diagram renderer unavailable'));
    script.onerror = () => finish(new Error('Diagram renderer could not load'));
    document.head.append(script);
  });
  return runtimePromise;
}
function themeFor(node) {
  const explicit = node.closest('[data-diagram-theme]')?.dataset.diagramTheme;
  if (explicit === 'dark' || explicit === 'light') return explicit;
  const scheme = getComputedStyle(node).colorScheme;
  if (scheme === 'dark' || scheme === 'light') return scheme;
  return matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
}
function prepare(node, options = {}) {
  if (records.has(node)) return records.get(node);
  const source = node.textContent, original = node.matches('code') ? node.parentElement : node;
  const figure = document.createElement('figure'); figure.className = 'cad-diagram';
  figure.dataset.theme = themeFor(original); figure.setAttribute('aria-label', 'Engineering diagram');
  const status = document.createElement('p'); status.className = 'cad-diagram-status'; status.setAttribute('role', 'status');
  const hint = document.createElement('p'); hint.className = 'cad-diagram-hint'; hint.hidden = true;
  hint.textContent = 'Scroll sideways to see the full diagram →';
  const view = document.createElement('div'); view.className = 'cad-diagram-view'; view.tabIndex = 0;
  view.setAttribute('role', 'group'); view.setAttribute('aria-label', 'Diagram; scroll horizontally if needed');
  const retry = document.createElement('button'); retry.type = 'button'; retry.textContent = 'Retry diagram'; retry.hidden = true;
  const details = document.createElement('details'), summary = document.createElement('summary'); summary.textContent = 'Diagram source';
  const pre = document.createElement('pre'); pre.className = 'cad-diagram-source'; pre.textContent = source; details.append(summary, pre);
  figure.append(status, hint, view, retry, details); original.replaceWith(figure); figures.add(figure);
  const record = {figure, status, view, retry, source, running: null, id: options.id, font: options.fontFamily, fontSize: options.fontSize,
    mermaid: options.mermaid};
  records.set(node, record);
  retry.addEventListener('click', () => render(record));
  return record;
}
// A figure drawn ahead of time: kept, unless the page's theme is not the one it was drawn in.
function adopt(figure) {
  figures.add(figure);
  const q = selector => figure.querySelector(selector);
  const record = {figure, status: q(':scope > .cad-diagram-status'), view: q(':scope > .cad-diagram-view'), retry: q(':scope > button'),
    source: q(':scope > details > pre')?.textContent ?? '', running: null};
  updateOverflowHint(figure);
  if (!record.status || !record.view || !record.retry || !record.source) return;
  record.retry.addEventListener('click', () => render(record));
  const theme = themeFor(figure.parentElement);
  if (theme === figure.dataset.theme) return;
  figure.dataset.theme = theme;
  return render(record);
}
function render(record) {
  if (record.running) return record.running;
  const {figure, status, view, retry, source} = record;
  figure.dataset.state = 'loading'; figure.setAttribute('aria-busy', 'true');
  status.hidden = false; status.textContent = 'Drawing diagram…'; retry.hidden = true;
  const task = async () => {
    let scratch;
    try {
      const mermaid = record.mermaid || await runtime();
      if (!figure.isConnected) return;
      mermaid.initialize({startOnLoad: false, securityLevel: 'strict', theme: figure.dataset.theme === 'dark' ? 'dark' : 'default',
        fontFamily: record.font || FONT, ...(record.fontSize ? {themeVariables: {fontSize: record.fontSize}} : {}), suppressErrorRendering: true});
      scratch = document.createElement('div'); scratch.style.cssText = 'position:absolute;left:-100000px;top:0;';
      document.body.append(scratch);
      const {svg, bindFunctions} = await mermaid.render(record.id || `cad-diagram-${++sequence}`, source, scratch);
      if (!figure.isConnected) return;
      view.innerHTML = svg;
      const rendered = view.querySelector('svg');
      if (!rendered || !rendered.viewBox.baseVal.width) throw new Error('Diagram returned no visible drawing');
      // Preserve legible labels on phones; contain scrolling inside the diagram instead of shrinking to unreadable text.
      rendered.style.width = `${rendered.viewBox.baseVal.width}px`;
      figure.style.setProperty('--cad-diagram-w', `${rendered.viewBox.baseVal.width}px`);
      bindFunctions?.(view); figure.dataset.state = 'ready'; status.hidden = true; updateOverflowHint(figure);
    } catch {
      if (!figure.isConnected) return;
      view.replaceChildren(); figure.style.removeProperty('--cad-diagram-w'); figure.dataset.state = 'error'; updateOverflowHint(figure);
      status.textContent = 'This diagram could not be drawn. Retry or open its source.'; retry.hidden = false;
    } finally {
      scratch?.remove(); figure.setAttribute('aria-busy', 'false'); record.running = null;
    }
  };
  record.running = queue.then(task, task); queue = record.running.catch(() => {}); return record.running;
}
export function renderDiagrams(root = document) {
  const all = selector => [...(root.matches?.(selector) ? [root] : []), ...root.querySelectorAll(selector)];
  return Promise.all([...all(SELECTOR).map(node => render(prepare(node))), ...all(DRAWN).filter(f => !figures.has(f)).map(adopt)]);
}
export function observeDiagrams(root = document.body) {
  renderDiagrams(root);
  const observer = new MutationObserver(changes => {
    for (const change of changes) for (const node of change.addedNodes)
      if (node.nodeType === 1 && !node.parentElement?.closest('.cad-diagram')) renderDiagrams(node);
  });
  observer.observe(root, {childList: true, subtree: true});
  return {render: () => renderDiagrams(root), dispose: () => observer.disconnect()};
}
/** Draw one diagram ahead of time, for a page that will show it without running Mermaid. The source goes into `parent`
 * as a block and is drawn in `theme` ('light' or 'dark'), with `id` as its SVG id, in `fontFamily` (a font the page
 * itself serves, already loaded here, so the labels measure the same for every reader) at `fontSize` (CSS; default
 * Mermaid's 16px). Returns the finished figure, taken out of `parent`, or null when Mermaid cannot draw it. The
 * overflow hint is left to the stylesheet, which knows the drawing's width and the column's. `mermaid` is the Mermaid to
 * draw with (default: the vendored one, loaded once): Mermaid numbers some elements with counters that run on from one
 * drawing to the next, so a drawing that must not depend on what was drawn before gets a fresh instance. */
export async function drawDiagram(source, {theme = 'light', id, fontFamily = FONT, fontSize, parent = document.body, mermaid} = {}) {
  const holder = document.createElement('div'); holder.dataset.diagramTheme = theme === 'dark' ? 'dark' : 'light';
  const pre = document.createElement('pre'); pre.className = 'mermaid'; pre.textContent = source;
  holder.append(pre); parent.append(holder);
  const record = prepare(pre, {id, fontFamily, fontSize, mermaid});
  await render(record);
  const {figure} = record;
  holder.remove();
  if (figure.dataset.state !== 'ready') return null;
  figure.querySelector('.cad-diagram-hint').removeAttribute('hidden');
  return figure;
}
