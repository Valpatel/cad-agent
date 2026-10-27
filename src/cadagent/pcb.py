"""PCB evidence adapters. CAD validity and production qualification stay separate.

No KiCad Python dependency: consume kicad-cli JSON reports and exact source hashes.
A missing report or unrecognized schema fails closed; a clean DRC never certifies
signal integrity, protection, supplier assembly, or physical fit.
"""
from __future__ import annotations
import csv
import hashlib
import json
import math
import re
from pathlib import Path


REPORT_KINDS = ('erc', 'drc')
# kicad-cli 10 writes the severities it was asked for into the report. Only --severity-all (or all three
# --severity-* flags) covers every finding; the default run leaves exclusions out, --severity-error drops warnings.
REQUIRED_SEVERITIES = ('error', 'warning', 'exclusion')


def sha256(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def contained(root: Path, rel) -> Path:
    """Resolve ``rel`` under ``root``; a path (or symlink) outside the root, or not a regular file, is a ValueError."""
    if not isinstance(rel, str) or not rel:
        raise ValueError(f'path must be a nonempty string: {rel!r}')
    base = Path(root).resolve()
    path = (base / rel).resolve()
    if base not in path.parents:
        raise ValueError(f'{rel} is outside the project root')
    if not path.is_file():
        raise ValueError(f'{rel} is not a regular file')
    return path


def _waivers(waivers) -> dict:
    if waivers is None:
        return {}
    if not isinstance(waivers, dict) or not all(isinstance(k, str) and k and isinstance(v, str) and v.strip()
                                                for k, v in waivers.items()):
        raise ValueError('waivers must map each KiCad check key to a nonempty reason')
    return waivers


def _failed_check(kind: str, reason: str) -> dict:
    return {'kind': kind, 'pass': False, 'errors': 0, 'warnings': 0, 'exclusions': 0,
            'unconnected': 0, 'parity': 0, 'ignored_checks': [], 'excluded_checks': [],
            'unwaived': [], 'waived': {}, 'reason': reason}


def kicad_report(path: Path, kind: str, waivers: dict | None = None) -> dict:
    """Summarise a kicad-cli ERC/DRC JSON report; anything unproven fails.

    The report must cover every severity (``included_severities`` holds error, warning and exclusion).
    Each ignored check (``ignored_checks``) and each excluded violation is a finding that fails unless
    ``waivers`` names its check key with a reason; waived findings stay listed in the result.
    """
    result = _failed_check(kind, '')
    try:
        if kind not in REPORT_KINDS:
            raise ValueError('kind must be erc or drc')
        waivers = _waivers(waivers)
        data = json.loads(Path(path).read_text())
        if not isinstance(data, dict):
            raise ValueError('report must be a JSON object')
        severities = data.get('included_severities')
        if not isinstance(severities, list) or not set(REQUIRED_SEVERITIES) <= set(severities):
            raise ValueError(f'report filtered severities: included_severities={severities!r}; '
                             'rerun kicad-cli with --severity-all')
        ignored = data.get('ignored_checks', [])
        if not isinstance(ignored, list) or any(not isinstance(c, dict) or not isinstance(c.get('key'), str)
                                                for c in ignored):
            raise ValueError('ignored_checks must be a list of {key, description}')
        if kind == 'erc':
            sheets = data['sheets']
            if not isinstance(sheets, list) or not sheets:
                raise ValueError('missing schematic sheets')
            collections = [s['violations'] for s in sheets]
            if any(not isinstance(c, list) for c in collections):
                raise ValueError('violations must be lists')
            violations = [v for c in collections for v in c]
        else:
            collections = [data[k] for k in ('violations','unconnected_items','schematic_parity')]
            if any(not isinstance(c, list) for c in collections):
                raise ValueError('DRC collections must be lists')
            violations, unconnected, parity = collections
            result.update(unconnected=len(unconnected), parity=len(parity))
        excluded = []
        for v in violations:
            if not isinstance(v, dict) or v.get('severity') not in set(REQUIRED_SEVERITIES):
                raise ValueError('unknown violation severity')
            if v['severity'] == 'error': result['errors'] += 1
            if v['severity'] == 'warning': result['warnings'] += 1
            if v['severity'] == 'exclusion': excluded.append(str(v.get('type') or '(untyped)'))
        result['exclusions'] = len(excluded)
        result['ignored_checks'] = sorted(c['key'] for c in ignored)
        result['excluded_checks'] = sorted(set(excluded))
        # Ignored checks and exclusions are visible findings; only a named, reasoned waiver accepts one.
        findings = sorted(set(result['ignored_checks']) | set(excluded))
        result['waived'] = {k: waivers[k] for k in findings if k in waivers}
        result['unwaived'] = [k for k in findings if k not in waivers]
        if result['unwaived']:
            result['reason'] = 'Unwaived ignored or excluded checks: ' + ', '.join(result['unwaived'])
        result['pass'] = not result['unwaived'] and not any(
            result[k] for k in ('errors','warnings','unconnected','parity'))
    except (OSError,ValueError,KeyError,TypeError) as e:
        result['reason'] = f'Unusable {kind} evidence: {e}'
    return result


def manifest_problems(reports, sources, gates, waivers=None) -> list[str]:
    """Shape errors in an evidence manifest (empty list when well formed)."""
    problems = []
    if not isinstance(reports, dict):
        problems.append('reports must be an object {erc: path, drc: path}')
    else:
        extra = sorted(set(map(str, reports)) - set(REPORT_KINDS))
        if extra:
            problems.append(f'unknown report kinds {extra}: only erc and drc are supported')
        if any(not isinstance(v, str) or not v for v in reports.values()):
            problems.append('report paths must be nonempty strings')
    if not isinstance(sources, list) or any(not isinstance(s, str) or not s for s in sources):
        problems.append('sources must be a list of path strings')
    if not isinstance(gates, list) or any(not isinstance(g, dict) for g in gates):
        problems.append('release_gates must be a list of objects such as {"id": "physical-fit", "pass": false}')
    try:
        _waivers(waivers)
    except ValueError as e:
        problems.append(str(e))
    return problems


def evidence_bundle(root: Path, reports: dict, sources: list[str], gates: list[dict], waivers: dict | None = None) -> dict:
    """Bind current review reports to source snapshots; all gates need literal True.

    Every source and report must be a regular file inside ``root`` (symlinks are resolved); anything else, or a
    malformed manifest, gives a failing bundle with its ``problems`` listed.
    """
    root = Path(root).resolve()
    problems = manifest_problems(reports, sources, gates, waivers)
    bad = {'schema_version': 1, 'pass': False, 'production_ready': False, 'problems': problems,
           'reports_older_than_source': [], 'checks': [], 'source_sha256': {}, 'report_sha256': {},
           'release_gates': gates if isinstance(gates, list) else [], 'waivers': {},
           'physical_fit_verified': False, 'electrical_tested': False}
    if problems:
        return bad
    resolved = {}
    for rel in list(reports.values()) + list(sources):
        try:
            resolved[rel] = contained(root, rel)
        except ValueError as e:
            problems.append(str(e))
    key = lambda rel: resolved[rel].relative_to(root).as_posix()
    checks = [kicad_report(resolved[rel], kind, waivers) if rel in resolved else
              _failed_check(kind, f'Unusable {kind} evidence: {rel} rejected')
              for kind, rel in reports.items()]
    if problems:
        return dict(bad, problems=problems, checks=checks)
    hashes = {key(rel): sha256(resolved[rel]) for rel in sources}
    report_hashes = {key(rel): sha256(resolved[rel]) for rel in reports.values()}
    newest = max((resolved[p].stat().st_mtime_ns for p in sources), default=0)
    stale = [key(rel) for rel in reports.values() if resolved[rel].stat().st_mtime_ns < newest]
    complete = set(reports) == set(REPORT_KINDS) and bool(sources) and not stale
    clean = complete and all(c['pass'] for c in checks)
    return {'schema_version':1,'pass':clean,'problems':[],
            'reports_older_than_source':stale,'checks':checks,'source_sha256':hashes,'report_sha256':report_hashes,
            'production_ready':clean and bool(gates) and all(g.get('pass') is True for g in gates),
            'release_gates':gates,'waivers':dict(waivers or {}),'physical_fit_verified':False,'electrical_tested':False}


def evidence_is_current(root: Path, bundle: dict) -> bool:
    """True when the bundle records sources and reports and every recorded file is unchanged inside ``root``."""
    from cadagent.evidence import hashes_are_current
    try:
        return (bool(bundle['source_sha256']) and bool(bundle['report_sha256'])
                and hashes_are_current(root, bundle))
    except (KeyError, TypeError):
        return False


def check_jlc_files(bom: Path, cpl: Path) -> dict:
    """Check exact columns, duplicate references, numeric placements and BOM/CPL parity.

    Input contains assembled SMT components only. THT/manual and DNP lists belong
    in separate files; having a C-code doesn't prove stock or orientation.
    """
    errors=[];bom_refs=set();pos_refs=set()
    try:
        with Path(bom).open(newline='') as f:
            reader=csv.DictReader(f,restval='')
            if not {'Comment','Designator','Footprint','LCSC Part #'} <= set(reader.fieldnames or []):
                errors.append('Missing required JLCPCB BOM columns')
            for row in reader:
                line=reader.line_num
                if None in row:errors.append(f'BOM line {line}: more fields than columns')
                if not re.fullmatch(r'C[0-9]+',row.get('LCSC Part #') or ''):errors.append(f'BOM line {line}: missing/invalid exact LCSC code')
                for ref in (row.get('Designator') or '').split(','):
                    ref=ref.strip()
                    if not ref or ref in bom_refs: errors.append(f'Empty/duplicate BOM reference: {ref}')
                    bom_refs.add(ref)
        with Path(cpl).open(newline='') as f:
            reader=csv.DictReader(f,restval='')
            if not {'Designator','Mid X','Mid Y','Layer','Rotation'} <= set(reader.fieldnames or []):
                errors.append('Missing required JLCPCB CPL columns')
            for row in reader:
                line=reader.line_num
                if None in row:errors.append(f'CPL line {line}: more fields than columns')
                ref=row.get('Designator') or ''
                if not ref or ref in pos_refs:errors.append(f'Empty/duplicate CPL reference: {ref}')
                pos_refs.add(ref)
                if row.get('Layer') not in {'top','bottom'}:errors.append(f'Invalid CPL layer: {ref}')
                for key in ('Mid X','Mid Y','Rotation'):
                    try:
                        if not math.isfinite(float(row[key])):raise ValueError()
                    except (ValueError,KeyError,TypeError):errors.append(f'Invalid {key}: {ref}')
        if not bom_refs:errors.append('Empty assembly BOM')
        if bom_refs != pos_refs:errors.append('BOM/CPL reference sets differ')
    except (OSError,csv.Error,UnicodeDecodeError) as e:errors.append(str(e))
    return {'pass':not errors,'errors':errors,'assembled_refs':sorted(bom_refs),
            'stock_verified':False,'rotation_verified':False,'production_ready':False}
