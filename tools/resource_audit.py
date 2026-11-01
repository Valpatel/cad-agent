#!/usr/bin/env python3
"""Supply-chain and resource safety report: what cad-agent depends on, vendors and points people to (#117).

    python3 tools/resource_audit.py report                       # offline checks only (default; what CI runs)
    python3 tools/resource_audit.py report --online --repo Valpatel/cad-agent \\
        --json research/security-report.json --md research/security-report.md
    python3 tools/resource_audit.py rows --base origin/dev        # report rows for what this branch adds (for the PR)
    python3 tools/resource_audit.py gate --base HEAD^1 --pr-body-env PR_BODY   # CI: rows present, no new bad item
    python3 tools/resource_audit.py issue --report r.json --repo OWNER/REPO [--post]   # weekly: one issue, kept current

What it reads:
- Python dependencies (pyproject.toml, every extra), npm dependencies (package.json and package-lock.json);
- vendored code (vendor/ with vendor/manifest.json, src/cadagent/webkit/vendor/ with its hash records) and the
  notice files (THIRD_PARTY_NOTICES.md and the kit's own);
- the external links the site publishes: catalog.json's sources (upstreams/registry.yaml, research/landscape.json),
  and the links in every published Markdown page;
- the skills and agents we ship or point to, and install advice in published pages (no installing from registries).

Offline checks (the default) need only the checkout: pins, recorded hashes, licence files, lockfile sources and
install scripts, non-HTTPS links, install-from-registry advice. They are deterministic, so CI can gate on them.
``--online`` adds checks that need the network; an unreachable service is reported as "not verified" (info), never as
a failure, so the weekly run cannot flake. Online sources, adopted rather than re-implemented:

- OSV.dev (``/v1/querybatch``, ``/v1/vulns``): advisories for PyPI and npm packages and git commits, including the
  OpenSSF malicious-packages feed (MAL- ids); the same database pip-audit and osv-scanner query;
- ``npm audit --package-lock-only`` (when npm is installed): the npm registry's advisories for the lockfile;
- PyPI's JSON API and the npm registry: latest release, release dates, licences, deprecation;
- deps.dev (Open Source Insights): resolved dependency graphs, for the direct-plus-transitive counts;
- the GitHub REST API (``gh`` when it is logged in, else GH_TOKEN or GITHUB_TOKEN): archived, deleted or renamed
  repos, licences, push dates, the vendored trees at their pinned commits, published repository advisories;
- the OpenSSF Scorecard API (``api.securityscorecards.dev``): repository hygiene scores.

Exit codes: 0 nothing at or above --fail-on (default high) that is not accepted; 1 there is; 2 usage or tool error.
Findings are fingerprinted; research/security-accepted.yaml lists those read and accepted (check, subject, reason).

Limits: a clean report is not proof of safety. Advisory databases only know what has been reported; licences are
detected from licence files and registry metadata, not by a lawyer; link checks see status codes and redirects, not
content, so a parked or changed page that answers 200 passes; domain expiry is not checked; GitHub links are checked
at repository level (a missing file inside a live repo is not seen). Read findings as leads for a reviewer.
"""
from __future__ import annotations

import argparse
import collections
import concurrent.futures as cf
import datetime as dt
import fnmatch
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCHEMA = 'cad-agent-supply-chain/1'
SEVERITIES = ('critical', 'high', 'medium', 'low', 'info')
RANK = {s: i for i, s in enumerate(SEVERITIES)}
SECTIONS = ('python', 'npm', 'vendored', 'webkit', 'links', 'skills', 'repo')
REPORT_MD = 'research/security-report.md'
ACCEPTED = 'research/security-accepted.yaml'
OUR_REPOS = {'valpatel/cad-agent'}
OUR_HOSTS = {'cad-agent.valpatel.com'}
UA = 'cad-agent-resource-audit/1 (+https://github.com/Valpatel/cad-agent)'
STALE_PUSH_DAYS = 365          # no push for a year: ask whether it is still maintained
STALE_RELEASE_DAYS = 730       # no release for two years
SCORECARD_MIN = 4.0
OSV = 'https://api.osv.dev/v1'
# Hosts that are examples, placeholders or XML namespaces, not resources we send people to.
IGNORED_HOSTS = re.compile(r'^(localhost|127\.0\.0\.1|0\.0\.0\.0|x|(.+\.)?example(\.(com|org|net|test))?|.+\.(test|invalid|local)'
                           r'|www\.w3\.org|schemas\.(microsoft|openxmlformats)\.(com|org)|www\.sitemaps\.org)$')
# Redirect services whose job is to send you to another domain.
RESOLVERS = {'doi.org', 'handle.net', 'youtu.be', 'arxiv.org'}
GITHUB_NOT_REPOS = {'orgs', 'sponsors', 'features', 'topics', 'marketplace', 'settings', 'apps', 'about', 'login',
                    'search', 'advisories', 'collections', 'trending', 'notifications', 'site', 'security', 'enterprise'}


# ----------------------------------------------------------------------------------------------------------- report
class Report:
    def __init__(self, root: Path, as_of: dt.date, online: bool):
        self.root, self.as_of, self.online = Path(root), as_of, online
        self.findings, self.inventory, self.sources, self._fps = [], {s: [] for s in SECTIONS}, {}, set()
        self.extra = {}

    def add(self, check, severity, subject, title, evidence, action, key=''):
        """One finding. Its fingerprint is the check, the subject and a stable key (not the evidence)."""
        assert severity in RANK, severity
        fp = hashlib.sha256(f'{check}|{subject}|{key}'.encode()).hexdigest()[:16]
        if fp not in self._fps:
            self._fps.add(fp)
            self.findings.append(dict(severity=severity, check=check, subject=subject, title=title,
                                      evidence=evidence, action=action, fp=fp))

    def item(self, section, **row):
        self.inventory[section].append(row)
        return row

    def to_json(self):
        findings = sorted(self.findings, key=lambda f: (RANK[f['severity']], f['check'], f['subject'], f['fp']))
        counts = collections.Counter(f['severity'] for f in findings if not f.get('accepted'))
        inv = {k: sorted(v, key=lambda r: (r.get('id', ''), json.dumps(r, sort_keys=True))) for k, v in self.inventory.items()}
        return {
            'schema': SCHEMA, 'as_of': self.as_of.isoformat(), 'mode': 'online' if self.online else 'offline',
            'revision': git(self.root, 'rev-parse', 'HEAD'),
            'summary': {s: counts.get(s, 0) for s in SEVERITIES} | {
                'accepted': sum(1 for f in findings if f.get('accepted')),
                'items': {k: len(v) for k, v in inv.items()}},
            'sources': dict(sorted(self.sources.items())), 'limits': LIMITS, 'extra': self.extra,
            'findings': findings, 'inventory': inv,
        }


LIMITS = [
    'A clean report is not proof of safety: advisory databases (OSV, the npm registry) only know what has been reported.',
    'Licences come from licence files and registry metadata (GitHub, PyPI, npm), matched by keyword; they are not a legal review.',
    'Link checks see status codes and redirects, not content: a parked or replaced page that answers 200 passes. Domain expiry is not checked.',
    'GitHub links are checked at repository level; a missing file or anchor inside a live repository is not seen.',
    'Python versions are checked at the newest release and the lowest release our range allows, not at every version in between.',
    'Offline mode checks only what the checkout shows (pins, hashes, licence files, lockfile, link schemes, install advice).',
]


def vkey(v):
    """Sort key for release versions (1.10.2 > 1.9); a pre-release sorts before its release. Not full PEP 440."""
    m = re.match(r'^v?(\d+(?:\.\d+)*)(.*)$', str(v).strip())
    if not m:
        return ((-1,), 0)
    nums = tuple(int(x) for x in m.group(1).split('.'))
    nums = nums + (0,) * (6 - len(nums)) if len(nums) < 6 else nums
    return (nums, 0 if not m.group(2) or m.group(2).startswith('+') else -1)


def norm(name):
    return re.sub(r'[-_.]+', '-', str(name)).lower()


def git(root, *args):
    try:
        return subprocess.run(['git', '-C', str(root), *args], capture_output=True, text=True, check=True).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return None


def tracked(root: Path, prefix=''):
    """Files git tracks under prefix, plus new ones it does not ignore (every file when root is not a git checkout)."""
    out = git(root, 'ls-files', '-z', '--cached', '--others', '--exclude-standard', '--', prefix or '.')
    if out is not None and (root / '.git').exists():
        return sorted({f for f in out.split('\0') if f and (root / f).is_file()})
    base = root / prefix if prefix else root
    if base.is_file():
        return [prefix]
    return sorted(str(p.relative_to(root)) for p in base.rglob('*') if p.is_file() and '.git' not in p.parts)


def read_text(path: Path):
    try:
        return path.read_text(encoding='utf-8')
    except (OSError, UnicodeDecodeError):
        return None


def days_since(as_of, iso):
    try:
        return (as_of - dt.date.fromisoformat(str(iso)[:10])).days
    except ValueError:
        return None


def load_yaml(text):
    import yaml          # pyyaml: one of cad-agent's two required dependencies, not a new one
    return yaml.safe_load(text)


# ------------------------------------------------------------------------------------------------------ TOML subset
_STR = re.compile(r'"((?:[^"\\]|\\.)*)"|\'([^\']*)\'')


def _strip_comment(line):
    out, quote = [], None
    for ch in line:
        if quote:
            quote = None if ch == quote else quote
        elif ch in '"\'':
            quote = ch
        elif ch == '#':
            break
        out.append(ch)
    return ''.join(out)


def _balanced(s):
    t = _STR.sub('', s)
    return t.count('[') <= t.count(']')


def mini_toml(text):
    """Enough TOML for [project] dependencies and [project.optional-dependencies] where tomllib is missing (3.10)."""
    data, table, pending, buf = {}, None, None, ''
    for raw in text.splitlines():
        line = _strip_comment(raw).strip()
        if pending is not None:
            buf += ' ' + line
            if _balanced(buf):
                table[pending] = [a or b for a, b in _STR.findall(buf)]
                pending = None
            continue
        if not line:
            continue
        m = re.match(r'^\[([^\[\]]+)\]$', line)
        if m:
            table = data
            for part in m.group(1).split('.'):
                table = table.setdefault(part.strip().strip('"'), {})
            continue
        m = re.match(r'^("[^"]+"|[A-Za-z0-9_.-]+)\s*=\s*(.*)$', line)
        if m and table is not None:
            key, val = m.group(1).strip('"'), m.group(2).strip()
            if val.startswith('['):
                if _balanced(val):
                    table[key] = [a or b for a, b in _STR.findall(val)]
                else:
                    pending, buf = key, val
            else:
                s = _STR.fullmatch(val)
                table[key] = (s.group(1) or s.group(2)) if s else val
    return data


def load_toml(text):
    try:
        import tomllib
    except ModuleNotFoundError:
        return mini_toml(text)
    return tomllib.loads(text)


# ------------------------------------------------------------------------------------------------------------ network
class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


