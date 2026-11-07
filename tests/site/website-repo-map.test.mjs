/** Real structural controls for #113. No browser/build/network is needed for the owner/link contract. */
import assert from 'node:assert/strict';
import test from 'node:test';
import { readFileSync, mkdtempSync, writeFileSync, mkdirSync, appendFileSync, rmSync } from 'node:fs';
import { execFileSync } from 'node:child_process';
import os from 'node:os';
import path from 'node:path';
import { createPublication } from '../../tools/site/publication.mjs';
import { checkMap, gitFiles, markdown, renderMap, main } from '../../tools/site/compiler/site-repo-map.mjs';

const root = path.resolve(import.meta.dirname, '../..');
const diagram = '```mermaid\nflowchart TD\nA[unit.py] --> B[result]\n```\n';
const owner = '# Code\n\n' + diagram + '\n| File | Purpose |\n|---|---|\n| [unit.py](unit.py) | Actual module. |\n\n[Up](../README.md)\n';
const base = () => ({ 'README.md': '# Root\n', 'code/README.md': owner, 'code/unit.py': '# actual module\n' });
const check = (data, policy = { delegated: [] }) => checkMap({ files: Object.keys(data).sort(), read: f => data[f], policy });
const rejects = (change, pattern, policy) => {
  const data = base(); change(data);
  assert.match(check(data, policy).problems.join('\n'), pattern);
};

