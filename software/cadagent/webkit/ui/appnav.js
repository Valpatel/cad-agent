// The app-wide top bar for a project's own pages: reads site/nav.json (written by `cad-agent site`) and renders the
// same tabs as the project site, so every page of the app shares one navigation.
//   mountAppNav({ root: '../', current: 'simulate' })   // root: path from this page to the project root
// The web kit's standalone viewers (model/viewer.html, files/file-viewer.html) mount it only when their address
// carries `nav=1`, so a host without site/nav.json gets no request and no console line from them; a host that has one
// links its viewers with nav=1. (A host that opts in without the file gets one 404 for it, and no bar.)
// `cad-agent site --serve` adds `mountAppNav({ root: '/', current, injected: true })` to every project page it sends
// whose markup has no bar (the kit's viewers included), and its nav.json says `"live": true`, which turns on live
// reload (below); a static copy of the site does not. An injected
// bar pads the body by its height unless the page made room itself on body.has-appnav (pages laid out for the bar, like
// the web kit's, use body.has-appnav and --appnav-h), stays off for an address with nav=0, and steps aside for a bar
// the page mounts itself, whichever comes first, even from an older copy of this file.
// On a page with the web kit's theme (ui/theme.css: all of --glass, --ink, --muted, --accent, --line-2 and --soft-2
// set) the bar takes those colours, so it follows the page's light or dark theme and its button (#807); on any other
// page it keeps the dark HUD colours it always had.
const THEME_TOKENS = ['--glass', '--ink', '--muted', '--accent', '--line-2', '--soft-2'];
const NAV_CSS = `
.appnav{position:fixed;top:0;left:0;right:0;z-index:50;display:flex;align-items:center;gap:4px;padding:0 16px;height:46px;
background:rgba(6,6,9,.94);backdrop-filter:blur(10px);border-bottom:1px solid #2a303c;overflow-x:auto;font-family:'Inter',system-ui,sans-serif}
.appnav .brand{font-weight:700;margin-right:12px;white-space:nowrap;display:flex;align-items:center;gap:8px;color:#e8edf5;text-decoration:none;font-size:15px}
.appnav .brand i{width:9px;height:9px;background:#00f0ff;transform:rotate(45deg);box-shadow:0 0 10px rgba(0,240,255,.3)}
.appnav a.tab{font:500 12px 'JetBrains Mono',ui-monospace,monospace;letter-spacing:.08em;text-transform:uppercase;color:#8892a4;
text-decoration:none;padding:6px 10px;border-radius:6px;white-space:nowrap}
.appnav a.tab:hover{color:#00f0ff}.appnav a.tab.on{color:#00f0ff;background:rgba(0,240,255,.06);box-shadow:inset 0 -2px 0 #00f0ff}
.appnav.themed{background:var(--glass);border-bottom-color:var(--line-2)}.appnav.themed .brand{color:var(--ink)}
.appnav.themed .brand i{background:var(--accent)}.appnav.themed a.tab{color:var(--muted)}
.appnav.themed a.tab:hover,.appnav.themed a.tab.on{color:var(--accent)}
.appnav.themed a.tab.on{background:var(--soft-2);box-shadow:inset 0 -2px 0 var(--accent)}
body.has-appnav{--appnav-h:46px}
@media(max-width:600px){.appnav{padding:0 8px;gap:2px}.appnav .brand{margin-right:4px;font-size:14px}
.appnav .brand,.appnav a.tab{min-height:44px;min-width:44px;box-sizing:border-box;display:inline-flex;align-items:center}
.appnav a.tab{padding:0 7px;font-size:11px;letter-spacing:.04em}}`;
const NAV_H = 46;

// root must be a plain relative path (../../, ./, designer/) or the site root "/" (the server-injected bar):
// it goes into links and the nav.json URL
const ROOT_OK = /^\/?(?:\.\.?\/)*(?:[A-Za-z0-9_-][A-Za-z0-9._-]*\/)*$/;

