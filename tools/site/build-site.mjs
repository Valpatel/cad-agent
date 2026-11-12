/** Build cad-agent.valpatel.com into dist/: one static bundle for local preview and Cloudflare Pages.
 *
 * Agent-first: every page has its Markdown source next to it (same path, .md), /llms.txt and /llms-full.txt index
 * everything, and /catalog.json is the machine-readable catalogue (tools, libraries, skills, docs, lessons, research).
 * Only committed files are published: every source is read from HEAD with `git show`, never from the working tree,
 * so an untracked or uncommitted file cannot reach the site. `--worktree` builds a local draft from tracked files as
 * they are on disk (the footer then says so); `--release` refuses a dirty tree.
 * Diagrams are drawn here, in headless Chromium (tools/site/compiler/site-diagrams.mjs); `--client-diagrams`, or a machine with no
 * browser, leaves them to the reader's browser, as before (#132).
 */
import { readFile, writeFile, mkdir, rm, readdir } from 'node:fs/promises';
import { readFileSync } from 'node:fs';
import { createHash } from 'node:crypto';
import { execFileSync } from 'node:child_process';
import path from 'node:path';
import { marked } from 'marked';
import YAML from 'yaml';
import { snapDemo } from './compiler/snap-demo.mjs';
import { buildCatalog } from './compiler/site-catalog.mjs';
import { prepareDiscoveryPage, discoveryModel, discoveryHTML } from './compiler/site-discovery.mjs';            // the catalogue page, catalog.json, catalog/*.json and covers
import { sanitize, safeUrl, rewriteUrls, imageSize } from './compiler/site-html.mjs';   // allowlist sanitizer for rendered Markdown
import { drawBoth, drawDiagrams } from './compiler/site-diagrams.mjs';         // Mermaid blocks drawn into finished figures, at build time
import { ON, fold, pagePlacer } from './compiler/site-pages.mjs';    // docs/pages.yaml: bands, section cards, figures, folds
import { SECTIONS, createPublication, validateRedirects, folderMapSources } from './publication.mjs';
import { loadReferences, referenceModel, referenceSite, linkTags, mdTags, healthOf } from './compiler/site-references.mjs';   // /references (#323)

// --root DIR builds another checkout of this repo (the tests use a scratch worktree); the build tools still run from here.
const rootArg = process.argv.indexOf('--root');
const root = path.resolve(rootArg > 0 ? process.argv[rootArg + 1] : path.join(import.meta.dirname, '../..'));
const outArg = process.argv.indexOf('--out');
const out = outArg > 0 ? path.resolve(process.argv[outArg + 1]) : path.join(root, 'dist');
// The site's one address. It is also served at cad-agent.gyropup.com, a second custom domain on the same Pages project.
// Every page names its address here as canonical (site pages by <link>, the kit's pages by a Link header), so search
// engines index one copy. llms.txt, catalog.json, the sitemap and the feedback links use it too.
const ORIGIN = 'https://cad-agent.valpatel.com';
const REPO = 'https://github.com/Valpatel/cad-agent';
const TAGLINE = 'Your one stop shop for agentic CAD';
const LEDE = 'Mapping the best free resources, demonstrating their capabilities, and filling the gaps. Made for AI and people.';
const WORKTREE = process.argv.includes('--worktree');
const RELEASE = process.argv.includes('--release');
const CLIENT_DIAGRAMS = process.argv.includes('--client-diagrams');
const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
const gitRaw = (...a) => execFileSync('git', a, { cwd: root, maxBuffer: 1 << 28 });
const git = (...a) => gitRaw(...a).toString().trim();
if (RELEASE && git('status', '--porcelain')) throw new Error('--release needs a clean working tree (commit or stash first)');
if (RELEASE && WORKTREE) throw new Error('--release and --worktree are exclusive');
// Production is built from reviewed history only: a commit on origin/main or origin/dev (CD deploys from main).
const onReviewed = ref => { try { execFileSync('git', ['merge-base', '--is-ancestor', 'HEAD', ref], { cwd: root }); return true; } catch { return false; } };
if (RELEASE && !onReviewed('origin/main') && !onReviewed('origin/dev')) throw new Error('--release needs HEAD on origin/main or origin/dev (merged and pushed), so production only shows reviewed commits');
const tracked = git('ls-tree', '-r', '-z', '--name-only', 'HEAD').split('\0').filter(Boolean);
// Preserve the public image library; rendered pages also add their actual local illustrations below.
const publishedImages = new Set(tracked.filter(f => /^docs\/img\/.*\.(svg|png|jpe?g|gif|webp)$/i.test(f)));
const head = git('rev-parse', 'HEAD');
const revision = head;
// The content is always HEAD's (or the working tree's with --worktree), but the build tools run from disk (from this
// checkout, even with --root): say so when they differ from the built commit's, and never release with them.
const TOOLS = ['tools/site/build-site.mjs', 'tools/site/compiler/site-html.mjs', 'tools/site/compiler/snap-demo.mjs', 'tools/site/compiler/site-catalog.mjs', 'tools/site/compiler/site-discovery.mjs', 'tools/site/compiler/catalog-art.mjs',
  'tools/site/compiler/site-diagrams.mjs', 'tools/site/compiler/site-pages.mjs', 'tools/site/compiler/site-references.mjs', 'tools/site/publication.mjs', 'tools/site/page-sources.json', 'tools/site/package.json', 'tools/site/package-lock.json'];
const toolsHere = path.join(import.meta.dirname, '../..');
const toolsDirty = TOOLS.filter(t => {
  let committedCopy; try { committedCopy = gitRaw('show', `HEAD:${t}`); } catch { return true; }
  return !committedCopy.equals(readFileSync(path.join(toolsHere, t)));
}).join(', ');
if (RELEASE && toolsDirty) throw new Error(`--release needs the build tools that run to match the built commit; these differ: ${toolsDirty}`);
const revisionLabel = WORKTREE ? `${head.slice(0, 7)} + local changes` : toolsDirty ? `${head.slice(0, 7)} + local build tools` : head.slice(0, 7);
const committed = git('show', '-s', '--format=%cI', 'HEAD');            // build time = commit time: reproducible
if (RELEASE && git('rev-parse', '--is-shallow-repository') === 'true') throw new Error('--release needs full git history (fetch-depth: 0), so each page shows when it really changed');
// When a page's source last changed: its last commit (null when it has uncommitted changes in a --worktree draft).
const lastChange = file => WORKTREE && git('status', '--porcelain', '--', file) ? null : git('log', '-1', '--format=%cI', 'HEAD', '--', file) || committed;
const isoDay = iso => iso.slice(0, 10);                 // the commit's own calendar date, as `git log` shows it
const day = iso => new Date(`${isoDay(iso)}T12:00:00Z`).toLocaleDateString('en-GB', { day: 'numeric', month: 'short', year: 'numeric', timeZone: 'UTC' });
const readBuf = p => WORKTREE ? readFile(path.join(root, p)) : Promise.resolve(gitRaw('show', `HEAD:${p}`));
const read = async p => (await readBuf(p)).toString('utf8');
const publication = createPublication(JSON.parse(await read('tools/site/page-sources.json')));
const folderSources = folderMapSources(tracked, JSON.parse(await read('tools/site/compiler/repo-map.json')), publication);
const folderPaths = new Map(folderSources.map(p => [p.file, p.public]));
const publicPath = f => folderPaths.get(f) || publication.publicPath(f);
const selectPages = publication.selectPages;
const copyTracked = async (f, dest) => { await mkdir(path.dirname(dest), { recursive: true }); await writeFile(dest, await readBuf(f)); };

await rm(out, { recursive: true, force: true });
await mkdir(out, { recursive: true });
const ASSETS = 'tools/site/assets';
for (const f of tracked.filter(f => f.startsWith(ASSETS + '/') && f !== ASSETS + '/README.md'))
  await copyTracked(f, path.join(out, 'web', f.slice(ASSETS.length + 1)));
// Browsers ask for /favicon.ico on pages without an icon link (llms.txt, the .md twins).
if (tracked.includes(ASSETS + '/favicon.ico')) await copyTracked(ASSETS + '/favicon.ico', path.join(out, 'favicon.ico'));
// The one-line installers (#282), at the short URLs the README and the home page give.
for (const f of ['install.sh', 'install.ps1']) await copyTracked(`${ASSETS}/${f}`, path.join(out, f));
// The shared web kit (3D viewer, part tables, diagrams) is published as /kit/, the same files projects copy.
for (const f of tracked.filter(f => f.startsWith('software/cadagent/webkit/'))) {
  await copyTracked(f, path.join(out, 'kit', f.slice('software/cadagent/webkit/'.length)));
}

