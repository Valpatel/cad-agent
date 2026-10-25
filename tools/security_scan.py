"""Static red-flag scan for vendored third-party code.

Scans a source tree (initial import) or only the files that changed between two trees (weekly update) for patterns
that could let a dependency update "hack us": install-time hooks, remote code execution, obfuscated payloads,
credential access, telemetry/self-update, network calls, process spawning, new binaries and dependency changes.

It is a tripwire for a human/agent reviewer, not a proof of safety. Findings are fingerprinted so a reviewed
baseline suppresses known items and an update only reports what is new.

    python tools/security_scan.py scan  <tree> [--baseline vendor/baselines/x.json] [--json out.json] [--md out.md]
    python tools/security_scan.py diff  <old_tree> <new_tree> [--baseline ...] [--json ...] [--md ...]
Exit code: 0 no new HIGH findings, 1 new HIGH findings (block), 2 usage error.
"""
from __future__ import annotations
import argparse, hashlib, json, re, sys
from pathlib import Path

TEXT_EXT = {'.py', '.pyi', '.js', '.mjs', '.cjs', '.ts', '.tsx', '.jsx', '.sh', '.bash', '.zsh', '.ps1', '.bat', '.cmd',
            '.toml', '.cfg', '.ini', '.json', '.yaml', '.yml', '.md', '.txt', '.html', '.rs', '.go', '.c', '.h', '.cpp'}
BINARY_MAGIC = {b'\x7fELF': 'ELF executable/library', b'MZ': 'Windows PE executable', b'\xcf\xfa\xed\xfe': 'Mach-O binary',
                b'\xca\xfe\xba\xbe': 'Mach-O/Java class', b'\x00asm': 'WebAssembly module'}
DEP_FILES = {'requirements.txt', 'requirements-dev.txt', 'pyproject.toml', 'setup.py', 'setup.cfg', 'package.json',
             'package-lock.json', 'pnpm-lock.yaml', 'yarn.lock', 'uv.lock', 'poetry.lock', 'Cargo.toml', 'Cargo.lock', 'go.mod'}

# (rule id, severity, regex, description). HIGH blocks until reviewed; MEDIUM/LOW are reported for review.
RULES = [
    ('exec-decoded', 'HIGH', r'(exec|eval)\s*\(\s*(base64|codecs|zlib|marshal|bytes\.fromhex|binascii|__import__)', 'executes decoded/obfuscated code'),
    ('pipe-to-shell', 'HIGH', r'(curl|wget)[^\n|]*\|\s*(sudo\s+)?(ba|z)?sh\b', 'downloads and pipes into a shell'),
    ('credential-read', 'HIGH', r'(\.ssh/|id_rsa|id_ed25519|\.aws/credentials|\.netrc|\.git-credentials|\.docker/config\.json|keyring\.get_password|GITHUB_TOKEN|ANTHROPIC_API_KEY|OPENAI_API_KEY|gh\s+auth\s+token)', 'touches credentials or secrets'),
    ('npm-install-hook', 'HIGH', r'"(preinstall|install|postinstall|prepare|prepublish)"\s*:', 'npm lifecycle script runs code at install'),
    ('setup-cmdclass', 'HIGH', r'cmdclass\s*=|class\s+\w+\((install|develop|egg_info|build_py)\)', 'setup.py hooks the install step'),
    ('dynamic-import-net', 'HIGH', r'(urlopen|requests\.get|httpx\.get|fetch)\([^)]*\)[^\n]*(exec|eval|import_module|loads)', 'loads code fetched from the network'),
    ('pickle-load', 'MEDIUM', r'(pickle|dill|joblib)\.loads?\(', 'unpickling can execute code'),
    ('eval-exec', 'MEDIUM', r'(?<![\w.])(eval|exec)\s*\(', 'eval/exec of a string'),
    ('subprocess', 'MEDIUM', r'(subprocess\.(run|Popen|call|check_output|check_call)|os\.(system|popen|exec\w*|spawn\w*)|child_process|execSync|spawnSync|\bspawn\()', 'starts processes'),
    ('network', 'MEDIUM', r'(requests\.(get|post|put|request)|urllib\.request|urlopen|httpx\.|aiohttp\.|http\.client|socket\.(socket|create_connection)|\bfetch\(|XMLHttpRequest|new WebSocket|axios\.)', 'makes network calls'),
    ('telemetry', 'MEDIUM', r'(telemetry|posthog|segment\.io|mixpanel|sentry_sdk|amplitude|analytics\.|DO_NOT_TRACK|update[_-]?check|self[_-]?update|check_for_updates)', 'telemetry or self-update'),
    ('env-dump', 'MEDIUM', r'(os\.environ(?!\.get)|process\.env)\s*[\)\]]?\s*(\)|$)', 'reads the whole environment'),
    ('home-write', 'LOW', r'(expanduser\(|Path\.home\(\)|os\.homedir\(\)|XDG_CONFIG_HOME|~/\.)', 'uses the home directory'),
    ('ci-workflow', 'LOW', r'^on:\s*$|^\s*(pull_request_target|workflow_run)\s*:', 'CI workflow trigger (we never run upstream CI)'),
]
COMPILED = [(r, s, re.compile(p, re.M | re.I), d) for r, s, p, d in RULES]
LONG_BLOB = re.compile(r'["\']([A-Za-z0-9+/=]{2000,}|[0-9a-fA-F]{2000,})["\']')


