// Rendered diagrams (Mermaid through the shared kit) on any page that has them.
import('/kit/documents/diagrams.js').then(m => {
  m.observeDiagrams();
  // Diagrams drawn at build time come in both themes (site.css shows one); any drawn here are redrawn after the theme
  // button (web/theme.js) switches the page.
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
