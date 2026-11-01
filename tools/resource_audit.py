#!/usr/bin/env python3
"""Supply-chain and resource safety report: what cad-agent depends on, vendors and points people to (#117).

    python3 tools/resource_audit.py report                       # offline checks only (default; what CI runs)
    python3 tools/resource_audit.py report --online \\
        --json research/security-report.json --md research/security-report.md
    python3 tools/resource_audit.py rows --base origin/dev        # report rows for what this branch adds (for the PR)
    python3 tools/resource_audit.py gate --base HEAD^1 --into dev --pr-body-env PR_BODY   # CI: rows present, no new bad item
    python3 tools/resource_audit.py issue --report r.json --repo OWNER/REPO [--post]   # weekly: one issue, kept current
    python3 tools/resource_audit.py render [--check]             # the report page and figure from the saved JSON

What it reads:
- Python dependencies (pyproject.toml, every extra), npm dependencies (package.json and package-lock.json);
- vendored code (vendor/ with vendor/manifest.json; src/cadagent/webkit/vendor/ with its receipts:
  file-viewer-sources.json and each folder's SOURCE.json, which name the npm package, its integrity, the path of each
  file in the package, the SHA-256 of each file and the libraries a file bundles) and the notice files
  (THIRD_PARTY_NOTICES.md and the kit's own);
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
- deps.dev (Open Source Insights): resolved dependency graphs, for the direct-plus-transitive counts and the transitive
  Python packages OSV is asked about;
- the npm registry's tarballs named by the web kit receipts: the package integrity and each vendored file's bytes;
- the GitHub REST API (``gh`` when it is logged in, else GH_TOKEN or GITHUB_TOKEN): archived, deleted or renamed
  repos, licences, push dates, the vendored trees at their pinned commits, published repository advisories;
- the OpenSSF Scorecard API (``api.securityscorecards.dev``): repository hygiene scores.

The link checks borrow two ideas from lychee (https://github.com/lycheeverse/lychee): fall back from HEAD to GET when a
server refuses HEAD, and treat 403 and 429 as "not verified" rather than broken.

Everything fetched is data: advisory text, package metadata, tarballs and pages are parsed, never executed or followed
as instructions, and tarballs are read in memory, never unpacked to disk.

Exit codes: 0 nothing at or above --fail-on (default high) that is not accepted; 1 there is; 2 usage or tool error.
Findings are fingerprinted; research/security-accepted.yaml lists those read and accepted (check, subject, reason,
and the fingerprint ``fp`` for an advisory). An acceptance never covers a critical finding.

``gate`` judges what a change adds only where new items enter: a PR or push into dev (``--into dev``). A dev -> main
release PR, and the push to main after it, carry only items that already passed dev's gate in their own PRs, and
"added since main" would be everything since the last release, so they get the whole-repository check alone.

Limits: a clean report is not proof of safety. Advisory databases only know what has been reported; licences are
detected from licence files and registry metadata, not by a lawyer; link checks see status codes and redirects, not
content, so a parked or changed page that answers 200 passes; domain expiry is not checked; GitHub links are checked
at repository level (a missing file inside a live repo is not seen). Read findings as leads for a reviewer.
"""
from __future__ import annotations