test('the actual repository map and generated inventory are current', () => main(root, '--check'));
test('ordinary owner maps pass without an exception baseline', () => assert.deepEqual(check(base()).problems, []));
test('missing owner map fails', () => rejects(d => delete d['code/README.md'], /missing owner map code\/README/));
test('missing diagram fails', () => rejects(d => d['code/README.md'] = owner.replace(diagram, ''), /missing Mermaid/));
test('missing file table fails', () => rejects(d => d['code/README.md'] = diagram + '[Up](../README.md)', /missing file\/folder table/));
test('a prose mention cannot stand in for a missing file row', () => rejects(d => d['code/README.md'] = owner.replace('| [unit.py](unit.py) | Actual module. |', '') + '\nunit.py\n', /table missing unit.py/));
test('missing up link fails', () => rejects(d => d['code/README.md'] = owner.replace('[Up](../README.md)', ''), /missing up link/));
test('a new unmapped owned child fails even when its sibling is mapped', () => rejects(d => d['code/new/worker.py'] = '# new', /missing owner map code\/new\/README/));
test('a mapped child still needs a parent row and a down link', () => rejects(d => {
  d['code/child/README.md'] = diagram + '\n[Up](../README.md)\n\n| File | Purpose |\n|---|---|\n| [task.py](task.py) | Task. |\n';
  d['code/child/task.py'] = '# task';
}, /table missing child[\s\S]*missing down link/));
test('broken relative links fail anywhere in owned Markdown, including HTML', () => {
  for (const link of ['[bad](missing.md)', '<a href="missing.md">bad</a>', '![bad](missing.png)'])
    rejects(d => d['code/note.md'] = link, /broken relative link missing/);
  assert.deepEqual(markdown('```md\n[example](not-a-real-file.md)\n```').links, []);
});
test('URL destinations are distinguished from local paths', () => {
  const d = base(); d['code/README.md'] += '\n[Web](https://example.com/a) [Fragment](#section)\n';
  assert.deepEqual(check(d).problems, []);
  rejects(d => d['code/README.md'] += '\n[bad](../../escape.md)', /broken relative link/);
});
test('package entry points cannot disappear from a table', () => rejects(d => d['code/__init__.py'] = '"""Public package API."""', /table missing __init__.py/));
test('fixture collection ownership permits nested data but rejects an unmapped new set', () => {
  const d = base();
  d['code/README.md'] = owner + '\n| Folder | Purpose |\n|---|---|\n| [fixtures/](fixtures/README.md) | Fixture sets. |\n';
  d['code/fixtures/README.md'] = diagram + '\n[Up](../README.md)\n\n| Set | Purpose |\n|---|---|\n| [recorded/](recorded/) | Recorded data. |\n';
  d['code/fixtures/recorded/deep/input.json'] = '{}';
  const p = { delegated: [{ root: 'code/fixtures', owner: 'code/fixtures/README.md', reason: 'Fixture data keeps its recorded layout.' }] };
  assert.deepEqual(check(d, p).problems, []);
  d['code/fixtures/new/input.json'] = '{}';
  assert.match(check(d, p).problems.join('\n'), /table missing new/);
});
test('delegation requires an actual owner, reason and live root', () => {
  assert.match(check(base(), { delegated: [{ root: 'gone', owner: 'gone/README.md' }] }).problems.join('\n'), /stale delegated root[\s\S]*missing parent owner[\s\S]*reason/);
});
test('a new role or bundled resource requires an actual parent link', () => {
  const d = base(); d['prompts/reviewer.md'] = '# Reviewer'; d['prompts/README.md'] = '# Accidental role';
  const p = { delegated: [{ root: 'prompts', owner: 'README.md', reason: 'Every Markdown is discovered as a prompt.', members: 'linked-files' }] };
  d['README.md'] += '\n[Reviewer](prompts/reviewer.md)\n';
  assert.match(check(d, p).problems.join('\n'), /prompts\/README.md needs an explicit owner link/);
});
test('an incident collection requires real links in its index', () => {
  const d = base(); d['code/README.md'] += '\n| File | Purpose |\n|---|---|\n| [INDEX.md](INDEX.md) | Incident index. |\n';
  d['code/INDEX.md'] = '# Index\n'; d['code/2026-11-07-incident.md'] = '# Evidence\n';
  const p = { delegated: [], indexed: { code: 'code/INDEX.md' } };
  d['code/INDEX.md'] += '\n[Owner](README.md)\n';
  assert.match(check(d, p).problems.join('\n'), /incident.md missing from authoritative index/);
  d['code/INDEX.md'] += '\n[Incident](2026-11-07-incident.md)\n';
  assert.deepEqual(check(d, p).problems, []);
});
test('NUL-delimited Git inventory preserves spaces, Unicode and newlines', () => {
  // Disposable fixture only; it is not an application worktree or environment.
  const dir = mkdtempSync(path.join(os.tmpdir(), 'repo-map-inventory-'));
  try {
    execFileSync('git', ['init', '-q', dir]);
    mkdirSync(path.join(dir, 'parts'));
    const names = ['parts/β model.md', 'parts/line\nbreak.txt'];
    for (const f of names) writeFileSync(path.join(dir, f), 'data');
    execFileSync('git', ['-C', dir, 'add', '--', ...names]);
    assert.deepEqual(gitFiles(dir), names.sort());
  } finally {
    // Only this test-created fixture: keep all application worktrees/environments and retained failure evidence.
    rmSync(dir, { recursive: true, force: true });
  }
});
test('generated map is deterministic and distinguishes publication from source ownership', () => {
  const rows = [{ dir: 'code', owner: 'code/README.md', published: null, reason: 'Owned code.' }, { dir: 'docs', owner: 'docs/README.md', published: 'docs/README.md', reason: 'Guide.' }];
  const out = renderMap(rows);
  assert.equal(out, renderMap(structuredClone(rows)));
  assert.match(out, /blob\/dev\/code\/README.md/);
  assert.match(out, /Source only/);
  assert.match(out, /\[Published owner\]\(README\.md\)/);
});

