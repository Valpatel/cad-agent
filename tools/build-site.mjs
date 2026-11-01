/** Build cad-agent.valpatel.com into dist/: one static bundle for local preview and Cloudflare Pages.
 *
 * Agent-first: every page has its Markdown source next to it (same path, .md), /llms.txt and /llms-full.txt index
 * everything, and /catalog.json is the machine-readable catalogue (tools, libraries, skills, docs, lessons, research).
 * Only committed files are published: every source is read from HEAD with `git show`, never from the working tree,
 * so an untracked or uncommitted file cannot reach the site. `--worktree` builds a local draft from tracked files as
 * they are on disk (the footer then says so); `--release` refuses a dirty tree.
 */
import { readFile, writeFile, mkdir, rm, readdir } from 'node:fs/promises';
import { readFileSync } from 'node:fs';
import { createHash } from 'node:crypto';
import { execFileSync } from 'node:child_process';
import path from 'node:path';
import { marked } from 'marked';
import YAML from 'yaml';
import { snapDemo } from './snap-demo.mjs';
import { sanitize, safeUrl, rewriteUrls, imageSize } from './site-html.mjs';   // allowlist sanitizer for rendered Markdown

// --root DIR builds another checkout of this repo (the tests use a scratch worktree); the build tools still run from here.
const rootArg = process.argv.indexOf('--root');
const root = path.resolve(rootArg > 0 ? process.argv[rootArg + 1] : path.join(import.meta.dirname, '..'));
const outArg = process.argv.indexOf('--out');
const out = outArg > 0 ? path.resolve(process.argv[outArg + 1]) : path.join(root, 'dist');
const ORIGIN = 'https://cad-agent.valpatel.com';
const REPO = 'https://github.com/Valpatel/cad-agent';
const TAGLINE = 'Your one stop shop for agentic CAD';
const LEDE = 'Mapping the best free resources, demonstrating their capabilities, and filling the gaps. Made for AI and people.';
const WORKTREE = process.argv.includes('--worktree');
const RELEASE = process.argv.includes('--release');
const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
const gitRaw = (...a) => execFileSync('git', a, { cwd: root, maxBuffer: 1 << 28 });
const git = (...a) => gitRaw(...a).toString().trim();
if (RELEASE && git('status', '--porcelain')) throw new Error('--release needs a clean working tree (commit or stash first)');
if (RELEASE && WORKTREE) throw new Error('--release and --worktree are exclusive');
// Production is built from reviewed history only: a commit on origin/main or origin/dev (CD deploys from main).
const onReviewed = ref => { try { execFileSync('git', ['merge-base', '--is-ancestor', 'HEAD', ref], { cwd: root }); return true; } catch { return false; } };
if (RELEASE && !onReviewed('origin/main') && !onReviewed('origin/dev')) throw new Error('--release needs HEAD on origin/main or origin/dev (merged and pushed), so production only shows reviewed commits');
const tracked = git('ls-tree', '-r', '-z', '--name-only', 'HEAD').split('\0').filter(Boolean);
const head = git('rev-parse', 'HEAD');
const revision = head;
// The content is always HEAD's (or the working tree's with --worktree), but the build tools run from disk (from this
// checkout, even with --root): say so when they differ from the built commit's, and never release with them.
const TOOLS = ['tools/build-site.mjs', 'tools/site-html.mjs', 'tools/snap-demo.mjs', 'package.json', 'package-lock.json'];
const toolsHere = path.join(import.meta.dirname, '..');
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
const copyTracked = async (f, dest) => { await mkdir(path.dirname(dest), { recursive: true }); await writeFile(dest, await readBuf(f)); };

await rm(out, { recursive: true, force: true });
await mkdir(out, { recursive: true });
for (const f of tracked.filter(f => f.startsWith('web/'))) await copyTracked(f, path.join(out, f));
// Browsers ask for /favicon.ico on pages without an icon link (llms.txt, the .md twins).
if (tracked.includes('web/favicon.ico')) await copyTracked('web/favicon.ico', path.join(out, 'favicon.ico'));
// The shared web kit (3D viewer, part tables, diagrams) is published as /kit/, the same files projects copy.
for (const f of tracked.filter(f => f.startsWith('src/cadagent/webkit/'))) {
  await copyTracked(f, path.join(out, 'kit', f.slice('src/cadagent/webkit/'.length)));
}

// ----------------------------------------------------------------------------- content
const front = src => {
  const m = src.match(/^---\n([\s\S]*?)\n---\n/);
  return m ? { meta: YAML.parse(m[1]) || {}, body: src.slice(m[0].length) } : { meta: {}, body: src };
};
// Summary: the first prose paragraph (not a heading, badge, image, table, code, HTML or list), else the first list
// item; plain text, cut at a sentence end before 260 characters.
const plain = s => s.replace(/!\[[^\]]*\]\([^)]*\)/g, '').replace(/\[([^\]]+)\]\([^)]*\)/g, '$1')
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

