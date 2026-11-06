/** Page-source discovery and stable public paths. No npm dependencies: audit parity runs without a site install. */
const PUBLIC_PATHS = new Map([
  ['.github/CONTRIBUTING.md', 'CONTRIBUTING.md'],
  ['vendor/THIRD_PARTY_NOTICES.md', 'THIRD_PARTY_NOTICES.md'],
]);

export const SECTIONS = [
  { id: 'docs', title: 'Docs', match: f => /^docs\/[^/]+\.md$/.test(f) || f === 'README.md' || PUBLIC_PATHS.has(f) },
  { id: 'skills', title: 'Skills', match: f => /^skills\/[^/]+\/SKILL\.md$/.test(f) },
  { id: 'agents', title: 'Subagents', match: f => /^agents\/[^/]+\.md$/.test(f) },
  { id: 'lessons', title: 'Lessons (pitfalls)', match: f => /^lessons\/(?:[a-z0-9-]+\/)?[^/]+\.md$/.test(f) },
  { id: 'research', title: 'Research', match: f => /^research\/[^/]+\.md$/.test(f) },
];

export const publicPath = file => PUBLIC_PATHS.get(file) || file;
export const pageSection = file => /(?:^|\/)(?:AGENTS|CLAUDE)\.md$/.test(file) ? null : SECTIONS.find(s => s.match(file)) || null;

/** Select actual tracked sources, never substitute a stale public-path file for its relocated source. */
export function selectPages(files) {
  const inventory = new Set(files);
  for (const source of PUBLIC_PATHS.keys()) if (!inventory.has(source))
    throw new Error(`required published source ${source} is missing from the tracked inventory`);
  return files.flatMap(file => {
    const section = pageSection(file);
    return section ? [{ file, section }] : [];
  });
}