class Net:
    """Network access for --online. Every call is memoised and returns (status, data, error); status 0 = no answer."""

    def __init__(self, timeout=20, workers=6):
        self.timeout, self.workers = timeout, workers
        self.token = os.environ.get('GH_TOKEN') or os.environ.get('GITHUB_TOKEN')
        self.gh = None if self.token else shutil.which('gh')
        self._cache, self._lock = {}, threading.Lock()
        self.calls = collections.Counter()

    def github_auth(self):
        return 'token' if self.token else 'gh' if self.gh else 'unauthenticated (60 requests an hour)'

    def _memo(self, key, fn):
        with self._lock:
            if key in self._cache:
                return self._cache[key]
        val = fn()
        with self._lock:
            self._cache[key] = val
        return val

    def request(self, url, data=None, headers=None):
        def go():
            self.calls[urllib.parse.urlsplit(url).hostname] += 1
            body = json.dumps(data).encode() if data is not None else None
            req = urllib.request.Request(url, data=body, method='POST' if body else 'GET')
            req.add_header('User-Agent', UA)
            if body:
                req.add_header('Content-Type', 'application/json')
            for k, v in (headers or {}).items():
                req.add_header(k, v)
            try:
                with urllib.request.urlopen(req, timeout=self.timeout) as r:
                    return r.status, r.read(), ''
            except urllib.error.HTTPError as e:
                return e.code, e.read() if e.fp else b'', ''
            except (urllib.error.URLError, OSError, ValueError) as e:
                return 0, b'', str(getattr(e, 'reason', e))[:200]
        return self._memo(('req', url, json.dumps(data, sort_keys=True) if data is not None else None), go)

    def json(self, url, data=None, headers=None):
        status, body, err = self.request(url, data, headers)
        try:
            return status, (json.loads(body) if body else None), err
        except ValueError:
            return status, None, err or 'answer is not JSON'

    def github(self, path):
        """GET a GitHub REST path ('repos/o/r'), with gh's login, a token, or unauthenticated."""
        if self.token:
            return self.json(f'https://api.github.com/{path}', headers={
                'Authorization': f'Bearer {self.token}', 'Accept': 'application/vnd.github+json'})
        if self.gh:
            def go():
                self.calls['api.github.com'] += 1
                try:
                    r = subprocess.run([self.gh, 'api', '-i', path], capture_output=True, text=True, timeout=self.timeout * 3)
                except (OSError, subprocess.TimeoutExpired) as e:
                    return 0, None, str(e)[:200]
                head, _, body = r.stdout.replace('\r\n', '\n').partition('\n\n')
                m = re.match(r'HTTP/[\d.]+\s+(\d+)', head)
                if not m:
                    return 0, None, (r.stderr.strip() or 'no answer')[:200]
                try:
                    return int(m.group(1)), (json.loads(body) if body.strip() else None), ''
                except ValueError:
                    return int(m.group(1)), None, 'answer is not JSON'
            return self._memo(('gh', path), go)
        return self.json(f'https://api.github.com/{path}', headers={'Accept': 'application/vnd.github+json'})

    def graphql(self, query):
        if self.token:
            return self.json('https://api.github.com/graphql', data={'query': query},
                             headers={'Authorization': f'Bearer {self.token}'})
        if self.gh:
            try:
                r = subprocess.run([self.gh, 'api', 'graphql', '-f', f'query={query}'], capture_output=True, text=True,
                                   timeout=self.timeout * 3)
                return (200 if r.returncode == 0 else 0), json.loads(r.stdout or 'null'), r.stderr.strip()[:200]
            except (OSError, ValueError, subprocess.TimeoutExpired) as e:
                return 0, None, str(e)[:200]
        return 0, None, 'needs a GitHub token or gh'

    def probe(self, url):
        """Follow redirects by hand: ([(status, url), ...], error). HEAD first; GET when a server refuses HEAD."""
        def go():
            opener = urllib.request.build_opener(_NoRedirect)
            chain, cur, method, retried = [], url, 'HEAD', False
            for _ in range(10):
                self.calls[urllib.parse.urlsplit(cur).hostname] += 1
                req = urllib.request.Request(cur, method=method, headers={'User-Agent': UA, 'Accept': '*/*'})
                try:
                    with opener.open(req, timeout=self.timeout) as r:
                        status, loc = r.status, None
                except urllib.error.HTTPError as e:
                    status, loc = e.code, e.headers.get('Location')
                    e.close()
                except (urllib.error.URLError, OSError, ValueError) as e:
                    return chain, str(getattr(e, 'reason', e))[:200]
                if method == 'HEAD' and not retried and status in (400, 403, 404, 405, 406, 429, 500, 501, 503):
                    method, retried = 'GET', True
                    continue
                chain.append((status, cur))
                if 300 <= status < 400 and loc:
                    cur = urllib.parse.urljoin(cur, loc)
                    continue
                return chain, ''
            return chain, 'too many redirects'
        return self._memo(('probe', url), go)

    def map(self, fn, items):
        items = list(items)
        with cf.ThreadPoolExecutor(max_workers=self.workers) as ex:
            return dict(zip(items, ex.map(fn, items)))


# ---------------------------------------------------------------------------------------------------------------- OSV
def vuln_severity(v):
    if str(v.get('id', '')).startswith('MAL-'):
        return 'critical'
    levels = {'CRITICAL': 'critical', 'HIGH': 'high', 'MODERATE': 'medium', 'MEDIUM': 'medium', 'LOW': 'low'}
    sev = str((v.get('database_specific') or {}).get('severity') or '').upper()
    for a in v.get('affected') or []:
        sev = sev or str((a.get('database_specific') or {}).get('severity') or '').upper()
        sev = sev or str((a.get('ecosystem_specific') or {}).get('severity') or '').upper()
    return levels.get(sev, 'medium')          # unrated advisories count as medium


def fixed_in(v, ecosystem, name):
    out = set()
    for a in v.get('affected') or []:
        p = a.get('package') or {}
        if p.get('ecosystem', '').lower() == ecosystem.lower() and norm(p.get('name', '')) == norm(name):
            for r in a.get('ranges') or []:
                out |= {ev['fixed'] for ev in r.get('events') or [] if 'fixed' in ev}
    return out


def osv_lookup(rep, net, asks):
    """asks: [{'q': OSV query, ...}] -> each ask gets 'vulns': [canonical advisory dicts] (None when OSV failed)."""
    if not asks:
        return asks
    ids = []
    for start in range(0, len(asks), 500):
        status, body, err = net.json(f'{OSV}/querybatch', data={'queries': [a['q'] for a in asks[start:start + 500]]})
        if status != 200 or not isinstance(body, dict):
            rep.sources['osv'] = f'not verified: {err or "HTTP " + str(status)}'
            rep.add('osv-unverified', 'info', 'osv.dev', 'OSV could not be queried; advisories were not checked',
                    err or f'HTTP {status}', 'Run the report again with --online later.')
            for a in asks:
                a['vulns'] = None
            return asks
        ids += [sorted({v['id'] for v in (r.get('vulns') or [])}) for r in body.get('results', [])]
    rep.sources['osv'] = 'osv.dev querybatch and vulns'
    details = net.map(lambda i: net.json(f'{OSV}/vulns/{i}')[1], sorted({i for group in ids for i in group}))
    for a, group in zip(asks, ids):
        seen, out = set(), []
        for i in group:                       # the same advisory under several ids (GHSA, PYSEC, CVE) counts once
            v = details.get(i) or {'id': i}
            names = {i, *(v.get('aliases') or [])}
            if names & seen:
                continue
            seen |= names
            ghsa = sorted(n for n in names if n.startswith('GHSA-'))
            out.append(dict(id=ghsa[0] if ghsa and not i.startswith('MAL-') else i, severity=vuln_severity(v),
                            summary=(v.get('summary') or v.get('details') or '')[:160].strip(),
                            fixed=sorted(fixed_in(v, a['q'].get('package', {}).get('ecosystem', ''),
                                                  a['q'].get('package', {}).get('name', '')), key=vkey)))
        a['vulns'] = out
    return asks


def worst(vulns):
    return min((v['severity'] for v in vulns), key=RANK.get, default='info')


def upgrade_hint(vulns, version):
    """'>= X' clearing every advisory that has a fix above version, and the ids that have none."""
    target, nofix = None, []
    for v in vulns:
        above = [f for f in v['fixed'] if vkey(f) > vkey(version)]
        if not above:
            nofix.append(v['id'])
        else:
            first = min(above, key=vkey)
            target = first if target is None or vkey(first) > vkey(target) else target
    return target, nofix


def advisory_finding(rep, subject, label, version, vulns, context, action_fix, scope=''):
    """One finding per package and context, listing every advisory; MAL- (malicious) ids are always critical."""
    if not vulns:
        return
    ids = sorted(v['id'] for v in vulns)
    sev = worst(vulns)
    target, nofix = upgrade_hint(vulns, version)
    if context == 'floor':
        sev = 'critical' if any(i.startswith('MAL-') for i in ids) else 'low'
    def fix(v):
        above = [f for f in v['fixed'] if vkey(f) > vkey(version)]
        return f', fixed in {min(above, key=vkey)}' if above else ', no fix listed'
    listed = '; '.join(f"{v['id']} ({v['severity']}{fix(v)}): {v['summary']}"
                       for v in sorted(vulns, key=lambda v: (RANK[v['severity']], v['id']))[:8])
    more = f' and {len(vulns) - 8} more' if len(vulns) > 8 else ''
    action = action_fix.format(target=target) if target else 'No fixed release is known: check whether our use is exposed; pin around it or replace it.'
    if nofix and target:
        action += f' No fix yet for {", ".join(nofix)}.'
    if any(i.startswith('MAL-') for i in ids):
        action = 'Malicious package: remove it now, rotate any secret the environment could read, and tell the owner.'
    n = f"{len(ids)} known {'advisory' if len(ids) == 1 else 'advisories'}"
    title = {'floor': f'our range allows {label} {version}, which has {n}',
             'latest': f'the newest release, {label} {version}, has {n}',
             'installed': f'{label} {version} installed here has {n}',
             'locked': f'{label} {version} in the lockfile has {n}',
             'vendored': f'the vendored {label} {version} has {n}',
             'commit': f'the pinned commit of {label} is affected by {n}'}[context]
    rep.add('advisory', sev, subject, title + scope, listed + more, action, key=f'{context}|{version}|{",".join(ids)}')


# ----------------------------------------------------------------------------------------------------------- licences
LICENCE_TEXT = [  # (detected id, keywords that must all appear), first match wins
    ('AGPL', ('GNU AFFERO GENERAL PUBLIC LICENSE',)), ('LGPL', ('GNU LESSER GENERAL PUBLIC LICENSE',)),
    ('GPL', ('GNU GENERAL PUBLIC LICENSE',)), ('Apache-2.0', ('Apache License', 'Version 2.0')),
    ('MPL-2.0', ('Mozilla Public License',)), ('OFL-1.1', ('SIL OPEN FONT LICENSE',)),
    ('ISC', ('Permission to use, copy, modify, and/or distribute',)),
    ('MIT', ('Permission is hereby granted, free of charge',)),
    ('BSD-3-Clause', ('Redistribution and use in source and binary forms', 'Neither the name')),
    ('BSD-2-Clause', ('Redistribution and use in source and binary forms',)),
]
COPYLEFT = re.compile(r'\b(A?GPL|LGPL|EUPL|MPL|SSPL|GNU (Affero |Lesser )?General Public)', re.I)


def detect_licence(text):
    up = (text or '').upper()
    for lid, keys in LICENCE_TEXT:
        if all(k.upper() in up for k in keys):
            return lid
    return None


def same_licence(recorded, detected):
    a, b = norm(recorded or ''), norm(detected or '')
    return bool(a and b) and (a == b or a.startswith(b) or b.startswith(a))


def licence_from_pypi(info):
    if info.get('license_expression'):
        return info['license_expression']
    lic = (info.get('license') or '').strip()
    if lic and len(lic) <= 60 and '\n' not in lic:
        return lic
    cls = [c.split(' :: ')[-1] for c in info.get('classifiers') or [] if c.startswith('License :: ')]
    return ', '.join(cls) or (lic[:60] + '…' if lic else None)


# ------------------------------------------------------------------------------------------------------------- Python
REQ = re.compile(r'^\s*([A-Za-z0-9][A-Za-z0-9._-]*)\s*(\[[^\]]*\])?\s*([^;]*?)\s*(?:;(.*))?$')


def parse_req(s):
    m = REQ.match(s)
    if not m:
        return None
    return dict(name=norm(m.group(1)), spec=m.group(3).replace(' ', ''), marker=(m.group(4) or '').strip())


def spec_floor(spec):
    """The lower bound of a specifier: ('>=', '3.7'), or None when it has none."""
    for part in spec.split(','):
        m = re.match(r'^(>=|===|==|~=|>)v?([0-9][0-9A-Za-z.!+-]*)$', part.strip())
        if m:
            return m.group(1), m.group(2)
    return None


def python_packages(text):
    proj = (load_toml(text) or {}).get('project', {})
    groups = {'required': proj.get('dependencies') or []}
    groups.update(proj.get('optional-dependencies') or {})
    pkgs, bad = {}, []
    for group, reqs in groups.items():
        for raw in reqs:
            r = parse_req(raw)
            if not r:
                bad.append((group, raw))
                continue
            p = pkgs.setdefault(r['name'], dict(id=f"pypi:{r['name']}", name=r['name'], groups=[], specs={}))
            p['groups'].append(group)
            p['specs'][group] = r['spec']
    return groups, pkgs, bad


def lowest_release(releases, floor):
    """The lowest final (non-pre, non-yanked) release a floor allows."""
    op, ver = floor
    if op in ('==', '==='):
        return ver
    ok = []
    for v, files in (releases or {}).items():
        if not re.fullmatch(r'\d+(\.\d+)*', v) or (files and all(f.get('yanked') for f in files)):
            continue
        if vkey(v) > vkey(ver) or (op != '>' and vkey(v) == vkey(ver)):
            ok.append(v)
    if op == '~=':                 # ~=X.Y allows X.*; ~=X.Y.Z allows X.Y.*
        prefix = ver.split('.')[:-1]
        ok = [v for v in ok if v.split('.')[:len(prefix)] == prefix]
    return min(ok, key=vkey) if ok else None