def fp(rule, path, text):
    return hashlib.sha256(f'{rule}|{path}|{" ".join(text.split())}'.encode()).hexdigest()[:16]


def scan_file(root: Path, rel: str):
    p = root / rel
    out = []
    try:
        head = p.open('rb').read(4)
    except OSError:
        return out
    for magic, what in BINARY_MAGIC.items():
        if head.startswith(magic):
            return [dict(rule='binary', severity='HIGH', path=rel, line=0, text=what, desc='binary executable or module', fp=fp('binary', rel, what))]
    if p.name in DEP_FILES:
        out.append(dict(rule='dependency-file', severity='MEDIUM', path=rel, line=0, text=p.name, desc='dependency manifest changed or present; diff it', fp=fp('dependency-file', rel, p.read_bytes().hex()[:64] if p.stat().st_size < 4e6 else 'big')))
    if p.suffix.lower() not in TEXT_EXT and p.name not in DEP_FILES and not p.name.startswith(('Makefile', 'Dockerfile')):
        return out
    if p.stat().st_size > 5e6:
        return out + [dict(rule='large-text', severity='LOW', path=rel, line=0, text=f'{p.stat().st_size} bytes', desc='large text file not scanned', fp=fp('large-text', rel, str(p.stat().st_size)))]
    text = p.read_text(errors='replace')
    is_wf = '.github/workflows' in rel
    for i, line in enumerate(text.splitlines(), 1):
        if len(line) > 4000:
            line = line[:4000]
        for rule, sev, rx, desc in COMPILED:
            if rule == 'ci-workflow' and not is_wf:
                continue
            if rule == 'npm-install-hook' and p.name != 'package.json':
                continue
            if rule == 'setup-cmdclass' and p.name != 'setup.py':
                continue
            if rx.search(line):
                snippet = line.strip()[:200]
                out.append(dict(rule=rule, severity=sev, path=rel, line=i, text=snippet, desc=desc, fp=fp(rule, rel, snippet)))
    for m in LONG_BLOB.finditer(text):
        out.append(dict(rule='encoded-blob', severity='HIGH', path=rel, line=text[:m.start()].count('\n') + 1, text=m.group(0)[:60] + '...', desc='long base64/hex literal', fp=fp('encoded-blob', rel, m.group(0)[:200])))
    return out


def files(root: Path):
    return sorted(str(p.relative_to(root)) for p in root.rglob('*') if p.is_file() and '.git' not in p.relative_to(root).parts)


def changed(old: Path, new: Path):
    a, b = set(files(old)) if old.exists() else set(), set(files(new))
    added = sorted(b - a)
    modified = sorted(f for f in a & b if (old / f).read_bytes() != (new / f).read_bytes())
    return added, modified, sorted(a - b)


def report(findings, baseline_fps, title, extra=''):
    new = [f for f in findings if f['fp'] not in baseline_fps]
    by = {s: [f for f in new if f['severity'] == s] for s in ('HIGH', 'MEDIUM', 'LOW')}
    md = [f'# {title}', '', extra, f'New findings (not in the reviewed baseline): HIGH {len(by["HIGH"])}, MEDIUM {len(by["MEDIUM"])}, LOW {len(by["LOW"])}. '
          f'Suppressed by baseline: {len(findings) - len(new)}.', '']
    for s in ('HIGH', 'MEDIUM', 'LOW'):
        if by[s]:
            md += [f'## {s}', '', '| rule | file:line | text |', '|---|---|---|']
            md += [f"| {f['rule']} | `{f['path']}:{f['line']}` | `{f['text'].replace('|', '/')[:140]}` |" for f in by[s][:400]]
            if len(by[s]) > 400:
                md.append(f'| ... | {len(by[s]) - 400} more | |')
            md.append('')
    return new, '\n'.join(md)


def main(argv=None):
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest='cmd', required=True)
    s = sub.add_parser('scan'); s.add_argument('tree')
    d = sub.add_parser('diff'); d.add_argument('old'); d.add_argument('new')
    for q in (s, d):
        q.add_argument('--baseline'); q.add_argument('--json'); q.add_argument('--md'); q.add_argument('--title', default='Security scan')
    a = ap.parse_args(argv)
    base = set(json.loads(Path(a.baseline).read_text())['fingerprints']) if a.baseline and Path(a.baseline).exists() else set()
    if a.cmd == 'scan':
        root = Path(a.tree); targets = files(root); extra = f'Full scan of {len(targets)} files.'
    else:
        root = Path(a.new); added, modified, removed = changed(Path(a.old), root); targets = added + modified
        extra = f'Changed files: {len(added)} added, {len(modified)} modified, {len(removed)} removed.'
    findings = [f for t in targets for f in scan_file(root, t)]
    new, md = report(findings, base, a.title, extra)
    if a.json:
        Path(a.json).write_text(json.dumps({'findings': findings, 'new': new}, indent=1))
    if a.md:
        Path(a.md).write_text(md)
    print(md.split('\n')[3] if len(md.split('\n')) > 3 else md)
    return 1 if any(f['severity'] == 'HIGH' for f in new) else 0


if __name__ == '__main__':
    sys.exit(main())
