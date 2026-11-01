/** <cad-nav>: a sticky page tree for long docs on wide screens, with the current page's outline and where you are.
 *
 *   <link rel="stylesheet" href="/kit/nav.css">          <!-- in <head>: styled and folded from the first paint -->
 *   <script type="module" src="/kit/nav.js"></script>
 *   <div class="layout">                                  <!-- your grid: nav column + content column -->
 *     <cad-nav for="article" role="navigation" aria-label="Pages and contents">
 *       <details class="cad-nav-fold"><summary class="cad-nav-toggle">Pages and contents</summary>
 *         <div class="cad-nav-panel">
 *           <input type="search" class="cad-nav-filter" placeholder="Filter pages" aria-label="Filter pages">
 *           <details class="cad-nav-group" open><summary>Docs</summary>
 *             <ul><li><a href="/docs/a">A</a></li><li><a href="/docs/b" aria-current="page">B</a>
 *               <ol class="cad-nav-outline" aria-label="On this page"><li class="h2"><a href="#x">X</a></li></ol></li></ul>
 *           </details>
 *         </div>
 *       </details>
 *     </cad-nav>
 *     <article>…<h2 id="x">…</h2>…</article>
 *   </div>
 *
 * Give <cad-nav> the full height of its column (align-self: stretch in a grid), so its panel can stay in view.
 * Everything above is plain HTML: without script, or while the script is slow or if it fails, the fold opens and closes
 * natively on narrow screens (Enter, Space or a tap on its summary), wide screens show the tree with no toggle
 * (nav.css), the groups open and close and the outline links work. Write it out like this (a build step can) and
 * nothing moves when the script arrives. A bare tree of groups also works: the script then adds the fold, the filter and
 * the outline (of the `for` element's h2/h3 headings with ids) itself, and sets the landmark role and label (`label`,
 * default "Contents"); it also wraps the <button class="cad-nav-toggle"> of earlier kit versions into the fold.
 * The script:
 * - marks the section being read in every outline (in the tree, and in any element matched by `rail`, e.g. a right-hand
 *   "On this page" column) with aria-current="location", as you scroll and when you follow an outline link;
 * - narrows the tree as you type in the filter (Esc clears; says so when nothing matches);
 * - keeps the fold open on wide screens (for browsers without ::details-content), and never opens or closes it on
 *   narrow ones, except to close again a fold it opened for a wide window.
 * No dependencies.
 */

/** The outline entries for a container: h2 and h3 headings that have ids. */
export function outlineOf(root) {
  return [...(root?.querySelectorAll('h2[id], h3[id]') || [])]
    .map(h => ({ id: h.id, level: h.tagName === 'H2' ? 2 : 3, text: h.textContent.trim() }))
    .filter(h => h.text);
}

function outlineList(items) {
  const list = document.createElement('ol');
  list.className = 'cad-nav-outline';
  list.setAttribute('aria-label', 'On this page');
  for (const h of items) {
    const li = document.createElement('li');
    li.className = `h${h.level}`;
    const a = document.createElement('a');
    a.href = `#${encodeURIComponent(h.id)}`;
    a.textContent = h.text;                                  // heading text, never markup
    li.append(a);
    list.append(li);
  }
  return list;
}

export class CadNav extends HTMLElement {
  #stop;

