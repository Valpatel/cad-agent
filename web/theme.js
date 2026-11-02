// The site's theme: the reader's system setting (prefers-color-scheme in web/site.css) until they press the header's
// theme button; that choice is kept in this browser's localStorage only, and nothing is sent anywhere. A choice that
// matches the system again is forgotten, so the page follows the system from then on.
// A classic script in <head>, before the stylesheets, so the first paint already has the chosen theme (the site allows
// no inline script). The kit's demos and diagrams follow the page's color-scheme; after a press they are told to look
// again (a press changes no media query they listen to).
(() => {
  const KEY = 'cad-theme', root = document.documentElement, system = matchMedia('(prefers-color-scheme: dark)');
  const load = () => { try { return localStorage.getItem(KEY); } catch { return null; } };
  const save = value => { try { value ? localStorage.setItem(KEY, value) : localStorage.removeItem(KEY); } catch { /* private mode: this page only */ } };
  const chosen = load();
  if (chosen === 'light' || chosen === 'dark') root.dataset.theme = chosen;
  const current = () => root.dataset.theme || (system.matches ? 'dark' : 'light');
  const show = () => {
    for (const button of document.querySelectorAll('.theme-toggle')) {
      button.hidden = false;
      button.setAttribute('aria-pressed', String(current() === 'dark'));
    }
  };
  const tell = () => {
    for (const el of document.querySelectorAll('cad-fourbar,cad-fan-curve,cad-torsion-snap,cad-printed-boss')) el.applyTheme?.();
    document.dispatchEvent(new CustomEvent('cad-themechange', { detail: { theme: current() } }));
  };
  const press = () => {
    const next = current() === 'dark' ? 'light' : 'dark';
    if (next === (system.matches ? 'dark' : 'light')) { delete root.dataset.theme; save(null); }
    else { root.dataset.theme = next; save(next); }
    show(); tell();
  };
  system.addEventListener?.('change', show);
  const start = () => { show(); for (const button of document.querySelectorAll('.theme-toggle')) button.addEventListener('click', press); };
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', start); else start();
})();
