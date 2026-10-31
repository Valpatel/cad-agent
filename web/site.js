// Catalogue filter: text search plus type chips. Works without JS (everything is shown).
const q = document.getElementById('q');
if (q) {
  const chips = [...document.querySelectorAll('.chip')];
  const cards = [...document.querySelectorAll('.group .card')];
  const groups = [...document.querySelectorAll('.group')];
  const params = new URLSearchParams(location.search);
  if (params.get('q')) q.value = params.get('q');
  const apply = () => {
    const terms = q.value.toLowerCase().split(/\s+/).filter(Boolean);
    const types = chips.filter(c => c.getAttribute('aria-pressed') === 'true').map(c => c.dataset.type);
    for (const c of cards) c.hidden = !(terms.every(t => c.dataset.text.includes(t)) && (!types.length || types.includes(c.dataset.type)));
    for (const g of groups) g.hidden = !g.querySelector('.card:not([hidden])');
  };
  q.addEventListener('input', apply);
  chips.forEach(c => c.addEventListener('click', () => { c.setAttribute('aria-pressed', c.getAttribute('aria-pressed') === 'true' ? 'false' : 'true'); apply(); }));
  apply();
}
// Header gets its rule once the page scrolls.
const header = document.querySelector('.site-header');
if (header) { const f = () => header.classList.toggle('scrolled', scrollY > 8); addEventListener('scroll', f, { passive: true }); f(); }
