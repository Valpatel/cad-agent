/** <cad-nav>: a sticky page tree for long docs on wide screens, with the current page's outline and where you are.
 *
 *   <script type="module" src="/kit/nav.js"></script>
 *   <div class="layout">                      <!-- your grid: nav column + content column -->
 *     <cad-nav for="article" label="Contents">
 *       <details class="cad-nav-group" open><summary>Docs</summary>
 *         <ul><li><a href="/docs/a">A</a></li><li><a href="/docs/b" aria-current="page">B</a></li></ul></details>
 *       <details class="cad-nav-group"><summary>Lessons</summary><ul>…</ul></details>
 *     </cad-nav>
 *     <article>…<h2 id="x">…</h2>…</article>
 *   </div>
 *
 * The tree is plain HTML (it works without script: groups open and close natively). The script adds:
 * - under the current page (`aria-current="page"`), an outline of the `for` element's h2/h3 headings (with ids), and
 *   marks the section being read as you scroll;
 * - a filter box that narrows the tree as you type (Esc clears);
 * - on narrow screens (below `wide`, default 1100px) one "Contents" toggle instead of a column.
 * Styles come in through a constructable stylesheet (no inline <style>, so strict CSPs allow it); restyle with the
 * --cad-nav-* custom properties or plain CSS. No dependencies.
 */
const CSS = `cad-nav{display:block;font:var(--cad-nav-font,13px/1.5 system-ui,sans-serif);color:var(--cad-nav-fg,#173d3c)}
cad-nav .cad-nav-panel{position:sticky;top:var(--cad-nav-top,96px);max-height:calc(100vh - var(--cad-nav-top,96px) - 16px);overflow:auto;
  padding:4px 10px 24px 2px;overscroll-behavior:contain;scrollbar-width:thin}
cad-nav .cad-nav-toggle{display:none}
cad-nav .cad-nav-filter{width:100%;box-sizing:border-box;margin:0 0 12px;padding:8px 12px;border-radius:999px;font:inherit;
  border:1px solid var(--cad-nav-line,#c9d8ca);background:var(--cad-nav-bg,#fff);color:inherit}
cad-nav .cad-nav-filter:focus-visible{outline:2px solid var(--cad-nav-accent,#bd3a12);outline-offset:1px}
cad-nav details{margin:0 0 6px}
cad-nav summary{cursor:pointer;font-weight:700;font-size:.78em;letter-spacing:.08em;text-transform:uppercase;padding:6px 4px;
  color:var(--cad-nav-muted,#526863);list-style-position:inside}
cad-nav ul,cad-nav ol{list-style:none;margin:0;padding:0}
cad-nav li a{display:block;padding:4px 8px 4px 12px;border-left:2px solid transparent;color:inherit;text-decoration:none;
  border-radius:0 8px 8px 0;overflow-wrap:anywhere}
cad-nav li a:hover{background:var(--cad-nav-hover,#eef1e4)}
cad-nav li a:focus-visible{outline:2px solid var(--cad-nav-accent,#bd3a12);outline-offset:-2px}
cad-nav a[aria-current=page]{font-weight:700;border-left-color:var(--cad-nav-accent,#bd3a12);background:var(--cad-nav-current,#f0f5e7)}
cad-nav .cad-nav-outline{margin:2px 0 8px 14px;border-left:1px solid var(--cad-nav-line,#c9d8ca)}
cad-nav .cad-nav-outline a{font-size:.92em;padding:3px 8px;color:var(--cad-nav-muted,#526863)}
cad-nav .cad-nav-outline .h3 a{padding-left:20px;font-size:.88em}
cad-nav .cad-nav-outline a[data-active]{color:var(--cad-nav-fg,#173d3c);font-weight:650;border-left-color:var(--cad-nav-active,#2e9d5b)}
cad-nav [hidden]{display:none!important}
cad-nav[data-narrow] .cad-nav-panel{position:static;max-height:none;overflow:visible;padding:0}
cad-nav[data-narrow] .cad-nav-toggle{display:flex;align-items:center;justify-content:space-between;width:100%;padding:10px 16px;
  border-radius:12px;border:1px solid var(--cad-nav-line,#c9d8ca);background:var(--cad-nav-current,#f0f5e7);color:inherit;
  font:inherit;font-weight:700;cursor:pointer;min-height:44px}
cad-nav[data-narrow]:not([data-open]) .cad-nav-panel{display:none}
cad-nav[data-narrow][data-open] .cad-nav-panel{margin-top:10px}
@media(prefers-reduced-motion:reduce){cad-nav *{scroll-behavior:auto!important}}`;

