"""Vendor third-party repositories into vendor/<name>/ safely, pinned by commit, never auto-merged.

    python tools/vendor_sync.py check                 # which upstreams moved (no code downloaded)
    python tools/vendor_sync.py import <name> [--sha SHA] [--initial]
    python tools/vendor_sync.py accept <name>         # after review: record the current findings as the baseline
    python tools/vendor_sync.py notices               # rebuild the vendored table in THIRD_PARTY_NOTICES.md

Safety rules this script enforces:
- Pins are full commit SHAs from vendor/manifest.json; a branch or tag is never trusted.
- Upstream code is fetched with git hooks disabled and exported with `git archive` (no .git, no submodules, nothing
  executed). Excluded paths are dropped before anything is scanned or copied.
- Imports never land on main: unless --initial, the script switches to a new branch vendor-update/<name>-<sha>.
- The security scan reports only findings that are new against the reviewed baseline; a new HIGH finding makes the
  command exit 1 so the update cannot be accepted without an explicit review.
"""
from __future__ import annotations
import argparse, datetime as dt, fnmatch, json, shutil, subprocess, sys, tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
V = ROOT / 'vendor'
MAN = V / 'manifest.json'
SAFE_GIT = ['git', '-c', 'core.hooksPath=/dev/null', '-c', 'protocol.file.allow=never', '-c', 'protocol.ext.allow=never',
            '-c', 'submodule.recurse=false', '-c', 'core.symlinks=false']


def run(cmd, **kw):
    return subprocess.run(cmd, check=True, text=True, capture_output=True, **kw).stdout.strip()


def manifest():
    return json.loads(MAN.read_text())


def save(m):
    MAN.write_text(json.dumps(m, indent=2) + '\n')


def entry(m, name):
    for e in m['projects']:
        if e['name'] == name:
            return e
    sys.exit(f'unknown project {name}; add it to vendor/manifest.json first')


def remote_head(url):
    return run(['git', 'ls-remote', url, 'HEAD']).split()[0]


def cmd_check(_):
    m = manifest(); rows = []
    for e in m['projects']:
        head = remote_head(e['url']); pinned = e.get('sha') or '-'
        rows.append((e['name'], pinned[:12], head[:12], 'up to date' if head == pinned else 'UPSTREAM MOVED'))
    w = max(len(r[0]) for r in rows)
    for r in rows:
        print(f'{r[0]:<{w}}  pinned {r[1]:<12}  upstream {r[2]}  {r[3]}')


def export_tree(url, sha, dest: Path, exclude):
    with tempfile.TemporaryDirectory() as td:
        repo = Path(td) / 'repo'
        subprocess.run(SAFE_GIT + ['clone', '--quiet', '--filter=blob:none', '--no-checkout', url, str(repo)], check=True)
        subprocess.run(SAFE_GIT + ['-C', str(repo), 'fetch', '--quiet', 'origin', sha], check=False)
        full = run(SAFE_GIT + ['-C', str(repo), 'rev-parse', '--verify', f'{sha}^{{commit}}'])
        tar = Path(td) / 'tree.tar'
        subprocess.run(SAFE_GIT + ['-C', str(repo), 'archive', '--format=tar', '-o', str(tar), full], check=True)
        dest.mkdir(parents=True)
        subprocess.run(['tar', '-x', '--no-same-owner', '--no-same-permissions', '-f', str(tar), '-C', str(dest)], check=True)
    # Drop excluded paths and anything that is not a plain file or directory (symlinks could point outside the tree).
    for p in sorted(dest.rglob('*'), key=lambda q: -len(q.parts)):
        rel = str(p.relative_to(dest))
        if p.is_symlink():
            p.unlink(); continue
        if any(fnmatch.fnmatch(rel, g) or fnmatch.fnmatch(rel, g.rstrip('/') + '/*') for g in exclude):
            shutil.rmtree(p) if p.is_dir() else p.unlink()
    return full