export async function mountAppNav({ root = '../', current = '', injected = false } = {}) {
  if (typeof root !== 'string' || !ROOT_OK.test(root)) return null;
  // nav=0 in the address turns the bar off, for the server's injected call too (`cad-agent site --serve` also skips it).
  if (injected && new URLSearchParams(location.search).get('nav') === '0') return null;
  // Embedded reviews inherit the host page's navigation; keep the model area clear.
  if (window.top !== window.self) return null;
  let cfg;
  try { cfg = await (await fetch(`${root}site/nav.json`)).json(); } catch { return null; }
  if (!cfg?.nav?.length) return null;
  const own = document.querySelector('nav.appnav:not([data-injected])');
  if (own) return injected ? null : own;                       // one bar per page; the page's own wins
  if (injected && document.querySelector('nav.appnav[data-injected]')) return null;
  document.querySelectorAll('nav.appnav[data-injected]').forEach((n) => n.unmount?.());
  if (!document.getElementById('cadagent-appnav-css')) {
    const style = document.createElement('style');
    style.id = 'cadagent-appnav-css';
    style.textContent = NAV_CSS;
    document.head.appendChild(style);
  }
  const nav = document.createElement('nav');
  nav.className = 'appnav';
  const tokens = getComputedStyle(document.documentElement);
  if (THEME_TOKENS.every((t) => tokens.getPropertyValue(t).trim())) nav.classList.add('themed');
  const esc = (s) => String(s ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  // nav.json links: relative to the project root, or absolute http(s)/mailto; anything else (javascript:, data:) is dropped
  const href = (h) => {
    h = String(h ?? '');
    if (/^[a-z][a-z0-9+.-]*:/i.test(h)) return /^(https?:|mailto:)/i.test(h) ? h : null;
    return h.startsWith('//') ? null : root + h;
  };
  nav.innerHTML = `<a class="brand" href="${esc(root)}site/"><i></i>${esc(cfg.title)}</a>`
    + cfg.nav.filter((n) => href(n?.href) !== null).map((n) => `<a class="tab${(n.id ?? n.href) === current ? ' on' : ''}" `
      + `href="${esc(href(n.href))}">${esc(n.title)}</a>`).join('');
  const body = document.body;
  const hadClass = body.classList.contains('has-appnav');
  // Where the page's first boxes sit, and its padding: a page laid out for the bar moves them itself on has-appnav.
  const layout = () => [getComputedStyle(body).paddingTop, ...[...body.children].filter((e) => e !== nav && e.tagName !== 'SCRIPT')
    .slice(0, 8).map((e) => Math.round(e.getBoundingClientRect().top))].join();
  // The bar goes in first, so the class is the only change between the two measurements: a page whose first child's
  // margin changes when it stops being first (body>:first-child{margin-top:0}) must not read as having made room.
  body.prepend(nav);
  const pad = parseFloat(getComputedStyle(body).paddingTop) || 0, unmoved = layout();
  body.classList.add('has-appnav');
  if (injected) {
    nav.dataset.injected = '1';
    const before = body.style.paddingTop;
    // A fixed bar over a page that was not laid out for one: pad the body by its height. A page that is (the kit's
    // viewers: body.has-appnav and --appnav-h) has already made room, and padding it too left a 46 px gap (#807).
    if (!hadClass && layout() === unmoved) body.style.paddingTop = `${pad + NAV_H}px`;
    const watch = new MutationObserver(() => { if (document.querySelector('nav.appnav:not([data-injected])')) nav.unmount(); });
    watch.observe(body, { childList: true, subtree: true });
    nav.unmount = () => {
      watch.disconnect();
      nav.remove();
      body.style.paddingTop = before;
      if (!hadClass && !document.querySelector('nav.appnav')) body.classList.remove('has-appnav');
    };
  }
  // Only the server that answers the change poll (`cad-agent site --serve`) offers it: any other local server would
  // answer each poll with a 404 (#804: the kit's viewers on a static preview of a site).
  if (cfg.live === true) liveReload();
  return nav;
}

/**
 * Live reload for local work: when the page is served by `cad-agent site --serve` on this machine, it polls the
 * server for the newest change under the project and reloads once changes have settled (2 s quiet), at most every
 * 8 s. `?live=0` turns it off for a page.
 */
export function liveReload({ every = 2000, settle = 2000, minGap = 8000 } = {}) {
  if (!/^(127\.0\.0\.1|localhost|\[::1\])$/.test(location.hostname) || new URLSearchParams(location.search).get('live') === '0') return;
  if (window.__cadagentLive) return;
  window.__cadagentLive = true;
  let first = null, seen = null, changedAt = 0;
  const loadedAt = Date.now();
  const tick = async () => {
    try {
      const r = await fetch('/_cadagent/changes', { cache: 'no-store' });
      if (!r.ok) return;                                   // an older server: no live reload
      const { stamp } = await r.json();
      if (first === null) { first = seen = stamp; }
      else if (stamp !== seen) { seen = stamp; changedAt = Date.now(); }
      if (seen !== first && changedAt && Date.now() - changedAt >= settle && Date.now() - loadedAt >= minGap) location.reload();
    } catch { /* server restarting */ }
  };
  setInterval(tick, every);
  tick();
}
