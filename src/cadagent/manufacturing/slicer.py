"""Real filament grams and print time from a slicer (Bambu Studio's command line, run as a separate program).

    from cadagent.manufacturing.slicer import slice_part
    r = slice_part('exports/base.3mf', workdir='build/slicer', overrides={'wall_loops': '3', 'sparse_infill_density': '15%'})
    r['grams'], r['minutes']

The slicer's own system profiles inherit from parent profiles; passed to the command line as they are, they leave
values such as the filament density unset (the slicer then reports 0 g). ``flatten`` resolves parents and ordered
included templates into one file per profile before slicing. Profiles are named as the slicer names them
(printer, process, filament). ``resolve_profile`` also returns hashes of the consumed profile files.

Bambu Studio is AGPL-3.0: it is only ever run as a separate process. The snap package cannot read hidden folders
or /tmp, so the work folder must be a normal folder under your home directory (the default is next to the model).
"""
from __future__ import annotations

import hashlib
import json
import re
import shutil
import subprocess
import zipfile
from pathlib import Path
from typing import Dict, List, Optional

PRINTER = 'Bambu Lab P1S 0.4 nozzle'
_MARK = '.cadagent-slicer'
PROCESS = '0.20mm Standard @BBL X1C'          # lists the P1S 0.4 nozzle among its compatible printers
FILAMENTS = {'pla': 'Bambu PLA Basic @BBL P1S 0.4 nozzle', 'petg': 'Bambu PETG HF @BBL P1S 0.4 nozzle'}

_PROFILE_ROOTS = [
    Path('/snap/bambu-studio/current/opt/bambu-studio/resources/profiles/BBL'),
    Path('/opt/bambu-studio/resources/profiles/BBL'),
    Path.home() / '.local/share/BambuStudio/resources/profiles/BBL',
]


def executable() -> Optional[str]:
    for name in ('bambu-studio', 'BambuStudio', 'bambu-studio.AppImage'):
        p = shutil.which(name)
        if p:
            return p
    return None


def profile_root() -> Path:
    for r in _PROFILE_ROOTS:
        if (r / 'machine').is_dir():
            return r
    raise FileNotFoundError('Bambu Studio system profiles not found; install Bambu Studio (snap install bambu-studio)')


def _profile_name(value, kind: str) -> str:
    # Names are lookup labels, never paths: real Bambu labels include PA/PET.
    if (not isinstance(value, str) or not value.strip() or '\\' in value
            or value.startswith('/') or any(p in ('.', '..') for p in value.split('/'))):
        raise ValueError(f'Invalid {kind} profile reference: {value!r}')
    return value


def _index(kind: str, root: Path) -> dict:
    """Capture each JSON once; resolution and dependency hashes use those same bytes."""
    out = {}
    for f in sorted((root / kind).glob('*.json')):
        if not f.resolve().is_relative_to(root.resolve()):
            raise ValueError(f'Profile path escapes root: {f}')
        try:
            raw = f.read_bytes()
            data = json.loads(raw)
        except (json.JSONDecodeError, UnicodeDecodeError):
            raise ValueError(f'Malformed {kind} profile JSON: {f}') from None
        if not isinstance(data, dict):
            raise ValueError(f'{kind} profile JSON must be an object: {f}')
        if 'name' not in data:
            # Bambu also ships nameless lookup maps in the profile folders.
            # A named profile cannot be silently omitted from the index.
            continue
        n = _profile_name(data['name'], kind)
        if n in out:
            raise ValueError(f'Duplicate {kind} profile {n!r}: {out[n][0]} and {f}')
        out[n] = (f, data, hashlib.sha256(raw).hexdigest())
    return out


