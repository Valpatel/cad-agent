/** Serve dist/ the way Cloudflare Pages does, for local preview and the site tests.
 *
 *   node tools/preview-site.mjs [--dir dist] [--port 8781] [--host 127.0.0.1]
 *
 * Pretty URLs (/docs/toolkit serves docs/toolkit.html; /x.html redirects to /x), 404.html with status 404, and the
 * response headers from dist/_headers, so the Content-Security-Policy is exercised before a deploy. Listens on
 * loopback only unless --host says otherwise.
 */
import { createServer } from 'node:http';
import { readFile, stat } from 'node:fs/promises';
import path from 'node:path';

const arg = (name, dflt) => { const i = process.argv.indexOf(name); return i > 0 ? process.argv[i + 1] : dflt; };
const dir = path.resolve(arg('--dir', path.join(import.meta.dirname, '..', 'dist')));
const port = Number(arg('--port', 8781)), host = arg('--host', '127.0.0.1');
const TYPES = { '.html': 'text/html; charset=utf-8', '.css': 'text/css; charset=utf-8', '.js': 'text/javascript; charset=utf-8',
  '.mjs': 'text/javascript; charset=utf-8', '.json': 'application/json', '.svg': 'image/svg+xml', '.png': 'image/png',
  '.jpg': 'image/jpeg', '.jpeg': 'image/jpeg', '.gif': 'image/gif', '.webp': 'image/webp', '.woff2': 'font/woff2',
  '.wasm': 'application/wasm', '.txt': 'text/plain; charset=utf-8', '.md': 'text/markdown; charset=utf-8',
  '.xml': 'application/xml', '.step': 'model/step', '.stl': 'model/stl', '.glb': 'model/gltf-binary' };

/** Parse a Cloudflare Pages _headers file into [{ pattern: RegExp, headers: [[name, value]] }]. */
export function parseHeaders(text) {
  const rules = [];
  for (const line of text.split('\n')) {
    if (!line.trim() || line.trim().startsWith('#')) continue;
    if (!/^\s/.test(line)) {
      const re = '^' + line.trim().replace(/[.+?^${}()|[\]\\]/g, '\\$&').replace(/\*/g, '.*').replace(/:\w+/g, '[^/]+') + '$';
      rules.push({ pattern: new RegExp(re), headers: [] });
    } else if (rules.length) {
      const i = line.indexOf(':');
      rules.at(-1).headers.push([line.slice(0, i).trim(), line.slice(i + 1).trim()]);
    }
  }
  return rules;
}
/** Headers for a path; a header set by several matching rules gets the values joined, as Pages does. */
export function headersFor(rules, pathname) {
  const out = {};
  for (const r of rules) if (r.pattern.test(pathname))
    for (const [k, v] of r.headers) { const key = k.toLowerCase(); out[key] = out[key] ? `${out[key]}, ${v}` : v; }
  return out;
}

const exists = async f => { try { return (await stat(f)).isFile(); } catch { return false; } };
const rules = parseHeaders(await readFile(path.join(dir, '_headers'), 'utf8').catch(() => ''));

const server = createServer(async (req, res) => {
  const url = new URL(req.url, 'http://x');
  let pathname = decodeURIComponent(url.pathname);
  if (pathname.includes('\0') || path.posix.normalize(pathname) !== pathname) { res.writeHead(400).end(); return; }
  if (pathname.endsWith('.html')) {                               // Pages drops .html with a redirect
    const pretty = pathname === '/index.html' ? '/' : pathname.replace(/(?:\/index)?\.html$/, '');
    res.writeHead(308, { location: pretty + url.search }).end(); return;
  }
  const candidates = pathname.endsWith('/') ? [pathname + 'index.html'] : [pathname, pathname + '.html', pathname + '/index.html'];
  let file = null;
  for (const c of candidates) if (await exists(path.join(dir, c))) { file = c; break; }
  const status = file ? 200 : 404;
  file ??= '/404.html';
  const body = await readFile(path.join(dir, file)).catch(() => Buffer.from('Not found'));
  res.writeHead(status, { 'content-type': TYPES[path.extname(file)] || 'application/octet-stream', ...headersFor(rules, pathname) });
  res.end(req.method === 'HEAD' ? undefined : body);
});
if (process.argv[1] === import.meta.filename) {
  server.listen(port, host, () => console.log(`Serving ${path.relative(process.cwd(), dir) || dir} at http://${host}:${server.address().port}/`));
}
export { server };