def check_python(rep, net, installed=False):
    text = read_text(rep.root / 'pyproject.toml')
    if text is None:
        return
    groups, pkgs, bad = python_packages(text)
    notices = (read_text(rep.root / 'THIRD_PARTY_NOTICES.md') or '').lower()
    for group, raw in bad:
        rep.add('py-unparsed', 'low', f'pypi:{raw}', 'a requirement this report cannot read', f'{group}: {raw!r}',
                'Write it as name[extras]>=version; markers after ";".')
    for name, p in sorted(pkgs.items()):
        floors = {g: spec_floor(s) for g, s in p['specs'].items()}
        row = rep.item('python', id=p['id'], name=name, groups=sorted(set(p['groups'])),
                       range={g: s or 'any' for g, s in sorted(p['specs'].items())})
        nofloor = sorted(g for g, f in floors.items() if f is None)
        if nofloor:
            sev = 'info' if set(nofloor) <= {'dev'} else 'low'
            rep.add('py-no-floor', sev, p['id'], f'{name} has no lower version bound in {", ".join(nofloor)}',
                    'pyproject.toml: ' + ', '.join(f"{g}: {name}{p['specs'][g]}" for g in nofloor),
                    'Set a floor at a release without known advisories (and the oldest one you are willing to support), '
                    'so an install with old pins cannot pick something worse.')
        lows = [f for f in floors.values() if f]
        low = min(lows, key=lambda f: vkey(f[1])) if lows else None
        row['floor'] = low[0] + low[1] if low else None
        if installed:
            try:
                import importlib.metadata as md
                row['installed'] = md.version(name)
            except Exception:
                row['installed'] = None
    rep.extra['python_groups'] = {g: sorted({parse_req(r)['name'] for r in reqs if parse_req(r)}) for g, reqs in groups.items()}
    if not net:
        return
    rep.sources['pypi'] = 'pypi.org JSON API'
    meta = net.map(lambda n: net.json(f'https://pypi.org/pypi/{n}/json'), sorted(pkgs))
    asks = []
    for row in rep.inventory['python']:
        status, data, err = meta[row['name']]
        if status == 404:
            rep.add('py-not-on-pypi', 'high', row['id'], f"{row['name']} is not on PyPI",
                    'pypi.org answers 404', 'A missing name can be registered by anyone (dependency confusion): '
                    'fix the name or remove the requirement.')
            continue
        if status != 200 or not data:
            rep.add('py-unverified', 'info', row['id'], 'PyPI could not be read', err or f'HTTP {status}', 'Run again later.')
            continue
        info, releases = data.get('info') or {}, data.get('releases') or {}
        latest = info.get('version')
        files = releases.get(latest) or []
        row.update(latest=latest, last_release=min((f['upload_time'][:10] for f in files), default=None),
                   licence=licence_from_pypi(info))
        lows = [spec_floor(s) for s in row['range'].values() if s != 'any']
        lows = [f for f in lows if f]
        if lows:
            row['floor_release'] = lowest_release(releases, min(lows, key=lambda f: vkey(f[1])))
        if any('Development Status :: 7 - Inactive' in c for c in info.get('classifiers') or []):
            rep.add('py-inactive', 'medium', row['id'], f"{row['name']} says it is inactive",
                    'classifier "Development Status :: 7 - Inactive"', 'Find a maintained replacement or vendor what we use.')
        age = days_since(rep.as_of, row['last_release']) if row['last_release'] else None
        if age is not None and age > STALE_RELEASE_DAYS:
            rep.add('py-stale', 'low', row['id'], f"no {row['name']} release for {age // 365} years",
                    f"latest {latest} on {row['last_release']}", 'Check the project is maintained; can we drop it?')
        if row.get('licence') and COPYLEFT.search(row['licence']) and row['name'] not in notices and norm(row['name']) not in norm(notices):
            rep.add('licence-copyleft-unlisted', 'low', row['id'], f"copyleft {row['name']} is not in THIRD_PARTY_NOTICES.md",
                    f"PyPI licence: {row['licence']}", 'Add it to the runtime table with how we use it (imported or external program).')
        for ctx, ver in (('latest', latest), ('floor', row.get('floor_release')), ('installed', row.get('installed'))):
            if ver and not (ctx != 'latest' and ver == latest):
                asks.append(dict(q={'package': {'ecosystem': 'PyPI', 'name': row['name']}, 'version': ver}, row=row, ctx=ctx, ver=ver))
    for a in osv_lookup(rep, net, asks):
        if a.get('vulns') is None:
            continue
        a['row'].setdefault('advisories', {})[a['ctx']] = sorted(v['id'] for v in a['vulns'])
        scope = ' (dev extra only)' if set(a['row']['groups']) <= {'dev'} else ''
        advisory_finding(rep, a['row']['id'], a['row']['name'], a['ver'], a['vulns'], a['ctx'],
                         {'floor': 'Raise the floor to >={target} in pyproject.toml.',
                          'latest': 'Upgrade to >={target} when it is released.',
                          'installed': 'Upgrade this environment to >={target}.'}[a['ctx']], scope)
    # deps.dev: the resolved graph of each newest release, for "direct plus transitive" per extra.
    rep.sources['deps.dev'] = 'api.deps.dev v3 dependency graphs (newest releases)'
    by_name = {r['name']: r for r in rep.inventory['python']}
    graphs = net.map(lambda n: net.json(f"https://api.deps.dev/v3/systems/pypi/packages/{urllib.parse.quote(n)}"
                                        f"/versions/{urllib.parse.quote(by_name[n]['latest'])}:dependencies"),
                     sorted(n for n, r in by_name.items() if r.get('latest')))
    closure = {}
    for name, (status, data, _err) in graphs.items():
        if status == 200 and isinstance(data, dict) and data.get('nodes'):
            deps = sorted({norm(n['versionKey']['name']) for n in data['nodes'] if n.get('relation') != 'SELF'})
            by_name[name]['dependencies'] = len(deps)
            closure[name] = set(deps)
    rep.extra['python_counts'] = {
        g: {'direct': len(names), 'with_transitive': len(set(names).union(*[closure.get(n, set()) for n in names]))
            if all(n in closure for n in names) else None}
        for g, names in rep.extra['python_groups'].items()}


# ---------------------------------------------------------------------------------------------------------------- npm
EXACT = re.compile(r'^\d+\.\d+\.\d+(?:[-+][0-9A-Za-z.-]+)?$')


def npm_packages(lock):
    out = {}
    for path, e in (lock.get('packages') or {}).items():
        if not path or e.get('link'):
            continue
        name = e.get('name') or path.rsplit('node_modules/', 1)[-1]
        out.setdefault(name, []).append(dict(path=path, **e))
    return out


def check_npm(rep, net, npm_audit=True):
    pj_text, lock_text = read_text(rep.root / 'package.json'), read_text(rep.root / 'package-lock.json')
    if pj_text is None:
        return
    pj = json.loads(pj_text)
    direct = {}
    for field in ('dependencies', 'devDependencies', 'optionalDependencies'):
        direct.update(pj.get(field) or {})
    if lock_text is None:
        if direct:
            rep.add('npm-no-lockfile', 'high', 'npm:package-lock.json', 'package.json has dependencies but no lockfile',
                    'package-lock.json is missing', 'Commit package-lock.json so installs are reproducible and auditable.')
        return
    lock = json.loads(lock_text)
    if int(lock.get('lockfileVersion') or 0) < 2:
        rep.add('npm-lockfile-old', 'medium', 'npm:package-lock.json', 'lockfile version 1 has no per-package integrity record',
                f"lockfileVersion {lock.get('lockfileVersion')}", 'Regenerate it with npm 7 or later.')
    root_pkg = (lock.get('packages') or {}).get('', {})
    locked_direct = {}
    for field in ('dependencies', 'devDependencies', 'optionalDependencies'):
        locked_direct.update(root_pkg.get(field) or {})
    for name, spec in sorted(direct.items()):
        if not EXACT.match(str(spec)):
            rep.add('npm-range', 'low', f'npm:{name}', f'{name} is not pinned to one version in package.json', f'"{name}": "{spec}"',
                    'Pin it exactly (the lockfile pins installs, but a range invites silent upgrades on npm install).')
        if locked_direct.get(name) != spec:
            rep.add('npm-lock-out-of-sync', 'medium', f'npm:{name}', 'package.json and package-lock.json disagree',
                    f'package.json {spec!r}, lockfile {locked_direct.get(name)!r}', 'Run npm install and commit the lockfile.')
    pkgs = npm_packages(lock)
    for name, entries in sorted(pkgs.items()):
        for e in entries:
            sid = f'npm:{name}'
            row = rep.item('npm', id=sid, name=name, version=e.get('version'), direct=name in direct and e['path'].count('node_modules/') == 1,
                           dev=bool(e.get('dev')), optional=bool(e.get('optional')), licence=e.get('license'),
                           install_script=bool(e.get('hasInstallScript')), os=e.get('os'))
            resolved, integrity = e.get('resolved') or '', e.get('integrity') or ''
            if not resolved.startswith('https://registry.npmjs.org/'):
                rep.add('npm-foreign-source', 'high', sid, f'{name} is not resolved from the npm registry over HTTPS',
                        f"{e['path']}: resolved {resolved or '(none)'}", 'Install it from registry.npmjs.org, or explain and accept it.')
            if not integrity.startswith('sha512-'):
                rep.add('npm-integrity', 'medium', sid, f'{name} has no sha512 integrity hash in the lockfile',
                        f"{e['path']}: integrity {integrity[:20] or '(none)'}", 'Regenerate the lockfile with a current npm.')
            if e.get('hasInstallScript'):
                where = f" (only on {', '.join(e['os'])})" if e.get('os') else ''
                rep.add('npm-install-script', 'medium', sid, f'{name} runs an install script{where}',
                        f"{e['path']} {e.get('version')}: hasInstallScript" + (', optional' if e.get('optional') else ''),
                        'Read the script; in CI prefer npm ci --ignore-scripts where the package works without it.')
            if not e.get('license'):
                rep.add('npm-no-licence', 'low', sid, f'{name} declares no licence', f"{e['path']} {e.get('version')}",
                        'Check its repository for a licence before relying on it.')
    rep.extra['npm_counts'] = {'direct': len(direct), 'with_transitive': len(rep.inventory['npm'])}
    if not net:
        return
    asks = [dict(q={'package': {'ecosystem': 'npm', 'name': r['name']}, 'version': r['version']}, row=r)
            for r in rep.inventory['npm'] if r.get('version')]
    osv_lookup(rep, net, asks)
    audit = run_npm_audit(rep) if npm_audit else {}
    for a in asks:
        row, vulns = a['row'], list(a.get('vulns') or [])
        known = {v['id'] for v in vulns}
        for v in audit.get(row['name'], []):        # npm audit reports by name; OSV already matched the version
            if v['id'] not in known:
                vulns.append(v)
                known.add(v['id'])
        if vulns:
            row['advisories'] = sorted(v['id'] for v in vulns)
            scope = ' (dev dependency)' if row['dev'] else ''
            advisory_finding(rep, row['id'], row['name'], row['version'], vulns, 'locked',
                             'Update to >={target} (npm update, or bump the pin in package.json).', scope)
    # The registry: deprecation and the newest release.
    rep.sources['npm-registry'] = 'registry.npmjs.org (abbreviated metadata)'
    meta = net.map(lambda n: net.json(f'https://registry.npmjs.org/{urllib.parse.quote(n, safe="@")}',
                                      headers={'Accept': 'application/vnd.npm.install-v1+json'}), sorted(pkgs))
    for row in rep.inventory['npm']:
        status, data, _err = meta.get(row['name'], (0, None, ''))
        if status != 200 or not isinstance(data, dict):
            continue
        row['latest'] = (data.get('dist-tags') or {}).get('latest')
        dep = ((data.get('versions') or {}).get(row['version']) or {}).get('deprecated')
        if dep:
            rep.add('npm-deprecated', 'medium', row['id'], f"{row['name']} {row['version']} is deprecated", str(dep)[:200],
                    'Move to the replacement its maintainers name, or drop it.')


def run_npm_audit(rep):
    """npm's own advisory check on the lockfile (no node_modules, no scripts run). {package: [advisories]}."""
    npm = shutil.which('npm')
    if not npm:
        rep.sources['npm-audit'] = 'not run (npm not installed)'
        return {}
    try:
        r = subprocess.run([npm, 'audit', '--package-lock-only', '--json'], cwd=rep.root, capture_output=True,
                           text=True, timeout=120)
        data = json.loads(r.stdout or '{}')
    except (OSError, ValueError, subprocess.TimeoutExpired) as e:
        rep.sources['npm-audit'] = f'not verified: {str(e)[:120]}'
        return {}
    if 'vulnerabilities' not in data:
        rep.sources['npm-audit'] = f"not verified: {str(data.get('error', {}).get('summary', 'no answer'))[:120]}"
        return {}
    rep.sources['npm-audit'] = 'npm audit --package-lock-only'
    out = collections.defaultdict(list)
    levels = {'critical': 'critical', 'high': 'high', 'moderate': 'medium', 'low': 'low', 'info': 'info'}
    for name, v in (data.get('vulnerabilities') or {}).items():
        for via in v.get('via') or []:
            if isinstance(via, dict) and via.get('url'):
                vid = via['url'].rstrip('/').rsplit('/', 1)[-1]
                out[via.get('name') or name].append(dict(id=vid, severity=levels.get(via.get('severity'), 'medium'),
                                                         summary=(via.get('title') or '')[:160], fixed=[], range=via.get('range')))
    return out