def resolve_profile(kind: str, name: str) -> dict:
    """Return ``settings`` and ``files`` (root-relative path → SHA-256) for a system profile.

    Merge parent → includes in list order → explicit keys, recursively. Include
    may be one name or a list. Missing dependencies raise KeyError; malformed,
    ambiguous, escaping or cyclic dependencies raise ValueError. Files are read
    once per call. The identities describe that capture, not ongoing filesystem
    stability, executable G-code validation or physical print qualification.
    """
    ids = {'machine': 'printer_settings_id', 'process': 'print_settings_id', 'filament': 'filament_settings_id'}
    if kind not in ids:
        raise ValueError(f'Unknown profile kind: {kind!r}')
    root = profile_root()
    idx = _index(kind, root)
    active, cache, files = [], {}, {}

    def resolve(current):
        current = _profile_name(current, kind)
        if current in active:
            raise ValueError(f'Cyclic {kind} inheritance/include: {" -> ".join(active + [current])}')
        if current not in idx:
            raise KeyError(f'{kind} profile {current!r} not found under {root / kind}')
        if current in cache:
            return dict(cache[current])
        active.append(current)
        path, data, sha = idx[current]
        files[path.relative_to(root).as_posix()] = sha
        parent = data.get('inherits', '')
        if not isinstance(parent, str):
            raise ValueError(f'Invalid {kind} parent in {current!r}: {parent!r}')
        settings = resolve(parent) if parent else {}
        included = data.get('include', [])
        if isinstance(included, str):
            included = [included]
        if not isinstance(included, list):
            raise ValueError(f'Invalid {kind} include list in {current!r}: {included!r}')
        for reference in included:
            settings.update(resolve(reference))
        settings.update({k: v for k, v in data.items() if k not in ('inherits', 'include')})
        active.pop()
        cache[current] = dict(settings)
        return settings

    out = resolve(name)
    out['name'] = name
    out['from'] = 'system'          # 'User' presets fail the CLI's printer compatibility check
    # the compatibility check matches the process's compatible_printers against the printer's settings id
    out[ids[kind]] = [name] if kind == 'filament' else name
    return {'settings': out, 'files': files}


def flatten(kind: str, name: str) -> dict:
    """A system profile with parent and ordered includes merged before explicit child keys."""
    return resolve_profile(kind, name)['settings']


def _read_result(out: Path) -> dict:
    r = {}
    rj = out / 'result.json'
    if rj.exists():
        d = json.loads(rj.read_text())
        plates = d.get('sliced_plates') or []
        g = sum(f.get('total_used_g', 0) for p in plates for f in p.get('filaments', []))
        t = sum(p.get('total_predication', 0) for p in plates)
        r.update(grams=round(float(g), 2), seconds=float(t), return_code=d.get('return_code'), error=d.get('error_string') or None)
    for z in out.glob('*.3mf'):
        try:
            with zipfile.ZipFile(z) as zf:
                info = zf.read('Metadata/slice_info.config').decode()
        except (KeyError, zipfile.BadZipFile):
            continue
        m = re.search(r'used_m="([\d.]+)"', info)
        if m:
            r['filament_m'] = float(m.group(1))
        if 'grams' not in r:
            m = re.search(r'used_g="([\d.]+)"', info)
            if m:
                r['grams'] = float(m.group(1))
    return r


def slice_part(model, workdir=None, printer: str = PRINTER, process: str = PROCESS, filament: str = 'pla',
               overrides: Optional[dict] = None, timeout: float = 900) -> dict:
    """Slice one STL or 3MF (already in print orientation) and return grams, minutes and the settings used."""
    exe = executable()
    if not exe:
        raise RuntimeError('Bambu Studio is not installed (snap install bambu-studio); cannot measure filament')
    model = Path(model).resolve()
    work = Path(workdir).resolve() if workdir else model.parent / 'slicer' / model.stem
    if work.exists():
        # only ever clear a folder this function wrote (or an empty one)
        ours = (work / _MARK).exists() or (work / 'result-summary.json').exists()   # the older marker too
        if not ours and any(work.iterdir()):
            raise FileExistsError(f'{work} exists and is not a slicer work folder; choose an empty or new folder')
        shutil.rmtree(work)
    work.mkdir(parents=True)
    (work / _MARK).write_text('cadagent.manufacturing.slicer work folder: safe to delete\n')   # first, so a crashed slice can be redone
    fil = FILAMENTS.get(filament, filament)
    profiles = {kind: resolve_profile(kind, name)
                for kind, name in (('machine', printer), ('process', process), ('filament', fil))}
    mach, proc, fl = (profiles[kind]['settings'] for kind in ('machine', 'process', 'filament'))
    for k, v in (overrides or {}).items():
        proc[k] = v if isinstance(v, list) or k not in proc or not isinstance(proc[k], list) else [str(v)] * len(proc[k])
    paths = {}
    for key, d in (('machine', mach), ('process', proc), ('filament', fl)):
        paths[key] = work / f'{key}.json'
        paths[key].write_text(json.dumps(d, indent=1))
    settings_hashes = {kind: _sha(path) for kind, path in paths.items()}
    out = work / 'out'
    out.mkdir()
    cmd = [exe, '--slice', '0', '--arrange', '1', '--orient', '0',
           '--load-settings', f"{paths['machine']};{paths['process']}", '--load-filaments', str(paths['filament']),
           '--outputdir', str(out), '--export-3mf', 'sliced.3mf', str(model)]
    p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    if any(_sha(path) != settings_hashes[kind] for kind, path in paths.items()):
        raise ValueError('Resolved slicer settings changed during slicing')
    r = _read_result(out)
    r.update(model=str(model), printer=printer, process=process, filament=fil,
             overrides=dict(overrides or {}), exit_code=p.returncode,
             profile_sources={kind: p['files'] for kind, p in profiles.items()},
             settings_sha256=settings_hashes,
             slicer=Path(exe).name, minutes=round(r.get('seconds', 0) / 60, 1) if r.get('seconds') else None)
    if not r.get('grams'):
        r['log_tail'] = (p.stdout + p.stderr)[-2000:]
    (work / 'result-summary.json').write_text(json.dumps(r, indent=2) + '\n')
    return r


