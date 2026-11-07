/** Repository ownership map: check the committed inventory and regenerate docs/map.md (#113).
 * Uses the site's existing Markdown parser. No network, dependency discovery or filesystem glob inventory.
 * Data/upstream subtrees retain their layout; their named parent owns them explicitly (see repo-map.json).
 */
import { execFileSync } from 'node:child_process';
import { readFileSync, writeFileSync } from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { marked } from 'marked';
import { createPublication } from '../publication.mjs';

const posix = path.posix;
export function gitFiles(root) {
  return [...new Set(execFileSync('git', ['ls-files', '-z', '--cached', '--others', '--exclude-standard'],
    { cwd: root, maxBuffer: 1 << 27 }).toString('utf8').split('\0').filter(Boolean))].sort();
}
export function inventory(files) {
  const dirs = new Map([['', new Set()]]);
  for (const f of files) {
    const parts = f.split('/');
    for (let i = 0; i < parts.length; i++) {
      const d = parts.slice(0, i).join('/');
      if (!dirs.has(d)) dirs.set(d, new Set());
      dirs.get(d).add(parts[i]);
    }
  }
  return dirs;
}
export function markdown(text) {
  // YAML/frontmatter is metadata, not prose links or a folder diagram.
  const tokens = marked.lexer(text.replace(/^---\r?\n[\s\S]*?\r?\n---\r?\n/, ''));
  const links = [], tables = [], diagrams = [];
  marked.walkTokens(tokens, token => {
    if (token.type === 'link' || token.type === 'image') links.push(token.href);
    if (token.type === 'table') tables.push(token.raw);
    if (token.type === 'html') for (const match of token.text.matchAll(/\b(?:href|src)=["']([^"']*)["']/gi)) links.push(match[1]);
    if (token.type === 'code' && token.lang === 'mermaid') diagrams.push(token.text);
  });
  return { links, tables: tables.join('\n'), diagrams };
}
const beneath = (file, root) => file === root || file.startsWith(root + '/');
const resolve = (from, href) => {
  if (!href || href.startsWith('#') || /^(?:[a-z][a-z0-9+.-]*:|\/\/)/i.test(href)) return null;
  let target; try { target = decodeURIComponent(href.split(/[?#]/)[0]); } catch { return false; }
  if (target.startsWith('/')) return null; // Public routes are checked against actual site output by website-build.
  return posix.normalize(posix.join(posix.dirname(from), target)).replace(/\/$/, '');
};
export function checkMap({ files, read, policy, publication = null }) {
  const dirs = inventory(files), known = new Set(files), problems = [], rows = [];
  const allowedPolicy = new Set(['delegated', 'indexed']);
  const allowedRow = new Set(['root', 'owner', 'reason', 'kind', 'members']);
  const plain = p => typeof p === 'string' && p && !p.startsWith('/') && !p.split('/').some(x => !x || x === '.' || x === '..');
  if (!policy || Object.keys(policy).some(k => !allowedPolicy.has(k)) || !Array.isArray(policy.delegated))
    return { rows, problems: ['repo-map policy needs only delegated/indexed, with a delegated array'] };
  for (const [i, row] of policy.delegated.entries()) {
    if (!row || Object.keys(row).some(k => !allowedRow.has(k)) || !plain(row.root) || !plain(row.owner) || !row.owner.endsWith('.md') ||
        (row.reason !== undefined && typeof row.reason !== 'string') ||
        (row.kind !== undefined && !['owned', 'upstream', 'data'].includes(row.kind)) ||
        (row.members !== undefined && !['linked-files', 'policy'].includes(row.members)))
      problems.push(`repo-map policy row ${i}: invalid path, field, kind or members choice`);
    else if (policy.delegated.slice(0, i).some(before => typeof before?.root === 'string' && (beneath(row.root, before.root) || beneath(before.root, row.root))))
      problems.push(`repo-map policy row ${i}: overlapping delegated roots`);
  }
  if (policy.indexed !== undefined && (!policy.indexed || typeof policy.indexed !== 'object' || Array.isArray(policy.indexed) ||
      Object.entries(policy.indexed).some(([dir, index]) => !plain(dir) || !plain(index))))
    problems.push('repo-map indexed collections need plain folder/index paths');
  if (problems.length) return { rows, problems };

  const parsed = new Map();
  const md = f => { if (!parsed.has(f)) parsed.set(f, markdown(read(f))); return parsed.get(f); };
  const targetExists = target => known.has(target) || dirs.has(target);
  const selected = publication ? publication.selectPages(files) : [];
  const published = new Map(selected.map(row => [row.file, publication.publicPath(row.file)]));
  const publicSources = new Map(selected.map(row => [publication.publicPath(row.file), row.file]));
  const delegate = dir => policy.delegated.find(p => beneath(dir, p.root));
  const ownerOf = dir => {
    const p = delegate(dir);
    if (p) return p.owner;
    if (dir.startsWith('.agents/skills/') && known.has(dir + '/SKILL.md')) return dir + '/SKILL.md';
    return dir ? dir + '/README.md' : 'README.md';
  };
  for (const p of policy.delegated) {
    if (!dirs.has(p.root)) problems.push(`${p.root}: stale delegated root`);
    if (!known.has(p.owner)) problems.push(`${p.root}: missing parent owner ${p.owner}`);
    if (!p.reason?.trim()) problems.push(`${p.root}: delegation needs its consumer/layout reason`);
    if (p.members === 'linked-files' && known.has(p.owner)) {
      const links = md(p.owner).links.map(h => resolve(p.owner, h));
      for (const f of files.filter(f => beneath(f, p.root)))
        if (!links.includes(f)) problems.push(`${p.owner}: delegated file ${f} needs an explicit owner link`);
    }

  }
  for (const dir of [...dirs.keys()].sort()) {
    const owner = ownerOf(dir), p = delegate(dir);
    rows.push({ dir, owner, published: published.get(owner) || null, reason: p?.reason || (owner.endsWith('/SKILL.md') ? 'Installed skill entry; resource links stay relative to SKILL.md.' : 'Owned folder map.') });
    if (!known.has(owner)) { problems.push(`${dir || '.'}: missing owner map ${owner}`); continue; }
    if (owner.endsWith('/SKILL.md')) {
      const links = md(owner).links.map(h => resolve(owner, h));
      for (const f of files.filter(f => beneath(f, dir) && f !== owner))
        if (!links.includes(f)) problems.push(`${owner}: bundled resource ${f} needs an explicit skill link`);
      continue;
    }
    if ((p && owner !== dir + '/README.md' && p.members !== 'policy') || !dir) continue;
    const doc = md(owner);
    if (!doc.diagrams.length) problems.push(`${owner}: missing Mermaid map`);
    if (!doc.tables.trim()) problems.push(`${owner}: missing file/folder table`);
    const links = doc.links.map(h => resolve(owner, h)).filter(Boolean);
    const parent = posix.dirname(dir) === '.' ? '' : posix.dirname(dir), parentOwner = ownerOf(parent);
    if (parentOwner !== owner && !links.includes(parentOwner) && !doc.links.includes(sourceURL(parentOwner))) problems.push(`${owner}: missing up link to ${parentOwner}`);
    for (const name of [...dirs.get(dir)].sort()) {
      if (name === 'README.md') continue;
      const item = dir + '/' + name;
      // A dynamic incident/fragment collection delegates only to its real index/validator, never a blanket filename baseline.
      if (policy.indexed?.[dir] && name.endsWith('.md')) {
        const index = policy.indexed[dir];
        if (item !== index && (!known.has(index) || !md(index).links.some(h => resolve(index, h) === item)))
          problems.push(`${owner}: ${name} missing from authoritative index ${index}`);
        continue;
      }
      if (dir === 'docs/changelog.d' && /^\d+-[a-z0-9-]+\.md$/.test(name)) continue; // Actual cut_release parser tests own fragment format.
      const literal = doc.tables.includes('`' + name + '`') || doc.tables.includes('`' + name + '/`') || doc.tables.includes('[' + name + ']') || doc.tables.includes('[' + name + '/]') || doc.tables.includes('](' + name + '/') || doc.tables.includes('](' + name + ')');
      if (!literal) problems.push(`${owner}: table missing ${name}`);
      if (p?.members === 'policy' && !dirs.has(item) && !links.includes(item))
        problems.push(`${owner}: policy file ${item} needs its exact owner link`);
      if (dirs.has(item)) {
        const childOwner = ownerOf(item);
        if (childOwner !== owner && !links.includes(childOwner) && !links.includes(item)) problems.push(`${owner}: missing down link to ${childOwner}`);
      }
    }
  }
  const ownedPages = new Set(rows.map(r => r.owner));
  // Ownership delegation is independent of link scanning. Only explicit upstream/data prose is exempt.
  for (const f of files.filter(f => f.endsWith('.md') && (!['upstream', 'data'].includes(delegate(f)?.kind) || ownedPages.has(f)))) {
    const text = read(f);
    // Existing ci_gates.changelog_history preserves dated release records byte-for-byte, including the relative
    // destinations valid at release time. Only that region may name a CURRENT selected public Markdown identity.
    const heading = f === 'CHANGELOG.md' && /^##[ \t]+v[0-9]+(?:\.[0-9]+)* \((\d{4}-\d{2}-\d{2})\)[ \t]*\r?$/m.exec(text);
    const date = heading && new Date(heading[1] + 'T00:00:00Z');
    const boundary = heading && Number(heading[1].slice(0, 4)) > 0 && Number.isFinite(date.getTime()) &&
      date.toISOString().slice(0, 10) === heading[1] ? heading.index : text.length;
    for (const [body, historical] of [[text.slice(0, boundary), false], [text.slice(boundary), boundary < text.length]]) {
      for (const href of markdown(body).links) {
        const target = resolve(f, href), source = historical && publicSources.get(target);
        if (target === false || (target !== null && (!targetExists(target) || target.startsWith('../')) &&
            !(source && known.has(source))))
          problems.push(`${f}: broken relative link ${href}`);
      }
    }
  }
  return { problems, rows };
}
const escape = text => String(text).replace(/\|/g, '\\|').replace(/\n/g, ' ');
const sourceURL = file => `https://github.com/Valpatel/cad-agent/blob/dev/${file.split('/').map(encodeURIComponent).join('/')}`;
export function renderMap(rows) {
  const nav = [
    ['Project overview', 'README.md', 'Start here and choose an existing workflow.'],
    ['Toolkit packages', 'software/README.md', 'Reusable code and its domain owners.'],
    ['Guides and research', 'docs/README.md', 'Published explanations, source records and examples.'],
    ['Repository tools', 'tools/README.md', 'Build, release, audit and figure producers.'],
    ['Tests and fixtures', 'tests/README.md', 'Actual consumers, controls and recorded data.'],
    ['Agent kit', '.agents/README.md', 'Installed skills, independent roles and source-only operations.'],
    ['Contribution policy', '.github/CONTRIBUTING.md', 'Review, CI, integration and publication.'],
  ];
  let out = '# Repository map\n\nChoose an owner below. The full tracked inventory is grouped in closed disclosures, including upstream and fixture descendants. This is an ownership map, not a quality percentage or proof of physical performance.\n\n```mermaid\nflowchart TD\n    R["README.md"] --> D["docs/ + .agents/"]\n    R --> S["software/"]\n    R --> T["tests/ + tools/<br/>.github/"]\n    classDef here fill:#fffdf5,stroke:#173d3c,color:#173d3c\n    class R,D,S,T here\n```\n\n| Owner | Use |\n|---|---|\n' + nav.map(([label, file, why]) => `| [${label}](${rows.some(row => row.owner === file && row.published) ? posix.relative('docs', file) : sourceURL(file)}) | ${why} |`).join('\n') +
    '\n\nPublic owner links below are checked against the actual built HTML and catalogue. Code, tool and operational maps remain canonical source pages rather than new catalogue routes. Relative source file/directory destinations are checked; remote availability and source-only Markdown anchors are not newly verified.\n\n## Full inventory\n\n';
  const groups = new Map();
  for (const row of rows) {
    const top = row.dir.split('/')[0] || 'Repository root';
    if (!groups.has(top)) groups.set(top, []);
    groups.get(top).push(row);
  }
  for (const [top, members] of groups) {
    out += `<details>\n<summary>${escape(top)} — ${members.length} folders</summary>\n\n`;
    const owners = new Map();
    for (const row of members) { if (!owners.has(row.owner)) owners.set(row.owner, []); owners.get(row.owner).push(row); }
    for (const [owner, owned] of owners) {
      const published = owned[0].published;
      out += `<details>\n<summary><code>${escape(owner)}</code> — ${owned.length} folders</summary>\n\n` +
        (published ? `[Published owner](${posix.relative('docs', owner)})` : `[Canonical source owner](${sourceURL(owner)}) · Source only`) + '\n\n' +
        [...new Set(owned.map(row => row.reason))].map(reason => `- ${escape(reason)}`).join('\n') + '\n\n| Folder |\n|---|\n' +
        owned.map(row => `| \`${escape(row.dir || '.')}\` |`).join('\n') + '\n\n</details>\n\n';
    }
    out += '</details>\n\n';
  }
  return out + 'Generated by `node tools/site/compiler/site-repo-map.mjs --write`; `--check` verifies freshness. Sources and file tables stay authored by their owners.\n\n[Guides](README.md) · [Style guide](practice/style-guide.md) · [Contributor workflow](../.github/CONTRIBUTING.md)\n';
}
export function main(root, mode) {
  if (Number(process.versions.node.split('.')[0]) < 22) throw new Error('repo-map needs the existing Node 22 site runtime');
  const files = gitFiles(root), read = f => readFileSync(path.join(root, f), 'utf8');
  const policy = JSON.parse(read('tools/site/compiler/repo-map.json'));
  const publication = createPublication(JSON.parse(read('tools/site/page-sources.json')));
  const result = checkMap({ files, read, policy, publication });
  if (result.problems.length) throw new Error(result.problems.join('\n'));
  const rendered = renderMap(result.rows);
  if (mode === '--write') writeFileSync(path.join(root, 'docs/map.md'), rendered);
  else if (read('docs/map.md') !== rendered) throw new Error('docs/map.md is stale: run site-repo-map.mjs --write');
  console.log(`repo-map: ${result.rows.length} folders, explicit owners and relative destinations checked`);
}
if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  try { main(path.resolve(import.meta.dirname, '../../..'), process.argv.includes('--write') ? '--write' : '--check'); }
  catch (error) { console.error(error.message); process.exitCode = 1; }
}