const SECTIONS = [
  { id: 'docs', title: 'Docs', match: f => /^docs\/[^/]+\.md$/.test(f) || f === 'README.md' || f === 'CONTRIBUTING.md' || f === 'THIRD_PARTY_NOTICES.md' },
  { id: 'skills', title: 'Skills', match: f => /^skills\/[^/]+\/SKILL\.md$/.test(f) },
  { id: 'agents', title: 'Subagents', match: f => /^agents\/[^/]+\.md$/.test(f) },
  { id: 'lessons', title: 'Lessons (pitfalls)', match: f => /^lessons\/(?:[a-z0-9-]+\/)?[^/]+\.md$/.test(f) },   // lessons/<area>/
  { id: 'research', title: 'Research', match: f => /^research\/[^/]+\.md$/.test(f) },
];
const pages = [];
// A file that moved keeps a one-line stub at its old path (`<!-- moved-to: new/path.md -->`), so links into the repo
// keep working on GitHub; the site serves a permanent redirect instead of a page.
const moved = [];
for (const file of tracked) {
  const section = SECTIONS.find(s => s.match(file));
  if (!section || /(?:^|\/)(?:AGENTS|CLAUDE)\.md$/.test(file)) continue;
  const src = await read(file);
  const to = src.match(/^<!--\s*moved-to:\s*(\S+?\.md)\s*-->/)?.[1];
  if (to) {
    const target = path.posix.normalize(path.posix.join(path.posix.dirname(file), to));
    if (!tracked.includes(target)) throw new Error(`${file} says it moved to ${target}, which does not exist`);
    moved.push([file, target]);
    continue;
  }
  const { meta, body } = front(src);
  const title = meta.name || body.match(/^#\s+(.+)$/m)?.[1] || file;
  pages.push({ file, section: section.id, title: String(title).replace(/[`*]/g, ''), summary: meta.description || firstPara(body), body, src });
}
const pageURL = f => '/' + f.replace(/\.md$/, '');                  // Cloudflare Pages serves x.html at /x
const pageFile = f => f.replace(/\.md$/, '.html');
const pageFiles = new Set(pages.map(p => p.file));
// Permanent redirects (tools/site-redirects.txt): they outlive the stubs, so deleting a stub never drops a 301.
const redirects = (await read('tools/site-redirects.txt')).split('\n').map(l => l.replace(/#.*/, '').trim()).filter(Boolean)
  .map(l => l.split(/\s+/));
const stubFiles = new Set(moved.map(([from]) => from)), seenFrom = new Set();
for (const [from, to] of redirects) {
  const at = `tools/site-redirects.txt: ${from}`;
  // Pages keeps the first rule for a path and the preview server the last, so a duplicate would make them disagree.
  if (seenFrom.has(from)) throw new Error(`${at} is listed twice`);
  seenFrom.add(from);
  // Pages reads * as a splat and :name as a placeholder, so `lessons/*.md` would redirect every lesson page, the
  // target included, into a loop; the preview server matches exact paths and would never show it. Plain paths only.
  if (!/^[\w-][\w.\/-]*\.md$/.test(from) || path.posix.normalize(from) !== from)
    throw new Error(`${at}: a source is a plain repo path to a .md file (letters, digits, - _ . /), without a leading slash ` +
      'or dot, `.` or `..` segments, `//`, `*` or `:`');
  if (tracked.includes(from) && !stubFiles.has(from)) throw new Error(`${at} is still a file in the repo (only its stub may remain)`);
  if (!to || !pageFiles.has(to)) throw new Error(`${at} -> ${to}, which is not a published page`);
}
for (const [from, to] of moved) {
  if (!pageFiles.has(to)) throw new Error(`${from} says it moved to ${to}, which is not a published page`);
  const listed = redirects.find(([f]) => f === from);
  if (!listed) throw new Error(`${from} moved to ${to}: add "${from} ${to}" to tools/site-redirects.txt`);
  if (listed[1] !== to) throw new Error(`${from} moved to ${to}: change its line in tools/site-redirects.txt (it says ${listed[1]})`);
}

// ----------------------------------------------------------------------------- catalogue
const landscape = JSON.parse(await read('research/landscape.json'));
const upstreams = YAML.parse(await read('upstreams/registry.yaml')) || [];
const cli = await read('src/cadagent/cli.py');
const parserCount = (cli.match(/sub\.add_parser\(/g) || []).length;
const commands = [...cli.matchAll(/sub\.add_parser\("([a-z0-9-]+)",[^)]*?help="((?:[^"\\]|\\.)*)"(?:\s*\n?\s*"((?:[^"\\]|\\.)*)")?/g)]
  .map(m => ({ name: m[1], help: (m[2] + (m[3] || '')).replace(/\\"/g, '"') }));
if (commands.length !== parserCount) throw new Error(`read ${commands.length} of ${parserCount} cli.py subcommands: fix the pattern`);
const projectNotes = new Map(landscape.projects.map(p => [p.name, p.notes || '']));
const catalog = {
  schema: 'cad-agent-catalog/1', origin: ORIGIN, repo: REPO, revision, built: committed,
  tagline: TAGLINE, description: LEDE,
  items: [
    ...commands.map(c => ({ type: 'tool', status: 'ours', name: `cad-agent ${c.name}`, summary: c.help,
      url: `${ORIGIN}/docs/toolkit`, how: `cad-agent ${c.name} --help` })),
    ...upstreams.map(u => ({ type: 'upstream', status: u.status, name: u.name, url: u.url,
      summary: projectNotes.get(u.name) || u.what || u.policy, policy: u.policy,
      license: u.license, stars: u.stars, last_push: u.last_push })),
    // A library is 'used' only when landscape.json says so (a real dependency); otherwise it is tracked for reference.
    ...landscape.libraries.map(l => ({ type: 'library', status: l.status || 'reference', name: l.name, url: l.url || `https://github.com/${l.name}`,
      license: l.license_spdx, stars: l.stars, last_push: l.last_push, summary: l.use || l.role || l.notes || '' })),
    ...landscape.benchmarks.map(b => ({ type: 'benchmark', status: b.status === 'unverified' ? 'unverified' : 'reference', name: b.name, url: b.url,
      license: b.license_spdx || b.license, summary: [b.tasks || b.notes, b.size, b.venue || b.paper].filter(Boolean).join(' · ')
        || (b.status === 'unverified' ? 'Listed from its paper or site; tasks, data and licence not yet checked.' : '') })),
    ...pages.map(p => ({ type: p.section === 'docs' ? 'doc' : p.section.replace(/s$/, ''), status: 'ours', name: p.title,
      summary: p.summary, url: ORIGIN + pageURL(p.file), markdown: `${ORIGIN}/${p.file}`, source: `${REPO}/blob/dev/${p.file}` })),
  ],
};
const counts = catalog.items.reduce((a, i) => (a[i.type] = (a[i.type] || 0) + 1, a), {});
// Each ### entry in a lesson file is one lesson (lessons/README.md#lesson-format); the area READMEs are maps, not lessons.
const lessonCount = pages.filter(p => p.section === 'lessons' && !/(?:^|\/)README\.md$/.test(p.file))
  .reduce((n, p) => n + (p.body.replace(/```[\s\S]*?```/g, '').match(/^### /gm) || []).length, 0);
await writeFile(path.join(out, 'catalog.json'), JSON.stringify(catalog, null, 2) + '\n');

// ----------------------------------------------------------------------------- HTML frame
const NAV = [['/catalog', 'Catalogue', true], ['/docs/toolkit', 'Toolkit', true], ['/research/landscape', 'Landscape'],
  ['/docs/common-issues', 'Pitfalls'], ['/docs/agent-workflow', 'For agents']];
// Feedback goes to GitHub: a short issue form with the page filled in, or an edit of the page's source.
const feedbackURL = (title, url) => `${REPO}/issues/new?template=feedback.yml&title=${encodeURIComponent(`Feedback: ${title}`)}&page=${encodeURIComponent(ORIGIN + url)}`;
const feedbackBox = (title, url, file) => `<aside class="feedback" aria-label="Feedback"><div><p class="feedback-title">Help us improve!</p>
<p>Something wrong, missing or confusing on this page? Tell us in a minute. Every note is read, and ideas we use are credited.</p></div>
<div class="feedback-actions"><a class="button" href="${esc(feedbackURL(title, url))}">Give feedback</a>${file ? `<a href="${REPO}/edit/dev/${esc(file)}">Suggest an edit</a>` : ''}</div></aside>`;
function frame({ title, body, md, description = LEDE, current = '', page = 'doc', css = [], updated = committed, url = current || '/' }) {
  return `<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>${esc(title === TAGLINE ? 'cad-agent · ' + TAGLINE : title + ' · cad-agent')}</title>
<meta name="description" content="${esc(description)}">
<link rel="icon" href="/web/icon.svg"><link rel="preload" href="/kit/vendor/fonts/inter.woff2" as="font" type="font/woff2" crossorigin><link rel="stylesheet" href="/web/site.css"><link rel="stylesheet" href="/kit/diagrams.css">${css.map(c => `<link rel="stylesheet" href="${c}">`).join('')}
${md ? `<link rel="alternate" type="text/markdown" href="${esc(md)}" title="Markdown for agents">` : ''}
<link rel="alternate" type="text/plain" href="/llms.txt" title="llms.txt"></head>
<body class="${page}-page" data-diagram-theme="light"><a class="skip-link" href="#main:content">Skip to content</a><header class="site-header"><div class="wrap"><a class="wordmark" href="/"><img src="/web/icon.svg" alt="" width="34" height="34">cad-agent<b>.</b></a>
<nav aria-label="Main">${NAV.map(([h, t, keep]) => `<a href="${h}"${keep ? ' data-keep' : ''}${h === current ? ' aria-current="page"' : ''}>${t}</a>`).join('')}<a class="pill-link" href="${REPO}">GitHub ↗</a></nav></div></header>
<main class="${page === 'landing' ? '' : 'wrap'} ${page === 'doc' ? 'doc' : ''}"${body.includes('id="main:content"') ? '' : ' id="main:content" tabindex="-1"'}>${body}</main>
<footer class="site-footer"><div class="wrap"><p>Created by <a href="https://valpatel.com">Valpatel Software LLC</a>. Code under the <a href="${REPO}/blob/dev/LICENSE">MIT licence</a>; every third-party tool keeps its own licence and credit. ${updated ? `Last updated <time datetime="${isoDay(updated)}">${day(updated)}</time>.` : 'This page has uncommitted changes.'} Built from <a href="${REPO}/commit/${revision}">${esc(revisionLabel)}</a>.</p>
<div class="links"><a href="${esc(feedbackURL(title === TAGLINE ? 'home page' : title, url))}">Help us improve ↗</a><a href="/llms.txt">llms.txt</a><a href="/llms-full.txt">llms-full.txt</a><a href="/catalog.json">catalog.json</a>${md ? `<a href="${esc(md)}">this page .md</a>` : ''}</div></div></footer>
<script type="module" src="/web/site.js"></script></body></html>`;
}

// ----------------------------------------------------------------------------- pages
const ENT = { amp: '&', lt: '<', gt: '>', quot: '"', apos: "'", nbsp: ' ' };
const decode = s => s.replace(/&(#x[\da-f]+|#\d+|[a-z]+);/gi, (m, e) => e[0] === '#'
  ? String.fromCodePoint(e[1].toLowerCase() === 'x' ? parseInt(e.slice(2), 16) : parseInt(e.slice(1), 10)) : (ENT[e] ?? m));
// GitHub's anchor rule (github-slugger): lower case, drop everything but letters, marks, numbers, connectors, hyphens
// and spaces, then each space becomes a hyphen (runs are not collapsed); repeats get -1, -2.
export const slug = text => decode(text.replace(/<[^>]*>/g, '')).toLowerCase().replace(/[^\p{L}\p{M}\p{N}\p{Pc}\- ]/gu, '').replace(/ /g, '-');

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
// A link to a folder whose README is a page goes to that page (lessons/process/ → lessons/process/README).
const folderPage = resolved => {
  const readme = resolved.replace(/\/?$/, '/README.md');
  return !resolved.endsWith('.md') && pageFiles.has(readme) ? readme : null;
};
// Relative links in a Markdown copy: published pages and images stay relative (their .md twin or file is at the same
// path); anything else (source files, tests) points at GitHub. absolute=true makes every link absolute (llms-full.txt).
const rewriteMd = (file, md, absolute = false) => md.split(/(```[\s\S]*?```)/).map((chunk, i) => i % 2 ? chunk :
  chunk.replace(/(\]\()([^)\s#][^)\s]*)((?:\s+"[^"]*")?\))/g, (all, open, url, close) => {
    if (/^(?:[a-z][a-z\d+.-]*:|\/\/)/i.test(url)) return all;
    const [pathname, ...hash] = url.split('#');
    const resolved = pathname.startsWith('/') ? pathname.slice(1) : path.posix.normalize(path.posix.join(path.posix.dirname(file), pathname));
    const folder = folderPage(resolved);
    if (folder) return `${open}${absolute ? `${ORIGIN}/${folder}` : pathname.replace(/\/?$/, '/README.md')}${hash.length ? '#' + hash.join('#') : ''}${close}`;
    const published = pageFiles.has(resolved) || (/^docs\/img\//.test(resolved) && tracked.includes(resolved));
    const target = published ? (absolute ? `${ORIGIN}/${resolved}` : url.split('#')[0])
      : `${REPO}/${tracked.includes(resolved) ? 'blob' : 'tree'}/dev/${resolved}`;
    return `${open}${target}${hash.length ? '#' + hash.join('#') : ''}${close}`;
  })).join('');
// Every page should show something: a picture, render, diagram, animation or demo. Pages without one are listed by
// the build and kept from growing by tests/website-build.test.mjs.
// What counts as something to look at in a doc page's sanitized HTML (the sanitizer drops inline <svg>, <video> and
// custom elements, so pictures arrive as <img> and diagrams as Mermaid blocks; the browser test checks they render).
const VISUAL = /<img\b|class="language-mermaid"|<pre class="mermaid"/g;
const visuals = new Map();
for (const p of pages) {
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
    else if (attr === 'src' && tracked.includes(resolved) && /\.(svg|png|jpe?g|gif|webp)$/i.test(resolved)) target = '/' + resolved;
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
  html = html.replace(/<table>/g, '<div class="table-scroll"><table>').replace(/<\/table>/g, '</table></div>');
  // One-click copy on every code block (not on diagram sources, which render as pictures).
  html = html.replace(/<pre>(<code(?! class="language-mermaid")[\s\S]*?<\/pre>)/g, '<cad-copy><pre>$1</cad-copy>');
  const crumbs = `<p class="crumbs"><a href="/catalog#${p.section}">${esc(SECTIONS.find(s => s.id === p.section).title)}</a> · <a href="${REPO}/blob/dev/${esc(p.file)}">${esc(p.file)}</a> · <a href="/${esc(p.file)}">Markdown</a></p>`;
  const dest = path.join(out, pageFile(p.file));
  await mkdir(path.dirname(dest), { recursive: true });
  // Long pages: the kit's <cad-nav> on the left (every page, grouped, with this page's outline under it) and, on very
  // wide screens, the outline again in a right-hand column. All written out here, so the first paint is final (the
  // script only marks the section being read, filters and toggles) and it all works without script.
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
  const nav = `<cad-nav for=".prose" rail=".doc-rail" role="navigation" aria-label="Pages and contents"><button type="button" class="cad-nav-toggle" aria-expanded="false">Pages and contents</button><div class="cad-nav-panel"><input type="search" class="cad-nav-filter" placeholder="Filter pages" aria-label="Filter pages"><p class="cad-nav-empty" role="status"></p>${tree}</div></cad-nav>`;
  const rail = heads.length < 2 ? '' : `<nav class="doc-rail" aria-labelledby="rail-title"><p class="doc-rail-title" id="rail-title">On this page</p>${outline(' cad-nav-rail', false)}</nav>`;
  await writeFile(dest, frame({ title: p.title, body: `<div class="doc-layout">${nav}<div class="doc-main" id="main:content" tabindex="-1">${crumbs}<article class="prose">${html}</article>` + feedbackBox(p.title, pageURL(p.file), p.file) + `</div>${rail}</div>`, md: '/' + p.file, description: p.summary, current: pageURL(p.file), updated: lastChange(p.file), css: ['/kit/nav.css'] }));
  visuals.set(p.file, (html.match(VISUAL) || []).length);
  await writeFile(path.join(out, p.file), rewriteMd(p.file, p.src));   // the Markdown twin, same path
}
// Images referenced by docs.
for (const f of tracked.filter(f => /^docs\/img\/.*\.(svg|png|jpe?g|gif|webp)$/i.test(f))) await copyTracked(f, path.join(out, f));

// Catalogue page: cards from catalog.json, filterable in the browser.
const TYPE_LABEL = { tool: 'cad-agent tools', upstream: 'Agentic CAD projects we track', library: 'Libraries', benchmark: 'Benchmarks',
  doc: 'Docs', skill: 'Skills', agent: 'Subagents', lesson: 'Lessons (pitfalls)', research: 'Research' };
const STATUS_NOTE = { ours: 'built here', adopted: 'adopted', trial: 'in trial', candidate: 'candidate', rejected: 'rejected', used: 'used', reference: 'tracked', unverified: 'unverified' };
const card = i => `<li class="card" data-type="${esc(i.type)}" data-text="${esc((i.name + ' ' + (i.summary || '') + ' ' + (i.license || '')).toLowerCase())}">
<a href="${esc(safeUrl(i.url))}"><span class="card-name">${esc(i.name)}</span></a>
<span class="pill pill-${esc(i.status)}">${esc(STATUS_NOTE[i.status] || i.status)}</span>${i.license ? `<span class="pill">${esc(i.license)}</span>` : ''}${i.stars ? `<span class="pill">★ ${Number(i.stars).toLocaleString('en-US')}</span>` : ''}
<p>${esc(i.summary || '')}</p>${i.policy && i.policy !== i.summary ? `<p class="policy">${esc(i.policy)}</p>` : ''}${i.markdown ? `<a class="md" href="${esc(i.markdown.replace(ORIGIN, ''))}">.md</a>` : ''}</li>`;
const groups = Object.keys(TYPE_LABEL).filter(t => counts[t]);
const catalogBody = `<section class="section" style="padding-bottom:10px"><p class="eyebrow"><span class="status-dot"></span>Catalogue · ${catalog.items.length} entries</p><h1>Everything we map, <span>demonstrate</span> or build.</h1>
<p class="hero-description">Other people's open-source projects and libraries come first; our own tools only where nothing free fills the gap. Agents read the same list as <a href="/catalog.json">catalog.json</a>.</p>
<div class="filters"><input id="q" type="search" placeholder="Filter: snap fit, FEA, KiCad, MIT…" aria-label="Filter the catalogue"><p id="filter-status" class="filter-status" role="status" aria-live="polite"></p>
<div class="chips">${groups.map(t => `<button class="chip" data-type="${t}" aria-pressed="false">${esc(TYPE_LABEL[t])} <small>${counts[t]}</small></button>`).join('')}</div></div></section>
${groups.map(t => `<section class="group" id="${t === 'doc' ? 'docs' : t === 'skill' ? 'skills' : t === 'agent' ? 'agents' : t === 'lesson' ? 'lessons' : t}" data-group="${t}"><h2>${esc(TYPE_LABEL[t])}</h2><ul class="cards">${catalog.items.filter(i => i.type === t).map(card).join('')}</ul></section>`).join('')}`;
await writeFile(path.join(out, 'catalog.html'), frame({ title: 'Catalogue', body: catalogBody, current: '/catalog', page: 'catalog' }));

// Landing page: the real model first, then real outputs, then where cad-agent fits (docs/home.yaml), then the map.
const skillCards = pages.filter(p => p.section === 'skills' || p.section === 'agents');
const SNAP = snapDemo();                 // geometry-driven animation: tools/snap-demo.mjs
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
const CREDIT = { gyropup: '<a href="https://gyropup.com">Gyropup</a> · MIT' };
const reel = [];
for (const [i, r] of home.reel.entries()) {
  const at = `reel[${i}]`;
  for (const k of ['img', 'tool', 'title', 'caption', 'alt', 'href']) if (!r[k]) throw new Error(`docs/home.yaml ${at} has no ${k}`);
  if (r.credit && !CREDIT[r.credit]) throw new Error(`docs/home.yaml ${at}: unknown credit ${r.credit}`);
  reel.push(`<li class="reel-tile${r.fit === 'cover' ? ' reel-cover' : ''}"><a class="reel-media" href="${esc(homeHref(r.href, at))}" tabindex="-1" aria-hidden="true">${await homeImg(r.img, at, ` alt="" loading="lazy" decoding="async"`)}</a>
<p class="reel-tool"><code>${esc(r.tool)}</code></p><h3><a href="${esc(homeHref(r.href, at))}">${esc(r.title)}</a></h3><p>${esc(r.caption)}</p>${r.credit ? `<p class="reel-credit">${CREDIT[r.credit]}</p>` : ''}
<span class="visually-hidden">${esc(r.alt)}</span></li>`);
}
// The snap-fit demo is drawn from its geometry in this build (tools/snap-demo.mjs), so it joins the reel inline.
reel.splice(3, 0, `<li class="reel-tile reel-snap"><a class="reel-media" href="/docs/compliant" tabindex="-1" aria-hidden="true">${SNAP.svg}</a>
<p class="reel-tool"><code>cad-agent snapfit</code></p><h3><a href="/docs/compliant">One part, no screws</a></h3><p>A cantilever snap fit animated from its own geometry: contact and root strain computed against the material and the print's layer direction.</p></li>`);
const fitsTile = async (t, i) => {
  const at = `fits.ours[${i}]`;
  const levels = t.maturity ? [t.maturity] : (t.areas || []).map(a => {
    if (!areaMaturity.has(a)) throw new Error(`docs/home.yaml ${at}: no area ${a} in docs/areas.yaml`);
    return areaMaturity.get(a);
  });
  if (!levels.length || levels.some(l => !LADDER.includes(l))) throw new Error(`docs/home.yaml ${at}: a maturity on the ladder (${LADDER.join(', ')}), from areas or stated with a why`);
  if (t.maturity && !t.why) throw new Error(`docs/home.yaml ${at}: a stated maturity needs its why`);
  const level = levels.reduce((lo, l) => LADDER.indexOf(l) < LADDER.indexOf(lo) ? l : lo);      // the least mature area decides
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
  if (m.upstream && !u) throw new Error(`docs/home.yaml fits.make[${i}]: ${m.upstream} is not in upstreams/registry.yaml`);
  return `<li><span class="make-name"><a href="${esc(homeHref(m.href, `fits.make[${i}]`))}"><b>${esc(m.name)}</b></a>${u ? ` <span class="pill">${esc(u.license)}</span><span class="pill" title="GitHub stars when surveyed">★ ${Number(u.stars).toLocaleString('en-US')}</span>` : ''}</span><span>${esc(m.does)}</span>${m.note ? `<small>${esc(m.note)}</small>` : ''}</li>`;
};
const testCount = git('grep', '-c', '-E', '^\\s*def test_', 'HEAD', '--', 'tests/*.py').split('\n').filter(Boolean)
  .reduce((n, l) => n + Number(l.split(':').pop()), 0);
// The hero model (web/models/, from tools/gyropup_showcase.py) and its still poster (tools/site-model-poster.mjs).
const heroModel = JSON.parse(await read('web/models/gyropup.json'));
const poster = imageSize(await readBuf('web/models/gyropup.webp'), 'gyropup.webp');
if (!poster) throw new Error('web/models/gyropup.webp: run node tools/site-model-poster.mjs');
const kb = n => `${Math.round(n / 1024)} KB`;
const landing = `<div class="wrap"><section class="hero hero-3d">
<div class="hero-head"><p class="eyebrow"><span class="status-dot"></span>Open source · for AI agents and people</p>
<h1>Your one stop shop for <span>agentic CAD.</span></h1>
<p class="intro">Checks, simulation and cited engineering for the hardware agents design, in tested code.</p></div>
<figure class="hero-model"><cad-model src="/web/models/gyropup.json" label="Gyropup" style="aspect-ratio:${poster.width}/${poster.height}"><img class="cad-model-poster" src="/web/models/gyropup.webp" width="${poster.width}" height="${poster.height}" fetchpriority="high" alt="Gyropup, a wheel-legged robot with a foam-ball turret, assembled from its ${heroModel.parts.length} parts"></cad-model>
<figcaption><span><b>Gyropup</b>, ${heroModel.parts.length} parts in place, exported from its STEP files by <code>cad-agent view</code>: ${heroModel.triangles.toLocaleString('en-US')} triangles in ${kb(heroModel.bytes)}.</span><span><a href="https://gyropup.com">gyropup.com</a> · MIT · drag to turn</span></figcaption></figure>
<div class="hero-actions"><div class="actions"><a class="button primary" href="#outputs">See what it computes <span>↓</span></a><a class="button" href="/catalog">Browse the catalogue</a><a class="button quiet" href="${REPO}">GitHub ↗</a></div>
<cad-copy class="agent-copy" label="Copy"><pre class="agent-box" aria-label="How an agent reads this site"><b># agents: start here</b>
curl -s ${ORIGIN}/llms.txt
curl -s ${ORIGIN}/catalog.json
curl -s ${ORIGIN}/docs/toolkit.md  <b># any page, as .md</b></pre></cad-copy></div>
</section></div>
<section class="reel-band" id="outputs"><div class="wrap"><div class="lead"><h2>What the code <span>computes.</span></h2><p>Real outputs of cad-agent's tools on real parts, with the numbers they computed. Each opens the page that explains it.</p></div>
<ul class="reel">${reel.join('')}</ul></div></section>
<div class="wrap"><section class="section fits" aria-labelledby="fits-title"><div class="lead"><h2 id="fits-title">Where cad-agent <span>fits.</span></h2><p>Other people's tools make the model, and we use them: text-to-cad writes and exports it, but <a href="/research/landscape#2-deep-dive-earthtojaketext-to-cad-v0726-2026-10-20">its code computes no stress, fatigue or safety factor</a>. cad-agent's engineering is Python with ${testCount.toLocaleString('en-US')} test functions in CI. Each block shows how far it has got.</p></div>
<div class="fits-make"><p class="fits-label">Make: other people's tools we use, credited</p><ul>${home.fits.make.map(makeChip).join('')}</ul></div>
<p class="fits-arrow" aria-hidden="true"><span>STEP, 3MF, boards</span></p>
<div class="fits-ours"><p class="fits-label">Check, simulate, explain, measure: cad-agent</p><ul>${(await Promise.all(home.fits.ours.map(fitsTile))).join('')}</ul>
<p class="fits-key">Maturity: ${areasTree.maturity.map(m => `<b>${esc(m.level)}</b> ${esc(m.means)}`).join('; ')}. From <a href="${REPO}/blob/dev/docs/areas.yaml">docs/areas.yaml</a>.</p></div></section>
<section class="section" style="padding-top:0"><div class="missions">
<a class="mission mission-blue" href="/research/landscape"><span class="mission-tag">Map</span><span class="mission-num">${(counts.upstream || 0) + (counts.library || 0) + (counts.benchmark || 0)}</span><p>Agentic-CAD projects, libraries and benchmarks, checked with dates and licences.</p><span class="go">See the landscape <span>→</span></span></a>
<a class="mission mission-yellow" href="/docs/toolkit"><span class="mission-tag">Demonstrate</span><span class="mission-num">${counts.tool || 0}</span><p>Commands that run on real projects: gates, holes, FEA, CFD, topology, slicing, the 3D viewer.</p><span class="go">Open the toolkit <span>→</span></span></a>
<a class="mission mission-orange" href="/docs/common-issues"><span class="mission-tag">Fill the gaps</span><span class="mission-num">${lessonCount}</span><p>Lessons from real builds, each with the incident behind it and the check that catches it.</p><span class="go">Read the pitfalls <span>→</span></span></a>
</div></section>
<section class="section built-with" style="padding-top:0"><div class="lead"><h2>Built with <span>cad-agent.</span></h2><p>Real projects are the test bench: every tool here was needed by one of them first.</p></div>
<ul class="projects"><li><a href="https://gyropup.com">${await homeImg('docs/img/gyropup.jpg', 'projects', ' alt="Gyropup, a wheel-legged robot with a turret, rendered" loading="lazy" decoding="async"')}<b>Gyropup</b></a><p>A wheel-legged foam-ball battle robot, designed, simulated and documented by agents with this toolkit. MIT.</p></li>
<li><a href="https://github.com/mvalancy/j501-agx-orin">${await homeImg('docs/img/viewer.jpg', 'projects', ' alt="The J501 enclosure in the kit\'s 3D viewer, with its parts list" loading="lazy" decoding="async"')}<b>J501 AGX Orin enclosure</b></a><p>A printed enclosure and cooler for a Jetson AGX Orin carrier, where most of the lessons came from.</p></li></ul></section>

<section class="section skills-row" style="padding-top:0"><div class="lead"><h2>Skills your agents <span>can load.</span></h2><p><code>cad-agent agents install</code> adds them to Claude Code and Codex. <a href="/docs/agent-workflow">How they work together →</a></p></div>
<ul class="skill-chips">${skillCards.map(p => `<li><a href="${esc(pageURL(p.file))}"><b>${esc(p.title)}</b><span class="pill">${p.section === 'agents' ? 'subagent' : 'skill'}</span></a><a class="skill-md" href="/${esc(p.file)}" aria-label="${esc(p.title)} as Markdown">.md</a></li>`).join('')}</ul></section>
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

- Source: ${REPO} (MIT). Install: \`pip install -e .\` in a checkout; agent skills: \`cad-agent agents install\`.
- Machine-readable catalogue: ${ORIGIN}/catalog.json (schema ${catalog.schema}; ${catalog.items.length} entries).
- Full text of every page in one file: ${ORIGIN}/llms-full.txt
- Built from commit ${revision}.

## Start here

- [README](${ORIGIN}/README.md): what cad-agent is and how it grows
- [Toolkit](${ORIGIN}/docs/toolkit.md): every command, the project contract and the Python API
- [Agent workflow](${ORIGIN}/docs/agent-workflow.md): skills, subagents, work claims and crash-safe work
- [Common issues](${ORIGIN}/docs/common-issues.md): recurring CAD mistakes and the checks that catch them
- [Landscape](${ORIGIN}/research/landscape.md): the agentic-CAD tools we track, verified

${SECTIONS.map(s => `## ${s.title}\n\n${bySection(s.id).map(p => `- [${p.title}](${ORIGIN}/${p.file}): ${p.summary.replace(/\s+/g, ' ').slice(0, 200)}`).join('\n')}`).join('\n\n')}

## Commands

${commands.map(c => `- \`cad-agent ${c.name}\`: ${c.help}`).join('\n')}
`;
await writeFile(path.join(out, 'llms.txt'), llms);
await writeFile(path.join(out, 'index.md'), llms);
await writeFile(path.join(out, 'llms-full.txt'), `# cad-agent: full text\n\n> ${TAGLINE}. ${LEDE}\n\n` +
  pages.map(p => `\n\n---\n\nSource: ${ORIGIN}/${p.file}\n\n${rewriteMd(p.file, p.body, true).trim()}\n`).join(''));
// Cloudflare Pages joins the values of a header set by more than one matching rule, so each header is set by one rule
// only: security headers on /*, Cache-Control only on /kit/vendor/* (everything else keeps the Pages default, which
// revalidates). The site's own pages have no inline script; the kit's viewer pages have an import map and a module
// script each, allowed by hash. Styles allow inline for the diagram kit's SVG output; wasm for the STEP reader.
const htmlFiles = async d => (await readdir(d, { withFileTypes: true, recursive: true }))
  .filter(e => e.isFile() && e.name.endsWith('.html')).map(e => path.join(e.parentPath, e.name));
// Only the kit's own pages (copied byte for byte from src/cadagent/webkit/) may carry inline script, so only their
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
  [`/${from.replace(/\.md$/, '')} /${to.replace(/\.md$/, '')} 301`, `/${from} /${to} 301`]).join('\n') + (redirects.length ? '\n' : ''));
await writeFile(path.join(out, '_headers'), [
  '/*', '  X-Content-Type-Options: nosniff', '  Referrer-Policy: strict-origin-when-cross-origin', `  Content-Security-Policy: ${CSP}`,
  '  Permissions-Policy: camera=(), microphone=(), geolocation=(), payment=(), usb=()', '  Cross-Origin-Opener-Policy: same-origin',
  '  Strict-Transport-Security: max-age=31536000',
  '/*.md', '  Content-Type: text/markdown; charset=utf-8', '/llms.txt', '  Content-Type: text/plain; charset=utf-8',
  '/llms-full.txt', '  Content-Type: text/plain; charset=utf-8', '/kit/vendor/*', '  Cache-Control: public, max-age=86400', ''].join('\n'));
await writeFile(path.join(out, 'robots.txt'), `User-agent: *\nAllow: /\nSitemap: ${ORIGIN}/sitemap.xml\n`);
await writeFile(path.join(out, 'sitemap.xml'), '<?xml version="1.0" encoding="UTF-8"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">' +
  ['/', '/catalog', ...pages.map(p => pageURL(p.file))].map(u => `<url><loc>${ORIGIN}${u}</loc></url>`).join('') + '</urlset>\n');
await writeFile(path.join(out, '404.html'), frame({ title: 'Not found', body: '<h1>Not here.</h1><p>Try the <a href="/catalog">catalogue</a> or <a href="/llms.txt">llms.txt</a>.</p>' }));
await writeFile(path.join(out, 'version.json'), JSON.stringify({ revision, built: catalog.built, pages: pages.length, items: catalog.items.length }, null, 2) + '\n');
// For agents and the tests: which pages still have nothing to look at.
const noVisual = [...visuals].filter(([, n]) => !n).map(([f]) => f).sort();
await writeFile(path.join(out, 'visuals.json'), JSON.stringify({ pages: Object.fromEntries([...visuals].sort()), without: noVisual }, null, 2) + '\n');
console.log(`Built ${path.relative(root, out) || out}${WORKTREE ? ' (draft: working tree)' : ''}: ${pages.length} pages (+ Markdown twins), ${catalog.items.length} catalogue entries, ${commands.length} commands. Revision ${revision.slice(0, 12)}. ${noVisual.length} pages have no picture, diagram or demo yet (visuals.json).`);
