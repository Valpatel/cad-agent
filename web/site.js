// Rendered diagrams (Mermaid through the shared kit) on any page that has them.
import('/kit/diagrams.js').then(m => m.observeDiagrams()).catch(() => {});
// One-click copy buttons on code blocks (the build wraps them in <cad-copy>).
import('/kit/copy.js').catch(() => {});
// Page tree and outline beside long pages (the build writes the tree into <cad-nav>).
import('/kit/nav.js').catch(() => {});
// The catalogue's tabs, area tree, filters, sorting and URL state (the build writes every card into <cad-gallery>).
// If the gallery does not start (a blocked module, a script error), every card shows and the controls that need it hide.
const gallery = document.querySelector('cad-gallery');
if (gallery) import('/kit/gallery.js').catch(() => {}).finally(() => {
  if (!gallery.hasAttribute('data-ready')) gallery.setAttribute('data-failed', '');
});
// Header gets its rule once the page scrolls.
const header = document.querySelector('.site-header');
if (header) { const f = () => header.classList.toggle('scrolled', scrollY > 8); addEventListener('scroll', f, { passive: true }); f(); }
// Interactive demos from the kit, only on pages that have one (the build links their stylesheets).
if (document.querySelector('cad-cantilever')) import('/kit/cantilever.js').catch(() => {});
// A 3D model (the home page's Gyropup): the element waits for the page to load and come into view before it fetches
// three.js and the model, so the poster is all the first paint needs.
if (document.querySelector('cad-model')) import('/kit/model.js').catch(() => {});
