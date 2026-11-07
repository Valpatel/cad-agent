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
  const parsed = new Map();
  const md = f => { if (!parsed.has(f)) parsed.set(f, markdown(read(f))); return parsed.get(f); };
  const targetExists = target => known.has(target) || dirs.has(target);
  const published = new Map(publication ? publication.selectPages(files).map(row => [row.file, publication.publicPath(row.file)]) : []);
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
    if ((p && owner !== dir + '/README.md' && p.members !== 'policy') || owner.endsWith('/SKILL.md') || !dir) continue;
    const doc = md(owner);
    if (!doc.diagrams.length) problems.push(`${owner}: missing Mermaid map`);
    if (!doc.tables.trim()) problems.push(`${owner}: missing file/folder table`);
    const links = doc.links.map(h => resolve(owner, h)).filter(Boolean);
    const parent = posix.dirname(dir) === '.' ? '' : posix.dirname(dir), parentOwner = ownerOf(parent);
    if (parentOwner !== owner && !links.includes(parentOwner)) problems.push(`${owner}: missing up link to ${parentOwner}`);
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
      if (dirs.has(item)) {
        const childOwner = ownerOf(item);
        if (childOwner !== owner && !links.includes(childOwner) && !links.includes(item)) problems.push(`${owner}: missing down link to ${childOwner}`);
      }
    }
  }
  const ownedPages = new Set(rows.map(r => r.owner));
  // Owned Markdown, including operational notes. Upstream/data Markdown keeps its original namespace/content.
  for (const f of files.filter(f => f.endsWith('.md') && (!delegate(f) || ownedPages.has(f)))) {
    for (const href of md(f).links) {
      const target = resolve(f, href);
      if (target === false || (target !== null && (!targetExists(target) || target.startsWith('../'))))
        problems.push(`${f}: broken relative link ${href}`);
    }
  }
  return { problems, rows };
}
const escape = text => String(text).replace(/\|/g, '\\|').replace(/\n/g, ' ');
export function renderMap(rows) {
  return '# Repository map\n\nEvery tracked folder has an owner below. Published owner pages have a separate public link; source-only software, tooling and operational maps retain their canonical GitHub source, with no new catalogue routes. Upstream, fixture and generated-data descendants retain their layouts; the named parent explains the collection. This is an ownership inventory, not a quality percentage or proof of physical performance.\n\n```mermaid\nflowchart TD\n    R["README.md"] --> D["docs/"]\n    R --> S["software/"]\n    R --> T["tests/ + tools/"]\n    R --> A[".agents/ + .github/"]\n    classDef here fill:#fffdf5,stroke:#173d3c,color:#173d3c\n    class R,D,S,T,A here\n```\n\nGenerated by `node tools/site/compiler/site-repo-map.mjs --write`; use `--check` in review. Sources and file tables remain authored by their owners. Public routes and fragments are checked by the existing site build; the map checker validates relative file/directory destinations (not remote availability or Markdown anchors).\n\n| Folder | Canonical source owner | Published owner | Coverage |\n|---|---|---|---|\n' + rows.map(r => `| \`${escape(r.dir || '.')}\` | [${escape(r.owner)}](https://github.com/Valpatel/cad-agent/blob/dev/${r.owner.split('/').map(encodeURIComponent).join('/')}) | ${r.published ? `[Page](/${r.published.replace(/\.md$/, '')})` : 'Source only'} | ${escape(r.reason)} |`).join('\n') + '\n\n[Guides](README.md) · [Style guide](practice/style-guide.md) · [Contributor workflow](../.github/CONTRIBUTING.md)\n';
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
