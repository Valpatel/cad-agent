/** The catalogue: cad-agent.valpatel.com/catalog, /catalog.json (schema cad-agent-catalog/2), /catalog/index.json and
 * one /catalog/<area>.json per domain, area and bucket, and the covers under /catalog/covers/. Built by
 * tools/build-site.mjs from committed files only:
 * - our commands (cli.py), pages (docs, lessons, research, skills, agents) and demos and tool pictures (docs/catalog.yaml);
 * - outside projects (upstreams/registry.yaml), libraries and benchmarks (research/landscape.json);
 * - the topic tree (docs/areas.yaml), which places pages, commands, skills, agents and lesson folders in areas. Outside
 *   entries take an `areas:` list of their own; until they have one they are listed as not yet placed.
 * Agents first: an agent reads catalog/index.json (areas with counts and links), then one area file, then the entry.
 * The page is plain semantic HTML that shows every entry, grouped by kind, without script; the kit's <cad-gallery>
 * adds the kind tabs, the area tree, filters, sorting and the URL state (kit/gallery.js).
 */
import { GLYPHS, DOMAIN_GLYPH, TINT, STATUS_STYLE, glyphSprite, outsideCover, pageCover, toolCover, stillFrame, isAnimated } from './catalog-art.mjs';

const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
const slugify = s => String(s).toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '');
const plainText = s => String(s ?? '').replace(/`/g, '').replace(/\s+/g, ' ').trim();
const LIMIT = 6;                                // entries per kind in the overview (two rows of three, three of two)

/** Kinds, in page order: the tab value (also the URL's kind= and the section id), labels and a one-line blurb.
 * `anchor` keeps the section ids of the schema-1 page (/catalog#tool, #upstream, #docs, …) working. */
export const KINDS = [
  { kind: 'demo', tab: 'demos', label: 'Demos', one: 'demo', many: 'demos', type: 'demo',
    blurb: 'Interactive and animated demos, and renders, made with our own tools.' },
  { kind: 'tool', tab: 'tools', label: 'Tools', one: 'tool', many: 'tools', type: 'tool', anchor: 'tool',
    blurb: 'cad-agent commands. Each one ran on a real project first and says what it cannot see.' },
  { kind: 'project', tab: 'projects', label: 'Open-source projects', one: 'open-source project', many: 'open-source projects', type: 'upstream', anchor: 'upstream',
    blurb: 'Agentic-CAD projects by other people, checked for licence, activity and what they really do.' },
  { kind: 'library', tab: 'libraries', label: 'Libraries', one: 'library', many: 'libraries', type: 'library', anchor: 'library',
    blurb: 'The CAD, mesh and simulation libraries agents build on, and the ones we use.' },
  { kind: 'benchmark', tab: 'benchmarks', label: 'Benchmarks', one: 'benchmark', many: 'benchmarks', type: 'benchmark', anchor: 'benchmark',
    blurb: 'Published datasets and benchmarks for CAD generation and editing.' },
  { kind: 'guide', tab: 'guides', label: 'Guides', one: 'guide', many: 'guides', type: 'doc', anchor: 'docs',
    blurb: 'How to use the toolkit, and the method behind each check, with its limits.' },
  { kind: 'lesson', tab: 'lessons', label: 'Lessons', one: 'lesson page', many: 'lesson pages', type: 'lesson',
    blurb: 'Rules learned on real builds, each with the incident behind it and how to check it.' },
  { kind: 'research', tab: 'research', label: 'Research', one: 'research page', many: 'research pages', type: 'research',
    blurb: 'Surveys of tools, papers and data sheets, with what we adopt and why.' },
  { kind: 'skill', tab: 'skills', label: 'Skills and agents', one: 'skill or agent', many: 'skills and agents', type: 'skill', anchor: 'agents',
    blurb: 'Agent skills and subagents for Claude Code and Codex: cad-agent agents install.' },
];
const KIND = Object.fromEntries(KINDS.map(k => [k.kind, k]));
const tabOf = kind => (KIND[kind] || KIND.skill).tab;                       // subagents share the skills tab
const KIND_LABEL = { demo: 'Demo', tool: 'Tool', project: 'Project', library: 'Library', benchmark: 'Benchmark', guide: 'Guide',
  lesson: 'Lessons', research: 'Research', skill: 'Skill', agent: 'Subagent' };
const LEVELS = ['idea', 'surveyed', 'tooling', 'validated', 'proven'];
const STATUS_ORDER = ['ours', 'adopted', 'used', 'trial', 'candidate', 'reference', 'unverified', 'rejected'];
const LICENCES = { permissive: 'Permissive', copyleft: 'Copyleft', other: 'None or restricted' };
const MODE_LABEL = { interactive: 'Interactive', animated: 'Animated', render: 'Render' };
const SORTS = [['featured', 'Featured'], ['recent', 'Recently active'], ['stars', 'Most stars'], ['maturity', 'Maturity'], ['az', 'A–Z']];
const BUCKETS = { 'cross-cutting': { title: 'Across all areas', scope: 'Pages about the whole project: the toolkit, the vision, the landscape and how to contribute.' },
  unplaced: { title: 'Not yet placed', scope: 'Outside projects, libraries and benchmarks waiting for an areas: field in their registry.' } };

export function licenceFamily(spdx) {
  const s = String(spdx || '').trim();
  if (!s || /^(none|noassertion|unknown|other)$/i.test(s)) return 'other';
  if (/^(MIT|MIT-0|Apache-2\.0|BSD-[0-4]-Clause|0BSD|ISC|Zlib|Unlicense|CC0-1\.0|CC-BY-[34]\.0|BSL-1\.0|PSF-2\.0|Python-2\.0)$/i.test(s)) return 'permissive';
  if (/^(A?GPL|LGPL|MPL|EPL|EUPL|OSL|CC-BY-SA|CDDL)/i.test(s)) return 'copyleft';
  return 'other';                              // non-commercial, source-available and custom licences: ideas only
}

/** A plain "what it is" for a landscape project without a `what`: its clients, kernel and processes, never our notes. */
const CLIENT = { 'claude-code-plugin': 'Claude Code plugin', 'codex-plugin': 'Codex plugin', 'cursor-plugin': 'Cursor plugin',
  'gemini-extension': 'Gemini extension', mcp: 'MCP server', 'skills.sh': 'skills.sh skills', 'web-app': 'web app', 'desktop-app': 'desktop app',
  cli: 'CLI', 'claude-code-skill': 'Claude Code skill', 'claude-code-skills': 'Claude Code skills', 'claude-code-template': 'Claude Code template',
  'kicad-plugin': 'KiCad plugin', 'github-action': 'GitHub Action', vscode: 'VS Code' };
function composeWhat(p) {
  if (!p?.kernel && !p?.clients?.length) return '';
  const clients = (p.clients || []).map(c => CLIENT[c] || c.replace(/\s*\(.*$/, '').replace(/-/g, ' ')).filter(Boolean);
  const head = clients.length > 2 ? `${clients.slice(0, 2).join(', ')} and ${clients.length - 2} more` : clients.join(' and ');
  const kernel = String(p.kernel || '').split(/ \(|, | on /)[0].trim();
  const procs = (p.processes || []).map(s => s.replace(/\s*\((?:u|review|unverified)\)/g, '').trim()).filter(s => s && !/^(general|visual only)$/i.test(s));
  const parts = [head && head[0].toUpperCase() + head.slice(1), kernel && `on ${kernel}`].filter(Boolean).join(' ');
  return plainText(`${parts}${procs.length ? ` · ${procs.slice(0, 3).join(', ')}${procs.length > 3 ? ' and more' : ''}` : ''}`);
}
/** One line: the first sentence, cut at a word before `max` characters. */
const oneLine = (s, max = 200) => {
  s = plainText(s);
  const end = s.search(/[.!?](?:\s|$)/);
  if (end > 30 && end < max) return s.slice(0, end + 1);
  return s.length <= max ? s : s.slice(0, max).replace(/\s+\S*$/, '') + '…';
};

/** Sections of a page's Markdown: words, and whether each has a picture or diagram, or code (the page cover). */
function sectionsOf(md) {
  const out = [];
  let cur = { words: 0 }, fence = false, fenceLang = '';
  for (const line of md.split('\n')) {
    const f = line.match(/^\s*(```|~~~)\s*(\w*)/);
    if (f) { if (!fence) { fence = true; fenceLang = f[2]; if (fenceLang === 'mermaid') cur.figure = true; else cur.code = true; } else fence = false; continue; }
    if (fence) continue;
    if (/^##\s/.test(line)) { out.push(cur); cur = { words: 0 }; continue; }
    if (/!\[|<img\b/.test(line)) cur.figure = true;
    cur.words += (line.match(/[\p{L}\p{N}]+/gu) || []).length;
  }
  out.push(cur);
  return out.filter((s, i) => i || s.words > 20).filter(s => s.words || s.figure || s.code);
}

