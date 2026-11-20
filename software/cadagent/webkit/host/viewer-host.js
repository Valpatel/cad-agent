/** A scoped viewer shell. Domain adapters supply camera, parser and selection semantics. */
function element(tag, className, text) {
  const node = document.createElement(tag); node.className = className;
  if (text !== undefined) node.textContent = text;
  return node;
}

export function createViewerHost(container, { title = 'Engineering viewer', mount, signal } = {}) {
  if (!(container instanceof HTMLElement) || !container.isConnected) throw new TypeError('A connected viewer container is required');
  if (typeof mount !== 'function') throw new TypeError('A viewer mount adapter is required');
  const root = element('section', 'cad-viewer-host'); root.setAttribute('aria-label', title);
  const header = element('header', 'cad-viewer-toolbar'), heading = element('h2', 'cad-viewer-title', title);
  const fitButton = element('button', 'cad-viewer-button', 'Zoom to fit'); fitButton.type = 'button'; fitButton.disabled = true;
  const inspectButton = element('button', 'cad-viewer-button', 'Inspector'); inspectButton.type = 'button'; inspectButton.setAttribute('aria-expanded', 'false');
  const content = element('div', 'cad-viewer-content'), viewport = element('div', 'cad-viewer-viewport');
  viewport.tabIndex = 0; viewport.setAttribute('role', 'group'); viewport.setAttribute('aria-label', `${title} camera; arrows orbit, Shift arrows pan, plus and minus zoom, Home fits`);
  const inspector = element('aside', 'cad-viewer-inspector'); inspector.setAttribute('aria-label', `${title} inspector`); inspector.hidden = true;
  const status = element('div', 'cad-viewer-status'); status.setAttribute('role', 'status'); status.setAttribute('aria-live', 'polite');
  const message = element('p', 'cad-viewer-message', 'Preparing viewer…');
  const retryButton = element('button', 'cad-viewer-button', 'Retry viewer'); retryButton.type = 'button'; retryButton.hidden = true;
  status.append(message, retryButton); content.append(viewport, inspector, status); header.append(heading, fitButton, inspectButton);
  const selection = element('output', 'cad-viewer-selection', 'No selection'); selection.setAttribute('aria-live', 'polite');
  root.append(header, content, selection); container.append(root);
  const lifetime = new AbortController(), listeners = new Set();
  let attempt = 0, pending, current, disposed = false, ready;
  const notify = event => { for (const listener of [...listeners]) { try { listener(event); } catch (error) { console.error(error); } } };
  const live = () => { if (disposed) throw new Error('Viewer host is disposed'); };
  const setState = (state, text = '') => {
    root.dataset.state = state; root.setAttribute('aria-busy', String(state === 'loading'));
    message.textContent = text; status.hidden = state === 'ready'; retryButton.hidden = state !== 'error';
    fitButton.disabled = state !== 'ready' || typeof current?.fit !== 'function';
    notify({ type: 'status', state, message: text });
  };
  const selected = value => {
    selection.textContent = value === null ? 'No selection' : `Selected: ${String(value)}`;
    notify({ type: 'selection', nativeId: value });
  };
  async function load() {
    live(); const own = ++attempt; pending?.abort(); current?.dispose(); current = null;
    const abort = new AbortController(); pending = abort;
    viewport.replaceChildren(); inspector.replaceChildren(); selected(null); setState('loading', 'Preparing viewer…');
    let candidate;
    try {
      candidate = await mount({ viewport, inspector, signal: abort.signal,
        onProgress: text => { if (!disposed && own === attempt) setState('loading', String(text)); },
        onSelect: value => { if (!disposed && own === attempt) selected(value); },
        onState: event => {
          if (!disposed && own === attempt) {
            if (event.state === 'error' && current) setState('error', event.message || 'Viewer failed');
            notify({ type: 'domain-state', ...event });
          }
        } });
      if (disposed || own !== attempt || abort.signal.aborted) { candidate?.dispose(); return false; }
      if (!candidate || typeof candidate.dispose !== 'function' || typeof candidate.fit !== 'function'
          || typeof candidate.getViewState !== 'function' || typeof candidate.restoreViewState !== 'function') throw new TypeError('Invalid camera viewer adapter');
      current = candidate; candidate = null; setState('ready'); return true;
    } catch (error) {
      candidate?.dispose();
      if (disposed || own !== attempt || abort.signal.aborted) return false;
      viewport.replaceChildren(); inspector.replaceChildren(); setState('error', error?.message || 'Viewer unavailable');
      return false;
    }
  }
  function dispose() {
    if (disposed) return;
    const ownedFocus = root.contains(document.activeElement); disposed = true; attempt++;
    pending?.abort(); lifetime.abort(); observer.disconnect(); signal?.removeEventListener('abort', dispose);
    try { current?.dispose(); } finally { current = null; root.remove(); listeners.clear(); }
    if (ownedFocus && container.isConnected) { if (!container.hasAttribute('tabindex')) container.tabIndex = -1; container.focus({ preventScroll: true }); }
  }
  const observer = new MutationObserver(() => { if (!root.isConnected) dispose(); });
  observer.observe(document.documentElement, { childList: true, subtree: true });
  fitButton.addEventListener('click', () => current?.fit(), { signal: lifetime.signal });
  inspectButton.addEventListener('click', () => {
    inspector.hidden = !inspector.hidden; inspectButton.setAttribute('aria-expanded', String(!inspector.hidden));
  }, { signal: lifetime.signal });
  retryButton.addEventListener('click', () => { ready = load(); }, { signal: lifetime.signal });
  signal?.addEventListener('abort', dispose, { once: true });
  if (signal?.aborted) { dispose(); ready = Promise.resolve(false); } else ready = load();
  return {
    root, get ready() { return ready; },
    get capabilities() { return Object.freeze({ fit: !!current, selection: typeof current?.select === 'function', viewState: !!current }); },
    retry() { live(); ready = load(); return ready; },
    fit() { live(); if (!current) throw new Error('Viewer is not ready'); current.fit(); },
    select(value) { live(); if (typeof current?.select !== 'function') throw new Error('Selection unavailable'); return current.select(value); },
    getViewState() { live(); if (!current) throw new Error('Viewer is not ready'); return current.getViewState(); },
    restoreViewState(value) { live(); if (!current) throw new Error('Viewer is not ready'); return current.restoreViewState(value); },
    subscribe(listener) { live(); if (typeof listener !== 'function') throw new TypeError('A listener is required'); listeners.add(listener); return () => listeners.delete(listener); },
    dispose,
  };
}