// Source-only owner diagrams are deliberately not published as new catalogue routes. Validate them with the same
// kit drawing consumer in the existing required Chromium CI job; never turn a local structural test into a build.
test('all owned folder diagrams render in both themes through the existing kit', { skip: process.env.CAD_AGENT_REPO_MAP_DIAGRAMS !== '1', timeout: 180000 }, async () => {
  const { drawDiagrams } = await import('../../tools/site/compiler/site-diagrams.mjs');
  const files = gitFiles(root), read = f => readFileSync(path.join(root, f), 'utf8');
  const policy = JSON.parse(read('tools/site/compiler/repo-map.json'));
  const result = checkMap({ files, read, policy });
  assert.deepEqual(result.problems, []);
  const maps = [...new Set(result.rows.map(row => row.owner))].filter(f => f.endsWith('/README.md') || f.endsWith('/CONTRIBUTING.md'));
  const escape = s => s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
  const htmls = maps.flatMap(f => markdown(read(f)).diagrams.map(source => `<pre><code class="language-mermaid">${escape(source)}</code></pre>`));
  assert.ok(htmls.length > 50, 'exercise actual owned maps, not a hand-authored example');
  let drew = false;
  for (const theme of ['light', 'dark']) {
    const drawn = await drawDiagrams(htmls, {
      kit: f => readFileSync(path.join(root, 'software/cadagent/webkit', f)),
      site: f => readFileSync(path.join(root, 'tools/site/assets', f)),
      cacheDir: path.join(root, '.cache/site-diagrams'), theme,
    });
    drew ||= drawn.stats.drawn > 0;
    assert.equal(drawn.stats.left, 0, `${theme}: no parse failure/client fallback is an acceptance`);
    for (const html of htmls) assert.match(drawn.draw(html), /<figure class="cad-diagram"[^>]*data-state="ready"/);
    console.log(`repo-map ${theme}: ${maps.length} owner maps, ${htmls.length} blocks, ${JSON.stringify(drawn.stats)}`);
  }
  if (drew && process.env.GITHUB_OUTPUT) appendFileSync(process.env.GITHUB_OUTPUT, 'drew=true\n');
});

test('unknown policy choices and overlapping roots cannot silently broaden an exemption', () => {
  for (const row of [
    { root: 'code', owner: 'README.md', reason: 'r', kind: 'datta' },
    { root: 'code', owner: 'README.md', reason: 'r', members: 'link-files' },
    { root: 'code', owner: 'README.md', reason: 'r', exempt: true },
    { root: '../outside', owner: 'README.md', reason: 'r' },
  ]) assert.match(check(base(), { delegated: [row] }).problems.join('\n'), /invalid path, field, kind or members/);
  assert.match(check(base(), { delegated: [], baseline: [] }).problems.join('\n'), /policy needs/);
  assert.match(check(base(), { delegated: [
    { root: 'code', owner: 'README.md', reason: 'r' }, { root: 'code/child', owner: 'README.md', reason: 'r' },
  ] }).problems.join('\n'), /overlapping delegated roots/);
});
test('authored delegated role, resource and policy Markdown still gets relative-link checks', () => {
  for (const [label, members] of [['role', 'linked-files'], ['resource', 'linked-files'], ['policy', 'policy']]) {
    const d = base(), file = `owned-${label}/guide.md`;
    d['README.md'] += `\n[Owned](./${file})\n`;
    d[file] = '[Missing procedure](missing-procedure.md)';
    const policy = { delegated: [{ root: `owned-${label}`, owner: 'README.md', reason: 'Authored consumer entry.', members, kind: 'owned' }] };
    assert.match(check(d, policy).problems.join('\n'), /broken relative link missing-procedure.md/, label);
  }
});
test('new direct bundled skill resources need actual SKILL links', () => {
  const d = base();
  d['.agents/README.md'] = diagram + '\n[Up](../README.md)\n\n| Folder | Purpose |\n|---|---|\n| [skills/](skills/README.md) | Skills. |\n';
  d['.agents/skills/README.md'] = diagram + '\n[Up](../README.md)\n\n| Folder | Purpose |\n|---|---|\n| [example/](example/SKILL.md) | Skill. |\n';
  d['.agents/skills/example/SKILL.md'] = '# Example skill\n';
  d['.agents/skills/example/helper.md'] = '# Bundled resource\n';
  assert.match(check(d).problems.join('\n'), /bundled resource .*helper.md needs an explicit skill link/);
  d['.agents/skills/example/SKILL.md'] += '\n[Resource](helper.md)\n';
  assert.deepEqual(check(d).problems, []);
  d['.agents/skills/example/helper.md'] += '\n[Bad](missing.md)\n';
  assert.match(check(d).problems.join('\n'), /broken relative link missing.md/);
});
test('native disclosures keep the complete inventory closed and group repeated owners', () => {
  const rows = [{ dir: 'software/vendor/a', owner: 'software/README.md', published: null, reason: 'Pinned upstream.' },
    { dir: 'software/vendor/a/deep', owner: 'software/README.md', published: null, reason: 'Pinned upstream.' }];
  const out = renderMap(rows);
  assert.equal((out.match(/<details>/g) || []).length, 2);
  assert.doesNotMatch(out, /<details[^>]*open/);
  assert.match(out, /`software\/vendor\/a`/);
  assert.match(out, /`software\/vendor\/a\/deep`/);
  assert.equal((out.match(/Pinned upstream\./g) || []).length, 1);
});