  connectedCallback() {
    if (this.#stop) return;
    this.#stop = new AbortController();
    const signal = this.#stop.signal;
    const label = this.getAttribute('label') || 'Contents';
    if (!this.hasAttribute('role')) this.setAttribute('role', 'navigation');
    if (!this.hasAttribute('aria-label')) this.setAttribute('aria-label', label);

    // The fold around the panel: written out by the page, or built here for a bare tree (or an old <button> toggle).
    let fold = this.querySelector(':scope > details.cad-nav-fold');
    const old = fold ? null : this.querySelector(':scope > .cad-nav-toggle'), host = fold || this;
    let panel = host.querySelector(':scope > .cad-nav-panel');
    if (!panel) {
      panel = document.createElement('div');
      panel.className = 'cad-nav-panel';
      panel.append(...[...host.childNodes].filter(n => n !== old && n.localName !== 'summary'));
      host.append(panel);
    }
    if (!fold) {
      fold = document.createElement('details');
      fold.className = 'cad-nav-fold';
      fold.open = this.hasAttribute('data-open');
      const summary = document.createElement('summary');
      summary.className = 'cad-nav-toggle';
      summary.textContent = old?.textContent.trim() || label;   // the label is page text, never markup
      fold.append(summary, panel);
      old?.remove();
      this.append(fold);
    }
    this.#fold(fold, signal);
    let filter = panel.querySelector(':scope > .cad-nav-filter');
    if (!filter) {
      filter = document.createElement('input');
      filter.type = 'search';
      filter.className = 'cad-nav-filter';
      filter.placeholder = 'Filter pages';
      filter.setAttribute('aria-label', 'Filter pages');
      panel.prepend(filter);
    }
    this.#filter(filter, panel, signal);
    this.#outline(panel, signal);
    this.#reveal(panel, filter);
  }

  disconnectedCallback() {
    this.#stop?.abort();
    this.#stop = undefined;
  }

  /** On wide screens nav.css takes the fold's box away (display: contents) and shows the panel whether or not the
   * <details> is open; the fold is opened there anyway, so a browser without ::details-content shows the panel too
   * and the open state says what is on screen. The native toggle is the reader's on narrow screens: the only fold
   * closed here is one opened here, when the window narrows again. */
  #fold(fold, signal) {
    let opened = false;
    const fit = () => {
      const wide = getComputedStyle(fold).display === 'contents';
      if (wide && !fold.open) { fold.open = true; opened = true; }
      else if (!wide && opened) { fold.open = false; opened = false; }
    };
    fit();
    addEventListener('resize', fit, { passive: true, signal });
  }