import argparse
import base64
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
OUR_MARKETPLACES = {'valpatel'}   # the plugin marketplace name our own repository publishes
CHANGE_BRANCHES = ('dev',)       # where new items enter: gate checks what a change adds only for these (see gate)
FP_REQUIRED = {'advisory', 'vendor-upstream-advisory'}   # an acceptance of these names its fingerprint
TARBALL_LIMIT = 64 << 20         # largest npm tarball read to check a web kit receipt
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
        self.unverified = set()        # subjects some check could not reach this run (their old findings are not "resolved")

    def add(self, check, severity, subject, title, evidence, action, key='', scope=None):
        """One finding. Its fingerprint is the check, the subject and a stable key (not the evidence).

        scope: what has to be reachable for the finding to be seen again (default: its subject). When a later run
        cannot reach it, the weekly issue keeps the finding as "not re-checked" instead of calling it resolved."""
        assert severity in RANK, severity
        if check.endswith('-unverified'):
            self.unverified.add(subject)
        fp = hashlib.sha256(f'{check}|{subject}|{key}'.encode()).hexdigest()[:16]
        if fp not in self._fps:
            self._fps.add(fp)
            self.findings.append(dict(severity=severity, check=check, subject=subject, title=title,
                                      evidence=evidence, action=action, fp=fp, **({'scope': scope} if scope else {})))

    def item(self, section, **row):
        self.inventory[section].append(row)
        return row

    def to_json(self):
        findings = sorted(self.findings, key=lambda f: (RANK[f['severity']], f['check'], f['subject'], f['fp']))
        counts = collections.Counter(f['severity'] for f in findings if not f.get('accepted'))
        inv = {k: sorted(v, key=lambda r: (r.get('id', ''), json.dumps(r, sort_keys=True))) for k, v in self.inventory.items()}
        return {
            'schema': SCHEMA, 'as_of': self.as_of.isoformat(), 'mode': 'online' if self.online else 'offline',
            'revision': git(self.root, 'rev-parse', 'HEAD'), 'dirty': dirty(self.root),
            'unverified': sorted(self.unverified),
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
    'Transitive Python dependencies are checked at the versions deps.dev resolves for our newest direct releases; an '
    'existing environment may hold other versions, and --installed checks only the installed versions of our direct dependencies.',
    'Libraries bundled inside a vendored file (DOMPurify and KaTeX inside mermaid.min.js) are checked at the versions its '
    'receipt records; whether the bundling library reaches the affected code is not assessed.',
    'Repository settings (secret scanning, Dependabot) are read only with an admin token; the weekly workflow cannot see them.',
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


def dirty(root):
    """True when the checkout has changes git would commit (the report then describes more than its revision)."""
    out = git(root, 'status', '--porcelain', '--untracked-files=normal')
    return bool(out) if out is not None else None


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
                if k.lower() == 'authorization':    # urllib copies plain headers to a redirect's host; never the token
                    req.add_unredirected_header(k, v)
                else:
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
        """Follow redirects by hand: ([(status, url), ...], error). HEAD first; GET when a server refuses HEAD.

        Both ideas come from lychee (https://github.com/lycheeverse/lychee): many servers refuse HEAD, so a refusal is
        retried as GET, and judge_link treats 403 and 429 (scripts refused, rate limited) as not verified, not broken."""
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
    """asks: [{'q': OSV query, 'subject': report item, ...}] -> each ask gets 'vulns': [advisory dicts] (None when OSV
    failed, and its subject is marked unverified).

    An advisory whose record cannot be read (OSV answered the batch, then failed on /v1/vulns/<id>) fails closed: it
    keeps its id, counts as high (a MAL- id as critical), says its fix is unknown, and an osv-unverified finding names
    it. A failed read must never make a finding look milder than the record would.

    The batch answer is matched to the queries by position, so a chunk whose `results` is not one result per query
    (short, empty, not a list) leaves every ask in it unchecked: 'vulns' None, unverified, an osv-unverified finding.
    So does a single entry that cannot be read (not an object, or 'vulns' not a list of advisories with ids).
    A result with `next_page_token` (OSV pages past 1,000 advisories for one query or 3,000 for a batch) keeps the
    advisories it has and is marked unverified the same way: the rest were not read."""
    if not asks:
        return asks
    ids, short, paged = [], [], []
    for start in range(0, len(asks), 500):
        chunk = asks[start:start + 500]
        status, body, err = net.json(f'{OSV}/querybatch', data={'queries': [a['q'] for a in chunk]})
        if status != 200 or not isinstance(body, dict):
            rep.sources['osv'] = f'not verified: {err or "HTTP " + str(status)}'
            rep.add('osv-unverified', 'info', 'osv.dev', 'OSV could not be queried; advisories were not checked',
                    err or f'HTTP {status}', 'Run the report again with --online later.')
            for a in asks:
                a['vulns'] = None
                if a.get('subject'):
                    rep.unverified.add(a['subject'])
            return asks
        results = body.get('results')
        if not isinstance(results, list) or len(results) != len(chunk):
            ids += [None] * len(chunk)
            short += chunk
            continue
        for a, r in zip(chunk, results):
            vulns = r.get('vulns', []) if isinstance(r, dict) else None     # no 'vulns' key: OSV knows of none
            if not isinstance(vulns, list) or not all(isinstance(v, dict) and isinstance(v.get('id'), str) for v in vulns):
                ids.append(None)                                             # an entry we cannot read: unchecked
                short.append(a)
                continue
            if r.get('next_page_token'):
                paged.append(a)
            ids.append(sorted({v['id'] for v in vulns}))
    for gap, title, action in (
            (short, 'OSV gave no readable result for some queries; those packages were not checked',
             'Run the report again with --online later; until then they count as not verified.'),
            (paged, 'OSV paged its answer; advisories after the first page were not read',
             'Run again with --online; if it persists, query these packages one at a time (osv.dev, page_token).')):
        if gap:
            subjects = sorted({f"{a['q']['package'].get('ecosystem', '')}:{a['q']['package'].get('name', '')}"
                               if 'package' in a['q'] else f"commit {str(a['q'].get('commit', '?'))[:12]}" for a in gap})
            for a in gap:
                if a.get('subject'):
                    rep.unverified.add(a['subject'])
            rep.add('osv-unverified', 'info', 'osv.dev', title, ', '.join(subjects[:20]) + (' …' if len(subjects) > 20 else ''),
                    action, key=('short:' if gap is short else 'paged:') + ','.join(subjects))
    rep.sources.setdefault('osv', 'osv.dev querybatch and vulns')
    answers = net.map(lambda i: net.json(f'{OSV}/vulns/{i}'), sorted({i for group in ids if group for i in group}))
    unread = sorted(i for i, (st, body, _err) in answers.items() if st != 200 or not isinstance(body, dict))
    if unread:
        rep.add('osv-unverified', 'info', 'osv.dev', f"{len(unread)} OSV advisory record{'s' if len(unread) > 1 else ''} could not be read",
                ', '.join(unread[:20]) + (' …' if len(unread) > 20 else ''),
                'Run again with --online: until a run reads them they count as high (MAL- ids as critical), fix unknown.',
                key='records:' + ','.join(unread))
    for a, group in zip(asks, ids):
        if group is None:                     # no answer for this query: unchecked, never clean
            a['vulns'] = None
            continue
        seen, out = set(), []
        for i in group:                       # the same advisory under several ids (GHSA, PYSEC, CVE) counts once
            st, v, _err = answers[i]
            if i in unread:
                out.append(dict(id=i, severity='critical' if i.startswith('MAL-') else 'high',
                                summary='record not read', fixed=[], unread=True))
                seen.add(i)
                continue
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
    """'>= X' clearing every read advisory that has a fix above version, and the read ids that have none."""
    target, nofix = None, []
    for v in vulns:
        if v.get('unread'):
            continue
        above = [f for f in v['fixed'] if vkey(f) > vkey(version)]
        if not above:
            nofix.append(v['id'])
        else:
            first = min(above, key=vkey)
            target = first if target is None or vkey(first) > vkey(target) else target
    return target, nofix


def advisory_finding(rep, subject, label, version, vulns, context, action_fix, where='', scope=None):
    """One finding per package and context, listing every advisory; MAL- (malicious) ids are always critical.

    The lowest release a range allows (context 'floor') is what a fresh install avoids but an existing environment can
    keep (pip does not upgrade a package that already satisfies the range): low, or medium when that release has a high
    or critical advisory."""
    if not vulns:
        return
    ids = sorted(v['id'] for v in vulns)
    sev = worst(vulns)
    target, nofix = upgrade_hint(vulns, version)
    unread = sorted(v['id'] for v in vulns if v.get('unread'))
    if context == 'floor':
        sev = 'critical' if any(i.startswith('MAL-') for i in ids) else 'medium' if RANK[sev] <= RANK['high'] else 'low'
    def fix(v):
        if v.get('unread'):
            return ', record not read'
        above = [f for f in v['fixed'] if vkey(f) > vkey(version)]
        return f', fixed in {min(above, key=vkey)}' if above else ', no fix listed'
    listed = '; '.join(f"{v['id']} ({v['severity']}{fix(v)}): {v['summary']}"
                       for v in sorted(vulns, key=lambda v: (RANK[v['severity']], v['id']))[:8])
    more = f' and {len(vulns) - 8} more' if len(vulns) > 8 else ''
    if target:
        action = action_fix.format(target=target)
        if nofix:
            action += f' No fix yet for {", ".join(nofix)}.'
    elif nofix:
        action = 'No fixed release is known: check whether our use is exposed; pin around it or replace it.'
    else:
        action = ''
    if unread:
        action = (action + ' ' if action else '') + (f'Not read: {", ".join(unread)}. Run again to learn their severity '
                                                    'and fix; until then they count as high.')
    if any(i.startswith('MAL-') for i in ids):
        action = 'Malicious package: remove it now, rotate any secret the environment could read, and tell the owner.'
    n = f"{len(ids)} known {'advisory' if len(ids) == 1 else 'advisories'}"
    title = {'floor': f'our range allows {label} {version}, which has {n}',
             'latest': f'the newest release, {label} {version}, has {n}',
             'installed': f'{label} {version} installed here has {n}',
             'locked': f'{label} {version} in the lockfile has {n}',
             'vendored': f'the vendored {label} {version} has {n}',
             'bundled': f'{label} {version}, bundled inside a vendored file, has {n}',
             'transitive': f'{label} {version}, a transitive dependency, has {n}',
             'commit': f'the pinned commit of {label} is affected by {n}'}[context]
    rep.add('advisory', sev, subject, title + where, listed + more, action, key=f'{context}|{label}|{version}|{",".join(ids)}',
            scope=scope)


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
                asks.append(dict(q={'package': {'ecosystem': 'PyPI', 'name': row['name']}, 'version': ver}, row=row, ctx=ctx,
                                 ver=ver, subject=row['id']))
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
    closure, resolved = {}, collections.defaultdict(set)      # resolved[(name, version)] = the direct packages that pull it in
    for name, (status, data, _err) in graphs.items():
        if status == 200 and isinstance(data, dict) and data.get('nodes'):
            nodes = [n['versionKey'] for n in data['nodes'] if n.get('relation') != 'SELF' and n.get('versionKey')]
            deps = sorted({norm(k['name']) for k in nodes})
            by_name[name]['dependencies'] = len(deps)
            closure[name] = set(deps)
            for k in nodes:
                if norm(k['name']) not in by_name and k.get('version'):
                    resolved[(norm(k['name']), k['version'])].add(name)
        else:
            rep.unverified.add('deps.dev')
    rep.extra['python_counts'] = {
        g: {'direct': len(names), 'with_transitive': len(set(names).union(*[closure.get(n, set()) for n in names]))
            if all(n in closure for n in names) else None}
        for g, names in rep.extra['python_groups'].items()}
    check_transitive(rep, net, resolved)


def check_transitive(rep, net, resolved):
    """OSV for the packages our direct dependencies pull in, at the versions deps.dev resolved for their newest releases.

    Subject pypi:<name>; the finding names the direct packages it comes through. Its scope is deps.dev: when a later run
    cannot read the graphs, the weekly issue keeps it rather than calling it resolved."""
    rep.extra['python_transitive'] = [dict(name=n, version=v, via=sorted(via)) for (n, v), via in sorted(resolved.items())]
    asks = [dict(q={'package': {'ecosystem': 'PyPI', 'name': n}, 'version': v}, name=n, ver=v, via=sorted(via),
                 subject='deps.dev') for (n, v), via in sorted(resolved.items())]
    for a in osv_lookup(rep, net, asks):
        if a.get('vulns'):
            via = ', '.join(a['via'][:4]) + (' …' if len(a['via']) > 4 else '')
            advisory_finding(rep, f"pypi:{a['name']}", a['name'], a['ver'], a['vulns'], 'transitive',
                             'Upgrade it to >={target} (pip install -U ' + a['name'] + '); if a direct dependency pins it, '
                             'raise or replace that one.', f' (through {via})', scope='deps.dev')


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
    asks = [dict(q={'package': {'ecosystem': 'npm', 'name': r['name']}, 'version': r['version']}, row=r, subject=r['id'])
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
            rep.unverified.add(row['id'])
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
    """What GitHub says about a repository. A private one (seen only through an owner's token) is reported as gone: a
    reader cannot open it, and nothing about it may reach a published report."""
    status, data, err = net.github(f'repos/{slug}')
    if status == 200 and isinstance(data, dict) and data.get('private'):
        return dict(state='gone', http=404, private=True)
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
    asks = [dict(q={'commit': r['sha']}, row=r, subject=r['id']) for r in projects.values() if re.fullmatch(r'[0-9a-f]{40}', r['sha'] or '')]
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
        if str(sc.get('note', '')).startswith('not verified'):
            rep.unverified.add(r['id'])
        if sc['score'] is not None and sc['score'] < SCORECARD_MIN:
            rep.add('scorecard-low', 'medium', r['id'], f"OpenSSF Scorecard {sc['score']}/10 for {slug}",
                    f"checks at 0: {', '.join(sc['zero']) or 'none'} ({sc['date']})", 'Read its scan report again before the next import.')
        status, cmp, _ = net.github(f"repos/{slug}/compare/{r['sha']}...{st['default_branch']}")
        if status == 200 and isinstance(cmp, dict):
            r['behind'] = cmp.get('ahead_by')
        status, advs, _ = net.github(f'repos/{slug}/security-advisories?state=published&per_page=100')
        if status != 200 or not isinstance(advs, list):
            rep.unverified.add(r['id'])
        else:
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
VIEWER_RECEIPT = 'file-viewer-sources.json'
RECORD_FILES = {VIEWER_RECEIPT, 'FILE-VIEWER-NOTICES.md'}       # plus every <folder>/SOURCE.json
# Where a receipt leaves a repository out, the repository each kit folder comes from.
KIT_REPOS = {'three': 'mrdoob/three.js', 'file-parsers': 'mrdoob/three.js', 'mermaid': 'mermaid-js/mermaid',
             'linkedom': 'WebReflection/linkedom', 'occt-import-js': 'kovacsv/occt-import-js'}


def kit_receipts(root):
    """The web kit's receipts (#152, #192): file-viewer-sources.json for the file viewer's libraries, and a SOURCE.json
    in any folder (mermaid/ today). Returns (viewer receipt, {folder: SOURCE.json}, [unreadable receipt paths])."""
    bad = []

    def load(rel):
        text = read_text(root / KIT / rel)
        try:
            data = json.loads(text) if text else {}
        except ValueError:
            data = None
        if not isinstance(data, dict):
            bad.append(rel)
            return {}
        return data
    src = load(VIEWER_RECEIPT)
    folders = {p.parent.name: load(f'{p.parent.name}/SOURCE.json') for p in sorted((root / KIT).glob('*/SOURCE.json'))}
    return src, folders, bad


def kit_hashes(src, folders):
    """kit-relative path -> recorded SHA-256, from every receipt."""
    out = {k: v for k, v in (src.get('sha256') or {}).items() if isinstance(v, str)}
    for folder, rec in folders.items():
        out.update({f'{folder}/{k}': v for k, v in (rec.get('files') or {}).items() if isinstance(v, str)})
    return out


def bundled_of(rec):
    """[(package, version)] a receipt says its file inlines ('bundled': {'dompurify': '3.4.12', 'note': ...})."""
    return sorted((k, v) for k, v in (rec.get('bundled') or {}).items() if k != 'note')


def webkit_components(root):
    """Each top-level folder of the kit's vendor/: the npm packages it holds, the ones its files bundle, its repositories
    and its npm receipts, all read from the kit's own receipts. A folder with a SOURCE.json describes itself."""
    src, folders, _bad = kit_receipts(root)

    def entry(key):
        return src.get(key) if isinstance(src.get(key), dict) else {}

    def repo(rec, folder):
        return github_repo(rec.get('repository') or '') or github_repo(rec.get('source') or '') or KIT_REPOS.get(folder)
    tag = entry('three').get('tag') or ''
    three = f'0.{tag[1:]}.0' if re.fullmatch(r'r\d+', str(tag)) else None
    three_repo = repo(entry('three'), 'three')
    comps = {
        'three': dict(packages=[('three', three)], repos=[three_repo]),
        'file-parsers': dict(packages=[('three', three), ('fflate', entry('fflate').get('version'))],
                             repos=[three_repo, repo(entry('fflate'), 'fflate')], receipts=[('fflate', entry('fflate'))]),
        'linkedom': dict(packages=[('linkedom', entry('linkedom').get('version'))], repos=[repo(entry('linkedom'), 'linkedom')]),
        'occt-import-js': dict(packages=[('occt-import-js', entry('occt').get('version'))],
                               repos=[repo(entry('occt'), 'occt-import-js')]),
        'fonts': dict(packages=[], repos=[]),
    }
    for folder, rec in folders.items():
        comps[folder] = dict(packages=[(rec.get('package') or folder, rec.get('version'))], bundled=bundled_of(rec),
                             repos=[repo(rec, folder)], receipts=[(rec.get('package') or folder, rec)])
    for c in comps.values():
        c['repos'] = sorted({r for r in c['repos'] if r})
        c.setdefault('bundled', [])
        c.setdefault('receipts', [])
    return comps


def receipt_problems(name, rec):
    """Offline: does an npm receipt say exactly which tarball it came from? [(title, evidence)]."""
    out, src, integ = [], str(rec.get('source') or ''), str(rec.get('npm_integrity') or '')
    ver = rec.get('version')
    if src and not re.fullmatch(r'https://registry\.npmjs\.org/(@[^/]+/)?[^/]+/-/[^/]+-' + re.escape(str(ver)) + r'\.tgz', src):
        out.append((f'the {name} receipt does not name the npm tarball of version {ver}', f'source {src}'))
    if src.startswith('https://registry.npmjs.org/') and not integ.startswith('sha512-'):
        out.append((f'the {name} receipt has no sha512 package integrity', f'npm_integrity {integ[:20] or "(none)"}'))
    return out


def check_webkit(rep, net, added_files=()):
    kit = rep.root / KIT
    if not kit.is_dir():
        return
    files = [f[len(KIT) + 1:] for f in tracked(rep.root, KIT)]
    src, folders, bad = kit_receipts(rep.root)
    for rel in bad:
        rep.add('webkit-receipt', 'high', f"webkit:{rel.split('/')[0] if '/' in rel else 'receipts'}", f'{KIT}/{rel} is not a JSON object',
                'the receipt cannot be read', 'Restore the receipt: without it no file in the folder is checked.', key=rel)
    hashes = kit_hashes(src, folders)
    records = RECORD_FILES | {f'{d}/SOURCE.json' for d in folders}
    comps = webkit_components(rep.root)
    unhashed = collections.defaultdict(list)
    for rel in files:
        if rel in records:
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
    folder_names = sorted({f.split('/')[0] for f in files if '/' in f})
    for top in folder_names:
        c = comps.get(top)
        row = rep.item('webkit', id=f'webkit:{top}', name=top, files=sum(1 for f in files if f.startswith(top + '/')),
                       hashed=sum(1 for f in files if f.startswith(top + '/') and f in hashes),
                       packages=[f'{n}@{v}' for n, v in (c or {}).get('packages', [])],
                       bundled=[f'{n}@{v}' for n, v in (c or {}).get('bundled', [])], repos=(c or {}).get('repos', []))
        if c is None:
            rep.add('webkit-unknown', 'medium', row['id'], f'{KIT}/{top} is not a component this report knows',
                    f'{row["files"]} files', f'Give it a SOURCE.json receipt (package, version, source, npm_integrity, files), '
                    f'as mermaid/SOURCE.json has, or add it to webkit_components() in tools/resource_audit.py.')
        for n, v in (c or {}).get('packages', []) + (c or {}).get('bundled', []):
            if not v or not isinstance(v, str):
                rep.add('webkit-version', 'medium', row['id'], f'no recorded version for {n} in {top}', 'kit receipts',
                        f'Record the exact version in {VIEWER_RECEIPT} or the folder\'s SOURCE.json.', key=n)
        bundlers = [kit / top / f for _n, rec in (c or {}).get('receipts', []) for f in (rec.get('files') or {}) if f.endswith('.js')]
        texts = [read_text(f) or '' for f in bundlers if f.exists()]
        for n, v in (c or {}).get('bundled', []):
            if texts and isinstance(v, str) and not any(f'"{v}"' in t for t in texts):
                rep.add('webkit-version', 'medium', row['id'], f'the {top} receipt says it bundles {n} {v}, but no file carries "{v}"',
                        ', '.join(f.name for f in bundlers), 'Read the bundle\'s version strings and correct the receipt.', key=f'bundled:{n}')
        for name, rec in (c or {}).get('receipts', []):
            for title, evidence in receipt_problems(name, rec):
                rep.add('webkit-receipt', 'medium', row['id'], title, evidence,
                        'Record the registry tarball and its integrity, as the npm lockfile does, so the files can be checked against it.',
                        key=f'{name}:{title}')
        new_unhashed = [f for f in unhashed.get(top, []) if f'{KIT}/{f}' in set(added_files)]
        if new_unhashed:
            rep.add('webkit-unhashed', 'medium', row['id'], f'new vendored files in {top} have no recorded hash',
                    ', '.join(new_unhashed[:6]), f'Record their SHA-256 in {VIEWER_RECEIPT} (or the folder\'s SOURCE.json).',
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
    mv = folders.get('mermaid', {}).get('version')
    if mm.exists() and mv and mv not in (read_text(mm) or ''):
        rep.add('webkit-version', 'medium', 'webkit:mermaid', f'mermaid.min.js does not contain its recorded version {mv}',
                'version string not found', 'Check which Mermaid release the file is.', key='version')
    if not net:
        return
    rows = {r['name']: r for r in rep.inventory['webkit']}
    asks, seen = [], set()
    for top, row in sorted(rows.items()):
        c = comps.get(top) or {}
        for ctx, pkgs in (('vendored', c.get('packages', [])), ('bundled', c.get('bundled', []))):
            for n, v in pkgs:
                if v and isinstance(v, str) and (n, v) not in seen:      # a package once, on the first folder that carries it
                    seen.add((n, v))
                    asks.append(dict(q={'package': {'ecosystem': 'npm', 'name': n}, 'version': v}, pkg=(n, v), ctx=ctx,
                                     row=row, subject=row['id']))
    for a in osv_lookup(rep, net, asks):
        n, v = a['pkg']
        if a.get('vulns'):
            a['row'].setdefault('advisories', []).extend(x['id'] for x in a['vulns'])
            action = ('Update the vendored copy to >={target}: new files, new SHA-256 records and notices, then the web kit '
                      'browser suites (it ships to every project site that copies the kit).') if a['ctx'] == 'vendored' else \
                     (f'{n} comes inside another library\'s file: take the first release of that library that bundles '
                      f'{n} >={{target}}, and say in the receipt whether the affected code is reachable.')
            advisory_finding(rep, a['row']['id'], n, v, a['vulns'], a['ctx'], action)
    names = sorted({n for n, v in seen})
    meta = net.map(lambda n: net.json(f'https://registry.npmjs.org/{urllib.parse.quote(n, safe="@")}',
                                      headers={'Accept': 'application/vnd.npm.install-v1+json'}), names)
    for row in rep.inventory['webkit']:
        row['latest'] = {}
        for spec in row['packages'] + row['bundled']:
            n, v = spec.rsplit('@', 1)
            status, data, _ = meta.get(n, (0, None, ''))
            if status == 200 and isinstance(data, dict):
                row['latest'][n] = (data.get('dist-tags') or {}).get('latest')
                dep = ((data.get('versions') or {}).get(v) or {}).get('deprecated')
                if dep:
                    rep.add('npm-deprecated', 'medium', row['id'], f'vendored {n} {v} is deprecated', str(dep)[:200],
                            'Move to the replacement its maintainers name.', key=n)
            elif n in meta:
                rep.unverified.add(row['id'])
    for top, row in sorted(rows.items()):
        for name, rec in (comps.get(top) or {}).get('receipts', []):
            verify_receipt(rep, net, row, top, name, rec)
    slugs = sorted({s for r in rep.inventory['webkit'] for s in r.get('repos') or []})
    statuses = net.map(lambda s: repo_status(net, s), slugs)
    reported = set()
    for row in rep.inventory['webkit']:
        for slug in row.get('repos') or []:
            if slug not in reported:                 # three.js serves two folders: one finding
                reported.add(slug)
                repo_findings(rep, row['id'], slug, statuses[slug], None, 'vendored', rep.as_of)


def tar_files(data, wanted):
    """{path: bytes} for the regular files named in wanted, read from a .tgz in memory (never unpacked to disk)."""
    import io
    import tarfile
    out = {}
    with tarfile.open(fileobj=io.BytesIO(data), mode='r:gz') as tf:
        for m in tf:
            if m.name in wanted and m.isfile() and m.size <= TARBALL_LIMIT:
                f = tf.extractfile(m)
                out[m.name] = f.read() if f else b''
    return out


def verify_receipt(rep, net, row, top, name, rec):
    """Online: fetch the npm tarball a receipt names, check its sha512 integrity, and compare each vendored file with the
    file at its recorded path in the package. A receipt that declares a modification is compared but not flagged."""
    src, integ, paths = rec.get('source'), str(rec.get('npm_integrity') or ''), rec.get('paths_in_package') or {}
    if not (src and str(src).startswith('https://registry.npmjs.org/') and integ.startswith('sha512-') and paths):
        return
    status, data, err = net.request(src)
    if status != 200 or not data or len(data) > TARBALL_LIMIT:
        rep.add('webkit-receipt-unverified', 'info', row['id'], f'the {name} tarball could not be read',
                err or (f'HTTP {status}' if status != 200 else f'{len(data or b"")} bytes'), 'Run again later.', key=name)
        return
    got = 'sha512-' + base64.b64encode(hashlib.sha512(data).digest()).decode()
    if got != integ:
        rep.add('webkit-receipt-integrity', 'high', row['id'], f'the {name} tarball no longer matches the integrity in its receipt',
                f'{src}: receipt {integ[:24]}…, registry {got[:24]}…',
                'Stop: the registry now serves different bytes under this version. Tell the owner; do not re-vendor from it.', key=name)
        return
    try:
        members = tar_files(data, set(paths.values()))
    except Exception as e:                 # tarfile, gzip and zlib raise many kinds on a damaged archive
        rep.add('webkit-receipt-unverified', 'info', row['id'], f'the {name} tarball could not be opened', str(e)[:160],
                'Run again later.', key=name)
        return
    modified = not str(rec.get('modifications') or 'None').startswith('None')
    differ, missing = [], []
    for local, inpkg in sorted(paths.items()):
        mine = rep.root / KIT / top / local
        if inpkg not in members:
            missing.append(inpkg)
        elif mine.is_file() and hashlib.sha256(mine.read_bytes()).hexdigest() != hashlib.sha256(members[inpkg]).hexdigest():
            differ.append(local)
    row.setdefault('receipts', {})[name] = dict(files=len(paths), identical=len(paths) - len(differ) - len(missing),
                                                differ=differ, missing=missing)
    if missing:
        rep.add('webkit-receipt', 'medium', row['id'], f'the {name} receipt names paths its package does not have',
                ', '.join(missing), 'Correct paths_in_package in the receipt.', key=f'{name}:missing')
    if differ and not modified:
        rep.add('webkit-drift', 'high', row['id'], f'{len(differ)} vendored {top} files differ from the {name} package their receipt names',
                f"{', '.join(differ)} vs {src}", 'Find out who changed them; restore the package\'s files, or record the change '
                'in the receipt\'s "modifications" and re-review.', key=f'{name}:' + ','.join(differ))


# -------------------------------------------------------------------------------------------------------------- links
# The Markdown files tools/build-site.mjs publishes as pages: its SECTIONS, in the same order and with the same patterns.
# tests/test_resource_audit.py reads build-site.mjs and fails when the two disagree.
PUBLISHED = [re.compile(r'^docs/[^/]+\.md$'), re.compile(r'^skills/[^/]+/SKILL\.md$'), re.compile(r'^agents/[^/]+\.md$'),
             re.compile(r'^lessons/(?:[a-z0-9-]+/)?[^/]+\.md$'), re.compile(r'^research/[^/]+\.md$')]
PUBLISHED_FILES = ('README.md', 'CONTRIBUTING.md', 'THIRD_PARTY_NOTICES.md')


def published(f, report=False):
    """Is f a page tools/build-site.mjs publishes? The report page is left out unless asked for (its URLs are findings)."""
    if re.search(r'(?:^|/)(?:AGENTS|CLAUDE)\.md$', f) or (f == REPORT_MD and not report):
        return False
    return f in PUBLISHED_FILES or any(rx.match(f) for rx in PUBLISHED)


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
                if str(sc.get('note', '')).startswith('not verified'):
                    rep.unverified.add(r['id'])
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
# `claude plugin marketplace add Valpatel/cad-agent#v0.8.0` (a tag) or `#<commit>`: our own release, pinned.
OUR_PINNED_MARKETPLACE = re.compile(r'\bmarketplace\s+add\s+(?:https://github\.com/)?([\w.-]+/[\w.-]+?)(?:\.git)?'
                                    r'#(v\d+(?:\.\d+)*|[0-9a-f]{7,40})(?![\w.-])', re.I)
PLUGIN_INSTALL = re.compile(r'\bplugin\s+install\s+[\w.-]+@([\w.-]+)', re.I)


def our_pinned_plugin(line, file_pinned):
    """True for plugin advice about our own marketplace pinned to a release: the `marketplace add` line itself, or a
    `plugin install <name>@<ours>` line in a file that adds our marketplace pinned (#120's install instructions)."""
    m = OUR_PINNED_MARKETPLACE.search(line)
    if m:
        return m.group(1).lower() in OUR_REPOS
    m = PLUGIN_INSTALL.search(line)
    return bool(m and file_pinned and m.group(1).lower() in OUR_MARKETPLACES)
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
        spans = code_spans(text)
        file_pinned = any(our_pinned_plugin(ln, False) for _l, code in spans for ln in code.splitlines())
        for line0, code in spans:
            for off, ln in enumerate(code.splitlines()):
                where = f'{f}:{line0 + off}'
                advice = False
                for check, sev, rx, what, action in INSTALL_ADVICE:
                    if rx.search(ln):
                        advice = True
                        if check == 'install-from-registry' and our_pinned_plugin(ln, file_pinned):
                            continue          # our own plugin at a release tag or commit: the advice we want people to follow
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
    admin = bool(((data or {}).get('permissions') or {}).get('admin')) if isinstance(data, dict) else False
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
        rep.unverified.add(f'repo:{repo}')
    # 204 enabled, 404 disabled, but only for a token with admin rights: GitHub answers 404 to anyone else as well.
    status, _, _ = net.github(f'repos/{repo}/vulnerability-alerts')
    row['dependabot_alerts'] = {204: 'enabled', 404: 'disabled' if admin else 'not verified (needs admin)'}.get(status, f'not verified ({status})')
    if status != 204 and not (status == 404 and admin):
        rep.unverified.add(f'repo:{repo}')
    if status == 404 and admin:
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
    """research/security-accepted.yaml: [{check, subject, reason, accepted, fp?}]. An acceptance without fp covers every
    finding of that check on that subject, so the advisory checks must name the fingerprint: otherwise accepting one
    moderate advisory would hide every later one on the same package."""
    text = read_text(Path(path)) if path else None
    if not text:
        return []
    items = load_yaml(text) or []
    if not isinstance(items, list):
        raise SystemExit(f'{path}: a list of accepted findings')
    for a in items:
        if not (isinstance(a, dict) and a.get('check') and a.get('subject') and a.get('reason')):
            raise SystemExit(f'{path}: every accepted finding needs check, subject and reason')
        if a['check'] in FP_REQUIRED and not a.get('fp'):
            raise SystemExit(f"{path}: accepting {a['check']} on {a['subject']} needs its fp (the finding's fingerprint), "
                             'so a later advisory on the same package is not hidden too')
    return items


def accepted_reason(items, f):
    """The reason f is accepted, or None. Nothing accepts a critical finding (a malicious package, a critical advisory)."""
    if f['severity'] == 'critical':
        return None
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


LINKY = re.compile(URL.pattern + r'|(?<![/\w.@-])www\.[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)+[^\s|<>]*')   # GFM autolinks www. too


def inert(s):
    """Text for a published table: URLs in code spans, so the report page never links people to what it flags."""
    return LINKY.sub(lambda m: f'`{m.group(0)}`', cell(str(s).replace('`', "'")))


def findings_table(fs):
    lines = ['| Severity | Subject | Finding | Evidence | Action |', '|---|---|---|---|---|']
    for f in fs:
        lines.append(f"| {f['severity']} | `{cell(f['subject'])}` | {inert(f['title'])} | {inert(f['evidence'][:300])} | "
                     f"{inert(f['action'])}{' **Accepted:** ' + inert(f['accepted']) if f.get('accepted') else ''} |")
    return lines


def revision_label(r):
    rev = f"`{(r.get('revision') or 'working tree')[:12]}`"
    return rev + (' with uncommitted changes' if r.get('dirty') else '')


def fold(summary, lines):
    """A <details> block: the page shows its summary, and the reader opens it (the site's wall-of-text gate, #179)."""
    return [f'<details><summary>{summary}</summary>', '', *lines, '', '</details>', '']


def to_markdown(r, inventory=True, limit=None, figure=None):
    """The report as one Markdown page. figure: a picture of the findings to show after the lede (a path from the page).

    Critical and high findings stay open on the page; the rest, the limits and the inventory are folded under a summary
    that gives their counts, so the page is a picture and a short list, not a wall of tables."""
    s = r['summary']
    open_ = [f for f in r['findings'] if not f.get('accepted')]
    accepted = [f for f in r['findings'] if f.get('accepted')]
    counts = ', '.join(f'{s[k]} {k}' for k in SEVERITIES if s[k]) or 'none'
    out = ['# Supply-chain and resource report', '',
           f"What cad-agent depends on, vendors and links to, checked on {r['as_of']} at revision {revision_label(r)} "
           f"({r['mode']} checks). Findings: {counts}. Generated by `tools/resource_audit.py`; how to read it and what blocks "
           "a merge are in the [cad-supply-chain skill](../skills/cad-supply-chain/SKILL.md) and on the "
           "[supply-chain page](../docs/supply-chain.md).", '']
    if figure:
        out += [f'![Open findings by area and severity, from this report: {counts}]({figure})', '']
    elif any(s[k] for k in SEVERITIES):
        out += ['```mermaid', 'pie showData title Open findings by severity'] + \
               [f'    "{k}" : {s[k]}' for k in SEVERITIES if s[k]] + ['```', '']
    out += fold('<strong>Limits.</strong> A clean report is not proof of safety: what each check can and cannot see',
                [f'- {limit_}' for limit_ in r['limits']])
    out += ['## Findings', '']
    if not open_:
        out += ['No open findings.', '']
    for sev in SEVERITIES:
        fs = [f for f in open_ if f['severity'] == sev]
        if fs and RANK[sev] <= RANK['high']:
            out += [f'### {sev.capitalize()} ({len(fs)})', ''] + findings_table(fs) + ['']
        elif fs:
            checks_ = collections.Counter(f['check'] for f in fs)
            what = ', '.join(f'{n} {c}' for c, n in sorted(checks_.items(), key=lambda x: (-x[1], x[0]))[:6])
            out += [f'### {sev.capitalize()} ({len(fs)})', ''] + fold(f'{len(fs)} {sev}: {what}' +
                                                                     (' …' if len(checks_) > 6 else ''), findings_table(fs))
    if accepted:
        out += [f'### Accepted ({len(accepted)})', ''] + fold(f'{len(accepted)} read and accepted in <code>{ACCEPTED}</code>',
                                                               findings_table(accepted))
    if inventory:
        inv, ex = r['inventory'], r.get('extra') or {}
        out += ['## What we depend on', '']
        n_tr = len(ex.get('python_transitive') or [])
        body = ['### Python dependencies', '']
        counts = ex.get('python_counts') or {}
        if counts:
            body += ['| Extra | Direct | With transitive (deps.dev, newest releases) |', '|---|---|---|'] + \
                   [f"| {g} | {c['direct']} | {c['with_transitive'] if c['with_transitive'] is not None else 'unknown'} |"
                    for g, c in counts.items()] + ['']
        if 'python_transitive' in ex:
            body += [f"{len(ex['python_transitive'])} transitive packages (at the versions deps.dev resolves) were also checked "
                    'against OSV; findings on them name the direct dependency they come through.', '']
        body += ['| Package | Extras | Range | Newest | Released | Licence | Lowest allowed | Advisories (newest / lowest) |',
                '|---|---|---|---|---|---|---|---|']
        for p in inv['python']:
            adv = p.get('advisories') or {}
            body.append(f"| `{p['name']}` | {', '.join(p['groups'])} | {cell(', '.join(sorted(set(p['range'].values()))))} | "
                       f"{p.get('latest') or ''} | {p.get('last_release') or ''} | {cell(p.get('licence') or '')} | "
                       f"{p.get('floor_release') or ''} | {len(adv.get('latest', []))} / {len(adv.get('floor', []))} |")
        nc = ex.get('npm_counts') or {}
        body += ['', '### npm (site build and browser tests)', '', f"{nc.get('direct', 0)} direct, {nc.get('with_transitive', 0)} "
                'packages in the lockfile including transitive.', '',
                '| Package | Version | Direct | Dev | Licence | Install script | Advisories |', '|---|---|---|---|---|---|---|']
        for p in inv['npm']:
            body.append(f"| `{p['name']}` | {p['version']} | {'yes' if p['direct'] else ''} | {'yes' if p['dev'] else ''} | "
                       f"{p.get('licence') or ''} | {'yes' if p['install_script'] else ''} | {len(p.get('advisories') or [])} |")
        flagged = {f['subject'] for f in open_}
        body += ['', '### Vendored code (vendor/)', '', '| Project | Pinned | Imported | Licence (manifest / file) | Files | Skills | '
                'Upstream | Behind | Scorecard | Drift |', '|---|---|---|---|---|---|---|---|---|---|']
        for v in inv['vendored']:
            up, d = v.get('upstream') or {}, v.get('drift')
            drift = f"{d['changed']} changed, {d['added']} added, {d['missing']} missing ({d['compared']} compared)" if d else ''
            score = (v.get('scorecard') or {}).get('score')
            # linked only while it has no open finding: the page never sends people to what it flags
            name = f"{cell(v['name'])} ({inert(v['url'])})" if v['id'] in flagged else f"[{cell(v['name'])}]({v['url']})"
            body.append(f"| {name} | `{(v['sha'] or '')[:12]}` | {v.get('imported') or ''} | {v.get('licence')} / "
                       f"{v.get('licence_detected') or '?'} | {v['files']} | {v['skills']} | "
                       f"{'archived' if up.get('archived') else up.get('state', '')} | {v.get('behind', '')} | "
                       f"{score if score is not None else ''} | {drift} |")
        body += ['', '### Web kit (src/cadagent/webkit/vendor/)', '',
                '| Folder | Packages | Bundled inside | Files | Hashed | Matches its npm package | Newest | Advisories |',
                '|---|---|---|---|---|---|---|---|']
        for w in inv['webkit']:
            rc = w.get('receipts') or {}
            match = ', '.join(f"{n}: {c['identical']} of {c['files']}" for n, c in sorted(rc.items()))
            body.append(f"| `{w['name']}` | {', '.join(w['packages'])} | {', '.join(w.get('bundled') or [])} | {w['files']} | "
                       f"{w['hashed']} | {match} | {', '.join(f'{k} {v}' for k, v in sorted((w.get('latest') or {}).items()))} | "
                       f"{len(set(w.get('advisories') or []))} |")
        cat = [l for l in inv['links'] if l['kind'] == 'catalogue']
        body += ['', '### Links we send people to', '',
                f"{len(cat)} catalogue links (catalog.json, upstreams/registry.yaml, research/landscape.json) and "
                f"{len(inv['links']) - len(cat)} more in published pages; {sum(1 for l in inv['links'] if l['id'] in flagged)} have "
                'findings above.', '', '### Skills and agents', '', '| Item | Kind | Source | Version |', '|---|---|---|---|']
        for k in inv['skills']:
            body.append(f"| `{k['name']}` | {k['kind']} | {cell(k['source'])} | `{k['version']}` |")
        summary = (f"{len(inv['python'])} Python packages{f' ({n_tr} more pulled in)' if n_tr else ''}, "
                   f"{len(inv['npm'])} npm packages, {len(inv['vendored'])} vendored projects, {len(inv['webkit'])} web kit "
                   f"folders, {len(inv['links'])} links, {len(inv['skills'])} skills and agents")
        out += fold(summary, body)
        out += ['## Sources', ''] + fold(f"{len(r['sources'])} sources, with how each was reached",
                                         [f'- **{k}:** {v}' for k, v in r['sources'].items()])
    text = '\n'.join(out) + '\n'
    if limit and len(text) > limit:
        text = text[:limit - 200] + '\n\n…(cut; the full report is in the run\'s artifact)\n'
    return text


# The figure: open findings per area, stacked by severity. Severity is ordinal, so one hue (the site's rust) from light
# (low) to dark (critical), checked with the dataviz palette validator: neighbours at least 15 apart in OKLab for normal
# and colour-blind vision; the light end is 2.15:1 on the page, so every segment also carries its count as a label.
SEV_FILL = {'critical': '#5e0000', 'high': '#903517', 'medium': '#c46446', 'low': '#ef9a7f'}
SEV_TEXT = {'critical': '#ffffff', 'high': '#ffffff', 'medium': '#ffffff', 'low': '#173d3c'}
FIG_INK, FIG_MUTED, FIG_LINE, FIG_BG = '#173d3c', '#526863', '#d8e0d3', '#fffdf5'
FIG_FONT = 'system-ui,-apple-system,Segoe UI,Roboto,sans-serif'
AREAS = [  # (label, subject prefixes, inventory section, what was checked: {n} is the section's item count)
    ('Python dependencies', ('pypi:',), 'python', '{n} direct, and what they pull in'),
    ('npm packages', ('npm:',), 'npm', '{n} in the lockfile'),
    ('Vendored projects', ('vendor:',), 'vendored', '{n} pinned projects'),
    ('Web kit files', ('webkit:',), 'webkit', '{n} folders and their receipts'),
    ('Links and catalogue', ('url:', 'catalogue:'), 'links', '{n} links'),
    ('Install advice in pages', ('doc:', 'skill:', 'agent:'), 'skills', 'every published page'),
    ('Repository', ('repo:',), 'repo', 'Dependabot; settings need an admin run'),
]


def area_counts(r):
    """[(label, items checked, what they are, {severity: open findings})], in AREAS order."""
    out = []
    for label, prefixes, section, noun in AREAS:
        fs = [f for f in r['findings'] if not f.get('accepted') and f['severity'] in SEV_FILL and f['subject'].startswith(prefixes)]
        out.append((label, len(r['inventory'].get(section) or []), noun.format(n=len(r['inventory'].get(section) or [])),
                    collections.Counter(f['severity'] for f in fs)))
    return out


def findings_svg(r):
    """The report as one picture (deterministic: the same report gives the same bytes)."""
    rows = area_counts(r)
    total = max((sum(c.values()) for *_x, c in rows), default=0)
    step = 5 if total <= 25 else 10 if total <= 60 else 25
    vmax = max(step, -(-total // step) * step)
    w, left, right, top, row_h, bar_h = 720, 236, 40, 92, 44, 22
    plot = w - left - right
    h = top + len(rows) * row_h + 44
    x = lambda v: left + plot * v / vmax
    e = lambda t: str(t).replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;').replace('"', '&quot;')
    open_n = sum(sum(c.values()) for *_x, c in rows)
    sub = (f"tools/resource_audit.py, {r['mode']} checks, {r['as_of']}: {open_n} open at low or above"
           + (f", {r['summary'].get('accepted', 0)} accepted" if r['summary'].get('accepted') else '')
           + (f", {r['summary'].get('info', 0)} not verified (info, not shown)" if r['summary'].get('info') else ''))
    out = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {h}" width="{w}" height="{h}" role="img" '
           f'aria-labelledby="t d" font-family="{FIG_FONT}">',
           '<title id="t">Open supply-chain findings by area and severity</title>',
           '<desc id="d">' + e('; '.join(f"{label}: " + (', '.join(f'{c[s]} {s}' for s in SEV_FILL if c[s]) or 'none')
                                         for label, _n, _noun, c in rows)) + '</desc>',
           f'<rect width="{w}" height="{h}" fill="{FIG_BG}"/>',
           f'<text x="16" y="28" font-size="17" font-weight="600" fill="{FIG_INK}">Open findings by area and severity</text>',
           f'<text x="16" y="48" font-size="12" fill="{FIG_MUTED}">{e(sub)}</text>']
    lx = 16
    for sev, fill in SEV_FILL.items():                      # legend, in severity order
        out.append(f'<rect x="{lx}" y="62" width="12" height="12" rx="2" fill="{fill}"/>'
                   f'<text x="{lx + 17}" y="72" font-size="12" fill="{FIG_INK}">{sev}</text>')
        lx += 17 + 7.2 * len(sev) + 18
    for v in range(0, vmax + 1, step):                      # recessive grid
        out.append(f'<line x1="{x(v):.1f}" y1="{top - 6}" x2="{x(v):.1f}" y2="{top + len(rows) * row_h - 10}" stroke="{FIG_LINE}"/>'
                   f'<text x="{x(v):.1f}" y="{top + len(rows) * row_h + 6}" font-size="11" fill="{FIG_MUTED}" text-anchor="middle">{v}</text>')
    for i, (label, n, noun, c) in enumerate(rows):
        y = top + i * row_h
        out.append(f'<text x="{left - 12}" y="{y + 10}" font-size="13" fill="{FIG_INK}" text-anchor="end">{e(label)}</text>'
                   f'<text x="{left - 12}" y="{y + 25}" font-size="11" fill="{FIG_MUTED}" text-anchor="end">'
                   f'{e(noun)}</text>')
        at = 0
        for sev, fill in SEV_FILL.items():
            k = c[sev]
            if not k:
                continue
            x0, x1 = x(at), x(at + k)
            out.append(f'<rect x="{x0:.1f}" y="{y}" width="{max(x1 - x0 - 2, 1):.1f}" height="{bar_h}" rx="2" fill="{fill}">'
                       f'<title>{e(label)}: {k} {sev}</title></rect>')
            if x1 - x0 >= 18:
                out.append(f'<text x="{(x0 + x1 - 2) / 2:.1f}" y="{y + 15.5}" font-size="11" fill="{SEV_TEXT[sev]}" '
                           f'text-anchor="middle">{k}</text>')
            at += k
        tail = f'{at}' if at else 'none'
        out.append(f'<text x="{x(at) + 6:.1f}" y="{y + 15.5}" font-size="12" font-weight="600" fill="{FIG_INK if at else FIG_MUTED}">{tail}</text>')
    out.append(f'<text x="16" y="{h - 12}" font-size="11" fill="{FIG_MUTED}">A clean bar is not proof of safety: the '
               'report lists what each check can and cannot see.</text>')
    return '\n'.join(out) + '\n</svg>\n'


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
    unverified = set(r.get('unverified') or [])
    for sid in ids:
        section, row = item_row(r, sid)
        what, ver, lic = describe(section, row) if row else ('removed or unknown', '', None)
        fs = [f for f in r['findings'] if f['subject'] == sid and not f.get('accepted')]
        rep = '; '.join(f"{f['severity']}: {f['title']}" for f in sorted(fs, key=lambda f: RANK[f['severity']])) or \
              f"no findings ({r['mode']} checks)"
        if sid in unverified:          # say so: a quiet row must not read as a clean one
            rep += '; some online checks did not answer, run again'
        lines.append(f'| `{sid}` | {what} | {cell(ver)} | {cell(lic or "")} | {cell(rep)} |')
    return '\n'.join(lines) + '\n'


def has_row(body, sid):
    """Does the PR description carry the report row for sid: a table row whose first cell is exactly `sid`? A mention
    elsewhere, or an id that only starts with sid (url:https://github.com/a/b vs .../a/bc), is not a row."""
    return bool(re.search(r'^[ \t]*\|[ \t]*`' + re.escape(sid) + r'`[ \t]*\|', body or '', re.M))


# ----------------------------------------------------------------------------------------------------------- commands
def make_report(a, added_files=()):
    net = Net() if a.online else None
    accepted = load_accepted(a.accepted or Path(a.root) / ACCEPTED)
    as_of = dt.date.fromisoformat(a.as_of) if a.as_of else None
    rep = build(Path(a.root), as_of, net, a.repo, a.installed, a.catalog, not a.no_npm_audit, added_files, accepted)
    return rep.to_json()


def cmd_report(a):
    r = make_report(a)
    if a.json:
        Path(a.json).parent.mkdir(parents=True, exist_ok=True)
        Path(a.json).write_text(json.dumps(r, indent=1, ensure_ascii=False) + '\n', encoding='utf-8')
    if a.md or a.svg:
        with tempfile.TemporaryDirectory() as td:          # the page and figure come from the JSON, as `render` makes them
            saved = Path(td) / 'report.json'
            saved.write_text(json.dumps(r), encoding='utf-8')
            for path, text in rendered(saved, a.md, a.svg).items():
                Path(path).parent.mkdir(parents=True, exist_ok=True)
                Path(path).write_text(text, encoding='utf-8')
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


def gate_scope(into):
    """What gate checks for a change into `into`: 'change' (the whole repository, plus what the change adds and its rows)
    where new items enter (CHANGE_BRANCHES: dev), else 'repo' (the whole repository only).

    A dev -> main release PR, and the push to main after it, carry only items that came into dev through PRs this gate
    already judged, each with its rows. Judged against main instead, "what the change adds" is everything since the last
    release: rows nobody could write in a release PR, and "new" files that were new weeks ago. That failed every release
    by construction (the review of #138)."""
    return 'change' if into in CHANGE_BRANCHES else 'repo'


def cmd_gate(a):
    """CI: nothing at --fail-on-repo anywhere; and, for a change into dev, every item it adds has its report row in the PR
    body and none has a finding at --fail-on or above."""
    scope = gate_scope(a.into)
    ids, new_files = added_items(Path(a.root), a.base) if scope == 'change' else ([], [])
    r = make_report(a, new_files)
    problems = []
    whole = failing(r, a.fail_on_repo)
    if whole:
        problems.append(f'{len(whole)} finding(s) at or above {a.fail_on_repo} in the repository:')
        problems += [f"  {f['severity']} {f['subject']}: {f['title']}" for f in whole]
    if scope == 'repo':
        print(f'supply-chain gate into {a.into}: the whole-repository check only (at or above {a.fail_on_repo}). What a '
              f'change adds, and its rows, are checked where items enter: PRs and pushes into {", ".join(CHANGE_BRANCHES)}.')
    else:
        bad = [f for f in failing(r, a.fail_on) if f['subject'] in ids]
        if bad:
            problems.append(f'{len(bad)} finding(s) at or above {a.fail_on} on what this change adds:')
            problems += [f"  {f['severity']} {f['subject']}: {f['title']} -> {f['action']}" for f in bad]
        body = os.environ.get(a.pr_body_env, '') if a.pr_body_env else (Path(a.pr_body_file).read_text() if a.pr_body_file else None)
        if body is not None and ids:
            missing = [i for i in ids if not has_row(body, i)]
            if missing:
                problems.append('the PR description has no report row for: ' + ', '.join(missing) +
                                f'\n  paste the table from: python3 tools/resource_audit.py rows --base origin/{a.into} --online '
                                '(under "Supply chain"; each row starts with the item\'s id in backticks)')
        print(f'supply-chain gate into {a.into}: {len(ids)} item(s) added since {a.base}' + (': ' + ', '.join(ids) if ids else ''))
        if ids:
            print(rows_markdown(r, ids))
    for p in problems:
        print(p)
    return 1 if problems else 0


def rendered(report_path, md, svg):
    """{path: text} for the page and the figure a saved report gives (no network: a layout change re-renders them)."""
    r = json.loads(Path(report_path).read_text(encoding='utf-8'))
    out = {}
    if svg:
        out[svg] = findings_svg(r)
    if md:
        fig = os.path.relpath(Path(svg).resolve(), Path(md).resolve().parent).replace(os.sep, '/') if svg else None
        out[md] = to_markdown(r, figure=fig)
    return out


def cmd_render(a):
    """Write the page and the figure from a saved report; --check: exit 1 when a committed file is not what it gives."""
    bad = 0
    for path, text in rendered(a.report, a.md, a.svg).items():
        if a.check:
            same = Path(path).exists() and Path(path).read_text(encoding='utf-8') == text
            print(f"{path}: {'matches' if same else 'differs from'} {a.report}")
            bad += not same
        else:
            Path(path).parent.mkdir(parents=True, exist_ok=True)
            Path(path).write_text(text, encoding='utf-8')
    return 1 if bad else 0


MARK = re.compile(r'<!-- cad-supply-chain-report fps=([0-9a-f~,]*) -->')
BOTS = ('github-actions[bot]', 'app/github-actions', 'github-actions')


def scope_tag(subject):
    """8 hex digits naming a finding's scope in the issue marker, so a later run knows which old findings it could not
    re-check (the marker stays short and carries no third-party text)."""
    return hashlib.sha256(str(subject).encode()).hexdigest()[:8]


def no_mentions(text):
    """Text for a public issue: outside code spans, `@name` and `#123` get a zero-width space, so third-party text
    (advisory summaries, deprecation notes) never notifies a person or links an unrelated issue."""
    parts = re.split(r'(`[^`\n]+`)', text)
    return ''.join(p if len(p) > 1 and p[0] == p[-1] == '`' else
                   re.sub(r'(?<!&)#(?=\d)', '#\u200b', re.sub(r'(?<![\w&])@(?=[A-Za-z0-9])', '@\u200b', p)) for p in parts)


def gh_json(*args):
    r = subprocess.run(['gh', *args], capture_output=True, text=True)
    if r.returncode:
        raise SystemExit(f"gh {' '.join(args[:3])} failed: {r.stderr.strip()[:300]}")
    return json.loads(r.stdout or 'null')


def plan_issue(r, issues, repo, title, authors=BOTS):
    """The gh commands that bring the one tracking issue in line with a report: [(args, stdin)], and a note.

    The issue is the one open issue opened by an allowed author whose body carries the fingerprint marker; anyone can
    write a marker, so the author check keeps the workflow from editing someone else's issue. A finding this run could
    not re-check (its scope is in the report's `unverified`: OSV, a repository or a site did not answer) is kept as
    "not re-checked", not counted as resolved, so a week without an answer does not close and reopen it."""
    live = [f for f in r['findings'] if not f.get('accepted') and RANK[f['severity']] <= RANK['low']
            and not f['check'].endswith('-unverified')]
    tags = {f['fp']: scope_tag(f.get('scope') or f['subject']) for f in live}
    unverified = {scope_tag(s) for s in r.get('unverified') or []}
    mine = [i for i in issues or [] if MARK.search(i.get('body') or '') and (i.get('author') or {}).get('login') in set(authors)]
    if not mine:
        if not tags:
            return [], 'no open findings at low or above; no issue needed'
        return [(['issue', 'create', '-R', repo, '--title', title, '--body-file', '-'], issue_body(r, tags, {}))], 'open a new issue'
    num = str(mine[0]['number'])
    old = dict((e.split('~', 1) + [''])[:2] for e in MARK.search(mine[0]['body']).group(1).split(',') if e)
    carried = {fp: t for fp, t in old.items() if fp not in tags and t and t in unverified}
    keep = {**tags, **carried}
    if set(old) == set(keep) and all(old[fp] == keep[fp] for fp in old if old[fp]):
        return [], f'issue #{num}: findings unchanged' + (f' ({len(carried)} not re-checked)' if carried else '')
    new = [f for f in live if f['fp'] not in old]
    gone = len(set(old) - set(keep))
    rev = f"revision `{(r['revision'] or '')[:12]}`" + (' with uncommitted changes' if r.get('dirty') else '')
    note = '\n'.join([f"Report of {r['as_of']} ({rev}): {len(new)} new, {gone} resolved"
                      + (f", {len(carried)} not re-checked (kept open)" if carried else '') + '.', ''] +
                     [f"- **{f['severity']}** `{f['subject']}`: {inert(f['title'])}" for f in new[:50]]) + '\n'
    plan = [(['issue', 'edit', num, '-R', repo, '--body-file', '-'], issue_body(r, tags, carried)),
            (['issue', 'comment', num, '-R', repo, '--body-file', '-'], no_mentions(note))]
    if not keep:
        plan.append((['issue', 'close', num, '-R', repo, '--comment', 'No open findings at low or above: closing.'], None))
    return plan, f'update issue #{num}: {len(new)} new, {gone} resolved' + (f', {len(carried)} not re-checked' if carried else '')


def issue_body(r, tags, carried):
    body = to_markdown(r, inventory=False, limit=60000)
    if carried:
        body += (f"\n{len(carried)} finding(s) from an earlier report could not be re-checked this time (a service or "
                 'site did not answer), so they stay open until a run can check them.\n')
    marker = ','.join(f'{fp}~{t}' for fp, t in sorted({**tags, **carried}.items()))
    return no_mentions(body) + f"\n<!-- cad-supply-chain-report fps={marker} -->\n"


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
    p = sub.add_parser('report', help='run the checks; write JSON, Markdown and the figure')
    common(p)
    p.add_argument('--json')
    p.add_argument('--md')
    p.add_argument('--svg', help='also draw the findings figure here (the Markdown then shows it)')
    p.add_argument('--fail-on', default='high', choices=[*SEVERITIES, 'none'])
    p = sub.add_parser('rows', help='report rows for the items this branch adds since --base (paste into the PR)')
    common(p)
    p.add_argument('--base', default='origin/dev')
    p = sub.add_parser('gate', help='CI: added items have rows in the PR body and no finding at --fail-on or above')
    common(p)
    p.add_argument('--base', default='origin/dev')
    p.add_argument('--into', default='dev', help='the branch the change goes into (a PR\'s base, a push\'s branch). Only '
                   f'{", ".join(CHANGE_BRANCHES)} judges what the change adds; any other gets the whole-repository check alone')
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
    p = sub.add_parser('render', help='write the report page and its figure from a saved report (no network)')
    p.add_argument('--report', default=str(ROOT / 'research/security-report.json'))
    p.add_argument('--md', default=str(ROOT / REPORT_MD))
    p.add_argument('--svg', default=str(ROOT / 'docs/img/supply-chain/findings.svg'))
    p.add_argument('--check', action='store_true', help='exit 1 if a file is not what the report gives')
    a = ap.parse_args(argv)
    try:
        return {'report': cmd_report, 'rows': cmd_rows, 'gate': cmd_gate, 'issue': cmd_issue, 'render': cmd_render}[a.cmd](a)
    except (OSError, ValueError, KeyError) as e:
        print(f'resource_audit: {type(e).__name__}: {e}', file=sys.stderr)
        return 2


if __name__ == '__main__':
    sys.exit(main())
