/** <cad-gallery>: tabs, facets, search and sorting over cards the page already wrote, with every view in the URL.
 *
 *   <link rel="stylesheet" href="/kit/gallery.css">       <!-- in <head>: the overview's first paint is final -->
 *   <script type="module" src="/kit/gallery.js"></script>
 *   <cad-gallery tab-param="kind" limit="6" item-noun="entry" items-noun="entries" data-overview>
 *     <input type="search" name="q" aria-label="Search" data-gallery-search>
 *     <nav aria-label="Kinds" data-gallery-tabs><a href="#all" data-tab="">All <span data-count>9</span></a>
 *       <a href="#tools" data-tab="tools">Tools <span data-count>4</span></a></nav>
 *     <a href="?area=gears" data-gallery-link data-facet="area" data-value="gears">Gears <span data-count>2</span></a>
 *     <form data-gallery-filters><label><input type="checkbox" name="status" value="adopted"> Adopted <span data-count></span></label></form>
 *     <select name="sort" data-gallery-sort><option value="featured">Featured</option><option value="stars" data-dir="desc">Stars</option></select>
 *     <p role="status" data-gallery-status></p>  <p data-gallery-empty hidden>Nothing matches.</p>
 *     <div data-gallery-results>
 *       <section id="tools" data-group="tools"><ul>
 *         <li data-item data-area="gears mechanical" data-status="adopted" data-text="…" data-sort-stars="120">…</li>
 *         <li data-item … data-over>…</li></ul>                         <!-- beyond `limit` in the overview -->
 *       <a href="?kind=tools" data-gallery-link data-gallery-more>See all</a></section>
 *     </div>
 *   </cad-gallery>
 *
 * Everything is plain HTML first: without script every card shows, grouped, and the tab links jump to their groups.
 * The script adds:
 * - tabs (a `data-tab` link per group, '' for all; arrow keys, Home and End), one tab parameter in the URL (`tab-param`);
 * - facets: checkboxes (several values, any of them matches) and `data-facet` links (one value), matched against the
 *   card's space-separated `data-<name>` tokens; facets combine with AND. Counts in `[data-count]` (inside the
 *   control) and `[data-count-of="name:value"]` show what each choice would leave, given the others;
 * - search over `data-text` (each word matches the start of a word), sorting by `data-sort-<option value>` (numbers or
 *   text, `data-dir="desc"` on the option; empty values last, ties in the page's order);
 * - the overview (no tab): the first `limit` cards of each group, a `[data-gallery-more]` link when there are more;
 *   the page writes `data-over` on the cards past the limit in its own order, so the first paint already matches;
 * - the URL: every choice is a parameter (?kind=tools&area=gears&sort=stars), history works, `[data-gallery-link]`
 *   links merge their parameters into the current view (and their href is kept as the view they lead to), a #hash
 *   inside a group opens that group's tab (and is written into the URL, so Back returns to it); a link that carries a
 *   view opens scrolled to `[data-gallery-results]`; `[data-gallery-when="area:gears"]` elements show only for that choice;
 * - `[data-gallery-chips]` (removable chips for the active choices), `[data-gallery-status]` (a live count),
 *   `[data-gallery-empty]`, `[data-gallery-empty-scope]` (instead, when a one-value facet alone leaves nothing: an area
 *   with nothing in it yet; `[data-gallery-scope-name]` inside it gets the choice's label), `[data-gallery-empty-kind]`
 *   (that facet has entries, but none under the chosen tab; `[data-gallery-kind-name]` gets the tab's name),
 *   `[data-gallery-clear]`, `[data-gallery-active]` (how many filters are on). While one of these boxes shows, the
 *   status line gets `data-gallery-boxed` (gallery.css hides it from view, not from screen readers);
 * - a sheet for small screens: `[data-gallery-sheet]` opens as a modal dialog from `[data-gallery-sheet-open]` (the
 *   page's CSS decides when that button shows) and closes with `[data-gallery-sheet-close]`, Escape or a click outside;
 * - covers that move: an <img data-anim="moving.svg"> swaps to it while its card is hovered or focused
 *   (`data-anim-view`: while it is in view), and back; never under prefers-reduced-motion.
 * Labels and chips are text, never markup. No dependencies.
 *
 * If this module does not start (blocked, or an error), the page should set `data-failed` on the element; gallery.css
 * then shows every card and hides `[data-gallery-js]` controls, as without script:
 *   import('/kit/gallery.js').catch(() => {}).finally(() => el.hasAttribute('data-ready') || el.setAttribute('data-failed', ''));
 */

