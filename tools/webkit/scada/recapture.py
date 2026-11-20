#!/usr/bin/env python3
"""Recapture stale SCADA provenance outputs on CI's pinned shell and stage them for upload.

Runs only after the SCADA provenance step has failed (see .github/workflows/webkit.yml).
Each of the five read-only provenance checks runs again; only the generators whose
check failed run, then every check runs once more. Every file the generators changed
must lie inside that generator's declared outputs: anything else (the frozen model
baseline in tests/fixtures/scada/ included) aborts without staging. The changed files
are copied to --out at their repository paths, with a manifest at
.cache/scada/recapture-manifest.json (an ignored path, so unpacking the artifact at the
repository root never stages it). Exit status is nonzero when nothing can be offered, and
then --out is left as it was: staging fills a sibling directory renamed into place only when
complete.

Limits: the recapture is only as good as the pinned shell. It proves the outputs were
produced from the checked-out sources, not that the images look right. On a pull
request the checkout is the merge commit with the base branch.
"""
import argparse
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile

REPO = Path(__file__).resolve().parents[3]
TOOL = 'tools/webkit/scada'
UI = 'software/cadagent/webkit/scada/ui/'
SIM = 'software/cadagent/webkit/scada/sim/'
REQUIREMENTS = TOOL + '/ui/requirements.txt'
MANIFEST = '.cache/scada/recapture-manifest.json'
FROZEN = ('tests/fixtures/scada/',)  # read-only oracle; no generator may touch it

# (check script, generator script, regexes for the repository paths the generator owns)
PAIRS = [
    ('gallery:check', 'gallery:generate', [
        re.escape(UI) + r'img/(symbols|states)/.+',
        re.escape(UI) + r'img/(README\.md|gallery-map\.svg)',
        re.escape(UI) + r'metadata/gallery\.json']),
    ('thumbnails:check', 'thumbnails', [
        re.escape(UI) + r'img/thumbnails/.+',
        re.escape(UI) + r'metadata/thumbnails\.json',
        re.escape(UI) + r'docs/VARIANTS\.md']),
    ('topologies:check', 'topologies:generate', [
        re.escape(SIM) + r'img/topologies/.+',
        re.escape(SIM) + r'metadata/topologies\.json']),
    ('docs:scenarios:check', 'docs:scenarios', [
        re.escape(SIM) + r'scenarios/([a-z0-9]+(-[a-z0-9]+)*/)?README\.md']),
    ('thumbnails:scenarios:check', 'thumbnails:scenarios', [
        re.escape(SIM) + r'img/thumbnails/.+',
        re.escape(SIM) + r'img/README\.md',
        re.escape(SIM) + r'metadata/thumbnails\.json',
        re.escape(SIM) + r'docs/scenario-gallery\.md']),
]


def npm(script):
    return f'npm --prefix {TOOL} run {script}'


def parse_porcelain(data):
    """Parse `git status --porcelain=v1 -z --no-renames` into (code, path) pairs."""
    entries = []
    for record in data.decode('utf-8', 'surrogateescape').split('\0'):
        if not record:
            continue
        if len(record) < 4 or record[2] != ' ':
            raise ValueError(f'Unexpected status record: {record!r}')
        entries.append((record[:2], record[3:]))
    return entries


def split_changes(entries):
    """Return (written, deleted) sorted repository paths."""
    written = sorted(path for code, path in entries if 'D' not in code)
    deleted = sorted(path for code, path in entries if 'D' in code)
    return written, deleted


def generators_for(check_results):
    """Generators to run, in PAIRS order, for each check that failed."""
    return [generate for check, generate, _ in PAIRS if check_results[check] != 0]


def unowned(paths, generators):
    """Paths no generator that ran owns, frozen paths always included."""
    patterns = [re.compile(p) for _, generate, owned in PAIRS if generate in generators for p in owned]
    bad = []
    for path in paths:
        parts = Path(path).parts
        if (path.startswith(FROZEN) or path.startswith('/') or '..' in parts or '\\' in path
                or not any(p.fullmatch(path) for p in patterns)):
            bad.append(path)
    return bad


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def stage(repo, paths, out):
    """Copy each path to out at the same relative path; return its records."""
    records = []
    for relative in paths:
        source = Path(repo) / relative
        if source.is_symlink() or not source.is_file():
            raise ValueError(f'Not a regular file: {relative}')
        target = Path(out) / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
        records.append({'path': relative, 'bytes': target.stat().st_size, 'sha256': sha256(target)})
    return records


