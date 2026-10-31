/** <cad-nav>: a sticky page tree for long docs on wide screens, with the current page's outline and where you are.
 *
 *   <link rel="stylesheet" href="/kit/nav.css">          <!-- in <head>: styled and folded from the first paint -->
 *   <script type="module" src="/kit/nav.js"></script>
 *   <div class="layout">                                  <!-- your grid: nav column + content column -->
 *     <cad-nav for="article" role="navigation" aria-label="Pages and contents">
 *       <button type="button" class="cad-nav-toggle" aria-expanded="false">Pages and contents</button>
 *       <div class="cad-nav-panel">
 *         <input type="search" class="cad-nav-filter" placeholder="Filter pages" aria-label="Filter pages">
 *         <details class="cad-nav-group" open><summary>Docs</summary>
 *           <ul><li><a href="/docs/a">A</a></li><li><a href="/docs/b" aria-current="page">B</a>
 *             <ol class="cad-nav-outline" aria-label="On this page"><li class="h2"><a href="#x">X</a></li></ol></li></ul>
 *         </details>
 *       </div>
 *     </cad-nav>
 *     <article>…<h2 id="x">…</h2>…</article>
 *   </div>
 *
 * Give <cad-nav> the full height of its column (align-self: stretch in a grid), so its panel can stay in view.
 * Everything above is plain HTML: without script the groups open and close natively and the outline links work. Write
 * it out like this (a build step can) and nothing moves when the script arrives. A bare tree of groups also works:
 * the script then adds the toggle, the filter and the outline (of the `for` element's h2/h3 headings with ids) itself,
 * and sets the landmark role and label (`label`, default "Contents").
 * The script:
 * - marks the section being read in every outline (in the tree, and in any element matched by `rail`, e.g. a right-hand
 *   "On this page" column) with aria-current="location", as you scroll and when you follow an outline link;
 * - narrows the tree as you type in the filter (Esc clears; says so when nothing matches);
 * - opens and closes the tree with the toggle on narrow screens (nav.css decides when the toggle shows).
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

    let panel = this.querySelector(':scope > .cad-nav-panel');
    if (!panel) {
      panel = document.createElement('div');
      panel.className = 'cad-nav-panel';
      panel.append(...[...this.childNodes].filter(n => !n.classList?.contains('cad-nav-toggle')));
      this.append(panel);
    }
    panel.id ||= `cad-nav-${Math.random().toString(36).slice(2, 8)}`;
    let toggle = this.querySelector(':scope > .cad-nav-toggle');
    if (!toggle) {
      toggle = document.createElement('button');
      toggle.type = 'button';
      toggle.className = 'cad-nav-toggle';
      toggle.textContent = label;                            // the label is page text, never markup
      this.prepend(toggle);
    }
    toggle.setAttribute('aria-controls', panel.id);
    toggle.setAttribute('aria-expanded', String(this.hasAttribute('data-open')));
    toggle.addEventListener('click', () => {
      const open = !this.hasAttribute('data-open');
      this.toggleAttribute('data-open', open);
      toggle.setAttribute('aria-expanded', String(open));
    }, { signal });
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

  /** On a scrolling panel, bring the current page into view without hiding the filter (it is sticky) or, when it
   * fits, the name of the page's group; never moves the page itself. */
  #reveal(panel, filter) {
    const current = panel.querySelector('a[aria-current=page]');
    if (!current || panel.scrollHeight <= panel.clientHeight + 1) return;
    const top = el => el.getBoundingClientRect().top - panel.getBoundingClientRect().top + panel.scrollTop;
    const room = filter.offsetHeight + 16, visible = () => top(current) - panel.scrollTop + current.offsetHeight <= panel.clientHeight - 24;
    if (visible()) return;
    const group = current.closest('details');
    panel.scrollTop = Math.max(0, (group ? top(group) : top(current)) - room);
    if (!visible()) panel.scrollTop = Math.max(0, top(current) - panel.clientHeight / 3);
  }

  #outline(panel, signal) {
    const target = document.querySelector(this.getAttribute('for') || 'article');
    const current = panel.querySelector('a[aria-current=page]');
    if (current && !panel.querySelector('.cad-nav-outline')) {
      const items = outlineOf(target);
      if (items.length >= 2) current.after(outlineList(items));
    }
    current?.closest('details')?.setAttribute('open', '');
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
    let pinned = null, settled = true, settle = 0, queued = false, shown = null;
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
    const quiet = () => { clearTimeout(settle); settle = setTimeout(() => { settled = true; }, 150); };
    const pin = id => {
      if (!byId.has(id)) return;                              // only outline headings: not the skip link's target
      pinned = document.getElementById(id); settled = false; quiet(); schedule();
    };
    const release = () => { if (pinned) { pinned = null; schedule(); } };
    addEventListener('scroll', () => { if (pinned && settled) release(); else if (pinned) quiet(); schedule(); }, { passive: true, signal });
    addEventListener('resize', schedule, { passive: true, signal });
    for (const type of ['wheel', 'touchmove']) addEventListener(type, release, { passive: true, signal });
    addEventListener('keydown', e => { if (/^(?:Arrow(?:Up|Down)|Page(?:Up|Down)|Home|End| )$/.test(e.key)) release(); }, { signal });
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