# ------------------------------------------------------------------------------------------------------- GitHub repos
def github_repo(url):
    m = re.match(r'^https?://(?:www\.)?github\.com/([A-Za-z0-9_.-]+)/([A-Za-z0-9_.-]+?)(?:\.git)?(?:[/#?].*)?$', url or '')
    if not m or m.group(1).lower() in GITHUB_NOT_REPOS:
        return None
    return f'{m.group(1)}/{m.group(2)}'


def repo_status(net, slug):
    status, data, err = net.github(f'repos/{slug}')
    if status == 200 and isinstance(data, dict):
        lic = (data.get('license') or {}).get('spdx_id')
        return dict(state='ok', full_name=data.get('full_name'), archived=bool(data.get('archived')),
                    disabled=bool(data.get('disabled')), licence=lic, pushed=(data.get('pushed_at') or '')[:10],
                    default_branch=data.get('default_branch'), stars=data.get('stargazers_count'))
    if status in (404, 451):
        return dict(state='gone', http=status)
    return dict(state='unverified', error=err or f'HTTP {status}' + (f": {data.get('message')}" if isinstance(data, dict) else ''))


def scorecard(net, slug):
    status, data, err = net.json(f'https://api.securityscorecards.dev/projects/github.com/{slug}')
    if status == 200 and isinstance(data, dict) and 'score' in data:
        zero = sorted(c['name'] for c in data.get('checks') or [] if c.get('score') == 0)
        return dict(score=data['score'], date=data.get('date'), zero=zero)
    return dict(score=None, note='not scored' if status == 404 else f'not verified ({err or status})')


def repo_findings(rep, subject, slug, st, recorded_licence=None, context='catalogue', as_of=None):
    """Archived, deleted, renamed, disabled, licence changed, stale: the signals that a link no longer goes where we think."""
    url = f'https://github.com/{slug}'
    if st['state'] == 'gone':
        rep.add('repo-gone', 'high', subject, f'{slug} no longer exists (or is private)', f'GitHub answers {st["http"]} for {url}',
                'Mark the entry "moved" or "gone" (status in upstreams/registry.yaml or a note in research/landscape.json) and '
                'remove the link: anyone can register the freed name.')
        return
    if st['state'] != 'ok':
        rep.add('repo-unverified', 'info', subject, f'{slug} could not be checked', st.get('error', ''), 'Run again later.')
        return
    if st['disabled']:
        rep.add('repo-disabled', 'high', subject, f'GitHub has disabled {slug}', url, 'Remove the link; find out why.')
    if st['full_name'] and st['full_name'].lower() != slug.lower():
        rep.add('repo-moved', 'medium', subject, f"{slug} moved to {st['full_name']}",
                f'{url} redirects to https://github.com/{st["full_name"]}',
                'Update the link to the new name (the old name can be registered by someone else); check the new owner is who you expect.')
    if st['archived']:
        rep.add('repo-archived', 'medium', subject, f'{slug} is archived (read-only, no fixes)', f"last push {st['pushed']}",
                'Show it as "unmaintained" (status or note) instead of removing it; plan a replacement if we use its code.')
    elif st['pushed'] and as_of and (days_since(as_of, st['pushed']) or 0) > STALE_PUSH_DAYS:
        rep.add('repo-stale', 'low', subject, f'no push to {slug} for over a year', f"last push {st['pushed']}",
                'Check it is still maintained; if not, show it as "unmaintained".')
    rec = (recorded_licence or '').strip()
    gh = st.get('licence')
    if rec and gh and gh not in ('NOASSERTION', 'NONE') and re.fullmatch(r'[A-Za-z0-9.+-]+', rec) and not same_licence(rec, gh):
        rep.add('licence-changed', 'medium' if context != 'docs' else 'low', subject, f'{slug} licence is now {gh}, we record {rec}',
                f'GitHub licence detection: {gh}', 'Re-read the licence; update the record and the policy (incorporate, external, ideas only).')
    if context in ('catalogue', 'vendored') and not gh and not rec:
        rep.add('licence-none', 'low', subject, f'{slug} has no licence GitHub can detect', url,
                'Without a licence it is all rights reserved: ideas only, never copied code.')


# ----------------------------------------------------------------------------------------------------------- vendored
def git_blob_sha(data: bytes):
    return hashlib.sha1(b'blob %d\0' % len(data) + data).hexdigest()


def excluded(rel, globs):
    return any(fnmatch.fnmatch(rel, g) or fnmatch.fnmatch(rel, g.rstrip('/') + '/*') or rel.startswith(g.rstrip('/') + '/')
               for g in globs)


def patched_paths(root, name):
    out = set()
    for p in sorted((root / 'vendor' / 'patches' / name).glob('*.patch')):
        out |= set(re.findall(r'^diff --git a/\S+ b/(\S+)$', read_text(p) or '', re.M))
    return out


def notice_rows(text):
    rows = {}
    for line in (text or '').splitlines():
        cells = [c.strip() for c in line.strip().strip('|').split('|')]
        if len(cells) == 5 and cells[2].startswith('https://'):
            rows[cells[0]] = dict(licence=cells[1], url=cells[2], sha=cells[3].strip('`'))
    return rows


def find_licence_file(d: Path):
    for p in sorted(d.iterdir()) if d.is_dir() else []:
        if p.is_file() and re.match(r'^(LICEN[CS]E|COPYING|NOTICE)', p.name, re.I):
            return p
    return None


def check_vendored(rep, net):
    man_text = read_text(rep.root / 'vendor' / 'manifest.json')
    if man_text is None:
        return
    man = json.loads(man_text)
    notices = notice_rows(read_text(rep.root / 'THIRD_PARTY_NOTICES.md'))
    names = set()
    for e in man.get('projects') or []:
        name, sha, url = e['name'], e.get('sha') or '', e.get('url') or ''
        names.add(name)
        sid, d = f'vendor:{name}', rep.root / 'vendor' / name
        files = tracked(rep.root, f'vendor/{name}') if d.is_dir() else []
        skills = [f for f in files if f.endswith('/SKILL.md')]
        row = rep.item('vendored', id=sid, name=name, url=url, sha=sha, imported=e.get('imported'), licence=e.get('license'),
                       files=len(files), skills=len(skills), patches=sorted(patched_paths(rep.root, name)))
        if not re.fullmatch(r'[0-9a-f]{40}', sha):
            rep.add('vendor-pin', 'high', sid, f'{name} is not pinned to a full commit SHA', f'manifest sha {sha!r}',
                    'Pin the full 40-character commit (SECURITY.md rule 1).')
        if not url.startswith('https://github.com/'):
            rep.add('vendor-source', 'medium', sid, f'{name} is not fetched from GitHub over HTTPS', url,
                    'Use an HTTPS GitHub URL, or extend this report to verify that host.')
        if not d.is_dir():
            rep.add('vendor-missing', 'high', sid, f'vendor/{name} is in the manifest but not in the tree', f'vendor/{name}',
                    'Re-import it with tools/vendor_sync.py or remove it from the manifest.')
            continue
        lf = find_licence_file(d)
        row['licence_file'] = str(lf.relative_to(rep.root)) if lf else None
        found = detect_licence(read_text(lf)) if lf else None
        row['licence_detected'] = found
        if not lf:
            rep.add('vendor-no-licence', 'high', sid, f'vendor/{name} has no LICENSE/COPYING/NOTICE file', f'vendor/{name}/',
                    'Keep the upstream licence text with the code, or remove the code.')
        elif not found:
            rep.add('vendor-licence-unknown', 'low', sid, f'the licence text of {name} is not one this report recognises',
                    row['licence_file'], 'Read it and record the licence in vendor/manifest.json.')
        elif not same_licence(e.get('license'), found):
            rep.add('vendor-licence-mismatch', 'medium', sid, f"{name}: manifest says {e.get('license')}, the licence file reads as {found}",
                    row['licence_file'], 'The licence file governs: correct the manifest and THIRD_PARTY_NOTICES.md, and the policy.')
        base = rep.root / 'vendor' / 'baselines' / f'{name}.json'
        bsha = (json.loads(read_text(base) or '{}') or {}).get('sha') if base.exists() else None
        if bsha != sha:
            rep.add('vendor-baseline', 'medium', sid, f'the reviewed security baseline of {name} is not for the pinned commit',
                    f'baseline sha {str(bsha)[:12]}, pinned {sha[:12]}',
                    'Review the scan report for this commit, then python tools/vendor_sync.py accept ' + name + '.')
        if e.get('report') and not (rep.root / e['report']).exists():
            rep.add('vendor-report-missing', 'low', sid, f'the scan report of {name} is missing', e['report'], 'Re-run the import scan.')
        n = notices.get(name)
        if not n:
            rep.add('vendor-notices', 'medium', sid, f'{name} is not in THIRD_PARTY_NOTICES.md', 'no table row',
                    'Regenerate the vendored table (tools/vendor_sync.py notices) or add the row.')
        elif n['url'] != url or not sha.startswith(n['sha']) or not same_licence(n['licence'], e.get('license')):
            rep.add('vendor-notices', 'medium', sid, f'THIRD_PARTY_NOTICES.md disagrees with the manifest for {name}',
                    f"notices: {n['licence']}, {n['url']}, {n['sha']}; manifest: {e.get('license')}, {url}, {sha[:12]}",
                    'Make the notices match the manifest.')
    for d in sorted((rep.root / 'vendor').iterdir()):
        if d.is_dir() and d.name not in names and d.name not in ('baselines', 'patches', 'reports'):
            rep.add('vendor-unrecorded', 'high', f'vendor:{d.name}', f'vendor/{d.name} is not in vendor/manifest.json',
                    f'vendor/{d.name}/', 'Every vendored tree needs a pinned manifest entry, a scan report and a baseline (SECURITY.md).')
    if not net:
        return
    projects = {r['name']: r for r in rep.inventory['vendored']}
    entries = {e['name']: e for e in man.get('projects') or []}
    slugs = {n: github_repo(r['url']) for n, r in projects.items() if github_repo(r['url'])}
    statuses = net.map(lambda s: repo_status(net, s), sorted(set(slugs.values())))
    asks = [dict(q={'commit': r['sha']}, row=r) for r in projects.values() if re.fullmatch(r'[0-9a-f]{40}', r['sha'] or '')]
    for a in osv_lookup(rep, net, asks):
        advisory_finding(rep, a['row']['id'], a['row']['name'], a['row']['sha'][:12], a.get('vulns') or [], 'commit',
                         'Re-import a fixed commit (>= {target}) with tools/vendor_sync.py.')
    for name, slug in sorted(slugs.items()):
        r, st = projects[name], statuses[slug]
        repo_findings(rep, r['id'], slug, st, r['licence'], 'vendored', rep.as_of)
        r['upstream'] = {k: st.get(k) for k in ('state', 'full_name', 'archived', 'licence', 'pushed')}
        if st['state'] != 'ok':
            continue
        sc = scorecard(net, slug)
        r['scorecard'] = sc
        if sc['score'] is not None and sc['score'] < SCORECARD_MIN:
            rep.add('scorecard-low', 'medium', r['id'], f"OpenSSF Scorecard {sc['score']}/10 for {slug}",
                    f"checks at 0: {', '.join(sc['zero']) or 'none'} ({sc['date']})", 'Read its scan report again before the next import.')
        status, cmp, _ = net.github(f"repos/{slug}/compare/{r['sha']}...{st['default_branch']}")
        if status == 200 and isinstance(cmp, dict):
            r['behind'] = cmp.get('ahead_by')
        status, advs, _ = net.github(f'repos/{slug}/security-advisories?state=published&per_page=100')
        if status == 200 and isinstance(advs, list):
            for adv in advs:
                if (adv.get('published_at') or '')[:10] >= (r.get('imported') or ''):
                    rep.add('vendor-upstream-advisory', {'critical': 'critical', 'high': 'high'}.get(adv.get('severity'), 'medium'),
                            r['id'], f"{slug} published advisory {adv.get('ghsa_id')} since our import",
                            f"{adv.get('summary', '')[:160]} (published {adv.get('published_at', '')[:10]})",
                            'Check whether the pinned commit is affected; re-import a fixed commit.', key=adv.get('ghsa_id', ''))
        vendor_drift(rep, net, r, slug, entries[name])