  /** On a scrolling panel, bring the current page into view without hiding the filter (it is sticky) or, when it
   * fits, the name of the page's group; never moves the page itself. */
  #reveal(panel, filter) {
    const current = panel.querySelector('a[aria-current=page]');
    if (!current || panel.scrollHeight <= panel.clientHeight + 1) return;
    const top = el => el.getBoundingClientRect().top - panel.getBoundingClientRect().top + panel.scrollTop;
    const room = filter.offsetHeight + 16, visible = () => top(current) - panel.scrollTop + current.offsetHeight <= panel.clientHeight - 24;
    if (visible()) return;
    const group = current.closest('details');                   // its group, if the tree has groups (not the fold)
    panel.scrollTop = Math.max(0, (group && panel.contains(group) ? top(group) : top(current)) - room);
    if (!visible()) panel.scrollTop = Math.max(0, top(current) - panel.clientHeight / 3);
  }

  #outline(panel, signal) {
    const target = document.querySelector(this.getAttribute('for') || 'article');
    const current = panel.querySelector('a[aria-current=page]');
    if (current && !panel.querySelector('.cad-nav-outline')) {
      const items = outlineOf(target);
      if (items.length >= 2) current.after(outlineList(items));
    }
    const group = current?.closest('details');
    if (group && panel.contains(group)) group.open = true;   // its group, never the fold around the panel (a flat tree)
    const rails = this.getAttribute('rail') ? [...document.querySelectorAll(this.getAttribute('rail'))] : [];
    const links = [...panel.querySelectorAll('.cad-nav-outline a'), ...rails.flatMap(r => [...r.querySelectorAll('a[href^="#"]')])];
    const byId = new Map();
    for (const a of links) {
      const id = decodeURIComponent(a.hash.slice(1));
      if (!byId.has(id)) byId.set(id, []);
      byId.get(id).push(a);
    }
    const heads = [...byId.keys()].map(id => document.getElementById(id)).filter(Boolean)
      .sort((a, b) => a.compareDocumentPosition(b) & Node.DOCUMENT_POSITION_FOLLOWING ? -1 : 1);
    if (!heads.length) return;
    // The section being read: the last heading above a line a third of the way down the window, checked once per frame
    // while scrolling. Two exceptions: a heading just jumped to (an outline link or its #hash) stays marked, through a
    // smooth scroll, until the reader scrolls on; and at the very bottom of a page that scrolls, where the last
    // sections can never reach the line, the last heading on screen is marked.
    // A jump ends where its heading shows below the page's scroll padding (or as far as the page scrolls), not after a
    // quiet spell: a frame slow to paint can stall a smooth scroll for longer than that (#158). From there any scroll
    // releases it. Before that only the reader's input does: a wheel, touch or scroll key that will move the page, aimed
    // anywhere (over the tree or a rail too, unless that list scrolls instead; never typing in a field), makes the next
    // page scroll theirs (#123 review 4). A jump that stops short with no such input (the page moved under it, a
    // scrollbar drag) counts as ended after 600 ms without a scroll.
    let pinned = null, settled = true, settle = 0, steered = false, queued = false, shown = null;
    const root = document.scrollingElement || document.documentElement;
    const onScreen = h => { const t = h.getBoundingClientRect().top; return t >= -2 && t < innerHeight - 8; };
    const mark = () => {
      queued = false;
      const line = Math.min(innerHeight / 3, 220);
      let active = heads.filter(h => h.getBoundingClientRect().top <= line).at(-1);
      if (root.scrollHeight > innerHeight + 2 && root.scrollTop + innerHeight >= root.scrollHeight - 2)
        active = heads.filter(onScreen).at(-1) || active;
      if (pinned) active = pinned;
      for (const [id, as] of byId) for (const a of as) {
        if (id === active?.id) a.setAttribute('aria-current', 'location');
        else a.removeAttribute('aria-current');
      }
      if (active !== shown) { shown = active; for (const a of byId.get(active?.id) || []) this.#keepVisible(a, panel); }
    };
    const schedule = () => { if (!queued) { queued = true; requestAnimationFrame(mark); } };
    const px = (v, of) => v.endsWith('%') ? parseFloat(v) * of / 100 : parseFloat(v) || 0;
    const arrived = () => {
      const pad = px(getComputedStyle(root).scrollPaddingTop, root.clientHeight) + px(getComputedStyle(pinned).scrollMarginTop, 0);
      const end = Math.max(0, Math.min(root.scrollHeight - root.clientHeight, root.scrollTop + pinned.getBoundingClientRect().top - pad));
      return Math.abs(root.scrollTop - end) <= 2;
    };
    const quiet = () => { clearTimeout(settle); settle = setTimeout(() => { settled = true; }, 600); };
    const pin = id => {
      const h = byId.has(id) && document.getElementById(id);   // only outline headings: not the skip link's target
      // The hashchange after a link's click is the same jump; the same link again after a jump stopped short is a new one.
      if (!h || (h === pinned && (!settled || arrived()))) return;
      pinned = h; steered = false; settled = arrived();
      if (settled) clearTimeout(settle); else quiet();
      schedule();
    };
    const release = () => { pinned = null; clearTimeout(settle); schedule(); };
    addEventListener('scroll', () => {
      if (pinned) {
        const there = arrived();
        if (steered || (settled && !there)) release();
        else if (there) { settled = true; clearTimeout(settle); }
        else if (!settled) quiet();
      }
      schedule();
    }, { passive: true, signal });
    addEventListener('resize', schedule, { passive: true, signal });
    // Whether input aimed at `el` that moves `dy` (down when positive) scrolls the page: no box on the way up takes it
    // (one that can still scroll that way, or keeps its scrolling to itself), and the page can move that way.
    const movesPage = (el, dy) => {
      if (!dy) return false;
      for (let box = el instanceof Element ? el : el?.parentElement; box && box !== root && box !== document.body; box = box.parentElement) {
        if (box.scrollHeight <= box.clientHeight + 1) continue;
        const cs = getComputedStyle(box);
        if (!/auto|scroll|overlay/.test(cs.overflowY)) continue;
        if (/contain|none/.test(cs.overscrollBehaviorY) || (dy < 0 ? box.scrollTop > 0 : box.scrollTop + box.clientHeight < box.scrollHeight - 1)) return false;
      }
      return dy < 0 ? root.scrollTop > 0 : root.scrollTop + root.clientHeight < root.scrollHeight - 1;
    };
    addEventListener('wheel', e => { if (pinned && !e.ctrlKey && !e.defaultPrevented && movesPage(e.target, e.deltaY)) steered = true; }, { passive: true, signal });
    let touchY = null;
    addEventListener('touchstart', e => { touchY = e.touches[0]?.clientY ?? null; }, { passive: true, signal });
    addEventListener('touchmove', e => {
      const y = e.touches[0]?.clientY ?? null;
      if (pinned && touchY !== null && y !== null && movesPage(e.target, touchY - y)) steered = true;
      touchY = y;
    }, { passive: true, signal });
    // Keys that scroll, by direction; never while typing in a field, nor Space on a control it presses.
    const KEYS = new Map([['ArrowUp', -1], ['ArrowDown', 1], ['PageUp', -1], ['PageDown', 1], ['Home', -1], ['End', 1], [' ', 1]]);
    addEventListener('keydown', e => {
      const t = e.target, dy = e.key === ' ' && e.shiftKey ? -1 : KEYS.get(e.key);
      if (!pinned || !dy || e.defaultPrevented || t?.closest?.('input, textarea, select, [contenteditable]:not([contenteditable=false])')) return;
      if (e.key === ' ' && t?.closest?.('button, summary, [role=button]')) return;
      if (movesPage(t, dy)) steered = true;
    }, { signal });
    addEventListener('hashchange', () => pin(decodeURIComponent(location.hash.slice(1))), { signal });
    for (const a of links) a.addEventListener('click', () => pin(decodeURIComponent(a.hash.slice(1))), { signal });
    if (location.hash) pin(decodeURIComponent(location.hash.slice(1)));
    mark();
  }

  /** Scroll the list that holds a marked link (the panel, or a rail with its own scrollbar) so the link is in view;
   * never the page. Not while the reader is filtering the tree. */
  #keepVisible(a, panel) {
    if (!a.getClientRects().length) return;                   // that copy of the outline is not shown at this width
    let box = a.parentElement;
    while (box && box !== document.body && !(box.scrollHeight > box.clientHeight + 1 && /auto|scroll/.test(getComputedStyle(box).overflowY)))
      box = box.parentElement;
    if (!box || box === document.body) return;
    if (box === panel && panel.querySelector(':scope > .cad-nav-filter')?.value) return;
    const filter = box === panel ? panel.querySelector(':scope > .cad-nav-filter') : null;
    const top = (filter?.offsetHeight || 0) + 16, bottom = 24;
    const b = box.getBoundingClientRect(), r = a.getBoundingClientRect();
    if (r.top < b.top + top) box.scrollTop -= b.top + top - r.top;
    else if (r.bottom > b.bottom - bottom) box.scrollTop += r.bottom - (b.bottom - bottom);
  }

  #filter(input, panel, signal) {
    let status = panel.querySelector(':scope > .cad-nav-empty');
    if (!status) {
      status = document.createElement('p');
      status.className = 'cad-nav-empty';
      status.setAttribute('role', 'status');
      input.after(status);
    }
    // Groups are the tree's <details> (with or without class="cad-nav-group"); pages are its links outside an outline.
    const groups = [...panel.querySelectorAll('details')].filter(d => !d.closest('.cad-nav-outline'));
    const pageItem = li => !li.closest('.cad-nav-outline');
    let saved = null;                                        // which groups were open before filtering began
    const apply = () => {
      const terms = input.value.toLowerCase().split(/\s+/).filter(Boolean);
      if (terms.length && !saved) saved = groups.map(g => g.open);
      let shown = 0;
      for (const li of [...panel.querySelectorAll('li')].filter(pageItem)) {
        const a = li.querySelector(':scope > a');
        li.hidden = !terms.every(t => (a?.textContent || li.textContent).toLowerCase().includes(t));
        if (!li.hidden) shown++;
      }
      groups.forEach((group, i) => {
        const any = [...group.querySelectorAll('li')].some(li => pageItem(li) && !li.hidden);
        group.hidden = !any;
        if (terms.length) { if (any) group.open = true; }
        else if (saved) group.open = saved[i];
      });
      if (!terms.length) saved = null;
      status.textContent = terms.length && !shown ? `No pages match “${input.value.trim()}”.` : '';
    };
    input.addEventListener('input', apply, { signal });
    input.addEventListener('keydown', e => { if (e.key === 'Escape' && input.value) { input.value = ''; apply(); } }, { signal });
  }
}

if (typeof customElements !== 'undefined' && !customElements.get('cad-nav')) customElements.define('cad-nav', CadNav);
