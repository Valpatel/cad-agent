"""Real filament grams and print time from a slicer (Bambu Studio's command line, run as a separate program).

    from cadagent.slicer import slice_part
    r = slice_part('exports/base.3mf', workdir='build/slicer', overrides={'wall_loops': '3', 'sparse_infill_density': '15%'})
    r['grams'], r['minutes']

The slicer's own system profiles inherit from parent profiles; passed to the command line as they are, they leave
values such as the filament density unset (the slicer then reports 0 g). ``flatten`` resolves the whole chain into
one file per profile before slicing. Profiles are named as the slicer names them (printer, process, filament).

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
from typing import Dict, Optional

PRINTER = 'Bambu Lab P1S 0.4 nozzle'
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


def _index(kind: str) -> Dict[str, Path]:
    out = {}
    for f in (profile_root() / kind).glob('*.json'):
        try:
            n = json.loads(f.read_text()).get('name')
        except (json.JSONDecodeError, UnicodeDecodeError):
            continue
        if n:
            out[n] = f
    return out


def flatten(kind: str, name: str) -> dict:
    """A system profile with its whole ``inherits`` chain merged (child values win)."""
    idx = _index(kind)
    chain, seen = [], set()
    n = name
    while n:
        if n in seen or n not in idx:
            if n not in idx:
                raise KeyError(f'{kind} profile {n!r} not found under {profile_root() / kind}')
            break
        seen.add(n)
        d = json.loads(idx[n].read_text())
        chain.append(d)
        n = d.get('inherits')
    out = {}
    for d in reversed(chain):
        out.update(d)
    out.pop('inherits', None)
    out['name'] = name
    out['from'] = 'system'          # 'User' presets fail the CLI's printer compatibility check
    # the compatibility check matches the process's compatible_printers against the printer's settings id
    sid = {'machine': 'printer_settings_id', 'process': 'print_settings_id', 'filament': 'filament_settings_id'}[kind]
    out[sid] = [name] if kind == 'filament' else name
    return out


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
        shutil.rmtree(work)
    work.mkdir(parents=True)
    fil = FILAMENTS.get(filament, filament)
    mach, proc, fl = flatten('machine', printer), flatten('process', process), flatten('filament', fil)
    for k, v in (overrides or {}).items():
        proc[k] = v if isinstance(v, list) or k not in proc or not isinstance(proc[k], list) else [str(v)] * len(proc[k])
    paths = {}
    for key, d in (('machine', mach), ('process', proc), ('filament', fl)):
        paths[key] = work / f'{key}.json'
        paths[key].write_text(json.dumps(d, indent=1))
    out = work / 'out'
    out.mkdir()
    cmd = [exe, '--slice', '0', '--arrange', '1', '--orient', '0',
           '--load-settings', f"{paths['machine']};{paths['process']}", '--load-filaments', str(paths['filament']),
           '--outputdir', str(out), '--export-3mf', 'sliced.3mf', str(model)]
    p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    r = _read_result(out)
    r.update(model=str(model), printer=printer, process=process, filament=fil,
             overrides=dict(overrides or {}), exit_code=p.returncode,
             slicer=Path(exe).name, minutes=round(r.get('seconds', 0) / 60, 1) if r.get('seconds') else None)
    if not r.get('grams'):
        r['log_tail'] = (p.stdout + p.stderr)[-2000:]
    (work / 'result-summary.json').write_text(json.dumps(r, indent=2) + '\n')
    return r


def _sha(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def slice_project(project, parts=None) -> dict:
    """Slice each part's 3MF (``exports/<part>.3mf``) with the project's ``cad.slicer`` settings and write
    ``exports/slice-report.json``: grams and minutes per part, the totals, the settings, and each 3MF's sha256 so the
    report can tell a stale result from a current one.

    ``cad.slicer`` keys (all optional): printer, process, filament (``pla``, ``petg`` or a profile name), overrides
    (process settings, e.g. ``{wall_loops: "3"}``), parts (the parts to slice; default all)."""
    from cadagent.report import load_parts

    cfg = dict(project.slicer or {})
    known, error = load_parts(project)
    if error:
        raise FileNotFoundError(error)
    names = list(parts or cfg.get('parts') or known)
    work = project.root / 'build' / 'slicer'
    rows, total_g, total_min = {}, 0.0, 0.0
    for name in names:
        model = project.exports_dir / f'{name}.3mf'
        if not model.exists():
            rows[name] = {'error': f'{model.name} not found'}
            continue
        r = slice_part(model, workdir=work / name, printer=cfg.get('printer', PRINTER), process=cfg.get('process', PROCESS),
                       filament=cfg.get('filament', 'pla'), overrides=cfg.get('overrides'))
        r['sha256'] = _sha(model)
        rows[name] = {k: r.get(k) for k in ('grams', 'minutes', 'filament_m', 'error', 'sha256')}
        total_g += r.get('grams') or 0.0
        total_min += r.get('minutes') or 0.0
    out = {'slicer': 'Bambu Studio (command line)', 'printer': cfg.get('printer', PRINTER), 'process': cfg.get('process', PROCESS),
           'filament': FILAMENTS.get(cfg.get('filament', 'pla'), cfg.get('filament', 'pla')), 'overrides': cfg.get('overrides') or {},
           'parts': rows, 'total_grams': round(total_g, 1), 'total_hours': round(total_min / 60, 2),
           'pass': all(v.get('grams') for v in rows.values()),
           'note': 'Slicer estimates for one copy of each part with the stated profile; supports off unless the profile turns them on.'}
    path = project.exports_dir / 'slice-report.json'
    path.write_text(json.dumps(out, indent=2) + '\n')
    out['path'] = str(path)
    return out


def current_report(project) -> Optional[dict]:
    """The slice report when every sliced part's 3MF is unchanged since it was sliced, else None."""
    path = project.exports_dir / 'slice-report.json'
    if not path.exists():
        return None
    try:
        rep = json.loads(path.read_text())
    except json.JSONDecodeError:
        return None
    for name, row in rep.get('parts', {}).items():
        f = project.exports_dir / f'{name}.3mf'
        if not row.get('grams') or not f.exists() or _sha(f) != row.get('sha256'):
            return None
    return rep
