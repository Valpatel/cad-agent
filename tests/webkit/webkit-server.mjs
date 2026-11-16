import http from 'node:http';
import path from 'node:path';
import { readFile } from 'node:fs/promises';
import { fileURLToPath } from 'node:url';
const kit = fileURLToPath(new URL('../../software/cadagent/webkit', import.meta.url));
const types = { '.js': 'text/javascript', '.mjs': 'text/javascript', '.css': 'text/css', '.html': 'text/html', '.json': 'application/json', '.wasm': 'application/wasm', '.svg': 'image/svg+xml', '.png': 'image/png', '.jpg': 'image/jpeg', '.jpeg': 'image/jpeg', '.woff2': 'font/woff2' };
export async function serveWebkit(routes = new Map(), { cacheControl = 'no-store' } = {}) {
  const server = http.createServer(async (req, res) => {
    try {
      const url = new URL(req.url, 'http://localhost');
      if (routes.has(url.pathname)) { await routes.get(url.pathname)(req, res, url); return; }
      // The kit's standalone viewers ask their host for a top bar (ui/appnav.js, <root>/site/nav.json); this host is a
      // project without one. A test that needs a bar or a missing file routes /site/nav.json itself (#804).
      if (url.pathname === '/site/nav.json') { res.writeHead(200, { 'Content-Type': 'application/json' }).end('{"title":"","nav":[]}\n'); return; }
      if (!url.pathname.startsWith('/kit/')) { res.writeHead(404).end(); return; }
      const target = path.resolve(kit, '.' + decodeURIComponent(url.pathname.slice(4)));
      if (!target.startsWith(kit)) { res.writeHead(403).end(); return; }
      const data = await readFile(target);
      res.writeHead(200, { 'Content-Type': types[path.extname(target)] || 'application/octet-stream', 'Cache-Control': cacheControl }); res.end(data);
    } catch { if (!res.headersSent) res.writeHead(404); res.end(); }
  });
  await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
  return { url: `http://127.0.0.1:${server.address().port}`, close: () => new Promise(resolve => { server.close(resolve); server.closeAllConnections(); }) };
}