def vendor_drift(rep, net, row, slug, entry):
    """Do the vendored files still match upstream at the pinned commit? Git blob hashes, so nothing is downloaded."""
    status, tree, err = net.github(f"repos/{slug}/git/trees/{row['sha']}?recursive=1")
    if status != 200 or not isinstance(tree, dict) or tree.get('truncated'):
        rep.add('vendor-drift-unverified', 'info', row['id'], f"the upstream tree of {row['name']} could not be compared",
                'tree listing truncated' if isinstance(tree, dict) and tree.get('truncated') else (err or f'HTTP {status}'), 'Run again later.')
        return
    up = {t['path']: t['sha'] for t in tree.get('tree') or [] if t.get('type') == 'blob' and t.get('mode') != '120000'}
    base = rep.root / 'vendor' / row['name']
    local = {}
    for rel in tracked(rep.root, f"vendor/{row['name']}"):
        p = rep.root / rel
        if p.is_file() and not p.is_symlink():
            local[rel[len(f"vendor/{row['name']}/"):]] = git_blob_sha(p.read_bytes())
    patched, globs = set(row['patches']), entry.get('exclude') or []
    changed = sorted(p for p in local if p in up and up[p] != local[p] and p not in patched)
    added = sorted(p for p in local if p not in up and p not in patched)
    missing = sorted(p for p in up if p not in local and not excluded(p, globs))
    row['drift'] = dict(compared=len(local), changed=len(changed), added=len(added), missing=len(missing))
    if changed or added:
        rep.add('vendor-drift', 'high', row['id'], f"{len(changed) + len(added)} vendored files of {row['name']} differ from upstream "
                f"at the pinned commit with no patch to explain them",
                'changed: ' + ', '.join(changed[:6]) + (' …' if len(changed) > 6 else '') + '; added: ' + ', '.join(added[:6]),
                'Re-import with tools/vendor_sync.py, or record the change as a patch in vendor/patches/.',
                key=','.join(changed + added))
    if missing:
        ignored = git(rep.root, 'check-ignore', '--', *[f"vendor/{row['name']}/{m}" for m in missing[:50]]) or ''
        hidden = f" ({len(ignored.splitlines())} of them ignored by a .gitignore, so never committed)" if ignored else ''
        rep.add('vendor-incomplete', 'low', row['id'], f"{len(missing)} upstream files of {row['name']} are neither vendored nor excluded",
                ', '.join(missing[:8]) + (' …' if len(missing) > 8 else '') + hidden,
                'Add them to the manifest exclude list with a reason (or commit them), so the record says what was left out.',
                key=','.join(missing))


# ------------------------------------------------------------------------------------------------------------ web kit
KIT = 'src/cadagent/webkit/vendor'
RECORD_FILES = {'file-viewer-sources.json', 'mermaid/SOURCE.json', 'FILE-VIEWER-NOTICES.md'}


def webkit_components(root):
    """Each top-level folder of the kit's vendor/ with the npm packages it holds, read from the kit's own records."""
    src = json.loads(read_text(root / KIT / 'file-viewer-sources.json') or '{}')
    mer = json.loads(read_text(root / KIT / 'mermaid' / 'SOURCE.json') or '{}')
    notes = read_text(root / KIT / 'FILE-VIEWER-NOTICES.md') or ''
    tag = (src.get('three') or {}).get('tag') or ''
    three = f'0.{tag[1:]}.0' if re.fullmatch(r'r\d+', tag) else None
    fflate = re.search(r'fflate (\d+\.\d+\.\d+)', notes)
    return {
        'three': dict(packages=[('three', three)], repo='mrdoob/three.js'),
        'file-parsers': dict(packages=[('three', three), ('fflate', fflate.group(1) if fflate else None)], repo='mrdoob/three.js'),
        'mermaid': dict(packages=[(mer.get('package', 'mermaid'), mer.get('version'))], repo='mermaid-js/mermaid'),
        'linkedom': dict(packages=[('linkedom', (src.get('linkedom') or {}).get('version'))], repo='WebReflection/linkedom'),
        'occt-import-js': dict(packages=[('occt-import-js', (src.get('occt') or {}).get('version'))], repo='kovacsv/occt-import-js'),
        'fonts': dict(packages=[], repo=None),
    }


def check_webkit(rep, net, added_files=()):
    kit = rep.root / KIT
    if not kit.is_dir():
        return
    files = [f[len(KIT) + 1:] for f in tracked(rep.root, KIT)]
    src = json.loads(read_text(kit / 'file-viewer-sources.json') or '{}')
    mer = json.loads(read_text(kit / 'mermaid' / 'SOURCE.json') or '{}')
    hashes = dict(src.get('sha256') or {})
    hashes.update({f'mermaid/{k}': v for k, v in (mer.get('files') or {}).items()})
    comps = webkit_components(rep.root)
    unhashed = collections.defaultdict(list)
    for rel in files:
        if rel in RECORD_FILES:
            continue
        top = rel.split('/')[0] if '/' in rel else '(top)'
        if rel in hashes:
            got = hashlib.sha256((kit / rel).read_bytes()).hexdigest()
            if got != hashes[rel]:
                rep.add('webkit-hash', 'high', f'webkit:{top}', f'{KIT}/{rel} does not match its recorded SHA-256',
                        f'recorded {hashes[rel][:16]}…, file {got[:16]}…', 'Find out who changed it; restore the recorded file or '
                        're-vendor it with a new provenance review and record.', key=rel)
        else:
            unhashed[top].append(rel)
    for rel in sorted(set(hashes) - set(files)):
        rep.add('webkit-hash-missing', 'high', f"webkit:{rel.split('/')[0]}", f'{KIT}/{rel} is recorded but missing',
                'listed in a hash record', 'Restore it or remove it from the record.', key=rel)
    notices = read_text(rep.root / 'THIRD_PARTY_NOTICES.md') or ''
    kit_section = notices.split('## Web kit', 1)[-1] if '## Web kit' in notices else ''
    for lic in sorted(set(re.findall(r'`([^`]+)`', kit_section))):
        if '/' in lic and not lic.startswith(('src/', 'vendor/')) and not (kit / lic.rstrip('/')).exists():
            rep.add('webkit-licence-missing', 'medium', f"webkit:{lic.split('/')[0]}", f'licence file {lic} named in THIRD_PARTY_NOTICES.md is missing',
                    f'{KIT}/{lic}', 'Restore the licence text beside the code.', key=lic)
    folders = sorted({f.split('/')[0] for f in files if '/' in f})
    for top in folders:
        c = comps.get(top)
        row = rep.item('webkit', id=f'webkit:{top}', name=top, files=sum(1 for f in files if f.startswith(top + '/')),
                       hashed=sum(1 for f in files if f.startswith(top + '/') and f in hashes),
                       packages=[f'{n}@{v}' for n, v in (c or {}).get('packages', [])], repo=(c or {}).get('repo'))
        if c is None:
            rep.add('webkit-unknown', 'medium', row['id'], f'{KIT}/{top} is not a component this report knows',
                    f'{row["files"]} files', 'Add it to webkit_components() in tools/resource_audit.py with its package, version and repo.')
        for n, v in (c or {}).get('packages', []):
            if not v:
                rep.add('webkit-version', 'medium', row['id'], f'no recorded version for {n} in {top}', 'kit records',
                        'Record the exact version in file-viewer-sources.json or SOURCE.json.', key=n)
        new_unhashed = [f for f in unhashed.get(top, []) if f'{KIT}/{f}' in set(added_files)]
        if new_unhashed:
            rep.add('webkit-unhashed', 'medium', row['id'], f'new vendored files in {top} have no recorded hash',
                    ', '.join(new_unhashed[:6]), 'Record their SHA-256 in file-viewer-sources.json (or the folder\'s SOURCE.json).',
                    key='new:' + ','.join(new_unhashed))
        elif unhashed.get(top):
            rep.add('webkit-unhashed', 'low', row['id'], f"{len(unhashed[top])} vendored files in {top} have no recorded hash",
                    ', '.join(unhashed[top][:6]) + (' …' if len(unhashed[top]) > 6 else ''),
                    'Record their SHA-256 and source (as mermaid/SOURCE.json does), so a silent change is caught.',
                    key=','.join(unhashed[top]))
    three = kit / 'three' / 'three.module.min.js'
    want = dict(comps['three']['packages']).get('three')
    if three.exists() and want and f'"{want.split(".")[1]}"' not in (read_text(three) or '')[:4000]:
        rep.add('webkit-version', 'medium', 'webkit:three', f'three.module.min.js does not carry revision {want.split(".")[1]}',
                'REVISION string not found in the file header', 'Check which three.js release the file is.', key='revision')
    mm = kit / 'mermaid' / 'mermaid.min.js'
    mv = mer.get('version')
    if mm.exists() and mv and mv not in (read_text(mm) or ''):
        rep.add('webkit-version', 'medium', 'webkit:mermaid', f'mermaid.min.js does not contain its recorded version {mv}',
                'version string not found', 'Check which Mermaid release the file is.', key='version')
    if not net:
        return
    pkgs = sorted({(n, v) for c in comps.values() for n, v in c['packages'] if v})
    asks = [dict(q={'package': {'ecosystem': 'npm', 'name': n}, 'version': v}, pkg=(n, v)) for n, v in pkgs]
    osv_lookup(rep, net, asks)
    for a in asks:
        n, v = a['pkg']
        for row in rep.inventory['webkit']:
            if f'{n}@{v}' in row['packages'] and a.get('vulns'):
                row.setdefault('advisories', []).extend(x['id'] for x in a['vulns'])
                advisory_finding(rep, row['id'], n, v, a['vulns'], 'vendored',
                                 'Update the vendored copy to >={target}: new files, new SHA-256 records and notices, then '
                                 'the web kit browser suites (it ships to every project site that copies the kit).')
                break                     # report a package once, on the first folder that carries it
    meta = net.map(lambda n: net.json(f'https://registry.npmjs.org/{n}', headers={'Accept': 'application/vnd.npm.install-v1+json'}),
                   sorted({n for n, _ in pkgs}))
    for row in rep.inventory['webkit']:
        row['latest'] = {}
        for spec in row['packages']:
            n, v = spec.rsplit('@', 1)
            status, data, _ = meta.get(n, (0, None, ''))
            if status == 200 and isinstance(data, dict):
                row['latest'][n] = (data.get('dist-tags') or {}).get('latest')
                dep = ((data.get('versions') or {}).get(v) or {}).get('deprecated')
                if dep:
                    rep.add('npm-deprecated', 'medium', row['id'], f'vendored {n} {v} is deprecated', str(dep)[:200],
                            'Move to the replacement its maintainers name.', key=n)
    slugs = sorted({r['repo'] for r in rep.inventory['webkit'] if r.get('repo')})
    statuses = net.map(lambda s: repo_status(net, s), slugs)
    for row in rep.inventory['webkit']:
        if row.get('repo'):
            repo_findings(rep, row['id'], row['repo'], statuses[row['repo']], None, 'vendored', rep.as_of)


# -------------------------------------------------------------------------------------------------------------- links
def published(f):
    """The Markdown files tools/build-site.mjs publishes as pages (keep in step with its SECTIONS)."""
    if re.search(r'(?:^|/)(?:AGENTS|CLAUDE)\.md$', f) or f == REPORT_MD:
        return False
    return bool(f in ('README.md', 'CONTRIBUTING.md', 'THIRD_PARTY_NOTICES.md') or re.match(r'^docs/[^/]+\.md$', f)
                or re.match(r'^skills/[^/]+/SKILL\.md$', f) or re.match(r'^agents/[^/]+\.md$', f)
                or re.match(r'^lessons/[^/]+\.md$', f) or re.match(r'^research/[^/]+\.md$', f))


FENCE = re.compile(r'^(```|~~~)[^\n]*\n.*?^\1[ \t]*$', re.M | re.S)
CODE = re.compile(r'`[^`\n]+`')
URL = re.compile(r'https?://(?:[^\s<>"\'`|\]()]|\([^\s()<>]*\))+')       # balanced (...) inside a URL is kept


def code_spans(text):
    """(line number, code) for fenced blocks and inline code."""
    out = []
    for m in FENCE.finditer(text):
        out.append((text.count('\n', 0, m.start()) + 1, m.group(0)))
    rest = FENCE.sub(lambda m: '\n' * m.group(0).count('\n'), text)
    for m in CODE.finditer(rest):
        out.append((rest.count('\n', 0, m.start()) + 1, m.group(0)))
    return out


def prose_urls(text):
    """(line, url) for links in prose (code is examples and commands, not resources we send people to)."""
    rest = FENCE.sub(lambda m: '\n' * m.group(0).count('\n'), text)
    rest = CODE.sub(lambda m: ' ' * len(m.group(0)), rest)
    out = []
    for m in URL.finditer(rest):
        u = m.group(0).rstrip('.,;:!?*_)')
        out.append((rest.count('\n', 0, m.start()) + 1, u))
    return out


def host(url):
    try:
        return (urllib.parse.urlsplit(url).hostname or '').lower()
    except ValueError:
        return ''


def site(h):
    """The registrable part of a host, roughly: foo.github.io stays itself, docs.python.org -> python.org."""
    h = h[4:] if h.startswith('www.') else h
    if re.search(r'\.(github|gitlab)\.io$|\.readthedocs\.io$|\.pages\.dev$|\.netlify\.app$|\.vercel\.app$', h):
        return h
    parts = h.split('.')
    if len(parts) >= 3 and '.'.join(parts[-2:]) in ('co.uk', 'ac.uk', 'org.uk', 'gov.uk', 'com.au', 'edu.au', 'co.jp', 'ac.jp', 'com.br', 'co.nz'):
        return '.'.join(parts[-3:])
    return '.'.join(parts[-2:])


