"""PCB evidence adapters. CAD validity and production qualification stay separate.

No KiCad Python dependency: consume kicad-cli JSON reports and exact source hashes.
A missing report or unrecognized schema fails closed; a clean DRC never certifies
signal integrity, protection, supplier assembly, or physical fit.
"""
from __future__ import annotations
import csv
import hashlib
import json
from pathlib import Path


def sha256(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def kicad_report(path: Path, kind: str) -> dict:
    if kind not in {'erc', 'drc'}:
        raise ValueError('kind must be erc or drc')
    result = {'kind': kind, 'pass': False, 'errors': 0, 'warnings': 0,
              'unconnected': 0, 'parity': 0, 'reason': ''}
    try:
        data = json.loads(Path(path).read_text())
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
        for v in violations:
            if not isinstance(v, dict) or v.get('severity') not in {'error','warning','exclusion'}:
                raise ValueError('unknown violation severity')
            if v['severity'] == 'error': result['errors'] += 1
            if v['severity'] == 'warning': result['warnings'] += 1
        # Exclusions are visible and must be reviewed, not silently accepted.
        result['exclusions'] = sum(v['severity']=='exclusion' for v in violations)
        result['pass'] = not any(result[k] for k in ('errors','warnings','exclusions','unconnected','parity'))
    except (OSError,ValueError,KeyError,TypeError) as e:
        result['reason'] = f'Unusable {kind} evidence: {e}'
    return result


def evidence_bundle(root: Path, reports: dict, sources: list[str], gates: list[dict]) -> dict:
    """Bind current review reports to source snapshots; all gates need literal True."""
    root=Path(root)
    checks=[kicad_report(root/rel,kind) for kind,rel in reports.items()]
    complete=set(reports)=={'erc','drc'} and bool(sources)
    hashes={rel:sha256(root/rel) for rel in sources}
    report_hashes={rel:sha256(root/rel) for rel in reports.values() if (root/rel).is_file()}
    return {'schema_version':1,'pass':complete and all(c['pass'] for c in checks),
            'checks':checks,'source_sha256':hashes,'report_sha256':report_hashes,
            'production_ready':complete and bool(gates) and all(g.get('pass') is True for g in gates) and all(c['pass'] for c in checks),
            'release_gates':gates,'physical_fit_verified':False,'electrical_tested':False}


def evidence_is_current(root: Path, bundle: dict) -> bool:
    try:
        sources=bundle['source_sha256'];reports=bundle['report_sha256']
        return bool(sources) and bool(reports) and all(sha256(Path(root)/p)==h for p,h in {**sources,**reports}.items())
    except (OSError,KeyError,TypeError):return False


def check_jlc_files(bom: Path, cpl: Path) -> dict:
    """Check exact columns, duplicate references, numeric placements and BOM/CPL parity.

    Input contains assembled SMT components only. THT/manual and DNP lists belong
    in separate files; having a C-code doesn't prove stock or orientation.
    """
    errors=[];bom_refs=set();pos_refs=set()
    try:
        with Path(bom).open(newline='') as f:
            reader=csv.DictReader(f)
            if not {'Comment','Designator','Footprint','LCSC Part #'} <= set(reader.fieldnames or []):
                errors.append('Missing required JLCPCB BOM columns')
            for row in reader:
                import re
                if not re.fullmatch(r'C[0-9]+',row.get('LCSC Part #','')):errors.append('Missing/invalid exact LCSC code')
                for ref in row.get('Designator','').split(','):
                    ref=ref.strip()
                    if not ref or ref in bom_refs: errors.append(f'Empty/duplicate BOM reference: {ref}')
                    bom_refs.add(ref)
        with Path(cpl).open(newline='') as f:
            reader=csv.DictReader(f)
            if not {'Designator','Mid X','Mid Y','Layer','Rotation'} <= set(reader.fieldnames or []):
                errors.append('Missing required JLCPCB CPL columns')
            for row in reader:
                ref=row.get('Designator','')
                if not ref or ref in pos_refs:errors.append(f'Empty/duplicate CPL reference: {ref}')
                pos_refs.add(ref)
                if row.get('Layer') not in {'top','bottom'}:errors.append(f'Invalid CPL layer: {ref}')
                import math
                for key in ('Mid X','Mid Y','Rotation'):
                    try:
                        if not math.isfinite(float(row[key])):raise ValueError()
                    except (ValueError,KeyError):errors.append(f'Invalid {key}: {ref}')
        if not bom_refs:errors.append('Empty assembly BOM')
        if bom_refs != pos_refs:errors.append('BOM/CPL reference sets differ')
    except (OSError,csv.Error) as e:errors.append(str(e))
    return {'pass':not errors,'errors':errors,'assembled_refs':sorted(bom_refs),
            'stock_verified':False,'rotation_verified':False,'production_ready':False}
