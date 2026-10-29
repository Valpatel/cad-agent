/** Explicit, recoverable Mermaid rendering for static and dynamically inserted Markdown. */
const SELECTOR = 'pre > code.language-mermaid, pre.mermaid';
const runtimeURL = new URL('./vendor/mermaid/mermaid.min.js', import.meta.url);
let runtimePromise, queue = Promise.resolve(), sequence = 0;
const records = new WeakMap();
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
function prepare(node) {
  if (records.has(node)) return records.get(node);
  const source = node.textContent, original = node.matches('code') ? node.parentElement : node;
  const figure = document.createElement('figure'); figure.className = 'cad-diagram';
  figure.dataset.theme = themeFor(original); figure.setAttribute('aria-label', 'Engineering diagram');
  const status = document.createElement('p'); status.className = 'cad-diagram-status'; status.setAttribute('role', 'status');
  const view = document.createElement('div'); view.className = 'cad-diagram-view'; view.tabIndex = 0;
  view.setAttribute('role', 'group'); view.setAttribute('aria-label', 'Diagram; scroll horizontally if needed');
  const retry = document.createElement('button'); retry.type = 'button'; retry.textContent = 'Retry diagram'; retry.hidden = true;
  const details = document.createElement('details'), summary = document.createElement('summary'); summary.textContent = 'Diagram source';
  const pre = document.createElement('pre'); pre.textContent = source; details.append(summary, pre);
  figure.append(status, view, retry, details); original.replaceWith(figure);
  const record = {figure, status, view, retry, source, running: null}; records.set(node, record);
  retry.addEventListener('click', () => render(record));
  return record;
}
function render(record) {
  if (record.running) return record.running;
  const {figure, status, view, retry, source} = record;
  figure.dataset.state = 'loading'; figure.setAttribute('aria-busy', 'true');
  status.hidden = false; status.textContent = 'Drawing diagram…'; retry.hidden = true;
  const task = async () => {
    let scratch;
    try {
      const mermaid = await runtime();
      if (!figure.isConnected) return;
      // A generic font avoids asynchronous webfont swaps changing Mermaid's label measurements.
      mermaid.initialize({startOnLoad: false, securityLevel: 'strict', theme: figure.dataset.theme === 'dark' ? 'dark' : 'default',
        fontFamily: 'Arial, sans-serif', suppressErrorRendering: true});
      scratch = document.createElement('div'); scratch.style.cssText = 'position:absolute;left:-100000px;top:0;';
      document.body.append(scratch);
      const {svg, bindFunctions} = await mermaid.render(`cad-diagram-${++sequence}`, source, scratch);
      if (!figure.isConnected) return;
      view.innerHTML = svg;
      const rendered = view.querySelector('svg');
      if (!rendered || !rendered.viewBox.baseVal.width) throw new Error('Diagram returned no visible drawing');
      // Preserve legible labels on phones; contain scrolling inside the diagram instead of shrinking to unreadable text.
      rendered.style.width = `${rendered.viewBox.baseVal.width}px`;
      bindFunctions?.(view); figure.dataset.state = 'ready'; status.hidden = true;
    } catch {
      if (!figure.isConnected) return;
      view.replaceChildren(); figure.dataset.state = 'error'; status.textContent = 'This diagram could not be drawn. Retry or open its source.'; retry.hidden = false;
    } finally {
      scratch?.remove(); figure.setAttribute('aria-busy', 'false'); record.running = null;
    }
  };
  record.running = queue.then(task, task); queue = record.running.catch(() => {}); return record.running;
}
export function renderDiagrams(root = document) {
  const nodes = [...(root.matches?.(SELECTOR) ? [root] : []), ...root.querySelectorAll(SELECTOR)];
  return Promise.all(nodes.map(node => render(prepare(node))));
}
export function observeDiagrams(root = document.body) {
  renderDiagrams(root);
  const observer = new MutationObserver(changes => {
    for (const change of changes) for (const node of change.addedNodes)
      if (node.nodeType === 1 && !node.closest('.cad-diagram')) renderDiagrams(node);
  });
  observer.observe(root, {childList: true, subtree: true});
  return {render: () => renderDiagrams(root), dispose: () => observer.disconnect()};
}