let styled = false;
function addStyles() {
  if (styled || typeof document === 'undefined') return;
  styled = true;
  try {
    const sheet = new CSSStyleSheet();
    sheet.replaceSync(CSS);
    document.adoptedStyleSheets = [...document.adoptedStyleSheets, sheet];
  } catch {
    const style = document.createElement('style');
    style.textContent = CSS;
    document.head.append(style);
  }
}

/** The outline entries for a container: h2 and h3 headings that have ids. */
export function outlineOf(root) {
  return [...(root?.querySelectorAll('h2[id], h3[id]') || [])]
    .map(h => ({ id: h.id, level: h.tagName === 'H2' ? 2 : 3, text: h.textContent.trim() }))
    .filter(h => h.text);
}

export class CadNav extends HTMLElement {
  connectedCallback() {
    if (this.dataset.ready) return;
    this.dataset.ready = '1';
    addStyles();
    const panel = document.createElement('div');
    panel.className = 'cad-nav-panel';
    panel.id = `cad-nav-${Math.random().toString(36).slice(2, 8)}`;
    panel.append(...this.childNodes);
    const toggle = document.createElement('button');
    toggle.type = 'button';
    toggle.className = 'cad-nav-toggle';
    toggle.setAttribute('aria-controls', panel.id);
    toggle.setAttribute('aria-expanded', 'false');
    toggle.innerHTML = `<span>${this.getAttribute('label') || 'Contents'}</span><span aria-hidden="true">▾</span>`;
    toggle.addEventListener('click', () => {
      const open = !this.hasAttribute('data-open');
      this.toggleAttribute('data-open', open);
      toggle.setAttribute('aria-expanded', String(open));
    });
    const filter = document.createElement('input');
    filter.type = 'search';
    filter.className = 'cad-nav-filter';
    filter.placeholder = 'Filter pages';
    filter.setAttribute('aria-label', 'Filter pages');
    panel.prepend(filter);
    this.append(toggle, panel);
    this.#outline(panel);
    this.#filter(filter, panel);
    const wide = window.matchMedia(`(min-width: ${this.getAttribute('wide') || '1100px'})`);
    const fit = () => this.toggleAttribute('data-narrow', !wide.matches);
    wide.addEventListener('change', fit);
    fit();
    // Show the current page in the column without moving the page itself.
    const current = panel.querySelector('a[aria-current=page]');
    if (current && wide.matches) panel.scrollTop = Math.max(0, current.offsetTop - panel.clientHeight / 3);
  }

  #outline(panel) {
    const target = document.querySelector(this.getAttribute('for') || 'article');
    const current = panel.querySelector('a[aria-current=page]');
    const items = outlineOf(target);
    if (!current || items.length < 2) return;
    current.closest('details')?.setAttribute('open', '');
    const list = document.createElement('ol');
    list.className = 'cad-nav-outline';
    list.setAttribute('aria-label', 'On this page');
    for (const h of items) {
      const li = document.createElement('li');
      li.className = `h${h.level}`;
      const a = document.createElement('a');
      a.href = `#${encodeURIComponent(h.id)}`;
      a.textContent = h.text;
      li.append(a);
      list.append(li);
    }
    current.after(list);
    const links = new Map([...list.querySelectorAll('a')].map(a => [decodeURIComponent(a.hash.slice(1)), a]));
    const visible = new Set();
    const mark = () => {
      const ids = [...links.keys()];
      const first = ids.find(id => visible.has(id)) ?? lastAbove(ids);
      for (const [id, a] of links) a.toggleAttribute('data-active', id === first);
    };
    const lastAbove = ids => ids.filter(id => document.getElementById(id)?.getBoundingClientRect().top < 120).at(-1);
    const io = new IntersectionObserver(entries => {
      for (const e of entries) e.isIntersecting ? visible.add(e.target.id) : visible.delete(e.target.id);
      mark();
    }, { rootMargin: '-80px 0px -55% 0px' });
    for (const id of links.keys()) { const el = document.getElementById(id); if (el) io.observe(el); }
    mark();
  }

  #filter(input, panel) {
    const apply = () => {
      const terms = input.value.toLowerCase().split(/\s+/).filter(Boolean);
      for (const li of panel.querySelectorAll('.cad-nav-group li')) {
        if (li.closest('.cad-nav-outline')) continue;
        li.hidden = !terms.every(t => li.textContent.toLowerCase().includes(t));
      }
      for (const group of panel.querySelectorAll('.cad-nav-group')) {
        const any = group.querySelector(':scope > ul > li:not([hidden])');
        group.hidden = !any;
        if (terms.length && any) group.setAttribute('open', '');
      }
    };
    input.addEventListener('input', apply);
    input.addEventListener('keydown', e => { if (e.key === 'Escape') { input.value = ''; apply(); } });
  }
}

if (typeof customElements !== 'undefined' && !customElements.get('cad-nav')) customElements.define('cad-nav', CadNav);
