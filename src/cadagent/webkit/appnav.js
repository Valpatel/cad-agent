// The app-wide top bar for a project's own pages: reads site/nav.json (written by `cad-agent site`) and renders the
// same tabs as the project site, so every page of the app shares one navigation.
//   mountAppNav({ root: '../', current: 'simulate' })   // root: path from this page to the project root
const NAV_CSS = `
.appnav{position:fixed;top:0;left:0;right:0;z-index:50;display:flex;align-items:center;gap:4px;padding:0 16px;height:46px;
background:rgba(6,6,9,.94);backdrop-filter:blur(10px);border-bottom:1px solid #2a303c;overflow-x:auto;font-family:'Inter',system-ui,sans-serif}
.appnav .brand{font-weight:700;margin-right:12px;white-space:nowrap;display:flex;align-items:center;gap:8px;color:#e8edf5;text-decoration:none;font-size:15px}
.appnav .brand i{width:9px;height:9px;background:#00f0ff;transform:rotate(45deg);box-shadow:0 0 10px rgba(0,240,255,.3)}
.appnav a.tab{font:500 12px 'JetBrains Mono',ui-monospace,monospace;letter-spacing:.08em;text-transform:uppercase;color:#8892a4;
text-decoration:none;padding:6px 10px;border-radius:6px;white-space:nowrap}
.appnav a.tab:hover{color:#00f0ff}.appnav a.tab.on{color:#00f0ff;background:rgba(0,240,255,.06);box-shadow:inset 0 -2px 0 #00f0ff}
body.has-appnav{--appnav-h:46px}`;

export async function mountAppNav({ root = '../', current = '' } = {}) {
  let cfg;
  try { cfg = await (await fetch(`${root}site/nav.json`)).json(); } catch { return null; }
  if (!cfg?.nav?.length) return null;
  const style = document.createElement('style');
  style.textContent = NAV_CSS;
  document.head.appendChild(style);
  const nav = document.createElement('nav');
  nav.className = 'appnav';
  const esc = (s) => String(s ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  nav.innerHTML = `<a class="brand" href="${root}site/"><i></i>${esc(cfg.title)}</a>`
    + cfg.nav.map((n) => `<a class="tab${(n.id ?? n.href) === current ? ' on' : ''}" href="${/^[a-z]+:/.test(n.href) ? n.href : root + n.href}">${esc(n.title)}</a>`).join('');
  document.body.prepend(nav);
  document.body.classList.add('has-appnav');
  return nav;
}