test('only dated CHANGELOG history can resolve current selected public Markdown aliases', () => {
  const data = base();
  data['knowledge/README.md'] = diagram + '\n[Up](../README.md)\n\n| File | Purpose |\n|---|---|\n| [current.md](current.md) | Current source. |\n';
  data['knowledge/current.md'] = '# Current guide\n';
  const publication = createPublication({ schema: 1, roots: [{ source: 'knowledge', public: 'docs' }],
    files: [{ source: 'knowledge/current.md', public: 'docs/old-guide.md' }] });
  const run = () => checkMap({ files: Object.keys(data), read: f => data[f], policy: { delegated: [] }, publication });
  data['CHANGELOG.md'] = '# Changelog\n\n## Unreleased\n\n## v1.0.0 (2026-11-07)\n\n[Original public identity](docs/old-guide.md)\n';
  assert.deepEqual(run().problems, []);
  data['CHANGELOG.md'] = data['CHANGELOG.md'].replace('## Unreleased', '## Unreleased\n\n[Current stale source path](docs/old-guide.md)');
  assert.match(run().problems.join('\n'), /CHANGELOG.md: broken relative link docs\/old-guide.md/);
  data['CHANGELOG.md'] = '# Changelog\n\n## v1.0.0 (2026-11-07)\n\n[Unknown alias](docs/not-registered.md)\n';
  assert.match(run().problems.join('\n'), /broken relative link docs\/not-registered.md/);
  data['CHANGELOG.md'] = '# Changelog\n\n## v1.0.0 (2026-02-31)\n\n[Impossible date](docs/old-guide.md)\n';
  assert.match(run().problems.join('\n'), /broken relative link docs\/old-guide.md/);
  data['CHANGELOG.md'] = '# Changelog\n\n## v1.0.0 (2026-11-07)\n\n[Original](docs/old-guide.md)\n';
  data['knowledge/current.md'] += '\n[Equally stale authored path](../docs/old-guide.md)\n';
  assert.match(run().problems.join('\n'), /knowledge\/current.md: broken relative link/);
  delete data['knowledge/current.md'];
  assert.throws(run, /required published source knowledge\/current.md is missing/);
});

test('reference definitions keep whole-document context while their usage owns the history scope', () => {
  const data = base();
  data['knowledge/README.md'] = diagram + '\n[Up](../README.md)\n\n| File | Purpose |\n|---|---|\n| [current.md](current.md) | Current source. |\n';
  data['knowledge/current.md'] = '# Current guide\n';
  const publication = createPublication({ schema: 1, roots: [{ source: 'knowledge', public: 'docs' }],
    files: [{ source: 'knowledge/current.md', public: 'docs/old-guide.md' }] });
  const run = () => checkMap({ files: Object.keys(data), read: f => data[f], policy: { delegated: [] }, publication });
  data['CHANGELOG.md'] = '# Changelog\n\n## Unreleased\n\n[Current stale source][guide]\n\n## v1.0.0 (2026-11-07)\n\n[guide]: docs/old-guide.md\n';
  assert.deepEqual(markdown(data['CHANGELOG.md']).links, ['docs/old-guide.md'], 'the actual whole parser resolves the definition');
  assert.match(run().problems.join('\n'), /CHANGELOG.md: broken relative link docs\/old-guide.md/);
  data['CHANGELOG.md'] = '# Changelog\n\n## Unreleased\n\n[guide]: docs/old-guide.md\n\n## v1.0.0 (2026-11-07)\n\n[Original identity][guide]\n';
  assert.deepEqual(markdown(data['CHANGELOG.md']).links, ['docs/old-guide.md']);
  assert.deepEqual(run().problems, [], 'a released usage may resolve a definition elsewhere');
  data['CHANGELOG.md'] = data['CHANGELOG.md'].replace('docs/old-guide.md', 'docs/unregistered.md');
  assert.match(run().problems.join('\n'), /broken relative link docs\/unregistered.md/);
});