const words = s => String(s || '').toLowerCase().split(/\s+/).filter(Boolean);
const escapeRe = s => s.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');

/** The view in a query string: { tab, q, sort, facets: { name: [values] } } for the given facet names. */
export function parseState(search, { tabParam = 'tab', facets = [] } = {}) {
  const p = new URLSearchParams(search);
  const state = { tab: p.get(tabParam) || '', q: p.get('q') || '', sort: p.get('sort') || '', facets: {} };
  for (const name of facets) {
    const values = (p.get(name) || '').split(',').map(v => v.trim()).filter(Boolean);
    if (values.length) state.facets[name] = [...new Set(values)];
  }
  return state;
}

/** The query string for a view, parameters in a fixed order: the tab, single-value facets, q, the others, sort. */
export function stateToSearch(state, { tabParam = 'tab', facets = [], single = [], defaultSort = '' } = {}) {
  const p = new URLSearchParams();
  if (state.tab) p.set(tabParam, state.tab);
  for (const name of facets.filter(n => single.includes(n))) if (state.facets[name]?.length) p.set(name, state.facets[name].join(','));
  if (state.q.trim()) p.set('q', state.q.trim());
  for (const name of facets.filter(n => !single.includes(n))) if (state.facets[name]?.length) p.set(name, state.facets[name].join(','));
  if (state.sort && state.sort !== defaultSort) p.set('sort', state.sort);
  const s = p.toString().replace(/%2C/g, ',');
  return s ? '?' + s : '';
}

/** Search terms as patterns: each word must start a word of the text, so "mit" finds MIT but not "commit". */
export const searchPatterns = q => words(q).map(t => new RegExp('(?:^|[^\\p{L}\\p{N}])' + escapeRe(t), 'u'));

/** Does an item ({ tab, text, facets: { name: Set } }) pass the view, ignoring one facet (`except`, or 'tab')? */
export function matches(item, state, patterns, except = null) {
  if (except !== 'tab' && state.tab && item.tab !== state.tab) return false;
  if (!patterns.every(r => r.test(item.text))) return false;
  for (const [name, values] of Object.entries(state.facets)) {
    if (name === except || !values.length) continue;
    if (!values.some(v => item.facets[name]?.has(v))) return false;
  }
  return true;
}

/** Compare two items by a sort key ('' keeps the page's order). Empty values go last; ties keep the page's order. */
export function compareBy(key, dir = 'asc') {
  return (a, b) => {
    if (!key) return a.index - b.index;
    const x = a.sort[key] ?? '', y = b.sort[key] ?? '';
    if (x === '' || y === '') return (x === '') - (y === '') || a.index - b.index;
    const nx = Number(x), ny = Number(y);
    const c = Number.isFinite(nx) && Number.isFinite(ny) ? nx - ny : String(x).localeCompare(String(y), 'en', { sensitivity: 'base' });
    return (dir === 'desc' ? -c : c) || a.index - b.index;
  };
}

// The element needs a browser; the functions above also run in Node (tests/webkit-gallery.test.mjs).
const Base = globalThis.HTMLElement ?? class {};

export class CadGallery extends Base {
  #stop;
  #state;
  #items = [];
  #timer = 0;

