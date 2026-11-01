// Rendered diagrams (Mermaid through the shared kit) on any page that has them.
import('/kit/diagrams.js').then(m => m.observeDiagrams()).catch(() => {});
// One-click copy buttons on code blocks (the build wraps them in <cad-copy>).
import('/kit/copy.js').catch(() => {});
// Catalogue filter: text search plus type chips. Works without JS (everything is shown). Each term matches the start
// of a word, so "mit" finds the MIT licence but not "commit".
const q = document.getElementById('q');
if (q) {
  const chips = [...document.querySelectorAll('.chip')];
  const cards = [...document.querySelectorAll('.group .card')];
  const groups = [...document.querySelectorAll('.group')];
  const status = document.getElementById('filter-status');
  const params = new URLSearchParams(location.search);
  if (params.get('q')) q.value = params.get('q');
  const apply = () => {
    const terms = q.value.toLowerCase().split(/\s+/).filter(Boolean);
    const types = chips.filter(c => c.getAttribute('aria-pressed') === 'true').map(c => c.dataset.type);
    const res = terms.map(t => new RegExp('(?:^|[^\\p{L}\\p{N}])' + t.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'), 'u'));
    let shown = 0;
    for (const c of cards) {
      c.hidden = !(res.every(r => r.test(c.dataset.text)) && (!types.length || types.includes(c.dataset.type)));
      if (!c.hidden) shown++;
    }
    for (const g of groups) g.hidden = !g.querySelector('.card:not([hidden])');
    if (status) status.textContent = terms.length || types.length
      ? (shown ? `${shown} of ${cards.length} entries` : 'No entries match. Try fewer words or clear the type filters.') : '';
  };
  q.addEventListener('input', apply);
  chips.forEach(c => c.addEventListener('click', () => { c.setAttribute('aria-pressed', c.getAttribute('aria-pressed') === 'true' ? 'false' : 'true'); apply(); }));
  apply();
}
// Header gets its rule once the page scrolls.
const header = document.querySelector('.site-header');
if (header) { const f = () => header.classList.toggle('scrolled', scrollY > 8); addEventListener('scroll', f, { passive: true }); f(); }
// Interactive demos from the kit, only on pages that have one (the build links their stylesheets).
if (document.querySelector('cad-cantilever')) import('/kit/cantilever.js').catch(() => {});