def catalogue_entries(root, catalog=None):
    """The external entries the site's catalog.json publishes, read from the same sources tools/build-site.mjs reads."""
    land = json.loads(read_text(root / 'research' / 'landscape.json') or '{}')
    ups = load_yaml(read_text(root / 'upstreams' / 'registry.yaml') or '[]') or []
    out = []
    for u in ups:
        out.append(dict(source='upstreams/registry.yaml', name=u.get('name'), url=u.get('url'), licence=u.get('license'),
                        last_push=str(u.get('last_push') or '') or None, status=u.get('status')))
    for p in land.get('projects') or []:
        out.append(dict(source='research/landscape.json projects', name=p.get('name'), url=p.get('url'),
                        licence=p.get('license_spdx') or p.get('license'), last_push=p.get('last_push')))
    for lib in land.get('libraries') or []:
        out.append(dict(source='research/landscape.json libraries', name=lib.get('name'),
                        url=lib.get('url') or f"https://github.com/{lib.get('name')}", licence=lib.get('license_spdx'),
                        last_push=lib.get('last_push'), status=lib.get('status')))
    for b in land.get('benchmarks') or []:
        out.append(dict(source='research/landscape.json benchmarks', name=b.get('name'), url=b.get('url'),
                        licence=b.get('license_spdx') or b.get('license') or b.get('data_license')))
    if catalog:
        for i in json.loads(Path(catalog).read_text()).get('items') or []:
            if i.get('url') and host(i['url']) not in OUR_HOSTS:
                out.append(dict(source='catalog.json', name=i.get('name'), url=i['url'], licence=i.get('license'),
                                last_push=i.get('last_push'), status=i.get('status')))
    return out


def check_links(rep, net, catalog=None):
    entries = catalogue_entries(rep.root, catalog)
    links = collections.OrderedDict()          # url -> {'where': [...], 'catalogue': [entries]}

    def note(url, where, entry=None):
        rec = links.setdefault(url, dict(where=[], catalogue=[]))
        if where not in rec['where']:
            rec['where'].append(where)
        if entry:
            rec['catalogue'].append(entry)
    by_name = collections.defaultdict(list)
    for e in entries:
        if not e['url']:
            rep.add('catalogue-no-url', 'medium', f"catalogue:{e['name']}", f"{e['name']} has no URL", e['source'],
                    'Add the canonical https URL, or drop the entry.')
            continue
        note(e['url'], e['source'], e)
        by_name[e['name']].append(e)
    for f in tracked(rep.root):
        if f.endswith('.md') and published(f):
            for line, u in prose_urls(read_text(rep.root / f) or ''):
                note(u, f'{f}:{line}')
    for url, rec in links.items():
        h = host(url)
        if not h or IGNORED_HOSTS.match(h) or '{' in url or '$' in url:
            continue
        if h in OUR_HOSTS or (github_repo(url) or '').lower() in OUR_REPOS:
            continue
        cat = rec['catalogue']
        rec['id'] = f'url:{url}'
        row = rep.item('links', id=rec['id'], url=url, kind='catalogue' if cat else 'docs',
                       names=sorted({e['name'] for e in cat}), where=rec['where'][:5] + (['…'] if len(rec['where']) > 5 else []),
                       licence=sorted({str(e['licence']) for e in cat if e.get('licence')}) or None,
                       status=sorted({str(e['status']) for e in cat if e.get('status')}) or None)
        if url.startswith('http://'):
            rep.add('link-not-https', 'medium', row['id'], f'{h} is linked over plain HTTP', '; '.join(rec['where'][:3]),
                    'Link the https:// address; if the site has none, say so next to the link.')
        if cat and not any(e.get('licence') for e in cat) and site(h) not in ('arxiv.org', 'doi.org'):   # a paper, not code
            rep.add('catalogue-no-licence', 'low', row['id'], f"no licence recorded for {', '.join(row['names'])}",
                    '; '.join(rec['where'][:3]), 'Record the licence (or "none": ideas only).')
        pushes = [e['last_push'] for e in cat if e.get('last_push')]
        if pushes and not net:
            age = days_since(rep.as_of, max(pushes))
            if age is not None and age > STALE_PUSH_DAYS:
                rep.add('catalogue-stale', 'low', row['id'], f"{', '.join(row['names'])}: last push {max(pushes)} as recorded",
                        '; '.join(rec['where'][:3]), 'Check it is maintained (--online); if not, show it as "unmaintained".')
    for name, es in sorted(by_name.items()):
        lics = {norm(str(e['licence'])) for e in es if e.get('licence') and re.fullmatch(r'[A-Za-z0-9.+-]+', str(e['licence']))}
        if len(lics) > 1:
            rep.add('catalogue-records-disagree', 'low', f'url:{es[0]["url"]}', f'{name}: the records give different licences',
                    '; '.join(f"{e['source']}: {e['licence']}" for e in es), 'Check the licence and make the records agree.')
    if not net:
        return
    rows = rep.inventory['links']
    slugs = sorted({github_repo(r['url']) for r in rows if github_repo(r['url'])})
    statuses = net.map(lambda s: repo_status(net, s), slugs)
    cat_slugs = sorted({github_repo(r['url']) for r in rows if github_repo(r['url']) and r['kind'] == 'catalogue'})
    scores = net.map(lambda s: scorecard(net, s), [s for s in cat_slugs if statuses[s]['state'] == 'ok'])
    rep.sources['github'] = f'GitHub REST API ({net.github_auth()})'
    rep.sources['scorecard'] = 'api.securityscorecards.dev'
    reported = set()
    for r in rows:
        slug = github_repo(r['url'])
        if slug:
            st = statuses[slug]
            r['github'] = {k: st.get(k) for k in ('state', 'full_name', 'archived', 'licence', 'pushed')}
            rec_lic = (r.get('licence') or [None])[0]
            if slug in reported and r['kind'] != 'catalogue':
                continue                   # one finding per repository, on its catalogue entry if it has one
            reported.add(slug)
            repo_findings(rep, r['id'], slug, st, rec_lic, r['kind'], rep.as_of)
            sc = scores.get(slug)
            if sc:
                r['scorecard'] = sc['score']
                if sc['score'] is not None and sc['score'] < SCORECARD_MIN:
                    rep.add('scorecard-low', 'low', r['id'], f"OpenSSF Scorecard {sc['score']}/10 for {slug}",
                            f"checks at 0: {', '.join(sc['zero'][:8]) or 'none'} ({sc['date']})",
                            'Fine to read; review its code and maintenance before adopting or vendoring it.')
    plain = [r for r in rows if not github_repo(r['url'])]
    probes = net.map(net.probe, [r['url'] for r in plain])
    for r in plain:
        chain, err = probes[r['url']]
        r['http'] = [s for s, _ in chain] or None
        judge_link(rep, r, chain, err)


def judge_link(rep, row, chain, err):
    url, sid = row['url'], row['id']
    where = '; '.join(row['where'][:3])
    if not chain:
        rep.add('link-unverified', 'info', sid, f'{host(url)} did not answer', f'{err} ({where})', 'Check by hand; run again later.')
        return
    status, final = chain[-1]
    row['final'] = final if final != url else None
    if status in (404, 410):
        rep.add('link-dead', 'medium', sid, f'{url} is gone (HTTP {status})', where,
                'Replace it with a live source (or an archive.org copy, marked as such), or remove it.')
    elif status >= 500 or status in (401, 403, 429) or (300 <= status < 400):
        rep.add('link-unverified', 'info', sid, f'{host(url)} answered HTTP {status}', where,
                'Many sites refuse scripts; check by hand.')
    a, b = site(host(url)), site(host(final))
    if a != b and a not in RESOLVERS and host(url) not in RESOLVERS:
        rep.add('link-redirect-domain', 'medium', sid, f'{host(url)} now redirects to {host(final)}',
                ' -> '.join(u for _, u in chain[:4]) + f' ({where})',
                'Check the new site belongs to the same owner and is what we meant; link it directly, or drop the link.',
                key=b)
    if url.startswith('https://') and final.startswith('http://'):
        rep.add('link-https-downgrade', 'medium', sid, f'{host(url)} redirects from HTTPS to plain HTTP', ' -> '.join(u for _, u in chain[:4]),
                'Link a page that stays on HTTPS, or say so.')


# ------------------------------------------------------------------------------------------------------------- skills
REGISTRY_ACTION = ('Standing rule: never install skills or plugins from registries. Vendor a pinned commit '
                   '(tools/vendor_sync.py) or point at a reviewed release by commit, and say so.')
INSTALL_ADVICE = [
    ('install-from-registry', 'medium', re.compile(r'\b(?:npx|bunx|pnpm\s+dlx)\s+(?:-y\s+|--yes\s+)?skills\s+(?:add|install)\b', re.I),
     'installs a skill from a registry', REGISTRY_ACTION),
    ('install-from-registry', 'medium', re.compile(r'\b(?:claude\s+plugin|/plugin)\s+(?:install|marketplace\s+add)\b', re.I),
     'installs a plugin from a marketplace', REGISTRY_ACTION),
    ('install-from-registry', 'medium', re.compile(r'\b(?:smithery|clawhub|skillsmp)\b[^\n`]*\b(?:install|add)\b', re.I),
     'installs from a skill registry', REGISTRY_ACTION),
    ('install-pipe-to-shell', 'medium', re.compile(r'(?:curl|wget)[^\n|`]*\|\s*(?:sudo\s+)?(?:ba|z)?sh\b', re.I),
     'pipes a download into a shell', 'If this is advice, replace it with a pinned, checksummed download or a package '
     'manager; if it only describes how a project installs, say that it is a risk.'),
]
RUNNER = re.compile(r'\b(npx|uvx|pipx\s+run|bunx)\s+([^\n`|;&]+)')
TAKES_VALUE = {'--python', '-p', '--with', '--from', '--index', '--index-url', '--package', '--spec', '-c', '--call'}


def unpinned_runner(tool, args):
    """The package an npx/uvx/pipx command fetches without a version, or None when it is pinned."""
    toks, i, pkg = args.split(), 0, None
    while i < len(toks):
        t = toks[i]
        if t in ('--from', '--package', '--spec') and i + 1 < len(toks):
            v = toks[i + 1]
            return None if ('==' in v or re.search(r'.@\d', v)) else v
        if t.startswith('-'):
            i += 2 if t in TAKES_VALUE else 1
            continue
        pkg = t
        break
    if not pkg or pkg.startswith(('.', '/', '$')) or not re.match(r'^@?[a-z0-9]', pkg, re.I):
        return None
    if tool.startswith(('npx', 'bunx')):
        return None if re.search(r'.@(?!latest\b)[\w.^~-]+$', pkg) else pkg
    return None if '==' in pkg or '@' in pkg[1:] else pkg


def check_skills(rep, net=None):
    files = tracked(rep.root)
    ours = [f for f in files if re.match(r'^skills/[^/]+/SKILL\.md$', f)] + [f for f in files if re.match(r'^agents/[^/]+\.md$', f)]
    rev = (git(rep.root, 'rev-parse', '--short=12', 'HEAD') or 'working tree')
    for f in ours:
        kind = 'skill' if f.startswith('skills/') else 'agent'
        name = f.split('/')[1] if kind == 'skill' else Path(f).stem
        rep.item('skills', id=f'{kind}:{name}', name=name, kind=kind, source='this repository', file=f, version=rev)
    man = json.loads(read_text(rep.root / 'vendor' / 'manifest.json') or '{"projects": []}')
    for e in man.get('projects') or []:
        n = sum(1 for f in files if f.startswith(f"vendor/{e['name']}/") and f.endswith('/SKILL.md'))
        if n:
            rep.item('skills', id=f"vendored-skills:{e['name']}", name=e['name'], kind=f'{n} vendored skills',
                     source=e.get('url'), file=f"vendor/{e['name']}/", version=(e.get('sha') or '')[:12])
    scan = [f for f in files if f.endswith('.md') and (published(f) or f.startswith(('skills/', 'agents/')))]
    for f in scan:
        text = read_text(rep.root / f) or ''
        for line0, code in code_spans(text):
            for off, ln in enumerate(code.splitlines()):
                where = f'{f}:{line0 + off}'
                advice = False
                for check, sev, rx, what, action in INSTALL_ADVICE:
                    if rx.search(ln):
                        advice = True
                        rep.add(check, sev, f'doc:{f}', f'{f} {what}', f'{where}: {ln.strip()[:160]}', action,
                                key=' '.join(ln.split()))
                for m in RUNNER.finditer(ln):
                    pkg = unpinned_runner(m.group(1), m.group(2))
                    if pkg:
                        rep.add('install-unpinned', 'low', f'doc:{f}', f'{f} runs {pkg} without a version',
                                f'{where}: {ln.strip()[:160]}', f'Pin it ({pkg}==X or {pkg}@X), so a later release cannot change what runs.',
                                key=f'{m.group(1)} {pkg}')
                if re.search(r'[@#]latest\b', ln) and not RUNNER.search(ln) and not advice:
                    rep.add('install-unpinned', 'low', f'doc:{f}', f'{f} points at a moving "latest"', f'{where}: {ln.strip()[:160]}',
                            'Point at a release or commit instead of latest.', key=' '.join(ln.split()))