// ----------------------------------------------------------------------------- content
const front = src => {
  const m = src.match(/^---\n([\s\S]*?)\n---\n/);
  return m ? { meta: YAML.parse(m[1]) || {}, body: src.slice(m[0].length) } : { meta: {}, body: src };
};
// Summary: the first prose paragraph (not a heading, badge, image, table, code, HTML or list), else the first list
// item; plain text, cut at a sentence end before 260 characters.
const plain = s => s.replace(/<img\b[^>]*\balt="([^"]*)"[^>]*>/gi, '$1').replace(/!\[[^\]]*\]\([^)]*\)/g, '').replace(/\[([^\]]+)\]\([^)]*\)/g, '$1')
  .replace(/<[^>]+>/g, '').replace(/[*_`]/g, '').replace(/\s+/g, ' ').trim();
const clip = s => {
  if (s.length <= 260) return s;
  const cut = s.slice(0, 260), end = Math.max(cut.lastIndexOf('. '), cut.lastIndexOf('; '));
  return end > 80 ? cut.slice(0, end + 1) : cut.replace(/\s+\S*$/, '') + '…';
};
// A page that goes straight from its title into sections (the lessons) is summarised by its first section titles.
const firstPara = md => {
  const lines = md.replace(/```[\s\S]*?```/g, '').split('\n');
  const notProse = /^(\||<|!\[|\[!\[|[-*+] |\d+\. |>|---)/;
  let para = [];
  for (const raw of lines) {
    const line = raw.trim();
    if (/^#\s/.test(line)) continue;                                   // the page title
    if (!line) { if (plain(para.join(' ')).length > 30) break; para = []; continue; }
    if (/^#{2,6}\s/.test(line)) {
      if (plain(para.join(' ')).length > 30) break;
      const heads = lines.filter(l => /^#{2,3}\s/.test(l)).slice(0, 4).map(l => plain(l.replace(/^#+\s*/, '')));
      return clip(heads.join('; ') + (heads.length ? '.' : ''));
    }
    if (notProse.test(line)) { if (plain(para.join(' ')).length > 30) break; para = []; continue; }
    para.push(line);
  }
  return clip(plain(para.join(' ')));
};

const pages = [];
const folderMapPages = [];
// A file that moved keeps a one-line stub at its old path (`<!-- moved-to: new/path.md -->`), so links into the repo
// keep working on GitHub; the site serves a permanent redirect instead of a page.
const moved = [];
for (const { file, section, parent } of [...selectPages(tracked), ...folderSources.map(p => ({ ...p, section: { id: 'folder-maps' } }))]) {
  const src = await read(file);
  const to = src.match(/^<!--\s*moved-to:\s*(\S+?\.md)\s*-->/)?.[1];
  if (to) {
    const target = path.posix.normalize(path.posix.join(path.posix.dirname(file), to));
    if (!tracked.includes(target)) throw new Error(`${file} says it moved to ${target}, which does not exist`);
    moved.push([file, target]);
    continue;
  }
  const { meta, body } = front(src);
  const headingTitle = body.match(/^#\s+(.+)$/m)?.[1];
  const title = meta.name || (headingTitle?.includes('<picture>') ? plain(headingTitle) : headingTitle) || file;
  (section.id === 'folder-maps' ? folderMapPages : pages).push({ file, section: section.id, parent, title: String(title).replace(/[`*]/g, ''), summary: meta.description || firstPara(body), body, src });
}
const pageURL = f => '/' + publicPath(f).replace(/\.md$/, '');                  // Cloudflare Pages serves x.html at /x
const pageFile = f => publicPath(f).replace(/\.md$/, '.html');
const allPages = [...pages, ...folderMapPages];
const pageFiles = new Set(allPages.map(p => p.file));
const pageDestinations = new Set();
for (const p of allPages) for (const file of [publicPath(p.file), pageFile(p.file)]) {
  if (pageDestinations.has(file)) throw new Error(`duplicate public output: ${file}`);
  pageDestinations.add(file);
}
// Permanent redirects (tools/site/compiler/site-redirects.txt): they outlive the stubs, so deleting a stub never drops a 301.
const redirects = (await read('tools/site/compiler/site-redirects.txt')).split('\n').map(l => l.replace(/#.*/, '').trim()).filter(Boolean)
  .map(l => l.split(/\s+/));
validateRedirects(redirects, { tracked, pageFiles, moved, publicPath });

// ----------------------------------------------------------------------------- references
// The reference registry (docs/research/references.yaml and its shards): /references pages, their JSON, and [ref:<id>]
// tags in every page as links to the record (tools/site/compiler/site-references.mjs). Records are not catalogue entries.
const refModel = referenceModel(await loadReferences({ files: tracked, read }), YAML.parse(await read('docs/areas.yaml')));

// ----------------------------------------------------------------------------- catalogue
const landscape = JSON.parse(await read('docs/research/landscape.json'));
const upstreams = YAML.parse(await read('software/vendor/upstreams/registry.yaml')) || [];
const cli = await read('software/cadagent/cli.py');
const parserCount = (cli.match(/sub\.add_parser\(/g) || []).length;
const commands = [...cli.matchAll(/sub\.add_parser\("([a-z0-9-]+)",[^)]*?help="((?:[^"\\]|\\.)*)"(?:\s*\n?\s*"((?:[^"\\]|\\.)*)")?/g)]
  .map(m => ({ name: m[1], help: (m[2] + (m[3] || '')).replace(/\\"/g, '"') }));
if (commands.length !== parserCount) throw new Error(`read ${commands.length} of ${parserCount} cli.py subcommands: fix the pattern`);
// The catalogue itself is built after the pages (it uses their figures): see `buildCatalog` below.

// ----------------------------------------------------------------------------- HTML frame
const NAV = [['/explore', 'Explore', true], ['/docs/toolkit', 'Toolkit', true], ['/docs/agent-workflow', 'For agents']];
// Feedback goes to GitHub: a short issue form with the page filled in, or an edit of the page's source.
const feedbackURL = (title, url) => `${REPO}/issues/new?template=feedback.yml&title=${encodeURIComponent(`Feedback: ${title}`)}&page=${encodeURIComponent(ORIGIN + url)}`;
const feedbackBox = (title, url, file) => `<aside class="feedback" aria-label="Feedback"><div><p class="feedback-title">Help us improve!</p>
<p>Something wrong, missing or confusing on this page? Tell us in a minute. Every note is read, and ideas we use are credited.</p></div>
<div class="feedback-actions"><a class="button" href="${esc(feedbackURL(title, url))}">Give feedback</a>${file ? `<a href="${REPO}/edit/dev/${esc(file)}">Suggest an edit</a>` : ''}</div></aside>`;
// Pages with one of the kit's interactive demos load its stylesheet in <head> (it reserves the demo's size before the
// script runs, so nothing moves) and preload its module; web/site.js imports it.
const KIT_DEMOS = { 'cad-cantilever': 'cantilever', 'cad-fourbar': 'fourbar', 'cad-fan-curve': 'fan-curve',
  'cad-torsion-snap': 'torsion-snap', 'cad-printed-boss': 'printed-boss' };
const kitDemos = body => Object.entries(KIT_DEMOS).filter(([tag]) => body.includes(`<${tag}`))
  .map(([, f]) => `<link rel="stylesheet" href="/kit/${f}.css"><link rel="modulepreload" href="/kit/${f}.js">`).join('');
// The theme button (web/theme.js shows it and keeps aria-pressed true while the page is dark).
const THEME_BUTTON = '<button type="button" class="theme-toggle" aria-pressed="false" title="Dark theme" hidden><span class="visually-hidden">Dark theme</span>' +
  '<svg class="sun" viewBox="0 0 24 24" aria-hidden="true"><circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4"/></svg>' +
  '<svg class="moon" viewBox="0 0 24 24" aria-hidden="true"><path d="M20 14.5A8 8 0 0 1 9.5 4a8 8 0 1 0 10.5 10.5z"/></svg></button>';
function frame({ title, body, md, description = LEDE, current = '', page = 'doc', css = [], updated = committed, url = current || '/' }) {
  // Cloudflare's documented region guard preserves package@version code literals without changing zone settings,
  // compression or CSP. Keep the guard outside the authored elements; verify actual hosted bytes after release.
  return `<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>${esc(title === TAGLINE ? 'cad-agent · ' + TAGLINE : title + ' · cad-agent')}</title>
<meta name="description" content="${esc(description)}">${current ? `<link rel="canonical" href="${esc(ORIGIN + current)}">` : ''}
<script src="/web/theme.js"></script><link rel="icon" href="/web/icon.svg"><link rel="preload" href="/kit/vendor/fonts/inter.woff2" as="font" type="font/woff2" crossorigin><link rel="preload" href="/kit/vendor/fonts/jetbrains-mono.woff2" as="font" type="font/woff2" crossorigin><link rel="stylesheet" href="/web/site.css"><link rel="stylesheet" href="/kit/diagrams.css">${css.map(c => `<link rel="stylesheet" href="${c}">`).join('')}${kitDemos(body)}
${md ? `<link rel="alternate" type="text/markdown" href="${esc(md)}" title="Markdown for agents">` : ''}
<link rel="alternate" type="text/plain" href="/llms.txt" title="llms.txt"></head>
<body class="${page}-page"><!--email_off--><a class="skip-link" href="#main:content">Skip to content</a><header class="site-header"><div class="wrap"><a class="wordmark" href="/"><img src="/web/icon.svg" alt="" width="34" height="34">cad-agent<b>.</b></a>
<nav aria-label="Main">${NAV.map(([h, t, keep]) => `<a href="${h}"${keep ? ' data-keep' : ''}${h === current ? ' aria-current="page"' : ''}>${t}</a>`).join('')}<a class="pill-link" href="${REPO}">GitHub ↗</a>${THEME_BUTTON}</nav></div></header>
<main class="${page === 'landing' ? '' : 'wrap'} ${page === 'doc' ? 'doc' : ''}"${body.includes('id="main:content"') ? '' : ' id="main:content" tabindex="-1"'}>${current === '/catalog' || current.startsWith('/references') || current === '/docs/common-issues' || current === '/research/landscape' ? `<p class="discovery-context"><a href="/explore${current.startsWith('/references') ? '?kind=references' + (current.split('/')[2] ? '&amp;area=' + encodeURIComponent(current.split('/')[2]) : '') : current === '/docs/common-issues' ? '?kind=lessons' : current === '/research/landscape' ? '?kind=external' : ''}">← Explore all knowledge${current.startsWith('/references') ? ' · search sources across topics' : current === '/docs/common-issues' ? ' · search individual lessons and pitfalls' : ''}</a></p>` : ''}${body}</main>
<footer class="site-footer"><div class="wrap"><p>Created by <a href="https://valpatel.com">Valpatel Software LLC</a>. Code under the <a href="${REPO}/blob/dev/LICENSE">MIT licence</a>; every third-party tool keeps its own licence and credit. ${updated ? `Last updated <time datetime="${isoDay(updated)}">${day(updated)}</time>.` : 'This page has uncommitted changes.'} Built from <a href="${REPO}/commit/${revision}">${esc(revisionLabel)}</a>.</p>
<div class="links"><a href="${esc(feedbackURL(title === TAGLINE ? 'home page' : title, url))}">Help us improve ↗</a><a href="/llms.txt">llms.txt</a><a href="/llms-full.txt">llms-full.txt</a><a href="/catalog.json">catalog.json</a>${md ? `<a href="${esc(md)}">this page .md</a>` : ''}</div></div></footer>
<script type="module" src="/web/site.js"></script><!--/email_off--></body></html>`;
}

// ----------------------------------------------------------------------------- pages
const ENT = { amp: '&', lt: '<', gt: '>', quot: '"', apos: "'", nbsp: ' ' };
const decode = s => s.replace(/&(#x[\da-f]+|#\d+|[a-z]+);/gi, (m, e) => e[0] === '#'
  ? String.fromCodePoint(e[1].toLowerCase() === 'x' ? parseInt(e.slice(2), 16) : parseInt(e.slice(1), 10)) : (ENT[e] ?? m));
// GitHub's anchor rule (github-slugger): lower case, drop everything but letters, marks, numbers, connectors, hyphens
// and spaces, then each space becomes a hyphen (runs are not collapsed); repeats get -1, -2.
export const slug = text => decode(text.replace(/<img\b[^>]*\balt="([^"]*)"[^>]*>/gi, '$1').replace(/<[^>]*>/g, '')).toLowerCase().replace(/[^\p{L}\p{M}\p{N}\p{Pc}\- ]/gu, '').replace(/ /g, '-');

// The shared diagram palette (the style guide, #121). Files agents load (skills, subagents) keep only their
// `class … here` lines (or `:::here`), to save context; GitHub draws those diagrams in its default colours, and the site
// adds the classDefs a diagram uses but does not define. Applied to the parsed code block, so a Mermaid example quoted
// inside another fence is left as written.
const PALETTE = { here: 'fill:#fffdf5,stroke:#173d3c,color:#173d3c', near: 'fill:#eef1e4,stroke:#6f8a80,color:#173d3c',
  out: 'fill:#ffe1cc,stroke:#bd3a12,color:#173d3c' };
const withPalette = src => {
  const used = new Set([...src.matchAll(/^\s*class\s+\S+\s+(here|near|out)\s*;?\s*$/gm), ...src.matchAll(/:::(here|near|out)\b/g)].map(m => m[1]));
  const missing = [...used].filter(c => !new RegExp(`^\\s*classDef\\s+${c}\\b`, 'm').test(src));
  return missing.length ? src.replace(/\n?$/, '\n') + missing.map(c => `    classDef ${c} ${PALETTE[c]}`).join('\n') : src;
};
// A link to a folder whose README is a page goes to that page (docs/lessons/process/ → docs/lessons/process/README).
const folderPage = resolved => {
  const readme = resolved.replace(/\/?$/, '/README.md');
  return !resolved.endsWith('.md') && pageFiles.has(readme) ? readme : null;
};
// Resolve links from the real source location, then write them relative to the public Markdown location.
// A moved policy is sourced under .github/ but keeps its original public URL and Markdown twin.
const rewriteMdURL = (file, url, absolute) => {
    if (!url || url.startsWith('#') || /^(?:[a-z][a-z\d+.-]*:|\/\/)/i.test(url)) return null;
    const [pathname, ...hash] = url.split('#');
    const resolved = pathname.startsWith('/') ? pathname.slice(1) : path.posix.normalize(path.posix.join(path.posix.dirname(file), pathname));
    const folder = folderPage(resolved);
    const destination = folder || resolved;
    const published = pageFiles.has(destination) || publishedImages.has(destination);
    let target;
    if (published) {
      const publicFile = publicPath(destination);
      target = absolute ? `${ORIGIN}/${publicFile}` : pathname.startsWith('/') ? '/' + publicFile
        : path.posix.relative(path.posix.dirname(publicPath(file)), publicFile) || path.posix.basename(publicFile);
    } else target = `${REPO}/${tracked.includes(resolved) ? 'blob' : 'tree'}/dev/${resolved}`;
    return `${target}${hash.length ? '#' + hash.join('#') : ''}`;
};
const rewriteMd = (file, md, absolute = false) => md.split(/(```[\s\S]*?```|`+[^`]*`+)/).map((chunk, i) => {
  if (i % 2) return chunk;
  const links = chunk.replace(/(\]\()([^)\s#][^)\s]*)((?:\s+"[^"]*")?\))/g, (all, open, url, close) => {
    const target = rewriteMdURL(file, url, absolute);
    return target === null ? all : `${open}${target}${close}`;
  });
  // Raw HTML images are used to size folder previews. Their twin URLs must follow the same public identity.
  return rewriteUrls(links, url => rewriteMdURL(file, url, absolute));
}).join('');
// A Markdown copy with its [ref:<id>] tags as links to the records' pages (relative, or absolute for llms-full.txt).
const twinMd = (file, md, absolute = false) => mdTags(rewriteMd(file, md, absolute), publicPath(file), refModel, { ORIGIN, absolute });
// Every page should show something: a picture, render, diagram, animation or demo. Pages without one are listed by
// the build and kept from growing by tests/site/website-build.test.mjs.
// What counts as something to look at in a doc page's sanitized HTML (the sanitizer drops inline <svg>, <video> and
// custom elements, so pictures arrive as <img> and diagrams as Mermaid blocks; the browser test checks they render).
const VISUAL = /<img\b|class="language-mermaid"|<pre class="mermaid"/g;
const visuals = new Map();
const docPages = [];                         // [path in out, HTML]: written once their diagrams are drawn, below
// Visual-first pages (#179): real outputs placed from docs/pages.yaml, long reference parts folded (tools/site/compiler/site-pages.mjs).
const placeVisuals = pagePlacer({ spec: YAML.parse(await read('docs/pages.yaml')) || {}, pageFiles, tracked,
  commandNames: new Set(commands.map(c => c.name)), readBuf, pageURL });
for (const p of allPages) {
  const ids = new Map();
  const renderer = new marked.Renderer();
  const code = renderer.code.bind(renderer);
  renderer.code = token => code(token.lang === 'mermaid' ? { ...token, text: withPalette(token.text) } : token);
  renderer.heading = function ({ tokens, depth }) {
    const text = this.parser.parseInline(tokens);
    const base = slug(text);
    const n = ids.get(base) || 0; ids.set(base, n + 1);
    return `<h${depth} id="${base}${n ? '-' + n : ''}">${text}</h${depth}>`;
  };
  const body = /^#\s/m.test(p.body) ? p.body : `# ${p.title}\n\n${p.body}`;          // subagents have no heading
  let html = sanitize(await marked.parse(body, { renderer }));
  html = rewriteUrls(html, (url, attr) => {          // only real tags: link text inside code samples stays as written
    if (!url || url.startsWith('#') || /^(?:[a-z][a-z\d+.-]*:|\/\/)/i.test(url)) return null;
    const [pathname, ...hash] = url.split('#');
    const resolved = pathname.startsWith('/') ? pathname.slice(1) : path.posix.normalize(path.posix.join(path.posix.dirname(p.file), pathname));
    let target;
    if (pageFiles.has(resolved)) target = pageURL(resolved);
    else if (folderPage(resolved)) target = pageURL(folderPage(resolved));
    else if ((attr === 'src' || attr === 'srcset') && tracked.includes(resolved) && /\.(svg|png|jpe?g|gif|webp)$/i.test(resolved)) {
      publishedImages.add(resolved);                    // embedded example images can live beside their source README
      target = '/' + resolved;
    }
    else target = `${REPO}/${tracked.includes(resolved) ? 'blob' : 'tree'}/dev/${resolved}`;
    return target + (hash.length ? '#' + hash.join('#') : '');
  });
  // Every local image gets a width and height, so its space is kept while it loads (no layout shift). The author's
  // size wins, as on GitHub: a pixel width (or height) keeps its value and the other side follows the image's
  // proportions; a percentage width becomes a style (the attributes then only carry the proportions); otherwise the
  // image's own size. CSS (max-width:100%; height:auto) fits all of them to the column.
  const sized = [];
  for (const [tag] of html.matchAll(/<img\b[^>]*>/gi)) {
    const src = tag.match(/\ssrc="\/([^"#?]+)"/)?.[1]?.replace(/&amp;/g, '&');
    if (src && !(/\swidth="\d+"/.test(tag) && /\sheight="\d+"/.test(tag)) && tracked.includes(src)) sized.push([tag, imageSize(await readBuf(src), src)]);
  }
  for (const [tag, size] of sized) if (size) {
    const given = a => tag.match(new RegExp(`\\s${a}="\\s*([^"]*?)\\s*"`, 'i'))?.[1] || '';
    const [w, h] = [given('width'), given('height')];
    let { width, height } = size, style = '';
    if (/^\d+(?:px)?$/.test(w)) [width, height] = [parseInt(w), Math.round(parseInt(w) * size.height / size.width)];
    else if (/^\d+(?:px)?$/.test(h)) [width, height] = [Math.round(parseInt(h) * size.width / size.height), parseInt(h)];
    else if (/^\d+(?:\.\d+)?%$/.test(w) && !/\sstyle=/i.test(tag)) style = ` style="width:${w}"`;
    const fixed = tag.replace(/\s(?:width|height)="[^"]*"/gi, '').replace(/^<img/i, `<img width="${width}" height="${height}"${style}`);
    html = html.replace(tag, () => fixed);                       // a function: "$&" or "$'" in an alt text stays literal
  }
  // No third-party requests from the site: remote images (README badges) become their alt text.
  html = html.replace(/<img\b[^>]*\bsrc="(?:https?:)?\/\/[^"]*"[^>]*>/gi, m => {
    const alt = m.match(/\balt="([^"]*)"/)?.[1];
    return alt ? `<span class="badge">${alt}</span>` : '';
  });
  html = linkTags(html, refModel);                    // [ref:<id>] → the record's row and the source
  html = html.replace(/<table>/g, '<div class="table-scroll"><table>').replace(/<\/table>/g, '</table></div>');
  // One-click copy on every code block (not on diagram sources, which render as pictures).
  html = html.replace(/<pre>(<code(?! class="language-mermaid")[\s\S]*?<\/pre>)/g, '<cad-copy><pre>$1</cad-copy>');
  html = await placeVisuals(p.file, fold(html));
  html = prepareDiscoveryPage(p, html);
  if (p.parent && !pageFiles.has(p.parent)) throw new Error(`folder map ${p.file}: parent ${p.parent} is not published`);
  const entrance = p.section === 'folder-maps'
    ? `<a href="/docs/map">Repository map</a> · <a href="${esc(pageURL(p.parent))}">Parent folder</a>`
    : `<a href="/catalog#${p.section}">${esc(SECTIONS.find(s => s.id === p.section).title)}</a>`;
  const crumbs = `<p class="crumbs">${entrance} · <a href="${REPO}/blob/dev/${esc(p.file)}">${esc(p.file)}</a> · <a href="/${esc(publicPath(p.file))}">Markdown</a></p>`;
  const dest = path.join(out, pageFile(p.file));
  await mkdir(path.dirname(dest), { recursive: true });
  // Long pages: the kit's <cad-nav> on the left (every page, grouped, with this page's outline under it) and, on very
  // wide screens, the outline again in a right-hand column. All written out here, so the first paint is final (the
  // script only marks the section being read and filters) and it all works without script: on phones the tree folds
  // into a native <details>, which opens with or without nav.js.
  const heads = [...html.matchAll(/<h([23]) id="([^"]+)">([\s\S]*?)<\/h\1>/g)]
    .map(([, level, id, inner]) => ({ level, id, text: inner.replace(/<[^>]+>/g, '').trim() })).filter(h => h.text);
  // The skip link's target is "main:content": slug() drops ":", so no heading id can take it (a "## Content" is "content").
  const outline = (cls, label) => heads.length < 2 ? '' : `<ol class="cad-nav-outline${cls}"${label ? ' aria-label="On this page"' : ''}>${heads.map(h =>
    `<li class="h${h.level}"><a href="#${esc(encodeURIComponent(h.id))}">${h.text}</a></li>`).join('')}</ol>`;
  const tree = SECTIONS.map(s => {
    const list = pages.filter(q => q.section === s.id);
    if (!list.length) return '';
    return `<details class="cad-nav-group"${s.id === p.section ? ' open' : ''}><summary>${esc(s.title)}</summary><ul>${list.map(q =>
      `<li><a href="${esc(pageURL(q.file))}"${q.file === p.file ? ` aria-current="page">${esc(q.title)}</a>${outline('', true)}` : `>${esc(q.title)}</a>`}</li>`).join('')}</ul></details>`;
  }).join('');
  const nav = `<cad-nav for=".prose" rail=".doc-rail" role="navigation" aria-label="Pages and contents"><details class="cad-nav-fold"><summary class="cad-nav-toggle">Pages and contents</summary><div class="cad-nav-panel"><input type="search" class="cad-nav-filter" placeholder="Filter pages" aria-label="Filter pages"><p class="cad-nav-empty" role="status"></p>${tree}</div></details></cad-nav>`;
  const rail = heads.length < 2 ? '' : `<nav class="doc-rail" aria-labelledby="rail-title"><p class="doc-rail-title" id="rail-title">On this page</p>${outline(' cad-nav-rail', false)}</nav>`;
  docPages.push([dest, frame({ title: p.title, body: `<div class="doc-layout">${nav}<div class="doc-main" id="main:content" tabindex="-1">${crumbs}<article class="prose">${html}</article>` + feedbackBox(p.title, pageURL(p.file), p.file) + `</div>${rail}</div>`, md: '/' + publicPath(p.file), description: p.summary, current: pageURL(p.file), updated: lastChange(p.file), css: ['/kit/nav.css', ...(html.includes('class="ref-cite') ? ['/web/references.css'] : [])] })]);
  visuals.set(p.file, (html.match(VISUAL) || []).length);
  p.html = html;                                                      // the catalogue takes each page's first figure
  p.updated = lastChange(p.file);
}
// All rendered image sources are known before any twin is rewritten, independent of page traversal order.
for (const p of allPages) await writeFile(path.join(out, publicPath(p.file)), twinMd(p.file, p.src));
placeVisuals.checkLinks(file => pages.find(q => q.file === file)?.html);   // band tiles' links to other pages' headings
// Every Mermaid block drawn once in each of the site's themes and written into its page as two finished figures, which
// web/site.css shows one of (#305). A block left as it is (no browser, or one Mermaid cannot draw) is drawn by
// kit/diagrams.js in the reader's browser, in the page's theme.
const drawIn = theme => drawDiagrams(docPages.map(([, html]) => html), {
  kit: f => readBuf(`software/cadagent/webkit/${f}`), site: f => readBuf(`${ASSETS}/${f}`), theme, client: CLIENT_DIAGRAMS,
  cacheDir: process.env.CAD_AGENT_DIAGRAM_CACHE || path.join(toolsHere, '.cache', 'site-diagrams'),
});
const drawnLight = await drawIn('light'), drawnDark = await drawIn('dark'), leftBlocks = new Set();
for (const [dest, html] of docPages) await writeFile(dest, drawBoth(html, drawnLight, drawnDark, leftBlocks));
const diagrams = { stats: { ...drawnLight.stats, cached: drawnLight.stats.cached + drawnDark.stats.cached, drawn: drawnLight.stats.drawn + drawnDark.stats.drawn,
  left: leftBlocks.size } };
// Images referenced by docs.
for (const f of publishedImages) await copyTracked(f, path.join(out, f));

// Catalogue: catalog.json, catalog/index.json, catalog/<area>.json, the covers and the page (tools/site/compiler/site-catalog.mjs).
const SNAP = snapDemo();                 // geometry-driven animation: tools/site/compiler/snap-demo.mjs
const { catalog, files: catalogFiles, body: catalogBody, counts } = await buildCatalog({
  ORIGIN, REPO, revision, built: committed, tagline: TAGLINE, description: LEDE, commands, cli, upstreams, landscape, pages, pageURL, publicPath, safeUrl,
  areas: YAML.parse(await read('docs/areas.yaml')), data: YAML.parse(await read('docs/catalog.yaml')) || {}, tracked, read: readBuf,
  securityReport: JSON.parse(await read('docs/research/security-report.json')),
  snap: SNAP, cliUpdated: lastChange('software/cadagent/cli.py'), draft: WORKTREE,
});
for (const [f, text] of catalogFiles) { await mkdir(path.dirname(path.join(out, f)), { recursive: true }); await writeFile(path.join(out, f), text); }
// Each ### entry in a lesson file is one lesson (docs/lessons/README.md#lesson-format); the area READMEs are maps, not lessons.
const lessonCount = pages.filter(p => p.section === 'lessons' && !/(?:^|\/)README\.md$/.test(p.file))
  .reduce((n, p) => n + (p.body.replace(/```[\s\S]*?```/g, '').match(/^### /gm) || []).length, 0);
await writeFile(path.join(out, 'catalog.html'), frame({ title: 'Catalogue', body: catalogBody, current: '/catalog', page: 'catalog',
  description: `${catalog.items.length} open-source projects, libraries, benchmarks, demos, tools, guides and lessons for agentic CAD, by area of hardware design.`,
  css: ['/kit/gallery.css', '/web/catalog.css'] }));

// A derived search view: no new source identity and no mutation of the catalogue/reference machine feeds.
const discovery = discoveryModel({ catalog, pages, references: refModel, ORIGIN, revision, pageURL });
await writeFile(path.join(out, 'discovery.json'), JSON.stringify(discovery) + '\n');
await writeFile(path.join(out, 'explore.html'), frame({ title: 'Explore', current: '/explore', page: 'discovery',
  description: 'Find tools, guides, practical lessons and reference records by topic.',
  body: discoveryHTML(discovery, { areas: YAML.parse(await read('docs/areas.yaml')) }),
  md: '/explore.md', css: ['/kit/gallery.css', '/web/catalog.css', '/web/discovery.css'] }));
await writeFile(path.join(out, 'explore.md'), '# Explore hardware knowledge\n\nSearch: ' + ORIGIN + '/explore\n\n'
  + '- [Full catalogue](/catalog)\n- [Toolkit and Python API](/docs/toolkit)\n- [Reference evidence](/references)\n- [Review pitfalls](/docs/common-issues)\n- [Tool landscape](/research/landscape)\n\n'
  + 'Derived search metadata: /discovery.json. Existing source IDs, evidence and adoption decisions remain separate.\n');

// The reference pages and their twins, and catalog/references/*.json (no record is a catalogue entry).
// CAD_AGENT_REFERENCES_HEALTH: the weekly link check's JSON (its references-health artifact), to show each record's
// link health in catalog/references/*.json. Health is not kept in git (#323), so a build without it shows none.
const refHealth = process.env.CAD_AGENT_REFERENCES_HEALTH
  ? healthOf(JSON.parse(await readFile(process.env.CAD_AGENT_REFERENCES_HEALTH, 'utf8'))) : null;
const refSite = referenceSite(refModel, { ORIGIN, revision, built: committed, feedbackBox, health: refHealth });
for (const [f, text] of refSite.files) { await mkdir(path.dirname(path.join(out, f)), { recursive: true }); await writeFile(path.join(out, f), text); }
// They change with the registry and the topic tree: their last commit (null in a draft with either changed).
const REF_SOURCES = ['docs/research/references.yaml', 'docs/research/references', 'docs/areas.yaml'];
const refsUpdated = WORKTREE && git('status', '--porcelain', '--', ...REF_SOURCES) ? null : git('log', '-1', '--format=%cI', 'HEAD', '--', ...REF_SOURCES) || committed;
for (const p of refSite.pages) {
  await mkdir(path.dirname(path.join(out, p.file)), { recursive: true });
  await writeFile(path.join(out, p.file), frame({ title: p.title, body: p.body, md: '/' + p.md, description: p.description, current: p.url,
    page: 'references', css: ['/web/references.css'], updated: refsUpdated }));
  await writeFile(path.join(out, p.md), p.markdown);
}

// Cards on the landing page.
const STATUS_NOTE = { ours: 'built here', adopted: 'adopted', trial: 'in trial', candidate: 'candidate', rejected: 'rejected', used: 'used', reference: 'tracked', unverified: 'unverified' };
const card = i => `<li class="card" data-type="${esc(i.type)}" data-text="${esc((i.name + ' ' + (i.summary || '') + ' ' + (i.license || '')).toLowerCase())}">
<a href="${esc(safeUrl(i.url))}"><span class="card-name">${esc(i.name)}</span></a>
<span class="pill pill-${esc(i.status)}">${esc(STATUS_NOTE[i.status] || i.status)}</span>${i.license ? `<span class="pill">${esc(i.license)}</span>` : ''}${i.stars ? `<span class="pill">★ ${Number(i.stars).toLocaleString('en-US')}</span>` : ''}
<p>${esc(i.summary || '')}</p>${i.policy && i.policy !== i.summary ? `<p class="policy">${esc(i.policy)}</p>` : ''}${i.markdown ? `<a class="md" href="${esc(i.markdown.replace(ORIGIN, ''))}">.md</a>` : ''}</li>`;
// Landing page: the real model first, then real outputs, then where cad-agent fits (docs/home.yaml), then the map.
const skillCards = pages.filter(p => p.section === 'skills' || p.section === 'agents');
await writeFile(path.join(out, 'web', 'snap-demo.css'), SNAP.css);
const home = YAML.parse(await read('docs/home.yaml'));
const areasTree = YAML.parse(await read('docs/areas.yaml'));
const LADDER = areasTree.maturity.map(m => m.level);
const areaMaturity = new Map();
for (const d of areasTree.domains) for (const a of d.areas || []) areaMaturity.set(a.slug, a.maturity);
// A home link is a published page (repo path) or a full URL; a picture is a committed image, sized so nothing jumps.
const homeHref = (h, at) => {
  if (/^https:\/\//.test(h)) return h;
  if (!pageFiles.has(h)) throw new Error(`docs/home.yaml ${at}: ${h} is not a published page`);
  return pageURL(h);
};
const homeImg = async (src, at, attrs = '') => {
  if (!tracked.includes(src) || !/^docs\/img\/.*\.(svg|png|jpe?g|webp)$/.test(src)) throw new Error(`docs/home.yaml ${at}: ${src} is not a committed picture under docs/img/`);
  const size = imageSize(await readBuf(src), src);
  if (!size) throw new Error(`docs/home.yaml ${at}: cannot read the size of ${src}`);
  return `<img src="/${esc(src)}" width="${size.width}" height="${size.height}"${attrs}>`;
};
// What each output was computed on, said on its tile (#182 review: not every picture is a real part): ON, from
// tools/site/compiler/site-pages.mjs, which the doc pages' figures use too.
// A tool on a tile is a cad-agent command, a cadagent module or a script under tools/, and it must exist.
const commandNames = new Set(commands.map(c => c.name));
const realTool = (tool, at) => {
  const cmd = tool.match(/^cad-agent ([a-z0-9-]+)$/)?.[1], mod = tool.match(/^cadagent(?:\.[a-z_]+)+$/)?.[0];
  const ok = cmd ? commandNames.has(cmd) : mod ? [`software/${mod.replace(/\./g, '/')}.py`, `software/${mod.replace(/\./g, '/')}/__init__.py`].some(f => tracked.includes(f))
    : /^tools\/[\w./-]+$/.test(tool) && tracked.includes(tool);
  if (!ok) throw new Error(`docs/home.yaml ${at}: ${tool} is not a cad-agent command, a cadagent module or a script under tools/`);
  return tool;
};
// Gyropup's FEA numbers come from its summary (docs/img/gyropup/SOURCE.json, written by tools/gyropup_showcase.py):
// a caption that does not quote them fails the build, so a new export cannot leave an old number on the page.
const gyropupSource = JSON.parse(await read('docs/img/gyropup/SOURCE.json'));
const checkNumbers = (r, at) => {
  const fea = gyropupSource.pictures[path.basename(r.img).replace(/\.\w+$/, '')];
  if (!r.img.startsWith('docs/img/gyropup/') || !fea?.safety_factor) return;
  // Whole numbers only: 3.1 does not pass inside 3.15, nor 52,134 inside 152,134.
  const quotes = n => new RegExp(`(?<![\\d.,])${n.replace(/[.,]/g, '\\$&')}(?![\\d]|[.,]\\d)`).test(r.caption);
  for (const n of [fea.tets.toLocaleString('en-US'), String(fea.safety_factor), Number(fea.target).toFixed(1)])
    if (!quotes(n)) throw new Error(`docs/home.yaml ${at}: the caption does not quote ${n} from docs/img/gyropup/SOURCE.json`);
};
const reel = [], homeMd = { reel: [], ours: [] };
for (const [i, r] of home.reel.entries()) {
  const at = `reel[${i}]`;
  for (const k of ['img', 'tool', 'title', 'caption', 'alt', 'href', 'on']) if (!r[k]) throw new Error(`docs/home.yaml ${at} has no ${k}`);
  if (!ON[r.on]) throw new Error(`docs/home.yaml ${at}: on is one of ${Object.keys(ON).join(', ')}`);
  checkNumbers(r, at);
  homeMd.reel.push(`- [${r.title}](${/^https:/.test(r.href) ? r.href : ORIGIN + pageURL(r.href)}): ${r.caption} (\`${r.tool}\`, on ${ON[r.on].replace(/<[^>]+>/g, '')})`);
  reel.push(`<li class="reel-tile${r.fit === 'cover' ? ' reel-cover' : ''}"><a class="reel-media" href="${esc(homeHref(r.href, at))}" tabindex="-1" aria-hidden="true">${await homeImg(r.img, at, ` alt="" loading="lazy" decoding="async"`)}</a>
<p class="reel-tool"><code>${esc(realTool(r.tool, at))}</code></p><h3><a href="${esc(homeHref(r.href, at))}">${esc(r.title)}</a></h3><p>${esc(r.caption)}</p><p class="reel-credit">On ${ON[r.on]}</p>
<span class="visually-hidden">${esc(r.alt)}</span></li>`);
}
// The snap-fit demo is drawn from its geometry in this build (tools/site/compiler/snap-demo.mjs), so it joins the reel inline.
reel.splice(3, 0, `<li class="reel-tile reel-snap"><a class="reel-media" href="/docs/compliant" tabindex="-1" aria-hidden="true">${SNAP.svg}</a>
<p class="reel-tool"><code>cad-agent snapfit</code></p><h3><a href="/docs/compliant">One part, no screws</a></h3><p>A cantilever snap fit animated from its own geometry: contact and root strain computed against the material and the print's layer direction.</p><p class="reel-credit">Drawn by this site's build from the snap-fit geometry</p></li>`);
const fitsTile = async (t, i) => {
  const at = `fits.ours[${i}]`;
  const levels = t.maturity ? [t.maturity] : (t.areas || []).map(a => {
    if (!areaMaturity.has(a)) throw new Error(`docs/home.yaml ${at}: no area ${a} in docs/areas.yaml`);
    return areaMaturity.get(a);
  });
  if (!levels.length || levels.some(l => !LADDER.includes(l))) throw new Error(`docs/home.yaml ${at}: a maturity on the ladder (${LADDER.join(', ')}), from areas or stated with a why`);
  if (t.maturity && !t.why) throw new Error(`docs/home.yaml ${at}: a stated maturity needs its why`);
  const level = levels.reduce((lo, l) => LADDER.indexOf(l) < LADDER.indexOf(lo) ? l : lo);      // the least mature area decides
  homeMd.ours.push(`- [${t.title}](${/^https:/.test(t.href) ? t.href : ORIGIN + pageURL(t.href)}) (${level}): ${t.does}`);
  const step = LADDER.indexOf(level);
  return `<li class="fit-tile"><a href="${esc(homeHref(t.href, at))}">${t.img ? `<span class="fit-media">${await homeImg(t.img, at, ' alt="" loading="lazy" decoding="async"')}</span>`
  : t.cmd ? `<span class="fit-media fit-cmd"><code>$ ${esc(t.cmd)}</code></span>`
  : step === 0 ? '<span class="fit-media fit-empty">not built yet</span>' : (() => { throw new Error(`docs/home.yaml ${at}: a built block needs an img or a cmd`); })()}
<span class="fit-title">${esc(t.title)}</span></a><p>${esc(t.does)}</p>
<p class="ladder" title="${esc(t.why || `the least mature of: ${t.areas.join(', ')}`)}"><span class="visually-hidden">Maturity: </span>${LADDER.map((l, k) => `<span class="rung${k <= step ? ' on' : ''}${k === step ? ' here' : ''}"${k === step ? '' : ' aria-hidden="true"'}>${k === step ? esc(l) : ''}</span>`).join('')}</p></li>`;
};
const upstreamByName = new Map(upstreams.map(u => [u.name, u]));
const makeChip = (m, i) => {
  const u = m.upstream && upstreamByName.get(m.upstream);
  if (m.upstream && !u) throw new Error(`docs/home.yaml fits.make[${i}]: ${m.upstream} is not in software/vendor/upstreams/registry.yaml`);
  return `<li><span class="make-name"><a href="${esc(homeHref(m.href, `fits.make[${i}]`))}"><b>${esc(m.name)}</b></a>${u ? ` <span class="pill pill-${esc(u.status)}">${esc(STATUS_NOTE[u.status] || u.status)}</span><span class="pill">${esc(u.license)}</span><span class="pill" title="GitHub stars when surveyed">★ ${Number(u.stars).toLocaleString('en-US')}</span>` : ''}</span><span>${esc(m.does)}</span>${m.note ? `<small>${esc(m.note)}</small>` : ''}</li>`;
};
const testCount = git('grep', '-c', '-E', '^\\s*def test_', 'HEAD', '--', 'tests/*.py').split('\n').filter(Boolean)
  .reduce((n, l) => n + Number(l.split(':').pop()), 0);
// The hero model (web/models/, from tools/gyropup_showcase.py) and its still poster (tools/site/figures/site-model-poster.mjs).
const heroModel = JSON.parse(await read(ASSETS + '/models/gyropup.json'));
const poster = imageSize(await readBuf(ASSETS + '/models/gyropup.webp'), 'gyropup.webp');
if (!poster) throw new Error('web/models/gyropup.webp: run node tools/site/figures/site-model-poster.mjs');
// One checked installation guide per platform, or one line to paste into an agent. Keep checksum/immutable-source
// instructions canonical in agent-workflow.md; agent-prompt.txt and the README route readers there too.
const agentPrompt = await read('docs/agent-prompt.txt');
const [pasteLine, agentGuide] = (([first, ...rest]) => [first, rest.join('\n').trim()])(agentPrompt.split('\n'));
const INSTALL = [['unix', 'macOS / Linux', '/docs/agent-workflow#install-unix'], ['win', 'Windows', '/docs/agent-workflow#install-windows']];
const USE_STEPS = [['Install', 'verify first'], ['Find', 'the tool in llms.txt'], ['Build', 'with tested checks'], ['Give back', 'a PR or an issue']];
const useLoop = `<svg class="use-loop" viewBox="0 0 400 132" role="img" aria-label="The loop it sets up: install, find the tool, build with tested checks, give back what was learned, so the next agent finds more">
<defs><marker id="use-arrow" viewBox="0 0 8 8" refX="7" refY="4" markerWidth="7" markerHeight="7" orient="auto"><path class="tip" d="M0 0L8 4L0 8z"/></marker></defs>
${USE_STEPS.map(([t, d], i) => `<g transform="translate(${8 + i * 98} 10)"><rect class="box${i === 3 ? ' out' : ''}" width="86" height="74" rx="14"/><text class="num" x="43" y="26" text-anchor="middle" font-size="22" font-weight="750">${i + 1}</text><text class="name" x="43" y="47" text-anchor="middle" font-size="12" font-weight="700">${esc(t)}</text><text class="sub" x="43" y="62" text-anchor="middle" font-size="8.5">${esc(d)}</text></g>${i < 3 ? `<path class="flow" d="M${96 + i * 98} 47h8" stroke-width="2" marker-end="url(#use-arrow)"/>` : ''}`).join('')}
<path class="flow" d="M345 86v18a8 8 0 0 1-8 8H59a8 8 0 0 1-8-8v-14" fill="none" stroke-width="2" stroke-dasharray="4 4" marker-end="url(#use-arrow)"/>
<text class="sub" x="200" y="128" text-anchor="middle" font-size="10">the next agent finds what this one learned</text></svg>`;
// The card's heading is the README's too (tests/site/website-build.test.mjs).
const USE_HEADING = 'Build with your favorite AI agent';
// Where the skills work. Names only, in plain text badges: no product marks, and no endorsement implied. They read
// ~/.claude/skills or ~/.agents/skills, where the installer puts them (cadagent/agentkit.py, docs/practice/agent-workflow.md).
const AGENTS = [['Claude Code', 'CC'], ['Codex CLI', 'Cx'], ['Copilot CLI', 'Co'], ['Cursor', 'Cu'], ['Gemini CLI', 'Ge'], ['opencode', 'oc']];
const useCard = `<section class="use-band" id="use-it" aria-labelledby="use-title"><div class="wrap"><div class="use-card">
<div class="use-head"><p class="eyebrow">Download, verify, install</p><h2 id="use-title">${esc(USE_HEADING).replace(/AI agent$/, '<span>AI agent.</span>')}</h2>
<div class="os-tabs">${INSTALL.map(([id], i) => `<input type="radio" name="install-os" id="os-${id}" class="visually-hidden"${i === 0 ? ' checked' : ''}>`).join('')}
<div class="os-tab-row" aria-hidden="true">${INSTALL.map(([id, name]) => `<label for="os-${id}" class="os-tab tab-${id}">${esc(name)}</label>`).join('')}</div>
${INSTALL.map(([id, name, href]) => `<div class="os-panel panel-${id}"><a class="install-guide" href="${esc(href)}">Install on ${esc(name)} →</a></div>`).join('')}</div>
<p class="use-lead">Then ask your agent for a part, check or simulation.</p>
<ul class="agent-badges" aria-label="Agents it works with">${AGENTS.map(([name, mark]) => `<li><span class="agent-badge"><span class="agent-mark" aria-hidden="true">${esc(mark)}</span>${esc(name)}</span></li>`).join('')}</ul></div>
<div class="use-paste"><p class="paste-title">Or paste this into your agent:</p>
<cad-copy class="agent-copy" label="Copy prompt"><pre class="agent-box" aria-label="The line to paste into your agent">${esc(pasteLine)}</pre></cad-copy>
${useLoop}
<p class="use-note">No telemetry. Your agent sends what it learns as a pull request or issue, only when you say yes. <a href="/docs/agent-workflow#install">Install by hand</a> · Names belong to their owners; no endorsement implied.</p></div>
</div></div></section>`;
const landing = `<div class="wrap"><section class="hero hero-3d">
<div class="hero-head"><p class="eyebrow"><span class="status-dot"></span>Open source · for agents and people</p>
<h1>Your one stop shop for <span>agentic CAD.</span></h1>
<p class="intro">AI helping AI build anything you want.</p>
<p class="intro-sub">cad-agent is a free toolkit your AI assistant installs in one line. It helps the AI design real, physical things, check them for problems before anything is made, and, with your OK, share what it learns as a pull request, so every AI that uses it gets better at building for people.</p></div>
<figure class="hero-model"><cad-model src="/web/models/gyropup.json" label="Gyropup" style="aspect-ratio:${poster.width}/${poster.height}"><img class="cad-model-poster" src="/web/models/gyropup.webp" width="${poster.width}" height="${poster.height}" fetchpriority="high" alt="Gyropup, a wheel-legged robot with a foam-ball turret"></cad-model>
<figcaption><span><b>Gyropup</b>, the current CAD assembly${heroModel.source?.left_out?.length ? ' (internal parts and fasteners hidden)' : ''}.</span><span><a href="https://gyropup.com">gyropup.com</a> · <a href="${esc(heroModel.source.repo + '/tree/' + heroModel.source.revision)}">CAD source</a> · MIT · drag to turn</span></figcaption></figure>
<div class="hero-actions"><div class="actions"><a class="button primary" href="#use-it">Copy this to your agent <span>↓</span></a><a class="button" href="/explore">Explore the knowledge</a><a class="button quiet" href="${REPO}">GitHub ↗</a></div>
</div>
</section></div>
${useCard}
<section class="reel-band" id="outputs"><div class="wrap"><div class="lead"><h2>What the code <span>computes.</span></h2><p>Outputs of cad-agent's tools with the numbers they computed: on Gyropup, on a printed enclosure, on this repo's test fixtures and on worked examples. Each tile says which, and opens the page that explains it.</p></div>
<ul class="reel">${reel.join('')}</ul></div></section>
<div class="wrap"><section class="section fits" aria-labelledby="fits-title"><div class="lead"><h2 id="fits-title">Where cad-agent <span>fits.</span></h2><p>Other people's tools make the model. text-to-cad, which we are trialling, writes and exports models, but <a href="/research/landscape#2-deep-dive-earthtojaketext-to-cad-v0726-2026-10-20">its code computes no stress, fatigue or safety factor</a>. cad-agent's engineering is Python with ${testCount.toLocaleString('en-US')} test functions in CI. Each block shows how far it has got.</p></div>
<div class="fits-make"><p class="fits-label">Make: other people's tools we build on or are trialling, credited</p><ul>${home.fits.make.map(makeChip).join('')}</ul></div>
<p class="fits-arrow" aria-hidden="true"><span>STEP, 3MF, boards</span></p>
<div class="fits-ours"><p class="fits-label">Check, simulate, explain, measure: cad-agent</p><ul>${(await Promise.all(home.fits.ours.map(fitsTile))).join('')}</ul>
<p class="fits-key">Maturity: ${areasTree.maturity.map(m => `<b>${esc(m.level)}</b> ${esc(m.means)}`).join('; ')}. From <a href="${REPO}/blob/dev/docs/areas.yaml">docs/areas.yaml</a>.</p></div></section>
<section class="section" style="padding-top:0"><div class="missions">
<a class="mission mission-blue" href="/research/landscape"><span class="mission-tag">Map</span><span class="mission-num">${(counts.upstream || 0) + (counts.library || 0) + (counts.benchmark || 0)}</span><p>Agentic-CAD projects, libraries and benchmarks, checked with dates and licences.</p><span class="go">See the landscape <span>→</span></span></a>
<a class="mission mission-yellow" href="/docs/toolkit"><span class="mission-tag">Demonstrate</span><span class="mission-num">${counts.tool || 0}</span><p>Commands that run on real projects: gates, holes, FEA, CFD, topology, slicing, the 3D viewer.</p><span class="go">Open the tools <span>→</span></span></a>
<a class="mission mission-orange" href="/docs/common-issues"><span class="mission-tag">Fill the gaps</span><span class="mission-num">${lessonCount}</span><p>Lessons from real builds, each with the incident behind it and the check that catches it.</p><span class="go">Read the pitfalls <span>→</span></span></a>
</div></section>
<section class="section built-with" style="padding-top:0"><div class="lead"><h2>Built with <span>cad-agent.</span></h2><p>Real projects are the test bench: every tool here was needed by one of them first.</p></div>
<ul class="projects"><li><a href="https://gyropup.com">${await homeImg('docs/img/gyropup.jpg', 'projects', ' alt="Gyropup, a wheel-legged robot with a turret, rendered" loading="lazy" decoding="async"')}<b>Gyropup</b></a><p>A wheel-legged foam-ball battle robot, designed, simulated and documented by agents with this toolkit. MIT.</p></li>
<li><a href="https://github.com/mvalancy/j501-agx-orin">${await homeImg('docs/img/viewer.jpg', 'projects', ' alt="The J501 enclosure in the kit\'s 3D viewer, with its parts list" loading="lazy" decoding="async"')}<b>J501 AGX Orin enclosure</b></a><p>A printed enclosure and cooler for a Jetson AGX Orin carrier, where most of the lessons came from.</p></li></ul></section>

<section class="section skills-row" style="padding-top:0"><div class="lead"><h2>Skills your agents <span>can load.</span></h2><p>The installer puts them where Claude Code, Codex and the other agents look (<code>~/.claude/skills</code>, <code>~/.agents/skills</code>). <a href="/docs/agent-workflow">How they work together →</a></p></div>
<ul class="skill-chips">${skillCards.map(p => `<li><a href="${esc(pageURL(p.file))}"><b>${esc(p.title)}</b><span class="pill">${p.section === 'agents' ? 'subagent' : 'skill'}</span></a><a class="skill-md" href="/${esc(publicPath(p.file))}" aria-label="${esc(p.title)} as Markdown">.md</a></li>`).join('')}</ul></section>
<section class="section help-band"><div class="lead"><h2>Help us <span>improve!</span></h2><p>Found a mistake, a better tool, or a page that wasted your time? It takes a minute, and ideas we use are credited by name.</p></div>
<div class="help-actions"><a class="button primary" href="${esc(feedbackURL('home page', '/'))}">Give feedback</a><a class="button" href="${REPO}/issues">See open issues</a><a class="button" href="/CONTRIBUTING">How to contribute</a></div></section></div>`;
await writeFile(path.join(out, 'index.html'), frame({ title: TAGLINE, body: landing, md: '/index.md', current: '/', page: 'landing', css: ['/web/snap-demo.css', '/kit/model.css'] }));

// ----------------------------------------------------------------------------- agent files
const bySection = id => pages.filter(p => p.section === id);
const llms = `# cad-agent

> ${TAGLINE}. ${LEDE}

cad-agent is an open-source toolkit and knowledge base for AI agents that design hardware: CAD models, assemblies,
simulation and print releases. It maps the best free tools, demonstrates them on real projects and fills the gaps with
tested tools of its own. Every page on this site has a Markdown twin at the same path with a .md extension.

- Source: ${REPO} (MIT). Install and use: the checked guide below (then \`cad-agent update\` to update).
  cad-agent collects no telemetry.
- Machine-readable catalogue: ${ORIGIN}/catalog.json (schema ${catalog.schema}; ${catalog.items.length} entries, each with an id, kind,
  areas, maturity, a one-line \`what\`, our \`notes\`, a cover picture, a demo link and related ids; tools also have \`doc\`,
  the page that documents the command, and \`markdown\`, its twin). Every schema-1 field keeps its schema-1 value: \`summary\`
  is still our notes first for outside projects, a tool's \`url\` is still ${ORIGIN}/docs/toolkit, and a field that was null
  is still null. Each file says what its fields mean in \`fields\`; catalog.json's \`fields.removed\` names the fields taken out
  within schema 2, which no reader should rely on.
- Find your way in two small fetches: ${ORIGIN}/catalog/index.json lists the domains and areas of hardware design
  (docs/areas.yaml) with counts, maturity and links; ${ORIGIN}/catalog/<area>.json (e.g. catalog/compliant-mechanisms.json)
  lists every tool, page, lesson, skill, demo and outside project in that area. Outside entries not yet placed in an area:
  ${ORIGIN}/catalog/unplaced.json. The page takes the same filters as URL parameters, e.g.
  ${ORIGIN}/catalog?kind=tools&area=compliant-mechanisms&sort=stars.
- Full text of every page in one file: ${ORIGIN}/llms-full.txt
- Built from commit ${revision}.

## Install and work with it

People install with the platform's [pinned download and checksum-before-execution block](${ORIGIN}${pageURL('docs/practice/agent-workflow.md')}#install),
or paste this line into their agent, followed by what they want made:

\`\`\`text
${pasteLine}
\`\`\`

An agent that read that line, or found this file, does this:

\`\`\`text
${agentGuide}
\`\`\`

## Start here

- [README](${ORIGIN}/README.md): what cad-agent is and how it grows
- [Tools](${ORIGIN}/docs/toolkit.md): every command, the project contract and the Python API
- [Agent workflow](${ORIGIN}/${publicPath("docs/practice/agent-workflow.md")}): skills, subagents, work claims and crash-safe work
- [Common issues](${ORIGIN}/${publicPath("docs/practice/common-issues.md")}): recurring CAD mistakes and the checks that catch them
- [Landscape](${ORIGIN}/${publicPath("docs/research/agent-workflow/landscape.md")}): the agentic-CAD tools we track, verified

${SECTIONS.map(s => `## ${s.title}\n\n${bySection(s.id).map(p => `- [${p.title}](${ORIGIN}/${publicPath(p.file)}): ${p.summary.replace(/\s+/g, ' ').slice(0, 200)}`).join('\n')}`).join('\n\n')}

## Commands

${commands.map(c => `- \`cad-agent ${c.name}\`: ${c.help}`).join('\n')}

${refSite.llms}
`;
await writeFile(path.join(out, 'llms.txt'), llms);
// The home page's twin: llms.txt, then what the page shows beside it (the reel and where cad-agent fits), in words.
const fitsMake = home.fits.make.map(m => { const u = m.upstream && upstreamByName.get(m.upstream); return `- ${m.name}${u ? ` (${u.license}, ${STATUS_NOTE[u.status] || u.status})` : ''}: ${m.does}`; });
await writeFile(path.join(out, 'index.md'), `${llms.replace(/\n*$/, '\n')}
## On the home page

### What the code computes

${homeMd.reel.join('\n')}

### Where cad-agent fits

Other people's tools make the model (we build on them or are trialling them):

${fitsMake.join('\n')}

cad-agent checks, simulates, explains and measures around it (maturity: ${LADDER.join(' → ')}, from docs/areas.yaml):

${homeMd.ours.join('\n')}
`);
await writeFile(path.join(out, 'llms-full.txt'), `# cad-agent: full text\n\n> ${TAGLINE}. ${LEDE}\n\n` +
  pages.map(p => `\n\n---\n\nSource: ${ORIGIN}/${publicPath(p.file)}\n\n${twinMd(p.file, p.body, true).trim()}\n`).join(''));
// Cloudflare Pages joins the values of a header set by more than one matching rule, so each header is set by one rule
// only: security headers on /*, Cache-Control only on /kit/vendor/*. Those stable URLs can change between releases,
// so they revalidate, like the Pages default for everything else. The site's own pages have no inline script;
// the kit's viewer pages have an import map and a module
// script each, allowed by hash. Styles allow inline for the diagram kit's SVG output; wasm for the STEP reader.
const htmlFiles = async d => (await readdir(d, { withFileTypes: true, recursive: true }))
  .filter(e => e.isFile() && e.name.endsWith('.html')).map(e => path.join(e.parentPath, e.name));
// Only the kit's own pages (copied byte for byte from software/cadagent/webkit/) may carry inline script, so only their
// hashes go into the policy; any inline script on a site page stops the build.
const inlineHashes = new Set();
// Every <script> tag is looked at (any attributes, `</script >`, an unclosed one): a script with a src may not also
// have a body, and an inline one is only allowed on the kit's pages.
const SCRIPT = /<script\b([^>]*)>([\s\S]*?)(<\/script\s*>|$)/gi;
for (const f of await htmlFiles(out)) {
  const where = path.relative(out, f), kit = where.split(path.sep)[0] === 'kit';
  for (const m of (await readFile(f, 'utf8')).matchAll(SCRIPT)) {
    if (!m[3]) throw new Error(`${where}: unclosed <script>`);
    if (/(?:^|\s)src\s*=/i.test(m[1])) { if (m[2].trim()) throw new Error(`${where}: <script src> with a body`); continue; }
    if (!m[2].trim()) continue;
    if (!kit) throw new Error(`${where}: inline <script> on a site page (only the kit's pages may have one)`);
    inlineHashes.add(`'sha256-${createHash('sha256').update(m[2]).digest('base64')}'`);
  }
}
export const CSP = `default-src 'self'; script-src 'self' ${[...inlineHashes].sort().join(' ')} 'wasm-unsafe-eval'; style-src 'self' 'unsafe-inline'; ` +
  "img-src 'self' data: blob:; font-src 'self' data:; connect-src 'self'; worker-src 'self' blob:; object-src 'none'; base-uri 'self'; " +
  "form-action 'self'; frame-ancestors 'self'";
// Cloudflare Pages redirects: each moved page and its Markdown twin, to the new path.
await writeFile(path.join(out, '_redirects'), redirects.flatMap(([from, to]) =>
  [`/${from.replace(/\.md$/, '')} /${publicPath(to).replace(/\.md$/, '')} 301`, `/${from} /${publicPath(to)} 301`]).join('\n') + (redirects.length ? '\n' : ''));
// The kit's own pages (kit/*.html) are copied byte for byte from the kit, so they cannot carry a canonical <link>;
// Pages sends it as a Link header instead, at the pretty URL Pages serves them on (/kit/viewer, not /kit/viewer.html).
const kitPages = (await readdir(path.join(out, 'kit'))).filter(f => f.endsWith('.html')).sort().map(f => '/kit/' + f.replace(/\.html$/, ''));
await writeFile(path.join(out, '_headers'), [
  '/*', '  X-Content-Type-Options: nosniff', '  Referrer-Policy: strict-origin-when-cross-origin', `  Content-Security-Policy: ${CSP}`,
  '  Permissions-Policy: camera=(), microphone=(), geolocation=(), payment=(), usb=()', '  Cross-Origin-Opener-Policy: same-origin',
  '  Strict-Transport-Security: max-age=31536000',
  '/*.md', '  Content-Type: text/markdown; charset=utf-8', '/llms.txt', '  Content-Type: text/plain; charset=utf-8',
  '/llms-full.txt', '  Content-Type: text/plain; charset=utf-8', '/install.sh', '  Content-Type: text/plain; charset=utf-8',
  '/install.ps1', '  Content-Type: text/plain; charset=utf-8', '/kit/vendor/*', '  Cache-Control: public, max-age=0, no-cache, must-revalidate',
  ...kitPages.flatMap(u => [u, `  Link: <${ORIGIN}${u}>; rel="canonical"`]), ''].join('\n'));
await writeFile(path.join(out, 'robots.txt'), `User-agent: *\nAllow: /\nSitemap: ${ORIGIN}/sitemap.xml\n`);
await writeFile(path.join(out, 'sitemap.xml'), '<?xml version="1.0" encoding="UTF-8"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">' +
  ['/', '/explore', '/catalog', ...allPages.map(p => pageURL(p.file)), ...refSite.urls].map(u => `<url><loc>${ORIGIN}${u}</loc></url>`).join('') + '</urlset>\n');
await writeFile(path.join(out, '404.html'), frame({ title: 'Not found', body: '<h1>Not here.</h1><p>Try the <a href="/explore">Explore search</a> or <a href="/llms.txt">llms.txt</a>.</p>' }));
await writeFile(path.join(out, 'version.json'), JSON.stringify({ revision, built: catalog.built, pages: pages.length, folder_maps: folderMapPages.length, items: catalog.items.length }, null, 2) + '\n');
// For agents and the tests: which pages still have nothing to look at.
const noVisual = [...visuals].filter(([, n]) => !n).map(([f]) => f).sort();
await writeFile(path.join(out, 'visuals.json'), JSON.stringify({ pages: Object.fromEntries([...visuals].sort()), without: noVisual }, null, 2) + '\n');
console.log(`Built ${path.relative(root, out) || out}${WORKTREE ? ' (draft: working tree)' : ''}: ${pages.length} editorial pages + ${folderMapPages.length} folder maps (+ Markdown twins), ${catalog.items.length} catalogue entries, ${commands.length} commands. Revision ${revision.slice(0, 12)}. ${noVisual.length} pages have no picture, diagram or demo yet (visuals.json). ` +
  `Diagrams: ${diagrams.stats.diagrams} (Mermaid ${diagrams.stats.mermaid}), ${diagrams.stats.cached} from the cache, ${diagrams.stats.drawn} drawn` +
  `${diagrams.stats.browser ? ` in ${diagrams.stats.browser}` : ''}${diagrams.stats.left ? `, ${diagrams.stats.left} left to the reader's browser` : ''}.`);
