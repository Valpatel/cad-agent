// Application theme: the reader's system setting (prefers-color-scheme in ui/theme.css) until they press the page's
// theme button; that choice is kept in this browser's localStorage only, and nothing is sent anywhere. A choice that
// matches the system again is forgotten, so the page follows the system from then on.
// A classic script in <head>, before the stylesheets, so the first paint already has the chosen theme (the site allows
// no inline script). Hosts can refresh their own renderers after the cad-themechange event.
// No website resources, network requests or domain models are required.
(() => {
  const KEY = 'cad-theme', root = document.documentElement, system = matchMedia('(prefers-color-scheme: dark)');
  const load = () => { try { return localStorage.getItem(KEY); } catch { return null; } };
  const save = value => { try { value ? localStorage.setItem(KEY, value) : localStorage.removeItem(KEY); } catch { /* private mode: this page only */ } };
  const apply = value => { if (value === 'light' || value === 'dark') root.dataset.theme = value; else delete root.dataset.theme; };
  apply(load());
  const current = () => root.dataset.theme || (system.matches ? 'dark' : 'light');
  let effective = current(), started = false;
  const show = () => {
    for (const button of document.querySelectorAll('.theme-toggle')) {
      if (started) button.hidden = false;
      button.setAttribute('aria-pressed', String(current() === 'dark'));
    }
  };
  const tell = () => {
    document.dispatchEvent(new CustomEvent('cad-themechange', { detail: { theme: current() } }));
  };
  const changed = () => {
    const next = current(); show();
    if (next !== effective) { effective = next; tell(); }
  };
  const press = () => {
    const next = current() === 'dark' ? 'light' : 'dark';
    if (next === (system.matches ? 'dark' : 'light')) { delete root.dataset.theme; save(null); }
    else { root.dataset.theme = next; save(next); }
    changed();
  };
  system.addEventListener?.('change', changed);
  // a choice made in another tab, or kept while this page sat in the back/forward cache
  const reload = () => { apply(load()); changed(); };
  addEventListener('storage', e => { if (e.key === KEY || e.key === null) reload(); });
  addEventListener('pageshow', e => { if (e.persisted) reload(); });
  const start = () => { started = true; show(); for (const button of document.querySelectorAll('.theme-toggle')) button.addEventListener('click', press); };
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', start); else start();
})();