def build_manifest(*, source_commit, pr_head, shell, commands, files, deleted):
    return {
        'format': 'scada-provenance-recapture', 'version': 1,
        'source_commit': source_commit, 'pull_request_head': pr_head,
        'shell': shell, 'commands': commands, 'files': files, 'deleted': deleted,
        'apply': 'Unpack at the repository root, delete any "deleted" paths, and commit the files unchanged.',
        'limits': 'Produced by the CI job pinned shell from source_commit; this proves provenance, not visual correctness.',
    }


def pinned_playwright(requirements):
    match = re.search(r'^playwright==(\S+)\s*$', Path(requirements).read_text(), re.M)
    if not match:
        raise ValueError('No pinned playwright in ' + str(requirements))
    return match.group(1)


def shell_record():
    """Prove the pinned capture shell is the one installed; report its browser."""
    pinned = pinned_playwright(REPO / REQUIREMENTS)
    installed = importlib.metadata.version('playwright')
    if installed != pinned:
        raise SystemExit(f'Playwright {installed} is installed but {REQUIREMENTS} pins {pinned}; not recapturing.')
    record = {'python_playwright': installed, 'chromium_on_path': shutil.which('chromium'),
              'browsers_path': os.environ.get('PLAYWRIGHT_BROWSERS_PATH')}
    from playwright.sync_api import sync_playwright
    with sync_playwright() as playwright:
        # Same executable resolution as the generators.
        browser = playwright.chromium.launch(executable_path=shutil.which('chromium'), headless=True, args=['--no-sandbox'])
        record['browser_version'] = browser.version
        browser.close()
    return record


def git(*args):
    # The checkout is mounted into a container as another user; trust only this repository.
    return subprocess.run(['git', '-c', f'safe.directory={REPO}', '-C', str(REPO), *args],
                          check=True, stdout=subprocess.PIPE).stdout


def status():
    # Assumes no generator output is git-ignored: git status would not list it, so it would be
    # missing from the artifact while the re-check here still passed (tested against .gitignore).
    return parse_porcelain(git('status', '--porcelain=v1', '-z', '--untracked-files=all', '--no-renames'))


def run(script, commands):
    print(f'::group::{npm(script)}', flush=True)
    code = subprocess.run(['npm', 'run', script], cwd=REPO / TOOL).returncode
    print('::endgroup::', flush=True)
    commands.append({'command': npm(script), 'exit': code})
    return code


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
    parser.add_argument('--out', type=Path, required=True, help='Empty staging directory for the artifact')
    args = parser.parse_args(argv)
    out = args.out.absolute()
    if out.exists() and any(out.iterdir()):
        raise SystemExit(f'{out} is not empty')
    if status():
        raise SystemExit('The working tree is not clean before recapture; refusing to attribute changes.')
    shell = shell_record()
    commands = []
    first = {check: run(check, commands) for check, _, _ in PAIRS}
    generators = generators_for(first)
    if not generators:
        raise SystemExit('Every provenance check passes here; the failure was not stale provenance. Nothing to recapture.')
    for generate in generators:
        if run(generate, commands):
            raise SystemExit(f'{npm(generate)} failed; nothing staged.')
    final = {check: run(check, commands) for check, _, _ in PAIRS}
    if any(final.values()):
        raise SystemExit('Checks still fail after recapture; nothing staged: ' + ', '.join(c for c, v in final.items() if v))
    written, deleted = split_changes(status())
    bad = unowned(written + deleted, generators)
    if bad:
        raise SystemExit('Recapture changed files outside its generators\' outputs; nothing staged: ' + ', '.join(bad))
    if not written and not deleted:
        raise SystemExit('Generators changed no files; nothing to upload.')
    # All or nothing: fill a sibling directory and rename it to --out only once complete.
    out.parent.mkdir(parents=True, exist_ok=True)
    partial = Path(tempfile.mkdtemp(prefix='.recapture-', dir=out.parent))
    try:
        files = stage(REPO, written, partial)
        manifest = build_manifest(source_commit=git('rev-parse', 'HEAD').decode().strip(),
                                  pr_head=os.environ.get('PR_HEAD_SHA') or None, shell=shell,
                                  commands=commands, files=files, deleted=deleted)
        target = partial / MANIFEST
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(manifest, indent=2) + '\n')
        # On the Linux CI runner rename replaces an empty directory in one operation.
        partial.rename(out)
    except BaseException:
        shutil.rmtree(partial, ignore_errors=True)
        raise
    print(json.dumps({'staged': len(files), 'deleted': deleted, 'generators': generators, 'out': str(out)}))
    return 0


if __name__ == '__main__':
    sys.exit(main())
