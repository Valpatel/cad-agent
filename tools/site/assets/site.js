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
// Recordings (#748, #798): the page paints the still; after load (and, for a lazy card, once it nears the screen)
// data-motion-src swaps the animation in. Never under reduced motion or Save-Data (<cad-model> also asks first there).
for (const img of document.querySelectorAll('img[data-motion-src]')) {
  const swap = () => {
    if (matchMedia('(prefers-reduced-motion: reduce)').matches || navigator.connection?.saveData) return;
    const next = new Image();
    next.onload = () => { img.src = next.src; };
    next.src = img.dataset.motionSrc;
  };
  const near = () => new Promise(go => {
    if (img.loading !== 'lazy' || !window.IntersectionObserver) return go();
    const seen = new IntersectionObserver(e => { if (e.some(x => x.isIntersecting)) { seen.disconnect(); go(); } }, { rootMargin: '150px 0px' });
    seen.observe(img);
  });
  (document.readyState === 'complete' ? Promise.resolve() : new Promise(go => addEventListener('load', go, { once: true }))).then(near).then(swap);
}
// A link to a closed <details> (or to something inside one), such as /docs/agent-workflow#install-unix, opens it on
// arrival and when the address's #part changes, so the reader lands on the command, not on a closed toggle (#804).
// Without script the browser still scrolls to the block's summary; one click opens it.
// On Back, Forward or a reload the reader goes back where they left, not to the block (#807: 434 px off on a phone).
// Engines differ: Chromium restores the scroll before or after this script runs, WebKit lands on the # part again. So
// while such a page is read, its place is kept in its own history entry (history.state, which a fresh link to it does
// not have). Back there, the block opens without scroll anchoring and the page goes to that place, and keeps it
// through the engine's own restore until the reader scrolls, taps or types, the # part changes, or 1.5 s pass.
const saved = history.state?.cadReaderY;
let keeping = false;
const keepPlace = () => {
  if (keeping) return;
  keeping = true;
  let timer = 0;
  const save = () => { try { history.replaceState({ ...history.state, cadReaderY: scrollY }, ''); } catch { /* rate limit */ } };
  addEventListener('scroll', () => { clearTimeout(timer); timer = setTimeout(save, 200); }, { passive: true });
  addEventListener('pagehide', save);
  save();
};
const restorePlace = y => {
  const put = () => scrollTo({ top: y, behavior: 'instant' }), until = performance.now() + 1500, at = location.hash;
  let reader = false;
  for (const name of ['wheel', 'touchstart', 'pointerdown', 'keydown']) addEventListener(name, () => { reader = true; }, { once: true, passive: true, capture: true });
  // A new # part (a link, a script, the browser's Back to another # of this page) ends the hold, checked in the frame
  // itself: a hashchange listener can run after a frame has already put the page back. Another script's scroll cannot
  // be told from the engine's own restore, which is what the hold outlasts, so it still waits out the 1.5 s.
  const hold = () => { if (reader || location.hash !== at || performance.now() > until) return; if (Math.abs(scrollY - y) > 1) put(); requestAnimationFrame(hold); };
  put(); requestAnimationFrame(hold);
};
const openTarget = event => {
  let id = '';
  try { id = decodeURIComponent(location.hash.slice(1)); } catch { return; }
  const target = id ? document.getElementById(id) : null;
  if (!target?.closest('details')) return;
  keepPlace();
  const restore = !event && typeof saved === 'number', root = document.documentElement, anchor = root.style.overflowAnchor;
  if (restore) root.style.overflowAnchor = 'none';
  let opened = false;
  for (let d = target.closest('details'); d; d = d.parentElement?.closest('details')) if (!d.open) { d.open = true; opened = true; }
  if (restore) { root.getBoundingClientRect(); root.style.overflowAnchor = anchor; restorePlace(saved); return; }
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
