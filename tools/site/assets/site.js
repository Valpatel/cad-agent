// The website owns its calculator refreshes; the shared theme controller only emits a preference event.
document.addEventListener('cad-themechange', () => {
  for (const element of document.querySelectorAll('cad-fourbar,cad-fan-curve,cad-torsion-snap,cad-printed-boss')) element.applyTheme?.();
});
// Rendered diagrams (Mermaid through the shared kit) on any page that has them.
import('/kit/documents/diagrams.js').then(m => {
  m.observeDiagrams();
  // Diagrams drawn at build time come in both themes (site.css shows one); any drawn here are redrawn after the theme
  // button (kit/ui/theme.js) switches the page.
  document.addEventListener('cad-themechange', () => m.refreshDiagramThemes());
}).catch(() => {});
// One-click copy buttons on code blocks (the build wraps them in <cad-copy>).
import('/kit/documents/copy.js').catch(() => {});
// Page tree and outline beside long pages (the build writes the tree into <cad-nav>).
import('/kit/documents/nav.js').catch(() => {});
// The catalogue's tabs, area tree, filters, sorting and URL state (the build writes every card into <cad-gallery>).
// If the gallery does not start (a blocked module, a script error), every card shows and the controls that need it hide.
const gallery = document.querySelector('cad-gallery');
if (gallery) import('/kit/ui/gallery.js').catch(() => {}).finally(() => {
  if (!gallery.hasAttribute('data-ready')) gallery.setAttribute('data-failed', '');
});
// The reference pages' filters (/references/<area>): the table shows every row without it.
if (document.querySelector('.refs-filters')) import('/web/references.js').catch(() => {});
// Header gets its rule once the page scrolls.
const header = document.querySelector('.site-header');
if (header) { const f = () => header.classList.toggle('scrolled', scrollY > 8); addEventListener('scroll', f, { passive: true }); f(); }
// Interactive demos from the kit, only on pages that have one (the build links their stylesheets).
if (document.querySelector('cad-cantilever')) import('/kit/calculators/cantilever.js').catch(() => {});
if (document.querySelector('cad-fourbar')) import('/kit/calculators/fourbar.js').catch(() => {});
if (document.querySelector('cad-fan-curve')) import('/kit/calculators/fan-curve.js').catch(() => {});
if (document.querySelector('cad-torsion-snap')) import('/kit/calculators/torsion-snap.js').catch(() => {});
if (document.querySelector('cad-printed-boss')) import('/kit/calculators/printed-boss.js').catch(() => {});
// A 3D model (the home page's Gyropup): the element waits for the page to load and come into view before it fetches
// three.js and the model, so the poster is all the first paint needs.
if (document.querySelector('cad-model')) import('/kit/model/model.js').catch(() => {});
// Rich entry details are an enhancement of compact Explore results; the existing JSON feed is authoritative.
if (document.querySelector('details[data-catalogue-id]')) import('/web/discovery.js').catch(() => {});
// The Toolkit keeps all cards and SVG links usable without JavaScript; this adds search and state controls.
if (document.querySelector('[data-scada-browser]')) import('/web/toolkit.js').catch(() => {});
// The home hero's recording (#748): the page loads and paints its 9 KB still; once the page has loaded, the animation
// (data-motion-src) replaces it when it has arrived. Never under reduced motion, where the picture's still is kept, and
// never with Save-Data on, where <cad-model> on the same page also asks first.
for (const img of document.querySelectorAll('img[data-motion-src]')) {
  const swap = () => {
    if (matchMedia('(prefers-reduced-motion: reduce)').matches || navigator.connection?.saveData) return;
    const next = new Image();
    next.onload = () => { img.src = next.src; };
    next.src = img.dataset.motionSrc;
  };
  if (document.readyState === 'complete') swap(); else addEventListener('load', swap, { once: true });
}
// A link to a closed <details> (or to something inside one), such as /docs/agent-workflow#install-unix, opens it on
// arrival and when the address's #part changes, so the reader lands on the command, not on a closed toggle (#804).
// Without script the browser still scrolls to the block's summary; one click opens it.
const openTarget = () => {
  let id = '';
  try { id = decodeURIComponent(location.hash.slice(1)); } catch { return; }
  const target = id && document.getElementById(id);
  if (!target) return;
  let opened = false;
  for (let d = target.closest('details'); d; d = d.parentElement?.closest('details')) if (!d.open) { d.open = true; opened = true; }
  // At once, as the browser lands on any other # address: the page's smooth scrolling would leave the reader mid-way.
  if (opened) target.scrollIntoView({ block: 'start', behavior: 'instant' });
};
openTarget();
addEventListener('hashchange', openTarget);
// The 404 page's feedback link names the address the reader asked for, not a page of its own (#804).
for (const a of document.querySelectorAll('a[data-feedback-here]')) {
  const url = new URL(a.href);
  url.searchParams.set('page', location.origin + location.pathname + location.search);
  a.href = url.href;
}