  connectedCallback() {
    if (this.#stop) return;
    this.#stop = new AbortController();
    this.removeAttribute('data-failed');                         // a new try (the element was moved)
    // Ready only once the first view is drawn. If setting up or the first render throws, the element goes back to the
    // markup and attributes the page wrote: every card in its order, the strip, plain jump links instead of tabs, no
    // chips, the counts and status as written (the no-script page). It marks itself failed, so gallery.css hides the
    // controls that need script, stops listening and rethrows. Buttons that <cad-copy> added are left out of the copy
    // kept here, so the restored <cad-copy> elements build theirs again.
    const attrs = [...this.attributes].map(a => [a.name, a.value]);
    const pristine = document.createDocumentFragment();
    for (const n of this.childNodes) pristine.append(n.cloneNode(true));
    for (const el of pristine.querySelectorAll('cad-copy > .cad-copy-btn, cad-copy > .cad-copy-status')) el.remove();
    try { this.#start(this.#stop.signal); } catch (err) {
      this.#stop.abort();
      clearTimeout(this.#timer);
      for (const a of [...this.attributes]) this.removeAttribute(a.name);
      for (const [name, value] of attrs) this.setAttribute(name, value);
      this.replaceChildren(...pristine.childNodes);
      this.setAttribute('data-failed', '');
      throw err;
    }
  }

  #start(signal) {
    const $ = s => this.querySelector(s), $$ = s => [...this.querySelectorAll(s)];
    this.tabParam = this.getAttribute('tab-param') || 'tab';
    this.limit = Math.max(1, parseInt(this.getAttribute('limit'), 10) || 6);
    this.nouns = [this.getAttribute('item-noun') || 'item', this.getAttribute('items-noun') || 'items'];
    this.tabs = $$('[data-gallery-tabs] [data-tab]');
    this.groups = $$('[data-group]');
    this.search = $('[data-gallery-search]');
    this.sortSelect = $('[data-gallery-sort]');
    this.boxes = $$('[data-gallery-filters] input[type=checkbox][name]');
    this.facetLinks = $$('[data-facet][data-value]');
    this.single = [...new Set(this.facetLinks.map(a => a.dataset.facet))];
    this.facetNames = [...this.single, ...new Set(this.boxes.map(b => b.name).filter(n => !this.single.includes(n)))];
    this.defaultSort = this.sortSelect?.options[0]?.value || '';
    // Each link is a choice applied to the current view; its href is rewritten to that view on every render, so the
    // choice as written (which may clear something: ?kind= is every kind) is kept in data-gallery-to.
    this.links = $$('a[data-gallery-link]');
    for (const a of this.links) a.dataset.galleryTo ??= a.getAttribute('href');
    this.results = $('[data-gallery-results]');
    this.#items = $$('[data-item]').map((el, index) => ({
      el, index, tab: el.closest('[data-group]')?.dataset.group || '', list: el.parentElement,
      text: (el.dataset.text || el.textContent).toLowerCase(),
      facets: Object.fromEntries(this.facetNames.map(n => [n, new Set(words(el.getAttribute(`data-${n}`)))])),
      sort: Object.fromEntries([...el.attributes].filter(a => a.name.startsWith('data-sort-')).map(a => [a.name.slice(10), a.value])),
    }));
    this.#setupTabs(signal);
    this.#state = this.#fromLocation();
    const target = this.#hashTarget();
    let fromHash = false;
    if (target && !new URLSearchParams(location.search).has(this.tabParam)) {
      const group = target.closest('[data-group]');
      if (group && (target.hasAttribute('data-item') || target.matches('[data-group], .anchor, [data-group] > [id]'))) { this.#state.tab = group.dataset.group; fromHash = true; }
    }
    this.#render();
    this.toggleAttribute('data-ready', true);
    // A tab chosen from an old #anchor goes into the address too, so Back returns to it.
    if (fromHash) history.replaceState(history.state, '', this.#url() + location.hash);
    // A link that carries a view (?kind=, ?area=, ?q=...) opens on its results, not on the page's introduction; not when
    // the browser is restoring a scroll position (Back, reload).
    const how = globalThis.performance?.getEntriesByType?.('navigation')[0]?.type;
    if (target && this.#state.tab) requestAnimationFrame(() => target.scrollIntoView({ block: 'start' }));
    else if (!target && this.#url() !== location.pathname && how !== 'back_forward' && how !== 'reload')
      requestAnimationFrame(() => this.results?.scrollIntoView({ block: 'start', behavior: 'instant' }));

    this.search?.addEventListener('input', () => { this.#state.q = this.search.value; this.#render(); this.#remember(true); }, { signal });
    this.search?.addEventListener('keydown', e => { if (e.key === 'Escape' && this.search.value) { this.search.value = ''; this.#state.q = ''; this.#render(); this.#remember(true); } }, { signal });
    for (const box of this.boxes) box.addEventListener('change', () => {
      const values = this.boxes.filter(b => b.name === box.name && b.checked).map(b => b.value);
      if (values.length) this.#state.facets[box.name] = values; else delete this.#state.facets[box.name];
      this.#render(); this.#remember(); this.#reveal();
    }, { signal });
    this.sortSelect?.addEventListener('change', () => { this.#state.sort = this.sortSelect.value; this.#render(); this.#remember(); }, { signal });
    this.addEventListener('click', e => {
      if (e.defaultPrevented || e.button || e.metaKey || e.ctrlKey || e.shiftKey || e.altKey) return;
      const link = e.target.closest?.('a[data-gallery-link], [data-gallery-tabs] [data-tab]');
      if (link && this.contains(link)) {
        e.preventDefault();
        if (link.matches('[data-tab]')) this.#state.tab = link.dataset.tab;
        else this.#merge(new URL(link.dataset.galleryTo ?? link.getAttribute('href'), location.href).searchParams);
        this.#render(); this.#remember(); this.#reveal();
        return;
      }
      if (e.target.closest?.('[data-gallery-clear]')) { this.#state = { tab: this.#state.tab, q: '', sort: this.#state.sort, facets: {} }; this.#render(); this.#remember(); this.#reveal(); }
    }, { signal });
    addEventListener('popstate', () => { this.#state = this.#fromLocation(); this.#render(); }, { signal });
    // "/" jumps to the search box, as on many sites; not while typing somewhere.
    addEventListener('keydown', e => {
      if (e.key !== '/' || e.metaKey || e.ctrlKey || e.altKey || !this.search) return;
      if (e.target.closest?.('input, textarea, select, [contenteditable]:not([contenteditable=false])')) return;
      e.preventDefault(); this.search.focus({ preventScroll: false }); this.search.select();
    }, { signal });
    this.#setupSheet(signal);
    this.#setupCovers(signal);
  }

  disconnectedCallback() {
    this.#stop?.abort();
    this.#stop = undefined;
    clearTimeout(this.#timer);
  }

  /** The current view (a copy). */
  get state() { return structuredClone(this.#state); }

  #fromLocation() {
    const s = parseState(location.search, { tabParam: this.tabParam, facets: this.facetNames });
    // Only values the page offers: a stale or mistyped link shows everything rather than nothing.
    if (s.tab && !this.tabs.some(t => t.dataset.tab === s.tab)) s.tab = '';
    for (const name of Object.keys(s.facets)) {
      const offered = new Set([...this.boxes.filter(b => b.name === name).map(b => b.value), ...this.facetLinks.filter(a => a.dataset.facet === name).map(a => a.dataset.value)]);
      s.facets[name] = s.facets[name].filter(v => offered.has(v));
      if (this.single.includes(name)) s.facets[name] = s.facets[name].slice(0, 1);
      if (!s.facets[name].length) delete s.facets[name];
    }
    if (s.sort && ![...(this.sortSelect?.options || [])].some(o => o.value === s.sort)) s.sort = '';
    return s;
  }

  #hashTarget() {
    if (!location.hash) return null;
    try { return document.getElementById(decodeURIComponent(location.hash.slice(1))); } catch { return null; }
  }

  /** Merge a link's parameters into the view: an empty value clears that choice. */
  #merge(params) {
    for (const [k, v] of params) {
      if (k === this.tabParam) this.#state.tab = v;
      else if (k === 'q') this.#state.q = v;
      else if (k === 'sort') this.#state.sort = v;
      else if (this.facetNames.includes(k)) { const vals = v.split(',').filter(Boolean); if (vals.length) this.#state.facets[k] = vals; else delete this.#state.facets[k]; }
    }
  }

  #url(state = this.#state) {
    return location.pathname + stateToSearch(state, { tabParam: this.tabParam, facets: this.facetNames, single: this.single, defaultSort: this.defaultSort });
  }

  /** Write the view to the address bar: typing replaces the entry (once it pauses), choices add one. */
  #remember(typing = false) {
    clearTimeout(this.#timer);
    const write = () => { const url = this.#url(); if (url !== location.pathname + location.search) history[typing ? 'replaceState' : 'pushState'](null, '', url); };
    if (typing) this.#timer = setTimeout(write, 350); else write();
  }

  /** After a choice, bring the results' top into view if the reader had scrolled past it (the list above them changed). */
  #reveal() {
    if (this.results && this.results.getBoundingClientRect().top < 0) this.results.scrollIntoView({ block: 'start' });
  }

  #setupTabs(signal) {
    const nav = this.querySelector('[data-gallery-tabs]');
    if (!nav || !this.tabs.length) return;
    nav.setAttribute('role', 'tablist');
    if (this.results && !this.results.id) this.results.id = `cad-gallery-results-${Math.random().toString(36).slice(2, 8)}`;
    this.tabs.forEach((t, i) => {
      t.setAttribute('role', 'tab');
      t.id ||= `${this.results?.id || 'cad-gallery'}-tab-${i}`;
      if (this.results) t.setAttribute('aria-controls', this.results.id);
    });
    this.results?.setAttribute('role', 'tabpanel');
    nav.addEventListener('keydown', e => {
      const i = this.tabs.indexOf(document.activeElement);
      if (i < 0) return;
      const next = { ArrowRight: i + 1, ArrowLeft: i - 1, Home: 0, End: this.tabs.length - 1 }[e.key];
      if (e.key === ' ') { e.preventDefault(); this.tabs[i].click(); return; }
      if (next === undefined) return;
      e.preventDefault();
      const t = this.tabs[(next + this.tabs.length) % this.tabs.length];
      t.focus(); t.click();
    }, { signal });
  }

  #render() {
    if (this.hasAttribute('data-failed')) return;                // the page is the no-script page now
    const s = this.#state, patterns = searchPatterns(s.q);
    const filtered = !!(patterns.length || Object.keys(s.facets).length);
    const overview = !s.tab;
    this.toggleAttribute('data-overview', overview);
    this.toggleAttribute('data-filtered', filtered);
    // Order, then visibility, then the overview's limit per group.
    const opt = this.sortSelect ? [...this.sortSelect.options].find(o => o.value === (s.sort || this.defaultSort)) : null;
    const key = s.sort && s.sort !== this.defaultSort ? s.sort : '';
    const byList = new Map();
    for (const it of this.#items) { if (!byList.has(it.list)) byList.set(it.list, []); byList.get(it.list).push(it); }
    for (const [list, its] of byList) {
      const sorted = [...its].sort(compareBy(key, opt?.dataset.dir));
      if (sorted.some((it, i) => list.children[i] !== it.el)) list.append(...sorted.map(it => it.el));
      byList.set(list, sorted);
    }
    let shown = 0;
    for (const it of this.#items) { it.visible = matches(it, s, patterns); if (it.visible) shown++; it.el.hidden = !it.visible; }
    for (const g of this.groups) {
      const its = [...g.querySelectorAll('[data-item]')].map(el => this.#items.find(it => it.el === el)).filter(Boolean);
      let n = 0;
      for (const it of its) { if (it.visible) n++; it.el.toggleAttribute('data-over', overview && it.visible && n > this.limit); }
      g.hidden = !n || (!!s.tab && g.dataset.group !== s.tab);
      g.toggleAttribute('data-more', overview && n > this.limit);
      for (const c of g.querySelectorAll('[data-group-count]')) c.textContent = n;
    }
    // Controls show the view.
    for (const t of this.tabs) {
      const on = t.dataset.tab === s.tab;
      t.setAttribute('aria-selected', String(on));
      t.tabIndex = on ? 0 : -1;
      if (on && this.results) this.results.setAttribute('aria-labelledby', t.id);
    }
    for (const a of this.facetLinks) {
      const on = (s.facets[a.dataset.facet]?.[0] || '') === a.dataset.value;
      if (on) a.setAttribute('aria-current', 'true'); else a.removeAttribute('aria-current');
      if (on) a.closest('details')?.setAttribute('open', '');
    }
    for (const b of this.boxes) b.checked = !!s.facets[b.name]?.includes(b.value);
    if (this.search && this.search.value !== s.q && document.activeElement !== this.search) this.search.value = s.q;
    if (this.sortSelect) this.sortSelect.value = s.sort || this.defaultSort;
    this.#counts(s, patterns);
    for (const el of this.querySelectorAll('[data-gallery-when]')) {
      const [name, value] = el.dataset.galleryWhen.split(':');
      el.hidden = !(name === this.tabParam ? s.tab === value : s.facets[name]?.includes(value));
    }
    // Nothing to show: either the words and filters exclude everything, or the chosen area (a single-value facet, with
    // no words or other filters) has nothing in it yet, or nothing of the chosen kind; each gets its own message box.
    const tab = this.tabs.find(t => t.dataset.tab === s.tab && s.tab);
    const tabName = tab ? tab.firstChild.textContent.trim().toLowerCase() : '';
    const scoped = !patterns.length && Object.keys(s.facets).length > 0 && Object.keys(s.facets).every(n => this.single.includes(n));
    const scopeName = scoped ? Object.entries(s.facets).map(([n, v]) => this.#labelOf(n, v[0])).join(', ') : '';
    const scopeEmpty = scoped && !shown && !this.#items.some(it => matches(it, s, patterns, 'tab'));
    const kindEmpty = scoped && !!s.tab && !shown && !scopeEmpty;
    const empty = this.querySelector('[data-gallery-empty]'), emptyScope = this.querySelector('[data-gallery-empty-scope]');
    const emptyKind = this.querySelector('[data-gallery-empty-kind]');
    if (emptyScope) emptyScope.hidden = !scopeEmpty;
    if (emptyKind) emptyKind.hidden = !kindEmpty;
    if (empty) empty.hidden = shown > 0 || (scopeEmpty && !!emptyScope) || (kindEmpty && !!emptyKind);
    for (const el of this.querySelectorAll('[data-gallery-scope-name]')) el.textContent = scopeName;
    for (const el of this.querySelectorAll('[data-gallery-kind-name]')) el.textContent = tabName;
    const status = this.querySelector('[data-gallery-status]');
    if (status) {
      // While a message box says it, the status line stays for screen readers but is hidden from view.
      status.toggleAttribute('data-gallery-boxed', [empty, emptyScope, emptyKind].some(b => b && !b.hidden));
      const what = tabName || this.nouns[shown === 1 ? 0 : 1];
      status.textContent = scopeEmpty ? `Nothing in ${scopeName} yet.`
        : !shown && scoped && s.tab ? `No ${tabName} in ${scopeName} yet.`
          : !shown ? `No ${this.nouns[1]} match. Try fewer words or clear the filters.`
            : filtered ? `${shown} of ${this.#items.filter(it => !s.tab || it.tab === s.tab).length} ${what}` : `${shown} ${what}`;
    }
    const active = Object.values(s.facets).reduce((n, v) => n + v.length, 0);
    for (const el of this.querySelectorAll('[data-gallery-active]')) el.textContent = active ? String(active) : '';
    for (const el of this.querySelectorAll('[data-gallery-sheet-close]')) el.dataset.shown = shown;
    this.#chips(s);
    for (const a of this.links) {                                // each link's href is the view it leads to
      const next = structuredClone(s);
      const before = this.#state; this.#state = next;
      this.#merge(new URL(a.dataset.galleryTo, location.href).searchParams);
      this.#state = before;
      a.setAttribute('href', this.#url(next));
    }
    this.dispatchEvent(new CustomEvent('cad-gallery-change', { bubbles: true, detail: { state: this.state, shown } }));
  }

  /** What each choice would leave, given every other choice. */
  #counts(s, patterns) {
    const set = (el, n) => {
      const c = el.matches('[data-count], [data-count-of]') ? el : el.querySelector('[data-count]') || el.closest('label')?.querySelector('[data-count]');
      if (c) c.textContent = n;
      (el.closest('label, summary') || el).toggleAttribute('data-empty', n === 0);
    };
    for (const t of this.tabs) set(t, this.#items.filter(it => (!t.dataset.tab || it.tab === t.dataset.tab) && matches(it, s, patterns, 'tab')).length);
    const facetCount = (name, value) => this.#items.filter(it => (!value || it.facets[name]?.has(value)) && matches(it, s, patterns, name)).length;
    for (const a of this.facetLinks) set(a, facetCount(a.dataset.facet, a.dataset.value));
    for (const b of this.boxes) set(b, facetCount(b.name, b.value));
    for (const el of this.querySelectorAll('[data-count-of]')) { const [n, v] = el.dataset.countOf.split(':'); set(el, facetCount(n, v)); }
  }

  /** A choice's label, as its control shows it (text only). */
  #labelOf(name, value) {
    const el = this.facetLinks.find(a => a.dataset.facet === name && a.dataset.value === value) || this.boxes.find(b => b.name === name && b.value === value)?.closest('label');
    return (el?.querySelector('.area-name, span:not([data-count]):not(.sr)') || el)?.textContent.trim() || value;
  }

  /** One removable chip per active choice; its label is the control's own text, never markup. */
  #chips(s) {
    const box = this.querySelector('[data-gallery-chips]');
    if (!box) return;
    const chips = [];
    if (s.q.trim()) chips.push([`“${s.q.trim()}”`, () => { this.#state.q = ''; if (this.search) this.search.value = ''; }]);
    for (const [name, values] of Object.entries(s.facets)) for (const v of values) {
      chips.push([this.#labelOf(name, v), () => {
        const rest = this.#state.facets[name].filter(x => x !== v);
        if (rest.length) this.#state.facets[name] = rest; else delete this.#state.facets[name];
      }]);
    }
    box.replaceChildren(...chips.map(([text, drop]) => {
      const b = document.createElement('button');
      b.type = 'button'; b.className = 'cad-gallery-chip';
      b.textContent = text;                                       // text, never markup
      b.setAttribute('aria-label', `Remove filter: ${text}`);
      b.addEventListener('click', () => { drop(); this.#render(); this.#remember(); (box.querySelector('button') || this.search)?.focus(); });
      return b;
    }));
    box.hidden = !chips.length;
  }

  #setupSheet(signal) {
    const sheet = this.querySelector('[data-gallery-sheet]'), openers = [...this.querySelectorAll('[data-gallery-sheet-open]')];
    if (!sheet || !openers.length) return;
    let inerted = [], opener = null;
    const close = () => {
      if (!sheet.hasAttribute('data-open')) return;
      sheet.removeAttribute('data-open');
      sheet.removeAttribute('role'); sheet.removeAttribute('aria-modal');
      for (const el of inerted) el.inert = false;
      inerted = [];
      document.documentElement.classList.remove('cad-gallery-sheet-open');
      openers.forEach(o => o.setAttribute('aria-expanded', 'false'));
      opener?.focus();
    };
    const open = o => {
      opener = o;
      sheet.setAttribute('data-open', '');
      sheet.setAttribute('role', 'dialog'); sheet.setAttribute('aria-modal', 'true');
      // Everything outside the sheet is inert while it is open (a modal), restored on close.
      for (let el = sheet; el && el !== document.body; el = el.parentElement)
        for (const sib of el.parentElement?.children || []) if (sib !== el && !sib.inert && sib.tagName !== 'SCRIPT') { sib.inert = true; inerted.push(sib); }
      document.documentElement.classList.add('cad-gallery-sheet-open');
      openers.forEach(b => b.setAttribute('aria-expanded', 'true'));
      (sheet.querySelector('[data-gallery-sheet-close]') || sheet).focus();
    };
    // On a small screen (the sheet's button shows) the tree starts folded but for the chosen branch; wide screens keep
    // the page's open tree as the map beside the results.
    if (openers.some(o => o.offsetParent)) for (const d of sheet.querySelectorAll('details[open]')) if (!d.querySelector('[aria-current="true"]')) d.open = false;
    for (const o of openers) o.addEventListener('click', () => (sheet.hasAttribute('data-open') ? close() : open(o)), { signal });
    sheet.addEventListener('click', e => { if (e.target.closest('[data-gallery-sheet-close]') || e.target === sheet) close(); }, { signal });
    addEventListener('keydown', e => { if (e.key === 'Escape' && sheet.hasAttribute('data-open')) { e.preventDefault(); close(); } }, { signal });
    // A sheet left open when the window grows past the narrow layout closes, so nothing stays inert.
    addEventListener('resize', () => { if (sheet.hasAttribute('data-open') && openers.every(o => !o.offsetParent)) close(); }, { passive: true, signal });
  }

  #setupCovers(signal) {
    const still = matchMedia('(prefers-reduced-motion: reduce)');
    const play = (img, on) => {
      if (!img?.dataset.anim) return;
      img.dataset.still ||= img.getAttribute('src');
      const want = on && !still.matches ? img.dataset.anim : img.dataset.still;
      if (img.getAttribute('src') !== want) img.setAttribute('src', want);
    };
    const coverOf = el => el?.closest?.('[data-item]')?.querySelector('img[data-anim]:not([data-anim-view])');
    this.addEventListener('pointerover', e => { const it = e.target.closest?.('[data-item]'); if (it && !it.contains(e.relatedTarget)) play(coverOf(it), true); }, { signal });
    this.addEventListener('pointerout', e => { const it = e.target.closest?.('[data-item]'); if (it && !it.contains(e.relatedTarget)) play(coverOf(it), false); }, { signal });
    this.addEventListener('focusin', e => play(coverOf(e.target), true), { signal });
    this.addEventListener('focusout', e => { const it = e.target.closest?.('[data-item]'); if (it && !it.contains(e.relatedTarget)) play(coverOf(it), false); }, { signal });
    const views = [...this.querySelectorAll('img[data-anim][data-anim-view]')];
    if (views.length && 'IntersectionObserver' in window) {
      const io = new IntersectionObserver(entries => { for (const e of entries) play(e.target, e.isIntersecting); }, { threshold: 0.6 });
      views.forEach(v => io.observe(v));
      signal.addEventListener('abort', () => io.disconnect());
    }
    still.addEventListener?.('change', () => { for (const img of this.querySelectorAll('img[data-anim]')) play(img, false); }, { signal });
  }
}

if (typeof customElements !== 'undefined' && !customElements.get('cad-gallery')) customElements.define('cad-gallery', CadGallery);