# --------------------------------------------------------------------------------------------------------------- repo
def check_repo(rep, net, repo=None):
    dep = read_text(rep.root / '.github' / 'dependabot.yml')
    ecos = {u.get('package-ecosystem') for u in (load_yaml(dep) or {}).get('updates', [])} if dep else set()
    rep.item('repo', id='dependabot', ecosystems=sorted(e for e in ecos if e))
    for eco, manifest in (('npm', 'package.json'), ('pip', 'pyproject.toml')):
        if (rep.root / manifest).exists() and eco not in ecos:
            rep.add('dependabot-ecosystem', 'low', f'repo:dependabot-{eco}', f'Dependabot does not watch {eco} ({manifest})',
                    f".github/dependabot.yml ecosystems: {', '.join(sorted(e for e in ecos if e)) or 'none'}",
                    f'Add a weekly {eco} entry targeting dev (owner decision: it opens PRs).', key=eco)
    if not (net and repo):
        return
    status, data, err = net.github(f'repos/{repo}')
    sa = (data or {}).get('security_and_analysis') if status == 200 and isinstance(data, dict) else None
    row = rep.item('repo', id=f'repo:{repo}', settings=sa and {k: (v or {}).get('status') for k, v in sa.items()})
    if sa:
        if (sa.get('secret_scanning') or {}).get('status') != 'enabled':
            rep.add('repo-secret-scanning', 'medium', f'repo:{repo}', 'secret scanning is off',
                    'security_and_analysis.secret_scanning: ' + str((sa.get('secret_scanning') or {}).get('status')),
                    'Owner: turn on secret scanning and push protection (Settings, Code security); free for public repositories.')
        if (sa.get('dependabot_security_updates') or {}).get('status') != 'enabled':
            rep.add('repo-dependabot-updates', 'low', f'repo:{repo}', 'Dependabot security updates are off',
                    'security_and_analysis.dependabot_security_updates: ' + str((sa.get('dependabot_security_updates') or {}).get('status')),
                    'Owner decision: they open fix PRs for alerts (into the default branch, dev).')
    else:
        row['settings'] = f'not visible ({err or "needs admin"})'
    status, _, _ = net.github(f'repos/{repo}/vulnerability-alerts')
    row['dependabot_alerts'] = {204: 'enabled', 404: 'disabled'}.get(status, f'not verified ({status})')
    if status == 404:
        rep.add('repo-dependabot-alerts', 'medium', f'repo:{repo}', 'Dependabot alerts are off', 'vulnerability-alerts: 404',
                'Owner: turn on Dependabot alerts.')
    owner, name = repo.split('/', 1)
    status, data, err = net.graphql('{ repository(owner: "%s", name: "%s") { dependencyGraphManifests(first: 50) '
                                    '{ totalCount nodes { filename dependenciesCount } } } }' % (owner, name))
    graph = (((data or {}).get('data') or {}).get('repository') or {}).get('dependencyGraphManifests') if isinstance(data, dict) else None
    if graph is not None:
        row['dependency_graph'] = sorted(f"{n['filename']} ({n['dependenciesCount']})" for n in graph.get('nodes') or [])
        if not graph.get('totalCount'):
            rep.add('repo-dependency-graph-empty', 'medium', f'repo:{repo}', "GitHub's dependency graph sees no manifests",
                    'dependencyGraphManifests.totalCount = 0, so Dependabot alerts cannot fire for package-lock.json or pyproject.toml',
                    'Owner: check the dependency graph is enabled (Settings, Code security); until then this report is the only advisory check.')


# -------------------------------------------------------------------------------------------------------------- build
def build(root, as_of=None, net=None, repo=None, installed=False, catalog=None, npm_audit=True, added_files=(), accepted=None):
    rep = Report(root, as_of or dt.datetime.now(dt.timezone.utc).date(), bool(net))
    rep.sources.setdefault('offline', 'pyproject.toml, package.json, package-lock.json, vendor/manifest.json, kit hash records, '
                           'THIRD_PARTY_NOTICES.md, upstreams/registry.yaml, research/landscape.json, published Markdown')
    check_python(rep, net, installed)
    check_npm(rep, net, npm_audit)
    check_vendored(rep, net)
    check_webkit(rep, net, added_files)
    check_links(rep, net, catalog)
    check_skills(rep, net)
    check_repo(rep, net, repo)
    for f in rep.findings:
        why = accepted_reason(accepted or [], f)
        if why:
            f['accepted'] = why
    return rep


def load_accepted(path):
    text = read_text(Path(path)) if path else None
    if not text:
        return []
    items = load_yaml(text) or []
    for a in items:
        if not (a.get('check') and a.get('subject') and a.get('reason')):
            raise SystemExit(f'{path}: every accepted finding needs check, subject and reason')
    return items


def accepted_reason(items, f):
    for a in items:
        if a['check'] == f['check'] and a['subject'] == f['subject'] and a.get('fp', f['fp']) == f['fp']:
            return f"{a['reason']} ({a.get('accepted', 'undated')})"
    return None


def failing(report, threshold):
    if threshold == 'none':
        return []
    return [f for f in report['findings'] if not f.get('accepted') and RANK[f['severity']] <= RANK[threshold]]


# ------------------------------------------------------------------------------------------------------------- output
def cell(s):
    return str(s if s is not None else '').replace('|', '\\|').replace('\n', ' ')


def inert(s):
    """Text for a published table: URLs in code spans, so the report page never links people to what it flags."""
    return URL.sub(lambda m: f'`{m.group(0)}`', cell(str(s).replace('`', "'")))


def findings_table(fs):
    lines = ['| Severity | Subject | Finding | Evidence | Action |', '|---|---|---|---|---|']
    for f in fs:
        lines.append(f"| {f['severity']} | `{cell(f['subject'])}` | {inert(f['title'])} | {inert(f['evidence'][:300])} | "
                     f"{inert(f['action'])}{' **Accepted:** ' + inert(f['accepted']) if f.get('accepted') else ''} |")
    return lines


def to_markdown(r, inventory=True, limit=None):
    s = r['summary']
    open_ = [f for f in r['findings'] if not f.get('accepted')]
    accepted = [f for f in r['findings'] if f.get('accepted')]
    counts = ', '.join(f'{s[k]} {k}' for k in SEVERITIES if s[k]) or 'none'
    out = ['# Supply-chain and resource report', '',
           f"What cad-agent depends on, vendors and links to, checked on {r['as_of']} at revision `{(r['revision'] or 'working tree')[:12]}` "
           f"({r['mode']} checks). Findings: {counts}. Generated by `tools/resource_audit.py`; how to read it and what blocks "
           "a merge are in the [cad-supply-chain skill](../skills/cad-supply-chain/SKILL.md).", '',
           '**Limits.** ' + ' '.join(r['limits']), '']
    if any(s[k] for k in SEVERITIES):
        out += ['```mermaid', 'pie showData title Open findings by severity'] + \
               [f'    "{k}" : {s[k]}' for k in SEVERITIES if s[k]] + ['```', '']
    out += ['## Findings', '']
    if not open_:
        out += ['No open findings.', '']
    for sev in SEVERITIES:
        fs = [f for f in open_ if f['severity'] == sev]
        if fs:
            out += [f'### {sev.capitalize()} ({len(fs)})', ''] + findings_table(fs) + ['']
    if accepted:
        out += [f'### Accepted ({len(accepted)})', '', f'Read and accepted in `{ACCEPTED}`.', ''] + findings_table(accepted) + ['']
    if inventory:
        inv, ex = r['inventory'], r.get('extra') or {}
        out += ['## What we depend on', '', '### Python dependencies', '']
        counts = ex.get('python_counts') or {}
        if counts:
            out += ['| Extra | Direct | With transitive (deps.dev, newest releases) |', '|---|---|---|'] + \
                   [f"| {g} | {c['direct']} | {c['with_transitive'] if c['with_transitive'] is not None else 'unknown'} |"
                    for g, c in counts.items()] + ['']
        out += ['| Package | Extras | Range | Newest | Released | Licence | Lowest allowed | Advisories (newest / lowest) |',
                '|---|---|---|---|---|---|---|---|']
        for p in inv['python']:
            adv = p.get('advisories') or {}
            out.append(f"| `{p['name']}` | {', '.join(p['groups'])} | {cell(', '.join(sorted(set(p['range'].values()))))} | "
                       f"{p.get('latest') or ''} | {p.get('last_release') or ''} | {cell(p.get('licence') or '')} | "
                       f"{p.get('floor_release') or ''} | {len(adv.get('latest', []))} / {len(adv.get('floor', []))} |")
        nc = ex.get('npm_counts') or {}
        out += ['', '### npm (site build and browser tests)', '', f"{nc.get('direct', 0)} direct, {nc.get('with_transitive', 0)} "
                'packages in the lockfile including transitive.', '',
                '| Package | Version | Direct | Dev | Licence | Install script | Advisories |', '|---|---|---|---|---|---|---|']
        for p in inv['npm']:
            out.append(f"| `{p['name']}` | {p['version']} | {'yes' if p['direct'] else ''} | {'yes' if p['dev'] else ''} | "
                       f"{p.get('licence') or ''} | {'yes' if p['install_script'] else ''} | {len(p.get('advisories') or [])} |")
        out += ['', '### Vendored code (vendor/)', '', '| Project | Pinned | Imported | Licence (manifest / file) | Files | Skills | '
                'Upstream | Behind | Scorecard | Drift |', '|---|---|---|---|---|---|---|---|---|---|']
        for v in inv['vendored']:
            up, d = v.get('upstream') or {}, v.get('drift')
            drift = f"{d['changed']} changed, {d['added']} added, {d['missing']} missing ({d['compared']} compared)" if d else ''
            score = (v.get('scorecard') or {}).get('score')
            out.append(f"| [{v['name']}]({v['url']}) | `{(v['sha'] or '')[:12]}` | {v.get('imported') or ''} | {v.get('licence')} / "
                       f"{v.get('licence_detected') or '?'} | {v['files']} | {v['skills']} | "
                       f"{'archived' if up.get('archived') else up.get('state', '')} | {v.get('behind', '')} | "
                       f"{score if score is not None else ''} | {drift} |")
        out += ['', '### Web kit (src/cadagent/webkit/vendor/)', '', '| Folder | Packages | Files | Hashed | Newest | Advisories |',
                '|---|---|---|---|---|---|']
        for w in inv['webkit']:
            out.append(f"| `{w['name']}` | {', '.join(w['packages'])} | {w['files']} | {w['hashed']} | "
                       f"{', '.join(f'{k} {v}' for k, v in sorted((w.get('latest') or {}).items()))} | {len(set(w.get('advisories') or []))} |")
        cat = [l for l in inv['links'] if l['kind'] == 'catalogue']
        flagged = {f['subject'] for f in open_}
        out += ['', '### Links we send people to', '',
                f"{len(cat)} catalogue links (catalog.json, upstreams/registry.yaml, research/landscape.json) and "
                f"{len(inv['links']) - len(cat)} more in published pages; {sum(1 for l in inv['links'] if l['id'] in flagged)} have "
                'findings above.', '', '### Skills and agents', '', '| Item | Kind | Source | Version |', '|---|---|---|---|']
        for k in inv['skills']:
            out.append(f"| `{k['name']}` | {k['kind']} | {cell(k['source'])} | `{k['version']}` |")
        out += ['', '## Sources', ''] + [f'- **{k}:** {v}' for k, v in r['sources'].items()] + ['']
    text = '\n'.join(out) + '\n'
    if limit and len(text) > limit:
        text = text[:limit - 200] + '\n\n…(cut; the full report is in the run\'s artifact)\n'
    return text


def print_summary(r, fail):
    s = r['summary']
    print(f"supply-chain report ({r['mode']}, {r['as_of']}): " + ', '.join(f'{s[k]} {k}' for k in SEVERITIES) +
          f", {s['accepted']} accepted; items: " + ', '.join(f'{k} {v}' for k, v in s['items'].items()))
    for f in [f for f in r['findings'] if not f.get('accepted') and RANK[f['severity']] <= RANK['medium']][:40]:
        print(f"  {f['severity']:<8} {f['subject']}: {f['title']}")
    if fail:
        print(f'{len(fail)} finding(s) at or above the threshold (exit 1)')


# ------------------------------------------------------------------------------------------------------- base vs head
class GitTree:
    """The files of a commit, read with git (for --base)."""

    def __init__(self, root, ref):
        self.root, self.ref = root, ref
        out = git(root, 'ls-tree', '-r', '-z', '--name-only', ref)
        if out is None:
            raise SystemExit(f'cannot read {ref!r}: fetch it first (git fetch origin)')
        self.files = sorted(f for f in out.split('\0') if f)

    def read(self, path):
        try:
            return subprocess.run(['git', '-C', str(self.root), 'show', f'{self.ref}:{path}'], capture_output=True,
                                  check=True).stdout.decode('utf-8', 'replace')
        except subprocess.CalledProcessError:
            return None