def cmd_import(a):
    m = manifest(); e = entry(m, a.name)
    sha = a.sha or remote_head(e['url'])
    branch = run(['git', '-C', str(ROOT), 'rev-parse', '--abbrev-ref', 'HEAD'])
    if branch == 'main' and not a.initial:
        nb = f'vendor-update/{a.name}-{sha[:10]}'
        run(['git', '-C', str(ROOT), 'switch', '-c', nb]); print(f'switched to {nb} (imports never land on main directly)')
    staging = Path(tempfile.mkdtemp(prefix=f'vendor-{a.name}-'))
    new = staging / 'tree'
    full = export_tree(e['url'], sha, new, e.get('exclude', []))
    target = V / a.name
    reports = V / 'reports'; reports.mkdir(exist_ok=True)
    rep = reports / f'{a.name}-{full[:10]}.md'
    base = V / 'baselines' / f'{a.name}.json'
    scan = [sys.executable, str(ROOT / 'tools/security_scan.py')]
    scan += (['diff', str(target), str(new)] if target.exists() else ['scan', str(new)])
    scan += ['--baseline', str(base), '--md', str(rep), '--json', str(staging / 'scan.json'), '--title',
             f'{a.name} {e.get("sha", "none")[:10]} -> {full[:10]} ({e["license"]})']
    rc = subprocess.run(scan).returncode
    if target.exists():
        shutil.rmtree(target)
    shutil.copytree(new, target)
    for patch in sorted((V / 'patches' / a.name).glob('*.patch')) if (V / 'patches' / a.name).exists() else []:
        subprocess.run(['git', '-C', str(ROOT), 'apply', '--directory', f'vendor/{a.name}', str(patch)], check=True)
        print('applied', patch.name)
    e['previous_sha'] = e.get('sha'); e['sha'] = full; e['imported'] = dt.date.today().isoformat(); e['report'] = str(rep.relative_to(ROOT))
    save(m); cmd_notices(None)
    shutil.rmtree(staging, ignore_errors=True)
    print(f'imported {a.name} @ {full[:12]}; review {rep.relative_to(ROOT)}' + ('  ** NEW HIGH FINDINGS: do not accept without review **' if rc else ''))
    return rc


def cmd_accept(a):
    target = V / a.name
    with tempfile.TemporaryDirectory() as td:
        out = Path(td) / 's.json'
        subprocess.run([sys.executable, str(ROOT / 'tools/security_scan.py'), 'scan', str(target), '--json', str(out)], check=False)
        fps = sorted({f['fp'] for f in json.loads(out.read_text())['findings']})
    b = V / 'baselines'; b.mkdir(exist_ok=True)
    e = entry(manifest(), a.name)
    (b / f'{a.name}.json').write_text(json.dumps({'project': a.name, 'sha': e['sha'], 'accepted': dt.date.today().isoformat(), 'fingerprints': fps}, indent=1) + '\n')
    print(f'baseline for {a.name}: {len(fps)} reviewed findings')


TABLE_HEAD = '| Project | Licence | Upstream | Pinned commit | Imported |'
NOTICES_HEAD = ['# Third-party notices', '', 'Code under `vendor/` is copied from the projects below at the pinned commit. Each directory keeps its',
                "upstream LICENSE/NOTICE files; those terms apply to that code. Our changes are listed as patches in `vendor/patches/`.", '']


def vendored_table(projects):
    """The vendored-projects table, one row per manifest entry, in manifest order."""
    return [TABLE_HEAD, '|---|---|---|---|---|'] + [
        f"| {e['name']} | {e['license']} | {e['url']} | `{(e.get('sha') or '-')[:12]}` | {e.get('imported', '-')} |" for e in projects]


def notices_text(text, projects):
    """THIRD_PARTY_NOTICES.md with only the vendored table rebuilt from the manifest. Every other line is kept as it is:
    the showcase, runtime-dependency and web kit sections are hand-kept licence records the manifest knows nothing
    about. Exits, leaving the file as it is, unless it has exactly one vendored table (its header line)."""
    lines = text.split('\n')
    heads = [i for i, line in enumerate(lines) if line.rstrip() == TABLE_HEAD]
    if len(heads) != 1:
        sys.exit(f'THIRD_PARTY_NOTICES.md: expected one vendored table headed "{TABLE_HEAD}", found {len(heads)}; '
                 'left it unchanged')
    start = end = heads[0]
    while end < len(lines) and lines[end].startswith('|'):
        end += 1
    return '\n'.join(lines[:start] + vendored_table(projects) + lines[end:])


def cmd_notices(_):
    path = ROOT / 'THIRD_PARTY_NOTICES.md'
    projects = manifest()['projects']
    text = notices_text(path.read_text(), projects) if path.exists() else '\n'.join(NOTICES_HEAD + vendored_table(projects)) + '\n'
    path.write_text(text)


def main():
    ap = argparse.ArgumentParser(); sub = ap.add_subparsers(dest='cmd', required=True)
    sub.add_parser('check')
    i = sub.add_parser('import'); i.add_argument('name'); i.add_argument('--sha'); i.add_argument('--initial', action='store_true')
    c = sub.add_parser('accept'); c.add_argument('name')
    sub.add_parser('notices')
    a = ap.parse_args()
    return {'check': cmd_check, 'import': cmd_import, 'accept': cmd_accept, 'notices': cmd_notices}[a.cmd](a) or 0


if __name__ == '__main__':
    sys.exit(main())
