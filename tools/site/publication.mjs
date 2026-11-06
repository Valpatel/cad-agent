/** Page-source discovery and stable public paths. No npm dependencies: audit parity runs without a site install. */
import { readFileSync } from 'node:fs';

export const SECTIONS = [
  { id: 'docs', title: 'Docs', match: f => /^docs\/(?:[a-z0-9-]+\/)?[^/]+\.md$/.test(f) || ['README.md', 'CONTRIBUTING.md', 'THIRD_PARTY_NOTICES.md'].includes(f) },
  { id: 'skills', title: 'Skills', match: f => /^skills\/[^/]+\/SKILL\.md$/.test(f) },
  { id: 'agents', title: 'Subagents', match: f => /^agents\/[^/]+\.md$/.test(f) },
  { id: 'lessons', title: 'Lessons (pitfalls)', match: f => /^lessons\/(?:[a-z0-9-]+\/)?[^/]+\.md$/.test(f) },
  { id: 'research', title: 'Research', match: f => /^research\/(?:[a-z0-9-]+\/)?[^/]+\.md$/.test(f) },
];

/** Compile data-only source aliases. Every explicit alias names a required current source, never a fallback. */
export function createPublication(spec) {
  if (spec?.schema !== 1 || !Array.isArray(spec.roots) || !spec.roots.length || !Array.isArray(spec.files) || !spec.files.length)
    throw new Error('page source contract needs schema 1, roots and files');
  const plain = value => typeof value === 'string' && /^(?:\.github\/)?[a-zA-Z0-9_][a-zA-Z0-9_.\/-]*$/.test(value)
    && !value.split('/').some(p => !p || p === '.' || p === '..');
  const aliases = new Map(), publicFiles = new Set();
  for (const row of spec.files) {
    if (!plain(row?.source) || !plain(row?.public) || !row.source.endsWith('.md') || !row.public.endsWith('.md'))
      throw new Error('page source aliases need plain Markdown source and public paths');
    if (aliases.has(row.source) || publicFiles.has(row.public)) throw new Error('duplicate page source or public identity');
    aliases.set(row.source, row.public); publicFiles.add(row.public);
  }
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
  const pageSection = file => {
    if (excluded.has(file) || /(?:^|\/)(?:AGENTS|CLAUDE)\.md$/.test(file)) return null;
    // Old top-level knowledge roots and root policies are no longer page sources, even if a stale copy exists.
    if (roots.some(r => file.startsWith(r.public + '/')) || ['CONTRIBUTING.md', 'THIRD_PARTY_NOTICES.md'].includes(file)) return null;
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
  return { publicPath, pageSection, selectPages, requiredSources: [...aliases.keys()] };
}

export const sourceSpec = JSON.parse(readFileSync(new URL('./page-sources.json', import.meta.url), 'utf8'));
export const { publicPath, pageSection, selectPages, requiredSources } = createPublication(sourceSpec);
