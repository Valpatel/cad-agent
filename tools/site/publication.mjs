/** Page-source discovery and stable public paths. No npm dependencies: audit parity runs without a site install. */
import { readFileSync } from 'node:fs';
import path from 'node:path';

export const SECTIONS = [
  { id: 'docs', title: 'Docs', match: f => /^docs\/(?:[a-z0-9-]+\/)?[^/]+\.md$/.test(f) || ['README.md', 'CONTRIBUTING.md', 'THIRD_PARTY_NOTICES.md'].includes(f) },
  { id: 'skills', title: 'Skills', match: f => /^skills\/[^/]+\/SKILL\.md$/.test(f) },
  { id: 'agents', title: 'Subagents', match: f => /^agents\/[^/]+\.md$/.test(f) },
  { id: 'lessons', title: 'Lessons (pitfalls)', match: f => /^lessons\/(?:[a-z0-9-]+\/)?[^/]+\.md$/.test(f) },
  { id: 'research', title: 'Research', match: f => /^research\/(?:[a-z0-9-]+\/)?[^/]+\.md$/.test(f) },
];

/** Shared ownership selection only; the repo-map CI check validates prose, diagrams, tables and links. */
export function folderOwner(dir, policy) {
  const row = policy.delegated.find(p => dir === p.root || dir.startsWith(p.root + '/'));
  return row && row.members !== 'folder-maps' ? row.owner : dir ? dir + '/README.md' : 'README.md';
}
export function folderMapPath(file) {
  if (typeof file !== 'string' || !file.endsWith('/README.md') || file.includes('\0') || file.split('/').some(p => !p || p === '.' || p === '..'))
    throw new Error(`folder map needs a plain owned README path: ${file}`);
  // Prefix EVERY directory component: .agents is dot-safe, and cannot collide with an actual _agents folder.
  // Escape URL/Markdown metacharacters and UTF-8 bytes without a literal percent (which servers decode).
  const segment = p => 'd-' + encodeURIComponent(p).replace(/[!'()*~]/g, c => '%' + c.charCodeAt(0).toString(16).toUpperCase()).replaceAll('%', '~');
  return 'repo/folders/' + file.split('/').slice(0, -1).map(segment).join('/') + '/README.md';
}
export function folderMapSources(files, policy, publication) {
  if (!policy || !Array.isArray(policy.delegated)) throw new Error('folder maps need the ownership policy');
  const editorial = new Set(publication.selectPages(files).map(p => p.file));
  const destinations = new Set([...editorial].map(f => publication.publicPath(f)));
  const selected = [];
  for (const file of [...new Set(files)].sort()) {
    if (!file.endsWith('/README.md') || editorial.has(file) || !publication.isCurrentSource(file)) continue;
    const dir = file.slice(0, -'/README.md'.length);
    if (folderOwner(dir, policy) !== file) continue; // upstream and fixture leaves keep their existing owner
    const destination = folderMapPath(file);
    if (destinations.has(destination)) throw new Error(`folder map public route collision: ${destination}`);
    destinations.add(destination);
    const parent = path.posix.dirname(dir);
    selected.push({ file, public: destination, parent: folderOwner(parent === '.' ? '' : parent, policy) });
  }
  return selected;
}

/** Compile data-only source aliases. Every explicit alias names a required current source, never a fallback. */
export function createPublication(spec) {
  if (spec?.schema !== 1 || !Array.isArray(spec.roots) || !spec.roots.length || !Array.isArray(spec.files) || !spec.files.length)
    throw new Error('page source contract needs schema 1, roots and files');
  const plain = value => typeof value === 'string' && /^(?:\.github\/|\.agents\/)?[a-zA-Z0-9_][a-zA-Z0-9_.\/-]*$/.test(value)
    && !value.split('/').some(p => !p || p === '.' || p === '..');
  const aliases = new Map(), publicFiles = new Set();
  for (const row of spec.files) {
    if (!plain(row?.source) || !plain(row?.public) || !row.source.endsWith('.md') || !row.public.endsWith('.md'))
      throw new Error('page source aliases need plain Markdown source and public paths');
    if (aliases.has(row.source) || publicFiles.has(row.public)) throw new Error('duplicate page source or public identity');
    aliases.set(row.source, row.public); publicFiles.add(row.public);
  }
  if (spec.unpublished !== undefined && !Array.isArray(spec.unpublished)) throw new Error('unpublished sources must be an array');
  const excluded = new Set(spec.unpublished || []);
  if ([...excluded].some(f => !plain(f) || aliases.has(f))) throw new Error('invalid or contradictory unpublished source');
  const roots = spec.roots;
  for (let i = 0; i < roots.length; i++) {
    const row = roots[i];
    if (!plain(row?.source) || !plain(row?.public) || row.source === row.public)
      throw new Error('page source roots need distinct plain source and public paths');
    for (const before of roots.slice(0, i)) for (const key of ['source', 'public'])
      if (row[key] === before[key] || row[key].startsWith(before[key] + '/') || before[key].startsWith(row[key] + '/'))
        throw new Error('ambiguous page source roots');
  }
  const publicPath = file => aliases.get(file) || (() => {
    const root = roots.find(r => file.startsWith(r.source + '/'));
    return root ? root.public + file.slice(root.source.length) : file;
  })();
  const isCurrentSource = file => !roots.some(r => file.startsWith(r.public + '/')) && !['CONTRIBUTING.md', 'THIRD_PARTY_NOTICES.md'].includes(file);
  const pageSection = file => {
    if (excluded.has(file) || /(?:^|\/)(?:AGENTS|CLAUDE)\.md$/.test(file)) return null;
    // Old top-level knowledge roots and root policies are no longer page sources, even if a stale copy exists.
    if (!isCurrentSource(file)) return null;
    return SECTIONS.find(s => s.match(publicPath(file))) || null;
  };
  const selectPages = files => {
    const inventory = new Set(files), identities = new Map();
    for (const source of aliases.keys()) if (!inventory.has(source))
      throw new Error(`required published source ${source} is missing from the tracked inventory`);
    for (const root of roots) if (!files.some(f => f.startsWith(root.source + '/')))
      throw new Error(`required published root ${root.source} is missing from the tracked inventory`);
    return files.flatMap(file => {
      const section = pageSection(file);
      if (!section) return [];
      const identity = publicPath(file);
      if (identities.has(identity)) throw new Error(`duplicate public page ${identity}: ${identities.get(identity)} and ${file}`);
      identities.set(identity, file);
      return [{ file, section }];
    });
  };
  // `unpublished` is the legacy editorial exclusion list; owned README maps have their separate detail selection.
  return { publicPath, pageSection, selectPages, isCurrentSource, requiredSources: [...aliases.keys()] };
}

/** Validate actual redirect data against physical pages and their public identities. */
export function validateRedirects(redirects, { tracked, pageFiles, moved, publicPath }) {
  const stubFiles = new Set(moved.map(([from]) => publicPath(from))), seenFrom = new Set();
  for (const [from, to] of redirects) {
    const at = `tools/site/compiler/site-redirects.txt: ${from}`;
    // Pages keeps the first rule for a path and the preview server the last, so a duplicate would make them disagree.
    if (seenFrom.has(from)) throw new Error(`${at} is listed twice`);
    seenFrom.add(from);
    // Pages reads * as a splat and :name as a placeholder, so `docs/lessons/*.md` would redirect every lesson page, the
    // target included, into a loop; the preview server matches exact paths and would never show it. Plain paths only.
    if (!/^[\w-][\w.\/-]*\.md$/.test(from) || path.posix.normalize(from) !== from)
      throw new Error(`${at}: a source is a plain repo path to a .md file (letters, digits, - _ . /), without a leading slash ` +
        'or dot, `.` or `..` segments, `//`, `*` or `:`');
    if ((tracked.includes(from) || [...pageFiles].some(f => publicPath(f) === from)) && !stubFiles.has(from))
      throw new Error(`${at} is still a file in the repo (only its stub may remain)`);
    if (!to || !pageFiles.has(to)) throw new Error(`${at} -> ${to}, which is not a published page`);
  }
  for (const [from, to] of moved) {
    if (!pageFiles.has(to)) throw new Error(`${from} says it moved to ${to}, which is not a published page`);
    const identity = publicPath(from);
    const listed = redirects.find(([f]) => f === identity);
    if (!listed) throw new Error(`${from} moved to ${to}: add "${identity} ${to}" to tools/site/compiler/site-redirects.txt`);
    if (listed[1] !== to) throw new Error(`${from} moved to ${to}: change its line in tools/site/compiler/site-redirects.txt (it says ${listed[1]})`);
  }
}

export const sourceSpec = JSON.parse(readFileSync(new URL('./page-sources.json', import.meta.url), 'utf8'));
export const { publicPath, pageSection, selectPages, requiredSources } = createPublication(sourceSpec);