/**
 * Build everything. ctx: { ORIGIN, REPO, revision, built, commands [{name, help}], cli (cli.py source), upstreams,
 * landscape, pages [{file, section, title, summary, body, html, updated}], areas (docs/areas.yaml), data
 * (docs/catalog.yaml), tracked (paths), read (async path → Buffer), pageURL, safeUrl, snap ({svg, css}) }.
 * Returns { catalog, files: Map(path → string), body (the page's HTML), counts (schema-1 type → count) }.
 */
export async function buildCatalog(ctx) {
  const { ORIGIN, REPO, pageURL, tracked } = ctx;
  const has = new Set(tracked);
  const files = new Map();
  const abs = u => (u && u.startsWith('/') ? ORIGIN + u : u);

  // --------------------------------------------------------------------------- the topic tree
  const nodes = new Map();                       // slug → node (domain, area or topic), with its domain and area
  for (const d of ctx.areas.domains) {
    nodes.set(d.slug, { ...d, level: 'domain', domain: d.slug });
    for (const a of d.areas || []) {
      nodes.set(a.slug, { ...a, level: 'area', domain: d.slug });
      for (const t of a.topics || []) nodes.set(t.slug, { ...t, level: 'topic', domain: d.slug, area: a.slug });
    }
  }
  for (const b of Object.keys(BUCKETS)) if (nodes.has(b)) throw new Error(`docs/areas.yaml: "${b}" is reserved for the catalogue`);
  const placed = { pages: new Map(), cli: new Map(), skills: new Map(), agents: new Map(), lessons: new Map() };
  const put = (key, value, slug) => { const m = placed[key]; if (!m.has(value)) m.set(value, []); m.get(value).push(slug); };
  for (const n of nodes.values()) for (const key of ['pages', 'cli', 'skills', 'agents']) for (const v of n[key] || []) put(key, v, n.slug);
  for (const n of nodes.values()) if (n.lessons) put('lessons', n.lessons, n.slug);
  for (const v of ctx.areas.cross_cutting?.pages || []) put('pages', v, 'cross-cutting');
  // Pages about the whole repository (README, CONTRIBUTING, licence notices, the lessons index) are cross-cutting too.
  for (const f of ['README.md', 'CONTRIBUTING.md', 'THIRD_PARTY_NOTICES.md', 'lessons/README.md']) if (!placed.pages.has(f)) put('pages', f, 'cross-cutting');
  /** Area and domain slugs for a list of node slugs (a topic counts for its area), with maturity, Gyropup and domains. */
  const place = (slugs, where) => {
    const areas = [], domains = [];
    let level = -1, gyropup = false;
    for (const s of slugs || []) {
      if (BUCKETS[s]) { if (!areas.includes(s)) areas.push(s); continue; }
      const n = nodes.get(s);
      if (!n) throw new Error(`${where}: unknown area "${s}" (see docs/areas.yaml)`);
      const at = n.level === 'topic' ? nodes.get(n.area) : n;
      if (!areas.includes(at.slug)) areas.push(at.slug);
      if (!domains.includes(n.domain)) domains.push(n.domain);
      level = Math.max(level, LEVELS.indexOf(at.maturity));
      if ((n.priority || []).includes('gyropup') || (at.priority || []).includes('gyropup')) gyropup = true;
    }
    return { areas, domains, maturity: level >= 0 ? LEVELS[level] : null, gyropup };
  };

  // --------------------------------------------------------------------------- covers
  const covers = new Map();                      // cover path on the site → { src, anim, fit }
  const coverFile = (name, svg) => { files.set(`catalog/covers/${name}`, svg); return `/catalog/covers/${name}`; };
  /** A figure from docs/img as a cover: animated SVGs get a still frame and keep the moving original for hover. */
  async function figureCover(file, still = 0.5) {
    if (!has.has(file)) return null;
    const key = `${file}@${still}`;
    if (covers.has(key)) return covers.get(key);
    let c = { src: '/' + file, anim: null, fit: /\.svg$/i.test(file) ? 'contain' : 'cover', figure: true };
    if (/\.svg$/i.test(file)) {
      const svg = (await ctx.read(file)).toString('utf8');
      if (isAnimated(svg)) c = { ...c, src: coverFile(`still/${file.replace(/^docs\/img\//, '').replace(/\//g, '-')}`, stillFrame(svg, still)), anim: '/' + file };
    }
    covers.set(key, c);
    return c;
  }
  const generated = (id, svg) => ({ src: coverFile(`${id}.svg`, svg), anim: null, fit: 'cover', figure: false });
  const tone = it => it.domains?.[0] || (it.areas?.[0] === 'cross-cutting' ? 'cross-cutting' : 'unplaced');
  // An outside entry not placed in an area yet still gets a picture of its subject, guessed from its own words. The
  // guess only picks the cover's glyph: the entry stays in "not yet placed" until upstreams/registry.yaml gives areas.
  const SUBJECT = [[/\b(kicad|pcb|gerber|schematic|circuit|eda)\b/, 'circuit-boards'], [/(slicer|slicing|\b3mf|\bfdm\b|g-?code|\bprint(?:ing|er)?\b)/, '3d-printing'],
    [/\b(cfd|openfoam|airflow|fluid)\b/, 'cfd'], [/\b(fea|fem|calculix|stress|elmer|finite.element)\b/, 'structural-fea'],
    [/\btopology\b/, 'topology-optimisation'], [/\b(render|blender|visuali[sz]|mesh)/, 'results-and-visuals'],
    [/\b(cnc|cam|toolpath|machining)\b/, 'cnc-machining'], [/\b(sheet.metal|laser)\b/, 'sheet-metal'], [/\b(gear|mechanism|linkage|kinematic)/, 'mechanisms'],
    [/\b(benchmark|eval|dataset|leaderboard)/, 'evaluation'], [/\b(mcp|agent|plugin|llm|copilot|skill)/, 'agent-workflow']];
  const subjectOf = it => SUBJECT.find(([re]) => re.test(`${it.name} ${it.what || ''} ${it.summary || ''}`.toLowerCase()))?.[1];
  const glyphOf = it => (it.areas?.length && !BUCKETS[it.areas[0]] ? it.areas[0] : it.areas?.[0] === 'cross-cutting' ? 'cross-cutting'
    : ['project', 'library', 'benchmark'].includes(it.kind) ? subjectOf(it) || it.kind : it.kind);

  // --------------------------------------------------------------------------- pages
  const pageBy = new Map(ctx.pages.map(p => [p.file, p]));
  const headingIds = html => new Set([...html.matchAll(/<h[1-6] id="([^"]+)"/g)].map(m => m[1]));
  /** A repo path with an optional #anchor → a site URL, checked: the page exists and so does the anchor. */
  const pageLink = (ref, where) => {
    const [file, hash] = String(ref).split('#');
    const p = pageBy.get(file);
    if (!p) return null;
    if (hash && !headingIds(p.html).has(hash)) {
      // A published build fails on a stale anchor; a local draft (--worktree) may be mid-edit, so it links the page.
      if (!ctx.draft) throw new Error(`${where}: ${file} has no heading #${hash}`);
      console.warn(`draft: ${where}: ${file} has no heading #${hash}; linking the page`);
      return pageURL(file);
    }
    return pageURL(file) + (hash ? '#' + hash : '');
  };
  /** Figures a page shows, in order: { src (repo path), alt, anchor (the heading above it) }. */
  const figuresOf = p => {
    const out = [];
    let anchor = '';
    for (const m of p.html.matchAll(/<h[1-6] id="([^"]+)"|<img\b[^>]*>/g)) {
      if (m[1]) { anchor = m[1]; continue; }
      const src = m[0].match(/\ssrc="\/([^"#?]+)"/)?.[1];
      if (src && has.has(src) && src.startsWith('docs/img/')) out.push({ src, alt: (m[0].match(/\salt="([^"]*)"/)?.[1] || '').replace(/&quot;/g, '"').replace(/&#39;/g, "'").replace(/&amp;/g, '&'), anchor });
    }
    return out;
  };
  const kindOfSection = { docs: 'guide', lessons: 'lesson', research: 'research', skills: 'skill', agents: 'agent' };
  const pageItemId = (p, kind) => {
    const rest = p.file.replace(/^(docs|lessons|research|skills|agents)\//, '').replace(/\/SKILL\.md$|\.md$/, '').replace(/(^|\/)README$/, '$1index');
    return `${kind}-${slugify(rest)}`;
  };
  const items = [];
  const pageItems = new Map();
  for (const p of ctx.pages) {
    const kind = kindOfSection[p.section];
    const lessonFolder = p.file.match(/^lessons\/([^/]+)\//)?.[1];
    const skill = p.file.match(/^skills\/([^/]+)\/SKILL\.md$/)?.[1], agent = p.file.match(/^agents\/([^/]+)\.md$/)?.[1];
    const slugs = [...(placed.pages.get(p.file) || []), ...(lessonFolder ? placed.lessons.get(lessonFolder) || [] : []),
      ...(skill ? placed.skills.get(skill) || [] : []), ...(agent ? placed.agents.get(agent) || [] : [])];
    const where = place(slugs, p.file);
    const it = { type: p.section === 'docs' ? 'doc' : p.section.replace(/s$/, ''), status: 'ours', name: p.title, summary: p.summary,
      url: ORIGIN + pageURL(p.file), markdown: `${ORIGIN}/${p.file}`, source: `${REPO}/blob/dev/${p.file}`,
      id: pageItemId(p, kind), kind, ...where, what: oneLine(p.summary), notes: null, license: 'MIT', updated: p.updated?.slice(0, 10) || null,
      page: p };
    const figs = figuresOf(p);
    const demoEl = p.html.match(/<cad-(?!copy|nav)[a-z][a-z0-9-]*[\s>]/);
    const animFig = [];
    for (const f of figs) if (/\.svg$/i.test(f.src) && isAnimated((await ctx.read(f.src)).toString('utf8'))) animFig.push(f);
    if (demoEl || animFig.length) {
      const before = demoEl ? [...p.html.slice(0, demoEl.index).matchAll(/<h[1-6] id="([^"]+)"/g)].at(-1)?.[1] : animFig[0].anchor;
      it.demo = ORIGIN + pageURL(p.file) + (before ? '#' + before : '');
    }
    it.cover = figs.length ? await figureCover(figs[0].src) : null;
    it.figures = figs;
    items.push(it);
    pageItems.set(p.file, it);
  }

  // --------------------------------------------------------------------------- demos (docs/catalog.yaml, then any other animated figure)
  const demos = [];
  const shownFigures = new Map();                 // figure → the first page that shows it, and where
  for (const it of pageItems.values()) for (const f of it.figures) if (!shownFigures.has(f.src)) shownFigures.set(f.src, { it, ...f });
  const addDemo = async (d, where) => {
    if (!d.id || !d.title || !d.cover || !MODE_LABEL[d.mode]) throw new Error(`${where}: a demo needs id, title, cover and mode (${Object.keys(MODE_LABEL).join(', ')})`);
    let cover;
    if (d.cover === 'snap-demo') {
      const svg = ctx.snap.svg.replace('<svg ', '<svg xmlns="http://www.w3.org/2000/svg" ').replace(/<\/svg>\s*$/, `<style>${ctx.snap.css}</style></svg>\n`);
      cover = { src: coverFile('still/snap-fit.svg', stillFrame(svg, d.still ?? 0.5)), anim: coverFile('snap-fit.svg', svg), fit: 'contain', figure: true };
    } else cover = await figureCover(d.cover, d.still ?? 0.5);
    if (!cover) return;                                              // its figure is not on this commit yet
    const shown = shownFigures.get(d.cover);
    const url = d.url ? pageLink(d.url, `docs/catalog.yaml demo ${d.id}`) : shown ? pageURL(shown.it.page.file) + (shown.anchor ? '#' + shown.anchor : '') : null;
    if (!url) return;                                                // no page shows it yet
    const pageFile = d.url ? d.url.split('#')[0] : shown.it.page.file;
    const where2 = d.areas ? place(d.areas, `docs/catalog.yaml demo ${d.id}`) : { ...pick(pageItems.get(pageFile)) };
    const what = d.what || oneLine(shown?.alt || '');
    demos.push({ type: 'demo', status: 'ours', name: d.title, summary: what, url: ORIGIN + url, markdown: pageItems.has(pageFile) ? `${ORIGIN}/${pageFile}` : undefined,
      id: `demo-${slugify(d.id)}`, kind: 'demo', mode: d.mode, ...where2, what, notes: null, license: 'MIT', cover, demo: ORIGIN + url,
      updated: pageItems.get(pageFile)?.updated || null, tools: d.tools || [], figure: d.cover });
  };
  const pick = it => ({ areas: it?.areas || [], domains: it?.domains || [], maturity: it?.maturity || null, gyropup: !!it?.gyropup });
  for (const d of ctx.data.demos || []) await addDemo(d, 'docs/catalog.yaml');
  const listed = new Set((ctx.data.demos || []).map(d => d.cover));
  for (const [src, s] of shownFigures) {
    if (listed.has(src) || !/\.svg$/i.test(src) || !isAnimated((await ctx.read(src)).toString('utf8'))) continue;
    const base = src.split('/').pop().replace(/\.svg$/, '');
    await addDemo({ id: base, title: base.replace(/-/g, ' ').replace(/^./, c => c.toUpperCase()), cover: src, mode: 'animated' }, src);
  }
  // The strip keeps the data file's order (curated: a mix of kinds up front), then any figure found by itself.

  // --------------------------------------------------------------------------- commands
  const flagsOf = name => {                    // the subcommand's own options, read from cli.py
    const v = ctx.cli.match(new RegExp(`(\\w+)\\s*=\\s*sub\\.add_parser\\(\\s*"${name}"`))?.[1];
    if (!v) return [];
    return [...ctx.cli.matchAll(new RegExp(`\\b${v}\\.add_argument\\(\\s*"([^"]+)"(?:\\s*,\\s*"([^"]+)")?([^)]*)`, 'g'))]
      .map(m => { const flag = m[2]?.startsWith('--') ? m[2] : m[1]; const meta = m[3].match(/metavar="([^"]+)"/)?.[1];
        return flag.startsWith('-') ? flag + (meta ? ` ${meta}` : /action="store_true"/.test(m[3]) ? '' : ' …') : `<${flag}>`; });
  };
  const toolData = ctx.data.tools || {};
  const cliChanged = ctx.cliUpdated?.slice(0, 10) || null;
  for (const c of ctx.commands) {
    const t = toolData[c.name] || {};
    const where = place(placed.cli.get(c.name) || [], `cad-agent ${c.name}`);
    const url = (t.page && pageLink(t.page, `docs/catalog.yaml tools.${c.name}`)) || '/docs/toolkit#commands';
    const it = { type: 'tool', status: 'ours', name: `cad-agent ${c.name}`, summary: c.help, url: ORIGIN + url, how: `cad-agent ${c.name} --help`,
      id: `tool-${c.name}`, kind: 'tool', ...where, what: oneLine(c.help), notes: null, license: 'MIT', updated: cliChanged, command: c.name };
    for (const f of t.figures || []) { it.cover = await figureCover(f, 0.5); if (it.cover) { it.figure = f; break; } }
    if (!it.cover) it.cover = generated(it.id, toolCover({ name: c.name, flags: flagsOf(c.name), glyphSlug: glyphOf(it), title: it.name }));
    const d = demos.find(d => d.tools.includes(c.name) || (it.figure && d.figure === it.figure));
    if (d) it.demo = d.demo;
    items.push(it);
  }

  // --------------------------------------------------------------------------- outside entries
  const asOf = ctx.landscape.refreshed_on || ctx.landscape.verified_on || ctx.built.slice(0, 10);
  const projectData = new Map(ctx.landscape.projects.map(p => [p.name, p]));
  for (const u of ctx.upstreams) {
    const p = projectData.get(u.name);
    const where = place(u.areas || [], `upstreams/registry.yaml ${u.name}`);
    const what = plainText(u.what) || composeWhat(p) || null;
    const notes = [p?.notes, p?.license_note].filter(Boolean).map(plainText).join(' ') || null;
    items.push({ type: 'upstream', status: u.status, name: u.name, url: u.url, summary: what || notes || u.policy, policy: u.policy,
      license: u.license, stars: u.stars, last_push: u.last_push, id: `project-${slugify(u.name)}`, kind: 'project', ...where,
      what, notes, updated: u.last_push || null });
  }
  // A library is 'used' only when landscape.json says so (a real dependency); otherwise it is tracked for reference.
  for (const l of ctx.landscape.libraries) {
    const where = place(l.areas || [], `research/landscape.json library ${l.name}`);
    const what = plainText(l.what || l.use || l.role) || null, notes = [l.notes, l.license_note].filter(Boolean).map(plainText).join(' ') || null;
    items.push({ type: 'library', status: l.status || 'reference', name: l.name, url: l.url || `https://github.com/${l.name}`,
      license: l.license_spdx, stars: l.stars, last_push: l.last_push, summary: what || notes || '', id: `library-${slugify(l.name)}`, kind: 'library',
      ...where, what, notes, updated: l.last_push || l.released || null });
  }
  for (const b of ctx.landscape.benchmarks) {
    const where = place(b.areas || [], `research/landscape.json benchmark ${b.name}`);
    const unverified = b.status === 'unverified';
    const what = plainText(b.what || [b.tasks, b.size, b.venue || b.paper].filter(Boolean).join(' · ')) || null;
    const notes = [b.notes, b.ground_truth && `Ground truth: ${b.ground_truth}.`, b.data_license && `Data licence: ${b.data_license}.`,
      unverified && 'Listed from its paper or site; tasks, data and licence not yet checked.'].filter(Boolean).map(plainText).join(' ') || null;
    items.push({ type: 'benchmark', status: unverified ? 'unverified' : 'reference', name: b.name, url: b.url, license: b.license_spdx || b.license,
      stars: b.stars, summary: what || notes || '', id: `benchmark-${slugify(b.name)}`, kind: 'benchmark', ...where, what, notes, updated: b.last_push || null });
  }
  items.unshift(...demos);

  // --------------------------------------------------------------------------- derived fields
  const ids = new Set();
  for (const it of items) {
    if (ids.has(it.id)) throw new Error(`catalogue: two entries have the id ${it.id}`);
    ids.add(it.id);
    if (!it.areas.length) it.areas = ['unplaced'];
    it.family = licenceFamily(it.license);
    if (!it.cover) {
      const tint = TINT[tone(it)] || TINT.unplaced;
      if (['project', 'library', 'benchmark'].includes(it.kind))
        it.cover = generated(it.id, outsideCover({ kind: it.kind, glyphSlug: glyphOf(it), tint, stars: it.stars, license: it.license, family: it.family,
          lastPush: it.last_push, status: it.status, asOf, name: it.name }));
      else {
        const lessons = it.kind === 'lesson' && !/README\.md$/.test(it.page.file) ? (it.page.body.replace(/```[\s\S]*?```/g, '').match(/^### /gm) || []).length : 0;
        it.cover = generated(it.id, pageCover({ kind: KIND_LABEL[it.kind], glyphSlug: glyphOf(it), tint, sections: sectionsOf(it.page.body), lessons, title: it.name }));
      }
    }
  }
  // Featured: a fixed score, so the order is the same on every build and agents can rely on it.
  const STATUS_SCORE = { adopted: 12, used: 12, trial: 8, ours: 6, candidate: 2, reference: 1, unverified: -4, rejected: -12 };
  const BOOST = new Set(['README.md', 'docs/toolkit.md', 'docs/compliant.md', 'docs/common-issues.md', 'research/landscape.md', 'lessons/README.md']);
  for (const it of items) {
    it.score = (it.cover.figure ? 20 : 0) + (it.demo ? 14 : 0) + (it.gyropup ? 8 : 0) + 5 * (LEVELS.indexOf(it.maturity) + 1) +
      (STATUS_SCORE[it.status] || 0) + 3 * Math.log10((it.stars || 0) + 1) + (it.page && BOOST.has(it.page.file) ? 30 : 0);
  }
  const kindIndex = Object.fromEntries(KINDS.map((k, i) => [k.kind, i]));
  const order = it => kindIndex[it.kind] ?? kindIndex.skill;
  items.sort((a, b) => order(a) - order(b) || (a.kind === 'demo' ? 0 : b.score - a.score));
  // Related: entries that share an area (another kind first), else the domain.
  for (const it of items) {
    const real = it.areas.filter(a => !BUCKETS[a]);
    if (!real.length) { it.related = []; continue; }
    const near = items.filter(o => o !== it && o.areas.some(a => real.includes(a)));
    const wide = items.filter(o => o !== it && !near.includes(o) && o.domains.some(d => it.domains.includes(d)));
    it.related = [...near.filter(o => o.kind !== it.kind), ...near.filter(o => o.kind === it.kind), ...wide].slice(0, 6).map(o => o.id);
  }

  // --------------------------------------------------------------------------- catalog.json
  const asJson = it => {
    const o = { type: it.type, status: it.status, name: it.name, url: it.url };
    for (const k of ['summary', 'how', 'policy', 'license', 'stars', 'last_push', 'markdown', 'source']) if (it[k] != null) o[k] = it[k];
    Object.assign(o, { id: it.id, kind: it.kind, areas: it.areas, maturity: it.maturity, what: it.what || null, notes: it.notes || null,
      cover: abs(it.cover.src), demo: it.demo || null, related: it.related, licence_family: it.family, gyropup: it.gyropup, updated: it.updated || null });
    if (it.mode) o.mode = it.mode;
    if (it.cover.anim) o.cover_animated = abs(it.cover.anim);
    return o;
  };
  const catalog = {
    schema: 'cad-agent-catalog/2', origin: ORIGIN, repo: REPO, revision: ctx.revision, built: ctx.built, tagline: ctx.tagline, description: ctx.description,
    index: `${ORIGIN}/catalog/index.json`, page: `${ORIGIN}/catalog`,
    fields: 'Schema 1 fields (type, status, name, url, summary, how, policy, license, stars, last_push, markdown, source) are kept. ' +
      'Schema 2 adds id (stable slug), kind, areas (docs/areas.yaml slugs; "unplaced" until an outside entry has some), maturity (of its areas), ' +
      'what (one plain line), notes (our assessment), cover (our own picture), cover_animated, demo, mode, related (ids), licence_family, gyropup and updated.',
    items: items.map(asJson),
  };
  files.set('catalog.json', JSON.stringify(catalog, null, 2) + '\n');

  // --------------------------------------------------------------------------- catalog/index.json and one file per node
  const inNode = slug => items.filter(it => it.areas.includes(slug) || it.domains.includes(slug));
  const countKinds = list => list.reduce((a, it) => (a[it.kind] = (a[it.kind] || 0) + 1, a), {});
  const brief = it => { const o = asJson(it); delete o.summary; delete o.related; return o; };
  const nodeUrl = slug => `${ORIGIN}/catalog?area=${slug}`, nodeJson = slug => `${ORIGIN}/catalog/${slug}.json`;
  const issueLinks = n => (n.issues || []).map(i => `${REPO}/issues/${i}`);
  const writeNode = (slug, extra) => {
    const list = inNode(slug);
    files.set(`catalog/${slug}.json`, JSON.stringify({ schema: 'cad-agent-catalog-area/1', origin: ORIGIN, revision: ctx.revision, ...extra,
      count: list.length, kinds: countKinds(list), page: nodeUrl(slug), index: `${ORIGIN}/catalog/index.json`, items: list.map(brief) }, null, 2) + '\n');
    return list.length;
  };
  const index = {
    schema: 'cad-agent-catalog-index/1', origin: ORIGIN, revision: ctx.revision, built: ctx.built,
    how: 'Pick a domain or area, fetch its json (every entry placed there, with its url, Markdown twin, command and cover), then open the entry. ' +
      'catalog.json has every entry. The page takes the same filters as URL parameters: kind, area, q, status, licence, maturity, gyropup, demo, sort.',
    catalog: `${ORIGIN}/catalog.json`, page: `${ORIGIN}/catalog`, areas_source: `${REPO}/blob/dev/docs/areas.yaml`,
    count: items.length, kinds: KINDS.map(k => ({ tab: k.tab, kinds: k.kind === 'skill' ? ['skill', 'agent'] : [k.kind], label: k.label,
      count: items.filter(it => tabOf(it.kind) === k.tab).length, page: `${ORIGIN}/catalog?kind=${k.tab}` })),
    maturity: ctx.areas.maturity,
    domains: ctx.areas.domains.map(d => ({ slug: d.slug, title: d.title, scope: d.scope, maturity: d.maturity,
      count: writeNode(d.slug, { slug: d.slug, title: d.title, scope: d.scope, maturity: d.maturity, level: 'domain',
        areas: (d.areas || []).map(a => ({ slug: a.slug, title: a.title, maturity: a.maturity, json: nodeJson(a.slug) })) }),
      json: nodeJson(d.slug), page: nodeUrl(d.slug),
      areas: (d.areas || []).map(a => ({ slug: a.slug, title: a.title, scope: a.scope, maturity: a.maturity, priority: a.priority || [],
        count: writeNode(a.slug, { slug: a.slug, title: a.title, scope: a.scope, maturity: a.maturity, level: 'area', domain: d.slug,
          priority: a.priority || [], issues: issueLinks(a), topics: (a.topics || []).map(t => ({ slug: t.slug, title: t.title, scope: t.scope, maturity: t.maturity, issues: issueLinks(t) })) }),
        kinds: countKinds(inNode(a.slug)), json: nodeJson(a.slug), page: nodeUrl(a.slug), issues: issueLinks(a) })),
    })),
    buckets: Object.entries(BUCKETS).map(([slug, b]) => ({ slug, ...b, count: writeNode(slug, { slug, ...b, level: 'bucket' }), json: nodeJson(slug), page: nodeUrl(slug) })),
  };
  files.set('catalog/index.json', JSON.stringify(index, null, 2) + '\n');

  // --------------------------------------------------------------------------- the page
  const body = catalogPage({ ...ctx, items, demos, nodes, index });
  const counts = items.reduce((a, it) => (a[it.type] = (a[it.type] || 0) + 1, a), {});
  return { catalog, files, body, counts, items };
}

// ----------------------------------------------------------------------------- HTML
const fmtMonth = iso => iso ? new Date(`${iso.slice(0, 10)}T12:00:00Z`).toLocaleDateString('en-US', { month: 'short', year: 'numeric', timeZone: 'UTC' }) : '';
const fmtDay = iso => iso ? new Date(`${iso.slice(0, 10)}T12:00:00Z`).toLocaleDateString('en-GB', { day: 'numeric', month: 'short', year: 'numeric', timeZone: 'UTC' }) : '';
const plural = (n, one, many) => `${n.toLocaleString('en-US')} ${n === 1 ? one : many}`;

function catalogPage({ ORIGIN, items, demos, nodes, index, areas, safeUrl }) {
  const site = u => (u?.startsWith(ORIGIN) ? u.slice(ORIGIN.length) || '/' : u);
  const title = it => it.kind === 'tool' ? `<span class="cmd-prefix">cad-agent </span>${esc(it.command)}`
    : it.kind === 'project' || it.kind === 'library' ? (it.name.includes('/') ? `<span class="owner">${esc(it.name.split('/')[0])}/</span>${esc(it.name.split('/').slice(1).join('/'))}` : esc(it.name))
      : esc(it.name);
  const areaTitle = s => BUCKETS[s]?.title || nodes.get(s)?.title || s;
  const statusText = s => (STATUS_STYLE[s] || STATUS_STYLE.reference)[2];
  const maturity = m => m ? `<span class="mat" data-level="${LEVELS.indexOf(m) + 1}" title="Maturity: ${esc(m)}"><i aria-hidden="true"></i>${esc(m)}</span>` : '';
  const img = (c, w = 400, h = 300, load = 'lazy') => `<img src="${esc(c.src)}"${c.anim ? ` data-anim="${esc(c.anim)}"` : ''} width="${w}" height="${h}" alt="" loading="${load}" decoding="async">`;
  const tokens = it => [...it.areas, ...it.domains].join(' ');

  const card = (it, i) => {
    const k = KIND[it.kind] || KIND.skill;
    const azKey = (it.kind === 'project' || it.kind === 'library' ? it.name.split('/').pop() : it.kind === 'tool' ? it.command : it.name).toLowerCase();
    const text = [it.name, it.what, it.notes, it.policy, it.license, KIND_LABEL[it.kind], statusText(it.status), it.mode,
      ...it.areas.map(areaTitle), ...it.domains.map(areaTitle)].filter(Boolean).join(' ').toLowerCase();
    const realAreas = it.areas.filter(a => !BUCKETS[a]);
    const area = realAreas.length
      ? `<a class="card-area" href="/catalog?area=${esc(realAreas[0])}" data-gallery-link>${esc(areaTitle(realAreas[0]))}</a>${realAreas.length > 1 ? `<span class="more" title="${esc(realAreas.slice(1).map(areaTitle).join(', '))}">+${realAreas.length - 1}</span>` : ''}`
      : it.areas[0] === 'cross-cutting' ? `<a class="card-area" href="/catalog?area=cross-cutting" data-gallery-link>Across all areas</a>` : '';
    const outside = ['project', 'library', 'benchmark'].includes(it.kind);
    const facts = outside ? `<p class="card-facts"><span class="lic lic-${it.family}" title="Licence">${esc(it.license || 'no licence')}</span>` +
      (it.stars != null ? `<span class="stars" title="GitHub stars">★ ${Number(it.stars).toLocaleString('en-US')}</span>` : '') +
      (it.last_push ? `<span title="Last push ${esc(fmtDay(it.last_push))}">pushed <time datetime="${esc(it.last_push)}">${esc(fmtMonth(it.last_push))}</time></span>` : '') + '</p>' : '';
    const meta = area || it.maturity ? `<p class="card-meta">${area}${maturity(it.maturity)}</p>` : '';
    const call = it.how ? `<cad-copy class="card-call" text="${esc(it.how)}" label="Copy call"><code>${esc(it.how)}</code></cad-copy>` : '';
    const notes = it.notes || (outside && it.policy) ? `<details class="card-notes"><summary>Our notes</summary>${it.notes ? `<p>${esc(it.notes)}</p>` : ''}${it.policy ? `<p class="policy">Licence policy: ${esc(it.policy)}.</p>` : ''}</details>` : '';
    const badge = it.mode ? `<span class="pill pill-mode pill-${esc(it.mode)}">${esc(MODE_LABEL[it.mode])}</span>` : '';
    return `<li class="card cat-card" id="${esc(it.id)}" data-item data-type="${esc(it.type)}" data-kind="${esc(k.tab)}" data-tone="${esc(it.domains[0] || it.areas[0])}" data-area="${esc(tokens(it))}" data-status="${esc(it.status)}" data-licence="${esc(it.family)}" data-maturity="${esc(it.maturity || 'none')}"${it.gyropup ? ' data-gyropup="1"' : ''}${it.demo ? ' data-demo="1"' : ''} data-sort-recent="${esc(it.updated || '')}" data-sort-stars="${it.stars ?? ''}" data-sort-maturity="${it.maturity ? LEVELS.indexOf(it.maturity) + 1 : ''}" data-sort-az="${esc(azKey)}" data-text="${esc(text)}"${i >= LIMIT ? ' data-over' : ''}>
<h3 class="card-name"><a href="${esc(site(safeUrl(it.url)))}">${title(it)}</a></h3>
<p class="card-kicker"><span class="pill pill-kind">${esc(KIND_LABEL[it.kind])}</span>${badge}<span class="pill pill-${esc(it.status)}">${esc(statusText(it.status))}</span>${it.gyropup ? '<span class="pill pill-gyropup" title="Needed for Gyropup to become real">Gyropup</span>' : ''}</p>
${it.what ? `<p class="card-what">${esc(it.what)}</p>` : ''}${facts}${meta}${call}${notes}
<div class="card-cover" data-fit="${it.cover.fit}">${img(it.cover)}</div></li>`;
  };

  // The "Play with it" strip: every demo in the data file's order; animated covers play while in view.
  const play = demos.length ? `<section class="play" aria-labelledby="play-title"><div class="play-head"><h2 id="play-title">Play with it</h2>
<p>Demos you can drive or watch, and renders from our own tools. Every picture comes from the code that does the work.</p>${demos.length > 4 ? `<a class="play-all" href="/catalog?kind=demos#demos" data-gallery-link>All ${demos.length} demos <span aria-hidden="true">→</span></a>` : ''}</div>
<ul class="play-strip" data-n="${demos.length}">${demos.map((d, i) => `<li class="play-tile" data-tone="${esc(d.domains[0] || 'unplaced')}"><a href="${esc(site(d.url))}">
<span class="play-cover" data-fit="${d.cover.fit}">${img(d.cover, 640, 400, i < 4 ? 'eager' : 'lazy').replace('<img ', '<img data-anim-view ')}</span>
<span class="play-text"><span class="pill pill-mode pill-${esc(d.mode)}">${esc(MODE_LABEL[d.mode])}</span><span class="play-name">${esc(d.name)}</span><span class="play-what">${esc(d.what)}</span></span></a></li>`).join('')}</ul></section>` : '';

  // Kind tabs: plain links to the sections without script; the gallery makes them tabs.
  const byTab = t => items.filter(it => tabOf(it.kind) === t);
  const tabs = `<nav class="cat-tabs" aria-label="Kinds" data-gallery-tabs><a href="#cat-results" data-tab="">All <span class="count" data-count>${items.length}</span></a>${KINDS.map(k =>
    `<a href="#${k.tab}" data-tab="${k.tab}">${esc(k.label)} <span class="count" data-count>${byTab(k.tab).length}</span></a>`).join('')}</nav>`;

  // Area tree: domains fold; each area shows its glyph, maturity, Gyropup flag and count.
  const areaLink = (slug, label, n, extra = '') => `<a class="area-link" href="/catalog?area=${esc(slug)}" data-gallery-link data-facet="area" data-value="${esc(slug)}"${extra}>${label}<span class="count" data-count>${n}</span></a>`;
  const glyphUse = slug => `<svg class="glyph" viewBox="0 0 100 100" aria-hidden="true" focusable="false"><use href="#g-${esc(GLYPHS[slug] ? slug : DOMAIN_GLYPH[slug] || 'unplaced')}"/></svg>`;
  const dots = m => `<span class="mat-dots" data-level="${LEVELS.indexOf(m) + 1}" title="Maturity: ${esc(m)}"><span class="sr">maturity ${esc(m)}</span></span>`;
  const gyro = n => (n.priority || []).includes('gyropup') ? '<span class="gyro" title="Needed for Gyropup"><span class="sr">needed for Gyropup</span></span>' : '';
  const count = slug => items.filter(it => it.areas.includes(slug) || it.domains.includes(slug)).length;
  const tree = `<nav class="cat-areas" aria-labelledby="areas-title"><h2 class="side-title" id="areas-title">Areas</h2><ul class="area-tree">
<li>${areaLink('', `${glyphUse('cross-cutting')}<span class="area-name">All areas</span>`, items.length, ' aria-current="true"').replace('?area=', '?area=')}</li>
${areas.domains.map(d => `<li><details class="dom" data-domain="${esc(d.slug)}"><summary>${glyphUse(d.slug)}<span class="area-name">${esc(d.title)}</span><span class="count" data-count-of="area:${esc(d.slug)}">${count(d.slug)}</span></summary><ul>
<li>${areaLink(d.slug, `<span class="area-name">Everything in ${esc(d.title.replace(/^./, c => c.toLowerCase()))}</span>`, count(d.slug))}</li>
${(d.areas || []).map(a => `<li>${areaLink(a.slug, `${glyphUse(a.slug)}<span class="area-name">${esc(a.title)}</span>${gyro(a)}${dots(a.maturity)}`, count(a.slug), ` data-maturity="${esc(a.maturity)}"`)}</li>`).join('')}</ul></details></li>`).join('')}
${Object.entries(BUCKETS).map(([slug, b]) => `<li class="bucket">${areaLink(slug, `${glyphUse(slug)}<span class="area-name">${esc(b.title)}</span>`, count(slug))}</li>`).join('')}
</ul></nav>`;

  const option = (name, value, label, n) => `<label class="opt"><input type="checkbox" name="${name}" value="${esc(value)}"><span>${label}</span><span class="count" data-count>${n}</span></label>`;
  const statuses = STATUS_ORDER.filter(s => items.some(it => it.status === s));
  const filters = `<form class="cat-filters" data-gallery-filters aria-labelledby="filters-title"><h2 class="side-title" id="filters-title">Filters</h2>
<fieldset><legend>Status</legend>${statuses.map(s => option('status', s, esc(statusText(s).replace(/^./, c => c.toUpperCase())), items.filter(it => it.status === s).length)).join('')}</fieldset>
<fieldset><legend>Licence</legend>${Object.entries(LICENCES).map(([f, l]) => option('licence', f, l, items.filter(it => it.family === f).length)).join('')}</fieldset>
<fieldset><legend>Maturity of its area</legend>${LEVELS.map(m => option('maturity', m, `${dots(m)}${esc(m.replace(/^./, c => c.toUpperCase()))}`, items.filter(it => it.maturity === m).length)).join('')}</fieldset>
<fieldset><legend>Only</legend>${option('gyropup', '1', 'Needed for Gyropup', items.filter(it => it.gyropup).length)}${option('demo', '1', 'Has a demo', items.filter(it => it.demo).length)}</fieldset>
<button type="button" class="button clear-all" data-gallery-clear>Clear all filters</button></form>`;

  // One panel per domain, area and bucket, shown above the results when it is the chosen area: what it covers, how
  // mature it is and where to help. An area with nothing yet says so.
  const nodePanel = (slug, n, level) => {
    const issues = (n.issues || []).map(i => `<a href="https://github.com/Valpatel/cad-agent/issues/${esc(i)}">#${esc(i)}</a>`).join(', ');
    const priority = (n.priority || []).map(p => p === 'gyropup' ? '<span class="pill pill-gyropup">Gyropup</span>' : '<span class="pill pill-mode">Good demo</span>').join('');
    return `<div class="area-panel" data-gallery-when="area:${esc(slug)}" data-tone="${esc(n.domain || slug)}" hidden>${glyphUse(slug)}<div><p class="eyebrow">${esc(level)}${n.maturity ? ` · ${esc(n.maturity)}` : ''}</p>
<h2>${esc(n.title)} ${priority}</h2><p>${esc(n.scope)}</p>${n.maturity ? `<p class="area-maturity">${maturity(n.maturity)} ${esc(areas.maturity.find(m => m.level === n.maturity)?.means || '')}.</p>` : ''}
${issues ? `<p class="area-issues">Work on it: ${issues}.</p>` : ''}<p class="area-json">For agents: <a href="/catalog/${esc(slug)}.json">catalog/${esc(slug)}.json</a></p></div></div>`;
  };
  const panels = [...areas.domains.flatMap(d => [nodePanel(d.slug, { ...d, domain: d.slug }, 'Domain'),
    ...(d.areas || []).map(a => nodePanel(a.slug, { ...a, domain: d.slug }, `Area in ${d.title}`))]),
    ...Object.entries(BUCKETS).map(([slug, b]) => nodePanel(slug, { ...b, domain: slug }, 'Bucket'))].join('');

  const sections = KINDS.map(k => {
    const list = byTab(k.tab);
    if (!list.length) return '';
    return `<section class="group cat-section" id="${k.tab}" data-group="${k.tab}"${list.length > LIMIT ? ' data-more' : ''}>${k.anchor ? `<span class="anchor" id="${k.anchor}"></span>` : ''}
<header class="cat-section-head"><h2>${esc(k.label)} <span class="count" data-group-count>${list.length}</span></h2><p>${esc(k.blurb)}</p></header>
<ul class="cards cat-grid">${list.map(card).join('')}</ul>
<a class="see-all" href="/catalog?kind=${k.tab}" data-gallery-link data-gallery-more data-gallery-js>See all <span data-group-count>${list.length}</span> ${esc(k.many)} <span aria-hidden="true">→</span></a></section>`;
  }).join('');

  const domains = areas.domains.length, areaCount = areas.domains.reduce((n, d) => n + (d.areas || []).length, 0);
  const quick = ['snap fit', 'FEA', 'KiCad', 'build123d', 'MCP', 'OpenSCAD', 'slicer'];
  const placedOut = items.filter(it => ['project', 'library', 'benchmark'].includes(it.kind) && it.areas[0] !== 'unplaced').length;
  return `${glyphSprite([...new Set([...Object.keys(GLYPHS)])])}
<cad-gallery class="catalog" tab-param="kind" limit="${LIMIT}" item-noun="entry" items-noun="entries" data-overview>
<section class="cat-hero"><p class="eyebrow"><span class="status-dot"></span>Catalogue · ${items.length} entries · ${domains} domains, ${areaCount} areas</p>
<h1>Everything we map, <span>demonstrate</span> or build.</h1>
<p class="hero-description">Other people's open-source projects, libraries and benchmarks come first; our own tools, guides and lessons fill the gaps. All of it sorted into the areas of hardware design it serves.</p>
<div class="cat-search" role="search" data-gallery-js><label class="sr" for="q">Search the catalogue</label><svg class="search-icon" viewBox="0 0 24 24" aria-hidden="true"><circle cx="10.5" cy="10.5" r="6.5"/><path d="M15.5 15.5 21 21"/></svg>
<input id="q" name="q" type="search" placeholder="Search ${items.length} entries: snap fit, FEA, KiCad, MIT…" aria-label="Search the catalogue" autocomplete="off" data-gallery-search><kbd class="search-key" aria-hidden="true">/</kbd></div>
<p class="quick" data-gallery-js><span>Try</span>${quick.map(q => `<a href="/catalog?q=${encodeURIComponent(q)}" data-gallery-link>${esc(q)}</a>`).join('')}</p>
<p class="agent-line"><b>Agents:</b> start at <a href="/catalog/index.json">catalog/index.json</a> (areas, counts, links), then one area's file, such as <a href="/catalog/compliant-mechanisms.json">catalog/compliant-mechanisms.json</a>. Everything: <a href="/catalog.json">catalog.json</a>.${placedOut ? '' : ' Outside entries are not placed in areas yet.'}</p></section>
${play}
<div class="cat-bar">${tabs}</div>
<div class="cat-body"><aside class="cat-side" id="cat-side" aria-label="Areas and filters" data-gallery-sheet data-gallery-js><div class="sheet-panel">
<div class="sheet-head"><p class="sheet-title">Areas and filters</p><button type="button" class="button primary" data-gallery-sheet-close>Show results</button></div>
${tree}${filters}</div></aside>
<div class="cat-main" id="cat-results" data-gallery-results>
<div class="cat-toolbar"><button type="button" class="button sheet-open" aria-controls="cat-side" aria-expanded="false" data-gallery-sheet-open data-gallery-js>Areas and filters <span class="count" data-gallery-active></span></button>
<p id="filter-status" class="filter-status" role="status" aria-live="polite" data-gallery-status>${items.length} entries</p>
<label class="sort" data-gallery-js><span>Sort</span><select id="sort" name="sort" data-gallery-sort>${SORTS.map(([v, l]) => `<option value="${v}"${v === 'recent' || v === 'stars' || v === 'maturity' ? ' data-dir="desc"' : ''}>${l}</option>`).join('')}</select></label></div>
<div class="cat-chips" data-gallery-chips aria-label="Active filters"></div>
${panels}
<p class="cat-empty" data-gallery-empty hidden>No entries match. Try fewer words or clear the filters.</p>
${sections}</div></div>
</cad-gallery><script type="module" src="/kit/gallery.js"></script>`;
}