class WorkTree:
    def __init__(self, root):
        self.root, self.files = Path(root), tracked(Path(root))

    def read(self, path):
        return read_text(self.root / path)


def item_ids(tree):
    """The report items a tree has, without any check: the units a PR must show a row for."""
    ids = set()
    py = tree.read('pyproject.toml')
    if py:
        ids |= {p['id'] for p in python_packages(py)[1].values()}
    lock = tree.read('package-lock.json')
    if lock:
        ids |= {f'npm:{n}' for n in npm_packages(json.loads(lock))}
    man = tree.read('vendor/manifest.json')
    if man:
        ids |= {f"vendor:{e['name']}" for e in json.loads(man).get('projects') or []}
    ids |= {f"vendor:{f.split('/')[1]}" for f in tree.files if f.startswith('vendor/') and f.count('/') >= 2
            and f.split('/')[1] not in ('baselines', 'patches', 'reports')}
    ids |= {f"webkit:{f[len(KIT) + 1:].split('/')[0]}" for f in tree.files if f.startswith(KIT + '/') and f[len(KIT) + 1:].count('/')}
    with tempfile.TemporaryDirectory() as td:          # the catalogue's sources, laid out as a tiny checkout
        for p in ('research/landscape.json', 'upstreams/registry.yaml'):
            t = tree.read(p)
            if t is not None:
                (Path(td) / p).parent.mkdir(parents=True, exist_ok=True)
                (Path(td) / p).write_text(t, encoding='utf-8')
        try:
            ids |= {f"url:{e['url']}" for e in catalogue_entries(Path(td)) if e.get('url')}
        except (ValueError, TypeError):
            pass
    return ids


def added_items(root, base):
    b, h = GitTree(root, base), WorkTree(root)
    ids = item_ids(h) - item_ids(b)
    old = set(b.files)
    new_files = [f for f in h.files if f not in old and (f.startswith('vendor/') or f.startswith(KIT + '/'))]
    for f in new_files:
        if f.startswith(KIT + '/') and f[len(KIT) + 1:].count('/'):
            ids.add(f"webkit:{f[len(KIT) + 1:].split('/')[0]}")
        elif f.startswith('vendor/') and f.count('/') >= 2 and f.split('/')[1] not in ('baselines', 'patches', 'reports'):
            ids.add(f"vendor:{f.split('/')[1]}")
    return sorted(ids), new_files


def item_row(r, sid):
    for section, rows in r['inventory'].items():
        for row in rows:
            if row.get('id') == sid:
                return section, row
    return None, None


def describe(section, row):
    if section == 'python':
        return 'Python dependency (' + ', '.join(row['groups']) + ')', ', '.join(sorted(set(row['range'].values()))), row.get('licence')
    if section == 'npm':
        return 'npm package' + (' (direct)' if row['direct'] else ' (transitive)'), row['version'], row.get('licence')
    if section == 'vendored':
        return 'vendored project', (row.get('sha') or '')[:12], row.get('licence')
    if section == 'webkit':
        return 'web kit vendored files', ', '.join(row['packages']) or f"{row['files']} files", None
    if section == 'links':
        return 'catalogue link' if row['kind'] == 'catalogue' else 'link', '', ', '.join(row.get('licence') or []) or None
    return section or 'item', '', None


def rows_markdown(r, ids):
    lines = ['| Item | What | Version / pin | Licence | Report |', '|---|---|---|---|---|']
    for sid in ids:
        section, row = item_row(r, sid)
        what, ver, lic = describe(section, row) if row else ('removed or unknown', '', None)
        fs = [f for f in r['findings'] if f['subject'] == sid and not f.get('accepted')]
        rep = '; '.join(f"{f['severity']}: {f['title']}" for f in sorted(fs, key=lambda f: RANK[f['severity']])) or \
              f"no findings ({r['mode']} checks)"
        lines.append(f'| `{sid}` | {what} | {cell(ver)} | {cell(lic or "")} | {cell(rep)} |')
    return '\n'.join(lines) + '\n'


# ----------------------------------------------------------------------------------------------------------- commands
def make_report(a, added_files=()):
    net = Net() if a.online else None
    accepted = load_accepted(a.accepted if a.accepted else (ROOT / ACCEPTED if Path(a.root) == ROOT else None))
    as_of = dt.date.fromisoformat(a.as_of) if a.as_of else None
    rep = build(Path(a.root), as_of, net, a.repo, a.installed, a.catalog, not a.no_npm_audit, added_files, accepted)
    return rep.to_json()


def cmd_report(a):
    r = make_report(a)
    if a.json:
        Path(a.json).parent.mkdir(parents=True, exist_ok=True)
        Path(a.json).write_text(json.dumps(r, indent=1, ensure_ascii=False) + '\n', encoding='utf-8')
    if a.md:
        Path(a.md).parent.mkdir(parents=True, exist_ok=True)
        Path(a.md).write_text(to_markdown(r), encoding='utf-8')
    fail = failing(r, a.fail_on)
    print_summary(r, fail)
    return 1 if fail else 0


def cmd_rows(a):
    ids, new_files = added_items(Path(a.root), a.base)
    if not ids:
        print(f'Nothing added since {a.base}: no dependency, vendored file or catalogue entry.')
        return 0
    r = make_report(a, new_files)
    print(f'<!-- supply-chain rows: python3 tools/resource_audit.py rows --base {a.base}{" --online" if a.online else ""} -->')
    print(rows_markdown(r, ids))
    return 0


def cmd_gate(a):
    """CI: every item the change adds has its report row in the PR body, and none has a finding at --fail-on or above."""
    ids, new_files = added_items(Path(a.root), a.base)
    r = make_report(a, new_files)
    problems = []
    whole = failing(r, a.fail_on_repo)
    if whole:
        problems.append(f'{len(whole)} finding(s) at or above {a.fail_on_repo} in the repository:')
        problems += [f"  {f['severity']} {f['subject']}: {f['title']}" for f in whole]
    bad = [f for f in failing(r, a.fail_on) if f['subject'] in ids]
    if bad:
        problems.append(f'{len(bad)} finding(s) at or above {a.fail_on} on what this change adds:')
        problems += [f"  {f['severity']} {f['subject']}: {f['title']} -> {f['action']}" for f in bad]
    body = os.environ.get(a.pr_body_env, '') if a.pr_body_env else (Path(a.pr_body_file).read_text() if a.pr_body_file else None)
    if body is not None and ids:
        missing = [i for i in ids if f'`{i}`' not in body and i not in body]
        if missing:
            problems.append('the PR description has no report row for: ' + ', '.join(missing) +
                            f'\n  paste the output of: python3 tools/resource_audit.py rows --base origin/<base> (into "Supply chain")')
    print(f'supply-chain gate: {len(ids)} item(s) added since {a.base}' + (': ' + ', '.join(ids) if ids else ''))
    if ids:
        print(rows_markdown(r, ids))
    for p in problems:
        print(p)
    return 1 if problems else 0


MARK = re.compile(r'<!-- cad-supply-chain-report fps=([0-9a-f,]*) -->')
BOTS = ('github-actions[bot]', 'app/github-actions', 'github-actions')


def gh_json(*args):
    r = subprocess.run(['gh', *args], capture_output=True, text=True)
    if r.returncode:
        raise SystemExit(f"gh {' '.join(args[:3])} failed: {r.stderr.strip()[:300]}")
    return json.loads(r.stdout or 'null')


def plan_issue(r, issues, repo, title, authors=BOTS):
    """The gh commands that bring the one tracking issue in line with a report: [(args, stdin)], and a note.

    The issue is the one open issue opened by an allowed author whose body carries the fingerprint marker; anyone can
    write a marker, so the author check keeps the workflow from editing someone else's issue."""
    live = [f for f in r['findings'] if not f.get('accepted') and RANK[f['severity']] <= RANK['low']
            and not f['check'].endswith('-unverified')]
    fps = sorted({f['fp'] for f in live})
    mine = [i for i in issues or [] if MARK.search(i.get('body') or '') and (i.get('author') or {}).get('login') in set(authors)]
    body = to_markdown(r, inventory=False, limit=60000) + f"\n<!-- cad-supply-chain-report fps={','.join(fps)} -->\n"
    if not mine:
        if not fps:
            return [], 'no open findings at low or above; no issue needed'
        return [(['issue', 'create', '-R', repo, '--title', title, '--body-file', '-'], body)], 'open a new issue'
    num, old = str(mine[0]['number']), set(filter(None, MARK.search(mine[0]['body']).group(1).split(',')))
    if old == set(fps):
        return [], f'issue #{num}: findings unchanged'
    new = [f for f in live if f['fp'] not in old]
    gone = len(old - set(fps))
    note = '\n'.join([f"Report of {r['as_of']} (revision `{(r['revision'] or '')[:12]}`): {len(new)} new, {gone} resolved.", ''] +
                     [f"- **{f['severity']}** `{f['subject']}`: {f['title']}" for f in new[:50]]) + '\n'
    plan = [(['issue', 'edit', num, '-R', repo, '--body-file', '-'], body),
            (['issue', 'comment', num, '-R', repo, '--body-file', '-'], note)]
    if not fps:
        plan.append((['issue', 'close', num, '-R', repo, '--comment', 'No open findings at low or above: closing.'], None))
    return plan, f'update issue #{num}: {len(new)} new, {gone} resolved'


def cmd_issue(a):
    """Open, update or close the one tracking issue from a report; nothing happens when the findings did not change."""
    r = json.loads(Path(a.report).read_text())
    issues = gh_json('issue', 'list', '-R', a.repo, '--state', 'open', '--search', f'"{a.title}" in:title', '--limit', '30',
                     '--json', 'number,title,body,author')
    plan, note = plan_issue(r, issues, a.repo, a.title, BOTS + tuple(a.author or ()))
    print(note)
    for args, stdin in plan:
        print(('gh ' if a.post else 'would run: gh ') + ' '.join(args))
        if a.post:
            res = subprocess.run(['gh', *args], input=stdin, capture_output=True, text=True)
            if res.returncode:
                print(res.stderr.strip()[:300], file=sys.stderr)
                return 2
            print(res.stdout.strip())
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split('\n\n')[0], formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest='cmd', required=True)

    def common(p):
        p.add_argument('--root', default=str(ROOT), help='the checkout to audit (default: this one)')
        p.add_argument('--online', action='store_true', help='also run the network checks (OSV, registries, GitHub, links)')
        p.add_argument('--repo', help='OWNER/REPO whose GitHub security settings to read (online)')
        p.add_argument('--installed', action='store_true', help='also check the Python versions installed in this interpreter')
        p.add_argument('--catalog', help='a built catalog.json (dist/catalog.json) to read links from as well')
        p.add_argument('--no-npm-audit', action='store_true', help='skip npm audit in --online mode')
        p.add_argument('--accepted', help=f'accepted findings (default {ACCEPTED} when it exists)')
        p.add_argument('--as-of', help='the date stale checks count from (YYYY-MM-DD; default today, UTC)')
    p = sub.add_parser('report', help='run the checks; write JSON and Markdown')
    common(p)
    p.add_argument('--json')
    p.add_argument('--md')
    p.add_argument('--fail-on', default='high', choices=[*SEVERITIES, 'none'])
    p = sub.add_parser('rows', help='report rows for the items this branch adds since --base (paste into the PR)')
    common(p)
    p.add_argument('--base', default='origin/dev')
    p = sub.add_parser('gate', help='CI: added items have rows in the PR body and no finding at --fail-on or above')
    common(p)
    p.add_argument('--base', default='origin/dev')
    p.add_argument('--fail-on', default='medium', choices=[*SEVERITIES, 'none'], help='threshold for added items')
    p.add_argument('--fail-on-repo', default='high', choices=[*SEVERITIES, 'none'], help='threshold for the whole repository')
    p.add_argument('--pr-body-env', help='environment variable holding the PR description')
    p.add_argument('--pr-body-file')
    p = sub.add_parser('issue', help='open or update the one tracking issue from a report (weekly workflow)')
    p.add_argument('--report', required=True)
    p.add_argument('--repo', required=True)
    p.add_argument('--title', default='Supply-chain report: open findings')
    p.add_argument('--author', action='append', help='also accept a tracking issue opened by this login')
    p.add_argument('--post', action='store_true', help='make the changes (default: print what would be done)')
    a = ap.parse_args(argv)
    try:
        return {'report': cmd_report, 'rows': cmd_rows, 'gate': cmd_gate, 'issue': cmd_issue}[a.cmd](a)
    except (OSError, ValueError, KeyError) as e:
        print(f'resource_audit: {type(e).__name__}: {e}', file=sys.stderr)
        return 2


if __name__ == '__main__':
    sys.exit(main())
