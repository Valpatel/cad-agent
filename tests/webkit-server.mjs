import http from 'node:http';
import path from 'node:path';
import { readFile } from 'node:fs/promises';
import { fileURLToPath } from 'node:url';
const kit = fileURLToPath(new URL('../src/cadagent/webkit/', import.meta.url));
const types = { '.js': 'text/javascript', '.css': 'text/css', '.html': 'text/html', '.json': 'application/json', '.wasm': 'application/wasm', '.png': 'image/png', '.woff2': 'font/woff2' };
export async function serveWebkit(routes = new Map()) {
  const server = http.createServer(async (req, res) => {
    try {
      const url = new URL(req.url, 'http://localhost');
      if (routes.has(url.pathname)) { await routes.get(url.pathname)(req, res, url); return; }
      if (!url.pathname.startsWith('/kit/')) { res.writeHead(404).end(); return; }
      const target = path.resolve(kit, '.' + decodeURIComponent(url.pathname.slice(4)));
      if (!target.startsWith(kit)) { res.writeHead(403).end(); return; }
      const data = await readFile(target);
      res.writeHead(200, { 'Content-Type': types[path.extname(target)] || 'application/octet-stream', 'Cache-Control': 'no-store' }); res.end(data);
    } catch { if (!res.headersSent) res.writeHead(404); res.end(); }
  });
  await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
  return { url: `http://127.0.0.1:${server.address().port}`, close: () => new Promise(resolve => { server.close(resolve); server.closeAllConnections(); }) };
}