def _sha(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _settings(project) -> dict:
    cfg = dict(project.slicer or {})
    fil = cfg.get('filament', 'pla')
    return {'printer': cfg.get('printer', PRINTER), 'process': cfg.get('process', PROCESS), 'filament': FILAMENTS.get(fil, fil),
            'overrides': cfg.get('overrides') or {}}


def _expected_parts(project) -> List[str]:
    from cadagent.publish.report import load_parts
    cfg = dict(project.slicer or {})
    known, _ = load_parts(project)
    return list(cfg.get('parts') or known)


def slice_project(project, parts=None) -> dict:
    """Slice each part's 3MF (``exports/<part>.3mf``) with the project's ``cad.slicer`` settings and write
    ``exports/slice-report.json``: grams and minutes per part, the totals, the settings, and each 3MF's sha256 so the
    report can tell a stale result from a current one.

    ``cad.slicer`` keys (all optional): printer, process, filament (``pla``, ``petg`` or a profile name), overrides
    (process settings, e.g. ``{wall_loops: "3"}``), parts (the parts to slice; default all)."""
    from cadagent.publish.report import load_parts

    cfg = dict(project.slicer or {})
    known, error = load_parts(project)
    if error:
        raise FileNotFoundError(error)
    names = list(parts or cfg.get('parts') or known)
    work = project.root / 'build' / 'slicer'
    path = project.exports_dir / 'slice-report.json'
    rows = {}
    if parts and path.exists():   # slicing some parts updates them in a report made with the same settings
        try:
            old = json.loads(path.read_text())
            if all(old.get(k) == v for k, v in _settings(project).items()):
                rows = dict(old.get('parts', {}))
        except json.JSONDecodeError:
            pass
    for name in names:
        model = project.exports_dir / f'{name}.3mf'
        if not model.exists():
            rows[name] = {'error': f'{model.name} not found'}
            continue
        r = slice_part(model, workdir=work / name, printer=cfg.get('printer', PRINTER), process=cfg.get('process', PROCESS),
                       filament=cfg.get('filament', 'pla'), overrides=cfg.get('overrides'))
        r['sha256'] = _sha(model)
        rows[name] = {k: r.get(k) for k in ('grams', 'minutes', 'filament_m', 'error', 'sha256')}
    total_g = sum(v.get('grams') or 0.0 for v in rows.values())
    total_min = sum(v.get('minutes') or 0.0 for v in rows.values())
    exe = executable()
    out = {'slicer': 'Bambu Studio (command line)', **_settings(project), 'slicer_executable': str(Path(exe).resolve()) if exe else None,
           'parts': rows, 'total_grams': round(total_g, 1), 'total_hours': round(total_min / 60, 2),
           'pass': bool(rows) and all(v.get('grams') for v in rows.values()),
           'note': 'Slicer estimates for one copy of each part with the stated profile; supports off unless the profile turns them on.'}
    path.write_text(json.dumps(out, indent=2) + '\n')
    out['path'] = str(path)
    return out


def current_report(project) -> Optional[dict]:
    """The slice report only when it is complete and current: every expected part (``cad.slicer.parts``, else every
    part) sliced, with the settings ``cad.slicer`` names now, from 3MF files unchanged since (sha256). Else None."""
    path = project.exports_dir / 'slice-report.json'
    if not path.exists():
        return None
    try:
        rep = json.loads(path.read_text())
    except json.JSONDecodeError:
        return None
    if not rep.get('parts') or set(rep['parts']) != set(_expected_parts(project)):
        return None
    if any(rep.get(k) != v for k, v in _settings(project).items()):
        return None
    for name, row in rep.get('parts', {}).items():
        f = project.exports_dir / f'{name}.3mf'
        if not row.get('grams') or not f.exists() or _sha(f) != row.get('sha256'):
            return None
    return rep
