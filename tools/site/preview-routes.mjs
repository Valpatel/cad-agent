/** Select the same response for the live preview and a failure-only inspection of its built site. */
import { readFile, stat } from 'node:fs/promises';
import path from 'node:path';

export async function previewRedirects(dir, options) {
  const text = await readFile(path.join(dir, '_redirects'), { ...options, encoding: 'utf8' }).catch(error => {
    if (options?.signal && error.code !== 'ENOENT') throw error;
    return '';
  });
  return new Map(text.split('\n').map(line => line.trim().split(/\s+/))
    .filter(parts => parts.length >= 2 && parts[0].startsWith('/'))
    .map(([from, to, code]) => [from, [to, Number(code) || 302]]));
}

export async function previewRoute(dir, encodedPath, redirects) {
  let pathname;
  try { pathname = decodeURIComponent(encodedPath); } catch { return { status: 400 }; }
  // No NUL, dot segments or backslashes: a redirect must stay on the intended host.
  if (/[\0\\]/.test(pathname) || path.posix.normalize(pathname) !== pathname) return { status: 400 };
  if (redirects.has(pathname)) {
    const [location, status] = redirects.get(pathname);
    return { status, location };
  }
  if (pathname.endsWith('.html')) {
    const location = pathname.endsWith('/index.html') ? pathname.slice(0, -'index.html'.length) : pathname.slice(0, -'.html'.length);
    return { status: 308, location };
  }
  const candidates = pathname.endsWith('/') ? [pathname + 'index.html'] : [pathname, pathname + '.html', pathname + '/index.html'];
  for (const file of candidates) {
    try { if (!(await stat(path.join(dir, file))).isFile()) continue; } catch { continue; }
    // A directory application's relative modules need the final slash.
    if (file === pathname + '/index.html') return { status: 308, location: pathname + '/' };
    return { status: 200, pathname, file };
  }
  return { status: 404, pathname, file: '/404.html' };
}
